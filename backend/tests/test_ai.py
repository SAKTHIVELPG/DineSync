import pytest
from backend.app.ai_engine import DineSyncAIEngine
from backend.app.database import init_db

def test_ai_engine_initialization_and_training():
    init_db()
    engine = DineSyncAIEngine()
    engine.train_models()
    assert engine.is_trained is True
    assert engine.heatmap_matrix is not None
    assert len(engine.heatmap_matrix) == 7
    assert len(engine.heatmap_matrix[0]) == 24

def test_ai_wait_time_prediction():
    engine = DineSyncAIEngine()
    engine.train_models()

    # Predict for party of 2
    res_2 = engine.predict_wait_time(party_size=2, preferred_section="Any", target_hour=19, day_of_week=5)
    assert res_2["predicted_wait_minutes"] >= 0
    assert res_2["confidence_score"] > 0.5
    assert "factors" in res_2

    # Predict for party of 8 (large party should have equal or higher wait time)
    res_8 = engine.predict_wait_time(party_size=8, preferred_section="VIP Booth", target_hour=20, day_of_week=5)
    assert res_8["predicted_wait_minutes"] >= 0

def test_hourly_occupancy_forecast():
    engine = DineSyncAIEngine()
    engine.train_models()

    forecast = engine.get_hourly_occupancy_forecast(day_of_week=5) # Saturday
    assert len(forecast) == 24
    
    # Lunch and dinner peak check
    lunch_hour = forecast[13] # 1 PM
    dinner_hour = forecast[19] # 7 PM
    late_night = forecast[3] # 3 AM

    assert lunch_hour["predicted_occupancy_percent"] > late_night["predicted_occupancy_percent"]
    assert dinner_hour["predicted_occupancy_percent"] > late_night["predicted_occupancy_percent"]
