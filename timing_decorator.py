from functools import wraps
import time
import asyncio
from collections import defaultdict
from typing import List, Dict, Union, Callable
import inspect
from contextlib import contextmanager, asynccontextmanager

class TimingStats:
    def __init__(self):
        self.stats = defaultdict(list)
        self.total_runtime = 0.0
        self.start_time = None
        
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
        
    def get_summary(self):
        print(f"DEBUG: total_runtime is {self.total_runtime}")  # Debug print
        summary = []
        # Add total runtime at the top
        if self.total_runtime > 0:
            summary.append("Total Program Runtime:")
            summary.append(f"  - {self.total_runtime:.2f} seconds")
            summary.append("\nFunction-specific timing:")
            
        for method_name, times in sorted(self.stats.items()):
            avg_time = sum(times) / len(times)
            total_time = sum(times)
            calls = len(times)
            summary.append(f"{method_name}:")
            summary.append(f"  - Total time: {total_time:.2f} seconds")
            summary.append(f"  - Average time: {avg_time:.2f} seconds")
            summary.append(f"  - Number of calls: {calls}")
        return "\n".join(summary)

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
            
        print(timing_stats.get_summary())

    asyncio.run(main())