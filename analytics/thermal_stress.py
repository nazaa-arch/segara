"""
Modul Analitik Stres Termal & Degree Heating Weeks (DHW) NOAA CRW.
Mengimplementasikan:
1. Coral Bleaching HotSpot
2. Degree Heating Weeks (DHW) jendela 12 minggu (84 hari)
3. Klasifikasi Tingkat Peringatan Pemutihan Karang (5-tier NOAA)
4. Indeks Stres Gabungan (Suhu, Asidifikasi pH, Kekeruhan)
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Sequence, Tuple
import numpy as np


class BleachingAlertLevel(IntEnum):
    NO_STRESS = 0
    BLEACHING_WATCH = 1
    BLEACHING_WARNING = 2
    ALERT_LEVEL_1 = 3
    ALERT_LEVEL_2 = 4

    @property
    def label(self) -> str:
        labels = {
            BleachingAlertLevel.NO_STRESS: "No Stress",
            BleachingAlertLevel.BLEACHING_WATCH: "Bleaching Watch",
            BleachingAlertLevel.BLEACHING_WARNING: "Bleaching Warning",
            BleachingAlertLevel.ALERT_LEVEL_1: "Alert Level 1",
            BleachingAlertLevel.ALERT_LEVEL_2: "Alert Level 2",
        }
        return labels[self]

    @property
    def ecological_impact(self) -> str:
        impacts = {
            BleachingAlertLevel.NO_STRESS: "Kondisi perairan normal dan aman bagi zooxanthellae.",
            BleachingAlertLevel.BLEACHING_WATCH: "Suhu melebihi rata-rata bulanan terpanas; potensi stres awal.",
            BleachingAlertLevel.BLEACHING_WARNING: "Stres termal nyata terakumulasi; pemutihan ringan mungkin terjadi.",
            BleachingAlertLevel.ALERT_LEVEL_1: "Stres termal tinggi (DHW >= 4); pemutihan massal signifikan pada koral rentan.",
            BleachingAlertLevel.ALERT_LEVEL_2: "Stres termal ekstrem (DHW >= 8); pemutihan massal parah & risiko kematian koral luas.",
        }
        return impacts[self]


@dataclass
class ThermalStressResult:
    sst: float
    mmm: float
    hotspot: float
    dhw: float
    alert_level: BleachingAlertLevel
    compound_stress: float
    stress_breakdown: Dict[str, float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sst": round(self.sst, 2),
            "mmm": round(self.mmm, 2),
            "hotspot": round(self.hotspot, 2),
            "dhw": round(self.dhw, 2),
            "alert_level": int(self.alert_level),
            "alert_label": self.alert_level.label,
            "ecological_impact": self.alert_level.ecological_impact,
            "compound_stress": round(self.compound_stress, 3),
            "stress_breakdown": self.stress_breakdown,
        }


def compute_hotspot(sst: float, mmm: float) -> float:
    """
    Menghitung anomali HotSpot NOAA CRW.
    HotSpot = SST - MMM jika SST > MMM, selain itu 0.0.
    """
    diff = sst - mmm
    return max(0.0, round(diff, 2))


def classify_bleaching_alert(hotspot: float, dhw: float) -> BleachingAlertLevel:
    """
    Mengklasifikasikan tingkat peringatan menurut sistem 5-tingkat lama NOAA CRW:
    - No Stress:         HotSpot <= 0
    - Bleaching Watch:   0 < HotSpot < 1
    - Bleaching Warning: HotSpot >= 1 dan DHW < 4
    - Alert Level 1:     HotSpot >= 1 dan 4 <= DHW < 8
    - Alert Level 2:     HotSpot >= 1 dan DHW >= 8

    Level Warning ke atas mensyaratkan HotSpot >= 1. Setelah suhu turun, status
    kembali ke Watch / No Stress walaupun DHW masih tinggi dari akumulasi lama.
    """
    if hotspot <= 0.0:
        return BleachingAlertLevel.NO_STRESS
    if hotspot < 1.0:
        return BleachingAlertLevel.BLEACHING_WATCH
    if dhw >= 8.0:
        return BleachingAlertLevel.ALERT_LEVEL_2
    if dhw >= 4.0:
        return BleachingAlertLevel.ALERT_LEVEL_1
    return BleachingAlertLevel.BLEACHING_WARNING


def compute_dhw_from_series(
    hotspot_series: List[float],
    dt_days: float = 1.0,
    window_days: int = 84,  # 12 minggu
) -> float:
    """
    Menghitung DHW terakumulasi selama jendela 12 minggu terakhir.
    Hanya HotSpot >= 1.0°C yang diakumulasikan.
    Formula NOAA: Sum(HotSpot * (dt_days / 7)) untuk HotSpot >= 1.0
    """
    if not hotspot_series:
        return 0.0

    # Ambil elemen dalam rentang jendela 12 minggu
    points_in_window = int(round(window_days / max(0.001, dt_days)))
    recent_hotspots = hotspot_series[-points_in_window:]

    accumulated = 0.0
    for hs in recent_hotspots:
        if hs >= 1.0:
            accumulated += hs * (dt_days / 7.0)

    return round(accumulated, 2)


def compute_compound_stress(
    dhw: float,
    ph: Optional[float],
    turbidity: Optional[float],
) -> Dict[str, Any]:
    """
    Menghitung indeks stres multi-parameter koral (bobot heuristik):
    - Termal: DHW / 8, bobot 70%
    - Asidifikasi: (7,80 - pH) / 0,30 bila pH < 7,80 (penuh pada pH <= 7,50), bobot 15%
    - Kekeruhan: (NTU - 10) / 30 bila NTU > 10 (penuh pada >= 40 NTU), bobot 15%

    pH / kekeruhan bernilai ``None`` bila ditolak QC; komponennya diisi 0 dan
    ditandai tidak tersedia, sehingga skor gabungan cenderung terlalu rendah.
    """
    thermal_score = min(1.0, max(0.0, dhw / 8.0))

    ph_score = 0.0
    if ph is not None and ph < 7.80:
        ph_score = min(1.0, max(0.0, (7.80 - ph) / 0.30))

    turb_score = 0.0
    if turbidity is not None and turbidity > 10.0:
        turb_score = min(1.0, max(0.0, (turbidity - 10.0) / 30.0))

    total_compound = 0.70 * thermal_score + 0.15 * ph_score + 0.15 * turb_score

    return {
        "compound_score": round(total_compound, 3),
        "thermal_component": round(thermal_score, 3),
        "ph_component": round(ph_score, 3),
        "turbidity_component": round(turb_score, 3),
        "ph_available": ph is not None,
        "turbidity_available": turbidity is not None,
    }


def compute_dhw_from_timed_samples(
    samples: Sequence[Tuple[float, float, float]],
    now_days: float,
    window_days: float = 84.0,
) -> float:
    """
    Menghitung DHW dari sampel bertanda waktu ``(t_hari, hotspot, dt_hari)``.

    Jendela 84 hari diukur dari waktu observasi, bukan dari jumlah titik, sehingga
    paket yang hilang atau ditolak QC tidak memperpanjang jendela. Setiap sampel
    menyumbang ``hotspot * dt / 7`` bila HotSpot >= 1.
    """
    start = now_days - window_days + 1e-9
    accumulated = 0.0
    for t, hs, dt in samples:
        if start < t <= now_days + 1e-9 and hs >= 1.0:
            accumulated += hs * (dt / 7.0)
    return round(accumulated, 2)


class ThermalAnalyticsEngine:
    def __init__(self, window_days: int = 84):
        self.window_days = window_days
        # Riwayat per node: list of (t_hari, hotspot, dt_hari), urut waktu
        self._node_hotspots: Dict[int, List[Tuple[float, float, float]]] = {}

    def reset_node(self, node_id: int):
        self._node_hotspots.pop(node_id, None)

    def has_node(self, node_id: int) -> bool:
        return node_id in self._node_hotspots

    def seed_history(
        self,
        node_id: int,
        samples: Sequence[Tuple[datetime, float, float]],
    ) -> None:
        """Memuat ulang riwayat HotSpot (mis. dari DB) setelah proses restart."""
        self._node_hotspots[node_id] = sorted(
            (_to_days(ts), float(hs), float(dt)) for ts, hs, dt in samples
        )

    def process_telemetry(
        self,
        node_id: int,
        sst: float,
        mmm: float,
        ph: Optional[float],
        turbidity: Optional[float],
        dt_days: float = 1.0,
        observed_at: Optional[datetime] = None,
    ) -> ThermalStressResult:
        """
        Memproses satu pembacaan telemetri untuk menghitung HotSpot, DHW,
        level peringatan NOAA CRW, dan indeks stres multi-parameter.

        ``observed_at`` adalah waktu observasi. Bila tidak diberikan, waktu
        diasumsikan maju ``dt_days`` dari sampel sebelumnya.
        """
        hotspot = compute_hotspot(sst, mmm)

        history = self._node_hotspots.setdefault(node_id, [])
        if observed_at is not None:
            t_now = _to_days(observed_at)
        else:
            t_now = (history[-1][0] + dt_days) if history else 0.0
        history.append((t_now, hotspot, dt_days))

        # Buang sampel yang sudah keluar dari jendela 84 hari
        cutoff = t_now - self.window_days + 1e-9
        while history and history[0][0] <= cutoff:
            history.pop(0)

        dhw = compute_dhw_from_timed_samples(history, now_days=t_now, window_days=self.window_days)
        alert_level = classify_bleaching_alert(hotspot, dhw)
        compound = compute_compound_stress(dhw, ph, turbidity)

        return ThermalStressResult(
            sst=sst,
            mmm=mmm,
            hotspot=hotspot,
            dhw=dhw,
            alert_level=alert_level,
            compound_stress=compound["compound_score"],
            stress_breakdown=compound,
        )


def _to_days(ts: datetime) -> float:
    """Konversi datetime ke hari sejak epoch (datetime naif dianggap UTC)."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.timestamp() / 86400.0
