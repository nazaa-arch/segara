"""
Unit Test Langsung: Mesin Notifikasi Peringatan Dini (Alerting) SEGARA.
"""
import pytest
from api.alerting import AlertDispatcher
from ingestion.database import init_db, Alert


def test_alert_dispatcher_cooldown_and_db_logging():
    session_factory = init_db("sqlite:///:memory:")
    dispatcher = AlertDispatcher(cooldown_seconds=3600)  # Cooldown 1 jam

    with session_factory() as session:
        # Kirim alert pertama (Alert Level 2: Bleaching Warning)
        alert1 = dispatcher.dispatch_alert(
            session=session,
            node_id=1,
            alert_level=2,
            alert_label="Bleaching Warning",
            sst=30.50,
            mmm=29.20,
            hotspot=1.30,
            dhw=2.10,
        )
        assert alert1 is not None
        assert alert1.alert_level == 2
        assert "PERINGATAN STRES TERMAL" in alert1.message

        # Coba kirim alert kedua pada level yang sama segera setelahnya (harus ditekan oleh cooldown)
        alert2 = dispatcher.dispatch_alert(
            session=session,
            node_id=1,
            alert_level=2,
            alert_label="Bleaching Warning",
            sst=30.55,
            mmm=29.20,
            hotspot=1.35,
            dhw=2.20,
        )
        assert alert2 is None  # Ditekan oleh cooldown anti-banjir

        # Verifikasi bahwa hanya 1 alert yang tercatat di tabel database
        total_alerts = session.query(Alert).count()
        assert total_alerts == 1


def test_alert_dispatcher_no_stress_no_alert():
    session_factory = init_db("sqlite:///:memory:")
    dispatcher = AlertDispatcher()

    with session_factory() as session:
        # Alert Level 0 (No Stress) tidak boleh memicu notifikasi
        alert = dispatcher.dispatch_alert(
            session=session,
            node_id=1,
            alert_level=0,
            alert_label="No Stress",
            sst=28.50,
            mmm=29.20,
            hotspot=0.0,
            dhw=0.0,
        )
        assert alert is None
        assert session.query(Alert).count() == 0
