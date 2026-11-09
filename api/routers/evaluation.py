"""
Router REST API: Evaluasi Kinerja Ilmiah & Pengujian Benchmark Sistem SEGARA.
Menghasilkan metrik kuantitatif berbasis pengujian:
1. Monte Carlo (100 Seeds) Dampak Rugi Paket (5%, 10%, 20%) terhadap Galat DHW & Keterlambatan Peringatan
2. Uji Fungsional Verifikasi Aturan Quality Control (Kurva Sensitivitas Lonjakan, Stuck, Drift, Range)
3. Evaluasi Peramalan Suhu Multi-Horizon (1, 7, 14 Hari) vs Baseline Persistence
4. Verifikasi Numerik Formula DHW & Analisis Galat Kuantisasi 12-Byte
5. Profil Latensi Komputasi Dalam-Proses (In-Process CPU Execution Latency)
"""
from fastapi import APIRouter, Query
from typing import Dict, Any, List, Optional
import os
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
import numpy as np
from simulator.generator import CoralBuoySimulator, FaultConfig
from simulator.replay import HistoricalReplayEngine
from simulator.encoder import encode_telemetry
from ingestion.subscriber import IngestionPipeline
from ingestion.database import init_db, _SESSION_FACTORIES
from qc.rules import QualityControlEngine, QCFlag
from analytics.thermal_stress import compute_hotspot, compute_dhw_from_series
from analytics.forecasting import evaluate_multi_horizon_forecasting

router = APIRouter(prefix="/api/evaluation", tags=["Evaluation"])


def run_packet_loss_monte_carlo(num_seeds: int = 100) -> Dict[str, Any]:
    """Estimate packet-loss effects on paired synthetic SST paths."""
    node_id, total_steps, dt_days = 1, 80, 0.25
    rates = [0.05, 0.10, 0.20]
    grouped: Dict[float, Dict[str, List[float]]] = {
        r: {"pdr": [], "mae": [], "max_bias": [], "delay": []} for r in rates
    }

    # Jam simulasi dipatok ke epoch tetap agar hasil dapat direproduksi
    # Dipatok ke pertengahan tahun agar variasi musiman mendekati maksimum,
    # sehingga ambang Alert 1 tercapai dengan margin pada semua seed.
    sim_epoch = datetime(2020, 6, 15, tzinfo=timezone.utc)

    for seed_idx in range(num_seeds):
        sim = CoralBuoySimulator(seed=1000 + seed_idx)
        sim.set_heatwave(node_id, active=True, intensity=2.3)
        sim.buoys[node_id].faults.packet_loss_rate = 0.0
        hotspots: List[float] = []
        for step in range(total_steps):
            pkt = sim.generate_next_packet(
                node_id, sim_time=sim_epoch + timedelta(hours=6.0 * (step + 1))
            )
            if pkt is not None:
                hotspots.append(compute_hotspot(pkt.temperature, sim.buoys[node_id].mmm))
            else:
                hotspots.append(hotspots[-1] if hotspots else 0.0)
        reference = np.asarray([
            compute_dhw_from_series(hotspots[:i + 1], dt_days=dt_days, window_days=84)
            for i in range(total_steps)
        ])
        ref_alert = next((i for i, value in enumerate(reference) if value >= 4.0), None)

        for rate_idx, rate in enumerate(rates):
            rng = np.random.default_rng(500000 + seed_idx * 10 + rate_idx)
            keep = rng.random(total_steps) >= rate
            observed: List[float] = []
            for i in range(total_steps):
                if keep[i]:
                    observed.append(hotspots[i])
                else:
                    observed.append(observed[-1] if observed else 0.0)
            estimated = np.asarray([
                compute_dhw_from_series(observed[:i + 1], dt_days=dt_days, window_days=84)
                for i in range(total_steps)
            ])
            values = grouped[rate]
            values["pdr"].append(float(np.mean(keep) * 100.0))
            errors = np.abs(reference - estimated)
            values["mae"].append(float(np.mean(errors)))
            values["max_bias"].append(float(np.max(errors)))
            alert = next((i for i, value in enumerate(estimated) if value >= 4.0), None)
            if ref_alert is not None and alert is not None:
                values["delay"].append(float(max(0, alert - ref_alert) * dt_days))

    results: Dict[str, Any] = {}
    for rate in rates:
        values = grouped[rate]
        delay = np.asarray(values["delay"], dtype=float)
        results[f"loss_{int(rate * 100)}pct"] = {
            "target_loss_rate_pct": rate * 100,
            "monte_carlo_runs": num_seeds,
            "telemetry_interval_hours": 6.0,
            "missing_packet_strategy": "Forward fill; initial missing values use 0 hotspot",
            "reference_design": "Paired synthetic SST path per seed; independent Bernoulli loss mask",
            "reproducibility": (
                "Simulator seeds 1000..{0}; mask seeds 500000+10*seed+rate_index; "
                "sim clock pinned to 2020-06-15T00:00Z with 6-hour steps".format(1000 + num_seeds - 1)
            ),
            "measured_pdr_mean": round(float(np.mean(values["pdr"])), 2),
            "measured_pdr_std": round(float(np.std(values["pdr"])), 2),
            "dhw_error_mae_mean": round(float(np.mean(values["mae"])), 4),
            "dhw_error_mae_std": round(float(np.std(values["mae"])), 4),
            "max_dhw_bias_mean": round(float(np.mean(values["max_bias"])), 4),
            "alert_1_delay_days_mean": round(float(np.mean(delay)), 3) if delay.size else None,
            "alert_1_delay_days_std": round(float(np.std(delay)), 3) if delay.size else None,
            "alert_1_delay_valid_runs": int(delay.size),
            "alert_1_delay_unavailable_runs": int(num_seeds - delay.size),
        }
    return results


