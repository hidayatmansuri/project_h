"""
Phase 7 tests: Integration (docedit ownership, utilitytracker read-only tester,
recipes login/signup redirect) and Pre-approved Hardenings (settings, passgen,
docedit PDF header/filename/session cap/font checks, theme-toggle.js null guards).
"""
import io
import json
import os
import shutil
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from docedit import storage as docedit_storage
from projectauth.models import AppAccess, ProtectedApp, UserProfile
from projectauth.registry import sync_protected_apps
from utilitytracker.models import TopUp, UtilityReading


MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n"
    b"0000000052 00000 n \n0000000101 00000 n \n"
    b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n164\n%%EOF\n"
)


class Phase7IntegrationAndHardeningTests(TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="phase7_docedit_")
        self.user_a = User.objects.create_user(
            username="alice7",
            email="alice7@example.com",
            password="StrongPassword!1234",
            is_active=True,
        )
        UserProfile.objects.create(
            user=self.user_a,
            status=UserProfile.STATUS_ACTIVE,
            email_verified_at=timezone.now(),
        )

        self.user_b = User.objects.create_user(
            username="bob7",
            email="bob7@example.com",
            password="StrongPassword!1234",
            is_active=True,
        )
        UserProfile.objects.create(
            user=self.user_b,
            status=UserProfile.STATUS_ACTIVE,
            email_verified_at=timezone.now(),
        )

        sync_protected_apps()
        self.docedit_app = ProtectedApp.objects.get(app_label="docedit")
        self.utility_app = ProtectedApp.objects.get(app_label="utilitytracker")
        self.passgen_app = ProtectedApp.objects.get(app_label="passgen")
        self.recipes_app = ProtectedApp.objects.get(app_label="recipes")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # ------------------------------------------------------------------ 7.1(a) docedit ownership
    def test_docedit_ownership_survives_session_key_rotation_and_blocks_other_users(self):
        AppAccess.objects.create(user=self.user_a, app=self.docedit_app, level="full")
        AppAccess.objects.create(user=self.user_b, app=self.docedit_app, level="full")

        with override_settings(DOCEDIT_WORK_DIR=self.tmp_dir, DOCEDIT_SYNC_PROCESSING=True):
            self.client.force_login(self.user_a, backend="projectauth.backends.EmailOrUsernameBackend")
            old_session_key = self.client.session.session_key

            pdf_file = SimpleUploadedFile("invoice../2026.pdf", MINIMAL_PDF, content_type="application/pdf")
            resp = self.client.post(reverse("docedit_upload"), {"document": pdf_file})
            self.assertEqual(resp.status_code, 200)
            sid = resp.json()["session_id"]

            meta = docedit_storage.get_session_meta(sid)
            self.assertEqual(meta["owner_key"], f"user:{self.user_a.pk}")
            self.assertNotIn("..", meta["original_filename"])

            # Rotate session key (as happens on re-auth or password change)
            s = self.client.session
            s.cycle_key()
            s.save()
            self.client.cookies[settings.SESSION_COOKIE_NAME] = s.session_key
            self.assertNotEqual(self.client.session.session_key, old_session_key)

            # User A still has access after session key rotation
            status_resp = self.client.get(reverse("docedit_status", args=[sid]))
            self.assertEqual(status_resp.status_code, 200)
            self.assertTrue(status_resp.json()["success"])

            # User B is denied access to User A's document (403)
            self.client.force_login(self.user_b, backend="projectauth.backends.EmailOrUsernameBackend")
            bob_resp = self.client.get(reverse("docedit_status", args=[sid]))
            self.assertEqual(bob_resp.status_code, 403)
            self.assertFalse(bob_resp.json()["success"])

    # ------------------------------------------------------------------ 7.3(3) docedit hardenings
    def test_docedit_rejects_non_pdf_magic_bytes_and_enforces_session_cap(self):
        AppAccess.objects.create(user=self.user_a, app=self.docedit_app, level="full")
        self.client.force_login(self.user_a, backend="projectauth.backends.EmailOrUsernameBackend")

        with override_settings(
            DOCEDIT_WORK_DIR=self.tmp_dir,
            DOCEDIT_SYNC_PROCESSING=True,
            DOCEDIT_MAX_ACTIVE_SESSIONS_PER_USER=2,
        ):
            # Fake PDF with .pdf extension but non-PDF content
            fake_pdf = SimpleUploadedFile("fake.pdf", b"NOT_A_PDF_HEADER_AT_ALL", content_type="application/pdf")
            r_fake = self.client.post(reverse("docedit_upload"), {"document": fake_pdf})
            self.assertEqual(r_fake.status_code, 400)
            self.assertIn("header", r_fake.json()["error"].lower())

            # Session cap = 2: first two uploads succeed, third returns 429
            for i in range(2):
                f = SimpleUploadedFile(f"doc{i}.pdf", MINIMAL_PDF, content_type="application/pdf")
                r = self.client.post(reverse("docedit_upload"), {"document": f})
                self.assertEqual(r.status_code, 200)

            f3 = SimpleUploadedFile("doc3.pdf", MINIMAL_PDF, content_type="application/pdf")
            r3 = self.client.post(reverse("docedit_upload"), {"document": f3})
            self.assertEqual(r3.status_code, 429)
            self.assertIn("limit", r3.json()["error"].lower())

            # Font upload with invalid magic bytes is rejected
            bad_font = SimpleUploadedFile("evil.ttf", b"MZ\x90\x00not_a_font", content_type="font/ttf")
            r_font = self.client.post(reverse("docedit_font_install"), {"font_file": bad_font})
            self.assertEqual(r_font.status_code, 400)
            self.assertIn("header", r_font.json()["error"].lower())

    # ------------------------------------------------------------------ 7.1(b) utilitytracker read-only tester
    def test_utilitytracker_read_only_and_expiring_grant_blocks_all_mutations(self):
        # Seed a reading and a top-up
        reading = UtilityReading.objects.create(
            date=date(2026, 3, 1),
            electricity=Decimal("100.00"),
            gas=Decimal("50.00"),
        )
        topup = TopUp.objects.create(
            meter="electricity",
            amount=Decimal("25.00"),
            date=timezone.now(),
        )

        # Grant read_only access with future expiry to User A
        grant = AppAccess.objects.create(
            user=self.user_a,
            app=self.utility_app,
            level="read_only",
            expires_at=timezone.now() + timedelta(hours=2),
        )
        self.client.force_login(self.user_a, backend="projectauth.backends.EmailOrUsernameBackend")

        # GET succeeds and displays household data
        r_get = self.client.get(reverse("utility"))
        self.assertEqual(r_get.status_code, 200)

        # POST submit_reading is blocked (403) and does not create/modify readings
        r_post_reading = self.client.post(
            reverse("utility"),
            {
                "submit_reading": "1",
                "date": "2026-03-02",
                "electricity": "120.00",
                "gas": "60.00",
            },
        )
        self.assertEqual(r_post_reading.status_code, 403)
        self.assertEqual(UtilityReading.objects.count(), 1)

        # POST submit_topup is blocked (403)
        r_post_topup = self.client.post(
            reverse("utility"),
            {
                "submit_topup": "1",
                "utility_type": "gas",
                "amount": "40.00",
                "date": "2026-03-02",
            },
        )
        self.assertEqual(r_post_topup.status_code, 403)
        self.assertEqual(TopUp.objects.count(), 1)

        # POST delete_topup is blocked (403) and topup still exists
        r_del_topup = self.client.post(
            reverse("utility"),
            {"delete_topup": "1", "topup_id": str(topup.id)},
        )
        self.assertEqual(r_del_topup.status_code, 403)
        self.assertTrue(TopUp.objects.filter(pk=topup.id).exists())

        # Once grant expires, even GET is blocked (403)
        grant.expires_at = timezone.now() - timedelta(minutes=1)
        grant.save()
        r_expired = self.client.get(reverse("utility"))
        self.assertEqual(r_expired.status_code, 403)

    # ------------------------------------------------------------------ 7.1(c) recipes login/signup alignment
    def test_recipes_login_and_signup_redirect_to_projectauth(self):
        AppAccess.objects.create(user=self.user_a, app=self.recipes_app, level="full")
        self.client.force_login(self.user_a, backend="projectauth.backends.EmailOrUsernameBackend")

        self.assertFalse(settings.RECIPES_ALLOW_SIGNUP)
        self.assertFalse(getattr(settings, "SIMASRECIPES_ALLOW_SIGNUP", True))

        r_login = self.client.get(reverse("recipes:login"))
        self.assertEqual(r_login.status_code, 302)
        self.assertTrue(r_login["Location"].startswith(reverse("projectauth:login")))

        r_signup = self.client.get(reverse("recipes:signup"))
        self.assertEqual(r_signup.status_code, 302)
        self.assertEqual(r_signup["Location"], reverse("projectauth:signup"))

    # ------------------------------------------------------------------ 7.3(4) passgen hardenings
    def test_passgen_sets_no_store_cache_header_and_clamps_length(self):
        AppAccess.objects.create(user=self.user_a, app=self.passgen_app, level="full")
        self.client.force_login(self.user_a, backend="projectauth.backends.EmailOrUsernameBackend")

        r = self.client.post(
            reverse("passgen"),
            {"length": "999999", "upper": "on", "lower": "on", "numbs": "on", "symbols": "on"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("no-store", r["Cache-Control"])
        self.assertEqual(r.context["length"], 128)
        self.assertEqual(len(r.context["password"]), 128)

    # ------------------------------------------------------------------ 7.3(1,2,5) settings, gitignore, theme-toggle.js
    def test_settings_logging_static_root_and_theme_toggle_null_guards(self):
        self.assertTrue(hasattr(settings, "STATIC_ROOT"))
        self.assertIn("projectauth.security", settings.LOGGING.get("loggers", {}))

        gitignore_text = (Path(settings.BASE_DIR) / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("staticfiles/", gitignore_text)
        self.assertIn("*.sqlite3", gitignore_text)

        theme_js = (Path(settings.BASE_DIR) / "static" / "js" / "theme-toggle.js").read_text(encoding="utf-8")
        self.assertIn("if (toggleCheckbox)", theme_js)
        self.assertIn("if (backToTop)", theme_js)

