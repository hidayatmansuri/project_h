"""
DocEdit views and REST API endpoints.
"""
import io
import json
import logging
import time
from pathlib import Path

from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseForbidden,
    JsonResponse,
)
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .conf import EXTENSION_KINDS, MIME_TYPES, conf
from .font_catalog import (
    download_google_font,
    get_categorized_font_list,
    get_font_index,
    install_uploaded_font,
    is_font_available_for_free,
    resolve_document_font,
)
from .fontmatch import get_editor_font_css, is_non_latin_script
from .processing import start_session_processing
from .security import (
    check_upload_throttle,
    sanitize_document_html,
    sanitize_font_name,
    validate_ocr_lang,
)
from .storage import (
    apply_atomic_block_updates,
    cleanup_expired_sessions,
    confirm_session_download,
    create_download_token,
    create_session,
    get_document_content,
    get_edited_file_path,
    get_original_file_path,
    get_session_dir,
    get_session_meta,
    get_session_words,
    purge_session,
    save_document_content,
    update_session,
    update_session_word,
    validate_download_token,
)
from .writers import write_document_to_disk

logger = logging.getLogger(__name__)

_LAST_CLEANUP_TIME = 0.0


def _is_session_authorized(request: HttpRequest, meta: dict) -> bool:
    """Verifies that the request comes from the owner of the session."""
    owner_key = meta.get("owner_key")
    if not owner_key:
        return True  # Legacy session or unauthenticated local setup
    curr_key = request.session.session_key
    return bool(curr_key and curr_key == owner_key)


def _maybe_cleanup_expired():
    global _LAST_CLEANUP_TIME
    now = time.time()
    if now - _LAST_CLEANUP_TIME > 3600:  # Run at most once an hour on page views
        _LAST_CLEANUP_TIME = now
        try:
            cleanup_expired_sessions()
        except Exception:
            pass


@ensure_csrf_cookie
def docedit_home(request: HttpRequest) -> HttpResponse:
    """Renders the main DocEdit application interface."""
    # Periodic background cleanup of expired sessions (throttled)
    _maybe_cleanup_expired()

    allowed_exts = sorted(EXTENSION_KINDS.keys())
    allowed_exts_str = ", ".join(f".{e}" for e in allowed_exts)

    # OCR languages
    languages = [
        {"code": code, "name": name}
        for code, name in conf.OCR_LANGUAGES.items()
    ]

    fonts_data = get_categorized_font_list()

    context = {
        "title": "Free Online PDF Editor - Easily Edit PDFs | project-h",
        "fonts": fonts_data,
        "max_upload_mb": conf.MAX_UPLOAD_MB,
        "allowed_extensions": ".pdf",
        "accept_mime": ".pdf,application/pdf",
    }
    return render(request, "docedit/docedit.html", context)


@require_POST
def upload_document(request: HttpRequest) -> JsonResponse:
    """
    Handles PDF document upload. Creates session and initiates extraction.
    """
    # Enforce upload throttling per Django session
    if not check_upload_throttle(request, max_requests=conf.UPLOAD_THROTTLE_LIMIT, window_seconds=conf.UPLOAD_THROTTLE_WINDOW):
        return JsonResponse({
            "success": False,
            "error": "Upload rate limit exceeded. Please wait a moment before uploading again."
        }, status=429)

    upload = request.FILES.get("document")
    if not upload:
        return JsonResponse({"success": False, "error": "No document file was provided."}, status=400)

    # Size check
    max_bytes = conf.MAX_UPLOAD_MB * 1024 * 1024
    if upload.size > max_bytes:
        return JsonResponse({
            "success": False,
            "error": f"File is too large ({upload.size / (1024*1024):.1f} MB). Maximum allowed size is {conf.MAX_UPLOAD_MB} MB."
        }, status=400)

    ext = Path(upload.name).suffix.lstrip(".").lower()
    if ext != "pdf":
        return JsonResponse({
            "success": False,
            "error": f"Unsupported file type (.{ext}). Only PDF files (.pdf) are supported."
        }, status=400)

    ocr_lang = "eng"
    ocr_profile = None
    ocr_deskew = False
    ocr_dewarp = False

    file_bytes = upload.read()

    # Session ownership: bind session to Django session_key
    if not request.session.session_key:
        request.session.save()
    owner_key = request.session.session_key

    sid = create_session(upload.name, file_bytes, owner_key=owner_key)

    # Kick off processing
    start_session_processing(
        sid,
        ocr_lang=ocr_lang,
        ocr_profile=ocr_profile,
        ocr_deskew=ocr_deskew,
        ocr_dewarp=ocr_dewarp,
    )

    return JsonResponse({
        "success": True,
        "session_id": sid,
        "message": "PDF uploaded successfully. Processing started.",
    })


