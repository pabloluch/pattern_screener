import numpy as np
from scipy.signal import find_peaks
import logging
from typing import List, Optional, Tuple, Dict, Literal
from datetime import datetime, timezone
from wave_indicator import WaveIndicator, WaveData

class JTTWPattern:
    def __init__(self, pattern_type: Literal['bull', 'bear']):
        self.logger = logging.getLogger(__name__)
        self.indicator = WaveIndicator()
        self.pattern_type = pattern_type
        self.timestamps = None
        
        # Set pattern-specific configurations
        if pattern_type == 'bull':
            self.wave_ranges = {
                'H1': (40, 100),   # H1 must be between 40 and 100
                'H2': (10, 100),    # H2 must be between 10 and 70
                'H3': (40, 100),   # H3 must be between 40 and 100
                'L1': (-10, 60),     # L1 must be between 0 and 60
                'L2': (-10, 60)      # L2 must be between 0 and 60
            }
            self.point_differences = {
                'H1_H2': 5,    # H2 must be 5 points lower than H1
                'H3_H2': 5,    # H2 must be 5 points lower than H3
                'H2_L1': 5,    # L1 must be 5 points lower than H2
                'H2_L2': 5     # L2 must be 5 points lower than H2
            }
        else:  # bear pattern
            self.wave_ranges = {
                'L1': (-100, -40), # L1 must be between -100 and -40
                'L2': (-100, -10),  # L2 must be between -70 and -10
                'L3': (-100, -40), # L3 must be between -100 and -40
                'H1': (-60, 10),    # H1 must be between -60 and 0
                'H2': (-60, 10)     # H2 must be between -60 and 0
            }
            self.point_differences = {
                'L1_L2': 5,    # L2 must be 5 points higher than L1
                'L3_L2': 5,    # L2 must be 5 points higher than L3
                'L2_H1': 5,    # H1 must be 5 points higher than L2
                'L2_H2': 5     # H2 must be 5 points higher than L2
            }

    def find_significant_peaks_and_troughs(self, 
                                         values: np.ndarray, 
                                         prominence: float = 10) -> Tuple[np.ndarray, np.ndarray]:
        """Find significant peaks and troughs in the indicator values"""
        peaks, _ = find_peaks(values, prominence=prominence)
        troughs, _ = find_peaks(-values, prominence=prominence)
        return peaks, troughs

    def find_initial_point(self, values: np.ndarray, ref_idx: int) -> Optional[Tuple[int, float]]:
        """Find the initial point before the first primary point (in oldest-to-newest order)"""
        if ref_idx >= len(values) - 1:
            return None
            
        # Look at data older than the first primary point
        initial_range = values[ref_idx:]
        if len(initial_range) == 0:
            return None
            
        # For bull pattern, find lowest point; for bear pattern, find highest point
        initial_idx = ref_idx + (np.argmin(initial_range) if self.pattern_type == 'bull' else np.argmax(initial_range))
        initial_value = values[initial_idx]
        
        return (initial_idx, initial_value)

    def initial_point_condition(self, initial_point: Tuple[int, float]) -> bool:
        """Check if the initial point meets the pattern-specific condition"""
        if not initial_point:
            return False
            
        _, initial_value = initial_point
        return initial_value < 0 if self.pattern_type == 'bull' else initial_value > 0

    def is_within_range(self, value: float, point_type: str) -> bool:
        """Check if a value is within the specified range for a given point type"""
        if point_type not in self.wave_ranges:
            return False
        min_val, max_val = self.wave_ranges[point_type]
        return min_val <= value <= max_val

    def find_extremes(self, values: np.ndarray, extremes: np.ndarray) -> Optional[Dict]:
        """Find the pattern-specific extreme points from oldest to newest"""
        if len(extremes) < 3:
            return None
            
        # Convert to oldest-first order for analysis
        extremes = extremes[::-1]  # Reverse to get oldest-first
        extreme_points = {}
        
        # Define points in oldest-to-newest order
        if self.pattern_type == 'bull':
            primary_points = ['H1', 'H2', 'H3']  # Oldest to newest
        else:
            primary_points = ['L1', 'L2', 'L3']  # Oldest to newest
        
        # Find three extreme points in oldest-to-newest sequence
        last_idx = len(values)  # Start from the end (oldest)
        for i, point_type in enumerate(primary_points):
            # Look for points that are older than the last found point
            candidates = [(idx, values[idx]) for idx in extremes 
                         if (i == 0 or idx < last_idx)  # Points must be older than previous point
                         and self.is_within_range(values[idx], point_type)]
            
            if not candidates:
                return None
                
            # Take the most recent valid point before the last point
            extreme_points[point_type] = max(candidates, key=lambda x: x[0])
            last_idx = extreme_points[point_type][0]
        
        return extreme_points

    def find_secondary_points(self, values: np.ndarray, other_extremes: np.ndarray, 
                            primary_points: Dict) -> Optional[Dict]:
        """Find the secondary points between primary extreme points in oldest-to-newest order"""
        if not primary_points:
            return None
            
        if self.pattern_type == 'bull':
            h1_idx = primary_points['H1'][0]
            h2_idx = primary_points['H2'][0]
            
            # Find L1 between H1 and H2 (looking at older data)
            l1_range = values[h2_idx:h1_idx] if h2_idx < h1_idx else values[h1_idx:h2_idx]
            # Find L2 between H2 and H3
            l2_range = values[primary_points['H3'][0]:h2_idx] if primary_points['H3'][0] < h2_idx else values[h2_idx:primary_points['H3'][0]]
            
            if len(l1_range) == 0 or len(l2_range) == 0:
                return None
                
            l1_idx = h2_idx + np.argmin(l1_range) if h2_idx < h1_idx else h1_idx + np.argmin(l1_range)
            l2_idx = primary_points['H3'][0] + np.argmin(l2_range) if primary_points['H3'][0] < h2_idx else h2_idx + np.argmin(l2_range)
            
            secondary_points = {
                'L1': (l1_idx, values[l1_idx]),
                'L2': (l2_idx, values[l2_idx])
            }
            
        else:  # bear pattern
            l1_idx = primary_points['L1'][0]
            l2_idx = primary_points['L2'][0]
            
            # Find H1 between L1 and L2 (looking at older data)
            h1_range = values[l2_idx:l1_idx] if l2_idx < l1_idx else values[l1_idx:l2_idx]
            # Find H2 between L2 and L3
            h2_range = values[primary_points['L3'][0]:l2_idx] if primary_points['L3'][0] < l2_idx else values[l2_idx:primary_points['L3'][0]]
            
            if len(h1_range) == 0 or len(h2_range) == 0:
                return None
                
            h1_idx = l2_idx + np.argmax(h1_range) if l2_idx < l1_idx else l1_idx + np.argmax(h1_range)
            h2_idx = primary_points['L3'][0] + np.argmax(h2_range) if primary_points['L3'][0] < l2_idx else l2_idx + np.argmax(h2_range)
            
            secondary_points = {
                'H1': (h1_idx, values[h1_idx]),
                'H2': (h2_idx, values[h2_idx])
            }
        
        # Validate ranges for secondary points
        for point_type, point_data in secondary_points.items():
            if not self.is_within_range(point_data[1], point_type):
                return None
                
        return secondary_points

    def validate_pattern_conditions(self, primary_points: Dict, 
                                secondary_points: Dict) -> bool:
        """Validate relationships between pattern points"""
        if not primary_points or not secondary_points:
            return False
            
        if self.pattern_type == 'bull':
            # Get point values
            _, h1_value = primary_points['H1']
            _, h2_value = primary_points['H2']
            _, h3_value = primary_points['H3']
            _, l1_value = secondary_points['L1']
            _, l2_value = secondary_points['L2']
            
            # Check all required differences
            return (
                h1_value - h2_value >= self.point_differences['H1_H2'] and  # H2 lower than H1
                h3_value - h2_value >= self.point_differences['H3_H2'] and  # H2 lower than H3
                h2_value - l1_value >= self.point_differences['H2_L1'] and  # L1 lower than H2
                h2_value - l2_value >= self.point_differences['H2_L2']      # L2 lower than H2
            )
        else:  # bear pattern
            # Get point values
            _, l1_value = primary_points['L1']
            _, l2_value = primary_points['L2']
            _, l3_value = primary_points['L3']
            _, h1_value = secondary_points['H1']
            _, h2_value = secondary_points['H2']
            
            # Check all required differences
            return (
                l2_value - l1_value >= self.point_differences['L1_L2'] and  # L2 higher than L1
                l2_value - l3_value >= self.point_differences['L3_L2'] and  # L2 higher than L3
                h1_value - l2_value >= self.point_differences['L2_H1'] and  # H1 higher than L2
                h2_value - l2_value >= self.point_differences['L2_H2']      # H2 higher than L2
            )

    def detect_patterns(self, wave_data: WaveData) -> Dict[str, Optional[dict]]:
        """
        Detect patterns in both Fast and Slow Wave indicators
        
        Args:
            wave_data: WaveData object containing fast_wave and slow_wave arrays
        
        Returns:
            Dictionary containing pattern detection results for both wave types
        """
        if wave_data.fast_wave.size == 0 or wave_data.slow_wave.size == 0:
            return {"fast_wave": None, "slow_wave": None}
        
        # Extract timestamps from candles if available
        self.timestamps = wave_data.timestamps if hasattr(wave_data, 'timestamps') else None
        
        # Check patterns for both wave types
        fast_pattern = self._check_wave_pattern(wave_data.fast_wave)
        slow_pattern = self._check_wave_pattern(wave_data.slow_wave)
        
        # Return results with wave type information and formatted points
        return {
            "fast_wave": {
                "wave_type": "Fast Wave",
                "pattern": fast_pattern,
                "timeframe": wave_data.timeframe,
                "pattern_points": self.format_pattern_points(fast_pattern, "Fast Wave", wave_data.timeframe) if fast_pattern else None
            } if fast_pattern else None,
            
            "slow_wave": {
                "wave_type": "Slow Wave",
                "pattern": slow_pattern,
                "timeframe": wave_data.timeframe,
                "pattern_points": self.format_pattern_points(slow_pattern, "Slow Wave", wave_data.timeframe) if slow_pattern else None
            } if slow_pattern else None
        }

    def _check_wave_pattern(self, wave_values: np.ndarray) -> Optional[dict]:
        """Check wave pattern for a specific wave type"""
        peaks, troughs = self.find_significant_peaks_and_troughs(wave_values)
        
        # Find primary extreme points based on pattern type
        extremes = peaks if self.pattern_type == 'bull' else troughs
        other_extremes = troughs if self.pattern_type == 'bull' else peaks
        
        primary_points = self.find_extremes(wave_values, extremes)
        if not primary_points:
            return None
            
        # Find and validate initial point
        ref_point = 'H1' if self.pattern_type == 'bull' else 'L1'
        initial_point = self.find_initial_point(wave_values, primary_points[ref_point][0])
        if not initial_point or not self.initial_point_condition(initial_point):
            return None
            
        # Find and validate secondary points
        secondary_points = self.find_secondary_points(wave_values, other_extremes, primary_points)
        if not secondary_points:
            return None
            
        if not self.validate_pattern_conditions(primary_points, secondary_points):
            return None
            
        # Combine all points
        pattern = {
            'Initial': initial_point,
            **primary_points,
            **secondary_points
        }
        
        return pattern

    def print_pattern_details(self, pattern_results: Dict[str, dict], symbol: str, price: str):
        """
        Print detailed information about the detected patterns
        
        Args:
            pattern_results: Dictionary containing pattern results for both wave types
            symbol: Trading pair symbol
            price: Current price
        """
        for wave_key, result in pattern_results.items():
            if result and result.get("pattern"):
                wave_type = result["wave_type"]
                timeframe = result.get("timeframe", "Unknown")
                pattern_name = "Bull" if self.pattern_type == 'bull' else "Bear"
                print(f"{pattern_name} pattern found in {symbol} ({wave_type} - {timeframe})")
                print(f"Current price: {price}")
                print("-" * 50)

    def format_pattern_points(self, pattern: dict, wave_type: str, timeframe: str) -> str:
        """Format pattern points with their timestamps and values"""
        if not pattern:
            return ""
            
        formatted_output = []
        points_order = ['Initial']
        
        if self.pattern_type == 'bull':
            points_order.extend(['H1', 'L1', 'H2', 'L2', 'H3'])
        else:  # bear pattern
            points_order.extend(['L1', 'H1', 'L2', 'H2', 'L3'])
        
        for point in points_order:
            if point in pattern:
                idx, value = pattern[point]
                # Use actual timestamp if available, otherwise calculate from index
                if self.timestamps is not None and idx < len(self.timestamps):
                    timestamp = datetime.fromtimestamp(self.timestamps[idx], tz=timezone.utc)
                else:
                    # Fallback to index-based timestamp (should not happen with proper data)
                    timestamp = datetime.fromtimestamp(0)  # Unix epoch as fallback
                formatted_output.append(f"    {point}: {timestamp.strftime('%Y-%m-%d %H:%M')} UTC - Value: {value:.4f}")
        
        return "\n".join(formatted_output)

# Example usage:
async def main():
    from market_data_fetcher import AsyncMarketDataFetcher
    
    async with AsyncMarketDataFetcher() as fetcher:
        # Get wave data
        wave_indicator = WaveIndicator()
        candles = await fetcher.fetch_single_candles("BTC_USDT", "Min5")
        fast_wave, slow_wave = wave_indicator.calculate(candles)
        
        wave_data = WaveData(
            timeframe="Min5",
            fast_wave=fast_wave,
            slow_wave=slow_wave
        )
        
        # Check for both pattern types
        for pattern_type in ['bull', 'bear']:
            pattern_detector = JTTWPattern(pattern_type)
            patterns = pattern_detector.detect_patterns(wave_data)
            
            # Print results
            for wave_type, result in patterns.items():
                if result:
                    print(f"Found {pattern_type} {wave_type} pattern in {result['timeframe']}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())