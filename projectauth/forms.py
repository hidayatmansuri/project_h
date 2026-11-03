"""
Forms and validators for projectauth (Section 5.1, 5.2, 5.4, 7).
"""

from __future__ import annotations

import hashlib
import re
import urllib.request
from typing import Optional

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models.functions import Lower

from .crypto import normalize_identifier
from .models import AuthSettings, ProtectedApp, UserProfile
from .tokens import check_form_timing_token, create_form_timing_token

User = get_user_model()

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.\-]+$")


def check_hibp_pwned_password(password: str) -> int:
    """
    Checks Have I Been Pwned k-anonymity range API (Section 7).
    Only sends the first 5 hex characters of the SHA-1 hash.
    Fails open (returns 0) if the network or service is unreachable.
    """
    if not getattr(settings, "PROJECTAUTH_HIBP_CHECK", False):
        return 0
    sha1_hex = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = sha1_hex[:5], sha1_hex[5:]
    url = f"https://api.pwnedpasswords.com/range/{prefix}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "project-h-projectauth/1.0", "Add-Padding": "true"},
    )
    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        for line in body.splitlines():
            if ":" not in line:
                continue
            h_suf, count_str = line.strip().split(":", 1)
            if h_suf.strip().upper() == suffix:
                return int(count_str.strip() or "0")
    except Exception:
        # Fail-open if HIBP is unreachable
        return 0
    return 0


def validate_projectauth_password(
    password: str,
    *,
    user=None,
    username: str = "",
    email: str = "",
) -> None:
    """
    Validates password against:
    - AuthSettings.password_min_length (default 12)
    - Not equal to username or email (case-insensitive)
    - Django AUTH_PASSWORD_VALIDATORS
    - Optional HIBP k-anonymity breached password check
    """
    if not password:
        raise ValidationError("Password is required.")

    auth_settings = AuthSettings.load()
    min_len = max(12, int(auth_settings.password_min_length or 12))
    if len(password) < min_len:
        raise ValidationError(f"Password must be at least {min_len} characters long.")

    pw_norm = normalize_identifier(password)
    uname_norm = normalize_identifier(username or (getattr(user, "username", "") if user else ""))
    email_norm = normalize_identifier(email or (getattr(user, "email", "") if user else ""))

    if uname_norm and pw_norm == uname_norm:
        raise ValidationError("Password cannot be the same as your username.")
    if email_norm and pw_norm == email_norm:
        raise ValidationError("Password cannot be the same as your email address.")

    validate_password(password, user=user)

    pwned_count = check_hibp_pwned_password(password)
    if pwned_count > 0:
        raise ValidationError(
            "This password has appeared in a known data breach. Please choose a different password."
        )


def validate_email_domain_policy(email: str) -> None:
    if not email or "@" not in email:
        return
    domain = email.rsplit("@", 1)[-1].strip().lower()
    auth_settings = AuthSettings.load()

    blocked_raw = (auth_settings.blocked_email_domains or "").strip()
    if blocked_raw:
        blocked = {
            d.strip().lower().lstrip("@")
            for d in re.split(r"[\s,;]+", blocked_raw)
            if d.strip()
        }
        if domain in blocked:
            raise ValidationError("Registrations from this email domain are not permitted.")

    allowed_raw = (auth_settings.allowed_email_domains or "").strip()
    if allowed_raw:
        allowed = {
            d.strip().lower().lstrip("@")
            for d in re.split(r"[\s,;]+", allowed_raw)
            if d.strip()
        }
        if allowed and domain not in allowed:
            raise ValidationError("Please use an email address from an approved domain.")


class BotProtectedFormMixin(forms.Form):
    """Adds honeypot and minimum-submit-time check without external CAPTCHA services."""

    website_url = forms.CharField(
        required=False,
        label="Leave this field empty",
        widget=forms.TextInput(
            attrs={
                "tabindex": "-1",
                "autocomplete": "off",
                "aria-hidden": "true",
                "class": "pa-honeypot",
            }
        ),
    )
    form_rendered_at = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.fields["form_rendered_at"].initial = create_form_timing_token()

    def clean(self):
        cleaned = super().clean()
        honeypot = (cleaned.get("website_url") or "").strip()
        if honeypot:
            raise ValidationError("Unable to process submission. Please try again.")

        min_sec = float(getattr(settings, "PROJECTAUTH_MIN_SUBMIT_SECONDS", 0.0))
        timing_token = (cleaned.get("form_rendered_at") or "").strip()
        if min_sec > 0 and not check_form_timing_token(timing_token, min_sec):
            raise ValidationError("Form submitted too quickly. Please wait a moment and try again.")
        return cleaned


