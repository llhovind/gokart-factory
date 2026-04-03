# ---- Stage 1: Build Vue frontend ----
FROM node:20-alpine AS frontend-build
WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

COPY frontend/ ./
RUN npm run build
# Output: /frontend/dist/

# ---- Stage 2: Python backend + compiled frontend ----
FROM python:3.12-slim
WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy Python package
COPY backend/ ./

# Copy compiled frontend from stage 1
# Path: /app/frontend/dist/ — matches STATIC_DIR in main.py when run from /app
COPY --from=frontend-build /frontend/dist ./frontend/dist

EXPOSE 8000

# SQLite DB written to /app/data/ — mount a volume there for persistence
ENV PYTHONUNBUFFERED=1
ENV FRONTEND_DIST_PATH=/app/frontend/dist

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
