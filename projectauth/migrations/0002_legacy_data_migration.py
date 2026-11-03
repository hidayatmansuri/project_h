"""
Reversible data migration (Section 4.3):
- Creates UserProfile for every existing User:
  * Superusers become admins (is_superuser=True, is_staff=True) with created_via='legacy', status='active'.
  * Other users become status='active', created_via='legacy' with NO app access.
- Seeds ProtectedApp rows from installed local apps (home & cv public; all others restricted).
- Initializes singleton AuthSettings(pk=1).
"""

from __future__ import annotations

import unicodedata
from django.conf import settings
from django.db import migrations
from django.utils import timezone

from projectauth.registry import DEFAULT_APP_METADATA, is_local_app_config


def _norm(val: str) -> str:
    if not val:
        return ""
    return unicodedata.normalize("NFKC", str(val)).strip().lower()


def forwards(apps_registry, schema_editor):
    from django.apps import apps as live_apps

    db_alias = schema_editor.connection.alias
    User = apps_registry.get_model("auth", "User")
    UserProfile = apps_registry.get_model("projectauth", "UserProfile")
    ProtectedApp = apps_registry.get_model("projectauth", "ProtectedApp")
    AuthSettings = apps_registry.get_model("projectauth", "AuthSettings")

    now = timezone.now()
    seen_emails = set(
        UserProfile.objects.using(db_alias)
        .exclude(email_normalized__isnull=True)
        .values_list("email_normalized", flat=True)
    )
    seen_usernames = set(
        UserProfile.objects.using(db_alias).values_list("username_normalized", flat=True)
    )

    for user in User.objects.using(db_alias).all().order_by("id"):
        if UserProfile.objects.using(db_alias).filter(user_id=user.pk).exists():
            continue

        uname_norm = _norm(user.username) or f"user_{user.pk}"
        if uname_norm in seen_usernames:
            uname_norm = f"{uname_norm}_{user.pk}"
        seen_usernames.add(uname_norm)

        email_norm = _norm(user.email or "")
        if not email_norm or email_norm in seen_emails:
            email_val = None
        else:
            email_val = email_norm
            seen_emails.add(email_norm)

        if user.is_superuser and not user.is_staff:
            user.is_staff = True
            user.save(using=db_alias, update_fields=["is_staff"])

        UserProfile.objects.using(db_alias).create(
            user_id=user.pk,
            status="active",
            username_normalized=uname_norm,
            email_normalized=email_val,
            email_verified_at=now if email_val else None,
            must_change_password=False,
            created_via="legacy",
            approved_at=now,
            created_at=now,
        )

    public_labels = set(getattr(settings, "PROJECTAUTH_PUBLIC_APPS", ["home", "cv"]))
    for app_config in live_apps.get_app_configs():
        if not is_local_app_config(app_config):
            continue
        label = app_config.label
        meta = DEFAULT_APP_METADATA.get(label, {})
        ProtectedApp.objects.using(db_alias).get_or_create(
            app_label=label,
            defaults={
                "name": meta.get("name") or str(getattr(app_config, "verbose_name", label)).title(),
                "description": meta.get("description", ""),
                "icon": meta.get("icon", "fa-solid fa-cube"),
                "home_url_name": meta.get("home_url_name", ""),
                "is_public": label in public_labels,
                "is_active": True,
                "sort_order": meta.get("sort_order", 100),
                "auto_discovered": True,
            },
        )

    AuthSettings.objects.using(db_alias).get_or_create(
        pk=1,
        defaults={
            "signup_mode": "open_with_approval",
            "require_2fa_for_admins": True,
            "require_2fa_for_all": False,
            "twofa_grace_days": 0,
            "notify_admins_on_signup": True,
            "admin_idle_timeout_min": 30,
            "user_idle_timeout_hours": 12,
            "password_min_length": 12,
        },
    )


def backwards(apps_registry, schema_editor):
    db_alias = schema_editor.connection.alias
    UserProfile = apps_registry.get_model("projectauth", "UserProfile")
    ProtectedApp = apps_registry.get_model("projectauth", "ProtectedApp")

    UserProfile.objects.using(db_alias).filter(created_via="legacy").delete()
    ProtectedApp.objects.using(db_alias).filter(auto_discovered=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("projectauth", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]

