"""
Model Database dan Pengelolaan Sesi SEGARA.
Mendukung SQLite (default lokal) dan PostgreSQL/TimescaleDB.
"""
from __future__ import annotations
import os
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    event,
    create_engine,
    Column,
    Integer,
    Float,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    Index,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session
from sqlalchemy.pool import QueuePool

Base = declarative_base()


class Node(Base):
    __tablename__ = "nodes"

    id = Column(Integer, primary_key=True)  # Node ID pelampung (1-255)
    name = Column(String(100), nullable=False)
    region = Column(String(100), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    mmm_sst = Column(Float, nullable=False)  # Maximum Monthly Mean (°C)
    bleaching_threshold = Column(Float, nullable=False)  # MMM + 1.0°C
    depth_m = Column(Float, default=5.0)
    is_active = Column(Boolean, default=True)
    last_seen = Column(DateTime, nullable=True)
    battery = Column(Integer, default=100)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    measurements = relationship("Measurement", back_populates="node", cascade="all, delete-orphan")
    thermal_metrics = relationship("ThermalMetric", back_populates="node", cascade="all, delete-orphan")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "region": self.region,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "mmm_sst": self.mmm_sst,
            "bleaching_threshold": self.bleaching_threshold,
            "depth_m": self.depth_m,
            "is_active": self.is_active,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "battery": self.battery,
        }


class Measurement(Base):
    __tablename__ = "measurements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    node_id = Column(Integer, ForeignKey("nodes.id"), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True, default=lambda: datetime.now(timezone.utc))
    counter = Column(Integer, nullable=False)
    temperature = Column(Float, nullable=False)
    ph = Column(Float, nullable=False)
    salinity = Column(Float, nullable=False)
    turbidity = Column(Float, nullable=False)
    battery = Column(Integer, nullable=False)
    raw_hex = Column(String(32), nullable=True)

    node = relationship("Node", back_populates="measurements")
    qc = relationship("QCRecord", back_populates="measurement", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_meas_node_time", "node_id", "timestamp"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "node_id": self.node_id,
            "timestamp": self.timestamp.isoformat(),
            "counter": self.counter,
            "temperature": round(self.temperature, 2),
            "ph": round(self.ph, 2),
            "salinity": round(self.salinity, 2),
            "turbidity": round(self.turbidity, 1),
            "battery": self.battery,
            "raw_hex": self.raw_hex,
        }


class QCRecord(Base):
    __tablename__ = "qc_flags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    measurement_id = Column(Integer, ForeignKey("measurements.id"), nullable=False, unique=True, index=True)
    node_id = Column(Integer, nullable=False, index=True)
    flag_mask = Column(Integer, nullable=False)
    flag_names = Column(String(200), nullable=False)
    is_valid = Column(Boolean, nullable=False)
    packet_loss_count = Column(Integer, default=0)
    details_json = Column(Text, default="{}")

    measurement = relationship("Measurement", back_populates="qc")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "measurement_id": self.measurement_id,
            "node_id": self.node_id,
            "flag_mask": self.flag_mask,
            "flag_names": self.flag_names.split(",") if self.flag_names else [],
            "is_valid": self.is_valid,
            "packet_loss_count": self.packet_loss_count,
            "details": json.loads(self.details_json) if self.details_json else {},
        }


