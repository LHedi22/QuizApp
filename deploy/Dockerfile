# Stage 1: compile Tailwind CSS. Keeps node out of the runtime image — the
# built `app/web/static/web/app.css` is the only thing copied forward, so
# `docker compose ... up --build` always ships current CSS regardless of
# what's committed or what's installed on the host.
FROM node:20-slim AS assets
WORKDIR /assets
COPY package.json package-lock.json* ./
RUN npm install
COPY tailwind.config.js ./
COPY assets ./assets
COPY app/web/templates ./app/web/templates
RUN npx tailwindcss -i ./assets/tailwind/input.css -o ./app/web/static/web/app.css --minify

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
COPY config ./config
COPY manage.py ./
COPY --from=assets /assets/app/web/static/web/app.css ./app/web/static/web/app.css
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
