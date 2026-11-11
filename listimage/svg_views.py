"""
ListImage SVG Views and API Endpoints.
Handles SVG start/upload, options configuration, background render dispatching,
SVG streaming preview, downloadable blob export, and cooperative cancellation.
"""

import json
import logging
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
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .executor import check_submission_limits, dispatch_job
from .models import ImageJob
from .services import (
    MAX_UPLOAD_BYTES,
    ValidationError,
    fork_job_for_svg,
    validate_and_normalize_upload,
)
from .svg_services import (
    MAX_SVG_BYTES,
    MAX_TRACE_PX,
    PRESETS,
    apply_palette_recoloring,
)
from .views import _get_owned_job_or_404, _get_request_owner

logger = logging.getLogger(__name__)


@ensure_csrf_cookie
def svg_start(request: HttpRequest) -> HttpResponse:
    """
    Renders SVG start/upload page (GET) or accepts SVG image upload (POST).
    On successful upload, queues job and redirects to options wizard.
    """
    owner = _get_request_owner(request)

    if request.method == 'POST':
        can_submit, error_msg = check_submission_limits(owner)
        if not can_submit:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
                return JsonResponse({'success': False, 'error': error_msg}, status=429)
            context = {
                'max_upload_mb': MAX_UPLOAD_BYTES // (1024 * 1024),
                'step': 'upload',
                'error_message': error_msg,
            }
            return render(request, 'listimage/svg_wizard.html', context, status=429)

        uploaded_file = request.FILES.get('image')
        if not uploaded_file:
            return JsonResponse({'success': False, 'error': 'No image file uploaded.'}, status=400)

        # Initial SVG params
        use_full_image = request.POST.get('use_full_image') in ('true', '1', 'on')
        color_mode = request.POST.get('color_mode', 'monochrome')
        preset = request.POST.get('preset', 'balanced')

        job = ImageJob.objects.create(
            owner=owner,
            kind=ImageJob.Kind.SVG,
            original_filename=getattr(uploaded_file, 'name', '')[:250],
            status=ImageJob.Status.QUEUED,
            params={
                'color_mode': color_mode,
                'sub_option': 'silhouette',
                'color': '#000000',
                'preset': preset,
                'use_full_image': use_full_image,
                'square_canvas': False,
                'bg_color': 'transparent',
                'hierarchical': 'stacked',
                'mode': 'spline',
                'n_colors': 8,
            }
        )

        try:
            orig_path, dims = validate_and_normalize_upload(uploaded_file, job.workspace_path)
            job.params['original_dimensions'] = list(dims)
            job.save(update_fields=['params'])

            # Dispatch background worker
            dispatch_job(str(job.id))

            options_url = reverse('listimage:svg_options', args=[job.id])
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
                return JsonResponse({
                    'success': True,
                    'job_id': str(job.id),
                    'status': job.status,
                    'status_url': reverse('listimage:status', args=[job.id]),
                    'options_url': options_url,
                })
            return redirect(options_url)

        except ValidationError as e:
            job.cleanup_files()
            job.delete()
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
        except Exception as e:
            logger.exception("SVG upload failed: %s", e)
            job.cleanup_files()
            job.delete()
            return JsonResponse({'success': False, 'error': f"Failed to upload: {e}"}, status=500)

    # GET request - check if active SVG job already in progress
    active_job = ImageJob.objects.filter(
        owner=owner,
        kind=ImageJob.Kind.SVG,
        status__in=[ImageJob.Status.QUEUED, ImageJob.Status.PROCESSING]
    ).order_by('-created_at').first()
    if active_job:
        return redirect('listimage:svg_options', job_id=active_job.id)

    context = {
        'max_upload_mb': MAX_UPLOAD_BYTES // (1024 * 1024),
        'step': 'upload',
    }
    return render(request, 'listimage/svg_wizard.html', context)


@require_POST
def svg_from_raster(request: HttpRequest, job_id) -> HttpResponse:
    """
    Entry Point 10(b): Creates a new ImageJob(kind='svg') forked from an existing
    raster job's cutout, preserving the source raster job.
    """
    owner = _get_request_owner(request)
    raster_job = _get_owned_job_or_404(request, job_id)

    can_submit, error_msg = check_submission_limits(owner)
    if not can_submit:
        return JsonResponse({'success': False, 'error': error_msg}, status=429)

    try:
        svg_job = fork_job_for_svg(raster_job, owner)

        # Set default SVG options
        svg_job.params.update({
            'color_mode': 'monochrome',
            'sub_option': 'silhouette',
            'color': '#000000',
            'preset': 'balanced',
            'use_full_image': False,
            'square_canvas': False,
            'bg_color': 'transparent',
            'hierarchical': 'stacked',
            'mode': 'spline',
            'n_colors': 8,
        })
        svg_job.status = ImageJob.Status.QUEUED
        svg_job.save(update_fields=['params', 'status'])

        # Dispatch background worker to trace initial SVG
        dispatch_job(str(svg_job.id))

        options_url = reverse('listimage:svg_options', args=[svg_job.id])
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
            return JsonResponse({
                'success': True,
                'job_id': str(svg_job.id),
                'redirect_url': options_url,
                'status_url': reverse('listimage:status', args=[svg_job.id]),
            })
        return redirect(options_url)
    except Exception as e:
        logger.exception("Failed to fork raster job %s for SVG: %s", job_id, e)
        return JsonResponse({'success': False, 'error': f"Failed to create SVG job: {e}"}, status=500)


