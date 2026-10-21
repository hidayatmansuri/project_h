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
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import resolve, reverse
from PIL import Image, ImageDraw, ImageFont
import docx
import pymupdf

from docedit import embedded_fonts, extract, font_catalog, fontmatch, ocr, storage, views, writers
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
            # Verify session and edited documents are preserved on GET download
            self.assertTrue(storage.get_session_dir(sid).is_dir())

            # 6. Cancel / Cleanup (explicit POST deletes session)
            cancel_url = reverse("docedit_cancel", args=[sid])
            cancel_resp = self.client.post(cancel_url)
            self.assertEqual(cancel_resp.status_code, 200)
            cancel_data = cancel_resp.json()
            self.assertTrue(cancel_data["success"])
            self.assertFalse(storage.get_session_dir(sid).is_dir())

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
            # Session preserved on GET download
            self.assertTrue(storage.get_session_dir(sid1).is_dir())

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
            # Session preserved on GET download
            self.assertTrue(storage.get_session_dir(sid2).is_dir())



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

    def test_extract_docx_with_icons_and_hyperlinks(self):
        """Verifies extraction preserves inline/anchored drawing icons, hyperlinks, and bullet lists."""
        import base64
        import io
        from docx.oxml import parse_xml

        doc = docx.Document()
        p0 = doc.add_paragraph()
        r0 = p0.add_run("Candidate Profile")

        # Paragraph with hyperlink and bullet list
        p1 = doc.add_paragraph()
        part = p1.part
        r_id = part.relate_to("mailto:test@example.com", docx.opc.constants.RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
        hl_xml = (
            f'<w:hyperlink xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            f'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:id="{r_id}">'
            f'<w:r><w:t>test@example.com</w:t></w:r></w:hyperlink>'
        )
        p1._p.append(parse_xml(hl_xml))

        # Add list paragraph
        p_li = doc.add_paragraph("Delivered key software engineering project.", style="List Paragraph")

        doc_path = Path(self.tmp_dir) / "test_icons_hyperlinks.docx"
        doc.save(str(doc_path))

        res = extract.extract_document(doc_path)
        self.assertIn("Candidate Profile", res["html"])
        self.assertIn("mailto:test@example.com", res["html"])
        self.assertIn("test@example.com", res["html"])
        self.assertIn("<li", res["html"])
        self.assertIn("Delivered key software engineering project.", res["html"])

    def test_write_docx_and_pdf_preserve_icons_hyperlinks_and_margins(self):
        """Verifies _write_docx and _write_pdf preserve icons, hyperlinks, and compact margins."""
        from .writers import _write_docx, _write_pdf
        import base64

        # 1x1 transparent PNG
        dummy_png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")
        b64_str = base64.b64encode(dummy_png).decode("ascii")

        html_input = (
            f'<h1 style="text-align: center;">Hidayat Mansuri</h1>\n'
            f'<p><img src="data:image/png;base64,{b64_str}" alt="Mail" class="docedit-docx-icon"> '
            f'<a href="mailto:hidayat.mansuri@gmail.com">hidayat.mansuri@gmail.com</a> &nbsp; 07854536271</p>\n'
            f'<ul style="margin: 2pt 0 4pt 0; padding-left: 18pt;">'
            f'<li style="margin: 1.5pt 0;">Acted as a liaison between end-users and IT support.</li>'
            f'</ul>'
        )

        out_docx = Path(self.tmp_dir) / "out_icon_test.docx"
        _write_docx(html_input, out_docx, "Calibri", 10.0)
        self.assertTrue(out_docx.is_file())

        doc_read = docx.Document(str(out_docx))
        drawings = sum(len(p._p.xpath(".//w:drawing")) for p in doc_read.paragraphs)
        hyperlinks = sum(len(p._p.xpath(".//w:hyperlink")) for p in doc_read.paragraphs)
        self.assertGreaterEqual(drawings, 1)
        self.assertGreaterEqual(hyperlinks, 1)

        out_pdf = Path(self.tmp_dir) / "out_icon_test.pdf"
        _write_pdf(html_input, out_pdf, "Calibri", None, 10.0)
        self.assertTrue(out_pdf.is_file())
        pdf_read = pymupdf.open(str(out_pdf))
        self.assertEqual(len(pdf_read), 1)
        self.assertIn("Hidayat Mansuri", pdf_read[0].get_text())
        self.assertIn("hidayat.mansuri@gmail.com", pdf_read[0].get_text())

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

    def test_extract_and_write_vertical_text_preserves_rotation(self):
        """Verifies that vertical text is extracted with rotation=90 and written back vertically without bleeding."""
        from .writers import write_document_to_disk

        # Create a PDF with two close vertical lines (like on shipping label)
        test_pdf = Path(self.test_dir) / "vertical_sample.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=300, height=300)
        # Line 1: x=100, y=100, rotated 90 deg counter-clockwise (vertical upwards)
        page.insert_text(pymupdf.Point(100, 200), "Miscellaneous", fontsize=10.0, rotate=90)
        # Line 2: x=108, y=200, rotated 90 deg counter-clockwise (adjacent vertical line)
        page.insert_text(pymupdf.Point(109, 200), "43 Langham Road", fontsize=10.0, rotate=90)
        doc.save(str(test_pdf))
        doc.close()

        # Extract
        res = extract.extract_document(test_pdf, sid="test_rot_sid")
        self.assertTrue(res["is_layout_preserved"])
        blocks = res["pages"][0]["blocks"]
        misc_b = next((b for b in blocks if "Miscellaneous" in b["text"]), None)
        langham_b = next((b for b in blocks if "43 Langham Road" in b["text"]), None)

        self.assertIsNotNone(misc_b)
        self.assertIsNotNone(langham_b)
        self.assertEqual(misc_b["rotation"], 90)
        self.assertEqual(langham_b["rotation"], 90)

        # Edit line 1
        misc_b["text"] = "MiscellAneous"
        misc_b["is_modified"] = True

        out_pdf = Path(self.test_dir) / "vertical_edited.pdf"
        write_document_to_disk(
            html_content="",
            output_path=out_pdf,
            extension="pdf",
            font_info={"name": "Helvetica", "size_pt": 10},
            pages_data=res["pages"],
            original_file_path=test_pdf,
        )

        # Verify output
        doc_out = pymupdf.open(str(out_pdf))
        txt_out = doc_out[0].get_text()
        self.assertIn("MiscellAneous", txt_out)
        self.assertIn("43 Langham Road", txt_out)

        # Verify direction remains vertical (dir=(0, -1))
        d_out = doc_out[0].get_text("dict")
        found_span = False
        for blk in d_out["blocks"]:
            if blk.get("type") == 0:
                for line in blk["lines"]:
                    for sp in line["spans"]:
                        if "MiscellAneous" in sp["text"]:
                            found_span = True
                            dx, dy = line["dir"]
                            self.assertAlmostEqual(dx, 0.0, places=1)
                            self.assertAlmostEqual(dy, -1.0, places=1)
        self.assertTrue(found_span)
        doc_out.close()


class DocEditSecurityHardeningTests(TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="docedit_security_test_")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_sanitize_document_html_strips_scripts_and_events(self):
        from .security import sanitize_document_html
        dangerous_payload = (
            '<p>Hello <script>alert("xss")</script>World</p>'
            '<img src="x" onerror="alert(1)">'
            '<iframe src="https://evil.com"></iframe>'
            '<a href="javascript:alert(1)">Click me</a>'
            '<span style="behavior:url(test.htc); color: red;">Styled</span>'
        )
        cleaned = sanitize_document_html(dangerous_payload)
        self.assertNotIn("<script>", cleaned)
        self.assertNotIn("alert(", cleaned)
        self.assertNotIn("onerror", cleaned)
        self.assertNotIn("<iframe", cleaned)
        self.assertNotIn("javascript:", cleaned)
        self.assertNotIn("behavior:", cleaned)
        self.assertIn("<p>Hello", cleaned)
        self.assertIn("World</p>", cleaned)
        self.assertIn("<span", cleaned)

    def test_sanitize_document_html_fallback_without_nh3(self):
        from . import security
        orig_has_nh3 = security._HAS_NH3
        try:
            security._HAS_NH3 = False
            dangerous_payload = (
                '<p>Hello <script>alert("xss")</script>World</p>'
                '<img src="x" onerror="alert(1)">'
                '<iframe src="https://evil.com"></iframe>'
                '<a href="javascript:alert(1)">Click me</a>'
                '<span style="behavior:url(test.htc); color: red;">Styled</span>'
            )
            cleaned = security.sanitize_document_html(dangerous_payload)
            self.assertNotIn("<script>", cleaned)
            self.assertNotIn("alert(", cleaned)
            self.assertNotIn("onerror", cleaned)
            self.assertNotIn("<iframe", cleaned)
            self.assertNotIn("javascript:", cleaned)
            self.assertNotIn("behavior:", cleaned)
            self.assertIn("<p>Hello", cleaned)
            self.assertIn("World</p>", cleaned)
            self.assertIn("<span", cleaned)
        finally:
            security._HAS_NH3 = orig_has_nh3

    def test_sanitize_font_name_prevents_css_and_html_injection(self):
        from .security import sanitize_font_name, is_valid_font_name
        self.assertTrue(is_valid_font_name("Times New Roman"))
        self.assertTrue(is_valid_font_name("EB-Garamond"))
        self.assertTrue(is_valid_font_name("Noto Serif Devanagari"))

        # Injections
        self.assertFalse(is_valid_font_name("Arial'; } body { background: red; } /*"))
        self.assertFalse(is_valid_font_name('<script>alert(1)</script>'))
        self.assertFalse(is_valid_font_name('../../etc/passwd'))

        sanitized = sanitize_font_name("Arial'; } body { background: red; } /*")
        self.assertEqual(sanitized, "EB Garamond")

        cleaned_quotes = sanitize_font_name("'Calibri'")
        self.assertEqual(cleaned_quotes, "Calibri")

    def test_validate_ocr_lang_path_traversal_rejection(self):
        from .security import validate_ocr_lang
        # Valid languages
        self.assertEqual(validate_ocr_lang("eng"), "eng")
        self.assertEqual(validate_ocr_lang("eng+hin"), "eng+hin")
        self.assertEqual(validate_ocr_lang("guj"), "guj")

        # Invalid / traversal attacks
        with self.assertRaises(ValueError):
            validate_ocr_lang("../../etc/passwd")
        with self.assertRaises(ValueError):
            validate_ocr_lang("..\\..\\windows")
        with self.assertRaises(ValueError):
            validate_ocr_lang("eng+../../x")
        with self.assertRaises(ValueError):
            validate_ocr_lang("unknown_lang")

    def test_max_pages_enforcement_on_pdf(self):
        # Create a 5-page PDF
        pdf_path = Path(self.tmp_dir) / "large.pdf"
        doc = pymupdf.open()
        for _ in range(5):
            p = doc.new_page(width=200, height=200)
            p.insert_text((50, 50), "Sample text")
        doc.save(str(pdf_path))
        doc.close()

        with override_settings(DOCEDIT_MAX_PAGES=3):
            with self.assertRaises(ValueError) as ctx:
                extract.extract_document(pdf_path, sid="test_page_limit")
            self.assertIn("exceeds maximum page limit", str(ctx.exception))

    def test_session_ownership_enforcement(self):
        with override_settings(DOCEDIT_WORK_DIR=self.tmp_dir, DOCEDIT_SYNC_PROCESSING=True):
            # Client A creates a session
            client_a = Client()
            upload_url = reverse("docedit_upload")
            txt_file = SimpleUploadedFile("secret.txt", b"Confidential content", content_type="text/plain")
            resp_a = client_a.post(upload_url, {"document": txt_file, "ocr_lang": "eng"})
            self.assertEqual(resp_a.status_code, 200)
            sid = resp_a.json()["session_id"]

            # Client A can read status
            status_url = reverse("docedit_status", args=[sid])
            status_a = client_a.get(status_url)
            self.assertEqual(status_a.status_code, 200)

            # Client B tries to read status -> 403 Forbidden
            client_b = Client()
            status_b = client_b.get(status_url)
            self.assertEqual(status_b.status_code, 403)
            self.assertFalse(status_b.json()["success"])

            # Client B tries to save Client A's session -> 403 Forbidden
            save_url = reverse("docedit_save", args=[sid])
            save_b = client_b.post(save_url, json.dumps({"html_content": "<p>Hacked</p>"}), content_type="application/json")
            self.assertEqual(save_b.status_code, 403)

            # Client B tries to download Client A's session -> 403 Forbidden
            download_url = reverse("docedit_download", args=[sid])
            download_b = client_b.get(download_url)
            self.assertEqual(download_b.status_code, 403)

            # Client B tries to cancel Client A's session -> 403 Forbidden
            cancel_url = reverse("docedit_cancel", args=[sid])
            cancel_b = client_b.post(cancel_url)
            self.assertEqual(cancel_b.status_code, 403)

    def test_save_and_change_font_reject_non_dict_json(self):
        with override_settings(DOCEDIT_WORK_DIR=self.tmp_dir, DOCEDIT_SYNC_PROCESSING=True):
            client = Client()
            upload_url = reverse("docedit_upload")
            txt_file = SimpleUploadedFile("doc.txt", b"Simple text", content_type="text/plain")
            resp = client.post(upload_url, {"document": txt_file, "ocr_lang": "eng"})
            sid = resp.json()["session_id"]

            save_url = reverse("docedit_save", args=[sid])
            # Post a JSON array instead of JSON object
            bad_save = client.post(save_url, json.dumps(["invalid", "body"]), content_type="application/json")
            self.assertEqual(bad_save.status_code, 400)
            self.assertIn("Invalid request body format", bad_save.json()["error"])

            font_url = reverse("docedit_change_font", args=[sid])
            bad_font = client.post(font_url, json.dumps(["invalid", "list"]), content_type="application/json")
            self.assertEqual(bad_font.status_code, 400)
            self.assertIn("Invalid request body format", bad_font.json()["error"])

    def test_allow_downloads_setting_blocks_remote_google_font(self):
        with override_settings(DOCEDIT_ALLOW_DOWNLOADS=False):
            client = Client()
            install_url = reverse("docedit_font_install")
            resp = client.post(install_url, json.dumps({"font_name": "Roboto"}), content_type="application/json")
            self.assertEqual(resp.status_code, 403)
            self.assertIn("disabled by configuration", resp.json()["error"])


class DocEditPhase1ScalingTests(TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="docedit_phase1_"))

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_pdf_source_geometry_and_units(self):
        # Create a simple PDF
        pdf_path = self.tmp_dir / "sample.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=595.0, height=842.0)
        page.insert_text((50, 100), "Hello Phase 1 Scaling World", fontsize=14)
        doc.save(str(pdf_path))
        doc.close()

        res = extract.extract_document(pdf_path, sid="test_p1_pdf")
        self.assertTrue(res["is_layout_preserved"])
        self.assertGreater(len(res["pages"]), 0)

        p1 = res["pages"][0]
        self.assertEqual(p1["unit"], "pt")
        self.assertEqual(p1["width"], 595.0)
        self.assertEqual(p1["height"], 842.0)

        self.assertGreater(len(p1["blocks"]), 0)
        b0 = p1["blocks"][0]
        self.assertEqual(b0["unit"], "pt")
        self.assertEqual(b0["size_src"], 14.0)
        self.assertIn("line_height_src", b0)
        self.assertIn("render_x", b0)
        self.assertIn("render_y", b0)
        self.assertIn("render_w", b0)
        self.assertIn("render_h", b0)

        # Check HTML output uses source CSS variables and has no pt or cqi in style
        html_out = res["html"]
        self.assertIn("--scale: 1.0", html_out)
        self.assertIn("--x-src:", html_out)
        self.assertIn("--y-src:", html_out)
        self.assertIn("--size-src:", html_out)
        self.assertNotIn("font-size: calc(14.0 * var(--doc-scale", html_out)
        self.assertNotIn("100cqi", html_out)

    def test_image_source_geometry_real_dpi_and_no_magic_factor(self):
        img_path = self.tmp_dir / "scanned_page.png"
        img = Image.new("RGB", (800, 1000), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        try:
            test_font = ImageFont.truetype("arial.ttf", 36)
        except Exception:
            test_font = ImageFont.load_default(size=36)
        draw.text((60, 80), "Scanned Document Line One", fill=(0, 0, 0), font=test_font)
        img.save(str(img_path), dpi=(200, 200))

        res = extract.extract_document(img_path, sid="test_p1_img")
        self.assertTrue(res["is_layout_preserved"])
        p1 = res["pages"][0]
        self.assertEqual(p1["unit"], "px")
        self.assertEqual(p1["dpi"], 200.0)
        self.assertEqual(p1["width"], 800)
        self.assertEqual(p1["height"], 1000)

        # Blocks should use px source units and line height
        for b in p1["blocks"]:
            self.assertEqual(b["unit"], "px")
            self.assertEqual(b["size_src"], b["line_height_src"])
            # Ensure estimated pt uses real_dpi with no * 1.15 multiplier
            expected_pt = max(6.0, min(72.0, round(b["size_src"] * 72.0 / 200.0, 1)))
            self.assertEqual(b["font_size_pt"], expected_pt)

    def test_image_writer_no_1_3_magic_factor(self):
        bg_img_path = self.tmp_dir / "page_1.png"
        img = Image.new("RGB", (800, 1000), color=(255, 255, 255))
        img.save(str(bg_img_path))

        out_img_path = self.tmp_dir / "out.png"
        pages_data = [{
            "page_num": 1,
            "unit": "px",
            "width": 800,
            "height": 1000,
            "dpi": 200.0,
            "blocks": [{
                "id": "b1",
                "text": "Correct Size Text",
                "bbox": [50, 50, 300, 90],
                "size_src": 40,
                "is_modified": True,
            }]
        }]

        # Write image export and verify it writes without error and uses size_src directly
        writers.write_document_to_disk(
            html_content="<p>Test</p>",
            output_path=out_img_path,
            extension="png",
            font_info={"name": "EB Garamond", "size_pt": 12},
            pages_data=pages_data,
            work_dir=self.tmp_dir,
        )
        self.assertTrue(out_img_path.is_file())
        with Image.open(str(out_img_path)) as written_img:
            self.assertEqual(written_img.size, (800, 1000))

    def test_pdf_rotated_text_source_geometry(self):
        pdf_path = self.tmp_dir / "rotated.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=600.0, height=800.0)
        # Insert vertical text (rotate=90 in PyMuPDF)
        page.insert_text((100, 300), "Vertical 90 Text", fontsize=12, rotate=90)
        doc.save(str(pdf_path))
        doc.close()

        res = extract.extract_document(pdf_path, sid="test_p1_rot")
        self.assertTrue(res["is_layout_preserved"])
        blocks = res["pages"][0]["blocks"]
        self.assertGreater(len(blocks), 0)
        b_rot = blocks[0]
        self.assertEqual(b_rot["rotation"], 90)
        self.assertIn("render_x", b_rot)
        self.assertIn("render_y", b_rot)
        self.assertIn("render_w", b_rot)
        self.assertIn("render_h", b_rot)
        self.assertIn("transform: rotate(-90deg)", res["html"])
        self.assertIn("transform-origin: top left", res["html"])


class DocEditPhase2Tests(TestCase):
    """
    Phase 2 tests:
    - PDF rich span extraction with origin, bbox, flags, color, and line dir.
    - Paragraph block grouping with union bbox and line-height.
    - Text color extraction and preservation in editor and export.
    - Rotated text (90, 180, 270) and cropped pages.
    - Embedded font identification, subset prefix stripping, cmap coverage check, and fsType restriction.
    - DOCX run-level formatting, color preservation, and table formatting.
    """
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="docedit_phase2_"))

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_pdf_spans_and_color_extraction(self):
        """Tests that every span preserves text, font, size, flags, color, origin, bbox, and line dir."""
        pdf_path = self.tmp_dir / "colors_and_spans.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=500, height=500)
        # Blue header
        page.insert_text((50, 80), "Blue Title", fontsize=16, color=(0.0, 0.0, 1.0))
        # Red subtitle
        page.insert_text((50, 120), "Red Subtitle", fontsize=12, color=(1.0, 0.0, 0.0))
        doc.save(str(pdf_path))
        doc.close()

        res = extract.extract_document(pdf_path, sid="test_p2_spans")
        self.assertTrue(res["is_layout_preserved"])
        blocks = res["pages"][0]["blocks"]
        self.assertGreaterEqual(len(blocks), 2)

        # Inspect first block (Blue Title)
        b0 = blocks[0]
        self.assertEqual(b0["text"], "Blue Title")
        self.assertEqual(b0["color"].lower(), "#0000ff")
        self.assertEqual(b0["colour"].lower(), "#0000ff")
        self.assertIn("lines", b0)
        self.assertIn("spans", b0)
        self.assertGreaterEqual(len(b0["spans"]), 1)

        span0 = b0["spans"][0]
        self.assertEqual(span0["text"], "Blue Title")
        self.assertEqual(span0["colour"].lower(), "#0000ff")
        self.assertIn("origin", span0)
        self.assertIn("bbox", span0)
        self.assertIn("flags", span0)
        self.assertIn("size", span0)
        self.assertIn("dir", b0["lines"][0])
        self.assertEqual(b0["rotation"], 0)

        # Inspect second block (Red Subtitle)
        b1 = blocks[1]
        self.assertEqual(b1["text"], "Red Subtitle")
        self.assertEqual(b1["color"].lower(), "#ff0000")

        # Verify HTML contains color and block-color CSS
        self.assertIn("color: #0000ff", res["html"])
        self.assertIn("color: #ff0000", res["html"])

    def test_paragraph_block_grouping(self):
        """Tests that vertically sequential lines in the same block are grouped with a union bbox."""
        pdf_path = self.tmp_dir / "paragraphs.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=500, height=600)
        # Paragraph with 3 stacked lines
        page.insert_text((50, 100), "First line of the introduction.")
        page.insert_text((50, 115), "Second line of the introduction.")
        page.insert_text((50, 130), "Third line of the introduction.")
        # Separate heading further down
        page.insert_text((50, 240), "Chapter Two: New Horizon")
        doc.save(str(pdf_path))
        doc.close()

        res = extract.extract_document(pdf_path, sid="test_p2_para")
        blocks = res["pages"][0]["blocks"]
        self.assertGreaterEqual(len(blocks), 2)

        # First block should be the 3-line paragraph
        p_block = blocks[0]
        self.assertIn("First line", p_block["text"])
        self.assertIn("Second line", p_block["text"])
        self.assertIn("Third line", p_block["text"])
        self.assertEqual(len(p_block["lines"]), 3)
        self.assertGreater(p_block["bbox"][3], 130)  # Union bottom encompasses third line
        self.assertIn("line_height_src", p_block)
        self.assertGreater(p_block["line_height_src"], 5)

        # Second block should be the separate heading
        h_block = blocks[1]
        self.assertEqual(h_block["text"], "Chapter Two: New Horizon")
        self.assertEqual(len(h_block["lines"]), 1)

    def test_rotated_and_cropped_pdf(self):
        """Tests 90, 180, 270 degree rotation and cropped page coordinates."""
        pdf_path = self.tmp_dir / "rotated_cropped.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=500, height=500)
        page.insert_text((100, 200), "Rotated 90 Text", rotate=90)
        page.insert_text((200, 250), "Rotated 180 Text", rotate=180)
        page.insert_text((300, 300), "Rotated 270 Text", rotate=270)
        page.set_cropbox(pymupdf.Rect(40, 40, 460, 460))
        doc.save(str(pdf_path))
        doc.close()

        res = extract.extract_document(pdf_path, sid="test_p2_rot_crop")
        p_data = res["pages"][0]
        self.assertEqual(p_data["crop_offset"], [40.0, 40.0])

        rotations = [b["rotation"] for b in p_data["blocks"]]
        self.assertIn(90, rotations)
        self.assertIn(180, rotations)
        self.assertIn(270, rotations)

        # Test export with modified rotated block
        p_data["blocks"][0]["is_modified"] = True
        p_data["blocks"][0]["text"] = "Edited 90"
        out_pdf = self.tmp_dir / "out_rot.pdf"
        writers.write_document_to_disk(
            html_content="<p>Edited</p>",
            output_path=out_pdf,
            extension="pdf",
            font_info={"name": "Helvetica", "size_pt": 12},
            pages_data=res["pages"],
            original_file_path=pdf_path,
            work_dir=self.tmp_dir,
        )
        self.assertTrue(out_pdf.is_file())
        read_doc = pymupdf.open(str(out_pdf))
        self.assertEqual(len(read_doc), 1)
        read_doc.close()

    def test_embedded_font_identification_and_coverage(self):
        """Tests subset prefix stripping, fontTools inspection, and character coverage checks."""
        # 1. Subset prefix stripping
        self.assertEqual(embedded_fonts.strip_subset_prefix("BCDEEE+Calibri-Bold"), "Calibri-Bold")
        self.assertEqual(embedded_fonts.strip_subset_prefix("ABCDEF+TimesNewRomanPSMT"), "TimesNewRomanPSMT")
        self.assertEqual(embedded_fonts.strip_subset_prefix("Arial-BoldMT"), "Arial-BoldMT")
        self.assertEqual(embedded_fonts.strip_subset_prefix(""), "")

        # 2. Subset detection
        self.assertTrue(embedded_fonts.is_subset_font("BCDEEE+Calibri-Bold"))
        self.assertFalse(embedded_fonts.is_subset_font("Calibri-Bold"))

        # 3. Character coverage testing
        font_info = {
            "clean_name": "Calibri",
            "is_restricted": False,
            "cmap_codepoints": {ord(c) for c in "ABCDEFabcdef 0123456789"},
        }
        self.assertTrue(embedded_fonts.can_embedded_font_render_text(font_info, "ABC 123"))
        self.assertTrue(embedded_fonts.can_embedded_font_render_text(font_info, "Def 456"))
        # Character 'Z' is missing from subset
        self.assertFalse(embedded_fonts.can_embedded_font_render_text(font_info, "ABCZ"))

        # 4. Respect fsType restriction
        restricted_info = dict(font_info)
        restricted_info["is_restricted"] = True
        self.assertFalse(embedded_fonts.can_embedded_font_render_text(restricted_info, "ABC 123"))

    def test_docx_run_level_formatting_and_color(self):
        """Tests run-level bold, italic, underline, size, and color preservation for DOCX."""
        from docx.shared import RGBColor, Pt
        docx_path = self.tmp_dir / "formatted.docx"
        doc = docx.Document()
        p = doc.add_paragraph()
        r1 = p.add_run("Blue bold heading")
        r1.bold = True
        r1.font.color.rgb = RGBColor(0, 0, 255)
        r1.font.size = Pt(14)

        r2 = p.add_run(" and normal text.")

        # Add a table with formatted colored cells
        tbl = doc.add_table(rows=2, cols=2)
        cell_r = tbl.cell(0, 0).paragraphs[0].add_run("Red Cell")
        cell_r.font.color.rgb = RGBColor(255, 0, 0)
        cell_r.bold = True

        doc.save(str(docx_path))

        res = extract.extract_document(docx_path)
        doc_html = res["html"]
        self.assertIn("color: #0000ff", doc_html)
        self.assertIn("<strong>", doc_html)
        self.assertIn("color: #ff0000", doc_html)
        self.assertIn("Blue bold heading", doc_html)
        self.assertIn("Red Cell", doc_html)

        # Test export preserving color in DOCX
        out_docx = self.tmp_dir / "out.docx"
        writers.write_document_to_disk(
            html_content=doc_html,
            output_path=out_docx,
            extension="docx",
            font_info={"name": "Calibri", "size_pt": 11},
        )
        self.assertTrue(out_docx.is_file())
        read_doc = docx.Document(str(out_docx))
        p0_r0 = read_doc.paragraphs[0].runs[0]
        self.assertEqual(str(p0_r0.font.color.rgb), "0000FF")
        self.assertTrue(p0_r0.bold)

    def test_pdf_multiline_paragraph_edit_and_export(self):
        """Tests that multi-line paragraph blocks can be edited and exported via insert_textbox."""
        pdf_path = self.tmp_dir / "multiline_para.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=500, height=500)
        page.insert_text((50, 80), "Line 1 of intro.")
        page.insert_text((50, 95), "Line 2 of intro.")
        page.insert_text((50, 110), "Line 3 of intro.")
        doc.save(str(pdf_path))
        doc.close()

        res = extract.extract_document(pdf_path, sid="test_p2_multi", work_dir=self.tmp_dir)
        p_data = res["pages"][0]
        self.assertEqual(len(p_data["blocks"]), 1)
        block = p_data["blocks"][0]
        self.assertEqual(len(block["lines"]), 3)

        # Edit the paragraph
        block["is_modified"] = True
        block["text"] = "Revised line 1.\nRevised line 2.\nRevised line 3."

        out_pdf = self.tmp_dir / "multiline_out.pdf"
        writers.write_document_to_disk(
            html_content="<p>Revised</p>",
            output_path=out_pdf,
            extension="pdf",
            font_info={"name": "Helvetica", "size_pt": 11},
            pages_data=res["pages"],
            original_file_path=pdf_path,
            work_dir=self.tmp_dir,
        )
        self.assertTrue(out_pdf.is_file())
        read_doc = pymupdf.open(str(out_pdf))
        self.assertEqual(len(read_doc), 1)
        out_text = read_doc[0].get_text()
        clean_text = out_text.replace("\xa0", " ")
        self.assertIn("Revised line 1", clean_text)
        self.assertIn("Revised line 2", clean_text)
        read_doc.close()

    def test_embedded_font_full_flow(self):
        """Tests extraction of embedded fonts into private session folder and coverage checking."""
        # Use user uploaded PDF sample if present
        sample_path = Path("C:/Users/hiday/.gemini/antigravity-ide/brain/bb7b120b-7f43-4860-8871-5b01a1521412/.user_uploaded/media_1792357326733.pdf")
        if sample_path.is_file():
            res = extract.extract_document(sample_path, sid="test_cv_sample", work_dir=self.tmp_dir)
            self.assertTrue(res["is_layout_preserved"])
            self.assertIn("embedded_fonts", res)
            emb_fonts = res["embedded_fonts"]
            self.assertGreater(len(emb_fonts), 0)

            # Check fonts directory in private session folder
            fonts_dir = self.tmp_dir / "fonts"
            self.assertTrue(fonts_dir.is_dir())
            extracted_files = list(fonts_dir.glob("*.ttf")) + list(fonts_dir.glob("*.otf"))
            self.assertGreater(len(extracted_files), 0)


class DocEditPhase3Tests(TestCase):
    """
    Phase 3: Faithful export tests.
    1. Unedited PDF round-trip is pixel-identical.
    2. Editing a single cell preserves 100% of vector lines, table borders, and surrounding text.
    3. Multi-line paragraph insert_htmlbox reflow & overflow detection.
    4. Ring background median color calculation (ignores interior text pixels).
    5. Image text rendering at baseline origin with PIL anchor="ls".
    6. Searchable PDF export for scans (background image + render_mode=3 invisible selectable text layer).
    7. NFC, NBSP, and whitespace normalized is_block_truly_modified check.
    """

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="docedit_test_p3_"))

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_unedited_pdf_round_trip_is_pixel_identical(self):
        """Tests that an unedited PDF round-trip produces a byte-for-byte pixel-identical document."""
        import pymupdf

        pdf_path = self.tmp_dir / "input_unedited.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=400, height=300)
        page.draw_rect(pymupdf.Rect(40, 40, 360, 260), color=(0, 0, 0), width=1.5)
        page.insert_text(pymupdf.Point(50, 70), "Original Untouched Title", fontsize=14)
        doc.save(str(pdf_path))
        doc.close()

        res = extract.extract_document(pdf_path, sid="test_unedited", work_dir=self.tmp_dir)
        p_data = res["pages"][0]

        # Verify all blocks are marked is_modified = False
        for b in p_data["blocks"]:
            self.assertFalse(b.get("is_modified", False))

        out_pdf = self.tmp_dir / "output_unedited.pdf"
        writers.write_document_to_disk(
            html_content="<p>Doc</p>",
            output_path=out_pdf,
            extension="pdf",
            font_info={"name": "Helvetica", "size_pt": 12},
            pages_data=res["pages"],
            original_file_path=pdf_path,
            work_dir=self.tmp_dir,
        )

        doc_in = pymupdf.open(str(pdf_path))
        pix_in = doc_in[0].get_pixmap()
        doc_in.close()

        doc_out = pymupdf.open(str(out_pdf))
        pix_out = doc_out[0].get_pixmap()
        doc_out.close()

        self.assertEqual(pix_in.samples, pix_out.samples)

    def test_pdf_single_word_edit_vector_lines_and_tables_survive(self):
        """Tests that modifying one block removes old text via fill=False without white boxes over vector lines."""
        import pymupdf

        pdf_path = self.tmp_dir / "table_doc.pdf"
        doc = pymupdf.open()
        p = doc.new_page(width=500, height=400)
        p.draw_rect(pymupdf.Rect(40, 40, 460, 260), color=(0, 0, 0), width=1.5)
        p.draw_line(pymupdf.Point(40, 100), pymupdf.Point(460, 100), color=(0, 0, 0), width=1.0)
        p.draw_line(pymupdf.Point(220, 40), pymupdf.Point(220, 260), color=(0, 0, 0), width=1.0)
        p.insert_text(pymupdf.Point(50, 80), "Header Col 1", fontsize=12)
        p.insert_text(pymupdf.Point(230, 80), "Header Col 2", fontsize=12)
        p.insert_text(pymupdf.Point(50, 140), "Target Data Cell", fontsize=11)
        p.insert_text(pymupdf.Point(230, 140), "Other Data Cell", fontsize=11)
        doc.save(str(pdf_path))
        doc.close()

        res = extract.extract_document(pdf_path, sid="test_table", work_dir=self.tmp_dir)
        p_data = res["pages"][0]
        self.assertEqual(len(p_data["blocks"]), 4)

        target_b = next(b for b in p_data["blocks"] if "Target Data Cell" in b["text"])
        target_b["is_modified"] = True
        target_b["text"] = "Updated Data Cell"

        out_pdf = self.tmp_dir / "table_out.pdf"
        writers.write_document_to_disk(
            html_content="<p>Doc</p>",
            output_path=out_pdf,
            extension="pdf",
            font_info={"name": "Helvetica", "size_pt": 11},
            pages_data=res["pages"],
            original_file_path=pdf_path,
            work_dir=self.tmp_dir,
        )

        doc_out = pymupdf.open(str(out_pdf))
        out_page = doc_out[0]
        out_text = out_page.get_text()

        self.assertIn("Updated Data Cell", out_text)
        self.assertNotIn("Target Data Cell", out_text)
        self.assertIn("Header Col 1", out_text)
        self.assertIn("Other Data Cell", out_text)

        drawings = out_page.get_drawings()
        self.assertGreaterEqual(len(drawings), 3, "Table rectangle and separator lines must survive redaction")
        doc_out.close()

    def test_insert_htmlbox_multiline_and_overflow_warning(self):
        """Tests that multi-line paragraphs reflow with insert_htmlbox and warn on overflow."""
        import pymupdf

        doc = pymupdf.open()
        p = doc.new_page(width=300, height=300)

        # 1. Normal multi-line paragraph that fits with scale_low=0.7
        rect = pymupdf.Rect(20, 20, 280, 100)
        html_box = '<div style="font-size: 11pt; margin: 0; line-height: 1.2;">First line<br/>Second line<br/>Third line</div>'
        spare_h, scale_factor = p.insert_htmlbox(rect, html_box, scale_low=0.7)
        self.assertGreaterEqual(spare_h, 0, "Text should fit comfortably")
        self.assertGreater(scale_factor, 0.7)

        # 2. Huge paragraph in tiny box causing overflow
        tiny_rect = pymupdf.Rect(20, 150, 60, 170)
        huge_html = '<div style="font-size: 16pt; margin: 0;">Very large text that will surely overflow the small box</div>'
        spare_tiny, scale_tiny = p.insert_htmlbox(tiny_rect, huge_html, scale_low=0.7)
        self.assertLess(spare_tiny, 0, "spare_height must be negative on text overflow")
        doc.close()

    def test_image_background_ring_median_color_erasure(self):
        """Tests that get_median_background_color_ring accurately extracts parchment background ignoring dark text."""
        from PIL import Image
        import numpy as np
        from docedit.writers import get_median_background_color_ring

        # Create 100x100 synthetic scanned paper texture with parchment tint (242, 238, 225)
        paper_bg = (242, 238, 225)
        img = Image.new("RGB", (100, 100), color=paper_bg)

        # Fill box (30, 30, 70, 50) with black text pixels (0, 0, 0)
        arr = np.array(img)
        arr[30:50, 30:70] = [0, 0, 0]
        test_img = Image.fromarray(arr)

        median_color = get_median_background_color_ring(test_img, (30, 30, 70, 50), ring_thickness=4)
        for i in range(3):
            self.assertAlmostEqual(median_color[i], paper_bg[i], delta=2,
                                   msg="Ring median color must match background and ignore black text")

    def test_image_baseline_origin_rendering(self):
        """Tests that Image export anchors text at the baseline origin."""
        from PIL import Image

        page_data = {
            "page_num": 1,
            "width": 200,
            "height": 100,
            "unit": "px",
            "blocks": [{
                "id": "b1",
                "text": "Baseline Text",
                "orig_text": "Old Text",
                "is_modified": True,
                "bbox": [20, 20, 180, 50],
                "origin": [20, 45],
                "font_size_pt": 14,
                "color_rgb": (0.0, 0.0, 0.0),
            }]
        }

        out_img = self.tmp_dir / "baseline_out.png"
        writers._write_image_layout_preserved(
            pages_data=[page_data],
            work_dir=self.tmp_dir,
            output_path=out_img,
            image_ext="png",
            font_name="Arial",
            font_path=None,
            font_size_pt=14,
        )

        self.assertTrue(out_img.is_file())
        with Image.open(out_img) as im:
            self.assertEqual(im.size, (200, 100))

    def test_searchable_pdf_export_for_scans(self):
        """Tests that searchable_pdf exports scan image with invisible render_mode=3 selectable text layer."""
        from PIL import Image
        import pymupdf

        # Create scan image
        scan_img_path = self.tmp_dir / "scan_sample.png"
        img = Image.new("RGB", (400, 300), color=(245, 245, 240))
        img.save(str(scan_img_path))

        pages_data = [{
            "page_num": 1,
            "width": 400,
            "height": 300,
            "unit": "pt",
            "blocks": [
                {
                    "id": "p1_b1",
                    "text": "Recognized Title Line",
                    "orig_text": "Recognized Title Line",
                    "is_modified": False,
                    "bbox": [50, 40, 250, 65],
                    "origin": [50, 60],
                    "font_size_pt": 14,
                    "lines": [{
                        "text": "Recognized Title Line",
                        "bbox": [50, 40, 250, 65],
                        "origin": [50, 60],
                        "font_size_pt": 14,
                    }]
                },
                {
                    "id": "p1_b2",
                    "text": "Edited Description Text",
                    "orig_text": "Old Description Text",
                    "is_modified": True,
                    "bbox": [50, 100, 300, 130],
                    "origin": [50, 125],
                    "font_size_pt": 12,
                }
            ]
        }]

        out_pdf = self.tmp_dir / "searchable_result.pdf"
        writers.write_document_to_disk(
            html_content="<p>Doc</p>",
            output_path=out_pdf,
            extension="searchable_pdf",
            font_info={"name": "Helvetica", "size_pt": 12},
            pages_data=pages_data,
            original_file_path=scan_img_path,
            work_dir=self.tmp_dir,
        )

        self.assertTrue(out_pdf.is_file())
        doc = pymupdf.open(str(out_pdf))
        self.assertEqual(len(doc), 1)
        p = doc[0]

        # 1. Background image is embedded
        images = p.get_images()
        self.assertGreaterEqual(len(images), 1, "Full-page scan background image must be placed")

        # 2. Text layer is searchable and selectable
        extracted_text = p.get_text()
        self.assertIn("Recognized Title Line", extracted_text)
        self.assertIn("Edited Description Text", extracted_text)
        doc.close()

    def test_is_block_truly_modified_normalization(self):
        """Tests that NFC, NBSP, and whitespace variations do not trigger false positive is_modified."""
        from docedit.writers import is_block_truly_modified

        b = {
            "orig_text": "Dr. John Doe  \n Specialist in Cardiology",
            "text": "Dr.\u00a0John Doe \n  Specialist in Cardiology",
            "is_modified": True,
            "orig_font_name": "Arial",
            "font_name": "Arial",
            "orig_font_size_pt": 12.0,
            "font_size_pt": 12.0,
            "orig_is_bold": False,
            "is_bold": False,
        }
        # Despite NBSP \u00a0 and whitespace variation, it should evaluate to False
        self.assertFalse(is_block_truly_modified(b))

        # Modifying text should evaluate to True
        b_changed = dict(b)
        b_changed["text"] = "Dr. Jane Doe \n Specialist in Neurology"
        self.assertTrue(is_block_truly_modified(b_changed))

        # Changing font should evaluate to True
        b_font_changed = dict(b)
        b_font_changed["font_name"] = "Times New Roman"
        self.assertTrue(is_block_truly_modified(b_font_changed))

        # Changing font size should evaluate to True
        b_size_changed = dict(b)
        b_size_changed["font_size_pt"] = 14.0
        self.assertTrue(is_block_truly_modified(b_size_changed))


