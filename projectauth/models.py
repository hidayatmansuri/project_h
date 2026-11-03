"""
Data models for projectauth (Section 4.2).
Keeps django.contrib.auth.models.User (Constraint C4 / Decision D1) and extends it
with UserProfile, per-app access control, 2FA factors, audit log, DB throttling,
session tracking, and singleton policy settings.
"""

from __future__ import annotations

from datetime import timedelta
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone

from .crypto import decrypt_str, encrypt, normalize_identifier


class UserProfile(models.Model):
    STATUS_PENDING_EMAIL = "pending_email"
    STATUS_PENDING_APPROVAL = "pending_approval"
    STATUS_ACTIVE = "active"
    STATUS_SUSPENDED = "suspended"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = [
        (STATUS_PENDING_EMAIL, "Pending email verification"),
        (STATUS_PENDING_APPROVAL, "Pending admin approval"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_SUSPENDED, "Suspended"),
        (STATUS_REJECTED, "Rejected"),
    ]

    CREATED_VIA_SIGNUP = "signup"
    CREATED_VIA_ADMIN = "admin"
    CREATED_VIA_INVITE = "invite"
    CREATED_VIA_LEGACY = "legacy"

    CREATED_VIA_CHOICES = [
        (CREATED_VIA_SIGNUP, "Self sign-up"),
        (CREATED_VIA_ADMIN, "Created by admin"),
        (CREATED_VIA_INVITE, "Admin invitation"),
        (CREATED_VIA_LEGACY, "Legacy migration"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    status = models.CharField(
        max_length=24,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING_EMAIL,
        db_index=True,
    )
    username_normalized = models.CharField(
        max_length=150,
        unique=True,
        db_index=True,
    )
    email_normalized = models.CharField(
        max_length=254,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
    )
    email_verified_at = models.DateTimeField(null=True, blank=True)
    must_change_password = models.BooleanField(default=False)
    password_changed_at = models.DateTimeField(null=True, blank=True)
    created_via = models.CharField(
        max_length=16,
        choices=CREATED_VIA_CHOICES,
        default=CREATED_VIA_SIGNUP,
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_user_profiles",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default="")
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        permissions = [
            ("manage_access", "Can approve users and grant or revoke app access"),
        ]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["email_normalized"]),
            models.Index(fields=["username_normalized"]),
        ]
        constraints = [
            models.UniqueConstraint(
                Lower("username_normalized"),
                name="pa_userprofile_username_lower_uniq",
            ),
            models.UniqueConstraint(
                Lower("email_normalized"),
                condition=Q(email_normalized__isnull=False) & ~Q(email_normalized=""),
                name="pa_userprofile_email_lower_uniq",
            ),
        ]

    def sync_from_user(self) -> None:
        if self.user_id and self.user:
            self.username_normalized = normalize_identifier(self.user.username)
            norm_email = normalize_identifier(self.user.email or "")
            self.email_normalized = norm_email if norm_email else None
            if norm_email and self.user.email != norm_email:
                self.user.email = norm_email

    def save(self, *args, **kwargs):
        self.sync_from_user()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Profile({self.username_normalized}, {self.status})"


class ProtectedApp(models.Model):
    app_label = models.CharField(max_length=100, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    icon = models.CharField(max_length=100, blank=True, default="fa-solid fa-cube")
    home_url_name = models.CharField(max_length=120, blank=True, default="")
    is_public = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.IntegerField(default=100)
    auto_discovered = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "name", "app_label"]
        indexes = [
            models.Index(fields=["is_public", "is_active", "sort_order"]),
        ]

    def save(self, *args, **kwargs):
        public_apps = set(getattr(settings, "PROJECTAUTH_PUBLIC_APPS", ["home", "cv"]))
        if self.app_label in public_apps:
            self.is_public = True
        else:
            # Changing public status requires a code deploy via PROJECTAUTH_PUBLIC_APPS (Section 9)
            self.is_public = False
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} ({self.app_label})"


