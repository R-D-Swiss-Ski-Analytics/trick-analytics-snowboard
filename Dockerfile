FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
 && rm -rf /var/lib/apt/lists/*

# Python deps
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# App
COPY backend /app/backend
COPY frontend /app/frontend

ENV PORT=8080
EXPOSE 8080

CMD exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers
