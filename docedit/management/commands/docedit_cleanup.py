"""
Management command to clean up expired temporary DocEdit sessions.
"""
from django.core.management.base import BaseCommand
from docedit.storage import cleanup_expired_sessions


class Command(BaseCommand):
    help = "Cleans up expired DocEdit temporary sessions from docedit/media/docedit_tmp."

    def handle(self, *args, **options):
        count = cleanup_expired_sessions()
        self.stdout.write(self.style.SUCCESS(f"Cleaned up {count} expired DocEdit session(s)."))
