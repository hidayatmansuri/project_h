"""
Admin Console and Admin Invitation views for projectauth (Phase 5, Section 8 & 12).
All screens render through projectauth/templates/projectauth.html switched by `mode`.
"""

from __future__ import annotations

import csv
import hashlib
import json
import secrets
from datetime import datetime, time, timedelta
from datetime import timezone as dt_timezone
from functools import wraps
from typing import List, Optional, Sequence, Tuple
from urllib.parse import quote

from axes.models import AccessAttempt
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.db.models.functions import Lower
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import patch_cache_control
from django.utils.dateparse import parse_date, parse_datetime
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import twofa
from .access import user_is_access_manager, user_is_active_admin
from .audit import log_audit
from .crypto import has_configured_encryption_keys, hmac_sha256, normalize_identifier
from .email_service import (
    build_absolute_url,
    get_daily_email_status,
    send_projectauth_email,
)
from .forms import USERNAME_RE, AuthSettingsForm, InviteAcceptForm, validate_email_domain_policy
from .models import (
    AccessRequest,
    AdminInvitation,
    AppAccess,
    AuditEvent,
    AuthSettings,
    ProtectedApp,
    RecoveryCode,
    SessionRecord,
    Throttle,
    TOTPDevice,
    UserProfile,
)
from .sessions import revoke_all_user_sessions
from .tokens import create_password_reset_token, mask_email
from .views import (
    count_active_admins,
    is_last_active_admin,
    is_sudo_active,
    mark_sudo_verified,
    render_projectauth,
)

User = get_user_model()

ACCESS_MANAGERS_GROUP_NAME = "Access Managers"
SPECIAL_CHARS = "!£$%^&*+#~@"
INVITE_EXPIRY_HOURS = 72


def ensure_access_managers_group() -> Group:
    """
    Ensures the 'Access Managers' Django Group exists and holds the
    'projectauth.manage_access' permission (Section 4.2).
    """
    group, _ = Group.objects.get_or_create(name=ACCESS_MANAGERS_GROUP_NAME)
    ct = ContentType.objects.get_for_model(UserProfile)
    perm, _ = Permission.objects.get_or_create(
        codename="manage_access",
        content_type=ct,
        defaults={"name": "Can approve users and grant or revoke app access"},
    )
    if not group.permissions.filter(pk=perm.pk).exists():
        group.permissions.add(perm)
    return group


def generate_strong_password(length: int = 16) -> str:
    """
    Generates a cryptographically random password using `secrets` and the project's
    special character set `!£$%^&*+#~@` (Section 3, 7, 8.2, 8.3).
    """
    length = max(16, int(length))
    upper = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    lower = "abcdefghijkmnopqrstuvwxyz"
    digits = "23456789"
    all_chars = upper + lower + digits + SPECIAL_CHARS
    chars = [
        secrets.choice(upper),
        secrets.choice(lower),
        secrets.choice(digits),
        secrets.choice(SPECIAL_CHARS),
    ]
    chars.extend(secrets.choice(all_chars) for _ in range(length - len(chars)))
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def _console_denied_response(request: HttpRequest, title: str = "Admin Console") -> HttpResponse:
    log_audit(
        "console.denied",
        request=request,
        actor=request.user if request.user.is_authenticated else None,
        details={"path": request.path},
    )
    return render_projectauth(
        request,
        "access_denied",
        {
            "denied_app_label": "console",
            "denied_app_name": title,
            "reason_code": "denied_no_grant",
            "reason_message": "You do not have permission to open this administration screen.",
        },
        status=403,
    )


def console_access_required(view_func):
    """
    Allows active Admins AND Access Managers (Section 4.2 & 8).
    Anonymous users redirect to login; regular authenticated users receive 403.
    """

    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if not request.user.is_authenticated:
            login_url = reverse("projectauth:login")
            return redirect(f"{login_url}?next={quote(request.get_full_path(), safe='/:?&=')}")
        if not user_is_access_manager(request.user):
            return _console_denied_response(request, "Admin Console")
        return view_func(request, *args, **kwargs)

    return _wrapped


def console_admin_required(view_func):
    """
    Allows ONLY active Admins (`is_superuser=True` and `is_staff=True`).
    Access Managers and regular users receive 403 (Section 4.2 & 8).
    """

    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if not request.user.is_authenticated:
            login_url = reverse("projectauth:login")
            return redirect(f"{login_url}?next={quote(request.get_full_path(), safe='/:?&=')}")
        if not user_is_active_admin(request.user):
            return _console_denied_response(request, "Admin Console (Administrator Only)")
        return view_func(request, *args, **kwargs)

    return _wrapped


def _check_or_verify_sudo(request: HttpRequest) -> bool:
    """
    Returns True if sudo mode is active in session OR if the current POST includes
    a valid `sudo_password` for `request.user` (which also activates sudo mode).
    """
    if is_sudo_active(request):
        return True
    sudo_pw = request.POST.get("sudo_password") or ""
    if sudo_pw and request.user.is_authenticated and request.user.check_password(sudo_pw):
        mark_sudo_verified(request)
        return True
    return False


def _parse_access_level_and_expiry(post_data) -> Tuple[str, Optional[datetime]]:
    """
    Extracts `(level, expires_at)` from POST data, supporting:
    - `preset="tester"` -> `level="read_only"`, `expires_at = now + 7 days` (Section 8.1)
    - `level` in `("full", "read_only")`
    - `expires_days` integer OR `expires_at` ISO/date string
    """
    now = timezone.now()
    preset = (post_data.get("preset") or "").strip().lower()
    if preset == "tester":
        return AppAccess.LEVEL_READ_ONLY, now + timedelta(days=7)

    raw_level = (post_data.get("level") or AppAccess.LEVEL_FULL).strip()
    level = (
        AppAccess.LEVEL_READ_ONLY
        if raw_level == AppAccess.LEVEL_READ_ONLY
        else AppAccess.LEVEL_FULL
    )

    expires_days = (post_data.get("expires_days") or "").strip()
    if expires_days and expires_days.isdigit() and int(expires_days) > 0:
        return level, now + timedelta(days=int(expires_days))

    raw_expires = (post_data.get("expires_at") or "").strip()
    if not raw_expires:
        return level, None

    dt = parse_datetime(raw_expires)
    if dt is not None:
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, dt_timezone.utc)
        return level, dt

    d = parse_date(raw_expires)
    if d is not None:
        dt = datetime.combine(d, time(23, 59, 59), tzinfo=dt_timezone.utc)
        return level, dt

    return level, None


