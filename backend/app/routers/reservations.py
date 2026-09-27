import re
import secrets
from datetime import datetime, timedelta
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
    duration_hours: int = Field(default=2, ge=1, le=4)


def _valid_email(value: Optional[str]) -> bool:
    return bool(value and re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value.strip()))


def _valid_phone(value: Optional[str]) -> bool:
    return bool(value and len(re.sub(r"\D", "", value)) >= 7)


def _booking_id() -> str:
    return f"DS-{datetime.now():%y%m%d}-{secrets.token_hex(3).upper()}"


def _parse_start(date_value: str, time_value: str) -> datetime:
    try:
        return datetime.fromisoformat(f"{date_value}T{time_value}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Choose a valid reservation date and time.") from exc


def _display_time(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        formatted = datetime.fromisoformat(value).strftime("%b %d at %I:%M %p")
        return formatted.replace(" 0", " ")
    except ValueError:
        return value


def _current_table_hold(table, now: datetime):
    """Return the estimated current hold end for seeded/live table states."""
    status = table["status"]
    if status == "OCCUPIED":
        occupied_since = table["occupied_since"]
        if occupied_since:
            try:
                return datetime.fromisoformat(occupied_since) + timedelta(minutes=90)
            except ValueError:
                pass
        return now + timedelta(minutes=90)
    if status == "RESERVED":
        return now + timedelta(hours=2)
    if status == "CLEANING":
        return now + timedelta(minutes=30)
    return None


def _availability(conn, table_id: int, start_at: datetime, duration_hours: int):
    table = conn.execute("SELECT * FROM tables WHERE id = ?", (table_id,)).fetchone()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found.")

    end_at = start_at + timedelta(hours=duration_hours)
    now = datetime.now()
    conflicts = []
    for row in conn.execute(
        """SELECT booking_id, customer_name, party_size, start_at, end_at
           FROM reservations
           WHERE table_id = ? AND status = 'CONFIRMED'
             AND start_at < ? AND end_at > ?
           ORDER BY start_at""",
        (table_id, end_at.isoformat(), start_at.isoformat()),
    ).fetchall():
        conflicts.append(dict(row))

    current_hold_end = None
    if start_at.date() == now.date():
        current_hold_end = _current_table_hold(table, now)
        if current_hold_end and start_at < current_hold_end:
            conflicts.append({
                "booking_id": None,
                "customer_name": "Current table service",
                "party_size": None,
                "start_at": now.isoformat(),
                "end_at": current_hold_end.isoformat(),
            })

    next_available = max((datetime.fromisoformat(c["end_at"]) for c in conflicts if c.get("end_at")), default=None)
    booking_summary = conn.execute(
        """SELECT COUNT(*) AS booking_count, COALESCE(SUM(party_size), 0) AS booked_guests
           FROM reservations
           WHERE table_id = ? AND reservation_date = ? AND status = 'CONFIRMED'""",
        (table_id, start_at.date().isoformat()),
    ).fetchone()

    return {
        "table_id": table_id,
        "available": not conflicts,
        "booking_count": booking_summary["booking_count"],
        "booked_guests": booking_summary["booked_guests"],
        "requested_start_at": start_at.isoformat(),
        "requested_end_at": end_at.isoformat(),
        "requested_end_display": _display_time(end_at.isoformat()),
        "next_available_at": next_available.isoformat() if next_available else None,
        "next_available_display": _display_time(next_available.isoformat()) if next_available else "Available for this time",
        "conflicts": conflicts,
    }


@router.get("/availability/check")
def check_availability(table_id: int, reservation_date: str, reservation_time: str, duration_hours: int = 2):
    if duration_hours < 1 or duration_hours > 4:
        raise HTTPException(status_code=400, detail="Reservation duration must be between 1 and 4 hours.")
    start_at = _parse_start(reservation_date, reservation_time)
    conn = get_db_connection()
    try:
        return _availability(conn, table_id, start_at, duration_hours)
    finally:
        conn.close()


@router.post("", status_code=201)
async def create_reservation(request: ReservationRequest):
    if request.notification_method == "email" and not _valid_email(request.email):
        raise HTTPException(status_code=400, detail="Enter a valid email address for email confirmation.")
    if request.notification_method == "sms" and not _valid_phone(request.phone):
        raise HTTPException(status_code=400, detail="Enter a valid phone number for SMS confirmation.")

    start_at = _parse_start(request.reservation_date, request.reservation_time)
    if start_at < datetime.now() - timedelta(minutes=5):
        raise HTTPException(status_code=400, detail="Choose a reservation time that has not already passed.")

    conn = get_db_connection()
    try:
        # BEGIN IMMEDIATE serializes writers so two guests cannot claim the same slot.
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.cursor()
        table = cur.execute("SELECT * FROM tables WHERE id = ?", (request.table_id,)).fetchone()
        if not table:
            conn.rollback()
            raise HTTPException(status_code=404, detail="Table not found.")
        if request.party_size > table["capacity"]:
            conn.rollback()
            raise HTTPException(status_code=400, detail=f"This table seats up to {table['capacity']} guests.")

        availability = _availability(conn, request.table_id, start_at, request.duration_hours)
        if not availability["available"]:
            conn.rollback()
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "This table is busy for the selected time.",
                    "next_available_at": availability["next_available_at"],
                    "next_available_display": availability["next_available_display"],
                    "booking_count": availability["booking_count"],
                    "booked_guests": availability["booked_guests"],
                },
            )

        end_at = start_at + timedelta(hours=request.duration_hours)
        booking_id = _booking_id()
        now = datetime.now().isoformat()
        cur.execute(
            """INSERT INTO reservations
               (booking_id, table_id, customer_name, email, phone, notification_method,
                party_size, reservation_date, reservation_time, duration_hours,
                start_at, end_at, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'CONFIRMED', ?)""",
            (booking_id, request.table_id, request.customer_name.strip(), request.email.strip() if request.email else None,
             request.phone.strip() if request.phone else None, request.notification_method, request.party_size,
             request.reservation_date, request.reservation_time, request.duration_hours,
             start_at.isoformat(), end_at.isoformat(), now),
        )
        # Only reflect a reservation in the live floor status when its slot is active now.
        if start_at <= datetime.now() <= end_at:
            cur.execute("UPDATE tables SET status = 'RESERVED' WHERE id = ? AND status = 'AVAILABLE'", (request.table_id,))

        notification_status = "QUEUED"
        destination = request.email.strip() if request.notification_method == "email" else request.phone.strip()
        cur.execute(
            """INSERT INTO notification_log
               (booking_id, method, destination, status, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (booking_id, request.notification_method, destination, notification_status, now),
        )
        conn.commit()
        updated_table = dict(cur.execute("SELECT * FROM tables WHERE id = ?", (request.table_id,)).fetchone())
        availability = _availability(conn, request.table_id, start_at, request.duration_hours)
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
        "availability": availability,
        "reservation": {
            "customer_name": request.customer_name.strip(),
            "party_size": request.party_size,
            "date": request.reservation_date,
            "time": request.reservation_time,
            "duration_hours": request.duration_hours,
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
            "end_display": _display_time(end_at.isoformat()),
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
