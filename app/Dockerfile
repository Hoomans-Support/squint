# Build context is app/ only. Copies server.py, the three guarded endpoint modules and static/; no data/, pipeline/ or tests.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py ask_gemini.py factcheck.py brief_ai.py ./
COPY static/ static/
RUN useradd --system --no-create-home appuser
USER appuser
# Cloud Run sets PORT. One worker with 8 threads keeps memory low; the app is read-only static serving.
CMD exec gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --threads 8 --timeout 60 server:app
