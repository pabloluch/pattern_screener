import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from timeframe_converter import AggregatedCandle
import logging

@dataclass
class WaveData:
    timeframe: str
    fast_wave: np.ndarray  # Last 50 values
    slow_wave: np.ndarray  # Last 50 values
    timestamps: Optional[np.ndarray] = None

class WaveIndicator:
    def __init__(
        self,
        ema_length1: int = 9,
        ema_length2: int = 12,
        sma_length: int = 3,
        scale_factor: float = 0.015,
        output_length: int = 50
    ):
        self.ema_length1 = ema_length1
        self.ema_length2 = ema_length2
        self.sma_length = sma_length
        self.scale_factor = scale_factor
        self.output_length = output_length
        self.logger = logging.getLogger(__name__)
        self.epsilon = 1e-10
        
        # Calculate required warm-up periods
        self.warmup_periods = self._calculate_warmup_periods()

    def _calculate_warmup_periods(self) -> int:
        """
        Calculate the minimum number of candles needed for proper warm-up.
        Returns the maximum of:
        - 2 * longest EMA period (for proper EMA convergence)
        - SMA period (for proper SMA calculation)
        - 1 (for Heikin-Ashi calculation)
        """
        ema_warmup = 2 * max(self.ema_length1, self.ema_length2)
        return max(ema_warmup, self.sma_length, 1)

    def calculate_ema(self, data: np.ndarray, length: int) -> np.ndarray:
        """Calculate Exponential Moving Average with proper warm-up"""
        alpha = 2 / (length + 1)
        ema = np.zeros_like(data)
        
        # Use SMA for initial value to improve accuracy
        ema[0:length] = np.mean(data[0:length])
        
        # Calculate EMA
        for i in range(length, len(data)):
            ema[i] = data[i] * alpha + ema[i-1] * (1 - alpha)
        return ema
    
    def calculate_sma(self, data: np.ndarray, length: int) -> np.ndarray:
        """Calculate Simple Moving Average with proper padding"""
        weights = np.ones(length) / length
        sma = np.convolve(data, weights, mode='valid')
        
        # Pad the beginning with the first valid SMA value
        padding = np.full(length - 1, sma[0])
        return np.concatenate([padding, sma])
    
    def calculate_heikin_ashi(self, candles: List[AggregatedCandle]) -> np.ndarray:
        """Calculate Heikin-Ashi in chronological order"""
        # This function now receives candles in chronological order
        ha_close = np.zeros(len(candles))
        ha_open = np.zeros(len(candles))
        ha_high = np.zeros(len(candles))
        ha_low = np.zeros(len(candles))
        
        # First candle
        ha_close[0] = (candles[0].open + candles[0].high + candles[0].low + candles[0].close) / 4
        ha_open[0] = candles[0].open
        ha_high[0] = candles[0].high
        ha_low[0] = candles[0].low
        
        # Calculate subsequent candles
        for i in range(1, len(candles)):
            ha_close[i] = (candles[i].open + candles[i].high + candles[i].low + candles[i].close) / 4
            ha_open[i] = (ha_open[i-1] + ha_close[i-1]) / 2
            ha_high[i] = max(candles[i].high, ha_open[i], ha_close[i])
            ha_low[i] = min(candles[i].low, ha_open[i], ha_close[i])
        
        return (ha_high + ha_low + ha_close) / 3

    def calculate(self, candles: List[AggregatedCandle]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Optimize internal calculations while preserving output order"""
        if not candles:
            self.logger.warning("No candles provided for calculation")
            return np.array([]), np.array([]), np.array([])

        # Work with chronological order internally for calculations
        calc_candles = list(reversed(candles))  # Single reversal for internal work
        
        # Calculate indicators in chronological order
        hlc3 = self.calculate_heikin_ashi(calc_candles)
        x = self.calculate_ema(hlc3, self.ema_length1)
        abs_diff = np.abs(hlc3 - x)
        y = self.calculate_ema(abs_diff, self.ema_length1)
        y = y + self.epsilon
        z = (hlc3 - x) / (self.scale_factor * y)
        fast_wave = self.calculate_ema(z, self.ema_length2)
        slow_wave = self.calculate_sma(fast_wave, self.sma_length)
        
        # Replace any NaN values
        fast_wave = np.nan_to_num(fast_wave, 0)
        slow_wave = np.nan_to_num(slow_wave, 0)
        
        # Reverse back to newest-first order for output
        fast_wave = fast_wave[::-1]
        slow_wave = slow_wave[::-1]
        timestamps = np.array([candle.timestamp for candle in candles])  # Already in newest-first order
        
        # Return latest values first
        return (
            fast_wave[:self.output_length],
            slow_wave[:self.output_length],
            timestamps[:self.output_length]
        )
    
    def calculate_all_timeframes(self, timeframe_candles: Dict[str, List[AggregatedCandle]]) -> Dict[str, WaveData]:
        """
        Calculate Wave indicators for all timeframes using AggregatedCandle data
        
        Args:
            timeframe_candles: Dictionary with timeframe as key and list of AggregatedCandle as value
        Returns:
            Dictionary with timeframe as key and WaveData as value containing waves and timestamps
        """
        wave_data = {}
        for timeframe, candles in timeframe_candles.items():
            if not candles:
                self.logger.warning(f"No candles provided for timeframe {timeframe}")
                continue
                
            fast_wave, slow_wave, timestamps = self.calculate(candles)
            
            if len(fast_wave) == 0 or len(slow_wave) == 0:
                self.logger.warning(f"No wave data calculated for timeframe {timeframe}")
                continue
                
            wave_data[timeframe] = WaveData(
                timeframe=timeframe,
                fast_wave=fast_wave,
                slow_wave=slow_wave,
                timestamps=timestamps
            )
        return wave_data

# Example usage
import asyncio
from market_data_fetcher import MultiSessionMarketFetcher
from timeframe_converter import TimeframeConverter
from wave_indicator import WaveIndicator
from datetime import datetime, timezone
import pandas as pd

async def main():
    # Initialize Wave Indicator
    wave_ind = WaveIndicator(
        ema_length1=9,
        ema_length2=12,
        sma_length=3,
        scale_factor=0.015,
        output_length=50
    )

    # Define timeframes
    timeframes = ['Min60']  # We'll fetch 1-hour candles as base
    symbol = "BTC_USDT"    # Test with Bitcoin

    # Fetch market data
    async with MultiSessionMarketFetcher(timeframes) as fetcher:
        print(f"\nFetching {symbol} candles...")
        all_candles = await fetcher.fetch_all_candles([symbol])
        
        if not all_candles or symbol not in all_candles:
            print("No data fetched")
            return

        # Create timeframe converter
        converter = TimeframeConverter()
        
        # Get candles for different timeframes
        timeframes_data = {
            "1-hour": converter.get_candles(all_candles[symbol], 60),
            "2-hour": converter.get_candles(all_candles[symbol], 120),
            "3-hour": converter.get_candles(all_candles[symbol], 180)
        }

        # Calculate and print wave indicators for each timeframe
        for timeframe_name, candles in timeframes_data.items():
            print(f"\n{'='*50}")
            print(f"Analysis for {timeframe_name}")
            print(f"{'='*50}")
            
            if len(candles) < wave_ind.warmup_periods:
                print(f"Not enough candles for {timeframe_name}. "
                      f"Need at least {wave_ind.warmup_periods}, got {len(candles)}")
                continue

            print(f"\nTotal candles: {len(candles)}")
            print(f"Warmup periods required: {wave_ind.warmup_periods}")
            
            # Print the oldest few candles (used for warmup)
            print("\nOldest 3 candles (used for warmup):")
            for candle in list(reversed(candles))[:3]:
                dt = datetime.fromtimestamp(candle.timestamp, tz=timezone.utc)
                print(f"Time: {dt} UTC")
                print(f"OHLC: {candle.open:.2f}, {candle.high:.2f}, "
                      f"{candle.low:.2f}, {candle.close:.2f}\n")

            # Calculate wave indicators
            fast_wave, slow_wave = wave_ind.calculate(candles)
            
            # Print newest few wave values
            print(f"\nNewest 5 Wave values ({timeframe_name}):")
            print("Timestamp (UTC) | Fast Wave | Slow Wave")
            print("-" * 45)
            
            # Create a list of timestamps from the candles
            timestamps = [datetime.fromtimestamp(c.timestamp, tz=timezone.utc) 
                        for c in candles[:5]]
            
            # Print the wave values with their corresponding timestamps
            for dt, fast, slow in zip(timestamps, fast_wave[:5], slow_wave[:5]):
                print(f"{dt.strftime('%Y-%m-%d %H:%M')} | {fast:8.4f} | {slow:8.4f}")
            
            # Calculate some basic statistics
            print(f"\nWave Statistics for {timeframe_name}:")
            print(f"Fast Wave - Min: {fast_wave.min():.4f}, Max: {fast_wave.max():.4f}, "
                  f"Mean: {fast_wave.mean():.4f}")
            print(f"Slow Wave - Min: {slow_wave.min():.4f}, Max: {slow_wave.max():.4f}, "
                  f"Mean: {slow_wave.mean():.4f}")
            
            # Calculate wave crossovers
            crossovers = np.where(
                (fast_wave[:-1] < slow_wave[:-1]) & (fast_wave[1:] >= slow_wave[1:]) |
                (fast_wave[:-1] > slow_wave[:-1]) & (fast_wave[1:] <= slow_wave[1:])
            )[0]
            
            if len(crossovers) > 0:
                print(f"\nLast 3 Wave Crossovers ({timeframe_name}):")
                for idx in crossovers[-3:]:
                    dt = datetime.fromtimestamp(candles[idx].timestamp, tz=timezone.utc)
                    cross_type = "Bullish" if fast_wave[idx] > slow_wave[idx] else "Bearish"
                    print(f"{dt.strftime('%Y-%m-%d %H:%M')} - {cross_type} crossover "
                          f"(Fast: {fast_wave[idx]:.4f}, Slow: {slow_wave[idx]:.4f})")

if __name__ == "__main__":
    asyncio.run(main())

