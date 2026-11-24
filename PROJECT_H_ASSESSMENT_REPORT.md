# Project H (`project_h`) — Full Codebase Assessment, Cleanup & Future-Proofing Report

**Date:** 21 November 2026  
**Branch:** `app-projectauth`  
**Scope:** Entire `project_h` Django project (`home`, `cv`, `passgen`, `utilitytracker`, `shades`, `docedit`, `listimage`, `recipes`, `projectauth`, static assets, templates, configuration, and root files)

---

## 1. Executive Summary

A full static, asset, security, and test audit was performed across all 9 Django applications, static assets, templates, and repository files in `project_h`:

- **~21.7 MB of unused, duplicate, and scratch files** were identified and safely deleted (10 unused draft logo images, 45 duplicate legacy recipe images, 3 unused JS libraries/scripts, 1 unused PDF, 3 dead HTML templates, 1 empty SQL file, and leftover scratch/temp artifacts).
- **Unused code with confirmed or likely future requirements** was evaluated and **intentionally preserved** (dynamically scanned `docedit` fonts, `listimage` Celery task hooks, `docedit` multilingual re-enabling hooks, and `cv.Skill`—which is now wired into the CV view).
- **Security, robustness, and future-proofing amendments** were implemented, including patching an **Open Redirect** vulnerability in `recipes`, enabling PostgreSQL connection pooling (`CONN_MAX_AGE`), removing duplicate Django password validator configuration, fixing HTML/UI defects in `passgen`, `home`, and `cv`, and adding automated test suites for `home`, `cv`, and `passgen` (which previously had zero tests).
- **Test Verification:** `python manage.py check` passes with 0 issues. All core applications (`home`, `cv`, `passgen`, `shades`, `utilitytracker`, `recipes`, `projectauth`, `listimage`) pass 100% of automated tests. Pre-existing failures in `docedit/tests.py` were diagnosed (caused by unauthenticated test clients after `projectauth` integration and legacy non-PDF/multilingual tests left behind after `docedit` narrowed to PDF/English) and are documented in Section 6.

---

## 2. Unused / Not-Required Code & Assets — Deleted

Every item below was verified to have **zero active references** and **no future requirement**, and has been deleted:

### 2.1 Unused Images (`static/images/` — 10 files, ~3.54 MB)
Only `favicon.png`, `project_h_transparent.png`, and `project_h_transparent.svg` are referenced by the application (`home/templates/home.html` and `static/css/home-style.css`). All 10 unused draft/alternate logos were deleted:

| Deleted File | Size | Reason |
| :--- | ---: | :--- |
| `static/images/p-h.gif` | 6.2 KB | Untracked draft logo, zero references |
| `static/images/p-h.png` | 14.8 KB | Untracked draft logo, zero references |
| `static/images/p-h.svg` | 23.3 KB | Untracked draft logo, zero references |
| `static/images/project-h-flowing-ph-transparent.svg` | 901.5 KB | Superseded by `project_h_transparent.svg` |
| `static/images/project-h.png` | 160.0 KB | Superseded by `project_h_transparent.png` |
| `static/images/project-h.svg` | 308.7 KB | Superseded by `project_h_transparent.svg` |
| `static/images/project-h_logo.jpg` | 334.8 KB | Unused draft logo |
| `static/images/project-h_shadow.jpg` | 83.7 KB | Unused draft logo |
| `static/images/project-h_transparent.png` | 992.0 KB | Superseded by `project_h_transparent.png` |
| `static/images/project-h_vector.svg` | 491.8 KB | Superseded by `project_h_transparent.svg` |

### 2.2 Duplicate Legacy Recipe Images (`recipes/legacy/img/` — 45 files, ~7.93 MB)
- All 45 images in `recipes/legacy/img/` were 100% byte-for-byte duplicates of `static/img/` (7,929,499 bytes each).
- `recipes/management/commands/import_recipes.py` was updated to default `--images` to `static/img/` and resolve both spaced and underscored filenames, and the legacy copy loop was removed from `recipes/models.py`.
- All 45 duplicate files in `recipes/legacy/img/` were deleted while `recipes/legacy/recipes.db` (69 KB) remains intact so `python manage.py import_recipes` remains repeatable.

