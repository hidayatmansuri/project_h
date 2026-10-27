"""
Django Management Command: cleanup_listimage
Prunes expired ImageJobs and their workspace directories.
Cleans orphaned folders in listimage/workspace/.
Guards against concurrent runs using a lock file.
"""

import os
import shutil
import time
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from listimage.models import ImageJob


class Command(BaseCommand):
    help = "Cleans up expired ImageJob records and orphaned workspace folders."

    def add_arguments(self, parser):
        parser.add_argument(
            '--max-age-minutes',
            type=int,
            default=getattr(settings, 'LISTIMAGE_MAX_AGE_MINUTES', 60),
            help="Maximum age in minutes for jobs before deletion (default: 60)."
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Simulates cleanup without deleting database rows or files."
        )

    def handle(self, *args, **options):
        max_age_minutes = options['max_age_minutes']
        dry_run = options['dry_run']

        workspace_dir = getattr(
            settings,
            'LISTIMAGE_WORKSPACE_DIR',
            settings.BASE_DIR / 'listimage' / 'workspace'
        )
        workspace_dir = Path(workspace_dir)
        workspace_dir.mkdir(parents=True, exist_ok=True)

        lock_file = workspace_dir / '.cleanup.lock'

        # Lock check to prevent overlapping runs
        if lock_file.exists():
            # Check if lock is stale (older than 30 minutes)
            try:
                lock_age = time.time() - lock_file.stat().st_mtime
                if lock_age < 1800:
                    self.stdout.write(
                        self.style.WARNING(f"Cleanup lock file is active (age {int(lock_age)}s). Another cleanup is running. Exiting.")
                    )
                    return
                else:
                    self.stdout.write(
                        self.style.WARNING("Found stale lock file (>30 mins). Removing stale lock.")
                    )
                    lock_file.unlink(missing_ok=True)
            except Exception:
                pass

        # Acquire lock
        try:
            lock_file.write_text(f"pid={os.getpid()}\ntime={time.time()}\n")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Could not create lock file: {e}"))
            return

        try:
            cutoff = timezone.now() - timedelta(minutes=max_age_minutes)
            self.stdout.write(f"Running ListImage cleanup (cutoff: jobs before {cutoff.isoformat()}, dry_run={dry_run})...")

            # 1. Clean expired jobs
            expired_jobs = ImageJob.objects.filter(created_at__lt=cutoff)
            expired_count = expired_jobs.count()
            self.stdout.write(f"Found {expired_count} expired job(s) older than {max_age_minutes} minutes.")

            for job in expired_jobs:
                folder = job.workspace_path
                if dry_run:
                    self.stdout.write(f"  [DRY RUN] Would delete job {job.id} and folder: {folder}")
                else:
                    self.stdout.write(f"  Deleting job {job.id} and folder: {folder}")
                    if folder.exists():
                        shutil.rmtree(folder, ignore_errors=True)
                    job.delete()

            # 2. Clean orphaned workspace folders
            all_known_job_ids = set(str(jid) for jid in ImageJob.objects.values_list('id', flat=True))
            orphan_count = 0

            for entry in workspace_dir.iterdir():
                if not entry.is_dir():
                    continue
                folder_name = entry.name
                if folder_name.startswith('.'):
                    continue

                if folder_name not in all_known_job_ids:
                    orphan_count += 1
                    if dry_run:
                        self.stdout.write(f"  [DRY RUN] Would delete orphaned folder: {entry}")
                    else:
                        self.stdout.write(f"  Deleting orphaned folder: {entry}")
                        shutil.rmtree(entry, ignore_errors=True)

            self.stdout.write(
                self.style.SUCCESS(
                    f"Cleanup complete! Expired jobs processed: {expired_count}, Orphaned folders: {orphan_count}"
                )
            )

        finally:
            # Release lock
            if lock_file.exists():
                try:
                    lock_file.unlink()
                except Exception:
                    pass
