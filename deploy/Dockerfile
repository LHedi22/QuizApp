# Single image for both the web process and the Django-Q2 worker.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# libzbar0: runtime lib for pyzbar (QR decode). curl: container healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libzbar0 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
COPY manage.py ./
RUN pip install .

COPY deploy/entrypoint.sh /app/deploy/entrypoint.sh
RUN chmod +x /app/deploy/entrypoint.sh \
    && useradd --create-home --uid 1000 appuser \
    && mkdir -p /data/blob /app/staticfiles \
    && chown -R appuser:appuser /app /data

USER appuser
EXPOSE 8000
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
CMD ["web"]
