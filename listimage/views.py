"""
ListImage Views and API Endpoints.
All business logic is delegated to services.py and executor.py.
Handles upload validation, progress polling, preview streaming,
interactive edits, download, and file cleanup.
"""

import io
import json
import logging
import zipfile
from pathlib import Path
from typing import Any, Dict

from django.conf import settings
from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponse,
    JsonResponse,
)
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .executor import check_submission_limits, dispatch_job, get_queue_position
from .models import BatchJob, ImageJob
from .services import (
    AVAILABLE_MODELS,
    CANVAS_SIZE,
    MAX_OBJECT_DIM,
    MAX_UPLOAD_BYTES,
    PADDING_PX,
    ValidationError,
    apply_edits_and_rerender,
    apply_touchup_to_workspace,
    export_rendered_image,
    validate_and_normalize_upload,
)

logger = logging.getLogger(__name__)


def _get_request_owner(request: HttpRequest) -> str:
    """Returns unique owner identifier: user pk if authenticated, or session key."""
    if request.user.is_authenticated:
        return f"user:{request.user.pk}"
    if not request.session.session_key:
        request.session.save()
    return f"session:{request.session.session_key}"


def _get_owned_job_or_404(request: HttpRequest, job_id) -> ImageJob:
    """
    Retrieves job by UUID and verifies ownership.
    Returns 404 if job does not exist or requester is not the owner.
    """
    owner = _get_request_owner(request)
    try:
        job = ImageJob.objects.get(id=job_id)
    except (ImageJob.DoesNotExist, ValueError):
        raise Http404("Image job not found.")

    if not job.is_owned_by(owner):
        logger.warning("Unauthorized access attempt to job %s by owner %s", job_id, owner)
        raise Http404("Image job not found.")

    return job


def _get_owned_batch_or_404(request: HttpRequest, batch_id) -> BatchJob:
    """
    Retrieves BatchJob by UUID and verifies ownership.
    Returns 404 if batch does not exist or requester is not the owner.
    """
    owner = _get_request_owner(request)
    try:
        batch = BatchJob.objects.get(id=batch_id)
    except (BatchJob.DoesNotExist, ValueError):
        raise Http404("Batch not found.")

    if not batch.is_owned_by(owner):
        logger.warning("Unauthorized access attempt to batch %s by owner %s", batch_id, owner)
        raise Http404("Batch not found.")

    return batch


@ensure_csrf_cookie
def index(request: HttpRequest) -> HttpResponse:
    """
    Renders the ListImage main page.
    Every exit point (after download, cancel, error) navigates back here.
    """
    owner = _get_request_owner(request)

    # Check if the user has an active or recent single job
    latest_job = ImageJob.objects.filter(
        owner=owner,
        batch__isnull=True,
        status__in=[ImageJob.Status.QUEUED, ImageJob.Status.PROCESSING, ImageJob.Status.DONE]
    ).order_by('-created_at').first()

    # Check if user has an active or recent batch
    latest_batch = BatchJob.objects.filter(
        owner=owner,
        status__in=[BatchJob.Status.QUEUED, BatchJob.Status.PROCESSING, BatchJob.Status.DONE]
    ).order_by('-created_at').first()

    context: Dict[str, Any] = {
        'title': 'ListImage - Pure White Background & Object Isolator | project-h',
        'available_models': AVAILABLE_MODELS,
        'max_upload_mb': MAX_UPLOAD_BYTES // (1024 * 1024),
        'max_batch_size': getattr(settings, 'LISTIMAGE_MAX_BATCH_SIZE', 20),
        'canvas_size': CANVAS_SIZE,
        'padding_px': PADDING_PX,
        'max_object_dim': MAX_OBJECT_DIM,
        'active_job_id': str(latest_job.id) if latest_job else '',
        'active_job_status': latest_job.status if latest_job else '',
        'active_batch_id': str(latest_batch.id) if latest_batch else '',
        'active_batch_status': latest_batch.status if latest_batch else '',
    }
    return render(request, 'listimage.html', context)


