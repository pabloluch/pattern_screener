# main.py
from fastapi import FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
from wave_scanner import AsyncWaveScanner
import asyncio
from typing import Dict, Any
from datetime import datetime
import logging
from pydantic import BaseModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Wave Scanner API",
    description="API for scanning cryptocurrency market patterns",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    logger.info("Application starting up")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutting down")

class HealthCheck(BaseModel):
    status: str
    timestamp: str
    uptime: float
    version: str

start_time = datetime.now()

@app.get("/", response_model=HealthCheck)
async def root():
    logger.info("Health check endpoint accessed")
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "uptime": (datetime.now() - start_time).total_seconds(),
        "version": "1.0.0"
    }

@app.get("/scan")
async def scan_market():
    """Run market scan for patterns with enhanced error handling"""
    scan_start_time = datetime.now()
    logger.info("Starting market scan")
    
    try:
        scanner = AsyncWaveScanner()
        # Set a timeout for the entire scan operation
        results = await asyncio.wait_for(
            scanner.scan_market(),
            timeout=240  # 4 minutes timeout
        )
        
        duration = (datetime.now() - scan_start_time).total_seconds()
        logger.info(f"Market scan completed successfully in {duration:.2f} seconds")
        
        return {
            "status": "success",
            "duration": duration,
            "timestamp": datetime.now().isoformat(),
            "results": results
        }
    except asyncio.TimeoutError:
        logger.error("Market scan timed out")
        raise HTTPException(
            status_code=504,
            detail={
                "error": "Scan operation timed out",
                "timestamp": datetime.now().isoformat()
            }
        )
    except Exception as e:
        logger.error(f"Market scan failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
        )

@app.get("/status")
async def get_status():
    """Get API status and basic statistics"""
    logger.info("Status endpoint accessed")
    return {
        "status": "operational",
        "timestamp": datetime.now().isoformat(),
        "uptime": (datetime.now() - start_time).total_seconds(),
        "version": "1.0.0",
        "endpoints": ["/", "/health", "/scan", "/status"]
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)