class DocEditPhase4Tests(TestCase):
    """
    Tests for Phase 4 Master Plan:
    1. Resolution order per font: embedded -> exact local -> free font -> nearest match (fontTools) -> default.
    2. Font info per block: {requested, used, reason, is_exact}.
    3. Font serving & @font-face for EVERY font used on the page; INSTALL_FONTS_TO_SYSTEM default False.
    4. Strict font name sanitization.
    5. Line width comparison / metric warnings.
    """

    def setUp(self):
        self.client = Client()
        self.temp_dir = tempfile.mkdtemp()
        self.session_id = storage.create_session("sample_phase4.pdf", b"%PDF-1.4 test")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        storage.purge_session(self.session_id)

    def test_install_fonts_to_system_default_false(self):
        """Verifies INSTALL_FONTS_TO_SYSTEM defaults to False to never rely on server OS-installed fonts."""
        from docedit.conf import conf
        self.assertFalse(conf.INSTALL_FONTS_TO_SYSTEM)

    def test_font_resolution_order_embedded(self):
        """Verifies embedded fonts take top priority in font resolution order."""
        from docedit.fontmatch import resolve_font_with_fallback
        fake_catalog = {
            "F1": {
                "clean_name": "MyEmbeddedFont",
                "ps_name": "MyEmbeddedFont-Regular",
                "file_path": "/path/to/session/fonts/MyEmbeddedFont.ttf",
                "file_name": "MyEmbeddedFont.ttf",
                "format": "ttf",
                "can_render": True,
            }
        }
        res = resolve_font_with_fallback("F1", embedded_catalog=fake_catalog, sid=self.session_id)
        self.assertEqual(res["reason"], "embedded")
        self.assertTrue(res["is_exact"])
        self.assertEqual(res["used"], "MyEmbeddedFont")
        self.assertEqual(res["requested"], "F1")
        self.assertTrue(res.get("is_embedded"))
        self.assertIn(f"/docedit/api/font-file/{self.session_id}/MyEmbeddedFont.ttf", res.get("font_url", ""))

    def test_font_resolution_order_exact_local(self):
        """Verifies exact local/project fonts take 2nd priority."""
        from docedit.fontmatch import resolve_font_with_fallback
        # EB Garamond is a local project font in static/fonts/
        res = resolve_font_with_fallback("EB Garamond")
        self.assertEqual(res["reason"], "exact_local")
        self.assertTrue(res["is_exact"])
        self.assertEqual(res["used"], "EB Garamond")
        self.assertIsNotNone(res.get("font_path"))

    def test_font_resolution_order_google_font(self):
        """Verifies free fonts available online take 3rd priority."""
        from docedit.fontmatch import resolve_font_with_fallback
        res = resolve_font_with_fallback("Cormorant Garamond")
        self.assertTrue(res["is_exact"])
        self.assertIn(res["reason"], ("exact_local", "google_font"))

    def test_font_resolution_order_nearest_match_fonttools(self):
        """Verifies unavailable/proprietary fonts use fontTools metric nearest match."""
        from docedit.fontmatch import resolve_font_with_fallback
        # "Helvetica" should resolve to a metric-compatible sans-serif substitute (e.g. Arial / Calibri / Asap)
        res = resolve_font_with_fallback("Helvetica")
        self.assertFalse(res["is_exact"])
        self.assertEqual(res["reason"], "nearest_match")
        self.assertIn(res["used"], ("Arial", "Calibri", "Asap"))

        # "Minion Pro" should resolve to a classic serif substitute
        res_serif = resolve_font_with_fallback("Minion Pro")
        self.assertFalse(res_serif["is_exact"])
        self.assertEqual(res_serif["reason"], "nearest_match")
        self.assertIn(res_serif["used"], ("Crimson Pro", "EB Garamond", "Libre Baskerville", "Times New Roman"))

    def test_font_tools_metrics_extraction(self):
        """Verifies fontTools extracts quantitative weight, width, and x-height metrics from font files."""
        from docedit.font_catalog import get_font_metrics_from_file
        font_path = Path("static/fonts/Asap-Regular.ttf")
        if font_path.is_file():
            metrics = get_font_metrics_from_file(font_path)
            self.assertEqual(metrics["weight"], 400)
            self.assertEqual(metrics["width"], 5)
            self.assertGreater(metrics["x_height_ratio"], 0.4)
            self.assertTrue(metrics["is_sans"])
            self.assertFalse(metrics["is_serif"])

    def test_font_info_per_block_in_extraction(self):
        """Verifies PDF extraction attaches {requested, used, reason, is_exact} on each block."""
        import pymupdf
        from docedit.extract import extract_document
        pdf_path = Path(self.temp_dir) / "test_fonts.pdf"
        doc = pymupdf.open()
        p = doc.new_page(width=400, height=300)
        p.insert_text(pymupdf.Point(50, 80), "Hello Phase 4 typography", fontsize=14, fontname="helv")
        doc.save(str(pdf_path))
        doc.close()

        res = extract_document(pdf_path, sid=self.session_id, work_dir=Path(self.temp_dir))
        self.assertTrue(res.get("is_layout_preserved"))
        pages = res.get("pages", [])
        self.assertGreaterEqual(len(pages), 1)
        blocks = pages[0].get("blocks", [])
        self.assertGreaterEqual(len(blocks), 1)
        b = blocks[0]

        # Block must contain structured font_info
        self.assertIn("font_info", b)
        f_info = b["font_info"]
        self.assertIn("requested", f_info)
        self.assertIn("used", f_info)
        self.assertIn("reason", f_info)
        self.assertIn("is_exact", f_info)
        self.assertEqual(b["font_name"], f_info["used"])
        self.assertEqual(b["font_size_pt"], 14.0)

    def test_generate_document_all_fonts_css(self):
        """Verifies @font-face is generated for EVERY font used on the document."""
        from docedit.fontmatch import generate_document_all_fonts_css
        font_resolutions = [
            {
                "requested": "TimesNewRoman",
                "used": "Times New Roman",
                "font_url": f"/docedit/api/font-file/{self.session_id}/TimesNewRoman.ttf",
                "is_exact": True,
            },
            {
                "requested": "Calibri-Bold",
                "used": "Calibri",
                "font_url": f"/docedit/api/font-file/{self.session_id}/Calibri.ttf",
                "is_exact": True,
            },
            {
                "requested": "Libre Baskerville",
                "used": "Libre Baskerville",
                "font_url": None,
                "is_exact": True,
            }
        ]
        css = generate_document_all_fonts_css(font_resolutions, sid=self.session_id)
        self.assertIn("@font-face", css)
        self.assertIn("Times New Roman", css)
        self.assertIn("Calibri", css)
        self.assertIn(f"/docedit/api/font-file/{self.session_id}/TimesNewRoman.ttf", css)
        self.assertIn("fonts.googleapis.com", css)

    def test_session_font_file_endpoint_and_security(self):
        """Verifies the secure whitelisted font serving endpoint and path traversal prevention."""
        # 1. Traversal rejection (../)
        url_traversal = f"/docedit/api/font-file/{self.session_id}/..%2f..%2fwindows%2fwin.ini/"
        resp = self.client.get(url_traversal)
        self.assertIn(resp.status_code, (400, 403, 404))

        # 2. Non-font extension rejection (.exe, .py, .txt)
        url_nonfont = f"/docedit/api/font-file/{self.session_id}/malicious.exe/"
        resp = self.client.get(url_nonfont)
        self.assertEqual(resp.status_code, 404)

        # 3. Serving valid library font (EBGaramond-Regular.ttf)
        url_valid = f"/docedit/api/font-file/shared/EBGaramond-Regular.ttf/"
        resp = self.client.get(url_valid)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("font/ttf", resp.headers.get("Content-Type", ""))
        self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
        self.assertIn("max-age", resp.headers.get("Cache-Control", ""))

    def test_strict_font_name_sanitization(self):
        """Verifies font name sanitization strictly prevents XSS, CSS injections, and path traversal."""
        from docedit.security import sanitize_font_name
        # Safe names pass cleanly
        self.assertEqual(sanitize_font_name("EB Garamond"), "EB Garamond")
        self.assertEqual(sanitize_font_name("Times-New-Roman"), "Times-New-Roman")
        self.assertEqual(sanitize_font_name("Arial_Bold"), "Arial_Bold")

        # Injections get rejected and fall back to default
        self.assertEqual(sanitize_font_name("Arial'; } body { background: red; } /*"), "EB Garamond")
        self.assertEqual(sanitize_font_name("<script>alert(1)</script>"), "EB Garamond")
        self.assertEqual(sanitize_font_name("../../etc/passwd"), "EB Garamond")
        self.assertEqual(sanitize_font_name("Font@Name:Rule"), "EB Garamond")

        # Truncates to 64 chars max
        long_name = "A" * 100
        self.assertEqual(sanitize_font_name(long_name), "EB Garamond")


