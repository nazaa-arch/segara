"""
Router REST API: Pengendali Simulator Telemetri & Injeksi Gangguan SEGARA.
"""
import threading
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from simulator.generator import CoralBuoySimulator, FaultConfig
from simulator.replay import HistoricalReplayEngine
from simulator.publisher import TelemetryPublisher
from ingestion.subscriber import IngestionPipeline

router = APIRouter(prefix="/api/simulator", tags=["Simulator"])

# Global simulator & ingestion singleton instance
# Gelombang panas naik/turun 0,15 °C per siklus 6 jam (penuh +2,2 °C dalam ±4 hari)
_simulator = CoralBuoySimulator(seed=42, heatwave_ramp_per_step=0.15)
_replay_engine = HistoricalReplayEngine()
_ingestion = IngestionPipeline()
_publisher = TelemetryPublisher()

# Hubungkan publisher ke ingestion pipeline secara langsung (memastikan data tetap mengalir bahkan saat broker offline)
_publisher.local_subscriber_hook = _ingestion.process_raw_message

# Simulator state
_sim_state = {
    "is_running": False,
    "scenario": "normal",  # "normal", "heatwave", "storm", "historical_replay", "fault_injection"
    "step_count": 0,
    "speed_sec": 1.0,
    "packet_loss_rate": 0.0,
}


# Satu langkah simulasi pada satu waktu: loop latar dan endpoint /step / /control
# berjalan di thread berbeda dan berbagi simulator + pipeline.
_sim_lock = threading.Lock()


class ControlRequest(BaseModel):
    # 'control' = hanya ubah setelan (skenario / loss / kecepatan) tanpa start/stop.
    action: Literal["start", "stop", "step", "reset", "control"] = Field(
        ..., description="'start', 'stop', 'step', 'reset', 'control' (ubah setelan saja)"
    )
    # Field yang tidak dikirim (None) TIDAK mengubah setelan yang sedang berlaku.
    scenario: Optional[Literal["normal", "heatwave", "storm", "historical_replay", "fault_injection"]] = None
    speed_sec: Optional[float] = Field(None, ge=0.2, le=60.0)
    packet_loss_rate: Optional[float] = Field(None, ge=0.0, le=0.9)


class FaultInjectionRequest(BaseModel):
    node_id: int
    fault_type: Literal["spike", "stuck", "drift", "out_of_range", "packet_loss", "clear"] = Field(
        ..., description="'spike', 'stuck', 'drift', 'out_of_range', 'packet_loss', 'clear'"
    )
    param: Optional[Literal["temperature", "ph", "salinity", "turbidity"]] = "temperature"
    magnitude: Optional[float] = Field(3.0, ge=-20.0, le=20.0)
    cycles: Optional[int] = Field(8, ge=1, le=500)
    loss_rate: Optional[float] = Field(0.20, ge=0.0, le=0.9)


def execute_sim_step(scenario: str, packet_loss: float = 0.0) -> List[Dict[str, Any]]:
    """Mengeksekusi satu siklus telemetri untuk seluruh 5 node pelampung virtual (thread-safe)."""
    with _sim_lock:
        return _execute_sim_step_unlocked(scenario, packet_loss)


def _execute_sim_step_unlocked(scenario: str, packet_loss: float) -> List[Dict[str, Any]]:
    results = []

    for node_id in [1, 2, 3, 4, 5]:
        buoy = _simulator.buoys.get(node_id)
        if not buoy:
            continue

        buoy.faults.packet_loss_rate = packet_loss

        # Konfigurasi skenario lingkungan
        if scenario == "heatwave":
            _simulator.set_heatwave(node_id, active=True, intensity=2.2)
            _simulator.set_storm(node_id, active=False)
        elif scenario == "storm":
            _simulator.set_storm(node_id, active=True)
            _simulator.set_heatwave(node_id, active=False)
        elif scenario == "historical_replay":
            # Replay SST dari CSV rekonstruksi (bukan unduhan NOAA terverifikasi).
            # Paket tetap dibuat oleh pelampung yang sama agar counter berlanjut
            # (tanpa "reboot"/paket hilang palsu saat ganti skenario) dan pH,
            # salinitas, kekeruhan tetap bervariasi (tanpa flag "stuck" palsu);
            # hanya suhu yang diganti dengan nilai historis.
            _simulator.set_heatwave(node_id, active=False)
            _simulator.set_storm(node_id, active=False)
            item = _replay_engine.step_next(node_id)
            if item:
                _, rec = item
                pkt = _simulator.generate_next_packet(node_id=node_id)
                if pkt is None:
                    results.append({"node_id": node_id, "mode": "dropped", "reason": "simulated_packet_loss"})
                    continue
                pkt.temperature = rec.sst
                _publisher.publish_packet(pkt)
                results.append({"node_id": node_id, "mode": "historical", "sst": rec.sst, "dhw_official": rec.dhw_official})
                continue
        else:
            _simulator.set_heatwave(node_id, active=False)
            _simulator.set_storm(node_id, active=False)

        # Hasilkan paket baru
        pkt = _simulator.generate_next_packet(node_id=node_id)
        if pkt is not None:
            _publisher.publish_packet(pkt)
            results.append({"node_id": node_id, "mode": "synthetic", "packet": pkt.to_dict()})
        else:
            results.append({"node_id": node_id, "mode": "dropped", "reason": "simulated_packet_loss"})

    _sim_state["step_count"] += 1
    return results