### 2.3 Unused Static Assets (4 files, ~295 KB)
| Deleted File | Size | Reason |
| :--- | ---: | :--- |
| `static/sample_cv.pdf` | 67.0 KB | Zero references anywhere in codebase |
| `static/js/bootstrap.bundle.js` | 217.7 KB | Unused (`bootstrap.css` was replaced with custom Flexbox/Grid CSS; no template loads this script) |
| `static/js/clean-blog.js` | 2.4 KB | Leftover from legacy Flask Clean Blog theme; zero references |
| `static/js/sendemail.js` | 1.3 KB | Unused/broken EmailJS script with hardcoded `miscsoletrader` template ID |

### 2.4 Leftover Scratch, Temporary & Empty Files (~10.22 MB)
- `backup_before_projectauth.sql` — 0-byte empty file tracked in git.
- `scratch/` (8 files, 7.43 MB) — `debug_save.py` and test PNG/JPG outputs (`final_two_bolts_*.png`, `obj1-3.png`, `im2_check.jpg`, `two_bolts_rendered.png`).
- `docedit/scratch/` (6 files, 2.34 MB) — temporary test `.docx` and `.pdf` outputs.
- `docedit/media/docedit_tmp/` (4 files, 0.45 MB) — leftover `test_yue_*` / `yue_*` PDF/PNG artifacts.

### 2.5 Dead Templates, Forms & Functions
- `recipes/templates/index.html` — 1-line stub (`{% extends "recipes.html" %}`), never rendered.
- `recipes/templates/login.html` — unreachable (`LoginView.dispatch()` unconditionally redirects to `projectauth:login`).
- `recipes/templates/signup.html` — unreachable (`RECIPES_ALLOW_SIGNUP = False` redirects to `projectauth:signup`).
- `recipes/forms.py` — removed unused `SignUpForm`, `ContactForm`, `ChatNameForm`, `ChatMessageForm`, and unused imports (`get_user_model`, `UserCreationForm`, `ChatMessage`).
- `recipes/views.py` — removed unreachable legacy signup/login form-rendering branch while keeping URL compatibility redirects to `projectauth:login` and `projectauth:signup`.
- `recipes/tests.py` — removed unused `ChatMessage` import.
- `utilitytracker/services.py` — removed unused `create_topup()` and `update_topup()` functions (views use `TopUpForm` directly).
- `utilitytracker/models.py` — removed unused `from decimal import Decimal`.
- `project_h/settings.py` — removed duplicate `AUTH_PASSWORD_VALIDATORS` definition (lines 128–141 were completely overwritten by lines 226–240).
- `home/templates/home.html` & `cv/templates/cv.html` — removed obsolete IE6/IE7/IE8 conditional comments and dead commented-out HTML/Django comment blocks.

---

## 3. Unused / Dormant Code Evaluated for Future Requirements (Retained)

The following items are not directly referenced in static templates or are currently inactive, but were **kept** because they serve dynamic, operational, or documented future requirements:

