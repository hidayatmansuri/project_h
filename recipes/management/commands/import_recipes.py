r"""
Import the data from the ORIGINAL Flask app (SQLite) into the Django models.

    python manage.py import_recipes                  # uses the copy bundled in recipes/legacy/
    python manage.py import_recipes --sqlite D:\recipes\data\recipes.db --images D:\recipes\static\img

Safe to run more than once: rows are matched by name / slug and updated, not duplicated.
Flask users and their password hashes are intentionally NOT imported.
"""
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from recipes import legacy
from recipes.models import Category, Cuisine, Recipe, RecipeImage

APP_DIR = Path(__file__).resolve().parents[2]


class Command(BaseCommand):
    help = "Import categories, cuisines, images and recipes from the old Flask SQLite database."

    def add_arguments(self, parser):
        parser.add_argument("--sqlite", default=str(APP_DIR / "legacy" / "recipes.db"),
                            help="Path to the Flask recipes.db file")
        parser.add_argument("--images", default=str(APP_DIR / "legacy" / "img"),
                            help="Folder holding the Flask static/img files")
        parser.add_argument("--dry-run", action="store_true",
                            help="Read and report only; write nothing")

    def handle(self, *args, **options):
        sqlite_path = Path(options["sqlite"])
        images_dir = Path(options["images"])
        if not sqlite_path.is_file():
            raise CommandError(f"SQLite file not found: {sqlite_path}")

        data = legacy.read_legacy_database(sqlite_path)
        self.stdout.write(
            f"Found {len(data['categories'])} categories, {len(data['cuisines'])} cuisines, "
            f"{len(data['library'])} library images, {len(data['recipes'])} recipes."
        )
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run: nothing written."))
            return

        with transaction.atomic():
            categories = self._import_categories(data["categories"] + [r["category"] for r in data["recipes"]])
            cuisines = self._import_cuisines(data["cuisines"] + [r["cuisine"] for r in data["recipes"]])
            images = self._import_images(images_dir, data)
            created = updated = 0
            for item in data["recipes"]:
                if not item["name"]:
                    continue
                recipe = Recipe.objects.filter(slug=item["slug"]).first() if item["slug"] else None
                recipe = recipe or Recipe.objects.filter(name__iexact=item["name"]).first()
                is_new = recipe is None
                recipe = recipe or Recipe(name=item["name"])
                recipe.name = item["name"]
                if is_new and item["slug"]:
                    recipe.slug = item["slug"]
                recipe.category = categories.get(item["category"])
                recipe.cuisine = cuisines.get(item["cuisine"])
                recipe.image = images.get(item["image"])
                recipe.ingredients = item["ingredients"]
                recipe.methods = item["methods"]
                recipe.prep_time = item["prep_time"]
                recipe.cook_time = item["cook_time"]
                recipe.created_on = item["created_on"]
                recipe.save()
                created += is_new
                updated += not is_new
                if item["created_on_raw"] and not item["created_on"]:
                    self.stdout.write(self.style.WARNING(
                        f"  Could not read date {item['created_on_raw']!r} for '{item['name']}' - left blank."))

        self.stdout.write(self.style.SUCCESS(
            f"Done. Recipes created: {created}, updated: {updated}. "
            f"Categories: {len(categories)}, cuisines: {len(cuisines)}, library images: {len(images)}."
        ))

    # ------------------------------------------------------------------
    def _import_categories(self, names):
        result = {}
        for name in dict.fromkeys(n for n in names if n):
            icon, accent, tagline = legacy.CATEGORY_META.get(name, ("fa-utensils", "healthy", ""))
            obj, created = Category.objects.get_or_create(
                name=name, defaults={"icon": icon, "accent": accent, "tagline": tagline})
            result[name] = obj
        return result

    def _import_cuisines(self, names):
        result = {}
        for name in dict.fromkeys(n for n in names if n):
            short, accent, tagline = legacy.CUISINE_META.get(name, ("", "red", ""))
            obj, created = Cuisine.objects.get_or_create(
                name=name, defaults={"short_name": short, "accent": accent, "tagline": tagline})
            result[name] = obj
        return result

    def _import_images(self, images_dir, data):
        """Copy real recipe photos into MEDIA_ROOT through Django's storage. Returns {filename: RecipeImage}."""
        wanted = list(dict.fromkeys(
            [r["image"] for r in data["recipes"] if r["image"]] + data["library"]))
        result = {}
        for filename in wanted:
            if not legacy.is_recipe_photo(filename):
                continue
            source = images_dir / filename
            if not source.is_file():
                self.stdout.write(self.style.WARNING(f"  Image file missing, skipped: {filename}"))
                continue
            title = Path(filename).stem[:150]
            existing = RecipeImage.objects.filter(title=title).first()
            if existing:
                result[filename] = existing
                continue
            with source.open("rb") as handle:
                obj = RecipeImage(title=title)
                obj.image.save(filename, File(handle), save=True)
            result[filename] = obj
        return result
