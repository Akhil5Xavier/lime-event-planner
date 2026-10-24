FROM python:3.12.15-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

# Run as an unprivileged user; the app writes nothing to disk (data lives in Postgres).
RUN useradd --create-home --uid 10001 app
COPY --chown=app:app . .
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

# Migrate + seed venues, then serve. The nightly sync runs in the separate worker
# service (SCHEDULER_ENABLED=false here), so several API workers are safe.
CMD ["sh", "-c", "python -m app.cli init-db && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-2} --proxy-headers --forwarded-allow-ips='*'"]
