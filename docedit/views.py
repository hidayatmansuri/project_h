"""
DocEdit views and REST API endpoints.
"""
import io
import json
import logging
import time
from pathlib import Path

from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
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
from .fontmatch import get_editor_font_css
from .processing import start_session_processing
from .storage import (
    cleanup_expired_sessions,
    create_session,
    get_document_content,
    get_edited_file_path,
    get_original_file_path,
    get_session_dir,
    get_session_meta,
    purge_session,
    save_document_content,
    update_session,
)
from .writers import write_document_to_disk

logger = logging.getLogger(__name__)


@ensure_csrf_cookie
def docedit_home(request: HttpRequest) -> HttpResponse:
    """Renders the main DocEdit application interface."""
    # Periodic background cleanup of expired sessions
    try:
        cleanup_expired_sessions()
    except Exception:
        pass

    allowed_exts = sorted(EXTENSION_KINDS.keys())
    allowed_exts_str = ", ".join(f".{e}" for e in allowed_exts)

    # OCR languages
    languages = [
        {"code": code, "name": name}
        for code, name in conf.OCR_LANGUAGES.items()
    ]

    fonts_data = get_categorized_font_list()

    context = {
        "title": "Document Editor | project-h",
        "languages": languages,
        "fonts": fonts_data,
        "max_upload_mb": conf.MAX_UPLOAD_MB,
        "allowed_extensions": allowed_exts_str,
        "accept_mime": "image/*,.pdf,.docx,.txt,.md,.html,.htm",
    }
    return render(request, "docedit/docedit.html", context)


@require_POST
def upload_document(request: HttpRequest) -> JsonResponse:
    """
    Handles document upload. Creates session and initiates extraction/OCR.
    """
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
    if ext not in EXTENSION_KINDS:
        return JsonResponse({
            "success": False,
            "error": f"Unsupported file type (.{ext}). Supported types: {', '.join(sorted(EXTENSION_KINDS.keys()))}."
        }, status=400)

    ocr_lang = request.POST.get("ocr_lang", "eng").strip()
    file_bytes = upload.read()

    sid = create_session(upload.name, file_bytes)

    # Kick off processing
    start_session_processing(sid, ocr_lang=ocr_lang)

    return JsonResponse({
        "success": True,
        "session_id": sid,
        "message": "File uploaded successfully. Processing started.",
    })


@require_GET
def session_status(request: HttpRequest, sid: str) -> JsonResponse:
    """Returns current processing/editing status and metadata for the side panel."""
    meta = get_session_meta(sid)
    if not meta:
        return JsonResponse({"success": False, "error": "Session not found or expired."}, status=404)

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
        "editor_font_css": meta.get("editor_font_css", ""),
        "edited_file": meta.get("edited_file"),
        "error": meta.get("error"),
    }

    # If editable, include current document HTML
    if meta.get("is_editable"):
        response_data["document_html"] = get_document_content(sid)

    return JsonResponse(response_data)


