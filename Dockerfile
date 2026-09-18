# GridWise Smart Campus Energy Optimization - fallback execution path.
#
#   docker build -t gridwise-llm:1.0.0 .
#   docker run --rm -p 8000:8000 -e GEMINI_API_KEY=... gridwise-llm:1.0.0
#
# /health is ready with no credentials at all; a provider key is only needed for
# operator-note interpretation. No secrets are baked into this image.

# Stage 1: Builder
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Create virtual environment and install requirements
COPY requirements.txt .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r requirements.txt

# Stage 2: Final Image
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# libgomp1 is required by the bundled CBC solver shipped with PuLP.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application files
COPY app ./app
COPY tools ./tools
COPY docs ./docs

# Set up non-root user
RUN useradd --create-home --uid 10001 gridwise && chown -R gridwise /srv
USER gridwise

EXPOSE 8000
ENV PORT=8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://127.0.0.1:${PORT}/health || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
