"""
Phase 1 Foundation unit and integration tests:
- Crypto (AES-256-GCM round-trip, tamper detection, AAD binding, key rotation, missing key in prod, HMAC-SHA256)
- Models, constraints, ProtectedApp sync, AuthSettings singleton, legacy migration logic
- Audit logging & secret scrubbing
- Database Throttle helper
- Email wrapper & daily email budget guard + projectauth_email_test command
"""

from __future__ import annotations

import base64
import importlib
import io
import secrets
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError
from django.test import TestCase, override_settings

from projectauth.audit import log_audit
from projectauth.crypto import (
    CryptoError,
    compare_hmac,
    decrypt,
    decrypt_str,
    encrypt,
    get_active_key_id,
    hmac_sha256,
    needs_reencryption,
    normalize_identifier,
)
from projectauth.email_service import get_daily_email_status, send_projectauth_email
from projectauth.models import (
    AppAccess,
    AuditEvent,
    AuthSettings,
    ProtectedApp,
    TOTPDevice,
    UserProfile,
)
from projectauth.registry import sync_protected_apps
from projectauth.throttling import (
    check_and_increment_throttle,
    is_throttled,
    reset_throttle,
)

User = get_user_model()


def _make_b64_key() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")


class CryptoTests(TestCase):
    def setUp(self):
        self.k0 = _make_b64_key()
        self.k1 = _make_b64_key()

    def test_encrypt_decrypt_roundtrip_str_and_bytes(self):
        keys = f"kid1:{self.k1},kid0:{self.k0}"
        with override_settings(PROJECTAUTH_ENCRYPTION_KEYS=keys):
            aad = b"totp:42"
            ct = encrypt("JBSWY3DPEHPK3PXP", aad=aad)
            self.assertTrue(ct.startswith("v1:kid1:"))
            self.assertEqual(decrypt_str(ct, aad=aad), "JBSWY3DPEHPK3PXP")

            raw_bytes = b"\x00\x01\xfe\xffsecret-bytes"
            ct_b = encrypt(raw_bytes, aad=aad)
            self.assertEqual(decrypt(ct_b, aad=aad), raw_bytes)

    def test_tamper_detection_and_aad_mismatch(self):
        keys = f"kid1:{self.k1}"
        with override_settings(PROJECTAUTH_ENCRYPTION_KEYS=keys):
            aad = b"totp:100"
            ct = encrypt("SUPERSECRETBASE32", aad=aad)

            # Wrong AAD must fail authentication
            with self.assertRaises(CryptoError):
                decrypt(ct, aad=b"totp:101")

            # Tamper with ciphertext payload
            parts = ct.split(":")
            raw_ct = bytearray(base64.urlsafe_b64decode(parts[3].encode("ascii")))
            raw_ct[-1] ^= 0xFF
            parts[3] = base64.urlsafe_b64encode(bytes(raw_ct)).decode("ascii")
            tampered_ct = ":".join(parts)
            with self.assertRaises(CryptoError):
                decrypt(tampered_ct, aad=aad)

            # Tamper with nonce
            parts_n = ct.split(":")
            raw_nonce = bytearray(base64.urlsafe_b64decode(parts_n[2].encode("ascii")))
            raw_nonce[0] ^= 0x01
            parts_n[2] = base64.urlsafe_b64encode(bytes(raw_nonce)).decode("ascii")
            with self.assertRaises(CryptoError):
                decrypt(":".join(parts_n), aad=aad)

    def test_key_rotation_decrypts_old_and_reencrypts_to_new(self):
        aad = b"totp:7"
        with override_settings(PROJECTAUTH_ENCRYPTION_KEYS=f"kid0:{self.k0}"):
            old_ct = encrypt("MYTOTPSECRET", aad=aad)
            self.assertEqual(get_active_key_id(), "kid0")
            self.assertFalse(needs_reencryption(old_ct))

        # Rotate: kid1 is now first (active), kid0 is second
        with override_settings(PROJECTAUTH_ENCRYPTION_KEYS=f"kid1:{self.k1},kid0:{self.k0}"):
            self.assertEqual(get_active_key_id(), "kid1")
            self.assertTrue(needs_reencryption(old_ct))
            pt = decrypt_str(old_ct, aad=aad)
            self.assertEqual(pt, "MYTOTPSECRET")

            new_ct = encrypt(pt, aad=aad)
            self.assertTrue(new_ct.startswith("v1:kid1:"))
            self.assertFalse(needs_reencryption(new_ct))
            self.assertEqual(decrypt_str(new_ct, aad=aad), "MYTOTPSECRET")

    def test_missing_key_in_production_raises_improperly_configured(self):
        with override_settings(DEBUG=False, PROJECTAUTH_ENCRYPTION_KEYS=""):
            with self.assertRaises(ImproperlyConfigured):
                encrypt("secret", aad=b"totp:1")

    def test_hmac_sha256_domain_separation_and_constant_time_compare(self):
        h1 = hmac_sha256("otp_login", "123456")
        h2 = hmac_sha256("otp_reauth", "123456")
        self.assertNotEqual(h1, h2)
        self.assertTrue(compare_hmac("otp_login", "123456", h1))
        self.assertFalse(compare_hmac("otp_login", "654321", h1))
        self.assertFalse(compare_hmac("otp_reauth", "123456", h1))

    def test_normalize_identifier_nfkc_and_lowercase(self):
        # Fullwidth Latin 'Ａｌｉｃｅ＠Ｅｘａｍｐｌｅ．ｃｏｍ' normalizes to 'alice@example.com'
        self.assertEqual(
            normalize_identifier("  Ａｌｉｃｅ＠Ｅｘａｍｐｌｅ．ｃｏｍ "),
            "alice@example.com",
        )


