"""
Management command `python manage.py projectauth_init_admin` (Section 8.2 & 13).
Bootstraps or promotes a projectauth Administrator safely without a "first visitor becomes admin" path.
- Interactive by default (prompts for username, email, hidden password + confirmation).
- Non-interactive via `--username` and `--email` reading password from env `PROJECTAUTH_INIT_ADMIN_PASSWORD`
  (never accepts a password as a CLI argument).
- `--generate` creates a strong random password and prints it once.
- `--promote <existing_username>` upgrades an existing user to an active projectauth Admin.
- `--no-force-change` is opt-in (default sets `must_change_password=True` when setting/generating a password).
- Idempotent and safe to re-run. Audits `admin.bootstrap`.
"""

from __future__ import annotations

import getpass
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone

from projectauth.audit import log_audit
from projectauth.console_views import generate_strong_password
from projectauth.crypto import normalize_identifier
from projectauth.forms import validate_projectauth_password
from projectauth.models import UserProfile

User = get_user_model()


class Command(BaseCommand):
    help = "Creates or promotes a projectauth Administrator account (idempotent, audited as admin.bootstrap)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            default="",
            help="Username for the administrator account (non-interactive mode).",
        )
        parser.add_argument(
            "--email",
            type=str,
            default="",
            help="Email address for the administrator account (non-interactive mode).",
        )
        parser.add_argument(
            "--generate",
            action="store_true",
            help="Generate a strong random password and print it once.",
        )
        parser.add_argument(
            "--promote",
            type=str,
            default="",
            help="Promote an existing user by username to active projectauth Administrator.",
        )
        parser.add_argument(
            "--no-force-change",
            action="store_true",
            help="Do not set must_change_password=True on the created/updated account.",
        )

    def handle(self, *args, **options):
        promote_uname = normalize_identifier(options.get("promote") or "")
        generate_flag = bool(options.get("generate"))
        no_force_change = bool(options.get("no_force_change"))
        now = timezone.now()

        if promote_uname:
            user = (
                User.objects.select_related("profile")
                .annotate(_ul=Lower("username"))
                .filter(Q(_ul=promote_uname) | Q(profile__username_normalized=promote_uname))
                .first()
            )
            if user is None:
                raise CommandError(f"User '{promote_uname}' does not exist.")

            generated_pw = ""
            env_pw = os.environ.get("PROJECTAUTH_INIT_ADMIN_PASSWORD", "")
            password_to_set = ""
            if generate_flag:
                generated_pw = generate_strong_password(16)
                password_to_set = generated_pw
            elif env_pw:
                validate_projectauth_password(env_pw, user=user)
                password_to_set = env_pw

            with transaction.atomic():
                user.is_superuser = True
                user.is_staff = True
                user.is_active = True
                if password_to_set:
                    user.set_password(password_to_set)
                user.save()

                profile, _ = UserProfile.objects.get_or_create(
                    user=user,
                    defaults={
                        "username_normalized": normalize_identifier(user.username),
                        "email_normalized": normalize_identifier(user.email or "") or None,
                        "created_via": UserProfile.CREATED_VIA_ADMIN,
                    },
                )
                profile.status = UserProfile.STATUS_ACTIVE
                if not profile.email_verified_at:
                    profile.email_verified_at = now
                if password_to_set:
                    profile.password_changed_at = now
                    profile.must_change_password = not no_force_change
                elif no_force_change:
                    profile.must_change_password = False
                profile.save()

            log_audit(
                "admin.bootstrap",
                actor_label="cli:projectauth_init_admin",
                target_user=user,
                details={
                    "mode": "promote",
                    "password_updated": bool(password_to_set),
                    "must_change_password": profile.must_change_password,
                },
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Promoted user '{user.username}' to active projectauth Administrator."
                )
            )
            if generated_pw:
                self.stdout.write(
                    f"Generated temporary password (shown once): {generated_pw}"
                )
            return

        username = normalize_identifier(options.get("username") or "")
        email = normalize_identifier(options.get("email") or "")

        if not username:
            raw_u = input("Administrator username: ").strip()
            username = normalize_identifier(raw_u)
        if not email:
            raw_e = input("Administrator email: ").strip()
            email = normalize_identifier(raw_e)

        if not username or len(username) < 3:
            raise CommandError("A valid username of at least 3 characters is required.")
        if not email or "@" not in email:
            raise CommandError("A valid email address is required.")

        existing_user = (
            User.objects.select_related("profile")
            .annotate(_ul=Lower("username"), _el=Lower("email"))
            .filter(
                Q(_ul=username)
                | Q(profile__username_normalized=username)
                | Q(_el=email)
                | Q(profile__email_normalized=email)
            )
            .first()
        )

        generated_pw = ""
        password = ""
        if generate_flag:
            generated_pw = generate_strong_password(16)
            password = generated_pw
        else:
            env_pw = os.environ.get("PROJECTAUTH_INIT_ADMIN_PASSWORD", "")
            if env_pw:
                password = env_pw
            elif existing_user is not None and options.get("username"):
                # Idempotent re-run on existing user when no new password requested
                password = ""
            else:
                pw1 = getpass.getpass("Password: ")
                pw2 = getpass.getpass("Password (again): ")
                if pw1 != pw2:
                    raise CommandError("Passwords did not match.")
                password = pw1

        if password:
            validate_projectauth_password(
                password,
                user=existing_user,
                username=username,
                email=email,
            )

        with transaction.atomic():
            if existing_user is not None:
                user = existing_user
                user.username = username
                user.email = email
                user.is_superuser = True
                user.is_staff = True
                user.is_active = True
                if password:
                    user.set_password(password)
                user.save()
                action_mode = "updated"
            else:
                if not password:
                    raise CommandError(
                        "Password is required when creating a new admin (set PROJECTAUTH_INIT_ADMIN_PASSWORD or pass --generate)."
                    )
                user = User(
                    username=username,
                    email=email,
                    is_superuser=True,
                    is_staff=True,
                    is_active=True,
                )
                user.set_password(password)
                user.save()
                action_mode = "created"

            profile, _ = UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    "username_normalized": username,
                    "email_normalized": email,
                    "created_via": UserProfile.CREATED_VIA_ADMIN,
                },
            )
            profile.status = UserProfile.STATUS_ACTIVE
            profile.username_normalized = username
            profile.email_normalized = email
            if not profile.email_verified_at:
                profile.email_verified_at = now
            if password:
                profile.password_changed_at = now
                profile.must_change_password = not no_force_change
            elif no_force_change:
                profile.must_change_password = False
            profile.save()

        log_audit(
            "admin.bootstrap",
            actor_label="cli:projectauth_init_admin",
            target_user=user,
            details={
                "mode": action_mode,
                "must_change_password": profile.must_change_password,
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Administrator '{user.username}' ({action_mode}) is active (must_change_password={profile.must_change_password})."
            )
        )
        if generated_pw:
            self.stdout.write(f"Generated temporary password (shown once): {generated_pw}")

