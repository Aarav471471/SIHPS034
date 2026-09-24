# =============================================================================
#  MetriX backend image
#
#  Debian slim rather than Alpine: OpenCV, WeasyPrint and PaddleOCR all ship
#  manylinux wheels and native deps that Alpine's musl libc does not satisfy
#  without a lengthy source build.
# =============================================================================
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System libraries:
#   libgl1/libglib2.0    -> OpenCV runtime
#   libzbar0             -> pyzbar barcode decoding
#   libpango/libcairo    -> WeasyPrint PDF rendering
#   libpq5               -> PostgreSQL client
RUN apt-get update && apt-get install --no-install-recommends -y \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        libzbar0 \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        libffi-dev \
        shared-mime-info \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependency layer first so source edits do not invalidate the pip cache.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir weasyprint==63.0

COPY . .

# Run as a non-root user; evidence storage must remain writable.
RUN useradd --create-home --shell /bin/bash metrix \
    && mkdir -p /app/storage \
    && chown -R metrix:metrix /app
USER metrix

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