@require_POST
def upload(request: HttpRequest) -> JsonResponse:
    """
    Handles file upload:
    - If multiple files are provided, delegates seamlessly to batch_upload.
    - Validates image format (Pillow), size (<=25MB), megapixels (<=60MP)
    - Normalizes sRGB / EXIF
    - Creates ImageJob
    - Dispatches async processing (returns immediately with job_id)
    """
    owner = _get_request_owner(request)

    files = request.FILES.getlist('images') or request.FILES.getlist('image')
    if len(files) > 1:
        return batch_upload(request)

    uploaded_file = files[0] if files else request.FILES.get('image')
    if not uploaded_file:
        return JsonResponse({'success': False, 'error': 'No image file uploaded.'}, status=400)

    # Enforce concurrency and queue constraints
    can_submit, error_msg = check_submission_limits(owner)
    if not can_submit:
        return JsonResponse({'success': False, 'error': error_msg}, status=429)

    # Initial job parameters
    model_name = request.POST.get('model', 'isnet-general-use')
    alpha_matting = request.POST.get('alpha_matting') in ('true', '1', 'on')
    edge_smoothing = request.POST.get('edge_smoothing') in ('true', '1', 'on')
    keep_largest = request.POST.get('keep_largest', 'false') in ('true', '1', 'on')
    transparent_mode = request.POST.get('transparent_mode') in ('true', '1', 'on')

    # Create job in database
    job = ImageJob.objects.create(
        owner=owner,
        original_filename=getattr(uploaded_file, 'name', '')[:250],
        status=ImageJob.Status.QUEUED,
        params={
            'model': model_name,
            'alpha_matting': alpha_matting,
            'edge_smoothing': edge_smoothing,
            'keep_largest': keep_largest,
            'transparent_mode': transparent_mode,
        }
    )

    try:
        # Validate and store normalized image in workspace
        original_path, dimensions = validate_and_normalize_upload(uploaded_file, job.workspace_path)
        job.params['original_dimensions'] = list(dimensions)
        job.save(update_fields=['params'])

        # Dispatch background worker
        dispatch_job(str(job.id))

        return JsonResponse({
            'success': True,
            'job_id': str(job.id),
            'status': job.status,
            'status_url': reverse('listimage:status', args=[job.id]),
        })

    except ValidationError as e:
        job.cleanup_files()
        job.delete()
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    except Exception as e:
        logger.exception("Upload processing failed: %s", e)
        job.cleanup_files()
        job.delete()
        return JsonResponse({'success': False, 'error': f"Failed to accept upload: {e}"}, status=500)


@require_GET
def job_status(request: HttpRequest, job_id) -> JsonResponse:
    """
    Polling endpoint returning status of an ImageJob:
    queued (with position), processing, done, or failed.
    """
    job = _get_owned_job_or_404(request, job_id)
    ahead_count, queue_text = get_queue_position(job)

    data: Dict[str, Any] = {
        'job_id': str(job.id),
        'batch_id': str(job.batch_id) if job.batch_id else '',
        'original_filename': job.original_filename,
        'status': job.status,
        'error_message': job.error_message,
        'queue_ahead': ahead_count,
        'queue_text': queue_text,
        'params': job.params,
    }

    if job.status == ImageJob.Status.DONE:
        data.update({
            'preview_url': reverse('listimage:preview', args=[job.id]),
            'preview_trans_url': reverse('listimage:preview', args=[job.id]) + '?bg=transparent',
            'cutout_url': reverse('listimage:cutout_preview', args=[job.id]),
            'download_url': reverse('listimage:download', args=[job.id]),
            'warn_white_edges': job.params.get('warn_white_edges', False),
            'detected_objects': job.params.get('detected_objects', []),
            'metrics': job.params.get('metrics', {}),
        })

    return JsonResponse(data)


