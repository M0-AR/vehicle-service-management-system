FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install --retries 10 --timeout 60 -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
COPY scripts ./scripts

RUN useradd -r -u 1001 appuser && chown -R appuser /srv \
    && mkdir -p /data/uploads && chown -R appuser /data
USER appuser

EXPOSE 8000
# migrations run at start (idempotent), then the API boots
CMD ["sh", "scripts/start.sh"]
