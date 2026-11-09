"""
Unit Test: Aturan Quality Control (QC) SEGARA.
"""
import pytest
from qc.rules import QualityControlEngine, QCFlag


def test_qc_clean_data_pass():
    qc = QualityControlEngine()
    res = qc.evaluate(
        node_id=1,
        counter=1,
        temperature=28.5,
        ph=8.15,
        salinity=34.0,
        turbidity=2.5,
        battery=90,
    )
    assert res.is_valid is True
    assert res.flags == QCFlag.PASS
    assert res.flag_names() == ["PASS"]


def test_qc_range_fail():
    qc = QualityControlEngine()
    # Suhu 42°C (di luar rentang 20-35°C)
    res = qc.evaluate(
        node_id=1,
        counter=1,
        temperature=42.0,
        ph=8.15,
        salinity=34.0,
        turbidity=2.5,
        battery=90,
    )
    assert res.is_valid is False
    assert QCFlag.RANGE_FAIL in res.flags
    assert "RANGE_FAIL" in res.flag_names()


def test_qc_spike_fail():
    qc = QualityControlEngine()
    # Data pertama
    qc.evaluate(
        node_id=1,
        counter=1,
        temperature=28.0,
        ph=8.15,
        salinity=34.0,
        turbidity=2.5,
        battery=90,
    )
    # Lonjakan suhu sebesar 3.0°C (batas lonjakan: 1.5°C)
    res2 = qc.evaluate(
        node_id=1,
        counter=2,
        temperature=31.0,
        ph=8.15,
        salinity=34.0,
        turbidity=2.5,
        battery=90,
    )
    assert res2.is_valid is False
    assert QCFlag.SPIKE_FAIL in res2.flags
    assert "SPIKE_FAIL" in res2.flag_names()


def test_qc_stuck_sensor_fail():
    qc = QualityControlEngine(stuck_window_size=6)
    # Masukkan 6 nilai suhu yang persis sama
    for c in range(1, 6):
        res = qc.evaluate(
            node_id=1,
            counter=c,
            temperature=29.0,
            ph=8.15 + (c * 0.01),
            salinity=34.0,
            turbidity=2.5,
            battery=90,
        )
        assert QCFlag.STUCK_FAIL not in res.flags

    # Pembacaan ke-6 dengan suhu tetap 29.0
    res_stuck = qc.evaluate(
        node_id=1,
        counter=6,
        temperature=29.0,
        ph=8.22,
        salinity=34.0,
        turbidity=2.5,
        battery=90,
    )
    assert QCFlag.STUCK_FAIL in res_stuck.flags
    assert "STUCK_FAIL" in res_stuck.flag_names()


def test_qc_packet_loss_detection():
    qc = QualityControlEngine()
    # Counter 10
    qc.evaluate(
        node_id=1,
        counter=10,
        temperature=28.5,
        ph=8.15,
        salinity=34.0,
        turbidity=2.5,
        battery=90,
    )
    # Counter lompat ke 14 (3 paket hilang)
    res_loss = qc.evaluate(
        node_id=1,
        counter=14,
        temperature=28.6,
        ph=8.15,
        salinity=34.0,
        turbidity=2.5,
        battery=90,
    )
    assert QCFlag.PACKET_LOSS in res_loss.flags
    assert res_loss.packet_loss_count == 3
