"""
Comprehensive Automated Test Suite for ListImage.
Verifies all canvas dimensions, 10 px padding on constraining side,
centering, upscaling/downscaling, upload validation, object detection,
status polling, concurrency limits, cross-user 404 security,
cleanup command, and post-download flow.
"""

import io
import json
import shutil
import uuid
from datetime import timedelta
from pathlib import Path
import unittest
from unittest.mock import patch

try:
    import cairosvg
    HAS_CAIROSVG = True
except Exception:
    HAS_CAIROSVG = False

import numpy as np
from PIL import Image, ImageDraw
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import ImageJob
from .services import (
    CANVAS_SIZE,
    MAX_OBJECT_DIM,
    PADDING_PX,
    ValidationError,
    apply_object_filter_to_mask,
    auto_touchup_alpha,
    detect_connected_objects,
    remove_background_with_rembg,
    render_to_pure_white_canvas,
    validate_and_normalize_upload,
)


class CanvasMathAndRenderingTests(TestCase):
    """Verifies pure white 2000x2000 canvas, 10px constraining padding, and scaling."""

    def test_constraining_width_exact_10px_padding(self):
        """Wide image (W > H): width is constrained to 1980 with exact 10px padding."""
        img = Image.new('RGBA', (800, 400), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, 800, 400], fill=(255, 0, 0, 255))

        canvas, _trans, metrics = render_to_pure_white_canvas(img)

        # Output canvas dimensions must be exactly 2000x2000
        self.assertEqual(canvas.size, (2000, 2000))
        self.assertEqual(metrics['scaled_w'], 1980)
        self.assertEqual(metrics['scaled_h'], 990)
        self.assertEqual(metrics['constraining_side'], 'width')

        # Constraining side padding must be EXACTLY 10 px
        self.assertEqual(metrics['pad_left'], 10)
        self.assertEqual(metrics['pad_right'], 10)

        # Non-constraining side must be centered
        expected_y_offset = (2000 - 990) // 2
        self.assertEqual(metrics['offset_y'], expected_y_offset)

        # Corners of the canvas must be pure white (255, 255, 255)
        self.assertEqual(canvas.getpixel((0, 0)), (255, 255, 255))
        self.assertEqual(canvas.getpixel((1999, 0)), (255, 255, 255))
        self.assertEqual(canvas.getpixel((0, 1999)), (255, 255, 255))
        self.assertEqual(canvas.getpixel((1999, 1999)), (255, 255, 255))

    def test_constraining_height_exact_10px_padding(self):
        """Tall image (H > W): height is constrained to 1980 with exact 10px padding."""
        img = Image.new('RGBA', (400, 800), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, 400, 800], fill=(0, 128, 255, 255))

        canvas, _trans, metrics = render_to_pure_white_canvas(img)

        self.assertEqual(canvas.size, (2000, 2000))
        self.assertEqual(metrics['scaled_h'], 1980)
        self.assertEqual(metrics['scaled_w'], 990)
        self.assertEqual(metrics['constraining_side'], 'height')

        # Constraining side top and bottom padding must be exactly 10 px
        self.assertEqual(metrics['pad_top'], 10)
        self.assertEqual(metrics['pad_bottom'], 10)

        # Horizontal centering
        expected_x_offset = (2000 - 990) // 2
        self.assertEqual(metrics['offset_x'], expected_x_offset)

    def test_small_image_upscaling_with_unsharp_mask(self):
        """Small image (< 1980px) is upscaled uniformly to 1980px on premultiplied alpha."""
        small_img = Image.new('RGBA', (50, 50), (100, 150, 200, 255))
        canvas, _trans, metrics = render_to_pure_white_canvas(small_img)

        self.assertEqual(canvas.size, (2000, 2000))
        self.assertTrue(metrics['is_upscaled'])
        self.assertEqual(metrics['scaled_w'], 1980)
        self.assertEqual(metrics['scaled_h'], 1980)
        self.assertEqual(metrics['pad_left'], 10)
        self.assertEqual(metrics['pad_right'], 10)
        self.assertEqual(metrics['pad_top'], 10)
        self.assertEqual(metrics['pad_bottom'], 10)

    def test_huge_image_downscaling_no_clipped_edges(self):
        """Huge image (> 2000px) is downscaled cleanly without losing corners or edges."""
        huge_img = Image.new('RGBA', (4000, 2000), (0, 0, 0, 0))
        draw = ImageDraw.Draw(huge_img)
        draw.rectangle([0, 0, 4000, 2000], fill=(50, 200, 50, 255))

        canvas, _trans, metrics = render_to_pure_white_canvas(huge_img)

        self.assertEqual(canvas.size, (2000, 2000))
        self.assertFalse(metrics['is_upscaled'])
        self.assertEqual(metrics['scaled_w'], 1980)
        self.assertEqual(metrics['scaled_h'], 990)
        self.assertEqual(metrics['pad_left'], 10)
        self.assertEqual(metrics['pad_right'], 10)

    def test_transparent_blank_image_returns_pure_white(self):
        """An empty transparent image safely produces a pure white 2000x2000 canvas."""
        empty_img = Image.new('RGBA', (500, 500), (0, 0, 0, 0))
        canvas, _trans, metrics = render_to_pure_white_canvas(empty_img)

        self.assertEqual(canvas.size, (2000, 2000))
        self.assertEqual(metrics['constraining_side'], 'none')
        # All pixels are white
        colors = canvas.getcolors()
        self.assertEqual(len(colors), 1)
        self.assertEqual(colors[0][1], (255, 255, 255))


class UploadValidationTests(TestCase):
    """Tests upload size limits, Pillow verification, and animated file rejections."""

    def setUp(self):
        self.test_ws = settings.BASE_DIR / 'listimage' / 'workspace' / 'test_val'
        self.test_ws.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if self.test_ws.exists():
            shutil.rmtree(self.test_ws, ignore_errors=True)

    def test_valid_image_accepted_and_normalized(self):
        img = Image.new('RGB', (200, 200), color='blue')
        buf = io.BytesIO()
        img.save(buf, format='JPEG')
        buf.seek(0)

        upload = SimpleUploadedFile("product.jpg", buf.read(), content_type="image/jpeg")
        path, dims = validate_and_normalize_upload(upload, self.test_ws)

        self.assertTrue(path.exists())
        self.assertEqual(dims, (200, 200))

    def test_reject_animated_gif(self):
        """Animated GIFs with multiple frames are rejected."""
        frame1 = Image.new('RGB', (100, 100), color='red')
        frame2 = Image.new('RGB', (100, 100), color='green')
        buf = io.BytesIO()
        frame1.save(buf, format='GIF', save_all=True, append_images=[frame2], duration=200, loop=0)
        buf.seek(0)

        upload = SimpleUploadedFile("animated.gif", buf.read(), content_type="image/gif")
        with self.assertRaises(ValidationError) as ctx:
            validate_and_normalize_upload(upload, self.test_ws)
        self.assertIn("Animated", str(ctx.exception))

    def test_reject_corrupt_file(self):
        """Corrupt non-image byte stream is rejected."""
        upload = SimpleUploadedFile("bad.png", b"NOT_A_REAL_IMAGE_DATA", content_type="image/png")
        with self.assertRaises(ValidationError):
            validate_and_normalize_upload(upload, self.test_ws)


class ObjectSegmentationAndTouchupTests(TestCase):
    """Tests connected components labeling, keep-largest vs keep-all, and auto touch-up."""

    def test_connected_components_and_keep_largest(self):
        # Create alpha with two distinct square components:
        # Object 1 (large): 100x100
        # Object 2 (small): 30x30
        alpha = Image.new('L', (400, 400), 0)
        draw = ImageDraw.Draw(alpha)
        draw.rectangle([50, 50, 150, 150], fill=255)  # Area 10,000
        draw.rectangle([250, 250, 280, 280], fill=255) # Area 900

        labeled_array, detected, _cleaned = detect_connected_objects(alpha, min_area_threshold=100)

        self.assertEqual(len(detected), 2)
        # Largest object should be first
        self.assertTrue(detected[0]['is_largest'])
        self.assertEqual(detected[0]['area'], 10201)

        # Test keep largest: filter out the small component
        mask_np = np.array(alpha)
        active_ids = {detected[0]['id']}
        filtered_np = apply_object_filter_to_mask(mask_np, labeled_array, active_ids, keep_all=False)

        # Pixels in the small box area should now be 0
        self.assertEqual(filtered_np[260, 260], 0)
        # Pixels in the large box area should remain 255
        self.assertEqual(filtered_np[100, 100], 255)

    def test_auto_touchup_fills_holes_in_transparent_glass(self):
        """Simulates hollow hole inside glass/chrome object and verifies binary fill holes."""
        # Create a hollow donut / frame
        alpha = Image.new('L', (200, 200), 0)
        draw = ImageDraw.Draw(alpha)
        # Outer ring
        draw.rectangle([40, 40, 160, 160], fill=255)
        # Inner hollow hole
        draw.rectangle([70, 70, 130, 130], fill=0)

        # Pre-check: center is hollow (0)
        self.assertEqual(alpha.getpixel((100, 100)), 0)

        touched_alpha = auto_touchup_alpha(alpha, guided_refine=False)

        # Center should now be filled (> 0)
        self.assertGreater(touched_alpha.getpixel((100, 100)), 200)

    @patch('listimage.services.get_rembg_session')
    @patch('rembg.remove')
    def test_remove_background_with_rembg_accepts_pil_image(self, mock_remove, mock_session):
        """Verifies rembg.remove handles PIL Image without TypeError."""
        mock_session.return_value = 'mock_session'
        mock_remove.return_value = Image.new('RGBA', (100, 100), color=(255, 0, 0, 128))
        input_img = Image.new('RGB', (100, 100), color=(255, 0, 0))
        result = remove_background_with_rembg(input_img, model_name='u2netp')
        self.assertIsInstance(result, Image.Image)
        self.assertEqual(result.size, (100, 100))
        self.assertEqual(result.mode, 'RGBA')


