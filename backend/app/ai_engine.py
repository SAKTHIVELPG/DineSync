import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
import logging
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional
from .database import get_db_connection, query_db

logger = logging.getLogger("dinesync.ai")

class DineSyncAIEngine:
    def __init__(self):
        self.wait_time_model: Optional[GradientBoostingRegressor] = None
        self.is_trained = False
        self.heatmap_matrix: Optional[List[List[float]]] = None
        self.r2_score: Optional[float] = None
        self.training_samples: int = 0
        self.last_trained: Optional[str] = None

    def train_models(self) -> Dict[str, Any]:
        """Train AI regression models on historical dining and occupancy records"""
        try:
            conn = get_db_connection()
            # Fetch historical dining records
            df_history = pd.read_sql_query("""
                SELECT table_id, party_size, duration_minutes, wait_time_minutes, day_of_week, hour_of_day
                FROM dining_history
            """, conn)
            
            # Fetch snapshots for context
            df_snaps = pd.read_sql_query("""
                SELECT occupancy_rate, queue_length, hour_of_day, day_of_week
                FROM occupancy_snapshots
            """, conn)
            conn.close()

            if len(df_history) < 20:
                logger.warning("Insufficient data for full AI training. Using base parametric model.")
                self.is_trained = False
                return {
                    "success": False,
                    "is_trained": False,
                    "training_samples": len(df_history),
                    "r2_score": None,
                    "last_trained": datetime.now().isoformat(),
                    "message": "Insufficient historical data for training (< 20 records)"
                }

            # Feature Engineering for Wait Time Model
            # Simulated features based on hour & day match
            merged_records = []
            for _, row in df_history.iterrows():
                h = int(row['hour_of_day'])
                d = int(row['day_of_week'])
                snaps_match = df_snaps[(df_snaps['hour_of_day'] == h) & (df_snaps['day_of_week'] == d)]
                occ = snaps_match['occupancy_rate'].mean() if not snaps_match.empty else 0.5
                q_len = snaps_match['queue_length'].mean() if not snaps_match.empty else 2.0

                # Feature vector: [party_size, q_len, occ, hour_of_day, is_weekend]
                is_weekend = 1 if d in [4, 5, 6] else 0
                merged_records.append({
                    'party_size': row['party_size'],
                    'queue_length': q_len,
                    'occupancy_rate': occ,
                    'hour_of_day': h,
                    'is_weekend': is_weekend,
                    'wait_time_minutes': row['wait_time_minutes']
                })

            df_train = pd.DataFrame(merged_records)
            X = df_train[['party_size', 'queue_length', 'occupancy_rate', 'hour_of_day', 'is_weekend']]
            y = df_train['wait_time_minutes']

            self.wait_time_model = GradientBoostingRegressor(
                n_estimators=60,
                learning_rate=0.08,
                max_depth=3,
                random_state=42
            )
            self.wait_time_model.fit(X, y)
            self.r2_score = round(float(self.wait_time_model.score(X, y)), 3)
            self.training_samples = len(merged_records)
            self.is_trained = True
            self.last_trained = datetime.now().isoformat()
            logger.info(f"AI Wait Time Regressor successfully trained! (Samples: {self.training_samples}, R2: {self.r2_score})")

            # Precalculate 7x24 Occupancy Heatmap
            self._compute_heatmap(df_snaps)

            return {
                "success": True,
                "is_trained": True,
                "training_samples": self.training_samples,
                "r2_score": self.r2_score,
                "last_trained": self.last_trained,
                "message": f"Successfully trained AI models on {self.training_samples} records with R2 = {self.r2_score}"
            }

        except Exception as e:
            logger.error(f"Error training AI models: {e}")
            self.is_trained = False
            return {
                "success": False,
                "is_trained": False,
                "training_samples": 0,
                "r2_score": None,
                "last_trained": datetime.now().isoformat(),
                "message": str(e)
            }

    def _compute_heatmap(self, df_snaps: pd.DataFrame):
        """Build 7 days x 24 hours occupancy percentage matrix"""
        matrix = [[0.0 for _ in range(24)] for _ in range(7)]
        for day in range(7):
            for hour in range(24):
                subset = df_snaps[(df_snaps['day_of_week'] == day) & (df_snaps['hour_of_day'] == hour)]
                if not subset.empty:
                    val = float(subset['occupancy_rate'].mean() * 100)
                    matrix[day][hour] = round(val, 1)
                else:
                    # Realistic baseline for non-operational hours
                    if 0 <= hour < 11:
                        matrix[day][hour] = 0.0
                    elif 12 <= hour <= 14:
                        matrix[day][hour] = 65.0 if day < 5 else 82.0
                    elif 18 <= hour <= 21:
                        matrix[day][hour] = 78.0 if day < 4 else 92.0
                    else:
                        matrix[day][hour] = 35.0
        self.heatmap_matrix = matrix

    def predict_wait_time(self, party_size: int, preferred_section: str = "Any", target_hour: Optional[int] = None, day_of_week: Optional[int] = None) -> Dict[str, Any]:
        """Dynamic AI wait time estimation taking current restaurant state or what-if scenario into account"""
        now = datetime.now()
        is_simulation_mode = (target_hour is not None and (target_hour != now.hour or (day_of_week is not None and day_of_week != now.weekday())))
        
        h = target_hour if target_hour is not None else now.hour
        d = day_of_week if day_of_week is not None else now.weekday()
        is_weekend = 1 if d in [4, 5, 6] else 0

        # Query live database state
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Count total and occupied tables
        cur.execute("SELECT COUNT(*) as total, SUM(CASE WHEN status = 'OCCUPIED' THEN 1 ELSE 0 END) as occupied FROM tables")
        t_row = cur.fetchone()
        total_tables = t_row["total"] if t_row["total"] > 0 else 16
        occupied_tables = t_row["occupied"] or 0
        live_occ_rate = round(occupied_tables / total_tables, 3)

        # Count active waiting queue length
        cur.execute("SELECT COUNT(*) as q_count FROM queue WHERE status = 'WAITING'")
        q_row = cur.fetchone()
        live_queue_len = q_row["q_count"] if q_row else 0

        # Check matching available tables
        section_query = "AND section = ?" if preferred_section != "Any" else ""
        args = (party_size, preferred_section) if preferred_section != "Any" else (party_size,)
        cur.execute(f"SELECT COUNT(*) as matching_avail FROM tables WHERE status = 'AVAILABLE' AND capacity >= ? {section_query}", args)
        m_row = cur.fetchone()
        matching_available = m_row["matching_avail"] if m_row else 0
        conn.close()

        # If in simulation mode, calculate expected occupancy & queue depth from historical heatmap
        if is_simulation_mode:
            projected_occ_pct = self.heatmap_matrix[d][h] if (self.heatmap_matrix and len(self.heatmap_matrix) > d) else (85.0 if (18 <= h <= 21) else (65.0 if (12 <= h <= 14) else 35.0))
            current_occ_rate = round(projected_occ_pct / 100.0, 3)
            # Projected queue length proportional to congestion
            if current_occ_rate >= 0.85:
                active_queue_len = 6
                matching_available = 0
            elif current_occ_rate >= 0.65:
                active_queue_len = 3
                matching_available = 1
            else:
                active_queue_len = 0
                matching_available = 3
        else:
            current_occ_rate = live_occ_rate
            active_queue_len = live_queue_len

        # If live (not simulation), matching table is immediately available and no queue ahead: 0 mins wait!
        if not is_simulation_mode and active_queue_len == 0 and matching_available > 0:
            return {
                "predicted_wait_minutes": 0,
                "min_estimated_minutes": 0,
                "max_estimated_minutes": 3,
                "confidence_score": 0.98,
                "factors": {
                    "immediate_table_available": True,
                    "matching_available_tables": matching_available,
                    "active_queue_ahead": 0,
                    "occupancy_rate_pct": round(current_occ_rate * 100, 1),
                    "rush_level": "Immediate Seating"
                },
                "recommendation": "Tables ready now! Walk straight to the host stand."
            }

        # Model Inference
        if self.is_trained and self.wait_time_model is not None:
            features = pd.DataFrame([{
                'party_size': party_size,
                'queue_length': active_queue_len + 1,
                'occupancy_rate': current_occ_rate,
                'hour_of_day': h,
                'is_weekend': is_weekend
            }])
            raw_pred = float(self.wait_time_model.predict(features)[0])
        else:
            # Calibrated analytical fallback
            base_turnover = 45.0 # avg mins per table
            turnover_rate = (total_tables / base_turnover) # tables cleared per min
            raw_pred = ((active_queue_len + 1) / max(0.2, turnover_rate)) * (1 + (party_size * 0.1))

        # Adjust for matching available tables
        if matching_available > 0:
            raw_pred = max(0.0, raw_pred - (matching_available * 4.0))

        predicted = max(2, int(round(raw_pred)))
        min_est = max(0, predicted - int(predicted * 0.25) - 2)
        max_est = predicted + int(predicted * 0.35) + 3

        # Determine rush level
        if current_occ_rate > 0.85:
            rush_level = "High Peak Rush"
            recommendation = "High demand. Joining the digital queue now will save substantial wait time."
        elif current_occ_rate > 0.60:
            rush_level = "Moderate Traffic"
            recommendation = "Normal dinner/lunch flow. Expected turn time is steady."
        else:
            rush_level = "Light Activity"
            recommendation = "Low wait times. Great time to dine."

        return {
            "predicted_wait_minutes": predicted,
            "min_estimated_minutes": min_est,
            "max_estimated_minutes": max_est,
            "confidence_score": 0.92,
            "factors": {
                "active_queue_ahead": active_queue_len,
                "current_occupancy_pct": round(current_occ_rate * 100, 1),
                "matching_available_tables": matching_available,
                "party_size_impact_mins": round(party_size * 1.8, 1),
                "rush_level": rush_level
            },
            "recommendation": recommendation
        }

    def get_hourly_occupancy_forecast(self, day_of_week: Optional[int] = None) -> List[Dict[str, Any]]:
        """Generate 24-hour occupancy forecast for a given day"""
        now = datetime.now()
        d = day_of_week if day_of_week is not None else now.weekday()
        
        forecast = []
        for hour in range(24):
            # Calculate predicted occupancy
            is_lunch = (12 <= hour <= 14)
            is_dinner = (18 <= hour <= 21)
            is_weekend = d in [4, 5, 6]

            if self.heatmap_matrix and len(self.heatmap_matrix) > d:
                occ_pct = self.heatmap_matrix[d][hour]
            else:
                if 0 <= hour < 11:
                    occ_pct = 0.0
                elif is_dinner:
                    occ_pct = 88.0 if is_weekend else 74.0
                elif is_lunch:
                    occ_pct = 75.0 if is_weekend else 62.0
                elif 15 <= hour <= 17:
                    occ_pct = 32.0
                elif 11 <= hour <= 23:
                    occ_pct = 48.0
                else:
                    occ_pct = 0.0

            is_rush = is_lunch or is_dinner
            if occ_pct >= 80.0:
                status = "Peak Rush"
            elif occ_pct >= 50.0:
                status = "Moderate"
            else:
                status = "Light"

            hour_label = datetime.strptime(f"{hour}:00", "%H:%M").strftime("%I:%M %p")
            avail_est = max(0, int(16 * (1.0 - (occ_pct / 100.0))))

            forecast.append({
                "hour": hour,
                "hour_label": hour_label,
                "predicted_occupancy_percent": occ_pct,
                "is_rush_hour": is_rush,
                "status": status,
                "available_tables_est": avail_est
            })
        return forecast

    def get_peak_hour_insights(self) -> Dict[str, Any]:
        """Aggregate insights on rush windows and 7x24 heatmap"""
        now = datetime.now()
        current_hour = now.hour

        # Query live table occupancy
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as total, SUM(CASE WHEN status = 'OCCUPIED' THEN 1 ELSE 0 END) as occupied FROM tables")
        row = cur.fetchone()
        conn.close()

        total = row["total"] if row and row["total"] > 0 else 16
        occupied = row["occupied"] if row and row["occupied"] else 0
        curr_rate = round((occupied / total) * 100, 1)

        if curr_rate >= 80:
            curr_status = "Peak Rush"
        elif curr_rate >= 50:
            curr_status = "Moderate Traffic"
        else:
            curr_status = "Light / Low Traffic"

        # Determine next rush
        if current_hour < 12:
            next_rush = "Lunch Rush starting at 12:00 PM"
        elif 14 < current_hour < 18:
            next_rush = "Dinner Rush starting at 6:30 PM"
        elif current_hour >= 21:
            next_rush = "Tomorrow Lunch Rush at 12:00 PM"
        else:
            next_rush = "Currently inside Active Rush Window"

        forecast = self.get_hourly_occupancy_forecast()
        heatmap = self.heatmap_matrix if self.heatmap_matrix else [[0.0]*24 for _ in range(7)]

        return {
            "current_occupancy_rate": curr_rate,
            "current_status": curr_status,
            "next_rush_hour": next_rush,
            "lunch_rush_window": "12:00 PM - 2:30 PM",
            "dinner_rush_window": "6:30 PM - 9:00 PM",
            "hourly_forecast": forecast,
            "heatmap_matrix": heatmap
        }

ai_engine = DineSyncAIEngine()
