"""
Modul Enkoder Telemetri Biner SEGARA.
Mengemas data sensor menjadi frame 12-byte LoRaWAN-friendly.
"""
from __future__ import annotations
import struct
from dataclasses import dataclass
from typing import Dict, Any

# Format Big-Endian:
# NodeID (uint8, 1B), Counter (uint16, 2B), Suhu (int16 x100, 2B),
# pH (uint16 x100, 2B), Salinitas (uint16 x100, 2B), Kekeruhan (uint16 x10, 2B),
# Baterai (uint8, 1B)
BINARY_FRAME_FORMAT = ">BHhHHHB"
BINARY_FRAME_SIZE = struct.calcsize(BINARY_FRAME_FORMAT)  # 12 bytes


@dataclass
class TelemetryPacket:
    node_id: int
    counter: int
    temperature: float  # °C
    ph: float
    salinity: float     # PSU
    turbidity: float    # NTU
    battery: int        # %

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "counter": self.counter,
            "temperature": round(self.temperature, 2),
            "ph": round(self.ph, 2),
            "salinity": round(self.salinity, 2),
            "turbidity": round(self.turbidity, 1),
            "battery": self.battery,
        }


def encode_telemetry(packet: TelemetryPacket) -> bytes:
    """Mengodekan objek TelemetryPacket menjadi 12 byte biner."""
    # Batasi rentang agar tidak overflow struct
    raw_node_id = max(0, min(255, int(packet.node_id)))
    raw_counter = max(0, min(65535, int(packet.counter)))
    raw_suhu = max(-32768, min(32767, int(round(packet.temperature * 100))))
    raw_ph = max(0, min(65535, int(round(packet.ph * 100))))
    raw_salinitas = max(0, min(65535, int(round(packet.salinity * 100))))
    raw_kekeruhan = max(0, min(65535, int(round(packet.turbidity * 10))))
    raw_baterai = max(0, min(100, int(round(packet.battery))))

    return struct.pack(
        BINARY_FRAME_FORMAT,
        raw_node_id,
        raw_counter,
        raw_suhu,
        raw_ph,
        raw_salinitas,
        raw_kekeruhan,
        raw_baterai,
    )
