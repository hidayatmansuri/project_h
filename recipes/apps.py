from django.apps import AppConfig


class RecipesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "recipes"
    verbose_name = "Recipes"

    def ready(self):
        from .models import ensure_images_in_static_img
        try:
            ensure_images_in_static_img()
        except Exception:
            pass


recipesConfig = RecipesConfig
