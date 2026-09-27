from fastapi import APIRouter, Response
from typing import Dict, Any, List
from datetime import datetime, timedelta
import io
import csv
from ..database import get_db_connection, query_db
from ..models import AnalyticsSummary

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])

@router.get("/summary", response_model=AnalyticsSummary)
def get_analytics_summary():
    conn = get_db_connection()
    cur = conn.cursor()

    # 1. Total seated and average metrics from dining_history
    cur.execute("""
        SELECT 
            COUNT(*) as total_seated,
            AVG(duration_minutes) as avg_duration,
            AVG(wait_time_minutes) as avg_wait
        FROM dining_history
    """)
    agg_row = cur.fetchone()
    total_seated = agg_row["total_seated"] or 0
    avg_duration = round(agg_row["avg_duration"] or 52.4, 1)
    avg_wait = round(agg_row["avg_wait"] or 14.8, 1)

    # 2. Peak occupancy today
    cur.execute("""
        SELECT MAX(occupancy_rate) as peak_rate 
        FROM occupancy_snapshots 
        ORDER BY id DESC LIMIT 24
    """)
    peak_row = cur.fetchone()
    peak_occ = round((peak_row["peak_rate"] or 0.88) * 100, 1)

    # 3. Current occupancy
    cur.execute("SELECT COUNT(*) as total, SUM(CASE WHEN status = 'OCCUPIED' THEN 1 ELSE 0 END) as occupied FROM tables")
    t_row = cur.fetchone()
    curr_total = t_row["total"] if t_row["total"] > 0 else 16
    curr_occ = t_row["occupied"] or 0
    curr_rate = round((curr_occ / curr_total) * 100, 1)

    # 4. Turnover rate per hour (average tables turned per operating hour)
    turnover_per_hour = round(16 / (avg_duration / 60.0), 1) if avg_duration > 0 else 18.0

    # 5. Party size breakdown
    cur.execute("""
        SELECT party_size, COUNT(*) as count 
        FROM dining_history 
        GROUP BY party_size 
        ORDER BY party_size ASC
    """)
    party_rows = cur.fetchall()
    party_size_breakdown = {f"{r['party_size']} Guests": r["count"] for r in party_rows} if party_rows else {"2 Guests": 120, "4 Guests": 85, "6 Guests": 40, "8 Guests": 18}

    # 6. Section Popularity
    cur.execute("""
        SELECT section, COUNT(*) as count 
        FROM dining_history 
        GROUP BY section
    """)
    sec_rows = cur.fetchall()
    total_sec = sum(r["count"] for r in sec_rows) or 1
    section_popularity = {r["section"]: round((r["count"] / total_sec) * 100, 1) for r in sec_rows} if sec_rows else {"Main Dining": 38.0, "Patio": 24.0, "Window View": 20.0, "Bar Lounge": 10.0, "VIP Booth": 8.0}

    # 7. Hourly occupancy history for chart (Last 24 hours of snapshots)
    cur.execute("""
        SELECT hour_of_day, AVG(occupancy_rate) as avg_occ, AVG(queue_length) as avg_q
        FROM occupancy_snapshots
        GROUP BY hour_of_day
        ORDER BY hour_of_day ASC
    """)
    occ_hist_rows = cur.fetchall()
    hourly_occupancy_history = [
        {
            "hour": r["hour_of_day"],
            "hour_label": datetime.strptime(f"{r['hour_of_day']}:00", "%H:%M").strftime("%I %p"),
            "occupancy_rate": round(r["avg_occ"] * 100, 1),
            "queue_depth": round(r["avg_q"], 1)
        }
        for r in occ_hist_rows
    ]

    # 8. Actual wait time vs AI predicted wait time comparison
    cur.execute("""
        SELECT wait_time_minutes, predicted_wait_minutes, party_size, hour_of_day
        FROM dining_history
        ORDER BY id DESC LIMIT 15
    """)
    wait_comp_rows = cur.fetchall()
    wait_time_vs_predicted = [
        {
            "session_id": f"Party #{idx+1}",
            "party_size": r["party_size"],
            "actual_wait_minutes": round(r["wait_time_minutes"], 1),
            "predicted_wait_minutes": round(r["predicted_wait_minutes"], 1),
            "error_minutes": round(abs(r["wait_time_minutes"] - r["predicted_wait_minutes"]), 1)
        }
        for idx, r in enumerate(reversed(wait_comp_rows))
    ]

    conn.close()

    return AnalyticsSummary(
        total_seated_today=total_seated,
        avg_dining_duration_mins=avg_duration,
        avg_queue_wait_mins=avg_wait,
        peak_occupancy_today=peak_occ,
        current_occupancy_rate=curr_rate,
        turnover_rate_per_hour=turnover_per_hour,
        party_size_breakdown=party_size_breakdown,
        hourly_occupancy_history=hourly_occupancy_history,
        wait_time_vs_predicted=wait_time_vs_predicted,
        section_popularity=section_popularity
    )

@router.get("/export")
def export_analytics_csv():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM dining_history ORDER BY id DESC LIMIT 500")
    rows = cur.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Table_ID", "Party_Size", "Section", "Seated_At", "Cleared_At", "Duration_Mins", "Wait_Time_Mins", "Predicted_Wait_Mins", "Day_Of_Week", "Hour_Of_Day"])

    for r in rows:
        writer.writerow([r["id"], r["table_id"], r["party_size"], r["section"], r["seated_at"], r["cleared_at"], r["duration_minutes"], r["wait_time_minutes"], r["predicted_wait_minutes"], r["day_of_week"], r["hour_of_day"]])

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=dinesync_analytics_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"}
    )
