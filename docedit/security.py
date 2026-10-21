"""
Security utilities for DocEdit:
- HTML sanitization via nh3 (allowlist for tags and attributes, blocking XSS)
- Font name validation & CSS sanitization
- OCR language parameter validation (blocking path traversal)
"""
import html
import logging
import re
from html.parser import HTMLParser
from typing import Optional

try:
    import nh3
    _HAS_NH3 = True
except ImportError:
    nh3 = None
    _HAS_NH3 = False

from .conf import conf

logger = logging.getLogger(__name__)

SAFE_FONT_PATTERN = re.compile(r"^[a-zA-Z0-9_\- ]{1,64}$")

ALLOWED_TAGS = {
    "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td",
    "strong", "b", "em", "i", "u", "s", "span", "br", "hr",
    "ul", "ol", "li", "div", "a", "img",
}

ALLOWED_ATTRIBUTES = {
    "*": {"style", "class", "id"},
    "div": {
        "data-block-id", "data-page", "data-font-size-pt", "data-rotation",
        "contenteditable", "spellcheck"
    },
    "span": {"class", "style", "data-fuzzy-word", "data-word-id", "data-conf", "data-conf-tier"},
    "table": {"class", "style", "border", "cellpadding", "cellspacing"},
    "th": {"class", "style", "colspan", "rowspan", "scope"},
    "td": {"class", "style", "colspan", "rowspan"},
    "a": {"href", "title", "target", "class", "style"},
    "img": {"src", "alt", "title", "width", "height", "class", "style"},
}

DROP_CONTENT_TAGS = {"script", "style", "iframe", "object", "embed", "applet", "svg", "math", "noscript"}
SELF_CLOSING = {"br", "hr", "img"}


class _FallbackHTMLSanitizer(HTMLParser):
    """
    Zero-dependency pure-Python HTML sanitizer for environments where
    the compiled Rust 'nh3' package is not installed.
    """
    def __init__(self):
        super().__init__()
        self.result = []
        self.drop_depth = 0

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t in DROP_CONTENT_TAGS:
            self.drop_depth += 1
            return
        if self.drop_depth > 0:
            return
        if t not in ALLOWED_TAGS:
            return

        allowed_attrs = ALLOWED_ATTRIBUTES.get(t, set()) | ALLOWED_ATTRIBUTES.get("*", set())
        clean_attrs = []
        for name, val in attrs:
            if not name or val is None:
                continue
            name_l = name.lower()
            if name_l.startswith("on"):
                continue
            if name_l == "href":
                val_l = val.lower().strip()
                if not (val_l.startswith("http://") or val_l.startswith("https://") or val_l.startswith("mailto:") or val_l.startswith("#")):
                    continue
            if name_l == "src":
                val_l = val.lower().strip()
                if not (val_l.startswith("http://") or val_l.startswith("https://") or val_l.startswith("data:image/") or val_l.startswith("/")):
                    continue
            if name_l == "style":
                if re.search(r"(?:javascript:|expression\(|behavior:|-moz-binding|@import|url\()", val, re.IGNORECASE):
                    continue
            escaped_val = html.escape(val, quote=True)
            clean_attrs.append(f'{name_l}="{escaped_val}"')

        attr_str = (" " + " ".join(clean_attrs)) if clean_attrs else ""
        self.result.append(f"<{t}{attr_str}>")

    def handle_endtag(self, tag):
        t = tag.lower()
        if t in DROP_CONTENT_TAGS:
            if self.drop_depth > 0:
                self.drop_depth -= 1
            return
        if self.drop_depth > 0:
            return
        if t in ALLOWED_TAGS and t not in SELF_CLOSING:
            self.result.append(f"</{t}>")

    def handle_data(self, data):
        if self.drop_depth > 0:
            return
        self.result.append(html.escape(data, quote=False))

    def handle_entityref(self, name):
        if self.drop_depth > 0:
            return
        self.result.append(f"&{name};")

    def handle_charref(self, name):
        if self.drop_depth > 0:
            return
        self.result.append(f"&#{name};")

    def get_clean_html(self) -> str:
        return "".join(self.result)


