"""
Router REST API: Pengelolaan dan Status Node Pelampung Virtual SEGARA.
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from ingestion.database import Session, Node, Measurement, ThermalMetric, init_db

router = APIRouter(prefix="/api/nodes", tags=["Nodes"])
session_factory = init_db()


def get_db():
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


@router.get("", response_model=List[Dict[str, Any]])
def list_nodes(db: Session = Depends(get_db)):
    """Mengambil daftar semua stasiun pelampung terumbu karang dengan status terkini."""
    nodes = db.query(Node).all()
    results = []

    for node in nodes:
        node_dict = node.to_dict()

        # Ambil pengukuran terkini
        latest_meas = (
            db.query(Measurement)
            .filter(Measurement.node_id == node.id)
            .order_by(Measurement.timestamp.desc())
            .first()
        )
        # Ambil metrik termal terkini
        latest_thermal = (
            db.query(ThermalMetric)
            .filter(ThermalMetric.node_id == node.id)
            .order_by(ThermalMetric.timestamp.desc())
            .first()
        )

        node_dict["latest_measurement"] = latest_meas.to_dict() if latest_meas else None
        node_dict["latest_thermal"] = latest_thermal.to_dict() if latest_thermal else {
            "sst": latest_meas.temperature if latest_meas else node.mmm_sst,
            "mmm": node.mmm_sst,
            "hotspot": 0.0,
            "dhw": 0.0,
            "alert_level": 0,
            "alert_label": "No Stress",
            "compound_stress": 0.0,
        }
        results.append(node_dict)

    return results


@router.get("/{node_id}", response_model=Dict[str, Any])
def get_node_detail(node_id: int, db: Session = Depends(get_db)):
    """Mengambil rincian satu stasiun pelampung berdasarkan ID."""
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

    latest_meas = (
        db.query(Measurement)
        .filter(Measurement.node_id == node.id)
        .order_by(Measurement.timestamp.desc())
        .first()
    )
    latest_thermal = (
        db.query(ThermalMetric)
        .filter(ThermalMetric.node_id == node.id)
        .order_by(ThermalMetric.timestamp.desc())
        .first()
    )

    node_dict = node.to_dict()
    node_dict["latest_measurement"] = latest_meas.to_dict() if latest_meas else None
    node_dict["latest_thermal"] = latest_thermal.to_dict() if latest_thermal else None

    return node_dict