def grant_or_update_app_access(
    actor,
    target_user,
    app_obj: ProtectedApp,
    *,
    level: str = AppAccess.LEVEL_FULL,
    expires_at: Optional[datetime] = None,
    note: str = "",
    request: Optional[HttpRequest] = None,
    send_email: bool = True,
) -> AppAccess:
    """
    Grants or updates an active AppAccess row for `(target_user, app_obj)`, resolves any
    pending AccessRequest, audits `access.grant`, and optionally emails the user.
    """
    now = timezone.now()
    with transaction.atomic():
        grant = (
            AppAccess.objects.select_for_update()
            .filter(user=target_user, app=app_obj, revoked_at__isnull=True)
            .first()
        )
        if grant is None:
            grant = AppAccess.objects.create(
                user=target_user,
                app=app_obj,
                granted_by=actor,
                granted_at=now,
                level=level,
                expires_at=expires_at,
                note=note[:255],
            )
        else:
            grant.granted_by = actor
            grant.granted_at = now
            grant.level = level
            grant.expires_at = expires_at
            if note:
                grant.note = note[:255]
            grant.save(
                update_fields=["granted_by", "granted_at", "level", "expires_at", "note"]
            )

        AccessRequest.objects.filter(
            user=target_user,
            app=app_obj,
            status=AccessRequest.STATUS_PENDING,
        ).update(
            status=AccessRequest.STATUS_APPROVED,
            decided_by=actor,
            decided_at=now,
            decision_note=note or f"Granted {level} access.",
        )

    log_audit(
        "access.grant",
        request=request,
        actor=actor,
        target_user=target_user,
        details={
            "app": app_obj.app_label,
            "level": level,
            "expires_at": expires_at.isoformat() if expires_at else None,
        },
    )

    if send_email and target_user.email:
        send_projectauth_email(
            "access_granted",
            [target_user.email],
            context={
                "username": target_user.username,
                "app_name": app_obj.name,
                "app_label": app_obj.app_label,
                "level": dict(AppAccess.LEVEL_CHOICES).get(level, level),
                "expires_at": (
                    expires_at.strftime("%d %b %Y %H:%M UTC") if expires_at else "No expiry"
                ),
                "action_url": build_absolute_url(reverse("home")),
            },
        )
    return grant


def revoke_app_access(
    actor,
    target_user,
    app_obj: ProtectedApp,
    *,
    request: Optional[HttpRequest] = None,
    send_email: bool = True,
) -> int:
    """
    Revokes active AppAccess for `(target_user, app_obj)`, audits `access.revoke`,
    and optionally emails the user.
    """
    now = timezone.now()
    updated = AppAccess.objects.filter(
        user=target_user,
        app=app_obj,
        revoked_at__isnull=True,
    ).update(revoked_at=now, revoked_by=actor)

    if updated:
        log_audit(
            "access.revoke",
            request=request,
            actor=actor,
            target_user=target_user,
            details={"app": app_obj.app_label},
        )
        if send_email and target_user.email:
            send_projectauth_email(
                "access_revoked",
                [target_user.email],
                context={
                    "username": target_user.username,
                    "app_name": app_obj.name,
                    "app_label": app_obj.app_label,
                },
            )
    return updated


def _approve_user_account(
    actor,
    target_user,
    *,
    app_labels: Sequence[str] = (),
    level: str = AppAccess.LEVEL_FULL,
    expires_at: Optional[datetime] = None,
    request: Optional[HttpRequest] = None,
) -> List[str]:
    """
    Approves a pending/rejected user account, grants selected apps, resolves pending
    AccessRequests, audits `user.approved`, and sends `account_approved`.
    """
    now = timezone.now()
    profile, _ = UserProfile.objects.get_or_create(
        user=target_user,
        defaults={
            "username_normalized": normalize_identifier(target_user.username),
            "email_normalized": normalize_identifier(target_user.email or "") or None,
        },
    )

    with transaction.atomic():
        target_user.is_active = True
        target_user.save(update_fields=["is_active"])

        profile.status = UserProfile.STATUS_ACTIVE
        profile.approved_by = actor
        profile.approved_at = now
        if not profile.email_verified_at:
            profile.email_verified_at = now
        profile.rejection_reason = ""
        profile.save(
            update_fields=[
                "status",
                "approved_by",
                "approved_at",
                "email_verified_at",
                "rejection_reason",
            ]
        )

        granted_names: List[str] = []
        clean_labels = [str(lbl).strip() for lbl in app_labels if str(lbl).strip()]
        if clean_labels:
            apps_to_grant = list(
                ProtectedApp.objects.filter(
                    app_label__in=clean_labels,
                    is_public=False,
                )
            )
            for app_obj in apps_to_grant:
                grant_or_update_app_access(
                    actor,
                    target_user,
                    app_obj,
                    level=level,
                    expires_at=expires_at,
                    note="Granted on account approval",
                    request=request,
                    send_email=False,
                )
                granted_names.append(app_obj.name)

    log_audit(
        "user.approved",
        request=request,
        actor=actor,
        target_user=target_user,
        details={
            "granted_apps": clean_labels,
            "level": level,
            "expires_at": expires_at.isoformat() if expires_at else None,
        },
    )

    if target_user.email:
        send_projectauth_email(
            "account_approved",
            [target_user.email],
            context={
                "username": target_user.username,
                "granted_apps": ", ".join(granted_names) if granted_names else "None yet",
                "action_url": build_absolute_url(reverse("projectauth:login")),
            },
        )
    return granted_names


def _reject_user_account(
    actor,
    target_user,
    *,
    reason: str = "",
    request: Optional[HttpRequest] = None,
) -> None:
    now = timezone.now()
    profile, _ = UserProfile.objects.get_or_create(
        user=target_user,
        defaults={
            "username_normalized": normalize_identifier(target_user.username),
            "email_normalized": normalize_identifier(target_user.email or "") or None,
        },
    )
    with transaction.atomic():
        target_user.is_active = False
        target_user.save(update_fields=["is_active"])
        profile.status = UserProfile.STATUS_REJECTED
        profile.rejection_reason = (reason or "").strip()
        profile.save(update_fields=["status", "rejection_reason"])
        AccessRequest.objects.filter(
            user=target_user,
            status=AccessRequest.STATUS_PENDING,
        ).update(
            status=AccessRequest.STATUS_DENIED,
            decided_by=actor,
            decided_at=now,
            decision_note=profile.rejection_reason or "Account rejected.",
        )
        revoke_all_user_sessions(target_user)

    log_audit(
        "user.rejected",
        request=request,
        actor=actor,
        target_user=target_user,
        details={"reason": profile.rejection_reason[:200]},
    )
    if target_user.email:
        send_projectauth_email(
            "account_rejected",
            [target_user.email],
            context={
                "username": target_user.username,
                "reason": profile.rejection_reason,
            },
        )


def _console_common_context(request: HttpRequest) -> dict:
    return {
        "is_console": True,
        "viewer_is_admin": user_is_active_admin(request.user),
        "viewer_is_access_manager": user_is_access_manager(request.user),
        "pending_users_badge": UserProfile.objects.filter(
            status__in=[
                UserProfile.STATUS_PENDING_APPROVAL,
                UserProfile.STATUS_PENDING_EMAIL,
            ]
        ).count(),
        "pending_requests_badge": AccessRequest.objects.filter(
            status=AccessRequest.STATUS_PENDING
        ).count(),
    }