@require_GET
def session_status(request: HttpRequest, sid: str) -> JsonResponse:
    """Returns current processing/editing status and metadata for the side panel."""
    meta = get_session_meta(sid)
    if not meta:
        return JsonResponse({"success": False, "error": "Session not found or expired."}, status=404)

    if not _is_session_authorized(request, meta):
        return JsonResponse({"success": False, "error": "Access denied."}, status=403)

    response_data = {
        "success": True,
        "session_id": sid,
        "status": meta.get("status"),
        "progress": meta.get("progress", 0),
        "progress_message": meta.get("progress_message", ""),
        "original_filename": meta.get("original_filename"),
        "extension": meta.get("extension"),
        "file_size": meta.get("file_size", 0),
        "is_editable": meta.get("is_editable", False),
        "is_layout_preserved": meta.get("is_layout_preserved", False),
        "pages": meta.get("pages", []),
        "needs_ocr": meta.get("needs_ocr", False),
        "stats": meta.get("stats", {}),
        "font_info": meta.get("font_info", {}),
        "fuzzy_words": meta.get("fuzzy_words", []),
        "editor_font_css": meta.get("all_fonts_css") or meta.get("editor_font_css", ""),
        "all_fonts_css": meta.get("all_fonts_css", ""),
        "version": meta.get("version", 1),
        "edited_file": meta.get("edited_file"),
        "error": meta.get("error"),
    }

    # Only attach document HTML if editable and ready/saved, or if ?full=1 is explicitly requested
    if meta.get("is_editable") and (meta.get("status") in ("ready", "saved") or request.GET.get("full") == "1"):
        response_data["document_html"] = get_document_content(sid)

    return JsonResponse(response_data)


@require_GET
def session_page_image(request: HttpRequest, sid: str, page_num: int) -> HttpResponse:
    """
    Returns the high-resolution background image for page `page_num` of session `sid`.
    Preserves all tables, vector lines, borders, logos, and graphics of that page.
    """
    meta = get_session_meta(sid)
    if not meta or not _is_session_authorized(request, meta):
        return HttpResponseForbidden("Access denied.")

    work_dir = get_session_dir(sid)
    img_path = work_dir / f"page_{page_num}.png"
    if img_path.is_file():
        return HttpResponse(img_path.read_bytes(), content_type="image/png")

    orig_path = get_original_file_path(sid)
    if not orig_path or not orig_path.is_file():
        raise Http404("Document page image not found.")

    ext = orig_path.suffix.lstrip(".").lower()
    if ext == "pdf":
        import pymupdf
        doc = pymupdf.open(str(orig_path))
        if page_num < 1 or page_num > len(doc):
            doc.close()
            raise Http404("Page number out of range.")
        page = doc[page_num - 1]
        pix = page.get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
        doc.close()
        try:
            img_path.write_bytes(img_bytes)
        except Exception:
            pass
        return HttpResponse(img_bytes, content_type="image/png")
    elif ext in ("png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp"):
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = conf.MAX_IMAGE_PIXELS
        try:
            img = Image.open(str(orig_path))
            img.seek(page_num - 1)
            if img.width * img.height > conf.MAX_IMAGE_PIXELS:
                raise Http404("Image exceeds maximum pixel limit.")
        except Image.DecompressionBombError:
            raise Http404("Image decompression bomb detected.")
        except EOFError:
            raise Http404("Page frame out of range.")
        cur_frame = img.copy()
        if cur_frame.mode not in ("RGB", "RGBA"):
            cur_frame = cur_frame.convert("RGB")
        buf = io.BytesIO()
        cur_frame.save(buf, format="PNG")
        img_bytes = buf.getvalue()
        try:
            img_path.write_bytes(img_bytes)
        except Exception:
            pass
        return HttpResponse(img_bytes, content_type="image/png")

    raise Http404("Page image not available for this document type.")