class ViewsAndWorkflowTests(TestCase):
    """End-to-end integration tests for views, ownership security, concurrency, and download."""

    def setUp(self):
        from projectauth.test_helpers import grant_test_client_app_access

        self.client_a = Client()
        self.client_b = Client()
        grant_test_client_app_access(self.client_a, "listimage", username="listimage_user_a")
        grant_test_client_app_access(self.client_b, "listimage", username="listimage_user_b")

    def _create_sample_upload(self):
        img = Image.new('RGB', (300, 300), color=(200, 50, 50))
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return SimpleUploadedFile("product.png", buf.read(), content_type="image/png")

    def test_index_page_renders_listimage_template(self):
        """Verifies that the index endpoint renders listimage.html successfully."""
        res = self.client_a.get(reverse('listimage:index'))
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, 'listimage.html')

    @patch('listimage.views.dispatch_job')
    def test_upload_returns_job_and_polls_status(self, mock_dispatch):
        upload_file = self._create_sample_upload()
        res = self.client_a.post(reverse('listimage:upload'), {'image': upload_file})
        self.assertEqual(res.status_code, 200)

        data = res.json()
        self.assertTrue(data['success'])
        job_id = data['job_id']

        # Poll status
        status_res = self.client_a.get(reverse('listimage:status', args=[job_id]))
        self.assertEqual(status_res.status_code, 200)
        status_data = status_res.json()
        self.assertEqual(status_data['status'], 'queued')

    def _get_owner(self, client):
        user_id = client.session.get('_auth_user_id')
        if user_id:
            return f"user:{user_id}"
        return f"session:{client.session.session_key}"

    def test_cross_user_access_returns_404(self):
        """Requester B attempting to access Requester A's job gets 404."""
        # Create job owned by client A's session/user
        self.client_a.get(reverse('listimage:index'))
        owner_a = self._get_owner(self.client_a)

        job = ImageJob.objects.create(
            owner=owner_a,
            status=ImageJob.Status.DONE,
            params={'metrics': {}}
        )

        # Client B attempts to view status
        self.client_b.get(reverse('listimage:index'))
        res = self.client_b.get(reverse('listimage:status', args=[job.id]))
        self.assertEqual(res.status_code, 404)

        # Client B attempts to download
        res_dl = self.client_b.get(reverse('listimage:download', args=[job.id]))
        self.assertEqual(res_dl.status_code, 404)

        # Clean up
        job.delete()

    @patch('listimage.views.dispatch_job')
    def test_concurrency_single_job_per_user_limit(self, mock_dispatch):
        """User cannot upload a second job while one is queued or processing."""
        # First upload
        up1 = self._create_sample_upload()
        r1 = self.client_a.post(reverse('listimage:upload'), {'image': up1})
        self.assertEqual(r1.status_code, 200)

        # Second upload from same client
        up2 = self._create_sample_upload()
        r2 = self.client_a.post(reverse('listimage:upload'), {'image': up2})
        self.assertEqual(r2.status_code, 429)
        self.assertIn("already have an image in progress", r2.json()['error'])

    @patch('listimage.views.dispatch_job')
    def test_server_busy_when_queue_full(self, mock_dispatch):
        """When queued jobs reach LISTIMAGE_MAX_QUEUE, new uploads receive 429."""
        from listimage.executor import MAX_QUEUE

        # Create MAX_QUEUE * 5 queued jobs from different owners
        for i in range(MAX_QUEUE * 5):
            ImageJob.objects.create(
                owner=f"user_batch_{i}",
                status=ImageJob.Status.QUEUED
            )

        up = self._create_sample_upload()
        res = self.client_b.post(reverse('listimage:upload'), {'image': up})
        self.assertEqual(res.status_code, 429)
        self.assertIn("Server is currently busy", res.json()['error'])

    def test_edit_endpoint_applies_nudge_and_rerenders(self):
        """Tests that edit_job adjusts coordinates non-destructively and produces updated preview."""
        self.client_a.get(reverse('listimage:index'))
        owner_a = self._get_owner(self.client_a)

        job = ImageJob.objects.create(
            owner=owner_a,
            status=ImageJob.Status.DONE,
            params={'metrics': {}}
        )
        job.workspace_path.mkdir(parents=True, exist_ok=True)

        # Create mock cutout.png and current_mask.png
        cutout = Image.new('RGBA', (400, 400), (255, 0, 0, 255))
        cutout.save(job.workspace_path / 'cutout.png', format='PNG')
        cutout.split()[3].save(job.workspace_path / 'current_mask.png', format='PNG')

        edit_payload = {'nudge_x': 15, 'nudge_y': -10, 'zoom': 0.9}
        res = self.client_a.post(
            reverse('listimage:edit', args=[job.id]),
            data=json.dumps(edit_payload),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertTrue((job.workspace_path / 'rendered_2000.png').exists())

        job.cleanup_files()
        job.delete()

    def test_download_and_cleanup_redirect(self):
        """Simulates download and post-download cleanup redirect to listimage:index."""
        self.client_a.get(reverse('listimage:index'))
        owner_a = self._get_owner(self.client_a)

        job = ImageJob.objects.create(
            owner=owner_a,
            status=ImageJob.Status.DONE,
            params={'metrics': {}}
        )
        job.workspace_path.mkdir(parents=True, exist_ok=True)

        # Save dummy rendered_2000.png
        rendered = Image.new('RGB', (2000, 2000), (255, 255, 255))
        rendered.save(job.workspace_path / 'rendered_2000.png', format='PNG')

        # Download PNG
        dl_res = self.client_a.get(reverse('listimage:download', args=[job.id]))
        self.assertEqual(dl_res.status_code, 200)
        self.assertEqual(dl_res['Content-Type'], 'image/png')

        # Cleanup POST
        clean_res = self.client_a.post(reverse('listimage:cleanup', args=[job.id]))
        self.assertEqual(clean_res.status_code, 302)
        self.assertEqual(clean_res.url, reverse('listimage:index'))

        # Verify DB row and folder are deleted
        self.assertFalse(ImageJob.objects.filter(id=job.id).exists())
        self.assertFalse(job.workspace_path.exists())


class CleanupManagementCommandTests(TestCase):
    """Tests the cleanup_listimage command for expired jobs, dry-run, and orphan folder removal."""

    def setUp(self):
        self.ws_base = settings.BASE_DIR / 'listimage' / 'workspace'
        self.ws_base.mkdir(parents=True, exist_ok=True)

    def test_cleanup_expired_and_orphaned_folders(self):
        # 1. Expired job (created 2 hours ago)
        expired_job = ImageJob.objects.create(
            owner='test_expired',
            status=ImageJob.Status.DONE
        )
        # Update created_at in the past
        ImageJob.objects.filter(id=expired_job.id).update(
            created_at=timezone.now() - timedelta(minutes=120)
        )
        expired_folder = expired_job.workspace_path
        expired_folder.mkdir(parents=True, exist_ok=True)

        # 2. Fresh job (created 5 mins ago)
        fresh_job = ImageJob.objects.create(
            owner='test_fresh',
            status=ImageJob.Status.DONE
        )
        fresh_folder = fresh_job.workspace_path
        fresh_folder.mkdir(parents=True, exist_ok=True)

        # 3. Orphaned folder without DB row
        orphan_uuid = str(uuid.uuid4())
        orphan_folder = self.ws_base / orphan_uuid
        orphan_folder.mkdir(parents=True, exist_ok=True)

        # Test Dry Run
        out = io.StringIO()
        call_command('cleanup_listimage', '--dry-run', stdout=out)
        self.assertTrue(expired_folder.exists())
        self.assertTrue(orphan_folder.exists())
        self.assertTrue(fresh_folder.exists())

        # Test Real Run
        call_command('cleanup_listimage', stdout=out)
        # Expired job and folder should be deleted
        self.assertFalse(ImageJob.objects.filter(id=expired_job.id).exists())
        self.assertFalse(expired_folder.exists())
        # Orphan folder should be deleted
        self.assertFalse(orphan_folder.exists())
        # Fresh job and folder should be kept
        self.assertTrue(ImageJob.objects.filter(id=fresh_job.id).exists())
        self.assertTrue(fresh_folder.exists())

        # Cleanup fresh job
        fresh_job.cleanup_files()
        fresh_job.delete()


class Stage1RefactorTests(TestCase):
    """Tests Stage 1 refactoring: kind field, workspace fork, and cooperative cancellation helper."""

    def test_default_kind_is_raster(self):
        job = ImageJob.objects.create(owner='test_owner')
        self.assertEqual(job.kind, ImageJob.Kind.RASTER)
        job.delete()

    def test_fork_job_for_svg_copies_files_and_preserves_source(self):
        from listimage.services import fork_job_for_svg

        source = ImageJob.objects.create(
            owner='test_owner',
            original_filename='product.png',
            status=ImageJob.Status.DONE,
            params={'model': 'isnet-general-use'}
        )
        source.workspace_path.mkdir(parents=True, exist_ok=True)
        (source.workspace_path / 'cutout.png').write_bytes(b'FAKE_CUTOUT_PNG')

        forked = fork_job_for_svg(source, 'test_owner')

        self.assertEqual(forked.kind, ImageJob.Kind.SVG)
        self.assertEqual(forked.original_filename, 'product.png')
        self.assertEqual(forked.params['source_job_id'], str(source.id))
        self.assertTrue((forked.workspace_path / 'cutout.png').exists())
        self.assertEqual((forked.workspace_path / 'cutout.png').read_bytes(), b'FAKE_CUTOUT_PNG')

        # Source job remains intact (Option A)
        self.assertTrue((source.workspace_path / 'cutout.png').exists())

        source.cleanup_files()
        source.delete()
        forked.cleanup_files()
        forked.delete()

    def test_is_job_cancelled_helper(self):
        from listimage.executor import is_job_cancelled

        job = ImageJob.objects.create(owner='test_owner', status=ImageJob.Status.PROCESSING)
        self.assertFalse(is_job_cancelled(str(job.id)))

        job.delete()
        self.assertTrue(is_job_cancelled(str(job.id)))


class Stage2MonochromeTests(TestCase):
    """Tests Stage 2: Monochrome SVG Engine (silhouette, detail, scaling, sanitization, square canvas)."""

    def setUp(self):
        self.test_img = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
        for x in range(30, 70):
            for y in range(30, 70):
                self.test_img.putpixel((x, y), (20, 30, 40, 255))

    def test_prepare_trace_source_scaling_and_aspect(self):
        from listimage.svg_services import prepare_trace_source

        # 1. Huge image capping at max_dim (2000 default)
        huge_img = Image.new('RGBA', (3000, 1500), (255, 0, 0, 255))
        prepared_huge = prepare_trace_source(huge_img, max_dim=2000, upscale_small=False)
        self.assertEqual(prepared_huge.size, (2000, 1000))

        # 2. Small image upscaling 2x Lanczos
        small_img = Image.new('RGBA', (200, 100), (0, 255, 0, 255))
        prepared_small = prepare_trace_source(small_img, upscale_small=True)
        self.assertEqual(prepared_small.size, (400, 200))

        # 3. Medium image preserved
        med_img = Image.new('RGBA', (1000, 600), (0, 0, 255, 255))
        prepared_med = prepare_trace_source(med_img, max_dim=2000, upscale_small=True)
        self.assertEqual(prepared_med.size, (1000, 600))

    def test_extract_monochrome_mask_silhouette_and_detail(self):
        from listimage.svg_services import extract_monochrome_mask

        sil_mask = extract_monochrome_mask(self.test_img, sub_option='silhouette')
        self.assertEqual(sil_mask.shape, (100, 100))
        self.assertEqual(sil_mask[50, 50], 255)
        self.assertEqual(sil_mask[10, 10], 0)

        detail_mask = extract_monochrome_mask(self.test_img, sub_option='detail', detail_threshold=128)
        self.assertEqual(detail_mask.shape, (100, 100))
        self.assertEqual(detail_mask[50, 50], 255)
        self.assertEqual(detail_mask[10, 10], 0)

        white_bg_img = Image.new('RGBA', (100, 100), (255, 255, 255, 255))
        for x in range(30, 70):
            for y in range(30, 70):
                white_bg_img.putpixel((x, y), (0, 0, 0, 255))
        full_mask = extract_monochrome_mask(white_bg_img, sub_option='silhouette', use_full_image=True)
        self.assertEqual(full_mask[50, 50], 255)
        self.assertEqual(full_mask[10, 10], 0)

    def test_trace_monochrome_silhouette(self):
        from listimage.svg_services import trace_monochrome

        svg_str, stats = trace_monochrome(
            self.test_img,
            sub_option='silhouette',
            color='#ff0000',
            preset='balanced',
            square_canvas=False
        )

        self.assertIn('<svg', svg_str)
        self.assertIn('</svg>', svg_str)
        self.assertIn('shape-rendering="geometricPrecision"', svg_str)
        self.assertIn('preserveAspectRatio="xMidYMid meet"', svg_str)
        self.assertIn('fill="#ff0000"', svg_str)
        self.assertIn('<path', svg_str)
        self.assertIn('<title>', svg_str)
        self.assertIn('<desc>', svg_str)

        self.assertGreaterEqual(stats['path_count'], 1)
        self.assertIn('#ff0000', stats['colors'])
        self.assertFalse(stats['warn_large'])

    def test_trace_monochrome_square_canvas_and_bg(self):
        from listimage.svg_services import trace_monochrome

        rect_img = Image.new('RGBA', (100, 50), (0, 0, 0, 0))
        for x in range(20, 80):
            for y in range(10, 40):
                rect_img.putpixel((x, y), (10, 10, 10, 255))

        svg_str, stats = trace_monochrome(
            rect_img,
            sub_option='silhouette',
            square_canvas=True,
            bg_color='white'
        )

        self.assertIn('<svg', svg_str)
        self.assertIn('viewBox="0 0 ', svg_str)
        import re
        vb_match = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg_str)
        self.assertIsNotNone(vb_match)
        vb_w, vb_h = vb_match.groups()
        self.assertEqual(vb_w, vb_h)
        self.assertIn('fill="#ffffff"', svg_str)

    def test_sanitize_svg_strips_disallowed_and_script(self):
        from listimage.svg_services import sanitize_svg, SvgTracingError

        malicious_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
            <script>alert('xss')</script>
            <image href="test.jpg" />
            <foreignObject><div>test</div></foreignObject>
            <filter id="blur"><feGaussianBlur stdDeviation="2"/></filter>
            <path d="M 0,0 L 10,10 Z" fill="#000" onclick="alert(1)" />
        </svg>"""

        cleaned = sanitize_svg(malicious_svg)
        self.assertNotIn('<script', cleaned)
        self.assertNotIn('<image', cleaned)
        self.assertNotIn('<foreignObject', cleaned)
        self.assertNotIn('<filter', cleaned)
        self.assertNotIn('onclick', cleaned)
        self.assertIn('<path', cleaned)
        self.assertIn('shape-rendering="geometricPrecision"', cleaned)

        with self.assertRaises(SvgTracingError):
            sanitize_svg("<svg><unclosed></svg>")

    def test_get_svg_stats(self):
        from listimage.svg_services import get_svg_stats

        svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
            <path d="M 0,0 L 10,10 Z" fill="#ff0000" />
            <path d="M 20,20 L 30,30 Z" fill="#00ff00" />
        </svg>"""
        stats = get_svg_stats(svg)
        self.assertEqual(stats['path_count'], 2)
        self.assertEqual(stats['color_count'], 2)
        self.assertIn('#ff0000', stats['colors'])
        self.assertIn('#00ff00', stats['colors'])
        self.assertFalse(stats['warn_large'])


