import logging
import asyncio
import numpy as np
import pandas as pd
from datetime import datetime
from market_data_fetcher import MultiSessionMarketFetcher
from combined_jttw_pattern import JTTWPattern
from timeframe_converter import TimeframeConverter
from typing import List, Dict, Any, Optional
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
    async def scan_market(self) -> Dict[str, Any]:
        """Main method to scan the market for patterns with detailed logging"""
        try:
            async with timing_stats.measure_total_time_async():
                self.logger.info("=== Starting Market Scan ===")
                
                async with MultiSessionMarketFetcher(self.timeframes) as fetcher:
                    # Step 1: Fetch pairs
                    self.logger.info("Step 1/4: Fetching perpetual pairs...")
                    pairs = await fetcher.fetch_perpetual_pairs()
                    self.logger.info(f"Found {len(pairs)} total pairs")
                    
                    if not pairs:
                        self.logger.error("No pairs fetched from exchange")
                        return {
                            "status": "error",
                            "message": "No pairs fetched from the exchange",
                            "data": None
                        }

                    # Step 2: Get position limits
                    self.logger.info("Step 2/4: Fetching position limits...")
                    position_limits = await fetcher.fetch_position_limits(pairs)
                    eligible_pairs = {
                        symbol: limit_info
                        for symbol, limit_info in position_limits.items()
                        if limit_info.max_position > self.min_position_size
                    }
                    self.logger.info(f"Found {len(eligible_pairs)} eligible pairs")

                    if not eligible_pairs:
                        self.logger.error("No eligible pairs found")
                        return {
                            "status": "error",
                            "message": "No eligible pairs found",
                            "data": None
                        }

                    # Step 3: Fetch candles
                    self.logger.info("Step 3/4: Fetching candle data...")
                    symbols = list(eligible_pairs.keys())[:5]  # Limit to 5 pairs for testing
                    self.logger.info(f"Processing pairs: {symbols}")
                    
                    all_candles = await fetcher.fetch_all_candles(symbols)
                    self.logger.info(f"Fetched candle data for {len(all_candles)} pairs")
                    
                    # Step 4: Analysis
                    self.logger.info("Step 4/4: Analyzing patterns...")
                    all_results = {}
                    
                    for symbol, timeframe_data in all_candles.items():
                        self.logger.info(f"Analyzing {symbol}...")
                        try:
                            patterns = await self.analyze_symbol(symbol, timeframe_data)
                            if any(pattern for pattern in patterns.values()):
                                all_results[symbol] = patterns
                                self.logger.info(f"Found patterns for {symbol}")
                        except Exception as e:
                            self.logger.error(f"Error analyzing {symbol}: {str(e)}")
                    
                    self.logger.info(f"Analysis complete. Found patterns in {len(all_results)} pairs")

                    # Generate response
                    self.logger.info("Generating response...")
                    response_data = self._generate_response(all_results, position_limits)
                    
                    self.logger.info("=== Market Scan Complete ===")
                    return {
                        "status": "success",
                        "message": "Market scan completed successfully",
                        "data": response_data
                    }

        except asyncio.TimeoutError:
            self.logger.error("Market scan timed out")
            raise
        except Exception as e:
            self.logger.error(f"Error in market scan: {str(e)}")
            raise

    def _monitor_candles(self, eligible_pairs: Dict, all_candles: Dict) -> None:
        """Monitor candle reception for all eligible pairs"""
        for symbol in eligible_pairs.keys():
            timeframe_data = all_candles.get(symbol, {})
            for timeframe in self.timeframes:
                candles = timeframe_data.get(timeframe, [])
                timing_stats.monitor_candles(symbol, timeframe, len(candles))

    async def analyze_all_symbols(self, eligible_pairs: Dict, all_candles: Dict) -> Dict[str, Dict[str, dict]]:
        """Analyze wave patterns for each eligible symbol"""
        all_results = {}
        
        for symbol, timeframe_data in all_candles.items():
            if symbol not in eligible_pairs:
                continue

            patterns = await self.analyze_symbol(symbol, timeframe_data)
            if any(pattern for pattern in patterns.values()):
                all_results[symbol] = patterns

        return all_results

    async def analyze_symbol(self, symbol: str, timeframe_data: Dict[str, List]) -> Dict[str, dict]:
        """Analyze patterns for a specific symbol with logging"""
        results = {}
        self.logger.info(f"  Analyzing timeframes for {symbol}...")
        
        for minutes in self.timeframes_minutes:
            try:
                timeframe_candles = self.converter.get_candles(timeframe_data, minutes)
                timeframe = self.converter.format_timeframe(minutes)
                
                if not timeframe_candles:
                    self.logger.warning(f"  No candles for {symbol} {timeframe}")
                    continue

                # Calculate wave indicators
                fast_wave, slow_wave, timestamps = self.wave_indicator.calculate(timeframe_candles)
                
                if len(fast_wave) == 0 or len(slow_wave) == 0:
                    self.logger.warning(f"  No wave data for {symbol} {timeframe}")
                    continue
                
                wave_data = WaveData(
                    timeframe=timeframe,
                    fast_wave=fast_wave,
                    slow_wave=slow_wave,
                    timestamps=timestamps
                )
                
                # Detect patterns
                bull_patterns = await asyncio.to_thread(self.bull_detector.detect_patterns, wave_data)
                bear_patterns = await asyncio.to_thread(self.bear_detector.detect_patterns, wave_data)

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
                    self.logger.info(f"  Found patterns for {symbol} {timeframe}")
            except Exception as e:
                self.logger.error(f"  Error analyzing {symbol} {timeframe}: {str(e)}")

        return results

    def _generate_response(self, all_results: Dict, position_limits: Dict) -> Dict[str, Any]:
        """Generate structured response data"""
        return {
            "summary": self._create_summary_data(all_results, position_limits),
            "detailed_results": self._format_detailed_results(all_results, position_limits),
            "statistics": self._generate_statistics(all_results),
            "performance_metrics": self._get_performance_metrics()
        }

    def _create_summary_data(self, all_results: Dict, position_limits: Dict) -> List[Dict]:
        """Create summary data from results"""
        df = self.create_results_dataframe(all_results, position_limits)
        return df.to_dict(orient='records')

    def create_results_dataframe(self, all_results: Dict, position_limits: Dict) -> pd.DataFrame:
        """Create a DataFrame from the scanning results"""
        timeframe_columns = [
            f'{minutes}h' if minutes >= 60 else f'{minutes}m'
            for minutes in self.timeframes_minutes
        ]
        
        data = []
        for symbol, timeframe_results in sorted(all_results.items()):
            limit_info = position_limits.get(symbol)
            if not limit_info:
                continue
                
            row = {
                'Pair': symbol,
                'Max position': limit_info.max_position,
                'Max leverage': limit_info.max_leverage
            }
            
            for col in timeframe_columns:
                row[col] = '-'
            
            patterns_found = False
            for timeframe, patterns in timeframe_results.items():
                tf_minutes = int(timeframe.replace('Min', '')) if timeframe.startswith('Min') else \
                            int(timeframe.replace('Hour', '')) * 60
                
                col_name = f'{tf_minutes//60}h' if tf_minutes >= 60 else f'{tf_minutes}m'
                
                # Determine pattern indicators
                bull_pattern = self._get_pattern_indicator(patterns["bull"])
                bear_pattern = self._get_pattern_indicator(patterns["bear"])
                
                if bull_pattern or bear_pattern:
                    row[col_name] = f'{bull_pattern}/{bear_pattern}' if bull_pattern and bear_pattern else \
                                  bull_pattern or bear_pattern
                    patterns_found = True
            
            if patterns_found:
                data.append(row)
        
        df = pd.DataFrame(data)
        columns = ['Pair'] + timeframe_columns + ['Max position', 'Max leverage']
        return df[columns].sort_values('Max position', ascending=False)

    def _get_pattern_indicator(self, patterns: Dict) -> str:
        """Get pattern indicator string"""
        if patterns["fast_wave"] and patterns["slow_wave"]:
            return '\u2191\u2191' if isinstance(patterns, dict) and patterns.get("bull") else '\u2193\u2193'
        elif patterns["fast_wave"] or patterns["slow_wave"]:
            return '\u2191' if isinstance(patterns, dict) and patterns.get("bull") else '\u2193'
        return ''

    def _format_detailed_results(self, all_results: Dict, position_limits: Dict) -> Dict:
        """Format detailed pattern results"""
        detailed_results = {}
        
        for symbol, timeframe_results in all_results.items():
            limit_info = position_limits.get(symbol)
            if not limit_info:
                continue

            detailed_results[symbol] = {
                "position_info": {
                    "last_price": limit_info.last_price,
                    "max_position": limit_info.max_position,
                    "max_leverage": limit_info.max_leverage
                },
                "patterns": {
                    timeframe: {
                        "wave_values": patterns["wave_values"],
                        "bull_patterns": self._format_pattern_data(patterns["bull"]),
                        "bear_patterns": self._format_pattern_data(patterns["bear"])
                    }
                    for timeframe, patterns in timeframe_results.items()
                }
            }

        return detailed_results

    def _format_pattern_data(self, pattern: Dict) -> Dict:
        """Format pattern data"""
        return {
            "fast_wave": bool(pattern["fast_wave"]),
            "slow_wave": bool(pattern["slow_wave"]),
            "pattern_points": pattern.get("pattern_points", {})
        }

    def _generate_statistics(self, all_results: Dict) -> Dict:
        """Generate statistical summary"""
        stats = {
            "total_pairs_analyzed": len(all_results),
            "patterns_by_timeframe": defaultdict(lambda: {
                "bull": {"fast_wave": 0, "slow_wave": 0},
                "bear": {"fast_wave": 0, "slow_wave": 0}
            }),
            "total_patterns": {
                "bull": {"fast_wave": 0, "slow_wave": 0},
                "bear": {"fast_wave": 0, "slow_wave": 0}
            }
        }

        for timeframe_results in all_results.values():
            for timeframe, patterns in timeframe_results.items():
                for pattern_type in ["bull", "bear"]:
                    for wave_type in ["fast_wave", "slow_wave"]:
                        if patterns[pattern_type][wave_type]:
                            stats["patterns_by_timeframe"][timeframe][pattern_type][wave_type] += 1
                            stats["total_patterns"][pattern_type][wave_type] += 1

        return stats

    def _get_performance_metrics(self) -> Dict:
        """Get performance metrics from timing stats"""
        return {
            "timing_statistics": timing_stats.get_summary(),
            "candle_statistics": timing_stats.get_candle_summary()
        }