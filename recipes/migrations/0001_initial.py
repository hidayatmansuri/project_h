import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True)),
                ("slug", models.SlugField(blank=True, max_length=120, unique=True)),
                ("icon", models.CharField(default="fa-utensils", help_text="Font Awesome 5 icon class, e.g. fa-fish", max_length=50)),
                ("tagline", models.CharField(blank=True, max_length=140)),
                ("accent", models.CharField(
                    choices=[
                        ("chick", "Orange"),
                        ("beef", "Maroon"),
                        ("lamb", "Brown"),
                        ("pork", "Plum"),
                        ("seafood", "Blue"),
                        ("healthy", "Green"),
                        ("vegan", "Emerald"),
                        ("veg", "Leaf green"),
                    ],
                    default="healthy",
                    max_length=10,
                )),
            ],
            options={
                "verbose_name_plural": "categories",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="Cuisine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True)),
                ("slug", models.SlugField(blank=True, max_length=120, unique=True)),
                ("short_name", models.CharField(blank=True, help_text="Compact label used on cards and quick links, e.g. 'S. Asian'", max_length=30)),
                ("icon", models.CharField(default="fa-utensils", max_length=50)),
                ("tagline", models.CharField(blank=True, max_length=140)),
                ("accent", models.CharField(
                    choices=[
                        ("red", "Red"),
                        ("purple", "Purple"),
                        ("blue", "Blue"),
                        ("green", "Green"),
                    ],
                    default="red",
                    max_length=10,
                )),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="RecipeImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(blank=True, max_length=150)),
                ("image", models.ImageField(
                    upload_to="recipes/library/",
                    validators=[django.core.validators.FileExtensionValidator(["png", "jpg", "jpeg", "gif", "webp"])],
                )),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["title", "id"],
            },
        ),
        migrations.CreateModel(
            name="ChatMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("username", models.CharField(max_length=40)),
                ("message", models.CharField(max_length=500)),
                ("created", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                "ordering": ["created", "id"],
            },
        ),
        migrations.CreateModel(
            name="Recipe",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("slug", models.SlugField(blank=True, max_length=220, unique=True)),
                ("ingredients", models.JSONField(blank=True, default=list)),
                ("methods", models.JSONField(blank=True, default=list)),
                ("prep_time", models.PositiveSmallIntegerField(default=0, help_text="Minutes")),
                ("cook_time", models.PositiveSmallIntegerField(default=0, help_text="Minutes")),
                ("created_on", models.DateField(blank=True, help_text="Date shown on the recipe", null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("category", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="recipes", to="recipes.category",
                )),
                ("cuisine", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="recipes", to="recipes.cuisine",
                )),
                ("image", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="recipes", to="recipes.recipeimage",
                )),
            ],
            options={
                "ordering": ["name"],
            },
        ),
    ]
