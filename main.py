import os
import asyncio
import logging
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import schedule
import threading
import time
from typing import List, Dict, Optional
import json
from datetime import datetime, timezone
import uvicorn

# Import your existing modules
from wave_scanner import AsyncWaveScanner
from market_data_fetcher import MultiSessionMarketFetcher
from timeframe_converter import TimeframeConverter
from wave_indicator import WaveIndicator
from timing_decorator import timing_decorator, timing_stats

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="Wave Pattern Scanner")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Global variables
scanner = AsyncWaveScanner()
active_connections: List[WebSocket] = []
recent_patterns: List[Dict] = []
last_scan_time: Optional[datetime] = None
is_scanning: bool = False
scan_history: List[Dict] = []  # Store basic scan statistics

# Base router
@app.get("/", response_class=HTMLResponse)
async def root():
    """Redirect to the dashboard"""
    return """
    <!DOCTYPE html>
    <html>
        <head>
            <title>Wave Pattern Scanner</title>
            <meta http-equiv="refresh" content="0;url=/static/index.html">
        </head>
    </html>
    """

# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connection opened")
    active_connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
    finally:
        if websocket in active_connections:
            active_connections.remove(websocket)
        logger.info("WebSocket connection closed")

# Health and status endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "last_scan": last_scan_time.isoformat() if last_scan_time else None,
        "patterns_found": len(recent_patterns),
        "active_connections": len(active_connections),
        "is_scanning": is_scanning
    }

@app.get("/status")
async def get_status():
    """Get detailed scanner status"""
    return {
        "last_scan_time": last_scan_time.isoformat() if last_scan_time else None,
        "patterns_found": len(recent_patterns),
        "active_connections": len(active_connections),
        "is_scanning": is_scanning,
        "scan_history": scan_history[-10:],  # Last 10 scans
        "memory_usage": {
            "patterns": len(recent_patterns),
            "connections": len(active_connections)
        }
    }

# Pattern management endpoints
@app.get("/patterns")
async def get_patterns():
    """Get recent patterns"""
    return recent_patterns

@app.get("/patterns/statistics")
async def get_pattern_statistics():
    """Get pattern statistics"""
    if not recent_patterns:
        return {"message": "No patterns found"}
    
    # Calculate statistics
    bull_patterns = len([p for p in recent_patterns if p.get("pattern_type") == "bull"])
    bear_patterns = len([p for p in recent_patterns if p.get("pattern_type") == "bear"])
    timeframes = {}
    symbols = {}
    
    for pattern in recent_patterns:
        # Count timeframes
        tf = pattern.get("timeframe", "unknown")
        timeframes[tf] = timeframes.get(tf, 0) + 1
        
        # Count symbols
        symbol = pattern.get("symbol", "unknown")
        symbols[symbol] = symbols.get(symbol, 0) + 1
    
    return {
        "total_patterns": len(recent_patterns),
        "bull_patterns": bull_patterns,
        "bear_patterns": bear_patterns,
        "timeframe_distribution": timeframes,
        "symbol_distribution": symbols,
        "last_update": last_scan_time.isoformat() if last_scan_time else None
    }

# Scanner control endpoints
@app.get("/trigger-scan")
async def trigger_scan():
    """Manually trigger a scan"""
    try:
        await run_scan()
        return {
            "status": "success",
            "message": "Scan triggered successfully",
            "last_scan_time": last_scan_time.isoformat() if last_scan_time else None,
            "patterns_found": len(recent_patterns)
        }
    except Exception as e:
        logger.error(f"Scan trigger error: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }

# WebSocket notification
async def notify_clients(data: Dict):
    """Send updates to all connected clients"""
    disconnected = []
    for connection in active_connections:
        try:
            await connection.send_json(data)
        except Exception as e:
            logger.error(f"Error sending to client: {str(e)}")
            disconnected.append(connection)
    
    # Clean up disconnected clients
    for connection in disconnected:
        if connection in active_connections:
            active_connections.remove(connection)

# Scanner functionality
async def run_scan():
    """Run a single market scan"""
    global last_scan_time, recent_patterns, is_scanning
    
    if is_scanning:
        logger.warning("Scan already in progress, skipping...")
        return
    
    is_scanning = True
    scan_start_time = datetime.now(timezone.utc)
    
    try:
        logger.info("Starting market scan...")
        results = await scanner.scan_market()
        
        if results:
            # Update patterns list
            recent_patterns = results + recent_patterns
            recent_patterns = recent_patterns[:100]  # Keep only last 100 patterns
            
            # Notify connected clients
            await notify_clients({
                "type": "scan_update",
                "data": results,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            logger.info(f"Scan completed. Found {len(results)} patterns")
        else:
            logger.info("Scan completed. No patterns found")
            
        # Update scan history
        scan_duration = (datetime.now(timezone.utc) - scan_start_time).total_seconds()
        scan_history.append({
            "timestamp": scan_start_time.isoformat(),
            "duration": scan_duration,
            "patterns_found": len(results) if results else 0,
            "status": "success"
        })
        
        # Keep only last 100 scan records
        if len(scan_history) > 100:
            scan_history.pop(0)
            
    except Exception as e:
        logger.error(f"Error during scan: {str(e)}")
        scan_history.append({
            "timestamp": scan_start_time.isoformat(),
            "duration": (datetime.now(timezone.utc) - scan_start_time).total_seconds(),
            "status": "error",
            "error": str(e)
        })
    finally:
        last_scan_time = datetime.now(timezone.utc)
        is_scanning = False

async def scheduled_scan():
    """Wrapper for scheduled scan"""
    await run_scan()

def run_scheduler():
    """Run the scheduler in background"""
    logger.info("Starting scheduler")
    
    # Schedule scans every 30 minutes
    schedule.every(30).minutes.do(lambda: asyncio.run(scheduled_scan()))
    
    # Run first scan immediately
    asyncio.run(scheduled_scan())
    
    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except Exception as e:
            logger.error(f"Scheduler error: {str(e)}")
            time.sleep(60)  # Wait before retrying

@app.on_event("startup")
async def startup_event():
    """Start the scheduler when the application starts"""
    logger.info("Starting application...")
    # Start scheduler in background thread
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    logger.info("Scheduler started")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down application...")
    # Close all WebSocket connections
    for connection in active_connections:
        try:
            await connection.close()
        except Exception:
            pass
    logger.info("Application shutdown complete")

if __name__ == "__main__":
    # Get port from environment variable or use default
    port = int(os.environ.get("PORT", 10000))
    
    # Run the application
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )