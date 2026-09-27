import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .database import init_db
from .ai_engine import ai_engine
from .websocket_manager import ws_manager
from .routers import tables, queue, sensors, predictions, analytics, admin, reservations

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("dinesync")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing DINESYNC database...")
    init_db()
    logger.info("Training AI models from historical data...")
    ai_engine.train_models()
    logger.info("DINESYNC Backend initialized and ready!")
    yield
    # Shutdown
    logger.info("DINESYNC Backend shutting down.")

app = FastAPI(
    title="DINESYNC API",
    description="Smart Restaurant IoT Table Occupancy, Queue Management & AI Predictive Analytics Platform",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(tables.router)
app.include_router(queue.router)
app.include_router(sensors.router)
app.include_router(predictions.router)
app.include_router(analytics.router)
app.include_router(admin.router)
app.include_router(reservations.router)

# WebSocket Endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and accept client ping messages
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)

# Mount Static Frontend
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "DINESYNC Smart Restaurant Engine",
        "ai_engine_trained": ai_engine.is_trained
    }

@app.get("/healthz")
def healthz():
    return health_check()