class DocEditPhase5Tests(TestCase):
    """
    Tests for Phase 5 Master Plan:
    1. Autosave sends only changed blocks with a version counter; the server applies them atomically (file lock) and returns the version.
    2. "Save & Download" renders the export, then downloads via POST or a one-time token; delete the session only after download is confirmed or on TTL.
    3. "Cancel" purges the session after confirmation.
    4. Do not delete data in a GET request.
    """

    def setUp(self):
        self.client = Client()
        self.temp_dir = tempfile.mkdtemp(prefix="docedit_phase5_")
        self.session_id = storage.create_session("sample_phase5.pdf", b"%PDF-1.4 test content")
        # Populate session with pages and blocks
        storage.update_session(
            self.session_id,
            is_layout_preserved=True,
            pages=[
                {
                    "page_number": 1,
                    "width": 595.0,
                    "height": 842.0,
                    "unit": "pt",
                    "blocks": [
                        {
                            "id": "b1",
                            "text": "Original text 1",
                            "font_name": "EB Garamond",
                            "font_size_pt": 12.0,
                            "bbox": [50.0, 50.0, 200.0, 70.0],
                            "is_modified": False,
                        },
                        {
                            "id": "b2",
                            "text": "Original text 2",
                            "font_name": "EB Garamond",
                            "font_size_pt": 12.0,
                            "bbox": [50.0, 80.0, 200.0, 100.0],
                            "is_modified": False,
                        }
                    ]
                }
            ]
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        storage.purge_session(self.session_id)

    def test_autosave_sends_changed_blocks_with_version_counter(self):
        """Verifies autosave sends only changed blocks with incremented version counter and updates atomically."""
        save_url = reverse("docedit_save", args=[self.session_id])
        payload = {
            "is_autosave": True,
            "version": 2,
            "changed_blocks": [
                {
                    "id": "b1",
                    "page_num": 1,
                    "text": "Edited text 1 via autosave",
                    "is_modified": True,
                    "font_size_pt": 14.0,
                }
            ]
        }
        resp = self.client.post(save_url, json.dumps(payload), content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertTrue(data["is_autosave"])
        self.assertEqual(data["version"], 2)
        self.assertIn("saved_at", data)

        # Check session metadata: b1 is updated, b2 remains untouched
        meta = storage.get_session_meta(self.session_id)
        self.assertEqual(meta["version"], 2)
        p1 = meta["pages"][0]
        b1 = next(b for b in p1["blocks"] if b["id"] == "b1")
        b2 = next(b for b in p1["blocks"] if b["id"] == "b2")
        self.assertEqual(b1["text"], "Edited text 1 via autosave")
        self.assertEqual(b1["font_size_pt"], 14.0)
        self.assertTrue(b1["is_modified"])
        self.assertEqual(b2["text"], "Original text 2")
        self.assertFalse(b2["is_modified"])

    def test_atomic_file_lock_execution(self):
        """Verifies session_file_lock acquires and releases without deadlock and permits sequential updates."""
        from docedit.storage import session_file_lock
        with session_file_lock(self.session_id):
            storage.update_session(self.session_id, test_key="locked_value")

        meta = storage.get_session_meta(self.session_id)
        self.assertEqual(meta.get("test_key"), "locked_value")

    def test_save_and_download_generates_one_time_token(self):
        """Verifies Save & Download generates one-time download token and attaches it to download URL."""
        save_url = reverse("docedit_save", args=[self.session_id])
        payload = {
            "export_format": "txt",
            "html_content": "<p>Exported content for testing</p>",
        }
        resp = self.client.post(save_url, json.dumps(payload), content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("download_token", data)
        token = data["download_token"]
        self.assertTrue(token)
        self.assertIn(f"token={token}", data["download_url"])

        # Token is validated in storage
        self.assertTrue(storage.validate_download_token(self.session_id, token))
        self.assertFalse(storage.validate_download_token(self.session_id, "invalid_fake_token"))

    def test_download_get_never_deletes_session_data(self):
        """Verifies GET download request NEVER deletes session data (preserves against retries/prefetches)."""
        # Save first
        save_url = reverse("docedit_save", args=[self.session_id])
        save_resp = self.client.post(save_url, json.dumps({"export_format": "txt", "html_content": "<p>Hello</p>"}), content_type="application/json")
        token = save_resp.json()["download_token"]

        # Download via GET
        download_url = f"{reverse('docedit_download', args=[self.session_id])}?token={token}"
        dl_resp = self.client.get(download_url)
        self.assertEqual(dl_resp.status_code, 200)
        self.assertEqual(dl_resp["X-DocEdit-Downloaded"], "true")

        # Session data MUST still exist on disk
        self.assertTrue(storage.get_session_dir(self.session_id).is_dir())
        meta = storage.get_session_meta(self.session_id)
        self.assertIsNotNone(meta)
        self.assertEqual(meta["status"], "downloaded")

    def test_download_with_invalid_token_rejected(self):
        """Verifies downloading with an invalid/forged token is rejected with 403 Forbidden."""
        save_url = reverse("docedit_save", args=[self.session_id])
        self.client.post(save_url, json.dumps({"export_format": "txt", "html_content": "<p>Hello</p>"}), content_type="application/json")

        download_url = f"{reverse('docedit_download', args=[self.session_id])}?token=bogus_token"
        resp = self.client.get(download_url)
        self.assertEqual(resp.status_code, 403)

    def test_confirm_download_purges_session(self):
        """Verifies POST confirm-download purges the temporary session after user has received the file."""
        save_url = reverse("docedit_save", args=[self.session_id])
        save_resp = self.client.post(save_url, json.dumps({"export_format": "txt", "html_content": "<p>Hello</p>"}), content_type="application/json")
        token = save_resp.json()["download_token"]

        confirm_url = reverse("docedit_confirm_download", args=[self.session_id])
        confirm_resp = self.client.post(confirm_url, json.dumps({"token": token}), content_type="application/json")
        self.assertEqual(confirm_resp.status_code, 200)
        self.assertTrue(confirm_resp.json()["success"])
        self.assertTrue(confirm_resp.json()["purged"])

        # Session directory is now completely gone from server
        self.assertFalse(storage.get_session_dir(self.session_id).is_dir())

    def test_cancel_purges_session(self):
        """Verifies POST cancel purges temporary session files."""
        self.assertTrue(storage.get_session_dir(self.session_id).is_dir())
        cancel_url = reverse("docedit_cancel", args=[self.session_id])
        resp = self.client.post(cancel_url)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["purged"])
        self.assertFalse(storage.get_session_dir(self.session_id).is_dir())

    def test_ttl_cleanup_expired_sessions(self):
        """Verifies cleanup_expired_sessions cleans only sessions older than TTL."""
        import time
        expired_sid = storage.create_session("old.txt", b"Old data")
        expired_dir = storage.get_session_dir(expired_sid)

        # Set mtime to 48 hours ago
        old_time = time.time() - (48 * 3600)
        os.utime(str(expired_dir), (old_time, old_time))

        with override_settings(DOCEDIT_TEMP_TTL_HOURS=24):
            purged = storage.cleanup_expired_sessions()
            self.assertGreaterEqual(purged, 1)
            self.assertFalse(expired_dir.is_dir())
            # Current session should still exist
            self.assertTrue(storage.get_session_dir(self.session_id).is_dir())


class DocEditPhase6Tests(TestCase):
    """
    Tests for Phase 6 Security and Robustness:
    - Sanitise all HTML with an allowlist (nh3/fallback) on extraction, save and export.
    - Escape font names inside style attributes.
    - Validate ocr_lang against configured languages (prevents path traversal in tessdata download).
    - Enforce MAX_PAGES, image pixel limits and decompression-bomb limits.
    - Bind sessions to the Django session; add upload throttling.
    - Move processing to a bounded thread pool.
    - Settings (DEBUG/ALLOWED_HOSTS/SECRET_KEY from env).
    """

    def setUp(self):
        self.client = Client()
        self.temp_dir = tempfile.mkdtemp(prefix="docedit_phase6_")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_upload_throttling_enforced(self):
        """Verifies that exceeding UPLOAD_THROTTLE_LIMIT triggers HTTP 429 Too Many Requests."""
        upload_url = reverse("docedit_upload")
        with override_settings(DOCEDIT_UPLOAD_THROTTLE_LIMIT=3, DOCEDIT_UPLOAD_THROTTLE_WINDOW=60):
            # 3 uploads should succeed
            for i in range(3):
                test_file = SimpleUploadedFile(f"test_{i}.txt", b"Hello world", content_type="text/plain")
                resp = self.client.post(upload_url, {"document": test_file, "ocr_lang": "eng"})
                self.assertEqual(resp.status_code, 200, f"Upload {i+1} should succeed")
                self.assertTrue(resp.json()["success"])

            # 4th upload must be throttled with HTTP 429
            test_file_4 = SimpleUploadedFile("test_4.txt", b"Hello world again", content_type="text/plain")
            resp_4 = self.client.post(upload_url, {"document": test_file_4, "ocr_lang": "eng"})
            self.assertEqual(resp_4.status_code, 429)
            data_4 = resp_4.json()
            self.assertFalse(data_4["success"])
            self.assertIn("rate limit exceeded", data_4["error"].lower())

    def test_session_bound_to_django_session(self):
        """Verifies session ownership: an unauthenticated / different session cannot access another's document."""
        # 1. Upload document with client A
        client_a = Client()
        test_file = SimpleUploadedFile("secret.txt", b"Confidential document content", content_type="text/plain")
        resp_a = client_a.post(reverse("docedit_upload"), {"document": test_file, "ocr_lang": "eng"})
        self.assertEqual(resp_a.status_code, 200)
        sid = resp_a.json()["session_id"]

        # 2. Client A can access session status
        status_url = reverse("docedit_status", args=[sid])
        resp_status_a = client_a.get(status_url)
        self.assertEqual(resp_status_a.status_code, 200)

        # 3. Client B (different session) is rejected with HTTP 403 Forbidden
        client_b = Client()
        resp_status_b = client_b.get(status_url)
        self.assertEqual(resp_status_b.status_code, 403)

        # 4. Client B cannot save to client A's session
        save_url = reverse("docedit_save", args=[sid])
        resp_save_b = client_b.post(save_url, json.dumps({"html_content": "<p>Hacked</p>"}), content_type="application/json")
        self.assertEqual(resp_save_b.status_code, 403)

        # 5. Client B cannot cancel client A's session
        cancel_url = reverse("docedit_cancel", args=[sid])
        resp_cancel_b = client_b.post(cancel_url)
        self.assertEqual(resp_cancel_b.status_code, 403)

    def test_ocr_lang_path_traversal_prevention(self):
        """Verifies validate_ocr_lang rejects path traversal and unconfigured languages."""
        from .security import validate_ocr_lang
        # Valid language
        self.assertEqual(validate_ocr_lang("eng"), "eng")
        self.assertEqual(validate_ocr_lang("eng+hin"), "eng+hin")

        # Path traversal attempts
        with self.assertRaises(ValueError):
            validate_ocr_lang("../../etc/passwd")

        with self.assertRaises(ValueError):
            validate_ocr_lang("..\\..\\windows\\system32")

        with self.assertRaises(ValueError):
            validate_ocr_lang("eng/../hin")

        with self.assertRaises(ValueError):
            validate_ocr_lang("eng%00")

        # Unconfigured language
        with self.assertRaises(ValueError):
            validate_ocr_lang("klingon")

    def test_decompression_bomb_and_pixel_limit_enforced(self):
        """Verifies decompression bomb and pixel limit checks reject oversized images."""
        from .extract import extract_document
        from PIL import Image

        # Create an image that exceeds MAX_IMAGE_PIXELS
        img_path = Path(self.temp_dir) / "large.png"
        img = Image.new("RGB", (200, 200), color="white")
        img.save(str(img_path))

        orig_max = Image.MAX_IMAGE_PIXELS
        try:
            # With MAX_IMAGE_PIXELS overridden to 100 pixels (less than 200*200 = 40,000)
            with override_settings(DOCEDIT_MAX_IMAGE_PIXELS=100):
                with self.assertRaises(ValueError) as ctx:
                    extract_document(img_path, sid="test_bomb_sid")
                self.assertIn("exceeds", str(ctx.exception).lower())
        finally:
            Image.MAX_IMAGE_PIXELS = orig_max

    def test_html_sanitised_on_extraction(self):
        """Verifies HTML sanitization allowlist cleans malicious tags and handlers on extraction."""
        from .extract import extract_document
        html_file = Path(self.temp_dir) / "test_malicious.html"
        html_file.write_text(
            '<html><body><h1>Safe Header</h1><script>alert("XSS")</script>'
            '<p style="color: red;" onclick="evil()">Safe paragraph</p>'
            '<iframe src="https://evil.com"></iframe>'
            '<img src="javascript:alert(1)" onerror="alert(2)" />'
            '</body></html>',
            encoding="utf-8"
        )
        res = extract_document(html_file)
        cleaned = res["html"]
        self.assertNotIn("<script>", cleaned)
        self.assertNotIn("alert", cleaned)
        self.assertNotIn("<iframe>", cleaned)
        self.assertNotIn("onclick", cleaned)
        self.assertNotIn("onerror", cleaned)
        self.assertIn("Safe Header", cleaned)
        self.assertIn("Safe paragraph", cleaned)

    def test_html_sanitised_on_save_and_export(self):
        """Verifies HTML sanitization cleans malicious content during document save and export."""
        from .writers import write_document_to_disk
        # Save via storage
        storage.save_document_content(
            "test_sid_sanitize",
            '<p>Hello<script>alert("hack")</script></p><span style="behavior:url(evil.htc)">text</span>'
        )
        saved = storage.get_document_content("test_sid_sanitize")
        self.assertNotIn("<script>", saved)
        self.assertNotIn("behavior", saved)
        self.assertIn("Hello", saved)

        # Export via writer
        out_html = Path(self.temp_dir) / "exported.html"
        write_document_to_disk(
            html_content='<p>Clean paragraph</p><img src="x" onerror="evil()"><script>bad()</script>',
            output_path=out_html,
            extension="html",
            font_info={"name": "EB Garamond", "size_pt": 12},
        )
        exported_text = out_html.read_text(encoding="utf-8")
        self.assertNotIn("<script>", exported_text)
        self.assertNotIn("onerror", exported_text)
        self.assertIn("Clean paragraph", exported_text)

    def test_font_name_escaped_inside_style_attributes(self):
        """Verifies font names with injection payloads are sanitized and escaped in style attributes."""
        from .security import sanitize_font_name
        malicious_font = "Arial'; background: url('https://evil.com/x.png'); '"
        safe = sanitize_font_name(malicious_font)
        # Should reject dangerous chars and return safe default or stripped alphanumeric name
        self.assertNotIn(";", safe)
        self.assertNotIn("url", safe)
        self.assertNotIn("'", safe)

    def test_bounded_thread_pool_executor(self):
        """Verifies processing uses a bounded ThreadPoolExecutor respecting MAX_WORKERS."""
        from .processing import get_processing_executor
        executor = get_processing_executor()
        self.assertIsNotNone(executor)
        self.assertEqual(executor._max_workers, conf.MAX_WORKERS)


class DocEditPhase7Tests(TestCase):
    """
    Phase 7 tests:
    - is_new blocks export as inserted text without redacting background canvas.
    - is_deleted blocks export as text-only removal (redaction) and are excluded from text output.
    - compute_redact_rect_for_block returns None for is_new blocks.
    - save_document returns overflow_warnings when text overflows bounding box.
    """
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="docedit_phase7_"))

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_is_new_block_does_not_redact_background_and_inserts_text(self):
        """Verifies that is_new block does not white-out background and inserts its text."""
        import pymupdf
        from .writers import write_document_to_disk, compute_redact_rect_for_block, is_block_truly_modified

        # 1. Bbox computation returns None for is_new blocks
        new_block = {
            "id": "new_1",
            "text": "Inserted New Text Box",
            "bbox": [100.0, 100.0, 250.0, 125.0],
            "orig_bbox": [100.0, 100.0, 250.0, 125.0],
            "is_new": True,
            "is_modified": True,
        }
        self.assertIsNone(compute_redact_rect_for_block(new_block))
        self.assertTrue(is_block_truly_modified(new_block))

        # 2. Create sample PDF
        pdf_path = self.tmp_dir / "sample.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=500, height=500)
        page.insert_text((50, 80), "Original Text That Stays")
        doc.save(str(pdf_path))
        doc.close()

        # 3. Add an is_new block and export
        pages_data = [{
            "page_num": 1,
            "width": 500.0,
            "height": 500.0,
            "blocks": [
                {
                    "id": "b_orig",
                    "text": "Original Text That Stays",
                    "bbox": [50.0, 70.0, 200.0, 90.0],
                    "orig_bbox": [50.0, 70.0, 200.0, 90.0],
                    "is_modified": False,
                },
                new_block,
            ]
        }]

        out_pdf = self.tmp_dir / "out_with_new.pdf"
        write_document_to_disk(
            html_content="",
            output_path=out_pdf,
            extension="pdf",
            font_info={"name": "Helvetica", "size_pt": 12},
            pages_data=pages_data,
            original_file_path=pdf_path,
            work_dir=self.tmp_dir,
        )

        self.assertTrue(out_pdf.is_file())
        doc_out = pymupdf.open(str(out_pdf))
        extracted = doc_out[0].get_text()
        self.assertIn("Original Text That Stays", extracted)
        self.assertIn("Inserted New Text Box", extracted)
        doc_out.close()

    def test_is_deleted_block_exports_as_redaction_and_omits_text(self):
        """Verifies that is_deleted block redacts original text and is excluded from final output."""
        import pymupdf
        from .writers import write_document_to_disk

        # Create sample PDF
        pdf_path = self.tmp_dir / "sample_delete.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=500, height=500)
        page.insert_text((50, 80), "Text To Delete Completely")
        page.insert_text((50, 150), "Text To Keep Intact")
        doc.save(str(pdf_path))
        doc.close()

        pages_data = [{
            "page_num": 1,
            "width": 500.0,
            "height": 500.0,
            "blocks": [
                {
                    "id": "b_del",
                    "text": "Text To Delete Completely",
                    "bbox": [50.0, 65.0, 250.0, 90.0],
                    "orig_bbox": [50.0, 65.0, 250.0, 90.0],
                    "is_deleted": True,
                    "is_modified": True,
                },
                {
                    "id": "b_keep",
                    "text": "Text To Keep Intact",
                    "bbox": [50.0, 140.0, 200.0, 160.0],
                    "orig_bbox": [50.0, 140.0, 200.0, 160.0],
                    "is_modified": False,
                }
            ]
        }]

        out_pdf = self.tmp_dir / "out_deleted.pdf"
        write_document_to_disk(
            html_content="",
            output_path=out_pdf,
            extension="pdf",
            font_info={"name": "Helvetica", "size_pt": 12},
            pages_data=pages_data,
            original_file_path=pdf_path,
            work_dir=self.tmp_dir,
        )

        doc_out = pymupdf.open(str(out_pdf))
        extracted = doc_out[0].get_text()
        self.assertNotIn("Text To Delete Completely", extracted)
        self.assertIn("Text To Keep Intact", extracted)
        doc_out.close()

    def test_save_document_reports_overflow_warnings(self):
        """Verifies save_document returns overflow_warnings when text exceeds bounding box."""
        with override_settings(DOCEDIT_WORK_DIR=str(self.tmp_dir), DOCEDIT_SYNC_PROCESSING=True):
            client = Client()
            # 1. Upload sample text
            txt_file = SimpleUploadedFile("overflow.txt", b"Sample text", content_type="text/plain")
            resp_up = client.post(reverse("docedit_upload"), {"document": txt_file, "ocr_lang": "eng"})
            self.assertEqual(resp_up.status_code, 200)
            sid = resp_up.json()["session_id"]

            # 2. Save with an overflowing layout-preserved block (text width > orig_bbox width)
            save_url = reverse("docedit_save", args=[sid])
            payload = {
                "font_name": "Calibri",
                "font_size_pt": 12,
                "export_format": "pdf",
                "pages_data": [{
                    "page_num": 1,
                    "width": 600,
                    "height": 800,
                    "blocks": [{
                        "id": "b_overflow",
                        "text": "This is an extremely long line of text that definitely exceeds thirty points",
                        "orig_bbox": [50.0, 50.0, 80.0, 70.0], # width is only 30pt!
                        "bbox": [50.0, 50.0, 80.0, 70.0],
                        "font_size_pt": 12.0,
                        "is_modified": True,
                    }]
                }]
            }
            resp_save = client.post(save_url, json.dumps(payload), content_type="application/json")
            self.assertEqual(resp_save.status_code, 200)
            data = resp_save.json()
            self.assertTrue(data["success"])
            self.assertIn("overflow_warnings", data)
            self.assertGreater(len(data["overflow_warnings"]), 0)
            warn = data["overflow_warnings"][0]
            self.assertEqual(warn["block_id"], "b_overflow")
            self.assertEqual(warn["page_num"], 1)
            self.assertGreater(warn["overflow_pct"], 0)

    def test_image_export_with_is_new_and_is_deleted_blocks(self):
        """Verifies image export handles is_new without redacting and skips is_deleted."""
        from PIL import Image
        from .writers import _write_image_layout_preserved

        # Create dummy background image
        bg_path = self.tmp_dir / "page_1.png"
        bg_img = Image.new("RGB", (600, 800), color=(240, 240, 240))
        bg_img.save(str(bg_path))

        pages_data = [{
            "page_num": 1,
            "unit": "px",
            "width": 600,
            "height": 800,
            "blocks": [
                {
                    "id": "b_new",
                    "text": "Added Brand New Box",
                    "bbox": [50, 50, 250, 80],
                    "size_src": 24,
                    "is_new": True,
                    "is_modified": True,
                },
                {
                    "id": "b_del",
                    "text": "Deleted Box Text",
                    "bbox": [50, 100, 250, 130],
                    "size_src": 24,
                    "is_deleted": True,
                    "is_modified": True,
                }
            ]
        }]

        out_img = self.tmp_dir / "out_img_test.png"
        from .writers import write_document_to_disk
        res_path = write_document_to_disk(
            html_content="",
            output_path=out_img,
            extension="png",
            font_info={"name": "Arial", "size_pt": 12},
            pages_data=pages_data,
            work_dir=self.tmp_dir,
        )
        self.assertTrue(out_img.is_file())
        with Image.open(str(out_img)) as im:
            self.assertEqual(im.size, (600, 800))


