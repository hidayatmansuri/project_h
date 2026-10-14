"""
Document processing coordinator.

Coordinates the end-to-end upload pipeline:
1. Document extraction (and OCR if needed).
2. Script detection & font matching.
3. System check / Google Fonts download / system installation.
4. Setting up session metadata for the side panel and editor.
"""
import logging
import threading
from typing import Optional

from .conf import conf
from .extract import extract_document
from .font_catalog import resolve_document_font
from .fontmatch import get_editor_font_css
from .storage import (
    get_original_file_path,
    get_session_dir,
    get_session_meta,
    save_document_content,
    update_session,
)

logger = logging.getLogger(__name__)


def process_session(sid: str, ocr_lang: str = "eng") -> None:
    """
    Executes the document processing pipeline.
    Can be run in a background thread or synchronously.
    """
    orig_path = get_original_file_path(sid)
    if not orig_path or not orig_path.is_file():
        update_session(
            sid,
            status="error",
            error="Original document file not found in temporary storage.",
            progress=0,
            progress_message="Error: file missing",
        )
        return

    def on_progress(percent: int, msg: str):
        update_session(sid, progress=percent, progress_message=msg, status="processing")

    try:
        on_progress(15, "Starting document analysis...")

        work_dir = get_session_dir(sid)
        extracted = extract_document(
            orig_path,
            ocr_lang=ocr_lang,
            work_dir=work_dir,
            sid=sid,
            progress_callback=on_progress
        )

        on_progress(80, "Matching document typography and checking fonts...")

        detected_font = extracted.get("detected_font_name")
        font_res = resolve_document_font(detected_font)

        # Merge extracted font size
        font_res["size_pt"] = extracted.get("font_size_pt", 12.0)
        editor_css = get_editor_font_css(font_res)

        # Save HTML and plain text
        html_content = extracted.get("html", "")
        raw_text = extracted.get("raw_text", "")
        save_document_content(sid, html_content, raw_text)

        stats = extracted.get("stats", {})

        on_progress(100, "Document ready to edit with matching font!")
        update_session(
            sid,
            status="ready",
            is_editable=True,
            is_layout_preserved=extracted.get("is_layout_preserved", False),
            pages=extracted.get("pages", []),
            needs_ocr=extracted.get("needs_ocr", False),
            font_info=font_res,
            stats=stats,
            fuzzy_words=extracted.get("fuzzy_words", []),
            editor_font_css=editor_css,
            error=None,
        )
    except Exception as e:
        logger.exception("Failed processing document session %s: %s", sid, e)
        update_session(
            sid,
            status="error",
            error=f"Could not convert document: {str(e)}",
            progress=0,
            progress_message="Processing failed",
            is_editable=False,
        )


def start_session_processing(sid: str, ocr_lang: str = "eng") -> None:
    """
    Starts session processing in a thread (or synchronously if configured).
    """
    if conf.SYNC_PROCESSING:
        process_session(sid, ocr_lang=ocr_lang)
    else:
        t = threading.Thread(
            target=process_session,
            args=(sid,),
            kwargs={"ocr_lang": ocr_lang},
            daemon=True
        )
        t.start()
