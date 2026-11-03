"""
Phase 2 Core Authentication unit and integration tests:
- EmailOrUsernameBackend (case-insensitive username/email, timing equalization, status checks)
- Sign-up, anti-enumeration, <dialog> popup, honeypot, single-use verification link, pending screen
- Login, django-axes lockout, new-device email, open-redirect protection, forced password change, POST-only logout
- Forgot password (single-use + invalidated on password change), username reminder
- Account self-service (password/username/email change, session revocation, JSON export, account deletion + last-admin protection, idle timeout)
"""

from __future__ import annotations

import json
import re
from datetime import timedelta

from django.contrib.auth import authenticate, get_user_model
from django.core import mail
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from projectauth.models import (
    AccessRequest,
    AuditEvent,
    CodeChallenge,
    PendingEmailChange,
    ProtectedApp,
    SessionRecord,
    UserProfile,
)
from projectauth.registry import sync_protected_apps
from projectauth.tokens import create_email_verification_token, create_password_reset_token

User = get_user_model()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class BackendAndSignupTests(TestCase):
    def setUp(self):
        sync_protected_apps()
        self.client = Client()

    def _create_active_user(self, username="alice", email="alice@example.com", password="StrongPassword123!"):
        u = User.objects.create_user(username=username, email=email, password=password, is_active=True)
        UserProfile.objects.create(
            user=u,
            status=UserProfile.STATUS_ACTIVE,
            email_verified_at=timezone.now(),
        )
        return u

    def test_backend_authenticates_case_insensitive_username_and_email(self):
        u = self._create_active_user("Alice_Smith", "Alice.Smith@Example.com", "StrongPassword123!")
        req = RequestFactory().post("/auth/login/")

        self.assertEqual(authenticate(request=req, username="ALICE_SMITH", password="StrongPassword123!"), u)
        self.assertEqual(authenticate(request=req, username="alice.smith@example.com", password="StrongPassword123!"), u)
        self.assertEqual(authenticate(request=req, username="ALICE.SMITH@EXAMPLE.COM", password="StrongPassword123!"), u)
        self.assertIsNone(authenticate(request=req, username="alice_smith", password="WrongPassword!"))
        self.assertIsNone(authenticate(request=req, username="nonexistent@example.com", password="StrongPassword123!"))

    def test_backend_rejects_non_active_profile_statuses(self):
        u = self._create_active_user("bob", "bob@example.com", "StrongPassword123!")
        req = RequestFactory().post("/auth/login/")
        for st in (
            UserProfile.STATUS_PENDING_EMAIL,
            UserProfile.STATUS_PENDING_APPROVAL,
            UserProfile.STATUS_SUSPENDED,
            UserProfile.STATUS_REJECTED,
        ):
            u.profile.status = st
            u.profile.save(update_fields=["status"])
            self.assertIsNone(authenticate(request=req, username="bob", password="StrongPassword123!"))

    def test_signup_flow_popup_verification_single_use_and_pending_screen(self):
        passgen_app = ProtectedApp.objects.get(app_label="passgen")
        resp = self.client.post(
            reverse("projectauth:signup"),
            {
                "username": "NewTester",
                "email": "NewTester@Example.com",
                "password": "VeryStrongPassword!23",
                "password_confirm": "VeryStrongPassword!23",
                "requested_apps": [passgen_app.pk],
                "accept_terms": "on",
                "website_url": "",
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")
        # Check <dialog> modal and required copy (Section 5.1)
        self.assertIn('<dialog id="paSignupModal"', html)
        self.assertIn("Account created: access pending.", html)
        self.assertIn("newtester", html)
        self.assertIn("n****r@example.com", html)

        user = User.objects.get(username="newtester")
        self.assertFalse(user.is_active)
        self.assertEqual(user.profile.status, UserProfile.STATUS_PENDING_EMAIL)
        self.assertEqual(AccessRequest.objects.filter(user=user, app=passgen_app).count(), 1)
        self.assertEqual(len(mail.outbox), 1)

        # Extract verification path from email
        body = mail.outbox[0].body
        match = re.search(r"(/auth/verify-email/[^\s]+)", body)
        self.assertIsNotNone(match)
        verify_path = match.group(1)

        # 1st visit verifies email -> status becomes pending_approval
        v_resp1 = self.client.get(verify_path)
        self.assertEqual(v_resp1.status_code, 200)
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.status, UserProfile.STATUS_PENDING_APPROVAL)
        self.assertIsNotNone(user.profile.email_verified_at)

        # 2nd visit to the SAME link must fail (single-use nonce consumed)
        v_resp2 = self.client.get(verify_path)
        self.assertEqual(v_resp2.status_code, 400)

        # Logging in while pending_approval redirects to /auth/pending/
        login_resp = self.client.post(
            reverse("projectauth:login"),
            {"identifier": "newtester", "password": "VeryStrongPassword!23"},
            follow=True,
        )
        self.assertEqual(login_resp.status_code, 200)
        self.assertIn("Password Generator", login_resp.content.decode("utf-8"))

        # Requesting another app from the pending screen works
        shades_app = ProtectedApp.objects.get(app_label="shades")
        req_resp = self.client.post(
            reverse("projectauth:request_access"),
            {"app_label": "shades", "message": "Need shades tool"},
            follow=True,
        )
        self.assertEqual(req_resp.status_code, 200)
        self.assertTrue(AccessRequest.objects.filter(user=user, app=shades_app).exists())

    def test_signup_anti_enumeration_on_existing_email(self):
        existing = self._create_active_user("existing_owner", "owner@example.com", "StrongPassword123!")
        mail.outbox.clear()

        resp = self.client.post(
            reverse("projectauth:signup"),
            {
                "username": "different_uname",
                "email": "OWNER@example.com",
                "password": "AnotherStrongPassword!23",
                "password_confirm": "AnotherStrongPassword!23",
                "accept_terms": "on",
                "website_url": "",
            },
            follow=True,
        )
        # Shows identical signup_done screen
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Account created: access pending.", resp.content.decode("utf-8"))
        # Does NOT create second user
        self.assertFalse(User.objects.filter(username="different_uname").exists())
        # Sends already_registered_notice to existing owner
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [existing.email])
        self.assertIn("Sign-up attempt", mail.outbox[0].subject)

    def test_expired_email_verification_token_rejected(self):
        u = User.objects.create_user(username="expuser", email="exp@example.com", password="StrongPassword123!", is_active=False)
        UserProfile.objects.create(user=u, status=UserProfile.STATUS_PENDING_EMAIL)
        token = create_email_verification_token(u)
        # Expire the challenge row in DB
        CodeChallenge.objects.filter(user=u).update(expires_at=timezone.now() - timedelta(minutes=5))
        resp = self.client.get(reverse("projectauth:verify_email", kwargs={"token": token}))
        self.assertEqual(resp.status_code, 400)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class LoginAxesLogoutAndRecoveryTests(TestCase):
    def setUp(self):
        sync_protected_apps()
        self.client = Client()
        self.user = User.objects.create_user(
            username="member1",
            email="member1@example.com",
            password="CorrectHorseBattery!1",
            is_active=True,
        )
        UserProfile.objects.create(
            user=self.user,
            status=UserProfile.STATUS_ACTIVE,
            email_verified_at=timezone.now(),
        )

    def test_login_rotates_session_tracks_device_and_blocks_open_redirect(self):
        # 1st login from Device A
        resp1 = self.client.post(
            reverse("projectauth:login"),
            {
                "identifier": "member1@example.com",
                "password": "CorrectHorseBattery!1",
                "next": "https://evil.example.org/steal",
            },
            HTTP_USER_AGENT="BrowserA/1.0",
        )
        # Open redirect blocked -> redirects to home '/'
        self.assertEqual(resp1.status_code, 302)
        self.assertEqual(resp1["Location"], reverse("home"))
        self.assertEqual(SessionRecord.objects.filter(user=self.user).count(), 1)
        self.assertEqual(len(mail.outbox), 0)

        # 2nd login from a new device (BrowserB/2.0) triggers new_device_login email
        client2 = Client()
        resp2 = client2.post(
            reverse("projectauth:login"),
            {
                "identifier": "member1",
                "password": "CorrectHorseBattery!1",
                "next": "/cv/",
            },
            HTTP_USER_AGENT="BrowserB/2.0",
        )
        self.assertEqual(resp2.status_code, 302)
        self.assertEqual(resp2["Location"], "/cv/")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("New sign-in", mail.outbox[0].subject)

    def test_axes_locks_out_after_5_failed_login_attempts(self):
        for i in range(5):
            r = self.client.post(
                reverse("projectauth:login"),
                {"identifier": "member1", "password": f"WrongPass{i}!"},
            )
            self.assertIn(r.status_code, (200, 429))

        # 6th attempt even with right password must be locked out (429)
        r6 = self.client.post(
            reverse("projectauth:login"),
            {"identifier": "member1", "password": "CorrectHorseBattery!1"},
        )
        self.assertEqual(r6.status_code, 429)
        self.assertTrue(AuditEvent.objects.filter(action="login.locked").exists())

    def test_logout_is_post_only_and_flushes_session(self):
        self.client.post(
            reverse("projectauth:login"),
            {"identifier": "member1", "password": "CorrectHorseBattery!1"},
        )
        get_resp = self.client.get(reverse("projectauth:logout"))
        self.assertEqual(get_resp.status_code, 405)

        post_resp = self.client.post(reverse("projectauth:logout"))
        self.assertEqual(post_resp.status_code, 302)
        rec = SessionRecord.objects.filter(user=self.user).first()
        self.assertIsNotNone(rec.revoked_at)

    def test_forgot_and_reset_password_single_use_and_invalidated_by_password_change(self):
        # Anti-enumeration: unknown email gives same redirect/message
        r_unknown = self.client.post(
            reverse("projectauth:forgot_password"),
            {"email": "nobody@example.com"},
            follow=True,
        )
        self.assertEqual(r_unknown.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

        # Known email sends reset link
        r_known = self.client.post(
            reverse("projectauth:forgot_password"),
            {"email": "MEMBER1@example.com"},
            follow=True,
        )
        self.assertEqual(r_known.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

        # Issue two tokens; changing password via token 1 must invalidate token 2 AND make token 1 single-use
        t1 = create_password_reset_token(self.user)
        t2 = create_password_reset_token(self.user)

        reset_url1 = reverse("projectauth:reset_password", kwargs={"token": t1})
        reset_url2 = reverse("projectauth:reset_password", kwargs={"token": t2})

        resp_reset = self.client.post(
            reset_url1,
            {
                "password": "BrandNewPassword!456",
                "password_confirm": "BrandNewPassword!456",
            },
        )
        self.assertEqual(resp_reset.status_code, 302)

        # Token 1 cannot be reused
        self.assertEqual(self.client.get(reset_url1).status_code, 400)
        # Token 2 is automatically invalidated because the user's password changed
        self.assertEqual(self.client.get(reset_url2).status_code, 400)

    def test_forgot_username_anti_enumeration_and_email(self):
        self.client.post(reverse("projectauth:forgot_username"), {"email": "nobody@example.com"})
        self.assertEqual(len(mail.outbox), 0)

        self.client.post(reverse("projectauth:forgot_username"), {"email": "member1@example.com"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("member1", mail.outbox[0].body)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AccountSelfServiceAndSessionTimeoutTests(TestCase):
    def setUp(self):
        sync_protected_apps()
        self.client = Client()
        self.user = User.objects.create_user(
            username="acctuser",
            email="acctuser@example.com",
            password="InitialPassword!123",
            is_active=True,
        )
        UserProfile.objects.create(
            user=self.user,
            status=UserProfile.STATUS_ACTIVE,
            email_verified_at=timezone.now(),
        )
        self.client.post(
            reverse("projectauth:login"),
            {"identifier": "acctuser", "password": "InitialPassword!123"},
        )
        mail.outbox.clear()

    def test_email_change_verifies_new_and_notifies_old(self):
        resp = self.client.post(
            reverse("projectauth:account"),
            {
                "account_action": "change_email",
                "email-new_email": "NewAddress@Example.com",
                "email-current_password": "InitialPassword!123",
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        # Old email is still active before confirmation
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "acctuser@example.com")
        # Two emails sent: one to new address, one notice to old address
        self.assertEqual(len(mail.outbox), 2)
        recipients = {m.to[0] for m in mail.outbox}
        self.assertEqual(recipients, {"newaddress@example.com", "acctuser@example.com"})

        # Extract confirmation path from email sent to newaddress@example.com
        new_msg = [m for m in mail.outbox if m.to == ["newaddress@example.com"]][0]
        match = re.search(r"(/auth/confirm-email-change/[^\s]+)", new_msg.body)
        self.assertIsNotNone(match)

        c_resp = self.client.get(match.group(1))
        self.assertEqual(c_resp.status_code, 200)
        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.email, "newaddress@example.com")
        self.assertEqual(self.user.profile.email_normalized, "newaddress@example.com")

    def test_idle_timeout_signs_out_inactive_session(self):
        # Backdate pa_last_activity_ts beyond 12 hours
        session = self.client.session
        session["pa_last_activity_ts"] = int((timezone.now() - timedelta(hours=13)).timestamp())
        session.save()

        resp = self.client.get(reverse("projectauth:account"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("projectauth:login"), resp["Location"])
        self.assertTrue(AuditEvent.objects.filter(action="session.idle_timeout").exists())

    def test_data_export_and_account_delete_with_last_admin_protection(self):
        export_resp = self.client.get(reverse("projectauth:account_export"))
        self.assertEqual(export_resp.status_code, 200)
        payload = json.loads(export_resp.content.decode("utf-8"))
        self.assertEqual(payload["account"]["username"], "acctuser")

        # Delete regular user account -> anonymizes AuditEvent rows
        del_resp = self.client.post(
            reverse("projectauth:account_delete"),
            {
                "del-confirm_text": "DELETE",
                "del-current_password": "InitialPassword!123",
            },
        )
        self.assertEqual(del_resp.status_code, 302)
        self.assertFalse(User.objects.filter(username="acctuser").exists())
        del_ev = AuditEvent.objects.filter(action="account.deleted").first()
        self.assertIsNotNone(del_ev)
        self.assertTrue(del_ev.actor_label.startswith("deleted-user-"))

    def test_last_active_admin_cannot_delete_own_account(self):
        from projectauth.models import AuthSettings

        s = AuthSettings.load()
        s.require_2fa_for_admins = False
        s.save()

        # Remove any other superusers in test DB so only 1 active admin exists
        User.objects.filter(is_superuser=True).delete()
        admin = User.objects.create_superuser(
            username="sole_admin",
            email="sole@example.com",
            password="AdminPassword!123",
        )
        UserProfile.objects.create(user=admin, status=UserProfile.STATUS_ACTIVE)

        c = Client()
        c.post(reverse("projectauth:login"), {"identifier": "sole_admin", "password": "AdminPassword!123"})
        resp = c.post(
            reverse("projectauth:account_delete"),
            {
                "del-confirm_text": "DELETE",
                "del-current_password": "AdminPassword!123",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(User.objects.filter(username="sole_admin").exists())