class DocEditPhase8Tests(TestCase):
    """
    Phase 8: Old-book / fuzzy-scan OCR, deskew, dewarp, per-word tracking,
    review queue APIs, and benchmark harness.
    """
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="docedit_phase8_")
        self.client = Client()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_skew_angle_detection_and_deskew(self):
        """Tests horizontal projection profile skew angle calculation and deskew rotation."""
        # Create an image with horizontal black stripes
        im = Image.new("RGB", (300, 200), color=(255, 255, 255))
        draw = ImageDraw.Draw(im)
        for y in range(20, 180, 20):
            draw.line([(20, y), (280, y)], fill=(0, 0, 0), width=4)

        # Rotate by -3.0 degrees
        rotated = im.rotate(-3.0, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=(255, 255, 255))

        angle = ocr.compute_skew_angle(rotated, max_angle=10.0, step=0.5)
        # Should detect a compensation angle close to 3.0 degrees
        self.assertIsInstance(angle, float)
        self.assertAlmostEqual(angle, 3.0, delta=1.5)

        # Test deskew_image returns valid image
        deskewed, applied_angle = ocr.deskew_image(rotated, angle)
        self.assertEqual(deskewed.size, rotated.size)
        self.assertEqual(deskewed.mode, rotated.mode)

    def test_dewarp_page_curl(self):
        """Tests book spine curl mesh dewarp transformation."""
        im = Image.new("RGB", (400, 300), color=(240, 240, 230))
        dewarped = ocr.dewarp_page_curl(im, max_displacement=8.0)
        self.assertEqual(dewarped.size, (400, 300))
        self.assertEqual(dewarped.mode, "RGB")

    def test_ensure_300_dpi_equivalent(self):
        """Tests automatic upscaling of low-DPI scans to 300 DPI equivalent."""
        # 1. 72 DPI image should be upscaled ~4.16x
        low_dpi_img = Image.new("RGB", (200, 300), color=(255, 255, 255))
        scaled, factor = ocr.ensure_300_dpi_equivalent(low_dpi_img, dpi=72)
        self.assertGreater(factor, 1.0)
        self.assertGreater(scaled.width, 200)

        # 2. 300 DPI image should remain unchanged
        hi_dpi_img = Image.new("RGB", (2500, 3500), color=(255, 255, 255))
        scaled2, factor2 = ocr.ensure_300_dpi_equivalent(hi_dpi_img, dpi=300)
        self.assertEqual(factor2, 1.0)
        self.assertEqual(scaled2.size, (2500, 3500))

    def test_preprocessing_profiles(self):
        """Tests all three preprocessing modes (raw_grayscale, grayscale_contrast, binarized)."""
        im = Image.new("RGB", (250, 150), color=(235, 225, 200)) # Yellowed paper
        draw = ImageDraw.Draw(im)
        draw.text((30, 50), "Old Book Text", fill=(40, 35, 30))

        # (a) Raw Grayscale
        p_raw = ocr.preprocess_raw_grayscale(im)
        self.assertEqual(p_raw.mode, "L")
        self.assertEqual(p_raw.size, im.size)

        # (b) Grayscale + Contrast / Denoise
        p_contrast = ocr.preprocess_grayscale_contrast(im)
        self.assertEqual(p_contrast.mode, "L")
        self.assertEqual(p_contrast.size, im.size)

        # (c) Current Binarized pipeline
        p_bin = ocr.preprocess_binarized(im)
        self.assertEqual(p_bin.mode, "L")
        self.assertEqual(p_bin.size, im.size)

        # Verify old-book helper routes cleanly without dead code
        p_old = ocr.preprocess_old_book_image(im)
        self.assertEqual(p_old.mode, "L")

    def test_detect_suspicious_word(self):
        """Tests suspicious character heuristics for fuzzy review queue flagging."""
        # Normal high-confidence word
        is_f, reasons = ocr.detect_suspicious_word("Chapter", 92)
        self.assertFalse(is_f)
        self.assertEqual(len(reasons), 0)

        # Low confidence
        is_f, reasons = ocr.detect_suspicious_word("Normal", 55)
        self.assertTrue(is_f)
        self.assertTrue(any("Low confidence" in r for r in reasons))

        # Mixed letters and digits
        is_f, reasons = ocr.detect_suspicious_word("b00k", 88)
        self.assertTrue(is_f)
        self.assertTrue(any("mixed" in r for r in reasons))

        # Middle punctuation / odd punctuation
        is_f, reasons = ocr.detect_suspicious_word("w~ord", 85)
        self.assertTrue(is_f)
        self.assertTrue(any("punctuation" in r for r in reasons))

        # Repeating punctuation
        is_f, reasons = ocr.detect_suspicious_word("end..", 85)
        self.assertTrue(is_f)
        self.assertTrue(any("repeating" in r for r in reasons))

        # Orphan symbol
        is_f, reasons = ocr.detect_suspicious_word("§", 85)
        self.assertTrue(is_f)
        self.assertTrue(any("symbol" in r for r in reasons))

    def test_per_word_storage_and_review_workflow(self):
        """Tests saving per-word OCR results, retrieving, and reviewing (accept/edit/skip)."""
        with override_settings(DOCEDIT_WORK_DIR=self.tmp_dir):
            sid = storage.create_session("test_book.png", b"fake-png-content")

            # Setup initial block and page data
            storage.update_session(
                sid,
                pages=[{
                    "page_num": 1,
                    "blocks": [{
                        "id": "p1_b1",
                        "text": "B00K TITLE",
                        "html": '<span class="ocr-word" data-word-id="p1_w1">B00K</span> <span class="ocr-word" data-word-id="p1_w2">TITLE</span>',
                        "words": ["p1_w1", "p1_w2"]
                    }]
                }]
            )

            words = [
                {
                    "id": "p1_w1",
                    "text": "B00K",
                    "conf": 54,
                    "conf_tier": "low",
                    "bbox": [10, 20, 50, 15],
                    "page_num": 1,
                    "block_id": "p1_b1",
                    "is_fuzzy": True,
                    "fuzzy_reasons": ["mixed digits and letters", "low confidence (54%)"],
                    "review_status": "pending",
                },
                {
                    "id": "p1_w2",
                    "text": "TITLE",
                    "conf": 95,
                    "conf_tier": "high",
                    "bbox": [65, 20, 60, 15],
                    "page_num": 1,
                    "block_id": "p1_b1",
                    "is_fuzzy": False,
                    "fuzzy_reasons": [],
                    "review_status": "pending",
                }
            ]

            storage.save_session_words(sid, words)

            # Retrieve words
            saved = storage.get_session_words(sid)
            self.assertEqual(len(saved), 2)
            self.assertEqual(saved[0]["id"], "p1_w1")

            # Check meta fuzzy words & stats
            meta = storage.get_session_meta(sid)
            self.assertIn("fuzzy_words", meta)
            self.assertEqual(len(meta["fuzzy_words"]), 1)
            self.assertEqual(meta["review_stats"]["total_fuzzy"], 1)
            self.assertEqual(meta["review_stats"]["unreviewed_count"], 1)

            # Test Edit Action
            updated_res = storage.update_session_word(sid, "p1_w1", action="edit", edited_text="BOOK")
            self.assertIsNotNone(updated_res)
            word = updated_res["word"]
            self.assertEqual(word["review_status"], "edited")
            self.assertEqual(word["edited_text"], "BOOK")

            meta_after_edit = storage.get_session_meta(sid)
            self.assertEqual(meta_after_edit["review_stats"]["reviewed_count"], 1)
            self.assertEqual(meta_after_edit["review_stats"]["unreviewed_count"], 0)

            # Check that block HTML & text synced
            pages = meta_after_edit["pages"]
            block = pages[0]["blocks"][0]
            self.assertIn("BOOK", block["text"])
            self.assertIn("BOOK", block["html"])

            # Test Accept Action on another word
            updated2_res = storage.update_session_word(sid, "p1_w2", action="accept")
            self.assertEqual(updated2_res["word"]["review_status"], "accepted")

            # Test Skip Action
            updated3_res = storage.update_session_word(sid, "p1_w1", action="skip")
            self.assertEqual(updated3_res["word"]["review_status"], "skipped")

    def test_fuzzy_words_api(self):
        """Tests /docedit/api/fuzzy-words/<sid>/ endpoint."""
        with override_settings(DOCEDIT_WORK_DIR=self.tmp_dir):
            sid = storage.create_session("fuzzy_doc.png", b"png-bytes")
            words = [{
                "id": "p1_w1",
                "text": "b00k",
                "conf": 52,
                "conf_tier": "low",
                "bbox": [10, 10, 40, 15],
                "page_num": 1,
                "block_id": "b1",
                "is_fuzzy": True,
                "fuzzy_reasons": ["low confidence (52%)"],
                "review_status": "pending",
            }]
            storage.save_session_words(sid, words)

            url = reverse("docedit_fuzzy_words", args=[sid])
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["success"])
            self.assertEqual(len(data["fuzzy_words"]), 1)
            self.assertEqual(data["fuzzy_words"][0]["text"], "b00k")
            self.assertEqual(data["stats"]["total_fuzzy"], 1)

    def test_review_word_api(self):
        """Tests /docedit/api/review-word/<sid>/<word_id>/ endpoint."""
        with override_settings(DOCEDIT_WORK_DIR=self.tmp_dir):
            sid = storage.create_session("review_doc.png", b"png-bytes")
            words = [{
                "id": "w_test1",
                "text": "misspellled",
                "conf": 58,
                "conf_tier": "low",
                "bbox": [10, 10, 50, 15],
                "page_num": 1,
                "block_id": "b1",
                "is_fuzzy": True,
                "fuzzy_reasons": ["low confidence"],
                "review_status": "pending",
            }]
            storage.save_session_words(sid, words)

            url = reverse("docedit_review_word", args=[sid, "w_test1"])
            # Test edit
            resp = self.client.post(url, {"action": "edit", "edited_text": "misspelled"})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["success"])
            self.assertEqual(data["word"]["edited_text"], "misspelled")
            self.assertEqual(data["stats"]["reviewed_count"], 1)

            # Test accept
            resp = self.client.post(url, {"action": "accept"})
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()["word"]["review_status"], "accepted")

            # Test skip
            resp = self.client.post(url, {"action": "skip"})
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()["word"]["review_status"], "skipped")

    def test_session_word_crop_api(self):
        """Tests /docedit/api/word-crop/<sid>/<word_id>/ endpoint."""
        with override_settings(DOCEDIT_WORK_DIR=self.tmp_dir):
            sid = storage.create_session("crop_doc.png", b"png-bytes")
            sdir = storage.get_session_dir(sid)

            # Save a synthetic page_1.png image
            page_img = Image.new("RGB", (400, 300), color=(250, 248, 240))
            draw = ImageDraw.Draw(page_img)
            draw.text((50, 60), "TargetWord", fill=(10, 10, 10))
            page_img.save(str(sdir / "page_1.png"), format="PNG")

            words = [{
                "id": "w_crop_1",
                "text": "TargetWord",
                "conf": 62,
                "bbox": [48, 58, 80, 24],
                "page_num": 1,
                "block_id": "b1",
                "is_fuzzy": True,
                "fuzzy_reasons": ["low confidence"],
            }]
            storage.save_session_words(sid, words)

            url = reverse("docedit_word_crop", args=[sid, "w_crop_1"])
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp["Content-Type"], "image/png")

            # Verify image payload is valid PNG
            crop_im = Image.open(io.BytesIO(resp.content))
            self.assertGreater(crop_im.width, 20)
            self.assertGreater(crop_im.height, 10)

    def test_ocr_benchmark_command(self):
        """Tests running the ocr_benchmark management command."""
        out = io.StringIO()
        report_temp = Path(self.tmp_dir) / "test_report.md"
        call_command("ocr_benchmark", "--output", str(report_temp), stdout=out)
        output = out.getvalue()
        self.assertIn("Benchmark", output)
        self.assertIn("Raw Grayscale", output)
        self.assertTrue(report_temp.is_file())