def sanitize_document_html(raw_html: str) -> str:
    """
    Sanitizes HTML content to prevent Stored XSS attacks while preserving
    allowed document layout structures, tables, text spans, and styles.
    Uses 'nh3' if available; otherwise falls back to the built-in parser.
    """
    if not raw_html:
        return ""

    if _HAS_NH3 and nh3 is not None:
        cleaned = nh3.clean(
            raw_html,
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
            url_schemes={"http", "https", "mailto", "data"},
        )
        cleaned = re.sub(r'style="[^"]*?(?:javascript:|expression\(|behavior:)[^"]*"', '', cleaned, flags=re.IGNORECASE)
        return cleaned

    # Fallback when nh3 is not installed in the environment
    sanitizer = _FallbackHTMLSanitizer()
    sanitizer.feed(raw_html)
    return sanitizer.get_clean_html()


def is_valid_font_name(font_name: Optional[str]) -> bool:
    """Checks if a font name consists only of safe alphanumeric, space, hyphen, and underscore chars."""
    if not font_name or not isinstance(font_name, str):
        return False
    return bool(SAFE_FONT_PATTERN.match(font_name.strip()))


def sanitize_font_name(font_name: Optional[str], default: str = "EB Garamond") -> str:
    """
    Sanitizes a font name for safe interpolation in CSS, HTML, URLs, and filenames.
    Returns default if invalid or containing suspicious characters / injection attempts.
    """
    if not font_name or not isinstance(font_name, str):
        return default
    cleaned = font_name.strip()
    # If font name contains CSS/HTML/traversal injection syntax, reject and return default
    if any(c in cleaned for c in ("{", "}", ";", "/", "\\", "<", ">", "@", "*", "%", ":", "\0")):
        return default
    # Remove quotes
    cleaned = re.sub(r"['\"]", "", cleaned).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if is_valid_font_name(cleaned):
        return cleaned
    fallback = re.sub(r"[^a-zA-Z0-9_\- ]", "", cleaned).strip()
    if fallback and is_valid_font_name(fallback):
        return fallback
    return default


def validate_ocr_lang(
    lang_code: Optional[str],
    default: str = "eng",
    enabled_only: bool = False,
) -> str:
    """
    Validates the ocr_lang parameter against allowed language keys in conf.ALL_OCR_LANGUAGES
    (or conf.OCR_LANGUAGES / conf.DOCEDIT_ENABLED_LANGUAGES if enabled_only=True).
    Supports single keys ('eng') or '+'-delimited combinations ('eng+hin').
    Raises ValueError on path traversal attempts, unconfigured codes, or disabled languages.
    """
    if not lang_code or not isinstance(lang_code, str):
        return default

    clean_code = lang_code.strip().lower()
    # Fast path: check for traversal characters
    if any(c in clean_code for c in (".", "/", "\\", "%", "\0")):
        raise ValueError(f"Invalid characters in ocr_lang: '{lang_code}'")

    master_langs = set(conf.ALL_OCR_LANGUAGES.keys())
    parts = clean_code.split("+")
    for p in parts:
        p_clean = p.strip()
        if not p_clean or p_clean not in master_langs:
            raise ValueError(
                f"Unsupported or invalid OCR language code '{p}'. Allowed codes: {sorted(master_langs)}"
            )

    if enabled_only:
        enabled_langs = set(conf.DOCEDIT_ENABLED_LANGUAGES)
        for p in parts:
            p_clean = p.strip()
            if p_clean not in enabled_langs:
                raise ValueError(
                    f"OCR language '{p_clean}' is currently on hold. Currently enabled languages: {sorted(enabled_langs)}"
                )

    return "+".join(p.strip() for p in parts)


def check_upload_throttle(request, max_requests: int = 15, window_seconds: int = 60) -> bool:
    """
    Enforces upload rate limiting (default 15 uploads per 60 seconds per Django session).
    Returns True if allowed, False if throttled.
    """
    if not hasattr(request, "session"):
        return True
    import time
    now = time.time()
    history = request.session.get("docedit_upload_history", [])
    valid_history = [t for t in history if (now - t) < window_seconds]
    if len(valid_history) >= max_requests:
        return False
    valid_history.append(now)
    request.session["docedit_upload_history"] = valid_history
    return True
