# syntax=docker/dockerfile:1.7

FROM python:3.11-slim as runtime

# ==========================================
# 🌍 Variables de entorno
# ==========================================
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_PYPI_MIRROR="" \
    PATH="/home/appuser/.local/bin:${PATH}"

WORKDIR /app

# ==========================================
# 🧱 Dependencias del sistema
# ==========================================
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        build-essential \
        curl \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# ==========================================
# 📦 Instalación de dependencias Python
# ==========================================
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ==========================================
# 🗂️ Copia del proyecto
# ==========================================
COPY . .

# ==========================================
# 👤 Usuario y permisos
# ==========================================
RUN adduser --disabled-password --gecos "" appuser \
    && mkdir -p /data/uploads /data/uploads_detectadas /data/uploads_nodeteccion \
    && chown -R appuser:appuser /app /data

# ==========================================
# ⚙️ Variables de entorno internas
# ==========================================
ENV DB_PATH=/data/app.db \
    CAPTURE_DIR=/data/uploads \
    DETECTADAS_DIR=/data/uploads_detectadas \
    NODETECCION_DIR=/data/uploads_nodeteccion \
    FLASK_ENV=production \
    PYTHONPATH=/app

# ==========================================
# 🚀 Entrypoint y ejecución
# ==========================================
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

USER appuser
EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["gunicorn", "-b", "0.0.0.0:8000", "--workers", "1", "--timeout", "300", "--access-logfile", "-", "--error-logfile", "-", "app_web:create_app()"]
