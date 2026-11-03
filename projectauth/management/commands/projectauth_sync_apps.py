from django.core.management.base import BaseCommand

from projectauth.registry import sync_protected_apps


class Command(BaseCommand):
    help = "Discover and synchronize ProtectedApp rows for all local Django apps."

    def handle(self, *args, **options):
        synced = sync_protected_apps()
        for app_obj in synced:
            visibility = "PUBLIC" if app_obj.is_public else "PROTECTED"
            self.stdout.write(
                f"  [{visibility}] {app_obj.app_label} -> {app_obj.name} (active={app_obj.is_active})"
            )
        self.stdout.write(self.style.SUCCESS(f"Synchronized {len(synced)} local app(s)."))