@require_GET
def session_page_image(request: HttpRequest, sid: str, page_num: int) -> HttpResponse:
    """
    Returns the high-resolution background image for page `page_num` of session `sid`.
    Preserves all tables, vector lines, borders, logos, and graphics of that page.
    """
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
        img = Image.open(str(orig_path))
        try:
            img.seek(page_num - 1)
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

    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        body = request.POST

    html_content = body.get("html_content")
    pages_data = body.get("pages_data")

    if html_content is None and not pages_data:
        return JsonResponse({"success": False, "error": "No content provided to save."}, status=400)

    # Optional font adjustments from editor toolbar
    font_name = body.get("font_name")
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

    # User choice of download format
    export_format = body.get("export_format")
    orig_ext = meta.get("extension", "txt").lower()
    if not export_format or export_format == "original":
        chosen_ext = orig_ext
    else:
        chosen_ext = export_format.lstrip(".").lower()

    if chosen_ext not in EXTENSION_KINDS:
        chosen_ext = orig_ext

    is_autosave = bool(body.get("is_autosave", False))

    # Save HTML to workspace
    if html_content is not None:
        save_document_content(sid, html_content)
    if pages_data:
        update_session(sid, pages=pages_data)

    if is_autosave:
        update_session(
            sid,
            font_info=font_info,
            export_format=chosen_ext,
            edited_saved_at=time.time(),
        )
        return JsonResponse({
            "success": True,
            "is_autosave": True,
            "message": "Changes saved automatically.",
            "saved_at": time.time(),
        })

    # Render & write export file matching chosen format
    work_dir = get_session_dir(sid)
    edited_filename = f"edited.{chosen_ext}"
    output_path = work_dir / edited_filename

    try:
        write_document_to_disk(
            html_content=html_content or "",
            output_path=output_path,
            extension=chosen_ext,
            font_info=font_info,
            pages_data=pages_data,
            original_file_path=get_original_file_path(sid),
            work_dir=work_dir,
        )
    except Exception as e:
        logger.exception("Failed exporting edited document for %s: %s", sid, e)
        return JsonResponse({"success": False, "error": f"Failed writing document: {str(e)}"}, status=500)

    # Update session metadata
    orig_name = meta.get("original_filename", f"document.{chosen_ext}")
    stem = Path(orig_name).stem
    download_filename = f"{stem}_edited.{chosen_ext}"

    update_session(
        sid,
        status="saved",
        export_format=chosen_ext,
        edited_file=edited_filename,
        edited_saved_at=time.time(),
        font_info=font_info,
    )

    return JsonResponse({
        "success": True,
        "message": f"Document saved temporarily in {chosen_ext.upper()} format and ready for download.",
        "download_url": reverse("docedit_download", args=[sid]),
        "download_filename": download_filename,
        "export_format": chosen_ext,
    })



@require_GET
def download_document(request: HttpRequest, sid: str) -> HttpResponse:
    """
    Streams the temporary edited file to the user for download on their desired system folder
    in their chosen format.
    Displays / returns headers so frontend can display success message noting
    that the file has not been saved permanently on the server.
    """
    meta = get_session_meta(sid)
    if not meta:
        raise Http404("Session not found or expired.")

    edited_path = get_edited_file_path(sid)
    if not edited_path or not edited_path.is_file():
        raise Http404("Edited document not found. Please save first.")

    # Determine extension from the edited file or session metadata
    ext = edited_path.suffix.lstrip(".").lower() or meta.get("export_format") or meta.get("extension", "txt").lower()
    orig_name = meta.get("original_filename", f"document.{ext}")
    stem = Path(orig_name).stem
    download_filename = f"{stem}_edited.{ext}"

    mime_type = MIME_TYPES.get(ext, "application/octet-stream")

    # Read bytes into memory before purging so user receives the file cleanly
    file_bytes = edited_path.read_bytes()

    # Immediate server cleanup: as requested, delete all edited documents and temporary files
    # as soon as the user saves/downloads the document to their folder in the system,
    # preventing the project from accumulating unnecessary space.
    purge_session(sid)

    response = HttpResponse(file_bytes, content_type=mime_type)
    response["Content-Disposition"] = f'attachment; filename="{download_filename}"'
    response["X-DocEdit-Downloaded"] = "true"
    response["X-DocEdit-Original-Name"] = download_filename
    response["X-DocEdit-Format"] = ext
    return response



@require_POST
def cancel_document(request: HttpRequest, sid: str) -> JsonResponse:
    """
    Cancels the document editing / process and purges temporary files from disk.
    """
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

    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        data = request.POST

    requested_font = data.get("font_name", "").strip()
    if not requested_font:
        return JsonResponse({"success": False, "error": "No font specified."}, status=400)

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
    - If font_file (.ttf/.otf) is uploaded: saves and installs into system & Windows registry.
    - If font_name is provided: downloads from Google Fonts and installs into system & Windows registry.
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
            res = install_uploaded_font(font_file.read(), font_file.name)
            res["fonts"] = get_categorized_font_list(force_refresh=True)
            return JsonResponse(res)
        except Exception as e:
            logger.exception("Failed installing uploaded font: %s", e)
            return JsonResponse({"success": False, "error": f"Failed installing font: {str(e)}"}, status=500)

    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        body = request.POST

    font_name = body.get("font_name", "").strip()
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
