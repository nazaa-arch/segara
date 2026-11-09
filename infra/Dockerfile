# Build dari root repositori:  docker build -f infra/Dockerfile -t segara .
# (docker-compose.yml di folder ini sudah memakai context "..")

# --- Tahap 1: build dashboard React ---------------------------------------
FROM node:20-slim AS dashboard
WORKDIR /dashboard
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY dashboard/ ./
RUN npm run build

# --- Tahap 2: API Python ---------------------------------------------------
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# psycopg2-binary: driver PostgreSQL/TimescaleDB (SEGARA_DATABASE_URL=postgresql://...)
RUN pip install --no-cache-dir -r requirements.txt psycopg2-binary

COPY analytics/ analytics/
COPY api/ api/
COPY ingestion/ ingestion/
COPY qc/ qc/
COPY simulator/ simulator/
COPY data/ data/
COPY run_segara.py .
COPY --from=dashboard /dashboard/dist dashboard/dist

# Jalankan sebagai pengguna non-root
RUN useradd --create-home --uid 1000 segara && chown -R segara /app
USER segara

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
