from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime

class TableStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    OCCUPIED = "OCCUPIED"
    RESERVED = "RESERVED"
    CLEANING = "CLEANING"

class TableSection(str, Enum):
    MAIN_DINING = "Main Dining"
    PATIO = "Patio"
    WINDOW_VIEW = "Window View"
    BAR_LOUNGE = "Bar Lounge"
    VIP_BOOTH = "VIP Booth"

class QueueStatus(str, Enum):
    WAITING = "WAITING"
    CALLED = "CALLED"
    SEATED = "SEATED"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"

class SensorState(str, Enum):
    VACANT = "VACANT"
    OCCUPIED = "OCCUPIED"
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    WARNING = "WARNING"

# --- Table Models ---
class TableBase(BaseModel):
    table_number: int
    name: str
    capacity: int
    section: TableSection
    status: TableStatus = TableStatus.AVAILABLE
    sensor_id: Optional[str] = None
    pos_x: Optional[int] = 0
    pos_y: Optional[int] = 0
    shape: Optional[str] = "rect" # rect, circle, booth

class TableCreate(TableBase):
    pass

class TableUpdate(BaseModel):
    name: Optional[str] = None
    capacity: Optional[int] = None
    section: Optional[TableSection] = None
    status: Optional[TableStatus] = None
    sensor_id: Optional[str] = None
    pos_x: Optional[int] = None
    pos_y: Optional[int] = None
    shape: Optional[str] = None

class Table(TableBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    occupied_since: Optional[datetime] = None
    elapsed_minutes: Optional[int] = 0
    sensor_battery: Optional[int] = 100
    sensor_rssi: Optional[int] = -55
    sensor_distance_cm: Optional[float] = 120.0
    last_sensor_ping: Optional[datetime] = None

# --- Queue Models ---
class QueueJoinRequest(BaseModel):
    customer_name: str = Field(..., min_length=2, max_length=50)
    phone: str = Field(..., min_length=7, max_length=20)
    email: Optional[str] = None
    party_size: int = Field(..., ge=1, le=16)
    preferred_section: Optional[str] = "Any"
    special_notes: Optional[str] = ""

class QueueEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_code: str
    customer_name: str
    phone: str
    email: Optional[str] = None
    party_size: int
    preferred_section: str
    special_notes: Optional[str] = ""
    status: QueueStatus
    position: int = 0
    estimated_wait_minutes: int
    created_at: datetime
    called_at: Optional[datetime] = None
    seated_at: Optional[datetime] = None
    assigned_table_id: Optional[int] = None
    assigned_table_number: Optional[int] = None

class QueueActionRequest(BaseModel):
    action: str # "call", "seat", "cancel", "no_show"
    table_id: Optional[int] = None

# --- Reservation Models ---
class ReservationRequest(BaseModel):
    table_id: int
    customer_name: str = Field(..., min_length=2, max_length=80)
    email: Optional[str] = None
    phone: Optional[str] = None
    notification_method: str = "email"
    party_size: int = Field(default=2, ge=1, le=16)
    reservation_date: str
    reservation_time: str

# --- Sensor Models ---
class SensorTelemetryPayload(BaseModel):
    sensor_id: str
    table_id: Optional[int] = None
    distance_cm: float = Field(..., description="Ultrasonic / ToF distance reading in cm")
    occupied: bool = Field(..., description="True if seat/table is occupied")
    battery_level: Optional[int] = Field(100, ge=0, le=100)
    signal_rssi: Optional[int] = Field(-60, description="WiFi signal strength in dBm")
    firmware_version: Optional[str] = "v2.1.0-esp32"
    raw_reading: Optional[float] = None

class SensorInfo(BaseModel):
    sensor_id: str
    table_id: Optional[int] = None
    table_name: Optional[str] = None
    state: SensorState
    battery_level: int
    signal_rssi: int
    distance_cm: float
    last_ping: datetime
    firmware_version: str
    is_online: bool

# --- AI Prediction Models ---
class WaitTimePredictionRequest(BaseModel):
    party_size: int = Field(..., ge=1, le=16)
    preferred_section: Optional[str] = "Any"
    target_hour: Optional[int] = Field(None, ge=0, le=23, description="Hour of day (0-23), default is current hour")
    day_of_week: Optional[int] = Field(None, ge=0, le=6, description="0=Mon, 6=Sun, default is current day")

class WaitTimePredictionResponse(BaseModel):
    predicted_wait_minutes: int
    min_estimated_minutes: int
    max_estimated_minutes: int
    confidence_score: float
    factors: Dict[str, Any]
    recommendation: str

class HourlyOccupancyPrediction(BaseModel):
    hour: int
    hour_label: str
    predicted_occupancy_percent: float
    is_rush_hour: bool
    status: str # "Light", "Moderate", "Peak Rush"
    available_tables_est: int

class PeakHourResponse(BaseModel):
    current_occupancy_rate: float
    current_status: str
    next_rush_hour: Optional[str]
    lunch_rush_window: str = "12:00 PM - 2:30 PM"
    dinner_rush_window: str = "6:30 PM - 9:00 PM"
    hourly_forecast: List[HourlyOccupancyPrediction]
    heatmap_matrix: List[List[float]] # 7 days x 24 hours

# --- Analytics Models ---
class AnalyticsSummary(BaseModel):
    total_seated_today: int
    avg_dining_duration_mins: float
    avg_queue_wait_mins: float
    peak_occupancy_today: float
    current_occupancy_rate: float
    turnover_rate_per_hour: float
    party_size_breakdown: Dict[str, int]
    hourly_occupancy_history: List[Dict[str, Any]]
    wait_time_vs_predicted: List[Dict[str, Any]]
    section_popularity: Dict[str, float]

# --- Admin Models ---
class AdminLoginRequest(BaseModel):
    pin: str = "1234" # Default demo admin PIN

class AdminLoginResponse(BaseModel):
    authenticated: bool
    token: str
    message: str
    role: Optional[str] = "admin"
    name: Optional[str] = "Restaurant Manager"

class AITrainResponse(BaseModel):
    success: bool
    is_trained: bool
    training_samples: int
    r2_score: Optional[float] = None
    last_trained: str
    message: str