class ModelsAndRegistryTests(TestCase):
    def test_protected_apps_synced_and_public_apps_locked(self):
        sync_protected_apps()
        home_app = ProtectedApp.objects.get(app_label="home")
        cv_app = ProtectedApp.objects.get(app_label="cv")
        self.assertTrue(home_app.is_public)
        self.assertTrue(cv_app.is_public)

        # Attempting to make 'home' non-public via DB save must stay locked True
        home_app.is_public = False
        home_app.save()
        home_app.refresh_from_db()
        self.assertTrue(home_app.is_public)

        # Non-public apps are restricted and cannot be flipped to public via DB save
        for label in ("passgen", "utilitytracker", "shades", "docedit", "listimage", "recipes"):
            app_obj = ProtectedApp.objects.get(app_label=label)
            self.assertFalse(app_obj.is_public)
            app_obj.is_public = True
            app_obj.save()
            app_obj.refresh_from_db()
            self.assertFalse(app_obj.is_public)

    def test_user_profile_case_insensitive_uniqueness_and_totp_encryption(self):
        from django.db import transaction

        u1 = User.objects.create_user(username="AliceUser", email="Alice@Example.com", password="Password123!@#")
        p1 = UserProfile.objects.create(user=u1, status=UserProfile.STATUS_ACTIVE)
        self.assertEqual(p1.username_normalized, "aliceuser")
        self.assertEqual(p1.email_normalized, "alice@example.com")

        u2 = User.objects.create_user(username="BobUser", email="ALICE@example.com", password="Password123!@#")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                UserProfile.objects.create(user=u2, status=UserProfile.STATUS_ACTIVE)

        dev = TOTPDevice(user=u1, name="Phone")
        dev.set_secret("JBSWY3DPEHPK3PXP")
        dev.save()
        self.assertNotIn("JBSWY3DPEHPK3PXP", dev.secret_encrypted)
        self.assertEqual(dev.get_secret(), "JBSWY3DPEHPK3PXP")

    def test_auth_settings_singleton(self):
        s1 = AuthSettings.load()
        s2 = AuthSettings.load()
        self.assertEqual(s1.pk, 1)
        self.assertEqual(s2.pk, 1)
        self.assertTrue(s1.require_2fa_for_admins)

    def test_legacy_data_migration_forwards_and_backwards(self):
        import types
        from django.apps import apps as django_apps
        from django.db import connection

        legacy_mod = importlib.import_module("projectauth.migrations.0002_legacy_data_migration")
        su = User.objects.create_superuser(username="legacy_admin", email="admin@legacy.local", password="Password123!@#")
        regular = User.objects.create_user(username="legacy_user", email="user@legacy.local", password="Password123!@#")

        fake_editor = types.SimpleNamespace(connection=connection)
        legacy_mod.forwards(django_apps, fake_editor)

        su_prof = UserProfile.objects.get(user=su)
        reg_prof = UserProfile.objects.get(user=regular)
        self.assertEqual(su_prof.status, "active")
        self.assertEqual(su_prof.created_via, "legacy")
        self.assertEqual(reg_prof.status, "active")
        self.assertEqual(reg_prof.created_via, "legacy")
        self.assertEqual(AppAccess.objects.filter(user=regular).count(), 0)

        legacy_mod.backwards(django_apps, fake_editor)

        self.assertFalse(UserProfile.objects.filter(user=su).exists())
        self.assertFalse(UserProfile.objects.filter(user=regular).exists())


