# AGENTS.md — Engineering Invariants for `project-h`

This repository is a multi-app Django 5.2 + PostgreSQL 18 web platform (`home`, `cv`, `passgen`, `utilitytracker`, `shades`, `docedit`, `listimage`, `recipes`, `projectauth`). Follow every invariant below when reading, modifying, or testing this codebase.

---

## 1. Python Environment, Database & Testing

- **Virtual environment (Windows):** Always invoke the project venv interpreter directly:
  ```powershell
  D:\project-h\project-env\Scripts\python.exe manage.py check
  D:\project-h\project-env\Scripts\python.exe manage.py test --verbosity=1
  ```
- **Windows `listimage` tests:** Set `NUMBA_DISABLE_JIT=1` in the environment before running `listimage` tests on Windows (prevents Numba/LLVM JIT crashes under `rembg`/`pymatting`):
  ```powershell
  $env:NUMBA_DISABLE_JIT = "1"
  D:\project-h\project-env\Scripts\python.exe manage.py test listimage --verbosity=1
  ```
- **Database architecture:**
  - **Runtime:** Unified PostgreSQL 18 database (`projecthdb`, configured via `.env`, `CONN_MAX_AGE=60`, `connect_timeout=5`). Do **not** split runtime apps across multiple DB engines.
  - **Local offline fallback:** Optional `USE_SQLITE=True` env toggle uses `db.sqlite3`.
  - **Automated tests:** `project_h/settings.py` automatically switches `DATABASES['default']` to in-memory SQLite (`:memory:`) when `'test' in sys.argv`.
- **Dependencies:** Keep `requirements.txt` and pinned `requirements.lock` in sync.

---

## 2. `projectauth` Default-Deny Architecture

- **Centralised middleware enforcement:** Access control is enforced globally by `projectauth.middleware.ProjectAuthMiddleware` (alongside `IdleTimeoutMiddleware` and `AxesMiddleware`).
- **No per-view login decorators:** Do **not** add `@login_required` or bespoke per-app auth views/decorators unless explicitly required for an extraordinary edge case. `recipes` legacy `/login/` and `/signup/` routes remain simple redirects to `projectauth:login` and `projectauth:signup`.
- **Public apps allowlist:** `PROJECTAUTH_PUBLIC_APPS = ['home', 'cv']` in `project_h/settings.py`. Every other local app defaults to **deny** until a user has an active `AppAccess` grant (`full` or `read_only`, optional expiry).
- **Mandatory post-change commands:** Whenever you add, rename, or modify apps or URL patterns, run both:
  ```powershell
  D:\project-h\project-env\Scripts\python.exe manage.py projectauth_sync_apps
  D:\project-h\project-env\Scripts\python.exe manage.py projectauth_check
  ```
- **Testing protected apps:** In Django `TestCase` classes that call protected views/APIs, authenticate the test client using:
  ```python
  from projectauth.test_helpers import grant_test_client_app_access
  grant_test_client_app_access(self.client, "<app_label>")
  ```

---

## 3. Data Ownership & App Scope Invariants

- **Decision D3 (`utilitytracker`):** `UtilityReading` and `TopUp` remain a **shared household dataset with NO `owner` column**. Do not add user ownership FKs to `utilitytracker` models; read-only vs full write permissions are enforced by `projectauth` (`read_only` grants return HTTP 403 on POST mutations).
- **`docedit` scope:** Permanently **PDF-only** (`EXTENSION_KINDS = {'pdf': 'pdf'}`) and currently **English-only** (`DOCEDIT_ENABLED_LANGUAGES = ['eng']`). Keep non-Latin read-only guards intact; do not re-enable non-Latin OCR/export until the prerequisites in `MULTILINGUAL_RE_ENABLING_CHECKLIST.md` are satisfied.
- **Static vs Media image split:**
  - `static/images/` holds **immutable** site branding and static UI fallbacks (tracked in Git, served by WhiteNoise `CompressedStaticFilesStorage`).
  - `media/recipes/library/` holds **dynamic** user-uploaded recipe photos (gitignored, managed via `RecipeImage.image` with `post_delete` disk cleanup). Never move uploaded media into `static/`.

---

## 4. UI, Typography & CSS Rules

- **Base template:** Every app template must extend `home.html` and inject assets via `{% block extra_css %}`, `{% block content %}`, and `{% block script %}`.
- **Theme tokens:** Use the CSS variables defined under `html.light` and `html.dark` in `static/css/home-style.css` (`--bg-color`, `--text-color`, `--button-color`, `--hover-color`, `--warning-color`, `--box-shadow`). Never hardcode light-only or dark-only backgrounds/text colors that break theme toggling.
- **Mobile-first breakpoints ONLY (Constraint C6):** Use `min-width: 768px` (medium/tablet) and `min-width: 1200px` (large/desktop). **Never write `max-width` media queries** in `home-style.css`, `projectauth.css`, or new app stylesheets (enforced by `projectauth.tests.test_phase6_ui`).
- **Fonts & frontend stack:** Keep `Peignot` for the global navbar; use `Gotu` for app content (such as `cv`). Use self-hosted Font Awesome 6.7.2 (`static/vendor/fontawesome/css/all.min.css`) and Vanilla JS — do not reintroduce jQuery, Materialize, or external Font Awesome kit scripts.

---

## 5. Security & Repository Hygiene

- **Clickjacking:** `X_FRAME_OPTIONS = 'DENY'` is the global default. Only apply targeted `@xframe_options_sameorigin` when a view must be embedded in a same-origin `<object>` (e.g., `listimage/svg_views.py` SVG preview).
- **HTML sanitization:** Always sanitize user-supplied or extracted HTML through `nh3` with its pure-Python fallback (`docedit/security.py:sanitize_document_html`).
- **Safe redirects & sensitive responses:** Validate every `next` redirect parameter with `django.utils.http.url_has_allowed_host_and_scheme()`. Keep `Cache-Control: no-store` on sensitive endpoints (e.g., `passgen`).
- **Never commit secrets or scratch/backup files:** Never stage or commit `.env`, `*.sql`, `*_backup.json`, `data.json`, `*.sqlite3`, `*.log`, `scratch/`, `docedit/media/docedit_tmp/`, `listimage/workspace/`, `media/`, or `staticfiles/`.
