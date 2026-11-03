"""
Email sending wrapper with daily email budget guard (Decision D4, Section 10, 14, 15).
- Enforces PROJECTAUTH_MAX_EMAILS_PER_DAY (default 300) in the database.
- Exposes 80% warning state for the admin console health check.
- Catches SMTP/transport failures and logs without exposing secrets, OTPs, or tokens.
- Renders .txt and .html templates from projectauth/templates/projectauth_emails/.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Sequence

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import escape

from .audit import log_audit
from .crypto import hmac_sha256
from .models import Throttle

security_logger = logging.getLogger("projectauth.security")

DAILY_BUDGET_SCOPE = "daily_email_budget"

EMAIL_SUBJECTS: Dict[str, str] = {
    "verify_email": "Verify your email address",
    "already_registered_notice": "Sign-up attempt for your email address",
    "account_approved": "Your account has been approved",
    "account_rejected": "Update on your account request",
    "password_reset": "Password reset instructions",
    "password_changed": "Your password was changed",
    "username_reminder": "Your username reminder",
    "email_change_confirm_new": "Confirm your new email address",
    "email_change_notice_old": "Security notice: email change requested",
    "new_device_login": "New sign-in to your account",
    "twofa_enabled": "Two-factor authentication enabled",
    "twofa_disabled": "Two-factor authentication changed",
    "twofa_code": "Your verification code",
    "admin_invite": "You have been invited as an administrator",
    "admin_new_signup": "New account awaiting approval",
    "access_granted": "App access granted",
    "access_denied": "Update on your app access request",
    "access_revoked": "App access updated",
    "account_deleted": "Your account has been deleted",
    "email_test": "Test email configuration check",
}


def _today_budget_key_hmac() -> str:
    today_str = timezone.now().strftime("%Y-%m-%d")
    return hmac_sha256(f"throttle:{DAILY_BUDGET_SCOPE}", today_str)


def get_daily_email_cap() -> int:
    try:
        cap = int(getattr(settings, "PROJECTAUTH_MAX_EMAILS_PER_DAY", 300))
    except (TypeError, ValueError):
        cap = 300
    return max(1, cap)


def get_daily_email_status() -> Dict[str, Any]:
    """
    Returns current UTC day's email counter, cap, percentage, and 80% warning flag.
    """
    cap = get_daily_email_cap()
    kh = _today_budget_key_hmac()
    row = Throttle.objects.filter(scope=DAILY_BUDGET_SCOPE, key_hmac=kh).first()
    sent_today = row.count if row else 0
    percent = round((sent_today / cap) * 100.0, 1) if cap > 0 else 100.0
    return {
        "sent_today": sent_today,
        "daily_cap": cap,
        "percent": percent,
        "warning_80": sent_today >= int(cap * 0.8),
        "exhausted": sent_today >= cap,
    }


def _reserve_email_budget(recipient_count: int = 1) -> bool:
    """
    Atomically reserves `recipient_count` emails against today's budget.
    Returns True if within cap, False if budget would be exceeded.
    """
    cap = get_daily_email_cap()
    kh = _today_budget_key_hmac()
    now = timezone.now()

    with transaction.atomic():
        row, _ = Throttle.objects.select_for_update().get_or_create(
            scope=DAILY_BUDGET_SCOPE,
            key_hmac=kh,
            defaults={"count": 0, "window_started_at": now},
        )
        if row.count + recipient_count > cap:
            return False
        row.count += recipient_count
        row.save(update_fields=["count"])
        if row.count >= int(cap * 0.8):
            security_logger.warning(
                "Daily email budget at %d/%d (%.1f%%).",
                row.count,
                cap,
                (row.count / cap) * 100.0,
            )
        return True


def build_absolute_url(path: str) -> str:
    base = str(getattr(settings, "PROJECTAUTH_BASE_URL", "http://127.0.0.1:8000")).rstrip("/")
    if not path:
        return base
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if not path.startswith("/"):
        path = "/" + path
    return f"{base}{path}"


def send_projectauth_email(
    template_name: str,
    to_emails: Sequence[str] | str,
    context: Dict[str, Any] | None = None,
    *,
    subject: str | None = None,
    fail_silently: bool = True,
) -> Dict[str, Any]:
    """
    Sends a multi-part (.txt + .html) email through Django's configured EMAIL_BACKEND,
    enforcing the daily budget guard and catching SMTP errors safely.
    Never puts secrets in the subject line.
    """
    if isinstance(to_emails, str):
        recipients: List[str] = [to_emails.strip()] if to_emails.strip() else []
    else:
        recipients = [str(e).strip() for e in to_emails if str(e).strip()]

    if not recipients:
        return {"sent": False, "reason": "no_recipients"}

    if not _reserve_email_budget(len(recipients)):
        log_audit(
            "email.budget_exceeded",
            details={
                "template": template_name,
                "recipient_count": len(recipients),
                "daily_cap": get_daily_email_cap(),
            },
        )
        security_logger.error(
            "Email blocked by daily budget guard (template=%s, cap=%d).",
            template_name,
            get_daily_email_cap(),
        )
        return {"sent": False, "reason": "budget_exceeded"}

    site_name = getattr(settings, "PROJECTAUTH_SITE_NAME", "project-h")
    base_url = getattr(settings, "PROJECTAUTH_BASE_URL", "http://127.0.0.1:8000")

    ctx: Dict[str, Any] = {
        "site_name": site_name,
        "base_url": base_url.rstrip("/"),
        "timestamp_utc": timezone.now().strftime("%d %b %Y %H:%M UTC"),
    }
    if context:
        ctx.update(context)

    raw_subject = subject or EMAIL_SUBJECTS.get(template_name, "Account notification")
    # Ensure single-line subject prefixed with site name
    clean_subject = " ".join(str(raw_subject).splitlines()).strip()
    if not clean_subject.startswith(f"[{site_name}]"):
        full_subject = f"[{site_name}] {clean_subject}"
    else:
        full_subject = clean_subject

    txt_template = f"projectauth_emails/{template_name}.txt"
    html_template = f"projectauth_emails/{template_name}.html"

    try:
        text_body = render_to_string(txt_template, ctx)
    except TemplateDoesNotExist:
        text_body = _fallback_text_body(template_name, ctx)

    try:
        html_body = render_to_string(html_template, ctx)
    except TemplateDoesNotExist:
        html_body = _fallback_html_body(template_name, ctx, text_body)

    from_email = (
        getattr(settings, "DEFAULT_FROM_EMAIL", None)
        or getattr(settings, "EMAIL_HOST_USER", None)
        or f"noreply@{site_name}.local"
    )

    msg = EmailMultiAlternatives(
        subject=full_subject,
        body=text_body,
        from_email=from_email,
        to=recipients,
    )
    msg.attach_alternative(html_body, "text/html")

    try:
        msg.send(fail_silently=False)
        return {"sent": True, "reason": "ok", "subject": full_subject}
    except Exception as exc:
        err_type = type(exc).__name__
        security_logger.error(
            "SMTP/email send failure (template=%s, error_type=%s).",
            template_name,
            err_type,
        )
        log_audit(
            "email.send_error",
            details={"template": template_name, "error_type": err_type},
        )
        if not fail_silently:
            raise
        return {"sent": False, "reason": "smtp_error", "error_type": err_type}


def _fallback_text_body(template_name: str, ctx: Dict[str, Any]) -> str:
    site_name = ctx.get("site_name", "project-h")
    lines = [f"{site_name} — {EMAIL_SUBJECTS.get(template_name, 'Security notification')}", ""]
    if ctx.get("username"):
        lines.append(f"Hello {ctx['username']},")
        lines.append("")
    if ctx.get("usernames"):
        lines.append(f"Your registered username(s): {ctx['usernames']}")
        lines.append("")
    if ctx.get("message"):
        lines.append(str(ctx["message"]))
        lines.append("")
    if ctx.get("code"):
        lines.append(f"Your one-time verification code is: {ctx['code']}")
        lines.append(f"This code expires in {ctx.get('expires_minutes', 10)} minutes.")
        lines.append("")
    if ctx.get("action_url"):
        lines.append(f"Open this link to continue: {ctx['action_url']}")
        lines.append("")
    lines.append(
        "If this wasn't you, please ignore this email or contact the site administrator immediately."
    )
    lines.append(f"Time: {ctx.get('timestamp_utc', '')}")
    return "\n".join(lines)


def _fallback_html_body(template_name: str, ctx: Dict[str, Any], text_body: str) -> str:
    escaped = escape(text_body).replace("\n", "<br>\n")
    return (
        "<!DOCTYPE html><html><body style=\"font-family:sans-serif;line-height:1.5;color:#222;\">"
        f"<div style=\"max-width:560px;margin:20px auto;padding:20px;border:1px solid #ddd;border-radius:8px;\">{escaped}</div>"
        "</body></html>"
    )


def diagnose_email_settings() -> List[str]:
    """
    Returns a plain-language diagnostic checklist of current Django email / Gmail SMTP settings
    for `manage.py projectauth_email_test` (Section 13 & 19.6).
    """
    notes: List[str] = []
    backend = getattr(settings, "EMAIL_BACKEND", "")
    host = getattr(settings, "EMAIL_HOST", "")
    port = getattr(settings, "EMAIL_PORT", 587)
    use_tls = getattr(settings, "EMAIL_USE_TLS", True)
    host_user = getattr(settings, "EMAIL_HOST_USER", "")
    host_pw = getattr(settings, "EMAIL_HOST_PASSWORD", "")
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "")
    budget = get_daily_email_status()

    notes.append(f"EMAIL_BACKEND: {backend}")
    if "console" in backend:
        notes.append(
            "INFO: Using console email backend (emails print to stdout). Suitable for local development only."
        )
    elif "smtp" in backend:
        notes.append(f"SMTP Host: {host or '(empty)'}:{port} (TLS={use_tls})")
        if not host:
            notes.append("WARNING: EMAIL_HOST is empty. Set EMAIL_HOST=smtp.gmail.com for Gmail SMTP.")
        if int(port or 0) != 587 or not use_tls:
            notes.append("WARNING: Gmail SMTP recommends EMAIL_PORT=587 and EMAIL_USE_TLS=True.")
        if not host_user:
            notes.append("WARNING: EMAIL_HOST_USER is empty.")
        if not host_pw:
            notes.append(
                "WARNING: EMAIL_HOST_PASSWORD is empty. Generate a 16-character Google App Password (requires 2-Step Verification)."
            )
        elif len(str(host_pw).replace(" ", "")) != 16 and "gmail" in str(host).lower():
            notes.append(
                "NOTE: Google App Passwords are 16 characters (spaces removed). Check that you are not using your normal account password."
            )
        if host_user and from_email and host_user.strip().lower() != from_email.strip().lower():
            notes.append(
                "WARNING: DEFAULT_FROM_EMAIL does not match EMAIL_HOST_USER. Gmail rewrites or rejects mismatched sender addresses."
            )
    notes.append(
        f"Daily Email Budget: {budget['sent_today']}/{budget['daily_cap']} sent today ({budget['percent']}%)."
    )
    return notes

