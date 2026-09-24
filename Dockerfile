FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Includes app/seed_data, fixtures/ and samples/; .dockerignore keeps out .env, .venv and *.db.
COPY backend/ .
# main.py serves the React build from backend/static (/app/static here).
COPY --from=web /web/dist ./static
# Render sets PORT; 8000 is the local default. exec so uvicorn gets SIGTERM directly.
ENV PORT=8000
EXPOSE 8000
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'