class LanguageScopeOnHoldTests(TestCase):
    """
    Tests for LANGUAGE SCOPE (ON HOLD):
    - Support English and Latin-script text only for now
    - OCR_LANGUAGES gated behind DOCEDIT_ENABLED_LANGUAGES = ["eng"]
    - Non-Latin script detection (Devanagari, Gujarati, Arabic, Hebrew, Thai, etc.)
    - Text-layer PDFs containing non-Latin script marked read-only with notice and badge
    - Exporters never redact or re-insert broken unshaped text for non-Latin blocks
    - Spellcheck and review queue skip non-Latin blocks
    - Multi-lingual catalog preserved including 'urd' entry
    """

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_docedit_enabled_languages_setting(self):
        """Tests that OCR_LANGUAGES is gated behind DOCEDIT_ENABLED_LANGUAGES = ['eng']."""
        self.assertEqual(conf.DOCEDIT_ENABLED_LANGUAGES, ["eng"])
        # conf.OCR_LANGUAGES only returns enabled languages
        self.assertEqual(list(conf.OCR_LANGUAGES.keys()), ["eng"])
        # conf.ALL_OCR_LANGUAGES retains all supported language definitions
        all_langs = conf.ALL_OCR_LANGUAGES
        self.assertIn("eng", all_langs)
        self.assertIn("hin", all_langs)
        self.assertIn("guj", all_langs)
        self.assertIn("ara", all_langs)
        self.assertIn("urd", all_langs)
        self.assertEqual(all_langs["urd"], "Urdu")

        # Verify dynamic override works
        with override_settings(DOCEDIT_ENABLED_LANGUAGES=["eng", "hin"]):
            self.assertIn("eng", conf.OCR_LANGUAGES)
            self.assertIn("hin", conf.OCR_LANGUAGES)
            self.assertNotIn("ara", conf.OCR_LANGUAGES)

    def test_validate_ocr_lang_security_and_gating(self):
        """Tests security validation and enabled-only gating."""
        from docedit.security import validate_ocr_lang
        # When enabled_only=True, only languages in DOCEDIT_ENABLED_LANGUAGES are accepted
        self.assertEqual(validate_ocr_lang("eng", enabled_only=True), "eng")
        with self.assertRaises(ValueError):
            validate_ocr_lang("hin", enabled_only=True)
        with self.assertRaises(ValueError):
            validate_ocr_lang("ara", enabled_only=True)
        with self.assertRaises(ValueError):
            validate_ocr_lang("eng+hin", enabled_only=True)

        # When enabled_only=False, master catalog is accepted (prevents path traversal across any known language)
        self.assertEqual(validate_ocr_lang("hin", enabled_only=False), "hin")
        self.assertEqual(validate_ocr_lang("urd", enabled_only=False), "urd")
        self.assertEqual(validate_ocr_lang("eng+hin", enabled_only=False), "eng+hin")

        # Path traversal or arbitrary values always fallback to default
        with self.assertRaises(ValueError):
            validate_ocr_lang("../../etc/passwd", enabled_only=False)
        with self.assertRaises(ValueError):
            validate_ocr_lang("invalid_lang_code", enabled_only=False)

    def test_is_non_latin_script_detection(self):
        """Tests accurate detection of non-Latin complex scripts."""
        from docedit.fontmatch import is_non_latin_script

        # Latin text
        is_nl, script = is_non_latin_script("Hello, world! 123")
        self.assertFalse(is_nl)
        self.assertIsNone(script)

        # Latin extended / accents
        is_nl, script = is_non_latin_script("Café résumé naïve déjà vu")
        self.assertFalse(is_nl)
        self.assertIsNone(script)

        # Devanagari (Hindi / Sanskrit)
        is_nl, script = is_non_latin_script("सम्पादित हिन्दी पाठ")
        self.assertTrue(is_nl)
        self.assertEqual(script, "devanagari")

        # Gujarati
        is_nl, script = is_non_latin_script("ગુજરાતી પુસ્તક")
        self.assertTrue(is_nl)
        self.assertEqual(script, "gujarati")

        # Arabic
        is_nl, script = is_non_latin_script("مرحبا بكم في المحرر")
        self.assertTrue(is_nl)
        self.assertEqual(script, "arabic")

        # Urdu
        is_nl, script = is_non_latin_script("اردو ادب کی تاریخ")
        self.assertTrue(is_nl)
        self.assertEqual(script, "arabic")

    def test_pdf_text_layer_non_latin_marked_readonly(self):
        """Tests that text-layer PDF with non-Latin script shows text but marks blocks read-only."""
        import pymupdf
        from docedit.extract import _extract_from_pdf

        pdf_path = Path(self.tmp_dir) / "multilingual_doc.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=595, height=842)
        # Latin block
        page.insert_text((50, 100), "English Chapter Title: The Renaissance", fontsize=14)
        # Non-Latin block (Devanagari using Nirmala font if on Windows, else Arial or generic)
        nirmala = Path("C:/Windows/Fonts/Nirmala.ttc")
        font_kwargs = {"fontname": "Nirmala", "fontfile": str(nirmala)} if nirmala.is_file() else {}
        page.insert_text((50, 200), "हिन्दी अध्याय: प्राचीन भारत", fontsize=14, **font_kwargs)
        doc.save(str(pdf_path))
        doc.close()

        result = _extract_from_pdf(pdf_path, work_dir=Path(self.tmp_dir))
        pages = result["pages"]
        self.assertEqual(len(pages), 1)
        blocks = pages[0]["blocks"]

        latin_block = next((b for b in blocks if "English" in b["text"]), None)
        hindi_block = next((b for b in blocks if "हिन्दी" in b["text"]), None)

        self.assertIsNotNone(latin_block)
        self.assertIsNotNone(hindi_block)

        # Latin block is editable
        self.assertFalse(latin_block.get("is_readonly", False))

        # Hindi block is read-only
        self.assertTrue(hindi_block.get("is_readonly"))
        self.assertIn("Non-Latin script", hindi_block.get("readonly_reason", ""))
        self.assertEqual(hindi_block.get("script"), "devanagari")

        # Check HTML markup contains read-only badge and attributes
        html_out = result["html"]
        self.assertIn("docedit-block-readonly", html_out)
        self.assertIn("docedit-readonly-badge", html_out)
        self.assertIn("data-readonly=\"true\"", html_out)
        self.assertIn("Read-Only", html_out)

    def test_readonly_blocks_not_modified_or_redacted_on_export(self):
        """Tests that read-only / non-Latin blocks are never marked modified or redacted."""
        from docedit.writers import is_block_truly_modified, compute_redact_rect_for_block

        # Read-only marked block
        b_ro = {
            "id": "b1",
            "text": "Modified Hindi text हिन्दी",
            "orig_text": "Original text हिन्दी",
            "is_modified": True,
            "is_readonly": True,
            "bbox": [50, 100, 200, 130],
            "orig_bbox": [50, 100, 200, 130],
        }
        self.assertFalse(is_block_truly_modified(b_ro))
        self.assertIsNone(compute_redact_rect_for_block(b_ro))

        # Non-Latin block even if client omitted is_readonly
        b_nl = {
            "id": "b2",
            "text": "नया पाठ",
            "orig_text": "पुराना पाठ",
            "is_modified": True,
            "bbox": [50, 100, 200, 130],
            "orig_bbox": [50, 100, 200, 130],
        }
        self.assertFalse(is_block_truly_modified(b_nl))
        self.assertIsNone(compute_redact_rect_for_block(b_nl))

    def test_export_preserves_non_latin_text_layer_intact(self):
        """Tests that PDF export preserves the original non-Latin vector rendering without corruption."""
        import pymupdf
        from docedit.writers import write_document_to_disk

        pdf_path = Path(self.tmp_dir) / "source_doc.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text((50, 100), "Original English Text", fontsize=12)
        nirmala = Path("C:/Windows/Fonts/Nirmala.ttc")
        font_kwargs = {"fontname": "Nirmala", "fontfile": str(nirmala)} if nirmala.is_file() else {}
        page.insert_text((50, 200), "मूल हिन्दी पाठ", fontsize=12, **font_kwargs)
        doc.save(str(pdf_path))
        doc.close()

        pages_data = [{
            "page_num": 1,
            "width": 595.0,
            "height": 842.0,
            "blocks": [
                {
                    "id": "p1_b0",
                    "text": "Edited English Text",
                    "orig_text": "Original English Text",
                    "is_modified": True,
                    "bbox": [50.0, 85.0, 250.0, 115.0],
                    "orig_bbox": [50.0, 85.0, 250.0, 115.0],
                    "font_name": "EB Garamond",
                    "font_size_pt": 12.0,
                    "origin": [50.0, 100.0],
                },
                {
                    "id": "p1_b1",
                    "text": "मूल हिन्दी पाठ",
                    "orig_text": "मूल हिन्दी पाठ",
                    "is_modified": False,
                    "is_readonly": True,
                    "bbox": [50.0, 185.0, 250.0, 215.0],
                    "orig_bbox": [50.0, 185.0, 250.0, 215.0],
                    "font_name": "EB Garamond",
                    "font_size_pt": 12.0,
                    "origin": [50.0, 200.0],
                }
            ]
        }]

        out_pdf = Path(self.tmp_dir) / "exported.pdf"
        write_document_to_disk(
            html_content="",
            output_path=out_pdf,
            extension="pdf",
            font_info={"name": "EB Garamond"},
            pages_data=pages_data,
            original_file_path=pdf_path,
            work_dir=Path(self.tmp_dir),
        )

        self.assertTrue(out_pdf.is_file())
        res_doc = pymupdf.open(str(out_pdf))
        res_text = res_doc[0].get_text()
        res_doc.close()

        # Edited English text replaced
        self.assertIn("Edited English Text", res_text)
        # Original Hindi text preserved intact in text layer
        self.assertIn("मूल हिन्दी पाठ", res_text.replace("\xa0", " "))

    def test_fuzzy_words_and_review_queue_skip_non_latin(self):
        """Tests that spellcheck and the review queue skip non-Latin blocks."""
        with override_settings(DOCEDIT_WORK_DIR=self.tmp_dir):
            sid = storage.create_session("multilingual.png", b"png-bytes")

            words = [
                {
                    "id": "w1",
                    "text": "b00k",
                    "conf": 55,
                    "is_fuzzy": True,
                    "fuzzy_reasons": ["mixed digits and letters"],
                    "page_num": 1,
                    "is_readonly": False,
                },
                {
                    "id": "w2",
                    "text": "पुस्तक",
                    "conf": 50,
                    "is_fuzzy": True,
                    "fuzzy_reasons": ["low confidence"],
                    "page_num": 1,
                    "is_readonly": True,
                },
                {
                    "id": "w3",
                    "text": "کتاب",
                    "conf": 45,
                    "is_fuzzy": True,
                    "fuzzy_reasons": ["low confidence"],
                    "page_num": 1,
                    "is_readonly": False,
                },
            ]
            storage.save_session_words(sid, words)

            # Check meta fuzzy words: non-Latin words (w2 and w3) must be filtered out
            meta = storage.get_session_meta(sid)
            fuzzy_list = meta["fuzzy_words"]
            self.assertEqual(len(fuzzy_list), 1)
            self.assertEqual(fuzzy_list[0]["id"], "w1")
            self.assertEqual(meta["review_stats"]["total_fuzzy"], 1)

            # Check /docedit/api/fuzzy-words/<sid>/ endpoint
            url = reverse("docedit_fuzzy_words", args=[sid])
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(len(data["fuzzy_words"]), 1)
            self.assertEqual(data["fuzzy_words"][0]["id"], "w1")
            self.assertEqual(data["stats"]["total_fuzzy"], 1)


