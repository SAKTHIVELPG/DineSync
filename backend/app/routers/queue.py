from fastapi import APIRouter, HTTPException
from typing import List, Optional, Dict, Any
from datetime import datetime
import random
from ..database import get_db_connection, query_db, execute_db
from ..models import QueueEntry, QueueJoinRequest, QueueActionRequest, QueueStatus
from ..ai_engine import ai_engine
from ..websocket_manager import ws_manager

router = APIRouter(prefix="/api/v1/queue", tags=["Queue"])

def generate_ticket_code() -> str:
    return f"Q-{random.randint(100, 999)}"

def recalculate_queue_positions(conn):
    """Update position # and dynamic wait estimates for all active waiting guests"""
    cur = conn.cursor()
    cur.execute("SELECT * FROM queue WHERE status = 'WAITING' ORDER BY created_at ASC")
    waiting_rows = cur.fetchall()

    for idx, r in enumerate(waiting_rows):
        pos = idx + 1
        # Recalculate estimated wait with AI engine
        ai_res = ai_engine.predict_wait_time(r["party_size"], r["preferred_section"])
        est_wait = ai_res["predicted_wait_minutes"]
        cur.execute("UPDATE queue SET estimated_wait_minutes = ? WHERE id = ?", (est_wait, r["id"]))
    conn.commit()

@router.get("", response_model=List[QueueEntry])
def get_queue(status: Optional[str] = None):
    conn = get_db_connection()
    cur = conn.cursor()
    
    if status:
        cur.execute("SELECT q.*, t.table_number as assigned_table_number FROM queue q LEFT JOIN tables t ON q.assigned_table_id = t.id WHERE q.status = ? ORDER BY q.created_at ASC", (status,))
    else:
        cur.execute("SELECT q.*, t.table_number as assigned_table_number FROM queue q LEFT JOIN tables t ON q.assigned_table_id = t.id WHERE q.status IN ('WAITING', 'CALLED') ORDER BY q.created_at ASC")
    
    rows = cur.fetchall()
    conn.close()

    result = []
    for idx, r in enumerate(rows):
        d = dict(r)
        d["position"] = idx + 1 if d["status"] == "WAITING" else 0
        result.append(QueueEntry(**d))
    return result

@router.post("/join", response_model=QueueEntry)
async def join_queue(req: QueueJoinRequest):
    conn = get_db_connection()
    cur = conn.cursor()

    # Generate unique ticket code
    ticket_code = generate_ticket_code()
    now = datetime.now()

    # Calculate AI wait time
    ai_pred = ai_engine.predict_wait_time(req.party_size, req.preferred_section)
    est_wait = ai_pred["predicted_wait_minutes"]

    cur.execute("""
        INSERT INTO queue (
            ticket_code, customer_name, phone, email, party_size,
            preferred_section, special_notes, status, estimated_wait_minutes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'WAITING', ?, ?)
    """, (
        ticket_code, req.customer_name, req.phone, req.email,
        req.party_size, req.preferred_section, req.special_notes,
        est_wait, now.isoformat()
    ))
    new_id = cur.lastrowid
    
    recalculate_queue_positions(conn)

    # Fetch newly created entry
    cur.execute("SELECT * FROM queue WHERE id = ?", (new_id,))
    row = cur.fetchone()
    
    # Calculate position
    cur.execute("SELECT COUNT(*) as pos FROM queue WHERE status = 'WAITING' AND created_at <= ?", (row["created_at"],))
    pos_row = cur.fetchone()
    pos = pos_row["pos"] if pos_row else 1

    conn.close()

    entry_dict = dict(row)
    entry_dict["position"] = pos
    entry = QueueEntry(**entry_dict)

    await ws_manager.broadcast_queue_update("JOINED", entry_dict)
    await ws_manager.broadcast_stats_refresh()

    return entry

