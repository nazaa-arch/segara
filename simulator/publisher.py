"""
Klien Publisher MQTT SEGARA.
Mempublikasikan frame biner telemetri 12-byte ke broker MQTT (Mosquitto/amqtt).
"""
from __future__ import annotations
import time
import logging
from typing import Optional, Callable
import paho.mqtt.client as mqtt
from simulator.encoder import TelemetryPacket, encode_telemetry

logger = logging.getLogger("segara.simulator.publisher")


class TelemetryPublisher:
    def __init__(
        self,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        client_id: str = "segara_simulator_pub",
        qos: int = 0,
    ):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.client_id = client_id
        self.qos = qos
        self.is_connected = False
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

        # Callback lokal opsional jika sistem dijalankan dalam single-process mode
        self.local_subscriber_hook: Optional[Callable[[str, bytes], None]] = None

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self.is_connected = True
            logger.info("Simulator MQTT publisher connected to %s:%d", self.broker_host, self.broker_port)
        else:
            self.is_connected = False
            logger.warning("Simulator MQTT connect failed with rc=%s", rc)

    def _on_disconnect(self, client, userdata, flags, rc, properties=None):
        self.is_connected = False
        logger.info("Simulator MQTT publisher disconnected")

    def connect(self, timeout: float = 3.0) -> bool:
        """Mencoba menghubungkan ke broker MQTT."""
        try:
            self.client.connect(self.broker_host, self.broker_port, keepalive=60)
            self.client.loop_start()
            start = time.time()
            while not self.is_connected and (time.time() - start) < timeout:
                time.sleep(0.05)
            return self.is_connected
        except Exception as e:
            logger.warning("Could not connect to MQTT broker (%s:%s): %s", self.broker_host, self.broker_port, e)
            return False

    def disconnect(self):
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass
        self.is_connected = False

    def publish_packet(self, packet: TelemetryPacket) -> bool:
        """
        Mengemas TelemetryPacket ke biner 12 byte dan mempublikasikannya
        ke topik 'segara/telemetry/{node_id}'.
        """
        raw_payload = encode_telemetry(packet)
        topic = f"segara/telemetry/{packet.node_id}"

        # Jalankan hook lokal jika terdaftar (misal untuk in-memory testing tanpa broker luar)
        if self.local_subscriber_hook:
            try:
                self.local_subscriber_hook(topic, raw_payload)
            except Exception as e:
                logger.error("Error in local subscriber hook: %s", e)

        # Publikasikan ke MQTT jika terhubung
        if self.is_connected:
            try:
                info = self.client.publish(topic, raw_payload, qos=self.qos)
                return info.rc == mqtt.MQTT_ERR_SUCCESS
            except Exception as e:
                logger.error("Failed to publish to MQTT: %s", e)
                return False

        return self.local_subscriber_hook is not None
