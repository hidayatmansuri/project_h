"""
Phase 6 tests: Header Control (`{% projectauth_nav %}`), Mobile-First CSS/JS Constraints (C3, C6),
and Email Templates (Section 3, 6, 11, 14, 15, 16).
"""

from __future__ import annotations

import pathlib
import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from projectauth.email_service import send_projectauth_email
from projectauth.models import AccessRequest, ProtectedApp, TOTPDevice, UserProfile

User = get_user_model()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class Phase6UiAndHeaderTests(TestCase):
    def test_header_nav_control_logged_out_regular_user_and_admin_with_pending_badge(self):
        client = Client()

        # 1. Logged out on home page
        resp_anon = client.get(reverse("home"))
        self.assertEqual(resp_anon.status_code, 200)
        html_anon = resp_anon.content.decode("utf-8")
        self.assertIn('href="/auth/login/?next=/"', html_anon)
        self.assertIn("fa-right-to-bracket", html_anon)
        self.assertNotIn("Admin console", html_anon)

        # Verify exact placement: pa-nav-control appears immediately before the separator preceding theme-toggle-label
        nav_idx = html_anon.find("pa-nav-control")
        theme_idx = html_anon.find('class="theme-toggle-label"')
        self.assertGreater(nav_idx, 0)
        self.assertGreater(theme_idx, nav_idx)

        # 2. Logged in as regular active user
        reg_user = User.objects.create_user(
            username="alice_ui",
            email="alice_ui@example.com",
            password="AliceUiPass!234",
            is_active=True,
        )
        UserProfile.objects.create(
            user=reg_user,
            status=UserProfile.STATUS_ACTIVE,
            username_normalized="alice_ui",
            email_normalized="alice_ui@example.com",
            email_verified_at=timezone.now(),
        )
        client.force_login(reg_user, backend="projectauth.backends.EmailOrUsernameBackend")
        resp_user = client.get(reverse("home"))
        html_user = resp_user.content.decode("utf-8")
        self.assertIn("alice_ui", html_user)
        self.assertIn(reverse("projectauth:account"), html_user)
        self.assertIn(reverse("projectauth:twofa_setup"), html_user)
        self.assertIn(f'action="{reverse("projectauth:logout")}"', html_user)
        self.assertNotIn("Admin console", html_user)

        # 3. Logged in as Admin with pending user + pending access request -> badge shown
        admin_user = User.objects.create_user(
            username="admin_ui",
            email="admin_ui@example.com",
            password="AdminUiPass!234",
            is_superuser=True,
            is_staff=True,
            is_active=True,
        )
        UserProfile.objects.create(
            user=admin_user,
            status=UserProfile.STATUS_ACTIVE,
            username_normalized="admin_ui",
            email_normalized="admin_ui@example.com",
            email_verified_at=timezone.now(),
        )
        dev = TOTPDevice(user=admin_user, name="AuthApp", confirmed_at=timezone.now())
        dev.set_secret("JBSWY3DPEHPK3PXP")
        dev.save()

        # Create a pending user and a pending access request
        pending_u = User.objects.create_user(
            username="pending_bob",
            email="bob@example.com",
            password="BobPending!234",
            is_active=False,
        )
        UserProfile.objects.create(
            user=pending_u,
            status=UserProfile.STATUS_PENDING_APPROVAL,
            username_normalized="pending_bob",
            email_normalized="bob@example.com",
        )
        app_obj = ProtectedApp.objects.get(app_label="passgen")
        AccessRequest.objects.create(
            user=reg_user,
            app=app_obj,
            status=AccessRequest.STATUS_PENDING,
        )

        client.force_login(admin_user, backend="projectauth.backends.EmailOrUsernameBackend")
        s = client.session
        s["pa_2fa_verified"] = True
        s.save()

        resp_admin = client.get(reverse("home"))
        html_admin = resp_admin.content.decode("utf-8")
        self.assertIn("Admin console", html_admin)
        self.assertIn(reverse("projectauth:console_dashboard"), html_admin)
        self.assertIn("pa-nav-badge", html_admin)

    def test_mobile_first_css_and_no_app_static_folder_constraints(self):
        base_dir = pathlib.Path(settings.BASE_DIR)

        # Constraint C3: No static folder inside projectauth/
        app_static = base_dir / "projectauth" / "static"
        self.assertFalse(
            app_static.exists(),
            "Constraint C3 violated: projectauth/static/ must not exist.",
        )

        css_path = base_dir / "static" / "css" / "projectauth.css"
        js_path = base_dir / "static" / "js" / "projectauth.js"
        home_css_path = base_dir / "static" / "css" / "home-style.css"

        self.assertTrue(css_path.is_file())
        self.assertTrue(js_path.is_file())

        css_text = css_path.read_text(encoding="utf-8")
        js_text = js_path.read_text(encoding="utf-8")
        home_css_text = home_css_path.read_text(encoding="utf-8")

        # Constraint C6: Never write max-width media queries in projectauth.css or home-style.css
        css_no_comments = re.sub(r"/\*.*?\*/", "", css_text, flags=re.S)
        media_queries = re.findall(r"@media[^{]+", css_no_comments)
        for mq in media_queries:
            self.assertNotIn(
                "max-width",
                mq.lower(),
                f"Constraint C6 violated: max-width media query found: {mq}",
            )

        home_no_comments = re.sub(r"/\*.*?\*/", "", home_css_text, flags=re.S)
        home_media_queries = re.findall(r"@media[^{]+", home_no_comments)
        for mq in home_media_queries:
            self.assertNotIn(
                "max-width",
                mq.lower(),
                f"Constraint C6 violated in home-style.css: {mq}",
            )

        # Check required mobile-first tiers, 16px input font-size, 44px touch target, dvh fallback
        self.assertIn("@media (min-width: 768px)", css_text)
        self.assertIn("@media (min-width: 1200px)", css_text)
        self.assertIn("font-size: 16px", css_text)
        self.assertIn("min-height: 44px", css_text)
        self.assertIn("dvh", css_text)

        # Check JS uses crypto.getRandomValues and exact special charset `!£$%^&*+#~@`
        self.assertIn("crypto.getRandomValues", js_text)
        self.assertIn("!£$%^&*+#~@", js_text)

    def test_all_18_required_email_templates_exist_and_render_without_secrets_in_subject(self):
        required_templates = [
            "verify_email",
            "already_registered_notice",
            "account_approved",
            "account_rejected",
            "password_reset",
            "password_changed",
            "username_reminder",
            "email_change_confirm_new",
            "email_change_notice_old",
            "new_device_login",
            "twofa_enabled",
            "twofa_disabled",
            "admin_invite",
            "admin_new_signup",
            "access_granted",
            "access_denied",
            "access_revoked",
            "account_deleted",
        ]
        emails_dir = (
            pathlib.Path(settings.BASE_DIR)
            / "projectauth"
            / "templates"
            / "projectauth_emails"
        )
        for tpl in required_templates:
            self.assertTrue((emails_dir / f"{tpl}.txt").is_file(), f"Missing {tpl}.txt")
            self.assertTrue((emails_dir / f"{tpl}.html").is_file(), f"Missing {tpl}.html")

        mail.outbox.clear()
        secret_token = "SECRET_TOKEN_XYZ_987654"
        res = send_projectauth_email(
            "password_reset",
            ["check@example.com"],
            context={
                "username": "alice",
                "action_url": f"http://127.0.0.1:8000/auth/reset/{secret_token}/",
                "expires_minutes": 60,
            },
        )
        self.assertTrue(res["sent"])
        self.assertEqual(len(mail.outbox), 1)
        sent_msg = mail.outbox[0]
        self.assertNotIn(secret_token, sent_msg.subject)
        self.assertIn(secret_token, sent_msg.body)
        self.assertIn("wasn't you", sent_msg.body)
        self.assertEqual(len(sent_msg.alternatives), 1)
        self.assertEqual(sent_msg.alternatives[0][1], "text/html")