@require_GET
def session_font_file(request: HttpRequest, sid: str, filename: str) -> HttpResponse:
    """
    Secure whitelisted font serving endpoint.
    Serves embedded session fonts, project fonts, and downloaded library fonts
    to the browser with strict path traversal protection.
    """
    import re
    # 1. Strict sanitization of filename (alphanumeric, underscores, hyphens, and valid font ext)
    if not filename or not re.match(r"^[a-zA-Z0-9_\-]+\.(ttf|otf|woff|woff2)$", filename, re.IGNORECASE):
        raise Http404("Invalid font filename.")

    # 2. Path traversal checks
    if ".." in filename or "/" in filename or "\\" in filename or "%" in filename:
        return HttpResponseForbidden("Access denied.")

    target_path = None
    # 3. If sid is not 'shared' or 'common', check session directory first
    if sid not in ("shared", "common"):
        meta = get_session_meta(sid)
        if not meta or not _is_session_authorized(request, meta):
            return HttpResponseForbidden("Access denied.")
        session_font = get_session_dir(sid) / "fonts" / filename
        if session_font.is_file():
            target_path = session_font

    # 4. Check library and project font directories
    if not target_path or not target_path.is_file():
        lib_font = conf.FONT_LIBRARY_DIR / filename
        if lib_font.is_file():
            target_path = lib_font
        else:
            for pdir in conf.PROJECT_FONT_DIRS:
                cand = pdir / filename
                if cand.is_file():
                    target_path = cand
                    break
                cand_sub = pdir / "docedit" / filename
                if cand_sub.is_file():
                    target_path = cand_sub
                    break

    if not target_path or not target_path.is_file():
        raise Http404("Font file not found.")

    ext = target_path.suffix.lower()
    content_types = {
        ".ttf": "font/ttf",
        ".otf": "font/otf",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
    }
    content_type = content_types.get(ext, "application/font-sfnt")
    response = HttpResponse(target_path.read_bytes(), content_type=content_type)
    response["Access-Control-Allow-Origin"] = "*"
    response["Cache-Control"] = "public, max-age=86400"
    return response


