# syntax=docker/dockerfile:1.7

FROM python:3.11-slim as runtime

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_PYPI_MIRROR="" \
    PATH="/home/appuser/.local/bin:${PATH}"

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

RUN adduser --disabled-password --gecos "" appuser \
    && mkdir -p /data/uploads /data/uploads_detectadas /data/uploads_nodeteccion \
    && chown -R appuser:appuser /app /data

ENV DB_PATH=/data/app.db \
    CAPTURE_DIR=/data/uploads \
    DETECTADAS_DIR=/data/uploads_detectadas \
    NODETECCION_DIR=/data/uploads_nodeteccion \
    FLASK_ENV=production \
    PYTHONPATH=/app

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

USER appuser

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["gunicorn", "-b", "0.0.0.0:8000", "app_web:create_app()"]
