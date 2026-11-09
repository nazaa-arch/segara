"""
Router REST API: Notifikasi dan Log Peringatan Dini SEGARA.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from ingestion.database import Session, Alert, init_db

router = APIRouter(prefix="/api/alerts", tags=["Alerts"])
session_factory = init_db()


def get_db():
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


@router.get("", response_model=List[Dict[str, Any]])
def list_alerts(
    node_id: Optional[int] = Query(None, description="Filter berdasarkan ID Node"),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Mengambil daftar log peringatan dini stres termal karang."""
    query = db.query(Alert)
    if node_id is not None:
        query = query.filter(Alert.node_id == node_id)

    alerts = query.order_by(Alert.timestamp.desc()).limit(limit).all()
    return [a.to_dict() for a in alerts]


@router.post("/{alert_id}/acknowledge", response_model=Dict[str, Any])
def acknowledge_alert(alert_id: int, db: Session = Depends(get_db)):
    """Menandai suatu peringatan telah ditindaklanjuti oleh pengelola kawasan."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.acknowledged = True
    alert.acknowledged_at = datetime.now(timezone.utc)
    db.commit()
    return alert.to_dict()
