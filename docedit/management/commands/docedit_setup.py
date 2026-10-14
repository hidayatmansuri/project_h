"""
Management command to initialize DocEdit:
- Scans and indexes local and system fonts
- Pre-downloads essential book fonts (EB Garamond, Libre Baskerville, etc.)
- Installs downloaded fonts into the system for the current user
- Verifies Tesseract installation and downloads missing language packs (hin, guj, ara)
"""
from django.core.management.base import BaseCommand
from docedit.conf import conf
from docedit.font_catalog import (
    download_google_font,
    get_font_index,
    get_google_fonts_catalogue,
)
from docedit.ocr import ensure_ocr_language, get_available_ocr_languages, get_tesseract_cmd


class Command(BaseCommand):
    help = "Initializes DocEdit: indexes fonts, downloads book typography, and checks OCR."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("=== DocEdit Setup ==="))

        # 1. Tesseract OCR check
        tess = get_tesseract_cmd()
        self.stdout.write(f"Tesseract executable: {tess}")
        available_langs = get_available_ocr_languages()
        self.stdout.write(f"Installed OCR languages: {', '.join(available_langs)}")

        for lang in ("hin", "guj", "ara"):
            if lang not in available_langs:
                self.stdout.write(f"Downloading language pack '{lang}'...")
                if ensure_ocr_language(lang):
                    self.stdout.write(self.style.SUCCESS(f"  [OK] Language pack '{lang}' ready."))
                else:
                    self.stdout.write(self.style.WARNING(f"  [WARN] Could not download '{lang}'."))

        # 2. Font Indexing
        self.stdout.write("Building local font index...")
        idx = get_font_index(force_refresh=True)
        self.stdout.write(self.style.SUCCESS(f"Indexed {len(idx['families'])} local font families."))

        # 3. Google Fonts Catalogue
        self.stdout.write("Loading Google Fonts catalogue...")
        gf = get_google_fonts_catalogue()
        self.stdout.write(self.style.SUCCESS(f"Loaded {len(gf['families'])} Google Font families."))

        # 4. Pre-download essential free book fonts
        essential = ["EB Garamond", "Libre Baskerville", "Cormorant Garamond", "Amiri"]
        self.stdout.write(f"Pre-caching key book fonts: {', '.join(essential)}...")
        for font in essential:
            try:
                p = download_google_font(font)
                if p:
                    self.stdout.write(self.style.SUCCESS(f"  [OK] {font} saved to {p}"))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  [WARN] Failed to download {font}: {e}"))

        self.stdout.write(self.style.SUCCESS("=== DocEdit Setup Complete ==="))