class AppAccess(models.Model):
    LEVEL_FULL = "full"
    LEVEL_READ_ONLY = "read_only"

    LEVEL_CHOICES = [
        (LEVEL_FULL, "Full"),
        (LEVEL_READ_ONLY, "Read-only"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="app_access_grants",
    )
    app = models.ForeignKey(
        ProtectedApp,
        on_delete=models.CASCADE,
        related_name="access_grants",
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="granted_app_accesses",
    )
    granted_at = models.DateTimeField(default=timezone.now)
    level = models.CharField(
        max_length=20,
        choices=LEVEL_CHOICES,
        default=LEVEL_FULL,
    )
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True, db_index=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="revoked_app_accesses",
    )
    note = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-granted_at"]
        indexes = [
            models.Index(fields=["user", "app", "revoked_at"]),
            models.Index(fields=["app", "revoked_at", "expires_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "app"],
                condition=Q(revoked_at__isnull=True),
                name="pa_unique_active_user_app_access",
            ),
        ]

    def is_currently_active(self, now=None) -> bool:
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None:
            now = now or timezone.now()
            if self.expires_at <= now:
                return False
        return True

    def __str__(self) -> str:
        return f"AppAccess(user={self.user_id}, app={self.app.app_label}, level={self.level})"


class AccessRequest(models.Model):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_DENIED = "denied"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_DENIED, "Denied"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="access_requests",
    )
    app = models.ForeignKey(
        ProtectedApp,
        on_delete=models.CASCADE,
        related_name="access_requests",
    )
    message = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField(default=timezone.now)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="decided_access_requests",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["user", "app", "status"]),
        ]

    def __str__(self) -> str:
        return f"AccessRequest(user={self.user_id}, app={self.app.app_label}, status={self.status})"


class TOTPDevice(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="totp_devices",
    )
    name = models.CharField(max_length=100, default="Authenticator App")
    secret_encrypted = models.TextField()
    confirmed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_used_step = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["user", "confirmed_at"]),
        ]

    @property
    def aad(self) -> bytes:
        if not self.user_id:
            raise ValueError("TOTPDevice.user_id must be set before encrypting/decrypting secret.")
        return f"totp:{self.user_id}".encode("utf-8")

    def set_secret(self, raw_secret: str) -> None:
        self.secret_encrypted = encrypt(raw_secret, aad=self.aad)

    def get_secret(self) -> str:
        return decrypt_str(self.secret_encrypted, aad=self.aad)

    def __str__(self) -> str:
        state = "confirmed" if self.confirmed_at else "unconfirmed"
        return f"TOTPDevice(user={self.user_id}, {state})"


class CodeChallenge(models.Model):
    PURPOSE_LOGIN_2FA = "login_2fa"
    PURPOSE_REAUTH = "reauth"
    PURPOSE_VERIFY_EMAIL_NONCE = "verify_email_nonce"
    PURPOSE_PASSWORD_RESET_NONCE = "password_reset_nonce"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="code_challenges",
    )
    purpose = models.CharField(max_length=50, db_index=True)
    channel = models.CharField(max_length=20, default="email")
    code_hmac = models.CharField(max_length=64, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    consumed_at = models.DateTimeField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "purpose", "consumed_at", "expires_at"]),
            models.Index(fields=["purpose", "code_hmac"]),
        ]

    def is_valid(self, now=None, max_attempts: int = 5) -> bool:
        now = now or timezone.now()
        if self.consumed_at is not None:
            return False
        if self.expires_at <= now:
            return False
        if self.attempts >= max_attempts:
            return False
        return True


class RecoveryCode(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recovery_codes",
    )
    code_hmac = models.CharField(max_length=64, db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["user", "used_at"]),
        ]


class TrustedDevice(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="trusted_devices",
    )
    token_hmac = models.CharField(max_length=64, unique=True, db_index=True)
    user_agent = models.CharField(max_length=500, blank=True, default="")
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    last_used_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "expires_at"]),
        ]


class PendingEmailChange(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pending_email_changes",
    )
    new_email = models.EmailField(max_length=254)
    token_hmac = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(db_index=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "confirmed_at", "expires_at"]),
        ]


