"""
Modul Dekoder Telemetri Biner SEGARA.
Membongkar paket 12-byte biner menjadi data terstruktur.
"""
from __future__ import annotations
import struct
from dataclasses import dataclass
from typing import Optional, Dict, Any

BINARY_FRAME_FORMAT = ">BHhHHHB"
BINARY_FRAME_SIZE = struct.calcsize(BINARY_FRAME_FORMAT)  # 12 bytes


@dataclass
class DecodedTelemetry:
    node_id: int
    counter: int
    temperature: float  # °C
    ph: float
    salinity: float     # PSU
    turbidity: float    # NTU
    battery: int        # %
    raw_bytes: bytes

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


def decode_telemetry(payload: bytes) -> Optional[DecodedTelemetry]:
    """
    Mendekodekan frame biner 12 byte menjadi DecodedTelemetry.
    Mengembalikan None jika ukuran frame tidak sesuai.

    Catatan: frame tidak membawa checksum/CRC, sehingga yang diperiksa di sini
    hanya panjang frame. Integritas bit diandalkan pada lapisan transport
    (MIC/CRC LoRaWAN); nilai yang korup tetapi berukuran benar baru tertangkap
    oleh aturan QC (range, spike).
    """
    if len(payload) != BINARY_FRAME_SIZE:
        return None

    try:
        (
            node_id,
            counter,
            raw_suhu,
            raw_ph,
            raw_salinitas,
            raw_kekeruhan,
            battery,
        ) = struct.unpack(BINARY_FRAME_FORMAT, payload)

        return DecodedTelemetry(
            node_id=node_id,
            counter=counter,
            temperature=raw_suhu / 100.0,
            ph=raw_ph / 100.0,
            salinity=raw_salinitas / 100.0,
            turbidity=raw_kekeruhan / 10.0,
            battery=battery,
            raw_bytes=payload,
        )
    except Exception:
        return None
