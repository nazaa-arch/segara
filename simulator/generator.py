"""
Generator Telemetri Pelampung Virtual SEGARA.
Menghasilkan telemetri sintetis dengan dinamika fisik laut realistis:
- Siklus diurnal (sinusoidal) + variasi musiman + simulasi Marine Heatwave (MHW)
- Kejadian hujan/badai (lonjakan kekeruhan, penurunan salinitas)
- Injeksi gangguan terkontrol (lonjakan/spike, macet/stuck, drift, out-of-range, packet loss)
- Skenario berulang dengan seed tetap untuk replikasi eksperimen
"""
from __future__ import annotations
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from simulator.encoder import TelemetryPacket, encode_telemetry


@dataclass
class FaultConfig:
    spike_param: Optional[str] = None      # e.g., "temperature", "ph", "salinity"
    spike_magnitude: float = 0.0
    stuck_param: Optional[str] = None      # e.g., "temperature", "ph"
    stuck_cycles_remaining: int = 0
    drift_param: Optional[str] = None      # e.g., "ph"
    drift_rate_per_cycle: float = 0.0      # akumulasi per siklus
    drift_accumulated: float = 0.0
    out_of_range_param: Optional[str] = None
    packet_loss_rate: float = 0.0          # 0.0 - 1.0 (probabilitas paket hilang)


@dataclass
class BuoyState:
    node_id: int
    name: str
    region: str
    latitude: float
    longitude: float
    mmm: float
    counter: int = 0
    battery: float = 100.0
    step_index: int = 0
    # Kondisi cuaca lokal
    in_heatwave: bool = False
    heatwave_intensity: float = 0.0
    heatwave_level: float = 0.0  # anomali MHW yang sedang berlaku (°C), bisa bertahap
    in_storm: bool = False
    faults: FaultConfig = field(default_factory=FaultConfig)
    last_values: Dict[str, float] = field(default_factory=dict)


