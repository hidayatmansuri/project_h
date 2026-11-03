"""
Core authentication, credential recovery, and account self-service views for projectauth (Phase 2).
All HTML screens render through projectauth/templates/projectauth.html switched by `mode` (Constraint C2).
Sets Cache-Control: no-store on all auth/account responses (Section 5.5 & 19.10).
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import timedelta
from typing import Optional

from axes.handlers.proxy import AxesProxyHandler
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import (
    authenticate,
    get_user_model,
    login,
    logout,
    update_session_auth_hash,
)
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.db.models.functions import Lower
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseNotAllowed,
    JsonResponse,
)
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import patch_cache_control
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .audit import get_client_ip, log_audit
from .crypto import compare_hmac, hmac_sha256, normalize_identifier
from .email_service import build_absolute_url, send_projectauth_email
from .forms import (
    ChangeEmailForm,
    ChangePasswordForm,
    ChangeUsernameForm,
    DeleteAccountForm,
    ForcePasswordChangeForm,
    ForgotPasswordForm,
    ForgotUsernameForm,
    LoginForm,
    ResetPasswordForm,
    SignupForm,
)
from .models import (
    AccessRequest,
    AppAccess,
    AuditEvent,
    AuthSettings,
    PendingEmailChange,
    ProtectedApp,
    SessionRecord,
    UserProfile,
)
from .sessions import (
    hash_session_key,
    register_authenticated_session,
    revoke_all_user_sessions,
    revoke_other_sessions,
    revoke_session_by_id,
)
from .throttling import check_and_increment_throttle
from .tokens import (
    EMAIL_CHANGE_MAX_AGE,
    TokenValidationError,
    create_email_verification_token,
    create_password_reset_token,
    mask_email,
    verify_email_verification_token,
    verify_password_reset_token,
)

User = get_user_model()

GENERIC_LOGIN_ERROR = "Check your details and try again."
SUDO_TIMEOUT_SECONDS = 600  # 10 minutes (Section 5.3)


def render_projectauth(
    request: HttpRequest,
    mode: str,
    context: Optional[dict] = None,
    *,
    status: int = 200,
) -> HttpResponse:
    ctx = {"mode": mode}
    if context:
        ctx.update(context)
    response = render(request, "projectauth.html", ctx, status=status)
    patch_cache_control(response, no_store=True, no_cache=True, must_revalidate=True)
    return response


def is_sudo_active(request: HttpRequest) -> bool:
    sudo_ts = request.session.get("pa_sudo_ts")
    if not sudo_ts:
        return False
    elapsed = timezone.now().timestamp() - float(sudo_ts)
    return 0 <= elapsed <= SUDO_TIMEOUT_SECONDS


def mark_sudo_verified(request: HttpRequest) -> None:
    request.session["pa_sudo_ts"] = timezone.now().timestamp()


def count_active_admins(exclude_user_id: Optional[int] = None) -> int:
    qs = User.objects.filter(
        is_superuser=True,
        is_staff=True,
        is_active=True,
    ).filter(Q(profile__status=UserProfile.STATUS_ACTIVE) | Q(profile__isnull=True))
    if exclude_user_id is not None:
        qs = qs.exclude(pk=exclude_user_id)
    return qs.count()


def is_last_active_admin(user) -> bool:
    if not (user.is_superuser and user.is_staff and user.is_active):
        return False
    return count_active_admins(exclude_user_id=user.pk) == 0


def _get_admin_notification_recipients() -> list[str]:
    auth_settings = AuthSettings.load()
    recipients: set[str] = set()
    if auth_settings.admin_notify_emails:
        for part in auth_settings.admin_notify_emails.replace(";", ",").split(","):
            if part.strip() and "@" in part:
                recipients.add(part.strip().lower())
    for email in (
        User.objects.filter(is_superuser=True, is_staff=True, is_active=True)
        .exclude(email="")
        .values_list("email", flat=True)
    ):
        if email and "@" in email:
            recipients.add(email.strip().lower())
    return sorted(recipients)


def _safe_next_url(request: HttpRequest, candidate: Optional[str]) -> str:
    if candidate and url_has_allowed_host_and_scheme(
        url=candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return reverse("home")


@never_cache
@require_http_methods(["GET", "POST"])
def signup_view(request: HttpRequest) -> HttpResponse:
    auth_settings = AuthSettings.load()
    if auth_settings.signup_mode != AuthSettings.SIGNUP_OPEN_APPROVAL:
        return render_projectauth(
            request,
            "signup",
            {
                "signup_disabled": True,
                "signup_mode": auth_settings.signup_mode,
            },
        )

    if request.method == "POST":
        ip = get_client_ip(request) or "unknown"
        allowed, _ = check_and_increment_throttle(
            "signup_ip",
            ip,
            limit=10,
            window_seconds=3600,
        )
        if not allowed:
            messages.error(request, "Too many sign-up attempts from your network. Please try again later.")
            return render_projectauth(request, "signup", {"form": SignupForm(request.POST)}, status=429)

        form = SignupForm(request.POST)
        if form.is_valid():
            uname = form.cleaned_data["username"]
            email = form.cleaned_data["email"]
            password = form.cleaned_data["password"]
            requested_apps = form.cleaned_data.get("requested_apps") or []

            existing_user = (
                User.objects.select_related("profile")
                .annotate(_el=Lower("email"))
                .filter(Q(_el=email) | Q(profile__email_normalized=email))
                .first()
            )

            if existing_user is not None:
                # Anti-enumeration (Section 5.1): do NOT reveal that the email is registered.
                # Notify the existing account owner and show the identical success popup.
                send_projectauth_email(
                    "already_registered_notice",
                    [existing_user.email or email],
                    context={
                        "username": existing_user.username,
                        "action_url": build_absolute_url(reverse("projectauth:forgot_password")),
                    },
                )
                log_audit(
                    "signup.duplicate_email",
                    request=request,
                    target_user=existing_user,
                )
            else:
                now = timezone.now()
                with transaction.atomic():
                    new_user = User(
                        username=uname,
                        email=email,
                        is_active=False,
                    )
                    new_user.set_password(password)
                    new_user.save()

                    UserProfile.objects.create(
                        user=new_user,
                        status=UserProfile.STATUS_PENDING_EMAIL,
                        username_normalized=uname,
                        email_normalized=email,
                        created_via=UserProfile.CREATED_VIA_SIGNUP,
                        terms_accepted_at=now,
                        password_changed_at=now,
                    )

                    for app_obj in requested_apps:
                        AccessRequest.objects.get_or_create(
                            user=new_user,
                            app=app_obj,
                            status=AccessRequest.STATUS_PENDING,
                            defaults={"message": "Requested during sign-up"},
                        )

                token = create_email_verification_token(new_user, ip=ip)
                verify_url = build_absolute_url(
                    reverse("projectauth:verify_email", kwargs={"token": token})
                )
                send_projectauth_email(
                    "verify_email",
                    [email],
                    context={
                        "username": uname,
                        "action_url": verify_url,
                        "expires_hours": 24,
                    },
                )
                log_audit(
                    "signup.created",
                    request=request,
                    target_user=new_user,
                    details={"requested_apps": [a.app_label for a in requested_apps]},
                )

            request.session["pa_signup_popup"] = {
                "name": uname,
                "masked_email": mask_email(email),
            }
            return redirect("projectauth:signup_done")
    else:
        form = SignupForm()

    return render_projectauth(request, "signup", {"form": form})


@never_cache
@require_GET
def signup_done_view(request: HttpRequest) -> HttpResponse:
    popup = request.session.get("pa_signup_popup") or {
        "name": "there",
        "masked_email": "your email address",
    }
    return render_projectauth(
        request,
        "signup_done",
        {
            "signup_name": popup.get("name", "there"),
            "masked_email": popup.get("masked_email", "your email address"),
            "show_signup_modal": True,
        },
    )


@never_cache
@require_GET
def verify_email_view(request: HttpRequest, token: str) -> HttpResponse:
    try:
        user = verify_email_verification_token(token, consume=True)
    except TokenValidationError as exc:
        return render_projectauth(
            request,
            "verify_result",
            {"verified": False, "error_message": str(exc)},
            status=400,
        )

    now = timezone.now()
    profile = user.profile
    profile.email_verified_at = now
    if profile.status == UserProfile.STATUS_PENDING_EMAIL:
        profile.status = UserProfile.STATUS_PENDING_APPROVAL
    profile.save(update_fields=["email_verified_at", "status"])

    log_audit("email.verified", request=request, target_user=user)

    auth_settings = AuthSettings.load()
    if auth_settings.notify_admins_on_signup:
        admin_emails = _get_admin_notification_recipients()
        if admin_emails:
            requested_labels = list(
                AccessRequest.objects.filter(user=user).values_list("app__name", flat=True)
            )
            send_projectauth_email(
                "admin_new_signup",
                admin_emails,
                context={
                    "new_username": user.username,
                    "new_email": user.email,
                    "requested_apps": ", ".join(requested_labels) or "None specified",
                    "action_url": build_absolute_url(reverse("projectauth:login")),
                },
            )

    return render_projectauth(
        request,
        "verify_result",
        {
            "verified": True,
            "verified_username": user.username,
        },
    )


@never_cache
@require_POST
def verify_email_resend_view(request: HttpRequest) -> HttpResponse:
    ip = get_client_ip(request) or "unknown"
    email_input = normalize_identifier(request.POST.get("email") or "")
    uid = request.session.get("pa_verify_email_user_id")

    user = None
    if uid:
        user = User.objects.select_related("profile").filter(pk=uid).first()
    elif email_input:
        user = (
            User.objects.select_related("profile")
            .annotate(_el=Lower("email"))
            .filter(Q(_el=email_input) | Q(profile__email_normalized=email_input))
            .first()
        )

    throttle_key = (user.email if user else email_input) or ip
    allowed_ip, _ = check_and_increment_throttle("verify_resend_ip", ip, limit=5, window_seconds=900)
    allowed_em, _ = check_and_increment_throttle(
        "verify_resend_email", throttle_key, limit=3, window_seconds=900
    )

    if allowed_ip and allowed_em and user and getattr(user, "profile", None):
        if user.profile.status == UserProfile.STATUS_PENDING_EMAIL and user.email:
            token = create_email_verification_token(user, ip=ip)
            verify_url = build_absolute_url(
                reverse("projectauth:verify_email", kwargs={"token": token})
            )
            send_projectauth_email(
                "verify_email",
                [user.email],
                context={
                    "username": user.username,
                    "action_url": verify_url,
                    "expires_hours": 24,
                },
            )
            log_audit("email.verification_resent", request=request, target_user=user)

    messages.success(
        request,
        "If your account is awaiting email verification, a fresh verification link has been sent.",
    )
    return render_projectauth(
        request,
        "verify_sent",
        {
            "masked_email": mask_email(user.email if user and user.email else email_input),
        },
    )


def _resolve_pending_or_active_user(request: HttpRequest):
    if getattr(request.user, "is_authenticated", False):
        return request.user
    pending_uid = request.session.get("pa_pending_user_id")
    if pending_uid:
        return User.objects.select_related("profile").filter(pk=pending_uid).first()
    return None


@never_cache
@require_GET
def pending_view(request: HttpRequest) -> HttpResponse:
    user = _resolve_pending_or_active_user(request)
    if user is None:
        return redirect("projectauth:login")

    existing_requests = AccessRequest.objects.filter(user=user).select_related("app")
    requested_app_ids = set(existing_requests.values_list("app_id", flat=True))
    available_apps = ProtectedApp.objects.filter(is_public=False, is_active=True).exclude(
        pk__in=requested_app_ids
    )
    return render_projectauth(
        request,
        "pending",
        {
            "pending_user": user,
            "masked_email": mask_email(user.email or ""),
            "access_requests": existing_requests,
            "available_apps": available_apps,
        },
    )


@never_cache
@require_POST
def request_access_view(request: HttpRequest) -> HttpResponse:
    user = _resolve_pending_or_active_user(request)
    if user is None:
        return redirect("projectauth:login")

    app_label = (request.POST.get("app_label") or "").strip()
    app_id = request.POST.get("app_id")
    message = (request.POST.get("message") or "").strip()[:500]

    app_obj = None
    if app_label:
        app_obj = ProtectedApp.objects.filter(app_label=app_label, is_public=False, is_active=True).first()
    elif app_id and str(app_id).isdigit():
        app_obj = ProtectedApp.objects.filter(pk=int(app_id), is_public=False, is_active=True).first()

    if app_obj is not None:
        req_obj, created = AccessRequest.objects.get_or_create(
            user=user,
            app=app_obj,
            status=AccessRequest.STATUS_PENDING,
            defaults={"message": message},
        )
        if not created and message and not req_obj.message:
            req_obj.message = message
            req_obj.save(update_fields=["message"])
        log_audit(
            "access.requested",
            request=request,
            actor=user if request.user.is_authenticated else None,
            target_user=user,
            details={"app": app_obj.app_label},
        )
        messages.success(request, f"Access request submitted for {app_obj.name}.")

    if request.user.is_authenticated:
        next_url = _safe_next_url(request, request.POST.get("next"))
        return redirect(next_url)
    return redirect("projectauth:pending")


@never_cache
@require_http_methods(["GET", "POST"])
def login_view(request: HttpRequest) -> HttpResponse:
    next_param = request.GET.get("next") or request.POST.get("next") or ""
    if request.user.is_authenticated:
        return redirect(_safe_next_url(request, next_param))

    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            raw_identifier = form.cleaned_data["identifier"]
            norm_identifier = normalize_identifier(raw_identifier)
            password = form.cleaned_data["password"]
            remember_me = bool(form.cleaned_data.get("remember_me"))

            credentials = {"username": norm_identifier}
            if not AxesProxyHandler.is_allowed(request, credentials):
                log_audit(
                    "login.locked",
                    request=request,
                    details={"identifier": norm_identifier},
                )
                form.add_error(None, GENERIC_LOGIN_ERROR)
                return render_projectauth(
                    request,
                    "login",
                    {"form": form, "next": next_param},
                    status=429,
                )

            try:
                user = authenticate(
                    request=request,
                    username=norm_identifier,
                    password=password,
                )
            except PermissionDenied:
                log_audit(
                    "login.locked",
                    request=request,
                    details={"identifier": norm_identifier},
                )
                form.add_error(None, GENERIC_LOGIN_ERROR)
                return render_projectauth(
                    request,
                    "login",
                    {"form": form, "next": next_param},
                    status=429,
                )

            matched_user = getattr(request, "_projectauth_matched_user", None)

            if user is not None:
                return _handle_authenticated_user_after_password(
                    request,
                    user,
                    remember_me=remember_me,
                    next_param=next_param,
                )

            if matched_user is not None and getattr(matched_user, "profile", None):
                p_status = matched_user.profile.status
                if p_status == UserProfile.STATUS_PENDING_EMAIL:
                    request.session["pa_verify_email_user_id"] = matched_user.pk
                    return render_projectauth(
                        request,
                        "verify_sent",
                        {
                            "masked_email": mask_email(matched_user.email or ""),
                        },
                    )
                if p_status == UserProfile.STATUS_PENDING_APPROVAL:
                    request.session["pa_pending_user_id"] = matched_user.pk
                    return redirect("projectauth:pending")
                if p_status in (UserProfile.STATUS_SUSPENDED, UserProfile.STATUS_REJECTED):
                    log_audit(
                        "login.blocked_status",
                        request=request,
                        target_user=matched_user,
                        details={"status": p_status},
                    )
                    form.add_error(
                        None,
                        "Check your details and try again. If you need assistance, please contact the administrator.",
                    )
                    return render_projectauth(
                        request,
                        "login",
                        {"form": form, "next": next_param},
                    )

            log_audit(
                "login.failure",
                request=request,
                details={"identifier": norm_identifier},
            )
            form.add_error(None, GENERIC_LOGIN_ERROR)
    else:
        form = LoginForm()

    return render_projectauth(
        request,
        "login",
        {"form": form, "next": next_param},
    )


def _handle_authenticated_user_after_password(
    request: HttpRequest,
    user,
    *,
    remember_me: bool,
    next_param: str,
) -> HttpResponse:
    """
    Hook point for Phase 3 2FA challenge/setup vs immediate session completion.
    In Phase 3, if 2FA is enabled or mandatory for `user` (and device not trusted),
    this stores pre-auth state in session without calling `login()`.
    """
    from . import twofa

    if twofa.should_interpose_2fa(request, user, remember_me=remember_me, next_url=next_param):
        return twofa.begin_2fa_flow(request, user, remember_me=remember_me, next_url=next_param)

    return complete_user_login(
        request,
        user,
        remember_me=remember_me,
        next_param=next_param,
    )


def complete_user_login(
    request: HttpRequest,
    user,
    *,
    remember_me: bool = False,
    next_param: str = "",
    twofa_verified: bool = False,
) -> HttpResponse:
    login(request, user, backend="projectauth.backends.EmailOrUsernameBackend")
    request.session["pa_2fa_verified"] = bool(twofa_verified)
    register_authenticated_session(request, user, remember_me=remember_me)
    log_audit(
        "login.success",
        request=request,
        actor=user,
        details={"twofa": bool(twofa_verified)},
    )

    if getattr(user, "profile", None) and user.profile.must_change_password:
        return redirect("projectauth:force_password_change")

    return redirect(_safe_next_url(request, next_param))


@never_cache
def logout_view(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    user = request.user if request.user.is_authenticated else None
    all_devices = request.POST.get("all_devices") == "1"
    sk = request.session.session_key

    if user is not None:
        if all_devices:
            revoked = revoke_all_user_sessions(user)
            log_audit(
                "logout.all_devices",
                request=request,
                actor=user,
                details={"revoked_count": revoked},
            )
        else:
            if sk:
                SessionRecord.objects.filter(
                    session_key_hash=hash_session_key(sk),
                    revoked_at__isnull=True,
                ).update(revoked_at=timezone.now())
            log_audit("logout.success", request=request, actor=user)

    logout(request)
    messages.info(request, "You have been signed out.")
    return redirect(getattr(settings, "LOGOUT_REDIRECT_URL", "home"))


@never_cache
@require_http_methods(["GET", "POST"])
def forgot_password_view(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            ip = get_client_ip(request) or "unknown"
            ok_ip, _ = check_and_increment_throttle("pw_reset_ip", ip, limit=10, window_seconds=900)
            ok_em, _ = check_and_increment_throttle("pw_reset_email", email, limit=3, window_seconds=900)

            if ok_ip and ok_em:
                user = (
                    User.objects.select_related("profile")
                    .annotate(_el=Lower("email"))
                    .filter(Q(_el=email) | Q(profile__email_normalized=email))
                    .first()
                )
                if user is not None and user.email:
                    token = create_password_reset_token(user, ip=ip)
                    reset_url = build_absolute_url(
                        reverse("projectauth:reset_password", kwargs={"token": token})
                    )
                    send_projectauth_email(
                        "password_reset",
                        [user.email],
                        context={
                            "username": user.username,
                            "action_url": reset_url,
                            "expires_minutes": 60,
                        },
                    )
                    log_audit("password.reset_requested", request=request, target_user=user)

            # Generic response regardless of whether account exists (anti-enumeration)
            messages.success(
                request,
                "If an account matches that email address, we have sent password reset instructions.",
            )
            return redirect("projectauth:forgot_password")
    else:
        form = ForgotPasswordForm()

    return render_projectauth(request, "forgot_password", {"form": form})


@never_cache
@require_http_methods(["GET", "POST"])
def reset_password_view(request: HttpRequest, token: str) -> HttpResponse:
    try:
        user = verify_password_reset_token(token, consume=False)
    except TokenValidationError as exc:
        return render_projectauth(
            request,
            "reset_password",
            {"token_invalid": True, "error_message": str(exc)},
            status=400,
        )

    if request.method == "POST":
        form = ResetPasswordForm(request.POST, user=user)
        if form.is_valid():
            try:
                user = verify_password_reset_token(token, consume=True)
            except TokenValidationError as exc:
                return render_projectauth(
                    request,
                    "reset_password",
                    {"token_invalid": True, "error_message": str(exc)},
                    status=400,
                )

            new_pw = form.cleaned_data["password"]
            now = timezone.now()
            user.set_password(new_pw)
            user.save(update_fields=["password"])

            if getattr(user, "profile", None):
                user.profile.password_changed_at = now
                user.profile.must_change_password = False
                user.profile.save(update_fields=["password_changed_at", "must_change_password"])

            revoke_all_user_sessions(user)
            if user.email:
                send_projectauth_email(
                    "password_changed",
                    [user.email],
                    context={"username": user.username},
                )
            log_audit("password.reset_complete", request=request, target_user=user)
            messages.success(request, "Your password has been updated. You can now sign in.")
            return redirect("projectauth:login")
    else:
        form = ResetPasswordForm(user=user)

    return render_projectauth(
        request,
        "reset_password",
        {"form": form, "token": token, "token_invalid": False},
    )


@never_cache
@require_http_methods(["GET", "POST"])
def forgot_username_view(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = ForgotUsernameForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            ip = get_client_ip(request) or "unknown"
            ok_ip, _ = check_and_increment_throttle("uname_remind_ip", ip, limit=10, window_seconds=900)
            ok_em, _ = check_and_increment_throttle("uname_remind_email", email, limit=3, window_seconds=900)

            if ok_ip and ok_em:
                users = list(
                    User.objects.annotate(_el=Lower("email"))
                    .filter(Q(_el=email) | Q(profile__email_normalized=email))
                    .values_list("username", flat=True)
                )
                if users:
                    send_projectauth_email(
                        "username_reminder",
                        [email],
                        context={
                            "usernames": ", ".join(users),
                            "action_url": build_absolute_url(reverse("projectauth:login")),
                        },
                    )
                    log_audit(
                        "account.username_reminder_sent",
                        request=request,
                        details={"count": len(users)},
                    )

            messages.success(
                request,
                "If an account exists for that email address, we have sent a reminder with your username.",
            )
            return redirect("projectauth:forgot_username")
    else:
        form = ForgotUsernameForm()

    return render_projectauth(request, "forgot_username", {"form": form})


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def force_password_change_view(request: HttpRequest) -> HttpResponse:
    user = request.user
    if request.method == "POST":
        form = ForcePasswordChangeForm(request.POST, user=user)
        if form.is_valid():
            new_pw = form.cleaned_data["password"]
            now = timezone.now()
            user.set_password(new_pw)
            user.save(update_fields=["password"])
            update_session_auth_hash(request, user)
            request.session.cycle_key()
            register_authenticated_session(request, user, send_new_device_alert=False)

            if getattr(user, "profile", None):
                user.profile.must_change_password = False
                user.profile.password_changed_at = now
                user.profile.save(update_fields=["must_change_password", "password_changed_at"])

            revoke_other_sessions(user, request.session.session_key)
            log_audit("password.forced_change_complete", request=request, actor=user)
            messages.success(request, "Your password has been updated.")
            return redirect("home")
    else:
        form = ForcePasswordChangeForm(user=user)

    return render_projectauth(request, "force_password_change", {"form": form})


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def account_view(request: HttpRequest) -> HttpResponse:
    from . import twofa

    user = request.user
    sudo_ok = is_sudo_active(request)

    pw_form = ChangePasswordForm(user=user, prefix="pw")
    uname_form = ChangeUsernameForm(user=user, sudo_ok=sudo_ok, prefix="uname", initial={"new_username": user.username})
    email_form = ChangeEmailForm(user=user, sudo_ok=sudo_ok, prefix="email")
    delete_form = DeleteAccountForm(user=user, sudo_ok=sudo_ok, prefix="del")

    if request.method == "POST":
        action = request.POST.get("account_action") or ""

        if action == "change_password":
            pw_form = ChangePasswordForm(request.POST, user=user, prefix="pw")
            if pw_form.is_valid():
                now = timezone.now()
                user.set_password(pw_form.cleaned_data["password"])
                user.save(update_fields=["password"])
                update_session_auth_hash(request, user)
                request.session.cycle_key()
                register_authenticated_session(request, user, send_new_device_alert=False)

                if getattr(user, "profile", None):
                    user.profile.password_changed_at = now
                    user.profile.must_change_password = False
                    user.profile.save(update_fields=["password_changed_at", "must_change_password"])

                revoke_other_sessions(user, request.session.session_key)
                if user.email:
                    send_projectauth_email("password_changed", [user.email], context={"username": user.username})
                log_audit("password.changed", request=request, actor=user)
                messages.success(request, "Password changed and other sessions signed out.")
                return redirect("projectauth:account")

        elif action == "change_username":
            uname_form = ChangeUsernameForm(request.POST, user=user, sudo_ok=sudo_ok, prefix="uname")
            if uname_form.is_valid():
                allowed, _ = check_and_increment_throttle(
                    "username_change",
                    str(user.pk),
                    limit=3,
                    window_seconds=86400,
                )
                if not allowed:
                    messages.error(request, "You have changed your username too recently. Please try again tomorrow.")
                else:
                    old_uname = user.username
                    new_uname = uname_form.cleaned_data["new_username"]
                    user.username = new_uname
                    user.save(update_fields=["username"])
                    if getattr(user, "profile", None):
                        user.profile.username_normalized = new_uname
                        user.profile.save(update_fields=["username_normalized"])
                    log_audit(
                        "account.username_changed",
                        request=request,
                        actor=user,
                        details={"old_username": old_uname, "new_username": new_uname},
                    )
                    messages.success(request, f"Your username has been updated to {new_uname}.")
                    return redirect("projectauth:account")

        elif action == "change_email":
            if twofa.user_has_confirmed_totp(user) and not sudo_ok:
                messages.info(request, "Please re-authenticate with your second factor to change your email address.")
                return redirect(f"{reverse('projectauth:reauth')}?next={reverse('projectauth:account')}")
            email_form = ChangeEmailForm(request.POST, user=user, sudo_ok=sudo_ok, prefix="email")
            if email_form.is_valid():
                new_email = email_form.cleaned_data["new_email"]
                old_email = user.email or ""
                allowed, _ = check_and_increment_throttle(
                    "email_change",
                    str(user.pk),
                    limit=3,
                    window_seconds=3600,
                )
                if not allowed:
                    messages.error(request, "Too many email change requests. Please wait before trying again.")
                else:
                    raw_token = secrets.token_urlsafe(32)
                    token_hmac = hmac_sha256("email_change", raw_token)
                    now = timezone.now()
                    PendingEmailChange.objects.create(
                        user=user,
                        new_email=new_email,
                        token_hmac=token_hmac,
                        expires_at=now + timedelta(seconds=EMAIL_CHANGE_MAX_AGE),
                    )
                    confirm_url = build_absolute_url(
                        reverse("projectauth:confirm_email_change", kwargs={"token": raw_token})
                    )
                    send_projectauth_email(
                        "email_change_confirm_new",
                        [new_email],
                        context={
                            "username": user.username,
                            "new_email": new_email,
                            "action_url": confirm_url,
                        },
                    )
                    if old_email:
                        send_projectauth_email(
                            "email_change_notice_old",
                            [old_email],
                            context={
                                "username": user.username,
                                "masked_new_email": mask_email(new_email),
                            },
                        )
                    log_audit(
                        "account.email_change_requested",
                        request=request,
                        actor=user,
                        details={"masked_new_email": mask_email(new_email)},
                    )
                    messages.success(
                        request,
                        f"We sent a confirmation link to {mask_email(new_email)}. Your current email remains active until confirmed.",
                    )
                    return redirect("projectauth:account")

        elif action == "revoke_session":
            rec_id = request.POST.get("session_record_id")
            if rec_id and str(rec_id).isdigit():
                if revoke_session_by_id(user, int(rec_id)):
                    log_audit("session.revoked", request=request, actor=user, details={"record_id": int(rec_id)})
                    messages.success(request, "Session revoked.")
            return redirect("projectauth:account")

        elif action == "revoke_other_sessions":
            count = revoke_other_sessions(user, request.session.session_key)
            log_audit("session.revoked_others", request=request, actor=user, details={"count": count})
            messages.success(request, f"Signed out of {count} other session(s).")
            return redirect("projectauth:account")

    active_sessions = SessionRecord.objects.filter(user=user, revoked_at__isnull=True)
    current_sk_hash = hash_session_key(request.session.session_key or "")
    app_grants = AppAccess.objects.filter(user=user, revoked_at__isnull=True).select_related("app")
    pending_email_change = (
        PendingEmailChange.objects.filter(
            user=user,
            confirmed_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .order_by("-created_at")
        .first()
    )

    return render_projectauth(
        request,
        "account",
        {
            "pw_form": pw_form,
            "uname_form": uname_form,
            "email_form": email_form,
            "delete_form": delete_form,
            "active_sessions": active_sessions,
            "current_sk_hash": current_sk_hash,
            "app_grants": app_grants,
            "pending_email_change": pending_email_change,
            "sudo_ok": sudo_ok,
            "twofa_summary": twofa.get_user_2fa_summary(user),
        },
    )


@never_cache
@require_GET
def confirm_email_change_view(request: HttpRequest, token: str) -> HttpResponse:
    token_hmac = hmac_sha256("email_change", token or "")
    now = timezone.now()
    pending = (
        PendingEmailChange.objects.select_related("user", "user__profile")
        .filter(
            token_hmac=token_hmac,
            confirmed_at__isnull=True,
            expires_at__gt=now,
        )
        .first()
    )
    if pending is None:
        return render_projectauth(
            request,
            "verify_result",
            {
                "verified": False,
                "error_message": "This email change link is invalid or has expired.",
            },
            status=400,
        )

    user = pending.user
    new_email = normalize_identifier(pending.new_email)

    # Ensure new_email wasn't claimed in the meantime
    conflict = (
        User.objects.annotate(_el=Lower("email"))
        .filter(Q(_el=new_email) | Q(profile__email_normalized=new_email))
        .exclude(pk=user.pk)
        .exists()
    )
    if conflict:
        return render_projectauth(
            request,
            "verify_result",
            {
                "verified": False,
                "error_message": "Unable to complete email change. Please contact an administrator.",
            },
            status=400,
        )

    old_email = user.email
    with transaction.atomic():
        pending.confirmed_at = now
        pending.save(update_fields=["confirmed_at"])
        user.email = new_email
        user.save(update_fields=["email"])
        if getattr(user, "profile", None):
            user.profile.email_normalized = new_email
            user.profile.email_verified_at = now
            user.profile.save(update_fields=["email_normalized", "email_verified_at"])

    log_audit(
        "account.email_changed",
        request=request,
        actor=user,
        target_user=user,
        details={"old_email": mask_email(old_email), "new_email": mask_email(new_email)},
    )
    return render_projectauth(
        request,
        "verify_result",
        {
            "verified": True,
            "verified_username": user.username,
            "email_changed_to": new_email,
        },
    )


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def account_export_view(request: HttpRequest) -> HttpResponse:
    user = request.user
    profile = getattr(user, "profile", None)
    data = {
        "exported_at_utc": timezone.now().isoformat(),
        "account": {
            "username": user.username,
            "email": user.email,
            "date_joined": user.date_joined.isoformat() if user.date_joined else None,
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "status": profile.status if profile else None,
            "email_verified_at": (
                profile.email_verified_at.isoformat()
                if profile and profile.email_verified_at
                else None
            ),
            "created_via": profile.created_via if profile else None,
        },
        "app_access": [
            {
                "app_label": g.app.app_label,
                "app_name": g.app.name,
                "level": g.level,
                "granted_at": g.granted_at.isoformat(),
                "expires_at": g.expires_at.isoformat() if g.expires_at else None,
                "revoked_at": g.revoked_at.isoformat() if g.revoked_at else None,
            }
            for g in AppAccess.objects.filter(user=user).select_related("app")
        ],
        "access_requests": [
            {
                "app_label": r.app.app_label,
                "status": r.status,
                "created_at": r.created_at.isoformat(),
                "decided_at": r.decided_at.isoformat() if r.decided_at else None,
            }
            for r in AccessRequest.objects.filter(user=user).select_related("app")
        ],
        "active_sessions": [
            {
                "ip": s.ip,
                "user_agent": s.user_agent,
                "created_at": s.created_at.isoformat(),
                "last_seen_at": s.last_seen_at.isoformat(),
            }
            for s in SessionRecord.objects.filter(user=user, revoked_at__isnull=True)
        ],
        "audit_events": [
            {
                "action": e.action,
                "ip": e.ip,
                "created_at": e.created_at.isoformat(),
                "details": e.details,
            }
            for e in AuditEvent.objects.filter(Q(actor=user) | Q(target_user=user))[:200]
        ],
    }
    log_audit("account.data_exported", request=request, actor=user)
    response = HttpResponse(
        json.dumps(data, indent=2),
        content_type="application/json; charset=utf-8",
    )
    response["Content-Disposition"] = f'attachment; filename="projectauth-data-{user.username}.json"'
    patch_cache_control(response, no_store=True, no_cache=True, must_revalidate=True)
    return response


@never_cache
@login_required
@require_POST
def account_delete_view(request: HttpRequest) -> HttpResponse:
    user = request.user
    sudo_ok = is_sudo_active(request)
    form = DeleteAccountForm(request.POST, user=user, sudo_ok=sudo_ok, prefix="del")

    if not form.is_valid():
        for err in form.non_field_errors():
            messages.error(request, err)
        for field_errs in form.errors.values():
            for err in field_errs:
                messages.error(request, err)
        return redirect("projectauth:account")

    if is_last_active_admin(user):
        messages.error(
            request,
            "Cannot delete the last active administrator account. Promote another admin first.",
        )
        return redirect("projectauth:account")

    anon_tag = "deleted-user-" + hashlib.sha256(f"{user.pk}:{user.username}".encode("utf-8")).hexdigest()[:8]
    user_email = user.email
    username_snapshot = user.username

    with transaction.atomic():
        AuditEvent.objects.filter(actor=user).update(actor=None, actor_label=anon_tag)
        AuditEvent.objects.filter(target_user=user).update(target_user=None, target_label=anon_tag)
        log_audit(
            "account.deleted",
            request=request,
            actor=None,
            actor_label=anon_tag,
            target_label=anon_tag,
        )
        logout(request)
        user.delete()

    if user_email:
        send_projectauth_email(
            "account_deleted",
            [user_email],
            context={"username": username_snapshot},
        )

    messages.info(request, "Your account has been permanently deleted.")
    return redirect("home")


# ---------------------------------------------------------------------------
# Phase 3: Two-Factor Authentication & Sudo Re-Authentication Views
# ---------------------------------------------------------------------------


@never_cache
@require_http_methods(["GET", "POST"])
def twofa_challenge_view(request: HttpRequest) -> HttpResponse:
    from . import twofa
    from .models import CodeChallenge

    user, state = twofa.get_preauth_user_and_state(request)
    if user is None or state is None:
        messages.info(request, "Your sign-in session expired. Please enter your credentials again.")
        return redirect("projectauth:login")

    error_message = ""
    if request.method == "POST":
        challenge_action = request.POST.get("challenge_action") or "verify"

        if challenge_action == "send_email_code":
            sent, info_msg = twofa.send_email_otp_challenge(
                user,
                purpose=CodeChallenge.PURPOSE_LOGIN_2FA,
                request=request,
            )
            if sent:
                log_audit("twofa.email_code_sent", request=request, target_user=user)
                messages.success(request, info_msg)
            else:
                messages.error(request, info_msg)
            return render_projectauth(
                request,
                "twofa_challenge",
                {
                    "masked_email": mask_email(user.email or ""),
                    "has_totp": twofa.user_has_confirmed_totp(user),
                },
            )

        allowed, _ = check_and_increment_throttle(
            "twofa_challenge_attempt",
            str(user.pk),
            limit=10,
            window_seconds=300,
            lockout_seconds=300,
        )
        if not allowed:
            log_audit("twofa.challenge_locked", request=request, target_user=user)
            return render_projectauth(
                request,
                "twofa_challenge",
                {
                    "masked_email": mask_email(user.email or ""),
                    "has_totp": twofa.user_has_confirmed_totp(user),
                    "error_message": "Too many verification attempts. Please wait 5 minutes and try again.",
                },
                status=429,
            )

        raw_code = (request.POST.get("code") or "").strip()
        method = (request.POST.get("method") or "auto").strip()
        trust_device = request.POST.get("trust_device") in ("on", "1", "true")

        verified = False
        used_method = ""

        if method in ("auto", "totp") and twofa.verify_user_totp(user, raw_code):
            verified = True
            used_method = "totp"
        elif method in ("auto", "email") and twofa.verify_email_otp_challenge(
            user, raw_code, purpose=CodeChallenge.PURPOSE_LOGIN_2FA
        ):
            verified = True
            used_method = "email"
        elif method in ("auto", "recovery") and twofa.verify_and_consume_recovery_code(user, raw_code):
            verified = True
            used_method = "recovery"

        if verified:
            twofa.clear_preauth_state(request)
            log_audit(
                "twofa.challenge_success",
                request=request,
                actor=user,
                details={"method": used_method},
            )
            resp = complete_user_login(
                request,
                user,
                remember_me=bool(state.get("remember_me")),
                next_param=state.get("next") or "",
                twofa_verified=True,
            )
            if trust_device:
                twofa.issue_trusted_device_cookie(request, resp, user)
                log_audit("twofa.trusted_device_added", request=request, actor=user)
            return resp

        log_audit("twofa.challenge_failed", request=request, target_user=user)
        error_message = "Invalid or expired verification code. Please try again."

    return render_projectauth(
        request,
        "twofa_challenge",
        {
            "masked_email": mask_email(user.email or ""),
            "has_totp": twofa.user_has_confirmed_totp(user),
            "error_message": error_message,
        },
    )


@never_cache
@require_http_methods(["GET", "POST"])
def twofa_setup_view(request: HttpRequest) -> HttpResponse:
    from . import twofa

    preauth_user, preauth_state = twofa.get_preauth_user_and_state(request)
    if request.user.is_authenticated:
        user = request.user
        in_preauth = False
    elif preauth_user is not None and preauth_state is not None:
        user = preauth_user
        in_preauth = True
    else:
        return redirect("projectauth:login")

    has_confirmed = twofa.user_has_confirmed_totp(user)
    sudo_ok = is_sudo_active(request) or in_preauth

    error_message = ""
    if request.method == "POST":
        setup_action = request.POST.get("setup_action") or "confirm_totp"

        # Sensitive actions when a factor is already active require sudo mode (10 min)
        if has_confirmed and not sudo_ok and setup_action in ("confirm_totp", "disable_2fa"):
            messages.info(request, "Please confirm your credentials to modify two-factor authentication.")
            return redirect(f"{reverse('projectauth:reauth')}?next={reverse('projectauth:twofa_setup')}")

        if setup_action == "confirm_totp":
            pending_dev = twofa.get_or_create_pending_totp_device(user)
            code = (request.POST.get("code") or "").strip()
            if twofa.verify_totp_code(pending_dev, code, confirm_if_pending=True):
                # Remove any older TOTP devices for this user
                from .models import TOTPDevice

                TOTPDevice.objects.filter(user=user).exclude(pk=pending_dev.pk).delete()
                fresh_codes = twofa.generate_recovery_codes_for_user(user)
                if user.email:
                    send_projectauth_email(
                        "twofa_enabled",
                        [user.email],
                        context={"username": user.username},
                    )
                log_audit("twofa.enabled", request=request, actor=user, target_user=user)

                if in_preauth and preauth_state is not None:
                    twofa.clear_preauth_state(request)
                    complete_user_login(
                        request,
                        user,
                        remember_me=bool(preauth_state.get("remember_me")),
                        next_param=preauth_state.get("next") or "",
                        twofa_verified=True,
                    )

                request.session["pa_2fa_verified"] = True
                request.session["pa_fresh_recovery_codes"] = fresh_codes
                mark_sudo_verified(request)
                messages.success(request, "Authenticator app enabled. Save your recovery codes below.")
                return redirect("projectauth:twofa_recovery")
            else:
                error_message = "The 6-digit code did not match. Check your authenticator app and try again."

        elif setup_action == "disable_2fa":
            if twofa.user_requires_2fa_by_policy(user):
                messages.error(
                    request,
                    "Two-factor authentication is mandatory for your account role and cannot be disabled.",
                )
            else:
                twofa.reset_user_2fa(user, actor=user, request=request)
                request.session["pa_2fa_verified"] = False
                messages.info(request, "Two-factor authentication has been disabled.")
            return redirect("projectauth:twofa_setup")

        elif setup_action == "revoke_trusted_devices":
            count = twofa.revoke_all_trusted_devices(user)
            log_audit(
                "twofa.trusted_devices_revoked",
                request=request,
                actor=user,
                details={"count": count},
            )
            messages.success(request, f"Revoked {count} trusted device(s).")
            resp = redirect("projectauth:twofa_setup")
            resp.delete_cookie(twofa.TRUSTED_DEVICE_COOKIE_NAME)
            return resp

    pending_device = twofa.get_or_create_pending_totp_device(user)
    raw_secret = pending_device.get_secret()
    formatted_secret = " ".join(raw_secret[i : i + 4] for i in range(0, len(raw_secret), 4))
    uri = twofa.build_totp_provisioning_uri(user, raw_secret)
    qr_svg = twofa.render_totp_qr_svg(uri)

    return render_projectauth(
        request,
        "twofa_setup",
        {
            "pending_device": pending_device,
            "totp_secret": formatted_secret,
            "totp_secret_raw": raw_secret,
            "qr_svg": qr_svg,
            "twofa_summary": twofa.get_user_2fa_summary(user),
            "must_enrol": bool(preauth_state.get("must_enrol")) if preauth_state else twofa.user_requires_2fa_by_policy(user) and not has_confirmed,
            "error_message": error_message,
            "sudo_ok": sudo_ok,
        },
    )


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def twofa_recovery_view(request: HttpRequest) -> HttpResponse:
    from . import twofa
    from .models import RecoveryCode

    user = request.user
    if request.method == "POST":
        if not is_sudo_active(request):
            messages.info(request, "Please re-authenticate to regenerate recovery codes.")
            return redirect(f"{reverse('projectauth:reauth')}?next={reverse('projectauth:twofa_recovery')}")

        fresh_codes = twofa.generate_recovery_codes_for_user(user)
        request.session["pa_fresh_recovery_codes"] = fresh_codes
        log_audit("twofa.recovery_codes_regenerated", request=request, actor=user)
        if user.email:
            send_projectauth_email(
                "twofa_enabled",
                [user.email],
                context={
                    "username": user.username,
                    "message": "Your two-factor authentication recovery codes were regenerated.",
                },
            )
        messages.success(request, "New recovery codes generated. Your previous codes are no longer valid.")
        return redirect("projectauth:twofa_recovery")

    # Pop from session so recovery codes are displayed ONCE
    fresh_codes = request.session.pop("pa_fresh_recovery_codes", None)
    unused_count = RecoveryCode.objects.filter(user=user, used_at__isnull=True).count()

    return render_projectauth(
        request,
        "recovery_codes",
        {
            "recovery_codes": fresh_codes,
            "unused_recovery_count": unused_count,
        },
    )


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def reauth_view(request: HttpRequest) -> HttpResponse:
    from . import twofa
    from .models import CodeChallenge

    user = request.user
    next_param = request.GET.get("next") or request.POST.get("next") or reverse("projectauth:account")
    has_2fa = twofa.user_has_confirmed_totp(user)
    error_message = ""

    if request.method == "POST":
        reauth_action = request.POST.get("reauth_action") or "verify"

        if reauth_action == "send_email_code":
            sent, info_msg = twofa.send_email_otp_challenge(
                user,
                purpose=CodeChallenge.PURPOSE_REAUTH,
                request=request,
            )
            if sent:
                messages.success(request, info_msg)
            else:
                messages.error(request, info_msg)
            return render_projectauth(
                request,
                "reauth",
                {
                    "next": next_param,
                    "has_2fa": has_2fa,
                    "masked_email": mask_email(user.email or ""),
                },
            )

        allowed, _ = check_and_increment_throttle(
            "reauth_attempt",
            str(user.pk),
            limit=8,
            window_seconds=300,
        )
        if not allowed:
            return render_projectauth(
                request,
                "reauth",
                {
                    "next": next_param,
                    "has_2fa": has_2fa,
                    "masked_email": mask_email(user.email or ""),
                    "error_message": "Too many attempts. Please wait a few minutes.",
                },
                status=429,
            )

        password = request.POST.get("password") or ""
        code = (request.POST.get("code") or "").strip()

        pw_ok = user.check_password(password)
        factor_ok = True
        if has_2fa:
            factor_ok = (
                twofa.verify_user_totp(user, code)
                or twofa.verify_email_otp_challenge(user, code, purpose=CodeChallenge.PURPOSE_REAUTH)
                or twofa.verify_and_consume_recovery_code(user, code)
            )

        if pw_ok and factor_ok:
            mark_sudo_verified(request)
            log_audit("auth.reauth_success", request=request, actor=user)
            return redirect(_safe_next_url(request, next_param))

        log_audit("auth.reauth_failed", request=request, actor=user)
        error_message = "Verification failed. Please check your password and verification code."

    return render_projectauth(
        request,
        "reauth",
        {
            "next": next_param,
            "has_2fa": has_2fa,
            "masked_email": mask_email(user.email or ""),
            "error_message": error_message,
        },
    )


@never_cache
@require_GET
def access_denied_view(request: HttpRequest, app_label: str) -> HttpResponse:
    from .middleware import render_access_denied_response

    return render_access_denied_response(request, app_label=app_label)