class Stage3ColorAndHybridTests(TestCase):
    """Tests Stage 3: Colour and Hybrid vectorization, palette quantization, recoloring, and near-white removal."""

    def setUp(self):
        self.multicolor_img = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
        for x in range(10, 40):
            for y in range(10, 50):
                self.multicolor_img.putpixel((x, y), (220, 20, 20, 255))
        for x in range(50, 70):
            for y in range(20, 50):
                self.multicolor_img.putpixel((x, y), (20, 30, 220, 255))
        for x in range(70, 85):
            for y in range(60, 75):
                self.multicolor_img.putpixel((x, y), (250, 250, 250, 255))

    def test_quantize_palette_kmeans(self):
        from listimage.svg_services import quantize_palette_kmeans

        indices, palette, quant_rgb = quantize_palette_kmeans(
            self.multicolor_img,
            n_colors=3,
            use_full_image=False
        )

        self.assertLessEqual(len(palette), 3)
        self.assertGreaterEqual(len(palette), 2)
        self.assertEqual(indices.shape, (100, 100))
        self.assertEqual(indices[0, 0], -1)
        self.assertEqual(indices[20, 20], 0)
        for c in palette:
            self.assertTrue(c.startswith('#'))
            self.assertEqual(len(c), 7)

    def test_trace_full_color_and_palette_index(self):
        from listimage.svg_services import trace_full_color

        svg_doc, stats, palette = trace_full_color(
            self.multicolor_img,
            n_colors=3,
            preset='balanced'
        )

        self.assertIn('<svg', svg_doc)
        self.assertIn('data-palette-index="', svg_doc)
        self.assertGreaterEqual(stats['path_count'], 2)
        self.assertGreaterEqual(stats['color_count'], 2)
        self.assertIn('shape-rendering="geometricPrecision"', svg_doc)

    def test_apply_palette_recoloring(self):
        from listimage.svg_services import apply_palette_recoloring

        sample_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
            <path data-palette-index="0" d="M 10,10 L 20,20 Z" fill="#ff0000" />
            <path data-palette-index="1" d="M 30,30 L 40,40 Z" fill="#0000ff" />
        </svg>"""

        recolored, stats = apply_palette_recoloring(sample_svg, {0: '#ff00ff'})
        self.assertIn('fill="#ff00ff"', recolored)
        self.assertIn('fill="#0000ff"', recolored)
        self.assertNotIn('fill="#ff0000"', recolored)

        pruned, stats_pruned = apply_palette_recoloring(sample_svg, {1: None})
        self.assertEqual(stats_pruned['path_count'], 1)
        self.assertNotIn('data-palette-index="1"', pruned)

    def test_remove_near_white(self):
        from listimage.svg_services import apply_palette_recoloring

        svg_with_white = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
            <path data-palette-index="0" d="M 10,10 L 20,20 Z" fill="#112233" />
            <path data-palette-index="1" d="M 30,30 L 40,40 Z" fill="#ffffff" />
            <path data-palette-index="2" d="M 50,50 L 60,60 Z" fill="#fafafa" />
        </svg>"""

        cleaned, stats = apply_palette_recoloring(
            svg_with_white,
            palette_map={},
            remove_near_white=True,
            near_white_threshold=245
        )
        self.assertEqual(stats['path_count'], 1)
        self.assertIn('fill="#112233"', cleaned)
        self.assertNotIn('fill="#ffffff"', cleaned)
        self.assertNotIn('fill="#fafafa"', cleaned)

    def test_trace_hybrid(self):
        from listimage.svg_services import trace_hybrid

        hybrid_svg, stats, palette = trace_hybrid(
            self.multicolor_img,
            kept_indices=[0],
            monochrome_color='#333333',
            n_colors=3
        )

        self.assertIn('<svg', hybrid_svg)
        self.assertIn('data-palette-index="', hybrid_svg)
        self.assertIn('fill="#333333"', hybrid_svg)

    def test_trace_image_to_svg_unified(self):
        from listimage.svg_services import trace_image_to_svg

        svg1, stats1, pal1 = trace_image_to_svg(self.multicolor_img, color_mode='full', n_colors=3)
        self.assertGreaterEqual(stats1['path_count'], 2)

        svg2, stats2, pal2 = trace_image_to_svg(self.multicolor_img, color_mode='hybrid', monochrome_color='#000000')
        self.assertIn('fill="#000000"', svg2)

        svg3, stats3, pal3 = trace_image_to_svg(self.multicolor_img, color_mode='monochrome', color='#123456')
        self.assertIn('fill="#123456"', svg3)


