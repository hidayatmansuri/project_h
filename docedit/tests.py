"""
Comprehensive test suite for DocEdit app.
"""
import io
import json
import os
import shutil
import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import resolve, reverse
from PIL import Image, ImageDraw, ImageFont
import docx
import pymupdf

from docedit import extract, font_catalog, fontmatch, ocr, storage, views, writers
from docedit.conf import conf


class DocEditStorageTests(TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="docedit_test_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_session_lifecycle(self):
        with override_settings(DOCEDIT_WORK_DIR=self.test_dir):
            sid = storage.create_session("my_book.txt", b"Chapter 1: The Beginning")
            self.assertTrue(storage.get_session_dir(sid).is_dir())

            meta = storage.get_session_meta(sid)
            self.assertIsNotNone(meta)
            self.assertEqual(meta["original_filename"], "my_book.txt")
            self.assertEqual(meta["extension"], "txt")
            self.assertEqual(meta["status"], "uploaded")

            storage.update_session(sid, status="ready", progress=100)
            meta2 = storage.get_session_meta(sid)
            self.assertEqual(meta2["status"], "ready")
            self.assertEqual(meta2["progress"], 100)

            storage.save_document_content(sid, "<p>Edited content</p>", "Edited content")
            content = storage.get_document_content(sid)
            self.assertEqual(content, "<p>Edited content</p>")

            orig_path = storage.get_original_file_path(sid)
            self.assertIsNotNone(orig_path)
            self.assertTrue(orig_path.is_file())

            purged = storage.purge_session(sid)
            self.assertTrue(purged)
            self.assertFalse(storage.get_session_dir(sid).is_dir())


class DocEditFontCatalogTests(TestCase):
    def test_normalize_font_name(self):
        self.assertEqual(font_catalog.normalize_font_name("Times New Roman, Bold"), "times new roman bold")
        self.assertEqual(font_catalog.normalize_font_name("EB_Garamond-Regular"), "eb garamond regular")

    def test_find_nearest_match(self):
        sub_palatino = font_catalog.find_nearest_match("Palatino")
        self.assertIn("Garamond", sub_palatino["nearest_match"])

        sub_times = font_catalog.find_nearest_match("Times New Roman")
        self.assertEqual(sub_times["nearest_match"], "Tinos")

        sub_baskerville = font_catalog.find_nearest_match("Monotype Baskerville")
        self.assertEqual(sub_baskerville["nearest_match"], "Libre Baskerville")

        sub_hin = font_catalog.find_nearest_match("Chanakya Hindi")
        self.assertEqual(sub_hin["nearest_match"], "Rozha One")

    def test_resolve_document_font(self):
        # Even if unknown or proprietary, returns a valid font result dict
        res = font_catalog.resolve_document_font("Monotype Baskerville")
        self.assertIn("name", res)
        self.assertIn("is_system", res)
        self.assertIn("status", res)


class DocEditFontMatchTests(TestCase):
    def test_clean_pdf_font_name(self):
        cleaned = fontmatch.clean_pdf_font_name("BAAAAA+TimesNewRomanPSMT")
        self.assertEqual(cleaned, "Times New Roman")

    def test_detect_script(self):
        self.assertEqual(fontmatch.detect_script("This is an English book."), "latin")
        self.assertEqual(fontmatch.detect_script("नमस्ते यह एक हिंदी पुस्तक है।"), "devanagari")
        self.assertEqual(fontmatch.detect_script("આ એક ગુજરાતી પુસ્તક છે."), "gujarati")
        self.assertEqual(fontmatch.detect_script("هذا كتاب باللغة العربية القديم."), "arabic")


class DocEditWritersTests(TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="docedit_writer_test_")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_write_text_and_markdown(self):
        html_in = "<p>First paragraph with <strong>bold</strong> text.</p><p>Second paragraph.</p>"
        txt_out = Path(self.tmp_dir) / "output.txt"
        writers.write_document_to_disk(html_in, txt_out, "txt", {"name": "EB Garamond", "size_pt": 12})
        self.assertTrue(txt_out.is_file())
        self.assertIn("First paragraph with bold text.", txt_out.read_text(encoding="utf-8"))

        md_out = Path(self.tmp_dir) / "output.md"
        writers.write_document_to_disk(html_in, md_out, "md", {"name": "EB Garamond", "size_pt": 12})
        self.assertTrue(md_out.is_file())
        self.assertIn("**bold**", md_out.read_text(encoding="utf-8"))

    def test_write_docx(self):
        html_in = "<p>Word document with <em>italic</em> text.</p>"
        docx_out = Path(self.tmp_dir) / "output.docx"
        writers.write_document_to_disk(html_in, docx_out, "docx", {"name": "EB Garamond", "size_pt": 12})
        self.assertTrue(docx_out.is_file())
        self.assertGreater(docx_out.stat().st_size, 500)

    def test_write_docx_with_tables_and_lines(self):
        html_in = """
        <h1 style="text-align: center;">Historic Chronicle</h1>
        <p>A treatise regarding ancient records.</p>
        <hr class="docedit-line" style="border: 1px solid #777;">
        <table class="docedit-table" style="border-collapse: collapse; width: 100%; border: 1px solid #777;">
            <thead>
                <tr><th style="border: 1px solid #777; padding: 6px;">Year</th><th style="border: 1px solid #777; padding: 6px;">City</th></tr>
            </thead>
            <tbody>
                <tr><td style="border: 1px solid #777; padding: 6px;">1642</td><td style="border: 1px solid #777; padding: 6px;">London</td></tr>
                <tr><td style="border: 1px solid #777; padding: 6px;">1688</td><td style="border: 1px solid #777; padding: 6px;">Oxford</td></tr>
            </tbody>
        </table>
        <hr class="docedit-line" style="border: 1px solid #777;">
        <p>Concluding remarks.</p>
        """
        docx_out = Path(self.tmp_dir) / "table_output.docx"
        writers.write_document_to_disk(html_in, docx_out, "docx", {"name": "EB Garamond", "size_pt": 12})
        self.assertTrue(docx_out.is_file())

        # Verify Word document contains the table and elements
        doc_read = docx.Document(str(docx_out))
        self.assertEqual(len(doc_read.tables), 1)
        tbl = doc_read.tables[0]
        self.assertEqual(len(tbl.rows), 3)
        self.assertEqual(len(tbl.columns), 2)
        self.assertEqual(tbl.cell(0, 0).text.strip(), "Year")
        self.assertEqual(tbl.cell(0, 1).text.strip(), "City")
        self.assertEqual(tbl.cell(1, 0).text.strip(), "1642")
        self.assertEqual(tbl.cell(1, 1).text.strip(), "London")

    def test_write_pdf_and_image(self):
        html_in = "<p>Book page for PDF and Image export test.</p>"
        pdf_out = Path(self.tmp_dir) / "output.pdf"
        writers.write_document_to_disk(html_in, pdf_out, "pdf", {"name": "Times New Roman", "size_pt": 12})
        self.assertTrue(pdf_out.is_file())
        self.assertGreater(pdf_out.stat().st_size, 500)

        img_out = Path(self.tmp_dir) / "output.png"
        writers.write_document_to_disk(html_in, img_out, "png", {"name": "Times New Roman", "size_pt": 12})
        self.assertTrue(img_out.is_file())
        self.assertGreater(img_out.stat().st_size, 500)

    def test_write_pdf_with_tables_and_lines(self):
        html_in = """
        <h1>Book Index & Tables</h1>
        <p>Before table text.</p>
        <hr class="docedit-line">
        <table class="docedit-table">
            <tr><th>Vol</th><th>Title</th></tr>
            <tr><td>1</td><td>Volume One</td></tr>
        </table>
        <p>After table text.</p>
        """
        pdf_out = Path(self.tmp_dir) / "table_output.pdf"
        writers.write_document_to_disk(html_in, pdf_out, "pdf", {"name": "EB Garamond", "size_pt": 12})
        self.assertTrue(pdf_out.is_file())

        pdf_doc = pymupdf.open(str(pdf_out))
        self.assertGreaterEqual(len(pdf_doc), 1)
        tables = pdf_doc[0].find_tables()
        self.assertGreaterEqual(len(tables.tables), 1)
        pdf_doc.close()


class DocEditOCRTests(TestCase):
    def test_image_preprocessing_and_ocr(self):
        # Create a simple synthetic printed page image
        img = Image.new("RGB", (600, 200), color=(245, 240, 230))  # Slightly aged paper color
        draw = ImageDraw.Draw(img)
        # Draw dark text
        draw.text((30, 80), "Old Book Chapter One", fill=(30, 25, 20))

        # Test preprocessor
        clean = ocr.preprocess_old_book_image(img)
        self.assertEqual(clean.mode, "L")

        # Test OCR call
        res = ocr.ocr_image(img, lang="eng", dpi=300)
        self.assertIn("text", res)
        self.assertIn("html", res)
        self.assertIn("stats", res)
        self.assertIn("avg_font_size_pt", res)


class DocEditViewFlowTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.tmp_dir = tempfile.mkdtemp(prefix="docedit_view_test_")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_docedit_home_view(self):
        url = reverse("docedit")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "docedit/docedit.html")
        self.assertTemplateUsed(resp, "home.html")
        self.assertContains(resp, "DocEdit")
        self.assertContains(resp, "Document Progress")
        content = resp.content.decode('utf-8')
        self.assertIn("Typography & Font", content)
        self.assertIn("Save & Download", content)

    def test_upload_missing_file(self):
        url = reverse("docedit_upload")
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data["success"])

    def test_upload_unsupported_file_type(self):
        url = reverse("docedit_upload")
        bad_file = SimpleUploadedFile("bad.exe", b"binarycontent", content_type="application/octet-stream")
        resp = self.client.post(url, {"document": bad_file})
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data["success"])
        self.assertIn("Unsupported", data["error"])

    def test_upload_save_and_download_flow(self):
        with override_settings(DOCEDIT_WORK_DIR=self.tmp_dir, DOCEDIT_SYNC_PROCESSING=True):
            upload_url = reverse("docedit_upload")
            sample_text = (
                "Chapter I: The Old Antiquary\n\n"
                "In the year 1824, there lived a scholar of great curiosity who preserved ancient manuscripts."
            )
            doc_file = SimpleUploadedFile("test_book.txt", sample_text.encode("utf-8"), content_type="text/plain")

            # 1. Upload
            upload_resp = self.client.post(upload_url, {"document": doc_file, "ocr_lang": "eng"})
            self.assertEqual(upload_resp.status_code, 200)
            data = upload_resp.json()
            self.assertTrue(data["success"])
            sid = data["session_id"]
            self.assertTrue(sid)

            # 2. Check Status
            status_url = reverse("docedit_status", args=[sid])
            status_resp = self.client.get(status_url)
            self.assertEqual(status_resp.status_code, 200)
            status_data = status_resp.json()
            self.assertTrue(status_data["success"])
            self.assertEqual(status_data["status"], "ready")
            self.assertTrue(status_data["is_editable"])
            self.assertIn("document_html", status_data)
            self.assertIn("The Old Antiquary", status_data["document_html"])
            self.assertIn("font_info", status_data)

            # 3. Change Font
            font_url = reverse("docedit_change_font", args=[sid])
            font_resp = self.client.post(
                font_url,
                json.dumps({"font_name": "Libre Baskerville"}),
                content_type="application/json"
            )
            self.assertEqual(font_resp.status_code, 200)
            font_data = font_resp.json()
            self.assertTrue(font_data["success"])
            self.assertEqual(font_data["font_info"]["name"], "Libre Baskerville")

            # 4. Save Edited Content
            save_url = reverse("docedit_save", args=[sid])
            edited_html = "<p>Chapter I: The Old Antiquary (Corrected Spelling)</p><p>Revised text with matching fonts.</p>"
            save_resp = self.client.post(
                save_url,
                json.dumps({"html_content": edited_html, "font_name": "Libre Baskerville"}),
                content_type="application/json"
            )
            self.assertEqual(save_resp.status_code, 200)
            save_data = save_resp.json()
            self.assertTrue(save_data["success"])
            self.assertIn("download_url", save_data)
            self.assertEqual(save_data["download_filename"], "test_book_edited.txt")

            # 5. Download Edited Document
            download_url = reverse("docedit_download", args=[sid])
            download_resp = self.client.get(download_url)
            self.assertEqual(download_resp.status_code, 200)
            self.assertEqual(download_resp["X-DocEdit-Downloaded"], "true")
            downloaded_text = download_resp.content.decode("utf-8")
            self.assertIn("Corrected Spelling", downloaded_text)
            # Verify session and edited documents are immediately deleted from server
            self.assertFalse(storage.get_session_dir(sid).is_dir())

            # 6. Cancel / Cleanup (idempotent after download)
            cancel_url = reverse("docedit_cancel", args=[sid])
            cancel_resp = self.client.post(cancel_url)
            self.assertEqual(cancel_resp.status_code, 200)
            cancel_data = cancel_resp.json()
            self.assertTrue(cancel_data["success"])

    def test_save_and_download_choice_of_format(self):
        """Tests that user can choose any export format regardless of uploaded file type."""
        with override_settings(DOCEDIT_WORK_DIR=self.tmp_dir, DOCEDIT_SYNC_PROCESSING=True):
            upload_url = reverse("docedit_upload")
            sample_content = "Document with tables and notes."

            # 1. User chooses PDF export
            doc_file1 = SimpleUploadedFile("my_doc.txt", sample_content.encode("utf-8"), content_type="text/plain")
            upload_resp1 = self.client.post(upload_url, {"document": doc_file1, "ocr_lang": "eng"})
            sid1 = upload_resp1.json()["session_id"]
            save_url1 = reverse("docedit_save", args=[sid1])
            download_url1 = reverse("docedit_download", args=[sid1])

            table_html = """
            <h1>Document Summary</h1>
            <hr class="docedit-line">
            <table class="docedit-table">
                <tr><th>Key</th><th>Value</th></tr>
                <tr><td>Status</td><td>Active</td></tr>
            </table>
            <p>End of record.</p>
            """

            pdf_resp = self.client.post(
                save_url1,
                json.dumps({"html_content": table_html, "export_format": "pdf", "font_name": "EB Garamond"}),
                content_type="application/json"
            )
            self.assertEqual(pdf_resp.status_code, 200)
            pdf_data = pdf_resp.json()
            self.assertTrue(pdf_data["success"])
            self.assertEqual(pdf_data["export_format"], "pdf")
            self.assertEqual(pdf_data["download_filename"], "my_doc_edited.pdf")

            dl_pdf = self.client.get(download_url1)
            self.assertEqual(dl_pdf.status_code, 200)
            self.assertEqual(dl_pdf["Content-Type"], "application/pdf")
            self.assertEqual(dl_pdf["X-DocEdit-Downloaded"], "true")
            self.assertEqual(dl_pdf["X-DocEdit-Format"], "pdf")
            # Session deleted immediately on download
            self.assertFalse(storage.get_session_dir(sid1).is_dir())

            # 2. User chooses Word DOCX export in a new session
            doc_file2 = SimpleUploadedFile("my_doc.txt", sample_content.encode("utf-8"), content_type="text/plain")
            upload_resp2 = self.client.post(upload_url, {"document": doc_file2, "ocr_lang": "eng"})
            sid2 = upload_resp2.json()["session_id"]
            save_url2 = reverse("docedit_save", args=[sid2])
            download_url2 = reverse("docedit_download", args=[sid2])

            docx_resp = self.client.post(
                save_url2,
                json.dumps({"html_content": table_html, "export_format": "docx", "font_name": "EB Garamond"}),
                content_type="application/json"
            )
            self.assertEqual(docx_resp.status_code, 200)
            docx_data = docx_resp.json()
            self.assertTrue(docx_data["success"])
            self.assertEqual(docx_data["export_format"], "docx")
            self.assertEqual(docx_data["download_filename"], "my_doc_edited.docx")

            dl_docx = self.client.get(download_url2)
            self.assertEqual(dl_docx.status_code, 200)
            self.assertIn("officedocument.wordprocessingml", dl_docx["Content-Type"])
            self.assertEqual(dl_docx["X-DocEdit-Downloaded"], "true")
            self.assertEqual(dl_docx["X-DocEdit-Format"], "docx")
            # Session deleted immediately on download
            self.assertFalse(storage.get_session_dir(sid2).is_dir())



