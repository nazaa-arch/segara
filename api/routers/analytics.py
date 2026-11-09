"""
Router REST API: Analitik Ilmiah Stres Termal, DHW, Peramalan, dan Ringkasan QC.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Dict, Any, Optional
from ingestion.database import Session, Node, Measurement, QCRecord, ThermalMetric, init_db
from analytics.forecasting import forecast_thermal_stress
from qc.rules import QCFlag
from sqlalchemy import func, case

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])
session_factory = init_db()


def get_db():
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


@router.get("/dhw/{node_id}", response_model=Dict[str, Any])
def get_thermal_analytics(node_id: int, limit: int = 120, db: Session = Depends(get_db)):
    """Mengambil riwayat HotSpot, DHW, dan tingkat peringatan pemutihan koral untuk stasiun tertentu."""
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

    metrics = (
        db.query(ThermalMetric)
        .filter(ThermalMetric.node_id == node_id)
        .order_by(ThermalMetric.timestamp.desc())
        .limit(limit)
        .all()
    )
    # Urutkan secara kronologis (asc)
    metrics_chrono = list(reversed(metrics))

    latest = metrics[0] if metrics else None

    return {
        "node_id": node.id,
        "node_name": node.name,
        "region": node.region,
        "mmm_sst": node.mmm_sst,
        "bleaching_threshold": node.bleaching_threshold,
        "current_status": {
            "sst": latest.sst if latest else node.mmm_sst,
            "hotspot": latest.hotspot if latest else 0.0,
            "dhw": latest.dhw if latest else 0.0,
            "alert_level": latest.alert_level if latest else 0,
            "alert_label": latest.alert_label if latest else "No Stress",
            "compound_stress": latest.compound_stress if latest else 0.0,
        },
        "history": [m.to_dict() for m in metrics_chrono],
    }


@router.get("/forecast/{node_id}", response_model=Dict[str, Any])
def get_forecast(
    node_id: int,
    horizon_days: int = Query(14, ge=3, le=30, description="Jendela peramalan (hari)"),
    db: Session = Depends(get_db),
):
    """
    Menghasilkan proyeksi suhu permukaan laut dan lintasan DHW hingga 14 hari ke depan
    menggunakan model Exponential Smoothing dengan Local Trend vs Persistence Baseline.
    """
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

    # Ambil riwayat suhu terakhir yang LOLOS QC suhu. ThermalMetric hanya ditulis
    # bila suhu valid, sehingga spike / nilai macet / duplikat tidak ikut diramal.
    meas = (
        db.query(ThermalMetric.sst)
        .filter(ThermalMetric.node_id == node_id)
        .order_by(ThermalMetric.timestamp.desc(), ThermalMetric.id.desc())
        .limit(60)
        .all()
    )
    temps = [m[0] for m in reversed(meas)] if meas else [node.mmm_sst]

    latest_thermal = (
        db.query(ThermalMetric)
        .filter(ThermalMetric.node_id == node_id)
        .order_by(ThermalMetric.timestamp.desc())
        .first()
    )
    current_dhw = latest_thermal.dhw if latest_thermal else 0.0

    forecast = forecast_thermal_stress(
        historical_sst=temps,
        mmm=node.mmm_sst,
        current_dhw=current_dhw,
        horizon_days=horizon_days,
        step_days=0.25,  # telemetri tiap 6 jam
    )

    return {
        "node_id": node.id,
        "node_name": node.name,
        "mmm_sst": node.mmm_sst,
        "current_dhw": current_dhw,
        "forecast": forecast.to_dict(),
    }


@router.get("/qc-summary", response_model=Dict[str, Any])
def get_qc_summary(db: Session = Depends(get_db)):
    """Mengambil ringkasan statistik kendali mutu (QC) dari seluruh data yang diterima."""
    # Agregasi di SQL: sebelumnya seluruh baris dimuat ke Python setiap polling (2,5 dtk),
    # sehingga makin lambat seiring data bertambah.
    def count_flag(flag: QCFlag):
        return func.coalesce(func.sum(case((QCRecord.flag_mask.op("&")(int(flag)) != 0, 1), else_=0)), 0)

    row = db.query(
        func.count(QCRecord.id),
        func.coalesce(func.sum(case((QCRecord.is_valid.is_(True), 1), else_=0)), 0),
        count_flag(QCFlag.RANGE_FAIL),
        count_flag(QCFlag.SPIKE_FAIL),
        count_flag(QCFlag.STUCK_FAIL),
        count_flag(QCFlag.DRIFT_FAIL),
        count_flag(QCFlag.PACKET_LOSS),
        func.coalesce(func.sum(QCRecord.packet_loss_count), 0),
        count_flag(QCFlag.BATTERY_LOW),
        count_flag(QCFlag.DUPLICATE),
    ).one()
    (total_samples, total_valid, range_fails, spike_fails, stuck_fails, drift_fails,
     packet_loss_events, total_packets_dropped, battery_warnings, duplicates) = (int(v) for v in row)

    pass_rate = round((total_valid / total_samples * 100), 2) if total_samples > 0 else 100.0

    return {
        "total_samples": total_samples,
        "valid_samples": total_valid,
        "pass_rate_percent": pass_rate,
        "flags_breakdown": {
            "range_violations": range_fails,
            "spike_violations": spike_fails,
            "stuck_sensors": stuck_fails,
            "drift_sensors": drift_fails,
            "packet_loss_events": packet_loss_events,
            "total_packets_dropped": total_packets_dropped,
            "battery_low_warnings": battery_warnings,
            "duplicate_packets": duplicates,
        },
    }