# ---------------------------------------------------------------------------
# 8.1 Dashboard (`auth/console/`)
# ---------------------------------------------------------------------------


@never_cache
@console_access_required
@require_GET
def console_dashboard_view(request: HttpRequest) -> HttpResponse:
    now = timezone.now()
    failure_limit = int(getattr(settings, "AXES_FAILURE_LIMIT", 5))
    axes_locked = AccessAttempt.objects.filter(failures_since_start__gte=failure_limit).count()
    throttle_locked = Throttle.objects.filter(locked_until__gt=now).count()

    counts = {
        "pending_users": UserProfile.objects.filter(
            status__in=[
                UserProfile.STATUS_PENDING_APPROVAL,
                UserProfile.STATUS_PENDING_EMAIL,
            ]
        ).count(),
        "pending_approval": UserProfile.objects.filter(
            status=UserProfile.STATUS_PENDING_APPROVAL
        ).count(),
        "pending_requests": AccessRequest.objects.filter(
            status=AccessRequest.STATUS_PENDING
        ).count(),
        "active_users": UserProfile.objects.filter(
            status=UserProfile.STATUS_ACTIVE,
            user__is_active=True,
        ).count(),
        "admins": count_active_admins(),
        "locked_accounts": axes_locked + throttle_locked,
    }

    health_warnings: List[dict] = []

    # 1. Check if at least one active admin has confirmed 2FA enrolled
    admin_with_2fa = TOTPDevice.objects.filter(
        user__is_superuser=True,
        user__is_staff=True,
        user__is_active=True,
        confirmed_at__isnull=False,
    ).exists()
    if not admin_with_2fa:
        health_warnings.append(
            {
                "code": "no_admin_2fa",
                "level": "warning",
                "message": "No administrator currently has an authenticator app (2FA) enrolled.",
            }
        )

    # 2. Check if console email backend is active
    email_backend = str(getattr(settings, "EMAIL_BACKEND", ""))
    if "console" in email_backend.lower():
        health_warnings.append(
            {
                "code": "console_email_backend",
                "level": "danger" if not getattr(settings, "DEBUG", False) else "warning",
                "message": (
                    "Email backend is set to console. Emails are printed to stdout and are not sent via SMTP."
                ),
            }
        )

    # 3. Check if explicit encryption key is configured
    if not has_configured_encryption_keys():
        health_warnings.append(
            {
                "code": "dev_encryption_key",
                "level": "warning",
                "message": (
                    "PROJECTAUTH_ENCRYPTION_KEYS is not configured; using a development fallback key derived from SECRET_KEY."
                ),
            }
        )

    # 4. Daily email budget warning at 80% or exhausted (Section 10 & 15)
    budget = get_daily_email_status()
    if budget["exhausted"]:
        health_warnings.append(
            {
                "code": "email_budget_exhausted",
                "level": "danger",
                "message": (
                    f"Daily email budget exhausted ({budget['sent_today']}/{budget['daily_cap']}). "
                    "Outgoing emails are paused until 00:00 UTC."
                ),
            }
        )
    elif budget["warning_80"]:
        health_warnings.append(
            {
                "code": "email_budget_80",
                "level": "warning",
                "message": (
                    f"Daily email budget has reached {budget['percent']}% "
                    f"({budget['sent_today']}/{budget['daily_cap']} sent today)."
                ),
            }
        )

    recent_audit = AuditEvent.objects.select_related("actor", "target_user")[:20]

    ctx = _console_common_context(request)
    ctx.update(
        {
            "counts": counts,
            "health_warnings": health_warnings,
            "email_budget": budget,
            "recent_audit": recent_audit,
        }
    )
    return render_projectauth(request, "console_dashboard", ctx)


# ---------------------------------------------------------------------------
# 8.1 Pending Approvals (`auth/console/pending/`)
# ---------------------------------------------------------------------------


