# main.py
from fastapi import FastAPI, HTTPException
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

app = FastAPI(title="Wave Scanner API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Track application start time
start_time = datetime.now()

@app.get("/")
def root():
    """Root endpoint for basic health check"""
    return JSONResponse(content={
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "uptime": (datetime.now() - start_time).total_seconds(),
        "version": "1.0.0"
    })

@app.get("/health")
def health_check():
    """Health check endpoint"""
    try:
        # Basic health check - no need to initialize scanner
        return JSONResponse(content={
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "checks": {
                "api": "operational"
            }
        })
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }
        )

@app.get("/status")
def get_status():
    """Status endpoint"""
    return JSONResponse(content={
        "status": "operational",
        "timestamp": datetime.now().isoformat(),
        "uptime": (datetime.now() - start_time).total_seconds(),
        "version": "1.0.0",
        "endpoints": ["/", "/health", "/scan", "/status"]
    })

@app.get("/scan")
async def scan_market():
    """Run market scan for patterns"""
    scan_start_time = datetime.now()
    logger.info("Starting market scan")
    
    try:
        scanner = AsyncWaveScanner()
        results = await scanner.scan_market()
        
        duration = (datetime.now() - scan_start_time).total_seconds()
        logger.info(f"Market scan completed in {duration:.2f} seconds")
        
        return {
            "status": "success",
            "duration": duration,
            "timestamp": datetime.now().isoformat(),
            "results": results
        }
    except Exception as e:
        logger.error(f"Market scan failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
        )

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)