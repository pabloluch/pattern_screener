from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import asyncio
from datetime import timezone
from market_data_fetcher import MultiSessionMarketFetcher, CandleData

@dataclass
class AggregatedCandle:
    timestamp: int  # Unix timestamp in seconds
    open: float
    high: float
    close: float
    low: float
    timeframe: str

class TimeframeConverter:
    # Mapping of derived timeframes to their base timeframes
    TIMEFRAME_MAPPING = {
        1: ('Min1', 1),    # 1min derived from 1min
        2: ('Min1', 1),    # 2min derived from 1min
        3: ('Min1', 1),    # 3min derived from 1min
        10: ('Min5', 5),    # 10min derived from 5min
        15: ('Min15', 15),  # 15min derived from 15min
        30: ('Min15', 15),  # 30min derived from 15min
        45: ('Min15', 15),  # 45min derived from 15min
        60: ('Min60', 60), # 1hour derived from 1hour
        120: ('Min60', 60), # 2hour derived from 1hour
        180: ('Min60', 60)  # 3hour derived from 1hour
    }

    @staticmethod
    def validate_timeframe(minutes: int) -> bool:
        """
        Validate if the timeframe is valid (positive integer and divides evenly into a day)
        """
        if not isinstance(minutes, int) or minutes <= 0:
            return False
        minutes_in_day = 24 * 60
        return minutes_in_day % minutes == 0

    @staticmethod
    def format_timeframe(minutes: int) -> str:
        """
        Format timeframe into a readable string.
        Examples: Min5, Hour1, Hour4, etc.
        """
        if minutes < 60:
            return f"Min{minutes}"
        hours = minutes // 60
        return f"Hour{hours}"

    @staticmethod
    def align_timestamp(timestamp: int, minutes: int) -> int:
        """
        Align timestamp to the nearest timeframe start in UTC.
        Ensures alignment to proper boundaries for multi-hour timeframes.
        """
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        total_minutes = dt.hour * 60 + dt.minute
        
        # Calculate minutes since start of day and round down to nearest timeframe
        aligned_minutes = (total_minutes // minutes) * minutes
        
        aligned_dt = dt.replace(
            hour=aligned_minutes // 60,
            minute=aligned_minutes % 60,
            second=0,
            microsecond=0
        )
        
        return int(aligned_dt.timestamp())

    @classmethod
    def get_base_timeframe(cls, target_minutes: int) -> Tuple[str, int]:
        """
        Get the appropriate base timeframe for the target timeframe
        """
        return cls.TIMEFRAME_MAPPING.get(target_minutes, ('Min5', 5))

    @classmethod
    def get_candles(
        cls,
        all_timeframe_candles: Dict[str, List[CandleData]], 
        timeframe_minutes: int,
        limit: int = 498
    ) -> List[AggregatedCandle]:
        """
        Get candles for any specified timeframe using the appropriate base timeframe.
        """
        if not cls.validate_timeframe(timeframe_minutes):
            raise ValueError(f"Invalid timeframe: {timeframe_minutes} minutes")

        # Get the appropriate base timeframe
        base_timeframe, base_minutes = cls.get_base_timeframe(timeframe_minutes)
        
        # Get base candles
        base_candles = all_timeframe_candles.get(base_timeframe, [])
        if not base_candles:
            return []

        # Sort candles by timestamp in descending order (newest first)
        sorted_candles = sorted(base_candles, key=lambda x: x.timestamp, reverse=True)
        
        # If requesting the base timeframe, just convert format
        if timeframe_minutes == base_minutes:
            return [
                AggregatedCandle(
                    timestamp=candle.timestamp,
                    open=candle.open,
                    high=candle.high,
                    close=candle.close,
                    low=candle.low,
                    timeframe=cls.format_timeframe(timeframe_minutes)
                )
                for candle in sorted_candles[:limit]
            ]

        # Take only the candles we need based on limit and aggregation factor
        candles_needed = limit * (timeframe_minutes // base_minutes)
        candles_to_process = sorted_candles[:candles_needed]

        # Group candles by their aligned timestamp
        grouped_candles: Dict[int, List[CandleData]] = {}
        for candle in candles_to_process:
            aligned_ts = cls.align_timestamp(candle.timestamp, timeframe_minutes)
            if aligned_ts not in grouped_candles:
                grouped_candles[aligned_ts] = []
            grouped_candles[aligned_ts].append(candle)

        # Create aggregated candles
        aggregated = []
        for timestamp in sorted(grouped_candles.keys(), reverse=True):
            group = sorted(grouped_candles[timestamp], key=lambda x: x.timestamp)
            if len(group) > 0:
                aggregated_candle = AggregatedCandle(
                    timestamp=timestamp,
                    open=group[0].open,
                    close=group[-1].close,
                    high=max(c.high for c in group),
                    low=min(c.low for c in group),
                    timeframe=cls.format_timeframe(timeframe_minutes)
                )
                aggregated.append(aggregated_candle)
                if len(aggregated) >= limit:
                    break

        return aggregated[:limit]

#Example usage
async def main():
    timeframes = ['Min60']
    async with MultiSessionMarketFetcher(timeframes) as fetcher:
        symbol = "BTC_USDT"
        print(f"\nFetching data for {symbol}...")
        
        all_candles = await fetcher.fetch_all_candles([symbol])
        if not all_candles or symbol not in all_candles:
            print("No data fetched")
            return
            
        print("Fetched base timeframe candles:")
        for timeframe in timeframes:
            candle_count = len(all_candles[symbol].get(timeframe, []))
            print(f"{timeframe}: {candle_count} candles")
        
        converter = TimeframeConverter()
        timeframes_minutes = [60, 120, 180]
        
        timeframes_data = {
            f"{mins}-minute" if mins < 60 else f"{mins//60}-hour": 
            converter.get_candles(all_candles[symbol], mins)
            for mins in timeframes_minutes
        }
        
        print(f"\nTimeframe analysis for {symbol}:")
        for timeframe_name, candles in timeframes_data.items():
            print(f"\n{timeframe_name} candles:")
            print(f"Number of candles: {len(candles)}")
            
            if candles:
                # Print oldest 2 candles
                print("\nOldest 2 candles:")
                for i in range(min(2, len(candles)), 0, -1):
                    candle = candles[-i]
                    print(f"Time: {datetime.fromtimestamp(candle.timestamp, tz=timezone.utc)} UTC")
                    print(f"OHLC: {candle.open:.2f}, {candle.high:.2f}, "
                          f"{candle.low:.2f}, {candle.close:.2f}")
                
                # Print newest 2 candles
                print("\nNewest 2 candles:")
                for i in range(min(2, len(candles))):
                    candle = candles[i]
                    print(f"Time: {datetime.fromtimestamp(candle.timestamp, tz=timezone.utc)} UTC")
                    print(f"OHLC: {candle.open:.2f}, {candle.high:.2f}, "
                          f"{candle.low:.2f}, {candle.close:.2f}")
                
                # Print some alignment debugging info for 2-hour timeframe
                if timeframe_name == "2-hour":
                    print("\nAlignment check for first few 2-hour candles:")
                    for i in range(min(5, len(candles))):
                        candle = candles[i]
                        dt = datetime.fromtimestamp(candle.timestamp, tz=timezone.utc)
                        print(f"Candle {i}: Hour={dt.hour}, Minute={dt.minute}")


if __name__ == "__main__":
    asyncio.run(main())