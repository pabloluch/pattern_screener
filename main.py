import os
import asyncio
import logging
import traceback
from fastapi import FastAPI, WebSocket, HTTPException
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

class ScannerState:
    def __init__(self):
        self.recent_patterns = []
        self.last_scan_time = None
        self.is_scanning = False
        self.scan_history = []
        
    def add_patterns(self, new_patterns):
        try:
            flattened_patterns = []
            if isinstance(new_patterns, dict):
                for symbol, timeframe_data in new_patterns.items():
                    for timeframe, pattern_data in timeframe_data.items():
                        # Handle both bull and bear patterns
                        if pattern_data:
                            for pattern_type in ['bull', 'bear']:
                                for wave_type in ['fast_wave', 'slow_wave']:
                                    if (pattern := pattern_data.get(pattern_type, {}).get(wave_type)):
                                        pattern_entry = {
                                            'symbol': symbol,
                                            'timeframe': timeframe,
                                            'pattern_type': pattern_type,
                                            'wave_type': wave_type,
                                            'timestamp': datetime.now(timezone.utc).isoformat(),
                                            'pattern_points': pattern.get('pattern_points', ''),
                                            'max_position': pattern.get('max_position', 0),
                                            'max_leverage': pattern.get('max_leverage', 0)
                                        }
                                        flattened_patterns.append(pattern_entry)
            
            if flattened_patterns:
                self.recent_patterns = flattened_patterns + self.recent_patterns
                self.recent_patterns = self.recent_patterns[:100]  # Keep only last 100 patterns
                logger.info(f"Added {len(flattened_patterns)} new patterns. Total: {len(self.recent_patterns)}")
            else:
                logger.info("No new patterns to add")
                
        except Exception as e:
            logger.error(f"Error adding patterns: {str(e)}", exc_info=True)

# Initialize FastAPI app and state
app = FastAPI(title="Wave Pattern Scanner")
scanner_state = ScannerState()
scanner = AsyncWaveScanner()
active_connections: List[WebSocket] = []

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
        "last_scan": scanner_state.last_scan_time.isoformat() if scanner_state.last_scan_time else None,
        "patterns_found": len(scanner_state.recent_patterns),
        "active_connections": len(active_connections),
        "is_scanning": scanner_state.is_scanning
    }

@app.get("/status")
async def get_status():
    """Get detailed scanner status"""
    return {
        "last_scan_time": scanner_state.last_scan_time.isoformat() if scanner_state.last_scan_time else None,
        "patterns_found": len(scanner_state.recent_patterns),
        "active_connections": len(active_connections),
        "is_scanning": scanner_state.is_scanning,
        "scan_history": scanner_state.scan_history[-10:],  # Last 10 scans
        "memory_usage": {
            "patterns": len(scanner_state.recent_patterns),
            "connections": len(active_connections)
        }
    }

# Debug endpoints
@app.get("/debug/scan-result")
async def debug_last_scan():
    """Debug endpoint to see raw scan result structure"""
    try:
        results = await scanner.scan_market()
        return {
            "raw_results": results,
            "type": str(type(results)),
            "structure": {
                "is_dict": isinstance(results, dict),
                "is_list": isinstance(results, list),
                "keys": list(results.keys()) if isinstance(results, dict) else None,
                "sample": str(results)[:1000] + "..." if results else None
            }
        }
    except Exception as e:
        return {
            "error": str(e),
            "traceback": traceback.format_exc()
        }

@app.get("/debug/state")
async def debug_state():
    """Debug endpoint to see current scanner state"""
    return {
        "recent_patterns_count": len(scanner_state.recent_patterns),
        "recent_patterns_type": str(type(scanner_state.recent_patterns)),
        "last_scan_time": scanner_state.last_scan_time,
        "is_scanning": scanner_state.is_scanning,
        "scan_history_count": len(scanner_state.scan_history),
        "active_connections": len(active_connections)
    }

@app.get("/debug/patterns/raw")
async def debug_patterns_raw():
    """Show raw pattern data"""
    return {
        "patterns": scanner_state.recent_patterns,
        "sample_pattern": scanner_state.recent_patterns[0] if scanner_state.recent_patterns else None,
        "pattern_structure": {
            "keys": list(scanner_state.recent_patterns[0].keys()) if scanner_state.recent_patterns else None,
            "nested_structure": str(type(scanner_state.recent_patterns[0].get("patterns"))) if scanner_state.recent_patterns else None
        }
    }