@router.get("/lookup", response_model=QueueEntry)
def lookup_customer_ticket(phone: Optional[str] = None, ticket_code: Optional[str] = None):
    """Lookup active waiting or called queue ticket by customer phone or ticket code"""
    if not phone and not ticket_code:
        raise HTTPException(status_code=400, detail="Must provide phone or ticket_code for lookup")

    conn = get_db_connection()
    cur = conn.cursor()

    if ticket_code:
        cur.execute("SELECT q.*, t.table_number as assigned_table_number FROM queue q LEFT JOIN tables t ON q.assigned_table_id = t.id WHERE q.ticket_code = ? ORDER BY q.id DESC LIMIT 1", (ticket_code.strip(),))
    else:
        # Search by phone number (clean spaces and symbols)
        clean_phone = "".join(c for c in phone if c.isdigit())
        cur.execute("""
            SELECT q.*, t.table_number as assigned_table_number 
            FROM queue q 
            LEFT JOIN tables t ON q.assigned_table_id = t.id 
            WHERE replace(replace(replace(replace(q.phone, ' ', ''), '-', ''), '(', ''), ')', '') LIKE ? 
               OR q.phone = ?
            ORDER BY q.id DESC LIMIT 1
        """, (f"%{clean_phone}%", phone.strip()))

    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="No active ticket found for this phone or code")

    d = dict(row)
    if d["status"] == "WAITING":
        cur.execute("SELECT COUNT(*) as pos FROM queue WHERE status = 'WAITING' AND created_at <= ?", (d["created_at"],))
        pos_row = cur.fetchone()
        d["position"] = pos_row["pos"] if pos_row else 1
    else:
        d["position"] = 0

    conn.close()
    return QueueEntry(**d)

@router.get("/ticket/{ticket_code}", response_model=QueueEntry)
def get_ticket_status(ticket_code: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT q.*, t.table_number as assigned_table_number FROM queue q LEFT JOIN tables t ON q.assigned_table_id = t.id WHERE q.ticket_code = ?", (ticket_code,))
    row = cur.fetchone()
    
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Queue ticket not found")

    d = dict(row)
    if d["status"] == "WAITING":
        cur.execute("SELECT COUNT(*) as pos FROM queue WHERE status = 'WAITING' AND created_at <= ?", (d["created_at"],))
        pos_row = cur.fetchone()
        d["position"] = pos_row["pos"] if pos_row else 1
    else:
        d["position"] = 0

    conn.close()
    return QueueEntry(**d)

@router.post("/{queue_id}/action")
async def handle_queue_action(queue_id: int, action_req: QueueActionRequest):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM queue WHERE id = ?", (queue_id,))
    row = cur.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Queue entry not found")

    action = action_req.action.lower()
    now = datetime.now().isoformat()

    if action == "call":
        cur.execute("UPDATE queue SET status = 'CALLED', called_at = ? WHERE id = ?", (now, queue_id))
    
    elif action == "seat":
        table_id = action_req.table_id
        # If no table_id supplied, auto-assign best matching available table
        if not table_id:
            cur.execute("""
                SELECT id FROM tables 
                WHERE status = 'AVAILABLE' AND capacity >= ? 
                ORDER BY capacity ASC LIMIT 1
            """, (row["party_size"],))
            best_t = cur.fetchone()
            if not best_t:
                conn.close()
                raise HTTPException(status_code=400, detail="No matching available tables currently to seat this party")
            table_id = best_t["id"]

        # Mark table as OCCUPIED
        cur.execute("""
            UPDATE tables 
            SET status = 'OCCUPIED', occupied_since = ?, elapsed_minutes = 1, sensor_distance_cm = 25.0
            WHERE id = ?
        """, (now, table_id))

        # Update sensor if attached
        cur.execute("SELECT sensor_id FROM tables WHERE id = ?", (table_id,))
        t_info = cur.fetchone()
        if t_info and t_info["sensor_id"]:
            cur.execute("UPDATE sensor_nodes SET state = 'OCCUPIED', distance_cm = 25.0, last_ping = ? WHERE sensor_id = ?", (now, t_info["sensor_id"]))

        # Mark queue entry as SEATED
        cur.execute("UPDATE queue SET status = 'SEATED', seated_at = ?, assigned_table_id = ? WHERE id = ?", (now, table_id, queue_id))
        
        # Also broadcast table update
        cur.execute("SELECT * FROM tables WHERE id = ?", (table_id,))
        updated_t = cur.fetchone()
        if updated_t:
            await ws_manager.broadcast_table_update(dict(updated_t))

    elif action == "cancel":
        cur.execute("UPDATE queue SET status = 'CANCELLED' WHERE id = ?", (queue_id,))
    
    elif action == "no_show":
        cur.execute("UPDATE queue SET status = 'NO_SHOW' WHERE id = ?", (queue_id,))
    
    else:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Unknown queue action: {action}")

    recalculate_queue_positions(conn)
    conn.commit()

    # Fetch updated queue record
    cur.execute("SELECT q.*, t.table_number as assigned_table_number FROM queue q LEFT JOIN tables t ON q.assigned_table_id = t.id WHERE q.id = ?", (queue_id,))
    updated_q = cur.fetchone()
    conn.close()

    updated_dict = dict(updated_q)
    updated_dict["position"] = 0
    await ws_manager.broadcast_queue_update(action.upper(), updated_dict)
    await ws_manager.broadcast_stats_refresh()

    return {"message": f"Queue party successfully updated to {action}", "entry": updated_dict}
