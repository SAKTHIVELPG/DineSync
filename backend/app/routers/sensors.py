from fastapi import APIRouter, HTTPException
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import random
from ..database import get_db_connection, query_db, execute_db
from ..models import SensorTelemetryPayload, SensorInfo, SensorState
from ..websocket_manager import ws_manager

router = APIRouter(prefix="/api/v1/sensors", tags=["Sensors"])

@router.get("", response_model=List[SensorInfo])
def get_all_sensors():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT s.*, t.name as table_name, t.table_number 
        FROM sensor_nodes s
        LEFT JOIN tables t ON s.table_id = t.id
        ORDER BY s.sensor_id ASC
    """)
    rows = cur.fetchall()
    conn.close()

    now = datetime.now()
    sensors = []
    for r in rows:
        d = dict(r)
        # Check if online (ping within 3 minutes)
        is_online = True
        if d.get("last_ping"):
            try:
                ping_dt = datetime.fromisoformat(d["last_ping"])
                if (now - ping_dt).total_seconds() > 180:
                    is_online = False
            except Exception:
                is_online = False
        
        state = SensorState.ONLINE if is_online else SensorState.OFFLINE
        if is_online:
            if d.get("battery_level", 100) < 20:
                state = SensorState.WARNING
            elif d.get("state") == "OCCUPIED":
                state = SensorState.OCCUPIED
            else:
                state = SensorState.VACANT

        sensors.append(SensorInfo(
            sensor_id=d["sensor_id"],
            table_id=d.get("table_id"),
            table_name=d.get("table_name"),
            state=state,
            battery_level=d.get("battery_level", 100),
            signal_rssi=d.get("signal_rssi", -55),
            distance_cm=d.get("distance_cm", 120.0),
            last_ping=datetime.fromisoformat(d["last_ping"]) if d.get("last_ping") else now,
            firmware_version=d.get("firmware_version", "v2.1.0-esp32"),
            is_online=is_online
        ))
    return sensors

@router.post("/telemetry")
async def ingest_sensor_telemetry(payload: SensorTelemetryPayload):
    """
    Ingest real or simulated telemetry from ESP32 ultrasonic / IR sensor node.
    Automatically manages table occupancy state and records dining history.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    now = datetime.now().isoformat()
    sensor_id = payload.sensor_id
    occupied = payload.occupied or (payload.distance_cm < 50.0)
    state_str = "OCCUPIED" if occupied else "VACANT"

    # 1. Update or Insert Sensor Node
    cur.execute("SELECT * FROM sensor_nodes WHERE sensor_id = ?", (sensor_id,))
    sensor_row = cur.fetchone()

    table_id = payload.table_id
    if sensor_row:
        if not table_id:
            table_id = sensor_row["table_id"]
        cur.execute("""
            UPDATE sensor_nodes
            SET battery_level = ?, signal_rssi = ?, distance_cm = ?, state = ?, last_ping = ?, firmware_version = ?
            WHERE sensor_id = ?
        """, (
            payload.battery_level or 100,
            payload.signal_rssi or -55,
            payload.distance_cm,
            state_str,
            now,
            payload.firmware_version or "v2.1.0-esp32",
            sensor_id
        ))
    else:
        cur.execute("""
            INSERT INTO sensor_nodes (
                sensor_id, table_id, battery_level, signal_rssi, distance_cm, state, last_ping, firmware_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            sensor_id,
            table_id,
            payload.battery_level or 100,
            payload.signal_rssi or -55,
            payload.distance_cm,
            state_str,
            now,
            payload.firmware_version or "v2.1.0-esp32"
        ))

    # 2. Update Associated Table if linked
    updated_table = None
    if table_id or sensor_id:
        cur.execute("SELECT * FROM tables WHERE id = ? OR sensor_id = ?", (table_id, sensor_id))
        table_row = cur.fetchone()
        
        if table_row:
            t_id = table_row["id"]
            current_status = table_row["status"]
            new_status = current_status
            occ_since = table_row["occupied_since"]
            elapsed = table_row["elapsed_minutes"]

            if occupied and current_status != "OCCUPIED":
                # Customer sat down!
                new_status = "OCCUPIED"
                occ_since = now
                elapsed = 1
            elif not occupied and current_status == "OCCUPIED":
                # Customer vacated table -> transition to CLEANING / AVAILABLE
                new_status = "AVAILABLE"
                if occ_since:
                    try:
                        occ_dt = datetime.fromisoformat(occ_since)
                        dur = max(5.0, round((datetime.now() - occ_dt).total_seconds() / 60, 1))
                        cur.execute("""
                            INSERT INTO dining_history (
                                table_id, party_size, section, seated_at, cleared_at, duration_minutes,
                                wait_time_minutes, predicted_wait_minutes, day_of_week, hour_of_day
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (t_id, table_row["capacity"], table_row["section"], occ_since, now, dur, 10.0, 12.0, datetime.now().weekday(), datetime.now().hour))
                    except Exception:
                        pass
                occ_since = None
                elapsed = 0

            cur.execute("""
                UPDATE tables
                SET status = ?, occupied_since = ?, elapsed_minutes = ?, sensor_battery = ?,
                    sensor_rssi = ?, sensor_distance_cm = ?, last_sensor_ping = ?
                WHERE id = ?
            """, (
                new_status, occ_since, elapsed,
                payload.battery_level or table_row["sensor_battery"],
                payload.signal_rssi or table_row["sensor_rssi"],
                payload.distance_cm,
                now,
                t_id
            ))

            cur.execute("SELECT * FROM tables WHERE id = ?", (t_id,))
            updated_table = dict(cur.fetchone())

    conn.commit()
    conn.close()

    # Broadcast Live Telemetry & Table state
    telemetry_data = {
        "sensor_id": sensor_id,
        "table_id": table_id,
        "occupied": occupied,
        "distance_cm": payload.distance_cm,
        "battery_level": payload.battery_level,
        "signal_rssi": payload.signal_rssi,
        "timestamp": now
    }
    await ws_manager.broadcast_sensor_telemetry(telemetry_data)

    if updated_table:
        await ws_manager.broadcast_table_update(updated_table)
        await ws_manager.broadcast_stats_refresh()

    return {
        "status": "success",
        "message": f"Telemetry processed for sensor {sensor_id}",
        "table_updated": bool(updated_table),
        "current_table_state": updated_table.get("status") if updated_table else None
    }

@router.post("/simulate")
async def simulate_sensor_event(table_number: int, event_type: str):
    """
    Simulator helper to trigger ESP32 hardware events from the Admin UI with 1 click.
    event_type: 'OCCUPY', 'VACATE', 'BATTERY_LOW', 'PING'
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tables WHERE table_number = ?", (table_number,))
    table_row = cur.fetchone()
    conn.close()

    if not table_row:
        raise HTTPException(status_code=404, detail="Table not found")

    sensor_id = table_row["sensor_id"] or f"ESP32-NODE-{table_number:02d}"
    
    if event_type == "OCCUPY":
        payload = SensorTelemetryPayload(
            sensor_id=sensor_id,
            table_id=table_row["id"],
            distance_cm=round(random.uniform(18.0, 32.0), 1),
            occupied=True,
            battery_level=random.randint(85, 98),
            signal_rssi=random.randint(-62, -45)
        )
    elif event_type == "VACATE":
        payload = SensorTelemetryPayload(
            sensor_id=sensor_id,
            table_id=table_row["id"],
            distance_cm=round(random.uniform(115.0, 140.0), 1),
            occupied=False,
            battery_level=random.randint(85, 98),
            signal_rssi=random.randint(-62, -45)
        )
    elif event_type == "BATTERY_LOW":
        payload = SensorTelemetryPayload(
            sensor_id=sensor_id,
            table_id=table_row["id"],
            distance_cm=table_row["sensor_distance_cm"] or 120.0,
            occupied=(table_row["status"] == "OCCUPIED"),
            battery_level=12, # Low battery warning threshold
            signal_rssi=-84
        )
    else: # PING
        payload = SensorTelemetryPayload(
            sensor_id=sensor_id,
            table_id=table_row["id"],
            distance_cm=table_row["sensor_distance_cm"] or 120.0,
            occupied=(table_row["status"] == "OCCUPIED"),
            battery_level=table_row["sensor_battery"] or 90,
            signal_rssi=table_row["sensor_rssi"] or -55
        )

    return await ingest_sensor_telemetry(payload)
