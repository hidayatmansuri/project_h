"""
ListImage Background Job Execution Engine.
Provides a swappable concurrency-limited queue:
- ThreadPoolExecutor backend (default, zero extra infrastructure)
- Celery task backend (swappable via settings.LISTIMAGE_BACKEND)
Enforces concurrency limits, max queue depth, and one-active-job-per-owner.
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Tuple

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

logger = logging.getLogger(__name__)

# Settings
MAX_WORKERS = getattr(settings, 'LISTIMAGE_MAX_CONCURRENT_JOBS', 2)
MAX_QUEUE = getattr(settings, 'LISTIMAGE_MAX_QUEUE', 10)
BACKEND = getattr(settings, 'LISTIMAGE_BACKEND', 'thread')

# Internal thread executor singleton
_EXECUTOR_LOCK = threading.Lock()
_THREAD_EXECUTOR: Optional[ThreadPoolExecutor] = None


def get_thread_executor() -> ThreadPoolExecutor:
    """Returns singleton ThreadPoolExecutor sized by LISTIMAGE_MAX_CONCURRENT_JOBS."""
    global _THREAD_EXECUTOR
    with _EXECUTOR_LOCK:
        if _THREAD_EXECUTOR is None:
            logger.info("Initializing ThreadPoolExecutor with %d max workers", MAX_WORKERS)
            _THREAD_EXECUTOR = ThreadPoolExecutor(
                max_workers=MAX_WORKERS,
                thread_name_prefix='ListImageWorker'
            )
        return _THREAD_EXECUTOR


def check_submission_limits(owner_key: str, is_batch: bool = False, count: int = 1) -> Tuple[bool, str]:
    """
    Enforces concurrency and queue constraints:
    1. Single mode: 1 active standalone job per user / session.
    2. Batch mode: 1 active batch per user / session, max batch size enforced.
    3. Max server queued jobs limit.
    """
    from .models import ImageJob, BatchJob

    if is_batch:
        active_batches = BatchJob.objects.filter(
            owner=owner_key,
            status__in=[BatchJob.Status.QUEUED, BatchJob.Status.PROCESSING]
        ).count()
        if active_batches > 0:
            return False, "You already have a batch in progress. Please wait for it to complete or download before uploading another."
        max_batch = getattr(settings, 'LISTIMAGE_MAX_BATCH_SIZE', 20)
        if count > max_batch:
            return False, f"Batch size ({count}) exceeds maximum allowed ({max_batch} images per batch)."
    else:
        # Per-owner active single job check
        active_user_jobs = ImageJob.objects.filter(
            owner=owner_key,
            batch__isnull=True,
            status__in=[ImageJob.Status.QUEUED, ImageJob.Status.PROCESSING]
        ).count()

        if active_user_jobs > 0:
            return False, "You already have an image in progress. Please wait for it to complete or download before uploading another."

    # Server capacity / queue limit
    queued_count = ImageJob.objects.filter(status=ImageJob.Status.QUEUED).count()
    if queued_count + count >= MAX_QUEUE * 5:
        return False, "Server is currently busy with high queue volume. Please try again in a few moments."

    return True, ""


def _update_batch_progress(batch_id) -> None:
    """Updates BatchJob progress counts and overall status."""
    from .models import BatchJob, ImageJob
    if not batch_id:
        return
    try:
        batch = BatchJob.objects.get(id=batch_id)
        total = batch.items.count()
        done = batch.items.filter(status=ImageJob.Status.DONE).count()
        failed = batch.items.filter(status=ImageJob.Status.FAILED).count()
        batch.total_count = total
        batch.completed_count = done
        batch.failed_count = failed

        if done + failed >= total and total > 0:
            batch.status = BatchJob.Status.DONE if done > 0 else BatchJob.Status.FAILED
        elif batch.items.filter(status=ImageJob.Status.PROCESSING).exists():
            batch.status = BatchJob.Status.PROCESSING
        else:
            batch.status = BatchJob.Status.QUEUED

        batch.save(update_fields=['total_count', 'completed_count', 'failed_count', 'status', 'updated_at'])
    except Exception as e:
        logger.warning("Error updating batch %s progress: %s", batch_id, e)


def get_queue_position(job) -> Tuple[int, str]:
    """
    Calculates queue position for a waiting job:
    Returns (ahead_count, human_readable_description)
    """
    from .models import ImageJob

    if job.status == ImageJob.Status.PROCESSING:
        return 0, "Processing image..."
    if job.status != ImageJob.Status.QUEUED:
        return 0, job.get_status_display()

    # Count jobs created earlier that are still queued
    ahead = ImageJob.objects.filter(
        status=ImageJob.Status.QUEUED,
        created_at__lt=job.created_at
    ).count()

    if ahead == 0:
        return 0, "Next in queue..."
    if ahead == 1:
        return 1, "Queued, 1 job ahead"
    return ahead, f"Queued, {ahead} jobs ahead"


def _run_job_worker(job_id_str: str) -> None:
    """
    Worker function executed in the background thread.
    Handles DB state transitions and image processing with comprehensive error handling.
    """
    close_old_connections()
    from .models import ImageJob
    from .services import process_initial_job, ImageProcessingError

    job = None
    import time
    for attempt in range(5):
        try:
            job = ImageJob.objects.get(id=job_id_str)
            break
        except Exception as e:
            if 'locked' in str(e).lower() and attempt < 4:
                time.sleep(0.1 * (attempt + 1))
                continue
            raise

    try:
        # Check if job was cancelled while queued
        if job.status != ImageJob.Status.QUEUED:
            return

        job.status = ImageJob.Status.PROCESSING
        job.save(update_fields=['status', 'updated_at'])
        if job.batch_id:
            _update_batch_progress(job.batch_id)

        logger.info("Worker started processing job %s", job_id_str)
        updated_params = process_initial_job(
            job_id=str(job.id),
            workspace_dir=job.workspace_path,
            params=job.params
        )

        job.params = updated_params
        job.status = ImageJob.Status.DONE
        job.error_message = ''
        job.save(update_fields=['params', 'status', 'error_message', 'updated_at'])
        logger.info("Worker successfully completed job %s", job_id_str)

    except ImageProcessingError as e:
        logger.warning("Job %s failed with processing error: %s", job_id_str, e)
        if job:
            job.status = ImageJob.Status.FAILED
            job.error_message = str(e)
            job.save(update_fields=['status', 'error_message', 'updated_at'])
    except Exception as e:
        logger.exception("Unexpected error processing job %s: %s", job_id_str, e)
        if job:
            job.status = ImageJob.Status.FAILED
            job.error_message = f"An unexpected error occurred during processing: {e}"
            job.save(update_fields=['status', 'error_message', 'updated_at'])
    finally:
        if job and job.batch_id:
            _update_batch_progress(job.batch_id)
        close_old_connections()


def dispatch_job(job_id_str: str) -> None:
    """
    Dispatches job processing to either Celery or the internal ThreadPoolExecutor.
    """
    backend = getattr(settings, 'LISTIMAGE_BACKEND', 'thread').lower()

    if backend == 'celery':
        try:
            from .tasks import process_image_job_celery
            process_image_job_celery.delay(job_id_str)
            logger.info("Dispatched job %s to Celery worker", job_id_str)
            return
        except Exception as e:
            logger.warning("Celery dispatch failed (%s), falling back to ThreadPoolExecutor", e)

    # Default to thread executor
    executor = get_thread_executor()
    executor.submit(_run_job_worker, job_id_str)
    logger.info("Submitted job %s to thread pool", job_id_str)