class SignupForm(BotProtectedFormMixin, forms.Form):
    username = forms.CharField(
        max_length=150,
        min_length=3,
        label="Username",
        widget=forms.TextInput(
            attrs={
                "class": "ph-field",
                "autocomplete": "username",
                "placeholder": "e.g. alex_smith",
            }
        ),
    )
    email = forms.EmailField(
        max_length=254,
        label="Email address",
        widget=forms.EmailInput(
            attrs={
                "class": "ph-field",
                "autocomplete": "email",
                "placeholder": "you@example.com",
            }
        ),
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "ph-field",
                "autocomplete": "new-password",
                "id": "pa-signup-password",
            }
        ),
    )
    password_confirm = forms.CharField(
        label="Confirm password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "ph-field",
                "autocomplete": "new-password",
                "id": "pa-signup-password-confirm",
            }
        ),
    )
    requested_apps = forms.ModelMultipleChoiceField(
        queryset=ProtectedApp.objects.none(),
        required=False,
        label="Apps I need access to",
        widget=forms.CheckboxSelectMultiple(attrs={"class": "ph-checkbox"}),
    )
    accept_terms = forms.BooleanField(
        required=True,
        label="I agree to the terms of use and privacy notice",
        widget=forms.CheckboxInput(attrs={"class": "ph-checkbox"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["requested_apps"].queryset = ProtectedApp.objects.filter(
            is_public=False,
            is_active=True,
        ).order_by("sort_order", "name")

    def clean_username(self) -> str:
        raw = (self.cleaned_data.get("username") or "").strip()
        norm = normalize_identifier(raw)
        if len(norm) < 3:
            raise ValidationError("Username must be at least 3 characters.")
        if not USERNAME_RE.match(norm):
            raise ValidationError(
                "Username may only contain letters, numbers, dots, hyphens, and underscores."
            )
        return norm

    def clean_email(self) -> str:
        raw = (self.cleaned_data.get("email") or "").strip()
        norm = normalize_identifier(raw)
        validate_email_domain_policy(norm)
        return norm

    def clean(self):
        cleaned = super().clean()
        uname = cleaned.get("username") or ""
        email = cleaned.get("email") or ""
        pw1 = cleaned.get("password") or ""
        pw2 = cleaned.get("password_confirm") or ""

        if pw1 and pw2 and pw1 != pw2:
            self.add_error("password_confirm", "Passwords do not match.")

        if pw1:
            try:
                validate_projectauth_password(pw1, username=uname, email=email)
            except ValidationError as exc:
                self.add_error("password", exc)

        # Note: If email already exists, we do NOT raise an error here (anti-enumeration, Section 5.1).
        # If email is new but username is already taken, report username unavailable.
        if uname and email:
            email_exists = (
                User.objects.annotate(_el=Lower("email")).filter(_el=email).exists()
                or UserProfile.objects.filter(email_normalized=email).exists()
            )
            if not email_exists:
                uname_exists = (
                    User.objects.annotate(_ul=Lower("username")).filter(_ul=uname).exists()
                    or UserProfile.objects.filter(username_normalized=uname).exists()
                )
                if uname_exists:
                    self.add_error("username", "This username is already taken. Please choose another.")

        return cleaned


class LoginForm(forms.Form):
    identifier = forms.CharField(
        max_length=254,
        label="Email or username",
        widget=forms.TextInput(
            attrs={
                "class": "ph-field",
                "autocomplete": "username",
                "placeholder": "Email or username",
            }
        ),
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "ph-field",
                "autocomplete": "current-password",
                "id": "pa-login-password",
            }
        ),
    )
    remember_me = forms.BooleanField(
        required=False,
        label="Remember me for 30 days",
        widget=forms.CheckboxInput(attrs={"class": "ph-checkbox"}),
    )


class ForgotPasswordForm(BotProtectedFormMixin, forms.Form):
    email = forms.EmailField(
        max_length=254,
        label="Email address",
        widget=forms.EmailInput(
            attrs={
                "class": "ph-field",
                "autocomplete": "email",
                "placeholder": "you@example.com",
            }
        ),
    )

    def clean_email(self) -> str:
        return normalize_identifier(self.cleaned_data.get("email") or "")


class ResetPasswordForm(forms.Form):
    password = forms.CharField(
        label="New password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "ph-field",
                "autocomplete": "new-password",
                "id": "pa-reset-password",
            }
        ),
    )
    password_confirm = forms.CharField(
        label="Confirm new password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "ph-field",
                "autocomplete": "new-password",
            }
        ),
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        pw1 = cleaned.get("password") or ""
        pw2 = cleaned.get("password_confirm") or ""
        if pw1 and pw2 and pw1 != pw2:
            self.add_error("password_confirm", "Passwords do not match.")
        if pw1:
            try:
                validate_projectauth_password(pw1, user=self.user)
            except ValidationError as exc:
                self.add_error("password", exc)
        return cleaned