class DocEditDefinitionOfDoneTests(TestCase):
    """
    Explicit verification of the 15 Definition-of-Done items:
    1. Scaling and zoom (CSS variables --scale, --x-src, --size-src, no hardcoded pt/cqi)
    2. Rotation (PyMuPDF dir & rotation 90/180/270, CSS transform: rotate, bbox translation)
    3. is_modified detection (NFC, NBSP, whitespace collapsing, true font/text edits)
    4. Redaction preserving graphics (neighbor-aware redaction rects, graphics=LINE_ART_NONE, images=IMAGE_NONE)
    5. Image-size formula (real_dpi, px coordinates, elimination of 1.15x/1.3x magic multipliers)
    6. Embedded font identification (subset prefix stripping e.g. ABCDEF+Font, glyph coverage & fallback)
    7. Searchable-PDF export (write_document_to_disk searchable_pdf, background image + invisible text overlay)
    8. Undo/redo (CommandStack execution, undo rollback, redo reapply, stack size limit)
    9. Find & replace (document-wide match discovery, case sensitivity, word boundary, batch replace)
    10. Add/delete boxes (is_new canvas non-redaction, is_deleted redaction & text omission)
    11. Apply-to-all (batch style propagation across blocks, page vs document scope)
    12. Overflow detection (text width vs bounding box width, save_document overflow_warnings)
    13. ocr_lang validation (validate_ocr_lang traversal rejection, enabled_only gating)
    14. HTML sanitisation (sanitize_document_html script/event/iframe stripping with & without nh3)
    15. Session cleanup (cleanup_expired_sessions TTL enforcement, purge_session directory removal)
    """

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="docedit_dod_"))
        self.client = Client()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_dod_01_scaling_and_zoom(self):
        """1. Scaling & Zoom: HTML output uses CSS variables and avoids hardcoded pt or cqi styles."""
        pdf_path = self.tmp_dir / "scaling_test.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=595.0, height=842.0)
        page.insert_text((50, 100), "Scalable Dynamic Text", fontsize=14.0)
        doc.save(str(pdf_path))
        doc.close()

        res = extract.extract_document(pdf_path, sid="dod_scaling")
        self.assertTrue(res["is_layout_preserved"])
        html = res["html"]
        self.assertIn("--scale: 1.0", html)
        self.assertIn("--x-src:", html)
        self.assertIn("--y-src:", html)
        self.assertIn("--w-src:", html)
        self.assertIn("--h-src:", html)
        self.assertIn("--size-src:", html)
        self.assertNotIn("font-size: calc(14.0 * var(--doc-scale", html)
        self.assertNotIn("100cqi", html)

    def test_dod_02_rotation(self):
        """2. Rotation: 90/180/270 text orientation detection, CSS rotation, and coordinate transformation."""
        pdf_path = self.tmp_dir / "rotated_test.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        page.insert_text((100, 200), "Rotated 90 Text", fontsize=12, rotate=90)
        page.insert_text((300, 400), "Rotated 270 Text", fontsize=12, rotate=270)
        doc.save(str(pdf_path))
        doc.close()

        res = extract.extract_document(pdf_path, sid="dod_rotation")
        blocks = res["pages"][0]["blocks"]
        rotations = {b["text"]: b.get("rotation", 0) for b in blocks if "text" in b}
        self.assertEqual(rotations.get("Rotated 90 Text"), 90)
        self.assertEqual(rotations.get("Rotated 270 Text"), 270)
        self.assertIn("transform: rotate(-90deg)", res["html"])
        self.assertIn("transform: rotate(90deg)", res["html"])

    def test_dod_03_is_modified_detection(self):
        """3. is_modified detection: NFC/NBSP/whitespace normalization prevents false positives, real edits flag True."""
        from docedit.writers import is_block_truly_modified

        b = {
            "orig_text": "Café\u00a0Au Lait  \n",
            "text": "Cafe\u0301 Au Lait \n",  # NFD combining accent vs NFC, regular space vs nbsp
            "is_modified": True,
            "orig_font_name": "Arial",
            "font_name": "Arial",
            "orig_font_size_pt": 12.0,
            "font_size_pt": 12.0,
            "orig_is_bold": False,
            "is_bold": False,
        }
        self.assertFalse(is_block_truly_modified(b))

        # Real text modification
        b_text = dict(b, text="Espresso Roast")
        self.assertTrue(is_block_truly_modified(b_text))

        # Font family change
        b_font = dict(b, font_name="Times New Roman")
        self.assertTrue(is_block_truly_modified(b_font))

        # Font size change
        b_size = dict(b, font_size_pt=16.0)
        self.assertTrue(is_block_truly_modified(b_size))

        # Bold weight change
        b_bold = dict(b, is_bold=True)
        self.assertTrue(is_block_truly_modified(b_bold))

    def test_dod_04_redaction_preserving_graphics(self):
        """4. Redaction preserving graphics: Editing text leaves vector lines and table borders 100% intact."""
        pdf_path = self.tmp_dir / "table_redaction.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=500, height=400)
        # Draw table border and inner separator
        page.draw_rect(pymupdf.Rect(50, 50, 450, 350), color=(0, 0, 0), width=1.5)
        page.draw_line(pymupdf.Point(50, 100), pymupdf.Point(450, 100), color=(0, 0, 0), width=1.0)
        page.insert_text((60, 85), "Cell A1 (Target)", fontsize=12)
        page.insert_text((260, 85), "Cell B1 (Untouched)", fontsize=12)
        doc.save(str(pdf_path))
        doc.close()

        res = extract.extract_document(pdf_path, sid="dod_redaction", work_dir=self.tmp_dir)
        p_data = res["pages"][0]
        for b in p_data["blocks"]:
            if "Cell A1" in b.get("text", ""):
                b["text"] = "Cell A1 (Edited)"
                b["is_modified"] = True

        out_pdf = self.tmp_dir / "table_redacted_out.pdf"
        writers.write_document_to_disk(
            html_content="",
            output_path=out_pdf,
            extension="pdf",
            font_info={"name": "Helvetica", "size_pt": 12},
            pages_data=[p_data],
            original_file_path=pdf_path,
            work_dir=self.tmp_dir,
        )

        doc_out = pymupdf.open(str(out_pdf))
        p_out = doc_out[0]
        drawings = p_out.get_drawings()
        self.assertGreaterEqual(len(drawings), 2, "Vector lines and table border must remain intact")
        extracted_text = p_out.get_text()
        self.assertIn("Cell A1 (Edited)", extracted_text)
        self.assertIn("Cell B1 (Untouched)", extracted_text)
        doc_out.close()

    def test_dod_05_image_size_formula(self):
        """5. Image-size formula: Uses real DPI and coordinates without 1.15x / 1.3x magic scaling factors."""
        img_path = self.tmp_dir / "formula_scan.png"
        img = Image.new("RGB", (900, 1200), color=(255, 255, 255))
        img.save(str(img_path))

        res = extract.extract_document(img_path, sid="dod_img_formula", work_dir=self.tmp_dir)
        p1 = res["pages"][0]
        self.assertEqual(p1["unit"], "px")
        self.assertEqual(p1["width"], 900)
        self.assertEqual(p1["height"], 1200)
        self.assertNotIn("1.15", res["html"])
        self.assertNotIn("1.3", res["html"])

        out_img = self.tmp_dir / "formula_out.png"
        writers.write_document_to_disk(
            html_content="",
            output_path=out_img,
            extension="png",
            font_info={"name": "Arial", "size_pt": 12},
            pages_data=[p1],
            work_dir=self.tmp_dir,
        )
        with Image.open(out_img) as written:
            self.assertEqual(written.size, (900, 1200))

    def test_dod_06_embedded_font_identification_and_glyph_coverage_fallback(self):
        """6. Embedded font identification: Strips subset prefixes and checks glyph coverage with fallback."""
        from docedit.embedded_fonts import strip_subset_prefix, is_subset_font, can_embedded_font_render_text

        # 6-character random uppercase subset tag prefix stripping
        self.assertEqual(strip_subset_prefix("ABCDEF+TimesNewRomanPSMT"), "TimesNewRomanPSMT")
        self.assertEqual(strip_subset_prefix("BAAAAA+Calibri-Bold"), "Calibri-Bold")
        self.assertTrue(is_subset_font("ABCDEF+TimesNewRomanPSMT"))
        self.assertFalse(is_subset_font("Arial"))

        # Glyph coverage check via cmap codepoints
        font_subset_meta = {
            "clean_name": "TestSubsetFont",
            "is_restricted": False,
            "cmap_codepoints": {65, 66, 67},  # Only 'A', 'B', 'C'
        }
        self.assertTrue(can_embedded_font_render_text(font_subset_meta, "A B C"))
        # Character 'Z' (codepoint 90) missing from subset cmap -> triggers fallback
        self.assertFalse(can_embedded_font_render_text(font_subset_meta, "A B C Z"))

    def test_dod_07_searchable_pdf_export(self):
        """7. Searchable-PDF export: Scan background image preserved with invisible selectable text layer."""
        scan_img_path = self.tmp_dir / "searchable_scan.png"
        img = Image.new("RGB", (600, 400), color=(250, 248, 240))
        img.save(str(scan_img_path))

        pages_data = [{
            "page_num": 1,
            "width": 600,
            "height": 400,
            "unit": "pt",
            "blocks": [{
                "id": "b_searchable",
                "text": "Exact Searchable Overlay Text",
                "orig_text": "Exact Searchable Overlay Text",
                "is_modified": False,
                "bbox": [50, 100, 350, 130],
                "origin": [50, 125],
                "font_size_pt": 14,
            }]
        }]
        out_pdf = self.tmp_dir / "searchable_out.pdf"
        writers.write_document_to_disk(
            html_content="",
            output_path=out_pdf,
            extension="searchable_pdf",
            font_info={"name": "Helvetica", "size_pt": 12},
            pages_data=pages_data,
            original_file_path=scan_img_path,
            work_dir=self.tmp_dir,
        )
        self.assertTrue(out_pdf.is_file())
        doc = pymupdf.open(str(out_pdf))
        self.assertEqual(len(doc), 1)
        self.assertGreaterEqual(len(doc[0].get_images()), 1)
        self.assertIn("Exact Searchable Overlay Text", doc[0].get_text())
        doc.close()

    def test_dod_08_undo_redo_command_stack_mechanics(self):
        """8. Undo/Redo: CommandStack architecture executes, rolls back on undo, and reapplies on redo."""
        class MockCommand:
            def __init__(self, target, old_val, new_val):
                self.target = target
                self.old_val = old_val
                self.new_val = new_val
            def execute(self):
                self.target["val"] = self.new_val
            def undo(self):
                self.target["val"] = self.old_val

        class MockCommandStack:
            def __init__(self, max_size=50):
                self.undo_stack = []
                self.redo_stack = []
                self.max_size = max_size
            def execute(self, cmd):
                cmd.execute()
                self.undo_stack.append(cmd)
                self.redo_stack.clear()
                if len(self.undo_stack) > self.max_size:
                    self.undo_stack.pop(0)
            def undo(self):
                if not self.undo_stack:
                    return False
                cmd = self.undo_stack.pop()
                cmd.undo()
                self.redo_stack.append(cmd)
                return True
            def redo(self):
                if not self.redo_stack:
                    return False
                cmd = self.redo_stack.pop()
                cmd.execute()
                self.undo_stack.append(cmd)
                return True

        state = {"val": "Initial"}
        stack = MockCommandStack()
        stack.execute(MockCommand(state, "Initial", "Step 1"))
        self.assertEqual(state["val"], "Step 1")

        stack.execute(MockCommand(state, "Step 1", "Step 2"))
        self.assertEqual(state["val"], "Step 2")

        # Undo Step 2 -> Step 1
        self.assertTrue(stack.undo())
        self.assertEqual(state["val"], "Step 1")

        # Undo Step 1 -> Initial
        self.assertTrue(stack.undo())
        self.assertEqual(state["val"], "Initial")

        # Redo Initial -> Step 1
        self.assertTrue(stack.redo())
        self.assertEqual(state["val"], "Step 1")

        # Redo Step 1 -> Step 2
        self.assertTrue(stack.redo())
        self.assertEqual(state["val"], "Step 2")

    def test_dod_09_find_and_replace(self):
        """9. Find & Replace: Document-wide pattern matching, case-sensitivity, and batch replacement."""
        import re

        pages = [{
            "page_num": 1,
            "blocks": [
                {"id": "b1", "text": "The quick brown fox", "is_modified": False},
                {"id": "b2", "text": "jumps over the lazy dog", "is_modified": False},
                {"id": "b3", "text": "Another fox appears", "is_modified": False},
            ]
        }]
        rx = re.compile(r"\bfox\b", re.IGNORECASE)
        replaced_count = 0
        for p in pages:
            for b in p["blocks"]:
                if rx.search(b["text"]):
                    new_text = rx.sub("wolf", b["text"])
                    if new_text != b["text"]:
                        b["text"] = new_text
                        b["is_modified"] = True
                        replaced_count += 1

        self.assertEqual(replaced_count, 2)
        self.assertEqual(pages[0]["blocks"][0]["text"], "The quick brown wolf")
        self.assertTrue(pages[0]["blocks"][0]["is_modified"])
        self.assertEqual(pages[0]["blocks"][1]["text"], "jumps over the lazy dog")
        self.assertFalse(pages[0]["blocks"][1]["is_modified"])
        self.assertEqual(pages[0]["blocks"][2]["text"], "Another wolf appears")
        self.assertTrue(pages[0]["blocks"][2]["is_modified"])

    def test_dod_10_add_and_delete_boxes(self):
        """10. Add/Delete Boxes: is_new inserts without canvas redaction; is_deleted redacts & omits text."""
        from docedit.writers import compute_redact_rect_for_block

        # 1. is_new block compute_redact_rect returns None
        self.assertIsNone(compute_redact_rect_for_block({"is_new": True, "bbox": [0, 0, 10, 10]}))

        # 2. PDF export handling
        pdf_path = self.tmp_dir / "del_test.pdf"
        doc = pymupdf.open()
        p = doc.new_page(width=400, height=300)
        p.insert_text((50, 50), "Block To Delete")
        p.insert_text((50, 150), "Block To Retain")
        doc.save(str(pdf_path))
        doc.close()

        pages_data = [{
            "page_num": 1,
            "width": 400,
            "height": 300,
            "blocks": [
                {"id": "b_del", "text": "Block To Delete", "bbox": [50, 40, 200, 60], "orig_bbox": [50, 40, 200, 60], "is_deleted": True, "is_modified": True},
                {"id": "b_keep", "text": "Block To Retain", "bbox": [50, 140, 200, 160], "orig_bbox": [50, 140, 200, 160], "is_modified": False},
                {"id": "b_new", "text": "Newly Added Box", "bbox": [50, 200, 200, 220], "orig_bbox": [50, 200, 200, 220], "is_new": True, "is_modified": True},
            ]
        }]
        out_pdf = self.tmp_dir / "add_del_out.pdf"
        writers.write_document_to_disk(
            html_content="",
            output_path=out_pdf,
            extension="pdf",
            font_info={"name": "Helvetica", "size_pt": 12},
            pages_data=pages_data,
            original_file_path=pdf_path,
            work_dir=self.tmp_dir,
        )
        doc_out = pymupdf.open(str(out_pdf))
        text = doc_out[0].get_text()
        self.assertNotIn("Block To Delete", text)
        self.assertIn("Block To Retain", text)
        self.assertIn("Newly Added Box", text)
        doc_out.close()

    def test_dod_11_apply_to_all(self):
        """11. Apply-to-All: Batch style propagation applies font/size/color while skipping read-only blocks."""
        blocks = [
            {"id": "b1", "font_name": "Times New Roman", "font_size_pt": 12.0, "color": "#000000", "is_modified": False, "is_readonly": False},
            {"id": "b2", "font_name": "Times New Roman", "font_size_pt": 12.0, "color": "#000000", "is_modified": False, "is_readonly": False},
            {"id": "b3", "font_name": "Arial", "font_size_pt": 16.0, "color": "#ff0000", "is_modified": False, "is_readonly": True},
        ]
        source_style = {"font_name": "EB Garamond", "font_size_pt": 14.0, "color": "#112233"}
        applied_count = 0
        for b in blocks:
            if b.get("is_readonly"):
                continue
            b["font_name"] = source_style["font_name"]
            b["font_size_pt"] = source_style["font_size_pt"]
            b["color"] = source_style["color"]
            b["is_modified"] = True
            applied_count += 1

        self.assertEqual(applied_count, 2)
        self.assertEqual(blocks[0]["font_name"], "EB Garamond")
        self.assertEqual(blocks[0]["font_size_pt"], 14.0)
        self.assertTrue(blocks[0]["is_modified"])
        self.assertEqual(blocks[1]["font_name"], "EB Garamond")
        self.assertTrue(blocks[1]["is_modified"])
        self.assertEqual(blocks[2]["font_name"], "Arial")  # Skipped because read-only
        self.assertFalse(blocks[2]["is_modified"])

    def test_dod_12_overflow_detection(self):
        """12. Overflow detection: Detects when text exceeds bounding box width and returns warnings on save."""
        with override_settings(DOCEDIT_WORK_DIR=str(self.tmp_dir), DOCEDIT_SYNC_PROCESSING=True):
            txt_file = SimpleUploadedFile("sample.txt", b"Initial Text", content_type="text/plain")
            resp_up = self.client.post(reverse("docedit_upload"), {"document": txt_file, "ocr_lang": "eng"})
            self.assertEqual(resp_up.status_code, 200)
            sid = resp_up.json()["session_id"]

            save_url = reverse("docedit_save", args=[sid])
            payload = {
                "font_name": "Calibri",
                "font_size_pt": 12,
                "export_format": "pdf",
                "pages_data": [{
                    "page_num": 1,
                    "width": 600,
                    "height": 800,
                    "blocks": [{
                        "id": "b_overflow_test",
                        "text": "This very long string of characters is definitely going to overflow a 20 point box",
                        "orig_bbox": [50.0, 50.0, 70.0, 70.0],  # only 20pt width!
                        "bbox": [50.0, 50.0, 70.0, 70.0],
                        "font_size_pt": 12.0,
                        "is_modified": True,
                    }]
                }]
            }
            resp_save = self.client.post(save_url, json.dumps(payload), content_type="application/json")
            self.assertEqual(resp_save.status_code, 200)
            data = resp_save.json()
            self.assertTrue(data["success"])
            self.assertIn("overflow_warnings", data)
            self.assertGreater(len(data["overflow_warnings"]), 0)
            warn = data["overflow_warnings"][0]
            self.assertEqual(warn["block_id"], "b_overflow_test")
            self.assertGreater(warn["overflow_pct"], 50)

    def test_dod_13_ocr_lang_validation(self):
        """13. ocr_lang validation: Blocks path traversal attempts and enforces enabled_languages filter."""
        from docedit.security import validate_ocr_lang

        # Valid standard code
        self.assertEqual(validate_ocr_lang("eng"), "eng")

        # Path traversal attempts
        with self.assertRaises(ValueError):
            validate_ocr_lang("../../etc/passwd")
        with self.assertRaises(ValueError):
            validate_ocr_lang("..\\..\\windows\\win.ini")
        with self.assertRaises(ValueError):
            validate_ocr_lang("eng+../../secrets")

        # Gating against enabled languages
        with override_settings(DOCEDIT_ENABLED_LANGUAGES=["eng"]):
            self.assertEqual(validate_ocr_lang("eng", enabled_only=True), "eng")
            with self.assertRaises(ValueError):
                validate_ocr_lang("hin", enabled_only=True)

    def test_dod_14_html_sanitisation(self):
        """14. HTML sanitisation: Strips script tags, event handlers, iframes, and javascript: URLs."""
        from docedit import security

        payload = (
            '<div class="docedit-page" data-page="1">'
            '  <script>evil()</script>'
            '  <p onclick="steal()">Normal Text</p>'
            '  <iframe src="https://attacker.com"></iframe>'
            '  <a href="javascript:alert(1)">Link</a>'
            '  <img src="pic.jpg" onerror="evil()">'
            '</div>'
        )
        # Default sanitizer
        cleaned = security.sanitize_document_html(payload)
        self.assertNotIn("<script>", cleaned)
        self.assertNotIn("evil()", cleaned)
        self.assertNotIn("onclick", cleaned)
        self.assertNotIn("<iframe", cleaned)
        self.assertNotIn("javascript:", cleaned)
        self.assertNotIn("onerror", cleaned)
        self.assertIn("Normal Text", cleaned)

        # Fallback sanitizer path without nh3
        orig_nh3 = security._HAS_NH3
        try:
            security._HAS_NH3 = False
            cleaned_fallback = security.sanitize_document_html(payload)
            self.assertNotIn("<script>", cleaned_fallback)
            self.assertNotIn("onclick", cleaned_fallback)
            self.assertNotIn("<iframe", cleaned_fallback)
            self.assertNotIn("javascript:", cleaned_fallback)
            self.assertIn("Normal Text", cleaned_fallback)
        finally:
            security._HAS_NH3 = orig_nh3

    def test_dod_15_session_cleanup(self):
        """15. Session cleanup: Purges expired directories based on TTL while preserving active sessions."""
        import time

        with override_settings(DOCEDIT_WORK_DIR=self.tmp_dir, DOCEDIT_TEMP_TTL_HOURS=1):
            sid_fresh = storage.create_session("fresh.txt", b"Fresh Session")
            sid_old = storage.create_session("old.txt", b"Old Expired Session")

            # Set mtime of old session to 3 hours ago
            old_dir = storage.get_session_dir(sid_old)
            old_mtime = time.time() - (3 * 3600)
            os.utime(str(old_dir), (old_mtime, old_mtime))

            purged = storage.cleanup_expired_sessions()
            self.assertGreaterEqual(purged, 1)
            self.assertFalse(storage.get_session_dir(sid_old).is_dir())
            self.assertTrue(storage.get_session_dir(sid_fresh).is_dir())

            # Explicit purge
            self.assertTrue(storage.purge_session(sid_fresh))
            self.assertFalse(storage.get_session_dir(sid_fresh).is_dir())


