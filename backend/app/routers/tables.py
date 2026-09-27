from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any
from datetime import datetime
from ..database import get_db_connection, query_db, execute_db
from ..models import Table, TableStatus, TableSection, TableUpdate
from ..websocket_manager import ws_manager

router = APIRouter(prefix="/api/v1/tables", tags=["Tables"])

@router.get("", response_model=List[Table])
def get_tables(
    section: Optional[str] = None,
    capacity: Optional[int] = None,
    status: Optional[str] = None
):
    conn = get_db_connection()
    cur = conn.cursor()
    
    query = "SELECT * FROM tables WHERE 1=1"
    params = []

    if section and section != "All":
        query += " AND section = ?"
        params.append(section)
    if capacity:
        query += " AND capacity >= ?"
        params.append(capacity)
    if status and status != "All":
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY table_number ASC"
    cur.execute(query, tuple(params))
    rows = cur.fetchall()
    
    # Calculate updated elapsed minutes
    now = datetime.now()
    tables = []
    for r in rows:
        t_dict = dict(r)
        if t_dict.get("status") == "OCCUPIED" and t_dict.get("occupied_since"):
            try:
                occ_dt = datetime.fromisoformat(t_dict["occupied_since"])
                t_dict["elapsed_minutes"] = max(1, int((now - occ_dt).total_seconds() / 60))
            except Exception:
                pass
        tables.append(Table(**t_dict))
    
    conn.close()
    return tables

@router.get("/summary/stats")
def get_table_stats():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tables")
    rows = cur.fetchall()
    conn.close()

    total = len(rows)
    available = sum(1 for r in rows if r["status"] == "AVAILABLE")
    occupied = sum(1 for r in rows if r["status"] == "OCCUPIED")
    reserved = sum(1 for r in rows if r["status"] == "RESERVED")
    cleaning = sum(1 for r in rows if r["status"] == "CLEANING")
    
    total_seats = sum(r["capacity"] for r in rows)
    occupied_seats = sum(r["capacity"] for r in rows if r["status"] == "OCCUPIED")

    occ_rate = round((occupied / total * 100), 1) if total > 0 else 0.0
    seat_occ_rate = round((occupied_seats / total_seats * 100), 1) if total_seats > 0 else 0.0

    return {
        "total_tables": total,
        "available_tables": available,
        "occupied_tables": occupied,
        "reserved_tables": reserved,
        "cleaning_tables": cleaning,
        "total_seats": total_seats,
        "occupied_seats": occupied_seats,
        "table_occupancy_rate": occ_rate,
        "seat_occupancy_rate": seat_occ_rate,
        "rush_status": "Peak Rush" if occ_rate >= 80 else ("Moderate" if occ_rate >= 50 else "Normal")
    }

@router.get("/{table_id}", response_model=Table)
def get_table_details(table_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tables WHERE id = ? OR table_number = ?", (table_id, table_id))
    row = cur.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Table not found")
    
    t_dict = dict(row)
    if t_dict.get("status") == "OCCUPIED" and t_dict.get("occupied_since"):
        try:
            occ_dt = datetime.fromisoformat(t_dict["occupied_since"])
            t_dict["elapsed_minutes"] = max(1, int((datetime.now() - occ_dt).total_seconds() / 60))
        except Exception:
            pass
    return Table(**t_dict)

@router.patch("/{table_id}/status")
async def update_table_status(table_id: int, status_update: TableUpdate):
    if not status_update.status:
        raise HTTPException(status_code=400, detail="Status must be provided")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tables WHERE id = ?", (table_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Table not found")

    now = datetime.now().isoformat()
    old_status = row["status"]
    new_status = status_update.status.value

    occupied_since = row["occupied_since"]
    elapsed_minutes = 0

    if new_status == "OCCUPIED":
        occupied_since = now
        elapsed_minutes = 1
        sensor_dist = 25.0
        sensor_state = "OCCUPIED"
    else:
        # If transitioning from OCCUPIED to AVAILABLE/CLEANING, log to dining_history
        if old_status == "OCCUPIED" and row["occupied_since"]:
            try:
                occ_dt = datetime.fromisoformat(row["occupied_since"])
                dur = max(5.0, round((datetime.now() - occ_dt).total_seconds() / 60, 1))
                cur.execute("""
                    INSERT INTO dining_history (
                        table_id, party_size, section, seated_at, cleared_at, duration_minutes,
                        wait_time_minutes, predicted_wait_minutes, day_of_week, hour_of_day
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (table_id, row["capacity"], row["section"], row["occupied_since"], now, dur, 10.0, 12.0, datetime.now().weekday(), datetime.now().hour))
            except Exception:
                pass

        occupied_since = None
        elapsed_minutes = 0
        sensor_dist = 120.0
        sensor_state = "VACANT"

    cur.execute("""
        UPDATE tables
        SET status = ?, occupied_since = ?, elapsed_minutes = ?, sensor_distance_cm = ?
        WHERE id = ?
    """, (new_status, occupied_since, elapsed_minutes, sensor_dist, table_id))

    if row["sensor_id"]:
        cur.execute("""
            UPDATE sensor_nodes
            SET state = ?, distance_cm = ?, last_ping = ?
            WHERE sensor_id = ?
        """, (sensor_state, sensor_dist, now, row["sensor_id"]))

    conn.commit()

    # Fetch updated table
    cur.execute("SELECT * FROM tables WHERE id = ?", (table_id,))
    updated_row = cur.fetchone()
    conn.close()

    updated_dict = dict(updated_row)
    await ws_manager.broadcast_table_update(updated_dict)
    await ws_manager.broadcast_stats_refresh()

    return {"message": "Table status updated", "table": updated_dict}
