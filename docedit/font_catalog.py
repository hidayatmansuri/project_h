"""
Font discovery, indexing, Google Fonts downloading, and Windows font installation.

Supports:
1. Indexing installed system fonts + project fonts using fontTools.
2. Checking Google Fonts catalogue for free availability.
3. Downloading free TrueType fonts.
4. Installing downloaded fonts into the system for the current user
   (HKCU\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Fonts) without admin rights.
5. High-quality font substitutes for proprietary book faces.
"""
import hashlib
import io
import json
import logging
import os
import re
import shutil
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .conf import conf

logger = logging.getLogger(__name__)

# Known high-quality free open-source substitutes for common book fonts
FONT_SUBSTITUTES: Dict[str, Dict[str, str]] = {
    # Serif & Traditional Book Typefaces
    "times new roman": {"match": "Tinos", "category": "serif", "reason": "Standard serif book face"},
    "times": {"match": "Tinos", "category": "serif", "reason": "Standard serif book face"},
    "baskerville": {"match": "Libre Baskerville", "category": "serif", "reason": "Faithful open-source revival of John Baskerville's classic book type"},
    "monotype baskerville": {"match": "Libre Baskerville", "category": "serif", "reason": "Faithful open-source revival"},
    "caslon": {"match": "Libre Caslon Text", "category": "serif", "reason": "Revival of William Caslon's 18th-century English book type"},
    "adobe caslon": {"match": "Libre Caslon Text", "category": "serif", "reason": "Revival of William Caslon's book type"},
    "garamond": {"match": "EB Garamond", "category": "serif", "reason": "Claude Garamont 1592 classical book specimen revival"},
    "adobe garamond": {"match": "EB Garamond", "category": "serif", "reason": "Claude Garamont classical book revival"},
    "palatino": {"match": "Cormorant Garamond", "category": "serif", "reason": "Classical humanist renaissance book face with tall x-height"},
    "palatino linotype": {"match": "Cormorant Garamond", "category": "serif", "reason": "Humanist book face match"},
    "book antiqua": {"match": "Cormorant Garamond", "category": "serif", "reason": "Humanist renaissance serif match"},
    "georgia": {"match": "Georgia", "category": "serif", "reason": "Sturdy book serif with wide proportions"},
    "bodoni": {"match": "Bodoni Moda", "category": "serif", "reason": "Didone high-contrast modern book face"},
    "didot": {"match": "Playfair Display", "category": "serif", "reason": "High-contrast 18th-century European editorial type"},
    "minion": {"match": "Crimson Pro", "category": "serif", "reason": "Traditional book face with optical sizes designed for heavy reading"},
    "minion pro": {"match": "Crimson Pro", "category": "serif", "reason": "Traditional book face with optical sizes"},
    "bembo": {"match": "Cardo", "category": "serif", "reason": "Classic Aldine renaissance humanist book face"},
    "sabon": {"match": "Alegreya", "category": "serif", "reason": "Designed specifically for continuous literature reading"},
    "centaur": {"match": "EB Garamond", "category": "serif", "reason": "Venetian classical proportions"},
    "cambria": {"match": "Cambria", "category": "serif", "reason": "Standard document serif"},
    "bookman": {"match": "Merriweather", "category": "serif", "reason": "Legible, robust serif designed for sustained book reading"},
    "bookman old style": {"match": "Merriweather", "category": "serif", "reason": "Robust vintage book serif"},

    # Sans-Serif
    "helvetica": {"match": "Arial", "category": "sans-serif", "reason": "System-native metric-compatible sans-serif substitute"},
    "helvetica neue": {"match": "Arial", "category": "sans-serif", "reason": "System-native metric-compatible sans-serif substitute"},
    "arial": {"match": "Arial", "category": "sans-serif", "reason": "Universal modern sans-serif"},
    "calibri": {"match": "Calibri", "category": "sans-serif", "reason": "Standard modern book & document sans-serif"},
    "aptos": {"match": "Calibri", "category": "sans-serif", "reason": "Modern Microsoft sans-serif, matched to Calibri"},
    "aptos display": {"match": "Calibri", "category": "sans-serif", "reason": "Modern sans-serif match"},
    "segoe ui": {"match": "Segoe UI", "category": "sans-serif", "reason": "Modern Windows interface sans-serif"},
    "tahoma": {"match": "Segoe UI", "category": "sans-serif", "reason": "Clear humanist sans-serif"},
    "trebuchet": {"match": "Trebuchet MS", "category": "sans-serif", "reason": "Humanist sans-serif"},
    "trebuchet ms": {"match": "Trebuchet MS", "category": "sans-serif", "reason": "Humanist sans-serif"},
    "century gothic": {"match": "Century Gothic", "category": "sans-serif", "reason": "Geometric sans-serif match"},
    "futura": {"match": "Century Gothic", "category": "sans-serif", "reason": "Geometric sans-serif revival"},
    "gill sans": {"match": "Cabin", "category": "sans-serif", "reason": "Humanist sans-serif proportions"},
    "verdana": {"match": "Verdana", "category": "sans-serif", "reason": "Wide letterforms with generous spacing"},

    # Monospace / Typewriter
    "courier": {"match": "Courier New", "category": "monospace", "reason": "Metric-compatible vintage typewriter monospace"},
    "courier new": {"match": "Courier New", "category": "monospace", "reason": "Metric-compatible typewriter monospace"},
    "consolas": {"match": "Inconsolata", "category": "monospace", "reason": "Clean monospaced programming/manuscript font"},

    # Hindi / Devanagari book fonts
    "mangal": {"match": "Noto Serif Devanagari", "category": "devanagari", "reason": "Standard Devanagari book serif with full ligature support"},
    "kruti dev": {"match": "Rozha One", "category": "devanagari", "reason": "Classical high-contrast Devanagari book printing type"},
    "chanakya": {"match": "Rozha One", "category": "devanagari", "reason": "Traditional literary Devanagari type"},
    "kokila": {"match": "Noto Serif Devanagari", "category": "devanagari", "reason": "Literary Devanagari book style"},
    "aparajita": {"match": "Noto Serif Devanagari", "category": "devanagari", "reason": "Literary Devanagari book style"},
    "nirmala ui": {"match": "Noto Serif Devanagari", "category": "devanagari", "reason": "Devanagari serif match"},

    # Gujarati book fonts
    "shruti": {"match": "Noto Serif Gujarati", "category": "gujarati", "reason": "Classic Gujarati literary serif typeface"},
    "saral": {"match": "Rasa", "category": "gujarati", "reason": "Elegant literary Gujarati typeface designed for publishing"},
    "gopika": {"match": "Rasa", "category": "gujarati", "reason": "Literary Gujarati publication typeface"},
    "lmg arun": {"match": "Noto Serif Gujarati", "category": "gujarati", "reason": "Traditional Gujarati literary font"},

    # Arabic book fonts
    "traditional arabic": {"match": "Amiri", "category": "arabic", "reason": "Classical Naskh revival based on the pioneering Bulaq Press Arabic books"},
    "simplified arabic": {"match": "Scheherazade New", "category": "arabic", "reason": "Traditional Naskh style for extended literary texts"},
    "lotus": {"match": "Amiri", "category": "arabic", "reason": "Classical Arabic book Naskh"},
    "sakkal majalla": {"match": "Noto Naskh Arabic", "category": "arabic", "reason": "High-legibility Naskh literature font"},
    "andalus": {"match": "Amiri", "category": "arabic", "reason": "Classical Arabic manuscript face"},
}

