# =============================================================================
# ARCHIMEDES · API image (FastAPI)
#   docker build -f services/api/Dockerfile -t archimedes-api services/api
# Also the image for a Nebius Serverless Endpoint / Render.com deployment.
# =============================================================================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first so source changes don't bust the layer cache
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# /health must answer for the container healthcheck
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
