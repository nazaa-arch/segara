"""
Unit Test Langsung: Pipeline Ingestion dan Penyimpanan Database SEGARA.
"""
import pytest
from ingestion.subscriber import IngestionPipeline
from ingestion.database import init_db, Measurement, QCRecord, ThermalMetric
from simulator.encoder import TelemetryPacket, encode_telemetry


def test_ingestion_pipeline_process_raw_message():
    session_factory = init_db("sqlite:///:memory:")
    pipeline = IngestionPipeline(db_session_factory=session_factory)

    # Buat paket telemetri valid
    pkt = TelemetryPacket(
        node_id=1,
        counter=101,
        temperature=29.80,
        ph=8.18,
        salinity=34.20,
        turbidity=2.8,
        battery=94,
    )
    raw_payload = encode_telemetry(pkt)

    res = pipeline.process_raw_message("segara/telemetry/1", raw_payload)
    assert res is not None
    assert res["node_id"] == 1
    assert res["counter"] == 101
    assert res["qc"]["is_valid"] is True
    assert res["thermal"] is not None
    assert res["thermal"]["hotspot"] == pytest.approx(0.60, abs=0.05)

    # Verifikasi data tersimpan di basis data
    with session_factory() as session:
        meas = session.query(Measurement).filter(Measurement.counter == 101).first()
        assert meas is not None
        assert meas.temperature == pytest.approx(29.80, abs=0.01)

        qc = session.query(QCRecord).filter(QCRecord.measurement_id == meas.id).first()
        assert qc is not None
        assert qc.is_valid is True

        thermal = session.query(ThermalMetric).filter(ThermalMetric.node_id == 1).first()
        assert thermal is not None
        assert thermal.alert_level == 1  # Bleaching Watch (HotSpot = 29.80 - 29.20 = 0.60)


def test_ingestion_pipeline_malformed_payload():
    session_factory = init_db("sqlite:///:memory:")
    pipeline = IngestionPipeline(db_session_factory=session_factory)

    # Payload rusak (panjang bukan 12 byte)
    bad_payload = b"\x01\x02\x03"
    res = pipeline.process_raw_message("segara/telemetry/1", bad_payload)
    assert res is None
    assert pipeline.total_errors == 1