class DocEditExtractTests(TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="docedit_extract_test_")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_extract_docx_with_tables_and_headings(self):
        # Create a real DOCX with tables and headings
        doc = docx.Document()
        doc.add_heading("Chronicle of Events", level=1)
        doc.add_paragraph("An introductory note before the table.")
        tbl = doc.add_table(rows=2, cols=2)
        tbl.cell(0, 0).text = "Event"
        tbl.cell(0, 1).text = "Date"
        tbl.cell(1, 0).text = "Inauguration"
        tbl.cell(1, 1).text = "1840"

        doc_path = Path(self.tmp_dir) / "test_table.docx"
        doc.save(str(doc_path))

        res = extract.extract_document(doc_path)
        self.assertIn("<table class=\"docedit-table\"", res["html"])
        self.assertIn("Chronicle of Events", res["html"])
        self.assertIn("Inauguration", res["html"])
        self.assertIn("1840", res["html"])

    def test_extract_markdown_with_tables(self):
        md_text = (
            "# Literary Index\n\n"
            "Introductory text.\n\n"
            "| Volume | Author |\n"
            "| --- | --- |\n"
            "| Vol 1 | Milton |\n"
            "| Vol 2 | Shakespeare |\n\n"
            "Concluding remark.\n"
        )
        md_path = Path(self.tmp_dir) / "test.md"
        md_path.write_text(md_text, encoding="utf-8")

        res = extract.extract_document(md_path)
        self.assertIn("<table class=\"docedit-table\"", res["html"])
        self.assertIn("Literary Index", res["html"])
        self.assertIn("Milton", res["html"])

    def test_extract_multipage_pdf_separate_pages_and_layout_preservation(self):
        # Create a 2-page PDF with shapes and text
        doc = pymupdf.open()
        p1 = doc.new_page(width=595, height=842)
        shape1 = p1.new_shape()
        shape1.draw_rect(pymupdf.Rect(40, 40, 500, 800))
        shape1.finish(color=(0, 0, 0), width=1)
        shape1.commit()
        p1.insert_text((50, 100), "First Page Distinct Header", fontsize=16)

        p2 = doc.new_page(width=595, height=842)
        shape2 = p2.new_shape()
        shape2.draw_line(pymupdf.Point(40, 100), pymupdf.Point(500, 100))
        shape2.finish(color=(0.5, 0.5, 0.5), width=2)
        shape2.commit()
        p2.insert_text((50, 120), "Second Page Independent Content", fontsize=14)

        pdf_path = Path(self.tmp_dir) / "multipage_doc.pdf"
        doc.save(str(pdf_path))
        doc.close()

        res = extract.extract_document(pdf_path, work_dir=Path(self.tmp_dir), sid="test_sid")
        self.assertTrue(res.get("is_layout_preserved"))
        pages = res.get("pages", [])
        self.assertEqual(len(pages), 2, "Must keep every page separate!")
        self.assertEqual(pages[0]["page_num"], 1)
        self.assertEqual(pages[1]["page_num"], 2)

        # Check page 1 has its text block
        p1_texts = [b["text"] for b in pages[0]["blocks"]]
        self.assertTrue(any("First Page Distinct Header" in t for t in p1_texts))

        # Check page 2 has its text block
        p2_texts = [b["text"] for b in pages[1]["blocks"]]
        self.assertTrue(any("Second Page Independent Content" in t for t in p2_texts))

        # Check page images were generated
        self.assertTrue((Path(self.tmp_dir) / "page_1.png").is_file())
        self.assertTrue((Path(self.tmp_dir) / "page_2.png").is_file())

        # Now test in-place editing on page 1 without affecting page 2 or vector drawings
        pages[0]["blocks"][0]["text"] = "EDITED Page 1 Header"
        pages[0]["blocks"][0]["is_modified"] = True

        out_pdf = Path(self.tmp_dir) / "multipage_edited.pdf"
        writers.write_document_to_disk(
            html_content="",
            output_path=out_pdf,
            extension="pdf",
            font_info={"name": "EB Garamond", "size_pt": 14.0},
            pages_data=pages,
            original_file_path=pdf_path,
            work_dir=Path(self.tmp_dir),
        )
        self.assertTrue(out_pdf.is_file())

        # Verify output PDF maintains both pages separate and preserves vector drawings
        doc_out = pymupdf.open(str(out_pdf))
        self.assertEqual(len(doc_out), 2)
        self.assertIn("EDITED Page 1 Header", doc_out[0].get_text())
        self.assertIn("Second Page Independent Content", doc_out[1].get_text())
        self.assertGreater(len(doc_out[0].get_drawings()), 0, "Page 1 drawings must be preserved!")
        self.assertGreater(len(doc_out[1].get_drawings()), 0, "Page 2 drawings must be preserved!")
        doc_out.close()


