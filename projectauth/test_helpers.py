"""
Helper for authenticating test clients in existing app test suites with a valid
UserProfile and AppAccess grant.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import AppAccess, ProtectedApp, UserProfile
from .registry import sync_protected_apps

User = get_user_model()


def grant_test_client_app_access(
    client,
    app_label: str,
    *,
    username: str = "app_test_user",
    level: str = AppAccess.LEVEL_FULL,
):
    sync_protected_apps()
    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            "email": f"{username}@example.com",
            "is_active": True,
        },
    )
    if created:
        user.set_password("TestPassword!1234")
        user.save()
    UserProfile.objects.get_or_create(
        user=user,
        defaults={
            "status": UserProfile.STATUS_ACTIVE,
            "email_verified_at": timezone.now(),
        },
    )
    app_obj = ProtectedApp.objects.get(app_label=app_label)
    AppAccess.objects.update_or_create(
        user=user,
        app=app_obj,
        revoked_at=None,
        defaults={"level": level, "expires_at": None},
    )
    client.force_login(user, backend="projectauth.backends.EmailOrUsernameBackend")
    return user