_SYSTEM_INDEX: Optional[Dict[str, Any]] = None
_GF_CATALOGUE: Optional[Dict[str, Any]] = None


def normalize_font_name(name: str) -> str:
    """Cleans font name for case-insensitive matching."""
    if not name:
        return ""
    # Strip common suffixes like Regular, Bold, MT, PS, Pro
    cleaned = re.sub(r"[,\-_]+", " ", name).strip()
    return " ".join(cleaned.split()).lower()


def get_system_font_signature() -> str:
    """
    Computes a fast signature representing the state of system fonts & registry.
    Changes whenever fonts are installed, added, or removed.
    """
    parts: List[str] = []
    if os.name == "nt":
        import winreg
        for root, key_path in [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows NT\CurrentVersion\Fonts"),
        ]:
            try:
                with winreg.OpenKey(root, key_path, 0, winreg.KEY_READ) as k:
                    info = winreg.QueryInfoKey(k)
                    # info[1]: number of font values, info[2]: last modified timestamp
                    parts.append(f"{key_path}:{info[1]}:{info[2]}")
            except Exception:
                pass

    all_dirs = conf.SYSTEM_FONT_DIRS + conf.PROJECT_FONT_DIRS + [conf.FONT_LIBRARY_DIR]
    for d in all_dirs:
        try:
            if d.is_dir():
                mtime = d.stat().st_mtime
                parts.append(f"{d}:{mtime}")
        except Exception:
            pass

    return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()


