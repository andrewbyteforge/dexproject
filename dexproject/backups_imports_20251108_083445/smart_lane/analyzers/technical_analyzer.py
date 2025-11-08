"""
Technical Analysis Analyzer

Medium-priority analyzer that performs multi-timeframe technical chart analysis
using various indicators and pattern recognition. Provides trading signals
and price target calculations.

Path: engine/smart_lane/analyzers/technical_analyzer.py
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import math
import statistics

from . import BaseAnalyzer
from .. import RiskScore, RiskCategory, TechnicalSignal

logger = logging.getLogger(__name__)


@dataclass
class TechnicalIndicator:
    """Individual technical indicator result."""
    name: str  # RSI, MACD, SMA, EMA, etc.
    timeframe: str  # 5m, 30m, 4h, 1d
    value: float
    signal: str  # BUY, SELL, NEUTRAL
    strength: float  # 0-1 scale
    confidence: float
    description: str


@dataclass
class PriceLevel:
    """Support or resistance price level."""
    level_type: str  # SUPPORT, RESISTANCE
    price: float
    strength: float  # 0-1 scale
    test_count: int  # How many times price tested this level
    last_test_date: str
    confidence: float


@dataclass
class ChartPattern:
    """Identified chart pattern."""
    pattern_name: str  # TRIANGLE, WEDGE, HEAD_SHOULDERS, etc.
    pattern_type: str  # CONTINUATION, REVERSAL
    signal: str  # BULLISH, BEARISH, NEUTRAL
    completion_percent: float  # How complete the pattern is
    price_target: Optional[float]
    confidence: float
    timeframe: str


@dataclass
class TechnicalAnalysisResult:
    """Complete technical analysis result."""
    overall_signal: str  # STRONG_BUY, BUY, NEUTRAL, SELL, STRONG_SELL
    signal_strength: float  # 0-1 scale
    trend_direction: str  # UPTREND, DOWNTREND, SIDEWAYS
    trend_strength: float
    volatility_score: float
    momentum_score: float
    support_levels: List[PriceLevel]
    resistance_levels: List[PriceLevel]
    chart_patterns: List[ChartPattern]
    risk_reward_ratio: float
    confidence_level: float


class TechnicalAnalyzer(BaseAnalyzer):
    """
    Advanced technical analysis for token price charts.
    
    Analyzes:
    - Multi-timeframe technical indicators (RSI, MACD, SMA, EMA, etc.)
    - Support and resistance level identification
    - Chart pattern recognition
    - Trend analysis and momentum indicators
    - Volume analysis and price-volume relationships
    - Volatility and risk metrics
    - Price targets and risk/reward calculations
    """
    
    def __init__(self, chain_id: int, config: Optional[Dict[str, Any]] = None):
        """
        Initialize technical analyzer.
        
        Args:
            chain_id: Blockchain chain identifier
            config: Analyzer configuration including timeframes and indicators
        """
        super().__init__(chain_id, config)
        
        # Analysis configuration
        self.timeframes = config.get('timeframes', ['5m', '30m', '4h', '1d']) if config else ['5m', '30m', '4h', '1d']
        self.indicators = config.get('indicators', [
            'RSI', 'MACD', 'SMA_20', 'SMA_50', 'EMA_12', 'EMA_26', 'BB', 'STOCH'
        ]) if config else ['RSI', 'MACD', 'SMA_20', 'SMA_50', 'EMA_12', 'EMA_26', 'BB', 'STOCH']
        
        # Technical thresholds
        self.thresholds = {
            'rsi_oversold': 30,
            'rsi_overbought': 70,
            'trend_strength_min': 0.6,
            'pattern_confidence_min': 0.7,
            'min_price_history_hours': 24,
            'volatility_high_threshold': 0.15,  # 15% daily volatility
            'volume_spike_threshold': 2.0,  # 2x average volume
            'support_resistance_min_tests': 2
        }
        
        # Update with custom config
        if config:
            self.thresholds.update(config.get('thresholds', {}))
        
        # Technical analysis cache
        self.analysis_cache: Dict[str, Tuple[TechnicalAnalysisResult, datetime]] = {}
        self.cache_ttl_minutes = 5  # Short cache for technical data
        
        logger.info(f"Technical analyzer initialized for chain {chain_id} with timeframes: {self.timeframes}")
    
    def get_category(self) -> RiskCategory:
        """Get the risk category this analyzer handles."""
        return RiskCategory.TECHNICAL_ANALYSIS
    

    def _normalize_price_data(self, price_data: Any) -> List[Dict[str, Any]]:
        """Normalize price data to a consistent format."""
        if isinstance(price_data, list):
            return price_data
        elif isinstance(price_data, dict):
            return price_data.get('prices', [])
        else:
            return []

    async def analyze(
        self,
        token_address: str,
        context: Dict[str, Any]
    ) -> RiskScore:
        """
        Perform comprehensive technical analysis.
        
        Args:
            token_address: Token contract address to analyze
            context: Additional context including price data, volume data
            
        Returns:
            RiskScore with technical analysis assessment
        """
        analysis_start = time.time()
        
        try:
            logger.debug(f"Starting technical analysis for {token_address[:10]}...")
            
            # Update performance stats
            self.performance_stats['total_analyses'] += 1
            
            # Input validation
            if not self._validate_inputs(token_address, context):
                return self._create_error_risk_score("Invalid inputs for technical analysis")
            
            # Check cache first
            cached_result = self._get_cached_analysis(token_address)
            if cached_result and not context.get('force_refresh', False):
                self.performance_stats['cache_hits'] += 1
                return self._create_risk_score_from_cache(cached_result)
            
            self.performance_stats['cache_misses'] += 1
            
            # Get price and volume data
            raw_price_data = await self._fetch_price_data(token_address, context)
        price_data = self._normalize_price_data(raw_price_data)
            if not price_data or (isinstance(price_data, dict) and len(price_data.get('prices', [])) < 24) or (isinstance(price_data, list) and len(price_data) < 24):
                return self._create_error_risk_score("Insufficient price data for technical analysis")
            
            # Perform multi-timeframe analysis
            analysis_tasks = [
                self._calculate_technical_indicators(price_data),
                self._identify_support_resistance(price_data),
                self._detect_chart_patterns(price_data),
                self._analyze_trend_momentum(price_data),
                self._analyze_volume_patterns(price_data),
                self._calculate_volatility_metrics(price_data)
            ]
            
            # Execute all tasks with timeout protection
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*analysis_tasks, return_exceptions=True),
                    timeout=15.0  # 15 second timeout for technical analysis
                )
            except asyncio.TimeoutError:
                logger.warning(f"Technical analysis timeout for {token_address[:10]}")
                return self._create_timeout_risk_score()
            
            # Process results
            indicators = results[0] if not isinstance(results[0], Exception) else []
            support_resistance = results[1] if not isinstance(results[1], Exception) else ([], [])
            chart_patterns = results[2] if not isinstance(results[2], Exception) else []
            trend_momentum = results[3] if not isinstance(results[3], Exception) else {}
            volume_analysis = results[4] if not isinstance(results[4], Exception) else {}
            volatility_metrics = results[5] if not isinstance(results[5], Exception) else {}
            
            # Create comprehensive technical analysis
            technical_analysis = self._aggregate_technical_signals(
                indicators, support_resistance, chart_patterns, 
                trend_momentum, volume_analysis, volatility_metrics
            )
            
            # Calculate risk score
            risk_score = self._calculate_technical_risk_score(technical_analysis, volatility_metrics)
            
            # Generate technical signals for Smart Lane pipeline
            technical_signals = self._generate_technical_signals(indicators, technical_analysis)
            
            # Cache the result
            self._cache_analysis_result(token_address, technical_analysis)
            
            # Create detailed analysis data
            analysis_details = {
                'technical_analysis': technical_analysis.__dict__,
                'indicators': [ind.__dict__ for ind in indicators],
                'technical_signals': [sig.__dict__ for sig in technical_signals],
                'volatility_metrics': volatility_metrics,
                'volume_analysis': volume_analysis,
                'price_data_quality': self._assess_price_data_quality(price_data)
            }
            
            # Generate warnings
            warnings = self._generate_technical_warnings(technical_analysis, volatility_metrics)
            
            # Calculate analysis time
            analysis_time_ms = (time.time() - analysis_start) * 1000
            
            # Update performance stats
            self.performance_stats['successful_analyses'] += 1
            
            # Create and return risk score
            return RiskScore(
                category=self.get_category(),
                score=risk_score,
                confidence=technical_analysis.confidence_level,
                details=analysis_details,
                analysis_time_ms=analysis_time_ms,
                warnings=warnings,
                data_quality=self._assess_price_data_quality(price_data),
                last_updated=datetime.now(timezone.utc).isoformat()
            )
            
        except Exception as e:
            logger.error(f"Error in technical analysis: {e}", exc_info=True)
            self.performance_stats['failed_analyses'] += 1
            
            analysis_time_ms = (time.time() - analysis_start) * 1000
            return RiskScore(
                category=self.get_category(),
                score=0.5,  # Neutral risk due to analysis failure
                confidence=0.2,
                details={'error': str(e), 'analysis_failed': True},
                analysis_time_ms=analysis_time_ms,
                warnings=[f"Technical analysis failed: {str(e)}"],
                data_quality="POOR"
            )
    
    async def _fetch_price_data(
        self,
        token_address: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Fetch historical price and volume data.
        
        In production, this would fetch data from DEX APIs, price feeds,
        or blockchain data providers like The Graph.
        """
        await asyncio.sleep(0.1)  # Simulate API call
        
        # Mock price data generation
        current_time = datetime.now(timezone.utc)
        base_price = context.get('current_price', 1.0)
        
        # Generate 7 days of hourly price data
        prices = []
        volumes = []
        
        for i in range(168):  # 7 days * 24 hours
            timestamp = current_time - timedelta(hours=168-i)
            
            # Simulate price movement with trend and volatility
            trend_factor = 1.0 + (i / 1000)  # Slight uptrend
            volatility = 0.02 + (0.01 * math.sin(i / 10))  # Variable volatility
            random_factor = 1.0 + (volatility * math.sin(i * 0.7) * math.cos(i * 0.3))
            
            price = base_price * trend_factor * random_factor
            volume = 10000 + (5000 * math.sin(i / 5)) + (2000 * random_factor)
            
            prices.append({
                'timestamp': timestamp.isoformat(),
                'open': price * 0.999,
                'high': price * 1.002,
                'low': price * 0.998,
                'close': price,
                'volume': max(volume, 100)
            })
        
        return {
            'prices': prices,
            'current_price': base_price,
            'data_quality': 'GOOD',
            'source': 'mock_api'
        }
    
    async def _calculate_technical_indicators(self, price_data: Dict[str, Any]) -> List[TechnicalIndicator]:
        """Calculate various technical indicators across timeframes."""
        indicators = []
        prices = price_data['prices']
        
        if len(prices) < 50:
            return indicators
        
        # Extract close prices for calculations
        close_prices = [float(p['close']) for p in prices[-50:]]  # Last 50 periods
        volumes = [float(p['volume']) for p in prices[-50:]]
        
        try:
            # RSI Calculation
            rsi_value = self._calculate_rsi(close_prices)
            rsi_signal = "SELL" if rsi_value > self.thresholds['rsi_overbought'] else \
                        "BUY" if rsi_value < self.thresholds['rsi_oversold'] else "NEUTRAL"
            
            indicators.append(TechnicalIndicator(
                name="RSI",
                timeframe="4h",
                value=rsi_value,
                signal=rsi_signal,
                strength=abs(rsi_value - 50) / 50,
                confidence=0.8,
                description=f"RSI({rsi_value:.1f}) - {'Overbought' if rsi_value > 70 else 'Oversold' if rsi_value < 30 else 'Neutral'}"
            ))
            
            # MACD Calculation
            macd_line, signal_line = self._calculate_macd(close_prices)
            macd_signal = "BUY" if macd_line > signal_line else "SELL"
            
            indicators.append(TechnicalIndicator(
                name="MACD",
                timeframe="4h",
                value=macd_line - signal_line,
                signal=macd_signal,
                strength=min(abs(macd_line - signal_line) * 100, 1.0),
                confidence=0.75,
                description=f"MACD {'Bullish' if macd_line > signal_line else 'Bearish'} crossover"
            ))
            
            # Moving Averages
            sma_20 = sum(close_prices[-20:]) / 20
            sma_50 = sum(close_prices[-50:]) / 50
            current_price = close_prices[-1]
            
            sma_signal = "BUY" if current_price > sma_20 > sma_50 else \
                        "SELL" if current_price < sma_20 < sma_50 else "NEUTRAL"
            
            indicators.append(TechnicalIndicator(
                name="SMA_Cross",
                timeframe="4h",
                value=(sma_20 - sma_50) / sma_50,
                signal=sma_signal,
                strength=abs(sma_20 - sma_50) / sma_50,
                confidence=0.7,
                description=f"SMA20({'Above' if sma_20 > sma_50 else 'Below'}) SMA50"
            ))
            
            # Bollinger Bands
            bb_middle, bb_upper, bb_lower = self._calculate_bollinger_bands(close_prices)
            bb_position = (current_price - bb_lower) / (bb_upper - bb_lower)
            
            bb_signal = "SELL" if bb_position > 0.8 else "BUY" if bb_position < 0.2 else "NEUTRAL"
            
            indicators.append(TechnicalIndicator(
                name="BOLLINGER_BANDS",
                timeframe="4h",
                value=bb_position,
                signal=bb_signal,
                strength=abs(bb_position - 0.5) * 2,
                confidence=0.65,
                description=f"Price at {bb_position:.1%} of Bollinger Band range"
            ))
            
            # Volume Analysis
            avg_volume = sum(volumes[-20:]) / 20
            current_volume = volumes[-1]
            volume_ratio = current_volume / avg_volume
            
            volume_signal = "BUY" if volume_ratio > 1.5 and close_prices[-1] > close_prices[-5] else \
                           "SELL" if volume_ratio > 1.5 and close_prices[-1] < close_prices[-5] else "NEUTRAL"
            
            indicators.append(TechnicalIndicator(
                name="VOLUME",
                timeframe="4h",
                value=volume_ratio,
                signal=volume_signal,
                strength=min(volume_ratio / 3, 1.0),
                confidence=0.6,
                description=f"Volume {volume_ratio:.1f}x above average"
            ))
            
        except Exception as e:
            logger.warning(f"Error calculating technical indicators: {e}")
        
        return indicators
    
    async def _identify_support_resistance(self, price_data: Dict[str, Any]) -> Tuple[List[PriceLevel], List[PriceLevel]]:
        """Identify key support and resistance levels."""
        prices = price_data['prices']
        support_levels = []
        resistance_levels = []
        
        if len(prices) < 24:
            return support_levels, resistance_levels
        
        try:
            # Extract price data
            highs = [float(p['high']) for p in prices[-100:]]
            lows = [float(p['low']) for p in prices[-100:]]
            closes = [float(p['close']) for p in prices[-100:]]
            
            # Find local peaks and valleys
            resistance_candidates = self._find_local_peaks(highs, window=5)
            support_candidates = self._find_local_valleys(lows, window=5)
            
            # Analyze resistance levels
            for level in resistance_candidates:
                test_count = sum(1 for h in highs if abs(h - level) / level < 0.02)
                if test_count >= self.thresholds['support_resistance_min_tests']:
                    resistance_levels.append(PriceLevel(
                        level_type="RESISTANCE",
                        price=level,
                        strength=min(test_count / 5, 1.0),
                        test_count=test_count,
                        last_test_date=datetime.now(timezone.utc).isoformat(),
                        confidence=0.7
                    ))
            
            # Analyze support levels
            for level in support_candidates:
                test_count = sum(1 for l in lows if abs(l - level) / level < 0.02)
                if test_count >= self.thresholds['support_resistance_min_tests']:
                    support_levels.append(PriceLevel(
                        level_type="SUPPORT",
                        price=level,
                        strength=min(test_count / 5, 1.0),
                        test_count=test_count,
                        last_test_date=datetime.now(timezone.utc).isoformat(),
                        confidence=0.7
                    ))
            
            # Sort by strength
            support_levels.sort(key=lambda x: x.strength, reverse=True)
            resistance_levels.sort(key=lambda x: x.strength, reverse=True)
            
        except Exception as e:
            logger.warning(f"Error identifying support/resistance: {e}")
        
        return support_levels[:5], resistance_levels[:5]  # Return top 5 each
    
    async def _detect_chart_patterns(self, price_data: Dict[str, Any]) -> List[ChartPattern]:
        """Detect common chart patterns."""
        patterns = []
        prices = price_data['prices']
        
        if len(prices) < 20:
            return patterns
        
        try:
            closes = [float(p['close']) for p in prices[-50:]]
            
            # Simple trend pattern detection
            if len(closes) >= 20:
                recent_trend = self._calculate_trend_strength(closes[-20:])
                longer_trend = self._calculate_trend_strength(closes[-50:])
                
                # Detect trend patterns
                if recent_trend > 0.3 and longer_trend > 0.3:
                    patterns.append(ChartPattern(
                        pattern_name="UPTREND",
                        pattern_type="CONTINUATION",
                        signal="BULLISH",
                        completion_percent=0.8,
                        price_target=closes[-1] * 1.1,
                        confidence=0.7,
                        timeframe="4h"
                    ))
                elif recent_trend < -0.3 and longer_trend < -0.3:
                    patterns.append(ChartPattern(
                        pattern_name="DOWNTREND",
                        pattern_type="CONTINUATION",
                        signal="BEARISH",
                        completion_percent=0.8,
                        price_target=closes[-1] * 0.9,
                        confidence=0.7,
                        timeframe="4h"
                    ))
                
                # Detect reversal patterns (simplified)
                if recent_trend > 0.2 and longer_trend < -0.2:
                    patterns.append(ChartPattern(
                        pattern_name="TREND_REVERSAL",
                        pattern_type="REVERSAL",
                        signal="BULLISH",
                        completion_percent=0.6,
                        price_target=closes[-1] * 1.15,
                        confidence=0.6,
                        timeframe="4h"
                    ))
                elif recent_trend < -0.2 and longer_trend > 0.2:
                    patterns.append(ChartPattern(
                        pattern_name="TREND_REVERSAL",
                        pattern_type="REVERSAL",
                        signal="BEARISH",
                        completion_percent=0.6,
                        price_target=closes[-1] * 0.85,
                        confidence=0.6,
                        timeframe="4h"
                    ))
            
        except Exception as e:
            logger.warning(f"Error detecting chart patterns: {e}")
        
        return patterns
    
    async def _analyze_trend_momentum(self, price_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze trend direction and momentum."""
        prices = price_data['prices']
        
        if len(prices) < 10:
            return {}
        
        try:
            closes = [float(p['close']) for p in prices[-50:]]
            
            # Calculate trend strength
            trend_strength = self._calculate_trend_strength(closes)
            
            # Determine trend direction
            if trend_strength > 0.3:
                trend_direction = "UPTREND"
            elif trend_strength < -0.3:
                trend_direction = "DOWNTREND"
            else:
                trend_direction = "SIDEWAYS"
            
            # Calculate momentum
            short_momentum = (closes[-1] - closes[-5]) / closes[-5] if len(closes) >= 5 else 0
            medium_momentum = (closes[-1] - closes[-10]) / closes[-10] if len(closes) >= 10 else 0
            
            momentum_score = (short_momentum + medium_momentum) / 2
            
            return {
                'trend_direction': trend_direction,
                'trend_strength': abs(trend_strength),
                'momentum_score': momentum_score,
                'short_term_momentum': short_momentum,
                'medium_term_momentum': medium_momentum
            }
            
        except Exception as e:
            logger.warning(f"Error analyzing trend momentum: {e}")
            return {}
    
    async def _analyze_volume_patterns(self, price_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze volume patterns and relationships."""
        prices = price_data['prices']
        
        if len(prices) < 10:
            return {}
        
        try:
            volumes = [float(p['volume']) for p in prices[-20:]]
            closes = [float(p['close']) for p in prices[-20:]]
            
            # Volume trend analysis
            avg_volume = sum(volumes) / len(volumes)
            recent_volume = sum(volumes[-5:]) / 5
            volume_trend = (recent_volume - avg_volume) / avg_volume
            
            # Price-volume relationship
            price_changes = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
            volume_changes = [(volumes[i] - volumes[i-1]) / volumes[i-1] for i in range(1, len(volumes))]
            
            # Simple correlation
            correlation = self._calculate_correlation(price_changes, volume_changes)
            
            return {
                'volume_trend': volume_trend,
                'average_volume': avg_volume,
                'current_volume_ratio': volumes[-1] / avg_volume,
                'price_volume_correlation': correlation,
                'volume_spike_detected': volumes[-1] > avg_volume * self.thresholds['volume_spike_threshold']
            }
            
        except Exception as e:
            logger.warning(f"Error analyzing volume patterns: {e}")
            return {}
    
    async def _calculate_volatility_metrics(self, price_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate volatility and risk metrics."""
        prices = price_data['prices']
        
        if len(prices) < 10:
            return {}
        
        try:
            closes = [float(p['close']) for p in prices[-30:]]
            
            # Calculate returns
            returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
            
            # Volatility metrics
            volatility = statistics.stdev(returns) if len(returns) > 1 else 0
            mean_return = statistics.mean(returns) if returns else 0
            
            # Risk metrics
            downside_returns = [r for r in returns if r < 0]
            downside_volatility = statistics.stdev(downside_returns) if len(downside_returns) > 1 else 0
            
            # VaR approximation (95% confidence)
            sorted_returns = sorted(returns)
            var_95 = sorted_returns[int(len(sorted_returns) * 0.05)] if len(sorted_returns) > 20 else 0
            
            return {
                'volatility': volatility,
                'annualized_volatility': volatility * math.sqrt(365 * 24),  # Hourly to annual
                'mean_return': mean_return,
                'downside_volatility': downside_volatility,
                'value_at_risk_95': var_95,
                'volatility_rating': 'HIGH' if volatility > self.thresholds['volatility_high_threshold'] else 
                                   'MEDIUM' if volatility > 0.05 else 'LOW'
            }
            
        except Exception as e:
            logger.warning(f"Error calculating volatility metrics: {e}")
            return {}
    
    def _aggregate_technical_signals(
        self,
        indicators: List[TechnicalIndicator],
        support_resistance: Tuple[List[PriceLevel], List[PriceLevel]],
        chart_patterns: List[ChartPattern],
        trend_momentum: Dict[str, Any],
        volume_analysis: Dict[str, Any],
        volatility_metrics: Dict[str, Any]
    ) -> TechnicalAnalysisResult:
        """Aggregate all technical analysis components."""
        
        support_levels, resistance_levels = support_resistance
        
        # Calculate overall signal
        buy_signals = len([i for i in indicators if i.signal == "BUY"])
        sell_signals = len([i for i in indicators if i.signal == "SELL"])
        total_signals = len(indicators)
        
        if total_signals == 0:
            overall_signal = "NEUTRAL"
            signal_strength = 0.0
        else:
            signal_ratio = (buy_signals - sell_signals) / total_signals
            
            if signal_ratio > 0.6:
                overall_signal = "STRONG_BUY"
            elif signal_ratio > 0.2:
                overall_signal = "BUY"
            elif signal_ratio < -0.6:
                overall_signal = "STRONG_SELL"
            elif signal_ratio < -0.2:
                overall_signal = "SELL"
            else:
                overall_signal = "NEUTRAL"
            
            signal_strength = abs(signal_ratio)
        
        # Extract trend information
        trend_direction = trend_momentum.get('trend_direction', 'SIDEWAYS')
        trend_strength = trend_momentum.get('trend_strength', 0.0)
        momentum_score = trend_momentum.get('momentum_score', 0.0)
        
        # Calculate volatility score
        volatility_score = volatility_metrics.get('volatility', 0.0)
        
        # Calculate risk/reward ratio
        if resistance_levels and support_levels:
            nearest_resistance = min(resistance_levels, key=lambda x: abs(x.price - indicators[0].value) if indicators else 0)
            nearest_support = min(support_levels, key=lambda x: abs(x.price - indicators[0].value) if indicators else 0)
            current_price = indicators[0].value if indicators else 1.0
            
            potential_reward = abs(nearest_resistance.price - current_price) / current_price
            potential_risk = abs(current_price - nearest_support.price) / current_price
            
            risk_reward_ratio = potential_reward / potential_risk if potential_risk > 0 else 0
        else:
            risk_reward_ratio = 1.0
        
        # Calculate confidence level
        indicator_confidence = sum(i.confidence for i in indicators) / len(indicators) if indicators else 0.5
        pattern_confidence = sum(p.confidence for p in chart_patterns) / len(chart_patterns) if chart_patterns else 0.5
        data_quality_factor = 0.8 if len(indicators) >= 3 else 0.5
        
        confidence_level = (indicator_confidence * 0.6 + pattern_confidence * 0.3 + data_quality_factor * 0.1)
        
        return TechnicalAnalysisResult(
            overall_signal=overall_signal,
            signal_strength=signal_strength,
            trend_direction=trend_direction,
            trend_strength=trend_strength,
            volatility_score=volatility_score,
            momentum_score=momentum_score,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
            chart_patterns=chart_patterns,
            risk_reward_ratio=risk_reward_ratio,
            confidence_level=confidence_level
        )
    
    def _calculate_technical_risk_score(
        self,
        technical_analysis: TechnicalAnalysisResult,
        volatility_metrics: Dict[str, Any]
    ) -> float:
        """Calculate overall technical risk score."""
        risk_factors = []
        
        # Signal risk
        if technical_analysis.overall_signal in ["STRONG_SELL", "SELL"]:
            risk_factors.append(0.7)
        elif technical_analysis.overall_signal == "NEUTRAL":
            risk_factors.append(0.4)
        else:
            risk_factors.append(0.2)
        
        # Trend risk
        if technical_analysis.trend_direction == "DOWNTREND":
            risk_factors.append(0.6)
        elif technical_analysis.trend_direction == "SIDEWAYS":
            risk_factors.append(0.4)
        else:
            risk_factors.append(0.2)
        
        # Volatility risk
        volatility_rating = volatility_metrics.get('volatility_rating', 'MEDIUM')
        if volatility_rating == "HIGH":
            risk_factors.append(0.8)
        elif volatility_rating == "MEDIUM":
            risk_factors.append(0.4)
        else:
            risk_factors.append(0.2)
        
        # Risk/reward ratio
        if technical_analysis.risk_reward_ratio < 1.0:
            risk_factors.append(0.6)
        elif technical_analysis.risk_reward_ratio < 2.0:
            risk_factors.append(0.3)
        else:
            risk_factors.append(0.1)
        
        return sum(risk_factors) / len(risk_factors)
    
    def _generate_technical_signals(
        self,
        indicators: List[TechnicalIndicator],
        technical_analysis: TechnicalAnalysisResult
    ) -> List[TechnicalSignal]:
        """Generate technical signals for Smart Lane pipeline."""
        signals = []
        
        for timeframe in self.timeframes:
            timeframe_indicators = [i for i in indicators if i.timeframe == timeframe]
            
            if timeframe_indicators:
                # Aggregate signals for this timeframe
                buy_count = len([i for i in timeframe_indicators if i.signal == "BUY"])
                sell_count = len([i for i in timeframe_indicators if i.signal == "SELL"])
                total_count = len(timeframe_indicators)
                
                if total_count > 0:
                    signal_ratio = (buy_count - sell_count) / total_count
                    
                    if signal_ratio > 0.3:
                        signal = "BUY"
                    elif signal_ratio < -0.3:
                        signal = "SELL"
                    else:
                        signal = "NEUTRAL"
                    
                    strength = abs(signal_ratio)
                    confidence = sum(i.confidence for i in timeframe_indicators) / total_count
                    
                    # Create price targets from support/resistance
                    price_targets = {}
                    if technical_analysis.resistance_levels:
                        price_targets['resistance'] = technical_analysis.resistance_levels[0].price
                    if technical_analysis.support_levels:
                        price_targets['support'] = technical_analysis.support_levels[0].price
                    
                    # Extract indicator values
                    indicator_values = {i.name: i.value for i in timeframe_indicators}
                    
                    signals.append(TechnicalSignal(
                        timeframe=timeframe,
                        signal=signal,
                        strength=strength,
                        indicators=indicator_values,
                        price_targets=price_targets,
                        confidence=confidence
                    ))
        
        return signals
    
    def _generate_technical_warnings(
        self,
        technical_analysis: TechnicalAnalysisResult,
        volatility_metrics: Dict[str, Any]
    ) -> List[str]:
        """Generate warnings based on technical analysis."""
        warnings = []
        
        if technical_analysis.overall_signal in ["STRONG_SELL", "SELL"]:
            warnings.append("Technical indicators show strong bearish signals")
        
        if volatility_metrics.get('volatility_rating') == "HIGH":
            warnings.append("High volatility detected - increased trading risk")
        
        if technical_analysis.confidence_level < 0.5:
            warnings.append("Low confidence in technical analysis due to limited data")
        
        if technical_analysis.risk_reward_ratio < 1.0:
            warnings.append("Poor risk/reward ratio - limited upside potential")
        
        if not technical_analysis.support_levels:
            warnings.append("No clear support levels identified")
        
        return warnings
    
    # Technical calculation helper methods
    def _calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """Calculate Relative Strength Index."""
        if len(prices) < period + 1:
            return 50.0
        
        gains = []
        losses = []
        
        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        
        if len(gains) < period:
            return 50.0
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def _calculate_macd(self, prices: List[float]) -> Tuple[float, float]:
        """Calculate MACD and signal line."""
        if len(prices) < 26:
            return 0.0, 0.0
        
        # Calculate EMAs
        ema_12 = self._calculate_ema(prices, 12)
        ema_26 = self._calculate_ema(prices, 26)
        
        macd_line = ema_12 - ema_26
        
        # Signal line is 9-period EMA of MACD line
        # Simplified calculation for this example
        signal_line = macd_line * 0.9  # Approximation
        
        return macd_line, signal_line
    
    def _calculate_ema(self, prices: List[float], period: int) -> float:
        """Calculate Exponential Moving Average."""
        if len(prices) < period:
            return sum(prices) / len(prices)
        
        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period
        
        for price in prices[period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        
        return ema
    
    def _calculate_bollinger_bands(self, prices: List[float], period: int = 20) -> Tuple[float, float, float]:
        """Calculate Bollinger Bands."""
        if len(prices) < period:
            avg = sum(prices) / len(prices)
            return avg, avg * 1.02, avg * 0.98
        
        recent_prices = prices[-period:]
        middle = sum(recent_prices) / period
        
        variance = sum((p - middle) ** 2 for p in recent_prices) / period
        std_dev = math.sqrt(variance)
        
        upper = middle + (2 * std_dev)
        lower = middle - (2 * std_dev)
        
        return middle, upper, lower
    
    def _find_local_peaks(self, data: List[float], window: int = 3) -> List[float]:
        """Find local peaks in price data."""
        peaks = []
        
        for i in range(window, len(data) - window):
            is_peak = True
            for j in range(i - window, i + window + 1):
                if j != i and data[j] >= data[i]:
                    is_peak = False
                    break
            
            if is_peak:
                peaks.append(data[i])
        
        return peaks
    
    def _find_local_valleys(self, data: List[float], window: int = 3) -> List[float]:
        """Find local valleys in price data."""
        valleys = []
        
        for i in range(window, len(data) - window):
            is_valley = True
            for j in range(i - window, i + window + 1):
                if j != i and data[j] <= data[i]:
                    is_valley = False
                    break
            
            if is_valley:
                valleys.append(data[i])
        
        return valleys
    
    def _calculate_trend_strength(self, prices: List[float]) -> float:
        """Calculate trend strength using linear regression."""
        if len(prices) < 2:
            return 0.0
        
        n = len(prices)
        x = list(range(n))
        
        # Linear regression calculation
        sum_x = sum(x)
        sum_y = sum(prices)
        sum_xy = sum(x[i] * prices[i] for i in range(n))
        sum_x2 = sum(xi ** 2 for xi in x)
        
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2)
        
        # Normalize slope relative to price
        avg_price = sum_y / n
        trend_strength = slope / avg_price if avg_price > 0 else 0
        
        return max(-1.0, min(1.0, trend_strength))
    
    def _calculate_correlation(self, x: List[float], y: List[float]) -> float:
        """Calculate correlation between two data series."""
        if len(x) != len(y) or len(x) < 2:
            return 0.0
        
        n = len(x)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(x[i] * y[i] for i in range(n))
        sum_x2 = sum(xi ** 2 for xi in x)
        sum_y2 = sum(yi ** 2 for yi in y)
        
        numerator = n * sum_xy - sum_x * sum_y
        denominator = math.sqrt((n * sum_x2 - sum_x ** 2) * (n * sum_y2 - sum_y ** 2))
        
        return numerator / denominator if denominator != 0 else 0.0
    
    def _validate_inputs(self, token_address: str, context: Dict[str, Any]) -> bool:
        """Validate inputs for technical analysis."""
        if not token_address or len(token_address) != 42:
            return False
        
        return True
    
    def _create_error_risk_score(self, error_message: str) -> RiskScore:
        """Create error risk score for failed analysis."""
        return RiskScore(
            category=self.get_category(),
            score=0.5,  # Neutral risk when analysis fails
            confidence=0.1,
            details={'error': error_message, 'analysis_failed': True},
            analysis_time_ms=0.0,
            warnings=[error_message],
            data_quality="POOR"
        )
    
    def _create_timeout_risk_score(self) -> RiskScore:
        """Create risk score for timeout scenarios."""
        return RiskScore(
            category=self.get_category(),
            score=0.5,  # Neutral risk on timeout
            confidence=0.1,
            details={'timeout': True, 'analysis_incomplete': True},
            analysis_time_ms=15000.0,
            warnings=["Technical analysis timed out - results may be incomplete"],
            data_quality="POOR"
        )
    
    def _get_cached_analysis(self, token_address: str) -> Optional[TechnicalAnalysisResult]:
        """Get cached technical analysis if available and fresh."""
        if token_address in self.analysis_cache:
            result, timestamp = self.analysis_cache[token_address]
            age = datetime.now(timezone.utc) - timestamp
            
            if age.total_seconds() < (self.cache_ttl_minutes * 60):
                return result
            else:
                del self.analysis_cache[token_address]
        
        return None
    
    def _cache_analysis_result(self, token_address: str, result: TechnicalAnalysisResult) -> None:
        """Cache technical analysis result."""
        self.analysis_cache[token_address] = (result, datetime.now(timezone.utc))
        
        # Clean up old cache entries
        if len(self.analysis_cache) > 20:
            sorted_entries = sorted(
                self.analysis_cache.items(),
                key=lambda x: x[1][1]
            )
            for token, _ in sorted_entries[:5]:
                del self.analysis_cache[token]
    
    def _create_risk_score_from_cache(self, cached_result: TechnicalAnalysisResult) -> RiskScore:
        """Create risk score from cached technical analysis."""
        risk_score = self._calculate_technical_risk_score(cached_result, {})
        
        return RiskScore(
            category=self.get_category(),
            score=risk_score,
            confidence=cached_result.confidence_level,
            details={'technical_analysis': cached_result.__dict__, 'from_cache': True},
            analysis_time_ms=2.0,  # Fast cache retrieval
            warnings=[],
            data_quality="GOOD",
            last_updated=datetime.now(timezone.utc).isoformat()
        )
    
    def _assess_price_data_quality(self, price_data: Dict[str, Any]) -> str:
        """Assess the quality of price data used for analysis."""
        prices = price_data.get('prices', [])
        
        if len(prices) < 24:
            return "POOR"
        elif len(prices) < 48:
            return "FAIR"
        elif len(prices) < 168:  # 1 week
            return "GOOD"
        else:
            return "EXCELLENT"



    async def analyze_timeframe(
        self,
        token_address: str,
        timeframe: str,
        context: Dict[str, Any]
    ) -> Optional[TechnicalSignal]:
        """
        Analyze a specific timeframe.
        
        Args:
            timeframe: Timeframe to analyze (e.g., '5m', '1h')
            context: Market context with price data
            
        Returns:
            Technical signal for the timeframe or None
        """
        try:
            # Get price data for timeframe
            price_data = await self._fetch_price_data(timeframe, context)
            
            if not price_data:
                return None
            
            # Calculate indicators
            indicators = self._calculate_indicators(price_data)
            
            # Determine signal
            signal_type = self._determine_signal(indicators)
            strength = self._calculate_signal_strength(indicators)
            
            # Find price targets
            price_targets = self._find_price_targets(price_data, indicators)
            
            return TechnicalSignal(
                timeframe=timeframe,
                signal=signal_type,
                strength=strength,
                indicators=indicators,
                price_targets=price_targets,
                confidence=strength * 0.8  # Confidence based on signal strength
            )
            
        except Exception as e:
            logger.warning(f"Error analyzing timeframe {timeframe}: {e}")
            return None
    
    async def _fetch_price_data(
        self,
        timeframe: str,
        context: Dict[str, Any]
    ) -> Optional[List[Dict[str, Any]]]:
        """Fetch price data for the timeframe."""
        # Mock implementation - would fetch real data in production
        await asyncio.sleep(0.01)
        
        # Return mock price data
        current_price = context.get('current_price', 1.0)
        return [
            {'open': current_price * 0.98, 'high': current_price * 1.02, 
             'low': current_price * 0.97, 'close': current_price, 'volume': 1000}
            for _ in range(20)
        ]
    
    def _calculate_indicators(
        self,
        price_data: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """Calculate technical indicators."""
        if not price_data:
            return {}
        
        closes = [p['close'] for p in price_data]
        
        # Simple indicators (mock)
        sma = sum(closes) / len(closes) if closes else 0
        current = closes[-1] if closes else 0
        
        return {
            'sma': sma,
            'rsi': 50.0,  # Mock RSI
            'macd': 0.01,  # Mock MACD
            'volume_trend': 1.0,
            'price_vs_sma': (current - sma) / sma if sma else 0
        }
    
    def _determine_signal(self, indicators: Dict[str, float]) -> str:
        """Determine signal from indicators."""
        if not indicators:
            return 'NEUTRAL'
        
        price_vs_sma = indicators.get('price_vs_sma', 0)
        rsi = indicators.get('rsi', 50)
        
        if price_vs_sma > 0.02 and rsi < 70:
            return 'BUY'
        elif price_vs_sma < -0.02 and rsi > 30:
            return 'SELL'
        else:
            return 'NEUTRAL'
    
    def _calculate_signal_strength(self, indicators: Dict[str, float]) -> float:
        """Calculate signal strength."""
        if not indicators:
            return 0.5
        
        # Simple strength calculation
        price_vs_sma = abs(indicators.get('price_vs_sma', 0))
        strength = min(1.0, price_vs_sma * 10)
        
        return max(0.1, min(1.0, strength))
    
    def _find_price_targets(
        self,
        price_data: List[Dict[str, Any]],
        indicators: Dict[str, float]
    ) -> Dict[str, float]:
        """Find support and resistance levels."""
        if not price_data:
            return {}
        
        highs = [p['high'] for p in price_data]
        lows = [p['low'] for p in price_data]
        current = price_data[-1]['close']
        
        return {
            'support': min(lows) if lows else current * 0.95,
            'resistance': max(highs) if highs else current * 1.05,
            'take_profit': current * 1.1,
            'stop_loss': current * 0.95
        }
# Export the analyzer class
__all__ = [
    'TechnicalAnalyzer', 
    'TechnicalIndicator', 
    'PriceLevel', 
    'ChartPattern', 
    'TechnicalAnalysisResult'
]