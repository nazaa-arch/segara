"""Pengujian modul evaluasi (api/routers/evaluation.py).

Fokus pengujian ini adalah *struktur dan determinisme* keluaran evaluasi,
bukan angka ilmiahnya. Setiap fungsi evaluasi memakai seed tertentu atau
seri sintetis tertutup, sehingga hasilnya harus identik antar pemanggilan.

Angka yang dipakai sebagai assertion di sini adalah angka desain kasus uji
(mis. deteksi pertama pada siklus ke-6), bukan klaim akurasi lapangan.
"""

import pytest

from api.routers.evaluation import (
    run_packet_loss_monte_carlo,
    run_qc_functional_test,
    run_dhw_algorithmic_verification,
    run_forecasting_evaluation,
)
from analytics.forecasting import evaluate_multi_horizon_forecasting


# --------------------------------------------------------------------------
# Packet loss Monte Carlo
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def mc_small():
    """Monte Carlo 5 seed; cukup untuk uji struktur dan determinisme."""
    return run_packet_loss_monte_carlo(num_seeds=5)


def test_monte_carlo_structure(mc_small):
    assert set(mc_small) == {"loss_5pct", "loss_10pct", "loss_20pct"}
    for key, payload in mc_small.items():
        assert payload["monte_carlo_runs"] == 5
        assert payload["telemetry_interval_hours"] == 6.0
        # Setiap run harus masuk salah satu kategori delay.
        assert (
            payload["alert_1_delay_valid_runs"]
            + payload["alert_1_delay_unavailable_runs"]
            == 5
        )
        assert "Forward fill" in payload["missing_packet_strategy"]
        assert "Paired synthetic" in payload["reference_design"]
        assert payload["reproducibility"]


def test_monte_carlo_pdr_tracks_injected_loss(mc_small):
    """PDR yang terukur harus dekat dengan loss yang disuntikkan."""
    expected = {"loss_5pct": 95.0, "loss_10pct": 90.0, "loss_20pct": 80.0}
    for key, target in expected.items():
        pdr = mc_small[key]["measured_pdr_mean"]
        assert abs(pdr - target) < 5.0, f"{key}: PDR {pdr} menyimpang dari {target}"


def test_monte_carlo_dhw_error_increases_with_loss(mc_small):
    mae_5 = mc_small["loss_5pct"]["dhw_error_mae_mean"]
    mae_10 = mc_small["loss_10pct"]["dhw_error_mae_mean"]
    mae_20 = mc_small["loss_20pct"]["dhw_error_mae_mean"]
    # Hubungan ini tidak harus linier, tetapi harus monoton pada desain ini.
    assert mae_5 <= mae_10 <= mae_20


def test_monte_carlo_is_deterministic():
    first = run_packet_loss_monte_carlo(num_seeds=5)
    second = run_packet_loss_monte_carlo(num_seeds=5)
    assert first == second


# --------------------------------------------------------------------------
# QC fungsional
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qc():
    return run_qc_functional_test()


def test_qc_declares_its_scope(qc):
    assert "fungsional" in qc["test_type"].lower()
    assert "bukan akurasi" in qc["scope_note"].lower() or "bukan" in qc["scope_note"].lower()
    assert qc["limitations"]


def test_qc_clean_control_has_no_critical_flags(qc):
    counts = qc["clean_control"]["critical_flag_counts_per_rule"]
    assert qc["clean_control"]["cycles"] == 120
    assert all(value == 0 for value in counts.values()), counts


def test_qc_stuck_rule_detects_at_window_boundary(qc):
    case = qc["stuck_rule_case"]
    assert case["first_detection_cycle"] == case["expected_first_detection_cycle"]
    assert case["first_detection_cycle"] == case["window_cycles"]


def test_qc_drift_rule_detects_at_window_boundary(qc):
    case = qc["drift_rule_case"]
    assert case["first_detection_cycle"] == case["expected_first_detection_cycle"]
    assert case["first_detection_cycle"] == case["window_cycles"]


def test_qc_range_rule_detects_all_out_of_range(qc):
    case = qc["range_rule_case"]
    assert case["detected_count"] == case["trials"]


