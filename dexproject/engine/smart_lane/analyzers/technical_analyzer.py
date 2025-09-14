"""
Technical Analysis Analyzer

Medium-priority analyzer that evaluates token price action, technical
indicators, and chart patterns across multiple timeframes. Provides
technical trading signals and trend analysis.

Path: engine/smart_lane/analyzers/technical_analyzer.py
"""

import asyncio
import logging
import time
import math
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from . import BaseAnalyzer
from .. import RiskScore, RiskCategory, TechnicalSignal

logger = logging.getLogger(__name__)


@dataclass
class TechnicalIndicator:
    """Individual technical indicator result."""
    name: str
    timeframe: str
    value: float
    signal: str  # BUY, SELL, NEUTRAL
    strength: float  # 0-1 scale
    confidence: float
    description: str


@dataclass
class SupportResistance:
    """Support and resistance level."""
    level_type: str  # SUPPORT, RESISTANCE
    price: float
    strength: float  # 0-1 scale
    touches: int
    timeframe: str
    confidence: float


@dataclass
class ChartPattern:
    """Chart pattern identification."""
    pattern_name: str
    timeframe: str
    confidence: float
    signal: str  # BULLISH, BEARISH, NEUTRAL
    target_price: Optional[float]
    stop_loss: Optional[float]
    completion_percentage: float


