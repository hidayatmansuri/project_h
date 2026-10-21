"""
Font detection, visual matching for old scanned books, and CSS generation.

Identifies font names from document metadata (PDF, DOCX) or visual script
characteristics (scanned images), resolves them to available local or downloaded
fonts, and produces the required CSS rules for the editor.
"""
import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from .font_catalog import (
    find_nearest_match_with_fonttools,
    generate_document_all_fonts_css,
    resolve_document_font,
    resolve_font_with_fallback,
)
from .security import sanitize_font_name

logger = logging.getLogger(__name__)


def clean_pdf_font_name(raw_name: str) -> str:
    """
    Cleans PostScript / PDF subset prefixes and styles:
    'ABCDEF+TimesNewRomanPS-BoldMT' -> 'Times New Roman'
    'Calibri-Bold' -> 'Calibri'
    'ArialMT' -> 'Arial'
    """
    if not raw_name:
        return ""
    name = raw_name.strip()
    # Strip subset prefix like 'ABCDEF+' or 'BAAAAA+'
    name = re.sub(r"^[A-Z0-9]{6}\+", "", name)
    if "+" in name and len(name.split("+")[0]) <= 7:
        name = name.split("+", 1)[1]

    # Quick canonical matching for common PDF fonts
    known_families = [
        ("timesnewroman", "Times New Roman"),
        ("timesroman", "Times New Roman"),
        ("times", "Times New Roman"),
        ("tiro", "Times New Roman"),
        ("tibo", "Times New Roman"),
        ("tiit", "Times New Roman"),
        ("tibi", "Times New Roman"),
        ("arialmt", "Arial"),
        ("arial", "Arial"),
        ("helv", "Helvetica"),
        ("hebo", "Helvetica"),
        ("heit", "Helvetica"),
        ("hebi", "Helvetica"),
        ("helvetica", "Helvetica"),
        ("calibri", "Calibri"),
        ("segoeui", "Segoe UI"),
        ("aptos", "Aptos"),
        ("georgia", "Georgia"),
        ("cambria", "Cambria"),
        ("verdana", "Verdana"),
        ("tahoma", "Tahoma"),
        ("consolas", "Consolas"),
        ("couriernew", "Courier New"),
        ("courier", "Courier New"),
        ("couri", "Courier New"),
        ("cobi", "Courier New"),
        ("cobo", "Courier New"),
        ("coit", "Courier New"),
        ("trebuchetms", "Trebuchet MS"),
        ("trebuchet", "Trebuchet MS"),
        ("centurygothic", "Century Gothic"),
        ("palatino", "Palatino Linotype"),
        ("bookantiqua", "Book Antiqua"),
        ("candara", "Candara"),
        ("corbel", "Corbel"),
        ("constantia", "Constantia"),
        ("franklin", "Franklin Gothic Medium"),
        ("inter", "Inter"),
        ("poppins", "Poppins"),
        ("lato", "Lato"),
        ("montserrat", "Montserrat"),
        ("ebgaramond", "EB Garamond"),
        ("garamond", "EB Garamond"),
        ("librebaskerville", "Libre Baskerville"),
        ("baskerville", "Libre Baskerville"),
        ("librecaslon", "Libre Caslon Text"),
        ("caslon", "Libre Caslon Text"),
        ("playfair", "Playfair Display"),
        ("merriweather", "Merriweather"),
        ("roboto", "Roboto"),
        ("opensans", "Open Sans"),
        ("sourceserif", "Source Serif 4"),
        ("sourcesans", "Source Sans 3"),
        ("notoserifdevanagari", "Noto Serif Devanagari"),
        ("notoserifgujarati", "Noto Serif Gujarati"),
        ("amiri", "Amiri"),
    ]

    clean_key = re.sub(r"[^a-zA-Z0-9]", "", name).lower()
    for prefix, display in known_families:
        if clean_key.startswith(prefix):
            return display

    # Replace hyphens, underscores, commas, and dots with space
    name = re.sub(r"[-_,.]+", " ", name)
    # Strip common PostScript suffixes and style qualifiers
    name = re.sub(
        r"\b(PSMT|PS|MT|Pro|Std|Regular|Roman|Bold|Italic|Oblique|Light|SemiBold|Semibold|Medium|Black|Heavy|ExtraBold|ExtraLight|Hairline|Thin)\b",
        "",
        name,
        flags=re.IGNORECASE,
    )
    # Split camelCase
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    return " ".join(name.split()).strip()


