# verify_deployment.py
import aiohttp
import asyncio
import sys
from datetime import datetime
from typing import Dict, Any

async def verify_endpoint(session: aiohttp.ClientSession, url: str, endpoint: str) -> Dict[str, Any]:
    """Verify a specific endpoint"""
    try:
        async with session.get(f"{url}{endpoint}") as response:
            data = await response.json()
            return {
                "endpoint": endpoint,
                "status": response.status,
                "response": data
            }
    except Exception as e:
        return {
            "endpoint": endpoint,
            "status": "error",
            "error": str(e)
        }

async def verify_deployment(base_url: str):
    """Verify deployment by checking all endpoints"""
    print(f"Verifying deployment at {base_url}")
    print(f"Started at: {datetime.now().isoformat()}")
    print("-" * 50)
    
    async with aiohttp.ClientSession() as session:
        endpoints = ["/", "/health", "/status"]
        results = await asyncio.gather(*[
            verify_endpoint(session, base_url, endpoint)
            for endpoint in endpoints
        ])
        
        all_passed = True
        for result in results:
            print(f"\nChecking {result['endpoint']}:")
            if result['status'] == 200:
                print("✅ Success")
            else:
                print("❌ Failed")
                print(f"Error: {result.get('error', 'Unknown error')}")
                all_passed = False
            print(f"Response: {result.get('response', 'No response')}")
        
        print("\n" + "-" * 50)
        if all_passed:
            print("✅ All checks passed!")
            return True
        else:
            print("❌ Some checks failed!")
            return False

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python verify_deployment.py <base_url>")
        print("Example: python verify_deployment.py https://wave-scanner-api.onrender.com")
        sys.exit(1)
        
    base_url = sys.argv[1]
    success = asyncio.run(verify_deployment(base_url))
    sys.exit(0 if success else 1)