@ensure_csrf_cookie
def svg_options(request: HttpRequest, job_id) -> HttpResponse:
    """
    Renders the SVG options and interactive preview wizard.
    """
    job = _get_owned_job_or_404(request, job_id)
    if job.kind != ImageJob.Kind.SVG:
        raise Http404("Job is not an SVG job.")

    has_svg = (job.workspace_path / 'output.svg').exists()
    svg_stats = job.params.get('svg_stats', {})
    palette = job.params.get('palette', [])
    preset_key = job.params.get('preset', 'balanced')
    adv_defaults = PRESETS.get(preset_key, PRESETS['balanced']).copy()
    if isinstance(job.params.get('custom_params'), dict):
        adv_defaults.update(job.params['custom_params'])

    context = {
        'job': job,
        'params': job.params,
        'adv': adv_defaults,
        'error_message': job.error_message if job.status == ImageJob.Status.FAILED else '',
        'svg_stats': svg_stats,
        'palette': palette,
        'has_svg': has_svg,
        'max_svg_bytes': MAX_SVG_BYTES,
        'max_svg_mb': MAX_SVG_BYTES / (1024 * 1024),
        'step': 'options',
        'status_url': reverse('listimage:status', args=[job.id]),
        'render_url': reverse('listimage:svg_render', args=[job.id]),
        'preview_url': reverse('listimage:svg_preview', args=[job.id]),
        'download_url': reverse('listimage:svg_download', args=[job.id]),
        'cancel_url': reverse('listimage:svg_cancel', args=[job.id]),
        'cleanup_url': reverse('listimage:cleanup', args=[job.id]),
        'recolor_url': reverse('listimage:svg_recolor', args=[job.id]),
        'presets': PRESETS,
    }
    return render(request, 'listimage/svg_wizard.html', context)


@require_POST
def svg_render(request: HttpRequest, job_id) -> JsonResponse:
    """
    Updates SVG parameters and dispatches a background trace job.
    """
    job = _get_owned_job_or_404(request, job_id)
    if job.kind != ImageJob.Kind.SVG:
        return JsonResponse({'success': False, 'error': 'Not an SVG job'}, status=400)

    try:
        if request.content_type == 'application/json':
            payload = json.loads(request.body.decode('utf-8'))
        else:
            payload = request.POST.dict()
            if 'kept_indices' in payload and isinstance(payload['kept_indices'], str):
                try:
                    payload['kept_indices'] = json.loads(payload['kept_indices'])
                except Exception:
                    pass
            if 'palette_map' in payload and isinstance(payload['palette_map'], str):
                try:
                    payload['palette_map'] = json.loads(payload['palette_map'])
                except Exception:
                    pass
            if 'custom_params' in payload and isinstance(payload['custom_params'], str):
                try:
                    payload['custom_params'] = json.loads(payload['custom_params'])
                except Exception:
                    pass
    except Exception as e:
        return JsonResponse({'success': False, 'error': f"Invalid request body: {e}"}, status=400)

    # Extract options
    color_mode = payload.get('color_mode', job.params.get('color_mode', 'monochrome'))
    sub_option = payload.get('sub_option', job.params.get('sub_option', 'silhouette'))
    color = payload.get('color', job.params.get('color', '#000000'))
    detail_threshold = int(payload.get('detail_threshold', job.params.get('detail_threshold', 128)))
    n_colors = max(2, min(16, int(payload.get('n_colors', job.params.get('n_colors', 8)))))
    kept_indices = payload.get('kept_indices', job.params.get('kept_indices'))
    monochrome_color = payload.get('monochrome_color', job.params.get('monochrome_color', '#000000'))
    preset = payload.get('preset', job.params.get('preset', 'balanced'))
    mode = payload.get('mode', job.params.get('mode', 'spline'))
    hierarchical = payload.get('hierarchical', job.params.get('hierarchical', 'stacked'))
    use_full_image = payload.get('use_full_image') in (True, 'true', '1', 'on')
    square_canvas = payload.get('square_canvas') in (True, 'true', '1', 'on')
    bg_color = payload.get('bg_color', job.params.get('bg_color', 'transparent'))
    palette_map = payload.get('palette_map', job.params.get('palette_map'))
    remove_near_white = payload.get('remove_near_white') in (True, 'true', '1', 'on')
    custom_params = payload.get('custom_params')

    job.params.update({
        'color_mode': color_mode,
        'sub_option': sub_option,
        'color': color,
        'detail_threshold': detail_threshold,
        'n_colors': n_colors,
        'kept_indices': kept_indices,
        'monochrome_color': monochrome_color,
        'preset': preset,
        'mode': mode,
        'hierarchical': hierarchical,
        'use_full_image': use_full_image,
        'square_canvas': square_canvas,
        'bg_color': bg_color,
        'palette_map': palette_map,
        'remove_near_white': remove_near_white,
        'custom_params': custom_params,
    })
    job.status = ImageJob.Status.QUEUED
    job.save(update_fields=['params', 'status', 'updated_at'])

    dispatch_job(str(job.id))

    return JsonResponse({
        'success': True,
        'job_id': str(job.id),
        'status': job.status,
        'status_url': reverse('listimage:status', args=[job.id]),
    })