def test_qc_spike_curve_is_monotone_in_delta(qc):
    curve = list(qc["spike_sensitivity_curve"].values())
    deltas = [row["spike_delta_celsius"] for row in curve]
    detected = [row["detected_count"] for row in curve]
    assert deltas == sorted(deltas)
    assert detected == sorted(detected)
    # Ambang 1,5 C dengan aturan ketat ">" tidak boleh menandai tepat di ambang.
    at_threshold = next(
        row for row in curve if row["spike_delta_celsius"] == row["threshold_celsius"]
    )
    assert at_threshold["detected_count"] == 0


def test_qc_spike_false_positive_control(qc):
    case = qc["spike_false_positive_control"]
    assert case["spike_flag_count"] == 0
    assert case["subthreshold_bumps_celsius"] < 1.5


# --------------------------------------------------------------------------
# DHW
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def dhw():
    return run_dhw_algorithmic_verification()


def test_dhw_report_is_not_labelled_noaa_validation(dhw):
    assert "bukan validasi" in dhw["verification_type"].lower()
    assert "tidak terbukti" in dhw["reference_source"]["provenance_status"].lower()
    assert "bukan produk crw independen" in dhw["reference_source"]["reference_kind"].lower()


def test_dhw_reference_is_internally_inconsistent(dhw):
    check = dhw["internal_consistency_check"]
    assert check["window_covers_entire_series"] is True
    assert check["computed_dhw_decrease_steps"] == 0
    assert check["reference_dhw_decrease_steps"] > 0
    assert check["verdict"]


def test_dhw_alert_levels_flagged_as_legacy(dhw):
    version = dhw["noaa_alert_system_version"]
    assert "legacy" in version["implemented_version"].lower()
    assert version["note_on_2023_revision"]


# --------------------------------------------------------------------------
# Forecasting
# --------------------------------------------------------------------------


def test_forecast_evaluation_withholds_metrics():
    payload = run_forecasting_evaluation()
    assert payload["status"] == "not_evaluated"
    assert payload["horizon_benchmarks"] is None
    assert payload["samples_node_1"] < payload["requirements"]["minimum_samples"]
    assert payload["cadence_days"] > 1.0


def test_multi_horizon_rejects_short_series():
    # Deret jauh lebih pendek dari kebutuhan minimum rolling-origin.
    series = [28.0 + 0.05 * i for i in range(12)]
    payload = evaluate_multi_horizon_forecasting(series, horizons=[1, 7, 14], step_days=1.0)
    assert payload["status"] == "insufficient_data"
    assert payload["available_samples"] == len(series)
    assert payload["minimum_samples_required"] > len(series)


def test_multi_horizon_collapses_at_five_day_cadence():
    """Pada jarak 5 hari, horizon 1 dan 7 hari menjadi satu langkah yang sama.

    Ini alasan metrik peramalan pada deret replay tidak dipublikasikan: horizon
    harian tidak dapat dibedakan, sehingga angka MAE per horizon menyesatkan.
    """
    series = [28.0 + 0.05 * i for i in range(17)]
    payload = evaluate_multi_horizon_forecasting(series, horizons=[1, 7, 14], step_days=5.0)
    assert payload["step_days"] == 5.0
    steps = {
        h: payload[f"horizon_{h}_days"]["horizon_steps"]
        for h in (1, 7, 14)
    }
    assert steps[1] == 1
    assert steps[7] == 1  # 7 hari / 5 hari per langkah -> tetap 1 langkah
    assert steps[1] == steps[7]


def test_multi_horizon_runs_on_daily_series():
    # Deret harian 60 sampel harus cukup untuk horizon 1/7/14 hari.
    series = [28.5 + 1.2 * (i / 59.0) for i in range(60)]
    payload = evaluate_multi_horizon_forecasting(series, horizons=[1, 7, 14], step_days=1.0)
    assert payload["status"] == "ok"
    for horizon in (1, 7, 14):
        row = payload[f"horizon_{horizon}_days"]
        assert row["evaluated_origins"] > 0
        assert row["horizon_steps"] == horizon
        assert "improvement_vs_persistence_pct" in row