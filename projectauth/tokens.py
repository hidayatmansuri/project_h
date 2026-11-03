"""
Signed single-use token generation and verification for projectauth (Section 5.1, 5.4, 7).
Uses django.core.signing (HMAC-SHA256) with purpose-specific salts, max_age expiry,
and database nonce tracking (CodeChallenge) so every link is strictly single-use.
Password reset tokens also bind the user's password hash/timestamp so any password
change immediately invalidates outstanding reset tokens.
"""

from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any, Dict, Optional, Tuple

from django.contrib.auth import get_user_model
from django.core import signing
from django.utils import timezone

from .crypto import hmac_sha256
from .models import CodeChallenge

User = get_user_model()

VERIFY_EMAIL_SALT = "projectauth.verify_email.v1"
PASSWORD_RESET_SALT = "projectauth.password_reset.v1"
EMAIL_CHANGE_SALT = "projectauth.email_change.v1"
FORM_TIMING_SALT = "projectauth.form_timing.v1"

VERIFY_EMAIL_MAX_AGE = 60 * 60 * 24  # 24 hours
PASSWORD_RESET_MAX_AGE = 60 * 60     # 1 hour
EMAIL_CHANGE_MAX_AGE = 60 * 60 * 24  # 24 hours


class TokenValidationError(ValueError):
    """Raised when a signed token is expired, tampered, already consumed, or invalidated."""


def mask_email(email: str) -> str:
    """Masks an email address for UI display, e.g. 'alice@example.com' -> 'a***e@example.com'."""
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if len(local) <= 1:
        masked_local = "*"
    elif len(local) == 2:
        masked_local = local[0] + "*"
    else:
        masked_local = local[0] + ("*" * min(4, len(local) - 2)) + local[-1]
    return f"{masked_local}@{domain}"


def _password_fingerprint(user) -> str:
    pw_changed = ""
    try:
        if user.profile.password_changed_at:
            pw_changed = user.profile.password_changed_at.isoformat()
    except Exception:
        pass
    return hmac_sha256("pw_fp", f"{user.pk}:{user.password}:{pw_changed}")[:24]


def create_email_verification_token(user, *, ip: Optional[str] = None) -> str:
    nonce = secrets.token_urlsafe(24)
    nonce_hmac = hmac_sha256(CodeChallenge.PURPOSE_VERIFY_EMAIL_NONCE, nonce)
    now = timezone.now()
    CodeChallenge.objects.create(
        user=user,
        purpose=CodeChallenge.PURPOSE_VERIFY_EMAIL_NONCE,
        channel="email",
        code_hmac=nonce_hmac,
        expires_at=now + timedelta(seconds=VERIFY_EMAIL_MAX_AGE),
        ip=ip,
    )
    payload = {
        "uid": user.pk,
        "email": (user.email or "").lower(),
        "nonce": nonce,
    }
    return signing.dumps(payload, salt=VERIFY_EMAIL_SALT)


def verify_email_verification_token(token: str, *, consume: bool = True):
    try:
        data = signing.loads(token, salt=VERIFY_EMAIL_SALT, max_age=VERIFY_EMAIL_MAX_AGE)
    except signing.SignatureExpired as exc:
        raise TokenValidationError("Verification link has expired.") from exc
    except signing.BadSignature as exc:
        raise TokenValidationError("Invalid verification link.") from exc

    uid = data.get("uid")
    nonce = data.get("nonce")
    if not uid or not nonce:
        raise TokenValidationError("Malformed verification token.")

    user = User.objects.select_related("profile").filter(pk=uid).first()
    if user is None:
        raise TokenValidationError("Account not found.")

    nonce_hmac = hmac_sha256(CodeChallenge.PURPOSE_VERIFY_EMAIL_NONCE, nonce)
    now = timezone.now()
    challenge = (
        CodeChallenge.objects.filter(
            user=user,
            purpose=CodeChallenge.PURPOSE_VERIFY_EMAIL_NONCE,
            code_hmac=nonce_hmac,
        )
        .first()
    )
    if challenge is None or not challenge.is_valid(now=now):
        raise TokenValidationError("This verification link has already been used or expired.")

    if consume:
        challenge.consumed_at = now
        challenge.save(update_fields=["consumed_at"])

    return user


def create_password_reset_token(user, *, ip: Optional[str] = None) -> str:
    nonce = secrets.token_urlsafe(24)
    nonce_hmac = hmac_sha256(CodeChallenge.PURPOSE_PASSWORD_RESET_NONCE, nonce)
    now = timezone.now()
    CodeChallenge.objects.create(
        user=user,
        purpose=CodeChallenge.PURPOSE_PASSWORD_RESET_NONCE,
        channel="email",
        code_hmac=nonce_hmac,
        expires_at=now + timedelta(seconds=PASSWORD_RESET_MAX_AGE),
        ip=ip,
    )
    payload = {
        "uid": user.pk,
        "nonce": nonce,
        "pfp": _password_fingerprint(user),
    }
    return signing.dumps(payload, salt=PASSWORD_RESET_SALT)


def verify_password_reset_token(token: str, *, consume: bool = False):
    try:
        data = signing.loads(token, salt=PASSWORD_RESET_SALT, max_age=PASSWORD_RESET_MAX_AGE)
    except signing.SignatureExpired as exc:
        raise TokenValidationError("Password reset link has expired.") from exc
    except signing.BadSignature as exc:
        raise TokenValidationError("Invalid password reset link.") from exc

    uid = data.get("uid")
    nonce = data.get("nonce")
    pfp = data.get("pfp")
    if not uid or not nonce or not pfp:
        raise TokenValidationError("Malformed password reset token.")

    user = User.objects.select_related("profile").filter(pk=uid).first()
    if user is None:
        raise TokenValidationError("Account not found.")

    # Invalidate immediately if password was changed since the token was issued
    if not secrets.compare_digest(pfp, _password_fingerprint(user)):
        raise TokenValidationError("This password reset link is no longer valid because the password was changed.")

    nonce_hmac = hmac_sha256(CodeChallenge.PURPOSE_PASSWORD_RESET_NONCE, nonce)
    now = timezone.now()
    challenge = (
        CodeChallenge.objects.filter(
            user=user,
            purpose=CodeChallenge.PURPOSE_PASSWORD_RESET_NONCE,
            code_hmac=nonce_hmac,
        )
        .first()
    )
    if challenge is None or not challenge.is_valid(now=now):
        raise TokenValidationError("This password reset link has already been used or expired.")

    if consume:
        challenge.consumed_at = now
        challenge.save(update_fields=["consumed_at"])

    return user


def create_form_timing_token() -> str:
    return signing.dumps({"ts": timezone.now().timestamp()}, salt=FORM_TIMING_SALT)


def check_form_timing_token(token: str, min_seconds: float) -> bool:
    if min_seconds <= 0:
        return True
    if not token:
        return False
    try:
        data = signing.loads(token, salt=FORM_TIMING_SALT, max_age=60 * 60 * 6)
        issued_ts = float(data.get("ts", 0))
    except Exception:
        return False
    elapsed = timezone.now().timestamp() - issued_ts
    return elapsed >= min_seconds

