# main.py
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
from typing import List
import json
from wave_scanner import AsyncWaveScanner

app = FastAPI()

# Configure CORS for Render's domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, you can specify exact Render domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize scanner
scanner = AsyncWaveScanner()
active_connections: List[WebSocket] = []

# Store patterns in memory (simpler than setting up a database)
recent_patterns = []

@app.get("/")
async def root():
    """Serve the dashboard HTML"""
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
        <head>
            <title>Wave Pattern Scanner</title>
            <meta http-equiv="refresh" content="0;url=/static/index.html">
        </head>
    </html>
    """)

@app.get("/health")
async def health_check():
    """Health check endpoint for Render"""
    return {"status": "healthy"}

@app.get("/patterns")
async def get_patterns():
    """Get recent patterns"""
    return recent_patterns

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except:
        active_connections.remove(websocket)

async def notify_clients(data):
    """Send updates to all connected clients"""
    for connection in active_connections[:]:
        try:
            await connection.send_json(data)
        except:
            active_connections.remove(connection)

async def run_scan():
    """Run a single market scan"""
    try:
        print("Starting market scan...")
        results = await scanner.scan_market()
        if results:
            # Keep only recent patterns (last 100)
            global recent_patterns
            recent_patterns = (results + recent_patterns)[:100]
            await notify_clients(results)
        print("Scan completed")
    except Exception as e:
        print(f"Error during scan: {str(e)}")

def run_scheduler():
    """Run the scheduler in background"""
    schedule.every(30).minutes.do(lambda: asyncio.run(run_scan()))
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    # Start scheduler in background thread
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    # Start FastAPI application
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)