---
name: project-h-new-app
description: >-
  Guides the creation and integration of a new Django application inside project-h.
  Use this skill when the user asks to add, scaffold, or wire a new app or tool
  into project-h, ensuring proper projectauth default-deny registration, namespaced
  URLs, home.html navigation integration, architecture modules, and baseline tests.
---

# Adding a New Django App to `project-h`

Follow this ordered playbook whenever creating a new local Django app (`<app_name>`) in `project-h`. For copy-paste templates, see [references/scaffolding-templates.md](./references/scaffolding-templates.md).

## 1. Scaffold & Structure the App
1. Create the app from `d:\project-h\project_h`:
   ```powershell
   D:\project-h\project-env\Scripts\python.exe manage.py startapp <app_name>
   ```
2. Follow `project-h` layered module conventions when the app grows beyond a single view:
   - `services.py` — write operations, mutations, and business workflows (see `utilitytracker/services.py`).
   - `selectors.py` — read queries, aggregations, and view payloads (see `utilitytracker/selectors.py`).
   - `conf.py` — lazy `override_settings`-friendly app settings via `getattr(settings, "<APP>_...", default)` (see `docedit/conf.py`).

## 2. Configure `AppConfig` with `projectauth_*` Metadata
In `<app_name>/apps.py`, set `default_auto_field = "django.db.models.BigAutoField"` and define the `projectauth_*` attributes read automatically by `projectauth.registry.sync_protected_apps`:
- `projectauth_label` (display name)
- `projectauth_description` (short summary shown in Admin Console)
- `projectauth_icon` (self-hosted Font Awesome 6 class, e.g. `"fa-solid fa-cube"`)
- `projectauth_home_url_name` (namespaced URL name, e.g. `"<app_name>:index"`)
- `projectauth_sort_order` (integer order, e.g. `70`)

## 3. Wire Namespaced URLs & Register in `INSTALLED_APPS`
1. Create `<app_name>/urls.py` with `app_name = "<app_name>"` and a root `index` route.
2. Include it in `project_h/urls.py`:
   ```python
   path('<app_name>/', include('<app_name>.urls', namespace='<app_name>')),
   ```
3. Add `'<app_name>.apps.<AppName>Config'` to `INSTALLED_APPS` in `project_h/settings.py` **before** `'projectauth.apps.ProjectAuthConfig'`.
4. **Do NOT add `@login_required` decorators** — `ProjectAuthMiddleware` enforces default-deny automatically. Only add `<app_name>` to `PROJECTAUTH_PUBLIC_APPS` in `project_h/settings.py` if the user explicitly requests public anonymous access.

## 4. Integrate UI into `home/templates/home.html`
1. Create `<app_name>/templates/<app_name>/index.html` extending `home.html` (see `project-h-theme-ui` skill for theme tokens, typography, and mobile-first CSS rules).
2. Add a navigation entry inside `.dropdown-menu` under **Tools** in `home/templates/home.html`.
3. Add a `.ph-card.floating-card` tile inside `.welcome-cards` in `home/templates/home.html`.

## 5. Migrations, Registry Sync & Baseline Tests
1. Create and apply migrations (if the app defines models):
   ```powershell
   D:\project-h\project-env\Scripts\python.exe manage.py makemigrations <app_name>
   D:\project-h\project-env\Scripts\python.exe manage.py migrate
   ```
2. Register the app in `projectauth` and verify every route is classified:
   ```powershell
   D:\project-h\project-env\Scripts\python.exe manage.py projectauth_sync_apps
   D:\project-h\project-env\Scripts\python.exe manage.py projectauth_check
   ```
3. Write baseline tests in `<app_name>/tests.py` covering:
   - Anonymous visitor blocked (302 to `/auth/login/` for HTML, 401 for JSON/API).
   - Authenticated user with `grant_test_client_app_access(self.client, "<app_name>")` receives HTTP 200 and renders `home.html`.
   - `read_only` grant blocks POST mutations with HTTP 403 (if the app has mutations).

## Verification
Run all three checks and confirm 0 issues and 100% passing tests:
```powershell
D:\project-h\project-env\Scripts\python.exe manage.py check
D:\project-h\project-env\Scripts\python.exe manage.py projectauth_check
D:\project-h\project-env\Scripts\python.exe manage.py test <app_name> projectauth.tests.test_phase4_access projectauth.tests.test_phase6_ui --verbosity=1
```
