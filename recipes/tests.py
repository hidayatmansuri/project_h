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
            created_on=date(2026, 10, 4))

    def test_pages_render(self):
        urls = [
            reverse("recipes:index"),
            reverse("recipes:recipes"),
            reverse("recipes:recipe_detail", args=[self.recipe.slug]),
            reverse("recipes:category", args=[self.cat.slug]),
            reverse("recipes:cuisine", args=[self.cus.slug]),
            reverse("recipes:quick"),
            reverse("recipes:slow"),
            reverse("recipes:login"),
            reverse("recipes:signup"),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                content = response.content.decode()
                self.assertNotIn("{%", content)
                self.assertNotIn("{{", content)

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


class EditorAreaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user("editor", "e@example.com", "pass12345!", is_staff=True)
        cls.visitor = User.objects.create_user("visitor", "v@example.com", "pass12345!")
        cls.cat = Category.objects.create(name="Vegan")
        cls.cus = Cuisine.objects.create(name="Chinese Cuisine")

    def test_anonymous_and_non_staff_are_blocked(self):
        url = reverse("recipes:manage")
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.visitor)
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_staff_can_open_dashboard(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("recipes:manage")).status_code, 200)

    def test_create_recipe_with_dynamic_rows_and_upload(self):
        self.client.force_login(self.staff)
        with tempfile.TemporaryDirectory() as media:
            with override_settings(MEDIA_ROOT=media):
                response = self.client.post(reverse("recipes:recipe_create"), {
                    "name": "Tofu Stir-Fry", "category": self.cat.pk, "cuisine": self.cus.pk,
                    "ingredient[]": ["tofu", "", "basil"], "method[]": ["Fry", "Serve"],
                    "created_on": "Oct 24, 2026", "prep_time": "5", "cook_time": "12",
                    "image_file": SimpleUploadedFile("tofu.gif", TINY_GIF, content_type="image/gif"),
                })
                self.assertRedirects(response, reverse("recipes:manage"))
                recipe = Recipe.objects.get(name="Tofu Stir-Fry")
                self.assertEqual(recipe.ingredients, ["tofu", "basil"])
                self.assertEqual(recipe.methods, ["Fry", "Serve"])
                self.assertEqual(recipe.created_on, date(2026, 10, 24))
                self.assertEqual(recipe.cook_time, 12)
                self.assertTrue(recipe.image_url)
                self.assertEqual(RecipeImage.objects.count(), 1)

    def test_edit_keeps_image_when_nothing_chosen(self):
        self.client.force_login(self.staff)
        with tempfile.TemporaryDirectory() as media:
            with override_settings(MEDIA_ROOT=media):
                image = RecipeImage.objects.create(
                    title="t", image=SimpleUploadedFile("t.gif", TINY_GIF, content_type="image/gif"))
                recipe = Recipe.objects.create(name="Soup", image=image, category=self.cat)
                self.client.post(reverse("recipes:recipe_edit", args=[recipe.pk]), {
                    "name": "Soup v2", "category": self.cat.pk, "prep_time": "1", "cook_time": "2",
                    "ingredient[]": ["water"], "method[]": ["Boil"],
                })
                recipe.refresh_from_db()
                self.assertEqual(recipe.name, "Soup v2")
                self.assertEqual(recipe.image_id, image.pk)

    def test_delete_requires_post(self):
        self.client.force_login(self.staff)
        recipe = Recipe.objects.create(name="Gone")
        url = reverse("recipes:recipe_delete", args=[recipe.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertTrue(Recipe.objects.filter(pk=recipe.pk).exists())
        self.client.post(url)
        self.assertFalse(Recipe.objects.filter(pk=recipe.pk).exists())

    def test_category_and_cuisine_crud(self):
        self.client.force_login(self.staff)
        self.client.post(reverse("recipes:category_create"), {"name": "Dessert"})
        self.client.post(reverse("recipes:cuisine_create"), {"name": "French Cuisine"})
        self.assertTrue(Category.objects.filter(name="Dessert").exists())
        self.assertTrue(Cuisine.objects.filter(name="French Cuisine").exists())
        category = Category.objects.get(name="Dessert")
        self.client.post(reverse("recipes:category_edit", args=[category.pk]), {
            "name": "Desserts", "icon": "fa-birthday-cake", "tagline": "Sweet", "accent": "pork"})
        category.refresh_from_db()
        self.assertEqual(category.name, "Desserts")
        self.client.post(reverse("recipes:category_delete", args=[category.pk]))
        self.assertFalse(Category.objects.filter(pk=category.pk).exists())

    def test_embedded_admin_redirect_with_next(self):
        self.client.force_login(self.staff)
        next_target = reverse("recipes:index") + "#admin-section"
        response = self.client.post(reverse("recipes:category_create"), {
            "name": "Keto",
            "next": next_target,
        })
        self.assertRedirects(response, next_target)
        self.assertTrue(Category.objects.filter(name="Keto").exists())

    def test_logout_is_post_only(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("recipes:logout")).status_code, 405)
        self.client.post(reverse("recipes:logout"))
        self.assertEqual(self.client.get(reverse("recipes:manage")).status_code, 302)

    def test_signup_creates_non_staff_user(self):
        self.client.post(reverse("recipes:signup"), {
            "username": "newbie", "email": "n@example.com",
            "password1": "Str0ng-pass-123", "password2": "Str0ng-pass-123"})
        user = User.objects.get(username="newbie")
        self.assertFalse(user.is_staff)


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
