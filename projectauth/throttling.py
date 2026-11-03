"""
Database-backed rate limiting (Throttle model) for emails, OTP attempts, signups, and reminders.
Does NOT rely on LocMemCache (Section 2 & 19.4).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Tuple

from django.db import transaction
from django.utils import timezone

from .crypto import hmac_sha256, normalize_identifier
from .models import Throttle


def _throttle_key_hmac(scope: str, raw_key: str) -> str:
    norm = normalize_identifier(raw_key or "global")
    return hmac_sha256(f"throttle:{scope}", norm)


def is_throttled(
    scope: str,
    raw_key: str,
    *,
    limit: int,
    window_seconds: int,
) -> Tuple[bool, int]:
    """
    Read-only check whether (scope, raw_key) is currently locked or over limit.
    Returns (throttled: bool, retry_after_seconds: int).
    """
    now = timezone.now()
    kh = _throttle_key_hmac(scope, raw_key)
    row = Throttle.objects.filter(scope=scope, key_hmac=kh).first()
    if row is None:
        return False, 0

    if row.locked_until and row.locked_until > now:
        remaining = max(1, int((row.locked_until - now).total_seconds()))
        return True, remaining

    window_end = row.window_started_at + timedelta(seconds=window_seconds)
    if now >= window_end:
        return False, 0

    if row.count >= limit:
        remaining = max(1, int((window_end - now).total_seconds()))
        return True, remaining

    return False, 0


def check_and_increment_throttle(
    scope: str,
    raw_key: str,
    *,
    limit: int,
    window_seconds: int,
    lockout_seconds: int = 0,
) -> Tuple[bool, int]:
    """
    Atomically checks and increments the counter for (scope, raw_key).
    Returns (allowed: bool, retry_after_seconds: int).
    """
    now = timezone.now()
    kh = _throttle_key_hmac(scope, raw_key)

    with transaction.atomic():
        row, created = Throttle.objects.select_for_update().get_or_create(
            scope=scope,
            key_hmac=kh,
            defaults={
                "count": 0,
                "window_started_at": now,
                "locked_until": None,
            },
        )

        if row.locked_until and row.locked_until > now:
            remaining = max(1, int((row.locked_until - now).total_seconds()))
            return False, remaining

        window_end = row.window_started_at + timedelta(seconds=window_seconds)
        if now >= window_end or (row.locked_until and row.locked_until <= now):
            row.count = 0
            row.window_started_at = now
            row.locked_until = None
            window_end = now + timedelta(seconds=window_seconds)

        if row.count >= limit:
            if lockout_seconds > 0:
                row.locked_until = now + timedelta(seconds=lockout_seconds)
                row.save(update_fields=["locked_until"])
                return False, lockout_seconds
            remaining = max(1, int((window_end - now).total_seconds()))
            return False, remaining

        row.count += 1
        if row.count >= limit and lockout_seconds > 0:
            row.locked_until = now + timedelta(seconds=lockout_seconds)
        row.save(update_fields=["count", "window_started_at", "locked_until"])
        return True, 0


def reset_throttle(scope: str, raw_key: str) -> None:
    kh = _throttle_key_hmac(scope, raw_key)
    Throttle.objects.filter(scope=scope, key_hmac=kh).delete()