class ForgotUsernameForm(BotProtectedFormMixin, forms.Form):
    email = forms.EmailField(
        max_length=254,
        label="Email address",
        widget=forms.EmailInput(
            attrs={
                "class": "ph-field",
                "autocomplete": "email",
                "placeholder": "you@example.com",
            }
        ),
    )

    def clean_email(self) -> str:
        return normalize_identifier(self.cleaned_data.get("email") or "")


class ForcePasswordChangeForm(ResetPasswordForm):
    current_password = forms.CharField(
        label="Current (temporary) password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "ph-field",
                "autocomplete": "current-password",
            }
        ),
    )

    def clean_current_password(self):
        cpw = self.cleaned_data.get("current_password") or ""
        if self.user and not self.user.check_password(cpw):
            raise ValidationError("Current password is incorrect.")
        return cpw


class ChangePasswordForm(ForcePasswordChangeForm):
    pass


class ChangeUsernameForm(forms.Form):
    new_username = forms.CharField(
        max_length=150,
        min_length=3,
        label="New username",
        widget=forms.TextInput(attrs={"class": "ph-field", "autocomplete": "username"}),
    )
    current_password = forms.CharField(
        label="Current password",
        strip=False,
        required=False,
        widget=forms.PasswordInput(
            attrs={"class": "ph-field", "autocomplete": "current-password"}
        ),
    )

    def __init__(self, *args, user=None, sudo_ok: bool = False, **kwargs):
        self.user = user
        self.sudo_ok = sudo_ok
        super().__init__(*args, **kwargs)

    def clean_new_username(self) -> str:
        norm = normalize_identifier(self.cleaned_data.get("new_username") or "")
        if len(norm) < 3 or not USERNAME_RE.match(norm):
            raise ValidationError(
                "Username must be at least 3 characters and contain only letters, numbers, dots, hyphens, or underscores."
            )
        qs = User.objects.annotate(_ul=Lower("username")).filter(_ul=norm)
        p_qs = UserProfile.objects.filter(username_normalized=norm)
        if self.user:
            qs = qs.exclude(pk=self.user.pk)
            p_qs = p_qs.exclude(user_id=self.user.pk)
        if qs.exists() or p_qs.exists():
            raise ValidationError("This username is already taken.")
        return norm

    def clean(self):
        cleaned = super().clean()
        cpw = cleaned.get("current_password") or ""
        if not self.sudo_ok:
            if not cpw or (self.user and not self.user.check_password(cpw)):
                self.add_error("current_password", "Please enter your current password to confirm.")
        return cleaned


class ChangeEmailForm(forms.Form):
    new_email = forms.EmailField(
        max_length=254,
        label="New email address",
        widget=forms.EmailInput(attrs={"class": "ph-field", "autocomplete": "email"}),
    )
    current_password = forms.CharField(
        label="Current password",
        strip=False,
        required=False,
        widget=forms.PasswordInput(
            attrs={"class": "ph-field", "autocomplete": "current-password"}
        ),
    )

    def __init__(self, *args, user=None, sudo_ok: bool = False, **kwargs):
        self.user = user
        self.sudo_ok = sudo_ok
        super().__init__(*args, **kwargs)

    def clean_new_email(self) -> str:
        norm = normalize_identifier(self.cleaned_data.get("new_email") or "")
        validate_email_domain_policy(norm)
        if self.user and norm == normalize_identifier(self.user.email or ""):
            raise ValidationError("This is already your current email address.")
        return norm

    def clean(self):
        cleaned = super().clean()
        cpw = cleaned.get("current_password") or ""
        if not self.sudo_ok:
            if not cpw or (self.user and not self.user.check_password(cpw)):
                self.add_error("current_password", "Please enter your current password to confirm.")
        return cleaned


