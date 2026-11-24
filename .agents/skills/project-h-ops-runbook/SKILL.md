---
name: project-h-ops-runbook
description: >-
  Operational runbook for testing, maintaining, securing, and deploying project-h.
  Use this skill when running Windows tests (especially listimage with NUMBA_DISABLE_JIT=1),
  executing projectauth_* CLI commands, running workspace cleanups, or configuring
  production Gunicorn, Nginx, WhiteNoise, and rembg model pre-downloads.
---

# `project-h` Operations & Deployment Runbook

Use `D:\project-h\project-env\Scripts\python.exe` on Windows for all `manage.py` commands. For full production Gunicorn/Nginx configs and incident recovery playbooks, see [references/production-deploy.md](./references/production-deploy.md).

## 1. Running Tests on Windows
1. **Standard test suite** (automatically uses in-memory SQLite `:memory:`):
   ```powershell
   D:\project-h\project-env\Scripts\python.exe manage.py check
   D:\project-h\project-env\Scripts\python.exe manage.py test home cv passgen shades utilitytracker recipes projectauth docedit --verbosity=1
   ```
2. **`listimage` tests on Windows** (MUST disable Numba JIT to prevent LLVM crashes in `rembg`/`pymatting`):
   ```powershell
   $env:NUMBA_DISABLE_JIT = "1"
   D:\project-h\project-env\Scripts\python.exe manage.py test listimage --verbosity=1
   ```
3. **Production deployment check:**
   ```powershell
   $env:DJANGO_DEBUG = "False"
   $env:SECRET_KEY = "ephemeral-check-key-at-least-fifty-characters-long-0123456789"
   $env:ALLOWED_HOSTS = "example.com"
   D:\project-h\project-env\Scripts\python.exe manage.py check --deploy
   ```

## 2. `projectauth_*` Management Commands
| Command | Purpose |
| :--- | :--- |
| `manage.py projectauth_sync_apps` | Syncs local `INSTALLED_APPS` into `ProtectedApp` registry (run after adding/renaming apps). |
| `manage.py projectauth_check` | Audits every URL route as `public`, `protected`, or `unclassified` (exits non-zero if unclassified). |
| `manage.py projectauth_init_admin --username=<u> --email=<e> --password=<p>` | Bootstraps/promotes an admin or resets 2FA (`--reset-2fa`). |
| `manage.py projectauth_rotate_keys` | Re-encrypts stored AES-256-GCM secrets to the active primary key in `PROJECTAUTH_ENCRYPTION_KEYS`. |
| `manage.py projectauth_purge_audit --older-than-days=365` | Purges old audit log entries. |
| `manage.py projectauth_cleanup` | Prunes expired 2FA challenges, email tokens, invites, trusted devices, and stale sessions. |
| `manage.py projectauth_email_test <email>` | Verifies SMTP configuration and daily email budget guard. |

## 3. Workspace & Storage Cleanup Commands
Run periodically (every 30 minutes via `deploy/project_h_cleanup.timer` or cron):
```powershell
D:\project-h\project-env\Scripts\python.exe manage.py cleanup_listimage --max-age-minutes=60
D:\project-h\project-env\Scripts\python.exe manage.py docedit_cleanup
D:\project-h\project-env\Scripts\python.exe manage.py projectauth_cleanup
```
Use `--dry-run` with `cleanup_listimage` to preview before deleting.

## 4. Production Deployment Essentials
1. Install locked dependencies: `pip install -r requirements.lock`.
2. Collect WhiteNoise static files: `python manage.py collectstatic --noinput`.
3. Pre-download `rembg` ONNX models (`isnet-general-use`, `birefnet-general`, `u2netp`) before starting Gunicorn so first requests have zero cold-start delay (exact command in [references/production-deploy.md](./references/production-deploy.md)).
4. Configure Gunicorn (`--timeout 120 --max-requests 500 --max-requests-jitter 50`) and Nginx (`client_max_body_size 25M`, `proxy_read_timeout 120s`, `/media/` alias).

## Verification
```powershell
$env:NUMBA_DISABLE_JIT = "1"
D:\project-h\project-env\Scripts\python.exe manage.py check
D:\project-h\project-env\Scripts\python.exe manage.py projectauth_check
D:\project-h\project-env\Scripts\python.exe manage.py cleanup_listimage --dry-run
```
