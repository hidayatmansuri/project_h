"""
Optional Celery tasks for ListImage.
Used when settings.LISTIMAGE_BACKEND = 'celery'.
"""

import logging

logger = logging.getLogger(__name__)

try:
    from celery import shared_task

    @shared_task(bind=True, max_retries=2, default_retry_delay=5)
    def process_image_job_celery(self, job_id_str: str):
        """Celery task wrapper around ListImage worker processing."""
        from .executor import _run_job_worker
        try:
            _run_job_worker(job_id_str)
        except Exception as exc:
            logger.error("Celery task execution failed for job %s: %s", job_id_str, exc)
            raise self.retry(exc=exc)

except ImportError:
    # Celery is not installed in the environment
    def process_image_job_celery(job_id_str: str):
        """Fallback placeholder when Celery is not installed."""
        from .executor import _run_job_worker
        _run_job_worker(job_id_str)