def run_qc_functional_test() -> Dict[str, Any]:
    """Uji fungsional aturan QC pada kasus sintetis terisolasi per aturan.

    Bukan estimasi akurasi: setiap aturan diuji dengan seri yang dirancang agar
    hanya aturan tersebut yang relevan, dan kontrol "bersih" memakai variasi
    terbatas supaya aturan stuck tidak ikut menyala.
    """
    qc = QualityControlEngine(stuck_window_size=6, drift_window_size=24)
    node_id, counter = 7, 1

    def feed(temp: float, ph: float, salinity: float, turbidity: float) -> Any:
        nonlocal counter
        result = qc.evaluate(
            node_id, counter, temperature=temp, ph=ph,
            salinity=salinity, turbidity=turbidity, battery=90,
        )
        counter += 1
        return result

    def varying(i: int, temp_delta: float = 0.0):
        # Variasi kecil non-konstan pada semua parameter agar aturan stuck tidak menyala.
        return (
            28.4 + 0.25 * np.sin(i * 0.7) + temp_delta,
            8.15 + 0.01 * np.sin(i * 0.9),
            34.2 + 0.03 * np.cos(i * 0.6),
            2.0 + 0.15 * np.sin(i * 1.3),
        )

    # --- Kontrol bersih: variasi terbatas, seharusnya tidak ada flag kritis ---
    qc.reset_node(node_id)
    clean_cycles = 120
    clean_flag_counts: Dict[str, int] = {
        "RANGE_FAIL": 0, "SPIKE_FAIL": 0, "STUCK_FAIL": 0, "DRIFT_FAIL": 0,
    }
    for i in range(clean_cycles):
        t, ph, sal, turb = varying(i)
        res = qc.evaluate(node_id, counter, temperature=t, ph=ph,
                          salinity=sal, turbidity=turb, battery=90)
        counter += 1
        for name in clean_flag_counts:
            if res.flags & getattr(QCFlag, name):
                clean_flag_counts[name] += 1

    # --- Kurva sensitivitas spike: delta 0.5 s.d. 3.5 C, ambang 1.5 C (delta > ambang) ---
    spike_curve: Dict[str, Any] = {}
    for mag in [0.5, 0.8, 1.2, 1.5, 1.8, 2.5, 3.5]:
        hits, trials = 0, 5
        for trial in range(trials):
            qc.reset_node(node_id)
            base_t, ph, sal, turb = varying(trial)
            feed(base_t, ph, sal, turb)
            res = feed(base_t + mag, ph, sal, turb)
            hits += int(bool(res.flags & QCFlag.SPIKE_FAIL))
        spike_curve[f"delta_{mag}C"] = {
            "spike_delta_celsius": mag,
            "threshold_celsius": 1.5,
            "trials": trials,
            "detected_count": hits,
            "detection_rate_pct": round(100.0 * hits / trials, 1),
            "expected": "flagged" if mag > 1.5 else "not flagged (delta > threshold rule)",
        }

    # --- Stuck: nilai konstan 10 siklus, jendela 6 -> flag mulai siklus ke-6 ---
    qc.reset_node(node_id)
    stuck_first_detection = None
    stuck_detections = 0
    for i in range(10):
        res = qc.evaluate(node_id, counter, temperature=29.0, ph=8.15,
                          salinity=34.2, turbidity=2.0, battery=90)
        counter += 1
        if res.flags & QCFlag.STUCK_FAIL:
            stuck_detections += 1
            if stuck_first_detection is None:
                stuck_first_detection = i + 1
    stuck_case = {
        "cycles": 10, "window_cycles": 6, "constant_value": 29.0,
        "detected_cycles": stuck_detections,
        "first_detection_cycle": stuck_first_detection,
        "expected_first_detection_cycle": 6,
    }

    # --- Drift: pH turun 0.02 per siklus selama 40 siklus, jendela 24 ---
    qc.reset_node(node_id)
    drift_first_detection = None
    drift_detections = 0
    for i in range(40):
        res = qc.evaluate(node_id, counter, temperature=28.5, ph=8.15 - 0.02 * (i + 1),
                          salinity=34.2, turbidity=2.0, battery=90)
        counter += 1
        if res.flags & QCFlag.DRIFT_FAIL:
            drift_detections += 1
            if drift_first_detection is None:
                drift_first_detection = i + 1
    drift_case = {
        "cycles": 40, "window_cycles": 24, "ph_slope_per_cycle": -0.02,
        "threshold_slope_abs": 0.015,
        "detected_cycles": drift_detections,
        "first_detection_cycle": drift_first_detection,
        "expected_first_detection_cycle": 24,
    }

    # --- Range: 15 paket suhu di luar batas fisik ---
    qc.reset_node(node_id)
    range_hits = 0
    for trial in range(15):
        res = qc.evaluate(node_id, counter, temperature=45.0 + trial, ph=8.15,
                          salinity=34.2, turbidity=2.0, battery=90)
        counter += 1
        range_hits += int(bool(res.flags & QCFlag.RANGE_FAIL))
    range_case = {"trials": 15, "detected_count": range_hits,
                  "valid_range_celsius": [20.0, 35.0]}

    # --- Kombinasi lonjakan di bawah ambang di dalam seri bersih (kontrol FP spike) ---
    qc.reset_node(node_id)
    subthreshold_spike_hits = 0
    for i in range(30):
        delta = 0.4 if i % 5 == 0 else 0.0
        t, ph, sal, turb = varying(i, temp_delta=delta)
        res = qc.evaluate(node_id, counter, temperature=t, ph=ph,
                          salinity=sal, turbidity=turb, battery=90)
        counter += 1
        subthreshold_spike_hits += int(bool(res.flags & QCFlag.SPIKE_FAIL))

    return {
        "test_type": "Uji fungsional aturan QC pada kasus sintetis terisolasi",
        "scope_note": (
            "Kasus dibangun manual dan dijalankan in-process; hasilnya menggambarkan "
            "perilaku aturan pada seri uji ini, bukan akurasi lapangan atau presisi umum."
        ),
        "clean_control": {
            "cycles": clean_cycles,
            "design": "Variasi sinusoidal terbatas pada 4 parameter; tanpa pelanggaran yang disengaja",
            "critical_flag_counts_per_rule": clean_flag_counts,
        },
        "spike_sensitivity_curve": spike_curve,
        "stuck_rule_case": stuck_case,
        "drift_rule_case": drift_case,
        "range_rule_case": range_case,
        "spike_false_positive_control": {
            "cycles": 30, "subthreshold_bumps_celsius": 0.4,
            "spike_flag_count": subthreshold_spike_hits,
        },
        "limitations": [
            "Tidak ada ground truth lapangan; kasus dibangun dari spesifikasi aturan.",
            "Ambang dan jendela mengikuti implementasi saat ini, bukan standar eksternal.",
            "Tidak menguji packet loss, baterai rendah, atau duplikasi counter.",
        ],
    }


