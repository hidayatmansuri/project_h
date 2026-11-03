"""
Management command `python manage.py projectauth_cleanup` (Section 13).
Deletes expired tokens, CodeChallenges, PendingEmailChanges, AdminInvitations,
TrustedDevices, stale/revoked SessionRecords, and expired Django sessions.
Safe to run from cron daily.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from projectauth.audit import log_audit
from projectauth.email_service import DAILY_BUDGET_SCOPE
from projectauth.models import (
    AdminInvitation,
    CodeChallenge,
    PendingEmailChange,
    SessionRecord,
    Throttle,
    TrustedDevice,
)


class Command(BaseCommand):
    help = "Cleans up expired challenges, tokens, trusted devices, and stale session records."

    def handle(self, *args, **options):
        now = timezone.now()
        stale_cutoff = now - timedelta(days=30)

        challenges_del, _ = CodeChallenge.objects.filter(
            Q(expires_at__lte=now) | Q(consumed_at__isnull=False, created_at__lt=now - timedelta(days=1))
        ).delete()

        pending_email_del, _ = PendingEmailChange.objects.filter(
            Q(expires_at__lte=now, confirmed_at__isnull=True)
            | Q(confirmed_at__lt=stale_cutoff)
        ).delete()

        invites_del, _ = AdminInvitation.objects.filter(
            accepted_at__isnull=True,
            expires_at__lte=now - timedelta(days=7),
        ).delete()

        trusted_del, _ = TrustedDevice.objects.filter(expires_at__lte=now).delete()

        session_records_del, _ = SessionRecord.objects.filter(
            Q(expires_at__lte=now)
            | Q(revoked_at__lt=now - timedelta(days=7))
            | Q(last_seen_at__lt=stale_cutoff)
        ).delete()

        django_sessions_del, _ = Session.objects.filter(expire_date__lte=now).delete()

        throttles_del, _ = (
            Throttle.objects.exclude(scope=DAILY_BUDGET_SCOPE)
            .filter(
                Q(locked_until__lte=now - timedelta(days=1))
                | Q(locked_until__isnull=True, window_started_at__lt=now - timedelta(days=2))
            )
            .delete()
        )

        summary = {
            "challenges_deleted": challenges_del,
            "pending_email_changes_deleted": pending_email_del,
            "expired_invites_deleted": invites_del,
            "trusted_devices_deleted": trusted_del,
            "session_records_deleted": session_records_del,
            "django_sessions_deleted": django_sessions_del,
            "throttles_deleted": throttles_del,
        }
        log_audit(
            "system.cleanup",
            actor_label="cli:projectauth_cleanup",
            details=summary,
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Cleanup complete: "
                + ", ".join(f"{k}={v}" for k, v in summary.items())
            )
        )

