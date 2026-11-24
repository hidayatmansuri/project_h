# Deploying `project_h` (Full Django + PostgreSQL Stack)

`project_h` ships with a production `Dockerfile`, `render.yaml`, and `docker-compose.yml` so you can deploy to **Render**, **Railway**, or any **Linux VPS** in minutes.

---

## Option A: Render (Easiest Managed Hosting)

1. Sign in at [render.com](https://render.com) with your GitHub account.
2. Click **New → Blueprint**, select **`hidayatmansuri/project_h`**, and Render will read [`render.yaml`](../render.yaml) automatically.
3. Fill in the 4 prompted environment variables:
   - `ALLOWED_HOSTS`: `project-h.onrender.com` (or your custom domain)
   - `CSRF_TRUSTED_ORIGINS`: `https://project-h.onrender.com`
   - `PROJECTAUTH_BASE_URL`: `https://project-h.onrender.com`
   - `PROJECTAUTH_ENCRYPTION_KEYS`: generate once locally:
     ```powershell
     python -c "import secrets,base64; print('kid1:' + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
     ```
4. Click **Apply** — Render builds the Docker image, runs `migrate` + `projectauth_sync_apps`, and starts Gunicorn automatically.
5. Open the Render **Shell** tab once after deploy to create your admin user:
   ```bash
   python manage.py projectauth_init_admin --username=admin --email=you@example.com --password="YourStrongPassword!123"
   ```

> **RAM Note:** `listimage` loads ONNX models (`rembg`, ~250–500 MB per worker). Render's **Standard (2 GB RAM)** plan is recommended if using `listimage` heavily; if you only need CV/Utility/Recipes/DocEdit, the Starter (512 MB) plan with `GUNICORN_WORKERS=1` works.

---

## Option B: Railway (Docker + Managed PostgreSQL)

1. Sign in at [railway.app](https://railway.app) → **New Project → Deploy from GitHub Repo** (`hidayatmansuri/project_h`).
2. Railway auto-detects [`Dockerfile`](../Dockerfile).
3. Click **+ New → Database → Add PostgreSQL** and link `DATABASE_URL` to the web service.
4. Add a **Volume** mounted at `/app/media` for recipe photos.
5. Set the same environment variables (`DJANGO_DEBUG=False`, `SECURE_PROXY_SSL=True`, `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `PROJECTAUTH_BASE_URL`, `PROJECTAUTH_ENCRYPTION_KEYS`).
6. Run `python manage.py projectauth_init_admin ...` once via Railway Shell.

---

## Option C: Ubuntu VPS (Best Value for `listimage` ONNX RAM — ~$4–6/mo)

On any 2–4 GB Ubuntu VPS (Hetzner / DigitalOcean / Linode) with Docker installed:

```bash
git clone https://github.com/hidayatmansuri/project_h.git
cd project_h
cp .env.example .env
# Edit .env with production SECRET_KEY, DB_PASSWORD, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, PROJECTAUTH_ENCRYPTION_KEYS
docker compose up -d --build
docker compose exec web python manage.py projectauth_init_admin --username=admin --email=you@example.com --password="YourStrongPassword!123"
```

Put **Caddy** or **Nginx** in front of `127.0.0.1:8000` for automatic HTTPS (Let's Encrypt) and `/media/` serving (see [`deploy/maintenance.md`](./maintenance.md) and [`deploy/listimage.md`](./listimage.md)).