def run_dhw_algorithmic_verification() -> Dict[str, Any]:
    """Uji konsistensi internal implementasi DHW terhadap kolom pembanding di CSV.

    Ini BUKAN validasi terhadap produk NOAA. Kurva acuan berasal dari berkas
    `data/historical_noaa_indonesia.csv` yang mendeskripsikan dirinya sebagai
    rekonstruksi, dan provenance kolom `dhw_official` tidak terdokumentasi.
    """
    replay = HistoricalReplayEngine()
    records = replay.records_by_node.get(1, [])
    if not records:
        return {"status": "no_data", "reason": "CSV tidak memuat rekaman untuk node 1."}

    calculated, official, hotspots = [], [], []
    for r in records:
        hotspots.append(compute_hotspot(r.sst, r.mmm))
        calculated.append(compute_dhw_from_series(hotspots, dt_days=5.0, window_days=84))
        official.append(r.dhw_official)

    calc_arr = np.asarray(calculated, dtype=float)
    off_arr = np.asarray(official, dtype=float)
    residual = calc_arr - off_arr

    span_days = 5.0 * (len(records) - 1)
    window_holds_all = span_days <= 84.0
    decreases = int(np.sum(np.diff(off_arr) < -1e-9))
    calc_decreases = int(np.sum(np.diff(calc_arr) < -1e-9))

    return {
        "verification_type": "Uji konsistensi internal (bukan validasi NOAA)",
        "reference_source": {
            "file": "data/historical_noaa_indonesia.csv",
            "provenance_status": "tidak terbukti sebagai unduhan NOAA; header menyebut rekonstruksi",
            "records_node_1": len(records),
            "cadence_days": 5.0,
            "reference_kind": "kolom dhw_official pada berkas yang sama, bukan produk CRW independen",
        },
        "agreement_with_reference_column": {
            "mae_celsius_weeks": round(float(np.mean(np.abs(residual))), 3),
            "rmse_celsius_weeks": round(float(np.sqrt(np.mean(residual ** 2))), 3),
            "pearson_correlation": round(float(np.corrcoef(calc_arr, off_arr)[0, 1]), 4)
            if len(calc_arr) > 1 else None,
            "note": (
                "Kesesuaian hanya berarti implementasi mereproduksi kolom pembanding pada "
                "berkas yang sama. Tidak ada pembanding NOAA independen."
            ),
        },
        "internal_consistency_check": {
            "observation_span_days": span_days,
            "window_days": 84,
            "window_covers_entire_series": bool(window_holds_all),
            "expected_behaviour": (
                "DHW adalah jumlah bergerak 84 hari; bila seluruh seri berada di dalam "
                "jendela, nilai akumulasi tidak boleh menurun."
            ),
            "computed_dhw_decrease_steps": calc_decreases,
            "reference_dhw_decrease_steps": decreases,
            "reference_first_decrease_index": int(np.argmax(np.diff(off_arr) < -1e-9)) + 1
            if decreases else None,
            "verdict": (
                "Kolom pembanding menurun meski jendela 84 hari belum tergeser, sehingga "
                "kolom itu tidak konsisten dengan akumulasi HotSpot pada berkas yang sama."
                if decreases and window_holds_all and calc_decreases == 0
                else "Tidak ada pelanggaran monotonisitas yang terdeteksi."
            ),
        },
        "noaa_alert_system_version": {
            "implemented_version": "SEGARA legacy 5-tier approximation; not a current NOAA CRW implementation",
            "levels": ["No Stress", "Bleaching Watch", "Bleaching Warning", "Alert Level 1", "Alert Level 2"],
            "note_on_2023_revision": (
                "Label/ambang ini tidak boleh ditafsirkan sebagai sistem peringatan CRW terkini; "
                "ambang resmi terbaru belum diverifikasi dan belum diimplementasikan."
            ),
        },
    }