@require_POST
def save_document(request: HttpRequest, sid: str) -> JsonResponse:
    """
    Saves user edits to temporary storage and renders the export file
    matching the user's chosen extension.
    For non-editable documents (PDF/images), preserves separate pages and 100% of
    the original document layout, tables, lines, borders, and graphics.
    """
    meta = get_session_meta(sid)
    if not meta:
        return JsonResponse({"success": False, "error": "Session not found."}, status=404)

    if not _is_session_authorized(request, meta):
        return JsonResponse({"success": False, "error": "Access denied."}, status=403)

    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        body = request.POST

    if not isinstance(body, dict):
        return JsonResponse({"success": False, "error": "Invalid request body format."}, status=400)

    html_content = body.get("html_content")
    if html_content is not None:
        html_content = sanitize_document_html(html_content)

    pages_data = body.get("pages_data")
    changed_blocks = body.get("changed_blocks")
    client_version = body.get("version", 0)

    if html_content is None and not pages_data and not changed_blocks:
        return JsonResponse({"success": False, "error": "No content provided to save."}, status=400)

    # Optional font adjustments from editor toolbar
    font_name = body.get("font_name")
    if font_name:
        font_name = sanitize_font_name(font_name)
    font_size = body.get("font_size_pt")

    font_info = meta.get("font_info", {}).copy()
    if font_name and font_name != font_info.get("name"):
        resolved = resolve_document_font(font_name)
        font_info.update(resolved)
    if font_size:
        try:
            font_info["size_pt"] = float(font_size)
        except (ValueError, TypeError):
            pass

    # User choice of download format - PDF only
    chosen_ext = "pdf"

    is_autosave = bool(body.get("is_autosave", False))

    # Apply atomic updates under file lock with version tracking
    update_res = apply_atomic_block_updates(
        sid,
        changed_blocks=changed_blocks,
        pages_data=pages_data,
        client_version=client_version,
        html_content=html_content,
        font_info=font_info,
        export_format=chosen_ext,
    )

    if is_autosave:
        return JsonResponse({
            "success": True,
            "is_autosave": True,
            "message": "Changes saved automatically.",
            "version": update_res["version"],
            "saved_at": update_res["saved_at"],
        })

    # Render & write export file matching chosen format
    work_dir = get_session_dir(sid)
    actual_file_ext = "pdf" if chosen_ext == "searchable_pdf" else chosen_ext
    edited_filename = f"edited.{actual_file_ext}"
    output_path = work_dir / edited_filename

    # If pages_data was not passed in full in request body, reload from updated session meta
    current_pages = pages_data
    if not current_pages:
        fresh_meta = get_session_meta(sid)
        if fresh_meta:
            current_pages = fresh_meta.get("pages")

    try:
        write_document_to_disk(
            html_content=html_content or "",
            output_path=output_path,
            extension=chosen_ext,
            font_info=font_info,
            pages_data=current_pages,
            original_file_path=get_original_file_path(sid),
            work_dir=work_dir,
        )
    except Exception as e:
        logger.exception("Failed exporting edited document for %s: %s", sid, e)
        return JsonResponse({"success": False, "error": f"Failed writing document: {str(e)}"}, status=500)

    # Generate secure one-time download token
    download_token = create_download_token(sid)

    # Update session metadata
    orig_name = meta.get("original_filename", f"document.{actual_file_ext}")
    stem = Path(orig_name).stem
    if chosen_ext == "searchable_pdf":
        download_filename = f"{stem}_searchable.pdf"
    else:
        download_filename = f"{stem}_edited.{chosen_ext}"

    update_session(
        sid,
        status="saved",
        export_format=chosen_ext,
        edited_file=edited_filename,
        edited_saved_at=time.time(),
        font_info=font_info,
    )

    # Collect overflow warnings from exported pages
    overflow_warnings = []
    if current_pages:
        for p in current_pages:
            p_num = p.get("page_num", 1)
            for b in p.get("blocks", []):
                if b.get("overflow_warn"):
                    overflow_warnings.append({
                        "page_num": p_num,
                        "block_id": b.get("id"),
                        "text": (b.get("text") or "")[:40],
                        "overflow_pct": b.get("overflow_pct", 10),
                    })

    fmt_label = "Searchable PDF" if chosen_ext == "searchable_pdf" else chosen_ext.upper()
    download_url = f"{reverse('docedit_download', args=[sid])}?token={download_token}"
    return JsonResponse({
        "success": True,
        "message": f"Document saved temporarily in {fmt_label} format and ready for download.",
        "download_url": download_url,
        "download_token": download_token,
        "download_filename": download_filename,
        "export_format": chosen_ext,
        "version": update_res["version"],
        "overflow_warnings": overflow_warnings,
    })



