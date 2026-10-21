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
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from .conf import conf
from .fontmatch import is_non_latin_script
from .security import sanitize_document_html

import threading

logger = logging.getLogger(__name__)

_SESSION_LOCK = threading.RLock()
_LOCK_STATE = threading.local()


@contextmanager
def session_file_lock(sid: str, timeout: float = 5.0):
    """
    Cross-platform inter-process and reentrant file lock on the session folder.
    Ensures autosave operations and edits are applied atomically without reentrancy deadlocks.
    """
    if not hasattr(_LOCK_STATE, "depths"):
        _LOCK_STATE.depths = {}
        _LOCK_STATE.fds = {}

    current_depth = _LOCK_STATE.depths.get(sid, 0)
    if current_depth > 0:
        _LOCK_STATE.depths[sid] = current_depth + 1
        try:
            yield
        finally:
            _LOCK_STATE.depths[sid] -= 1
            if _LOCK_STATE.depths[sid] <= 0:
                _LOCK_STATE.depths.pop(sid, None)
        return

    sdir = get_session_dir(sid)
    sdir.mkdir(parents=True, exist_ok=True)
    lock_file_path = sdir / ".session.lock"
    start_time = time.time()

    lock_fd = None
    while True:
        try:
            lock_fd = os.open(str(lock_file_path), os.O_CREAT | os.O_RDWR)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock_fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except (OSError, IOError):
            if lock_fd is not None:
                try:
                    os.close(lock_fd)
                except Exception:
                    pass
                lock_fd = None
            if time.time() - start_time >= timeout:
                logger.warning("Timeout acquiring file lock for session %s", sid)
                break
            time.sleep(0.02)

    _LOCK_STATE.depths[sid] = 1
    _LOCK_STATE.fds[sid] = lock_fd

    try:
        yield
    finally:
        _LOCK_STATE.depths.pop(sid, None)
        _LOCK_STATE.fds.pop(sid, None)
        if lock_fd is not None:
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(lock_fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                os.close(lock_fd)
            except Exception:
                pass


def create_session(original_filename: str, file_bytes: bytes, owner_key: Optional[str] = None) -> str:
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
        "owner_key": owner_key,
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
        "version": 1,
        "download_token": None,
        "download_token_created_at": None,
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
    sdir = get_session_dir(sid)
    sdir.mkdir(parents=True, exist_ok=True)
    path = sdir / "session.json"
    data["updated_at"] = time.time()
    tmp_path = path.with_suffix(f".tmp.{os.getpid()}.{threading.get_ident()}")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # On Windows, os.replace can momentarily raise WinError 5 if file is read by another thread
        for attempt in range(5):
            try:
                tmp_path.replace(path)
                break
            except (PermissionError, OSError):
                if attempt == 4:
                    try:
                        path.write_text(tmp_path.read_text(encoding="utf-8"), encoding="utf-8")
                        tmp_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                else:
                    time.sleep(0.02 * (attempt + 1))
    except (FileNotFoundError, OSError) as e:
        logger.debug("Session %s directory was removed concurrently: %s", sid, e)


def update_session(sid: str, **kwargs) -> Optional[Dict[str, Any]]:
    with _SESSION_LOCK:
        with session_file_lock(sid):
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


def apply_atomic_block_updates(
    sid: str,
    changed_blocks: Optional[List[Dict[str, Any]]] = None,
    pages_data: Optional[List[Dict[str, Any]]] = None,
    client_version: int = 0,
    html_content: Optional[str] = None,
    font_info: Optional[Dict[str, Any]] = None,
    export_format: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Atomically updates session content and/or changed blocks under an inter-process file lock.
    Maintains a strictly monotonic version counter and returns the updated version and timestamp.
    """
    with _SESSION_LOCK:
        with session_file_lock(sid):
            meta = get_session_meta(sid)
            if not meta:
                raise ValueError(f"Session '{sid}' does not exist.")

            current_ver = int(meta.get("version", 0))
            new_ver = max(current_ver + 1, int(client_version))
            meta["version"] = new_ver
            now = time.time()
            meta["updated_at"] = now
            meta["edited_saved_at"] = now

            if font_info:
                meta.setdefault("font_info", {}).update(font_info)
            if export_format:
                meta["export_format"] = export_format

            if html_content is not None:
                save_document_content(sid, html_content)

            if pages_data is not None:
                meta["pages"] = pages_data
            elif changed_blocks:
                pages = meta.get("pages", [])
                if pages:
                    for ch_b in changed_blocks:
                        b_id = ch_b.get("id")
                        p_num = ch_b.get("page_num")
                        p_idx = ch_b.get("page_index")
                        target_p = None
                        if p_num is not None:
                            target_p = next((p for p in pages if p.get("page_number") == p_num), None)
                            if not target_p and 1 <= p_num <= len(pages):
                                target_p = pages[p_num - 1]
                        elif p_idx is not None and 0 <= p_idx < len(pages):
                            target_p = pages[p_idx]

                        if not target_p and b_id:
                            for p in pages:
                                if any(b.get("id") == b_id for b in p.get("blocks", [])):
                                    target_p = p
                                    break
                        if not target_p and pages:
                            target_p = pages[0]

                        if target_p:
                            blocks = target_p.setdefault("blocks", [])
                            existing_b = next((b for b in blocks if b.get("id") == b_id), None)
                            if existing_b:
                                if existing_b.get("is_readonly"):
                                    # Non-Latin / read-only blocks cannot be edited
                                    continue
                                for k, v in ch_b.items():
                                    if k not in ("page_num", "page_index"):
                                        existing_b[k] = v
                            elif ch_b.get("is_new"):
                                blocks.append(ch_b)

                    meta["pages"] = pages

            save_session_meta(sid, meta)
            return {"version": new_ver, "saved_at": now}


def create_download_token(sid: str) -> str:
    """Generates a secure one-time download token for an exported file."""
    with _SESSION_LOCK:
        token = uuid.uuid4().hex
        update_session(
            sid,
            download_token=token,
            download_token_created_at=time.time(),
            download_token_used=False,
        )
        return token


def validate_download_token(sid: str, token: Optional[str]) -> bool:
    """Validates the one-time download token. Does NOT delete data."""
    if not token:
        return False
    meta = get_session_meta(sid)
    if not meta:
        return False
    stored = meta.get("download_token")
    if not stored:
        return False
    created_at = meta.get("download_token_created_at", 0)
    # Token valid for 10 minutes
    if time.time() - created_at > 600:
        return False
    return stored == token


def confirm_session_download(sid: str, token: Optional[str] = None) -> bool:
    """
    Confirms download has completed successfully and purges the session.
    Only purges after confirmed download or explicit cancel.
    """
    with _SESSION_LOCK:
        meta = get_session_meta(sid)
        if not meta:
            return False
        if token and meta.get("download_token") and meta["download_token"] != token:
            return False
        return purge_session(sid)


def save_document_content(sid: str, html_content: str, text_content: Optional[str] = None) -> None:
    work_dir = get_session_dir(sid)
    work_dir.mkdir(parents=True, exist_ok=True)
    cleaned_html = sanitize_document_html(html_content) if html_content else ""
    (work_dir / "document.html").write_text(cleaned_html, encoding="utf-8")
    if text_content is not None:
        (work_dir / "document.txt").write_text(text_content, encoding="utf-8")


def get_document_content(sid: str) -> str:
    path = get_session_dir(sid) / "document.html"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return ""


def save_session_words(sid: str, words: List[Dict[str, Any]]) -> None:
    """Persists per-word OCR results to words.json and updates session metadata."""
    with _SESSION_LOCK:
        with session_file_lock(sid):
            sdir = get_session_dir(sid)
            sdir.mkdir(parents=True, exist_ok=True)
            w_path = sdir / "words.json"
            try:
                with open(w_path, "w", encoding="utf-8") as f:
                    json.dump(words, f, ensure_ascii=False)
            except Exception as e:
                logger.warning("Failed saving words.json for %s: %s", sid, e)

            meta = get_session_meta(sid)
            if meta:
                fuzzy_list = [
                    w for w in words
                    if w.get("is_fuzzy") and not w.get("is_readonly") and not is_non_latin_script(w.get("text", ""))[0]
                ]
                meta["fuzzy_words"] = fuzzy_list
                stats = meta.setdefault("stats", {})
                stats["word_count"] = len(words)
                stats["fuzzy_word_count"] = len(fuzzy_list)
                reviewed_count = sum(1 for w in fuzzy_list if w.get("reviewed"))
                meta["review_stats"] = {
                    "total_fuzzy": len(fuzzy_list),
                    "reviewed_count": reviewed_count,
                    "unreviewed_count": max(0, len(fuzzy_list) - reviewed_count),
                }
                save_session_meta(sid, meta)


def get_session_words(sid: str) -> List[Dict[str, Any]]:
    """Retrieves all per-word OCR results from words.json."""
    w_path = get_session_dir(sid) / "words.json"
    if w_path.is_file():
        try:
            with open(w_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed reading words.json for %s: %s", sid, e)
    meta = get_session_meta(sid)
    if meta:
        return meta.get("fuzzy_words", [])
    return []


def update_session_word(
    sid: str,
    word_id: str,
    action: str = "accept",
    edited_text: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Updates the review status of a word in words.json and synchronizes with session blocks.
    action: 'accept', 'edit', or 'skip'
    """
    with _SESSION_LOCK:
        with session_file_lock(sid):
            words = get_session_words(sid)
            target_word = next((w for w in words if w.get("id") == word_id), None)
            if not target_word:
                return None

            old_text = target_word.get("text", "")
            target_word["reviewed"] = True
            if action == "accept":
                target_word["accepted"] = True
                target_word["review_status"] = "accepted"
            elif action == "edit":
                target_word["accepted"] = True
                target_word["review_status"] = "edited"
                if edited_text is not None:
                    target_word["edited_text"] = edited_text
                    target_word["text"] = edited_text
            elif action == "skip":
                target_word["accepted"] = False
                target_word["review_status"] = "skipped"

            # Save updated words.json
            w_path = get_session_dir(sid) / "words.json"
            try:
                with open(w_path, "w", encoding="utf-8") as f:
                    json.dump(words, f, ensure_ascii=False)
            except Exception as e:
                logger.warning("Failed updating words.json for %s: %s", sid, e)

            reviewed_count = sum(
                1 for w in words
                if w.get("is_fuzzy") and not w.get("is_readonly") and not is_non_latin_script(w.get("text", ""))[0] and w.get("reviewed")
            )
            total_fuzzy = sum(
                1 for w in words
                if w.get("is_fuzzy") and not w.get("is_readonly") and not is_non_latin_script(w.get("text", ""))[0]
            )
            review_stats = {
                "total_fuzzy": total_fuzzy,
                "reviewed_count": reviewed_count,
                "unreviewed_count": max(0, total_fuzzy - reviewed_count),
                "remaining_count": max(0, total_fuzzy - reviewed_count),
                "fuzzy_count": total_fuzzy,
            }

            # Update session meta
            meta = get_session_meta(sid)
            if meta:
                # Update fuzzy_words in meta
                fw = meta.get("fuzzy_words", [])
                for f_item in fw:
                    if f_item.get("id") == word_id:
                        f_item.update(target_word)
                meta["fuzzy_words"] = fw
                meta["review_stats"] = review_stats

                # If word was edited, also update the block text if matching
                if action == "edit" and edited_text is not None and old_text:
                    pages = meta.get("pages", [])
                    p_num = target_word.get("page", 1) or target_word.get("page_num", 1)
                    target_p = next((p for p in pages if p.get("page_num") == p_num or p.get("page_number") == p_num), None)
                    if target_p:
                        for b in target_p.get("blocks", []):
                            b_text = b.get("text", "")
                            if old_text in b_text:
                                b["text"] = b_text.replace(old_text, edited_text, 1)
                                b["is_modified"] = True
                            b_html = b.get("html", "")
                            if old_text in b_html:
                                b["html"] = b_html.replace(old_text, edited_text, 1)
                                b["is_modified"] = True
                    meta["pages"] = pages

                save_session_meta(sid, meta)

            return {
                "word": target_word,
                "stats": review_stats,
            }


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
