"""
Aturan Kendali Mutu (Quality Control) SEGARA.
Menyediakan pengecekan: Rentang Fisik, Lonjakan (Spike), Sensor Macet (Stuck),
Penyimpangan Tren (Drift, pH saja), Paket Hilang, Paket Ganda, dan Baterai Rendah.

Flag dicatat dua kali:
- ``QCResult.flags``: gabungan seluruh flag paket (untuk ringkasan & kompatibilitas).
- ``QCResult.param_flags``: flag per parameter, sehingga sensor pH yang rusak tidak
  membuang data suhu yang sah untuk perhitungan DHW.
"""
from __future__ import annotations
from enum import IntFlag, auto
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import numpy as np


class QCFlag(IntFlag):
    PASS = 0
    RANGE_FAIL = auto()       # 1: Nilai di luar rentang fisik
    SPIKE_FAIL = auto()       # 2: Lonjakan ekstrem terhadap nilai valid terakhir
    STUCK_FAIL = auto()       # 4: Nilai konstan / varians nol
    DRIFT_FAIL = auto()       # 8: Penyimpangan tren tidak wajar (pH)
    PACKET_LOSS = auto()      # 16: Indikasi paket terlewat dari sequence counter
    BATTERY_LOW = auto()      # 32: Baterai di bawah ambang aman (< 15%)
    DUPLICATE = auto()        # 64: Counter sama dengan paket sebelumnya (paket ganda)


# Flag yang membuat suatu nilai tidak layak dipakai analitik
CRITICAL_FLAGS = QCFlag.RANGE_FAIL | QCFlag.SPIKE_FAIL | QCFlag.STUCK_FAIL | QCFlag.DUPLICATE

SENSOR_PARAMS = ("temperature", "ph", "salinity", "turbidity")

# Ambang batas fisik valid (Physical Bounds)
RANGE_LIMITS = {
    "temperature": (20.0, 35.0),  # °C
    "ph": (7.5, 8.5),
    "salinity": (30.0, 37.0),     # PSU
    "turbidity": (0.0, 100.0),    # NTU
    "battery": (0, 100),          # %
}

# Ambang batas laju perubahan maksimum per siklus (Spike Limits)
SPIKE_LIMITS = {
    "temperature": 1.5,   # °C
    "ph": 0.4,
    "salinity": 2.0,      # PSU
    "turbidity": 35.0,    # NTU
}

# Bila N pembacaan berturut-turut menyimpang dari nilai valid terakhir, dianggap
# pergeseran level nyata (mis. sensor dipindah) dan acuan spike disetel ulang.
SPIKE_REBASELINE_CYCLES = 3

# Ambang drift pH: |kemiringan| > 0,015 unit pH per siklus dalam jendela drift
DRIFT_PH_SLOPE_LIMIT = 0.015

# Ambang baterai rendah
BATTERY_LOW_THRESHOLD = 15  # %

# Selisih counter (mod 65536) di atas nilai ini dianggap counter mundur / node reboot,
# bukan ribuan paket hilang.
COUNTER_RESET_THRESHOLD = 32768


def default_stuck_windows(base: int) -> Dict[str, int]:
    """
    Jendela sensor macet per parameter (heuristik, bukan standar eksternal).

    Resolusi payload berbeda per parameter (suhu 0,01 °C dengan variasi diurnal
    ~0,35 °C; pH 0,01; salinitas 0,01 PSU yang nyaris statis; kekeruhan 0,1 NTU yang
    di air jernih sering konstan). Parameter yang secara alami stabil diberi jendela
    lebih panjang agar tidak memicu alarm palsu.
    """
    return {
        "temperature": base,
        "ph": base + 2,
        "salinity": base * 2,
        "turbidity": base * 2,
    }


