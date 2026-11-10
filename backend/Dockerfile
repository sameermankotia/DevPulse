FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
COPY docker-entrypoint.sh ./

# Run unprivileged. /srv stays writable so the SQLite demo build can keep its
# database file beside the code.
RUN useradd --system --uid 10001 devpulse \
    && chmod +x docker-entrypoint.sh \
    && chown -R devpulse:devpulse /srv
USER devpulse

# Hosts such as Render inject their own port; 8000 is only the local default.
ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT}/api/v1/health" || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
