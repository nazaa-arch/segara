"""Firmware dan backend harus memakai format payload yang sama (hardware/test_vectors.json)."""
import json
from pathlib import Path

import pytest

from simulator.encoder import TelemetryPacket, encode_telemetry
from ingestion.decoder import decode_telemetry
from ingestion.database import Node, init_db
from hardware.bridge.mqtt_ingest import ensure_node

VECTORS = json.loads(
    (Path(__file__).resolve().parents[1] / "hardware" / "test_vectors.json").read_text()
)["vectors"]
C_TEST = (Path(__file__).resolve().parents[1]
          / "hardware/firmware/node/test/test_payload/test_main.c").read_text()


@pytest.mark.parametrize("v", VECTORS, ids=lambda v: v["hex"])
def test_vector_matches_python_encoder(v):
    pkt = TelemetryPacket(v["node_id"], v["counter"], v["temperature"], v["ph"],
                          v["salinity"], v["turbidity"], v["battery"])
    assert encode_telemetry(pkt).hex() == v["hex"]


@pytest.mark.parametrize("v", VECTORS, ids=lambda v: v["hex"])
def test_vector_decodes(v):
    d = decode_telemetry(bytes.fromhex(v["hex"]))
    assert d.node_id == v["node_id"]
    assert d.counter == v["counter"]
    assert d.temperature == pytest.approx(v["temperature"])


@pytest.mark.parametrize("v", VECTORS, ids=lambda v: v["hex"])
def test_c_firmware_test_uses_same_vectors(v):
    assert f'"{v["hex"]}"' in C_TEST


def test_ensure_node_registers_once_and_rejects_simulator_ids():
    factory = init_db("sqlite://")
    assert ensure_node(factory, 10, "Proto", "Uji", -6.1, 106.8, 29.5, 1.0) is True
    assert ensure_node(factory, 10, "Proto", "Uji", -6.1, 106.8, 29.5, 1.0) is False
    with factory() as s:
        assert s.get(Node, 10).bleaching_threshold == pytest.approx(30.5)
    with pytest.raises(ValueError):
        ensure_node(factory, 3, "x", "x", 0, 0, 29, 1)


def test_temperature_only_prototype_still_feeds_dhw():
    """Fase 1 hanya punya sensor suhu; pH/salinitas/kekeruhan dikirim 0."""
    from ingestion.database import ThermalMetric
    from ingestion.subscriber import IngestionPipeline

    factory = init_db("sqlite://")
    ensure_node(factory, 10, "Proto", "Uji", -6.1, 106.8, 29.5, 1.0)
    pipeline = IngestionPipeline(db_session_factory=factory)
    for ctr, t in enumerate([29.40, 29.45, 29.50]):
        frame = encode_telemetry(TelemetryPacket(10, ctr, t, 0.0, 0.0, 0.0, 88))
        pipeline.process_raw_message("segara/telemetry/10", frame)
    with factory() as s:
        sst = [m.sst for m in s.query(ThermalMetric).filter_by(node_id=10).all()]
    assert sst == pytest.approx([29.40, 29.45, 29.50])
