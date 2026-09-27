import re
import secrets
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..database import get_db_connection
from ..websocket_manager import ws_manager

router = APIRouter(prefix="/api/v1/reservations", tags=["Reservations"])


class ReservationRequest(BaseModel):
    table_id: int
    customer_name: str = Field(..., min_length=2, max_length=80)
    email: Optional[str] = Field(default=None, max_length=120)
    phone: Optional[str] = Field(default=None, max_length=24)
    notification_method: Literal["email", "sms"] = "email"
    party_size: int = Field(default=2, ge=1, le=16)
    reservation_date: str = Field(..., min_length=8, max_length=32)
    reservation_time: str = Field(..., min_length=3, max_length=16)


def _valid_email(value: Optional[str]) -> bool:
    return bool(value and re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value.strip()))


def _valid_phone(value: Optional[str]) -> bool:
    return bool(value and len(re.sub(r"\D", "", value)) >= 7)


def _booking_id() -> str:
    return f"DS-{datetime.now():%y%m%d}-{secrets.token_hex(3).upper()}"


@router.post("", status_code=201)
async def create_reservation(request: ReservationRequest):
    if request.notification_method == "email" and not _valid_email(request.email):
        raise HTTPException(status_code=400, detail="Enter a valid email address for email confirmation.")
    if request.notification_method == "sms" and not _valid_phone(request.phone):
        raise HTTPException(status_code=400, detail="Enter a valid phone number for SMS confirmation.")

    conn = get_db_connection()
    try:
        # BEGIN IMMEDIATE serializes writers so two guests cannot reserve the same table.
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.cursor()
        cur.execute("SELECT * FROM tables WHERE id = ?", (request.table_id,))
        table = cur.fetchone()
        if not table:
            conn.rollback()
            raise HTTPException(status_code=404, detail="Table not found.")
        if table["status"] != "AVAILABLE":
            conn.rollback()
            raise HTTPException(status_code=409, detail="This table is no longer available. Please select another table.")
        if request.party_size > table["capacity"]:
            conn.rollback()
            raise HTTPException(status_code=400, detail=f"This table seats up to {table['capacity']} guests.")

        booking_id = _booking_id()
        now = datetime.now().isoformat()
        cur.execute(
            """INSERT INTO reservations
               (booking_id, table_id, customer_name, email, phone, notification_method,
                party_size, reservation_date, reservation_time, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'CONFIRMED', ?)""",
            (booking_id, request.table_id, request.customer_name.strip(), request.email.strip() if request.email else None,
             request.phone.strip() if request.phone else None, request.notification_method, request.party_size,
             request.reservation_date, request.reservation_time, now),
        )
        cur.execute("UPDATE tables SET status = 'RESERVED' WHERE id = ? AND status = 'AVAILABLE'", (request.table_id,))
        if cur.rowcount != 1:
            conn.rollback()
            raise HTTPException(status_code=409, detail="This table is no longer available. Please select another table.")

        notification_status = "QUEUED"
        destination = request.email.strip() if request.notification_method == "email" else request.phone.strip()
        cur.execute(
            """INSERT INTO notification_log
               (booking_id, method, destination, status, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (booking_id, request.notification_method, destination, notification_status, now),
        )
        conn.commit()
        cur.execute("SELECT * FROM tables WHERE id = ?", (request.table_id,))
        updated_table = dict(cur.fetchone())
    except HTTPException:
        raise
    except Exception:
        conn.rollback()
        raise HTTPException(status_code=500, detail="We could not complete the reservation. Please try again.")
    finally:
        conn.close()

    await ws_manager.broadcast_table_update(updated_table)
    await ws_manager.broadcast_stats_refresh()
    return {
        "message": "Your table has been reserved.",
        "booking_id": booking_id,
        "table": updated_table,
        "reservation": {
            "customer_name": request.customer_name.strip(),
            "party_size": request.party_size,
            "date": request.reservation_date,
            "time": request.reservation_time,
            "notification_method": request.notification_method,
            "notification_status": notification_status,
        },
    }


@router.get("/{booking_id}")
def get_reservation(booking_id: str):
    conn = get_db_connection()
    row = conn.execute(
        """SELECT r.*, t.table_number, t.name AS table_name, t.section
           FROM reservations r JOIN tables t ON t.id = r.table_id
           WHERE r.booking_id = ?""",
        (booking_id,),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Reservation not found.")
    return dict(row)
