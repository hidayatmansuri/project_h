"""
Custom authentication backend for projectauth (Section 4.1).
Authenticates by case-insensitive, NFKC-normalized username or email,
performs constant-time dummy password hashing when the account is missing,
and enforces User.is_active and UserProfile.status == 'active'.
"""

from __future__ import annotations

from typing import Optional

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q
from django.db.models.functions import Lower
from django.http import HttpRequest

from .crypto import normalize_identifier
from .models import UserProfile

User = get_user_model()


class EmailOrUsernameBackend(ModelBackend):
    """
    Authenticates against User.username or User.email / UserProfile.email_normalized
    (case-insensitive, NFKC normalized).
    """

    def authenticate(
        self,
        request: Optional[HttpRequest],
        username: Optional[str] = None,
        password: Optional[str] = None,
        **kwargs,
    ):
        identifier = username or kwargs.get(User.USERNAME_FIELD) or kwargs.get("email")
        if not identifier or password is None:
            return None

        norm = normalize_identifier(identifier)
        if not norm:
            return None

        user = (
            User.objects.select_related("profile")
            .annotate(
                _uname_lower=Lower("username"),
                _email_lower=Lower("email"),
            )
            .filter(
                Q(_uname_lower=norm)
                | Q(_email_lower=norm)
                | Q(profile__username_normalized=norm)
                | Q(profile__email_normalized=norm)
            )
            .first()
        )

        if user is None:
            # Timing equalisation: always hash the candidate password with the default hasher (Argon2id)
            User().set_password(password)
            return None

        password_ok = user.check_password(password)
        if not password_ok:
            return None

        if request is not None:
            # Expose matched user to the projectauth login view so pending_email / pending_approval
            # status screens can be shown after valid credentials without granting an active login.
            setattr(request, "_projectauth_matched_user", user)

        if not self.user_can_authenticate(user):
            # Raising PermissionDenied tells django.contrib.auth.authenticate() to stop
            # iterating further backends (such as ModelBackend) and return None.
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied

        return user

    def user_can_authenticate(self, user) -> bool:
        if not super().user_can_authenticate(user):
            return False
        try:
            profile = user.profile
        except UserProfile.DoesNotExist:
            return False
        return profile.status == UserProfile.STATUS_ACTIVE

