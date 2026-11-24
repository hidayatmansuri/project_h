# Production Deployment & Incident Recovery Reference

## 1. Pre-Download `rembg` ONNX Models
Run during server provisioning or CI image builds (saved by `pooch` into `~/.u2net/`):
```bash
python -c "from rembg import new_session; [new_session(m) for m in ['isnet-general-use', 'birefnet-general', 'u2netp']]; print('Models pre-downloaded!')"
```

## 2. Gunicorn Configuration
Each worker loads its own ONNX/rembg session (~250–500 MB RAM/worker; size at least 3–4 GB RAM for 3–4 workers):
```bash
gunicorn project_h.wsgi:application \
    --bind 127.0.0.1:8000 \
    --workers 3 \
    --timeout 120 \
    --max-requests 500 \
    --max-requests-jitter 50 \
    --access-logfile /var/log/gunicorn/access.log \
    --error-logfile /var/log/gunicorn/error.log
```

## 3. Nginx Reverse Proxy Configuration
Static files are served by WhiteNoise (`CompressedStaticFilesStorage`); serve `/media/` directly from `MEDIA_ROOT` and allow 25 MB uploads + 120s inference timeouts:
```nginx
server {
    listen 80;
    server_name yourdomain.com;
    client_max_body_size 25M;

    location /media/ {
        alias /srv/project_h/media/;
        expires 7d;
        add_header Cache-Control "public";
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 120s;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }
}
```

## 4. Scheduled Cleanup (`systemd` / `cron`)
Ready-to-deploy systemd unit files live in `deploy/project_h_cleanup.service` and `deploy/project_h_cleanup.timer`:
```bash
sudo cp deploy/project_h_cleanup.service deploy/project_h_cleanup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now project_h_cleanup.timer
```

## 5. `projectauth` Recovery Playbooks
- **Locked-out sole admin:**
  ```powershell
  python manage.py projectauth_init_admin --username=admin --password="TemporaryNewPassword!123" --reset-2fa
  ```
- **Zero-downtime encryption key rotation:**
  1. Generate key: `python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"`
  2. Prepend to `PROJECTAUTH_ENCRYPTION_KEYS` in `.env`: `kid2:<new>,kid1:<old>`.
  3. Run `python manage.py projectauth_rotate_keys` and verify `skipped_count = 0`.
  4. Remove `kid1` from `.env`.
- **PostgreSQL 18 off-repo backup (Windows):**
  ```powershell
  & "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" -U postgres -F c -f "d:\project-h\backups\projecthdb_$(Get-Date -Format yyyyMMdd).dump" projecthdb
  ```
