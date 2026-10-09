from django.test import TestCase, Client
from django.urls import reverse, resolve
from shades.views import shades


class ShadesViewTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_shades_url_resolves(self):
        match = resolve('/shades/')
        self.assertEqual(match.func, shades)

    def test_shades_view_status_code(self):
        response = self.client.get(reverse('shades'))
        self.assertEqual(response.status_code, 200)

    def test_shades_view_template(self):
        response = self.client.get(reverse('shades'))
        self.assertTemplateUsed(response, 'shades.html')
        self.assertTemplateUsed(response, 'home.html')

    def test_shades_contains_hex_and_rgb_and_bounds(self):
        response = self.client.get(reverse('shades'))
        content = response.content.decode('utf-8')
        self.assertIn('#000000', content)
        self.assertIn('#FFFFFF', content)
        self.assertIn('rgb(0, 0, 0)', content)
        self.assertIn('rgb(255, 255, 255)', content)
        self.assertIn('shade-color-square', content)
        self.assertIn('shade-info-square', content)