def get_font_index(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Builds or loads an index of all available local fonts (System + project-h fonts).
    Cached to conf.DATA_DIR / font_index.json.
    Automatically detects new fonts installed in the system/OS by comparing font signature.
    """
    global _SYSTEM_INDEX
    current_sig = get_system_font_signature()

    if _SYSTEM_INDEX and not force_refresh:
        if _SYSTEM_INDEX.get("signature") == current_sig:
            return _SYSTEM_INDEX

    cache_file = conf.DATA_DIR / "font_index.json"
    if not force_refresh and cache_file.is_file():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
                if cached.get("signature") == current_sig and cached.get("families"):
                    _SYSTEM_INDEX = cached
                    return _SYSTEM_INDEX
        except Exception as e:
            logger.warning("Failed loading font cache %s: %s", cache_file, e)

    index: Dict[str, Any] = {
        "families": {},       # normalized_name -> {name, file, is_system, is_project}
        "postscript": {},     # ps_name -> {name, file}
        "signature": current_sig,
        "indexed_at": time.time(),
    }

    try:
        from fontTools.ttLib import TTFont, TTCollection
    except ImportError:
        logger.warning("fontTools not installed, using filename-based font index")
        TTFont = None
        TTCollection = None

    search_dirs: List[Tuple[Path, bool]] = []
    # Project fonts
    for pdir in conf.PROJECT_FONT_DIRS:
        if pdir.is_dir():
            search_dirs.append((pdir, False))
    # Downloaded font library
    if conf.FONT_LIBRARY_DIR.is_dir():
        search_dirs.append((conf.FONT_LIBRARY_DIR, False))
    # System fonts
    for sdir in conf.SYSTEM_FONT_DIRS:
        if sdir.is_dir():
            search_dirs.append((sdir, True))

    seen_files = set()
    for directory, is_sys in search_dirs:
        try:
            for ext in ("*.ttf", "*.otf", "*.ttc"):
                for font_path in directory.rglob(ext):
                    if font_path in seen_files:
                        continue
                    seen_files.add(font_path)
                    try:
                        # Handle TrueType collections (.ttc)
                        if TTCollection and font_path.suffix.lower() == ".ttc":
                            try:
                                ttc = TTCollection(str(font_path))
                                for coll_font in ttc:
                                    try:
                                        rec = coll_font.get("name")
                                        if rec:
                                            cfam = rec.getDebugName(1)
                                            cps = rec.getDebugName(6)
                                            if cfam:
                                                norm = normalize_font_name(cfam)
                                                entry = {
                                                    "name": cfam,
                                                    "path": str(font_path),
                                                    "filename": font_path.name,
                                                    "is_system": is_sys,
                                                    "is_project": not is_sys,
                                                }
                                                if norm not in index["families"] or not is_sys:
                                                    index["families"][norm] = entry
                                                if cps:
                                                    index["postscript"][cps.lower()] = entry
                                    except Exception:
                                        pass
                                continue
                            except Exception:
                                pass

                        family_name = None
                        ps_name = None
                        if TTFont and font_path.suffix.lower() in (".ttf", ".otf"):
                            try:
                                tt = TTFont(str(font_path), fontNumber=0, lazy=True)
                                name_record = tt.get("name")
                                if name_record:
                                    family_name = name_record.getDebugName(1)
                                    ps_name = name_record.getDebugName(6)
                            except Exception:
                                pass

                        if not family_name:
                            # Fallback to stem
                            stem = font_path.stem
                            stem = re.sub(r"-(Regular|Bold|Italic|BoldItalic|Black|Light|Medium|SemiBold|Semibold)$", "", stem, flags=re.IGNORECASE)
                            clean_stem = stem.replace("_", " ").strip()
                            family_name = clean_stem.title() if clean_stem.islower() else clean_stem

                        norm = normalize_font_name(family_name)
                        entry = {
                            "name": family_name,
                            "path": str(font_path),
                            "filename": font_path.name,
                            "is_system": is_sys,
                            "is_project": not is_sys,
                        }
                        if norm not in index["families"] or not is_sys:
                            index["families"][norm] = entry
                        if ps_name:
                            index["postscript"][ps_name.lower()] = entry
                    except Exception as e:
                        logger.debug("Error reading font file %s: %s", font_path, e)
        except Exception as e:
            logger.warning("Error reading font directory %s: %s", directory, e)

    # On Windows, also enumerate registered fonts from HKLM & HKCU
    if os.name == "nt":
        import winreg
        windir = os.environ.get("WINDIR", r"C:\Windows")
        sys_fonts_dir = Path(windir) / "Fonts"
        local_app = os.environ.get("LOCALAPPDATA")
        user_fonts_dir = Path(local_app) / "Microsoft" / "Windows" / "Fonts" if local_app else None

        for root, key_path in [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows NT\CurrentVersion\Fonts"),
        ]:
            try:
                with winreg.OpenKey(root, key_path, 0, winreg.KEY_READ) as k:
                    num_vals = winreg.QueryInfoKey(k)[1]
                    for i in range(num_vals):
                        try:
                            val_name, val_data, _ = winreg.EnumValue(k, i)
                            # E.g. "Arial (TrueType)", "Calibri (TrueType)"
                            disp = re.sub(r"\s*\((TrueType|OpenType|PostScript)\)\s*$", "", val_name, flags=re.IGNORECASE).strip()
                            if not disp:
                                continue
                            norm = normalize_font_name(disp)
                            if norm in index["families"]:
                                continue

                            # Resolve file
                            p = Path(val_data)
                            if not p.is_file():
                                if (sys_fonts_dir / val_data).is_file():
                                    p = sys_fonts_dir / val_data
                                elif user_fonts_dir and (user_fonts_dir / val_data).is_file():
                                    p = user_fonts_dir / val_data

                            index["families"][norm] = {
                                "name": disp,
                                "path": str(p) if p.is_file() else None,
                                "filename": p.name if p.is_file() else val_data,
                                "is_system": True,
                                "is_project": False,
                            }
                        except Exception:
                            pass
            except Exception:
                pass

    # Save cache
    try:
        conf.DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("Failed saving font index cache: %s", e)

    _SYSTEM_INDEX = index
    return index


def get_categorized_font_list(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Returns all fonts available in the system or OS + project fonts,
    curated and categorized for dropdown display in DocEdit:
    - recommended: Classic book & literary faces
    - project: Fonts that ship with project-h
    - system: All other fonts installed on the OS, alphabetically sorted
    """
    idx = get_font_index(force_refresh=force_refresh)
    families = idx.get("families", {})

    # Recommended classical book & editorial fonts
    recommended_names = [
        "EB Garamond", "Libre Baskerville", "Libre Caslon Text", "Cormorant Garamond",
        "Playfair Display", "Merriweather", "Lora", "Crimson Pro", "Tinos", "Arimo",
        "Roboto", "Cousine", "Noto Serif Devanagari", "Rozha One", "Noto Serif Gujarati",
        "Rasa", "Amiri", "Scheherazade New",
    ]

    seen_norms = set()
    recommended_list = []
    for r_name in recommended_names:
        norm = normalize_font_name(r_name)
        info = families.get(norm)
        item = {
            "name": r_name,
            "label": r_name,
            "is_system": info.get("is_system", False) if info else False,
            "is_project": info.get("is_project", False) if info else False,
            "is_available": info is not None,
        }
        recommended_list.append(item)
        seen_norms.add(norm)

    project_list = []
    system_list = []

    for norm, info in families.items():
        if norm in seen_norms:
            continue
        seen_norms.add(norm)
        name = info.get("name") or norm.title()
        item = {
            "name": name,
            "label": name,
            "is_system": bool(info.get("is_system")),
            "is_project": bool(info.get("is_project")),
            "path": info.get("path"),
        }
        if info.get("is_project"):
            project_list.append(item)
        else:
            system_list.append(item)

    # Sort alphabetically
    project_list.sort(key=lambda x: x["name"].lower())
    system_list.sort(key=lambda x: x["name"].lower())

    all_unique = sorted(
        list({f["name"] for f in (recommended_list + project_list + system_list)}),
        key=lambda x: x.lower()
    )

    return {
        "recommended": recommended_list,
        "project": project_list,
        "system": system_list,
        "all_names": all_unique,
        "total_count": len(all_unique),
        "signature": idx.get("signature", ""),
    }


def _find_system_font_file(name_or_filename: Optional[str]) -> Optional[str]:
    """Resolves font file path from system or user font directories."""
    if not name_or_filename:
        return None
    p = Path(name_or_filename)
    if p.is_file():
        return str(p)

    windir = os.environ.get("WINDIR", r"C:\Windows")
    sys_fonts_dir = Path(windir) / "Fonts"
    local_app = os.environ.get("LOCALAPPDATA")
    user_fonts_dir = Path(local_app) / "Microsoft" / "Windows" / "Fonts" if local_app else None

    # Try direct filename
    for base_dir in [sys_fonts_dir, user_fonts_dir, conf.FONT_LIBRARY_DIR]:
        if base_dir and base_dir.is_dir():
            candidate = base_dir / name_or_filename
            if candidate.is_file():
                return str(candidate)
            for ext in (".ttf", ".otf", ".ttc"):
                cand_ext = base_dir / f"{name_or_filename}{ext}"
                if cand_ext.is_file():
                    return str(cand_ext)
                clean_name = re.sub(r"[^\w]", "", name_or_filename)
                cand_clean = base_dir / f"{clean_name}{ext}"
                if cand_clean.is_file():
                    return str(cand_clean)
    return None


def is_font_available_locally(font_name: str) -> Optional[Dict[str, Any]]:
    """
    Checks if font_name is present locally (system font, project font, or downloaded).
    Returns info dict or None.
    """
    if not font_name:
        return None
    idx = get_font_index()
    norm = normalize_font_name(font_name)
    if not norm:
        return None

    entry = None
    # 1. Exact match
    if norm in idx["families"]:
        entry = dict(idx["families"][norm])

    # 2. Compact match (ignoring spaces & hyphens)
    if not entry:
        compact_norm = re.sub(r"[\s\-_]+", "", norm)
        for k, v in idx["families"].items():
            if re.sub(r"[\s\-_]+", "", k) == compact_norm:
                entry = dict(v)
                break

    # 3. Match with common style qualifiers stripped
    # e.g., 'calibri bold' -> 'calibri', 'arial regular' -> 'arial'
    if not entry:
        base_norm = re.sub(
            r"\b(regular|bold|italic|oblique|light|semibold|medium|black|heavy|extrabold|thin|roman|psmt|ps|mt)\b",
            "",
            norm,
            flags=re.IGNORECASE,
        ).strip()
        base_norm = " ".join(base_norm.split())
        if base_norm and base_norm in idx["families"]:
            entry = dict(idx["families"][base_norm])

    # 4. Check postscript names
    if not entry:
        ps_key = font_name.lower().replace(" ", "").replace("-", "")
        if ps_key in idx.get("postscript", {}):
            entry = dict(idx["postscript"][ps_key])
        else:
            for k, v in idx.get("postscript", {}).items():
                if ps_key == k.replace("-", "") or ps_key == k:
                    entry = dict(v)
                    break

    # 5. Standard common aliases
    if not entry:
        FONT_ALIASES = {
            "times": "times new roman",
            "times-roman": "times new roman",
            "times roman": "times new roman",
            "tiro": "times new roman",
            "helv": "arial",
            "helvetica": "arial",
            "helvetica neue": "arial",
            "couri": "courier new",
            "courier": "courier new",
            "aptos": "calibri",
            "aptos display": "calibri",
        }
        alias = FONT_ALIASES.get(norm) or FONT_ALIASES.get(norm.replace("-", " "))
        if alias and alias in idx["families"]:
            entry = dict(idx["families"][alias])

    if entry:
        if not entry.get("path") or not Path(entry["path"]).is_file():
            resolved_p = _find_system_font_file(entry.get("filename") or entry.get("name"))
            if resolved_p:
                entry["path"] = resolved_p
        return entry

    return None


def find_font_variant_file(
    font_name: str,
    is_bold: bool = False,
    is_italic: bool = False,
    base_font_path: Optional[str] = None
) -> Optional[str]:
    """
    Finds a specific font variant file (Bold, Italic, Bold Italic, or Regular)
    matching the family name and style flags.
    Checks Windows registry font registrations, standard naming conventions,
    and local font directories.
    """
    if not font_name and not base_font_path:
        return None

    # If neither bold nor italic, return base font ONLY if valid and actually matching font_name
    if not is_bold and not is_italic:
        if base_font_path and Path(base_font_path).is_file():
            base_stem = Path(base_font_path).stem.lower().replace("-", "").replace("_", "")
            clean_target = re.sub(r"[^a-zA-Z0-9]", "", font_name or "").lower()
            if not clean_target or clean_target in base_stem or base_stem in clean_target:
                return str(base_font_path)
        loc = is_font_available_locally(font_name)
        if loc and loc.get("path") and Path(loc["path"]).is_file():
            return loc["path"]

    # 1. On Windows, check registry font entries first (most accurate for OS fonts)
    if os.name == "nt":
        import winreg
        windir = os.environ.get("WINDIR", r"C:\Windows")
        sys_fonts_dir = Path(windir) / "Fonts"
        local_app = os.environ.get("LOCALAPPDATA")
        user_fonts_dir = Path(local_app) / "Microsoft" / "Windows" / "Fonts" if local_app else None

        clean_fam = re.sub(
            r"\b(regular|bold|italic|oblique|light|semibold|medium|black|heavy|extrabold|thin|roman|psmt|ps|mt)\b",
            "",
            font_name or "",
            flags=re.IGNORECASE,
        ).strip().lower()

        candidates = []
        for root, key_path in [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows NT\CurrentVersion\Fonts"),
        ]:
            try:
                with winreg.OpenKey(root, key_path, 0, winreg.KEY_READ) as k:
                    num_vals = winreg.QueryInfoKey(k)[1]
                    for i in range(num_vals):
                        try:
                            val_name, val_data, _ = winreg.EnumValue(k, i)
                            disp = re.sub(r"\s*\((TrueType|OpenType|PostScript)\)\s*$", "", val_name, flags=re.IGNORECASE).strip().lower()
                            if clean_fam and clean_fam in disp:
                                is_black = any(w in disp for w in ["black", "heavy", "extrabold"])
                                is_b = any(w in disp for w in ["bold", "semibold", "demibold", "bd"]) or is_black
                                is_i = any(w in disp for w in ["italic", "oblique", "slant", "kursiv"])

                                match_score = 0
                                if is_bold and is_italic:
                                    if is_b and is_i: match_score = 100 if not is_black else 80
                                    elif is_b: match_score = 50
                                    elif is_i: match_score = 50
                                elif is_bold:
                                    if is_b and not is_i: match_score = 100 if not is_black else 80
                                    elif is_b: match_score = 60
                                elif is_italic:
                                    if is_i and not is_b: match_score = 100
                                    elif is_i: match_score = 60
                                else:
                                    if not is_b and not is_i: match_score = 100

                                # Penalize secondary modifiers like "Narrow" or "Condensed" if not requested
                                if "narrow" in disp and "narrow" not in (font_name or "").lower():
                                    match_score -= 20
                                if "condensed" in disp and "condensed" not in (font_name or "").lower():
                                    match_score -= 20
                                if "light" in disp and "light" not in (font_name or "").lower():
                                    match_score -= 30

                                if match_score > 0:
                                    # Resolve file path
                                    p = Path(val_data)
                                    if not p.is_file():
                                        if (sys_fonts_dir / val_data).is_file():
                                            p = sys_fonts_dir / val_data
                                        elif user_fonts_dir and (user_fonts_dir / val_data).is_file():
                                            p = user_fonts_dir / val_data
                                    if p.is_file():
                                        candidates.append((match_score, str(p)))
                        except Exception:
                            pass
            except Exception:
                pass

        if candidates:
            candidates.sort(key=lambda c: c[0], reverse=True)
            return candidates[0][1]

    # 2. File-system stem search
    search_dirs = []
    if base_font_path and Path(base_font_path).is_file():
        search_dirs.append(Path(base_font_path).parent)
    search_dirs.extend(conf.SYSTEM_FONT_DIRS)
    search_dirs.extend(conf.PROJECT_FONT_DIRS)
    search_dirs.append(conf.FONT_LIBRARY_DIR)

    base_stem = ""
    if base_font_path and Path(base_font_path).is_file():
        base_stem = Path(base_font_path).stem
    elif font_name:
        base_stem = re.sub(r"[^\w]", "", font_name)

    stem_clean = re.sub(r"-(Regular|Bold|Italic|BoldItalic|Black|Light|Medium|SemiBold)$", "", base_stem, flags=re.IGNORECASE)
    stem_clean = re.sub(r"(bd|bi|it|b|i|z)$", "", stem_clean, flags=re.IGNORECASE)

    if is_bold and is_italic:
        suffixes = ["-BoldItalic", "BoldItalic", "_BoldItalic", "-Bold-Italic", "bi", "z", "-BI"]
    elif is_bold:
        suffixes = ["-Bold", "Bold", "_Bold", "bd", "b", "-B"]
    elif is_italic:
        suffixes = ["-Italic", "Italic", "_Italic", "it", "i", "-I"]
    else:
        suffixes = ["-Regular", "Regular", "_Regular", ""]

    for d in search_dirs:
        if not d or not d.is_dir():
            continue
        for sfx in suffixes:
            for ext in (".ttf", ".otf"):
                candidate = d / f"{stem_clean}{sfx}{ext}"
                if candidate.is_file():
                    return str(candidate)
                low_cand_name = f"{stem_clean}{sfx}{ext}".lower()
                try:
                    for f in d.iterdir():
                        if f.name.lower() == low_cand_name:
                            return str(f)
                except Exception:
                    pass

    if base_font_path and Path(base_font_path).is_file():
        base_stem_low = Path(base_font_path).stem.lower().replace("-", "").replace("_", "")
        clean_target = re.sub(r"[^a-zA-Z0-9]", "", font_name or "").lower()
        if not clean_target or clean_target in base_stem_low or base_stem_low in clean_target:
            return str(base_font_path)

    loc = is_font_available_locally(font_name)
    if loc and loc.get("path") and Path(loc["path"]).is_file():
        return loc["path"]

    return None



def get_google_fonts_catalogue() -> Dict[str, Any]:
    """
    Loads list of Google Fonts. Caches to conf.DATA_DIR / google_fonts.json.
    Falls back to built-in list if offline.
    """
    global _GF_CATALOGUE
    if _GF_CATALOGUE:
        return _GF_CATALOGUE

    cache_path = conf.DATA_DIR / "google_fonts.json"
    if cache_path.is_file():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                _GF_CATALOGUE = json.load(f)
                return _GF_CATALOGUE
        except Exception as e:
            logger.warning("Error reading Google Fonts cache: %s", e)

    catalogue = {"families": {}}
    if conf.ALLOW_DOWNLOADS:
        try:
            req = urllib.request.Request(
                conf.GOOGLE_FONTS_METADATA_URL,
                headers={"User-Agent": "project-h-docedit/1.0"}
            )
            with urllib.request.urlopen(req, timeout=conf.HTTP_TIMEOUT) as resp:
                content = resp.read().decode("utf-8")
                if content.startswith(")]}'"):
                    content = content[4:].strip()
                data = json.loads(content)
                for item in data.get("familyMetadataList", []):
                    fam = item.get("family")
                    if fam:
                        catalogue["families"][normalize_font_name(fam)] = {
                            "family": fam,
                            "category": item.get("category", "serif"),
                            "subsets": item.get("subsets", []),
                            "is_free": True,
                        }
            # Cache it
            try:
                conf.DATA_DIR.mkdir(parents=True, exist_ok=True)
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(catalogue, f, ensure_ascii=False)
            except Exception as e:
                logger.warning("Failed saving GF cache: %s", e)
            _GF_CATALOGUE = catalogue
            return catalogue
        except Exception as e:
            logger.info("Could not fetch Google Fonts metadata online: %s. Using built-in catalogue.", e)

    # Built-in essential free fonts catalogue for books
    builtin_fonts = [
        "EB Garamond", "Libre Baskerville", "Libre Caslon Text", "Cormorant Garamond",
        "Playfair Display", "Merriweather", "Lora", "Crimson Pro", "Cardo", "Alegreya",
        "Cinzel", "Bodoni Moda", "Gelasio", "Tinos", "Arimo", "Cousine", "Roboto",
        "Open Sans", "Jost", "Cabin", "Inconsolata", "Gotu", "Asap", "Source Serif 4",
        "Noto Serif Devanagari", "Rozha One", "Rasa", "Noto Serif Gujarati", "Amiri",
        "Scheherazade New", "Noto Naskh Arabic", "Yatra One", "Kadwa",
    ]
    for bf in builtin_fonts:
        catalogue["families"][normalize_font_name(bf)] = {
            "family": bf,
            "category": "serif",
            "is_free": True,
        }
    _GF_CATALOGUE = catalogue
    return catalogue


def is_font_available_for_free(font_name: str) -> Optional[str]:
    """
    Checks if font_name is freely available online (via Google Fonts).
    Returns canonical family name if free, else None.
    """
    cat = get_google_fonts_catalogue()
    norm = normalize_font_name(font_name)
    if norm in cat["families"]:
        return cat["families"][norm]["family"]
    for k, v in cat["families"].items():
        if k == norm or norm.startswith(k) or k.startswith(norm):
            return v["family"]
    return None


def find_nearest_match(font_name: str) -> Dict[str, Any]:
    """
    Finds the nearest match for a given font name.
    Intelligently classifies unknown fonts into sans-serif, serif, monospace, or script,
    and returns the best available system font (e.g. Calibri, Arial, Times New Roman, Consolas)
    or high-quality free Google equivalent, rather than defaulting to EB Garamond for everything.
    """
    norm = normalize_font_name(font_name)
    # 1. Direct substitution table
    if norm in FONT_SUBSTITUTES:
        sub = FONT_SUBSTITUTES[norm]
        match_name = sub["match"]
        loc = is_font_available_locally(match_name)
        return {
            "original": font_name,
            "nearest_match": loc["name"] if loc else match_name,
            "reason": sub["reason"],
            "category": sub.get("category", "serif"),
        }

    # 2. Key matching in substitute table
    for k, sub in FONT_SUBSTITUTES.items():
        if k in norm:
            match_name = sub["match"]
            loc = is_font_available_locally(match_name)
            return {
                "original": font_name,
                "nearest_match": loc["name"] if loc else match_name,
                "reason": sub["reason"],
                "category": sub.get("category", "serif"),
            }

    # 3. Categorization heuristic
    # Monospace / typewriter
    mono_kw = ("mono", "typewriter", "courier", "console", "consolas", "code", "terminal", "cascadia", "inconsolata", "monaco", "menlo")
    if any(s in norm for s in mono_kw):
        for candidate in ("Consolas", "Courier New", "Cousine", "Inconsolata"):
            loc = is_font_available_locally(candidate)
            if loc:
                return {"original": font_name, "nearest_match": loc["name"], "reason": "Nearest available monospace type", "category": "monospace"}
        return {"original": font_name, "nearest_match": "Consolas", "reason": "Monospace match", "category": "monospace"}

    # Devanagari
    if any(s in norm for s in ("devanagari", "hindi", "sanskrit", "marathi", "mangal", "kokila", "aparajita")):
        for candidate in ("Mangal", "Nirmala UI", "Noto Serif Devanagari", "Rozha One"):
            loc = is_font_available_locally(candidate)
            if loc:
                return {"original": font_name, "nearest_match": loc["name"], "reason": "Nearest available Devanagari font", "category": "devanagari"}
        return {"original": font_name, "nearest_match": "Noto Serif Devanagari", "reason": "Free literary Devanagari serif", "category": "devanagari"}

    # Gujarati
    if any(s in norm for s in ("gujarati", "guj", "shruti", "saral")):
        for candidate in ("Shruti", "Noto Serif Gujarati", "Rasa"):
            loc = is_font_available_locally(candidate)
            if loc:
                return {"original": font_name, "nearest_match": loc["name"], "reason": "Nearest available Gujarati font", "category": "gujarati"}
        return {"original": font_name, "nearest_match": "Noto Serif Gujarati", "reason": "Free literary Gujarati serif", "category": "gujarati"}

    # Arabic
    if any(s in norm for s in ("arabic", "farsi", "urdu", "naskh", "amiri")):
        for candidate in ("Traditional Arabic", "Simplified Arabic", "Amiri", "Noto Naskh Arabic"):
            loc = is_font_available_locally(candidate)
            if loc:
                return {"original": font_name, "nearest_match": loc["name"], "reason": "Nearest available Arabic literary type", "category": "arabic"}
        return {"original": font_name, "nearest_match": "Amiri", "reason": "Classical Arabic literary Naskh", "category": "arabic"}

    # Sans-serif
    sans_kw = (
        "sans", "gothic", "grotesk", "grotesque", "helvetica", "arial", "calibri", "aptos",
        "segoe", "tahoma", "verdana", "trebuchet", "corbel", "candara", "franklin", "futura",
        "gill", "inter", "roboto", "lato", "poppins", "nunito", "open sans", "century gothic"
    )
    if any(s in norm for s in sans_kw):
        for candidate in ("Calibri", "Arial", "Segoe UI", "Roboto", "Open Sans"):
            loc = is_font_available_locally(candidate)
            if loc:
                return {"original": font_name, "nearest_match": loc["name"], "reason": "Nearest available clean sans-serif", "category": "sans-serif"}
        return {"original": font_name, "nearest_match": "Calibri", "reason": "Standard clean sans-serif match", "category": "sans-serif"}

    # Serif
    for candidate in ("Times New Roman", "Georgia", "Cambria", "EB Garamond", "Libre Baskerville"):
        loc = is_font_available_locally(candidate)
        if loc:
            return {"original": font_name, "nearest_match": loc["name"], "reason": "Nearest available book serif", "category": "serif"}

    return {
        "original": font_name,
        "nearest_match": "Times New Roman",
        "reason": "Standard literary book serif match",
        "category": "serif",
    }


def download_google_font(family_name: str) -> Optional[Path]:
    """
    Downloads TrueType font file for a Google Font.
    Saves to conf.FONT_LIBRARY_DIR / <family>.ttf.
    """
    if not conf.ALLOW_DOWNLOADS:
        return None

    dest_dir = conf.FONT_LIBRARY_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w\-]", "", family_name.replace(" ", ""))
    target_ttf = dest_dir / f"{safe_name}-Regular.ttf"
    if target_ttf.is_file() and target_ttf.stat().st_size > 1000:
        return target_ttf

    try:
        # Request CSS with legacy UA to receive .ttf url instead of woff2
        url = f"{conf.GOOGLE_FONTS_CSS_URL}?family={urllib.parse.quote(family_name)}:wght@400;700"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1)"})
        with urllib.request.urlopen(req, timeout=conf.HTTP_TIMEOUT) as resp:
            css_text = resp.read().decode("utf-8")

        # Find ttf url
        ttf_urls = re.findall(r"url\((https://[^\)]+\.ttf)\)", css_text)
        if not ttf_urls:
            # Try woff2 fallback if ttf not found
            ttf_urls = re.findall(r"url\((https://[^\)]+)\)", css_text)

        if not ttf_urls:
            logger.warning("No font file url found in CSS for %s", family_name)
            return None

        # Download the regular font
        font_file_url = ttf_urls[0]
        req_font = urllib.request.Request(font_file_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req_font, timeout=conf.HTTP_TIMEOUT) as font_resp:
            target_ttf.write_bytes(font_resp.read())

        # Update local index
        get_font_index(force_refresh=True)

        # Install to Windows system if configured
        if conf.INSTALL_FONTS_TO_SYSTEM:
            install_font_to_system(target_ttf, family_name)

        return target_ttf
    except Exception as e:
        logger.warning("Failed downloading font %s: %s", family_name, e)
        return None


