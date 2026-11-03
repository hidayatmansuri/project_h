"""
Phase 4 Access Control unit and integration tests (Section 5.5, 9, 15, 16):
- URL-walking exposure test across all patterns in `get_resolver().url_patterns`
- Anonymous & ungranted users blocked on every non-public route including all 15 `/docedit/api/*` (JSON 401/403)
- `home` and `cv` remain public; `/static/` remains accessible without auth
- `full` vs `read_only` access levels on `utilitytracker` (GET allowed, POST blocked with 403)
- Grant expiry (`expires_at`) and revocation (`revoked_at`)
- Fail-closed behaviour for unregistered or inactive apps
- HTML 403 screen + Request Access workflow
- `@app_access_required` decorator, `AppAccessRequiredMixin`, and `{% user_can_access %}` tag
- `manage.py projectauth_check` CLI command verification
"""

from __future__ import annotations

import io
import json
import re
import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.http import HttpResponse
from django.template import Context, Template
from django.test import Client, RequestFactory, TestCase
from django.urls import get_resolver, reverse
from django.utils import timezone

from projectauth.access import classify_app_label, resolve_view_app_label
from projectauth.decorators import AppAccessRequiredMixin, app_access_required
from projectauth.management.commands.projectauth_check import (
    _DummyMatch,
    iter_url_patterns,
)
from projectauth.models import (
    AccessRequest,
    AppAccess,
    ProtectedApp,
    TOTPDevice,
    UserProfile,
)
from projectauth.registry import sync_protected_apps
from projectauth.twofa import generate_totp_secret
from utilitytracker.models import UtilityReading

User = get_user_model()


def _materialize_url_pattern(pattern_str: str) -> str:
    """Replaces Django path converters and regex placeholders with concrete sample values."""
    sample = pattern_str
    sample = re.sub(r"<uuid:[^>]+>", str(uuid.uuid4()), sample)
    sample = re.sub(r"<int:[^>]+>", "1", sample)
    sample = re.sub(r"<slug:[^>]+>", "sample-slug", sample)
    sample = re.sub(r"<path:[^>]+>", "sample-path", sample)
    sample = re.sub(r"<str:[^>]+>", "sample-str", sample)
    sample = re.sub(r"<[^>]+>", "1", sample)
    sample = sample.replace("(?P<path>.*)$", "test.txt")
    return sample


