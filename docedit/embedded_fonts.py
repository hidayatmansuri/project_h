"""
Embedded font extraction, analysis, and validation using PyMuPDF and fontTools.

Extracts embedded fonts from PDF documents into a session-private folder,
strips subset prefixes (e.g. 'ABCDEF+'), inspects true typeface metadata
(family, style, weight, metrics, embedding permissions via OS/2 fsType),
and checks character coverage (cmap) to determine if the embedded font can
be used directly or requires fallback to a full font match.
"""
import io
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import fontTools.ttLib

logger = logging.getLogger(__name__)


def strip_subset_prefix(font_name: str) -> str:
    """
    Strips the 6-character random uppercase subset tag prefix + '+' from font names.
    E.g. 'BCDEEE+Calibri-Bold' -> 'Calibri-Bold'
         'ABCDEF+TimesNewRomanPSMT' -> 'TimesNewRomanPSMT'
    """
    if not font_name:
        return ""
    name = font_name.strip()
    name = re.sub(r"^[A-Z0-9]{6}\+", "", name)
    if "+" in name and len(name.split("+")[0]) <= 7:
        name = name.split("+", 1)[1]
    return name.strip()


def is_subset_font(font_name: str) -> bool:
    """Returns True if the font name carries a standard PDF subset tag prefix."""
    if not font_name:
        return False
    return bool(re.match(r"^[A-Z0-9]{6}\+", font_name.strip()))


def sanitize_filename(name: str) -> str:
    """Sanitizes font name for safe filename usage."""
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", name)


