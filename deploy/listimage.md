# ListImage Production Deployment & Operations Guide

## 1. Overview
`listimage` isolates foreground objects, removes backgrounds with neural networks (rembg / ONNX), centers the object on an exact $2000 \times 2000$ pure white canvas with exact 10 px padding on the constraining side, supports non-destructive editing (brush, wand, auto touch-up, object filtering), and deletes all temporary session files immediately upon download.

---

## 2. Nginx Configuration
Ensure `client_max_body_size` is at least `25M` to support large high-resolution images, and configure `proxy_read_timeout` to `120s`.

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    # Support high-resolution product photography up to 25 MB
    client_max_body_size 25M;

    location /static/ {
        alias /path/to/project_h/static/;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Keep proxy timeout aligned with long neural network inferences
        proxy_connect_timeout 120s;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }
}
```

---

## 3. Gunicorn Configuration
- **Timeout**: Set `--timeout 120` so model inference on huge images does not cause worker resets.
- **Worker count & RAM Sizing**:
  > [!IMPORTANT]
  > Each Gunicorn worker process loads its own copy of ONNX/rembg model sessions into memory (~250 MB – 500 MB per active worker).
  > For 4 workers, ensure your server has at least **3 GB – 4 GB RAM** available.
- **Worker Recycling**: Use `--max-requests 500 --max-requests-jitter 50` to automatically recycle workers and prevent gradual Python/C++ memory fragmentation.

Example command:
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

---

## 4. Pre-downloading Rembg Models
During automated CI/CD or server provisioning, run the pre-download script so the first user does not experience a cold-start delay:

```bash
python -c "from rembg import new_session; [new_session(m) for m in ['isnet-general-use', 'birefnet-general', 'u2netp']]; print('Models pre-downloaded!')"
```

Models are saved by `pooch` into `~/.u2net/`.

---

## 5. Automated Workspace Cleanup (Cron)
ListImage automatically deletes job directories and database rows when users download their file. To prune abandoned sessions or orphaned files older than `LISTIMAGE_MAX_AGE_MINUTES` (default 60 minutes), configure a cron job:

```cron
# Run ListImage cleanup every 15 minutes with file-lock protection
*/15 * * * * /path/to/venv/bin/python /path/to/project_h/manage.py cleanup_listimage >> /var/log/listimage_cleanup.log 2>&1
```

Testing manually:
```bash
python manage.py cleanup_listimage --dry-run
python manage.py cleanup_listimage --max-age-minutes 30
```

---

## 6. Celery & Redis Setup (Optional)
By default, ListImage operates with zero external infrastructure using Django's built-in `ThreadPoolExecutor` bounded by `LISTIMAGE_MAX_CONCURRENT_JOBS = 2`.

To switch to a distributed Celery queue:
1. In `.env`:
   ```env
   LISTIMAGE_BACKEND=celery
   CELERY_BROKER_URL=redis://127.0.0.1:6379/0
   ```
2. Start the Celery worker:
   ```bash
   celery -A project_h worker -l info --concurrency=2
   ```

---

## 7. Model Licensing & Commercial Use
- **IS-Net (`isnet-general-use`)**: Apache-2.0 license (commercial use allowed).
- **BiRefNet (`birefnet-general`)**: MIT / Apache-2.0 derivative.
- **U2Net / U2Netp**: Apache-2.0.
Always verify upstream checkpoints before deploying in specialized proprietary or resold SaaS environments.