class Stage4WizardUITests(TestCase):
    """Tests Stage 4: SVG Wizard UI, endpoints, background worker, and cooperative cancellation."""

    def setUp(self):
        from projectauth.test_helpers import grant_test_client_app_access

        self.client_a = Client()
        self.client_b = Client()
        grant_test_client_app_access(self.client_a, "listimage", username="listimage_user_a")
        grant_test_client_app_access(self.client_b, "listimage", username="listimage_user_b")

    def _create_sample_upload(self):
        img = Image.new('RGB', (200, 200), color=(50, 150, 250))
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return SimpleUploadedFile("vector_source.png", buf.read(), content_type="image/png")

    def test_svg_start_get_renders_upload_wizard(self):
        res = self.client_a.get(reverse('listimage:svg_start'))
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, 'listimage/svg_wizard.html')
        self.assertContains(res, 'Image to SVG Vector Converter')

    @patch('listimage.svg_views.dispatch_job')
    def test_svg_start_post_creates_svg_job(self, mock_dispatch):
        upload_file = self._create_sample_upload()
        res = self.client_a.post(
            reverse('listimage:svg_start'),
            {'image': upload_file, 'color_mode': 'monochrome'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        job_id = data['job_id']

        job = ImageJob.objects.get(id=job_id)
        self.assertEqual(job.kind, ImageJob.Kind.SVG)
        self.assertEqual(job.status, ImageJob.Status.QUEUED)
        mock_dispatch.assert_called_once_with(str(job.id))

        job.cleanup_files()
        job.delete()

    @patch('listimage.svg_views.dispatch_job')
    def test_svg_from_raster_entry_point(self, mock_dispatch):
        owner = "user:1"
        raster_job = ImageJob.objects.create(
            owner=owner,
            kind=ImageJob.Kind.RASTER,
            original_filename="raster.png",
            status=ImageJob.Status.DONE
        )
        raster_job.workspace_path.mkdir(parents=True, exist_ok=True)
        (raster_job.workspace_path / 'cutout.png').write_bytes(b'FAKE_PNG_BYTES')

        with patch('listimage.svg_views._get_request_owner', return_value=owner):
            res = self.client_a.post(
                reverse('listimage:svg_from_raster', args=[raster_job.id]),
                HTTP_X_REQUESTED_WITH='XMLHttpRequest'
            )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        svg_job_id = data['job_id']

        svg_job = ImageJob.objects.get(id=svg_job_id)
        self.assertEqual(svg_job.kind, ImageJob.Kind.SVG)
        self.assertTrue((svg_job.workspace_path / 'cutout.png').exists())

        raster_job.cleanup_files()
        raster_job.delete()
        svg_job.cleanup_files()
        svg_job.delete()

    def test_svg_options_ownership_check(self):
        owner = "user:1"
        job = ImageJob.objects.create(
            owner=owner,
            kind=ImageJob.Kind.SVG,
            original_filename="test.png",
            status=ImageJob.Status.DONE
        )
        res_b = self.client_b.get(reverse('listimage:svg_options', args=[job.id]))
        self.assertEqual(res_b.status_code, 404)

        with patch('listimage.svg_views._get_request_owner', return_value=owner):
            res_a = self.client_a.get(reverse('listimage:svg_options', args=[job.id]))
        self.assertEqual(res_a.status_code, 200)

        job.cleanup_files()
        job.delete()

    @patch('listimage.svg_views.dispatch_job')
    def test_svg_render_updates_params_and_queues(self, mock_dispatch):
        owner = "user:1"
        job = ImageJob.objects.create(
            owner=owner,
            kind=ImageJob.Kind.SVG,
            status=ImageJob.Status.DONE,
            params={'color_mode': 'monochrome'}
        )
        render_payload = {
            'color_mode': 'full',
            'n_colors': 12,
            'preset': 'detailed',
            'square_canvas': True,
        }
        with patch('listimage.svg_views._get_request_owner', return_value=owner):
            res = self.client_a.post(
                reverse('listimage:svg_render', args=[job.id]),
                data=json.dumps(render_payload),
                content_type='application/json'
            )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])

        job.refresh_from_db()
        self.assertEqual(job.params['color_mode'], 'full')
        self.assertEqual(job.params['n_colors'], 12)
        self.assertEqual(job.params['preset'], 'detailed')
        self.assertTrue(job.params['square_canvas'])
        self.assertEqual(job.status, ImageJob.Status.QUEUED)
        mock_dispatch.assert_called_once_with(str(job.id))

        job.cleanup_files()
        job.delete()

    def test_svg_preview_and_download_views(self):
        owner = "user:1"
        job = ImageJob.objects.create(
            owner=owner,
            kind=ImageJob.Kind.SVG,
            status=ImageJob.Status.DONE
        )
        job.workspace_path.mkdir(parents=True, exist_ok=True)
        svg_content = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><path d="M0,0 L10,10 Z"/></svg>'
        (job.workspace_path / 'output.svg').write_bytes(svg_content)

        with patch('listimage.svg_views._get_request_owner', return_value=owner):
            res_preview = self.client_a.get(reverse('listimage:svg_preview', args=[job.id]))
        self.assertEqual(res_preview.status_code, 200)
        self.assertEqual(res_preview['Content-Type'], 'image/svg+xml')
        self.assertEqual(res_preview['X-Content-Type-Options'], 'nosniff')

        with patch('listimage.svg_views._get_request_owner', return_value=owner):
            res_download = self.client_a.get(reverse('listimage:svg_download', args=[job.id]))
        self.assertEqual(res_download.status_code, 200)
        self.assertEqual(res_download['Content-Type'], 'image/svg+xml')
        self.assertIn('attachment;', res_download['Content-Disposition'])
        self.assertIn(f"listimage-{str(job.id)[:8]}.svg", res_download['Content-Disposition'])

        job.cleanup_files()
        job.delete()

    def test_svg_cancel_deletes_job_and_redirects(self):
        owner = "user:1"
        job = ImageJob.objects.create(
            owner=owner,
            kind=ImageJob.Kind.SVG,
            status=ImageJob.Status.PROCESSING
        )
        job_id = str(job.id)

        with patch('listimage.svg_views._get_request_owner', return_value=owner):
            res = self.client_a.post(
                reverse('listimage:svg_cancel', args=[job.id]),
                HTTP_X_REQUESTED_WITH='XMLHttpRequest'
            )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['redirect_url'], reverse('listimage:index'))

        self.assertFalse(ImageJob.objects.filter(id=job_id).exists())

    def test_executor_runs_svg_worker(self):
        from listimage.executor import _run_job_worker

        owner = "user:1"
        job = ImageJob.objects.create(
            owner=owner,
            kind=ImageJob.Kind.SVG,
            status=ImageJob.Status.QUEUED,
            params={
                'color_mode': 'monochrome',
                'sub_option': 'silhouette',
                'color': '#ff0000',
                'use_full_image': True
            }
        )
        job.workspace_path.mkdir(parents=True, exist_ok=True)
        img = Image.new('RGB', (80, 80), color=(10, 10, 10))
        img.save(job.workspace_path / 'original.png')

        _run_job_worker(str(job.id))

        job.refresh_from_db()
        self.assertEqual(job.status, ImageJob.Status.DONE)
        self.assertTrue((job.workspace_path / 'output.svg').exists())
        self.assertIn('svg_stats', job.params)

        job.cleanup_files()
        job.delete()


