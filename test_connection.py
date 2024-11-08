# test_connection.py
import aiohttp
import asyncio
from datetime import datetime

async def test_connection(url: str):
    print(f"Testing connection to {url}")
    print(f"Time: {datetime.now().isoformat()}")
    print("-" * 50)

    # Test with different timeouts
    timeouts = [5, 10, 30]
    
    for timeout in timeouts:
        print(f"\nTrying with {timeout} second timeout...")
        try:
            timeout_settings = aiohttp.ClientTimeout(total=timeout)
            async with aiohttp.ClientSession(timeout=timeout_settings) as session:
                async with session.get(url) as response:
                    print(f"Status code: {response.status}")
                    print(f"Headers: {response.headers}")
                    if response.status == 200:
                        data = await response.json()
                        print(f"Response: {data}")
                        print("✅ Connection successful!")
                        return
        except asyncio.TimeoutError:
            print(f"❌ Timeout after {timeout} seconds")
        except aiohttp.ClientConnectorError as e:
            print(f"❌ Connection error: {str(e)}")
        except Exception as e:
            print(f"❌ Other error: {str(e)}")
    
    print("\nAll connection attempts failed")

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python test_connection.py <base_url>")
        print("Example: python test_connection.py https://wave-scanner-api.onrender.com")
        sys.exit(1)
        
    url = sys.argv[1]
    asyncio.run(test_connection(url))