"""
DocEdit configuration.

Every value can be overridden from ``project_h/settings.py`` using the
``DOCEDIT_<NAME>`` setting. Values are read lazily (properties) so that
``override_settings`` works in tests.
"""
import os
from pathlib import Path

from django.conf import settings


def _get(name, default):
    return getattr(settings, f"DOCEDIT_{name}", default)


class DocEditConf:
    # ------------------------------------------------------------------ paths
    @property
    def BASE_DIR(self) -> Path:
        return Path(settings.BASE_DIR)

    @property
    def DOCEDIT_DIR(self) -> Path:
        return Path(__file__).resolve().parent

    @property
    def WORK_DIR(self) -> Path:
        """Temporary per-upload working folders (purged after download/cancel)."""
        return Path(_get("WORK_DIR", self.DOCEDIT_DIR / "media" / "docedit_tmp"))

    @property
    def DATA_DIR(self) -> Path:
        """Caches: font index, Google Fonts catalogue, OCR language packs."""
        return Path(_get("DATA_DIR", self.DOCEDIT_DIR / "media" / "docedit_data"))


    @property
    def FONT_LIBRARY_DIR(self) -> Path:
        """Free fonts downloaded by the app (kept for future use)."""
        return Path(_get("FONT_LIBRARY_DIR", self.BASE_DIR / "static" / "fonts" / "docedit"))

    @property
    def PROJECT_FONT_DIRS(self):
        """Fonts that ship with project-h (Gotu, Asap, Playfair...)."""
        return [Path(p) for p in _get("PROJECT_FONT_DIRS", [self.BASE_DIR / "static" / "fonts"])]

    @property
    def SYSTEM_FONT_DIRS(self):
        dirs = _get("SYSTEM_FONT_DIRS", None)
        if dirs is not None:
            return [Path(d) for d in dirs]
        found = []
        if os.name == "nt":
            windir = os.environ.get("WINDIR", r"C:\Windows")
            found.append(Path(windir) / "Fonts")
            local = os.environ.get("LOCALAPPDATA")
            if local:
                found.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
        else:
            home = Path.home()
            found += [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"),
                      home / ".fonts", home / ".local" / "share" / "fonts",
                      Path("/Library/Fonts"), Path("/System/Library/Fonts"), home / "Library" / "Fonts"]
        return found

    # ----------------------------------------------------------------- limits
    @property
    def MAX_UPLOAD_MB(self) -> int:
        return int(_get("MAX_UPLOAD_MB", 50))

    @property
    def TEMP_TTL_HOURS(self) -> float:
        return float(_get("TEMP_TTL_HOURS", 24))

    @property
    def MAX_PAGES(self) -> int:
        return int(_get("MAX_PAGES", 200))

    # -------------------------------------------------------------------- OCR
    @property
    def TESSERACT_CMD(self):
        val = _get("TESSERACT_CMD", os.environ.get("TESSERACT_CMD"))
        if val and Path(val).is_file():
            return str(val)
        if os.name == "nt":
            local_appdata = os.environ.get("LOCALAPPDATA", "")
            candidates = [
                Path(local_appdata) / "Programs" / "Tesseract-OCR" / "tesseract.exe",
                Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
                Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
            ]
            for c in candidates:
                if c.is_file():
                    return str(c)
        return "tesseract"

    @property
    def TESSDATA_URL(self) -> str:
        # "tessdata" = good balance of speed/accuracy. Use tessdata_best for max accuracy.
        return _get("TESSDATA_URL", "https://github.com/tesseract-ocr/tessdata/raw/main/{lang}.traineddata")

    @property
    def OCR_DPI(self) -> int:
        return int(_get("OCR_DPI", 300))

    @property
    def OCR_LOW_CONFIDENCE(self) -> int:
        """Words recognised below this confidence are flagged for review."""
        return int(_get("OCR_LOW_CONFIDENCE", 70))

    @property
    def OCR_LANGUAGES(self) -> dict:
        return _get("OCR_LANGUAGES", {
            "eng": "English",
            "hin": "Hindi",
            "guj": "Gujarati",
            "ara": "Arabic",
        })

    # ------------------------------------------------------------------ fonts
    @property
    def ALLOW_DOWNLOADS(self) -> bool:
        """Allow downloading free fonts / OCR language packs from the internet."""
        return bool(_get("ALLOW_DOWNLOADS", True))

    @property
    def INSTALL_FONTS_TO_SYSTEM(self) -> bool:
        """Install downloaded fonts for the current OS user (no admin rights needed)."""
        return bool(_get("INSTALL_FONTS_TO_SYSTEM", True))

    @property
    def GOOGLE_FONTS_METADATA_URL(self) -> str:
        return _get("GOOGLE_FONTS_METADATA_URL", "https://fonts.google.com/metadata/fonts")

    @property
    def GOOGLE_FONTS_CSS_URL(self) -> str:
        return _get("GOOGLE_FONTS_CSS_URL", "https://fonts.googleapis.com/css2")

    @property
    def HTTP_TIMEOUT(self) -> int:
        return int(_get("HTTP_TIMEOUT", 25))

    # ------------------------------------------------------------- processing
    @property
    def SYNC_PROCESSING(self) -> bool:
        """Process uploads in the request thread (used by tests)."""
        return bool(_get("SYNC_PROCESSING", False))


conf = DocEditConf()

# Upload extensions -> document kind
EXTENSION_KINDS = {
    "png": "image", "jpg": "image", "jpeg": "image", "tif": "image", "tiff": "image",
    "bmp": "image", "webp": "image",
    "pdf": "pdf",
    "docx": "docx",
    "txt": "text", "md": "markdown", "markdown": "markdown",
    "html": "html", "htm": "html",
}

MIME_TYPES = {
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "tif": "image/tiff",
    "tiff": "image/tiff", "bmp": "image/bmp", "webp": "image/webp",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain", "md": "text/markdown", "markdown": "text/markdown",
    "html": "text/html", "htm": "text/html",
}

KIND_LABELS = {
    "image": "Scanned image",
    "pdf": "PDF document",
    "docx": "Word document",
    "text": "Plain text",
    "markdown": "Markdown",
    "html": "Web page (HTML)",
}
