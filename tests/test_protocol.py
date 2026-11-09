"""
Unit Test: Protokol Biner 12-Byte SEGARA.
"""
import pytest
from simulator.encoder import TelemetryPacket, encode_telemetry, BINARY_FRAME_SIZE
from ingestion.decoder import decode_telemetry


def test_encode_decode_roundtrip():
    pkt = TelemetryPacket(
        node_id=1,
        counter=1042,
        temperature=29.85,
        ph=8.14,
        salinity=34.25,
        turbidity=12.5,
        battery=92,
    )

    encoded = encode_telemetry(pkt)
    assert len(encoded) == BINARY_FRAME_SIZE
    assert len(encoded) == 12

    decoded = decode_telemetry(encoded)
    assert decoded is not None
    assert decoded.node_id == 1
    assert decoded.counter == 1042
    assert decoded.temperature == pytest.approx(29.85, abs=0.01)
    assert decoded.ph == pytest.approx(8.14, abs=0.01)
    assert decoded.salinity == pytest.approx(34.25, abs=0.01)
    assert decoded.turbidity == pytest.approx(12.5, abs=0.1)
    assert decoded.battery == 92


def test_encode_decode_boundary_and_negative():
    pkt = TelemetryPacket(
        node_id=255,
        counter=65535,
        temperature=-5.50,
        ph=0.00,
        salinity=0.00,
        turbidity=0.0,
        battery=0,
    )
    encoded = encode_telemetry(pkt)
    decoded = decode_telemetry(encoded)
    assert decoded is not None
    assert decoded.node_id == 255
    assert decoded.counter == 65535
    assert decoded.temperature == pytest.approx(-5.50, abs=0.01)
    assert decoded.battery == 0


def test_decode_invalid_length():
    assert decode_telemetry(b"") is None
    assert decode_telemetry(b"\x00" * 11) is None
    assert decode_telemetry(b"\x00" * 13) is None