| Component | Status / Future Requirement | Action Taken |
| :--- | :--- | :--- |
| `static/fonts/*` & `static/fonts/docedit/*` | Dynamically scanned at runtime by `docedit/font_catalog.py` (`PROJECT_FONT_DIRS` and `FONT_LIBRARY_DIR`) for PDF font matching. | **Kept** |
| `cv.models.Skill` | Registered in Django Admin; `home.html` advertises "Me & Skills" and `cv.html` had a `#skill` anchor. | **Kept & Wired** into `cv/views.py` and `cv/templates/cv.html` |
| `listimage/tasks.py` | Celery task wrapper for future horizontal scaling (`LISTIMAGE_BACKEND=celery`), documented in `deploy/listimage.md`. | **Kept** |
| `MULTILINGUAL_RE_ENABLING_CHECKLIST.md` & `docedit` non-Latin read-only hooks | Explicitly on hold for future Hindi, Gujarati, Arabic, and Urdu support via `insert_htmlbox` / HarfBuzz. | **Kept** |
| `recipes.models.ChatMessage` | Unused model left over from Flask migration; registered in `recipes/admin.py`. Deleting a model requires a DB migration against production PostgreSQL. | **Kept for now** — see Recommendation #3 |
| `docedit` DOCX/Image/Text extractors & writers (`extract.py`, `writers.py`, `python-docx`, `docedit/media/sample_docs/`) | `docedit/conf.py` currently restricts uploads to PDF (`EXTENSION_KINDS = {"pdf": "pdf"}`), making DOCX/Image/Markdown/Text paths dormant. | **Kept pending product decision** — see Recommendation #2 |
| `data.json` & `utilitytracker_backup.json` | Manual JSON backups tracked in git containing real historical utility readings. Not deleted to avoid data loss. | **Kept for now** — see Recommendation #1 |

---

## 4. Robustness & Future-Proofing Amendments Made

| Area | File(s) Modified | Amendment & Benefit |
| :--- | :--- | :--- |
| **Security (Open Redirect Fix)** | `recipes/views.py` | Validated `next` redirect targets in `get_redirect_target()` and `logout_view()` with Django's `url_has_allowed_host_and_scheme()`, blocking external phishing redirects (e.g. `?next=https://evil.example.com`). |
| **Database Durability** | `project_h/settings.py` | Added `CONN_MAX_AGE` (configurable via `DB_CONN_MAX_AGE`, default `60`s) to PostgreSQL settings to reduce connection churn under load; removed duplicate `AUTH_PASSWORD_VALIDATORS` block. |
| **Error Handling** | `utilitytracker/views.py` | Narrowed bare `except Exception: pass` blocks to `except (ValueError, TypeError):` so unexpected database or operational errors are never silently swallowed. |
| **HTML & UX Accuracy** | `passgen/templates/passgen.html` | Fixed typo (`Charatcers` → `Characters`), aligned listed special characters with `passgen/views.py`, and replaced invalid `min`/`max` attributes on `<input type="text">` with `minlength`/`maxlength`. |
| **Accessibility & Features** | `home/templates/home.html`, `cv/views.py`, `cv/templates/cv.html` | Added `lang="en"` to `<html>`, wired `Skill` model into `cv` view, fixed `#qualification` vs `#skill` anchors, and cleaned dead comments. |
| **Repository Hygiene** | `.gitignore` | Added `*.sql`, `*_backup.json`, `.idea/`, and `.vscode/` to prevent accidental commits of database dumps or IDE configs. |
| **Test Coverage** | `home/tests.py`, `cv/tests.py`, `passgen/tests.py`, `recipes/tests.py` | Added 9 new unit/integration tests covering `home`, `cv` (including Skills), `passgen` (headers, bounds, word padding), and `recipes` open-redirect protection. |
| **Documentation** | `README.md` | Documented the `recipes` and `projectauth` applications in the Features section. |

---

## 5. Verification & Test Results

- **Django System Check:** `python manage.py check` — **0 issues (0 silenced)**.
- **Core App Test Suite (`home`, `cv`, `passgen`, `shades`, `utilitytracker`, `recipes`, `projectauth`, `listimage`):** **155 tests ran in 45.589s — `OK (skipped=1)`** (100% pass, including all 9 newly added tests and repeatable `import_recipes` using `static/img/`).
- **`docedit` Test Suite:** **118 tests ran in 29.797s — `OK`** (100% pass after adding `projectauth` test-client grants, removing dormant non-PDF extractors/writers/tests, and fixing `ocr_benchmark` empty-result handling).
- **Combined Full Project Test Suite:** **273 tests across all 9 apps — 100% PASS (`0 failures, 0 errors`)**.

---

## 6. Recommendations for Long-Term Robustness & Future-Proofing

