"""
ProtectedApp auto-discovery and registry synchronization (Section 9).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import DEFAULT_DB_ALIAS

from .models import ProtectedApp, UserProfile

ACCESS_MANAGERS_GROUP_NAME = "Access Managers"

DEFAULT_APP_METADATA: Dict[str, dict] = {
    "home": {
        "name": "Home",
        "description": "Public landing page and navigation hub.",
        "icon": "fa-solid fa-house",
        "home_url_name": "home",
        "sort_order": 1,
    },
    "cv": {
        "name": "About Me (CV)",
        "description": "Public curriculum vitae and skills profile.",
        "icon": "fa-regular fa-file-lines",
        "home_url_name": "cv",
        "sort_order": 2,
    },
    "passgen": {
        "name": "Password Generator",
        "description": "Generate high-entropy passwords with custom rules.",
        "icon": "fa-solid fa-star-of-life",
        "home_url_name": "passgen",
        "sort_order": 10,
    },
    "utilitytracker": {
        "name": "Utility Tracker",
        "description": "Shared household electricity and gas prepay meter tracker.",
        "icon": "fa-solid fa-fire-flame-curved",
        "home_url_name": "utility",
        "sort_order": 20,
    },
    "shades": {
        "name": "Colour Shades",
        "description": "Interactive colour shade and tint palette generator.",
        "icon": "fa-solid fa-palette",
        "home_url_name": "shades",
        "sort_order": 30,
    },
    "docedit": {
        "name": "DocEdit",
        "description": "Online PDF layout-preserving editor and OCR tool.",
        "icon": "fa-solid fa-file-pen",
        "home_url_name": "docedit",
        "sort_order": 40,
    },
    "listimage": {
        "name": "ListImage",
        "description": "E-commerce product background removal and 2000x2000 canvas studio.",
        "icon": "fa-solid fa-wand-magic-sparkles",
        "home_url_name": "listimage:index",
        "sort_order": 50,
    },
    "recipes": {
        "name": "Recipes",
        "description": "Recipe collection organised by category and cuisine.",
        "icon": "fa-solid fa-utensils",
        "home_url_name": "recipes:index",
        "sort_order": 60,
    },
}


def is_local_app_config(app_config) -> bool:
    """
    Returns True if app_config lives inside BASE_DIR and is not projectauth itself.
    """
    if app_config.label == "projectauth":
        return False
    base_dir = Path(settings.BASE_DIR).resolve()
    try:
        app_path = Path(app_config.path).resolve()
        app_path.relative_to(base_dir)
        return True
    except Exception:
        return False


def sync_protected_apps(using: str = DEFAULT_DB_ALIAS) -> List[ProtectedApp]:
    """
    Creates or refreshes ProtectedApp rows for all local apps in INSTALLED_APPS.
    Public apps are strictly governed by settings.PROJECTAUTH_PUBLIC_APPS.
    New non-public apps start restricted with no users granted access.
    Also ensures the 'Access Managers' group holds 'projectauth.manage_access'.
    """
    public_labels = set(getattr(settings, "PROJECTAUTH_PUBLIC_APPS", ["home", "cv"]))
    synced: List[ProtectedApp] = []

    for app_config in apps.get_app_configs():
        if not is_local_app_config(app_config):
            continue

        label = app_config.label
        defaults_meta = DEFAULT_APP_METADATA.get(label, {})

        name = (
            getattr(app_config, "projectauth_label", None)
            or defaults_meta.get("name")
            or str(getattr(app_config, "verbose_name", label)).title()
        )
        description = (
            getattr(app_config, "projectauth_description", None)
            or defaults_meta.get("description")
            or ""
        )
        icon = (
            getattr(app_config, "projectauth_icon", None)
            or defaults_meta.get("icon")
            or "fa-solid fa-cube"
        )
        home_url_name = (
            getattr(app_config, "projectauth_home_url_name", None)
            or defaults_meta.get("home_url_name")
            or ""
        )
        sort_order = (
            getattr(app_config, "projectauth_sort_order", None)
            or defaults_meta.get("sort_order")
            or 100
        )
        is_public = label in public_labels

        obj, created = ProtectedApp.objects.using(using).get_or_create(
            app_label=label,
            defaults={
                "name": name,
                "description": description,
                "icon": icon,
                "home_url_name": home_url_name,
                "is_public": is_public,
                "is_active": True,
                "sort_order": sort_order,
                "auto_discovered": True,
            },
        )
        if not created:
            changed = False
            if obj.is_public != is_public:
                obj.is_public = is_public
                changed = True
            if not obj.name and name:
                obj.name = name
                changed = True
            if not obj.home_url_name and home_url_name:
                obj.home_url_name = home_url_name
                changed = True
            if changed:
                obj.save(using=using)
        synced.append(obj)

    # Ensure Access Managers group and permission exist
    try:
        ct = ContentType.objects.db_manager(using).get_for_model(UserProfile)
        perm, _ = Permission.objects.using(using).get_or_create(
            content_type=ct,
            codename="manage_access",
            defaults={"name": "Can approve users and grant or revoke app access"},
        )
        group, _ = Group.objects.using(using).get_or_create(name=ACCESS_MANAGERS_GROUP_NAME)
        group.permissions.add(perm)
    except Exception:
        # Safe during partial migrations when auth_permission / auth_group may not be ready
        pass

    return synced

