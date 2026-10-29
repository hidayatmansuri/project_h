import os
import shutil
from pathlib import Path

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.templatetags.static import static
from django.urls import reverse
from django.utils.text import slugify

ALLOWED_IMAGE_EXTENSIONS = ["png", "jpg", "jpeg", "gif", "webp"]


def ensure_images_in_static_img():
    """
    Move any recipe images from ``recipes/library/`` (or ``media/recipes/library/``)
    into the project-level ``static/img/`` folder so all recipe cards serve images
    from ``static/img/``.
    """
    base_dir = Path(settings.BASE_DIR)
    static_img_dir = base_dir / "static" / "img"
    static_img_dir.mkdir(parents=True, exist_ok=True)

    for lib_dir in (
        base_dir / "recipes" / "library",
        base_dir / "media" / "recipes" / "library",
    ):
        if lib_dir.is_dir():
            for item in list(lib_dir.iterdir()):
                if item.is_file():
                    dest = static_img_dir / item.name
                    if dest.exists():
                        try:
                            item.unlink()
                        except OSError:
                            pass
                    else:
                        try:
                            shutil.move(str(item), str(dest))
                        except OSError:
                            try:
                                shutil.copy2(str(item), str(dest))
                            except OSError:
                                pass
            try:
                lib_dir.rmdir()
            except OSError:
                pass

    legacy_img_dir = base_dir / "recipes" / "legacy" / "img"
    if legacy_img_dir.is_dir():
        from .legacy import is_recipe_photo
        for item in legacy_img_dir.iterdir():
            if item.is_file() and is_recipe_photo(item.name):
                underscored = item.name.replace(" ", "_")
                dest_under = static_img_dir / underscored
                dest_exact = static_img_dir / item.name
                if not dest_under.exists() and not dest_exact.exists():
                    try:
                        shutil.copy2(str(item), str(dest_under))
                    except OSError:
                        pass


def unique_slug(model, value, *, pk=None, max_length=50):
    """Return a slug for ``value`` that is not used by another row of ``model``."""
    base = slugify(value)[:max_length] or "item"
    candidate, counter = base, 2
    queryset = model.objects.all()
    if pk:
        queryset = queryset.exclude(pk=pk)
    while queryset.filter(slug=candidate).exists():
        suffix = f"-{counter}"
        candidate = f"{base[:max_length - len(suffix)]}{suffix}"
        counter += 1
    return candidate


def minutes_label(minutes):
    if not minutes:
        return "N/A"
    return f"{minutes} min{'' if minutes == 1 else 's'}"


class Category(models.Model):
    """Replaces the Flask ``categories`` table (Beef, Chicken, Vegan ...)."""

    ACCENT_CHOICES = [
        ("chick", "Orange"),
        ("beef", "Maroon"),
        ("lamb", "Brown"),
        ("pork", "Plum"),
        ("seafood", "Blue"),
        ("healthy", "Green"),
        ("vegan", "Emerald"),
        ("veg", "Leaf green"),
    ]

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    icon = models.CharField(
        max_length=50, default="fa-utensils",
        help_text="Font Awesome 5 icon class, e.g. fa-fish",
    )
    tagline = models.CharField(max_length=140, blank=True)
    accent = models.CharField(max_length=10, choices=ACCENT_CHOICES, default="healthy")

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(Category, self.name, pk=self.pk, max_length=120)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("recipes:category", args=[self.slug])


class Cuisine(models.Model):
    """Replaces the Flask ``cuisines`` table (American Cuisine, Chinese Cuisine ...)."""

    ACCENT_CHOICES = [
        ("red", "Red"),
        ("purple", "Purple"),
        ("blue", "Blue"),
        ("green", "Green"),
    ]

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    short_name = models.CharField(
        max_length=30, blank=True,
        help_text="Compact label used on cards and quick links, e.g. 'S. Asian'",
    )
    icon = models.CharField(max_length=50, default="fa-utensils")
    tagline = models.CharField(max_length=140, blank=True)
    accent = models.CharField(max_length=10, choices=ACCENT_CHOICES, default="red")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def label(self):
        """Short text for cards: explicit short name, else the name minus 'Cuisine'."""
        if self.short_name:
            return self.short_name
        name = self.name.strip()
        if name.lower().endswith(" cuisine"):
            name = name[: -len(" cuisine")]
        return name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(Cuisine, self.name, pk=self.pk, max_length=120)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("recipes:cuisine", args=[self.slug])


class RecipeImage(models.Model):
    """Replaces the Flask ``images`` table: the reusable image library."""

    title = models.CharField(max_length=150, blank=True)
    image = models.ImageField(
        upload_to="recipes/library/",
        validators=[FileExtensionValidator(ALLOWED_IMAGE_EXTENSIONS)],
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["title", "id"]

    def __str__(self):
        return self.title or os.path.basename(self.image.name)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.image and Path(settings.MEDIA_ROOT).resolve() == (Path(settings.BASE_DIR) / "media").resolve():
            ensure_images_in_static_img()

    @property
    def url(self):
        """Return the URL for this image, resolving from project-level static/img/."""
        if not self.image:
            return ""
        filename = os.path.basename(str(self.image.name).replace("\\", "/"))
        if not filename:
            return ""
        static_img_dir = Path(settings.BASE_DIR) / "static" / "img"
        for candidate in dict.fromkeys((
            filename,
            filename.replace(" ", "_"),
            filename.replace("_", " "),
        )):
            if (static_img_dir / candidate).is_file():
                return static(f"img/{candidate}")
        try:
            if self.image.storage.exists(self.image.name):
                return self.image.url
        except Exception:
            pass
        return static(f"img/{filename}")


class Recipe(models.Model):
    """Replaces the Flask ``recipes`` table (without the ingredient_1..9 columns)."""

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    category = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="recipes"
    )
    cuisine = models.ForeignKey(
        Cuisine, null=True, blank=True, on_delete=models.SET_NULL, related_name="recipes"
    )
    image = models.ForeignKey(
        RecipeImage, null=True, blank=True, on_delete=models.SET_NULL, related_name="recipes"
    )
    ingredients = models.JSONField(default=list, blank=True)
    methods = models.JSONField(default=list, blank=True)
    prep_time = models.PositiveSmallIntegerField(default=0, help_text="Minutes")
    cook_time = models.PositiveSmallIntegerField(default=0, help_text="Minutes")
    created_on = models.DateField(null=True, blank=True, help_text="Date shown on the recipe")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(Recipe, self.name, pk=self.pk, max_length=220)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("recipes:recipe_detail", args=[self.slug])

    # ---- presentation helpers used by the templates -------------------------
    @property
    def image_url(self):
        """URL of the recipe photo, or '' so templates can fall back to a default."""
        if self.image_id and self.image and self.image.image:
            return self.image.url
        return ""

    @property
    def prep_display(self):
        return minutes_label(self.prep_time)

    @property
    def cook_display(self):
        return minutes_label(self.cook_time)

    @property
    def is_quick(self):
        """Same rule as the Flask app: 30 minutes or less of cooking."""
        return self.cook_time <= 30

    @property
    def search_text(self):
        return " ".join(self.ingredients or [])


class ChatMessage(models.Model):
    """
    Replaces the Flask in-memory ``messages`` list, which was lost on every restart
    and not shared between worker processes.
    """

    username = models.CharField(max_length=40)
    message = models.CharField(max_length=500)
    created = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created", "id"]

    def __str__(self):
        return f"{self.username}: {self.message[:40]}"
