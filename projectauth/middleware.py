"""
Middleware for projectauth (Sections 5.2, 5.5, 7, 9):
- IdleTimeoutMiddleware: session revocation check, status enforcement, idle timeout,
  30-day absolute cap, SessionRecord upkeep, and forced password change redirect.
- ProjectAuthMiddleware: default-deny per-app authorization via process_view,
  enforcing full vs read_only levels, grant expiry, JSON 401/403 vs HTML redirect/403,
  admin 2FA requirement, and Cache-Control: no-store on protected responses.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import patch_cache_control

from . import twofa
from .access import (
    evaluate_app_access,
    is_json_request,
    resolve_view_app_label,
)
from .audit import log_audit
from .models import (
    AccessRequest,
    AppAccess,
    AuthSettings,
    ProtectedApp,
    SessionRecord,
    UserProfile,
)
from .sessions import SESSION_MAX_DAYS, hash_session_key


def render_access_denied_response(
    request: HttpRequest,
    *,
    app_label: str,
    protected_app: Optional[ProtectedApp] = None,
    reason: str = "denied_no_grant",
    grant: Optional[AppAccess] = None,
) -> HttpResponse:
    from .views import _get_admin_notification_recipients, render_projectauth

    if protected_app is None and app_label:
        protected_app = ProtectedApp.objects.filter(app_label=app_label).first()

    app_name = protected_app.name if protected_app else app_label
    existing_request = None
    if getattr(request.user, "is_authenticated", False) and protected_app is not None:
        existing_request = (
            AccessRequest.objects.filter(
                user=request.user,
                app=protected_app,
                status=AccessRequest.STATUS_PENDING,
            )
            .order_by("-created_at")
            .first()
        )

    admin_contacts = _get_admin_notification_recipients()
    admin_contact = admin_contacts[0] if admin_contacts else getattr(settings, "DEFAULT_FROM_EMAIL", "")

    return render_projectauth(
        request,
        "access_denied",
        {
            "denied_app_label": app_label,
            "denied_app": protected_app,
            "denied_app_name": app_name,
            "denied_reason": reason,
            "read_only_blocked": reason == "denied_read_only_method",
            "expired_grant": reason == "denied_expired_grant",
            "grant": grant,
            "existing_request": existing_request,
            "admin_contact": admin_contact,
        },
        status=403,
    )


def enforce_app_access_for_request(
    request: HttpRequest,
    app_label: str,
) -> Optional[HttpResponse]:
    """
    Core decision table for a non-public app request.
    Returns None if allowed, or an HttpResponse (302, 401 JSON, or 403 HTML/JSON) if blocked.
    """
    public_apps = set(getattr(settings, "PROJECTAUTH_PUBLIC_APPS", ["home", "cv"]))
    if app_label in public_apps or app_label in ("staticfiles", "projectauth"):
        return None

    user = getattr(request, "user", None)
    wants_json = is_json_request(request)

    # 1. Anonymous request
    if user is None or not getattr(user, "is_authenticated", False):
        if wants_json:
            return JsonResponse(
                {"success": False, "error": "Authentication required."},
                status=401,
            )
        login_url = reverse("projectauth:login")
        next_q = quote(request.get_full_path())
        return redirect(f"{login_url}?next={next_q}")

    # 2. Active user & profile status check
    profile = getattr(user, "profile", None)
    if not user.is_active:
        if wants_json:
            return JsonResponse(
                {"success": False, "error": "Account is inactive."},
                status=403,
            )
        return redirect("projectauth:login")

    if profile is not None and profile.status != UserProfile.STATUS_ACTIVE:
        if wants_json:
            return JsonResponse(
                {"success": False, "error": "Account is pending approval or restricted."},
                status=403,
            )
        if profile.status == UserProfile.STATUS_PENDING_APPROVAL:
            return redirect("projectauth:pending")
        return redirect("projectauth:login")

    # 3. Mandatory 2FA policy check (e.g. admins must have confirmed 2FA)
    if twofa.user_requires_2fa_by_policy(user) and not twofa.user_has_confirmed_totp(user):
        if wants_json:
            return JsonResponse(
                {"success": False, "error": "Two-factor authentication enrolment is required."},
                status=403,
            )
        return redirect("projectauth:twofa_setup")

    # 4. Evaluate per-app access grant, expiry, and HTTP method level (full vs read_only)
    allowed, reason, protected_app, grant = evaluate_app_access(
        user,
        app_label,
        method=request.method,
    )
    if allowed:
        setattr(request, "projectauth_app_label", app_label)
        setattr(request, "projectauth_access_grant", grant)
        return None

    app_display_name = protected_app.name if protected_app else app_label
    if reason == "denied_read_only_method":
        err_msg = f"Read-only access to {app_display_name}: modifications are not permitted."
    elif reason == "denied_expired_grant":
        err_msg = f"Your access to {app_display_name} has expired."
    else:
        err_msg = f"You don't have access to {app_display_name}."

    if wants_json:
        return JsonResponse({"success": False, "error": err_msg}, status=403)

    return render_access_denied_response(
        request,
        app_label=app_label,
        protected_app=protected_app,
        reason=reason,
        grant=grant,
    )


class IdleTimeoutMiddleware:
    """
    Enforces:
    1. Revoked SessionRecord termination.
    2. Suspended/inactive user termination.
    3. Role-based idle timeout (admin_idle_timeout_min vs user_idle_timeout_hours) and 30-day absolute max.
    4. Forced password change redirect when UserProfile.must_change_password is True.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            expired_response = self._check_authenticated_session(request, user)
            if expired_response is not None:
                return expired_response

        return self.get_response(request)

    def _check_authenticated_session(self, request, user):
        now = timezone.now()
        now_ts = int(now.timestamp())

        # 1. Check active user and profile status
        profile = getattr(user, "profile", None)
        if not user.is_active or (
            profile is not None and profile.status != UserProfile.STATUS_ACTIVE
        ):
            logout(request)
            return redirect("projectauth:login")

        # 2. Check SessionRecord revocation if session is tracked
        sk = request.session.session_key
        if sk and request.session.get("pa_session_tracked"):
            sk_hash = hash_session_key(sk)
            rec = SessionRecord.objects.filter(session_key_hash=sk_hash).first()
            if rec is None or rec.revoked_at is not None:
                logout(request)
                messages.warning(
                    request,
                    "Your session has ended. Please sign in again.",
                )
                return redirect("projectauth:login")

        # 3. Check idle timeout and 30-day absolute maximum
        auth_settings = AuthSettings.load()
        is_admin = bool(user.is_superuser and user.is_staff)
        if is_admin:
            idle_limit_sec = int(auth_settings.admin_idle_timeout_min) * 60
        else:
            idle_limit_sec = int(auth_settings.user_idle_timeout_hours) * 3600

        last_ts = request.session.get("pa_last_activity_ts")
        created_ts = request.session.get("pa_created_ts")
        abs_limit_sec = SESSION_MAX_DAYS * 86400

        if last_ts is not None and (now_ts - int(last_ts)) > idle_limit_sec:
            log_audit("session.idle_timeout", request=request, actor=user)
            if sk:
                SessionRecord.objects.filter(
                    session_key_hash=hash_session_key(sk),
                    revoked_at__isnull=True,
                ).update(revoked_at=now)
            logout(request)
            messages.info(
                request,
                "You were signed out due to inactivity.",
            )
            return redirect("projectauth:login")

        if created_ts is not None and (now_ts - int(created_ts)) > abs_limit_sec:
            log_audit("session.absolute_timeout", request=request, actor=user)
            logout(request)
            messages.info(
                request,
                "Your session expired. Please sign in again.",
            )
            return redirect("projectauth:login")

        # Update activity timestamp in session and periodically in DB
        request.session["pa_last_activity_ts"] = now_ts
        if created_ts is None:
            request.session["pa_created_ts"] = now_ts

        if sk and (last_ts is None or (now_ts - int(last_ts)) >= 60):
            SessionRecord.objects.filter(
                session_key_hash=hash_session_key(sk),
                revoked_at__isnull=True,
            ).update(last_seen_at=now)
            if profile is not None:
                UserProfile.objects.filter(pk=profile.pk).update(last_seen_at=now)

        # 4. Forced password change check
        if profile is not None and profile.must_change_password:
            force_url = reverse("projectauth:force_password_change")
            logout_url = reverse("projectauth:logout")
            path = request.path
            if (
                path not in (force_url, logout_url)
                and not path.startswith("/static/")
                and not path.startswith("/media/")
            ):
                return redirect(force_url)

        return None


class ProjectAuthMiddleware:
    """
    Enforces default-deny per-app authorization via process_view (Section 5.5 & 9),
    and sets Cache-Control: no-store on authenticated / protected pages.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        path = request.path or ""
        if not path.startswith("/static/") and not path.startswith("/media/"):
            user = getattr(request, "user", None)
            app_label = getattr(request, "projectauth_app_label", None)
            if (
                (user is not None and getattr(user, "is_authenticated", False))
                or path.startswith("/auth/")
                or app_label is not None
            ):
                patch_cache_control(
                    response,
                    no_store=True,
                    no_cache=True,
                    must_revalidate=True,
                )
        return response

    def process_view(self, request: HttpRequest, view_func, view_args, view_kwargs):
        app_label = resolve_view_app_label(
            view_func,
            path=request.path,
            resolver_match=getattr(request, "resolver_match", None),
        )
        # Fail closed: if a view cannot be resolved to a known app, treat it as 'unregistered'
        effective_label = app_label or "unregistered"
        return enforce_app_access_for_request(request, effective_label)
