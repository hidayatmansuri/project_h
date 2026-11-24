from django.test import TestCase
from django.urls import reverse


class PassGenViewTests(TestCase):
    def setUp(self):
        from projectauth.test_helpers import grant_test_client_app_access

        grant_test_client_app_access(self.client, "passgen")

    def test_passgen_get_renders_defaults_with_no_store_header(self):
        response = self.client.get(reverse("passgen"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "passgen.html")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response.context["length"], 12)

    def test_passgen_requires_at_least_one_pool(self):
        response = self.client.post(reverse("passgen"), {"length": "12"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["error_message"])
        self.assertEqual(response.context["password"], "")

    def test_passgen_random_password_respects_length_bounds(self):
        response = self.client.post(
            reverse("passgen"),
            {"length": "20", "upper": "on", "lower": "on", "numbs": "on", "symbols": "on"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["password"]), 20)

        too_short = self.client.post(
            reverse("passgen"),
            {"length": "1", "lower": "on"},
        )
        self.assertEqual(too_short.context["length"], 4)
        self.assertEqual(len(too_short.context["password"]), 4)

    def test_passgen_desired_word_is_padded_to_requested_length(self):
        response = self.client.post(
            reverse("passgen"),
            {
                "length": "16",
                "upper": "on",
                "lower": "on",
                "numbs": "on",
                "symbols": "on",
                "desired": "hello",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["password"]), 16)
