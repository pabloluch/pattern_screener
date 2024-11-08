from functools import wraps
import time
import asyncio
from collections import defaultdict
from typing import List, Dict, Union, Callable, Optional
import inspect
from contextlib import contextmanager, asynccontextmanager

class TimingStats:
    def __init__(self):
        self.stats = defaultdict(list)
        self.total_runtime = 0.0
        self.start_time = None
        # Add candle monitoring statistics
        self.candle_stats = defaultdict(lambda: defaultdict(lambda: {
            'total': 0,
            'complete': 0,
            'incomplete': 0,
            'counts': []
        }))
        
    def add_timing(self, method_name: str, execution_time: float):
        self.stats[method_name].append(execution_time)
    
    def start_total_timer(self):
        """Start the total execution timer"""
        self.start_time = time.perf_counter()
    
    def stop_total_timer(self):
        """Stop the total execution timer and calculate total runtime"""
        if self.start_time is not None:
            self.total_runtime = time.perf_counter() - self.start_time
            print(f"DEBUG: Setting total_runtime to {self.total_runtime}")  # Debug print
            self.start_time = None

    def monitor_candles(self, 
                    symbol: str, 
                    timeframe: str, 
                    candle_count: int, 
                    expected_candles: int = 498) -> None:
        """
        Monitor candle reception for a specific symbol and timeframe
        
        Args:
            symbol: Trading pair symbol
            timeframe: Timeframe of the candles
            candle_count: Number of candles received
            expected_candles: Expected number of candles (default: 498)
        """
        # Reset the stats for this symbol/timeframe combination if it's the first time
        if symbol not in self.candle_stats[timeframe]:
            self.candle_stats[timeframe][symbol] = {
                'total': 0,
                'complete': 0,
                'incomplete': 0,
                'counts': []
            }
        
        stats = self.candle_stats[timeframe][symbol]
        # Only update if we haven't counted this symbol/timeframe combination before
        if not stats['total']:
            stats['total'] = 1
            stats['counts'].append(candle_count)
            
            if candle_count == expected_candles:
                stats['complete'] = 1
            elif candle_count > 0:
                stats['incomplete'] = 1

    def get_candle_summary(self, expected_candles: int = 498) -> str:
        """Generate a summary of candle reception statistics"""
        summary = ["\nCandle Reception Statistics:", "-" * 80]
        
        for timeframe, symbols_data in sorted(self.candle_stats.items()):
            all_counts = []
            total_pairs = 0
            complete_pairs = 0
            incomplete_pairs = 0
            
            for symbol_stats in symbols_data.values():
                total_pairs += symbol_stats['total']
                complete_pairs += symbol_stats['complete']
                incomplete_pairs += symbol_stats['incomplete']
                all_counts.extend(symbol_stats['counts'])
            
            if all_counts:
                avg_count = sum(all_counts) / len(all_counts)
                min_count = min(all_counts)
                max_count = max(all_counts)
                reception_rate = (avg_count / expected_candles) * 100
                
                summary.extend([
                    f"\nTimeframe: {timeframe}",
                    f"Total pairs processed: {total_pairs}",
                    f"Pairs with complete data ({expected_candles} candles): {complete_pairs}",
                    f"Pairs with incomplete data: {incomplete_pairs}",
                    f"Pairs with no data: {total_pairs - complete_pairs - incomplete_pairs}",
                    f"Average candles received: {avg_count:.2f}",
                    f"Min candles received: {min_count}",
                    f"Max candles received: {max_count}",
                    f"Average reception rate: {reception_rate:.2f}%"
                ])
            else:
                summary.extend([
                    f"\nTimeframe: {timeframe}",
                    "No data received"
                ])
        
        return "\n".join(summary)
        
    def get_summary(self):
        timing_summary = []
        # Add total runtime at the top
        if self.total_runtime > 0:
            timing_summary.extend([
                "Total Program Runtime:",
                f"  - {self.total_runtime:.2f} seconds",
                "\nFunction-specific timing:"
            ])
            
        for method_name, times in sorted(self.stats.items()):
            avg_time = sum(times) / len(times)
            total_time = sum(times)
            calls = len(times)
            timing_summary.extend([
                f"{method_name}:",
                f"  - Total time: {total_time:.2f} seconds",
                f"  - Average time: {avg_time:.2f} seconds",
                f"  - Number of calls: {calls}"
            ])
            
        # Add candle statistics if available
        if self.candle_stats:
            timing_summary.append("\n" + self.get_candle_summary())
            
        return "\n".join(timing_summary)

    @contextmanager
    def measure_total_time(self):
        """Context manager for measuring total execution time in sync code"""
        self.start_total_timer()
        try:
            yield
        finally:
            self.stop_total_timer()

    @asynccontextmanager
    async def measure_total_time_async(self):
        """Context manager for measuring total execution time in async code"""
        self.start_total_timer()
        try:
            yield
        finally:
            self.stop_total_timer()

# Create a global instance
timing_stats = TimingStats()

def timing_decorator(func: Callable) -> Callable:
    """
    A decorator that times function execution and works with both async and sync functions.
    """
    if asyncio.iscoroutinefunction(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                execution_time = time.perf_counter() - start_time
                timing_stats.add_timing(func.__name__, execution_time)
        return async_wrapper
    else:
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                execution_time = time.perf_counter() - start_time
                timing_stats.add_timing(func.__name__, execution_time)
        return sync_wrapper

# Example usage
if __name__ == "__main__":
    @timing_decorator
    async def async_task():
        await asyncio.sleep(1)
        return "done"

    async def main():
        # Use the async context manager to measure total time
        async with timing_stats.measure_total_time_async():
            # Simulate some work
            await async_task()
            await async_task()
            # Add some non-measured delay
            await asyncio.sleep(0.5)
            
        # Simulate monitoring some candles
        timing_stats.monitor_candles("BTC_USDT", "Min1", 498)
        timing_stats.monitor_candles("ETH_USDT", "Min1", 450)
        timing_stats.monitor_candles("BTC_USDT", "Min5", 498)
        timing_stats.monitor_candles("ETH_USDT", "Min5", 475)
        
        print(timing_stats.get_summary())

    asyncio.run(main())