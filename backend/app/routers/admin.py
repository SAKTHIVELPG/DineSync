from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, List
import uuid
from ..database import get_db_connection, seed_tables_and_sensors, seed_queue, seed_historical_data
from ..models import AdminLoginRequest, AdminLoginResponse, TableCreate, TableUpdate, AITrainResponse
from ..ai_engine import ai_engine
from ..websocket_manager import ws_manager

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])

VALID_ADMIN_PIN = "1234"

@router.post("/login", response_model=AdminLoginResponse)
def admin_login(req: AdminLoginRequest):
    if req.pin == VALID_ADMIN_PIN:
        token = f"admin-token-{uuid.uuid4().hex[:12]}"
        return AdminLoginResponse(
            authenticated=True,
            token=token,
            message="Admin authentication successful"
        )
    else:
        raise HTTPException(status_code=401, detail="Invalid Admin PIN. (Default demo PIN is 1234)")

@router.post("/tables")
async def create_table(req: TableCreate):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Check duplicate table_number
    cur.execute("SELECT id FROM tables WHERE table_number = ?", (req.table_number,))
    if cur.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail=f"Table number {req.table_number} already exists")

    cur.execute("""
        INSERT INTO tables (table_number, name, capacity, section, status, sensor_id, pos_x, pos_y, shape)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        req.table_number, req.name, req.capacity, req.section.value,
        req.status.value, req.sensor_id, req.pos_x or 0, req.pos_y or 0, req.shape or "rect"
    ))
    new_id = cur.lastrowid

    if req.sensor_id:
        cur.execute("""
            INSERT OR REPLACE INTO sensor_nodes (sensor_id, table_id, state)
            VALUES (?, ?, 'VACANT')
        """, (req.sensor_id, new_id))

    conn.commit()
    cur.execute("SELECT * FROM tables WHERE id = ?", (new_id,))
    t_dict = dict(cur.fetchone())
    conn.close()

    await ws_manager.broadcast_table_update(t_dict)
    await ws_manager.broadcast_stats_refresh()

    return {"message": "Table created successfully", "table": t_dict}

@router.put("/tables/{table_id}")
async def update_table(table_id: int, req: TableUpdate):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tables WHERE id = ?", (table_id,))
    existing = cur.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Table not found")

    name = req.name if req.name is not None else existing["name"]
    capacity = req.capacity if req.capacity is not None else existing["capacity"]
    section = req.section.value if req.section is not None else existing["section"]
    status = req.status.value if req.status is not None else existing["status"]
    sensor_id = req.sensor_id if req.sensor_id is not None else existing["sensor_id"]
    pos_x = req.pos_x if req.pos_x is not None else existing["pos_x"]
    pos_y = req.pos_y if req.pos_y is not None else existing["pos_y"]
    shape = req.shape if req.shape is not None else existing["shape"]

    cur.execute("""
        UPDATE tables
        SET name = ?, capacity = ?, section = ?, status = ?, sensor_id = ?, pos_x = ?, pos_y = ?, shape = ?
        WHERE id = ?
    """, (name, capacity, section, status, sensor_id, pos_x, pos_y, shape, table_id))

    if sensor_id:
        cur.execute("""
            INSERT OR REPLACE INTO sensor_nodes (sensor_id, table_id, state)
            VALUES (?, ?, 'VACANT')
        """, (sensor_id, table_id))

    conn.commit()
    cur.execute("SELECT * FROM tables WHERE id = ?", (table_id,))
    t_dict = dict(cur.fetchone())
    conn.close()

    await ws_manager.broadcast_table_update(t_dict)
    await ws_manager.broadcast_stats_refresh()

    return {"message": "Table updated successfully", "table": t_dict}

@router.delete("/tables/{table_id}")
async def delete_table(table_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM tables WHERE id = ?", (table_id,))
    cur.execute("UPDATE sensor_nodes SET table_id = NULL WHERE table_id = ?", (table_id,))
    conn.commit()
    conn.close()

    await ws_manager.broadcast_stats_refresh()
    return {"message": f"Table {table_id} deleted successfully"}

@router.post("/reset-demo")
async def reset_demo_data():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM tables")
    cur.execute("DELETE FROM queue")
    cur.execute("DELETE FROM sensor_nodes")
    cur.execute("DELETE FROM dining_history")
    cur.execute("DELETE FROM occupancy_snapshots")
    cur.execute("DELETE FROM notification_log")
    cur.execute("DELETE FROM reservations")
    cur.execute("DELETE FROM sqlite_sequence WHERE name IN ('tables', 'queue', 'sensor_nodes', 'dining_history', 'occupancy_snapshots', 'reservations', 'notification_log')")
    
    seed_tables_and_sensors(cur)
    seed_queue(cur)
    seed_historical_data(cur)
    conn.commit()
    conn.close()

    ai_engine.train_models()
    await ws_manager.broadcast_stats_refresh()

    return {"message": "DINESYNC demo database successfully re-seeded with fresh tables, sensors, and historical logs."}

@router.post("/train-ai", response_model=AITrainResponse)
async def trigger_ai_training():
    """Retrain AI regression and forecasting models on current historical data"""
    res = ai_engine.train_models()
    await ws_manager.broadcast_stats_refresh()
    return AITrainResponse(**res)