_NON_LATIN_SCRIPT_RANGES = [
    ("arabic", [
        (0x0600, 0x06FF),  # Arabic / Urdu
        (0x0750, 0x077F),  # Arabic Supplement
        (0x08A0, 0x08FF),  # Arabic Extended-A
        (0xFB50, 0xFDFF),  # Arabic Presentation Forms-A
        (0xFE70, 0xFEFF),  # Arabic Presentation Forms-B
    ]),
    ("devanagari", [
        (0x0900, 0x097F),  # Devanagari (Hindi, Marathi, Sanskrit)
        (0xA8E0, 0xA8FF),  # Devanagari Extended
    ]),
    ("gujarati", [
        (0x0A80, 0x0AFF),  # Gujarati
    ]),
    ("bengali", [
        (0x0980, 0x09FF),  # Bengali / Assamese
    ]),
    ("gurmukhi", [
        (0x0A00, 0x0A7F),  # Gurmukhi
    ]),
    ("tamil", [
        (0x0B80, 0x0BFF),  # Tamil
    ]),
    ("telugu", [
        (0x0C00, 0x0C7F),  # Telugu
    ]),
    ("kannada", [
        (0x0C80, 0x0CFF),  # Kannada
    ]),
    ("malayalam", [
        (0x0D00, 0x0D7F),  # Malayalam
    ]),
    ("hebrew", [
        (0x0590, 0x05FF),  # Hebrew
        (0xFB1D, 0xFB4F),  # Hebrew Presentation Forms
    ]),
    ("thai", [
        (0x0E00, 0x0E7F),  # Thai
    ]),
]


def is_non_latin_script(text: str) -> Tuple[bool, Optional[str]]:
    """
    Checks if a string contains non-Latin complex script characters (Arabic, Indic, Hebrew, etc.)
    that cannot be properly inserted into a PDF text layer without shaping or bidirectional RTL handling.
    Returns (True, script_name) if any non-Latin character is found, otherwise (False, None).
    """
    if not text:
        return False, None

    for ch in text:
        cp = ord(ch)
        # Fast path: ASCII, Latin-1 Supplement, Latin Extended-A/B, and common Latin punctuation are safe
        if cp < 0x0590:
            continue
        for script_name, ranges in _NON_LATIN_SCRIPT_RANGES:
            for start, end in ranges:
                if start <= cp <= end:
                    return True, script_name

    return False, None


def detect_script(text: str) -> str:
    """
    Detects predominant script from text sample.
    Returns: 'devanagari', 'gujarati', 'arabic', or 'latin'.
    """
    if not text:
        return "latin"

    dev_count = 0
    guj_count = 0
    ara_count = 0
    total = 0

    for ch in text[:5000]:
        cp = ord(ch)
        if 0x0900 <= cp <= 0x097F:
            dev_count += 1
            total += 1
        elif 0x0A80 <= cp <= 0x0AFF:
            guj_count += 1
            total += 1
        elif 0x0600 <= cp <= 0x06FF or 0x0750 <= cp <= 0x077F or 0x08A0 <= cp <= 0x08FF:
            ara_count += 1
            total += 1
        elif ch.isalpha():
            total += 1

    if total == 0:
        return "latin"
    if dev_count / total > 0.2:
        return "devanagari"
    if guj_count / total > 0.2:
        return "gujarati"
    if ara_count / total > 0.2:
        return "arabic"
    return "latin"


def detect_visual_font_for_scanned_book(sample_text: str = "") -> str:
    """
    For old scanned books where font metadata is absent from the raster image:
    Detects the script and selects the most authentic classical book typeface.
    """
    script = detect_script(sample_text)
    if script == "devanagari":
        return "Noto Serif Devanagari"
    elif script == "gujarati":
        return "Noto Serif Gujarati"
    elif script == "arabic":
        return "Amiri"
    else:
        # Classical printed literature serif (EB Garamond or Libre Baskerville)
        return "EB Garamond"


def get_editor_font_css(font_info: Dict[str, Any]) -> str:
    """
    Generates CSS @font-face or Google Fonts @import rule for the editor.
    """
    raw_family = font_info.get("name", "EB Garamond")
    family = sanitize_font_name(raw_family)
    font_path = font_info.get("font_path")

    # If it's a project font or static font file in static/
    # If font_path exists and points to static/
    if font_path and "static" in font_path:
        # Use local relative static URL
        rel = font_path.split("static", 1)[1].replace("\\", "/").lstrip("/")
        return f"""
        @font-face {{
            font-family: '{family}';
            src: url('/static/{rel}') format('truetype');
            font-weight: normal;
            font-style: normal;
        }}
        """

    # If it's a standard system font, no @font-face is required
    if font_info.get("is_system") and not font_info.get("is_downloaded"):
        return ""

    # Google Fonts import fallback so browser renders it with 100% fidelity
    safe_family = urllib.parse.quote_plus(family)
    return f"@import url('https://fonts.googleapis.com/css2?family={safe_family}:ital,wght@0,400;0,700;1,400;1,700&display=swap');"
