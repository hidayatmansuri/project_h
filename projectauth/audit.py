"""
Append-only security audit logging and safe client IP / User-Agent extraction (Section 4.2 & 7).
Never logs or stores secrets, passwords, OTP codes, recovery codes, or raw tokens.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from django.conf import settings
from django.http import HttpRequest

from .models import AuditEvent

security_logger = logging.getLogger("projectauth.security")

FORBIDDEN_DETAIL_SUBSTRINGS = (
    "password",
    "secret",
    "token",
    "otp",
    "code",
    "recovery",
    "private_key",
    "authorization",
    "cookie",
)


def get_client_ip(request: Optional[HttpRequest]) -> Optional[str]:
    """
    Extracts client IP safely. Respects AXES_IPWARE_PROXY_COUNT when behind a reverse proxy
    (Section 5.2 & 19.5) so X-Forwarded-For spoofing cannot bypass lockouts when proxy count is 0.
    """
    if request is None:
        return None
    meta = getattr(request, "META", {}) or {}
    proxy_count = int(getattr(settings, "AXES_IPWARE_PROXY_COUNT", 0) or 0)
    if proxy_count > 0:
        xff = meta.get("HTTP_X_FORWARDED_FOR", "")
        if xff:
            parts = [p.strip() for p in xff.split(",") if p.strip()]
            if parts:
                idx = max(0, len(parts) - proxy_count)
                return parts[idx][:45]
    remote_addr = meta.get("REMOTE_ADDR")
    if remote_addr:
        return str(remote_addr).strip()[:45]
    return None


def get_user_agent(request: Optional[HttpRequest]) -> str:
    if request is None:
        return ""
    meta = getattr(request, "META", {}) or {}
    ua = meta.get("HTTP_USER_AGENT", "") or ""
    return str(ua)[:500]


def scrub_audit_details(details: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Recursively removes or redacts any dictionary key that looks like a secret, password,
    token, or code before storing in AuditEvent.details or emitting to logs.
    """
    if not details or not isinstance(details, dict):
        return {}
    clean: Dict[str, Any] = {}
    for k, v in details.items():
        key_str = str(k)
        key_lower = key_str.lower()
        if any(bad in key_lower for bad in FORBIDDEN_DETAIL_SUBSTRINGS):
            continue
        if isinstance(v, dict):
            clean[key_str] = scrub_audit_details(v)
        elif isinstance(v, (list, tuple)):
            clean[key_str] = [
                scrub_audit_details(item) if isinstance(item, dict) else str(item)[:200]
                for item in v
            ]
        elif isinstance(v, (int, float, bool)) or v is None:
            clean[key_str] = v
        else:
            clean[key_str] = str(v)[:500]
    return clean


def log_audit(
    action: str,
    *,
    request: Optional[HttpRequest] = None,
    actor=None,
    target_user=None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    actor_label: str = "",
    target_label: str = "",
) -> AuditEvent:
    """
    Appends an AuditEvent row and emits a structured line to the projectauth.security logger.
    """
    if actor is None and request is not None:
        req_user = getattr(request, "user", None)
        if req_user is not None and getattr(req_user, "is_authenticated", False):
            actor = req_user

    resolved_ip = ip if ip is not None else get_client_ip(request)
    resolved_ua = user_agent if user_agent is not None else get_user_agent(request)
    safe_details = scrub_audit_details(details)

    if actor is not None and not getattr(actor, "pk", None):
        actor = None
    if target_user is not None and not getattr(target_user, "pk", None):
        target_user = None

    if not actor_label and actor is not None:
        actor_label = getattr(actor, "username", "")
    if not target_label and target_user is not None:
        target_label = getattr(target_user, "username", "")

    event = AuditEvent.objects.create(
        actor=actor,
        actor_label=actor_label,
        target_user=target_user,
        target_label=target_label,
        action=action,
        ip=resolved_ip,
        user_agent=resolved_ua or "",
        details=safe_details,
    )

    security_logger.info(
        "audit action=%s actor=%s target=%s ip=%s details=%s",
        action,
        actor_label or "anonymous",
        target_label or "-",
        resolved_ip or "-",
        safe_details,
    )
    return event

