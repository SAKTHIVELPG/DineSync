import json
import logging
from typing import List, Dict, Any, Optional
from fastapi import WebSocket

logger = logging.getLogger("dinesync.websocket")

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Active: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket client disconnected. Active: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast a message to all connected web clients"""
        if not self.active_connections:
            return
        
        json_data = json.dumps(message, default=str)
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_text(json_data)
            except Exception as e:
                logger.error(f"Error sending WebSocket message: {e}")
                dead_connections.append(connection)

        for dead in dead_connections:
            self.disconnect(dead)

    async def broadcast_table_update(self, table: Dict[str, Any]):
        await self.broadcast({
            "type": "TABLE_UPDATE",
            "data": table
        })

    async def broadcast_queue_update(self, event_type: str, queue_item: Optional[Dict[str, Any]] = None):
        await self.broadcast({
            "type": "QUEUE_UPDATE",
            "event": event_type,
            "data": queue_item
        })

    async def broadcast_sensor_telemetry(self, telemetry: Dict[str, Any]):
        await self.broadcast({
            "type": "SENSOR_TELEMETRY",
            "data": telemetry
        })

    async def broadcast_stats_refresh(self):
        await self.broadcast({
            "type": "STATS_REFRESH"
        })

ws_manager = ConnectionManager()
