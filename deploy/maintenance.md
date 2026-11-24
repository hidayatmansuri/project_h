# Production Static Files & Scheduled Cleanup Guide

## 1. Static Files in Production (WhiteNoise)

`project_h` is configured with **WhiteNoise** (`whitenoise.middleware.WhiteNoiseMiddleware` + `CompressedStaticFilesStorage`) in `project_h/settings.py`, so `STATIC_ROOT` (`staticfiles/`) is served efficiently with gzip/brotli compression and cache headers even when `DJANGO_DEBUG=False`.

Before starting or reloading the production WSGI/ASGI server, run:

```bash
python manage.py collectstatic --noinput
```

---

## 2. Scheduled Workspace & Auth Cleanup

Three management commands keep temporary workspaces and expired auth records clean:

1. `python manage.py cleanup_listimage --max-age-minutes=60` — purges stale `listimage/workspace/` job directories and expired DB rows.
2. `python manage.py docedit_cleanup` — purges expired `docedit/media/docedit_tmp/` sessions.
3. `python manage.py projectauth_cleanup` — removes expired 2FA challenges, pending email changes, invites, trusted devices, and stale session records.

### Option A: Linux `systemd` Timer (Recommended)

Copy the bundled unit files in `deploy/` and adjust `WorkingDirectory`, `User`, and virtualenv paths as needed:

```bash
sudo cp deploy/project_h_cleanup.service /etc/systemd/system/
sudo cp deploy/project_h_cleanup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now project_h_cleanup.timer
sudo systemctl list-timers --all | grep project_h_cleanup
```

### Option B: Linux `cron`

Add to `crontab -e`:

```cron
*/30 * * * * cd /srv/project_h && /srv/project-env/bin/python manage.py cleanup_listimage --max-age-minutes=60 && /srv/project-env/bin/python manage.py docedit_cleanup && /srv/project-env/bin/python manage.py projectauth_cleanup >> /var/log/project_h_cleanup.log 2>&1
```

### Option C: Windows Task Scheduler (PowerShell)

Run once in an elevated PowerShell prompt to register a 30-minute recurring task:

```powershell
$action = New-ScheduledTaskAction -Execute "d:\project-h\project-env\Scripts\python.exe" `
  -Argument "manage.py cleanup_listimage --max-age-minutes=60" `
  -WorkingDirectory "d:\project-h\project_h"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName "ProjectH-Cleanup" -Action $action -Trigger $trigger -Description "Periodic cleanup for project_h workspaces"
```

---

## 3. Serving Uploaded Media (`media/recipes/library/`) in Production

Uploaded recipe photos live in `MEDIA_ROOT` (`media/recipes/library/`), separated from immutable static assets in `static/images/`. In local development (`DJANGO_DEBUG=True`), Django serves `/media/` automatically. In production (`DJANGO_DEBUG=False`), serve `/media/` directly from your reverse proxy:

```nginx
location /media/ {
    alias /srv/project_h/media/;
    expires 7d;
    add_header Cache-Control "public";
}
```