def run_forecasting_evaluation() -> Dict[str, Any]:
    """Backtest peramalan pada deret SST yang tersedia di CSV replay.

    Deret CSV berspasi 5 hari dan hanya 17 titik untuk node 1, sehingga horizon
    harian tidak dapat dievaluasi. Tidak ada deret sintetis pengganti: bila data
    tidak memenuhi syarat, hasilnya dilaporkan sebagai tidak tersedia.
    """
    replay = HistoricalReplayEngine()
    records = replay.records_by_node.get(1, [])
    series = [r.sst for r in records]

    return {
        "status": "not_evaluated",
        "reason": (
            "Deret replay tidak memenuhi syarat backtest: sampel terlalu sedikit "
            "dan berjarak 5 hari, sehingga horizon 1/7/14 hari tidak dapat diuji."
        ),
        "data_source": "data/historical_noaa_indonesia.csv (rekonstruksi, bukan unduhan NOAA terverifikasi)",
        "cadence_days": 5.0,
        "samples_node_1": len(series),
        "requirements": {
            "daily_series_required_for_daily_horizons": True,
            "minimum_samples": 30,
        },
        "horizon_benchmarks": None,
        "note": (
            "Metrik sebelumnya pada laporan lama berasal dari deret sintetis pengganti "
            "dan sudah dicabut. Tidak ada angka peramalan yang dipublikasikan sampai "
            "tersedia deret SST harian yang sah."
        ),
    }


