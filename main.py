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
logging.basicConfig(level=logging.INFO)
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

class HealthCheck(BaseModel):
    status: str
    timestamp: str
    uptime: float
    version: str

start_time = datetime.now()

@app.get("/", response_model=HealthCheck)
async def root():
    """Root endpoint serving as a health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "uptime": (datetime.now() - start_time).total_seconds(),
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    """Detailed health check endpoint"""
    try:
        # Try to create scanner instance to verify dependencies
        scanner = AsyncWaveScanner()
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "checks": {
                    "scanner": "operational",
                    "api": "operational"
                }
            }
        )
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }
        )

@app.get("/scan")
async def scan_market():
    """Run market scan for patterns"""
    try:
        logger.info("Starting market scan")
        scanner = AsyncWaveScanner()
        results = await scanner.scan_market()
        logger.info("Market scan completed successfully")
        return results
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
    return {
        "status": "operational",
        "timestamp": datetime.now().isoformat(),
        "uptime": (datetime.now() - start_time).total_seconds(),
        "version": "1.0.0",
        "endpoints": [
            "/",
            "/health",
            "/scan",
            "/status"
        ]
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)