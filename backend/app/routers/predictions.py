from fastapi import APIRouter, Query
from typing import Optional, List, Dict, Any
from ..models import WaitTimePredictionRequest, WaitTimePredictionResponse, PeakHourResponse, HourlyOccupancyPrediction
from ..ai_engine import ai_engine

router = APIRouter(prefix="/api/v1/predictions", tags=["AI Predictions"])

@router.post("/wait-time", response_model=WaitTimePredictionResponse)
def predict_wait_time(req: WaitTimePredictionRequest):
    result = ai_engine.predict_wait_time(
        party_size=req.party_size,
        preferred_section=req.preferred_section or "Any",
        target_hour=req.target_hour,
        day_of_week=req.day_of_week
    )
    return WaitTimePredictionResponse(**result)

@router.get("/hourly-forecast", response_model=List[HourlyOccupancyPrediction])
def get_hourly_forecast(day_of_week: Optional[int] = Query(None, ge=0, le=6)):
    forecast = ai_engine.get_hourly_occupancy_forecast(day_of_week)
    return [HourlyOccupancyPrediction(**f) for f in forecast]

@router.get("/peak-hours", response_model=PeakHourResponse)
def get_peak_hours():
    insights = ai_engine.get_peak_hour_insights()
    return PeakHourResponse(
        current_occupancy_rate=insights["current_occupancy_rate"],
        current_status=insights["current_status"],
        next_rush_hour=insights["next_rush_hour"],
        lunch_rush_window=insights["lunch_rush_window"],
        dinner_rush_window=insights["dinner_rush_window"],
        hourly_forecast=[HourlyOccupancyPrediction(**f) for f in insights["hourly_forecast"]],
        heatmap_matrix=insights["heatmap_matrix"]
    )
