from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _on_post_migrate(sender, using, **kwargs):
    from .registry import sync_protected_apps

    sync_protected_apps(using=using)


class ProjectAuthConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "projectauth"
    verbose_name = "Project Auth & Access Control"

    def ready(self):
        post_migrate.connect(_on_post_migrate, sender=self)