@require_POST
def svg_recolor(request: HttpRequest, job_id) -> JsonResponse:
    """
    Applies live palette modifications server-side (swatch replacement, transparency, near-white removal)
    without re-tracing the image.
    """
    job = _get_owned_job_or_404(request, job_id)
    if job.kind != ImageJob.Kind.SVG:
        return JsonResponse({'success': False, 'error': 'Not an SVG job'}, status=400)

    svg_path = job.workspace_path / 'output.svg'
    if not svg_path.exists():
        return JsonResponse({'success': False, 'error': 'No SVG found to recolor.'}, status=404)

    try:
        if request.content_type == 'application/json':
            payload = json.loads(request.body.decode('utf-8'))
        else:
            payload = request.POST.dict()
            if 'palette_map' in payload and isinstance(payload['palette_map'], str):
                try:
                    payload['palette_map'] = json.loads(payload['palette_map'])
                except Exception:
                    pass
    except Exception as e:
        return JsonResponse({'success': False, 'error': f"Invalid JSON payload: {e}"}, status=400)

    palette_map = payload.get('palette_map', {})
    remove_near_white = payload.get('remove_near_white') in (True, 'true', '1', 'on')

    try:
        current_svg = svg_path.read_text(encoding='utf-8')
        recolored_svg, stats = apply_palette_recoloring(
            svg_content=current_svg,
            palette_map=palette_map,
            remove_near_white=remove_near_white
        )
        svg_path.write_text(recolored_svg, encoding='utf-8')

        job.params['svg_stats'] = stats
        job.params['palette_map'] = palette_map
        job.save(update_fields=['params', 'updated_at'])

        return JsonResponse({
            'success': True,
            'svg_stats': stats,
            'preview_url': reverse('listimage:svg_preview', args=[job.id]) + f"?t={job.updated_at.timestamp()}",
        })
    except Exception as e:
        logger.exception("SVG recoloring failed: %s", e)
        return JsonResponse({'success': False, 'error': f"Recoloring failed: {e}"}, status=500)


@xframe_options_sameorigin
@require_GET
def svg_preview(request: HttpRequest, job_id) -> HttpResponse:
    """
    Serves the pure vector SVG content with same-origin framing allowed for <object> preview,
    nosniff, and image/svg+xml MIME type.
    """
    job = _get_owned_job_or_404(request, job_id)
    svg_path = job.workspace_path / 'output.svg'
    if not svg_path.exists():
        raise Http404("SVG preview is not ready.")

    content = svg_path.read_bytes()
    response = HttpResponse(content, content_type='image/svg+xml')
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


@require_GET
def svg_download(request: HttpRequest, job_id) -> HttpResponse:
    """
    Serves the SVG as a downloadable attachment.
    Filename: sanitized listimage-<short-id>.svg.
    """
    job = _get_owned_job_or_404(request, job_id)
    svg_path = job.workspace_path / 'output.svg'
    if not svg_path.exists():
        raise Http404("SVG file not found for download.")

    content = svg_path.read_bytes()
    filename = f"listimage-{str(job.id)[:8]}.svg"

    response = HttpResponse(content, content_type='image/svg+xml')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'

    job.status = ImageJob.Status.DOWNLOADED
    job.save(update_fields=['status', 'updated_at'])

    return response


@require_POST
def svg_cancel(request: HttpRequest, job_id) -> HttpResponse:
    """
    Cancel endpoint on every SVG step:
    POST (CSRF) deletes job workspace files and DB row, then redirects to listimage:index.
    """
    job = _get_owned_job_or_404(request, job_id)
    logger.info("Cancelling SVG job %s", job_id)
    job.cleanup_files()
    job.delete()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
        return JsonResponse({'success': True, 'redirect_url': reverse('listimage:index')})

    return redirect('listimage:index')

