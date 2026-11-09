"""
Engine replay deret suhu historis untuk menguji pipeline telemetri.

CATATAN PROVENANS -- BACA SEBELUM MENGUTIP HASIL
================================================
Berkas `data/historical_noaa_indonesia.csv` adalah REKONSTRUKSI yang ditulis
manual untuk keperluan demo pipeline. Meskipun namanya memuat "noaa", berkas ini
BELUM diverifikasi sebagai unduhan resmi NOAA Coral Reef Watch:

  * Header CSV sendiri menyebut "Rekonstruksi Siklus Gelombang Panas Laut 120 Hari".
  * Cadence 5 hari dan 17 rekaman untuk node 1 tidak cocok dengan cadence harian
    produk CRW 5-km.
  * Kolom `dhw_official` menurun di tengah seri padahal jendela akumulasi 84 hari
    tidak pernah tergeser -- mustahil untuk akumulasi HotSpot yang benar.

Karena itu modul ini TIDAK boleh dipakai sebagai dasar klaim validasi NOAA.
Penggantian dengan unduhan CRW resmi adalah prasyarat sebelum klaim apa pun
tentang akurasi terhadap produk NOAA dibuat.
"""
from __future__ import annotations
import csv
import os
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from simulator.encoder import TelemetryPacket


@dataclass
class HistoricalRecord:
    date: str
    node_id: int
    station_name: str
    sst: float
    mmm: float
    hotspot: float
    dhw_official: float
    bleaching_alert: str


class HistoricalReplayEngine:
    def __init__(self, csv_path: Optional[str] = None):
        if csv_path is None:
            # Temukan path relatif terhadap root proyek
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            csv_path = os.path.join(base_dir, "data", "historical_noaa_indonesia.csv")

        self.csv_path = csv_path
        self.records_by_node: Dict[int, List[HistoricalRecord]] = {}
        self.current_index_by_node: Dict[int, int] = {}
        self.counter_by_node: Dict[int, int] = {}
        self.load_data()

    def load_data(self):
        if not os.path.exists(self.csv_path):
            return

        with open(self.csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(row for row in f if not row.startswith("#"))
            for row in reader:
                node_id = int(row["node_id"])
                rec = HistoricalRecord(
                    date=row["date"],
                    node_id=node_id,
                    station_name=row["station_name"],
                    sst=float(row["sst"]),
                    mmm=float(row["mmm"]),
                    hotspot=float(row["hotspot"]),
                    dhw_official=float(row["dhw_official"]),
                    bleaching_alert=row["bleaching_alert"],
                )
                self.records_by_node.setdefault(node_id, []).append(rec)
                self.current_index_by_node.setdefault(node_id, 0)
                self.counter_by_node.setdefault(node_id, 0)

    def get_total_records(self, node_id: int) -> int:
        return len(self.records_by_node.get(node_id, []))

    def reset(self, node_id: Optional[int] = None):
        if node_id is not None:
            self.current_index_by_node[node_id] = 0
            self.counter_by_node[node_id] = 0
        else:
            for nid in self.current_index_by_node:
                self.current_index_by_node[nid] = 0
                self.counter_by_node[nid] = 0

    def step_next(self, node_id: int) -> Optional[Tuple[TelemetryPacket, HistoricalRecord]]:
        """
        Mengambil satu rekaman data historis berikutnya dan mengubahnya menjadi
        TelemetryPacket biner yang siap disiarkan ke MQTT.
        """
        records = self.records_by_node.get(node_id, [])
        if not records:
            return None

        idx = self.current_index_by_node[node_id]
        if idx >= len(records):
            # Loop kembali ke awal jika sudah selesai
            idx = 0

        rec = records[idx]
        self.current_index_by_node[node_id] = idx + 1
        self.counter_by_node[node_id] = (self.counter_by_node[node_id] + 1) % 65536

        # Buat paket telemetri sintetis dengan suhu riil dari NOAA
        packet = TelemetryPacket(
            node_id=rec.node_id,
            counter=self.counter_by_node[node_id],
            temperature=rec.sst,
            ph=8.15,
            salinity=34.30,
            turbidity=2.2,
            battery=95,
        )

        return packet, rec
