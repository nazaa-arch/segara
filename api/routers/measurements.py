"""
Router REST API: Pembacaan Data Telemetri Mentah & Riwayat.
"""
from fastapi import APIRouter, Depends, Query
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import joinedload
from ingestion.database import Session, Measurement, QCRecord, init_db

router = APIRouter(prefix="/api/measurements", tags=["Measurements"])
session_factory = init_db()


def get_db():
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


@router.get("/latest", response_model=List[Dict[str, Any]])
def get_latest_measurements(db: Session = Depends(get_db)):
    """Mengambil rekaman telemetri terbaru dari setiap stasiun pelampung."""
    from ingestion.database import Node
    nodes = db.query(Node).all()
    results = []

    for node in nodes:
        meas = (
            db.query(Measurement)
            .filter(Measurement.node_id == node.id)
            .order_by(Measurement.timestamp.desc())
            .first()
        )
        if meas:
            m_dict = meas.to_dict()
            qc = db.query(QCRecord).filter(QCRecord.measurement_id == meas.id).first()
            m_dict["qc"] = qc.to_dict() if qc else None
            results.append(m_dict)

    return results


@router.get("/history", response_model=List[Dict[str, Any]])
def get_measurement_history(
    node_id: Optional[int] = Query(None, description="Filter berdasarkan ID Node (1-5)"),
    limit: int = Query(100, ge=1, le=1000, description="Batas jumlah rekaman"),
    db: Session = Depends(get_db),
):
    """Mengambil riwayat deret waktu telemetri beserta label QC."""
    query = db.query(Measurement)
    if node_id is not None:
        query = query.filter(Measurement.node_id == node_id)

    # Ambil N rekaman TERBARU, lalu urutkan kronologis untuk grafik.
    # QC dimuat dalam satu JOIN (sebelumnya 1 query per baris).
    latest = (
        query.options(joinedload(Measurement.qc))
        .order_by(Measurement.timestamp.desc(), Measurement.id.desc())
        .limit(limit)
        .all()
    )
    results = []
    for m in reversed(latest):
        m_dict = m.to_dict()
        m_dict["qc"] = m.qc.to_dict() if m.qc else None
        results.append(m_dict)

    return results