class CoralBuoySimulator:
    def __init__(
        self,
        nodes_config: Optional[List[Dict[str, Any]]] = None,
        seed: Optional[int] = 42,
        heatwave_ramp_per_step: Optional[float] = None,
    ):
        """
        heatwave_ramp_per_step: laju naik/turun anomali MHW per paket (°C). None =
        langsung penuh (perilaku lama, dipakai evaluator agar angkanya tetap).
        Simulator live memakai transisi bertahap agar mulai/berakhirnya gelombang
        panas tidak terbaca sebagai lonjakan sensor oleh QC.
        """
        self.heatwave_ramp_per_step = heatwave_ramp_per_step
        if seed is not None:
            random.seed(seed)
            self._rng = random.Random(seed)
        else:
            self._rng = random.Random()

        self.seed = seed
        self.nodes_config = nodes_config or [
            {"id": 1, "name": "Stasiun Bunaken Reef", "region": "Bunaken", "lat": 1.62, "lon": 124.75, "mmm": 29.20},
            {"id": 2, "name": "Stasiun Raja Ampat Kri", "region": "Raja Ampat", "lat": -0.55, "lon": 130.67, "mmm": 29.50},
            {"id": 3, "name": "Stasiun Wakatobi Tomia", "region": "Wakatobi", "lat": -5.51, "lon": 123.75, "mmm": 29.10},
            {"id": 4, "name": "Stasiun Karimunjawa", "region": "Karimunjawa", "lat": -5.85, "lon": 110.45, "mmm": 29.60},
            {"id": 5, "name": "Stasiun Komodo Padar", "region": "Komodo", "lat": -8.55, "lon": 119.53, "mmm": 28.80},
        ]

        self.buoys: Dict[int, BuoyState] = {}
        for cfg in self.nodes_config:
            self.buoys[cfg["id"]] = BuoyState(
                node_id=cfg["id"],
                name=cfg["name"],
                region=cfg["region"],
                latitude=cfg["lat"],
                longitude=cfg["lon"],
                mmm=cfg["mmm"],
                battery=float(self._rng.randint(85, 100)),
            )

    def set_fault(self, node_id: int, fault_config: FaultConfig):
        """Menyuntikkan konfigurasi gangguan sensor ke node tertentu."""
        if node_id in self.buoys:
            self.buoys[node_id].faults = fault_config

    def clear_faults(self, node_id: int):
        """Membersihkan gangguan pada node."""
        if node_id in self.buoys:
            self.buoys[node_id].faults = FaultConfig()

    def set_heatwave(self, node_id: int, active: bool, intensity: float = 1.8):
        """Mengaktifkan skenario gelombang panas laut (Marine Heatwave)."""
        if node_id in self.buoys:
            self.buoys[node_id].in_heatwave = active
            self.buoys[node_id].heatwave_intensity = intensity

    def set_storm(self, node_id: int, active: bool):
        """Mengaktifkan skenario badai / hujan deras laut."""
        if node_id in self.buoys:
            self.buoys[node_id].in_storm = active

    def generate_next_packet(
        self,
        node_id: int,
        sim_time: Optional[datetime] = None,
        dt_hours: float = 6.0,  # 4 kali sehari (setiap 6 jam) untuk mempercepat simulasi siklus
    ) -> Optional[TelemetryPacket]:
        """
        Menghasilkan satu paket telemetri baru untuk node_id.
        Mengembalikan None jika paket sengaja di-drop (packet loss injection).
        """
        buoy = self.buoys.get(node_id)
        if not buoy:
            return None

        buoy.counter = (buoy.counter + 1) % 65536
        buoy.step_index += 1

        # Cek simulasi kehilangan paket (Packet Loss)
        if buoy.faults.packet_loss_rate > 0.0:
            if self._rng.random() < buoy.faults.packet_loss_rate:
                # Paket hilang, tidak dikirim ke subscriber
                return None

        # Waktu simulasi lokal
        if sim_time is None:
            sim_time = datetime.now(timezone.utc) + timedelta(hours=buoy.step_index * dt_hours)

        hour_of_day = sim_time.hour + sim_time.minute / 60.0
        day_of_year = sim_time.timetuple().tm_yday

        # 1. Model Suhu Permukaan Laut (SST):
        # Base: rata-rata sekitar (MMM - 0.4°C) saat kondisi normal
        base_sst = buoy.mmm - 0.4
        # Fluktuasi diurnal: puncak sekitar pukul 14.00, lembah pukul 05.00
        diurnal_variation = 0.35 * math.sin((hour_of_day - 8.0) * (2 * math.pi / 24.0))
        # Variasi musiman ringan
        seasonal_variation = 0.50 * math.sin((day_of_year - 80) * (2 * math.pi / 365.25))

        # Kontribusi Marine Heatwave (MHW) jika aktif
        target = buoy.heatwave_intensity if buoy.in_heatwave else 0.0
        if self.heatwave_ramp_per_step is None:
            buoy.heatwave_level = target
        else:
            step = self.heatwave_ramp_per_step
            diff = target - buoy.heatwave_level
            buoy.heatwave_level += max(-step, min(step, diff))
        mhw_boost = buoy.heatwave_level

        # Noise acak sensor laut (Gaussian N(0, 0.05))
        sensor_noise_t = self._rng.gauss(0.0, 0.05)

        calc_temp = base_sst + diurnal_variation + seasonal_variation + mhw_boost + sensor_noise_t

        # 2. Model pH Air Laut:
        # Normal laut karang: ~8.15. Saat siang hari meningkat sedikit karena fotosintesis (+0.05)
        base_ph = 8.15 + 0.04 * math.sin((hour_of_day - 10.0) * (2 * math.pi / 24.0))
        calc_ph = base_ph + self._rng.gauss(0.0, 0.015)

        # 3. Model Salinitas (PSU):
        # Normal perairan karang Indonesia: ~33.8 - 34.5 PSU
        base_salinity = 34.2 + 0.2 * math.sin((day_of_year) * (2 * math.pi / 365.25))
        calc_salinity = base_salinity + self._rng.gauss(0.0, 0.08)

        # 4. Model Kekeruhan (Turbidity NTU):
        # Air jernih terumbu karang: 1.0 - 3.5 NTU
        base_turbidity = 2.0 + abs(self._rng.gauss(0.0, 0.5))

        # Efek Badai / Hujan:
        if buoy.in_storm:
            # Lonjakan kekeruhan tinggi karena sedimentasi dan gelombang
            calc_turbidity = base_turbidity + self._rng.uniform(25.0, 60.0)
            # Penurunan salinitas karena presipitasi air tawar
            calc_salinity -= self._rng.uniform(1.5, 3.2)
            # Sedikit penurunan suhu karena awan dan hujan
            calc_temp -= self._rng.uniform(0.3, 0.8)
        else:
            calc_turbidity = base_turbidity

        # 5. Model Baterai:
        # Konsumsi per siklus ~0.02%, pengisian tenaga surya di siang hari (07:00 - 16:00)
        is_daylight = 7.0 <= hour_of_day <= 16.0
        if is_daylight:
            buoy.battery = min(100.0, buoy.battery + 0.05)
        else:
            buoy.battery = max(5.0, buoy.battery - 0.03)

        # INJEKSI GANGGUAN SENSOR (FAULT INJECTION):
        # a. Stuck Sensor: pertahankan nilai konstan selama beberapa siklus
        if buoy.faults.stuck_param and buoy.faults.stuck_cycles_remaining > 0:
            param = buoy.faults.stuck_param
            if param in buoy.last_values:
                if param == "temperature":
                    calc_temp = buoy.last_values[param]
                elif param == "ph":
                    calc_ph = buoy.last_values[param]
                elif param == "salinity":
                    calc_salinity = buoy.last_values[param]
                elif param == "turbidity":
                    calc_turbidity = buoy.last_values[param]
            buoy.faults.stuck_cycles_remaining -= 1

        # b. Sensor Drift: deviasi tren bertahap yang tidak wajar
        if buoy.faults.drift_param:
            buoy.faults.drift_accumulated += buoy.faults.drift_rate_per_cycle
            if buoy.faults.drift_param == "ph":
                calc_ph -= buoy.faults.drift_accumulated  # asidifikasi palsu / drift elektroda
            elif buoy.faults.drift_param == "temperature":
                calc_temp += buoy.faults.drift_accumulated

        # c. Lonjakan Sensor (Spike): terjadi 1 siklus
        if buoy.faults.spike_param:
            mag = buoy.faults.spike_magnitude
            if buoy.faults.spike_param == "temperature":
                calc_temp += mag
            elif buoy.faults.spike_param == "ph":
                calc_ph += mag
            elif buoy.faults.spike_param == "salinity":
                calc_salinity += mag
            elif buoy.faults.spike_param == "turbidity":
                calc_turbidity += mag
            # Reset spike setelah 1 pembacaan
            buoy.faults.spike_param = None
            buoy.faults.spike_magnitude = 0.0

        # d. Nilai di luar rentang fisik (Out of range)
        if buoy.faults.out_of_range_param:
            if buoy.faults.out_of_range_param == "temperature":
                calc_temp = 48.5  # Jauh di atas 35°C
            elif buoy.faults.out_of_range_param == "ph":
                calc_ph = 5.2     # Asam ekstrem tidak wajar
            elif buoy.faults.out_of_range_param == "salinity":
                calc_salinity = 15.0 # Air payau ekstrem
            # Reset setelah terkirim
            buoy.faults.out_of_range_param = None

        # Simpan nilai terakhir untuk referensi perbandingan dan stuck detection
        buoy.last_values = {
            "temperature": calc_temp,
            "ph": calc_ph,
            "salinity": calc_salinity,
            "turbidity": calc_turbidity,
        }

        packet = TelemetryPacket(
            node_id=buoy.node_id,
            counter=buoy.counter,
            temperature=calc_temp,
            ph=calc_ph,
            salinity=calc_salinity,
            turbidity=calc_turbidity,
            battery=int(round(buoy.battery)),
        )

        return packet