@app.get("/debug/wave-compare/{symbol}/{timeframe}")
async def compare_wave_calculations(symbol: str, timeframe: str):
    """Compare wave calculations with pattern detection"""
    try:
        # Get wave data normally
        wave_data = await get_wave_data(symbol, timeframe)
        
        # Get pattern data
        scanner = AsyncWaveScanner()
        results = await scanner.scan_market()
        
        # Extract pattern data for comparison
        pattern_data = None
        if results and symbol in results:
            timeframe_data = results[symbol].get(timeframe, {})
            pattern_data = {
                "bull": timeframe_data.get("bull", {}),
                "bear": timeframe_data.get("bear", {})
            }
        
        return {
            "wave_calculation": {
                "fast_wave_sample": wave_data["fast_wave"][:5],
                "slow_wave_sample": wave_data["slow_wave"][:5],
                "timestamps_sample": wave_data["timestamps"][:5]
            },
            "pattern_data": pattern_data
        }
        
    except Exception as e:
        logger.error(f"Error in comparison: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# Pattern endpoints
@app.get("/patterns")
async def get_patterns():
    """Get recent patterns"""
    return scanner_state.recent_patterns

@app.get("/wave-data/{symbol}/{timeframe}")
async def get_wave_data(symbol: str, timeframe: str):
    """Get wave data for a specific symbol and timeframe"""
    try:
        logger.info(f"Fetching wave data for {symbol} {timeframe}")
        
        # Parse timeframe to minutes
        minutes = None
        if timeframe.startswith('Min'):
            minutes = int(timeframe.replace('Min', ''))
        elif timeframe.startswith('Hour'):
            minutes = int(timeframe.replace('Hour', '')) * 60
        
        if minutes is None:
            logger.error(f"Invalid timeframe format: {timeframe}")
            raise HTTPException(status_code=400, detail="Invalid timeframe format")

        # Get base timeframe using same logic as scanner
        base_timeframe = TimeframeConverter.get_base_timeframe(minutes)[0]
        logger.info(f"Using base timeframe {base_timeframe} for requested timeframe {timeframe}")

        # Fetch base timeframe candles
        async with MultiSessionMarketFetcher([base_timeframe]) as fetcher:
            all_candles = await fetcher.fetch_all_candles([symbol])
            
            if not all_candles or symbol not in all_candles:
                logger.error(f"No candles found for {symbol}")
                raise HTTPException(status_code=404, detail="No data found")

            # Convert to target timeframe using TimeframeConverter
            converter = TimeframeConverter()
            candles = converter.get_candles(all_candles[symbol], minutes)
            
            if not candles:
                logger.error(f"No candles after conversion for {timeframe}")
                raise HTTPException(status_code=404, detail="No candles found")

            logger.info(f"Got {len(candles)} candles for {symbol} {timeframe}")
            logger.info(f"First candle: {candles[0].timestamp}, Last candle: {candles[-1].timestamp}")

            # Calculate waves using the same WaveIndicator configuration as scanner
            wave_ind = WaveIndicator(
                ema_length1=9,
                ema_length2=12,
                sma_length=3,
                scale_factor=0.015,
                output_length=50
            )
            
            # Calculate waves with timestamps
            try:
                fast_wave, slow_wave, wave_timestamps = wave_ind.calculate(candles)
                
                if len(fast_wave) == 0 or len(slow_wave) == 0 or len(wave_timestamps) == 0:
                    logger.error("Wave calculation returned empty arrays")
                    raise HTTPException(status_code=500, detail="Wave calculation failed")
                
                logger.info(f"Calculated waves. Fast wave length: {len(fast_wave)}, "
                          f"Slow wave length: {len(slow_wave)}, "
                          f"Timestamps length: {len(wave_timestamps)}")
                
                # Format timestamps for frontend
                formatted_timestamps = []
                for ts in wave_timestamps:
                    try:
                        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                        formatted_timestamps.append(dt.strftime('%Y-%m-%d %H:%M:%S'))
                    except Exception as e:
                        logger.error(f"Error formatting timestamp {ts}: {str(e)}")
                        continue

                # Validate data consistency
                if not (len(formatted_timestamps) == len(fast_wave) == len(slow_wave)):
                    logger.error("Inconsistent lengths in calculated data")
                    raise HTTPException(
                        status_code=500, 
                        detail="Inconsistent data lengths in calculation results"
                    )

                # Prepare response data
                response_data = {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "timestamps": formatted_timestamps,
                    "fast_wave": fast_wave.tolist(),
                    "slow_wave": slow_wave.tolist(),
                    "candle_count": len(candles),
                    "wave_length": len(fast_wave)
                }

                # Add some debug information
                logger.debug(f"Sample fast wave values: {fast_wave[:5]}")
                logger.debug(f"Sample slow wave values: {slow_wave[:5]}")
                logger.debug(f"Sample timestamps: {formatted_timestamps[:5]}")

                return response_data

            except Exception as calc_error:
                logger.error(f"Error in wave calculation: {str(calc_error)}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Error calculating wave data: {str(calc_error)}"
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting wave data: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# Add a timeframe mapping endpoint for reference
@app.get("/timeframe-info/{timeframe}")
async def get_timeframe_info(timeframe: str):
    """Get information about timeframe conversion"""
    try:
        minutes = None
        if timeframe.startswith('Min'):
            minutes = int(timeframe.replace('Min', ''))
        elif timeframe.startswith('Hour'):
            minutes = int(timeframe.replace('Hour', '')) * 60
            
        if minutes is None:
            raise HTTPException(status_code=400, detail="Invalid timeframe format")
            
        base_timeframe, base_minutes = TimeframeConverter.get_base_timeframe(minutes)
        
        return {
            "requested_timeframe": timeframe,
            "minutes": minutes,
            "base_timeframe": base_timeframe,
            "base_minutes": base_minutes
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/patterns/statistics")
async def get_pattern_statistics():
    """Get pattern statistics"""
    if not scanner_state.recent_patterns:
        return {"message": "No patterns found"}
    
    try:
        # Calculate statistics
        patterns = scanner_state.recent_patterns
        timeframes = {}
        symbols = {}
        
        for pattern in patterns:
            # Count timeframes
            tf = pattern.get("timeframe", "unknown")
            timeframes[tf] = timeframes.get(tf, 0) + 1
            
            # Count symbols
            symbol = pattern.get("symbol", "unknown")
            symbols[symbol] = symbols.get(symbol, 0) + 1

        # Count pattern types
        pattern_types = {"bull": 0, "bear": 0}
        for pattern in patterns:
            if "patterns" in pattern:
                for p in pattern["patterns"]:
                    if "pattern_type" in p:
                        pattern_types[p["pattern_type"]] = pattern_types.get(p["pattern_type"], 0) + 1
        
        return {
            "total_patterns": len(patterns),
            "pattern_types": pattern_types,
            "timeframe_distribution": timeframes,
            "symbol_distribution": symbols,
            "last_update": scanner_state.last_scan_time.isoformat() if scanner_state.last_scan_time else None
        }
    except Exception as e:
        logger.error(f"Error calculating statistics: {str(e)}", exc_info=True)
        return {"error": "Error calculating statistics", "message": str(e)}

# Scanner control endpoint
@app.get("/trigger-scan")
async def trigger_scan():
    """Manually trigger a scan"""
    try:
        await run_scan()
        return {
            "status": "success",
            "message": "Scan triggered successfully",
            "last_scan_time": scanner_state.last_scan_time.isoformat() if scanner_state.last_scan_time else None,
            "patterns_found": len(scanner_state.recent_patterns)
        }
    except Exception as e:
        logger.error(f"Scan trigger error: {str(e)}", exc_info=True)
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
    if scanner_state.is_scanning:
        logger.warning("Scan already in progress, skipping...")
        return
    
    scanner_state.is_scanning = True
    scan_start_time = datetime.now(timezone.utc)
    
    try:
        logger.info("Starting market scan...")
        results = await scanner.scan_market()
        
        if results:
            # Update patterns list
            scanner_state.add_patterns(results)
            
            # Notify connected clients
            await notify_clients({
                "type": "scan_update",
                "data": scanner_state.recent_patterns,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            logger.info(f"Scan completed. Patterns found")
        else:
            logger.info("Scan completed. No patterns found")
        
        # Update scan history
        scan_duration = (datetime.now(timezone.utc) - scan_start_time).total_seconds()
        scanner_state.scan_history.append({
            "timestamp": scan_start_time.isoformat(),
            "duration": scan_duration,
            "patterns_found": len(scanner_state.recent_patterns),
            "status": "success"
        })
        
    except Exception as e:
        logger.error(f"Error during scan: {str(e)}", exc_info=True)
        scan_duration = (datetime.now(timezone.utc) - scan_start_time).total_seconds()
        scanner_state.scan_history.append({
            "timestamp": scan_start_time.isoformat(),
            "duration": scan_duration,
            "status": "error",
            "error": str(e)
        })
    finally:
        scanner_state.last_scan_time = datetime.now(timezone.utc)
        scanner_state.is_scanning = False
        # Keep only last 100 scan records
        scanner_state.scan_history = scanner_state.scan_history[-100:]

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