def run_in_process_latency_benchmark() -> Dict[str, Any]:
    """
    Mengukur profil latensi komputasi DALAM-PROSES (In-Process CPU Execution Latency).
    """
    sim = CoralBuoySimulator(seed=300)
    node_id = 1

    # Benchmark memakai DB SQLite sementara yang terpisah. Sebelumnya benchmark
    # menulis 100 paket palsu ke segara.db live (mencemari jam & DHW node 1 dan
    # dapat memicu alert palsu, bahkan pesan Telegram bila kredensial terpasang).
    latencies_ms = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        bench_url = "sqlite:///" + os.path.join(tmp, "bench.db").replace("\\", "/")
        session_factory = init_db(bench_url)
        pipeline = IngestionPipeline(db_session_factory=session_factory)
        pipeline.alert_dispatcher.telegram_token = None  # jangan kirim notifikasi nyata
        try:
            for _ in range(100):
                pkt = sim.generate_next_packet(node_id)
                if pkt:
                    t0 = time.perf_counter()
                    raw = encode_telemetry(pkt)
                    pipeline.process_raw_message(f"segara/telemetry/{node_id}", raw)
                    latencies_ms.append((time.perf_counter() - t0) * 1000.0)
        finally:
            session_factory.kw["bind"].dispose()
            _SESSION_FACTORIES.pop(bench_url, None)

    return {
        "benchmark_scope": "Latensi Komputasi Dalam-Proses CPU (In-Process Execution Latency)",
        "excluded_layers": [
            "Physical LoRaWAN Radio Time-on-Air (estimasi ~50-300 ms tergantung Spreading Factor SF7-SF12)",
            "Gateway-to-Network-Server Backhaul Latency (estimasi ~100-1000 ms via seluler/satelit)",
            "External MQTT Network Socket Roundtrip (estimasi ~5-50 ms)",
        ],
        "total_runs": len(latencies_ms),
        "mean_latency_ms": round(float(np.mean(latencies_ms)), 2),
        "median_latency_ms": round(float(np.median(latencies_ms)), 2),
        "p95_latency_ms": round(float(np.percentile(latencies_ms, 95)), 2),
        "p99_latency_ms": round(float(np.percentile(latencies_ms, 99)), 2),
    }


_metrics_cache: Optional[Dict[str, Any]] = None
_metrics_lock = threading.Lock()


@router.get("/metrics")
def get_evaluation_metrics(
    refresh: bool = Query(False, description="Hitung ulang alih-alih memakai cache"),
):
    """
    Mengambil kompilasi seluruh metrik evaluasi ilmiah sistem SEGARA.

    Komputasi memakan beberapa detik dan hasilnya deterministik (kecuali latensi),
    sehingga disimpan di cache proses. Pakai ``?refresh=true`` untuk menghitung ulang.
    """
    global _metrics_cache
    with _metrics_lock:
        if _metrics_cache is None or refresh:
            _metrics_cache = _compute_evaluation_metrics()
        return _metrics_cache


def warm_metrics_cache() -> None:
    """Dipanggil saat startup (di thread latar) agar tab Evaluasi langsung siap."""
    global _metrics_cache
    with _metrics_lock:
        if _metrics_cache is None:
            _metrics_cache = _compute_evaluation_metrics()


def _compute_evaluation_metrics() -> Dict[str, Any]:
    mc_loss = run_packet_loss_monte_carlo(num_seeds=100)
    qc_test = run_qc_functional_test()
    dhw_verif = run_dhw_algorithmic_verification()
    forecast_eval = run_forecasting_evaluation()
    latency = run_in_process_latency_benchmark()

    return {
        "system_name": "SEGARA (Sistem Early-warning Gangguan termal Atas terumbu kaRAng)",
        "evaluation_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "packet_loss_monte_carlo": mc_loss,
        "quality_control_functional_verification": qc_test,
        "dhw_algorithmic_verification": dhw_verif,
        "forecasting_multi_horizon_evaluation": forecast_eval,
        "in_process_execution_latency": latency,
    }
