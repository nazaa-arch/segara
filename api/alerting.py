"""
Sistem Peringatan Dini (Alerting Engine) SEGARA.
Mengelola pengiriman notifikasi (Telegram, Email/Webhook, dan Log Database)
dengan mekanisme anti-banjir (Deduplication & Cooldown) saat ambang batas terlampaui.
"""
from __future__ import annotations
import os
import html
import threading
import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import httpx
from ingestion.database import Session, Alert, Node

logger = logging.getLogger("segara.alerting")

SEPARATOR = "━━━━━━━━━━━━━━━━━━━━━━"
NEWLINE = chr(10)


class AlertDispatcher:
    def __init__(
        self,
        telegram_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        cooldown_seconds: int = 3600,  # 1 jam default cooldown per node untuk tingkat peringatan yang sama
    ):
        self.telegram_token = telegram_token or os.environ.get("SEGARA_TELEGRAM_TOKEN")
        self.telegram_chat_id = telegram_chat_id or os.environ.get("SEGARA_TELEGRAM_CHAT_ID")
        self.cooldown_seconds = cooldown_seconds
        # State cooldown: key = (node_id, alert_level), value = timestamp_last_sent
        self._last_alert_time: Dict[tuple[int, int], float] = {}

    @staticmethod
    def _fields(node_name, region, alert_label, sst, mmm, hotspot, dhw, action_advice):
        return [
            ("📍", "Lokasi", node_name),
            ("🌊", "Kawasan", region),
            ("📊", "Status", alert_label.upper()),
            (None, None, None),
            ("🌡️", "Suhu Air Laut (SST)", f"{sst:.2f} °C"),
            ("📈", "Ambang Panas (MMM)", f"{mmm:.2f} °C"),
            ("🔥", "HotSpot Anomali", f"{hotspot:.2f} °C"),
            ("⏳", "Akumulasi DHW", f"{dhw:.2f} °C-minggu"),
        ]

    def format_telegram_message(
        self,
        node_name: str,
        region: str,
        alert_label: str,
        sst: float,
        mmm: float,
        hotspot: float,
        dhw: float,
        action_advice: str,
    ) -> str:
        """
        Pesan teks polos (disimpan di DB & ditampilkan dashboard). Tanpa markup
        Markdown agar tidak muncul tanda * ` _ mentah di dashboard.
        """
        header_emoji = "🚨" if "Alert Level" in alert_label else "⚠️"
        lines = [f"{header_emoji} PERINGATAN STRES TERMAL KARANG - SEGARA", SEPARATOR]
        for emoji, key, val in self._fields(node_name, region, alert_label, sst, mmm, hotspot, dhw, action_advice):
            lines.append("" if key is None else f"{emoji} {key}: {val}")
        lines += [
            "",
            "📋 Rekomendasi Tindakan:",
            action_advice,
            SEPARATOR,
            f"⏰ Waktu Deteksi: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        ]
        return NEWLINE.join(lines)

    def format_telegram_html(
        self,
        node_name: str,
        region: str,
        alert_label: str,
        sst: float,
        mmm: float,
        hotspot: float,
        dhw: float,
        action_advice: str,
    ) -> str:
        """Versi HTML untuk Telegram (parse_mode=HTML); semua nilai di-escape."""
        e = html.escape
        header_emoji = "🚨" if "Alert Level" in alert_label else "⚠️"
        lines = [f"{header_emoji} <b>PERINGATAN STRES TERMAL KARANG - SEGARA</b>", SEPARATOR]
        for emoji, key, val in self._fields(node_name, region, alert_label, sst, mmm, hotspot, dhw, action_advice):
            lines.append("" if key is None else f"{emoji} <b>{e(key)}</b>: <code>{e(val)}</code>")
        lines += [
            "",
            "📋 <b>Rekomendasi Tindakan</b>:",
            f"<i>{e(action_advice)}</i>",
            SEPARATOR,
            f"⏰ Waktu Deteksi: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        ]
        return NEWLINE.join(lines)

    def _send_telegram(self, text_html: str, node_id: int, alert_label: str) -> None:
        """Dijalankan di thread latar agar pipeline ingestion tidak menunggu jaringan."""
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        try:
            with httpx.Client(timeout=4.0) as client:
                resp = client.post(
                    url,
                    json={"chat_id": self.telegram_chat_id, "text": text_html, "parse_mode": "HTML"},
                )
            if resp.status_code == 200 and resp.json().get("ok"):
                logger.info("Telegram notification sent for node %d (%s)", node_id, alert_label)
            else:
                logger.warning(
                    "Telegram menolak notifikasi node %d: HTTP %s %s",
                    node_id, resp.status_code, resp.text[:200],
                )
        except Exception as e:
            # Jangan log URL: berisi token bot
            logger.warning("Failed to send Telegram alert for node %d: %s", node_id, type(e).__name__)

    def dispatch_alert(
        self,
        session: Session,
        node_id: int,
        alert_level: int,
        alert_label: str,
        sst: float,
        mmm: float,
        hotspot: float,
        dhw: float,
    ) -> Optional[Alert]:
        """
        Memeriksa cooldown dan mengirimkan notifikasi peringatan.
        Menyimpan rekaman ke database tabel alerts.
        """
        # Jangan kirim notifikasi jika No Stress (0)
        if alert_level <= 0:
            return None

        now = time.time()
        last_sent = self._last_alert_time.get((node_id, alert_level), 0.0)

        # Cek apakah masih dalam periode cooldown untuk level ini
        if (now - last_sent) < self.cooldown_seconds:
            logger.debug("Alert level %d for node %d suppressed due to cooldown", alert_level, node_id)
            return None

        node = session.query(Node).filter(Node.id == node_id).first()
        node_name = node.name if node else f"Node {node_id}"
        region = node.region if node else "Perairan Indonesia"

        # Tentukan saran aksi
        if alert_level == 1:
            advice = "Tingkatkan frekuensi patroli terumbu karang dan pantau perkembangan anomali suhu mingguan."
            alert_type = "BLEACHING_WATCH"
        elif alert_level == 2:
            advice = "Siapkan protokol tanggap darurat pemutihan karang dan batasi aktivitas wisata penyelaman intensif."
            alert_type = "BLEACHING_WARNING"
        elif alert_level == 3:
            advice = "WASPADA TINGKAT 1: Pemutihan signifikan diperkirakan terjadi. Laporkan kondisi karang ke pengelola kawasan konservasi."
            alert_type = "ALERT_LEVEL_1"
        else:
            advice = "BAHAYA TINGKAT 2: Pemutihan massal parah & risiko kematian koral tinggi. Lakukan survei darurat dan mitigasi stresor lokal!"
            alert_type = "ALERT_LEVEL_2"

        msg_text = self.format_telegram_message(
            node_name=node_name,
            region=region,
            alert_label=alert_label,
            sst=sst,
            mmm=mmm,
            hotspot=hotspot,
            dhw=dhw,
            action_advice=advice,
        )

        # Simpan ke tabel alerts
        alert_record = Alert(
            node_id=node_id,
            node_name=node_name,
            timestamp=datetime.now(timezone.utc),
            alert_level=alert_level,
            alert_type=alert_type,
            message=msg_text,
            acknowledged=False,
        )
        session.add(alert_record)
        session.commit()
        session.refresh(alert_record)

        self._last_alert_time[(node_id, alert_level)] = now

        # Kirim ke Telegram di thread latar jika kredensial tersedia
        if self.telegram_token and self.telegram_chat_id:
            text_html = self.format_telegram_html(
                node_name=node_name, region=region, alert_label=alert_label,
                sst=sst, mmm=mmm, hotspot=hotspot, dhw=dhw, action_advice=advice,
            )
            threading.Thread(
                target=self._send_telegram,
                args=(text_html, node_id, alert_label),
                name=f"telegram-node-{node_id}",
                daemon=True,
            ).start()

        return alert_record