def install_font_to_system(font_path: Path, family_name: str) -> bool:
    """
    Installs font into Windows for the current user (no admin rights needed):
    Copies to %LOCALAPPDATA%\\Microsoft\\Windows\\Fonts and registers in HKCU Fonts registry.
    """
    if os.name != "nt":
        return False
    try:
        local_appdata = os.environ.get("LOCALAPPDATA")
        if not local_appdata:
            return False
        user_fonts_dir = Path(local_appdata) / "Microsoft" / "Windows" / "Fonts"
        user_fonts_dir.mkdir(parents=True, exist_ok=True)
        dest_font = user_fonts_dir / font_path.name
        if not dest_font.is_file() or dest_font.stat().st_size != font_path.stat().st_size:
            shutil.copy2(font_path, dest_font)

        import winreg
        key_path = r"Software\Microsoft\Windows NT\CurrentVersion\Fonts"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            val_name = f"{family_name} (TrueType)"
            winreg.SetValueEx(key, val_name, 0, winreg.REG_SZ, str(dest_font))

        # Notify Windows about the new font via AddFontResource / SendMessage
        try:
            import ctypes
            ctypes.windll.gdi32.AddFontResourceW(str(dest_font))
            HWND_BROADCAST = 0xFFFF
            WM_FONTCHANGE = 0x001D
            ctypes.windll.user32.SendMessageW(HWND_BROADCAST, WM_FONTCHANGE, 0, 0)
        except Exception:
            pass

        logger.info("Successfully installed font %s to Windows system", family_name)
        get_font_index(force_refresh=True)
        return True
    except Exception as e:
        logger.warning("Failed to install font %s to system: %s", family_name, e)
        return False