def download_document(request: HttpRequest, sid: str) -> HttpResponse:
    """
    Streams the temporary edited file to the user for download in their chosen format.
    Accepts GET or POST.
    Never deletes data on GET. Dropped connections, retries or prefetches
    preserve session data until confirmed via POST confirm-download or on TTL.
    """
    meta = get_session_meta(sid)
    if not meta:
        raise Http404("Session not found or expired.")

    if not _is_session_authorized(request, meta):
        return HttpResponseForbidden("Access denied.")

    token = request.GET.get("token") or request.POST.get("token")
    if token and not validate_download_token(sid, token):
        return HttpResponseForbidden("Invalid or expired download token.")

    edited_path = get_edited_file_path(sid)
    if not edited_path or not edited_path.is_file():
        raise Http404("Edited document not found. Please save first.")

    # Determine extension from the edited file or session metadata
    saved_fmt = meta.get("export_format")
    ext = edited_path.suffix.lstrip(".").lower() or saved_fmt or meta.get("extension", "txt").lower()
    orig_name = meta.get("original_filename", f"document.{ext}")
    stem = Path(orig_name).stem
    if saved_fmt == "searchable_pdf":
        download_filename = f"{stem}_searchable.pdf"
    else:
        download_filename = f"{stem}_edited.{ext}"

    mime_type = MIME_TYPES.get(saved_fmt, MIME_TYPES.get(ext, "application/octet-stream"))
    file_bytes = edited_path.read_bytes()

    # Mark as downloaded without destructive purge on GET
    update_session(sid, status="downloaded", downloaded_at=time.time())

    response = HttpResponse(file_bytes, content_type=mime_type)
    response["Content-Disposition"] = f'attachment; filename="{download_filename}"'
    response["X-DocEdit-Downloaded"] = "true"
    response["X-DocEdit-Original-Name"] = download_filename
    response["X-DocEdit-Format"] = ext
    return response


@require_POST
def confirm_download(request: HttpRequest, sid: str) -> JsonResponse:
    """
    Confirms download has completed successfully, then safely purges the session.
    """
    meta = get_session_meta(sid)
    if meta and not _is_session_authorized(request, meta):
        return JsonResponse({"success": False, "error": "Access denied."}, status=403)

    try:
        body = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        body = request.POST

    token = body.get("token") or request.GET.get("token")
    purged = confirm_session_download(sid, token)
    return JsonResponse({
        "success": True,
        "message": "Download confirmed. Temporary session data cleared.",
        "purged": purged,
    })


@require_POST
def cancel_document(request: HttpRequest, sid: str) -> JsonResponse:
    """
    Cancels the document editing / process and purges temporary files from disk.
    """
    meta = get_session_meta(sid)
    if meta and not _is_session_authorized(request, meta):
        return JsonResponse({"success": False, "error": "Access denied."}, status=403)

    purged = purge_session(sid)
    return JsonResponse({
        "success": True,
        "message": "Document process cancelled. Temporary files have been deleted.",
        "purged": purged,
    })


@require_POST
def change_font(request: HttpRequest, sid: str) -> JsonResponse:
    """
    Allows user to switch the active font for their document.
    Resolves availability, downloads if free online, installs to system,
    and returns updated CSS.
    """
    meta = get_session_meta(sid)
    if not meta:
        return JsonResponse({"success": False, "error": "Session not found."}, status=404)

    if not _is_session_authorized(request, meta):
        return JsonResponse({"success": False, "error": "Access denied."}, status=403)

    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        data = request.POST

    if not isinstance(data, dict):
        return JsonResponse({"success": False, "error": "Invalid request body format."}, status=400)

    requested_font = sanitize_font_name(data.get("font_name", "").strip())
    if not requested_font:
        return JsonResponse({"success": False, "error": "No valid font specified."}, status=400)

    font_res = resolve_document_font(requested_font)
    if "size_pt" in data:
        try:
            font_res["size_pt"] = float(data["size_pt"])
        except Exception:
            pass

    editor_css = get_editor_font_css(font_res)

    update_session(
        sid,
        font_info=font_res,
        editor_font_css=editor_css,
    )

    return JsonResponse({
        "success": True,
        "font_info": font_res,
        "editor_font_css": editor_css,
        "message": font_res.get("message", "Font updated."),
    })


