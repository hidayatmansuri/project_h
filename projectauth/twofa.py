"""
Two-factor authentication (Phase 3 / Section 5.3):
- Free, standards-based methods ONLY:
  1. Authenticator App (TOTP, RFC 6238 via pyotp, inline SVG QR via segno, AES-256-GCM encrypted secret, replay protection via last_used_step).
  2. Email one-time code (6 digits, 10-minute expiry, 5 attempts, HMAC-SHA256 stored).
  3. Recovery codes (10 single-use 8-char Crockford Base32 codes, HMAC-SHA256 stored).
- Trusted device cookie (30 days, signed + HMAC stored in DB, revocable).
- Policy enforcement (mandatory for admins by default, optional grace days, optional mandatory for all).
- 10-minute sudo re-authentication for sensitive 2FA/email changes.
- Zero SMS, zero phone numbers, zero paid services (Decision D2 / Constraint C11).
"""

from __future__ import annotations

import io
import secrets
import time
from datetime import timedelta
from typing import List, Optional, Tuple

import pyotp
import segno
from django.conf import settings
from django.core import signing
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from .audit import get_client_ip, get_user_agent, log_audit
from .crypto import compare_hmac, hmac_sha256
from .email_service import send_projectauth_email
from .models import (
    AuthSettings,
    CodeChallenge,
    RecoveryCode,
    TOTPDevice,
    TrustedDevice,
)
from .throttling import check_and_increment_throttle

PREAUTH_SESSION_KEY = "pa_preauth_2fa"
PREAUTH_MAX_SECONDS = 600  # 10 minutes to complete 2FA challenge/enrolment

TRUSTED_DEVICE_COOKIE_NAME = "pa_trusted_device"
TRUSTED_DEVICE_SALT = "projectauth.trusted_device.v1"
TRUSTED_DEVICE_DAYS = 30

EMAIL_OTP_EXPIRY_MINUTES = 10
EMAIL_OTP_MAX_ATTEMPTS = 5

CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_LENGTH = 8


# ---------------------------------------------------------------------------
# Policy & Summary Helpers
# ---------------------------------------------------------------------------

def user_has_confirmed_totp(user) -> bool:
    if not user or not getattr(user, "pk", None):
        return False
    return TOTPDevice.objects.filter(user=user, confirmed_at__isnull=False).exists()


def user_requires_2fa_by_policy(user) -> bool:
    """
    Returns True if 2FA is mandatory for this user under AuthSettings / settings,
    accounting for optional twofa_grace_days.
    """
    if not user or not getattr(user, "pk", None):
        return False

    auth_settings = AuthSettings.load()
    is_admin = bool(user.is_superuser and user.is_staff)

    req_admins = bool(auth_settings.require_2fa_for_admins)
    req_all = bool(auth_settings.require_2fa_for_all)

    if not (req_all or (is_admin and req_admins)):
        return False

    grace_days = int(auth_settings.twofa_grace_days or 0)
    if grace_days > 0 and getattr(user, "date_joined", None):
        deadline = user.date_joined + timedelta(days=grace_days)
        if timezone.now() < deadline:
            return False

    return True


def get_user_2fa_summary(user) -> dict:
    confirmed_totp = (
        TOTPDevice.objects.filter(user=user, confirmed_at__isnull=False)
        .order_by("-confirmed_at")
        .first()
    )
    unused_recovery = RecoveryCode.objects.filter(user=user, used_at__isnull=True).count()
    trusted_devices = TrustedDevice.objects.filter(
        user=user, expires_at__gt=timezone.now()
    ).count()
    required_by_policy = user_requires_2fa_by_policy(user)
    return {
        "has_totp": confirmed_totp is not None,
        "totp_device": confirmed_totp,
        "unused_recovery_codes": unused_recovery,
        "trusted_device_count": trusted_devices,
        "required_by_policy": required_by_policy,
    }


# ---------------------------------------------------------------------------
# TOTP (RFC 6238) + Inline SVG QR
# ---------------------------------------------------------------------------

def generate_totp_secret() -> str:
    return pyotp.random_base32(length=32)


