# verify_deployment.py
import aiohttp
import asyncio
import sys
from datetime import datetime
from typing import Dict, Any
import json

async def verify_endpoint(session: aiohttp.ClientSession, url: str, endpoint: str) -> Dict[str, Any]:
    """Verify a specific endpoint with detailed error reporting"""
    try:
        print(f"\nTesting {endpoint}...")
        start_time = datetime.now()
        async with session.get(f"{url}{endpoint}") as response:
            try:
                data = await response.json()
                return {
                    "endpoint": endpoint,
                    "status": response.status,
                    "duration": (datetime.now() - start_time).total_seconds(),
                    "response": data
                }
            except Exception as json_error:
                text = await response.text()
                return {
                    "endpoint": endpoint,
                    "status": response.status,
                    "error": f"JSON Parse Error: {str(json_error)}\nRaw Response: {text[:500]}...",
                    "duration": (datetime.now() - start_time).total_seconds()
                }
    except Exception as e:
        return {
            "endpoint": endpoint,
            "status": "error",
            "error": f"Error: {str(e)}\nType: {type(e).__name__}"
        }

async def verify_deployment(base_url: str):
    """Verify deployment with enhanced error reporting"""
    print(f"Verifying deployment at {base_url}")
    print(f"Started at: {datetime.now().isoformat()}")
    print("-" * 50)
    
    timeout = aiohttp.ClientTimeout(total=300)  # 5 minute timeout
    async with aiohttp.ClientSession(timeout=timeout) as session:
        endpoints = ["/", "/health", "/status", "/scan"]
        results = []
        
        # Check endpoints sequentially
        for endpoint in endpoints:
            result = await verify_endpoint(session, base_url, endpoint)
            print(f"\nChecking {endpoint}:")
            
            if result["status"] == 200:
                print("✅ Success")
                print(f"Response: {json.dumps(result['response'], indent=2)}")
            else:
                print("❌ Failed")
                print(f"Status: {result['status']}")
                print(f"Error: {result.get('error', 'Unknown error')}")
            
            results.append(result)
        
        # Summary
        print("\n" + "=" * 50)
        print("Deployment Verification Summary:")
        print("=" * 50)
        all_passed = all(r["status"] == 200 for r in results)
        
        for r in results:
            status = "✅" if r["status"] == 200 else "❌"
            print(f"{status} {r['endpoint']}: {r['status']}")
        
        print("\nOverall Status:", "✅ PASSED" if all_passed else "❌ FAILED")
        return all_passed

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python verify_deployment.py <base_url>")
        print("Example: python verify_deployment.py https://wave-scanner-api.onrender.com")
        sys.exit(1)
        
    base_url = sys.argv[1]
    success = asyncio.run(verify_deployment(base_url))
    sys.exit(0 if success else 1)