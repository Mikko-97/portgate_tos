FROM python:3.11-slim

# Mencegah Python membuat file .pyc dan unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies yang dibutuhkan untuk kompilasi psycopg2 dan healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy seluruh source code project (mengikuti .dockerignore)
COPY . /app/

# Collect static files untuk disajikan oleh Whitenoise di lingkungan produksi
RUN python manage.py collectstatic --noinput

# Expose port service
EXPOSE 8000

# Healthcheck untuk memantau kesiapan container
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/login/ || exit 1

# Default command: Gunicorn WSGI server untuk production
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--threads", "2", "--timeout", "60", "--access-logfile", "-", "--error-logfile", "-"]