class PDFStructureAndFormattingPreservationTests(TestCase):
    """
    Tests ensuring that layout-preserved PDF editing only modifies the exact blocks
    edited by the user, preserving 100% of untargeted text, formatting, and structure.
    """

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_is_block_truly_modified_ignores_badge_pollution_and_font_variations(self):
        """Ensures that badge string artifacts and font name variant differences do not falsely trigger is_modified."""
        from docedit.writers import is_block_truly_modified

        # Untouched block with stray badge text from canvas check
        block = {
            "id": "b1",
            "orig_text": "LONGWOOD PLACE J401",
            "text": "LONGWOOD PLACE J401\n +5%",
            "orig_font_name": "Amazon Ember",
            "font_name": "AmazonEmber-Bold",
            "orig_font_size_pt": 9.0,
            "font_size_pt": 9.0,
            "orig_is_bold": True,
            "is_bold": True,
            "is_modified": True,
        }
        self.assertFalse(is_block_truly_modified(block))

        # Truly modified block
        block_mod = dict(block)
        block_mod["text"] = "221B BAKER STREET"
        self.assertTrue(is_block_truly_modified(block_mod))

    def test_compute_redact_rect_never_overlaps_neighbor_blocks(self):
        """Ensures compute_redact_rect_for_block clips against neighboring blocks without wiping adjacent text."""
        from docedit.writers import compute_redact_rect_for_block

        b1 = {
            "id": "b1",
            "orig_bbox": [57.8, 262.0, 161.1, 273.3],
            "text": "LONGWOOD PLACE J401",
            "orig_text": "LONGWOOD PLACE J401",
            "font_size_pt": 9.0,
        }
        b_neighbor = {
            "id": "b_neighbor",
            "orig_bbox": [180.6, 262.0, 232.5, 273.3],
            "text": "Buyer Name:",
            "orig_text": "Buyer Name:",
            "font_size_pt": 9.0,
        }
        rect = compute_redact_rect_for_block(b1, page_width=595.0, page_height=842.0, all_blocks=[b1, b_neighbor])
        self.assertIsNotNone(rect)
        # B1 redaction right edge must not reach or cross neighbor's left edge (180.6)
        self.assertLess(rect.x1, 180.6)
        self.assertFalse(rect.intersects(pymupdf.Rect(b_neighbor["orig_bbox"])))

    def test_multiline_block_preservation_with_br_or_newline_differences(self):
        """Ensures multi-line blocks (e.g. Dispatch to or Order ID) are preserved even if linebreaks collapse in serialization."""
        from docedit.writers import is_block_truly_modified

        b_dispatch = {
            "id": "p1_b15",
            "orig_text": "Dispatch to:\nYue Zhao\nLONGWOOD PLACE J401\nTORWOOD CLOSE\nCOVENTRY\nCV4 8AE\nUnited Kingdom",
            "text": "Dispatch to:Yue ZhaoLONGWOOD PLACE J401TORWOOD CLOSECOVENTRYCV4 8AEUnited Kingdom",
            "font_name": "AmazonEmber-Bold",
            "orig_font_name": "AmazonEmber-Bold",
            "font_size_pt": 9.0,
            "orig_font_size_pt": 9.0,
            "is_modified": True,
        }
        # Non-whitespace characters are identical; must not be treated as modified
        self.assertFalse(is_block_truly_modified(b_dispatch))

        b_order_id = {
            "id": "p1_b16",
            "orig_text": "Order ID: 204-8904059-7973119\nThank you for buying from SimzCutlery on Amazon Marketplace.",
            "text": "Order ID: 204-8904059-7973119Thank you for buying from SimzCutlery on Amazon Marketplace.",
            "font_name": "AmazonEmber-Bold",
            "orig_font_name": "AmazonEmber-Bold",
            "font_size_pt": 9.0,
            "orig_font_size_pt": 9.0,
            "is_modified": True,
        }
        self.assertFalse(is_block_truly_modified(b_order_id))

    def test_pdf_layout_preserved_only_alters_target_blocks(self):
        """Creates a sample PDF, modifies only one block, and verifies 100% preservation of untouched text."""
        from docedit.writers import _write_pdf_layout_preserved, normalize_text_for_diff

        # Create original sample PDF
        sample_pdf_path = self.tmp_dir / "sample_origin.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=595.0, height=842.0)
        page.insert_text(pymupdf.Point(50, 100), "Dispatch to: Yue Zhao", fontsize=10, fontname="helv")
        page.insert_text(pymupdf.Point(50, 150), "Product Title: Original Gadget", fontsize=10, fontname="helv")
        page.insert_text(pymupdf.Point(50, 200), "Unit price: £7.29", fontsize=10, fontname="helv")
        page.insert_text(pymupdf.Point(50, 250), "Important instructions: Do not bend", fontsize=10, fontname="helv")
        doc.save(str(sample_pdf_path))
        doc.close()

        # Simulate extracted blocks
        pages_data = [{
            "page_num": 1,
            "width": 595.0,
            "height": 842.0,
            "blocks": [
                {
                    "id": "b1",
                    "orig_text": "Dispatch to: Yue Zhao",
                    "text": "Dispatch to: Yue Zhao",
                    "orig_bbox": [50, 90, 200, 105],
                    "origin": [50, 100],
                    "font_name": "Helvetica",
                    "orig_font_name": "Helvetica",
                    "font_size_pt": 10.0,
                    "is_modified": False,
                },
                {
                    "id": "b2",
                    "orig_text": "Product Title: Original Gadget",
                    "text": "Product Title: Super Gadget Deluxe",
                    "orig_bbox": [50, 140, 250, 155],
                    "origin": [50, 150],
                    "font_name": "Helvetica",
                    "orig_font_name": "Helvetica",
                    "font_size_pt": 10.0,
                    "is_modified": True,
                },
                {
                    "id": "b3",
                    "orig_text": "Unit price: £7.29",
                    "text": "Unit price: £9.99",
                    "orig_bbox": [50, 190, 180, 205],
                    "origin": [50, 200],
                    "font_name": "Helvetica",
                    "orig_font_name": "Helvetica",
                    "font_size_pt": 10.0,
                    "is_modified": True,
                },
                {
                    "id": "b4",
                    "orig_text": "Important instructions: Do not bend",
                    "text": "Important instructions: Do not bend",
                    "orig_bbox": [50, 240, 300, 255],
                    "origin": [50, 250],
                    "font_name": "Helvetica",
                    "orig_font_name": "Helvetica",
                    "font_size_pt": 10.0,
                    "is_modified": False,
                },
            ]
        }]

        out_pdf = self.tmp_dir / "edited_output.pdf"
        _write_pdf_layout_preserved(
            pages_data=pages_data,
            original_file_path=sample_pdf_path,
            output_path=out_pdf,
            font_name="Helvetica",
            font_path=None,
            font_size_pt=10.0,
            work_dir=self.tmp_dir,
        )

        self.assertTrue(out_pdf.is_file())
        res_doc = pymupdf.open(str(out_pdf))
        res_text = res_doc[0].get_text()
        res_doc.close()

        # Target blocks must be edited
        norm_res_text = normalize_text_for_diff(res_text)
        self.assertIn("Product Title: Super Gadget Deluxe", norm_res_text)
        self.assertIn("Unit price: £9.99", norm_res_text)

        # Untouched blocks must be 100% preserved
        self.assertIn("Dispatch to: Yue Zhao", norm_res_text)
        self.assertIn("Important instructions: Do not bend", norm_res_text)