@router.get("/status")
def get_simulator_status():
    """Mengambil status operasi terkini simulator."""
    return {
        "state": _sim_state,
        "buoys": [
            {
                "node_id": b.node_id,
                "name": b.name,
                "counter": b.counter,
                "battery": round(b.battery, 1),
                "in_heatwave": b.in_heatwave,
                "in_storm": b.in_storm,
                "packet_loss_rate": b.faults.packet_loss_rate,
                "active_faults": {
                    "stuck": b.faults.stuck_param if b.faults.stuck_cycles_remaining > 0 else None,
                    "drift": b.faults.drift_param if b.faults.drift_rate_per_cycle > 0 else None,
                    "spike": b.faults.spike_param,
                },
            }
            for b in _simulator.buoys.values()
        ],
        "replay_records": {nid: _replay_engine.get_total_records(nid) for nid in [1, 2, 3, 4, 5]},
    }


@router.post("/step")
def trigger_manual_step(steps: int = Query(1, ge=1, le=200)):
    """Menjalankan sejumlah langkah waktu simulasi secara manual."""
    all_step_results = []
    for _ in range(steps):
        res = execute_sim_step(
            scenario=_sim_state["scenario"],
            packet_loss=_sim_state["packet_loss_rate"],
        )
        all_step_results.append(res)
    return {"executed_steps": steps, "total_steps": _sim_state["step_count"], "latest_step": all_step_results[-1]}


@router.post("/control")
def control_simulation(req: ControlRequest):
    """Mengontrol jalannya simulasi (start, stop, ganti skenario, atau reset)."""
    if req.action == "start":
        _sim_state["is_running"] = True
    elif req.action == "stop":
        _sim_state["is_running"] = False
    elif req.action == "step":
        execute_sim_step(
            scenario=req.scenario or _sim_state["scenario"],
            packet_loss=req.packet_loss_rate if req.packet_loss_rate is not None else _sim_state["packet_loss_rate"],
        )
    elif req.action == "reset":
        _sim_state["is_running"] = False
        _sim_state["step_count"] = 0
        _replay_engine.reset()
        for nid in _simulator.buoys:
            _simulator.clear_faults(nid)
            _simulator.set_heatwave(nid, False)
            _simulator.set_storm(nid, False)

    if req.scenario:
        _sim_state["scenario"] = req.scenario
    if req.speed_sec is not None:
        _sim_state["speed_sec"] = req.speed_sec
    if req.packet_loss_rate is not None:
        _sim_state["packet_loss_rate"] = req.packet_loss_rate

    return {"status": "success", "state": _sim_state}


@router.post("/inject-fault")
def inject_sensor_fault(req: FaultInjectionRequest):
    """Menyuntikkan gangguan sensor spesifik pada satu node pelampung virtual."""
    buoy = _simulator.buoys.get(req.node_id)
    if not buoy:
        raise HTTPException(status_code=404, detail=f"Node {req.node_id} not found")

    if req.fault_type == "spike":
        buoy.faults.spike_param = req.param or "temperature"
        buoy.faults.spike_magnitude = req.magnitude or 3.0
    elif req.fault_type == "stuck":
        buoy.faults.stuck_param = req.param or "temperature"
        buoy.faults.stuck_cycles_remaining = req.cycles or 8
    elif req.fault_type == "drift":
        buoy.faults.drift_param = req.param or "ph"
        buoy.faults.drift_rate_per_cycle = 0.02
        buoy.faults.drift_accumulated = 0.0
    elif req.fault_type == "out_of_range":
        buoy.faults.out_of_range_param = req.param or "temperature"
    elif req.fault_type == "packet_loss":
        buoy.faults.packet_loss_rate = req.loss_rate or 0.20
    elif req.fault_type == "clear":
        _simulator.clear_faults(req.node_id)

    return {
        "status": "fault_injected",
        "node_id": req.node_id,
        "fault_type": req.fault_type,
        "param": req.param,
    }
