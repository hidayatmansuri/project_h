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
    "times new roman": {"match": "Tinos", "category": "serif", "reason": "Metric-compatible free book serif"},
    "times": {"match": "Tinos", "category": "serif", "reason": "Metric-compatible free book serif"},
    "baskerville": {"match": "Libre Baskerville", "category": "serif", "reason": "Faithful open-source revival of John Baskerville's classic book type"},
    "monotype baskerville": {"match": "Libre Baskerville", "category": "serif", "reason": "Faithful open-source revival"},
    "caslon": {"match": "Libre Caslon Text", "category": "serif", "reason": "Revival of William Caslon's 18th-century English book type"},
    "adobe caslon": {"match": "Libre Caslon Text", "category": "serif", "reason": "Revival of William Caslon's book type"},
    "garamond": {"match": "EB Garamond", "category": "serif", "reason": "Claude Garamont 1592 classical book specimen revival"},
    "adobe garamond": {"match": "EB Garamond", "category": "serif", "reason": "Claude Garamont classical book revival"},
    "palatino": {"match": "Cormorant Garamond", "category": "serif", "reason": "Classical humanist renaissance book face with tall x-height"},
    "palatino linotype": {"match": "Cormorant Garamond", "category": "serif", "reason": "Humanist book face match"},
    "book antiqua": {"match": "Cormorant Garamond", "category": "serif", "reason": "Humanist renaissance serif match"},
    "georgia": {"match": "Gelasio", "category": "serif", "reason": "Metric-compatible open serif with sturdy book proportions"},
    "bodoni": {"match": "Bodoni Moda", "category": "serif", "reason": "Didone high-contrast modern book face"},
    "didot": {"match": "Playfair Display", "category": "serif", "reason": "High-contrast 18th-century European editorial type"},
    "minion": {"match": "Crimson Pro", "category": "serif", "reason": "Traditional book face with optical sizes designed for heavy reading"},
    "minion pro": {"match": "Crimson Pro", "category": "serif", "reason": "Traditional book face with optical sizes"},
    "bembo": {"match": "Cardo", "category": "serif", "reason": "Classic Aldine renaissance humanist book face"},
    "sabon": {"match": "Alegreya", "category": "serif", "reason": "Designed specifically for continuous literature reading"},
    "centaur": {"match": "EB Garamond", "category": "serif", "reason": "Venetian classical proportions"},
    "cambria": {"match": "Caladea", "category": "serif", "reason": "Metric-compatible open-source substitute"},
    "bookman": {"match": "Merriweather", "category": "serif", "reason": "Legible, robust serif designed for sustained book reading"},
    "bookman old style": {"match": "Merriweather", "category": "serif", "reason": "Robust vintage book serif"},

    # Sans-Serif
    "helvetica": {"match": "Roboto", "category": "sans-serif", "reason": "Modern neo-grotesque sans-serif with excellent legibility"},
    "helvetica neue": {"match": "Roboto", "category": "sans-serif", "reason": "Modern neo-grotesque sans-serif"},
    "arial": {"match": "Arimo", "category": "sans-serif", "reason": "Metric-compatible free modern sans"},
    "calibri": {"match": "Carlito", "category": "sans-serif", "reason": "Metric-compatible open-source match"},
    "futura": {"match": "Jost", "category": "sans-serif", "reason": "Geometric sans-serif revival"},
    "gill sans": {"match": "Cabin", "category": "sans-serif", "reason": "Humanist sans-serif proportions"},
    "verdana": {"match": "Open Sans", "category": "sans-serif", "reason": "Wide letterforms with generous spacing"},

    # Monospace / Typewriter
    "courier": {"match": "Cousine", "category": "monospace", "reason": "Metric-compatible vintage typewriter monospace"},
    "courier new": {"match": "Cousine", "category": "monospace", "reason": "Metric-compatible typewriter monospace"},
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


