# syntax=docker/dockerfile:1.7
FROM python:3.12.10-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt

# ---------- runtime ----------
FROM python:3.12.10-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_ROOT_USER_ACTION=ignore \
    PATH="/opt/venv/bin:$PATH" \
    TZ=Asia/Ho_Chi_Minh \
    NLTK_DATA=/usr/local/share/nltk_data

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
        tzdata \
        curl \
        libmagic1 \
        poppler-utils \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-vie \
        antiword \
        libxml2 \
        libxslt1.1 \
        libjpeg62-turbo \
        libpng16-16 \
        libtiff6 \
        libwebp7 \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

# unstructured/langchain Excel parsing requires NLTK tokenizers (punkt_tab since NLTK 3.9+).
# Download at build time into a fixed NLTK_DATA dir so the container runs fully offline.
# `python -m nltk.downloader` exits non-zero on failure, so a broken build fails loudly
# instead of silently shipping an image that re-downloads (and hangs) at runtime.
RUN mkdir -p "$NLTK_DATA" \
    && /opt/venv/bin/python -m nltk.downloader -d "$NLTK_DATA" punkt_tab punkt \
    && /opt/venv/bin/python -c "import nltk; nltk.data.find('tokenizers/punkt_tab'); nltk.data.find('tokenizers/punkt')"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Single worker: Paddle layout (PP-DocLayoutV3) in-process is memory-heavy; multi-worker risks OOM/worker crash.
CMD ["uvicorn", "server_dev:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
