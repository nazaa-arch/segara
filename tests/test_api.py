"""
Unit & Integration Test: Endpoint REST API SEGARA.
"""
import pytest
from fastapi.testclient import TestClient
from api.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health_check(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"


def test_list_nodes(client):
    res = client.get("/api/nodes")
    assert res.status_code == 200
    nodes = res.json()
    assert len(nodes) == 5
    assert nodes[0]["name"] == "Stasiun Bunaken Reef"


def test_get_measurements_latest(client):
    res = client.get("/api/measurements/latest")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)


def test_simulator_status_and_step(client):
    res = client.get("/api/simulator/status")
    assert res.status_code == 200
    status = res.json()
    assert "state" in status
    assert len(status["buoys"]) == 5

    # Trigger manual step
    step_res = client.post("/api/simulator/step?steps=1")
    assert step_res.status_code == 200
    assert step_res.json()["executed_steps"] == 1


def test_analytics_dhw(client):
    res = client.get("/api/analytics/dhw/1")
    assert res.status_code == 200
    data = res.json()
    assert data["node_id"] == 1
    assert "current_status" in data
    assert "history" in data


def test_evaluation_metrics(client):
    res = client.get("/api/evaluation/metrics")
    assert res.status_code == 200
    data = res.json()
    assert "packet_loss_monte_carlo" in data
    assert "quality_control_functional_verification" in data
    assert "dhw_algorithmic_verification" in data
    assert "forecasting_multi_horizon_evaluation" in data
    assert "in_process_execution_latency" in data