def extract_embedded_font(
    doc: Any,
    xref: int,
    session_fonts_dir: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    """
    Extracts embedded font at xref, parses true typography metadata via fontTools,
    checks OS/2 embedding permissions, and records supported cmap characters.
    Saves the font file strictly into session_fonts_dir.
    """
    if xref <= 0:
        return None

    try:
        f_data = doc.extract_font(xref)
    except Exception as e:
        logger.debug("Failed extracting font at xref %s: %s", xref, e)
        return None

    if not f_data or len(f_data) < 4:
        return None

    raw_name, ext, fonttype, font_bytes = f_data
    if not font_bytes:
        return None

    clean_name = strip_subset_prefix(raw_name)
    is_subset = is_subset_font(raw_name)

    family_name = clean_name
    subfamily_name = "Regular"
    full_name = clean_name
    ps_name = clean_name
    weight_class = 400
    width_class = 5
    is_bold = False
    is_italic = False
    upem = 1000
    ascender = 800.0
    descender = -200.0
    x_height = None
    cap_height = None
    fs_type = 0
    is_restricted = False
    cmap_codepoints: Set[int] = set()

    try:
        tt = fontTools.ttLib.TTFont(io.BytesIO(font_bytes))

        # Read typography names from name table
        if "name" in tt:
            n_table = tt["name"]
            fam = n_table.getDebugName(16) or n_table.getDebugName(1)
            if fam:
                family_name = fam.strip()
            sub = n_table.getDebugName(17) or n_table.getDebugName(2)
            if sub:
                subfamily_name = sub.strip()
            fn = n_table.getDebugName(4)
            if fn:
                full_name = fn.strip()
            ps = n_table.getDebugName(6)
            if ps:
                ps_name = ps.strip()

        # Read head table for flags & units per em
        if "head" in tt:
            upem = tt["head"].unitsPerEm or 1000
            mac_style = getattr(tt["head"], "macStyle", 0)
            if mac_style & 1:
                is_bold = True
            if mac_style & 2:
                is_italic = True

        # Read OS/2 table for weight, metrics, and embedding permissions
        if "OS/2" in tt:
            os2 = tt["OS/2"]
            weight_class = getattr(os2, "usWeightClass", 400) or 400
            width_class = getattr(os2, "usWidthClass", 5) or 5
            if weight_class >= 600:
                is_bold = True

            fs_sel = getattr(os2, "fsSelection", 0)
            if fs_sel & 1:
                is_italic = True
            if fs_sel & 32:
                is_bold = True

            fs_type = getattr(os2, "fsType", 0) or 0
            # Bit 1 (0x0002): Restricted License Embedding
            # If bit 1 is set and neither bit 2 (Print/Preview 0x0004) nor bit 3 (Editable 0x0008) is set
            if (fs_type & 0x0002) != 0 and (fs_type & 0x000C) == 0:
                is_restricted = True

            if hasattr(os2, "sxHeight") and os2.sxHeight > 0:
                x_height = round(float(os2.sxHeight), 1)
            if hasattr(os2, "sCapHeight") and os2.sCapHeight > 0:
                cap_height = round(float(os2.sCapHeight), 1)

        # Read hhea for ascender / descender
        if "hhea" in tt:
            hhea = tt["hhea"]
            ascender = float(getattr(hhea, "ascent", 800))
            descender = float(getattr(hhea, "descent", -200))

        # Read cmap for supported character codepoints
        cmap = tt.getBestCmap()
        if cmap:
            cmap_codepoints = set(cmap.keys())
        elif "cmap" in tt:
            for t_table in tt["cmap"].tables:
                if hasattr(t_table, "cmap") and t_table.cmap:
                    cmap_codepoints.update(t_table.cmap.keys())

    except Exception as e:
        logger.debug("fontTools inspection failed for xref %s (%s): %s", xref, raw_name, e)

    # Save to private session folder if provided
    file_path = None
    if session_fonts_dir and font_bytes:
        try:
            session_fonts_dir.mkdir(parents=True, exist_ok=True)
            safe_f = sanitize_filename(f"embedded_{xref}_{clean_name}")
            target_file = session_fonts_dir / f"{safe_f}.{ext}"
            target_file.write_bytes(font_bytes)
            file_path = str(target_file)
        except Exception as e:
            logger.debug("Failed saving font file for xref %s: %s", xref, e)

    return {
        "xref": xref,
        "raw_name": raw_name,
        "clean_name": clean_name,
        "family": family_name,
        "subfamily": subfamily_name,
        "full_name": full_name,
        "ps_name": ps_name,
        "ext": ext,
        "font_type": fonttype,
        "weight_class": weight_class,
        "width_class": width_class,
        "is_bold": is_bold,
        "is_italic": is_italic,
        "units_per_em": upem,
        "ascender": ascender,
        "descender": descender,
        "x_height": x_height,
        "cap_height": cap_height,
        "fs_type": fs_type,
        "is_restricted": is_restricted,
        "is_subset": is_subset,
        "cmap_codepoints": cmap_codepoints,
        "cmap_char_count": len(cmap_codepoints),
        "file_path": file_path,
    }


def extract_all_embedded_fonts(
    doc: Any,
    session_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Extracts all unique embedded fonts from all pages of the document.
    Stores files inside session_dir / 'fonts' if session_dir is given.
    Returns:
        {
            "by_xref": {xref: font_info},
            "by_res_name": {res_name: font_info},
            "by_clean_name": {clean_name.lower(): font_info},
        }
    """
    session_fonts_dir = (session_dir / "fonts") if session_dir else None

    by_xref: Dict[int, Dict[str, Any]] = {}
    by_res_name: Dict[str, Dict[str, Any]] = {}
    by_clean_name: Dict[str, Dict[str, Any]] = {}

    for page in doc:
        try:
            fonts = page.get_fonts(full=True)
        except Exception:
            fonts = []

        for f_info in fonts:
            if not f_info or len(f_info) < 1:
                continue
            xref = f_info[0]
            res_name = f_info[4] if len(f_info) > 4 else ""

            if xref > 0 and xref not in by_xref:
                f_meta = extract_embedded_font(doc, xref, session_fonts_dir=session_fonts_dir)
                if f_meta:
                    by_xref[xref] = f_meta
                    c_name_key = f_meta["clean_name"].lower()
                    if c_name_key not in by_clean_name:
                        by_clean_name[c_name_key] = f_meta
                    fam_key = f_meta["family"].lower()
                    if fam_key not in by_clean_name:
                        by_clean_name[fam_key] = f_meta

            if xref in by_xref:
                f_meta = by_xref[xref]
                if res_name:
                    by_res_name[res_name] = f_meta
                    by_res_name[res_name.lstrip("/")] = f_meta

    return {
        "by_xref": by_xref,
        "by_res_name": by_res_name,
        "by_clean_name": by_clean_name,
    }


def can_embedded_font_render_text(font_info: Dict[str, Any], text: str) -> bool:
    """
    Checks if every non-whitespace character in text is present in the embedded font's cmap.
    Respects OS/2 fsType embedding permissions (returns False if restricted).
    If True, the embedded subset font has full glyph coverage for this edited text.
    """
    if not font_info:
        return False
    if font_info.get("is_restricted", False):
        return False

    cmap: Set[int] = font_info.get("cmap_codepoints", set())
    if not cmap:
        return False

    for ch in text:
        if ch.isspace():
            continue
        if ord(ch) not in cmap:
            return False

    return True


def serialize_embedded_font_summary(font_info: Dict[str, Any]) -> Dict[str, Any]:
    """Returns a JSON-serializable summary of font metadata without large sets/buffers."""
    if not font_info:
        return {}
    return {
        "xref": font_info.get("xref"),
        "raw_name": font_info.get("raw_name"),
        "clean_name": font_info.get("clean_name"),
        "family": font_info.get("family"),
        "subfamily": font_info.get("subfamily"),
        "full_name": font_info.get("full_name"),
        "ps_name": font_info.get("ps_name"),
        "ext": font_info.get("ext"),
        "font_type": font_info.get("font_type"),
        "weight_class": font_info.get("weight_class"),
        "is_bold": font_info.get("is_bold"),
        "is_italic": font_info.get("is_italic"),
        "units_per_em": font_info.get("units_per_em"),
        "fs_type": font_info.get("fs_type"),
        "is_restricted": font_info.get("is_restricted"),
        "is_subset": font_info.get("is_subset"),
        "cmap_char_count": font_info.get("cmap_char_count", len(font_info.get("cmap_codepoints", []))),
        "file_path": font_info.get("file_path"),
    }

