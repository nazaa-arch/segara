"""
Subscriber MQTT dan Pipeline Ingestion SEGARA.
Mendengarkan topik 'segara/telemetry/+', mendekode payload 12-byte,
menjalankan aturan Quality Control (QC), menghitung metrik stres termal (HotSpot & DHW),
menyimpan data ke database, dan memicu peringatan dini.
"""
from __future__ import annotations
import time
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple
import paho.mqtt.client as mqtt

from ingestion.decoder import decode_telemetry
from ingestion.database import (
    init_db,
    Node,
    Measurement,
    QCRecord,
    ThermalMetric,
)
from qc.rules import QualityControlEngine, QCFlag, COUNTER_RESET_THRESHOLD
from analytics.thermal_stress import ThermalAnalyticsEngine
from analytics.anomaly import AnomalyDetector
from api.alerting import AlertDispatcher

logger = logging.getLogger("segara.ingestion.subscriber")


class IngestionPipeline:
    def __init__(
        self,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        client_id: str = "segara_ingestion_sub",
        db_session_factory=None,
        cycle_hours: float = 6.0,
    ):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.client_id = client_id
        self.session_factory = db_session_factory or init_db()

        self.qc_engine = QualityControlEngine()
        self.thermal_engine = ThermalAnalyticsEngine()
        self.anomaly_detector = AnomalyDetector()
        self.alert_dispatcher = AlertDispatcher()

        # Interval nominal antarpaket. Waktu observasi diturunkan dari counter,
        # sehingga paket hilang tetap memajukan jam dan jendela DHW tetap 84 hari.
        self.cycle_hours = cycle_hours
        # Jam per node: node_id -> (counter terakhir, waktu observasi terakhir)
        self._node_clock: Dict[int, Tuple[int, datetime]] = {}

        self.is_connected = False
        self.total_received = 0
        self.total_processed = 0
        self.total_errors = 0

        # Klien MQTT Paho
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self.is_connected = True
            logger.info("Ingestion subscriber connected to %s:%d", self.broker_host, self.broker_port)
            # Berlangganan ke semua topik telemetri pelampung
            self.client.subscribe("segara/telemetry/+", qos=0)
            logger.info("Subscribed to 'segara/telemetry/+'")
        else:
            self.is_connected = False
            logger.warning("Ingestion MQTT connection failed with rc=%s", rc)

    def _on_disconnect(self, client, userdata, flags, rc, properties=None):
        self.is_connected = False
        logger.info("Ingestion MQTT subscriber disconnected")

    def _on_message(self, client, userdata, msg):
        self.process_raw_message(msg.topic, msg.payload)

    def process_raw_message(self, topic: str, payload: bytes) -> Optional[Dict[str, Any]]:
        """
        Memproses satu payload biner mentah secara langsung.
        Dapat dipanggil oleh MQTT callback atau langsung secara in-process.
        """
        self.total_received += 1
        t_start = time.perf_counter()

        # 1. Dekode payload biner 12 byte
        decoded = decode_telemetry(payload)
        if decoded is None:
            self.total_errors += 1
            logger.warning("Failed to decode binary frame of length %d from topic %s", len(payload), topic)
            return None

        with self.session_factory() as session:
            # Ambil node dari DB
            node = session.query(Node).filter(Node.id == decoded.node_id).first()
            if not node:
                logger.warning("Node ID %d not found in database", decoded.node_id)
                return None

            # Pulihkan state (counter, jam, riwayat DHW) dari DB bila proses baru mulai
            self._restore_node_state(session, decoded.node_id)
            observed_at = self._observation_time(decoded.node_id, decoded.counter)

            # 2. Evaluasi Quality Control (QC)
            qc_result = self.qc_engine.evaluate(
                node_id=decoded.node_id,
                counter=decoded.counter,
                temperature=decoded.temperature,
                ph=decoded.ph,
                salinity=decoded.salinity,
                turbidity=decoded.turbidity,
                battery=decoded.battery,
            )
            is_duplicate = bool(qc_result.flags & QCFlag.DUPLICATE)

            # Perbarui status node (last_seen = waktu terima, bukan waktu observasi)
            node.last_seen = datetime.now(timezone.utc)
            node.battery = decoded.battery

            # Simpan data mentah ke tabel measurements (duplikat tetap disimpan untuk audit,
            # tetapi ditandai DUPLICATE dan tidak masuk analitik)
            meas = Measurement(
                node_id=decoded.node_id,
                timestamp=observed_at,
                counter=decoded.counter,
                temperature=decoded.temperature,
                ph=decoded.ph,
                salinity=decoded.salinity,
                turbidity=decoded.turbidity,
                battery=decoded.battery,
                raw_hex=payload.hex(),
            )
            session.add(meas)
            session.flush()

            # Simpan label QC ke tabel qc_flags
            qc_rec = QCRecord(
                measurement_id=meas.id,
                node_id=decoded.node_id,
                flag_mask=int(qc_result.flags),
                flag_names=",".join(qc_result.flag_names()),
                is_valid=qc_result.is_valid,
                packet_loss_count=qc_result.packet_loss_count,
                details_json=json.dumps(qc_result.details),
            )
            session.add(qc_rec)

            # 3. Hitung Analitik Stres Termal jika SUHU lolos QC. Kegagalan sensor lain
            #    (pH, kekeruhan, baterai) tidak membuang data suhu untuk DHW.
            thermal_result = None
            if qc_result.is_param_valid("temperature"):
                thermal_result = self.thermal_engine.process_telemetry(
                    node_id=decoded.node_id,
                    sst=decoded.temperature,
                    mmm=node.mmm_sst,
                    ph=decoded.ph if qc_result.is_param_valid("ph") else None,
                    turbidity=decoded.turbidity if qc_result.is_param_valid("turbidity") else None,
                    dt_days=self.cycle_hours / 24.0,
                    observed_at=observed_at,
                )

                # Simpan metrik termal ke DB
                tm = ThermalMetric(
                    node_id=decoded.node_id,
                    timestamp=observed_at,
                    sst=thermal_result.sst,
                    mmm=thermal_result.mmm,
                    hotspot=thermal_result.hotspot,
                    dhw=thermal_result.dhw,
                    alert_level=int(thermal_result.alert_level),
                    alert_label=thermal_result.alert_level.label,
                    compound_stress=thermal_result.compound_stress,
                )
                session.add(tm)

                # Pemicu notifikasi peringatan jika ada ancaman pemutihan
                if int(thermal_result.alert_level) > 0:
                    self.alert_dispatcher.dispatch_alert(
                        session=session,
                        node_id=decoded.node_id,
                        alert_level=int(thermal_result.alert_level),
                        alert_label=thermal_result.alert_level.label,
                        sst=thermal_result.sst,
                        mmm=thermal_result.mmm,
                        hotspot=thermal_result.hotspot,
                        dhw=thermal_result.dhw,
                    )

            # 4. Deteksi Anomali (paket ganda dilewati agar tidak tercatat dua kali)
            anomaly_res = None
            if not is_duplicate:
                anomaly_res = self.anomaly_detector.add_observation(
                    node_id=decoded.node_id,
                    temperature=decoded.temperature,
                    ph=decoded.ph,
                    salinity=decoded.salinity,
                    turbidity=decoded.turbidity,
                )

            session.commit()

        self.total_processed += 1
        elapsed_ms = (time.perf_counter() - t_start) * 1000.0

        return {
            "node_id": decoded.node_id,
            "counter": decoded.counter,
            "observed_at": observed_at.isoformat(),
            "qc": qc_result.to_dict(),
            "thermal": thermal_result.to_dict() if thermal_result else None,
            "anomaly": anomaly_res.to_dict() if anomaly_res else None,
            "latency_ms": round(elapsed_ms, 2),
        }

    def _observation_time(self, node_id: int, counter: int) -> datetime:
        """
        Menurunkan waktu observasi dari selisih counter.

        - Paket pertama: waktu sekarang (UTC).
        - Maju n langkah: waktu terakhir + n * cycle_hours (paket hilang ikut dihitung).
        - Duplikat: waktu terakhir, tanpa maju.
        - Counter mundur (reboot): waktu terakhir + 1 siklus.
        """
        cycle = timedelta(hours=self.cycle_hours)
        prev = self._node_clock.get(node_id)
        if prev is None:
            observed = datetime.now(timezone.utc)
        else:
            prev_counter, prev_time = prev
            diff = (counter - prev_counter) % 65536
            if diff == 0:
                return prev_time
            if diff > COUNTER_RESET_THRESHOLD:
                observed = prev_time + cycle
            else:
                observed = prev_time + diff * cycle
        self._node_clock[node_id] = (counter, observed)
        return observed

    def _restore_node_state(self, session, node_id: int) -> None:
        """Memuat counter, jam, dan riwayat HotSpot 84 hari terakhir dari DB (sekali per node)."""
        if node_id in self._node_clock:
            return
        last = (
            session.query(Measurement)
            .filter(Measurement.node_id == node_id)
            .order_by(Measurement.timestamp.desc(), Measurement.id.desc())
            .first()
        )
        if last is None:
            return
        last_time = _as_utc(last.timestamp)
        self._node_clock[node_id] = (last.counter, last_time)
        if not self.qc_engine.has_node(node_id):
            self.qc_engine.set_last_counter(node_id, last.counter)

        if not self.thermal_engine.has_node(node_id):
            window = self.thermal_engine.window_days
            dt_days = self.cycle_hours / 24.0
            # Batasi juga jumlah titik: DB lama bisa berisi timestamp jam dinding
            # yang terlalu rapat sehingga ribuan titik jatuh dalam 84 hari.
            max_points = int(round(window / dt_days))
            rows = (
                session.query(ThermalMetric.timestamp, ThermalMetric.hotspot)
                .filter(ThermalMetric.node_id == node_id)
                .filter(ThermalMetric.timestamp > last_time - timedelta(days=window))
                .order_by(ThermalMetric.timestamp.desc(), ThermalMetric.id.desc())
                .limit(max_points)
                .all()
            )
            self.thermal_engine.seed_history(
                node_id, [(_as_utc(ts), hs, dt_days) for ts, hs in rows]
            )

    def start(self, timeout: float = 3.0) -> bool:
        """Menghubungkan ke broker MQTT dan memulai loop penerima."""
        try:
            self.client.connect(self.broker_host, self.broker_port, keepalive=60)
            self.client.loop_start()
            start = time.time()
            while not self.is_connected and (time.time() - start) < timeout:
                time.sleep(0.05)
            return self.is_connected
        except Exception as e:
            logger.warning("Could not connect subscriber to MQTT broker (%s:%s): %s", self.broker_host, self.broker_port, e)
            return False

    def stop(self):
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass
        self.is_connected = False


def _as_utc(ts: datetime) -> datetime:
    """SQLite mengembalikan datetime naif; anggap UTC."""
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts
