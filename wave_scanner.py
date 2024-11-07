import logging
import asyncio
import numpy as np
import pandas as pd
from datetime import datetime
import os
from openpyxl import load_workbook
from market_data_fetcher import MultiSessionMarketFetcher
from combined_jttw_pattern import JTTWPattern
from timeframe_converter import TimeframeConverter
from typing import List, Dict, Tuple
from collections import defaultdict
from timing_decorator import timing_decorator, timing_stats
from wave_indicator import WaveIndicator, WaveData

class AsyncWaveScanner:
    def __init__(self):
        self.timeframes = ['Min1','Min5','Min15', 'Min60']
        self.market_data = MultiSessionMarketFetcher(self.timeframes)
        self.bull_detector = JTTWPattern('bull')
        self.bear_detector = JTTWPattern('bear')
        self.converter = TimeframeConverter()
        self.wave_indicator = WaveIndicator()
        self.logger = logging.getLogger(__name__)
        self.min_position_size = 50000
        self.timeframes_minutes = [1, 2, 3, 5, 10, 15, 30, 45, 60, 120, 180]

    @timing_decorator
    async def scan_market(self):
        async with timing_stats.measure_total_time_async():
            async with MultiSessionMarketFetcher(self.timeframes) as fetcher:
                pairs = await fetcher.fetch_perpetual_pairs()
                if not pairs:
                    self.logger.error("No pairs fetched from the exchange")
                    return

                position_limits = await fetcher.fetch_position_limits(pairs)
                eligible_pairs = {
                    symbol: limit_info
                    for symbol, limit_info in position_limits.items()
                    if limit_info.max_position > self.min_position_size
                }

                all_candles = await fetcher.fetch_all_candles(list(eligible_pairs.keys()))
                return await self.analyze_all_symbols(eligible_pairs, all_candles)
            
    async def analyze_all_symbols(self, eligible_pairs: Dict, all_candles: Dict) -> Dict[str, Dict[str, dict]]:
        """
        Analyze wave patterns for each eligible symbol across multiple timeframes.
        """
        all_results = {}
        for symbol, timeframe_data in all_candles.items():
            if symbol not in eligible_pairs:
                continue

            # Pass the entire timeframe_data dictionary for this symbol
            patterns = await self.analyze_symbol(symbol, timeframe_data)
            if any(pattern for pattern in patterns.values()):
                all_results[symbol] = patterns

        return all_results

    async def analyze_symbol(self, symbol: str, timeframe_data: Dict[str, List]) -> Dict[str, dict]:
        results = {}
        
        for minutes in self.timeframes_minutes:
            timeframe_candles = self.converter.get_candles(timeframe_data, minutes)
            timeframe = self.converter.format_timeframe(minutes)
            
            if not timeframe_candles:
                continue

            # Calculate wave indicators for this timeframe
            fast_wave, slow_wave = self.wave_indicator.calculate(timeframe_candles)
            
            # Extract timestamps from candles
            timestamps = np.array([candle.timestamp for candle in timeframe_candles])
            
            # Create WaveData object with timestamps
            wave_data = WaveData(
                timeframe=timeframe,
                fast_wave=fast_wave,
                slow_wave=slow_wave,
                timestamps=timestamps  # Add timestamps here
            )
            
            # Run pattern detection in thread pool
            bull_patterns = await asyncio.to_thread(
                self.bull_detector.detect_patterns, 
                wave_data
            )
            
            bear_patterns = await asyncio.to_thread(
                self.bear_detector.detect_patterns, 
                wave_data
            )

            # Store results if patterns are found
            if bull_patterns["fast_wave"] or bull_patterns["slow_wave"] or \
            bear_patterns["fast_wave"] or bear_patterns["slow_wave"]:
                results[timeframe] = {
                    "bull": bull_patterns,
                    "bear": bear_patterns,
                    "wave_values": {
                        "fast_wave": float(fast_wave[0]) if len(fast_wave) > 0 else 0,
                        "slow_wave": float(slow_wave[0]) if len(slow_wave) > 0 else 0
                    }
                }

        return results

    def format_patterns_by_symbol(self, all_results: Dict[str, Dict[str, dict]], position_limits: Dict) -> str:
        formatted_output = []

        for symbol, timeframe_results in sorted(all_results.items()):
            limit_info = position_limits.get(symbol)
            if not limit_info:
                continue

            # Add symbol header with position information
            formatted_output.append(
                f"\n{symbol}: (last price: {limit_info.last_price:.2f} / "
                f"max position: {limit_info.max_position:.2f} / "
                f"max leverage: {limit_info.max_leverage})"
            )

            for timeframe, patterns in sorted(timeframe_results.items()):
                pattern_list = []
                wave_values = patterns["wave_values"]
                
                # Check and format bull patterns
                if patterns["bull"]["fast_wave"]:
                    pattern_list.append("Bull Fast Wave")
                if patterns["bull"]["slow_wave"]:
                    pattern_list.append("Bull Slow Wave")
                    
                # Check and format bear patterns
                if patterns["bear"]["fast_wave"]:
                    pattern_list.append("Bear Fast Wave")
                if patterns["bear"]["slow_wave"]:
                    pattern_list.append("Bear Slow Wave")

                if pattern_list:
                    # Format current wave values
                    formatted_output.append(
                        f"    {timeframe}: {', '.join(pattern_list)}\n"
                        f"    Current Wave Values - Fast: {wave_values['fast_wave']:.4f}, "
                        f"Slow: {wave_values['slow_wave']:.4f}"
                    )
                    
                    # Add pattern points information
                    for pattern_type in ["bull", "bear"]:
                        for wave_type in ["fast_wave", "slow_wave"]:
                            if patterns[pattern_type][wave_type]:
                                pattern_points = patterns[pattern_type][wave_type].get("pattern_points")
                                if pattern_points:
                                    formatted_output.append(f"\n    {pattern_type.title()} {wave_type.replace('_', ' ').title()} Pattern Points:")
                                    formatted_output.append(pattern_points)

            # Add a separator between symbols
            formatted_output.append("-" * 80)

        return "\n".join(formatted_output)



if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    scanner = AsyncWaveScanner()
    asyncio.run(scanner.scan_market())