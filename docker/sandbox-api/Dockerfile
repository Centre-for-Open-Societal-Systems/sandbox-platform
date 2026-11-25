# Sandbox API image. Build context is the repository root:
#   docker build -f docker/sandbox-api/Dockerfile .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# psycopg[binary] ships its own libpq, so no compiler or system libraries are needed.
COPY backend/requirements.txt .
# Long timeout and retries: slow or flaky links to PyPI otherwise fail the build.
RUN pip install --default-timeout=120 --retries 10 -r requirements.txt

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/scripts ./scripts
COPY backend/alembic.ini backend/pyproject.toml ./
COPY docker/sandbox-api/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# Windows checkouts may add CR line endings; strip them so sh can run the script.
RUN sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh \
    && chmod +x /usr/local/bin/docker-entrypoint.sh \
    && useradd --create-home --uid 1000 oan \
    && mkdir -p uploads logs keys \
    && chown -R oan:oan /app
USER oan

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/oan/health')"

ENTRYPOINT ["docker-entrypoint.sh"]
# Forwarding headers are handled by the app (TRUSTED_PROXIES), so uvicorn
# reports the real socket peer instead of trusting any X-Forwarded-For.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