class TechnicalAnalyzer(BaseAnalyzer):
    """
    Advanced multi-timeframe technical analysis for tokens.
    
    Analyzes:
    - Price action and trend direction across timeframes
    - Technical indicators (RSI, MACD, Moving Averages, etc.)
    - Support and resistance levels
    - Chart patterns and formations
    - Volume analysis and momentum
    - Fibonacci retracements and extensions
    """
    
    def __init__(self, chain_id: int, config: Optional[Dict[str, Any]] = None):
        """
        Initialize technical analyzer.
        
        Args:
            chain_id: Blockchain chain identifier
            config: Analyzer configuration
        """
        super().__init__(chain_id, config)
        
        # Technical analysis parameters
        self.timeframes = ['5m', '15m', '1h', '4h', '1d']
        self.indicators = ['RSI', 'MACD', 'SMA', 'EMA', 'BB', 'STOCH']
        
        # Analysis thresholds
        self.thresholds = {
            'rsi_oversold': 30,
            'rsi_overbought': 70,
            'trend_strength_min': 0.6,
            'pattern_confidence_min': 0.7,
            'volume_spike_threshold': 2.0,  # 2x average volume
            'momentum_threshold': 0.15      # 15% price change
        }
        
        # Update with custom config
        if config:
            self.thresholds.update(config.get('thresholds', {}))
        
        # Technical analysis cache
        self.technical_cache: Dict[str, Tuple[Dict[str, Any], datetime]] = {}
        self.cache_ttl_minutes = 5  # Technical data changes frequently
        
        logger.info(f"Technical analyzer initialized for chain {chain_id}")
    
    def get_category(self) -> RiskCategory:
        """Get the risk category this analyzer handles."""
        return RiskCategory.TECHNICAL_ANALYSIS
    
    async def analyze(
        self,
        token_address: str,
        context: Dict[str, Any]
    ) -> RiskScore:
        """
        Perform comprehensive technical analysis.
        
        Args:
            token_address: Token contract address to analyze
            context: Additional context including price data
            
        Returns:
            RiskScore with technical analysis assessment
        """
        analysis_start = time.time()
        
        try:
            logger.debug(f"Starting technical analysis for {token_address[:10]}...")
            
            # Input validation
            if not self._validate_inputs(token_address, context):
                return self._create_error_risk_score("Invalid inputs for technical analysis")
            
            # Check cache first
            cached_result = self._get_cached_analysis(token_address)
            if cached_result and not context.get('force_refresh', False):
                self.performance_stats['cache_hits'] += 1
                return self._create_risk_score_from_cache(cached_result)
            
            self.performance_stats['cache_misses'] += 1
            
            # Parallel technical analysis tasks
            analysis_tasks = [
                self._analyze_price_action(token_address, context),
                self._calculate_technical_indicators(token_address, context),
                self._identify_support_resistance(token_address, context),
                self._analyze_volume_patterns(token_address, context),
                self._detect_chart_patterns(token_address, context),
                self._analyze_momentum_oscillators(token_address, context)
            ]
            
            analysis_results = await asyncio.gather(*analysis_tasks, return_exceptions=True)
            
            # Process results and handle exceptions
            price_action = self._safe_extract_result(analysis_results[0], {})
            technical_indicators = self._safe_extract_result(analysis_results[1], [])
            support_resistance = self._safe_extract_result(analysis_results[2], [])
            volume_analysis = self._safe_extract_result(analysis_results[3], {})
            chart_patterns = self._safe_extract_result(analysis_results[4], [])
            momentum_analysis = self._safe_extract_result(analysis_results[5], {})
            
            # Generate comprehensive technical signals
            technical_signals = self._generate_technical_signals(
                price_action, technical_indicators, support_resistance,
                volume_analysis, chart_patterns, momentum_analysis
            )
            
            # Calculate technical risk score (inverted - good technicals = low risk)
            risk_score, confidence = self._calculate_technical_risk(
                technical_signals, price_action, volume_analysis
            )
            
            # Generate technical warnings
            warnings = self._generate_technical_warnings(
                technical_signals, price_action, volume_analysis
            )
            
            # Compile detailed analysis
            analysis_details = self._compile_technical_details(
                price_action, technical_indicators, support_resistance,
                volume_analysis, chart_patterns, momentum_analysis,
                technical_signals
            )
            
            analysis_time_ms = (time.time() - analysis_start) * 1000
            
            # Cache the results
            self._cache_analysis_result(token_address, {
                'risk_score': risk_score,
                'confidence': confidence,
                'details': analysis_details,
                'warnings': warnings,
                'technical_signals': technical_signals
            })
            
            # Update performance stats
            self._update_performance_stats(analysis_time_ms, success=True)
            
            logger.debug(
                f"Technical analysis completed for {token_address[:10]}... "
                f"Risk: {risk_score:.3f}, Confidence: {confidence:.3f} "
                f"({len(technical_signals)} signals, {analysis_time_ms:.1f}ms)"
            )
            
            return self._create_risk_score(
                score=risk_score,
                confidence=confidence,
                details=analysis_details,
                warnings=warnings,
                data_quality=self._assess_data_quality(technical_signals, price_action),
                analysis_time_ms=analysis_time_ms
            )
            
        except Exception as e:
            analysis_time_ms = (time.time() - analysis_start) * 1000
            self._update_performance_stats(analysis_time_ms, success=False)
            
            logger.error(f"Error in technical analysis: {e}", exc_info=True)
            return self._create_error_risk_score(f"Technical analysis failed: {str(e)}")
    
    async def _analyze_price_action(
        self, 
        token_address: str, 
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze basic price action and trends."""
        try:
            await asyncio.sleep(0.2)  # Simulate price data fetching
            
            # Mock price data generation based on token characteristics
            address_hash = hash(token_address)
            
            # Generate realistic price action data
            current_price = 1.0 + (address_hash % 1000) / 100.0  # $1.00-$11.00 range
            
            # Price changes over different periods
            price_changes = {
                '24h': -5 + (address_hash % 200) / 10.0,      # -5% to +15%
                '7d': -10 + (address_hash % 400) / 10.0,      # -10% to +30%
                '30d': -20 + (address_hash % 800) / 10.0,     # -20% to +60%
                '90d': -30 + (address_hash % 1200) / 10.0     # -30% to +90%
            }
            
            # Calculate trend strength
            trend_strength = abs(price_changes['7d']) / 30.0  # Normalize to 0-1
            trend_direction = 'BULLISH' if price_changes['7d'] > 5 else 'BEARISH' if price_changes['7d'] < -5 else 'SIDEWAYS'
            
            # Generate OHLC data for recent periods
            ohlc_data = []
            for i in range(24):  # Last 24 hours of hourly data
                hour_hash = hash(f"{token_address}_{i}")
                volatility = 0.02 + (hour_hash % 50) / 2500.0  # 2-4% hourly volatility
                
                open_price = current_price * (1 + (hour_hash % 100 - 50) / 5000.0)
                high_price = open_price * (1 + volatility)
                low_price = open_price * (1 - volatility)
                close_price = open_price * (1 + (hour_hash % 100 - 50) / 2500.0)
                
                ohlc_data.append({
                    'timestamp': datetime.now(timezone.utc) - timedelta(hours=24-i),
                    'open': open_price,
                    'high': high_price,
                    'low': low_price,
                    'close': close_price,
                    'volume': 10000 + (hour_hash % 50000)
                })
            
            price_action = {
                'current_price': current_price,
                'price_changes': price_changes,
                'trend_direction': trend_direction,
                'trend_strength': min(1.0, trend_strength),
                'volatility_24h': sum(abs(h['high'] - h['low']) / h['open'] for h in ohlc_data) / len(ohlc_data),
                'ohlc_data': ohlc_data,
                'all_time_high': current_price * (1.5 + (address_hash % 200) / 100.0),
                'all_time_low': current_price * (0.1 + (address_hash % 40) / 100.0),
                'trading_range': {
                    'support': current_price * 0.9,
                    'resistance': current_price * 1.1
                }
            }
            
            return price_action
            
        except Exception as e:
            logger.error(f"Error analyzing price action: {e}")
            return {'error': str(e)}
    
    async def _calculate_technical_indicators(
        self, 
        token_address: str, 
        context: Dict[str, Any]
    ) -> List[TechnicalIndicator]:
        """Calculate various technical indicators across timeframes."""
        try:
            await asyncio.sleep(0.25)  # Simulate indicator calculations
            
            indicators = []
            address_hash = hash(token_address)
            
            # Generate indicators for different timeframes
            for i, timeframe in enumerate(self.timeframes):
                tf_hash = hash(f"{token_address}_{timeframe}")
                
                # RSI (Relative Strength Index)
                rsi_value = 30 + (tf_hash % 400) / 10.0  # 30-70 typical range
                rsi_signal = 'BUY' if rsi_value < 35 else 'SELL' if rsi_value > 65 else 'NEUTRAL'
                
                indicators.append(TechnicalIndicator(
                    name='RSI',
                    timeframe=timeframe,
                    value=rsi_value,
                    signal=rsi_signal,
                    strength=abs(rsi_value - 50) / 50.0,
                    confidence=0.8,
                    description=f'RSI({timeframe}): {rsi_value:.1f} - {rsi_signal.lower()} signal'
                ))
                
                # MACD
                macd_value = -2 + (tf_hash % 400) / 100.0  # -2 to +2 range
                macd_signal = 'BUY' if macd_value > 0.5 else 'SELL' if macd_value < -0.5 else 'NEUTRAL'
                
                indicators.append(TechnicalIndicator(
                    name='MACD',
                    timeframe=timeframe,
                    value=macd_value,
                    signal=macd_signal,
                    strength=abs(macd_value) / 2.0,
                    confidence=0.75,
                    description=f'MACD({timeframe}): {macd_value:.2f} - {macd_signal.lower()} momentum'
                ))
                
                # Moving Average convergence
                ma_signal = ['BUY', 'SELL', 'NEUTRAL'][(tf_hash >> 4) % 3]
                ma_strength = (tf_hash % 100) / 100.0
                
                indicators.append(TechnicalIndicator(
                    name='MA_Cross',
                    timeframe=timeframe,
                    value=ma_strength,
                    signal=ma_signal,
                    strength=ma_strength,
                    confidence=0.7,
                    description=f'MA Cross({timeframe}): {ma_signal.lower()} trend'
                ))
                
                # Bollinger Bands
                bb_position = (tf_hash % 100) / 100.0  # Position within bands
                bb_signal = 'BUY' if bb_position < 0.2 else 'SELL' if bb_position > 0.8 else 'NEUTRAL'
                
                indicators.append(TechnicalIndicator(
                    name='BB',
                    timeframe=timeframe,
                    value=bb_position,
                    signal=bb_signal,
                    strength=abs(bb_position - 0.5) * 2,
                    confidence=0.65,
                    description=f'Bollinger Bands({timeframe}): {bb_signal.lower()} position'
                ))
            
            return indicators
            
        except Exception as e:
            logger.error(f"Error calculating technical indicators: {e}")
            return []
    
    async def _identify_support_resistance(
        self, 
        token_address: str, 
        context: Dict[str, Any]
    ) -> List[SupportResistance]:
        """Identify key support and resistance levels."""
        try:
            await asyncio.sleep(0.15)  # Simulate S/R level identification
            
            support_resistance = []
            address_hash = hash(token_address)
            current_price = 1.0 + (address_hash % 1000) / 100.0
            
            # Generate support levels
            for i in range(3):  # 3 support levels
                level_hash = hash(f"{token_address}_support_{i}")
                distance_factor = 0.05 + (i * 0.05) + (level_hash % 50) / 1000.0  # 5-20% below
                support_price = current_price * (1 - distance_factor)
                
                support_resistance.append(SupportResistance(
                    level_type='SUPPORT',
                    price=support_price,
                    strength=0.6 + (level_hash % 40) / 100.0,  # 0.6-0.99 strength
                    touches=2 + (level_hash % 5),  # 2-6 touches
                    timeframe=['1h', '4h', '1d'][i],
                    confidence=0.7 + (level_hash % 25) / 100.0
                ))
            
            # Generate resistance levels
            for i in range(3):  # 3 resistance levels
                level_hash = hash(f"{token_address}_resistance_{i}")
                distance_factor = 0.05 + (i * 0.05) + (level_hash % 50) / 1000.0  # 5-20% above
                resistance_price = current_price * (1 + distance_factor)
                
                support_resistance.append(SupportResistance(
                    level_type='RESISTANCE',
                    price=resistance_price,
                    strength=0.6 + (level_hash % 40) / 100.0,
                    touches=2 + (level_hash % 5),
                    timeframe=['1h', '4h', '1d'][i],
                    confidence=0.7 + (level_hash % 25) / 100.0
                ))
            
            return support_resistance
            
        except Exception as e:
            logger.error(f"Error identifying support/resistance: {e}")
            return []
    
    async def _analyze_volume_patterns(
        self, 
        token_address: str, 
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze volume patterns and trends."""
        try:
            await asyncio.sleep(0.12)  # Simulate volume analysis
            
            address_hash = hash(token_address)
            
            # Generate volume metrics
            avg_volume_24h = 100000 + (address_hash % 500000)  # $100K-$600K daily
            current_volume = avg_volume_24h * (0.5 + (address_hash % 200) / 100.0)  # 50%-250% of average
            
            volume_analysis = {
                'current_volume_24h': current_volume,
                'average_volume_24h': avg_volume_24h,
                'volume_ratio': current_volume / avg_volume_24h,
                'volume_trend': 'INCREASING' if current_volume > avg_volume_24h * 1.2 else 
                               'DECREASING' if current_volume < avg_volume_24h * 0.8 else 'STABLE',
                'volume_spike_detected': current_volume > avg_volume_24h * self.thresholds['volume_spike_threshold'],
                'volume_profile': {
                    'buy_volume_percentage': 45 + (address_hash % 20),  # 45-64% buy volume
                    'sell_volume_percentage': 36 + (address_hash % 20),  # 36-55% sell volume
                },
                'volume_oscillator': -0.2 + (address_hash % 40) / 100.0,  # -0.2 to +0.2
                'on_balance_volume_trend': ['BULLISH', 'BEARISH', 'NEUTRAL'][(address_hash >> 8) % 3],
                'accumulation_distribution': 0.3 + (address_hash % 40) / 100.0  # 0.3-0.7
            }
            
            # Volume-based signals
            volume_signals = []
            
            if volume_analysis['volume_spike_detected']:
                volume_signals.append('VOLUME_SPIKE')
            
            if volume_analysis['volume_ratio'] > 1.5:
                volume_signals.append('HIGH_VOLUME')
            elif volume_analysis['volume_ratio'] < 0.5:
                volume_signals.append('LOW_VOLUME')
            
            if volume_analysis['volume_profile']['buy_volume_percentage'] > 60:
                volume_signals.append('BUYING_PRESSURE')
            elif volume_analysis['volume_profile']['sell_volume_percentage'] > 60:
                volume_signals.append('SELLING_PRESSURE')
            
            volume_analysis['signals'] = volume_signals
            
            return volume_analysis
            
        except Exception as e:
            logger.error(f"Error analyzing volume patterns: {e}")
            return {'error': str(e)}
    
    async def _detect_chart_patterns(
        self, 
        token_address: str, 
        context: Dict[str, Any]
    ) -> List[ChartPattern]:
        """Detect chart patterns and formations."""
        try:
            await asyncio.sleep(0.18)  # Simulate pattern detection
            
            chart_patterns = []
            address_hash = hash(token_address)
            current_price = 1.0 + (address_hash % 1000) / 100.0
            
            # Common chart patterns
            patterns = [
                'Head_and_Shoulders', 'Double_Top', 'Double_Bottom', 
                'Triangle_Ascending', 'Triangle_Descending', 'Flag_Bull', 
                'Flag_Bear', 'Wedge_Rising', 'Wedge_Falling'
            ]
            
            # Generate 1-3 detected patterns
            pattern_count = 1 + (address_hash % 3)
            
            for i in range(pattern_count):
                pattern_hash = hash(f"{token_address}_pattern_{i}")
                pattern_name = patterns[pattern_hash % len(patterns)]
                
                # Determine pattern characteristics
                is_bullish = pattern_name in ['Double_Bottom', 'Triangle_Ascending', 'Flag_Bull', 'Wedge_Falling']
                is_bearish = pattern_name in ['Head_and_Shoulders', 'Double_Top', 'Flag_Bear', 'Wedge_Rising']
                
                signal = 'BULLISH' if is_bullish else 'BEARISH' if is_bearish else 'NEUTRAL'
                confidence = 0.6 + (pattern_hash % 35) / 100.0  # 0.6-0.94 confidence
                
                # Calculate target and stop loss
                if is_bullish:
                    target_price = current_price * (1.1 + (pattern_hash % 30) / 100.0)  # 10-40% upside
                    stop_loss = current_price * (0.95 - (pattern_hash % 10) / 100.0)   # 5-15% downside
                elif is_bearish:
                    target_price = current_price * (0.9 - (pattern_hash % 30) / 100.0)  # 10-40% downside
                    stop_loss = current_price * (1.05 + (pattern_hash % 10) / 100.0)   # 5-15% upside
                else:
                    target_price = None
                    stop_loss = None
                
                chart_patterns.append(ChartPattern(
                    pattern_name=pattern_name,
                    timeframe=self.timeframes[(pattern_hash >> 4) % len(self.timeframes)],
                    confidence=confidence,
                    signal=signal,
                    target_price=target_price,
                    stop_loss=stop_loss,
                    completion_percentage=70 + (pattern_hash % 30)  # 70-99% complete
                ))
            
            return chart_patterns
            
        except Exception as e:
            logger.error(f"Error detecting chart patterns: {e}")
            return []
    
    async def _analyze_momentum_oscillators(
        self, 
        token_address: str, 
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze momentum oscillators and momentum indicators."""
        try:
            await asyncio.sleep(0.1)  # Simulate momentum analysis
            
            address_hash = hash(token_address)
            
            momentum_analysis = {
                'stochastic': {
                    'k_percent': 20 + (address_hash % 600) / 10.0,  # 20-80 range
                    'd_percent': 25 + (address_hash % 500) / 10.0,  # 25-75 range
                    'signal': 'OVERSOLD' if (address_hash % 100) < 20 else 
                             'OVERBOUGHT' if (address_hash % 100) > 80 else 'NEUTRAL'
                },
                'williams_r': -80 + (address_hash % 600) / 10.0,  # -80 to -20
                'cci': -100 + (address_hash % 2000) / 10.0,  # -100 to +100
                'momentum_score': 0.3 + (address_hash % 400) / 1000.0,  # 0.3-0.7
                'rate_of_change': -15 + (address_hash % 300) / 10.0,  # -15% to +15%
                'momentum_divergence': (address_hash % 10) < 2,  # 20% chance of divergence
                'momentum_trend': ['ACCELERATING', 'DECELERATING', 'STABLE'][(address_hash >> 6) % 3],
                'bullish_momentum': (address_hash % 100) > 60,  # 40% chance of bullish momentum
                'bearish_momentum': (address_hash % 100) < 20   # 20% chance of bearish momentum
            }
            
            return momentum_analysis
            
        except Exception as e:
            logger.error(f"Error analyzing momentum oscillators: {e}")
            return {'error': str(e)}
    
    def _generate_technical_signals(
        self,
        price_action: Dict[str, Any],
        technical_indicators: List[TechnicalIndicator],
        support_resistance: List[SupportResistance],
        volume_analysis: Dict[str, Any],
        chart_patterns: List[ChartPattern],
        momentum_analysis: Dict[str, Any]
    ) -> List[TechnicalSignal]:
        """Generate comprehensive technical signals from all analyses."""
        signals = []
        
        # Generate signals for each timeframe
        for timeframe in self.timeframes:
            # Collect indicators for this timeframe
            tf_indicators = [ind for ind in technical_indicators if ind.timeframe == timeframe]
            
            # Calculate aggregated signal strength
            buy_signals = sum(1 for ind in tf_indicators if ind.signal == 'BUY')
            sell_signals = sum(1 for ind in tf_indicators if ind.signal == 'SELL')
            total_signals = len(tf_indicators)
            
            if total_signals == 0:
                continue
            
            # Determine overall signal
            if buy_signals > sell_signals and buy_signals >= total_signals * 0.6:
                signal = 'BUY'
                strength = buy_signals / total_signals
            elif sell_signals > buy_signals and sell_signals >= total_signals * 0.6:
                signal = 'SELL'
                strength = sell_signals / total_signals
            else:
                signal = 'NEUTRAL'
                strength = 0.5
            
            # Aggregate indicator values for this timeframe
            indicators_dict = {}
            for ind in tf_indicators:
                indicators_dict[ind.name] = ind.value
            
            # Find relevant support/resistance levels
            sr_levels = [sr for sr in support_resistance if sr.timeframe == timeframe]
            price_targets = {}
            
            if sr_levels:
                supports = [sr.price for sr in sr_levels if sr.level_type == 'SUPPORT']
                resistances = [sr.price for sr in sr_levels if sr.level_type == 'RESISTANCE']
                
                if supports:
                    price_targets['support'] = min(supports)
                if resistances:
                    price_targets['resistance'] = max(resistances)
            
            # Calculate confidence based on signal convergence
            signal_convergence = max(buy_signals, sell_signals) / total_signals
            confidence = signal_convergence * 0.8 + 0.2  # 0.2-1.0 range
            
            signals.append(TechnicalSignal(
                timeframe=timeframe,
                signal=signal,
                strength=strength,
                indicators=indicators_dict,
                price_targets=price_targets,
                confidence=confidence
            ))
        
        return signals
    
    def _calculate_technical_risk(
        self,
        technical_signals: List[TechnicalSignal],
        price_action: Dict[str, Any],
        volume_analysis: Dict[str, Any]
    ) -> Tuple[float, float]:
        """Calculate technical risk score (inverted - good technicals = low risk)."""
        if not technical_signals:
            return 0.6, 0.3  # Moderate risk, low confidence for no signals
        
        risk_factors = []
        
        # Signal consistency risk (conflicting signals = higher risk)
        buy_signals = sum(1 for sig in technical_signals if sig.signal == 'BUY')
        sell_signals = sum(1 for sig in technical_signals if sig.signal == 'SELL')
        neutral_signals = len(technical_signals) - buy_signals - sell_signals
        
        # Higher risk when signals conflict across timeframes
        signal_conflict = min(buy_signals, sell_signals) / len(technical_signals)
        consistency_risk = signal_conflict * 0.8  # 0-0.8 risk from conflicts
        risk_factors.append(('signal_consistency', consistency_risk, 0.3))
        
        # Trend strength risk (weak trends = higher risk)
        trend_strength = price_action.get('trend_strength', 0.5)
        trend_risk = 1.0 - trend_strength  # Invert: weak trend = high risk
        risk_factors.append(('trend_strength', trend_risk, 0.25))
        
        # Volatility risk
        volatility = price_action.get('volatility_24h', 0.05)
        volatility_risk = min(1.0, volatility * 10)  # Normalize to 0-1
        risk_factors.append(('volatility', volatility_risk, 0.2))
        
        # Volume risk (abnormal volume = higher risk)
        volume_ratio = volume_analysis.get('volume_ratio', 1.0)
        volume_risk = abs(volume_ratio - 1.0)  # Deviation from normal
        volume_risk = min(1.0, volume_risk)
        risk_factors.append(('volume', volume_risk, 0.15))
        
        # Momentum risk
        momentum_score = price_action.get('momentum_score', 0.5)
        momentum_risk = 1.0 - momentum_score  # Invert: weak momentum = high risk
        risk_factors.append(('momentum', momentum_risk, 0.1))
        
        # Calculate weighted risk
        total_risk = 0.0
        total_weight = 0.0
        
        for factor_name, risk, weight in risk_factors:
            total_risk += risk * weight
            total_weight += weight
        
        overall_risk = total_risk / total_weight if total_weight > 0 else 0.5
        
        # Confidence based on signal quality and data completeness
        avg_confidence = sum(sig.confidence for sig in technical_signals) / len(technical_signals)
        data_completeness = 1.0 if price_action and volume_analysis else 0.5
        
        overall_confidence = (avg_confidence + data_completeness) / 2
        overall_confidence = max(0.3, min(0.95, overall_confidence))