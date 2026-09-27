import sqlite3
import random
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

DB_PATH = os.getenv("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "dinesync.db"))
# Ensure the directory for the database exists
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
DB_FILE = DB_PATH

def get_db_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Tables table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tables (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        table_number INTEGER UNIQUE NOT NULL,
        name TEXT NOT NULL,
        capacity INTEGER NOT NULL,
        section TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'AVAILABLE',
        sensor_id TEXT UNIQUE,
        pos_x INTEGER DEFAULT 0,
        pos_y INTEGER DEFAULT 0,
        shape TEXT DEFAULT 'rect',
        occupied_since TEXT,
        elapsed_minutes INTEGER DEFAULT 0,
        sensor_battery INTEGER DEFAULT 100,
        sensor_rssi INTEGER DEFAULT -55,
        sensor_distance_cm REAL DEFAULT 120.0,
        last_sensor_ping TEXT
    )
    """)

    # Queue table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_code TEXT UNIQUE NOT NULL,
        customer_name TEXT NOT NULL,
        phone TEXT NOT NULL,
        email TEXT,
        party_size INTEGER NOT NULL,
        preferred_section TEXT DEFAULT 'Any',
        special_notes TEXT,
        status TEXT NOT NULL DEFAULT 'WAITING',
        estimated_wait_minutes INTEGER DEFAULT 15,
        created_at TEXT NOT NULL,
        called_at TEXT,
        seated_at TEXT,
        assigned_table_id INTEGER,
        FOREIGN KEY (assigned_table_id) REFERENCES tables (id)
    )
    """)

    # Sensor nodes table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sensor_nodes (
        sensor_id TEXT PRIMARY KEY,
        table_id INTEGER,
        battery_level INTEGER DEFAULT 100,
        signal_rssi INTEGER DEFAULT -55,
        distance_cm REAL DEFAULT 120.0,
        state TEXT DEFAULT 'VACANT',
        last_ping TEXT,
        firmware_version TEXT DEFAULT 'v2.1.0-esp32',
        FOREIGN KEY (table_id) REFERENCES tables (id)
    )
    """)

    # Dining history table (for AI model training & analytics)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS dining_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        table_id INTEGER NOT NULL,
        party_size INTEGER NOT NULL,
        section TEXT NOT NULL,
        seated_at TEXT NOT NULL,
        cleared_at TEXT NOT NULL,
        duration_minutes REAL NOT NULL,
        wait_time_minutes REAL NOT NULL,
        predicted_wait_minutes REAL NOT NULL,
        day_of_week INTEGER NOT NULL,
        hour_of_day INTEGER NOT NULL
    )
    """)

    # Hourly Occupancy Snapshots
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS occupancy_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        total_tables INTEGER NOT NULL,
        occupied_tables INTEGER NOT NULL,
        occupancy_rate REAL NOT NULL,
        queue_length INTEGER NOT NULL,
        hour_of_day INTEGER NOT NULL,
        day_of_week INTEGER NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reservations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        booking_id TEXT UNIQUE NOT NULL,
        table_id INTEGER NOT NULL,
        customer_name TEXT NOT NULL,
        email TEXT,
        phone TEXT,
        notification_method TEXT NOT NULL,
        party_size INTEGER NOT NULL,
        reservation_date TEXT NOT NULL,
        reservation_time TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'CONFIRMED',
        created_at TEXT NOT NULL,
        FOREIGN KEY (table_id) REFERENCES tables (id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notification_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        booking_id TEXT NOT NULL,
        method TEXT NOT NULL,
        destination TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (booking_id) REFERENCES reservations (booking_id)
    )
    """)

    conn.commit()

    # Seed default data if tables is empty
    cursor.execute("SELECT COUNT(*) as count FROM tables")
    row = cursor.fetchone()
    if row["count"] == 0:
        seed_tables_and_sensors(cursor)
        seed_queue(cursor)
        seed_historical_data(cursor)
        conn.commit()

    conn.close()

def seed_tables_and_sensors(cursor):
    initial_tables = [
        # Window View (Left column)
        (1, "Table 1", 2, "Window View", "AVAILABLE", "ESP32-NODE-01", 50, 60, "circle"),
        (2, "Table 2", 2, "Window View", "OCCUPIED", "ESP32-NODE-02", 50, 190, "circle"),
        (3, "Table 3", 4, "Window View", "AVAILABLE", "ESP32-NODE-03", 50, 320, "rect"),

        # Main Dining (Center grid)
        (4, "Table 4", 4, "Main Dining", "OCCUPIED", "ESP32-NODE-04", 230, 60, "rect"),
        (5, "Table 5", 4, "Main Dining", "AVAILABLE", "ESP32-NODE-05", 230, 190, "rect"),
        (6, "Table 6", 6, "Main Dining", "OCCUPIED", "ESP32-NODE-06", 230, 320, "rect"),
        (7, "Table 7", 6, "Main Dining", "AVAILABLE", "ESP32-NODE-07", 400, 60, "rect"),
        (8, "Table 8", 8, "Main Dining", "RESERVED", "ESP32-NODE-08", 400, 200, "rect"),

        # Patio (Top Right outdoor)
        (9, "Table 9", 4, "Patio", "AVAILABLE", "ESP32-NODE-09", 580, 50, "circle"),
        (10, "Table 10", 4, "Patio", "OCCUPIED", "ESP32-NODE-10", 580, 160, "circle"),
        (11, "Table 11", 2, "Patio", "AVAILABLE", "ESP32-NODE-11", 720, 50, "circle"),
        (12, "Table 12", 6, "Patio", "AVAILABLE", "ESP32-NODE-12", 720, 160, "rect"),

        # Bar Lounge (Bottom Center)
        (13, "Table 13", 2, "Bar Lounge", "OCCUPIED", "ESP32-NODE-13", 230, 460, "circle"),
        (14, "Table 14", 2, "Bar Lounge", "AVAILABLE", "ESP32-NODE-14", 370, 460, "circle"),

        # VIP Booths (Bottom Right)
        (15, "Table 15", 6, "VIP Booth", "OCCUPIED", "ESP32-NODE-15", 580, 340, "booth"),
        (16, "Table 16", 8, "VIP Booth", "AVAILABLE", "ESP32-NODE-16", 580, 470, "booth"),
    ]

    now = datetime.now()
    for t in initial_tables:
        t_id, name, cap, sec, status, s_id, px, py, shape = t
        occ_since = None
        elapsed = 0
        dist = 125.0
        s_state = "VACANT"
        battery = random.randint(82, 99)
        rssi = random.randint(-65, -42)

        if status == "OCCUPIED":
            elapsed = random.randint(15, 65)
            occ_since = (now - timedelta(minutes=elapsed)).isoformat()
            dist = random.uniform(15.0, 38.0)
            s_state = "OCCUPIED"

        cursor.execute("""
        INSERT INTO tables (
            table_number, name, capacity, section, status, sensor_id, pos_x, pos_y, shape,
            occupied_since, elapsed_minutes, sensor_battery, sensor_rssi, sensor_distance_cm, last_sensor_ping
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (t_id, name, cap, sec, status, s_id, px, py, shape, occ_since, elapsed, battery, rssi, dist, now.isoformat()))

        db_table_id = cursor.lastrowid

        cursor.execute("""
        INSERT INTO sensor_nodes (
            sensor_id, table_id, battery_level, signal_rssi, distance_cm, state, last_ping, firmware_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (s_id, db_table_id, battery, rssi, dist, s_state, now.isoformat(), "v2.1.0-esp32"))

def seed_queue(cursor):
    now = datetime.now()
    sample_queue = [
        ("Q-101", "Marcus Vance", "+1 555-0143", "marcus.v@example.com", 2, "Window View", "Anniversary celebration", "WAITING", 8, (now - timedelta(minutes=14)).isoformat()),
        ("Q-102", "Sarah Jenkins", "+1 555-0188", "sarah.j@example.com", 4, "Any", "High chair needed", "WAITING", 16, (now - timedelta(minutes=9)).isoformat()),
        ("Q-103", "Elena Rostova", "+1 555-0210", "elena.r@example.com", 6, "Patio", "Quiet corner preferred", "WAITING", 28, (now - timedelta(minutes=3)).isoformat()),
        ("Q-104", "David Kim", "+1 555-0322", "dkim@example.com", 2, "Bar Lounge", "", "CALLED", 0, (now - timedelta(minutes=22)).isoformat(), (now - timedelta(minutes=2)).isoformat()),
    ]

    for q in sample_queue:
        if len(q) == 10:
            cursor.execute("""
            INSERT INTO queue (ticket_code, customer_name, phone, email, party_size, preferred_section, special_notes, status, estimated_wait_minutes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, q)
        else:
            cursor.execute("""
            INSERT INTO queue (ticket_code, customer_name, phone, email, party_size, preferred_section, special_notes, status, estimated_wait_minutes, created_at, called_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, q)

def seed_historical_data(cursor):
    """Generate 30 days of realistic dining history and occupancy records for AI training"""
    now = datetime.now()
    sections = ["Main Dining", "Patio", "Window View", "Bar Lounge", "VIP Booth"]
    
    # 30 days back
    for day_offset in range(30, 0, -1):
        day_date = now - timedelta(days=day_offset)
        day_of_week = day_date.weekday() # 0 = Monday, 6 = Sunday
        is_weekend = day_of_week in [4, 5, 6] # Fri, Sat, Sun

        # Hourly simulation for each day from 11:00 AM to 11:00 PM (11 to 23)
        for hour in range(11, 24):
            # Rush hour curve: Lunch (12-14), Dinner (18-21)
            is_lunch_rush = (12 <= hour <= 14)
            is_dinner_rush = (18 <= hour <= 21)

            if is_dinner_rush:
                base_occupancy = random.uniform(0.75, 0.95) if is_weekend else random.uniform(0.65, 0.88)
                queue_len = random.randint(3, 10)
            elif is_lunch_rush:
                base_occupancy = random.uniform(0.60, 0.85) if is_weekend else random.uniform(0.50, 0.75)
                queue_len = random.randint(1, 6)
            elif 15 <= hour <= 17:
                base_occupancy = random.uniform(0.20, 0.45)
                queue_len = random.randint(0, 2)
            else:
                base_occupancy = random.uniform(0.30, 0.55)
                queue_len = random.randint(0, 3)

            occupied_count = int(16 * base_occupancy)
            occ_rate = round(occupied_count / 16.0, 3)

            snap_time = day_date.replace(hour=hour, minute=random.randint(0, 59), second=0).isoformat()
            cursor.execute("""
            INSERT INTO occupancy_snapshots (
                timestamp, total_tables, occupied_tables, occupancy_rate, queue_length, hour_of_day, day_of_week
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (snap_time, 16, occupied_count, occ_rate, queue_len, hour, day_of_week))

            # Generate individual dining sessions completed in this hour
            num_sessions = random.randint(2, 5)
            for _ in range(num_sessions):
                table_id = random.randint(1, 16)
                party_size = random.choice([2, 2, 2, 4, 4, 4, 6, 6, 8])
                section = random.choice(sections)

                # Base duration: 2-top ~ 40m, 4-top ~ 60m, 6-top ~ 80m, 8-top ~ 100m
                base_dur = 25 + (party_size * 9.5) + random.uniform(-10, 15)
                duration_mins = max(20.0, round(base_dur, 1))

                # Wait time: party size + queue depth * 3.5 + noise
                wait_mins = max(0.0, round(queue_len * 3.8 + (party_size * 1.5) + random.uniform(-3, 4), 1))
                pred_wait = max(0.0, round(wait_mins + random.uniform(-2, 2), 1))

                seated_time = (day_date.replace(hour=hour, minute=random.randint(0, 30)) - timedelta(minutes=int(duration_mins))).isoformat()
                cleared_time = day_date.replace(hour=hour, minute=random.randint(0, 59)).isoformat()

                cursor.execute("""
                INSERT INTO dining_history (
                    table_id, party_size, section, seated_at, cleared_at, duration_minutes,
                    wait_time_minutes, predicted_wait_minutes, day_of_week, hour_of_day
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (table_id, party_size, section, seated_time, cleared_time, duration_mins, wait_mins, pred_wait, day_of_week, hour))

# Helper query execution functions
def query_db(query: str, args: tuple = (), one: bool = False):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(query, args)
    r = cur.fetchall()
    conn.close()
    return (r[0] if r else None) if one else r

def execute_db(query: str, args: tuple = ()):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(query, args)
    conn.commit()
    last_id = cur.lastrowid
    conn.close()
    return last_id
