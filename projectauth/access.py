"""
Central per-app access resolution and authorization logic for projectauth (Section 5.5 & 9).
"""

from __future__ import annotations

import inspect
from typing import List, Optional, Set, Tuple

from django.apps import apps
from django.conf import settings
from django.http import HttpRequest
from django.urls import resolve
from django.utils import timezone

from .models import AppAccess, ProtectedApp, UserProfile

SAFE_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def is_json_request(request: HttpRequest) -> bool:
    """
    Returns True if the request expects a JSON response (Section 5.5):
    - X-Requested-With: XMLHttpRequest
    - Accept header prefers application/json
    - Path contains '/api/'
    - Content-Type is application/json
    """
    path = request.path or ""
    if "/api/" in path:
        return True
    headers = getattr(request, "headers", {}) or {}
    xrw = headers.get("X-Requested-With") or request.META.get("HTTP_X_REQUESTED_WITH", "")
    if xrw == "XMLHttpRequest":
        return True
    accept = (headers.get("Accept") or request.META.get("HTTP_ACCEPT", "")).lower()
    if "application/json" in accept and "text/html" not in accept:
        return True
    ctype = (getattr(request, "content_type", "") or "").lower()
    if ctype.startswith("application/json"):
        return True
    return False


def resolve_view_app_label(
    view_func,
    *,
    path: str = "",
    resolver_match=None,
) -> Optional[str]:
    """
    Resolves the owning Django app_label of a matched view function/class (Section 9).
    Supports function views, class-based views (.view_class), decorators (inspect.unwrap),
    RedirectView targets, static/media serving, and django.contrib.admin.
    """
    norm_path = path or ""
    if norm_path.startswith("/static/") or norm_path.startswith("/media/"):
        return "staticfiles"
    if norm_path.startswith("/admin/") or norm_path == "/admin":
        return "admin"

    if resolver_match is not None:
        app_name = getattr(resolver_match, "app_name", None)
        if app_name and app_name in apps.app_configs:
            return app_name

    if view_func is None:
        return None

    try:
        unwrapped = inspect.unwrap(view_func)
    except Exception:
        unwrapped = view_func

    view_cls = getattr(view_func, "view_class", None) or getattr(unwrapped, "view_class", None)
    mod_name = getattr(view_cls, "__module__", None) or getattr(unwrapped, "__module__", "")

    if mod_name == "django.views.static":
        return "staticfiles"
    if mod_name.startswith("django.contrib.admin"):
        return "admin"

    if mod_name:
        app_cfg = apps.get_containing_app_config(mod_name)
        if app_cfg is not None:
            return app_cfg.label

    # Handle RedirectView by resolving its target URL if internal
    initkwargs = getattr(view_func, "view_initkwargs", None) or getattr(
        unwrapped, "view_initkwargs", None
    )
    if initkwargs and isinstance(initkwargs, dict):
        target_url = str(initkwargs.get("url") or "")
        if target_url.startswith("/"):
            sample_target = target_url.replace("%(subpath)s", "")
            try:
                target_match = resolve(sample_target)
                if target_match.func != view_func:
                    return resolve_view_app_label(
                        target_match.func,
                        path=sample_target,
                        resolver_match=target_match,
                    )
            except Exception:
                pass

    return None


def classify_app_label(app_label: Optional[str]) -> str:
    """
    Classifies an app_label into 'public', 'protected', or 'unclassified' (Section 9).
    """
    if not app_label:
        return "unclassified"
    public_apps = set(getattr(settings, "PROJECTAUTH_PUBLIC_APPS", ["home", "cv"]))
    if app_label in public_apps or app_label in ("staticfiles", "projectauth"):
        return "public"
    if app_label == "admin":
        return "protected"
    if app_label in apps.app_configs:
        return "protected"
    return "unclassified"


def user_is_active_admin(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not (user.is_active and user.is_superuser and user.is_staff):
        return False
    profile = getattr(user, "profile", None)
    if profile is not None and profile.status != UserProfile.STATUS_ACTIVE:
        return False
    return True


def user_is_access_manager(user) -> bool:
    """
    Returns True if user is an active Admin OR member of 'Access Managers' holding
    'projectauth.manage_access' permission (Section 4.2).
    """
    if not user or not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    profile = getattr(user, "profile", None)
    if profile is not None and profile.status != UserProfile.STATUS_ACTIVE:
        return False
    if user.is_superuser and user.is_staff:
        return True
    return user.has_perm("projectauth.manage_access")


def evaluate_app_access(
    user,
    app_label: str,
    *,
    method: str = "GET",
    now=None,
) -> Tuple[bool, str, Optional[ProtectedApp], Optional[AppAccess]]:
    """
    Evaluates whether an authenticated, active, 2FA-satisfied `user` may access `app_label`
    with HTTP `method`.
    Returns (allowed, reason_code, protected_app, grant).
    reason_code is one of:
      - 'ok_public'
      - 'ok_admin'
      - 'ok_granted'
      - 'denied_unregistered_app'
      - 'denied_app_inactive'
      - 'denied_no_grant'
      - 'denied_expired_grant'
      - 'denied_read_only_method'
    """
    public_apps = set(getattr(settings, "PROJECTAUTH_PUBLIC_APPS", ["home", "cv"]))
    if app_label in public_apps or app_label in ("staticfiles", "projectauth"):
        return True, "ok_public", None, None

    protected_app = ProtectedApp.objects.filter(app_label=app_label).first()
    is_admin = user_is_active_admin(user)

    if app_label == "admin":
        if is_admin:
            return True, "ok_admin", None, None
        return False, "denied_no_grant", None, None

    # Fail-closed: an app not yet registered in ProtectedApp is treated as admin-only (Section 9)
    if protected_app is None:
        if is_admin:
            return True, "ok_admin", None, None
        return False, "denied_unregistered_app", None, None

    if not protected_app.is_active:
        if is_admin:
            return True, "ok_admin", protected_app, None
        return False, "denied_app_inactive", protected_app, None

    if is_admin:
        return True, "ok_admin", protected_app, None

    now = now or timezone.now()
    grant = (
        AppAccess.objects.filter(
            user=user,
            app=protected_app,
            revoked_at__isnull=True,
        )
        .order_by("-granted_at")
        .first()
    )
    if grant is None:
        return False, "denied_no_grant", protected_app, None

    if grant.expires_at is not None and grant.expires_at <= now:
        return False, "denied_expired_grant", protected_app, grant

    http_method = (method or "GET").upper()
    if grant.level == AppAccess.LEVEL_READ_ONLY and http_method not in SAFE_READ_METHODS:
        return False, "denied_read_only_method", protected_app, grant

    return True, "ok_granted", protected_app, grant


def get_accessible_app_labels(user) -> Set[str]:
    public_apps = set(getattr(settings, "PROJECTAUTH_PUBLIC_APPS", ["home", "cv"]))
    result: Set[str] = set(public_apps)
    if not user or not getattr(user, "is_authenticated", False) or not user.is_active:
        return result
    profile = getattr(user, "profile", None)
    if profile is not None and profile.status != UserProfile.STATUS_ACTIVE:
        return result

    if user_is_active_admin(user):
        result.update(
            ProtectedApp.objects.filter(is_active=True).values_list("app_label", flat=True)
        )
        return result

    now = timezone.now()
    grants = AppAccess.objects.filter(
        user=user,
        revoked_at__isnull=True,
        app__is_active=True,
    ).select_related("app")
    for g in grants:
        if g.is_currently_active(now=now):
            result.add(g.app.app_label)
    return result

