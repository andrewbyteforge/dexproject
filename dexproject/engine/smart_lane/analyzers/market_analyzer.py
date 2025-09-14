"""
Market Structure Analyzer

Medium-priority analyzer that evaluates market manipulation risks,
trading patterns, and market microstructure indicators. Helps identify
potential pump-and-dump schemes and coordinated trading activity.

Path: engine/smart_lane/analyzers/market_analyzer.py
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import statistics
import math

from . import BaseAnalyzer
from .. import RiskScore, RiskCategory

logger = logging.getLogger(__name__)


@dataclass
class TradingPattern:
    """Identified trading pattern or anomaly."""
    pattern_type: str  # PUMP_DUMP, WASH_TRADING, COORDINATED_BUYING, etc.
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    description: str
    evidence: Dict[str, Any]
    confidence: float
    time_window: str
    impact_score: float


@dataclass
class MarketMetric:
    """Individual market structure metric."""
    metric_name: str
    value: float
    normalized_score: float  # 0-1 scale, 1 = highest risk
    threshold_breached: bool
    description: str
    confidence: float


@dataclass
class VolumeAnalysis:
    """Volume pattern analysis results."""
    volume_concentration: float  # Gini coefficient for volume distribution
    unusual_volume_spikes: int
    volume_price_correlation: float
    wash_trading_score: float
    organic_volume_ratio: float
    volume_trend: str  # INCREASING, DECREASING, STABLE
    average_trade_size: float


@dataclass
class PriceManipulationIndicators:
    """Price manipulation detection results."""
    pump_dump_score: float
    coordinated_activity_score: float
    artificial_price_support: float
    price_volatility_manipulation: float
    manipulation_risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    suspicious_transactions: List[Dict[str, Any]]


class MarketAnalyzer(BaseAnalyzer):
    """
    Advanced market structure and manipulation detection analyzer.
    
    Analyzes:
    - Trading volume patterns and concentration
    - Price manipulation indicators (pump & dump, wash trading)
    - Market microstructure anomalies
    - Coordinated trading activity detection
    - Whale transaction analysis
    - Liquidity manipulation patterns
    - Order book depth and spread analysis
    """
    
    def __init__(self, chain_id: int, config: Optional[Dict[str, Any]] = None):
        """
        Initialize market structure analyzer.
        
        Args:
            chain_id: Blockchain chain identifier
            config: Analyzer configuration including thresholds and lookback periods
        """
        super().__init__(chain_id, config)
        
        # Analysis thresholds
        self.thresholds = {
            'volume_spike_threshold': 5.0,  # 5x normal volume
            'price_pump_threshold': 0.5,  # 50% price increase
            'wash_trading_threshold': 0.3,  # 30% suspected wash trading
            'coordination_threshold': 0.7,  # 70% coordination score
            'whale_transaction_threshold': 100000,  # $100k USD
            'volume_concentration_threshold': 0.8,  # 80% concentration
            'manipulation_score_threshold': 0.6,
            'min_transaction_sample': 50
        }
        
        # Update with custom config
        if config:
            self.thresholds.update(config.get('thresholds', {}))
        
        # Analysis time windows
        self.analysis_windows = {
            'short_term': 1,  # 1 hour
            'medium_term': 6,  # 6 hours  
            'long_term': 24   # 24 hours
        }
        
        # Pattern detection algorithms
        self.manipulation_patterns = self._load_manipulation_patterns()
        
        # Analysis cache
        self.market_cache: Dict[str, Tuple[Dict[str, Any], datetime]] = {}
        self.cache_ttl_minutes = 10  # Short cache for market data
        
        logger.info(f"Market analyzer initialized for chain {chain_id}")
    
    def get_category(self) -> RiskCategory:
        """Get the risk category this analyzer handles."""
        return RiskCategory.MARKET_STRUCTURE
    
    async def analyze(
        self,
        token_address: str,
        context: Dict[str, Any]
    ) -> RiskScore:
        """
        Perform comprehensive market structure analysis.
        
        Args:
            token_address: Token contract address to analyze
            context: Additional context including trading data, liquidity info
            
        Returns:
            RiskScore with market manipulation assessment
        """
        analysis_start = time.time()
        
        try:
            logger.debug(f"Starting market analysis for {token_address[:10]}...")
            
            # Update performance stats
            self.performance_stats['total_analyses'] += 1
            
            # Input validation
            if not self._validate_inputs(token_address, context):
                return self._create_error_risk_score("Invalid inputs for market analysis")
            
            # Check cache first
            cached_result = self._get_cached_analysis(token_address)
            if cached_result and not context.get('force_refresh', False):
                self.performance_stats['cache_hits'] += 1
                return self._create_risk_score_from_cache(cached_result)
            
            self.performance_stats['cache_misses'] += 1
            
            # Fetch trading and market data
            market_data = await self._fetch_market_data(token_address, context)
            if not market_data or len(market_data.get('transactions', [])) < self.thresholds['min_transaction_sample']:
                return self._create_error_risk_score("Insufficient trading data for market analysis")
            
            # Perform market analysis tasks
            analysis_tasks = [
                self._analyze_volume_patterns(market_data),
                self._detect_price_manipulation(market_data),
                self._analyze_trading_concentration(market_data),
                self._detect_coordinated_activity(market_data),
                self._analyze_whale_transactions(market_data),
                self._assess_market_microstructure(market_data)
            ]
            
            # Execute all tasks with timeout protection
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*analysis_tasks, return_exceptions=True),
                    timeout=25.0  # 25 second timeout for market analysis
                )
            except asyncio.TimeoutError:
                logger.warning(f"Market analysis timeout for {token_address[:10]}")
                return self._create_timeout_risk_score()
            
            # Process results
            volume_analysis = results[0] if not isinstance(results[0], Exception) else None
            manipulation_indicators = results[1] if not isinstance(results[1], Exception) else None
            concentration_metrics = results[2] if not isinstance(results[2], Exception) else []
            coordination_patterns = results[3] if not isinstance(results[3], Exception) else []
            whale_analysis = results[4] if not isinstance(results[4], Exception) else {}
            microstructure_metrics = results[5] if not isinstance(results[5], Exception) else {}
            
            # Aggregate all patterns and metrics
            all_patterns = coordination_patterns.copy() if coordination_patterns else []
            all_metrics = concentration_metrics.copy() if concentration_metrics else []
            
            # Calculate overall market risk score
            risk_score = self._calculate_market_risk_score(
                volume_analysis, manipulation_indicators, all_patterns, all_metrics
            )
            
            # Cache the result
            analysis_result = {
                'volume_analysis': volume_analysis,
                'manipulation_indicators': manipulation_indicators,
                'trading_patterns': all_patterns,
                'market_metrics': all_metrics,
                'whale_analysis': whale_analysis,
                'microstructure_metrics': microstructure_metrics
            }
            self._cache_analysis_result(token_address, analysis_result)
            
            # Create detailed analysis data
            analysis_details = {
                'volume_analysis': volume_analysis.__dict__ if volume_analysis else None,
                'manipulation_indicators': manipulation_indicators.__dict__ if manipulation_indicators else None,
                'trading_patterns': [p.__dict__ for p in all_patterns],
                'market_metrics': [m.__dict__ for m in all_metrics],
                'whale_analysis': whale_analysis,
                'microstructure_metrics': microstructure_metrics,
                'data_quality': self._assess_market_data_quality(market_data)
            }
            
            # Generate warnings
            warnings = self._generate_market_warnings(
                manipulation_indicators, all_patterns, volume_analysis
            )
            
            # Calculate analysis time
            analysis_time_ms = (time.time() - analysis_start) * 1000
            
            # Update performance stats
            self.performance_stats['successful_analyses'] += 1
            
            # Determine confidence based on data quality
            confidence = self._calculate_analysis_confidence(market_data, all_patterns)
            
            # Create and return risk score
            return RiskScore(
                category=self.get_category(),
                score=risk_score,
                confidence=confidence,
                details=analysis_details,
                analysis_time_ms=analysis_time_ms,
                warnings=warnings,
                data_quality=self._assess_market_data_quality(market_data),
                last_updated=datetime.now(timezone.utc).isoformat()
            )
            
        except Exception as e:
            logger.error(f"Error in market structure analysis: {e}", exc_info=True)
            self.performance_stats['failed_analyses'] += 1
            
            analysis_time_ms = (time.time() - analysis_start) * 1000
            return RiskScore(
                category=self.get_category(),
                score=0.6,  # Medium-high risk due to analysis failure
                confidence=0.2,
                details={'error': str(e), 'analysis_failed': True},
                analysis_time_ms=analysis_time_ms,
                warnings=[f"Market analysis failed: {str(e)}"],
                data_quality="POOR"
            )
    
    async def _fetch_market_data(
        self,
        token_address: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Fetch trading data, transactions, and market metrics.
        
        In production, this would fetch data from DEX APIs, blockchain indexers,
        and trading analytics providers.
        """
        await asyncio.sleep(0.15)  # Simulate API call
        
        # Mock market data generation
        current_time = datetime.now(timezone.utc)
        
        # Generate mock transactions for the last 24 hours
        transactions = []
        base_price = context.get('current_price', 1.0)
        
        for i in range(200):  # 200 mock transactions
            timestamp = current_time - timedelta(hours=24-i*0.12)
            
            # Simulate various transaction patterns
            tx_type = 'buy' if i % 2 == 0 else 'sell'
            
            # Add some volume spikes and manipulation patterns
            if 50 <= i <= 60:  # Coordinated activity period
                volume_multiplier = 5.0
                price_impact = 0.15 if tx_type == 'buy' else -0.05
            elif 120 <= i <= 125:  # Pump period
                volume_multiplier = 8.0
                price_impact = 0.25 if tx_type == 'buy' else 0.10
            else:
                volume_multiplier = 1.0 + (0.5 * math.sin(i / 10))
                price_impact = 0.02 * math.sin(i / 5)
            
            price = base_price * (1 + price_impact)
            volume_usd = (1000 + 500 * math.sin(i / 8)) * volume_multiplier
            
            # Some whale transactions
            if i % 30 == 0:
                volume_usd *= 50  # Whale transaction
            
            transactions.append({
                'timestamp': timestamp.isoformat(),
                'type': tx_type,
                'price': price,
                'volume_usd': volume_usd,
                'volume_tokens': volume_usd / price,
                'trader_address': f"0x{'abcd1234'*(i%5+1)}{'0'*(40-len('abcd1234'*(i%5+1)))}",
                'gas_price': 20 + (10 * math.sin(i / 15)),
                'block_number': 19000000 + i * 3
            })
        
        # Calculate aggregate metrics
        total_volume_24h = sum(tx['volume_usd'] for tx in transactions)
        unique_traders = len(set(tx['trader_address'] for tx in transactions))
        
        market_data = {
            'token_address': token_address,
            'transactions': transactions,
            'total_volume_24h': total_volume_24h,
            'unique_traders_24h': unique_traders,
            'current_price': base_price,
            'price_change_24h': 0.08,  # 8% change
            'market_cap': context.get('market_cap', 10000000),
            'liquidity_depth': context.get('liquidity_usd', 50000),
            'data_quality': 'GOOD',
            'last_updated': current_time.isoformat()
        }
        
        return market_data
    
    async def _analyze_volume_patterns(self, market_data: Dict[str, Any]) -> VolumeAnalysis:
        """Analyze trading volume patterns for anomalies."""
        transactions = market_data.get('transactions', [])
        
        if len(transactions) < 10:
            return VolumeAnalysis(
                volume_concentration=0.5,
                unusual_volume_spikes=0,
                volume_price_correlation=0.0,
                wash_trading_score=0.0,
                organic_volume_ratio=1.0,
                volume_trend="STABLE",
                average_trade_size=0.0
            )
        
        try:
            await asyncio.sleep(0.1)
            
            # Calculate volume metrics
            volumes = [tx['volume_usd'] for tx in transactions]
            prices = [tx['price'] for tx in transactions]
            
            # Volume concentration (Gini coefficient)
            volume_concentration = self._calculate_gini_coefficient(volumes)
            
            # Detect volume spikes
            avg_volume = sum(volumes) / len(volumes)
            volume_spikes = len([v for v in volumes if v > avg_volume * self.thresholds['volume_spike_threshold']])
            
            # Volume-price correlation
            volume_price_correlation = self._calculate_correlation(volumes, prices)
            
            # Wash trading detection
            wash_trading_score = self._detect_wash_trading(transactions)
            
            # Organic volume ratio
            organic_volume_ratio = max(0.0, 1.0 - wash_trading_score)
            
            # Volume trend
            recent_volume = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else avg_volume
            volume_trend = "INCREASING" if recent_volume > avg_volume * 1.2 else \
                          "DECREASING" if recent_volume < avg_volume * 0.8 else "STABLE"
            
            # Average trade size
            average_trade_size = avg_volume
            
            return VolumeAnalysis(
                volume_concentration=volume_concentration,
                unusual_volume_spikes=volume_spikes,
                volume_price_correlation=volume_price_correlation,
                wash_trading_score=wash_trading_score,
                organic_volume_ratio=organic_volume_ratio,
                volume_trend=volume_trend,
                average_trade_size=average_trade_size
            )
            
        except Exception as e:
            logger.warning(f"Error in volume analysis: {e}")
            return VolumeAnalysis(
                volume_concentration=0.5,
                unusual_volume_spikes=0,
                volume_price_correlation=0.0,
                wash_trading_score=0.0,
                organic_volume_ratio=1.0,
                volume_trend="UNKNOWN",
                average_trade_size=0.0
            )
    
    async def _detect_price_manipulation(self, market_data: Dict[str, Any]) -> PriceManipulationIndicators:
        """Detect various forms of price manipulation."""
        transactions = market_data.get('transactions', [])
        
        try:
            await asyncio.sleep(0.1)
            
            # Pump and dump detection
            pump_dump_score = self._detect_pump_dump_pattern(transactions)
            
            # Coordinated activity detection
            coordinated_activity_score = self._detect_coordinated_trading(transactions)
            
            # Artificial price support detection
            artificial_support = self._detect_artificial_price_support(transactions)
            
            # Price volatility manipulation
            volatility_manipulation = self._detect_volatility_manipulation(transactions)
            
            # Overall manipulation risk
            manipulation_scores = [
                pump_dump_score, coordinated_activity_score, 
                artificial_support, volatility_manipulation
            ]
            avg_manipulation = sum(manipulation_scores) / len(manipulation_scores)
            
            if avg_manipulation > 0.8:
                risk_level = "CRITICAL"
            elif avg_manipulation > 0.6:
                risk_level = "HIGH"
            elif avg_manipulation > 0.4:
                risk_level = "MEDIUM"
            else:
                risk_level = "LOW"
            
            # Identify suspicious transactions
            suspicious_transactions = self._identify_suspicious_transactions(transactions)
            
            return PriceManipulationIndicators(
                pump_dump_score=pump_dump_score,
                coordinated_activity_score=coordinated_activity_score,
                artificial_price_support=artificial_support,
                price_volatility_manipulation=volatility_manipulation,
                manipulation_risk_level=risk_level,
                suspicious_transactions=suspicious_transactions
            )
            
        except Exception as e:
            logger.warning(f"Error in manipulation detection: {e}")
            return PriceManipulationIndicators(
                pump_dump_score=0.0,
                coordinated_activity_score=0.0,
                artificial_price_support=0.0,
                price_volatility_manipulation=0.0,
                manipulation_risk_level="UNKNOWN",
                suspicious_transactions=[]
            )
    
    async def _analyze_trading_concentration(self, market_data: Dict[str, Any]) -> List[MarketMetric]:
        """Analyze trading concentration among participants."""
        transactions = market_data.get('transactions', [])
        metrics = []
        
        try:
            await asyncio.sleep(0.05)
            
            if len(transactions) < 10:
                return metrics
            
            # Calculate trader concentration
            trader_volumes = {}
            for tx in transactions:
                trader = tx['trader_address']
                trader_volumes[trader] = trader_volumes.get(trader, 0) + tx['volume_usd']
            
            volumes = list(trader_volumes.values())
            total_volume = sum(volumes)
            
            # Top trader concentration
            sorted_volumes = sorted(volumes, reverse=True)
            top_5_volume = sum(sorted_volumes[:5]) if len(sorted_volumes) >= 5 else sum(sorted_volumes)
            top_5_concentration = top_5_volume / total_volume if total_volume > 0 else 0
            
            metrics.append(MarketMetric(
                metric_name="TOP_5_TRADER_CONCENTRATION",
                value=top_5_concentration,
                normalized_score=top_5_concentration,
                threshold_breached=top_5_concentration > self.thresholds['volume_concentration_threshold'],
                description=f"Top 5 traders control {top_5_concentration:.1%} of volume",
                confidence=0.8
            ))
            
            # Trader diversity
            unique_traders = len(trader_volumes)
            trader_diversity = min(unique_traders / 100, 1.0)  # Normalize to 100 traders
            
            metrics.append(MarketMetric(
                metric_name="TRADER_DIVERSITY",
                value=unique_traders,
                normalized_score=1.0 - trader_diversity,  # Lower diversity = higher risk
                threshold_breached=unique_traders < 20,
                description=f"{unique_traders} unique traders in 24h",
                confidence=0.9
            ))
            
            # Volume distribution inequality (Gini coefficient)
            gini_coefficient = self._calculate_gini_coefficient(volumes)
            
            metrics.append(MarketMetric(
                metric_name="VOLUME_INEQUALITY",
                value=gini_coefficient,
                normalized_score=gini_coefficient,
                threshold_breached=gini_coefficient > 0.8,
                description=f"Volume Gini coefficient: {gini_coefficient:.3f}",
                confidence=0.7
            ))
            
        except Exception as e:
            logger.warning(f"Error in concentration analysis: {e}")
        
        return metrics
    
    async def _detect_coordinated_activity(self, market_data: Dict[str, Any]) -> List[TradingPattern]:
        """Detect coordinated trading activity patterns."""
        transactions = market_data.get('transactions', [])
        patterns = []
        
        try:
            await asyncio.sleep(0.1)
            
            if len(transactions) < 20:
                return patterns
            
            # Time-based coordination detection
            time_coordination = self._detect_time_coordination(transactions)
            if time_coordination['score'] > self.thresholds['coordination_threshold']:
                patterns.append(TradingPattern(
                    pattern_type="TIME_COORDINATED_TRADING",
                    severity="HIGH",
                    description=f"Detected coordinated trading in {time_coordination['window']} time windows",
                    evidence=time_coordination,
                    confidence=0.8,
                    time_window="24h",
                    impact_score=time_coordination['score']
                ))
            
            # Volume coordination detection
            volume_coordination = self._detect_volume_coordination(transactions)
            if volume_coordination['score'] > 0.6:
                patterns.append(TradingPattern(
                    pattern_type="VOLUME_COORDINATED_TRADING",
                    severity="MEDIUM",
                    description="Similar volume patterns detected across traders",
                    evidence=volume_coordination,
                    confidence=0.7,
                    time_window="24h",
                    impact_score=volume_coordination['score']
                ))
            
            # Price impact coordination
            price_coordination = self._detect_price_coordination(transactions)
            if price_coordination['score'] > 0.7:
                patterns.append(TradingPattern(
                    pattern_type="PRICE_IMPACT_COORDINATION",
                    severity="HIGH",
                    description="Coordinated price impact detected",
                    evidence=price_coordination,
                    confidence=0.75,
                    time_window="24h",
                    impact_score=price_coordination['score']
                ))
            
        except Exception as e:
            logger.warning(f"Error in coordination detection: {e}")
        
        return patterns
    
    async def _analyze_whale_transactions(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze large whale transactions and their impact."""
        transactions = market_data.get('transactions', [])
        
        try:
            await asyncio.sleep(0.05)
            
            # Identify whale transactions
            whale_threshold = self.thresholds['whale_transaction_threshold']
            whale_txs = [tx for tx in transactions if tx['volume_usd'] > whale_threshold]
            
            if not whale_txs:
                return {
                    'whale_transaction_count': 0,
                    'whale_volume_ratio': 0.0,
                    'whale_price_impact': 0.0,
                    'whale_timing_analysis': {},
                    'risk_level': 'LOW'
                }
            
            total_volume = sum(tx['volume_usd'] for tx in transactions)
            whale_volume = sum(tx['volume_usd'] for tx in whale_txs)
            whale_volume_ratio = whale_volume / total_volume if total_volume > 0 else 0
            
            # Analyze whale price impact
            whale_price_impact = self._calculate_whale_price_impact(whale_txs, transactions)
            
            # Whale timing analysis
            whale_timing = self._analyze_whale_timing(whale_txs)
            
            # Risk assessment
            if whale_volume_ratio > 0.5 or whale_price_impact > 0.3:
                risk_level = 'HIGH'
            elif whale_volume_ratio > 0.3 or whale_price_impact > 0.15:
                risk_level = 'MEDIUM'
            else:
                risk_level = 'LOW'
            
            return {
                'whale_transaction_count': len(whale_txs),
                'whale_volume_ratio': whale_volume_ratio,
                'whale_price_impact': whale_price_impact,
                'whale_timing_analysis': whale_timing,
                'largest_whale_transaction': max(whale_txs, key=lambda x: x['volume_usd'])['volume_usd'],
                'risk_level': risk_level
            }
            
        except Exception as e:
            logger.warning(f"Error in whale analysis: {e}")
            return {'error': str(e)}
    
    async def _assess_market_microstructure(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Assess market microstructure indicators."""
        transactions = market_data.get('transactions', [])
        
        try:
            await asyncio.sleep(0.05)
            
            if len(transactions) < 10:
                return {}
            
            # Calculate bid-ask spread proxy
            buy_txs = [tx for tx in transactions if tx['type'] == 'buy']
            sell_txs = [tx for tx in transactions if tx['type'] == 'sell']
            
            if buy_txs and sell_txs:
                avg_buy_price = sum(tx['price'] for tx in buy_txs) / len(buy_txs)
                avg_sell_price = sum(tx['price'] for tx in sell_txs) / len(sell_txs)
                spread = abs(avg_buy_price - avg_sell_price) / ((avg_buy_price + avg_sell_price) / 2)
            else:
                spread = 0.0
            
            # Market depth analysis
            recent_txs = transactions[-50:]  # Last 50 transactions
            market_depth = sum(tx['volume_usd'] for tx in recent_txs)
            
            # Transaction frequency
            if len(transactions) >= 2:
                timestamps = [datetime.fromisoformat(tx['timestamp'].replace('Z', '+00:00')) for tx in transactions]
                time_diffs = [(timestamps[i] - timestamps[i-1]).total_seconds() for i in range(1, len(timestamps))]
                avg_time_between_txs = sum(time_diffs) / len(time_diffs) if time_diffs else 0
            else:
                avg_time_between_txs = 0
            
            return {
                'effective_spread': spread,
                'market_depth_recent': market_depth,
                'average_time_between_transactions': avg_time_between_txs,
                'transaction_frequency': len(transactions) / 24,  # Transactions per hour
                'buy_sell_ratio': len(buy_txs) / len(sell_txs) if sell_txs else 0,
                'market_efficiency_score': max(0.0, 1.0 - spread - (avg_time_between_txs / 3600))
            }
            
        except Exception as e:
            logger.warning(f"Error in microstructure analysis: {e}")
            return {}
    
    # Helper methods for pattern detection
    def _detect_pump_dump_pattern(self, transactions: List[Dict[str, Any]]) -> float:
        """Detect pump and dump patterns in price movements."""
        if len(transactions) < 20:
            return 0.0
        
        prices = [tx['price'] for tx in transactions]
        volumes = [tx['volume_usd'] for tx in transactions]
        
        # Look for rapid price increases followed by dumps
        pump_score = 0.0
        window_size = 10
        
        for i in range(window_size, len(prices) - window_size):
            # Check for pump (price increase with volume)
            price_before = prices[i-window_size:i]
            price_pump = prices[i:i+window_size//2]
            price_after = prices[i+window_size//2:i+window_size]
            
            if len(price_before) > 0 and len(price_pump) > 0 and len(price_after) > 0:
                avg_before = sum(price_before) / len(price_before)
                avg_pump = sum(price_pump) / len(price_pump)
                avg_after = sum(price_after) / len(price_after)
                
                pump_increase = (avg_pump - avg_before) / avg_before if avg_before > 0 else 0
                dump_decrease = (avg_pump - avg_after) / avg_pump if avg_pump > 0 else 0
                
                if pump_increase > 0.3 and dump_decrease > 0.2:  # 30% pump, 20% dump
                    volume_during_pump = sum(volumes[i:i+window_size//2])
                    avg_volume = sum(volumes) / len(volumes)
                    volume_ratio = volume_during_pump / (avg_volume * (window_size//2)) if avg_volume > 0 else 0
                    
                    pattern_strength = min(pump_increase * dump_decrease * volume_ratio, 1.0)
                    pump_score = max(pump_score, pattern_strength)
        
        return pump_score
    
    def _detect_wash_trading(self, transactions: List[Dict[str, Any]]) -> float:
        """Detect wash trading patterns."""
        if len(transactions) < 10:
            return 0.0
        
        # Group transactions by trader
        trader_txs = {}
        for tx in transactions:
            trader = tx['trader_address']
            if trader not in trader_txs:
                trader_txs[trader] = []
            trader_txs[trader].append(tx)
        
        wash_indicators = 0
        total_volume = sum(tx['volume_usd'] for tx in transactions)
        suspicious_volume = 0
        
        for trader, txs in trader_txs.items():
            if len(txs) < 4:  # Need multiple transactions to detect wash trading
                continue
            
            # Check for rapid buy-sell patterns
            buy_txs = [tx for tx in txs if tx['type'] == 'buy']
            sell_txs = [tx for tx in txs if tx['type'] == 'sell']
            
            if len(buy_txs) > 0 and len(sell_txs) > 0:
                # Check if buy and sell volumes are similar
                total_buy_volume = sum(tx['volume_usd'] for tx in buy_txs)
                total_sell_volume = sum(tx['volume_usd'] for tx in sell_txs)
                
                if abs(total_buy_volume - total_sell_volume) / max(total_buy_volume, total_sell_volume) < 0.1:
                    # Check timing - wash trades often happen close together
                    timestamps = [datetime.fromisoformat(tx['timestamp'].replace('Z', '+00:00')) for tx in txs]
                    timestamps.sort()
                    
                    rapid_sequences = 0
                    for i in range(1, len(timestamps)):
                        if (timestamps[i] - timestamps[i-1]).total_seconds() < 300:  # 5 minutes
                            rapid_sequences += 1
                    
                    if rapid_sequences / len(timestamps) > 0.5:  # More than 50% rapid sequences
                        wash_indicators += 1
                        suspicious_volume += total_buy_volume + total_sell_volume
        
        wash_score = suspicious_volume / total_volume if total_volume > 0 else 0
        return min(wash_score, 1.0)
    
    def _detect_coordinated_trading(self, transactions: List[Dict[str, Any]]) -> float:
        """Detect coordinated trading activity."""
        if len(transactions) < 20:
            return 0.0
        
        # Group transactions by time windows
        time_windows = {}
        window_size = 300  # 5-minute windows
        
        for tx in transactions:
            timestamp = datetime.fromisoformat(tx['timestamp'].replace('Z', '+00:00'))
            window_key = int(timestamp.timestamp() // window_size)
            
            if window_key not in time_windows:
                time_windows[window_key] = []
            time_windows[window_key].append(tx)
        
        coordination_score = 0.0
        
        for window_txs in time_windows.values():
            if len(window_txs) < 3:
                continue
            
            # Check for similar transaction patterns
            volumes = [tx['volume_usd'] for tx in window_txs]
            traders = [tx['trader_address'] for tx in window_txs]
            
            # Check volume similarity
            if len(set(volumes)) == 1:  # All volumes identical
                coordination_score = max(coordination_score, 0.9)
            elif len(volumes) > 1:
                avg_volume = sum(volumes) / len(volumes)
                volume_variance = sum((v - avg_volume) ** 2 for v in volumes) / len(volumes)
                volume_similarity = 1.0 - min(volume_variance / (avg_volume ** 2), 1.0) if avg_volume > 0 else 0
                coordination_score = max(coordination_score, volume_similarity * 0.7)
            
            # Check for unique traders (not the same trader repeating)
            unique_trader_ratio = len(set(traders)) / len(traders)
            if unique_trader_ratio > 0.8:  # Different traders but coordinated
                coordination_score = max(coordination_score, 0.8)
        
        return coordination_score
    
    def _calculate_gini_coefficient(self, values: List[float]) -> float:
        """Calculate Gini coefficient for inequality measurement."""
        if not values or len(values) < 2:
            return 0.0
        
        sorted_values = sorted(values)
        n = len(sorted_values)
        cumsum = 0
        
        for i, value in enumerate(sorted_values):
            cumsum += value * (2 * i - n + 1)
        
        total_sum = sum(sorted_values)
        if total_sum == 0:
            return 0.0
        
        return cumsum / (n * total_sum)
    
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
    
    def _detect_artificial_price_support(self, transactions: List[Dict[str, Any]]) -> float:
        """Detect artificial price support mechanisms."""
        if len(transactions) < 20:
            return 0.0
        
        # Look for consistent buying at specific price levels
        buy_txs = [tx for tx in transactions if tx['type'] == 'buy']
        if len(buy_txs) < 10:
            return 0.0
        
        # Group buy transactions by price levels
        price_levels = {}
        for tx in buy_txs:
            price_key = round(tx['price'], 6)  # Round to 6 decimal places
            if price_key not in price_levels:
                price_levels[price_key] = []
            price_levels[price_key].append(tx)
        
        # Find price levels with multiple purchases
        support_score = 0.0
        total_buy_volume = sum(tx['volume_usd'] for tx in buy_txs)
        
        for price, txs in price_levels.items():
            if len(txs) >= 3:  # 3+ transactions at same price
                level_volume = sum(tx['volume_usd'] for tx in txs)
                volume_ratio = level_volume / total_buy_volume if total_buy_volume > 0 else 0
                
                # Check if these transactions are from different traders
                unique_traders = len(set(tx['trader_address'] for tx in txs))
                trader_diversity = unique_traders / len(txs)
                
                # Higher score for coordinated support (same traders) at key levels
                if trader_diversity < 0.5 and volume_ratio > 0.1:
                    support_score = max(support_score, volume_ratio * (1 - trader_diversity))
        
        return min(support_score, 1.0)
    
    def _detect_volatility_manipulation(self, transactions: List[Dict[str, Any]]) -> float:
        """Detect artificial volatility creation."""
        if len(transactions) < 20:
            return 0.0
        
        prices = [tx['price'] for tx in transactions]
        volumes = [tx['volume_usd'] for tx in transactions]
        
        # Calculate price volatility
        if len(prices) < 2:
            return 0.0
        
        price_changes = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices)) if prices[i-1] > 0]
        
        if not price_changes:
            return 0.0
        
        volatility = statistics.stdev(price_changes)
        
        # Look for high volatility periods with high volume
        manipulation_score = 0.0
        window_size = 5
        
        for i in range(window_size, len(transactions) - window_size):
            window_volatility = statistics.stdev(price_changes[i-window_size:i+window_size]) if len(price_changes[i-window_size:i+window_size]) > 1 else 0
            window_volume = sum(volumes[i-window_size:i+window_size])
            avg_volume = sum(volumes) / len(volumes)
            
            if window_volatility > volatility * 2 and window_volume > avg_volume * window_size * 3:
                manipulation_score = max(manipulation_score, min(window_volatility * 10, 1.0))
        
        return manipulation_score
    
    def _detect_time_coordination(self, transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Detect time-based coordination patterns."""
        if len(transactions) < 10:
            return {'score': 0.0, 'window': None}
        
        # Analyze transaction timing patterns
        timestamps = [datetime.fromisoformat(tx['timestamp'].replace('Z', '+00:00')) for tx in transactions]
        timestamps.sort()
        
        # Look for clustering in time
        time_gaps = [(timestamps[i] - timestamps[i-1]).total_seconds() for i in range(1, len(timestamps))]
        
        if not time_gaps:
            return {'score': 0.0, 'window': None}
        
        avg_gap = sum(time_gaps) / len(time_gaps)
        
        # Count short gaps (potential coordination)
        short_gaps = len([gap for gap in time_gaps if gap < avg_gap * 0.1])
        coordination_ratio = short_gaps / len(time_gaps)
        
        return {
            'score': coordination_ratio,
            'window': f"{avg_gap:.1f}s average gap",
            'short_gap_count': short_gaps,
            'total_gaps': len(time_gaps)
        }
    
    def _detect_volume_coordination(self, transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Detect volume-based coordination patterns."""
        volumes = [tx['volume_usd'] for tx in transactions]
        
        if len(volumes) < 5:
            return {'score': 0.0}
        
        # Check for repeated volume amounts
        volume_counts = {}
        for volume in volumes:
            rounded_volume = round(volume, -2)  # Round to nearest 100
            volume_counts[rounded_volume] = volume_counts.get(rounded_volume, 0) + 1
        
        # Find most common volumes
        max_count = max(volume_counts.values())
        repeated_volume_ratio = max_count / len(volumes)
        
        return {
            'score': repeated_volume_ratio,
            'most_common_volume': max(volume_counts, key=volume_counts.get),
            'repetition_count': max_count
        }
    
    def _detect_price_coordination(self, transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Detect price impact coordination."""
        if len(transactions) < 10:
            return {'score': 0.0}
        
        # Analyze price movements and their timing
        buy_txs = [tx for tx in transactions if tx['type'] == 'buy']
        sell_txs = [tx for tx in transactions if tx['type'] == 'sell']
        
        coordination_score = 0.0
        
        # Check for synchronized price movements
        if len(buy_txs) >= 3 and len(sell_txs) >= 3:
            buy_prices = [tx['price'] for tx in buy_txs]
            sell_prices = [tx['price'] for tx in sell_txs]
            
            # Look for step-like price movements
            buy_price_changes = [abs(buy_prices[i] - buy_prices[i-1]) / buy_prices[i-1] 
                               for i in range(1, len(buy_prices)) if buy_prices[i-1] > 0]
            
            if buy_price_changes:
                # Check if price changes are unusually uniform
                avg_change = sum(buy_price_changes) / len(buy_price_changes)
                uniform_changes = len([c for c in buy_price_changes if abs(c - avg_change) / avg_change < 0.1])
                coordination_score = uniform_changes / len(buy_price_changes)
        
        return {'score': coordination_score}
    
    def _identify_suspicious_transactions(self, transactions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Identify individual suspicious transactions."""
        suspicious = []
        
        if len(transactions) < 5:
            return suspicious
        
        volumes = [tx['volume_usd'] for tx in transactions]
        avg_volume = sum(volumes) / len(volumes)
        volume_threshold = avg_volume * 10  # 10x average
        
        for tx in transactions:
            suspicion_factors = []
            
            # Volume anomaly
            if tx['volume_usd'] > volume_threshold:
                suspicion_factors.append('unusually_large_volume')
            
            # Round number volume (often indicates manual trading)
            if tx['volume_usd'] % 1000 == 0 and tx['volume_usd'] >= 10000:
                suspicion_factors.append('round_number_volume')
            
            # Gas price anomaly (very high gas suggests urgency/MEV)
            if tx.get('gas_price', 0) > 100:  # High gas price
                suspicion_factors.append('high_gas_price')
            
            if suspicion_factors:
                suspicious.append({
                    'transaction': tx,
                    'suspicion_factors': suspicion_factors,
                    'suspicion_score': len(suspicion_factors) / 3  # Normalize to 0-1
                })
        
        return suspicious[:10]  # Return top 10 most suspicious
    
    def _calculate_whale_price_impact(self, whale_txs: List[Dict[str, Any]], all_txs: List[Dict[str, Any]]) -> float:
        """Calculate the price impact of whale transactions."""
        if not whale_txs or len(all_txs) < 10:
            return 0.0
        
        total_impact = 0.0
        
        for whale_tx in whale_txs:
            whale_time = datetime.fromisoformat(whale_tx['timestamp'].replace('Z', '+00:00'))
            
            # Find transactions before and after whale transaction
            before_txs = [tx for tx in all_txs 
                         if datetime.fromisoformat(tx['timestamp'].replace('Z', '+00:00')) < whale_time]
            after_txs = [tx for tx in all_txs 
                        if datetime.fromisoformat(tx['timestamp'].replace('Z', '+00:00')) > whale_time]
            
            if before_txs and after_txs:
                price_before = before_txs[-1]['price']  # Last price before
                price_after = after_txs[0]['price']      # First price after
                
                impact = abs(price_after - price_before) / price_before if price_before > 0 else 0
                total_impact += impact
        
        return total_impact / len(whale_txs) if whale_txs else 0.0
    
    def _analyze_whale_timing(self, whale_txs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze timing patterns in whale transactions."""
        if len(whale_txs) < 2:
            return {}
        
        # Analyze time gaps between whale transactions
        timestamps = [datetime.fromisoformat(tx['timestamp'].replace('Z', '+00:00')) for tx in whale_txs]
        timestamps.sort()
        
        time_gaps = [(timestamps[i] - timestamps[i-1]).total_seconds() / 3600 for i in range(1, len(timestamps))]  # Hours
        
        return {
            'whale_transaction_count': len(whale_txs),
            'average_time_gap_hours': sum(time_gaps) / len(time_gaps) if time_gaps else 0,
            'min_time_gap_hours': min(time_gaps) if time_gaps else 0,
            'max_time_gap_hours': max(time_gaps) if time_gaps else 0,
            'coordinated_timing': len([gap for gap in time_gaps if gap < 1.0])  # Within 1 hour
        }
    
    def _calculate_market_risk_score(
        self,
        volume_analysis: Optional[VolumeAnalysis],
        manipulation_indicators: Optional[PriceManipulationIndicators],
        trading_patterns: List[TradingPattern],
        market_metrics: List[MarketMetric]
    ) -> float:
        """Calculate overall market structure risk score."""
        risk_factors = []
        
        # Volume analysis risk
        if volume_analysis:
            volume_risk = 0.0
            if volume_analysis.wash_trading_score > 0.3:
                volume_risk += 0.4
            if volume_analysis.volume_concentration > 0.8:
                volume_risk += 0.3
            if volume_analysis.unusual_volume_spikes > 5:
                volume_risk += 0.2
            risk_factors.append(min(volume_risk, 1.0))
        
        # Manipulation indicators risk
        if manipulation_indicators:
            manip_risk = (
                manipulation_indicators.pump_dump_score * 0.4 +
                manipulation_indicators.coordinated_activity_score * 0.3 +
                manipulation_indicators.artificial_price_support * 0.2 +
                manipulation_indicators.price_volatility_manipulation * 0.1
            )
            risk_factors.append(manip_risk)
        
        # Trading patterns risk
        pattern_risk = 0.0
        for pattern in trading_patterns:
            if pattern.severity == 'CRITICAL':
                pattern_risk = max(pattern_risk, 0.9)
            elif pattern.severity == 'HIGH':
                pattern_risk = max(pattern_risk, 0.7)
            elif pattern.severity == 'MEDIUM':
                pattern_risk = max(pattern_risk, 0.5)
        risk_factors.append(pattern_risk)
        
        # Market metrics risk
        metrics_risk = 0.0
        for metric in market_metrics:
            if metric.threshold_breached:
                metrics_risk = max(metrics_risk, metric.normalized_score)
        risk_factors.append(metrics_risk)
        
        return sum(risk_factors) / len(risk_factors) if risk_factors else 0.5
    
    def _generate_market_warnings(
        self,
        manipulation_indicators: Optional[PriceManipulationIndicators],
        trading_patterns: List[TradingPattern],
        volume_analysis: Optional[VolumeAnalysis]
    ) -> List[str]:
        """Generate warnings based on market analysis."""
        warnings = []
        
        # Manipulation warnings
        if manipulation_indicators:
            if manipulation_indicators.manipulation_risk_level == 'CRITICAL':
                warnings.append("CRITICAL: High probability of active price manipulation")
            elif manipulation_indicators.manipulation_risk_level == 'HIGH':
                warnings.append("HIGH RISK: Multiple manipulation indicators detected")
            
            if manipulation_indicators.pump_dump_score > 0.7:
                warnings.append("Pump and dump pattern detected in recent trading")
            
            if manipulation_indicators.coordinated_activity_score > 0.8:
                warnings.append("Coordinated trading activity detected")
        
        # Pattern warnings
        critical_patterns = [p for p in trading_patterns if p.severity == 'CRITICAL']
        high_patterns = [p for p in trading_patterns if p.severity == 'HIGH']
        
        if critical_patterns:
            warnings.append(f"CRITICAL: {len(critical_patterns)} critical market manipulation patterns")
        elif high_patterns:
            warnings.append(f"HIGH RISK: {len(high_patterns)} suspicious trading patterns")
        
        # Volume warnings
        if volume_analysis:
            if volume_analysis.wash_trading_score > 0.5:
                warnings.append("High wash trading activity detected")
            
            if volume_analysis.volume_concentration > 0.9:
                warnings.append("Extremely concentrated trading volume - manipulation risk")
        
        return warnings
    
    def _load_manipulation_patterns(self) -> List[Dict[str, Any]]:
        """Load known market manipulation patterns."""
        return [
            {
                'name': 'pump_and_dump',
                'indicators': ['rapid_price_increase', 'high_volume', 'subsequent_dump'],
                'threshold': 0.7
            },
            {
                'name': 'wash_trading',
                'indicators': ['same_trader_buy_sell', 'volume_inflation', 'minimal_price_impact'],
                'threshold': 0.6
            },
            {
                'name': 'coordinated_manipulation',
                'indicators': ['synchronized_trading', 'similar_volumes', 'time_coordination'],
                'threshold': 0.8
            }
        ]
    
    def _validate_inputs(self, token_address: str, context: Dict[str, Any]) -> bool:
        """Validate inputs for market analysis."""
        if not token_address or len(token_address) != 42:
            return False
        
        return True
    
    def _create_error_risk_score(self, error_message: str) -> RiskScore:
        """Create error risk score for failed analysis."""
        return RiskScore(
            category=self.get_category(),
            score=0.6,  # Medium-high risk when analysis fails
            confidence=0.2,
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
            analysis_time_ms=25000.0,
            warnings=["Market analysis timed out - results may be incomplete"],
            data_quality="POOR"
        )
    
    def _get_cached_analysis(self, token_address: str) -> Optional[Dict[str, Any]]:
        """Get cached market analysis if available and fresh."""
        if token_address in self.market_cache:
            result, timestamp = self.market_cache[token_address]
            age = datetime.now(timezone.utc) - timestamp
            
            if age.total_seconds() < (self.cache_ttl_minutes * 60):
                return result
            else:
                del self.market_cache[token_address]
        
        return None
    
    def _cache_analysis_result(self, token_address: str, result: Dict[str, Any]) -> None:
        """Cache market analysis result."""
        self.market_cache[token_address] = (result, datetime.now(timezone.utc))
        
        # Clean up old cache entries
        if len(self.market_cache) > 50:
            sorted_entries = sorted(
                self.market_cache.items(),
                key=lambda x: x[1][1]
            )
            for token, _ in sorted_entries[:10]:
                del self.market_cache[token]
    
    def _create_risk_score_from_cache(self, cached_result: Dict[str, Any]) -> RiskScore:
        """Create risk score from cached analysis."""
        volume_analysis = cached_result.get('volume_analysis')
        manipulation_indicators = cached_result.get('manipulation_indicators')
        trading_patterns = cached_result.get('trading_patterns', [])
        market_metrics = cached_result.get('market_metrics', [])
        
        risk_score = self._calculate_market_risk_score(
            volume_analysis, manipulation_indicators, trading_patterns, market_metrics
        )
        
        return RiskScore(
            category=self.get_category(),
            score=risk_score,
            confidence=0.7,  # Good confidence for cached analysis
            details={**cached_result, 'from_cache': True},
            analysis_time_ms=5.0,  # Fast cache retrieval
            warnings=self._generate_market_warnings(manipulation_indicators, trading_patterns, volume_analysis),
            data_quality="GOOD",
            last_updated=datetime.now(timezone.utc).isoformat()
        )
    
    def _assess_market_data_quality(self, market_data: Dict[str, Any]) -> str:
        """Assess the quality of market data used for analysis."""
        transactions = market_data.get('transactions', [])
        
        if len(transactions) < 20:
            return "POOR"
        elif len(transactions) < 50:
            return "FAIR"
        elif len(transactions) < 100:
            return "GOOD"
        else:
            return "EXCELLENT"
    
    def _calculate_analysis_confidence(
        self,
        market_data: Dict[str, Any],
        trading_patterns: List[TradingPattern]
    ) -> float:
        """Calculate confidence level for market analysis."""
        confidence_factors = []
        
        # Data volume factor
        tx_count = len(market_data.get('transactions', []))
        data_factor = min(tx_count / 100, 1.0)
        confidence_factors.append(data_factor)
        
        # Pattern detection confidence
        if trading_patterns:
            avg_pattern_confidence = sum(p.confidence for p in trading_patterns) / len(trading_patterns)
            confidence_factors.append(avg_pattern_confidence)
        else:
            confidence_factors.append(0.7)  # No patterns detected is also meaningful
        
        # Data freshness factor
        confidence_factors.append(0.8)  # Assume good freshness for mock data
        
        return sum(confidence_factors) / len(confidence_factors)


# Export the analyzer class
__all__ = [
    'MarketAnalyzer',
    'TradingPattern',
    'MarketMetric', 
    'VolumeAnalysis',
    'PriceManipulationIndicators'
]