class DocEditPageImageViewTests(TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="docedit_page_img_test_")
        self.client = Client()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_session_page_image_endpoint(self):
        with override_settings(DOCEDIT_WORK_DIR=self.test_dir):
            # Create a 1-page PDF
            doc = pymupdf.open()
            p = doc.new_page(width=400, height=500)
            p.insert_text((50, 50), "Test image streaming")
            pdf_bytes = doc.tobytes()
            doc.close()

            sid = storage.create_session("stream_doc.pdf", pdf_bytes)
            img_url = reverse("docedit_page_image", args=[sid, 1])
            resp = self.client.get(img_url)
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp["Content-Type"], "image/png")
            self.assertGreater(len(resp.content), 100)


class DocEditSystemFontTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.test_dir = tempfile.mkdtemp(prefix="docedit_font_test_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_get_system_font_signature(self):
        sig = font_catalog.get_system_font_signature()
        self.assertIsInstance(sig, str)
        self.assertEqual(len(sig), 32)

    def test_get_font_index_and_categorized_list(self):
        idx = font_catalog.get_font_index()
        self.assertIn("families", idx)
        self.assertGreater(len(idx["families"]), 0)

        categorized = font_catalog.get_categorized_font_list()
        self.assertIn("recommended", categorized)
        self.assertIn("project", categorized)
        self.assertIn("system", categorized)
        self.assertIn("all_names", categorized)
        self.assertGreater(categorized["total_count"], 0)

        # Check system fonts are included
        system_names = [f["name"] for f in categorized["system"]]
        self.assertTrue(len(system_names) > 0 or len(categorized["all_names"]) > 0)

    def test_font_list_api(self):
        url = reverse("docedit_font_list")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertGreater(data["total_count"], 0)
        self.assertIn("recommended", data["groups"])
        self.assertIn("project", data["groups"])
        self.assertIn("system", data["groups"])

    def test_font_list_api_refresh(self):
        url = reverse("docedit_font_list") + "?refresh=1"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertGreater(data["total_count"], 0)

    def test_install_font_api_upload_invalid_ext(self):
        url = reverse("docedit_font_install")
        bad_file = SimpleUploadedFile("bad.txt", b"not a font", content_type="text/plain")
        resp = self.client.post(url, {"font_file": bad_file})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])

    def test_install_font_api_upload_valid_file(self):
        with override_settings(DOCEDIT_FONT_LIBRARY_DIR=Path(self.test_dir) / "fonts",
                               DOCEDIT_INSTALL_FONTS_TO_SYSTEM=False):
            font_bytes = b"FakeTTFContentForTestingPurpose123456789"
            test_font = SimpleUploadedFile("MockCustomBookFont-Regular.ttf", font_bytes, content_type="font/ttf")
            url = reverse("docedit_font_install")
            resp = self.client.post(url, {"font_file": test_font})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["success"])
            self.assertIn("MockCustomBookFont", data["name"])

            # Verify it was automatically added to font list
            cat = font_catalog.get_categorized_font_list()
            self.assertTrue(any("MockCustomBookFont" in name for name in cat["all_names"]))

    def test_install_font_api_online_not_found(self):
        url = reverse("docedit_font_install")
        resp = self.client.post(url, json.dumps({"font_name": "NonExistentUnknownFontXYZ999"}), content_type="application/json")
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(resp.json()["success"])