@require_GET
def preview_image(request: HttpRequest, job_id) -> HttpResponse:
    """Serves the rendered 2000x2000 preview image (pure white or transparent)."""
    job = _get_owned_job_or_404(request, job_id)
    is_trans = request.GET.get('bg') == 'transparent' or request.GET.get('transparent') in ('1', 'true')
    target_path = job.workspace_path / 'rendered_transparent.png' if is_trans else job.workspace_path / 'rendered_2000.png'

    if not target_path.exists():
        target_path = job.workspace_path / 'rendered_2000.png'
    if not target_path.exists():
        raise Http404("Rendered preview image not ready.")

    response = FileResponse(open(target_path, 'rb'), content_type='image/png')
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


@require_GET
def cutout_preview(request: HttpRequest, job_id) -> HttpResponse:
    """Serves the full-resolution transparent cutout."""
    job = _get_owned_job_or_404(request, job_id)
    cutout_path = job.workspace_path / 'cutout.png'

    if not cutout_path.exists():
        raise Http404("Cutout preview image not ready.")

    response = FileResponse(open(cutout_path, 'rb'), content_type='image/png')
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


@require_GET
def objects_metadata(request: HttpRequest, job_id) -> JsonResponse:
    """Returns detected connected objects for interactive selection/exclusion."""
    job = _get_owned_job_or_404(request, job_id)
    detected_objects = job.params.get('detected_objects', [])
    return JsonResponse({'objects': detected_objects})


@require_POST
def edit_job(request: HttpRequest, job_id) -> JsonResponse:
    """
    Applies non-destructive amendments:
    - Erase/restore brush mask strokes
    - Object selection/exclusion
    - Nudge and zoom
    - Re-process with alternative AI model
    """
    job = _get_owned_job_or_404(request, job_id)

    try:
        if request.content_type == 'application/json':
            payload = json.loads(request.body.decode('utf-8'))
        else:
            payload = request.POST.dict()
            if 'active_objects' in payload:
                try:
                    payload['active_objects'] = json.loads(payload['active_objects'])
                except Exception:
                    pass
    except Exception as e:
        return JsonResponse({'success': False, 'error': f"Invalid JSON payload: {e}"}, status=400)

    try:
        updated_meta = apply_edits_and_rerender(job.workspace_path, payload)
        job.params = updated_meta
        job.save(update_fields=['params', 'updated_at'])

        return JsonResponse({
            'success': True,
            'job_id': str(job.id),
            'params': job.params,
            'preview_url': reverse('listimage:preview', args=[job.id]) + f"?t={job.updated_at.timestamp()}",
            'metrics': updated_meta.get('metrics', {}),
            'warn_white_edges': updated_meta.get('warn_white_edges', False),
            'detected_objects': updated_meta.get('detected_objects', []),
        })
    except Exception as e:
        logger.exception("Failed to apply edits to job %s: %s", job_id, e)
        return JsonResponse({'success': False, 'error': f"Failed to apply edits: {e}"}, status=500)


@require_POST
def auto_touchup(request: HttpRequest, job_id) -> JsonResponse:
    """
    Toggles auto touch-up for transparent and reflective items
    (hole filling, morphological close, guided edge feathering).
    """
    job = _get_owned_job_or_404(request, job_id)

    try:
        enable = True
        if request.content_type == 'application/json':
            payload = json.loads(request.body.decode('utf-8'))
            enable = bool(payload.get('enable', True))
        else:
            enable = request.POST.get('enable', 'true') in ('true', '1', 'on')

        updated_meta = apply_touchup_to_workspace(job.workspace_path, enable=enable)
        job.params = updated_meta
        job.save(update_fields=['params', 'updated_at'])

        return JsonResponse({
            'success': True,
            'touchup_applied': updated_meta.get('touchup_applied', False),
            'preview_url': reverse('listimage:preview', args=[job.id]) + f"?t={job.updated_at.timestamp()}",
            'metrics': updated_meta.get('metrics', {}),
        })
    except Exception as e:
        logger.exception("Auto touchup failed on job %s: %s", job_id, e)
        return JsonResponse({'success': False, 'error': f"Auto touch-up failed: {e}"}, status=500)


