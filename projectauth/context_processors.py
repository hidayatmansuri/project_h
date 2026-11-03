"""
Context processor exposing accessible apps for templates (Section 9).
"""

from __future__ import annotations

from django.http import HttpRequest

from .access import get_accessible_app_labels


def projectauth_context(request: HttpRequest) -> dict:
    user = getattr(request, "user", None)
    return {
        "projectauth_accessible_apps": get_accessible_app_labels(user),
    }

