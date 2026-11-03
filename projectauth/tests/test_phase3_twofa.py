"""
Phase 3 Two-Factor Authentication unit and integration tests:
- TOTP setup with inline SVG QR, AES-256-GCM secret storage, +/-1 step window, and replay protection
- Pre-auth session isolation (password alone does not log in when 2FA applies)
- Email 6-digit OTP (HMAC storage, 10-minute expiry, 5-attempt cap)
- 10 Crockford Base32 recovery codes (shown once, HMAC storage, single-use consumption)
- 30-day trusted device cookie + revocation
- Mandatory admin 2FA policy enforcement (admin-must-enrol on login, cannot disable)
- Sudo re-authentication (10-minute window) for sensitive actions
- Break-glass CLI command `projectauth_reset_2fa`
- Static & runtime verification that NO phone/SMS field or dependency exists anywhere in projectauth
"""

from __future__ import annotations

import io
import re
import time
from datetime import timedelta
from pathlib import Path

import pyotp
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from projectauth import twofa
from projectauth.models import (
    AuditEvent,
    AuthSettings,
    CodeChallenge,
    RecoveryCode,
    TOTPDevice,
    TrustedDevice,
    UserProfile,
)
from projectauth.registry import sync_protected_apps

User = get_user_model()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class TwoFactorAuthenticationTests(TestCase):
    def setUp(self):
        sync_protected_apps()
        self.client = Client()
        self.user = User.objects.create_user(
            username="twofa_user",
            email="twofa_user@example.com",
            password="StrongPassword!123",
            is_active=True,
        )
        UserProfile.objects.create(
            user=self.user,
            status=UserProfile.STATUS_ACTIVE,
            email_verified_at=timezone.now(),
        )

    def test_totp_setup_inline_svg_qr_and_recovery_codes_shown_once(self):
        # Log in as regular user (2FA optional initially)
        self.client.post(
            reverse("projectauth:login"),
            {"identifier": "twofa_user", "password": "StrongPassword!123"},
        )
        setup_get = self.client.get(reverse("projectauth:twofa_setup"))
        self.assertEqual(setup_get.status_code, 200)
        html = setup_get.content.decode("utf-8")
        self.assertIn("<svg", html)
        self.assertIn("pa-qr-svg", html)

        pending_dev = TOTPDevice.objects.get(user=self.user, confirmed_at__isnull=True)
        secret = pending_dev.get_secret()
        totp = pyotp.TOTP(secret)

        # Confirm enrolment with valid TOTP code
        confirm_resp = self.client.post(
            reverse("projectauth:twofa_setup"),
            {"setup_action": "confirm_totp", "code": totp.now()},
            follow=True,
        )
        self.assertEqual(confirm_resp.status_code, 200)
        pending_dev.refresh_from_db()
        self.assertIsNotNone(pending_dev.confirmed_at)

        # Recovery codes are displayed ONCE on the redirected recovery page
        rec_html_1 = confirm_resp.content.decode("utf-8")
        self.assertIn("paRecoveryCodeList", rec_html_1)
        codes_found = re.findall(r"<code>([0-9A-Z]{4}-[0-9A-Z]{4})</code>", rec_html_1)
        self.assertEqual(len(codes_found), 10)

        # Reloading the recovery page does NOT show the plaintext codes again
        rec_resp_2 = self.client.get(reverse("projectauth:twofa_recovery"))
        rec_html_2 = rec_resp_2.content.decode("utf-8")
        self.assertNotIn("paRecoveryCodeList", rec_html_2)
        for c in codes_found:
            self.assertNotIn(c, rec_html_2)

    def test_totp_replay_protection_and_step_window(self):
        dev = TOTPDevice(user=self.user, name="AuthApp", confirmed_at=timezone.now())
        secret = twofa.generate_totp_secret()
        dev.set_secret(secret)
        dev.save()

        totp = pyotp.TOTP(secret)
        fixed_ts = 1_700_000_000.0
        code_now = totp.at(int(fixed_ts))

        # 1st verification at fixed_ts succeeds
        self.assertTrue(twofa.verify_totp_code(dev, code_now, now_timestamp=fixed_ts))
        # Replay of the exact same code at fixed_ts (or earlier step) MUST fail
        self.assertFalse(twofa.verify_totp_code(dev, code_now, now_timestamp=fixed_ts))
        self.assertFalse(
            twofa.verify_totp_code(dev, totp.at(int(fixed_ts - 30)), now_timestamp=fixed_ts)
        )

        # Next time step (+30s) succeeds within +/-1 window
        code_next = totp.at(int(fixed_ts + 30))
        self.assertTrue(twofa.verify_totp_code(dev, code_next, now_timestamp=fixed_ts))
        # Replaying code_next again fails
        self.assertFalse(twofa.verify_totp_code(dev, code_next, now_timestamp=fixed_ts + 30))

        # Code outside +/-1 step (+90s) fails
        code_far = totp.at(int(fixed_ts + 90))
        self.assertFalse(twofa.verify_totp_code(dev, code_far, now_timestamp=fixed_ts))

    def test_email_otp_expiry_and_5_attempt_limit(self):
        # Enable TOTP on user so login interposes 2FA
        dev = TOTPDevice(user=self.user, confirmed_at=timezone.now())
        dev.set_secret(twofa.generate_totp_secret())
        dev.save()

        # Password login stops at pre-auth state (not logged in yet)
        login_resp = self.client.post(
            reverse("projectauth:login"),
            {"identifier": "twofa_user", "password": "StrongPassword!123"},
        )
        self.assertEqual(login_resp.status_code, 302)
        self.assertEqual(login_resp["Location"], reverse("projectauth:twofa_challenge"))
        self.assertNotIn("_auth_user_id", self.client.session)

        # Request email OTP
        mail.outbox.clear()
        self.client.post(
            reverse("projectauth:twofa_challenge"),
            {"challenge_action": "send_email_code"},
        )
        self.assertEqual(len(mail.outbox), 1)
        m = re.search(r"\b(\d{6})\b", mail.outbox[0].body)
        self.assertIsNotNone(m)
        real_code = m.group(1)

        # Ensure raw code is NEVER stored in DB
        challenge = CodeChallenge.objects.filter(
            user=self.user, purpose=CodeChallenge.PURPOSE_LOGIN_2FA
        ).first()
        self.assertNotEqual(challenge.code_hmac, real_code)

        # 5 wrong attempts exhaust the challenge
        for _ in range(5):
            self.assertFalse(
                twofa.verify_email_otp_challenge(
                    self.user, "000000", purpose=CodeChallenge.PURPOSE_LOGIN_2FA
                )
            )
        # 6th attempt with the REAL code must now fail because attempts == 5
        self.assertFalse(
            twofa.verify_email_otp_challenge(
                self.user, real_code, purpose=CodeChallenge.PURPOSE_LOGIN_2FA
            )
        )

        # Issue a second email code and expire it -> must fail
        twofa.send_email_otp_challenge(self.user, purpose=CodeChallenge.PURPOSE_LOGIN_2FA)
        m2 = re.search(r"\b(\d{6})\b", mail.outbox[-1].body)
        code2 = m2.group(1)
        CodeChallenge.objects.filter(
            user=self.user, purpose=CodeChallenge.PURPOSE_LOGIN_2FA
        ).update(expires_at=timezone.now() - timedelta(seconds=10))
        self.assertFalse(
            twofa.verify_email_otp_challenge(
                self.user, code2, purpose=CodeChallenge.PURPOSE_LOGIN_2FA
            )
        )

    def test_recovery_code_single_use_and_trusted_device_30_days(self):
        dev = TOTPDevice(user=self.user, confirmed_at=timezone.now())
        dev.set_secret(twofa.generate_totp_secret())
        dev.save()
        codes = twofa.generate_recovery_codes_for_user(self.user)
        first_code = codes[0]

        # Login + verify with recovery code AND check "Trust this device for 30 days"
        self.client.post(
            reverse("projectauth:login"),
            {"identifier": "twofa_user", "password": "StrongPassword!123"},
        )
        ch_resp = self.client.post(
            reverse("projectauth:twofa_challenge"),
            {
                "challenge_action": "verify",
                "code": first_code,
                "trust_device": "on",
            },
        )
        self.assertEqual(ch_resp.status_code, 302)
        self.assertEqual(ch_resp["Location"], reverse("home"))
        self.assertIn("_auth_user_id", self.client.session)
        self.assertIn(twofa.TRUSTED_DEVICE_COOKIE_NAME, self.client.cookies)

        # Recovery code is now consumed (single-use)
        self.assertFalse(twofa.verify_and_consume_recovery_code(self.user, first_code))

        # Log out, then log back in on the same client -> trusted device skips 2FA challenge!
        self.client.post(reverse("projectauth:logout"))
        login2 = self.client.post(
            reverse("projectauth:login"),
            {"identifier": "twofa_user", "password": "StrongPassword!123"},
        )
        self.assertEqual(login2.status_code, 302)
        self.assertEqual(login2["Location"], reverse("home"))
        self.assertIn("_auth_user_id", self.client.session)

    def test_admin_must_enrol_2fa_by_default_and_cannot_disable(self):
        admin = User.objects.create_superuser(
            username="enrol_admin",
            email="enrol_admin@example.com",
            password="AdminPassword!123",
        )
        UserProfile.objects.create(user=admin, status=UserProfile.STATUS_ACTIVE)

        c = Client()
        r = c.post(
            reverse("projectauth:login"),
            {"identifier": "enrol_admin", "password": "AdminPassword!123"},
        )
        # Admin without 2FA is NOT logged in yet; sent directly to 2FA setup
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], reverse("projectauth:twofa_setup"))
        self.assertNotIn("_auth_user_id", c.session)

        # Complete setup on /auth/2fa/setup/
        c.get(reverse("projectauth:twofa_setup"))
        pending_dev = TOTPDevice.objects.get(user=admin, confirmed_at__isnull=True)
        totp = pyotp.TOTP(pending_dev.get_secret())
        c.post(
            reverse("projectauth:twofa_setup"),
            {"setup_action": "confirm_totp", "code": totp.now()},
        )
        self.assertIn("_auth_user_id", c.session)

        # Admin attempting to disable 2FA is refused by policy
        c.post(reverse("projectauth:twofa_setup"), {"setup_action": "disable_2fa"})
        self.assertTrue(twofa.user_has_confirmed_totp(admin))

    def test_sudo_reauth_required_for_sensitive_2fa_actions_and_cli_reset(self):
        dev = TOTPDevice(user=self.user, confirmed_at=timezone.now())
        secret = twofa.generate_totp_secret()
        dev.set_secret(secret)
        dev.save()
        totp = pyotp.TOTP(secret)

        # Sign in with password + TOTP
        self.client.post(
            reverse("projectauth:login"),
            {"identifier": "twofa_user", "password": "StrongPassword!123"},
        )
        self.client.post(
            reverse("projectauth:twofa_challenge"),
            {"challenge_action": "verify", "code": totp.at(int(time.time() - 30))},
        )

        # Without sudo mode, regenerating recovery codes redirects to /auth/reauth/
        regen_resp = self.client.post(reverse("projectauth:twofa_recovery"))
        self.assertEqual(regen_resp.status_code, 302)
        self.assertIn(reverse("projectauth:reauth"), regen_resp["Location"])

        # Complete reauth with password + current TOTP code
        reauth_resp = self.client.post(
            reverse("projectauth:reauth"),
            {
                "reauth_action": "verify",
                "password": "StrongPassword!123",
                "code": totp.now(),
                "next": reverse("projectauth:twofa_recovery"),
            },
        )
        self.assertEqual(reauth_resp.status_code, 302)

        # Now regenerating recovery codes succeeds within 10-minute sudo window
        regen_ok = self.client.post(reverse("projectauth:twofa_recovery"))
        self.assertEqual(regen_ok.status_code, 302)
        self.assertEqual(RecoveryCode.objects.filter(user=self.user, used_at__isnull=True).count(), 10)

        # Break-glass CLI command resets 2FA and audits twofa.cli_reset
        out = io.StringIO()
        call_command("projectauth_reset_2fa", "twofa_user", stdout=out)
        self.assertIn("2FA reset complete", out.getvalue())
        self.assertFalse(twofa.user_has_confirmed_totp(self.user))
        self.assertTrue(
            AuditEvent.objects.filter(action="twofa.cli_reset", target_user=self.user).exists()
        )

    def test_no_phone_or_sms_code_or_field_exists_anywhere(self):
        # 1. Inspect all fields on all projectauth models
        pa_config = apps.get_app_config("projectauth")
        for model in pa_config.get_models():
            for field in model._meta.get_fields():
                fname = field.name.lower()
                self.assertNotIn("phone", fname, f"Forbidden phone field on {model.__name__}.{field.name}")
                self.assertNotIn("sms", fname, f"Forbidden sms field on {model.__name__}.{field.name}")
                self.assertNotIn("mobile", fname, f"Forbidden mobile field on {model.__name__}.{field.name}")

        # 2. Inspect requirements.txt for forbidden SMS/phone/CAPTCHA libraries
        req_path = Path(__file__).resolve().parent.parent.parent / "requirements.txt"
        req_text = req_path.read_text(encoding="utf-8").lower()
        for forbidden_pkg in ("twilio", "phonenumbers", "vonage", "plivo", "recaptcha", "hcaptcha"):
            self.assertNotIn(forbidden_pkg, req_text)

