"""
Unit Test: Algoritma Stres Termal NOAA CRW & Forecasting SEGARA.
"""
import pytest
from analytics.thermal_stress import (
    compute_hotspot,
    compute_dhw_from_series,
    classify_bleaching_alert,
    BleachingAlertLevel,
    compute_compound_stress,
)
from analytics.forecasting import forecast_thermal_stress


def test_hotspot_calculation():
    mmm = 29.20
    assert compute_hotspot(28.50, mmm) == 0.0
    assert compute_hotspot(29.20, mmm) == 0.0
    assert compute_hotspot(29.70, mmm) == pytest.approx(0.50, abs=0.01)
    assert compute_hotspot(30.70, mmm) == pytest.approx(1.50, abs=0.01)


def test_noaa_alert_level_classification():
    # No stress
    assert classify_bleaching_alert(hotspot=0.0, dhw=0.0) == BleachingAlertLevel.NO_STRESS
    # Bleaching watch (0 < HotSpot < 1.0)
    assert classify_bleaching_alert(hotspot=0.5, dhw=0.0) == BleachingAlertLevel.BLEACHING_WATCH
    # Bleaching warning (HotSpot >= 1.0, DHW < 4.0)
    assert classify_bleaching_alert(hotspot=1.2, dhw=2.5) == BleachingAlertLevel.BLEACHING_WARNING
    # Alert Level 1 (4.0 <= DHW < 8.0)
    assert classify_bleaching_alert(hotspot=1.5, dhw=5.0) == BleachingAlertLevel.ALERT_LEVEL_1
    # Alert Level 2 (DHW >= 8.0)
    assert classify_bleaching_alert(hotspot=2.0, dhw=8.5) == BleachingAlertLevel.ALERT_LEVEL_2


def test_dhw_accumulation():
    # 7 hari berturut-turut HotSpot = 2.0°C (di atas 1.0°C) -> DHW harus = 2.0 °C-minggu
    hotspots = [2.0] * 7
    dhw = compute_dhw_from_series(hotspots, dt_days=1.0, window_days=84)
    assert dhw == pytest.approx(2.0, abs=0.05)

    # Hotspot < 1.0°C tidak boleh berkontribusi ke DHW
    low_hotspots = [0.8] * 14
    dhw_low = compute_dhw_from_series(low_hotspots, dt_days=1.0, window_days=84)
    assert dhw_low == 0.0


def test_compound_stress_indices():
    # Kondisi ideal
    res_ideal = compute_compound_stress(dhw=0.0, ph=8.2, turbidity=2.0)
    assert res_ideal["compound_score"] == 0.0

    # Kondisi stres parah
    res_severe = compute_compound_stress(dhw=8.0, ph=7.5, turbidity=40.0)
    assert res_severe["compound_score"] >= 0.85


def test_forecasting():
    temps = [29.0, 29.2, 29.4, 29.7, 30.1, 30.5, 30.8]
    fc = forecast_thermal_stress(historical_sst=temps, mmm=29.2, current_dhw=1.2, horizon_days=14)
    assert len(fc.predicted_sst) == 14
    assert len(fc.predicted_dhw) == 14
    assert fc.horizon_days == 14
    # Karena tren naik, suhu ramalan harus > 30.0
    assert fc.predicted_sst[-1] > 30.0