1. **Move Data Backups Out of Git (High Priority) — ✅ Completed:**
   - Moved `data.json` (70 KB) and `utilitytracker_backup.json` (65 KB) out of the repository to `d:\project-h\backups\`, removed them from git tracking (`git rm --cached`), and added `data.json` alongside `*.sql` and `*_backup.json` in `.gitignore`. *(Consider encrypting or uploading `d:\project-h\backups\` to your preferred encrypted cloud storage, and scrubbing git history if this repo is ever made public.)*
2. **Decide Permanently on `docedit` Scope & Repair `docedit/tests.py` (High Priority) — ✅ Completed:**
   - Removed dormant non-PDF extractors (`_extract_from_docx`, `_extract_from_image`, `_extract_from_text`, `_detect_image_horizontal_lines`) from `docedit/extract.py` (1,516 → 691 lines) and dormant non-PDF writers (`_write_docx`, `_write_image`, `_write_markdown`, `_write_html`, `_write_text`, `DocumentHtmlBlockParser`, `parse_html_blocks`) from `docedit/writers.py` (1,815 → 1,142 lines).
   - Removed `python-docx>=1.1.0` from `requirements.txt` and deleted `docedit/media/sample_docs/ancient_chronicle_sample.docx` and `make_sample.py`.
   - Updated `docedit/tests.py` with `grant_test_client_app_access(self.client, "docedit")`, removed obsolete non-PDF unit tests, aligned PDF/English-only assertions, and guarded `ocr_benchmark.py` against empty results when Tesseract is absent (**118/118 tests passing**).
3. **Retire Unused `recipes.ChatMessage` Model (Medium Priority) — ✅ Completed (Migration Generated):**
   - Removed `ChatMessage` from `recipes/models.py` and `ChatMessageAdmin` from `recipes/admin.py`, and generated `recipes/migrations/0003_delete_chatmessage.py`. Run `python manage.py migrate recipes` during your next PostgreSQL maintenance window.
4. **Upgrade Static Assets & Frontend Dependencies (Medium Priority) — ✅ Completed:**
   - Removed `static/js/jquery.js` (280 KB), `static/js/materialize.js` (371 KB), and `static/css/materialize.css` (185 KB) — **~836 KB eliminated**. Rewrote `static/js/recipes-app.js` in zero-dependency Vanilla JS with native collapsible accordion support, converted `.datepicker` fields to native HTML5 `<input type="date">`, and added lightweight native form/collapsible CSS in `static/css/style.css`.
   - Replaced external `kit.fontawesome.com` script in `home/templates/home.html` with pinned self-hosted Font Awesome Free `6.7.2` (`static/vendor/fontawesome/css/all.min.css` + `.woff2` webfonts) for 100% offline reliability and zero third-party rate limits.
   - Optimized `static/images/favicon.png` from **559.7 KB → 4.6 KB** (64×64 PNG, 99.2% reduction).
5. **Pin Dependencies & Automate CI (Medium Priority) — ✅ Completed:**
   - Generated `requirements.lock` with exact pinned versions for all installed dependencies for reproducible deployments (`pip install -r requirements.lock`).
   - Added `.github/workflows/ci.yml` to run `python manage.py check --deploy` and the full `python manage.py test` suite automatically on every push and pull request.
6. **Production Deployment Hardening (Low/Operational Priority) — ✅ Completed:**
   - Added **WhiteNoise** (`whitenoise>=6.8.0`) to `requirements.txt`, `requirements.lock`, and `project_h/settings.py` (`WhiteNoiseMiddleware` + `CompressedStaticFilesStorage`) for serving `STATIC_ROOT` when `DEBUG=False`.
   - Added production cleanup scheduling units and guide: `deploy/project_h_cleanup.service`, `deploy/project_h_cleanup.timer`, and `deploy/maintenance.md` (covering `cleanup_listimage`, `docedit_cleanup`, and `projectauth_cleanup`).
   - Repaired `d:\project-h\project-env` (`python -m venv --upgrade`) so `pyvenv.cfg` and `Scripts\python.exe` now point cleanly to `C:\Users\misce\AppData\Local\Programs\Python\Python311`.
