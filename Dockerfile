# syntax=docker/dockerfile:1

FROM node:22-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runner
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0
ENV PORT=8010
ENV FRONTEND_DIST_DIR=/app/frontend/dist
ENV INDEX_AGENT_DATA_DIR=/app/data/runtime
ENV OPENUNI_RUNTIME_DIR=/app/data/runtime

RUN adduser --disabled-password --gecos "" appuser \
  && mkdir -p /app/data/runtime /app/frontend/dist \
  && chown -R appuser:appuser /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend/app /app/backend/app
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

USER appuser
EXPOSE 8010

CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8010"]
