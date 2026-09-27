import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database import init_db
from backend.app.ai_engine import ai_engine

@pytest.fixture(scope="session", autouse=True)
def setup_test_app():
    init_db()
    ai_engine.train_models()

@pytest.fixture
def client():
    return TestClient(app)

def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "service" in data

def test_get_tables_and_stats(client):
    response = client.get("/api/v1/tables")
    assert response.status_code == 200
    tables = response.json()
    assert len(tables) >= 16
    assert "table_number" in tables[0]
    assert "section" in tables[0]
    assert "status" in tables[0]

    # Stats endpoint
    stats_res = client.get("/api/v1/tables/summary/stats")
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert stats["total_tables"] >= 16
    assert "available_tables" in stats
    assert "table_occupancy_rate" in stats

def test_table_filtering(client):
    # Filter by section
    res = client.get("/api/v1/tables?section=Patio")
    assert res.status_code == 200
    patio_tables = res.json()
    for t in patio_tables:
        assert t["section"] == "Patio"

    # Filter by capacity
    res_cap = client.get("/api/v1/tables?capacity=6")
    assert res_cap.status_code == 200
    large_tables = res_cap.json()
    for t in large_tables:
        assert t["capacity"] >= 6

def test_table_status_update(client):
    # Update table 1 status to OCCUPIED
    res = client.patch("/api/v1/tables/1/status", json={"status": "OCCUPIED"})
    assert res.status_code == 200
    data = res.json()
    assert data["table"]["status"] == "OCCUPIED"

    # Revert back to AVAILABLE
    res2 = client.patch("/api/v1/tables/1/status", json={"status": "AVAILABLE"})
    assert res2.status_code == 200
    assert res2.json()["table"]["status"] == "AVAILABLE"

def test_queue_flow(client):
    # 1. Join queue
    join_payload = {
        "customer_name": "Alexander Knight",
        "phone": "+1 555-0999",
        "email": "aknight@example.com",
        "party_size": 4,
        "preferred_section": "Main Dining",
        "special_notes": "Booth preferred"
    }
    join_res = client.post("/api/v1/queue/join", json=join_payload)
    assert join_res.status_code == 200
    ticket = join_res.json()
    assert ticket["customer_name"] == "Alexander Knight"
    assert ticket["status"] == "WAITING"
    ticket_code = ticket["ticket_code"]
    queue_id = ticket["id"]

    # 2. Get ticket status
    ticket_res = client.get(f"/api/v1/queue/ticket/{ticket_code}")
    assert ticket_res.status_code == 200
    assert ticket_res.json()["ticket_code"] == ticket_code

    # 2b. Lookup by phone and by ticket_code
    lookup_phone_res = client.get("/api/v1/queue/lookup?phone=5550999")
    assert lookup_phone_res.status_code == 200
    assert lookup_phone_res.json()["customer_name"] == "Alexander Knight"

    lookup_code_res = client.get(f"/api/v1/queue/lookup?ticket_code={ticket_code}")
    assert lookup_code_res.status_code == 200
    assert lookup_code_res.json()["ticket_code"] == ticket_code

    # 3. Call party
    call_res = client.post(f"/api/v1/queue/{queue_id}/action", json={"action": "call"})
    assert call_res.status_code == 200
    assert call_res.json()["entry"]["status"] == "CALLED"

    # 4. Seat party
    seat_res = client.post(f"/api/v1/queue/{queue_id}/action", json={"action": "seat", "table_id": 5})
    assert seat_res.status_code == 200
    assert seat_res.json()["entry"]["status"] == "SEATED"

def test_sensor_telemetry_and_simulation(client):
    # Ingest telemetry for ESP32-NODE-03 (Table 3)
    telemetry_payload = {
        "sensor_id": "ESP32-NODE-03",
        "table_id": 3,
        "distance_cm": 22.0,
        "occupied": True,
        "battery_level": 95,
        "signal_rssi": -48
    }
    res = client.post("/api/v1/sensors/telemetry", json=telemetry_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["current_table_state"] == "OCCUPIED"

    # Get sensors list
    s_list_res = client.get("/api/v1/sensors")
    assert s_list_res.status_code == 200
    sensors = s_list_res.json()
    assert len(sensors) >= 16

    # Test simulator trigger
    sim_res = client.post("/api/v1/sensors/simulate?table_number=3&event_type=VACATE")
    assert sim_res.status_code == 200
    assert sim_res.json()["current_table_state"] == "AVAILABLE"

def test_ai_predictions_endpoints(client):
    # Wait time estimation
    req = {
        "party_size": 4,
        "preferred_section": "Patio"
    }
    res = client.post("/api/v1/predictions/wait-time", json=req)
    assert res.status_code == 200
    data = res.json()
    assert "predicted_wait_minutes" in data
    assert "confidence_score" in data
    assert "factors" in data

    # Hourly forecast
    fc_res = client.get("/api/v1/predictions/hourly-forecast")
    assert fc_res.status_code == 200
    forecast = fc_res.json()
    assert len(forecast) == 24

    # Peak hours and heatmap
    pk_res = client.get("/api/v1/predictions/peak-hours")
    assert pk_res.status_code == 200
    pk_data = pk_res.json()
    assert "current_occupancy_rate" in pk_data
    assert len(pk_data["heatmap_matrix"]) == 7

def test_analytics_and_admin(client):
    # Analytics summary
    res = client.get("/api/v1/analytics/summary")
    assert res.status_code == 200
    summary = res.json()
    assert summary["total_seated_today"] >= 0
    assert "avg_dining_duration_mins" in summary
    assert "section_popularity" in summary

    # Admin login
    login_res = client.post("/api/v1/admin/login", json={"pin": "1234"})
    assert login_res.status_code == 200
    assert login_res.json()["authenticated"] is True

    # Bad PIN
    bad_login = client.post("/api/v1/admin/login", json={"pin": "0000"})
    assert bad_login.status_code == 401

def test_admin_train_ai(client):
    train_res = client.post("/api/v1/admin/train-ai")
    assert train_res.status_code == 200
    data = train_res.json()
    assert data["success"] is True
    assert data["is_trained"] is True
    assert data["training_samples"] > 0
    assert "r2_score" in data
    assert "last_trained" in data

def test_admin_table_crud(client):
    # 1. Create table 99
    new_table = {
        "table_number": 99,
        "name": "VIP Penthouse Table",
        "capacity": 8,
        "section": "VIP Booth",
        "status": "AVAILABLE",
        "sensor_id": "ESP32-NODE-99",
        "shape": "booth",
        "pos_x": 300,
        "pos_y": 300
    }
    create_res = client.post("/api/v1/admin/tables", json=new_table)
    assert create_res.status_code == 200
    created = create_res.json()["table"]
    created_id = created["id"]
    assert created["table_number"] == 99

    # 2. Update table
    update_res = client.put(f"/api/v1/admin/tables/{created_id}", json={"name": "VIP Penthouse Suite", "capacity": 10})
    assert update_res.status_code == 200
    updated = update_res.json()["table"]
    assert updated["name"] == "VIP Penthouse Suite"
    assert updated["capacity"] == 10

    # 3. Delete table
    del_res = client.delete(f"/api/v1/admin/tables/{created_id}")
    assert del_res.status_code == 200

