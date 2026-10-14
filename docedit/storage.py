"""
Temporary session storage management for DocEdit.

Files are stored in ``conf.WORK_DIR / <session_id>`` and are kept only
temporarily for editing and downloading. Once downloaded or cancelled,
or when their TTL expires, they are purged.
"""
import json
import logging
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from .conf import conf

logger = logging.getLogger(__name__)


def create_session(original_filename: str, file_bytes: bytes) -> str:
    """
    Creates a new temporary workspace directory for an uploaded document.
    Returns the session ID.
    """
    sid = uuid.uuid4().hex
    work_dir = get_session_dir(sid)
    work_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(original_filename).suffix.lstrip(".").lower()
    orig_path = work_dir / f"original.{ext}" if ext else work_dir / "original"
    orig_path.write_bytes(file_bytes)

    meta = {
        "id": sid,
        "created_at": time.time(),
        "updated_at": time.time(),
        "original_filename": original_filename,
        "extension": ext,
        "file_size": len(file_bytes),
        "status": "uploaded",  # uploaded -> processing -> ready -> saving -> saved -> downloaded -> cancelled
        "progress": 5,
        "progress_message": "Document uploaded successfully",
        "is_editable": False,
        "needs_ocr": False,
        "error": None,
        "font_info": {
            "name": "Default",
            "size_pt": 12.0,
            "is_system": True,
            "is_downloaded": False,
            "is_alternative": False,
            "alternative_to": None,
            "installed_to_system": False,
            "font_url": None,
            "details": "",
        },
        "stats": {
            "page_count": 0,
            "word_count": 0,
            "char_count": 0,
            "fuzzy_word_count": 0,
        },
        "fuzzy_words": [],  # list of {word, conf, bbox, page}
        "edited_file": None,
        "edited_saved_at": None,
    }
    save_session_meta(sid, meta)
    return sid


def get_session_dir(sid: str) -> Path:
    # Sanitize sid to avoid directory traversal
    clean_sid = "".join(c for c in sid if c.isalnum() or c in ("-", "_"))
    return conf.WORK_DIR / clean_sid


def get_session_meta(sid: str) -> Optional[Dict[str, Any]]:
    path = get_session_dir(sid) / "session.json"
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Failed reading session meta for %s: %s", sid, e)
        return None


def save_session_meta(sid: str, data: Dict[str, Any]) -> None:
    path = get_session_dir(sid) / "session.json"
    data["updated_at"] = time.time()
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp_path.replace(path)


def update_session(sid: str, **kwargs) -> Optional[Dict[str, Any]]:
    meta = get_session_meta(sid)
    if not meta:
        return None
    for k, v in kwargs.items():
        if isinstance(v, dict) and isinstance(meta.get(k), dict):
            meta[k].update(v)
        else:
            meta[k] = v
    save_session_meta(sid, meta)
    return meta


def save_document_content(sid: str, html_content: str, text_content: Optional[str] = None) -> None:
    work_dir = get_session_dir(sid)
    (work_dir / "document.html").write_text(html_content, encoding="utf-8")
    if text_content is not None:
        (work_dir / "document.txt").write_text(text_content, encoding="utf-8")


def get_document_content(sid: str) -> str:
    path = get_session_dir(sid) / "document.html"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    txt_path = get_session_dir(sid) / "document.txt"
    if txt_path.is_file():
        return txt_path.read_text(encoding="utf-8")
    return ""


def get_original_file_path(sid: str) -> Optional[Path]:
    meta = get_session_meta(sid)
    if not meta:
        return None
    ext = meta.get("extension", "")
    target = get_session_dir(sid) / f"original.{ext}" if ext else get_session_dir(sid) / "original"
    if target.is_file():
        return target
    # Fallback search
    for item in get_session_dir(sid).glob("original*"):
        if item.is_file() and not item.name.endswith(".json"):
            return item
    return None


def get_edited_file_path(sid: str) -> Optional[Path]:
    meta = get_session_meta(sid)
    if not meta:
        return None
    edited_rel = meta.get("edited_file")
    if edited_rel:
        p = get_session_dir(sid) / edited_rel
        if p.is_file():
            return p
    ext = meta.get("extension", "")
    cand = get_session_dir(sid) / f"edited.{ext}" if ext else get_session_dir(sid) / "edited"
    if cand.is_file():
        return cand
    return None


def purge_session(sid: str) -> bool:
    """Removes the entire session folder from temporary disk storage."""
    sdir = get_session_dir(sid)
    if sdir.is_dir():
        try:
            shutil.rmtree(sdir, ignore_errors=True)
            return True
        except Exception as e:
            logger.warning("Error purging session %s: %s", sid, e)
    return False


def cleanup_expired_sessions() -> int:
    """Deletes temporary sessions older than conf.TEMP_TTL_HOURS."""
    root = conf.WORK_DIR
    if not root.is_dir():
        return 0
    now = time.time()
    cutoff = now - (conf.TEMP_TTL_HOURS * 3600)
    purged = 0
    for entry in root.iterdir():
        if entry.is_dir():
            try:
                mtime = entry.stat().st_mtime
                if mtime < cutoff:
                    shutil.rmtree(entry, ignore_errors=True)
                    purged += 1
            except Exception as e:
                logger.warning("Failed cleanup on %s: %s", entry, e)
    return purged
