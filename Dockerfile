
# syntax=docker/dockerfile:1.7

# Build dependencies in a separate stage.
FROM python:3.14-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY app ./app
COPY dashboard ./dashboard

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir .

# Shared runtime image.
FROM python:3.14-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:${PATH}" \
    HOME=/tmp

RUN groupadd --system --gid 10001 adapter \
    && useradd --system \
        --uid 10001 \
        --gid adapter \
        --home-dir /app \
        --shell /usr/sbin/nologin \
        adapter

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

COPY --chown=adapter:adapter alembic.ini ./
COPY --chown=adapter:adapter alembic ./alembic
COPY --chown=adapter:adapter app ./app
COPY --chown=adapter:adapter dashboard ./dashboard
COPY --chown=adapter:adapter config ./config
COPY --chown=adapter:adapter .streamlit ./.streamlit

USER 10001:10001

# Dashboard target.
FROM runtime AS dashboard

EXPOSE 8501

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=6 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3).read()"]

CMD ["streamlit", "run", "dashboard/app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--server.enableCORS=true", \
     "--server.enableXsrfProtection=true", \
     "--browser.gatherUsageStats=false"]

# API target.
# Intentionally last so the API is the default Docker build target.
FROM runtime AS api

USER root

COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 0555 /usr/local/bin/docker-entrypoint.sh

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=6 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3).read()"]

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
