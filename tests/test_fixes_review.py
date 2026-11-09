"""
Tes regresi untuk perbaikan hasil review:
1. Alert Warning/AL1/AL2 mensyaratkan HotSpot >= 1.
2. DHW berbasis waktu observasi (paket hilang tidak memperpanjang jendela).
3. Riwayat DHW dipulihkan dari DB setelah restart.
4. /api/measurements/history mengembalikan rekaman terbaru.
5. Paket duplikat dan counter mundur ditangani QC.
"""
from datetime import datetime, timedelta, timezone

import pytest

from analytics.thermal_stress import (
    BleachingAlertLevel,
    ThermalAnalyticsEngine,
    classify_bleaching_alert,
)
from ingestion.database import init_db, Measurement, ThermalMetric
from ingestion.subscriber import IngestionPipeline
from qc.rules import QCFlag, QualityControlEngine
from simulator.encoder import TelemetryPacket, encode_telemetry


def _payload(counter: int, temperature: float, node_id: int = 1) -> bytes:
    return encode_telemetry(TelemetryPacket(
        # Jitter kecil agar aturan "sensor macet" tidak terpicu
        node_id=node_id, counter=counter, temperature=temperature + 0.01 * (counter % 2),
        ph=8.15 + 0.01 * (counter % 3), salinity=34.2 + 0.01 * (counter % 4),
        turbidity=2.0 + 0.1 * (counter % 5), battery=90,
    ))


# 1. Klasifikasi alert -------------------------------------------------------

def test_high_dhw_without_hotspot_is_not_alert():
    assert classify_bleaching_alert(hotspot=0.0, dhw=9.0) == BleachingAlertLevel.NO_STRESS
    assert classify_bleaching_alert(hotspot=0.5, dhw=9.0) == BleachingAlertLevel.BLEACHING_WATCH
    assert classify_bleaching_alert(hotspot=1.0, dhw=9.0) == BleachingAlertLevel.ALERT_LEVEL_2
    assert classify_bleaching_alert(hotspot=1.0, dhw=4.0) == BleachingAlertLevel.ALERT_LEVEL_1
    assert classify_bleaching_alert(hotspot=1.0, dhw=0.0) == BleachingAlertLevel.BLEACHING_WARNING


# 2. DHW berbasis waktu ------------------------------------------------------

def test_dhw_window_uses_time_not_point_count():
    engine = ThermalAnalyticsEngine(window_days=84)
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    # 10 hari HotSpot 2 °C, lalu jeda 80 hari tanpa data, lalu satu titik HotSpot 0
    for d in range(10):
        engine.process_telemetry(1, sst=31.0, mmm=29.0, ph=8.1, turbidity=2.0,
                                 dt_days=1.0, observed_at=t0 + timedelta(days=d))
    res = engine.process_telemetry(1, sst=29.0, mmm=29.0, ph=8.1, turbidity=2.0,
                                   dt_days=1.0, observed_at=t0 + timedelta(days=90))
    # Jendela (6, 90]: hari 0..6 keluar; hari 7..9 tersisa: 3 * 2/7.
    # Versi lama (84 titik terakhir) akan menghitung seluruh 10 hari = 2,86.
    assert res.dhw == pytest.approx(3 * 2.0 / 7.0, abs=0.01)


def test_dhw_without_timestamps_matches_point_based():
    engine = ThermalAnalyticsEngine(window_days=84)
    res = None
    for _ in range(100):
        res = engine.process_telemetry(1, sst=31.0, mmm=29.0, ph=8.1, turbidity=2.0, dt_days=1.0)
    assert res.dhw == pytest.approx(84 * 2.0 / 7.0, abs=0.01)


def test_packet_loss_advances_observation_time():
    sf = init_db("sqlite:///:memory:")
    pipe = IngestionPipeline(db_session_factory=sf, cycle_hours=6.0)
    r1 = pipe.process_raw_message("t", _payload(10, 29.0))
    r2 = pipe.process_raw_message("t", _payload(14, 29.0))  # 3 paket hilang
    t1 = datetime.fromisoformat(r1["observed_at"])
    t2 = datetime.fromisoformat(r2["observed_at"])
    assert t2 - t1 == timedelta(hours=24)


# 3. Pemulihan state dari DB --------------------------------------------------

def test_dhw_survives_pipeline_restart():
    sf = init_db("sqlite:///:memory:")
    pipe = IngestionPipeline(db_session_factory=sf)
    last = None
    for c in range(1, 41):
        last = pipe.process_raw_message("t", _payload(c, 31.2))  # HotSpot 2.0 di node 1
    dhw_before = last["thermal"]["dhw"]
    assert dhw_before > 0

    # Proses baru (restart) dengan DB yang sama
    pipe2 = IngestionPipeline(db_session_factory=sf)
    res = pipe2.process_raw_message("t", _payload(41, 31.2))
    assert res["qc"]["flag_names"] == ["PASS"]  # counter berlanjut, tanpa packet loss palsu
    assert res["thermal"]["dhw"] == pytest.approx(dhw_before + 2.0 * 0.25 / 7.0, abs=0.02)

    with sf() as s:
        times = [m.timestamp for m in s.query(Measurement).order_by(Measurement.id).all()]
    assert times == sorted(times)


# 4. Endpoint history ---------------------------------------------------------

def test_history_endpoint_returns_latest_records():
    from fastapi.testclient import TestClient
    from api.main import app

    with TestClient(app) as client:
        client.post("/api/simulator/step?steps=3")
        data = client.get("/api/measurements/history?node_id=1&limit=5").json()
        latest = client.get("/api/measurements/latest").json()
    assert len(data) == 5
    stamps = [d["timestamp"] for d in data]
    assert stamps == sorted(stamps)
    latest_node1 = next(m for m in latest if m["node_id"] == 1)
    assert data[-1]["id"] == latest_node1["id"]


# 5. Duplikat & counter reset -------------------------------------------------

def test_duplicate_packet_flagged_and_excluded_from_dhw():
    sf = init_db("sqlite:///:memory:")
    pipe = IngestionPipeline(db_session_factory=sf)
    pipe.process_raw_message("t", _payload(5, 31.2))
    dup = pipe.process_raw_message("t", _payload(5, 31.2))
    assert "DUPLICATE" in dup["qc"]["flag_names"]
    assert dup["qc"]["is_valid"] is False
    assert dup["thermal"] is None
    with sf() as s:
        assert s.query(ThermalMetric).count() == 1


def test_counter_reset_is_not_packet_loss():
    qc = QualityControlEngine()
    qc.evaluate(1, 5000, 29.0, 8.1, 34.0, 2.0, 90)
    res = qc.evaluate(1, 1, 29.1, 8.12, 34.0, 2.1, 90)
    assert not (res.flags & QCFlag.PACKET_LOSS)
    assert res.packet_loss_count == 0
    assert "counter_reset" in res.details


def test_counter_wraparound_is_normal():
    qc = QualityControlEngine()
    qc.evaluate(1, 65535, 29.0, 8.1, 34.0, 2.0, 90)
    res = qc.evaluate(1, 0, 29.1, 8.12, 34.0, 2.1, 90)
    assert res.flags == QCFlag.PASS
