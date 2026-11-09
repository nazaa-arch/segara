"""
Modul Peramalan Suhu Laut & Stres Termal SEGARA.
Menyediakan:
1. Baseline Persistence Model (prediksi nilai sama dengan titik terakhir: y_{t+h} = y_t)
2. Holt's Linear Exponential Smoothing with Damped Trend
3. Evaluasi Multi-Horizon (1, 7, 14 Hari) membandingkan model vs baseline persistence
4. Estimasi Hari menuju ambang peringatan (Bleaching Warning dan Alert Level 1/2)
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple, Optional
import numpy as np


@dataclass
class ForecastTrajectory:
    horizon_days: int
    timestamps_days: List[int]
    predicted_sst: List[float]
    predicted_hotspot: List[float]
    predicted_dhw: List[float]
    baseline_sst: List[float]
    projected_alert_level: str
    days_to_warning: Optional[int]
    days_to_alert_1: Optional[int]
    days_to_alert_2: Optional[int]
    metrics: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "horizon_days": self.horizon_days,
            "timestamps_days": self.timestamps_days,
            "predicted_sst": [round(x, 2) for x in self.predicted_sst],
            "predicted_hotspot": [round(x, 2) for x in self.predicted_hotspot],
            "predicted_dhw": [round(x, 2) for x in self.predicted_dhw],
            "baseline_sst": [round(x, 2) for x in self.baseline_sst],
            "projected_alert_level": self.projected_alert_level,
            "days_to_warning": self.days_to_warning,
            "days_to_alert_1": self.days_to_alert_1,
            "days_to_alert_2": self.days_to_alert_2,
            "metrics": self.metrics,
        }


def compute_forecast_metrics(actual: List[float], predicted: List[float]) -> Dict[str, float]:
    """Menghitung MAE dan RMSE antara nilai aktual dan prediksi."""
    act = np.array(actual)
    pred = np.array(predicted)
    mae = float(np.mean(np.abs(act - pred)))
    rmse = float(np.sqrt(np.mean((act - pred) ** 2)))
    return {"mae": round(mae, 3), "rmse": round(rmse, 3)}


def evaluate_multi_horizon_forecasting(
    series: List[float],
    horizons: List[int] = [1, 7, 14],
    alpha: float = 0.35,
    beta: float = 0.12,
    damping: float = 0.95,
    step_days: float = 1.0,
) -> Dict[str, Any]:
    """Rolling-origin backtest: Holt damped trend vs persistence.

    `horizons` dinyatakan dalam hari; `step_days` adalah jarak antar-sampel.
    Jika sampel tidak harian, horizon dikonversi ke jumlah langkah dan
    jumlah titik evaluasi dilaporkan agar tidak dibaca sebagai evaluasi harian.
    """
    n = len(series)
    step_days = float(step_days)
    if step_days <= 0:
        raise ValueError("step_days harus > 0")

    horizon_steps = {h: max(1, int(round(h / step_days))) for h in horizons}
    max_h = max(horizon_steps.values())
    min_train = max(10, max_h + 2)

    if n < min_train + max_h:
        return {
            "status": "insufficient_data",
            "available_samples": n,
            "minimum_samples_required": min_train + max_h,
            "requested_horizons_days": horizons,
            "step_days": step_days,
            "reason": "Tidak ada metrik yang dihitung; data tidak cukup untuk rolling-origin.",
        }

    results: Dict[str, Any] = {
        "status": "ok",
        "step_days": step_days,
        "samples": n,
        "design": "Rolling origin, one-step refit per origin, absolute error per horizon.",
    }
    for h in horizons:
        steps = horizon_steps[h]
        model_errors: List[float] = []
        baseline_errors: List[float] = []

        for t in range(min_train, n - steps + 1):
            train = series[:t]
            actual = series[t + steps - 1]

            level = train[0]
            trend = train[1] - train[0] if len(train) > 1 else 0.0
            for value in train[1:]:
                previous = level
                level = alpha * value + (1.0 - alpha) * (previous + trend)
                trend = beta * (level - previous) + (1.0 - beta) * trend

            predicted = level + sum(trend * (damping ** k) for k in range(1, steps + 1))
            model_errors.append(abs(actual - predicted))
            baseline_errors.append(abs(actual - train[-1]))

        model_mae = float(np.mean(model_errors))
        baseline_mae = float(np.mean(baseline_errors))
        improvement = ((baseline_mae - model_mae) / baseline_mae * 100.0) if baseline_mae > 0 else None

        results[f"horizon_{h}_days"] = {
            "horizon_days": h,
            "horizon_steps": steps,
            "evaluated_origins": len(model_errors),
            "model_mae": round(model_mae, 3),
            "baseline_mae": round(baseline_mae, 3),
            "model_beats_persistence": model_mae < baseline_mae,
            "improvement_vs_persistence_pct": round(improvement, 1) if improvement is not None else None,
        }
    return results


def forecast_thermal_stress(
    historical_sst: List[float],
    mmm: float,
    current_dhw: float,
    horizon_days: int = 14,
    alpha: float = 0.35,
    beta: float = 0.12,
    damping: float = 0.95,
    step_days: float = 1.0,
) -> ForecastTrajectory:
    """
    Melakukan peramalan SST dan DHW untuk jendela ke depan (horizon_days).
    Menggunakan Holt's Linear Trend Exponential Smoothing vs Persistence Baseline.

    step_days: jarak antarsampel ``historical_sst`` dalam hari (telemetri 6 jam = 0,25).
    Tren Holt dihitung per sampel, jadi proyeksi dijalankan per sampel lalu diambil
    satu titik per hari; DHW bertambah ``HotSpot * step_days / 7`` per sampel.

    Level peringatan proyeksi memakai aturan yang sama dengan sistem utama
    (Warning ke atas mensyaratkan HotSpot >= 1). Catatan: DHW proyeksi tidak
    dikurangi oleh HotSpot lama yang keluar dari jendela 84 hari, sehingga cenderung
    terlalu tinggi saat stres termal sedang mereda.
    """
    from analytics.thermal_stress import classify_bleaching_alert, BleachingAlertLevel

    if not historical_sst:
        historical_sst = [mmm]

    n = len(historical_sst)
    last_val = historical_sst[-1]
    step_days = max(1e-6, float(step_days))
    samples_per_day = max(1, int(round(1.0 / step_days)))

    # Baseline persistence: nilai konstan sama dengan observasi terakhir
    baseline_sst = [float(last_val)] * horizon_days

    # Jika data terlalu sedikit (< 3), gunakan tren datar
    if n < 3:
        level = last_val
        trend = 0.0
    else:
        # Terapkan Holt's Exponential Smoothing pada riwayat
        level = historical_sst[0]
        trend = historical_sst[1] - historical_sst[0]
        for t in range(1, n):
            val = historical_sst[t]
            prev_level = level
            level = alpha * val + (1 - alpha) * (prev_level + trend)
            trend = beta * (level - prev_level) + (1 - beta) * trend

    predicted_sst = []
    predicted_hotspot = []
    projected_dhw_list = []
    daily_levels = []

    accumulated_dhw = current_dhw
    damped_sum = 0.0
    total_steps = horizon_days * samples_per_day
    for k in range(1, total_steps + 1):
        # Tren teredam kumulatif (Holt damped): sum_{i=1..k} damping^i
        damped_sum += damping ** k
        pred_temp = float(level + trend * damped_sum)
        pred_temp = max(20.0, min(36.0, pred_temp))
        hs = max(0.0, pred_temp - mmm)
        if hs >= 1.0:
            accumulated_dhw += hs * step_days / 7.0
        if k % samples_per_day == 0:
            predicted_sst.append(pred_temp)
            predicted_hotspot.append(hs)
            projected_dhw_list.append(accumulated_dhw)
            daily_levels.append(classify_bleaching_alert(round(hs, 2), round(accumulated_dhw, 2)))

    def first_day(min_level: BleachingAlertLevel) -> Optional[int]:
        return next((d + 1 for d, lv in enumerate(daily_levels) if lv >= min_level), None)

    days_to_warning = first_day(BleachingAlertLevel.BLEACHING_WARNING)
    days_to_alert_1 = first_day(BleachingAlertLevel.ALERT_LEVEL_1)
    days_to_alert_2 = first_day(BleachingAlertLevel.ALERT_LEVEL_2)

    # Evaluasi multi-horizon
    multi_horizon_metrics = evaluate_multi_horizon_forecasting(
        series=historical_sst,
        horizons=[1, 7, 14],
        alpha=alpha,
        beta=beta,
        damping=damping,
    )

    # Proyeksi tingkat peringatan puncak (aturan sama dengan sistem utama)
    peak = max(daily_levels) if daily_levels else BleachingAlertLevel.NO_STRESS
    proj_label = {
        BleachingAlertLevel.ALERT_LEVEL_2: "Alert Level 2 (Severe Mortality)",
        BleachingAlertLevel.ALERT_LEVEL_1: "Alert Level 1 (Significant Bleaching)",
        BleachingAlertLevel.BLEACHING_WARNING: "Bleaching Warning",
        BleachingAlertLevel.BLEACHING_WATCH: "Bleaching Watch",
        BleachingAlertLevel.NO_STRESS: "No Stress",
    }[peak]

    return ForecastTrajectory(
        horizon_days=horizon_days,
        timestamps_days=list(range(1, horizon_days + 1)),
        predicted_sst=predicted_sst,
        predicted_hotspot=predicted_hotspot,
        predicted_dhw=projected_dhw_list,
        baseline_sst=baseline_sst,
        projected_alert_level=proj_label,
        days_to_warning=days_to_warning,
        days_to_alert_1=days_to_alert_1,
        days_to_alert_2=days_to_alert_2,
        metrics=multi_horizon_metrics,
    )
