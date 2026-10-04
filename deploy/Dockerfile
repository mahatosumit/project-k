# Vasool — production image.
#
# Multi-stage so the runtime layer carries no build toolchain and no compiler.
# Runs as a non-root user on a minimal base, with a read-only-friendly layout.

# ---------- build stage ----------
FROM python:3.13-slim-bookworm AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

# Build-only toolchain. Not present in the final image.
RUN apt-get update \
 && apt-get install --no-install-recommends -y build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Install into a self-contained prefix we can copy wholesale.
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r requirements.txt \
 && /opt/venv/bin/pip install "psycopg[binary]==3.2.10"

# ---------- runtime stage ----------
FROM python:3.13-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_ENV=prod \
    BACKUP_DIR=/data/backups

# Runtime system deps only: libpq for PostgreSQL, tini for correct signal handling.
RUN apt-get update \
 && apt-get install --no-install-recommends -y libpq5 tini curl \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 1001 vasool \
 && useradd --system --uid 1001 --gid vasool --home /app --shell /usr/sbin/nologin vasool

COPY --from=build /opt/venv /opt/venv

WORKDIR /app
COPY --chown=vasool:vasool app ./app
COPY --chown=vasool:vasool scripts ./scripts
COPY --chown=vasool:vasool requirements.txt ./

# Writable state lives on a volume, owned by the app user.
RUN mkdir -p /data/backups /data/logs && chown -R vasool:vasool /data

USER vasool
EXPOSE 8000

# Container-level health check hits the app's own readiness probe, which touches
# the database — so a container with a broken database connection is unhealthy.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/readyz || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
# --no-server-header keeps the framework name out of responses; --proxy-headers is
# only safe because the reverse proxy in front strips client-supplied XFF.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--no-server-header", "--proxy-headers", \
     "--forwarded-allow-ips", "172.16.0.0/12,10.0.0.0/8", \
     "--workers", "2", "--log-level", "warning"]