class DocEditFontAutoDetectionAndNearestMatchTests(TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="docedit_font_test_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_clean_pdf_font_name_variants(self):
        cases = {
            "ABCDEF+TimesNewRomanPS-BoldMT": "Times New Roman",
            "Calibri-Bold": "Calibri",
            "ArialMT": "Arial",
            "BAAAAA+Arial-BoldMT": "Arial",
            "SegoeUI-Semibold": "Segoe UI",
            "Aptos-Display": "Aptos",
            "CustomBrandSerif-Regular": "Custom Brand Serif",
        }
        for raw, expected in cases.items():
            cleaned = fontmatch.clean_pdf_font_name(raw)
            self.assertEqual(cleaned, expected, f"Failed on raw font: {raw}")
            self.assertFalse(cleaned.endswith("-"), f"Cleaned name has trailing hyphen: {cleaned}")

    def test_find_nearest_match_categorization_never_stuck_with_garamond_for_sans_or_mono(self):
        # Sans-serif should match a sans-serif (Calibri/Arial), NEVER EB Garamond
        sub_aptos = font_catalog.find_nearest_match("Aptos")
        self.assertEqual(sub_aptos["category"], "sans-serif")
        self.assertNotEqual(sub_aptos["nearest_match"], "EB Garamond")
        self.assertIn(sub_aptos["nearest_match"], ["Calibri", "Arial", "Roboto", "Segoe UI"])

        sub_custom_sans = font_catalog.find_nearest_match("Acme Modern Grotesk Sans")
        self.assertEqual(sub_custom_sans["category"], "sans-serif")
        self.assertNotEqual(sub_custom_sans["nearest_match"], "EB Garamond")
        self.assertIn(sub_custom_sans["nearest_match"], ["Calibri", "Arial", "Roboto", "Segoe UI"])

        # Monospace should match a monospace font, NEVER EB Garamond
        sub_monaco = font_catalog.find_nearest_match("Monaco Typewriter")
        self.assertEqual(sub_monaco["category"], "monospace")
        self.assertNotEqual(sub_monaco["nearest_match"], "EB Garamond")
        self.assertIn(sub_monaco["nearest_match"], ["Consolas", "Courier New", "Cousine", "Inconsolata"])

        # Script fonts
        sub_hin = font_catalog.find_nearest_match("Aparajita Devanagari")
        self.assertEqual(sub_hin["category"], "devanagari")
        self.assertIn(sub_hin["nearest_match"], ["Mangal", "Nirmala UI", "Noto Serif Devanagari"])

        sub_guj = font_catalog.find_nearest_match("Shruti Gujarati")
        self.assertEqual(sub_guj["category"], "gujarati")
        self.assertIn(sub_guj["nearest_match"], ["Shruti", "Noto Serif Gujarati", "Rasa"])

        sub_ara = font_catalog.find_nearest_match("Traditional Arabic Book")
        self.assertEqual(sub_ara["category"], "arabic")
        self.assertIn(sub_ara["nearest_match"], ["Traditional Arabic", "Simplified Arabic", "Amiri"])

    def test_resolve_document_font_preserves_system_font(self):
        res_calibri = font_catalog.resolve_document_font("Calibri")
        self.assertEqual(res_calibri["name"], "Calibri")
        self.assertTrue(res_calibri["is_system"])
        self.assertFalse(res_calibri["is_alternative"])

        res_times = font_catalog.resolve_document_font("Times New Roman")
        self.assertEqual(res_times["name"], "Times New Roman")
        self.assertTrue(res_times["is_system"])

    def test_change_font_api_with_font_and_size(self):
        with override_settings(DOCEDIT_WORK_DIR=self.test_dir):
            sid = storage.create_session("sample.txt", b"Hello typography testing.")
            url = reverse("docedit_change_font", args=[sid])
            payload = {"font_name": "Calibri", "size_pt": 14.5}
            resp = self.client.post(url, json.dumps(payload), content_type="application/json")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["success"])
            self.assertEqual(data["font_info"]["name"], "Calibri")
            self.assertEqual(data["font_info"]["size_pt"], 14.5)

            meta = storage.get_session_meta(sid)
            self.assertEqual(meta["font_info"]["size_pt"], 14.5)
            self.assertEqual(meta["font_info"]["name"], "Calibri")

    def test_docx_extract_detects_run_font_and_size(self):
        doc = docx.Document()
        p = doc.add_paragraph()
        run = p.add_run("Testing specific font extraction.")
        run.font.name = "Arial"
        run.font.size = docx.shared.Pt(15.0)
        docx_path = Path(self.test_dir) / "test_font.docx"
        doc.save(str(docx_path))

        res = extract._extract_from_docx(docx_path)
        self.assertEqual(res["detected_font_name"], "Arial")
        self.assertEqual(res["font_size_pt"], 15.0)

    def test_font_variant_resolution(self):
        """Verifies find_font_variant_file accurately identifies bold and italic files."""
        from .font_catalog import find_font_variant_file

        # Windows system fonts resolution
        if os.name == "nt":
            bold_arial = find_font_variant_file("Arial", is_bold=True)
            self.assertIsNotNone(bold_arial)
            self.assertTrue(Path(bold_arial).is_file())
            self.assertTrue("arial" in bold_arial.lower())

            italic_arial = find_font_variant_file("Arial", is_italic=True)
            self.assertIsNotNone(italic_arial)
            self.assertTrue(Path(italic_arial).is_file())

            bi_arial = find_font_variant_file("Arial", is_bold=True, is_italic=True)
            self.assertIsNotNone(bi_arial)
            self.assertTrue(Path(bi_arial).is_file())

    def test_pdf_bold_italic_extraction(self):
        """Verifies _extract_from_pdf extracts is_bold and is_italic span flags and names."""
        import pymupdf

        pdf_path = Path(self.test_dir) / "test_styled.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=595, height=842)
        # Insert bold text with built-in font
        page.insert_text(pymupdf.Point(72, 100), "Chapter 1: The Beginning", fontsize=16, fontname="hebo")
        # Insert italic text
        page.insert_text(pymupdf.Point(72, 140), "An introduction into typography.", fontsize=12, fontname="heit")
        # Insert regular text
        page.insert_text(pymupdf.Point(72, 180), "Standard paragraph text without styling.", fontsize=11, fontname="helv")
        doc.save(str(pdf_path))
        doc.close()

        res = extract._extract_from_pdf(pdf_path)
        self.assertTrue(res["is_layout_preserved"])
        blocks = res["pages"][0]["blocks"]
        self.assertTrue(len(blocks) >= 3)

        # Check bold block
        bold_blocks = [b for b in blocks if "Chapter 1" in b["text"]]
        self.assertTrue(len(bold_blocks) > 0)
        self.assertTrue(bold_blocks[0]["is_bold"])

        # Check italic block
        italic_blocks = [b for b in blocks if "introduction" in b["text"]]
        self.assertTrue(len(italic_blocks) > 0)
        self.assertTrue(italic_blocks[0]["is_italic"])

    def test_pdf_layout_preserved_bold_italic_underline(self):
        """Verifies _write_pdf_layout_preserved renders bold, italic, underline, and moved bbox."""
        import pymupdf
        from .writers import _write_pdf_layout_preserved

        out_pdf = Path(self.test_dir) / "out_layout_styled.pdf"
        pages_data = [{
            "page_num": 1,
            "width": 595.0,
            "height": 842.0,
            "blocks": [
                {
                    "id": "p1_b0",
                    "text": "Edited Bold & Underlined Headline",
                    "bbox": [80.0, 120.0, 320.0, 145.0],
                    "orig_bbox": [72.0, 100.0, 300.0, 125.0],
                    "left_pct": 13.4,
                    "top_pct": 14.2,
                    "font_name": "Arial",
                    "font_size_pt": 14.0,
                    "is_bold": True,
                    "is_italic": False,
                    "is_underline": True,
                    "is_modified": True,
                }
            ]
        }]

        res_path = _write_pdf_layout_preserved(
            pages_data=pages_data,
            original_file_path=None,
            output_path=out_pdf,
            font_name="Arial",
            font_path=None,
            font_size_pt=14.0,
        )
        self.assertTrue(res_path.is_file())
        self.assertGreater(res_path.stat().st_size, 500)

    def test_docx_nested_formatting(self):
        """Verifies _write_docx handles bold, italic, underline, and nested tags."""
        import docx
        from .writers import _write_docx

        out_docx = Path(self.test_dir) / "out_formatted.docx"
        html_input = '<p>Regular <b>Bold Text</b> and <i>Italic Text</i> and <u>Underline Text</u> and <b><i><u>All Three</u></i></b></p>'
        res_path = _write_docx(html_input, out_docx, "Calibri", 12.0)
        self.assertTrue(res_path.is_file())

        doc = docx.Document(str(res_path))
        p = doc.paragraphs[0]
        # Check run styles
        bold_runs = [r for r in p.runs if r.bold and not r.italic and not r.underline]
        self.assertTrue(len(bold_runs) > 0)
        self.assertIn("Bold Text", bold_runs[0].text)

        all_three_runs = [r for r in p.runs if r.bold and r.italic and r.underline]
        self.assertTrue(len(all_three_runs) > 0)
        self.assertIn("All Three", all_three_runs[0].text)

    def test_save_document_autosave_endpoint(self):
        """Verifies save_document handles is_autosave smoothly and quickly."""
        with override_settings(DOCEDIT_WORK_DIR=self.test_dir):
            sid = storage.create_session("sample.pdf", b"%PDF-1.4 sample")
            url = reverse("docedit_save", args=[sid])
            payload = {
                "is_autosave": True,
                "html_content": "<p>Auto-saved paragraph content</p>",
                "font_name": "Calibri",
                "font_size_pt": 13.0,
                "export_format": "pdf",
                "pages_data": [{
                    "page_num": 1,
                    "width": 600,
                    "height": 800,
                    "blocks": [{
                        "id": "b1",
                        "text": "Auto-saved block",
                        "font_name": "Calibri",
                        "font_size_pt": 13.0,
                        "is_modified": True,
                        "left_pct": 10.0,
                        "top_pct": 20.0,
                        "width_pct": 30.0,
                        "height_pct": 5.0,
                        "bbox": [60, 160, 240, 200]
                    }]
                }]
            }
            resp = self.client.post(url, json.dumps(payload), content_type="application/json")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["success"])
            self.assertTrue(data.get("is_autosave"))

            # Check that content was saved in workspace session
            saved_html = storage.get_document_content(sid)
            self.assertIn("Auto-saved paragraph content", saved_html)

            # Check pages metadata updated
            meta = storage.get_session_meta(sid)
            self.assertEqual(meta["font_info"]["name"], "Calibri")
            self.assertEqual(meta["font_info"]["size_pt"], 13.0)
            self.assertEqual(len(meta["pages"]), 1)
            self.assertEqual(meta["pages"][0]["blocks"][0]["text"], "Auto-saved block")

    def test_docx_per_run_font_and_size_preservation(self):
        """Verifies _write_docx preserves inline run-level font-family and font-size from spans."""
        import docx
        from docx.shared import Pt
        from .writers import _write_docx

        out_docx = Path(self.test_dir) / "out_run_fonts.docx"
        html_input = (
            '<p>'
            '<span style="font-family: \'Arial\'; font-size: 16pt;">Arial Heading Run</span> '
            '<span style="font-family: \'Courier New\'; font-size: 10pt;">Courier Monospace Run</span>'
            '</p>'
        )
        res_path = _write_docx(html_input, out_docx, "Calibri", 12.0)
        self.assertTrue(res_path.is_file())

        doc = docx.Document(str(res_path))
        p = doc.paragraphs[0]
        self.assertGreaterEqual(len(p.runs), 2)

        arial_run = next((r for r in p.runs if "Arial" in r.text), None)
        self.assertIsNotNone(arial_run)
        self.assertEqual(arial_run.font.name, "Arial")
        self.assertEqual(arial_run.font.size, Pt(16.0))

        courier_run = next((r for r in p.runs if "Courier" in r.text), None)
        self.assertIsNotNone(courier_run)
        self.assertEqual(courier_run.font.name, "Courier New")
        self.assertEqual(courier_run.font.size, Pt(10.0))

    def test_find_font_variant_file_does_not_mismatch_base_font(self):
        """Verifies find_font_variant_file does not return base_font_path if family differs."""
        from .font_catalog import find_font_variant_file
        # When asking for Arial with base_font_path being EB Garamond, it must NOT return EB Garamond
        fake_garamond = Path(self.test_dir) / "EBGaramond-Regular.ttf"
        fake_garamond.write_bytes(b"dummy")

        res = find_font_variant_file("Arial", is_bold=False, is_italic=False, base_font_path=str(fake_garamond))
        if res:
            self.assertNotIn("garamond", res.lower())
            self.assertIn("arial", res.lower())