@require_GET
def font_list_api(request: HttpRequest) -> JsonResponse:
    """
    Returns all fonts available in the system or OS + project fonts.
    Supports ?refresh=1 to force an immediate re-scan of the operating system.
    """
    force_refresh = request.GET.get("refresh") in ("1", "true", "yes")
    font_data = get_categorized_font_list(force_refresh=force_refresh)
    return JsonResponse({
        "success": True,
        "total_count": font_data["total_count"],
        "groups": {
            "recommended": font_data["recommended"],
            "project": font_data["project"],
            "system": font_data["system"],
        },
        "all_fonts": font_data["all_names"],
        "signature": font_data["signature"],
    })


@require_POST
def install_font_api(request: HttpRequest) -> JsonResponse:
    """
    Installs a new font into the system and DocEdit:
    - If font_file (.ttf/.otf) is uploaded: saves to project font library (and installs to system registry if configured).
    - If font_name is provided: downloads from Google Fonts (if ALLOW_DOWNLOADS is True) and installs.
    Automatically refreshes font list and returns the updated fonts.
    """
    font_file = request.FILES.get("font_file")
    if font_file:
        ext = Path(font_file.name).suffix.lower()
        if ext not in (".ttf", ".otf"):
            return JsonResponse({
                "success": False,
                "error": f"Invalid font format '{ext}'. Please upload a .ttf or .otf font file."
            }, status=400)
        try:
            safe_filename = Path(font_file.name).name
            res = install_uploaded_font(font_file.read(), safe_filename)
            res["fonts"] = get_categorized_font_list(force_refresh=True)
            return JsonResponse(res)
        except Exception as e:
            logger.exception("Failed installing uploaded font: %s", e)
            return JsonResponse({"success": False, "error": f"Failed installing font: {str(e)}"}, status=500)

    if not conf.ALLOW_DOWNLOADS:
        return JsonResponse({
            "success": False,
            "error": "Remote font downloads are disabled by configuration.",
        }, status=403)

    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        body = request.POST

    if not isinstance(body, dict):
        return JsonResponse({"success": False, "error": "Invalid request body format."}, status=400)

    font_name = sanitize_font_name(body.get("font_name", "").strip())
    if not font_name:
        return JsonResponse({"success": False, "error": "No font file or font name provided."}, status=400)

    free_canon = is_font_available_for_free(font_name) or font_name
    downloaded = download_google_font(free_canon)
    if not downloaded:
        return JsonResponse({
            "success": False,
            "error": f"Could not find or download font '{font_name}' online."
        }, status=404)

    return JsonResponse({
        "success": True,
        "name": free_canon,
        "path": str(downloaded),
        "installed_to_system": conf.INSTALL_FONTS_TO_SYSTEM,
        "message": f"Font '{free_canon}' successfully installed to your system and added to DocEdit.",
        "fonts": get_categorized_font_list(force_refresh=True),
    })


