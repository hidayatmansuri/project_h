FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System dependencies for Tesseract OCR, OpenCV/Pillow, and cross-platform fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    fonts-dejavu-core \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy project source
COPY . /app/

# Create runtime directories and non-root user
RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/staticfiles /app/media/recipes/library /app/listimage/workspace /app/docedit/media/docedit_tmp \
    && chmod +x /app/deploy/entrypoint.sh \
    && chown -R appuser:appuser /app

USER appuser

# Pre-collect WhiteNoise static assets (using ephemeral build-time dummy key)
RUN DJANGO_DEBUG=True SECRET_KEY=build-only-key python manage.py collectstatic --noinput

EXPOSE 8000

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
