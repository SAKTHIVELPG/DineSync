# 🍽️ DINESYNC: Smart Restaurant IoT Table Occupancy, Queue Management & AI Platform

**DINESYNC** is an IoT-powered restaurant floor management, contactless guest waitlist, and AI predictive analytics system. It bridges physical microcontrollers (**ESP32** ultrasonic/IR/pressure proximity sensors) with zero-latency **WebSocket** live dashboards, intelligent waitlist management, machine-learning wait-time regression, and 7-day rush-hour forecasting.

Per project directives, DINESYNC strictly focuses on table sensing, queue automation, and AI analytics without generic billing, POS, or inventory distractions.

---

## 🚀 Key Features

| Feature Area | Description | Priority |
| :--- | :--- | :--- |
| **Real-time Table Status** | Instant bi-directional state synchronization via WebSockets (Available, Occupied, Reserved, Cleaning). | ⭐⭐⭐⭐⭐ |
| **ESP32 Sensor Integration** | REST/JSON telemetry ingestion (`/api/v1/sensors/telemetry`), hardware debounce filter, and built-in Admin Simulator. | ⭐⭐⭐⭐⭐ |
| **Interactive 2D Floor Plan** | Visual spatial seating map with live elapsed dining timers and real-time sensor distance telemetry (cm). | ⭐⭐⭐⭐⭐ |
| **Guest Waitlist & Digital Ticket** | Contactless sign-up with live queue position countdown, AI-calculated ETA, and Web Audio API table-ready alerts. | ⭐⭐⭐⭐⭐ |
| **AI Wait-Time Prediction** | Gradient Boosting / Random Forest regression model calculating wait times by party size, turnover rate, and rush loads. | ⭐⭐⭐⭐⭐ |
| **Peak-Hour Forecaster & Heatmap** | 24-hour occupancy forecast curves and 7-Day $\times$ 24-Hour congestion heatmaps. | ⭐⭐⭐⭐ |
| **Occupancy & Dining Analytics** | Historical turnover rates, dining duration distributions, and actual vs. predicted accuracy charts. | ⭐⭐⭐⭐ |
| **Manager Admin Console** | Host stand queue board (Call/Seat/Cancel), ESP32 hardware fleet monitor, and 1-click sensor simulator. | ⭐⭐⭐⭐ |

---

## 🏗️ Project Architecture

```
dinesync/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI application, WebSocket hub & static mount
│   │   ├── database.py             # SQLite database schemas and initial seed dataset
│   │   ├── models.py               # Pydantic data schemas
│   │   ├── ai_engine.py            # Scikit-Learn Wait-Time Regressor & Forecaster
│   │   ├── websocket_manager.py    # Real-time WebSocket connection manager
│   │   └── routers/
│   │       ├── tables.py           # Table listing, floor details, status overrides
│   │       ├── queue.py            # Waitlist join, live ticket, host seating actions
│   │       ├── sensors.py          # ESP32 telemetry ingestion & hardware simulator
│   │       ├── predictions.py      # AI wait-time estimation & rush window queries
│   │       ├── analytics.py        # Historical turnover, accuracy, and CSV exports
│   │       └── admin.py            # Admin auth, sensor mapping, and demo DB reset
│   ├── firmware/
│   │   └── dinesync_esp32.ino      # Ready-to-flash Arduino C++ firmware for ESP32
│   └── tests/
│       ├── test_api.py             # Integration test suite for all REST endpoints
│       └── test_ai.py              # AI model training and prediction unit tests
├── frontend/
│   ├── index.html                  # Master Single Page Application (SPA)
│   ├── css/
│   │   └── custom.css              # Dark luxury UI, glowing badges, floor plan styling
│   └── js/
│       ├── app.js                  # Main controller, router, audio chime synthesizer
│       ├── websocket.js            # Auto-reconnecting real-time WebSocket client
│       ├── dashboard.js            # KPI metrics, radial occupancy gauge, mini floor
│       ├── tables.js               # Interactive 2D floor plan & sensor telemetry drawer
│       ├── queue.js                # Guest waitlist registration & live ticket tracker
│       ├── ai_predictions.js       # AI simulator, 24h curve, 7x24 rush hour heatmap
│       ├── analytics.js            # Chart.js historical trends & CSV export
│       └── admin.js                # Sensor fleet hub, hardware simulator, host stand
├── run.py                          # Server launcher script
├── requirements.txt                # Python backend dependencies
└── README.md
```

---

## ⚡ Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Test Suite
```bash
python -m pytest backend/tests/ -v
```

### 3. Launch DINESYNC Platform
```bash
python run.py
```

Open your browser to **http://localhost:8000**

---

## 🔌 ESP32 Hardware Integration

### Circuit Connections
- **Sensor**: HC-SR04 Ultrasonic Sensor (or VL53L0X Time-of-Flight Laser / Pressure Mat)
- **VCC** $\rightarrow$ `5V / 3.3V`
- **GND** $\rightarrow$ `GND`
- **TRIG** $\rightarrow$ `GPIO 5`
- **ECHO** $\rightarrow$ `GPIO 18` (via 1k/2k voltage divider for 3.3V tolerance)
- **Status LED** $\rightarrow$ `GPIO 2`

### Telemetry Payload Format (`POST /api/v1/sensors/telemetry`)
```json
{
  "sensor_id": "ESP32-NODE-04",
  "table_id": 4,
  "distance_cm": 24.5,
  "occupied": true,
  "battery_level": 94,
  "signal_rssi": -52,
  "firmware_version": "v2.1.0-esp32"
}
```

---

## 👨‍💼 Manager Portal Demo Access
- Go to the **Admin** tab
- **Demo PIN**: `1234`
- Features unlocked: Live Host Stand Queue Board, ESP32 Fleet Monitor, Interactive Hardware Simulator (1-click sit/vacate triggers), and DB Reset.

## Guest Reservations

The guest-facing floor plan exposes reservation actions for available tables through `POST /api/v1/reservations`.

The endpoint validates party size and email/SMS contact details, atomically locks the selected table, returns a booking ID, and stores a durable `QUEUED` notification record. A production deployment can connect the notification service boundary to SMTP or an SMS provider without changing the reservation transaction.

Local SQLite databases and credentials are intentionally excluded by `.gitignore`. Configure the ESP32 Wi-Fi values locally before flashing firmware.
