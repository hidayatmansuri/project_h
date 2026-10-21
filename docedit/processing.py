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
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from .conf import conf
from .extract import extract_document
from .font_catalog import resolve_document_font
from .fontmatch import get_editor_font_css
from .security import validate_ocr_lang
from .storage import (
    get_original_file_path,
    get_session_dir,
    get_session_meta,
    save_document_content,
    update_session,
)

logger = logging.getLogger(__name__)

_EXECUTOR: Optional[ThreadPoolExecutor] = None
_EXECUTOR_LOCK = threading.Lock()


def get_processing_executor() -> ThreadPoolExecutor:
    """Returns the singleton bounded thread pool executor for document processing tasks."""
    global _EXECUTOR
    if _EXECUTOR is None:
        with _EXECUTOR_LOCK:
            if _EXECUTOR is None:
                max_w = getattr(conf, "MAX_WORKERS", 4)
                _EXECUTOR = ThreadPoolExecutor(
                    max_workers=max_w,
                    thread_name_prefix="docedit-proc"
                )
    return _EXECUTOR



def process_session(
    sid: str,
    ocr_lang: str = "eng",
    ocr_profile: Optional[str] = None,
    ocr_deskew: Optional[bool] = None,
    ocr_dewarp: Optional[bool] = None,
) -> None:
    """
    Executes the document processing pipeline.
    Can be run in a bounded worker pool or synchronously.
    """
    try:
        ocr_lang = validate_ocr_lang(ocr_lang)
    except ValueError as e:
        update_session(
            sid,
            status="error",
            error=f"Invalid OCR language: {e}",
            progress=0,
            progress_message="Error: invalid language",
            is_editable=False,
        )
        return

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
            progress_callback=on_progress,
            ocr_profile=ocr_profile,
            ocr_deskew=ocr_deskew,
            ocr_dewarp=ocr_dewarp,
        )

        on_progress(80, "Matching document typography and checking fonts...")

        detected_font = extracted.get("detected_font_name")
        font_res = resolve_document_font(detected_font)

        # Merge extracted font size
        font_res["size_pt"] = extracted.get("font_size_pt", 12.0)
        editor_css = get_editor_font_css(font_res)
        all_fonts_css = extracted.get("all_fonts_css", "")
        if all_fonts_css:
            editor_css = f"{all_fonts_css}\n{editor_css}"

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
            all_fonts_css=all_fonts_css,
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


def start_session_processing(
    sid: str,
    ocr_lang: str = "eng",
    ocr_profile: Optional[str] = None,
    ocr_deskew: Optional[bool] = None,
    ocr_dewarp: Optional[bool] = None,
) -> None:
    """
    Starts session processing in a bounded thread pool (or synchronously if configured).
    """
    if conf.SYNC_PROCESSING:
        process_session(
            sid,
            ocr_lang=ocr_lang,
            ocr_profile=ocr_profile,
            ocr_deskew=ocr_deskew,
            ocr_dewarp=ocr_dewarp,
        )
    else:
        executor = get_processing_executor()
        executor.submit(
            process_session,
            sid,
            ocr_lang=ocr_lang,
            ocr_profile=ocr_profile,
            ocr_deskew=ocr_deskew,
            ocr_dewarp=ocr_dewarp,
        )