class Stage5ColorEditingTests(TestCase):
    """Tests Stage 5: Colour Editing UI, live recoloring sync endpoint, undo, near-white removal, and static assets."""

    def setUp(self):
        from projectauth.test_helpers import grant_test_client_app_access

        self.client = Client()
        grant_test_client_app_access(self.client, "listimage", username="listimage_user_stage5")

    def test_svg_recolor_endpoint_swaps_colors(self):
        owner = "user:1"
        job = ImageJob.objects.create(
            owner=owner,
            kind=ImageJob.Kind.SVG,
            status=ImageJob.Status.DONE,
            params={'palette': ['#ff0000', '#00ff00']}
        )
        job.workspace_path.mkdir(parents=True, exist_ok=True)
        svg_xml = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            '<path data-palette-index="0" d="M 0,0 L 10,10 Z" fill="#ff0000"/>'
            '<path data-palette-index="1" d="M 20,20 L 30,30 Z" fill="#00ff00"/>'
            '</svg>'
        )
        (job.workspace_path / 'output.svg').write_text(svg_xml, encoding='utf-8')

        recolor_payload = {
            'palette_map': {'0': '#123456'}
        }
        with patch('listimage.svg_views._get_request_owner', return_value=owner):
            res = self.client.post(
                reverse('listimage:svg_recolor', args=[job.id]),
                data=json.dumps(recolor_payload),
                content_type='application/json'
            )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])

        updated_svg = (job.workspace_path / 'output.svg').read_text(encoding='utf-8')
        self.assertIn('fill="#123456"', updated_svg)
        self.assertIn('fill="#00ff00"', updated_svg)
        self.assertNotIn('fill="#ff0000"', updated_svg)

        job.cleanup_files()
        job.delete()

    def test_svg_recolor_prunes_near_white_and_transparent(self):
        owner = "user:1"
        job = ImageJob.objects.create(
            owner=owner,
            kind=ImageJob.Kind.SVG,
            status=ImageJob.Status.DONE
        )
        job.workspace_path.mkdir(parents=True, exist_ok=True)
        svg_xml = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            '<path data-palette-index="0" d="M 0,0 L 10,10 Z" fill="#222222"/>'
            '<path data-palette-index="1" d="M 20,20 L 30,30 Z" fill="#fcfcfc"/>'
            '<path data-palette-index="2" d="M 40,40 L 50,50 Z" fill="#444444"/>'
            '</svg>'
        )
        (job.workspace_path / 'output.svg').write_text(svg_xml, encoding='utf-8')

        recolor_payload = {
            'palette_map': {'2': None},
            'remove_near_white': True
        }
        with patch('listimage.svg_views._get_request_owner', return_value=owner):
            res = self.client.post(
                reverse('listimage:svg_recolor', args=[job.id]),
                data=json.dumps(recolor_payload),
                content_type='application/json'
            )
        self.assertEqual(res.status_code, 200)

        updated_svg = (job.workspace_path / 'output.svg').read_text(encoding='utf-8')
        self.assertIn('fill="#222222"', updated_svg)
        self.assertNotIn('fill="#fcfcfc"', updated_svg)
        self.assertNotIn('data-palette-index="2"', updated_svg)

        job.cleanup_files()
        job.delete()

    def test_static_assets_exist_and_contain_palette_logic(self):
        js_path = Path(settings.BASE_DIR) / 'static' / 'listimage' / 'listimage_svg.js'
        css_path = Path(settings.BASE_DIR) / 'static' / 'listimage' / 'listimage_svg.css'

        self.assertTrue(js_path.exists())
        self.assertTrue(css_path.exists())

        js_content = js_path.read_text(encoding='utf-8')
        css_content = css_path.read_text(encoding='utf-8')

        self.assertIn('updateSvgDomFills', js_content)
        self.assertIn('pushUndoState', js_content)
        self.assertIn('applyLiveColor', js_content)
        self.assertIn('isNearWhite', js_content)
        self.assertIn('selectSwatch', js_content)

        self.assertIn('.li-svg-swatch', css_content)
        self.assertIn('.li-swatch-editor-card', css_content)
        self.assertIn('.is-transparent', css_content)


class Stage6SaveCancelCleanupTests(TestCase):
    """Tests Stage 6: JS blob save download headers, post-download cleanup, cancel everywhere, and cleanup command."""

    def setUp(self):
        from projectauth.test_helpers import grant_test_client_app_access

        self.client = Client()
        grant_test_client_app_access(self.client, "listimage", username="listimage_user_stage6")

    def test_existing_cleanup_endpoint_deletes_svg_job_and_redirects(self):
        owner = "user:1"
        job = ImageJob.objects.create(
            owner=owner,
            kind=ImageJob.Kind.SVG,
            status=ImageJob.Status.DONE
        )
        job.workspace_path.mkdir(parents=True, exist_ok=True)
        (job.workspace_path / 'output.svg').write_text('<svg></svg>')
        job_id = str(job.id)

        with patch('listimage.views._get_request_owner', return_value=owner):
            res = self.client.post(
                reverse('listimage:cleanup', args=[job.id]),
                HTTP_X_REQUESTED_WITH='XMLHttpRequest'
            )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['redirect_url'], reverse('listimage:index'))

        self.assertFalse(ImageJob.objects.filter(id=job_id).exists())
        self.assertFalse(job.workspace_path.exists())

    def test_svg_download_attachment_headers_and_nosniff(self):
        owner = "user:1"
        job = ImageJob.objects.create(
            owner=owner,
            kind=ImageJob.Kind.SVG,
            status=ImageJob.Status.DONE
        )
        job.workspace_path.mkdir(parents=True, exist_ok=True)
        (job.workspace_path / 'output.svg').write_text('<svg viewBox="0 0 10 10"><path d="M0,0 Z"/></svg>')

        with patch('listimage.svg_views._get_request_owner', return_value=owner):
            res = self.client.get(reverse('listimage:svg_download', args=[job.id]))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res['Content-Type'], 'image/svg+xml')
        self.assertEqual(res['X-Content-Type-Options'], 'nosniff')
        self.assertIn(f'attachment; filename="listimage-{str(job.id)[:8]}.svg"', res['Content-Disposition'])

        job.cleanup_files()
        job.delete()

    def test_cleanup_management_command_prunes_expired_svg_jobs(self):
        from datetime import timedelta
        from django.core.management import call_command
        from django.utils import timezone

        expired_svg = ImageJob.objects.create(
            owner='test_owner',
            kind=ImageJob.Kind.SVG,
            status=ImageJob.Status.DONE
        )
        expired_svg.created_at = timezone.now() - timedelta(minutes=120)
        expired_svg.save(update_fields=['created_at'])
        expired_svg.workspace_path.mkdir(parents=True, exist_ok=True)
        (expired_svg.workspace_path / 'output.svg').write_text('<svg></svg>')

        fresh_svg = ImageJob.objects.create(
            owner='test_owner',
            kind=ImageJob.Kind.SVG,
            status=ImageJob.Status.DONE
        )
        fresh_svg.workspace_path.mkdir(parents=True, exist_ok=True)
        (fresh_svg.workspace_path / 'output.svg').write_text('<svg></svg>')

        orphan_dir = settings.BASE_DIR / 'listimage' / 'workspace' / '99999999-9999-9999-9999-999999999999'
        orphan_dir.mkdir(parents=True, exist_ok=True)
        (orphan_dir / 'orphan.svg').write_text('<svg></svg>')

        out = io.StringIO()
        call_command('cleanup_listimage', '--max-age-minutes=60', '--kind=svg', stdout=out)

        self.assertFalse(ImageJob.objects.filter(id=expired_svg.id).exists())
        self.assertFalse(expired_svg.workspace_path.exists())

        self.assertTrue(ImageJob.objects.filter(id=fresh_svg.id).exists())
        self.assertTrue(fresh_svg.workspace_path.exists())

        self.assertFalse(orphan_dir.exists())

        fresh_svg.cleanup_files()
        fresh_svg.delete()