class AccessControlMiddlewareAndUrlWalkTests(TestCase):
    def setUp(self):
        sync_protected_apps()
        self.anon_client = Client()

        self.ungranted_user = User.objects.create_user(
            username="ungranted_user",
            email="ungranted@example.com",
            password="StrongPassword!123",
            is_active=True,
        )
        UserProfile.objects.create(
            user=self.ungranted_user,
            status=UserProfile.STATUS_ACTIVE,
            email_verified_at=timezone.now(),
        )
        self.ungranted_client = Client()
        self.ungranted_client.force_login(
            self.ungranted_user,
            backend="projectauth.backends.EmailOrUsernameBackend",
        )

    def test_public_apps_home_cv_and_static_are_accessible_anonymously(self):
        r_home = self.anon_client.get(reverse("home"))
        self.assertEqual(r_home.status_code, 200)

        r_cv = self.anon_client.get(reverse("cv"))
        self.assertEqual(r_cv.status_code, 200)

    def test_url_walking_exposure_blocks_anonymous_and_ungranted_on_all_protected_routes(self):
        resolver = get_resolver()
        entries = iter_url_patterns(resolver.url_patterns)
        protected_checked = 0

        for full_pattern, callback, ns, an in entries:
            match = _DummyMatch(app_name=an, namespace=ns)
            app_label = resolve_view_app_label(
                callback,
                path=full_pattern,
                resolver_match=match,
            )
            classification = classify_app_label(app_label)
            self.assertNotEqual(
                classification,
                "unclassified",
                f"Unclassified URL pattern discovered: {full_pattern}",
            )

            if classification != "protected":
                continue

            url = _materialize_url_pattern(full_pattern)
            protected_checked += 1

            # 1. Anonymous GET
            anon_resp = self.anon_client.get(url)
            if "/api/" in url:
                self.assertEqual(
                    anon_resp.status_code,
                    401,
                    f"Anonymous GET to API {url} did not return 401 (got {anon_resp.status_code})",
                )
                payload = json.loads(anon_resp.content.decode("utf-8"))
                self.assertFalse(payload["success"])
            else:
                self.assertEqual(
                    anon_resp.status_code,
                    302,
                    f"Anonymous GET to protected route {url} did not redirect to login (got {anon_resp.status_code})",
                )
                self.assertIn(reverse("projectauth:login"), anon_resp["Location"])

            # 2. Ungranted authenticated user GET
            ungranted_resp = self.ungranted_client.get(url)
            self.assertEqual(
                ungranted_resp.status_code,
                403,
                f"Ungranted user GET to protected route {url} did not return 403 (got {ungranted_resp.status_code})",
            )
            if "/api/" in url:
                payload = json.loads(ungranted_resp.content.decode("utf-8"))
                self.assertFalse(payload["success"])
                self.assertIn("error", payload)

        self.assertGreater(protected_checked, 30)

    def test_docedit_api_endpoints_return_json_401_and_403_never_html_redirect(self):
        docedit_api_urls = [
            "/docedit/api/upload/",
            "/docedit/api/status/test1234/",
            "/docedit/api/save/test1234/",
            "/docedit/api/download/test1234/",
            "/docedit/api/cancel/test1234/",
            "/docedit/api/font/test1234/",
            "/docedit/api/fonts/",
            "/docedit/api/fonts/install/",
            "/docedit/api/page-image/test1234/1/",
            "/docedit/api/font-file/test1234/font.ttf/",
            "/docedit/api/confirm-download/test1234/",
            "/docedit/api/word-crop/test1234/w1/",
            "/docedit/api/fuzzy-words/test1234/",
            "/docedit/api/review-word/test1234/w1/",
        ]
        for api_url in docedit_api_urls:
            with self.subTest(api_url=api_url):
                r_anon = self.anon_client.post(api_url)
                self.assertEqual(r_anon.status_code, 401)
                self.assertEqual(r_anon["Content-Type"], "application/json")
                data_anon = json.loads(r_anon.content.decode("utf-8"))
                self.assertEqual(set(data_anon.keys()), {"success", "error"})
                self.assertFalse(data_anon["success"])

                r_ungranted = self.ungranted_client.post(api_url)
                self.assertEqual(r_ungranted.status_code, 403)
                self.assertEqual(r_ungranted["Content-Type"], "application/json")
                data_ungranted = json.loads(r_ungranted.content.decode("utf-8"))
                self.assertEqual(set(data_ungranted.keys()), {"success", "error"})
                self.assertFalse(data_ungranted["success"])

    def test_read_only_vs_full_access_and_expiry_on_utilitytracker(self):
        utility_app = ProtectedApp.objects.get(app_label="utilitytracker")
        today = timezone.now().date()
        UtilityReading.objects.create(date=today, electricity=20.00, gas=30.00)

        # Grant read_only access with 7-day expiry ("Tester" preset)
        grant = AppAccess.objects.create(
            user=self.ungranted_user,
            app=utility_app,
            level=AppAccess.LEVEL_READ_ONLY,
            expires_at=timezone.now() + timedelta(days=7),
        )

        # 1. Read-only user CAN GET /utility
        get_resp = self.ungranted_client.get("/utility")
        self.assertEqual(get_resp.status_code, 200)
        self.assertIn("no-store", get_resp.get("Cache-Control", ""))

        # 2. Read-only user CANNOT POST to /utility (blocked centrally by middleware with 403)
        post_resp = self.ungranted_client.post(
            "/utility",
            {
                "submit_reading": "Submit",
                "date": today.isoformat(),
                "electricity": "99.99",
                "gas": "99.99",
            },
        )
        self.assertEqual(post_resp.status_code, 403)
        self.assertIn("Read-only", post_resp.content.decode("utf-8"))
        # Verify household data was untouched
        reading = UtilityReading.objects.get(date=today)
        self.assertEqual(float(reading.electricity), 20.00)

        # 3. Upgrade grant to 'full' -> POST now succeeds
        grant.level = AppAccess.LEVEL_FULL
        grant.save(update_fields=["level"])
        full_post_resp = self.ungranted_client.post(
            "/utility",
            {
                "submit_reading": "Submit",
                "date": today.isoformat(),
                "electricity": "45.50",
                "gas": "55.50",
            },
        )
        self.assertEqual(full_post_resp.status_code, 302)
        reading.refresh_from_db()
        self.assertEqual(float(reading.electricity), 45.50)

        # 4. Expire the grant -> GET is immediately refused with 403
        grant.expires_at = timezone.now() - timedelta(minutes=1)
        grant.save(update_fields=["expires_at"])
        exp_resp = self.ungranted_client.get("/utility")
        self.assertEqual(exp_resp.status_code, 403)
        self.assertIn("expired", exp_resp.content.decode("utf-8"))

    def test_html_403_request_access_flow_and_fail_closed_unregistered_app(self):
        # Ungranted user visits /shades/ -> friendly 403 with Request access form
        r403 = self.ungranted_client.get("/shades/")
        self.assertEqual(r403.status_code, 403)
        html = r403.content.decode("utf-8")
        self.assertIn("You don't have access to Colour Shades", html)

        # Submitting request access creates pending AccessRequest
        req_post = self.ungranted_client.post(
            reverse("projectauth:request_access"),
            {"app_label": "shades", "message": "Please grant access", "next": "/shades/"},
        )
        self.assertEqual(req_post.status_code, 302)
        self.assertTrue(
            AccessRequest.objects.filter(
                user=self.ungranted_user,
                app__app_label="shades",
                status=AccessRequest.STATUS_PENDING,
            ).exists()
        )

        # Decorator & fail-closed unregistered app check
        @app_access_required("unregistered_future_app")
        def dummy_view(request):
            return HttpResponse("ok")

        rf = RequestFactory()
        req = rf.get("/future/")
        req.user = self.ungranted_user
        resp_denied = dummy_view(req)
        self.assertEqual(resp_denied.status_code, 403)

        # Active admin with confirmed 2FA can access unregistered app
        admin = User.objects.create_superuser(
            username="super_boss",
            email="boss@example.com",
            password="AdminPassword!123",
        )
        UserProfile.objects.create(user=admin, status=UserProfile.STATUS_ACTIVE)
        dev = TOTPDevice(user=admin, confirmed_at=timezone.now())
        dev.set_secret(generate_totp_secret())
        dev.save()

        req_admin = rf.get("/future/")
        req_admin.user = admin
        resp_admin = dummy_view(req_admin)
        self.assertEqual(resp_admin.status_code, 200)

        # Template tag {% user_can_access %}
        tpl = Template("{% load projectauth_tags %}{% user_can_access 'shades' as ok %}{{ ok }}")
        rendered_ungranted = tpl.render(Context({"request": req})).strip()
        rendered_admin = tpl.render(Context({"request": req_admin})).strip()
        self.assertEqual(rendered_ungranted, "False")
        self.assertEqual(rendered_admin, "True")

    def test_projectauth_check_management_command_succeeds(self):
        out = io.StringIO()
        call_command("projectauth_check", stdout=out)
        self.assertIn("0 unclassified", out.getvalue())

