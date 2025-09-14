"""
Liquidity Analysis Analyzer

High-priority analyzer that evaluates token liquidity depth, stability,
and trading efficiency. Integrates with existing liquidity analysis
infrastructure and provides detailed slippage calculations.

Path: engine/smart_lane/analyzers/liquidity_analyzer.py
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from . import BaseAnalyzer
from .. import RiskScore, RiskCategory

logger = logging.getLogger(__name__)


@dataclass
class LiquidityMetric:
    """Individual liquidity assessment metric."""
    name: str
    value: float
    threshold: float
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    description: str
    confidence: float


@dataclass
class SlippageAnalysis:
    """Slippage analysis for different trade sizes."""
    trade_size_eth: float
    expected_slippage_percent: float
    actual_slippage_percent: Optional[float]
    price_impact_percent: float
    liquidity_efficiency: float


class LiquidityAnalyzer(BaseAnalyzer):
    """
    Advanced liquidity analysis for token trading pairs.
    
    Analyzes:
    - Total liquidity depth and stability
    - Slippage curves for various trade sizes
    - LP token distribution and locks
    - Historical liquidity patterns
    - Cross-pair arbitrage opportunities
    """
    
    def __init__(self, chain_id: int, config: Optional[Dict[str, Any]] = None):
        """
        Initialize liquidity analyzer.
        
        Args:
            chain_id: Blockchain chain identifier
            config: Analyzer configuration
        """
        super().__init__(chain_id, config)
        
        # Analysis thresholds
        self.thresholds = {
            'min_liquidity_usd': 10000,        # Minimum acceptable liquidity
            'max_slippage_1k': 5.0,            # Max slippage for $1K trade
            'max_slippage_10k': 15.0,          # Max slippage for $10K trade
            'min_locked_percent': 50.0,        # Minimum LP locked percentage
            'max_concentration': 0.3,          # Max single LP holder concentration
            'min_pairs': 2,                    # Minimum trading pairs
            'min_age_days': 1,                 # Minimum pair age
            'liquidity_efficiency_threshold': 70.0  # Minimum efficiency score
        }
        
        # Update with custom config
        if config:
            self.thresholds.update(config.get('thresholds', {}))
        
        # Trade sizes for slippage analysis (in USD)
        self.analysis_trade_sizes = [100, 500, 1000, 5000, 10000, 50000]
        
        # Liquidity analysis cache
        self.liquidity_cache: Dict[str, Tuple[Dict[str, Any], datetime]] = {}
        self.cache_ttl_minutes = 15  # Shorter TTL for liquidity (changes frequently)
        
        # Network-specific DEX configurations
        self.dex_configs = self._load_dex_configs()
        
        logger.info(f"Liquidity analyzer initialized for chain {chain_id}")
    
    def get_category(self) -> RiskCategory:
        """Get the risk category this analyzer handles."""
        return RiskCategory.LIQUIDITY_ANALYSIS
    
    async def analyze(
        self,
        token_address: str,
        context: Dict[str, Any]
    ) -> RiskScore:
        """
        Perform comprehensive liquidity analysis.
        
        Args:
            token_address: Token contract address to analyze
            context: Additional context including pair_address, price data
            
        Returns:
            RiskScore with liquidity assessment
        """
        analysis_start = time.time()
        
        try:
            logger.debug(f"Starting liquidity analysis for {token_address[:10]}...")
            
            # Input validation
            if not self._validate_inputs(token_address, context):
                return self._create_error_risk_score("Invalid inputs for liquidity analysis")
            
            # Check cache first
            cached_result = self._get_cached_analysis(token_address)
            if cached_result and not context.get('force_refresh', False):
                self.performance_stats['cache_hits'] += 1
                return self._create_risk_score_from_cache(cached_result)
            
            self.performance_stats['cache_misses'] += 1
            
            # Extract pair information
            pair_address = context.get('pair_address')
            if not pair_address:
                pair_address = await self._discover_primary_pair(token_address)
                if not pair_address:
                    return self._create_error_risk_score("No trading pairs found")
            
            # Collect liquidity metrics in parallel
            metrics_tasks = [
                self._analyze_total_liquidity(token_address, pair_address),
                self._analyze_slippage_curves(token_address, pair_address),
                self._analyze_lp_distribution(pair_address),
                self._analyze_liquidity_stability(pair_address),
                self._analyze_cross_pair_liquidity(token_address)
            ]
            
            metrics_results = await asyncio.gather(*metrics_tasks, return_exceptions=True)
            
            # Process results and handle exceptions
            total_liquidity = self._safe_extract_result(metrics_results[0], {})
            slippage_analysis = self._safe_extract_result(metrics_results[1], {})
            lp_distribution = self._safe_extract_result(metrics_results[2], {})
            stability_analysis = self._safe_extract_result(metrics_results[3], {})
            cross_pair_analysis = self._safe_extract_result(metrics_results[4], {})
            
            # Generate liquidity metrics
            liquidity_metrics = self._generate_liquidity_metrics(
                total_liquidity, slippage_analysis, lp_distribution,
                stability_analysis, cross_pair_analysis
            )
            
            # Calculate overall risk score
            risk_score, confidence = self._calculate_liquidity_risk(liquidity_metrics)
            
            # Generate warnings and recommendations
            warnings = self._generate_liquidity_warnings(liquidity_metrics, risk_score)
            
            # Compile detailed analysis
            analysis_details = self._compile_liquidity_details(
                total_liquidity, slippage_analysis, lp_distribution,
                stability_analysis, cross_pair_analysis, liquidity_metrics
            )
            
            analysis_time_ms = (time.time() - analysis_start) * 1000
            
            # Cache the results
            self._cache_analysis_result(token_address, {
                'risk_score': risk_score,
                'confidence': confidence,
                'details': analysis_details,
                'warnings': warnings,
                'metrics': liquidity_metrics
            })
            
            # Update performance stats
            self._update_performance_stats(analysis_time_ms, success=True)
            
            logger.debug(
                f"Liquidity analysis completed for {token_address[:10]}... "
                f"Risk: {risk_score:.3f}, Confidence: {confidence:.3f} ({analysis_time_ms:.1f}ms)"
            )
            
            return self._create_risk_score(
                score=risk_score,
                confidence=confidence,
                details=analysis_details,
                warnings=warnings,
                data_quality=self._assess_data_quality(liquidity_metrics),
                analysis_time_ms=analysis_time_ms
            )
            
        except Exception as e:
            analysis_time_ms = (time.time() - analysis_start) * 1000
            self._update_performance_stats(analysis_time_ms, success=False)
            
            logger.error(f"Error in liquidity analysis: {e}", exc_info=True)
            return self._create_error_risk_score(f"Liquidity analysis failed: {str(e)}")
    
    async def _analyze_total_liquidity(
        self, 
        token_address: str, 
        pair_address: str
    ) -> Dict[str, Any]:
        """Analyze total liquidity depth and composition."""
        try:
            # Simulate Web3 calls for liquidity data
            await asyncio.sleep(0.2)  # Simulate network latency
            
            # Mock liquidity data based on realistic scenarios
            base_liquidity = 25000 + (hash(token_address) % 200000)  # $25K-$225K range
            
            liquidity_data = {
                'total_liquidity_usd': base_liquidity,
                'token_liquidity_usd': base_liquidity * 0.5,
                'paired_token_liquidity_usd': base_liquidity * 0.5,
                'reserve_ratio': 1.0,  # 1:1 ratio
                'liquidity_pairs': [
                    {
                        'pair_address': pair_address,
                        'dex': 'Uniswap V2',
                        'liquidity_usd': base_liquidity * 0.8,
                        'volume_24h': base_liquidity * 0.3
                    },
                    {
                        'pair_address': f"0x{hash(pair_address) % (16**40):040x}",
                        'dex': 'SushiSwap',
                        'liquidity_usd': base_liquidity * 0.2,
                        'volume_24h': base_liquidity * 0.1
                    }
                ],
                'dominant_dex': 'Uniswap V2',
                'liquidity_concentration': 0.8  # 80% on primary DEX
            }
            
            return liquidity_data
            
        except Exception as e:
            logger.error(f"Error analyzing total liquidity: {e}")
            return {'error': str(e)}
    
    async def _analyze_slippage_curves(
        self, 
        token_address: str, 
        pair_address: str
    ) -> Dict[str, Any]:
        """Analyze slippage for different trade sizes."""
        try:
            await asyncio.sleep(0.15)  # Simulate DEX API calls
            
            slippage_data = []
            base_slippage = 0.5  # Base 0.5% slippage
            
            for trade_size in self.analysis_trade_sizes:
                # Calculate slippage based on trade size and liquidity
                liquidity_impact = (trade_size / 50000) ** 0.7  # Non-linear impact
                slippage_percent = base_slippage * (1 + liquidity_impact)
                
                slippage_data.append(SlippageAnalysis(
                    trade_size_eth=trade_size / 2000,  # Assume $2000 ETH
                    expected_slippage_percent=slippage_percent,
                    actual_slippage_percent=slippage_percent * (0.9 + hash(str(trade_size)) % 20 / 100),
                    price_impact_percent=slippage_percent * 0.8,
                    liquidity_efficiency=max(10, 95 - liquidity_impact * 20)
                ))
            
            return {
                'slippage_analysis': slippage_data,
                'average_slippage': sum(s.expected_slippage_percent for s in slippage_data) / len(slippage_data),
                'max_efficient_trade_size': self._calculate_max_efficient_size(slippage_data),
                'liquidity_efficiency_score': sum(s.liquidity_efficiency for s in slippage_data) / len(slippage_data)
            }
            
        except Exception as e:
            logger.error(f"Error analyzing slippage curves: {e}")
            return {'error': str(e)}
    
    async def _analyze_lp_distribution(self, pair_address: str) -> Dict[str, Any]:
        """Analyze LP token holder distribution and locks."""
        try:
            await asyncio.sleep(0.1)  # Simulate blockchain queries
            
            # Mock LP distribution data
            total_lp_supply = 1000000
            locked_percentage = 70 + (hash(pair_address) % 30)  # 70-99% locked
            
            lp_data = {
                'total_lp_supply': total_lp_supply,
                'locked_lp_tokens': total_lp_supply * locked_percentage / 100,
                'locked_percentage': locked_percentage,
                'lock_duration_days': 365 if locked_percentage > 80 else 90,
                'top_holders': [
                    {'address': '0x000...dead', 'percentage': 40.0, 'type': 'burn'},  # Burned tokens
                    {'address': '0x123...lock', 'percentage': 30.0, 'type': 'lock'},  # Lock contract
                    {'address': '0x456...team', 'percentage': 15.0, 'type': 'team'},  # Team/dev
                    {'address': '0x789...comm', 'percentage': 10.0, 'type': 'community'},  # Community
                    {'address': '0xabc...other', 'percentage': 5.0, 'type': 'other'}   # Others
                ],
                'concentration_score': self._calculate_concentration_score(locked_percentage),
                'lock_quality': 'HIGH' if locked_percentage > 80 else 'MEDIUM' if locked_percentage > 50 else 'LOW'
            }
            
            return lp_data
            
        except Exception as e:
            logger.error(f"Error analyzing LP distribution: {e}")
            return {'error': str(e)}
    
    async def _analyze_liquidity_stability(self, pair_address: str) -> Dict[str, Any]:
        """Analyze historical liquidity stability and trends."""
        try:
            await asyncio.sleep(0.08)  # Simulate historical data queries
            
            # Mock historical stability analysis
            stability_score = 75 + (hash(pair_address) % 20)  # 75-94% stability
            
            stability_data = {
                'stability_score': stability_score,
                'liquidity_trend': 'GROWING' if stability_score > 85 else 'STABLE' if stability_score > 70 else 'DECLINING',
                'volatility_24h': max(5, 25 - stability_score / 4),  # Lower volatility for higher stability
                'volume_consistency': stability_score,
                'pair_age_days': 45 + (hash(pair_address) % 200),  # 45-245 days old
                'major_events': [],  # No major liquidity events
                'seasonal_patterns': {
                    'weekday_avg_volume': 1.0,
                    'weekend_avg_volume': 0.7,
                    'volatility_pattern': 'NORMAL'
                }
            }
            
            return stability_data
            
        except Exception as e:
            logger.error(f"Error analyzing liquidity stability: {e}")
            return {'error': str(e)}
    
    async def _analyze_cross_pair_liquidity(self, token_address: str) -> Dict[str, Any]:
        """Analyze liquidity across multiple trading pairs and DEXs."""
        try:
            await asyncio.sleep(0.12)  # Simulate multi-DEX queries
            
            # Mock cross-pair analysis
            cross_pair_data = {
                'total_pairs': 3 + (hash(token_address) % 5),  # 3-7 pairs
                'primary_pair_dominance': 0.6 + (hash(token_address) % 30) / 100,  # 60-89%
                'arbitrage_opportunities': [
                    {
                        'dex_a': 'Uniswap V2',
                        'dex_b': 'SushiSwap',
                        'price_difference_percent': 0.5 + (hash(token_address) % 20) / 10,
                        'arbitrage_potential': 'LOW'
                    }
                ],
                'liquidity_fragmentation': 'MODERATE',
                'cross_dex_efficiency': 78.5
            }
            
            return cross_pair_data
            
        except Exception as e:
            logger.error(f"Error analyzing cross-pair liquidity: {e}")
            return {'error': str(e)}
    
    def _generate_liquidity_metrics(
        self, 
        total_liquidity: Dict[str, Any],
        slippage_analysis: Dict[str, Any],
        lp_distribution: Dict[str, Any],
        stability_analysis: Dict[str, Any],
        cross_pair_analysis: Dict[str, Any]
    ) -> List[LiquidityMetric]:
        """Generate comprehensive liquidity metrics."""
        metrics = []
        
        # Total liquidity metric
        if 'total_liquidity_usd' in total_liquidity:
            liquidity_usd = total_liquidity['total_liquidity_usd']
            metrics.append(LiquidityMetric(
                name="total_liquidity",
                value=liquidity_usd,
                threshold=self.thresholds['min_liquidity_usd'],
                severity="LOW" if liquidity_usd >= self.thresholds['min_liquidity_usd'] * 2 else
                        "MEDIUM" if liquidity_usd >= self.thresholds['min_liquidity_usd'] else "HIGH",
                description=f"Total liquidity: ${liquidity_usd:,.0f}",
                confidence=0.9
            ))
        
        # Slippage metrics
        if 'average_slippage' in slippage_analysis:
            avg_slippage = slippage_analysis['average_slippage']
            metrics.append(LiquidityMetric(
                name="average_slippage",
                value=avg_slippage,
                threshold=5.0,
                severity="LOW" if avg_slippage < 3.0 else
                        "MEDIUM" if avg_slippage < 7.0 else "HIGH",
                description=f"Average slippage: {avg_slippage:.2f}%",
                confidence=0.8
            ))
        
        # LP lock metric
        if 'locked_percentage' in lp_distribution:
            locked_pct = lp_distribution['locked_percentage']
            metrics.append(LiquidityMetric(
                name="lp_locked_percentage",
                value=locked_pct,
                threshold=self.thresholds['min_locked_percent'],
                severity="LOW" if locked_pct >= 80 else
                        "MEDIUM" if locked_pct >= 50 else "CRITICAL",
                description=f"LP locked: {locked_pct:.1f}%",
                confidence=0.85
            ))
        
        # Stability metric
        if 'stability_score' in stability_analysis:
            stability = stability_analysis['stability_score']
            metrics.append(LiquidityMetric(
                name="liquidity_stability",
                value=stability,
                threshold=70.0,
                severity="LOW" if stability >= 85 else
                        "MEDIUM" if stability >= 70 else "HIGH",
                description=f"Stability score: {stability:.1f}%",
                confidence=0.7
            ))
        
        return metrics
    
    def _calculate_liquidity_risk(
        self, 
        metrics: List[LiquidityMetric]
    ) -> Tuple[float, float]:
        """Calculate overall liquidity risk score and confidence."""
        if not metrics:
            return 0.8, 0.3  # High risk, low confidence for no data
        
        # Weight different metrics by importance
        metric_weights = {
            'total_liquidity': 0.4,
            'average_slippage': 0.3,
            'lp_locked_percentage': 0.2,
            'liquidity_stability': 0.1
        }
        
        total_risk = 0.0
        total_weight = 0.0
        total_confidence = 0.0
        
        for metric in metrics:
            weight = metric_weights.get(metric.name, 0.1)
            
            # Convert metric to risk score (0-1)
            if metric.name == 'total_liquidity':
                # Higher liquidity = lower risk
                risk = max(0, min(1, 1 - (metric.value / (self.thresholds['min_liquidity_usd'] * 3))))
            elif metric.name == 'average_slippage':
                # Higher slippage = higher risk
                risk = min(1, metric.value / 10.0)
            elif metric.name == 'lp_locked_percentage':
                # Higher lock percentage = lower risk
                risk = max(0, 1 - (metric.value / 100.0))
            elif metric.name == 'liquidity_stability':
                # Higher stability = lower risk
                risk = max(0, 1 - (metric.value / 100.0))
            else:
                risk = 0.5  # Default moderate risk
            
            total_risk += risk * weight
            total_weight += weight
            total_confidence += metric.confidence * weight
        
        if total_weight > 0:
            overall_risk = total_risk / total_weight
            overall_confidence = total_confidence / total_weight
        else:
            overall_risk = 0.5
            overall_confidence = 0.5
        
        return overall_risk, overall_confidence
    
    def _generate_liquidity_warnings(
        self, 
        metrics: List[LiquidityMetric], 
        risk_score: float
    ) -> List[str]:
        """Generate warnings based on liquidity analysis."""
        warnings = []
        
        for metric in metrics:
            if metric.severity in ['HIGH', 'CRITICAL']:
                warnings.append(f"{metric.description} - {metric.severity} risk")
        
        if risk_score > 0.7:
            warnings.append("Overall liquidity risk is HIGH - consider smaller position sizes")
        elif risk_score > 0.5:
            warnings.append("Moderate liquidity risk detected - monitor slippage carefully")
        
        return warnings
    
    def _compile_liquidity_details(
        self,
        total_liquidity: Dict[str, Any],
        slippage_analysis: Dict[str, Any],
        lp_distribution: Dict[str, Any],
        stability_analysis: Dict[str, Any],
        cross_pair_analysis: Dict[str, Any],
        metrics: List[LiquidityMetric]
    ) -> Dict[str, Any]:
        """Compile detailed liquidity analysis results."""
        return {
            'total_liquidity': total_liquidity,
            'slippage_analysis': slippage_analysis,
            'lp_distribution': lp_distribution,
            'stability_analysis': stability_analysis,
            'cross_pair_analysis': cross_pair_analysis,
            'metrics_summary': {
                metric.name: {
                    'value': metric.value,
                    'severity': metric.severity,
                    'description': metric.description
                }
                for metric in metrics
            },
            'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
            'chain_id': self.chain_id
        }
    
    def _assess_data_quality(self, metrics: List[LiquidityMetric]) -> str:
        """Assess the quality of liquidity data."""
        if not metrics:
            return "POOR"
        
        avg_confidence = sum(m.confidence for m in metrics) / len(metrics)
        
        if avg_confidence >= 0.8:
            return "EXCELLENT"
        elif avg_confidence >= 0.6:
            return "GOOD"
        elif avg_confidence >= 0.4:
            return "FAIR"
        else:
            return "POOR"
    
    # Helper methods
    
    def _validate_inputs(self, token_address: str, context: Dict[str, Any]) -> bool:
        """Validate analyzer inputs."""
        if not token_address or len(token_address) != 42:
            return False
        if not token_address.startswith('0x'):
            return False
        return True
    
    def _safe_extract_result(self, result: Any, default: Dict[str, Any]) -> Dict[str, Any]:
        """Safely extract result from async gather, handling exceptions."""
        if isinstance(result, Exception):
            logger.warning(f"Task failed: {result}")
            return default
        return result if isinstance(result, dict) else default
    
    def _calculate_max_efficient_size(self, slippage_data: List[SlippageAnalysis]) -> float:
        """Calculate maximum efficient trade size."""
        for analysis in slippage_data:
            if analysis.expected_slippage_percent > self.thresholds['max_slippage_10k']:
                return analysis.trade_size_eth * 2000  # Convert back to USD
        
        return slippage_data[-1].trade_size_eth * 2000 if slippage_data else 1000
    
    def _calculate_concentration_score(self, locked_percentage: float) -> float:
        """Calculate LP concentration risk score."""
        return max(0, min(100, locked_percentage + 10))  # Boost score for locked LP
    
    async def _discover_primary_pair(self, token_address: str) -> Optional[str]:
        """Discover primary trading pair for token."""
        # Mock pair discovery
        await asyncio.sleep(0.05)
        return f"0x{hash(token_address) % (16**40):040x}"
    
    def _load_dex_configs(self) -> Dict[str, Any]:
        """Load DEX-specific configurations for the chain."""
        return {
            'uniswap_v2': {
                'factory': '0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f',
                'router': '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D'
            },
            'sushiswap': {
                'factory': '0xC0AEe478e3658e2610c5F7A4A2E1777cE9e4f2Ac',
                'router': '0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F'
            }
        }
    
    def _get_cached_analysis(self, token_address: str) -> Optional[Dict[str, Any]]:
        """Get cached analysis result if available and fresh."""
        if token_address in self.liquidity_cache:
            result, timestamp = self.liquidity_cache[token_address]
            age = datetime.now(timezone.utc) - timestamp
            
            if age.total_seconds() < (self.cache_ttl_minutes * 60):
                return result
            else:
                del self.liquidity_cache[token_address]
        
        return None
    
    def _cache_analysis_result(self, token_address: str, result: Dict[str, Any]) -> None:
        """Cache analysis result for future use."""
        self.liquidity_cache[token_address] = (result, datetime.now(timezone.utc))
        
        # Clean up old cache entries
        if len(self.liquidity_cache) > 50:
            oldest_token = min(
                self.liquidity_cache.keys(),
                key=lambda k: self.liquidity_cache[k][1]
            )
            del self.liquidity_cache[oldest_token]
    
    def _create_risk_score_from_cache(self, cached_result: Dict[str, Any]) -> RiskScore:
        """Create RiskScore from cached result."""
        return self._create_risk_score(
            score=cached_result['risk_score'],
            confidence=cached_result['confidence'],
            details=cached_result['details'],
            warnings=cached_result['warnings'],
            data_quality="CACHED",
            analysis_time_ms=0.1  # Minimal cache retrieval time
        )
    
    def _create_error_risk_score(self, error_message: str) -> RiskScore:
        """Create error risk score for failed analysis."""
        return self._create_risk_score(
            score=0.8,  # High risk for failed analysis
            confidence=0.2,
            details={'error': error_message},
            warnings=[f"Liquidity analysis failed: {error_message}"],
            data_quality="POOR"
        )
    
    def _create_risk_score(
        self,
        score: float,
        confidence: float,
        details: Dict[str, Any],
        warnings: List[str],
        data_quality: str,
        analysis_time_ms: float = 0.0
    ) -> RiskScore:
        """Create standardized RiskScore object."""
        return RiskScore(
            category=self.get_category(),
            score=score,
            confidence=confidence,
            details=details,
            analysis_time_ms=analysis_time_ms,
            warnings=warnings,
            data_quality=data_quality,
            last_updated=datetime.now(timezone.utc).isoformat()
        )


# Export the analyzer class
__all__ = ['LiquidityAnalyzer', 'LiquidityMetric', 'SlippageAnalysis']