@never_cache
@console_access_required
@require_http_methods(["GET", "POST"])
def console_pending_view(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        pending_action = (request.POST.get("pending_action") or "").strip()
        uid = request.POST.get("user_id") or ""
        target_user = get_object_or_404(User.objects.select_related("profile"), pk=uid)

        if pending_action == "approve":
            app_labels = request.POST.getlist("app_labels")
            level, expires_at = _parse_access_level_and_expiry(request.POST)
            granted = _approve_user_account(
                request.user,
                target_user,
                app_labels=app_labels,
                level=level,
                expires_at=expires_at,
                request=request,
            )
            apps_note = f" Granted apps: {', '.join(granted)}." if granted else " (No app access granted yet.)"
            messages.success(request, f"Approved account '{target_user.username}'.{apps_note}")
            return redirect("projectauth:console_pending")

        elif pending_action == "reject":
            reason = (request.POST.get("reason") or "").strip()
            _reject_user_account(
                request.user,
                target_user,
                reason=reason,
                request=request,
            )
            messages.info(request, f"Rejected account '{target_user.username}'.")
            return redirect("projectauth:console_pending")

    pending_profiles = list(
        UserProfile.objects.filter(
            status__in=[
                UserProfile.STATUS_PENDING_APPROVAL,
                UserProfile.STATUS_PENDING_EMAIL,
            ]
        )
        .select_related("user")
        .order_by("created_at")
    )
    governed_apps = list(
        ProtectedApp.objects.filter(is_public=False, is_active=True).order_by("sort_order", "name")
    )

    user_ids = [p.user_id for p in pending_profiles]
    req_by_user: dict[int, set[str]] = {uid: set() for uid in user_ids}
    for req in AccessRequest.objects.filter(
        user_id__in=user_ids,
        status=AccessRequest.STATUS_PENDING,
    ).select_related("app"):
        req_by_user.setdefault(req.user_id, set()).add(req.app.app_label)

    pending_items = [
        {
            "profile": p,
            "user": p.user,
            "requested_app_labels": req_by_user.get(p.user_id, set()),
        }
        for p in pending_profiles
    ]

    ctx = _console_common_context(request)
    ctx.update(
        {
            "pending_items": pending_items,
            "governed_apps": governed_apps,
        }
    )
    return render_projectauth(request, "console_pending", ctx)


# ---------------------------------------------------------------------------
# 8.1 Users List & User Detail (`auth/console/users/`, `auth/console/users/<id>/`)
# ---------------------------------------------------------------------------


@never_cache
@console_access_required
@require_GET
def console_users_view(request: HttpRequest) -> HttpResponse:
    q = (request.GET.get("q") or "").strip()
    status_filter = (request.GET.get("status") or "").strip()
    role_filter = (request.GET.get("role") or "").strip()

    qs = User.objects.select_related("profile").order_by("-date_joined", "-id")
    if q:
        qs = qs.filter(
            Q(username__icontains=q)
            | Q(email__icontains=q)
            | Q(profile__username_normalized__icontains=q.lower())
            | Q(profile__email_normalized__icontains=q.lower())
        )
    if status_filter:
        qs = qs.filter(profile__status=status_filter)
    if role_filter == "admin":
        qs = qs.filter(is_superuser=True, is_staff=True)
    elif role_filter == "access_manager":
        qs = qs.filter(groups__name=ACCESS_MANAGERS_GROUP_NAME).distinct()
    elif role_filter == "user":
        qs = qs.filter(is_superuser=False).exclude(groups__name=ACCESS_MANAGERS_GROUP_NAME)

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    ctx = _console_common_context(request)
    ctx.update(
        {
            "page_obj": page_obj,
            "users_list": page_obj.object_list,
            "q": q,
            "status_filter": status_filter,
            "role_filter": role_filter,
            "status_choices": UserProfile.STATUS_CHOICES,
        }
    )
    return render_projectauth(request, "console_users", ctx)


@never_cache
@console_access_required
@require_http_methods(["GET", "POST"])
def console_user_detail_view(request: HttpRequest, user_id: int) -> HttpResponse:
    target_user = get_object_or_404(User.objects.select_related("profile"), pk=user_id)
    profile, _ = UserProfile.objects.get_or_create(
        user=target_user,
        defaults={
            "username_normalized": normalize_identifier(target_user.username),
            "email_normalized": normalize_identifier(target_user.email or "") or None,
            "status": UserProfile.STATUS_ACTIVE if target_user.is_active else UserProfile.STATUS_PENDING_EMAIL,
        },
    )

    actor_is_admin = user_is_active_admin(request.user)
    target_is_admin = bool(target_user.is_superuser and target_user.is_staff)

    if request.method == "POST":
        user_action = (request.POST.get("user_action") or "").strip()

        # Access managers cannot modify admin accounts or run admin-only credential/delete actions
        admin_only_actions = {
            "reset_2fa",
            "send_reset_link",
            "set_temp_password",
            "edit_identity",
            "delete_user",
        }
        if not actor_is_admin and (target_is_admin or user_action in admin_only_actions):
            return _console_denied_response(request, "Admin Console (Administrator Only)")

        # Changing another admin's credentials or deleting a user requires sudo re-auth (Section 8.3)
        sensitive_admin_target = target_is_admin and target_user.pk != request.user.pk
        if user_action in ("reset_2fa", "send_reset_link", "set_temp_password", "edit_identity") and sensitive_admin_target:
            if not _check_or_verify_sudo(request):
                messages.info(
                    request,
                    "Re-authentication is required before modifying another administrator's credentials.",
                )
                next_url = reverse("projectauth:console_user_detail", kwargs={"user_id": target_user.pk})
                return redirect(f"{reverse('projectauth:reauth')}?next={next_url}")

        if user_action == "approve":
            app_labels = request.POST.getlist("app_labels")
            level, expires_at = _parse_access_level_and_expiry(request.POST)
            _approve_user_account(
                request.user,
                target_user,
                app_labels=app_labels,
                level=level,
                expires_at=expires_at,
                request=request,
            )
            messages.success(request, f"Account '{target_user.username}' approved.")

        elif user_action == "reject":
            reason = (request.POST.get("reason") or "").strip()
            _reject_user_account(
                request.user,
                target_user,
                reason=reason,
                request=request,
            )
            messages.info(request, f"Account '{target_user.username}' rejected.")

        elif user_action == "suspend":
            if is_last_active_admin(target_user):
                log_audit(
                    "admin.last_admin_protected",
                    request=request,
                    actor=request.user,
                    target_user=target_user,
                    details={"attempted_action": "suspend"},
                )
                messages.error(
                    request,
                    "Refused: cannot suspend the last active administrator account.",
                )
            else:
                target_user.is_active = False
                target_user.save(update_fields=["is_active"])
                profile.status = UserProfile.STATUS_SUSPENDED
                profile.save(update_fields=["status"])
                revoke_all_user_sessions(target_user)
                log_audit(
                    "user.suspended",
                    request=request,
                    actor=request.user,
                    target_user=target_user,
                )
                messages.warning(request, f"Account '{target_user.username}' has been suspended.")

        elif user_action == "reactivate":
            target_user.is_active = True
            target_user.save(update_fields=["is_active"])
            profile.status = UserProfile.STATUS_ACTIVE
            profile.save(update_fields=["status"])
            log_audit(
                "user.reactivated",
                request=request,
                actor=request.user,
                target_user=target_user,
            )
            messages.success(request, f"Account '{target_user.username}' has been reactivated.")

        elif user_action == "unlock":
            identifiers = {
                target_user.username,
                normalize_identifier(target_user.username),
            }
            if target_user.email:
                identifiers.add(target_user.email)
                identifiers.add(normalize_identifier(target_user.email))
            AccessAttempt.objects.filter(username__in=identifiers).delete()
            Throttle.objects.filter(locked_until__isnull=False).update(locked_until=None, count=0)
            log_audit(
                "user.unlocked",
                request=request,
                actor=request.user,
                target_user=target_user,
            )
            messages.success(request, f"Cleared lockout counters for '{target_user.username}'.")

        elif user_action == "force_signout":
            revoked_count = revoke_all_user_sessions(target_user)
            log_audit(
                "user.force_signout",
                request=request,
                actor=request.user,
                target_user=target_user,
                details={"revoked_sessions": revoked_count},
            )
            messages.success(
                request,
                f"Signed '{target_user.username}' out of {revoked_count} active session(s).",
            )

        elif user_action == "reset_2fa":
            summary = twofa.reset_user_2fa(target_user, actor=request.user, request=request)
            messages.success(
                request,
                f"Reset 2FA for '{target_user.username}' (removed {summary['totp_deleted']} TOTP device(s)).",
            )

        elif user_action == "send_reset_link":
            if not target_user.email:
                messages.error(request, "This user does not have an email address configured.")
            else:
                token = create_password_reset_token(target_user)
                reset_url = build_absolute_url(
                    reverse("projectauth:reset_password", kwargs={"token": token})
                )
                send_projectauth_email(
                    "password_reset",
                    [target_user.email],
                    context={
                        "username": target_user.username,
                        "action_url": reset_url,
                        "expires_minutes": 60,
                    },
                )
                log_audit(
                    "admin.password_reset_sent",
                    request=request,
                    actor=request.user,
                    target_user=target_user,
                )
                messages.success(
                    request,
                    f"Sent password reset link to {mask_email(target_user.email)}.",
                )

        elif user_action == "set_temp_password":
            temp_pw = generate_strong_password(16)
            now = timezone.now()
            target_user.set_password(temp_pw)
            target_user.save(update_fields=["password"])
            profile.must_change_password = True
            profile.password_changed_at = now
            profile.save(update_fields=["must_change_password", "password_changed_at"])
            revoke_all_user_sessions(target_user)

            # Store once in session so it is displayed once and never logged/stored in DB (Section 8.3)
            request.session["pa_temp_password_once"] = {
                "user_id": target_user.pk,
                "username": target_user.username,
                "password": temp_pw,
            }
            if target_user.email:
                send_projectauth_email(
                    "password_changed",
                    [target_user.email],
                    context={
                        "username": target_user.username,
                        "message": (
                            "An administrator set a temporary password on your account. "
                            "You will be required to choose a new password on your next sign-in."
                        ),
                    },
                )
            log_audit(
                "admin.temp_password_set",
                request=request,
                actor=request.user,
                target_user=target_user,
            )
            messages.success(
                request,
                f"Temporary password generated for '{target_user.username}'. Copy it below — it will only be shown once.",
            )

        elif user_action == "edit_identity":
            new_uname = normalize_identifier(request.POST.get("username") or target_user.username)
            new_email = normalize_identifier(request.POST.get("email") or target_user.email or "")

            if len(new_uname) < 3 or not USERNAME_RE.match(new_uname):
                messages.error(request, "Invalid username format.")
                return redirect("projectauth:console_user_detail", user_id=target_user.pk)

            uname_conflict = (
                User.objects.annotate(_ul=Lower("username"))
                .filter(Q(_ul=new_uname) | Q(profile__username_normalized=new_uname))
                .exclude(pk=target_user.pk)
                .exists()
            )
            if uname_conflict:
                messages.error(request, f"Username '{new_uname}' is already taken.")
                return redirect("projectauth:console_user_detail", user_id=target_user.pk)

            if new_email:
                email_conflict = (
                    User.objects.annotate(_el=Lower("email"))
                    .filter(Q(_el=new_email) | Q(profile__email_normalized=new_email))
                    .exclude(pk=target_user.pk)
                    .exists()
                )
                if email_conflict:
                    messages.error(request, "That email address is already used by another account.")
                    return redirect("projectauth:console_user_detail", user_id=target_user.pk)

            old_uname = target_user.username
            old_email = target_user.email or ""
            target_user.username = new_uname
            target_user.email = new_email
            target_user.save(update_fields=["username", "email"])
            profile.username_normalized = new_uname
            profile.email_normalized = new_email or None
            profile.save(update_fields=["username_normalized", "email_normalized"])

            log_audit(
                "admin.user_identity_edited",
                request=request,
                actor=request.user,
                target_user=target_user,
                details={
                    "old_username": old_uname,
                    "new_username": new_uname,
                    "old_email": mask_email(old_email) if old_email else "",
                    "new_email": mask_email(new_email) if new_email else "",
                },
            )
            if sensitive_admin_target and (old_email or new_email):
                send_projectauth_email(
                    "password_changed",
                    [e for e in {old_email, new_email} if e],
                    context={
                        "username": new_uname,
                        "message": f"An administrator ({request.user.username}) updated your account username/email.",
                    },
                )
            messages.success(request, f"Updated identity details for '{new_uname}'.")

        elif user_action in ("grant_app", "tester_preset"):
            app_label = (request.POST.get("app_label") or "").strip()
            app_obj = get_object_or_404(ProtectedApp, app_label=app_label, is_public=False)
            if user_action == "tester_preset":
                level = AppAccess.LEVEL_READ_ONLY
                expires_at = timezone.now() + timedelta(days=7)
            else:
                level, expires_at = _parse_access_level_and_expiry(request.POST)
            grant_or_update_app_access(
                request.user,
                target_user,
                app_obj,
                level=level,
                expires_at=expires_at,
                note=(request.POST.get("note") or "").strip(),
                request=request,
            )
            messages.success(
                request,
                f"Granted '{target_user.username}' {level} access to {app_obj.name}.",
            )

        elif user_action == "revoke_app":
            app_label = (request.POST.get("app_label") or "").strip()
            app_obj = get_object_or_404(ProtectedApp, app_label=app_label)
            revoke_app_access(request.user, target_user, app_obj, request=request)
            messages.info(
                request,
                f"Revoked '{target_user.username}' access to {app_obj.name}.",
            )

        elif user_action == "delete_user":
            if is_last_active_admin(target_user):
                log_audit(
                    "admin.last_admin_protected",
                    request=request,
                    actor=request.user,
                    target_user=target_user,
                    details={"attempted_action": "delete_user"},
                )
                messages.error(
                    request,
                    "Refused: cannot delete the last active administrator account.",
                )
                return redirect("projectauth:console_user_detail", user_id=target_user.pk)

            anon_tag = "deleted-user-" + hashlib.sha256(
                f"{target_user.pk}:{target_user.username}".encode("utf-8")
            ).hexdigest()[:8]
            target_email = target_user.email
            target_uname = target_user.username

            with transaction.atomic():
                AuditEvent.objects.filter(actor=target_user).update(
                    actor=None, actor_label=anon_tag
                )
                AuditEvent.objects.filter(target_user=target_user).update(
                    target_user=None, target_label=anon_tag
                )
                log_audit(
                    "admin.user_deleted",
                    request=request,
                    actor=request.user,
                    target_label=anon_tag,
                )
                target_user.delete()

            if target_email:
                send_projectauth_email(
                    "account_deleted",
                    [target_email],
                    context={"username": target_uname},
                )
            messages.success(request, f"Deleted user '{target_uname}' and anonymised audit records.")
            return redirect("projectauth:console_users")

        return redirect("projectauth:console_user_detail", user_id=target_user.pk)

    temp_pw_once = None
    popped = request.session.pop("pa_temp_password_once", None)
    if popped and popped.get("user_id") == target_user.pk:
        temp_pw_once = popped.get("password")

    governed_apps = list(
        ProtectedApp.objects.filter(is_public=False).order_by("sort_order", "name")
    )
    active_grants_by_app = {
        g.app_id: g
        for g in AppAccess.objects.filter(
            user=target_user,
            revoked_at__isnull=True,
        ).select_related("app")
    }
    app_access_rows = [
        {"app": app_obj, "grant": active_grants_by_app.get(app_obj.pk)}
        for app_obj in governed_apps
    ]

    user_sessions = SessionRecord.objects.filter(user=target_user, revoked_at__isnull=True)[:25]
    user_audit = AuditEvent.objects.filter(
        Q(actor=target_user) | Q(target_user=target_user)
    ).select_related("actor", "target_user")[:30]

    ctx = _console_common_context(request)
    ctx.update(
        {
            "target_user": target_user,
            "target_profile": profile,
            "twofa_summary": twofa.get_user_2fa_summary(target_user),
            "app_access_rows": app_access_rows,
            "governed_apps": governed_apps,
            "user_sessions": user_sessions,
            "user_audit": user_audit,
            "temp_password_once": temp_pw_once,
        }
    )
    return render_projectauth(request, "console_user_detail", ctx)


# ---------------------------------------------------------------------------
# 8.1 Apps / Access Matrix (`auth/console/apps/`) & Access Requests (`auth/console/requests/`)
# ---------------------------------------------------------------------------


@never_cache
@console_access_required
@require_http_methods(["GET", "POST"])
def console_apps_view(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        matrix_action = (request.POST.get("matrix_action") or "grant").strip()
        raw_uids = request.POST.getlist("user_ids") or (
            [request.POST.get("user_id")] if request.POST.get("user_id") else []
        )
        raw_apps = request.POST.getlist("app_labels") or (
            [request.POST.get("app_label")] if request.POST.get("app_label") else []
        )

        user_ids = [int(u) for u in raw_uids if u and str(u).isdigit()]
        app_labels = [str(a).strip() for a in raw_apps if a and str(a).strip()]

        target_users = list(User.objects.filter(pk__in=user_ids))
        target_apps = list(ProtectedApp.objects.filter(app_label__in=app_labels, is_public=False))

        if not target_users or not target_apps:
            messages.error(request, "Select at least one user and one protected app.")
            return redirect("projectauth:console_apps")

        if matrix_action in ("grant", "tester_preset"):
            if matrix_action == "tester_preset":
                level = AppAccess.LEVEL_READ_ONLY
                expires_at = timezone.now() + timedelta(days=7)
            else:
                level, expires_at = _parse_access_level_and_expiry(request.POST)

            count = 0
            for u in target_users:
                for app_obj in target_apps:
                    grant_or_update_app_access(
                        request.user,
                        u,
                        app_obj,
                        level=level,
                        expires_at=expires_at,
                        note=(request.POST.get("note") or "").strip(),
                        request=request,
                    )
                    count += 1
            messages.success(request, f"Updated {count} app access grant(s) ({level}).")

        elif matrix_action == "revoke":
            count = 0
            for u in target_users:
                for app_obj in target_apps:
                    count += revoke_app_access(
                        request.user,
                        u,
                        app_obj,
                        request=request,
                    )
            messages.info(request, f"Revoked {count} app access grant(s).")

        return redirect("projectauth:console_apps")

    governed_apps = list(
        ProtectedApp.objects.filter(is_public=False).order_by("sort_order", "name")
    )
    users_qs = (
        User.objects.select_related("profile")
        .order_by("username")[:100]
    )
    users_list = list(users_qs)
    now = timezone.now()

    active_grants = AppAccess.objects.filter(
        user__in=users_list,
        app__in=governed_apps,
        revoked_at__isnull=True,
    ).select_related("app")

    grant_map: dict[Tuple[int, int], AppAccess] = {}
    for g in active_grants:
        if g.is_currently_active(now=now):
            grant_map[(g.user_id, g.app_id)] = g

    matrix_rows = []
    for u in users_list:
        cells = []
        for app_obj in governed_apps:
            cells.append(
                {
                    "app": app_obj,
                    "grant": grant_map.get((u.pk, app_obj.pk)),
                }
            )
        matrix_rows.append(
            {
                "user": u,
                "profile": getattr(u, "profile", None),
                "is_admin": user_is_active_admin(u),
                "cells": cells,
            }
        )

    pending_requests = AccessRequest.objects.filter(
        status=AccessRequest.STATUS_PENDING
    ).select_related("user", "app")[:30]

    ctx = _console_common_context(request)
    ctx.update(
        {
            "governed_apps": governed_apps,
            "matrix_rows": matrix_rows,
            "pending_requests": pending_requests,
        }
    )
    return render_projectauth(request, "console_apps", ctx)


@never_cache
@console_access_required
@require_http_methods(["GET", "POST"])
def console_requests_view(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        request_action = (request.POST.get("request_action") or "").strip()
        req_id = request.POST.get("request_id") or ""
        acc_req = get_object_or_404(
            AccessRequest.objects.select_related("user", "app"),
            pk=req_id,
        )
        now = timezone.now()

        if request_action in ("approve", "tester_preset"):
            if request_action == "tester_preset":
                level = AppAccess.LEVEL_READ_ONLY
                expires_at = now + timedelta(days=7)
            else:
                level, expires_at = _parse_access_level_and_expiry(request.POST)

            grant_or_update_app_access(
                request.user,
                acc_req.user,
                acc_req.app,
                level=level,
                expires_at=expires_at,
                note=(request.POST.get("decision_note") or "").strip(),
                request=request,
            )
            log_audit(
                "access.request_approved",
                request=request,
                actor=request.user,
                target_user=acc_req.user,
                details={"app": acc_req.app.app_label, "level": level},
            )
            messages.success(
                request,
                f"Approved {acc_req.user.username}'s request for {acc_req.app.name} ({level}).",
            )

        elif request_action == "deny":
            note = (request.POST.get("decision_note") or "").strip()
            acc_req.status = AccessRequest.STATUS_DENIED
            acc_req.decided_by = request.user
            acc_req.decided_at = now
            acc_req.decision_note = note
            acc_req.save(
                update_fields=["status", "decided_by", "decided_at", "decision_note"]
            )
            log_audit(
                "access.request_denied",
                request=request,
                actor=request.user,
                target_user=acc_req.user,
                details={"app": acc_req.app.app_label},
            )
            if acc_req.user.email:
                send_projectauth_email(
                    "access_denied",
                    [acc_req.user.email],
                    context={
                        "username": acc_req.user.username,
                        "app_name": acc_req.app.name,
                        "decision_note": note,
                    },
                )
            messages.info(
                request,
                f"Denied {acc_req.user.username}'s request for {acc_req.app.name}.",
            )

        return redirect("projectauth:console_requests")

    pending_requests = AccessRequest.objects.filter(
        status=AccessRequest.STATUS_PENDING
    ).select_related("user", "app")
    recent_decided = (
        AccessRequest.objects.exclude(status=AccessRequest.STATUS_PENDING)
        .select_related("user", "app", "decided_by")[:30]
    )

    ctx = _console_common_context(request)
    ctx.update(
        {
            "pending_requests": pending_requests,
            "recent_decided": recent_decided,
        }
    )
    return render_projectauth(request, "console_requests", ctx)


# ---------------------------------------------------------------------------
# 8.1 Admins & Access Managers (`auth/console/admins/`)
# ---------------------------------------------------------------------------


@never_cache
@console_admin_required
@require_http_methods(["GET", "POST"])
def console_admins_view(request: HttpRequest) -> HttpResponse:
    mgr_group = ensure_access_managers_group()

    if request.method == "POST":
        admin_action = (request.POST.get("admin_action") or "").strip()

        # Promoting or demoting admins requires sudo re-auth + 2FA when policy requires it (Section 8.1)
        if not _check_or_verify_sudo(request):
            messages.info(request, "Please re-authenticate to manage administrator roles.")
            return redirect(
                f"{reverse('projectauth:reauth')}?next={reverse('projectauth:console_admins')}"
            )

        auth_settings = AuthSettings.load()
        if auth_settings.require_2fa_for_admins and not twofa.user_has_confirmed_totp(request.user):
            messages.error(
                request,
                "You must enrol an authenticator app (2FA) on your own account before promoting or demoting administrators.",
            )
            return redirect("projectauth:twofa_setup")

        uid = request.POST.get("user_id") or ""
        uname = normalize_identifier(request.POST.get("username") or "")
        if uid and str(uid).isdigit():
            target_user = get_object_or_404(User.objects.select_related("profile"), pk=int(uid))
        elif uname:
            target_user = get_object_or_404(
                User.objects.select_related("profile").annotate(_ul=Lower("username")),
                _ul=uname,
            )
        else:
            messages.error(request, "Specify a valid user.")
            return redirect("projectauth:console_admins")

        if admin_action == "promote_admin":
            target_user.is_superuser = True
            target_user.is_staff = True
            target_user.is_active = True
            target_user.save(update_fields=["is_superuser", "is_staff", "is_active"])
            if getattr(target_user, "profile", None):
                target_user.profile.status = UserProfile.STATUS_ACTIVE
                target_user.profile.save(update_fields=["status"])
            log_audit(
                "admin.promoted",
                request=request,
                actor=request.user,
                target_user=target_user,
            )
            messages.success(request, f"Promoted '{target_user.username}' to Administrator.")

        elif admin_action == "promote_access_manager":
            target_user.groups.add(mgr_group)
            log_audit(
                "admin.access_manager_granted",
                request=request,
                actor=request.user,
                target_user=target_user,
            )
            messages.success(request, f"Added '{target_user.username}' to Access Managers.")

        elif admin_action == "demote_admin":
            if is_last_active_admin(target_user):
                log_audit(
                    "admin.last_admin_protected",
                    request=request,
                    actor=request.user,
                    target_user=target_user,
                    details={"attempted_action": "demote_admin"},
                )
                messages.error(
                    request,
                    "Refused: cannot demote the last active administrator account.",
                )
            else:
                target_user.is_superuser = False
                target_user.is_staff = False
                target_user.save(update_fields=["is_superuser", "is_staff"])
                log_audit(
                    "admin.demoted",
                    request=request,
                    actor=request.user,
                    target_user=target_user,
                )
                messages.info(request, f"Demoted '{target_user.username}' from Administrator.")

        elif admin_action == "demote_access_manager":
            target_user.groups.remove(mgr_group)
            log_audit(
                "admin.access_manager_revoked",
                request=request,
                actor=request.user,
                target_user=target_user,
            )
            messages.info(request, f"Removed '{target_user.username}' from Access Managers.")

        return redirect("projectauth:console_admins")

    admins_list = User.objects.filter(is_superuser=True, is_staff=True).select_related("profile")
    access_managers = User.objects.filter(groups=mgr_group).select_related("profile").distinct()
    eligible_users = (
        User.objects.filter(is_active=True, profile__status=UserProfile.STATUS_ACTIVE)
        .order_by("username")[:100]
    )

    ctx = _console_common_context(request)
    ctx.update(
        {
            "admins_list": admins_list,
            "access_managers": access_managers,
            "eligible_users": eligible_users,
            "sudo_ok": is_sudo_active(request),
        }
    )
    return render_projectauth(request, "console_admins", ctx)


# ---------------------------------------------------------------------------
# 8.1 Admin Invitations (`auth/console/invites/` & `auth/invite/<token>/`)
# ---------------------------------------------------------------------------


@never_cache
@console_admin_required
@require_http_methods(["GET", "POST"])
def console_invites_view(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        invite_action = (request.POST.get("invite_action") or "create").strip()

        if invite_action == "create":
            email = normalize_identifier(request.POST.get("email") or "")
            role = (request.POST.get("role") or AdminInvitation.ROLE_ADMIN).strip()
            if role not in (AdminInvitation.ROLE_ADMIN, AdminInvitation.ROLE_ACCESS_MANAGER):
                role = AdminInvitation.ROLE_ADMIN

            if not email or "@" not in email:
                messages.error(request, "Please enter a valid email address.")
                return redirect("projectauth:console_invites")

            try:
                validate_email_domain_policy(email)
            except Exception as exc:
                messages.error(request, str(exc))
                return redirect("projectauth:console_invites")

            raw_token = secrets.token_urlsafe(32)
            token_hmac = hmac_sha256("admin_invite", raw_token)
            now = timezone.now()
            invitation = AdminInvitation.objects.create(
                email=email,
                role=role,
                token_hmac=token_hmac,
                invited_by=request.user,
                expires_at=now + timedelta(hours=INVITE_EXPIRY_HOURS),
            )
            invite_url = build_absolute_url(
                reverse("projectauth:invite_accept", kwargs={"token": raw_token})
            )
            role_label = dict(AdminInvitation.ROLE_CHOICES).get(role, role)
            send_projectauth_email(
                "admin_invite",
                [email],
                context={
                    "email": email,
                    "role": role_label,
                    "invited_by": request.user.username,
                    "action_url": invite_url,
                    "expires_hours": INVITE_EXPIRY_HOURS,
                },
            )
            log_audit(
                "admin.invite_created",
                request=request,
                actor=request.user,
                details={
                    "invite_id": invitation.pk,
                    "masked_email": mask_email(email),
                    "role": role,
                },
            )
            messages.success(
                request,
                f"Sent {role_label} invitation to {mask_email(email)} (valid for 72 hours).",
            )

        elif invite_action == "revoke":
            inv_id = request.POST.get("invite_id") or ""
            inv = get_object_or_404(
                AdminInvitation,
                pk=inv_id,
                accepted_at__isnull=True,
            )
            masked = mask_email(inv.email)
            inv.delete()
            log_audit(
                "admin.invite_revoked",
                request=request,
                actor=request.user,
                details={"masked_email": masked},
            )
            messages.info(request, f"Revoked pending invitation for {masked}.")

        return redirect("projectauth:console_invites")

    now = timezone.now()
    pending_invites = AdminInvitation.objects.filter(
        accepted_at__isnull=True,
        expires_at__gt=now,
    ).select_related("invited_by")
    past_invites = AdminInvitation.objects.filter(
        Q(accepted_at__isnull=False) | Q(expires_at__lte=now)
    ).select_related("invited_by", "accepted_user")[:30]

    ctx = _console_common_context(request)
    ctx.update(
        {
            "pending_invites": pending_invites,
            "past_invites": past_invites,
            "role_choices": AdminInvitation.ROLE_CHOICES,
        }
    )
    return render_projectauth(request, "console_invites", ctx)


@never_cache
@require_http_methods(["GET", "POST"])
def invite_accept_view(request: HttpRequest, token: str) -> HttpResponse:
    token_hmac = hmac_sha256("admin_invite", token or "")
    now = timezone.now()
    invitation = (
        AdminInvitation.objects.filter(
            token_hmac=token_hmac,
            accepted_at__isnull=True,
            expires_at__gt=now,
        )
        .first()
    )
    if invitation is None:
        return render_projectauth(
            request,
            "invite_accept",
            {
                "invite_invalid": True,
                "error_message": "This invitation link is invalid, has expired, or has already been used.",
            },
            status=400,
        )

    email_norm = normalize_identifier(invitation.email)
    existing_user = (
        User.objects.select_related("profile")
        .annotate(_el=Lower("email"))
        .filter(Q(_el=email_norm) | Q(profile__email_normalized=email_norm))
        .first()
    )

    if request.method == "POST":
        form = InviteAcceptForm(
            request.POST,
            email=email_norm,
            existing_user=existing_user,
        )
        if form.is_valid():
            uname = form.cleaned_data["username"]
            password = form.cleaned_data["password"]
            mgr_group = ensure_access_managers_group()

            with transaction.atomic():
                if existing_user is not None:
                    user = existing_user
                    user.username = uname
                    user.email = email_norm
                    user.is_active = True
                else:
                    user = User(
                        username=uname,
                        email=email_norm,
                        is_active=True,
                    )

                if invitation.role == AdminInvitation.ROLE_ADMIN:
                    user.is_superuser = True
                    user.is_staff = True

                user.set_password(password)
                user.save()

                if invitation.role == AdminInvitation.ROLE_ACCESS_MANAGER:
                    user.groups.add(mgr_group)

                profile, _ = UserProfile.objects.get_or_create(
                    user=user,
                    defaults={
                        "username_normalized": uname,
                        "email_normalized": email_norm,
                        "created_via": UserProfile.CREATED_VIA_INVITE,
                    },
                )
                profile.status = UserProfile.STATUS_ACTIVE
                profile.username_normalized = uname
                profile.email_normalized = email_norm
                profile.email_verified_at = now
                profile.password_changed_at = now
                profile.must_change_password = False
                profile.created_via = UserProfile.CREATED_VIA_INVITE
                profile.approved_by = invitation.invited_by
                profile.approved_at = now
                profile.save()

                invitation.accepted_at = now
                invitation.accepted_user = user
                invitation.save(update_fields=["accepted_at", "accepted_user"])

            log_audit(
                "admin.invite_accepted",
                request=request,
                actor=user,
                target_user=user,
                details={"role": invitation.role, "invite_id": invitation.pk},
            )

            # Invitee must enrol 2FA before completing console access (Section 8.1)
            twofa.set_preauth_state(
                request,
                user,
                remember_me=False,
                next_url=reverse("projectauth:console_dashboard"),
                must_enrol=True,
            )
            messages.success(
                request,
                "Invitation accepted! Please set up two-factor authentication to activate your administrator access.",
            )
            return redirect("projectauth:twofa_setup")
    else:
        form = InviteAcceptForm(email=email_norm, existing_user=existing_user)

    return render_projectauth(
        request,
        "invite_accept",
        {
            "invite_invalid": False,
            "invitation": invitation,
            "form": form,
        },
    )


# ---------------------------------------------------------------------------
# 8.1 Audit Log & CSV Export (`auth/console/audit/`, `auth/console/audit/export/`)
# ---------------------------------------------------------------------------


def _filtered_audit_queryset(request: HttpRequest):
    qs = AuditEvent.objects.select_related("actor", "target_user").order_by("-created_at", "-id")
    actor_q = (request.GET.get("actor") or "").strip()
    target_q = (request.GET.get("target") or "").strip()
    action_q = (request.GET.get("action") or "").strip()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()

    if actor_q:
        qs = qs.filter(
            Q(actor__username__icontains=actor_q) | Q(actor_label__icontains=actor_q)
        )
    if target_q:
        qs = qs.filter(
            Q(target_user__username__icontains=target_q) | Q(target_label__icontains=target_q)
        )
    if action_q:
        qs = qs.filter(action__icontains=action_q)
    if date_from:
        d_from = parse_date(date_from)
        if d_from:
            qs = qs.filter(
                created_at__gte=datetime.combine(d_from, time.min, tzinfo=dt_timezone.utc)
            )
    if date_to:
        d_to = parse_date(date_to)
        if d_to:
            qs = qs.filter(
                created_at__lte=datetime.combine(d_to, time.max, tzinfo=dt_timezone.utc)
            )
    return qs


@never_cache
@console_admin_required
@require_GET
def console_audit_view(request: HttpRequest) -> HttpResponse:
    qs = _filtered_audit_queryset(request)
    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    ctx = _console_common_context(request)
    ctx.update(
        {
            "page_obj": page_obj,
            "audit_events": page_obj.object_list,
            "filter_actor": (request.GET.get("actor") or "").strip(),
            "filter_target": (request.GET.get("target") or "").strip(),
            "filter_action": (request.GET.get("action") or "").strip(),
            "filter_date_from": (request.GET.get("date_from") or "").strip(),
            "filter_date_to": (request.GET.get("date_to") or "").strip(),
        }
    )
    return render_projectauth(request, "console_audit", ctx)


@never_cache
@console_admin_required
@require_GET
def console_audit_export_view(request: HttpRequest) -> HttpResponse:
    qs = _filtered_audit_queryset(request)[:5000]
    log_audit("audit.exported", request=request, actor=request.user)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="projectauth-audit.csv"'
    patch_cache_control(response, no_store=True, no_cache=True, must_revalidate=True)

    writer = csv.writer(response)
    writer.writerow(
        [
            "id",
            "created_at_utc",
            "action",
            "actor",
            "target",
            "ip",
            "user_agent",
            "details_json",
        ]
    )
    for ev in qs:
        actor_str = ev.actor.username if ev.actor else (ev.actor_label or "")
        target_str = ev.target_user.username if ev.target_user else (ev.target_label or "")
        writer.writerow(
            [
                ev.pk,
                ev.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
                ev.action,
                actor_str,
                target_str,
                ev.ip or "",
                ev.user_agent or "",
                json.dumps(ev.details or {}, sort_keys=True),
            ]
        )
    return response


# ---------------------------------------------------------------------------
# 8.1 Policies / AuthSettings (`auth/console/settings/`)
# ---------------------------------------------------------------------------


@never_cache
@console_admin_required
@require_http_methods(["GET", "POST"])
def console_settings_view(request: HttpRequest) -> HttpResponse:
    auth_settings = AuthSettings.load()
    if request.method == "POST":
        form = AuthSettingsForm(request.POST, instance=auth_settings)
        if form.is_valid():
            changed = list(form.changed_data)
            form.save()
            log_audit(
                "settings.updated",
                request=request,
                actor=request.user,
                details={"changed_fields": changed},
            )
            messages.success(request, "Authentication & security policies updated.")
            return redirect("projectauth:console_settings")
    else:
        form = AuthSettingsForm(instance=auth_settings)

    ctx = _console_common_context(request)
    ctx.update(
        {
            "settings_form": form,
            "auth_settings": auth_settings,
            "public_apps": getattr(settings, "PROJECTAUTH_PUBLIC_APPS", ["home", "cv"]),
        }
    )
    return render_projectauth(request, "console_settings", ctx)