class ThermalMetric(Base):
    __tablename__ = "thermal_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    node_id = Column(Integer, ForeignKey("nodes.id"), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True, default=lambda: datetime.now(timezone.utc))
    sst = Column(Float, nullable=False)
    mmm = Column(Float, nullable=False)
    hotspot = Column(Float, nullable=False)
    dhw = Column(Float, nullable=False)
    alert_level = Column(Integer, nullable=False)  # 0 to 4
    alert_label = Column(String(30), nullable=False)
    compound_stress = Column(Float, default=0.0)

    node = relationship("Node", back_populates="thermal_metrics")

    __table_args__ = (
        Index("idx_thermal_node_time", "node_id", "timestamp"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "node_id": self.node_id,
            "timestamp": self.timestamp.isoformat(),
            "sst": round(self.sst, 2),
            "mmm": round(self.mmm, 2),
            "hotspot": round(self.hotspot, 2),
            "dhw": round(self.dhw, 2),
            "alert_level": self.alert_level,
            "alert_label": self.alert_label,
            "compound_stress": round(self.compound_stress, 3),
        }


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    node_id = Column(Integer, nullable=False, index=True)
    node_name = Column(String(100), nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True, default=lambda: datetime.now(timezone.utc))
    alert_level = Column(Integer, nullable=False)
    alert_type = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    acknowledged = Column(Boolean, default=False)
    acknowledged_at = Column(DateTime, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "node_id": self.node_id,
            "node_name": self.node_name,
            "timestamp": self.timestamp.isoformat(),
            "alert_level": self.alert_level,
            "alert_type": self.alert_type,
            "message": self.message,
            "acknowledged": self.acknowledged,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
        }


# Daftar default 5 stasiun pelampung virtual di terumbu karang utama Indonesia
DEFAULT_BUOY_NODES = [
    {
        "id": 1,
        "name": "Stasiun Bunaken Reef",
        "region": "Taman Nasional Bunaken, Sulawesi Utara",
        "latitude": 1.6240,
        "longitude": 124.7570,
        "mmm_sst": 29.20,
        "bleaching_threshold": 30.20,
        "depth_m": 4.5,
    },
    {
        "id": 2,
        "name": "Stasiun Raja Ampat Kri",
        "region": "Kepulauan Dampier, Raja Ampat, Papua Barat Daya",
        "latitude": -0.5510,
        "longitude": 130.6720,
        "mmm_sst": 29.50,
        "bleaching_threshold": 30.50,
        "depth_m": 5.0,
    },
    {
        "id": 3,
        "name": "Stasiun Wakatobi Tomia",
        "region": "Taman Nasional Wakatobi, Sulawesi Tenggara",
        "latitude": -5.5120,
        "longitude": 123.7540,
        "mmm_sst": 29.10,
        "bleaching_threshold": 30.10,
        "depth_m": 6.0,
    },
    {
        "id": 4,
        "name": "Stasiun Karimunjawa Menjangan",
        "region": "Taman Nasional Karimunjawa, Jawa Tengah",
        "latitude": -5.8520,
        "longitude": 110.4530,
        "mmm_sst": 29.60,
        "bleaching_threshold": 30.60,
        "depth_m": 4.0,
    },
    {
        "id": 5,
        "name": "Stasiun Komodo Padar",
        "region": "Taman Nasional Komodo, NTT",
        "latitude": -8.5520,
        "longitude": 119.5310,
        "mmm_sst": 28.80,
        "bleaching_threshold": 29.80,
        "depth_m": 7.0,
    },
]


def get_database_url() -> str:
    """Mengambil URL database dari environment atau default ke SQLite lokal."""
    return os.environ.get("SEGARA_DATABASE_URL", "sqlite:///segara.db")


_SESSION_FACTORIES: Dict[str, sessionmaker] = {}


def _configure_sqlite(engine) -> None:
    """WAL: pembaca tidak terblokir penulis; busy_timeout: tunggu kunci, bukan error."""

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()


def init_db(database_url: Optional[str] = None) -> sessionmaker:
    """
    Menginisialisasi tabel database dan mengisi data stasiun bawaan.

    Untuk DB berbasis file, satu engine dipakai bersama per URL (sebelumnya setiap
    router membuat engine sendiri). ``sqlite:///:memory:`` selalu mendapat DB baru.
    """
    url = database_url or get_database_url()
    is_memory = ":memory:" in url or url in ("sqlite://", "sqlite:///")
    if not is_memory and url in _SESSION_FACTORIES:
        return _SESSION_FACTORIES[url]

    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine_kwargs: Dict[str, Any] = {"connect_args": connect_args}
    if url.startswith("sqlite") and not is_memory:
        # SQLAlchemy 1.4 memakai NullPool untuk SQLite file: koneksi dibuka & ditutup
        # pada setiap sesi (~7 ms/paket, plus checkpoint WAL saat close). Pakai pool.
        engine_kwargs.update(poolclass=QueuePool, pool_size=5, max_overflow=10, pool_pre_ping=False)
    engine = create_engine(url, **engine_kwargs)
    if url.startswith("sqlite") and not is_memory:
        _configure_sqlite(engine)
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    if not is_memory:
        _SESSION_FACTORIES[url] = SessionLocal

    # Isi node awal jika tabel masih kosong
    with SessionLocal() as session:
        count = session.query(Node).count()
        if count == 0:
            for node_data in DEFAULT_BUOY_NODES:
                node = Node(
                    id=node_data["id"],
                    name=node_data["name"],
                    region=node_data["region"],
                    latitude=node_data["latitude"],
                    longitude=node_data["longitude"],
                    mmm_sst=node_data["mmm_sst"],
                    bleaching_threshold=node_data["bleaching_threshold"],
                    depth_m=node_data["depth_m"],
                    battery=100,
                )
                session.add(node)
            session.commit()

    return SessionLocal


# Factory sesi default modul
SessionLocal = init_db()

