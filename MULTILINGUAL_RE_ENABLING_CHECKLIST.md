# Multilingual Re-Enabling Checklist (Hindi, Gujarati, Arabic, Urdu)

This document outlines the technical prerequisites, shaping architectures, font configurations, and testing protocols required to safely re-enable non-Latin multilingual OCR, editing, and PDF export in **DocEdit**.

---

## 1. Background & Why Multilingual is On Hold

PyMuPDF's standard text insertion functions (`insert_text` and `insert_textbox`) write characters into PDF content streams using standard 1-to-1 glyph indices. 

1. **Complex Script Shaping (Indic / Devanagari & Gujarati):**
   - Characters change shape depending on consonants and vowels (matras, halants, conjuncts, conjunct ligatures like क्ष, त्र, ज्ञ, and reph/rakar).
   - `insert_text` outputs disjoint, unshaped glyph fragments (e.g., rendering "हिन्दी" as broken "ह ि न ् द ी"), corrupting the text visually and syntactically.
2. **Right-to-Left (RTL) & Bidirectional Layout (Arabic & Urdu):**
   - Arabic and Urdu require cursive contextual glyph joining (isolated, initial, medial, final forms).
   - Arabic and Urdu text flows Right-to-Left (RTL), whereas standard `insert_text` only renders Left-to-Right (LTR).
   - Without bidirectional text reordering (Unicode Bidirectional Algorithm / FriBiDi / HarfBuzz), glyphs are reversed and unjoined.
3. **Current Safe Behavior:**
   - Text-layer PDFs containing non-Latin scripts display their text in the visual editor canvas but are marked **Read-Only** (`is_readonly = True`, badge, disabled toolbar actions, `spellcheck="false"`, excluded from fuzzy review queue).
   - On PDF export, original vector text streams for read-only blocks remain untouched to prevent corrupting the document.

---

## 2. Re-Enabling Checklist by Language Group

### A. Hindi (`hin`) & Gujarati (`guj`) - Indic Complex Script Shaping

- [ ] **1. Font Acquisition & System Deployment:**
  - [ ] Package or download full Unicode Noto fonts with complete OpenType tables (`GSUB`, `GPOS`):
    - `Noto Serif Devanagari` and `Noto Sans Devanagari`
    - `Noto Serif Gujarati` and `Noto Sans Gujarati`
  - [ ] Verify font metrics (ascender, descender, cap-height, line gap) in `docedit/font_catalog.py`.
- [ ] **2. Complex Script Text Shaping Architecture:**
  - [ ] Transition `docedit/writers.py` from `page.insert_text()` / `page.insert_textbox()` to **`page.insert_htmlbox()`** (available in PyMuPDF v1.22+).
  - [ ] Configure `insert_htmlbox` with CSS referencing the local TTF font file:
    ```html
    <style>
      @font-face {
        font-family: 'NotoSerifDevanagari';
        src: url('/path/to/NotoSerifDevanagari-Regular.ttf');
      }
      p {
        font-family: 'NotoSerifDevanagari';
        font-size: 12pt;
        line-height: 1.4;
      }
    </style>
    <p>सम्पादित हिन्दी पाठ</p>
    ```
  - [ ] Alternatively, integrate Python HarfBuzz bindings (`uharfbuzz`) to shape strings into positioned glyph IDs before calling `page.insert_font()` / glyph drawing.
- [ ] **3. Quality & Round-Trip Verification:**
  - [ ] Dedicated test documents:
    - `tests/test_docs/hindi_sample_textlayer.pdf`
    - `tests/test_docs/hindi_sample_scan.png`
    - `tests/test_docs/gujarati_sample_textlayer.pdf`
    - `tests/test_docs/gujarati_sample_scan.png`
  - [ ] OCR accuracy benchmark (Character Error Rate < 5% using `tessdata_best/hin.traineddata` and `tessdata_best/guj.traineddata`).
  - [ ] Export round-trip check: extract text from exported PDF using `pymupdf` and ensure extracted Unicode exactly matches input text with correct conjuncts and matra ordering.

---

### B. Arabic (`ara`) & Urdu (`urd`) - RTL & Cursive Shaping

- [ ] **1. Urdu Configuration Entry:**
  - [ ] Add `urd` entry in `docedit/conf.py` under `ALL_OCR_LANGUAGES`:
    ```python
    "urd": {
        "label": "Urdu",
        "family": "Noto Nastaliq Urdu",
        "tess_code": "urd",
        "direction": "rtl",
        "script": "arabic",
    }
    ```
  - [ ] Add `urd.traineddata` download mapping in `docedit/conf.py`.
- [ ] **2. Font Acquisition:**
  - [ ] Arabic: `Amiri` or `Noto Naskh Arabic` / `Noto Sans Arabic`.
  - [ ] Urdu: `Noto Nastaliq Urdu` (Nastaliq script requires complex vertical cascading metrics).
- [ ] **3. RTL Direction & Contextual Shaping:**
  - [ ] Use `insert_htmlbox` with `direction: rtl; text-align: right;` in HTML styling:
    ```html
    <div dir="rtl" style="direction: rtl; font-family: 'Amiri'; text-align: right;">
        نص عربي معدل
    </div>
    ```
  - [ ] Implement `python-bidi` / `arabic_reshaper` or HarfBuzz shaping to convert logical characters to contextual glyph presentation forms (`U+FE70–U+FEFF` / `U+FB50–U+FDFF`) if rendering without HTMLBox.
- [ ] **4. Quality & Round-Trip Verification:**
  - [ ] Dedicated test documents:
    - `tests/test_docs/arabic_sample_textlayer.pdf`
    - `tests/test_docs/arabic_sample_scan.png`
    - `tests/test_docs/urdu_sample_textlayer.pdf`
    - `tests/test_docs/urdu_sample_scan.png`
  - [ ] OCR accuracy benchmark (Character Error Rate < 5% on 300 DPI scans using `ara.traineddata` and `urd.traineddata`).
  - [ ] Export round-trip check: verify Right-to-Left visual ordering and joined cursive letterforms in Adobe Acrobat / PDF.js.

---

## 3. Configuration & UI Activation Steps

Once shaping and test verification are complete for a language:

1. **Enable in `docedit/conf.py`:**
   ```python
   # Add language code to enabled list:
   DOCEDIT_ENABLED_LANGUAGES = ["eng", "hin", "guj", "ara", "urd"]
   ```
2. **Expose in UI (`docedit/templates/docedit/docedit.html`):**
   - Populate language selector dropdown options dynamically from `OCR_LANGUAGES`.
3. **Update Security Validator (`docedit/security.py`):**
   - `validate_ocr_lang(lang_code, enabled_only=True)` will automatically allow the enabled language codes.
4. **Remove Read-Only Restriction in `docedit/extract.py`:**
   - Update `emit_paragraph` and scanned line extraction to only mark scripts read-only if their shaping engine is not yet active.
5. **Run Benchmark Management Command:**
   ```bash
   python manage.py ocr_benchmark --doc tests/test_docs/hindi_sample_scan.png --lang hin --profile grayscale_contrast
   ```
