"""
Tes regresi perbaikan QC prioritas sedang:
- Validitas per parameter (suhu tetap dipakai DHW saat sensor lain gagal).
- Spike dibandingkan dengan nilai valid terakhir (satu lonjakan = satu flag).
- Rebaseline spike setelah pergeseran level konsisten.
- Jendela stuck per parameter.
- Forecast hanya memakai suhu yang lolos QC.
"""
import pytest

from ingestion.database import init_db, ThermalMetric
from ingestion.subscriber import IngestionPipeline
from qc.rules import QCFlag, QualityControlEngine, SPIKE_REBASELINE_CYCLES
from simulator.encoder import TelemetryPacket, encode_telemetry


def _vary(i: int):
    """Seri bersih yang berosilasi pada semua parameter."""
    return dict(
        temperature=29.0 + 0.05 * (i % 4),
        ph=8.15 + 0.01 * (i % 3),
        salinity=34.2 + 0.01 * (i % 5),
        turbidity=2.0 + 0.1 * (i % 6),
    )


def test_single_spike_produces_one_flag():
    qc = QualityControlEngine()
    flagged = []
    for i in range(10):
        v = _vary(i)
        if i == 5:
            v["temperature"] += 3.0
        res = qc.evaluate(1, i + 1, battery=90, **v)
        flagged.append(bool(res.param_flags["temperature"] & QCFlag.SPIKE_FAIL))
    assert flagged == [False] * 5 + [True] + [False] * 4


def test_level_shift_is_rebaselined():
    qc = QualityControlEngine()
    for i in range(5):
        qc.evaluate(1, i + 1, battery=90, **_vary(i))
    results = []
    for k in range(SPIKE_REBASELINE_CYCLES + 2):
        v = _vary(10 + k)
        v["temperature"] += 2.0  # pergeseran level permanen
        results.append(qc.evaluate(1, 10 + k, battery=90, **v))
    spike = [bool(r.param_flags["temperature"] & QCFlag.SPIKE_FAIL) for r in results]
    assert spike[:SPIKE_REBASELINE_CYCLES] == [True] * SPIKE_REBASELINE_CYCLES
    assert spike[SPIKE_REBASELINE_CYCLES:] == [False, False]


def test_broken_ph_does_not_invalidate_temperature():
    qc = QualityControlEngine()
    qc.evaluate(1, 1, battery=90, **_vary(0))
    v = _vary(1)
    v["ph"] = 6.0  # di luar rentang
    res = qc.evaluate(1, 2, battery=90, **v)
    assert res.is_valid is False                 # paket secara keseluruhan bermasalah
    assert res.is_param_valid("temperature")     # tetapi suhu sah
    assert not res.is_param_valid("ph")
    assert res.to_dict()["invalid_params"] == ["ph"]


def test_stable_turbidity_not_flagged_stuck_within_longer_window():
    qc = QualityControlEngine()  # suhu W=6, kekeruhan W=12
    flags = []
    for i in range(11):
        v = _vary(i)
        v["turbidity"] = 0.5  # air jernih, konstan
        flags.append(qc.evaluate(1, i + 1, battery=90, **v).flags)
    assert all(not (f & QCFlag.STUCK_FAIL) for f in flags)
    v = _vary(11)
    v["turbidity"] = 0.5
    res = qc.evaluate(1, 12, battery=90, **v)
    assert res.param_flags["turbidity"] & QCFlag.STUCK_FAIL
    assert res.is_param_valid("temperature")


def test_pipeline_keeps_dhw_when_ph_sensor_fails():
    sf = init_db("sqlite:///:memory:")
    pipe = IngestionPipeline(db_session_factory=sf)
    for c in range(1, 6):
        v = _vary(c)
        v["temperature"] = 31.2 + 0.01 * (c % 2)
        v["ph"] = 6.0  # sensor pH rusak terus-menerus
        res = pipe.process_raw_message("t", encode_telemetry(TelemetryPacket(
            node_id=1, counter=c, battery=90, **v)))
    assert res["thermal"] is not None
    assert res["thermal"]["dhw"] > 0
    assert res["thermal"]["stress_breakdown"]["ph_available"] is False


def test_forecast_uses_only_qc_valid_sst(monkeypatch):
    from api.routers import analytics as analytics_router

    sf = init_db("sqlite:///:memory:")
    pipe = IngestionPipeline(db_session_factory=sf)
    for c in range(1, 20):
        v = _vary(c)
        if c == 10:
            v["temperature"] = 34.9  # spike: tidak boleh masuk ke ThermalMetric
        pipe.process_raw_message("t", encode_telemetry(TelemetryPacket(
            node_id=1, counter=c, battery=90, **v)))
    with sf() as s:
        ssts = [r.sst for r in s.query(ThermalMetric).filter(ThermalMetric.node_id == 1)]
    assert 34.9 not in ssts and len(ssts) == 18

    captured = {}
    real_forecast = analytics_router.forecast_thermal_stress

    def spy(historical_sst, **kwargs):
        captured["sst"] = list(historical_sst)
        return real_forecast(historical_sst=historical_sst, **kwargs)

    monkeypatch.setattr(analytics_router, "forecast_thermal_stress", spy)
    with sf() as db:
        out = analytics_router.get_forecast(node_id=1, horizon_days=7, db=db)
    assert out["node_id"] == 1
    assert 34.9 not in captured["sst"]
    assert len(captured["sst"]) == 18