def get_font_index(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Builds or loads an index of all available local fonts (System + project-h fonts).
    Cached to conf.DATA_DIR / font_index.json.
    """
    global _SYSTEM_INDEX
    if _SYSTEM_INDEX and not force_refresh:
        return _SYSTEM_INDEX

    cache_file = conf.DATA_DIR / "font_index.json"
    if not force_refresh and cache_file.is_file():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                _SYSTEM_INDEX = json.load(f)
                return _SYSTEM_INDEX
        except Exception as e:
            logger.warning("Failed loading font cache %s: %s", cache_file, e)

    index: Dict[str, Any] = {
        "families": {},       # normalized_name -> {name, file, is_system, is_project}
        "postscript": {},     # ps_name -> {name, file}
        "indexed_at": time.time(),
    }

    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        logger.warning("fontTools not installed, using filename-based font index")
        TTFont = None

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
                        family_name = None
                        ps_name = None
                        if TTFont and font_path.suffix.lower() in (".ttf", ".otf"):
                            try:
                                tt = TTFont(str(font_path), fontNumber=0, lazy=True)
                                name_record = tt.get("name")
                                if name_record:
                                    for r in name_record.names:
                                        if r.nameID == 1 and not family_name:
                                            family_name = r.toUnicode()
                                        elif r.nameID == 6 and not ps_name:
                                            ps_name = r.toUnicode()
                                        if family_name and ps_name:
                                            break
                            except Exception:
                                pass

                        if not family_name:
                            # Fallback to stem
                            stem = font_path.stem
                            stem = re.sub(r"-(Regular|Bold|Italic|BoldItalic|Black|Light|Medium|SemiBold|Semibold)$", "", stem, flags=re.IGNORECASE)
                            family_name = stem.replace("_", " ")

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

    # Save cache
    try:
        conf.DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("Failed saving font index cache: %s", e)

    _SYSTEM_INDEX = index
    return index


def is_font_available_locally(font_name: str) -> Optional[Dict[str, Any]]:
    """
    Checks if font_name is present locally (system font, project font, or downloaded).
    Returns info dict or None.
    """
    if not font_name:
        return None
    idx = get_font_index()
    norm = normalize_font_name(font_name)
    if norm in idx["families"]:
        return idx["families"][norm]

    # Partial / stem match
    for k, v in idx["families"].items():
        if k == norm or norm.startswith(k) or k.startswith(norm):
            return v
    # Check postscript names
    ps_key = font_name.lower().replace(" ", "").replace("-", "")
    for k, v in idx["postscript"].items():
        if ps_key in k.replace("-", ""):
            return v
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
    Finds the nearest free match for a given font name.
    """
    norm = normalize_font_name(font_name)
    # 1. Direct substitution table
    if norm in FONT_SUBSTITUTES:
        sub = FONT_SUBSTITUTES[norm]
        return {
            "original": font_name,
            "nearest_match": sub["match"],
            "reason": sub["reason"],
            "category": sub.get("category", "serif"),
        }
    # 2. Key matching in substitute table
    for k, sub in FONT_SUBSTITUTES.items():
        if k in norm:
            return {
                "original": font_name,
                "nearest_match": sub["match"],
                "reason": sub["reason"],
                "category": sub.get("category", "serif"),
            }

    # 3. Keyword heuristic
    if any(s in norm for s in ("devanagari", "hindi", "sanskrit", "marathi")):
        return {"original": font_name, "nearest_match": "Noto Serif Devanagari", "reason": "Free literary Devanagari serif", "category": "devanagari"}
    if any(s in norm for s in ("gujarati", "guj")):
        return {"original": font_name, "nearest_match": "Noto Serif Gujarati", "reason": "Free literary Gujarati serif", "category": "gujarati"}
    if any(s in norm for s in ("arabic", "farsi", "urdu", "naskh")):
        return {"original": font_name, "nearest_match": "Amiri", "reason": "Classical Arabic literary Naskh", "category": "arabic"}
    if any(s in norm for s in ("sans", "gothic", "grotesk", "grotesque")):
        return {"original": font_name, "nearest_match": "Roboto", "reason": "Modern legible open-source sans-serif", "category": "sans-serif"}
    if any(s in norm for s in ("mono", "typewriter", "courier", "console")):
        return {"original": font_name, "nearest_match": "Cousine", "reason": "Metric typewriter open-source monospace", "category": "monospace"}

    # Default book serif fallback
    return {
        "original": font_name,
        "nearest_match": "EB Garamond",
        "reason": "Universal classical book serif with antique reading elegance",
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
        return True
    except Exception as e:
        logger.warning("Failed to install font %s to system: %s", family_name, e)
        return False


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
