"""
Phase 5 tests: Admin Console, Permission Boundaries, End-to-End User Journey,
Admin Invitations, Last-Admin Protection, and Management Commands (Section 8, 12, 13, 15).
"""

from __future__ import annotations

import base64
import io
import os
import re
from datetime import timedelta
from unittest.mock import patch

import pyotp
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from projectauth import twofa
from projectauth.console_views import ensure_access_managers_group
from projectauth.models import (
    AccessRequest,
    AdminInvitation,
    AppAccess,
    AuditEvent,
    AuthSettings,
    CodeChallenge,
    PendingEmailChange,
    ProtectedApp,
    SessionRecord,
    TOTPDevice,
    TrustedDevice,
    UserProfile,
)
from projectauth.tokens import create_email_verification_token

User = get_user_model()


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PROJECTAUTH_MIN_SUBMIT_SECONDS=0,
)
class AdminConsoleAndCommandsTests(TestCase):
    def setUp(self):
        self.admin_pw = "AdminStrong!2345"
        self.admin = User.objects.create_user(
            username="console_admin",
            email="admin@example.com",
            password=self.admin_pw,
            is_superuser=True,
            is_staff=True,
            is_active=True,
        )
        UserProfile.objects.create(
            user=self.admin,
            status=UserProfile.STATUS_ACTIVE,
            username_normalized="console_admin",
            email_normalized="admin@example.com",
            created_via=UserProfile.CREATED_VIA_ADMIN,
            email_verified_at=timezone.now(),
        )
        # Enrol TOTP for admin so admin 2FA requirement is satisfied
        self.admin_totp_secret = pyotp.random_base32()
        dev = TOTPDevice(
            user=self.admin,
            name="Admin Authenticator",
            confirmed_at=timezone.now(),
        )
        dev.set_secret(self.admin_totp_secret)
        dev.save()

    def _login_admin(self, client: Client) -> None:
        client.force_login(
            self.admin, backend="projectauth.backends.EmailOrUsernameBackend"
        )
        s = client.session
        s["pa_2fa_verified"] = True
        s["pa_sudo_ts"] = timezone.now().timestamp()
        s.save()

    def test_full_journey_new_user_approve_grant_one_app_only_that_app_works(self):
        """
        End-to-end journey required by Phase 5:
        new user -> verify email -> admin approves & grants ONE app (passgen) ->
        only passgen works; all other protected apps remain 403.
        """
        user_pw = "JourneyPass!2345"
        new_user = User.objects.create_user(
            username="journey_user",
            email="journey@example.com",
            password=user_pw,
            is_active=False,
        )
        UserProfile.objects.create(
            user=new_user,
            status=UserProfile.STATUS_PENDING_EMAIL,
            username_normalized="journey_user",
            email_normalized="journey@example.com",
            created_via=UserProfile.CREATED_VIA_SIGNUP,
        )
        passgen_app = ProtectedApp.objects.get(app_label="passgen")
        AccessRequest.objects.create(
            user=new_user,
            app=passgen_app,
            status=AccessRequest.STATUS_PENDING,
            message="Need password generator",
        )

        # Step 1: User verifies email -> status becomes pending_approval
        verify_token = create_email_verification_token(new_user)
        user_client = Client()
        resp_ver = user_client.get(
            reverse("projectauth:verify_email", kwargs={"token": verify_token})
        )
        self.assertEqual(resp_ver.status_code, 200)
        new_user.refresh_from_db()
        self.assertEqual(new_user.profile.status, UserProfile.STATUS_PENDING_APPROVAL)
        self.assertEqual(AppAccess.objects.filter(user=new_user).count(), 0)

        # Step 2: Admin approves user in console_pending and grants ONLY 'passgen'
        admin_client = Client()
        self._login_admin(admin_client)
        resp_approve = admin_client.post(
            reverse("projectauth:console_pending"),
            {
                "user_id": new_user.pk,
                "pending_action": "approve",
                "app_labels": ["passgen"],
                "level": "full",
            },
        )
        self.assertEqual(resp_approve.status_code, 302)

        new_user.refresh_from_db()
        self.assertTrue(new_user.is_active)
        self.assertEqual(new_user.profile.status, UserProfile.STATUS_ACTIVE)

        # Step 3: User signs in via login view
        resp_login = user_client.post(
            reverse("projectauth:login"),
            {"identifier": "journey_user", "password": user_pw},
        )
        self.assertEqual(resp_login.status_code, 302)

        # Step 4: Only passgen works (200); other protected apps return 403
        self.assertEqual(user_client.get(reverse("passgen")).status_code, 200)
        self.assertEqual(user_client.get(reverse("shades")).status_code, 403)
        self.assertEqual(user_client.get(reverse("utility")).status_code, 403)
        self.assertEqual(user_client.get(reverse("docedit")).status_code, 403)
        self.assertEqual(user_client.get("/recipes/").status_code, 403)

    def test_permission_boundaries_regular_user_vs_access_manager_vs_admin(self):
        """
        Verifies console permission boundaries:
        - Regular user cannot reach any console screen (403).
        - Access Manager can reach dashboard, pending, users, apps, requests, and grant/revoke access,
          but CANNOT reach admins, invites, audit, settings, or delete/modify admins (403).
        """
        # Regular active user
        reg_user = User.objects.create_user(
            username="reg_user",
            email="reg@example.com",
            password="RegUserPass!2345",
            is_active=True,
        )
        UserProfile.objects.create(
            user=reg_user,
            status=UserProfile.STATUS_ACTIVE,
            username_normalized="reg_user",
            email_normalized="reg@example.com",
            email_verified_at=timezone.now(),
        )
        reg_client = Client()
        reg_client.force_login(reg_user, backend="projectauth.backends.EmailOrUsernameBackend")
        self.assertEqual(
            reg_client.get(reverse("projectauth:console_dashboard")).status_code, 403
        )
        self.assertEqual(
            reg_client.get(reverse("projectauth:console_apps")).status_code, 403
        )

        # Access Manager user
        mgr_group = ensure_access_managers_group()
        mgr_user = User.objects.create_user(
            username="mgr_user",
            email="mgr@example.com",
            password="MgrUserPass!2345",
            is_active=True,
        )
        UserProfile.objects.create(
            user=mgr_user,
            status=UserProfile.STATUS_ACTIVE,
            username_normalized="mgr_user",
            email_normalized="mgr@example.com",
            email_verified_at=timezone.now(),
        )
        mgr_user.groups.add(mgr_group)

        mgr_client = Client()
        mgr_client.force_login(mgr_user, backend="projectauth.backends.EmailOrUsernameBackend")

        # Allowed screens for Access Manager
        self.assertEqual(
            mgr_client.get(reverse("projectauth:console_dashboard")).status_code, 200
        )
        self.assertEqual(
            mgr_client.get(reverse("projectauth:console_pending")).status_code, 200
        )
        self.assertEqual(
            mgr_client.get(reverse("projectauth:console_users")).status_code, 200
        )
        self.assertEqual(
            mgr_client.get(reverse("projectauth:console_apps")).status_code, 200
        )
        self.assertEqual(
            mgr_client.get(reverse("projectauth:console_requests")).status_code, 200
        )

        # Access Manager can grant Tester preset (read_only + 7 days) to regular user
        resp_grant = mgr_client.post(
            reverse("projectauth:console_apps"),
            {
                "matrix_action": "tester_preset",
                "user_ids": [str(reg_user.pk)],
                "app_labels": ["utilitytracker"],
            },
        )
        self.assertEqual(resp_grant.status_code, 302)
        grant = AppAccess.objects.get(
            user=reg_user,
            app__app_label="utilitytracker",
            revoked_at__isnull=True,
        )
        self.assertEqual(grant.level, AppAccess.LEVEL_READ_ONLY)
        self.assertIsNotNone(grant.expires_at)

        # Blocked screens for Access Manager (cannot create admins, change policies, or view full audit)
        self.assertEqual(
            mgr_client.get(reverse("projectauth:console_admins")).status_code, 403
        )
        self.assertEqual(
            mgr_client.post(
                reverse("projectauth:console_admins"),
                {"admin_action": "promote_admin", "user_id": reg_user.pk},
            ).status_code,
            403,
        )
        self.assertEqual(
            mgr_client.get(reverse("projectauth:console_invites")).status_code, 403
        )
        self.assertEqual(
            mgr_client.get(reverse("projectauth:console_settings")).status_code, 403
        )
        self.assertEqual(
            mgr_client.get(reverse("projectauth:console_audit")).status_code, 403
        )
        # Access Manager cannot delete users or edit admin accounts
        self.assertEqual(
            mgr_client.post(
                reverse("projectauth:console_user_detail", kwargs={"user_id": reg_user.pk}),
                {"user_action": "delete_user"},
            ).status_code,
            403,
        )
        self.assertEqual(
            mgr_client.post(
                reverse("projectauth:console_user_detail", kwargs={"user_id": self.admin.pk}),
                {"user_action": "suspend"},
            ).status_code,
            403,
        )

    def test_admin_invitation_flow_and_2fa_enrolment_redirect(self):
        admin_client = Client()
        self._login_admin(admin_client)
        mail.outbox.clear()

        resp = admin_client.post(
            reverse("projectauth:console_invites"),
            {
                "invite_action": "create",
                "email": "newadmin@example.com",
                "role": AdminInvitation.ROLE_ADMIN,
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(AdminInvitation.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

        body = mail.outbox[0].body
        match = re.search(r"/auth/invite/([A-Za-z0-9_\-]+)/", body)
        self.assertIsNotNone(match)
        raw_token = match.group(1)

        invitee_client = Client()
        resp_get = invitee_client.get(
            reverse("projectauth:invite_accept", kwargs={"token": raw_token})
        )
        self.assertEqual(resp_get.status_code, 200)

        resp_post = invitee_client.post(
            reverse("projectauth:invite_accept", kwargs={"token": raw_token}),
            {
                "username": "invited_boss",
                "password": "InvitedBoss!2345",
                "password_confirm": "InvitedBoss!2345",
            },
        )
        self.assertEqual(resp_post.status_code, 302)
        self.assertEqual(resp_post["Location"], reverse("projectauth:twofa_setup"))

        invited_user = User.objects.get(username="invited_boss")
        self.assertTrue(invited_user.is_superuser)
        self.assertTrue(invited_user.is_staff)
        self.assertEqual(invited_user.profile.status, UserProfile.STATUS_ACTIVE)

        # Re-using the same invitation token must fail (400)
        resp_reuse = invitee_client.get(
            reverse("projectauth:invite_accept", kwargs={"token": raw_token})
        )
        self.assertEqual(resp_reuse.status_code, 400)

    def test_last_admin_protection_blocks_demote_suspend_and_delete(self):
        # Ensure self.admin is the ONLY active superuser in the test DB
        User.objects.filter(is_superuser=True).exclude(pk=self.admin.pk).update(
            is_superuser=False, is_staff=False
        )

        admin_client = Client()
        self._login_admin(admin_client)

        # 1. Cannot demote last active admin
        admin_client.post(
            reverse("projectauth:console_admins"),
            {"admin_action": "demote_admin", "user_id": self.admin.pk},
        )
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_superuser)

        # 2. Cannot suspend last active admin
        admin_client.post(
            reverse("projectauth:console_user_detail", kwargs={"user_id": self.admin.pk}),
            {"user_action": "suspend"},
        )
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertEqual(self.admin.profile.status, UserProfile.STATUS_ACTIVE)

        # 3. Cannot delete last active admin
        admin_client.post(
            reverse("projectauth:console_user_detail", kwargs={"user_id": self.admin.pk}),
            {"user_action": "delete_user"},
        )
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())
        self.assertTrue(
            AuditEvent.objects.filter(action="admin.last_admin_protected").exists()
        )

    def test_user_detail_temp_password_once_delete_anonymisation_and_audit_csv(self):
        target = User.objects.create_user(
            username="temp_target",
            email="target@example.com",
            password="OldTargetPass!23",
            is_active=True,
        )
        UserProfile.objects.create(
            user=target,
            status=UserProfile.STATUS_ACTIVE,
            username_normalized="temp_target",
            email_normalized="target@example.com",
            email_verified_at=timezone.now(),
        )

        admin_client = Client()
        self._login_admin(admin_client)

        # Generate temporary password -> shown once on next GET, then cleared
        resp_temp = admin_client.post(
            reverse("projectauth:console_user_detail", kwargs={"user_id": target.pk}),
            {"user_action": "set_temp_password"},
            follow=True,
        )
        self.assertEqual(resp_temp.status_code, 200)
        self.assertIsNotNone(resp_temp.context["temp_password_once"])
        target.refresh_from_db()
        self.assertTrue(target.profile.must_change_password)

        # Refreshing the page no longer shows the temporary password
        resp_second = admin_client.get(
            reverse("projectauth:console_user_detail", kwargs={"user_id": target.pk})
        )
        self.assertIsNone(resp_second.context["temp_password_once"])

        # Delete target user -> audit events anonymised
        admin_client.post(
            reverse("projectauth:console_user_detail", kwargs={"user_id": target.pk}),
            {"user_action": "delete_user"},
        )
        self.assertFalse(User.objects.filter(pk=target.pk).exists())
        del_ev = AuditEvent.objects.filter(action="admin.user_deleted").first()
        self.assertIsNotNone(del_ev)
        self.assertTrue(del_ev.target_label.startswith("deleted-user-"))

        # Export Audit CSV
        resp_csv = admin_client.get(
            reverse("projectauth:console_audit_export") + "?action=admin.user_deleted"
        )
        self.assertEqual(resp_csv.status_code, 200)
        self.assertIn("text/csv", resp_csv["Content-Type"])
        self.assertIn("admin.user_deleted", resp_csv.content.decode("utf-8"))

    def test_management_commands_init_admin_rotate_keys_purge_audit_and_cleanup(self):
        # 1. projectauth_init_admin with env password & --promote
        out = io.StringIO()
        with patch.dict(
            os.environ, {"PROJECTAUTH_INIT_ADMIN_PASSWORD": "BootstrapAdmin!234"}
        ):
            call_command(
                "projectauth_init_admin",
                username="cli_admin",
                email="cli_admin@example.com",
                stdout=out,
            )
        cli_admin = User.objects.get(username="cli_admin")
        self.assertTrue(cli_admin.is_superuser)
        self.assertTrue(cli_admin.profile.must_change_password)
        self.assertTrue(AuditEvent.objects.filter(action="admin.bootstrap").exists())

        # Idempotent re-run with --promote --no-force-change
        call_command(
            "projectauth_init_admin",
            promote="cli_admin",
            no_force_change=True,
            stdout=out,
        )
        cli_admin.refresh_from_db()
        self.assertFalse(cli_admin.profile.must_change_password)

        # 2. projectauth_rotate_keys
        k0 = base64.urlsafe_b64encode(b"0" * 32).decode("ascii")
        k1 = base64.urlsafe_b64encode(b"1" * 32).decode("ascii")
        with override_settings(PROJECTAUTH_ENCRYPTION_KEYS=f"kid0:{k0}"):
            rot_dev = TOTPDevice(user=cli_admin, name="RotTest")
            rot_dev.set_secret("JBSWY3DPEHPK3PXP")
            rot_dev.save()
            self.assertTrue(rot_dev.secret_encrypted.startswith("v1:kid0:"))

        with override_settings(PROJECTAUTH_ENCRYPTION_KEYS=f"kid1:{k1},kid0:{k0}"):
            call_command("projectauth_rotate_keys", stdout=out)
            rot_dev.refresh_from_db()
            self.assertTrue(rot_dev.secret_encrypted.startswith("v1:kid1:"))
            self.assertEqual(rot_dev.get_secret(), "JBSWY3DPEHPK3PXP")

        # 3. projectauth_purge_audit
        old_ev = AuditEvent.objects.create(
            action="legacy.old_event",
            created_at=timezone.now() - timedelta(days=400),
        )
        call_command("projectauth_purge_audit", older_than=365, stdout=out)
        self.assertFalse(AuditEvent.objects.filter(pk=old_ev.pk).exists())
        self.assertTrue(AuditEvent.objects.filter(action="audit.purged").exists())

        # 4. projectauth_cleanup
        past = timezone.now() - timedelta(days=2)
        CodeChallenge.objects.create(
            user=cli_admin,
            purpose="login_2fa",
            code_hmac="a" * 64,
            expires_at=past,
        )
        TrustedDevice.objects.create(
            user=cli_admin,
            token_hmac="b" * 64,
            expires_at=past,
        )
        PendingEmailChange.objects.create(
            user=cli_admin,
            new_email="expired@example.com",
            token_hmac="c" * 64,
            expires_at=past,
        )
        SessionRecord.objects.create(
            user=cli_admin,
            session_key_hash="d" * 64,
            expires_at=past,
        )
        call_command("projectauth_cleanup", stdout=out)
        self.assertEqual(CodeChallenge.objects.filter(expires_at__lte=past).count(), 0)
        self.assertEqual(TrustedDevice.objects.filter(expires_at__lte=past).count(), 0)
        self.assertTrue(AuditEvent.objects.filter(action="system.cleanup").exists())
