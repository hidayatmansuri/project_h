"""
Template tags for projectauth (Section 6 & 9):
- `{% user_can_access 'docedit' as ok %}`
- `{% projectauth_nav %}` inclusion tag rendering `projectauth_parts/nav_control.html`
"""

from __future__ import annotations

from django import template
from django.contrib.auth import get_user_model

from projectauth.access import (
    evaluate_app_access,
    user_is_access_manager,
    user_is_active_admin,
)
from projectauth.models import AccessRequest, UserProfile

register = template.Library()
User = get_user_model()


@register.simple_tag(takes_context=True)
def user_can_access(context, app_label: str) -> bool:
    request = context.get("request")
    user = getattr(request, "user", None) if request else context.get("user")
    if not user or not getattr(user, "is_authenticated", False):
        allowed, _, _, _ = evaluate_app_access(None, app_label)
        return allowed
    allowed, _, _, _ = evaluate_app_access(user, app_label)
    return allowed


@register.inclusion_tag("projectauth_parts/nav_control.html", takes_context=True)
def projectauth_nav(context) -> dict:
    request = context.get("request")
    user = getattr(request, "user", None) if request else context.get("user")
    is_authenticated = bool(user and getattr(user, "is_authenticated", False))
    show_console = False
    pending_count = 0
    initial = ""
    username = ""
    next_path = "/"

    if request is not None:
        next_path = request.path or "/"

    if is_authenticated:
        username = user.username or ""
        initial = (username[:1] or "U").upper()
        show_console = user_is_active_admin(user) or user_is_access_manager(user)
        if show_console:
            pending_users = UserProfile.objects.filter(
                status__in=[
                    UserProfile.STATUS_PENDING_APPROVAL,
                    UserProfile.STATUS_PENDING_EMAIL,
                ]
            ).count()
            pending_reqs = AccessRequest.objects.filter(
                status=AccessRequest.STATUS_PENDING
            ).count()
            pending_count = pending_users + pending_reqs

    return {
        "request": request,
        "is_authenticated": is_authenticated,
        "username": username,
        "user_initial": initial,
        "show_console": show_console,
        "pending_count": pending_count,
        "next_path": next_path,
    }