def install_uploaded_font(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """
    Installs a user-uploaded font file (.ttf or .otf):
    1. Determines font family name from file headers.
    2. Saves to conf.FONT_LIBRARY_DIR.
    3. If on Windows, installs to current user fonts and registry.
    4. Automatically updates and refreshes font index.
    """
    ext = Path(filename).suffix.lower()
    if ext not in (".ttf", ".otf"):
        raise ValueError(f"Unsupported font format '{ext}'. Only .ttf and .otf font files are supported.")

    family_name = None
    try:
        from fontTools.ttLib import TTFont
        tt = TTFont(io.BytesIO(file_bytes), fontNumber=0, lazy=True)
        name_record = tt.get("name")
        if name_record:
            family_name = name_record.getDebugName(1)
    except Exception as e:
        logger.debug("Failed reading font family name from file: %s", e)

    if not family_name:
        stem = Path(filename).stem
        stem = re.sub(r"-(Regular|Bold|Italic|BoldItalic|Black|Light|Medium|SemiBold|Semibold)$", "", stem, flags=re.IGNORECASE)
        clean_stem = stem.replace("_", " ").strip()
        family_name = clean_stem.title() if clean_stem.islower() else clean_stem

    # Save to FONT_LIBRARY_DIR
    target_dir = conf.FONT_LIBRARY_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / filename
    target_path.write_bytes(file_bytes)

    # Install to Windows system
    installed_sys = False
    if conf.INSTALL_FONTS_TO_SYSTEM:
        installed_sys = install_font_to_system(target_path, family_name)

    # Force index refresh
    get_font_index(force_refresh=True)

    return {
        "success": True,
        "name": family_name,
        "filename": filename,
        "path": str(target_path),
        "installed_to_system": installed_sys,
        "message": f"Font '{family_name}' successfully installed to your system and added to DocEdit.",
    }


def resolve_document_font(detected_font_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Core font decision logic:
    1. If font is available locally -> use it.
    2. If font is available free online -> download, use it, install to system.
    3. If not free or not available -> inform user of original & nearest match.
       If nearest match is available free online -> download, use it, install to system.
    """
    target = (detected_font_name or "").strip()
    if not target or target.lower() in ("default", "unknown", "serif", "sans-serif"):
        # Default book font (EB Garamond or Playfair/Gotu)
        target = "EB Garamond"

    # Step 1: Is it available locally?
    local_info = is_font_available_locally(target)
    if local_info:
        return {
            "name": local_info["name"],
            "resolved_name": local_info["name"],
            "is_system": local_info.get("is_system", False),
            "is_downloaded": False,
            "is_alternative": False,
            "alternative_to": None,
            "installed_to_system": True,
            "font_path": local_info.get("path"),
            "status": "system_available",
            "message": f"Using font '{local_info['name']}' from your system.",
        }

    # Step 2: Is it freely available online?
    free_canon = is_font_available_for_free(target)
    if free_canon:
        downloaded = download_google_font(free_canon)
        if downloaded:
            return {
                "name": free_canon,
                "resolved_name": free_canon,
                "is_system": False,
                "is_downloaded": True,
                "is_alternative": False,
                "alternative_to": None,
                "installed_to_system": conf.INSTALL_FONTS_TO_SYSTEM,
                "font_path": str(downloaded),
                "status": "downloaded_free",
                "message": f"Font '{free_canon}' downloaded and installed to your system for future reference.",
            }

    # Step 3: Not freely available -> find nearest match
    sub = find_nearest_match(target)
    alt_name = sub["nearest_match"]
    reason = sub["reason"]

    # Check if alternative is available locally or online
    alt_local = is_font_available_locally(alt_name)
    if alt_local:
        return {
            "name": alt_local["name"],
            "resolved_name": alt_local["name"],
            "is_system": alt_local.get("is_system", False),
            "is_downloaded": False,
            "is_alternative": True,
            "alternative_to": target,
            "nearest_match_reason": reason,
            "installed_to_system": True,
            "font_path": alt_local.get("path"),
            "status": "alternative_local",
            "message": f"Original font '{target}' is not freely available. Nearest free match is '{alt_local['name']}' ({reason}).",
        }

    # Download the nearest match
    downloaded_alt = download_google_font(alt_name)
    return {
        "name": alt_name,
        "resolved_name": alt_name,
        "is_system": False,
        "is_downloaded": bool(downloaded_alt),
        "is_alternative": True,
        "alternative_to": target,
        "nearest_match_reason": reason,
        "installed_to_system": bool(downloaded_alt and conf.INSTALL_FONTS_TO_SYSTEM),
        "font_path": str(downloaded_alt) if downloaded_alt else None,
        "status": "alternative_downloaded",
        "message": f"Original font '{target}' is not freely available. Downloaded nearest free match '{alt_name}' and installed to system ({reason}).",
    }
