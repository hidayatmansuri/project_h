import tempfile
from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Category, ChatMessage, Cuisine, Recipe, RecipeImage

User = get_user_model()

# A 1x1 transparent GIF so ImageField validation (Pillow) accepts it.
TINY_GIF = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00"
            b",\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;")


class ModelTests(TestCase):
    def test_slugs_are_unique_and_stable(self):
        a = Recipe.objects.create(name="Chicken Biryani")
        b = Recipe.objects.create(name="Chicken Biryani")
        self.assertEqual(a.slug, "chicken-biryani")
        self.assertEqual(b.slug, "chicken-biryani-2")
        a.name = "Renamed"
        a.save()
        self.assertEqual(Recipe.objects.get(pk=a.pk).slug, "chicken-biryani")

    def test_cuisine_label(self):
        self.assertEqual(Cuisine(name="French Cuisine").label, "French")
        self.assertEqual(Cuisine(name="South Asian Cuisine", short_name="S. Asian").label, "S. Asian")

    def test_time_helpers(self):
        recipe = Recipe(name="x", prep_time=1, cook_time=30)
        self.assertEqual(recipe.prep_display, "1 min")
        self.assertEqual(recipe.cook_display, "30 mins")
        self.assertTrue(recipe.is_quick)
        self.assertFalse(Recipe(name="y", cook_time=31).is_quick)

    def test_recipe_passcode_british_6_digit_format(self):
        r_with_date = Recipe(name="Curry", created_on=date(2026, 2, 12))
        self.assertEqual(r_with_date.passcode, "120226")
        r_without_date = Recipe(name="No Date")
        self.assertEqual(r_without_date.passcode, "000000")

    def test_deleting_category_keeps_recipes(self):
        cat = Category.objects.create(name="Beef")
        recipe = Recipe.objects.create(name="Stew", category=cat)
        cat.delete()
        recipe.refresh_from_db()
        self.assertIsNone(recipe.category)


class PublicViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cat = Category.objects.create(name="Sea Food", icon="fa-fish", accent="seafood")
        cls.cus = Cuisine.objects.create(name="South Asian Cuisine", short_name="S. Asian")
        cls.recipe = Recipe.objects.create(
            name="Prawn Curry", category=cls.cat, cuisine=cls.cus,
            ingredients=["prawns", "coconut milk"], methods=["Simmer"], prep_time=10, cook_time=25,
            created_on=date(2026, 2, 12))

    def test_pages_render_and_use_british_date_format(self):
        urls = [
            reverse("recipes:index"),
            reverse("recipes:recipes"),
            reverse("recipes:recipe_detail", args=[self.recipe.slug]),
            reverse("recipes:category", args=[self.cat.slug]),
            reverse("recipes:cuisine", args=[self.cus.slug]),
            reverse("recipes:quick"),
            reverse("recipes:slow"),
            reverse("recipes:manage"),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                content = response.content.decode()
                self.assertNotIn("{%", content)
                self.assertNotIn("{{", content)

        detail_html = self.client.get(reverse("recipes:recipe_detail", args=[self.recipe.slug])).content.decode()
        self.assertIn("12 Feb 2026", detail_html)
        self.assertIn("12/02/2026", detail_html)

    def test_quick_and_slow_split(self):
        Recipe.objects.create(name="Slow roast", cook_time=120)
        self.assertContains(self.client.get(reverse("recipes:quick")), "Prawn Curry")
        self.assertNotContains(self.client.get(reverse("recipes:quick")), "Slow roast")
        self.assertContains(self.client.get(reverse("recipes:slow")), "Slow roast")

    def test_unknown_recipe_redirects(self):
        response = self.client.get(reverse("recipes:recipe_detail", args=["nope"]))
        self.assertRedirects(response, reverse("recipes:recipes"))

    def test_recipe_detail_by_numeric_id(self):
        response = self.client.get(reverse("recipes:recipe_detail", args=[str(self.recipe.pk)]))
        self.assertEqual(response.status_code, 200)


class PasscodeProtectedCrudTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cat = Category.objects.create(name="Vegan")
        cls.cus = Cuisine.objects.create(name="Chinese Cuisine")

    def test_no_login_required_for_manage_and_edit_pages(self):
        self.assertEqual(self.client.get(reverse("recipes:manage")).status_code, 200)
        recipe = Recipe.objects.create(name="Test Dish", created_on=date(2026, 2, 12))
        self.assertEqual(self.client.get(reverse("recipes:recipe_edit", args=[recipe.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("recipes:category_edit", args=[self.cat.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("recipes:cuisine_edit", args=[self.cus.pk])).status_code, 200)

    def test_create_recipe_with_british_date_and_000000_passcode(self):
        with tempfile.TemporaryDirectory() as media:
            with override_settings(MEDIA_ROOT=media):
                # Wrong passcode is rejected
                self.client.post(reverse("recipes:recipe_create"), {
                    "name": "Blocked Recipe", "category": self.cat.pk, "cuisine": self.cus.pk,
                    "created_on": "12 Feb 2026", "prep_time": "5", "cook_time": "12",
                    "passcode": "999999",
                })
                self.assertFalse(Recipe.objects.filter(name="Blocked Recipe").exists())

                # Correct '000000' passcode succeeds without login
                response = self.client.post(reverse("recipes:recipe_create"), {
                    "name": "Tofu Stir-Fry", "category": self.cat.pk, "cuisine": self.cus.pk,
                    "ingredient[]": ["tofu", "", "basil"], "method[]": ["Fry", "Serve"],
                    "created_on": "12 Feb 2026", "prep_time": "5", "cook_time": "12",
                    "passcode": "000000",
                    "image_file": SimpleUploadedFile("tofu.gif", TINY_GIF, content_type="image/gif"),
                })
                self.assertRedirects(response, reverse("recipes:manage"))
                recipe = Recipe.objects.get(name="Tofu Stir-Fry")
                self.assertEqual(recipe.ingredients, ["tofu", "basil"])
                self.assertEqual(recipe.methods, ["Fry", "Serve"])
                self.assertEqual(recipe.created_on, date(2026, 2, 12))
                self.assertEqual(recipe.passcode, "120226")
                self.assertEqual(recipe.cook_time, 12)
                self.assertTrue(recipe.image_url)

    def test_edit_and_delete_recipe_require_6_digit_creation_date_passcode(self):
        recipe = Recipe.objects.create(
            name="Lamb Tagine", category=self.cat, created_on=date(2026, 2, 12), prep_time=15, cook_time=45
        )
        # Wrong passcode ('000000' when recipe has creation date 12 Feb 2026 -> '120226') is rejected
        self.client.post(reverse("recipes:recipe_edit", args=[recipe.pk]), {
            "name": "Hacked Name", "category": self.cat.pk, "prep_time": "15", "cook_time": "45",
            "created_on": "12/02/2026", "passcode": "000000",
        })
        recipe.refresh_from_db()
        self.assertEqual(recipe.name, "Lamb Tagine")

        # Correct 6-digit creation date passcode ('120226') updates the recipe
        self.client.post(reverse("recipes:recipe_edit", args=[recipe.pk]), {
            "name": "Fruity Lamb Tagine", "category": self.cat.pk, "prep_time": "20", "cook_time": "50",
            "created_on": "12/02/2026", "ingredient[]": ["lamb"], "method[]": ["Slow cook"],
            "passcode": "120226",
        })
        recipe.refresh_from_db()
        self.assertEqual(recipe.name, "Fruity Lamb Tagine")

        # Delete with wrong passcode is rejected
        self.client.post(reverse("recipes:recipe_delete", args=[recipe.pk]), {"passcode": "000000"})
        self.assertTrue(Recipe.objects.filter(pk=recipe.pk).exists())

        # Delete with correct 6-digit creation date passcode ('120226') succeeds
        self.client.post(reverse("recipes:recipe_delete", args=[recipe.pk]), {"passcode": "120226"})
        self.assertFalse(Recipe.objects.filter(pk=recipe.pk).exists())

    def test_edit_keeps_image_when_nothing_chosen(self):
        with tempfile.TemporaryDirectory() as media:
            with override_settings(MEDIA_ROOT=media):
                image = RecipeImage.objects.create(
                    title="t", image=SimpleUploadedFile("t.gif", TINY_GIF, content_type="image/gif"))
                recipe = Recipe.objects.create(name="Soup", image=image, category=self.cat)
                self.client.post(reverse("recipes:recipe_edit", args=[recipe.pk]), {
                    "name": "Soup v2", "category": self.cat.pk, "prep_time": "1", "cook_time": "2",
                    "ingredient[]": ["water"], "method[]": ["Boil"],
                    "passcode": "000000",
                })
                recipe.refresh_from_db()
                self.assertEqual(recipe.name, "Soup v2")
                self.assertEqual(recipe.image_id, image.pk)

    def test_category_and_cuisine_crud_require_000000_passcode(self):
        # Blocked without '000000'
        self.client.post(reverse("recipes:category_create"), {"name": "Dessert", "passcode": "123456"})
        self.assertFalse(Category.objects.filter(name="Dessert").exists())

        # Allowed with '000000'
        self.client.post(reverse("recipes:category_create"), {"name": "Dessert", "passcode": "000000"})
        self.client.post(reverse("recipes:cuisine_create"), {"name": "French Cuisine", "passcode": "000000"})
        self.assertTrue(Category.objects.filter(name="Dessert").exists())
        self.assertTrue(Cuisine.objects.filter(name="French Cuisine").exists())

        category = Category.objects.get(name="Dessert")
        self.client.post(reverse("recipes:category_edit", args=[category.pk]), {
            "name": "Desserts", "icon": "fa-birthday-cake", "tagline": "Sweet", "accent": "pork",
            "passcode": "000000",
        })
        category.refresh_from_db()
        self.assertEqual(category.name, "Desserts")

        # Delete blocked with wrong passcode, allowed with '000000'
        self.client.post(reverse("recipes:category_delete", args=[category.pk]), {"passcode": "111111"})
        self.assertTrue(Category.objects.filter(pk=category.pk).exists())
        self.client.post(reverse("recipes:category_delete", args=[category.pk]), {"passcode": "000000"})
        self.assertFalse(Category.objects.filter(pk=category.pk).exists())

    def test_embedded_admin_redirect_with_next(self):
        next_target = reverse("recipes:index") + "#admin-section"
        response = self.client.post(reverse("recipes:category_create"), {
            "name": "Keto",
            "passcode": "000000",
            "next": next_target,
        })
        self.assertRedirects(response, next_target)
        self.assertTrue(Category.objects.filter(name="Keto").exists())


class ImportCommandTests(TestCase):
    def test_import_bundled_data_is_repeatable(self):
        with tempfile.TemporaryDirectory() as media:
            with override_settings(MEDIA_ROOT=media):
                call_command("import_recipes", verbosity=0)
                first = (Recipe.objects.count(), Category.objects.count(), Cuisine.objects.count())
                call_command("import_recipes", verbosity=0)
                second = (Recipe.objects.count(), Category.objects.count(), Cuisine.objects.count())
        self.assertEqual(first, second)
        self.assertEqual(first[0], 9)
        recipe = Recipe.objects.get(slug="chicken-biryani")
        self.assertEqual((recipe.prep_time, recipe.cook_time), (30, 35))
        self.assertEqual(len(recipe.ingredients), 9)
        self.assertTrue(recipe.image_url)
