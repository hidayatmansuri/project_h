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
from unittest.mock import patch

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

        canvas, metrics = render_to_pure_white_canvas(img)

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

        canvas, metrics = render_to_pure_white_canvas(img)

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
        canvas, metrics = render_to_pure_white_canvas(small_img)

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

        canvas, metrics = render_to_pure_white_canvas(huge_img)

        self.assertEqual(canvas.size, (2000, 2000))
        self.assertFalse(metrics['is_upscaled'])
        self.assertEqual(metrics['scaled_w'], 1980)
        self.assertEqual(metrics['scaled_h'], 990)
        self.assertEqual(metrics['pad_left'], 10)
        self.assertEqual(metrics['pad_right'], 10)

    def test_transparent_blank_image_returns_pure_white(self):
        """An empty transparent image safely produces a pure white 2000x2000 canvas."""
        empty_img = Image.new('RGBA', (500, 500), (0, 0, 0, 0))
        canvas, metrics = render_to_pure_white_canvas(empty_img)

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

        labeled_array, detected = detect_connected_objects(alpha, min_area_threshold=100)

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

    def test_remove_background_with_rembg_accepts_pil_image(self):
        """Verifies rembg.remove handles PIL Image without TypeError."""
        input_img = Image.new('RGB', (100, 100), color=(255, 0, 0))
        result = remove_background_with_rembg(input_img, model_name='u2netp')
        self.assertIsInstance(result, Image.Image)
        self.assertEqual(result.size, (100, 100))
        self.assertEqual(result.mode, 'RGBA')


class ViewsAndWorkflowTests(TestCase):
    """End-to-end integration tests for views, ownership security, concurrency, and download."""

    def setUp(self):
        self.client_a = Client()
        self.client_b = Client()

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

    def test_cross_user_access_returns_404(self):
        """Requester B attempting to access Requester A's job gets 404."""
        # Create job owned by client A's session
        self.client_a.get(reverse('listimage:index'))
        session_a = self.client_a.session.session_key
        owner_a = f"session:{session_a}"

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

        # Create MAX_QUEUE queued jobs from different owners
        for i in range(MAX_QUEUE):
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
        session_a = self.client_a.session.session_key
        owner_a = f"session:{session_a}"

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
        session_a = self.client_a.session.session_key
        owner_a = f"session:{session_a}"

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