@require_GET
def download_image(request: HttpRequest, job_id) -> HttpResponse:
    """
    Downloads the processed image:
    - PNG / PNG_WHITE: Lossless pure white 2000x2000
    - PNG_TRANSPARENT: Lossless transparent cutout (no background)
    - JPEG / JPG: Quality 95, 4:4:4 chroma subsampling, sRGB
    """
    job = _get_owned_job_or_404(request, job_id)
    fmt = request.GET.get('format', 'PNG_WHITE').upper()
    if fmt not in ('PNG', 'PNG_WHITE', 'PNG_TRANSPARENT', 'TRANSPARENT', 'JPG', 'JPEG'):
        fmt = 'PNG_WHITE'

    try:
        buffer = export_rendered_image(job.workspace_path, format=fmt)
        if fmt in ('PNG_TRANSPARENT', 'TRANSPARENT'):
            ext = 'png'
            filename = f"listimage_transparent_{str(job.id)[:8]}.png"
            content_type = 'image/png'
        elif fmt in ('JPG', 'JPEG'):
            ext = 'jpg'
            filename = f"listimage_2000x2000_{str(job.id)[:8]}.jpg"
            content_type = 'image/jpeg'
        else:
            ext = 'png'
            filename = f"listimage_2000x2000_white_{str(job.id)[:8]}.png"
            content_type = 'image/png'

        response = HttpResponse(buffer.getvalue(), content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'

        job.status = ImageJob.Status.DOWNLOADED
        job.save(update_fields=['status', 'updated_at'])

        return response
    except Exception as e:
        logger.exception("Download generation failed for job %s: %s", job_id, e)
        raise Http404(f"Download could not be generated: {e}")


@require_POST
def cleanup_job(request: HttpRequest, job_id) -> HttpResponse:
    """
    Deletes the job's workspace files and database row,
    then redirects to listimage:index.
    """
    job = _get_owned_job_or_404(request, job_id)
    logger.info("Cleaning up workspace and DB row for job %s", job_id)
    job.cleanup_files()
    job.delete()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
        return JsonResponse({'success': True, 'redirect_url': reverse('listimage:index')})

    return redirect('listimage:index')


@require_POST
def cancel_job(request: HttpRequest, job_id) -> HttpResponse:
    """
    Cancels an active or queued job, deletes workspace,
    and returns to listimage:index.
    """
    job = _get_owned_job_or_404(request, job_id)
    logger.info("Cancelling job %s", job_id)
    job.cleanup_files()
    job.delete()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
        return JsonResponse({'success': True, 'redirect_url': reverse('listimage:index')})

    return redirect('listimage:index')


# ==============================================================================
# Batch Processing Endpoints (Photoroom-style Batch Background Remover)
# ==============================================================================

@require_POST
def batch_upload(request: HttpRequest) -> JsonResponse:
    """
    Handles multi-image batch upload:
    - Accepts up to LISTIMAGE_MAX_BATCH_SIZE images
    - Applies uniform processing settings across the batch
    - Queues and executes them via the concurrency-managed thread worker pool
    """
    owner = _get_request_owner(request)
    files = request.FILES.getlist('images') or request.FILES.getlist('image')
    if not files:
        return JsonResponse({'success': False, 'error': 'No image files uploaded.'}, status=400)

    max_batch = getattr(settings, 'LISTIMAGE_MAX_BATCH_SIZE', 20)
    if len(files) > max_batch:
        return JsonResponse({
            'success': False,
            'error': f"Too many images ({len(files)}). Maximum allowed per batch is {max_batch}."
        }, status=400)

    can_submit, error_msg = check_submission_limits(owner, is_batch=True, count=len(files))
    if not can_submit:
        return JsonResponse({'success': False, 'error': error_msg}, status=429)

    model_name = request.POST.get('model', 'isnet-general-use')
    alpha_matting = request.POST.get('alpha_matting') in ('true', '1', 'on')
    edge_smoothing = request.POST.get('edge_smoothing') in ('true', '1', 'on')
    keep_largest = request.POST.get('keep_largest', 'false') in ('true', '1', 'on')
    transparent_mode = request.POST.get('transparent_mode') in ('true', '1', 'on')

    batch = BatchJob.objects.create(
        owner=owner,
        status=BatchJob.Status.QUEUED,
        total_count=len(files),
        params={
            'model': model_name,
            'alpha_matting': alpha_matting,
            'edge_smoothing': edge_smoothing,
            'keep_largest': keep_largest,
            'transparent_mode': transparent_mode,
        }
    )

    created_jobs = []
    errors = []

    for uploaded_file in files:
        job = ImageJob.objects.create(
            owner=owner,
            batch=batch,
            original_filename=getattr(uploaded_file, 'name', '')[:250],
            status=ImageJob.Status.QUEUED,
            params={
                'model': model_name,
                'alpha_matting': alpha_matting,
                'edge_smoothing': edge_smoothing,
                'keep_largest': keep_largest,
                'transparent_mode': transparent_mode,
            }
        )
        try:
            original_path, dimensions = validate_and_normalize_upload(uploaded_file, job.workspace_path)
            job.params['original_dimensions'] = list(dimensions)
            job.save(update_fields=['params'])
            created_jobs.append(job)
        except ValidationError as e:
            job.cleanup_files()
            job.status = ImageJob.Status.FAILED
            job.error_message = str(e)
            job.save(update_fields=['status', 'error_message'])
            errors.append(f"{uploaded_file.name}: {e}")
        except Exception as e:
            logger.exception("Upload processing failed for file %s: %s", getattr(uploaded_file, 'name', 'unknown'), e)
            job.cleanup_files()
            job.status = ImageJob.Status.FAILED
            job.error_message = f"Error: {e}"
            job.save(update_fields=['status', 'error_message'])
            errors.append(f"{getattr(uploaded_file, 'name', 'unknown')}: {e}")

    # Dispatch valid jobs to worker pool
    for job in created_jobs:
        dispatch_job(str(job.id))

    return JsonResponse({
        'success': True,
        'batch_id': str(batch.id),
        'total_count': len(files),
        'valid_count': len(created_jobs),
        'errors': errors,
        'status_url': reverse('listimage:batch_status', args=[batch.id]),
    })


@require_GET
def batch_status(request: HttpRequest, batch_id) -> JsonResponse:
    """
    Polling endpoint returning status of a BatchJob and all its items.
    """
    batch = _get_owned_batch_or_404(request, batch_id)
    items = batch.items.all().order_by('created_at')
    total = items.count()
    done = items.filter(status=ImageJob.Status.DONE).count()
    failed = items.filter(status=ImageJob.Status.FAILED).count()
    processing = items.filter(status=ImageJob.Status.PROCESSING).count()
    queued = items.filter(status=ImageJob.Status.QUEUED).count()

    items_data = []
    for item in items:
        item_data = {
            'job_id': str(item.id),
            'filename': item.original_filename or f"Image #{str(item.id)[:6]}",
            'status': item.status,
            'error_message': item.error_message,
        }
        if item.status == ImageJob.Status.DONE:
            item_data.update({
                'preview_url': reverse('listimage:preview', args=[item.id]),
                'preview_trans_url': reverse('listimage:preview', args=[item.id]) + '?bg=transparent',
                'download_url': reverse('listimage:download', args=[item.id]),
                'detected_objects_count': len(item.params.get('detected_objects', [])),
                'metrics': item.params.get('metrics', {}),
            })
        items_data.append(item_data)

    is_complete = (done + failed >= total and total > 0)
    percent = int(round((done + failed) / max(total, 1) * 100))

    return JsonResponse({
        'batch_id': str(batch.id),
        'status': batch.status,
        'total_count': total,
        'completed_count': done,
        'failed_count': failed,
        'processing_count': processing,
        'queued_count': queued,
        'percent': percent,
        'is_complete': is_complete,
        'items': items_data,
        'download_zip_url': reverse('listimage:batch_download', args=[batch.id]),
    })


@require_GET
def batch_download_zip(request: HttpRequest, batch_id) -> HttpResponse:
    """
    Packages all completed images from the batch into a single ZIP archive.
    Formats:
    - PNG / PNG_WHITE: Pure white 2000x2000 PNGs
    - PNG_TRANSPARENT: Lossless transparent cutouts
    - JPG / JPEG: High quality 95 JPEGs
    """
    batch = _get_owned_batch_or_404(request, batch_id)

    fmt = request.GET.get('format', 'PNG_WHITE').upper()
    if fmt not in ('PNG', 'PNG_WHITE', 'PNG_TRANSPARENT', 'TRANSPARENT', 'JPG', 'JPEG'):
        fmt = 'PNG_WHITE'

    done_items = batch.items.filter(status=ImageJob.Status.DONE)
    if not done_items.exists():
        raise Http404("No completed images in this batch to download.")

    zip_buffer = io.BytesIO()
    ext = 'jpg' if fmt in ('JPG', 'JPEG') else 'png'

    used_names = set()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for idx, job in enumerate(done_items, start=1):
            try:
                buf = export_rendered_image(job.workspace_path, format=fmt)
                orig_stem = Path(job.original_filename).stem if job.original_filename else f"image_{idx}"
                safe_stem = "".join(c for c in orig_stem if c.isalnum() or c in ('-', '_')).strip() or f"image_{idx}"

                suffix = "_white" if fmt in ('PNG', 'PNG_WHITE') else ("_transparent" if fmt in ('PNG_TRANSPARENT', 'TRANSPARENT') else "")
                entry_name = f"{safe_stem}{suffix}.{ext}"

                counter = 1
                while entry_name in used_names:
                    entry_name = f"{safe_stem}{suffix}_{counter}.{ext}"
                    counter += 1
                used_names.add(entry_name)

                zf.writestr(entry_name, buf.getvalue())
            except Exception as e:
                logger.warning("Failed to add job %s to batch zip: %s", job.id, e)

    zip_buffer.seek(0)
    zip_filename = f"listimage_batch_{str(batch.id)[:8]}_{fmt.lower()}.zip"

    response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{zip_filename}"'
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'

    batch.status = BatchJob.Status.DOWNLOADED
    batch.save(update_fields=['status', 'updated_at'])

    return response


@require_POST
def batch_cleanup(request: HttpRequest, batch_id) -> HttpResponse:
    """
    Deletes all workspace files and database rows for a batch,
    then redirects to listimage:index.
    """
    batch = _get_owned_batch_or_404(request, batch_id)
    logger.info("Cleaning up workspace and DB for batch %s", batch_id)
    batch.cleanup_files()
    batch.delete()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
        return JsonResponse({'success': True, 'redirect_url': reverse('listimage:index')})

    return redirect('listimage:index')


@require_POST
def batch_cancel(request: HttpRequest, batch_id) -> HttpResponse:
    """
    Cancels an in-progress batch, cleans up workspace files and DB rows.
    """
    batch = _get_owned_batch_or_404(request, batch_id)
    logger.info("Cancelling batch %s", batch_id)
    batch.cleanup_files()
    batch.delete()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
        return JsonResponse({'success': True, 'redirect_url': reverse('listimage:index')})

    return redirect('listimage:index')
