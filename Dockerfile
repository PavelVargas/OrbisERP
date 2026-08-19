FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl wkhtmltopdf fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN addgroup --system orbiserp && adduser --system --ingroup orbiserp orbiserp && mkdir -p /var/lib/orbiserp/uploads /app/logs && chown -R orbiserp:orbiserp /app /var/lib/orbiserp
USER orbiserp
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -fsS http://127.0.0.1:8000/operations/health/live || exit 1
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]