class AuditAndThrottleTests(TestCase):
    def test_audit_scrubs_secrets(self):
        ev = log_audit(
            "login.failure",
            details={
                "username": "alice",
                "password": "SuperSecretPassword!",
                "otp_code": "123456",
                "reason": "bad_credentials",
            },
        )
        self.assertEqual(ev.details.get("username"), "alice")
        self.assertEqual(ev.details.get("reason"), "bad_credentials")
        self.assertNotIn("password", ev.details)
        self.assertNotIn("otp_code", ev.details)

    def test_database_throttle_increment_and_lockout(self):
        scope = "test_email_send"
        key = "user@example.com"
        reset_throttle(scope, key)

        ok1, _ = check_and_increment_throttle(scope, key, limit=2, window_seconds=300, lockout_seconds=600)
        ok2, _ = check_and_increment_throttle(scope, key, limit=2, window_seconds=300, lockout_seconds=600)
        ok3, retry = check_and_increment_throttle(scope, key, limit=2, window_seconds=300, lockout_seconds=600)

        self.assertTrue(ok1)
        self.assertTrue(ok2)
        self.assertFalse(ok3)
        self.assertGreater(retry, 0)

        throttled, _ = is_throttled(scope, key, limit=2, window_seconds=300)
        self.assertTrue(throttled)


class EmailBudgetAndCommandTests(TestCase):
    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        PROJECTAUTH_MAX_EMAILS_PER_DAY=5,
    )
    def test_daily_email_budget_guard_and_80_percent_warning(self):
        for i in range(4):
            res = send_projectauth_email(
                "verify_email",
                [f"user{i}@example.com"],
                context={"username": f"user{i}", "action_url": "http://127.0.0.1:8000/auth/verify/abc"},
            )
            self.assertTrue(res["sent"])

        status_4 = get_daily_email_status()
        self.assertEqual(status_4["sent_today"], 4)
        self.assertTrue(status_4["warning_80"])
        self.assertFalse(status_4["exhausted"])

        # 5th email reaches cap
        res5 = send_projectauth_email("verify_email", ["user5@example.com"])
        self.assertTrue(res5["sent"])

        # 6th email exceeds daily cap and is blocked
        res6 = send_projectauth_email("verify_email", ["user6@example.com"])
        self.assertFalse(res6["sent"])
        self.assertEqual(res6["reason"], "budget_exceeded")
        self.assertEqual(len(mail.outbox), 5)
        self.assertTrue(AuditEvent.objects.filter(action="email.budget_exceeded").exists())

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_smtp_exception_is_caught_and_audited_without_secrets(self):
        with patch("django.core.mail.EmailMultiAlternatives.send", side_effect=RuntimeError("SMTP password xyz failed")):
            res = send_projectauth_email(
                "password_reset",
                ["alice@example.com"],
                context={"token": "secret-reset-token-123"},
                fail_silently=True,
            )
            self.assertFalse(res["sent"])
            self.assertEqual(res["reason"], "smtp_error")
            ev = AuditEvent.objects.filter(action="email.send_error").first()
            self.assertIsNotNone(ev)
            self.assertNotIn("secret-reset-token-123", str(ev.details))

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    def test_projectauth_email_test_command_produces_console_output(self):
        out = io.StringIO()
        with patch("sys.stdout", new=io.StringIO()) as fake_console:
            call_command("projectauth_email_test", "admin@example.com", stdout=out)
            console_output = fake_console.getvalue()
        cmd_output = out.getvalue()
        self.assertIn("Test email dispatched successfully to admin@example.com", cmd_output)
        self.assertIn("To: admin@example.com", console_output)