class DeleteAccountForm(forms.Form):
    confirm_text = forms.CharField(
        max_length=32,
        label="Type DELETE to confirm",
        widget=forms.TextInput(attrs={"class": "ph-field", "autocomplete": "off"}),
    )
    current_password = forms.CharField(
        label="Current password",
        strip=False,
        required=False,
        widget=forms.PasswordInput(
            attrs={"class": "ph-field", "autocomplete": "current-password"}
        ),
    )

    def __init__(self, *args, user=None, sudo_ok: bool = False, **kwargs):
        self.user = user
        self.sudo_ok = sudo_ok
        super().__init__(*args, **kwargs)

    def clean_confirm_text(self) -> str:
        val = (self.cleaned_data.get("confirm_text") or "").strip()
        if val != "DELETE":
            raise ValidationError("Please type DELETE in uppercase to confirm account deletion.")
        return val

    def clean(self):
        cleaned = super().clean()
        cpw = cleaned.get("current_password") or ""
        if not self.sudo_ok:
            if not cpw or (self.user and not self.user.check_password(cpw)):
                self.add_error("current_password", "Please enter your current password to confirm.")
        return cleaned


class InviteAcceptForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        min_length=3,
        label="Choose a username",
        widget=forms.TextInput(
            attrs={
                "class": "ph-field",
                "autocomplete": "username",
                "placeholder": "e.g. admin_alex",
            }
        ),
    )
    password = forms.CharField(
        label="Choose a password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "ph-field",
                "autocomplete": "new-password",
                "id": "pa-invite-password",
            }
        ),
    )
    password_confirm = forms.CharField(
        label="Confirm password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "ph-field",
                "autocomplete": "new-password",
            }
        ),
    )

    def __init__(self, *args, email: str = "", existing_user=None, **kwargs):
        self.email = normalize_identifier(email)
        self.existing_user = existing_user
        super().__init__(*args, **kwargs)
        if existing_user and not self.is_bound:
            self.fields["username"].initial = existing_user.username

    def clean_username(self) -> str:
        norm = normalize_identifier(self.cleaned_data.get("username") or "")
        if len(norm) < 3 or not USERNAME_RE.match(norm):
            raise ValidationError(
                "Username must be at least 3 characters and contain only letters, numbers, dots, hyphens, or underscores."
            )
        qs = User.objects.annotate(_ul=Lower("username")).filter(_ul=norm)
        p_qs = UserProfile.objects.filter(username_normalized=norm)
        if self.existing_user:
            qs = qs.exclude(pk=self.existing_user.pk)
            p_qs = p_qs.exclude(user_id=self.existing_user.pk)
        if qs.exists() or p_qs.exists():
            raise ValidationError("This username is already taken.")
        return norm

    def clean(self):
        cleaned = super().clean()
        uname = cleaned.get("username") or ""
        pw1 = cleaned.get("password") or ""
        pw2 = cleaned.get("password_confirm") or ""
        if pw1 and pw2 and pw1 != pw2:
            self.add_error("password_confirm", "Passwords do not match.")
        if pw1:
            try:
                validate_projectauth_password(
                    pw1,
                    user=self.existing_user,
                    username=uname,
                    email=self.email,
                )
            except ValidationError as exc:
                self.add_error("password", exc)
        return cleaned


class AuthSettingsForm(forms.ModelForm):
    class Meta:
        model = AuthSettings
        fields = [
            "signup_mode",
            "require_2fa_for_admins",
            "require_2fa_for_all",
            "twofa_grace_days",
            "notify_admins_on_signup",
            "admin_notify_emails",
            "allowed_email_domains",
            "blocked_email_domains",
            "admin_idle_timeout_min",
            "user_idle_timeout_hours",
            "password_min_length",
        ]
        widgets = {
            "signup_mode": forms.Select(attrs={"class": "ph-field"}),
            "require_2fa_for_admins": forms.CheckboxInput(attrs={"class": "ph-checkbox"}),
            "require_2fa_for_all": forms.CheckboxInput(attrs={"class": "ph-checkbox"}),
            "twofa_grace_days": forms.NumberInput(attrs={"class": "ph-field", "min": 0, "max": 90}),
            "notify_admins_on_signup": forms.CheckboxInput(attrs={"class": "ph-checkbox"}),
            "admin_notify_emails": forms.Textarea(attrs={"class": "ph-field", "rows": 2}),
            "allowed_email_domains": forms.Textarea(attrs={"class": "ph-field", "rows": 2}),
            "blocked_email_domains": forms.Textarea(attrs={"class": "ph-field", "rows": 2}),
            "admin_idle_timeout_min": forms.NumberInput(attrs={"class": "ph-field", "min": 5, "max": 1440}),
            "user_idle_timeout_hours": forms.NumberInput(attrs={"class": "ph-field", "min": 1, "max": 720}),
            "password_min_length": forms.NumberInput(attrs={"class": "ph-field", "min": 12, "max": 128}),
        }

    def clean_password_min_length(self):
        val = int(self.cleaned_data.get("password_min_length") or 12)
        if val < 12:
            raise ValidationError("Minimum password length must be at least 12 characters.")
        return val


