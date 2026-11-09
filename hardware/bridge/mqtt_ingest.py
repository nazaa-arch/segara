"""
Jembatan ingestion untuk pelampung fisik SEGARA.

`run_segara.py` hanya memakai event bus in-process untuk simulator; subscriber MQTT
(`ingestion.subscriber.IngestionPipeline`) tidak pernah dinyalakan. Skrip ini:

1. Mendaftarkan node prototipe ke DB bila belum ada (node 1-5 milik simulator).
2. Menyalakan IngestionPipeline yang berlangganan `segara/telemetry/+` pada broker nyata.

Gateway LoRa (hardware/firmware/gateway) menerbitkan frame 12 byte ke topik itu, sehingga
paket fisik melewati QC, DHW, dan peringatan yang sama dengan data simulasi, dan tampil di
dashboard karena memakai DB yang sama (SEGARA_DATABASE_URL, default sqlite:///segara.db).

Contoh:
    python -m hardware.bridge.mqtt_ingest --broker 127.0.0.1 --node-id 10 \
        --name "Prototipe Pantai Uji" --lat -6.12 --lon 106.83 --mmm 29.5
"""
from __future__ import annotations

import argparse
import logging
import signal
import threading

from ingestion.database import Node, init_db

logger = logging.getLogger("segara.hardware.bridge")

SIMULATOR_NODE_IDS = range(1, 6)


def ensure_node(
    session_factory,
    node_id: int,
    name: str,
    region: str,
    latitude: float,
    longitude: float,
    mmm_sst: float,
    depth_m: float,
) -> bool:
    """Daftarkan node bila belum ada. Mengembalikan True bila node baru dibuat."""
    if node_id in SIMULATOR_NODE_IDS:
        raise ValueError(f"node_id {node_id} dipakai simulator; gunakan 10 ke atas")
    with session_factory() as session:
        if session.get(Node, node_id) is not None:
            return False
        session.add(
            Node(
                id=node_id,
                name=name,
                region=region,
                latitude=latitude,
                longitude=longitude,
                mmm_sst=mmm_sst,
                bleaching_threshold=round(mmm_sst + 1.0, 2),
                depth_m=depth_m,
                battery=100,
            )
        )
        session.commit()
        return True


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Ingestion MQTT untuk pelampung fisik SEGARA")
    p.add_argument("--broker", default="127.0.0.1")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--node-id", type=int, default=10)
    p.add_argument("--name", default="Prototipe Pelampung 1")
    p.add_argument("--region", default="Lokasi uji prototipe")
    p.add_argument("--lat", type=float, required=True)
    p.add_argument("--lon", type=float, required=True)
    p.add_argument("--mmm", type=float, required=True,
                   help="Maximum Monthly Mean SST lokasi (°C), idealnya dari klimatologi CRW")
    p.add_argument("--depth", type=float, default=1.0)
    p.add_argument("--cycle-hours", type=float, default=6.0,
                   help="Harus sama dengan CYCLE_SECONDS di firmware node")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    # Impor di sini: subscriber menarik dependensi analitik yang berat
    from ingestion.subscriber import IngestionPipeline

    factory = init_db()
    if ensure_node(factory, args.node_id, args.name, args.region,
                   args.lat, args.lon, args.mmm, args.depth):
        logger.info("Node %d didaftarkan", args.node_id)

    pipeline = IngestionPipeline(
        broker_host=args.broker,
        broker_port=args.port,
        client_id=f"segara_hw_bridge_{args.node_id}",
        db_session_factory=factory,
        cycle_hours=args.cycle_hours,
    )
    if not pipeline.start(timeout=5.0):
        logger.error("Tidak dapat terhubung ke broker %s:%d", args.broker, args.port)
        return 1

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    logger.info("Menunggu paket di segara/telemetry/+ (Ctrl+C untuk berhenti)")
    while not stop.wait(30):
        logger.info("diterima=%d diproses=%d galat=%d",
                    pipeline.total_received, pipeline.total_processed, pipeline.total_errors)
    pipeline.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
