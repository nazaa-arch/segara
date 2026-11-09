"""
Tes pengerasan sistem: rute API, health check, notifikasi, validasi kontrol simulator,
isolasi benchmark evaluasi, dan biaya detektor anomali.
"""
import threading
import time

import pytest
from fastapi.testclient import TestClient

from api.alerting import AlertDispatcher
from api.main import app
from ingestion.database import init_db, Alert


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# --- Rute & health ----------------------------------------------------------

def test_unknown_api_path_returns_404(client):
    r = client.get("/api/tidak-ada")
    assert r.status_code == 404
    assert "tidak ditemukan" in r.json()["detail"]


def test_health_reports_database(client):
    body = client.get("/api/health").json()
    assert body["status"] == "healthy"
    assert body["database"] == "ok"
    assert "simulation_running" in body


# --- Validasi kontrol simulator ----------------------------------------------

def test_invalid_scenario_rejected(client):
    r = client.post("/api/simulator/control", json={"action": "control", "scenario": "xyz"})
    assert r.status_code == 422


def test_control_without_speed_keeps_speed(client):
    client.post("/api/simulator/control", json={"action": "control", "speed_sec": 0.5})
    client.post("/api/simulator/control", json={"action": "control", "scenario": "normal"})
    state = client.get("/api/simulator/status").json()["state"]
    assert state["speed_sec"] == 0.5
    client.post("/api/simulator/control", json={"action": "control", "speed_sec": 1.0})


def test_step_count_is_bounded(client):
    assert client.post("/api/simulator/step?steps=0").status_code == 422
    assert client.post("/api/simulator/step?steps=10000").status_code == 422


# --- Evaluasi tidak menyentuh DB live -----------------------------------------

def test_evaluation_metrics_do_not_write_live_db(client):
    sf = init_db()
    from ingestion.database import Measurement
    with sf() as s:
        before = s.query(Measurement).count()
    r = client.get("/api/evaluation/metrics?refresh=true")
    assert r.status_code == 200
    with sf() as s:
        after = s.query(Measurement).count()
    # Hanya simulasi latar (jika berjalan) yang boleh menambah data; benchmark tidak.
    assert after - before < 100


# --- Notifikasi ---------------------------------------------------------------

ARGS = dict(node_name="Stasiun <A&B>", region="R", alert_label="Alert Level 1",
            sst=30.5, mmm=29.2, hotspot=1.3, dhw=4.2, action_advice="parah & risiko")


def test_plain_message_has_no_markdown_markup():
    msg = AlertDispatcher().format_telegram_message(**ARGS)
    assert "PERINGATAN STRES TERMAL" in msg
    for ch in ("*", "`", "_"):
        assert ch not in msg


def test_telegram_html_escapes_values():
    html_msg = AlertDispatcher().format_telegram_html(**ARGS)
    assert "&lt;A&amp;B&gt;" in html_msg
    assert "parah &amp; risiko" in html_msg


def test_telegram_send_runs_in_background(monkeypatch):
    sent = threading.Event()
    started = {}

    def slow_send(self, text_html, node_id, alert_label):
        started["t"] = time.perf_counter()
        time.sleep(0.5)
        sent.set()

    monkeypatch.setattr(AlertDispatcher, "_send_telegram", slow_send)
    d = AlertDispatcher(telegram_token="x", telegram_chat_id="y")
    sf = init_db("sqlite:///:memory:")
    with sf() as s:
        t0 = time.perf_counter()
        rec = d.dispatch_alert(session=s, node_id=1, alert_level=3, alert_label="Alert Level 1",
                               sst=30.5, mmm=29.2, hotspot=1.3, dhw=4.2)
        elapsed = time.perf_counter() - t0
        assert rec is not None and s.query(Alert).count() == 1
    assert elapsed < 0.3          # tidak menunggu jaringan
    assert sent.wait(2.0)         # tetap terkirim di latar


# --- Detektor anomali ---------------------------------------------------------

def test_anomaly_model_not_refit_every_packet_when_buffer_full():
    from analytics.anomaly import AnomalyDetector
    det = AnomalyDetector(refit_every=50)
    fits = {"n": 0}
    import analytics.anomaly as mod
    real = mod.IsolationForest

    class Counting(real):
        def fit(self, *a, **k):
            fits["n"] += 1
            return super().fit(*a, **k)

    mod.IsolationForest = Counting
    try:
        for i in range(400):
            det.add_observation(1, 29.0 + 0.01 * (i % 7), 8.1, 34.2, 2.0)
    finally:
        mod.IsolationForest = real
    # 371 observasi ber-model (400 - 29): ±8 kali fit, bukan ratusan
    assert fits["n"] <= 10


# --- Peramalan ----------------------------------------------------------------

def test_forecast_no_alert_when_cool_despite_old_dhw():
    from analytics.forecasting import forecast_thermal_stress
    fc = forecast_thermal_stress([28.2] * 60, mmm=29.2, current_dhw=14.3, horizon_days=14, step_days=0.25)
    assert fc.projected_alert_level == "No Stress"
    assert fc.days_to_alert_1 is None and fc.days_to_alert_2 is None


def test_forecast_respects_six_hour_cadence():
    from analytics.forecasting import forecast_thermal_stress
    # SST konstan 31,2 (HotSpot 2): DHW naik 2/7 per HARI, bukan per sampel
    fc = forecast_thermal_stress([31.2] * 60, mmm=29.2, current_dhw=0.0, horizon_days=14, step_days=0.25)
    assert len(fc.predicted_sst) == 14
    assert fc.predicted_dhw[6] == pytest.approx(7 * 2.0 / 7.0, abs=0.05)
    assert fc.days_to_alert_1 == 14
