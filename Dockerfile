# UNTESTED draft for Cloud Run (see docs/DEPLOY_CLOUD_RUN.md)
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
# One worker: chat sessions are kept in process memory. Threads give concurrency.
CMD exec gunicorn --chdir src --bind 0.0.0.0:${PORT:-8080} --workers 1 --threads 8 --timeout 600 appl.app:app