class ComprehensiveSvgFeatureSpecificationTests(TestCase):
    """
    Dedicated tests verifying all 10 explicit SVG feature specifications:
    1. Output is well-formed XML with viewBox and no <script>, <image>, or <foreignObject>.
    2. Aspect ratio of viewBox matches traced content without squashing (wide and tall images).
    3. Monochrome output has exactly 1 fill colour; Full colour has <= N colours; Hybrid applies mapping (kept, custom, mono, removed).
    4. Large image downscaled to MAX_TRACE_PX, small image upscaled 2x, neither distorted.
    5. Transparent background is not traced as a shape.
    6. Cancel (idle and during processing) deletes files/DB row and redirects to listimage:index.
    7. Save followed by cleanup deletes upload, cutout, SVG and DB row, and redirects to listimage:index.
    8. Cross-user access returns 404; Queue limits and one-active-job rule apply to svg jobs.
    9. Existing raster tests/pipeline pass unchanged.
    10. Optional (skipped if cairosvg missing): rasterise SVG at 3 sizes and verify overlap with source mask.
    """

    def setUp(self):
        from projectauth.test_helpers import grant_test_client_app_access

        self.client_a = Client()
        self.client_b = Client()
        grant_test_client_app_access(self.client_a, "listimage", username="svg_spec_user_a")
        grant_test_client_app_access(self.client_b, "listimage", username="svg_spec_user_b")

    def _get_owner(self, client):
        user_id = client.session.get('_auth_user_id')
        if user_id:
            return f"user:{user_id}"
        return f"session:{client.session.session_key}"

    def test_spec_1_output_is_well_formed_xml_with_viewbox_and_no_disallowed_tags(self):
        """1. Output is well-formed XML with a viewBox and no <script>, <image> or foreignObject."""
        import lxml.etree as etree
        from listimage.svg_services import trace_monochrome, sanitize_svg

        img = Image.new('RGBA', (200, 200), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle([40, 40, 160, 160], fill=(255, 0, 0, 255))

        svg_content, _stats = trace_monochrome(img, preset='balanced', sub_option='silhouette')

        root = etree.fromstring(svg_content.encode('utf-8'))
        self.assertTrue(root.tag.endswith('svg'))

        view_box = root.get('viewBox')
        self.assertIsNotNone(view_box)
        vb_parts = view_box.split()
        self.assertEqual(len(vb_parts), 4)

        self.assertEqual(root.get('preserveAspectRatio'), 'xMidYMid meet')
        self.assertEqual(root.get('shape-rendering'), 'geometricPrecision')

        self.assertEqual(len(root.xpath('//*[local-name()="script"]')), 0)
        self.assertEqual(len(root.xpath('//*[local-name()="image"]')), 0)
        self.assertEqual(len(root.xpath('//*[local-name()="foreignObject"]')), 0)

        dirty_svg = (
            '<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">'
            '<script>alert("xss")</script>'
            '<image href="data:image/png;base64,123" width="50" height="50"/>'
            '<foreignObject width="100" height="100"><div>evil</div></foreignObject>'
            '<path d="M10,10 L90,90 Z" fill="#000000"/>'
            '</svg>'
        )
        cleaned_svg = sanitize_svg(dirty_svg)
        clean_root = etree.fromstring(cleaned_svg.encode('utf-8'))
        self.assertEqual(len(clean_root.xpath('//*[local-name()="script"]')), 0)
        self.assertEqual(len(clean_root.xpath('//*[local-name()="image"]')), 0)
        self.assertEqual(len(clean_root.xpath('//*[local-name()="foreignObject"]')), 0)
        self.assertEqual(len(clean_root.xpath('//*[local-name()="path"]')), 1)

    def test_spec_2_viewbox_aspect_ratio_matches_traced_content_without_squashing(self):
        """2. Aspect ratio of the viewBox matches the traced content (no squash). A very wide and a very tall test image both keep their ratio."""
        import lxml.etree as etree
        from listimage.svg_services import trace_monochrome

        wide_img = Image.new('RGBA', (600, 150), (0, 0, 0, 0))
        draw_w = ImageDraw.Draw(wide_img)
        draw_w.rectangle([50, 20, 550, 130], fill=(0, 255, 0, 255))

        svg_wide, _stats_w = trace_monochrome(wide_img, preset='balanced', square_canvas=False)
        root_w = etree.fromstring(svg_wide.encode('utf-8'))
        vb_w = [float(x) for x in root_w.get('viewBox').split()]
        self.assertAlmostEqual(vb_w[2] / vb_w[3], 600.0 / 150.0, places=2)
        self.assertEqual(root_w.get('preserveAspectRatio'), 'xMidYMid meet')

        tall_img = Image.new('RGBA', (150, 600), (0, 0, 0, 0))
        draw_t = ImageDraw.Draw(tall_img)
        draw_t.rectangle([20, 50, 130, 550], fill=(0, 0, 255, 255))

        svg_tall, _stats_t = trace_monochrome(tall_img, preset='balanced', square_canvas=False)
        root_t = etree.fromstring(svg_tall.encode('utf-8'))
        vb_t = [float(x) for x in root_t.get('viewBox').split()]
        self.assertAlmostEqual(vb_t[2] / vb_t[3], 150.0 / 600.0, places=2)
        self.assertEqual(root_t.get('preserveAspectRatio'), 'xMidYMid meet')

    def test_spec_3_color_modes_fill_count_and_hybrid_mapping(self):
        """3. Monochrome output has exactly one fill colour. Full colour has at most N colours. Hybrid applies the mapping (kept, custom, mono, removed)."""
        import lxml.etree as etree
        from listimage.svg_services import trace_monochrome, trace_full_color, apply_palette_recoloring

        # (a) Monochrome has exactly one fill colour
        img = Image.new('RGBA', (200, 200), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([40, 40, 160, 160], fill=(100, 150, 200, 255))

        svg_mono, _stats_m = trace_monochrome(img, color='#e11d48')
        root_mono = etree.fromstring(svg_mono.encode('utf-8'))
        paths_mono = root_mono.xpath('//*[local-name()="path"]')
        fills_mono = {p.get('fill') for p in paths_mono if p.get('fill') and p.get('fill') != 'none'}
        self.assertEqual(fills_mono, {'#e11d48'})

        # (b) Full colour has at most N colours
        multi_img = Image.new('RGBA', (200, 200), (0, 0, 0, 0))
        draw_m = ImageDraw.Draw(multi_img)
        draw_m.rectangle([10, 10, 90, 90], fill=(255, 0, 0, 255))
        draw_m.rectangle([110, 10, 190, 90], fill=(0, 255, 0, 255))
        draw_m.rectangle([10, 110, 90, 190], fill=(0, 0, 255, 255))
        draw_m.rectangle([110, 110, 190, 190], fill=(255, 255, 0, 255))

        svg_col, _stats_c, palette = trace_full_color(multi_img, n_colors=3)
        root_col = etree.fromstring(svg_col.encode('utf-8'))
        paths_col = root_col.xpath('//*[local-name()="path"]')
        fills_col = {p.get('fill') for p in paths_col if p.get('fill') and p.get('fill') != 'none'}
        self.assertLessEqual(len(fills_col), 3)

        # (c) Hybrid applies mapping (kept, custom, mono, removed)
        sample_svg = (
            '<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">'
            '<path data-palette-index="0" fill="#ff0000" d="M0,0 L10,0 L10,10 Z"/>'
            '<path data-palette-index="1" fill="#00ff00" d="M20,0 L30,0 L30,10 Z"/>'
            '<path data-palette-index="2" fill="#0000ff" d="M40,0 L50,0 L50,10 Z"/>'
            '<path data-palette-index="3" fill="#ffff00" d="M60,0 L70,0 L70,10 Z"/>'
            '</svg>'
        )
        palette_map = {
            0: '#ff0000',               # kept original
            1: '#123456',               # custom
            2: '#000000',               # mono
            3: None,                    # removed (transparent)
        }
        recolored, stats_rec = apply_palette_recoloring(sample_svg, palette_map)
        root_rec = etree.fromstring(recolored.encode('utf-8'))
        paths_rec = root_rec.xpath('//*[local-name()="path"]')

        p0 = root_rec.xpath('//*[@data-palette-index="0"]')
        p1 = root_rec.xpath('//*[@data-palette-index="1"]')
        p2 = root_rec.xpath('//*[@data-palette-index="2"]')
        p3 = root_rec.xpath('//*[@data-palette-index="3"]')

        self.assertEqual(len(p0), 1)
        self.assertEqual(p0[0].get('fill'), '#ff0000')

        self.assertEqual(len(p1), 1)
        self.assertEqual(p1[0].get('fill'), '#123456')

        self.assertEqual(len(p2), 1)
        self.assertEqual(p2[0].get('fill'), '#000000')

        self.assertEqual(len(p3), 0)
        self.assertEqual(len(paths_rec), 3)

    def test_spec_4_large_image_downscaled_small_image_upscaled_neither_distorted(self):
        """4. Large image is downscaled for tracing. Small image is upscaled. Neither is distorted."""
        from listimage.svg_services import prepare_trace_source

        # Large image: 3200 x 1600 (aspect ratio 2.0)
        large_img = Image.new('RGBA', (3200, 1600), (255, 0, 0, 255))
        downscaled = prepare_trace_source(large_img, max_dim=2000)
        self.assertEqual(downscaled.size, (2000, 1000))
        self.assertAlmostEqual(downscaled.width / downscaled.height, 3200.0 / 1600.0, places=5)

        # Small image: 300 x 150 (aspect ratio 2.0, max dim 300 < 800)
        small_img = Image.new('RGBA', (300, 150), (255, 0, 0, 255))
        upscaled = prepare_trace_source(small_img, max_dim=2000)
        self.assertEqual(upscaled.size, (600, 300))
        self.assertAlmostEqual(upscaled.width / upscaled.height, 300.0 / 150.0, places=5)

    def test_spec_5_transparent_background_not_traced_as_shape(self):
        """5. Transparent background is not traced as a shape."""
        import lxml.etree as etree
        from listimage.svg_services import trace_monochrome, trace_full_color

        img = Image.new('RGBA', (200, 200), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle([75, 75, 125, 125], fill=(255, 0, 0, 255))

        # Monochrome
        svg_mono, stats_m = trace_monochrome(img, preset='balanced')
        root_m = etree.fromstring(svg_mono.encode('utf-8'))
        paths_m = root_m.xpath('//*[local-name()="path"]')
        self.assertEqual(len(paths_m), 1)

        # Full colour
        svg_col, stats_c, _pal = trace_full_color(img, n_colors=4)
        root_c = etree.fromstring(svg_col.encode('utf-8'))
        paths_c = root_c.xpath('//*[local-name()="path"]')
        self.assertEqual(len(paths_c), 1)

        # Neither produces a background shape spanning the canvas
        for p in paths_m + paths_c:
            d = p.get('d', '')
            self.assertNotIn("0.0000,0.0000", d)
            self.assertNotIn("400.0000,400.0000", d)

    def test_spec_6_cancel_idle_and_during_processing_cleans_up_and_redirects(self):
        """6. Cancel (idle and during processing) deletes files and the DB row and redirects to listimage:index."""
        from listimage.executor import is_job_cancelled

        owner = self._get_owner(self.client_a)

        # (a) Idle cancel
        idle_job = ImageJob.objects.create(
            owner=owner,
            kind=ImageJob.Kind.SVG,
            status=ImageJob.Status.DONE
        )
        idle_job.workspace_path.mkdir(parents=True, exist_ok=True)
        (idle_job.workspace_path / 'upload.png').write_bytes(b'upload data')
        (idle_job.workspace_path / 'output.svg').write_text('<svg></svg>')
        idle_id = str(idle_job.id)

        res_idle = self.client_a.post(reverse('listimage:svg_cancel', args=[idle_job.id]))
        self.assertEqual(res_idle.status_code, 302)
        self.assertEqual(res_idle['Location'], reverse('listimage:index'))
        self.assertFalse(ImageJob.objects.filter(id=idle_id).exists())
        self.assertFalse(idle_job.workspace_path.exists())

        # (b) Cancel during processing
        proc_job = ImageJob.objects.create(
            owner=owner,
            kind=ImageJob.Kind.SVG,
            status=ImageJob.Status.PROCESSING
        )
        proc_job.workspace_path.mkdir(parents=True, exist_ok=True)
        (proc_job.workspace_path / 'temp.bin').write_bytes(b'intermediate')
        proc_id = str(proc_job.id)

        res_proc = self.client_a.post(reverse('listimage:svg_cancel', args=[proc_job.id]))
        self.assertEqual(res_proc.status_code, 302)
        self.assertEqual(res_proc['Location'], reverse('listimage:index'))
        self.assertFalse(ImageJob.objects.filter(id=proc_id).exists())
        self.assertFalse(proc_job.workspace_path.exists())
        self.assertTrue(is_job_cancelled(proc_id))

    def test_spec_7_save_followed_by_cleanup_cleans_workspace_db_and_redirects(self):
        """7. Save followed by cleanup deletes upload, cutout, SVG and DB row, and redirects to listimage:index."""
        owner = self._get_owner(self.client_a)

        job = ImageJob.objects.create(
            owner=owner,
            kind=ImageJob.Kind.SVG,
            status=ImageJob.Status.DONE
        )
        job.workspace_path.mkdir(parents=True, exist_ok=True)
        (job.workspace_path / 'upload.png').write_bytes(b'upload content')
        (job.workspace_path / 'cutout.png').write_bytes(b'cutout content')
        (job.workspace_path / 'output.svg').write_text('<svg viewBox="0 0 100 100"><path d="M0,0 Z"/></svg>')
        job_id = str(job.id)

        # Step 1: Save / download
        dl_res = self.client_a.get(reverse('listimage:svg_download', args=[job.id]))
        self.assertEqual(dl_res.status_code, 200)
        self.assertEqual(dl_res['Content-Type'], 'image/svg+xml')
        self.assertIn(f'attachment; filename="listimage-{job_id[:8]}.svg"', dl_res['Content-Disposition'])
        self.assertEqual(dl_res['X-Content-Type-Options'], 'nosniff')

        # Step 2: Post-download cleanup
        cl_res = self.client_a.post(reverse('listimage:cleanup', args=[job.id]))
        self.assertEqual(cl_res.status_code, 302)
        self.assertEqual(cl_res['Location'], reverse('listimage:index'))

        self.assertFalse(ImageJob.objects.filter(id=job_id).exists())
        self.assertFalse(job.workspace_path.exists())

    def test_spec_8_cross_user_access_returns_404_and_queue_limits_apply_to_svg(self):
        """8. Cross-user access returns 404. Queue limits and the one-active-job rule apply to svg jobs."""
        from listimage.executor import check_submission_limits

        owner_a = self._get_owner(self.client_a)
        owner_b = self._get_owner(self.client_b)

        job_a = ImageJob.objects.create(
            owner=owner_a,
            kind=ImageJob.Kind.SVG,
            status=ImageJob.Status.DONE
        )
        job_a.workspace_path.mkdir(parents=True, exist_ok=True)
        (job_a.workspace_path / 'output.svg').write_text('<svg></svg>')

        # Cross-user access returns 404
        endpoints = [
            ('get', reverse('listimage:svg_options', args=[job_a.id])),
            ('post', reverse('listimage:svg_render', args=[job_a.id])),
            ('get', reverse('listimage:svg_preview', args=[job_a.id])),
            ('get', reverse('listimage:svg_download', args=[job_a.id])),
            ('post', reverse('listimage:svg_cancel', args=[job_a.id])),
        ]
        for method, url in endpoints:
            res = getattr(self.client_b, method)(url)
            self.assertEqual(res.status_code, 404)

        # Queue limits and one-active-job rule apply to SVG jobs
        active_svg_job = ImageJob.objects.create(
            owner=owner_a,
            kind=ImageJob.Kind.SVG,
            status=ImageJob.Status.PROCESSING
        )
        can_submit, reason = check_submission_limits(owner_a)
        self.assertFalse(can_submit)
        self.assertIn("in progress", reason.lower())

        active_svg_job.cleanup_files()
        active_svg_job.delete()
        job_a.cleanup_files()
        job_a.delete()

    def test_spec_9_existing_raster_tests_and_pipeline_still_pass_unchanged(self):
        """9. Existing raster tests still pass unchanged."""
        owner = self._get_owner(self.client_a)

        raster_job = ImageJob.objects.create(
            owner=owner,
            kind=ImageJob.Kind.RASTER,
            status=ImageJob.Status.QUEUED
        )
        self.assertEqual(raster_job.kind, ImageJob.Kind.RASTER)

        # Pure white 2000x2000 canvas export with 10px constraining padding
        src_img = Image.new('RGBA', (400, 200), (0, 0, 0, 0))
        draw = ImageDraw.Draw(src_img)
        draw.rectangle([0, 0, 400, 200], fill=(255, 0, 0, 255))

        canvas, _trans, metrics = render_to_pure_white_canvas(src_img)
        self.assertEqual(canvas.size, (2000, 2000))
        self.assertEqual(canvas.getpixel((0, 0)), (255, 255, 255))
        self.assertEqual(metrics['constraining_side'], 'width')
        self.assertEqual(metrics['pad_left'], 10)
        self.assertEqual(metrics['pad_right'], 10)

        raster_job.cleanup_files()
        raster_job.delete()

    @unittest.skipUnless(HAS_CAIROSVG, "cairosvg is missing")
    def test_spec_10_optional_rasterise_svg_at_three_sizes_and_check_mask_overlap(self):
        """10. Optional (skipped if cairosvg is missing): rasterise the SVG at 3 sizes and check it overlaps the source mask closely at each size."""
        import cairosvg
        from listimage.svg_services import trace_monochrome

        src = Image.new('RGBA', (200, 200), (0, 0, 0, 0))
        draw = ImageDraw.Draw(src)
        draw.rectangle([50, 50, 150, 150], fill=(255, 0, 0, 255))
        src_alpha = np.array(src.split()[3]) > 0

        svg_str, _stats = trace_monochrome(src, preset='balanced', sub_option='silhouette')

        for size in (64, 256, 512):
            png_bytes = cairosvg.svg2png(bytestring=svg_str.encode('utf-8'), output_width=size, output_height=size)
            raster = Image.open(io.BytesIO(png_bytes)).convert('RGBA')
            raster_alpha = np.array(raster.split()[3]) > 0
            ref_alpha = np.array(Image.fromarray(src_alpha).resize((size, size), Image.Resampling.NEAREST))
            intersection = np.logical_and(raster_alpha, ref_alpha).sum()
            union = np.logical_or(raster_alpha, ref_alpha).sum()
            iou = intersection / max(union, 1)
            self.assertGreaterEqual(iou, 0.80)

    def test_spec_11_svg_import_and_from_raster_button_flow(self):
        """Verifies direct SVG upload and 'Make SVG from this' flow, ensuring scripts load and DOM elements exist."""
        owner = self._get_owner(self.client_a)

        # 1. Direct SVG upload page renders and includes listimage_svg.js
        start_res = self.client_a.get(reverse('listimage:svg_start'))
        self.assertEqual(start_res.status_code, 200)
        self.assertContains(start_res, 'listimage_svg.js')
        self.assertContains(start_res, 'liSvgUploadForm')
        self.assertContains(start_res, 'liSvgFileInput')

        # 2. Raster job with 'Make SVG from this' button
        raster_job = ImageJob.objects.create(
            owner=owner,
            kind=ImageJob.Kind.RASTER,
            status=ImageJob.Status.DONE,
            original_filename="sample.png",
            params={'original_dimensions': [400, 400]}
        )
        raster_job.workspace_path.mkdir(parents=True, exist_ok=True)
        img = Image.new('RGBA', (200, 200), (255, 0, 0, 255))
        img.save(raster_job.workspace_path / 'cutout.png', format='PNG')
        img.save(raster_job.workspace_path / 'original.png', format='PNG')

        # POST to svg_from_raster
        with patch('listimage.svg_views.dispatch_job'):
            fork_res = self.client_a.post(
                reverse('listimage:svg_from_raster', args=[raster_job.id]),
                HTTP_X_REQUESTED_WITH='XMLHttpRequest'
            )
        self.assertEqual(fork_res.status_code, 200)
        fork_data = fork_res.json()
        self.assertTrue(fork_data['success'])
        svg_job_id = fork_data['job_id']
        redirect_url = fork_data['redirect_url']

        # 3. Load options page for newly forked job (even before output.svg exists)
        opts_res = self.client_a.get(redirect_url)
        self.assertEqual(opts_res.status_code, 200)
        self.assertContains(opts_res, 'listimage_svg.js')
        self.assertContains(opts_res, 'id="liSvgObject"')
        self.assertContains(opts_res, 'id="liSvgPlaceholder"')
        self.assertContains(opts_res, 'id="liSvgProcessingBanner"')

        # Clean up jobs
        raster_job.cleanup_files()
        raster_job.delete()
        svg_job = ImageJob.objects.get(id=svg_job_id)
        svg_job.cleanup_files()
        svg_job.delete()

    def test_spec_12_transparent_png_preserves_coordinates_no_inversion_or_black_halo(self):
        """
        Regression test for uploaded transparent PNGs:
        - Ensures vtracer translate(tx, ty) transforms are baked into path coordinates (no top-left collage/crop).
        - Ensures monochrome binary masks are not inverted into a full-canvas black rectangle.
        - Ensures semi-transparent anti-aliased fringe does not introduce #000000 black halos or muddied colors.
        - Ensures use_full_image=True still respects existing transparent alpha pixels.
        """
        import re
        import lxml.etree as etree
        from listimage.svg_services import trace_image_to_svg

        img = Image.new('RGBA', (900, 900), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Anti-aliased halo fringe in semi-transparent alpha (should be de-fringed, never turned black)
        draw.rectangle([496, 296, 704, 604], fill=(120, 120, 120, 160))
        # Two saturated colored shapes far from (0, 0)
        draw.rectangle([500, 300, 700, 450], fill=(220, 20, 20, 255))
        draw.rectangle([500, 450, 700, 600], fill=(10, 90, 220, 255))

        token_num = re.compile(r'[-+]?(?:\d*\.\d+|\d+)')

        for color_mode in ('monochrome', 'full'):
            for full_img_flag in (False, True):
                svg_out, stats, palette = trace_image_to_svg(
                    img,
                    color_mode=color_mode,
                    n_colors=2,
                    color='#112233',
                    use_full_image=full_img_flag,
                )
                root = etree.fromstring(svg_out.encode('utf-8'))
                paths = root.xpath('//*[local-name()="path"]')
                self.assertGreaterEqual(len(paths), 1, f"No paths for {color_mode}, use_full_image={full_img_flag}")

                for p in paths:
                    # Transforms must be baked directly into d
                    self.assertIsNone(p.get('transform'))
                    d_str = p.get('d', '')
                    nums = [float(v) for v in token_num.findall(d_str)]
                    xs = nums[0::2]
                    ys = nums[1::2]
                    # Every shape lies in x ~ [490..710], y ~ [290..610]; must not collapse near 0 or span 0..900
                    self.assertGreater(min(xs), 450.0, f"Path shifted/inverted to left edge in {color_mode}: {d_str[:80]}")
                    self.assertGreater(min(ys), 250.0, f"Path shifted/inverted to top edge in {color_mode}: {d_str[:80]}")
                    self.assertLess(max(xs), 750.0)
                    self.assertLess(max(ys), 650.0)

                if color_mode == 'full':
                    # No black halo (#000000) generated from transparent/fringe border
                    self.assertNotIn('#000000', stats['colors'])

    def test_spec_13_executor_preserves_transparent_png_without_rembg(self):
        """Uploading an already-transparent PNG to SVG skips destructive neural rembg and preserves alpha."""
        from listimage.executor import _run_job_worker

        owner = self._get_owner(self.client_a)
        job = ImageJob.objects.create(
            owner=owner,
            kind=ImageJob.Kind.SVG,
            status=ImageJob.Status.QUEUED,
            params={'color_mode': 'full', 'n_colors': 4, 'use_full_image': False}
        )
        job.workspace_path.mkdir(parents=True, exist_ok=True)

        img = Image.new('RGBA', (300, 300), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([100, 100, 220, 220], fill=(10, 100, 210, 255))
        img.save(job.workspace_path / 'original.png', format='PNG')

        with patch('listimage.services.process_initial_job') as mock_rembg:
            _run_job_worker(str(job.id))
            mock_rembg.assert_not_called()

        job.refresh_from_db()
        self.assertEqual(job.status, ImageJob.Status.DONE)
        self.assertTrue((job.workspace_path / 'cutout.png').exists())
        self.assertTrue((job.workspace_path / 'output.svg').exists())

        job.cleanup_files()
        job.delete()

    def test_spec_14_svg_wizard_js_and_preset_defaults(self):
        """Verifies listimage_svg.js has no undefined symbol calls and svg_options renders preset defaults."""
        js_path = Path(settings.BASE_DIR) / 'static' / 'listimage' / 'listimage_svg.js'
        js_text = js_path.read_text(encoding='utf-8')
        self.assertNotIn('syncPreviewWithCurrentPalette', js_text)
        self.assertIn('PRESET_SLIDERS', js_text)

        owner = self._get_owner(self.client_a)
        job = ImageJob.objects.create(
            owner=owner,
            kind=ImageJob.Kind.SVG,
            status=ImageJob.Status.DONE,
            params={'preset': 'simple', 'color_mode': 'full', 'n_colors': 6}
        )
        res = self.client_a.get(reverse('listimage:svg_options', args=[job.id]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'value="16"')  # simple preset filter_speckle default
        self.assertNotContains(res, 'block extra_js')

        job.cleanup_files()
        job.delete()

    def test_spec_15_svg_preview_allows_sameorigin_framing(self):
        """svg_preview must return X-Frame-Options: SAMEORIGIN so <object type='image/svg+xml'> is not blocked by global DENY."""
        owner = self._get_owner(self.client_a)
        job = ImageJob.objects.create(
            owner=owner,
            kind=ImageJob.Kind.SVG,
            status=ImageJob.Status.DONE,
            params={'svg_stats': {'viewBox': '0 0 800 400'}}
        )
        job.workspace_path.mkdir(parents=True, exist_ok=True)
        (job.workspace_path / 'output.svg').write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 400"><path d="M0,0 L10,10 Z" fill="#000"/></svg>',
            encoding='utf-8'
        )

        res_preview = self.client_a.get(reverse('listimage:svg_preview', args=[job.id]))
        self.assertEqual(res_preview.status_code, 200)
        self.assertEqual(res_preview['Content-Type'], 'image/svg+xml')
        self.assertEqual(res_preview['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(res_preview.get('X-Frame-Options', '').upper(), 'SAMEORIGIN')

        res_opts = self.client_a.get(reverse('listimage:svg_options', args=[job.id]))
        self.assertEqual(res_opts.status_code, 200)
        self.assertContains(res_opts, 'id="liInitialViewBox" value="0 0 800 400"')

        job.cleanup_files()
        job.delete()