def get_or_create_pending_totp_device(user, name: str = "Authenticator App") -> TOTPDevice:
    pending = (
        TOTPDevice.objects.filter(user=user, confirmed_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if pending is not None:
        return pending
    device = TOTPDevice(user=user, name=name)
    device.set_secret(generate_totp_secret())
    device.save()
    return device


def build_totp_provisioning_uri(user, secret: str) -> str:
    issuer = getattr(settings, "PROJECTAUTH_SITE_NAME", "project-h")
    label = user.email or user.username
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=label, issuer_name=issuer)


def render_totp_qr_svg(provisioning_uri: str) -> str:
    """Renders the otpauth:// URI as an inline SVG string using segno (no image files)."""
    qr = segno.make(provisioning_uri, micro=False, error="m")
    buf = io.BytesIO()
    qr.save(
        buf,
        kind="svg",
        xmldecl=False,
        svgns=True,
        scale=4,
        border=2,
        svgclass="pa-qr-svg",
    )
    return buf.getvalue().decode("utf-8")


def normalize_otp_input(raw_code: str) -> str:
    if not raw_code:
        return ""
    return "".join(ch for ch in str(raw_code) if ch.isdigit())


def verify_totp_code(
    device: TOTPDevice,
    raw_code: str,
    *,
    now_timestamp: Optional[float] = None,
    confirm_if_pending: bool = False,
) -> bool:
    """
    Verifies a 6-digit TOTP code against `device` with +/-1 time step tolerance (30s step)
    and strict replay protection via `device.last_used_step` (Section 5.3).
    """
    code = normalize_otp_input(raw_code)
    if len(code) != 6:
        return False

    secret = device.get_secret()
    totp = pyotp.TOTP(secret, interval=30, digits=6)
    ts = float(now_timestamp if now_timestamp is not None else time.time())
    current_step = int(ts // 30)

    matched_step: Optional[int] = None
    for offset in (0, -1, 1):
        step = current_step + offset
        expected = totp.at(step * 30)
        if secrets.compare_digest(expected, code):
            matched_step = step
            break

    if matched_step is None:
        return False

    with transaction.atomic():
        locked = TOTPDevice.objects.select_for_update().get(pk=device.pk)
        if locked.last_used_step is not None and matched_step <= locked.last_used_step:
            # Replay detected
            return False
        locked.last_used_step = matched_step
        update_fields = ["last_used_step"]
        if confirm_if_pending and locked.confirmed_at is None:
            locked.confirmed_at = timezone.now()
            update_fields.append("confirmed_at")
        locked.save(update_fields=update_fields)
        device.last_used_step = locked.last_used_step
        device.confirmed_at = locked.confirmed_at

    return True


def verify_user_totp(user, raw_code: str, *, now_timestamp: Optional[float] = None) -> bool:
    devices = TOTPDevice.objects.filter(user=user, confirmed_at__isnull=False)
    for dev in devices:
        if verify_totp_code(dev, raw_code, now_timestamp=now_timestamp):
            return True
    return False


# ---------------------------------------------------------------------------
# Email One-Time Code (6 digits, 10-minute expiry, 5 attempts, HMAC stored)
# ---------------------------------------------------------------------------

def send_email_otp_challenge(
    user,
    *,
    purpose: str = CodeChallenge.PURPOSE_LOGIN_2FA,
    request: Optional[HttpRequest] = None,
) -> Tuple[bool, str]:
    """
    Generates a 6-digit email OTP, stores only its HMAC-SHA256 in CodeChallenge,
    and emails the code to `user.email`.
    Returns (sent: bool, message: str).
    """
    if not user.email:
        return False, "No email address is configured on this account."

    ip = get_client_ip(request) if request else None
    allowed_u, _ = check_and_increment_throttle(
        f"email_otp_send:{purpose}",
        str(user.pk),
        limit=5,
        window_seconds=600,
    )
    if not allowed_u:
        return False, "Too many verification codes requested. Please wait a few minutes."

    code = f"{secrets.randbelow(1_000_000):06d}"
    code_hmac = hmac_sha256(f"email_otp:{purpose}:{user.pk}", code)
    now = timezone.now()

    # Invalidate prior unconsumed email challenges for the same purpose
    CodeChallenge.objects.filter(
        user=user,
        purpose=purpose,
        channel="email",
        consumed_at__isnull=True,
    ).update(consumed_at=now)

    CodeChallenge.objects.create(
        user=user,
        purpose=purpose,
        channel="email",
        code_hmac=code_hmac,
        expires_at=now + timedelta(minutes=EMAIL_OTP_EXPIRY_MINUTES),
        attempts=0,
        ip=ip,
    )

    res = send_projectauth_email(
        "twofa_code",
        [user.email],
        context={
            "username": user.username,
            "code": code,
            "expires_minutes": EMAIL_OTP_EXPIRY_MINUTES,
        },
    )
    if not res.get("sent"):
        return False, "Unable to send verification email right now. Please use your authenticator app or recovery code."
    return True, "A 6-digit verification code has been sent to your email."


def verify_email_otp_challenge(
    user,
    raw_code: str,
    *,
    purpose: str = CodeChallenge.PURPOSE_LOGIN_2FA,
) -> bool:
    code = normalize_otp_input(raw_code)
    if len(code) != 6:
        return False

    now = timezone.now()
    with transaction.atomic():
        challenge = (
            CodeChallenge.objects.select_for_update()
            .filter(
                user=user,
                purpose=purpose,
                channel="email",
                consumed_at__isnull=True,
            )
            .order_by("-created_at")
            .first()
        )
        if challenge is None:
            return False

        if challenge.expires_at <= now or challenge.attempts >= EMAIL_OTP_MAX_ATTEMPTS:
            return False

        challenge.attempts += 1
        if compare_hmac(f"email_otp:{purpose}:{user.pk}", code, challenge.code_hmac):
            challenge.consumed_at = now
            challenge.save(update_fields=["attempts", "consumed_at"])
            return True

        challenge.save(update_fields=["attempts"])
        return False


# ---------------------------------------------------------------------------
# Recovery Codes (10 single-use 8-char Crockford Base32 codes)
# ---------------------------------------------------------------------------

def normalize_recovery_code(raw: str) -> str:
    if not raw:
        return ""
    cleaned = "".join(ch for ch in str(raw).upper() if ch.isalnum())
    # Crockford Base32 visual confusable mappings
    cleaned = cleaned.replace("I", "1").replace("L", "1").replace("O", "0")
    return cleaned


def format_recovery_code(norm_code: str) -> str:
    if len(norm_code) == 8:
        return f"{norm_code[:4]}-{norm_code[4:]}"
    return norm_code


def generate_recovery_codes_for_user(user) -> List[str]:
    """
    Deletes existing recovery codes for `user`, generates 10 fresh 8-character
    Crockford Base32 codes, stores only their HMAC-SHA256 digests, and returns
    the formatted plaintext codes to display ONCE.
    """
    plaintext_codes: List[str] = []
    new_rows: List[RecoveryCode] = []
    now = timezone.now()

    for _ in range(RECOVERY_CODE_COUNT):
        raw = "".join(secrets.choice(CROCKFORD_ALPHABET) for _ in range(RECOVERY_CODE_LENGTH))
        plaintext_codes.append(format_recovery_code(raw))
        digest = hmac_sha256(f"recovery_code:{user.pk}", raw)
        new_rows.append(
            RecoveryCode(
                user=user,
                code_hmac=digest,
                used_at=None,
                created_at=now,
            )
        )

    with transaction.atomic():
        RecoveryCode.objects.filter(user=user).delete()
        RecoveryCode.objects.bulk_create(new_rows)

    return plaintext_codes


def verify_and_consume_recovery_code(user, raw_code: str) -> bool:
    norm = normalize_recovery_code(raw_code)
    if len(norm) != RECOVERY_CODE_LENGTH:
        return False

    now = timezone.now()
    with transaction.atomic():
        unused_codes = list(
            RecoveryCode.objects.select_for_update().filter(user=user, used_at__isnull=True)
        )
        matched_row: Optional[RecoveryCode] = None
        for row in unused_codes:
            if compare_hmac(f"recovery_code:{user.pk}", norm, row.code_hmac):
                matched_row = row
                break
        if matched_row is None:
            return False
        matched_row.used_at = now
        matched_row.save(update_fields=["used_at"])
        return True


# ---------------------------------------------------------------------------
# Trusted Device (30 days)
# ---------------------------------------------------------------------------

def issue_trusted_device_cookie(request: HttpRequest, response: HttpResponse, user) -> str:
    raw_token = secrets.token_urlsafe(32)
    token_hmac = hmac_sha256("trusted_device", raw_token)
    now = timezone.now()
    expires_at = now + timedelta(days=TRUSTED_DEVICE_DAYS)

    TrustedDevice.objects.create(
        user=user,
        token_hmac=token_hmac,
        user_agent=get_user_agent(request),
        ip=get_client_ip(request),
        created_at=now,
        last_used_at=now,
        expires_at=expires_at,
    )

    signed_cookie = signing.dumps(
        {"uid": user.pk, "tok": raw_token},
        salt=TRUSTED_DEVICE_SALT,
    )
    response.set_cookie(
        TRUSTED_DEVICE_COOKIE_NAME,
        signed_cookie,
        max_age=TRUSTED_DEVICE_DAYS * 86400,
        httponly=True,
        samesite="Lax",
        secure=not getattr(settings, "DEBUG", False),
    )
    return raw_token


def is_request_from_trusted_device(request: HttpRequest, user) -> bool:
    cookie_val = request.COOKIES.get(TRUSTED_DEVICE_COOKIE_NAME)
    if not cookie_val or not user or not getattr(user, "pk", None):
        return False
    try:
        data = signing.loads(
            cookie_val,
            salt=TRUSTED_DEVICE_SALT,
            max_age=TRUSTED_DEVICE_DAYS * 86400,
        )
    except Exception:
        return False

    if data.get("uid") != user.pk:
        return False
    raw_token = data.get("tok")
    if not raw_token:
        return False

    token_hmac = hmac_sha256("trusted_device", raw_token)
    now = timezone.now()
    td = TrustedDevice.objects.filter(
        user=user,
        token_hmac=token_hmac,
        expires_at__gt=now,
    ).first()
    if td is None:
        return False

    td.last_used_at = now
    td.save(update_fields=["last_used_at"])
    return True


def revoke_all_trusted_devices(user) -> int:
    deleted, _ = TrustedDevice.objects.filter(user=user).delete()
    return deleted


# ---------------------------------------------------------------------------
# Pre-Auth Session State & Login Interposition
# ---------------------------------------------------------------------------

def set_preauth_state(
    request: HttpRequest,
    user,
    *,
    remember_me: bool = False,
    next_url: str = "",
    must_enrol: bool = False,
) -> None:
    request.session[PREAUTH_SESSION_KEY] = {
        "uid": user.pk,
        "ts": timezone.now().timestamp(),
        "remember_me": bool(remember_me),
        "next": next_url or "",
        "must_enrol": bool(must_enrol),
    }
    request.session.modified = True


def get_preauth_user_and_state(request: HttpRequest):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    state = request.session.get(PREAUTH_SESSION_KEY)
    if not state or not isinstance(state, dict):
        return None, None
    ts = float(state.get("ts") or 0)
    if (timezone.now().timestamp() - ts) > PREAUTH_MAX_SECONDS:
        request.session.pop(PREAUTH_SESSION_KEY, None)
        return None, None
    uid = state.get("uid")
    if not uid:
        return None, None
    user = User.objects.select_related("profile").filter(pk=uid, is_active=True).first()
    if user is None:
        request.session.pop(PREAUTH_SESSION_KEY, None)
        return None, None
    return user, state


def clear_preauth_state(request: HttpRequest) -> None:
    request.session.pop(PREAUTH_SESSION_KEY, None)


def should_interpose_2fa(
    request: HttpRequest,
    user,
    *,
    remember_me: bool = False,
    next_url: str = "",
) -> bool:
    """
    Determines whether password login must stop before calling login() and require
    2FA verification or mandatory 2FA enrolment.
    """
    has_totp = user_has_confirmed_totp(user)
    must_have = user_requires_2fa_by_policy(user)

    if not has_totp and not must_have:
        return False

    # If user already has 2FA confirmed and this request carries a valid 30-day trusted device cookie, skip challenge
    if has_totp and is_request_from_trusted_device(request, user):
        return False

    return True


def begin_2fa_flow(
    request: HttpRequest,
    user,
    *,
    remember_me: bool = False,
    next_url: str = "",
) -> HttpResponse:
    has_totp = user_has_confirmed_totp(user)
    must_enrol = not has_totp and user_requires_2fa_by_policy(user)
    set_preauth_state(
        request,
        user,
        remember_me=remember_me,
        next_url=next_url,
        must_enrol=must_enrol,
    )
    if must_enrol:
        log_audit("twofa.enrol_required", request=request, target_user=user)
        return redirect("projectauth:twofa_setup")

    log_audit("twofa.challenge_started", request=request, target_user=user)
    return redirect("projectauth:twofa_challenge")


def reset_user_2fa(user, *, actor=None, request: Optional[HttpRequest] = None, via_cli: bool = False) -> None:
    """
    Removes all 2FA devices, recovery codes, trusted devices, and pending 2FA challenges for `user`.
    """
    with transaction.atomic():
        TOTPDevice.objects.filter(user=user).delete()
        RecoveryCode.objects.filter(user=user).delete()
        TrustedDevice.objects.filter(user=user).delete()
        CodeChallenge.objects.filter(
            user=user,
            purpose__in=[CodeChallenge.PURPOSE_LOGIN_2FA, CodeChallenge.PURPOSE_REAUTH],
        ).delete()

    action = "twofa.cli_reset" if via_cli else "twofa.reset"
    log_audit(
        action,
        request=request,
        actor=actor,
        target_user=user,
    )
    if user.email:
        send_projectauth_email(
            "twofa_disabled",
            [user.email],
            context={"username": user.username},
        )
