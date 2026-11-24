from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from utilitytracker.models import UtilityReading


class HomeViewTests(TestCase):
    def test_home_renders_publicly_without_readings(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home.html")
        self.assertIsNone(response.context["electricity"])
        self.assertIsNone(response.context["gas"])
        self.assertContains(response, 'lang="en"')

    def test_home_displays_latest_electricity_and_gas_readings(self):
        UtilityReading.objects.create(
            date=date(2026, 1, 1),
            electricity=Decimal("10.00"),
            gas=Decimal("5.00"),
        )
        UtilityReading.objects.create(
            date=date(2026, 2, 1),
            electricity=Decimal("42.50"),
            gas=Decimal("19.75"),
        )
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["electricity"].electricity, Decimal("42.50"))
        self.assertEqual(response.context["gas"].gas, Decimal("19.75"))
        self.assertContains(response, "42.50")
        self.assertContains(response, "19.75")