@dataclass
class QCResult:
    flags: QCFlag = QCFlag.PASS
    details: Dict[str, Any] = field(default_factory=dict)
    packet_loss_count: int = 0
    param_flags: Dict[str, QCFlag] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        """True bila seluruh paket bebas pelanggaran kritis (semua parameter)."""
        return not bool(self.flags & CRITICAL_FLAGS)

    def is_param_valid(self, param: str) -> bool:
        """True bila parameter ini layak dipakai analitik."""
        if self.flags & QCFlag.DUPLICATE:
            return False
        return not bool(self.param_flags.get(param, QCFlag.PASS) & CRITICAL_FLAGS)

    def invalid_params(self) -> List[str]:
        return [p for p in (*SENSOR_PARAMS, "battery") if not self.is_param_valid(p)]

    def flag_names(self) -> List[str]:
        names = []
        for flag in QCFlag:
            if flag != QCFlag.PASS and (self.flags & flag):
                names.append(flag.name)
        return names if names else ["PASS"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "flag_mask": int(self.flags),
            "flag_names": self.flag_names(),
            "is_valid": self.is_valid,
            "invalid_params": self.invalid_params(),
            "packet_loss_count": self.packet_loss_count,
            "details": self.details,
        }


class QualityControlEngine:
    def __init__(
        self,
        stuck_window_size: int = 6,
        drift_window_size: int = 24,
        stuck_windows: Optional[Dict[str, int]] = None,
    ):
        self.stuck_window_size = stuck_window_size
        self.drift_window_size = drift_window_size
        self.stuck_windows = stuck_windows or default_stuck_windows(stuck_window_size)
        # State memori per node_id: riwayat pengukuran terakhir (nilai mentah)
        self._history: Dict[int, List[Dict[str, Any]]] = {}
        self._last_counter: Dict[int, int] = {}
        # Acuan spike per node: nilai valid terakhir & jumlah spike berturut-turut
        self._last_good: Dict[int, Dict[str, float]] = {}
        self._spike_run: Dict[int, Dict[str, int]] = {}

    def set_last_counter(self, node_id: int, counter: int) -> None:
        """Memulihkan counter terakhir (mis. dari DB) setelah proses restart."""
        self._last_counter[node_id] = counter

    def has_node(self, node_id: int) -> bool:
        return node_id in self._last_counter

    def reset_node(self, node_id: int):
        for store in (self._history, self._last_counter, self._last_good, self._spike_run):
            store.pop(node_id, None)

    def evaluate(
        self,
        node_id: int,
        counter: int,
        temperature: float,
        ph: float,
        salinity: float,
        turbidity: float,
        battery: int,
    ) -> QCResult:
        """Mengevaluasi satu paket data terhadap semua aturan QC."""
        current_data = {
            "temperature": temperature,
            "ph": ph,
            "salinity": salinity,
            "turbidity": turbidity,
            "battery": battery,
        }
        flags = QCFlag.PASS
        param_flags: Dict[str, QCFlag] = {p: QCFlag.PASS for p in current_data}
        details: Dict[str, Any] = {}
        packet_loss_count = 0

        # 1. Cek Sequence Counter (Packet Loss, Duplikat, Reset)
        if node_id in self._last_counter:
            prev_counter = self._last_counter[node_id]
            diff = (counter - prev_counter) % 65536
            if diff == 0:
                # Paket ganda: jangan simpan ke riwayat agar spike/stuck/drift
                # dan DHW tidak terhitung dua kali.
                details["duplicate_packet"] = counter
                return QCResult(
                    flags=QCFlag.DUPLICATE,
                    details=details,
                    param_flags={p: QCFlag.DUPLICATE for p in current_data},
                )
            if diff > COUNTER_RESET_THRESHOLD:
                # Counter mundur: kemungkinan node reboot, bukan paket hilang
                details["counter_reset"] = {"previous": prev_counter, "received": counter}
            elif diff > 1:
                flags |= QCFlag.PACKET_LOSS
                packet_loss_count = diff - 1
                details["packet_loss"] = {
                    "expected": (prev_counter + 1) % 65536,
                    "received": counter,
                    "dropped": packet_loss_count,
                }
        self._last_counter[node_id] = counter

        # 2. Cek Batas Fisik (Range Check)
        range_violations = []
        for param, (min_val, max_val) in RANGE_LIMITS.items():
            val = current_data[param]
            if val < min_val or val > max_val:
                param_flags[param] |= QCFlag.RANGE_FAIL
                range_violations.append({
                    "param": param,
                    "value": val,
                    "valid_range": [min_val, max_val],
                })
        if range_violations:
            flags |= QCFlag.RANGE_FAIL
            details["range_violations"] = range_violations

        # 3. Cek Status Baterai Rendah
        if battery < BATTERY_LOW_THRESHOLD:
            flags |= QCFlag.BATTERY_LOW
            param_flags["battery"] |= QCFlag.BATTERY_LOW
            details["battery_low"] = battery

        # 4. Cek Lonjakan (Spike) terhadap nilai VALID terakhir, bukan nilai mentah
        #    terakhir; satu lonjakan tidak lagi menghasilkan dua flag (naik & turun).
        last_good = self._last_good.setdefault(node_id, {})
        spike_run = self._spike_run.setdefault(node_id, {})
        spike_violations = []
        for param, max_delta in SPIKE_LIMITS.items():
            cur = current_data[param]
            in_range = not (param_flags[param] & QCFlag.RANGE_FAIL)
            ref = last_good.get(param)
            if ref is None:
                if in_range:
                    last_good[param] = cur
                continue
            delta = abs(cur - ref)
            if delta > max_delta:
                param_flags[param] |= QCFlag.SPIKE_FAIL
                run = spike_run.get(param, 0) + 1
                violation = {
                    "param": param,
                    "delta": round(delta, 2),
                    "max_allowed": max_delta,
                    "current": cur,
                    "reference": ref,
                }
                if run >= SPIKE_REBASELINE_CYCLES and in_range:
                    # Pergeseran level konsisten: terima sebagai acuan baru
                    last_good[param] = cur
                    run = 0
                    violation["rebaselined"] = True
                spike_run[param] = run
                spike_violations.append(violation)
            elif in_range:
                last_good[param] = cur
                spike_run[param] = 0
        if spike_violations:
            flags |= QCFlag.SPIKE_FAIL
            details["spike_violations"] = spike_violations

        history = self._history.setdefault(node_id, [])

        # 5. Cek Sensor Macet (Stuck) dengan jendela per parameter
        stuck_params = []
        for param in SENSOR_PARAMS:
            window = self.stuck_windows.get(param, self.stuck_window_size)
            if len(history) < window - 1:
                continue
            vals = [d[param] for d in history[-(window - 1):]] + [current_data[param]]
            if np.isclose(np.std(vals), 0.0, atol=1e-5):
                param_flags[param] |= QCFlag.STUCK_FAIL
                stuck_params.append({
                    "param": param,
                    "constant_value": vals[-1],
                    "window_size": len(vals),
                })
        if stuck_params:
            flags |= QCFlag.STUCK_FAIL
            details["stuck_sensor"] = stuck_params

        # 6. Cek Penyimpangan Tren (Drift) — hanya pH.
        #    Suhu sengaja tidak diuji: tren pemanasan saat gelombang panas laut adalah
        #    sinyal yang justru ingin dideteksi, bukan kesalahan sensor.
        if len(history) >= (self.drift_window_size - 1):
            window_data = history[-(self.drift_window_size - 1):] + [current_data]
            ph_vals = np.array([d["ph"] for d in window_data])
            x = np.arange(len(ph_vals))
            slope, _ = np.polyfit(x, ph_vals, 1)
            if abs(slope) > DRIFT_PH_SLOPE_LIMIT:
                flags |= QCFlag.DRIFT_FAIL
                param_flags["ph"] |= QCFlag.DRIFT_FAIL
                details["drift_sensor"] = {
                    "param": "ph",
                    "estimated_slope": round(float(slope), 4),
                    "window_size": len(ph_vals),
                }

        # Simpan ke memori riwayat (batasi panjang maksimal 100)
        history.append(current_data)
        if len(history) > 100:
            history.pop(0)

        return QCResult(
            flags=flags,
            details=details,
            packet_loss_count=packet_loss_count,
            param_flags=param_flags,
        )
