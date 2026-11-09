"""
Aplikasi Utama FastAPI SEGARA
Sistem Early-warning Gangguan termal Atas terumbu kaRAng
"""
from __future__ import annotations
import os
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from ingestion.database import init_db
from api.routers import nodes, measurements, analytics, alerts, simulator_ctrl, evaluation
from api.routers.simulator_ctrl import execute_sim_step, _sim_state

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("segara.main")

# Background simulation runner
async def simulation_loop():
    logger.info("Simulation background worker started")
    while True:
        try:
            if _sim_state["is_running"]:
                # Tulis-DB dijalankan di thread pekerja agar event loop tetap
                # melayani request API selama simulasi berjalan.
                await asyncio.to_thread(
                    execute_sim_step,
                    _sim_state["scenario"],
                    _sim_state["packet_loss_rate"],
                )
            await asyncio.sleep(max(0.2, _sim_state["speed_sec"]))
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Error in simulation worker loop: %s", e)
            await asyncio.sleep(1.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inisialisasi basis data
    init_db()
    logger.info("Database initialized with 5 Indonesian reef stations")

    # Jalankan 12 langkah awal agar dashboard memiliki data riwayat langsung saat pertama kali dibuka
    logger.info("Seeding initial historical telemetry steps...")
    for _ in range(12):
        await asyncio.to_thread(execute_sim_step, "normal", 0.0)

    # Jalankan background worker untuk simulator
    sim_task = asyncio.create_task(simulation_loop())
    # Hitung metrik evaluasi (beberapa detik) di thread latar agar tab Evaluasi langsung siap
    warm_task = asyncio.create_task(asyncio.to_thread(evaluation.warm_metrics_cache))

    yield

    warm_task.cancel()
    sim_task.cancel()
    try:
        await sim_task
    except asyncio.CancelledError:
        pass
    logger.info("SEGARA server shutdown clean")


app = FastAPI(
    title="SEGARA API - Sistem Early-warning Gangguan termal Atas terumbu kaRAng",
    description="Backend API analitik stres termal koral NOAA CRW, ingestion telemetri biner LoRaWAN, dan deteksi dini pemutihan.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS: dashboard disajikan dari origin yang sama, jadi CORS hanya dibutuhkan untuk
# klien lain (mis. Vite dev server). Origin diatur lewat SEGARA_CORS_ORIGINS
# (dipisah koma). allow_credentials=True + origin "*" tidak sah menurut spesifikasi CORS.
_cors_origins = [
    o.strip()
    for o in os.environ.get(
        "SEGARA_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Registrasi Router REST API
app.include_router(nodes.router)
app.include_router(measurements.router)
app.include_router(analytics.router)
app.include_router(alerts.router)
app.include_router(simulator_ctrl.router)
app.include_router(evaluation.router)


@app.get("/api/health")
def health_check():
    """Cek kesehatan termasuk koneksi database (dipakai healthcheck Docker)."""
    db_ok = True
    try:
        with init_db()() as session:
            session.execute(text("SELECT 1"))
    except Exception as e:  # pragma: no cover - hanya saat DB mati
        logger.error("Health check: database tidak dapat diakses: %s", e)
        db_ok = False
    body = {
        "status": "healthy" if db_ok else "degraded",
        "service": "SEGARA Coral Bleaching Early Warning System",
        "version": "1.0.0",
        "database": "ok" if db_ok else "error",
        "simulation_running": bool(_sim_state["is_running"]),
    }
    return body if db_ok else JSONResponse(status_code=503, content=body)


@app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
def api_not_found(rest: str):
    """Path API yang tidak dikenal → 404 JSON (bukan index.html / 200)."""
    raise HTTPException(status_code=404, detail=f"Endpoint /api/{rest} tidak ditemukan")


# Sajikan frontend jika folder static/build tersedia
static_dist_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard", "dist")
if os.path.exists(static_dist_path):
    app.mount("/assets", StaticFiles(directory=os.path.join(static_dist_path, "assets")), name="assets")
    # Aset brand (logo, favicon) disalin Vite dari dashboard/public/brand
    brand_path = os.path.join(static_dist_path, "brand")
    if os.path.isdir(brand_path):
        app.mount("/brand", StaticFiles(directory=brand_path), name="brand")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        # Rute non-API → index.html (SPA). Rute /api/* sudah ditangani di atas.
        index_file = os.path.join(static_dist_path, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="Dashboard belum di-build (jalankan npm run build)")
