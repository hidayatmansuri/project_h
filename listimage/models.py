import shutil
import uuid
from pathlib import Path
from django.conf import settings
from django.db import models


class BatchJob(models.Model):
    """
    Represents a collection of ImageJobs processed together in batch mode.
    """
    class Status(models.TextChoices):
        QUEUED = 'queued', 'Queued'
        PROCESSING = 'processing', 'Processing'
        DONE = 'done', 'Done'
        FAILED = 'failed', 'Failed'
        DOWNLOADED = 'downloaded', 'Downloaded'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.CharField(max_length=150, db_index=True, help_text="Session key or user ID")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    total_count = models.IntegerField(default=0)
    completed_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    params = models.JSONField(default=dict, blank=True, help_text="Common pipeline parameters for this batch")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['owner', 'status']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self) -> str:
        return f"BatchJob({self.id}, owner={self.owner[:8]}..., status={self.status}, {self.completed_count}/{self.total_count})"

    def is_owned_by(self, owner_identifier: str) -> bool:
        if not owner_identifier:
            return False
        return str(self.owner) == str(owner_identifier)

    def cleanup_files(self) -> None:
        """Deletes all item workspace directories belonging to this batch."""
        for item in self.items.all():
            item.cleanup_files()


class ImageJob(models.Model):
    """
    Represents an image processing job.
    Tracks state, owner (session key or username/id), edit parameters,
    and timestamps. Can belong to an optional BatchJob.
    """

    class Status(models.TextChoices):
        QUEUED = 'queued', 'Queued'
        PROCESSING = 'processing', 'Processing'
        DONE = 'done', 'Done'
        FAILED = 'failed', 'Failed'
        DOWNLOADED = 'downloaded', 'Downloaded'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(
        BatchJob,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='items',
        help_text="Optional parent batch"
    )
    original_filename = models.CharField(max_length=255, blank=True, default='', help_text="Original uploaded filename")
    owner = models.CharField(max_length=150, db_index=True, help_text="Session key or user ID")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    error_message = models.TextField(blank=True, default='')
    params = models.JSONField(default=dict, blank=True, help_text="Non-destructive edit and pipeline parameters")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['owner', 'status']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['batch', 'status']),
        ]

    def __str__(self) -> str:
        return f"ImageJob({self.id}, owner={self.owner[:8]}..., status={self.status})"

    @property
    def workspace_path(self) -> Path:
        """Returns the local workspace directory for this job."""
        base_dir = getattr(settings, 'LISTIMAGE_WORKSPACE_DIR', settings.BASE_DIR / 'listimage' / 'workspace')
        return Path(base_dir) / str(self.id)

    def is_owned_by(self, owner_identifier: str) -> bool:
        """Verifies if the requester owns this job."""
        if not owner_identifier:
            return False
        return str(self.owner) == str(owner_identifier)

    def cleanup_files(self) -> None:
        """Deletes this job's workspace directory from disk."""
        folder = self.workspace_path
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
