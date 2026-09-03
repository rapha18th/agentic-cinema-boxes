# THE BOXES backend for Cloud Run.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    GOOGLE_GENAI_USE_VERTEXAI=TRUE \
    GOOGLE_CLOUD_LOCATION=global

WORKDIR /app

COPY service/requirements.txt ./service/requirements.txt
RUN pip install --no-cache-dir -r service/requirements.txt

COPY src/ ./src/
COPY service/ ./service/

WORKDIR /app/service
EXPOSE 8080
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
