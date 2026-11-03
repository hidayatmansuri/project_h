"""
Management command `python manage.py projectauth_purge_audit --older-than 365` (Section 7, 13, 19.7).
Purges AuditEvent rows older than the specified retention window (default 365 days) for UK GDPR
data-minimisation compliance, and records an `audit.purged` event.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from projectauth.audit import log_audit
from projectauth.models import AuditEvent


class Command(BaseCommand):
    help = "Deletes AuditEvent rows older than --older-than <days> (default 365)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--older-than",
            type=int,
            default=365,
            dest="older_than",
            help="Delete AuditEvent rows older than this many days (default: 365).",
        )

    def handle(self, *args, **options):
        older_than = int(options.get("older_than") or 365)
        if older_than < 1:
            raise CommandError("--older-than must be at least 1 day.")

        cutoff = timezone.now() - timedelta(days=older_than)
        deleted_count, _ = AuditEvent.objects.filter(created_at__lt=cutoff).delete()

        log_audit(
            "audit.purged",
            actor_label="cli:projectauth_purge_audit",
            details={
                "older_than_days": older_than,
                "deleted_count": deleted_count,
                "cutoff_utc": cutoff.isoformat(),
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Purged {deleted_count} AuditEvent row(s) older than {older_than} day(s)."
            )
        )