class AdminInvitation(models.Model):
    ROLE_ADMIN = "admin"
    ROLE_ACCESS_MANAGER = "access_manager"

    ROLE_CHOICES = [
        (ROLE_ADMIN, "Administrator"),
        (ROLE_ACCESS_MANAGER, "Access Manager"),
    ]

    email = models.EmailField(max_length=254, db_index=True)
    role = models.CharField(
        max_length=30,
        choices=ROLE_CHOICES,
        default=ROLE_ADMIN,
    )
    token_hmac = models.CharField(max_length=64, unique=True, db_index=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_admin_invitations",
    )
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(db_index=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="accepted_admin_invitations",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["email", "accepted_at", "expires_at"]),
        ]


class AuditEvent(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events_performed",
    )
    actor_label = models.CharField(max_length=150, blank=True, default="")
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events_targeted",
    )
    target_label = models.CharField(max_length=150, blank=True, default="")
    action = models.CharField(max_length=100, db_index=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True, default="")
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["actor", "created_at"]),
            models.Index(fields=["target_user", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"AuditEvent({self.action} at {self.created_at.isoformat()})"


class SessionRecord(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="session_records",
    )
    session_key_hash = models.CharField(max_length=64, unique=True, db_index=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-last_seen_at"]
        indexes = [
            models.Index(fields=["user", "revoked_at", "last_seen_at"]),
        ]


class Throttle(models.Model):
    scope = models.CharField(max_length=64, db_index=True)
    key_hmac = models.CharField(max_length=64, db_index=True)
    count = models.PositiveIntegerField(default=0)
    window_started_at = models.DateTimeField(default=timezone.now)
    locked_until = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["scope", "key_hmac"]),
            models.Index(fields=["locked_until"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "key_hmac"],
                name="pa_unique_throttle_scope_key",
            ),
        ]


class AuthSettings(models.Model):
    SIGNUP_OPEN_APPROVAL = "open_with_approval"
    SIGNUP_INVITE_ONLY = "invite_only"
    SIGNUP_ADMIN_ONLY = "admin_only"

    SIGNUP_MODE_CHOICES = [
        (SIGNUP_OPEN_APPROVAL, "Open sign-up (requires admin approval)"),
        (SIGNUP_INVITE_ONLY, "Invite only"),
        (SIGNUP_ADMIN_ONLY, "Admin created only"),
    ]

    signup_mode = models.CharField(
        max_length=32,
        choices=SIGNUP_MODE_CHOICES,
        default=SIGNUP_OPEN_APPROVAL,
    )
    require_2fa_for_admins = models.BooleanField(default=True)
    require_2fa_for_all = models.BooleanField(default=False)
    twofa_grace_days = models.PositiveSmallIntegerField(default=0)
    notify_admins_on_signup = models.BooleanField(default=True)
    admin_notify_emails = models.TextField(blank=True, default="")
    allowed_email_domains = models.TextField(blank=True, default="")
    blocked_email_domains = models.TextField(blank=True, default="")
    admin_idle_timeout_min = models.PositiveIntegerField(default=30)
    user_idle_timeout_hours = models.PositiveIntegerField(default=12)
    password_min_length = models.PositiveSmallIntegerField(default=12)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Auth Settings"
        verbose_name_plural = "Auth Settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "AuthSettings":
        default_notify = getattr(settings, "PROJECTAUTH_ADMIN_NOTIFY_EMAILS", "")
        if isinstance(default_notify, (list, tuple)):
            default_notify = ",".join(default_notify)
        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={
                "signup_mode": getattr(
                    settings, "PROJECTAUTH_DEFAULT_SIGNUP_MODE", cls.SIGNUP_OPEN_APPROVAL
                ),
                "require_2fa_for_admins": getattr(
                    settings, "PROJECTAUTH_REQUIRE_2FA_FOR_ADMINS", True
                ),
                "require_2fa_for_all": getattr(
                    settings, "PROJECTAUTH_REQUIRE_2FA_FOR_ALL", False
                ),
                "notify_admins_on_signup": True,
                "admin_notify_emails": default_notify or "",
                "admin_idle_timeout_min": getattr(
                    settings, "PROJECTAUTH_ADMIN_IDLE_TIMEOUT_MIN", 30
                ),
                "user_idle_timeout_hours": getattr(
                    settings, "PROJECTAUTH_USER_IDLE_TIMEOUT_HOURS", 12
                ),
                "password_min_length": getattr(
                    settings, "PROJECTAUTH_PASSWORD_MIN_LENGTH", 12
                ),
            },
        )
        return obj

