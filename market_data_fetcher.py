from datetime import datetime
import logging
import asyncio
import aiohttp
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Set
from concurrent.futures import ThreadPoolExecutor

@dataclass
class CandleData:
    timestamp: int
    open: float
    high: float
    close: float
    low: float
    timeframe: str

@dataclass
class PositionLimit:
    symbol: str
    max_leverage: float
    contract_size: float
    max_vol: float
    last_price: float
    max_position: float

class TimeframeSession:
    def __init__(self, timeframe: str, rate_limit: int = 10):
        self.timeframe = timeframe
        self.base_url = "https://contract.mexc.com/api/v1/contract"
        self.session = None
        self.semaphore = asyncio.Semaphore(rate_limit)
        self.rate_limit_delay = 0.1
        self.logger = logging.getLogger(f"{__name__}_{timeframe}")

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def _safe_request(self, url: str, params: Optional[Dict] = None) -> Optional[Dict]:
        async with self.semaphore:
            try:
                await asyncio.sleep(self.rate_limit_delay)
                async with self.session.get(url, params=params, timeout=10) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        self.logger.error(f"Error in request {url}: {response.status}")
                        return None
            except Exception as e:
                self.logger.error(f"Exception in request {url}: {str(e)}")
                return None

    async def fetch_candles_batch(self, symbols: List[str]) -> Dict[str, List[CandleData]]:
        results = {}
        batch_size = 20
        
        for i in range(0, len(symbols), batch_size):
            batch_symbols = symbols[i:i + batch_size]
            tasks = [self.fetch_single_candles(symbol) for symbol in batch_symbols]
            batch_results = await asyncio.gather(*tasks)
            
            for symbol, candles in zip(batch_symbols, batch_results):
                results[symbol] = candles
            
            if i + batch_size < len(symbols):
                await asyncio.sleep(2)
        
        return results

    async def fetch_single_candles(self, symbol: str, limit: int = 498) -> List[CandleData]:
        url = f"{self.base_url}/kline/{symbol}"
        params = {'interval': self.timeframe, 'limit': limit}
        data = await self._safe_request(url, params)
        
        if not data:
            return []
            
        data = data.get('data', {})
        candles = []
        
        times = data.get('time', [])
        opens = data.get('open', [])
        closes = data.get('close', [])
        highs = data.get('high', [])
        lows = data.get('low', [])
        
        for i in range(len(times)):
            candle = CandleData(
                timestamp=times[i],
                open=opens[i],
                close=closes[i],
                high=highs[i],
                low=lows[i],
                timeframe=self.timeframe
            )
            candles.append(candle)
        
        return candles

class MultiSessionMarketFetcher:
    def __init__(self, timeframes: List[str]):
        self.timeframes = timeframes
        self.base_url = "https://contract.mexc.com/api/v1/contract"
        self.logger = logging.getLogger(__name__)
        self.session = None  # Main session for fetching pairs and limits

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def _safe_request(self, url: str, params: Optional[Dict] = None) -> Optional[Dict]:
        try:
            async with self.session.get(url, params=params, timeout=10) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    self.logger.error(f"Error in request {url}: {response.status}")
                    return None
        except Exception as e:
            self.logger.error(f"Exception in request {url}: {str(e)}")
            return None

    async def fetch_perpetual_pairs(self) -> List[Dict]:
        url = f"{self.base_url}/ticker?fields=symbol,lastPrice"
        data = await self._safe_request(url)
        
        if not data:
            return []
            
        pairs = data.get('data', [])
        return [{'pair': pair['symbol'], 'price': float(pair.get('lastPrice', 'N/A'))} 
                for pair in pairs]

    async def fetch_position_limits(self, pairs: List[Dict]) -> Dict[str, PositionLimit]:
        url = f"{self.base_url}/detail"
        price_map = {pair['pair']: pair['price'] for pair in pairs}
        data = await self._safe_request(url)
        
        if not data:
            return {}
            
        data = data.get('data', [])
        if not isinstance(data, list):
            data = [data]
            
        limits = {}
        for contract in data:
            symbol = contract.get('symbol')
            if symbol not in price_map:
                continue
                
            last_price = price_map[symbol]
            limit = PositionLimit(
                symbol=symbol,
                max_leverage=float(contract.get('maxLeverage', 0)),
                contract_size=float(contract.get('contractSize', 0)),
                max_vol=float(contract.get('maxVol', 0)),
                last_price=last_price,
                max_position=float(contract.get('maxVol', 0)) * float(contract.get('contractSize', 0)) * last_price
            )
            limits[symbol] = limit
        
        return limits

    async def fetch_all_candles(self, symbols: List[str]) -> Dict[str, Dict[str, List[CandleData]]]:
        """Fetch candles for all timeframes concurrently using separate sessions"""
        async def fetch_timeframe(timeframe: str) -> Tuple[str, Dict[str, List[CandleData]]]:
            async with TimeframeSession(timeframe) as session:
                candles = await session.fetch_candles_batch(symbols)
                return timeframe, candles

        # Create tasks for each timeframe
        tasks = [fetch_timeframe(tf) for tf in self.timeframes]
        
        # Run all timeframe fetches concurrently
        results = await asyncio.gather(*tasks)
        
        # Reorganize results by symbol
        final_results: Dict[str, Dict[str, List[CandleData]]] = {}
        for timeframe, timeframe_data in results:
            for symbol, candles in timeframe_data.items():
                if symbol not in final_results:
                    final_results[symbol] = {}
                final_results[symbol][timeframe] = candles
                
        return final_results

# Example usage
async def main():
    #Min1、Min5、Min15、Min30、Min60、Hour4、Hour8、Day1、Week1、Month1
    timeframes = ['Min1','Min5','Min15', 'Min60'] 
    symbols = ['BTC_USDT']
    
    async with MultiSessionMarketFetcher(timeframes) as fetcher:
        # Fetch pairs and their prices (we still need this to get the current price)
        pairs = await fetcher.fetch_perpetual_pairs()
        if not pairs:
            print("No pairs fetched")
            return

        # Filter for just BTC_USDT
        btc_pair = next((pair for pair in pairs if pair['pair'] == 'BTC_USDT'), None)
        if not btc_pair:
            print("BTC_USDT pair not found")
            return

        # Fetch position limits
        position_limits = await fetcher.fetch_position_limits([btc_pair])
        
        # Fetch candles for BTC_USDT
        all_candles = await fetcher.fetch_all_candles(symbols)
        
        # Print detailed information
        print(f"\nSymbol: BTC_USDT")
        if 'BTC_USDT' in all_candles:
            for timeframe in timeframes:
                if timeframe in all_candles['BTC_USDT']:
                    candles = all_candles['BTC_USDT'][timeframe]
                    num_candles = len(candles)
                    
                    # Get last two timestamps if available
                    last_times = []
                    if num_candles >= 2:
                        last_times = [candles[-1].timestamp, candles[-2].timestamp]
                    
                    print(f"  {timeframe}: {num_candles} candles")
                    if last_times:
                        print(f"    Ultimo timestamps: {last_times[0]}, {datetime.utcfromtimestamp(last_times[0])}")
                        print(f"    Penltimo timestamps: {last_times[1]}, {datetime.utcfromtimestamp(last_times[1])}")
                else:
                    print(f"  {timeframe}: No data")

if __name__ == "__main__":
    asyncio.run(main())