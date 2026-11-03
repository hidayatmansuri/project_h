"""
Defence-in-depth view decorator and CBV mixin for per-app access control (Section 9).
"""

from __future__ import annotations

from functools import wraps

from django.http import HttpRequest, HttpResponse

from .middleware import enforce_app_access_for_request


def app_access_required(app_label: str):
    """
    Decorator enforcing projectauth access rules for `app_label` on a view function.
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            denied_response = enforce_app_access_for_request(request, app_label)
            if denied_response is not None:
                return denied_response
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


class AppAccessRequiredMixin:
    """
    Class-based view mixin enforcing projectauth access rules for `self.projectauth_app_label`.
    """

    projectauth_app_label: str = ""

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        label = self.projectauth_app_label
        if label:
            denied_response = enforce_app_access_for_request(request, label)
            if denied_response is not None:
                return denied_response
        return super().dispatch(request, *args, **kwargs)

