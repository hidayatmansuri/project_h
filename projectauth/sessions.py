"""
Session lifecycle, device detection, revocation, and idle timeout management (Section 5.2, 5.4, 7).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Optional

from django.contrib.sessions.models import Session
from django.http import HttpRequest
from django.utils import timezone

from .audit import get_client_ip, get_user_agent
from .crypto import hmac_sha256
from .email_service import send_projectauth_email
from .models import SessionRecord

SESSION_MAX_DAYS = 30


def hash_session_key(session_key: str) -> str:
    return hmac_sha256("session_key", session_key or "")


def register_authenticated_session(
    request: HttpRequest,
    user,
    *,
    remember_me: bool = False,
    send_new_device_alert: bool = True,
) -> SessionRecord:
    """
    Records or updates the SessionRecord for a newly authenticated session,
    sets cookie expiry (browser-session vs 30-day remember_me), initializes
    idle-timeout timestamps, and sends a new-device alert email when appropriate.
    """
    now = timezone.now()
    if remember_me:
        request.session.set_expiry(60 * 60 * 24 * SESSION_MAX_DAYS)
    else:
        request.session.set_expiry(0)

    if not request.session.session_key:
        request.session.save()

    sk = request.session.session_key
    sk_hash = hash_session_key(sk)
    ip = get_client_ip(request)
    ua = get_user_agent(request)

    request.session["pa_last_activity_ts"] = int(now.timestamp())
    request.session["pa_created_ts"] = int(now.timestamp())
    request.session["pa_session_tracked"] = True

    # Check if user has prior sessions and whether this (ip, user_agent) is new
    has_prior_sessions = SessionRecord.objects.filter(user=user).exists()
    known_device = SessionRecord.objects.filter(
        user=user,
        ip=ip,
        user_agent=ua,
    ).exists()

    record, _ = SessionRecord.objects.update_or_create(
        session_key_hash=sk_hash,
        defaults={
            "user": user,
            "ip": ip,
            "user_agent": ua,
            "last_seen_at": now,
            "expires_at": now + timedelta(days=SESSION_MAX_DAYS),
            "revoked_at": None,
        },
    )

    try:
        profile = user.profile
        profile.last_seen_at = now
        profile.save(update_fields=["last_seen_at"])
    except Exception:
        pass

    if send_new_device_alert and has_prior_sessions and not known_device and user.email:
        send_projectauth_email(
            "new_device_login",
            [user.email],
            context={
                "username": user.username,
                "ip": ip or "Unknown IP",
                "user_agent": ua or "Unknown browser/device",
            },
        )

    return record


def revoke_session_by_id(user, record_id: int) -> bool:
    now = timezone.now()
    updated = SessionRecord.objects.filter(
        pk=record_id,
        user=user,
        revoked_at__isnull=True,
    ).update(revoked_at=now)
    return updated > 0


def revoke_other_sessions(user, current_session_key: Optional[str]) -> int:
    now = timezone.now()
    qs = SessionRecord.objects.filter(user=user, revoked_at__isnull=True)
    if current_session_key:
        qs = qs.exclude(session_key_hash=hash_session_key(current_session_key))
    return qs.update(revoked_at=now)


def revoke_all_user_sessions(user) -> int:
    now = timezone.now()
    count = SessionRecord.objects.filter(user=user, revoked_at__isnull=True).update(
        revoked_at=now
    )
    # Also purge any matching Django Session rows if decodable
    try:
        for s in Session.objects.all():
            data = s.get_decoded()
            if str(data.get("_auth_user_id")) == str(user.pk):
                s.delete()
    except Exception:
        pass
    return count