@require_GET
def session_word_crop(request: HttpRequest, sid: str, word_id: str) -> HttpResponse:
    """
    Serves a cropped thumbnail of a specific word from the scanned page image with padding.
    Used by the Fuzzy OCR Review Queue to display the original scan beside editable text.
    """
    meta = get_session_meta(sid)
    if not meta or not _is_session_authorized(request, meta):
        return HttpResponseForbidden("Access denied.")

    words = get_session_words(sid)
    target = next((w for w in words if w.get("id") == word_id), None)
    if not target:
        raise Http404("Word not found.")

    page_num = target.get("page", 1)
    bbox = target.get("bbox")
    if not bbox or len(bbox) != 4:
        raise Http404("Word bounding box not available.")

    x, y, w, h = bbox
    work_dir = get_session_dir(sid)
    page_img_path = work_dir / f"page_{page_num}.png"
    if not page_img_path.is_file():
        orig_path = get_original_file_path(sid)
        if not orig_path or not orig_path.is_file():
            raise Http404("Page image not found.")
        ext = meta.get("extension", "").lower()
        if ext == "pdf":
            import pymupdf
            doc = pymupdf.open(str(orig_path))
            if page_num < 1 or page_num > len(doc):
                doc.close()
                raise Http404("Page out of range.")
            pix = doc[page_num - 1].get_pixmap(dpi=conf.OCR_DPI)
            pix.save(str(page_img_path))
            doc.close()
        else:
            from PIL import Image
            img = Image.open(str(orig_path))
            img.seek(page_num - 1)
            img.save(str(page_img_path), format="PNG")

    from PIL import Image
    try:
        page_img = Image.open(str(page_img_path))
    except Exception as e:
        logger.warning("Could not open page image for word crop: %s", e)
        raise Http404("Could not load page image.")

    pad_x = 6
    pad_y = 4
    x0 = max(0, x - pad_x)
    y0 = max(0, y - pad_y)
    x1 = min(page_img.width, x + w + pad_x)
    y1 = min(page_img.height, y + h + pad_y)

    if x1 <= x0 or y1 <= y0:
        raise Http404("Invalid crop dimensions.")

    cropped = page_img.crop((x0, y0, x1, y1))
    buf = io.BytesIO()
    cropped.save(buf, format="PNG")
    crop_bytes = buf.getvalue()

    resp = HttpResponse(crop_bytes, content_type="image/png")
    resp["Cache-Control"] = "public, max-age=3600"
    return resp


@require_GET
def get_fuzzy_words_api(request: HttpRequest, sid: str) -> JsonResponse:
    """
    Returns flagged / fuzzy words for the review queue along with review progress stats.
    """
    meta = get_session_meta(sid)
    if not meta or not _is_session_authorized(request, meta):
        return JsonResponse({"success": False, "error": "Access denied."}, status=403)

    words = get_session_words(sid)
    fuzzy_words = [
        w for w in words
        if w.get("is_fuzzy") and not w.get("is_readonly") and not is_non_latin_script(w.get("text", ""))[0]
    ]
    reviewed_count = sum(1 for w in fuzzy_words if w.get("reviewed"))

    return JsonResponse({
        "success": True,
        "fuzzy_words": fuzzy_words,
        "stats": {
            "total_words": len(words),
            "fuzzy_count": len(fuzzy_words),
            "total_fuzzy": len(fuzzy_words),
            "reviewed_count": reviewed_count,
            "unreviewed_count": max(0, len(fuzzy_words) - reviewed_count),
            "remaining_count": max(0, len(fuzzy_words) - reviewed_count),
            "all_reviewed": len(fuzzy_words) > 0 and reviewed_count >= len(fuzzy_words),
        }
    })


@require_POST
def review_word_api(request: HttpRequest, sid: str, word_id: str) -> JsonResponse:
    """
    Reviews an OCR word: accept, edit, or skip.
    """
    meta = get_session_meta(sid)
    if not meta or not _is_session_authorized(request, meta):
        return JsonResponse({"success": False, "error": "Access denied."}, status=403)

    try:
        body = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        body = request.POST

    action = body.get("action", "accept")
    edited_text = body.get("edited_text")
    if edited_text is None:
        edited_text = body.get("text")
    if edited_text is not None:
        edited_text = str(edited_text).strip()

    res = update_session_word(sid, word_id, action=action, edited_text=edited_text)
    if not res:
        return JsonResponse({"success": False, "error": "Word not found."}, status=404)

    return JsonResponse({
        "success": True,
        "word": res["word"],
        "stats": res["stats"],
    })

