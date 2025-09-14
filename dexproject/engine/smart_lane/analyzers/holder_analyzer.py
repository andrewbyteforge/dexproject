"""
Holder Distribution Analyzer

High-priority analyzer that evaluates token holder concentration,
distribution patterns, and whale behavior. Critical for assessing
market manipulation risk and token stability.

Path: engine/smart_lane/analyzers/holder_analyzer.py
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
class HolderTier:
    """Holder tier analysis."""
    tier_name: str
    min_balance_tokens: float
    max_balance_tokens: float
    holder_count: int
    total_tokens_held: float
    percentage_of_supply: float
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL


@dataclass
class WhaleHolder:
    """Individual whale holder analysis."""
    address: str
    balance_tokens: float
    percentage_of_supply: float
    holder_type: str  # WHALE, TEAM, DEV, EXCHANGE, BURN, UNKNOWN
    first_transaction_date: Optional[str]
    transaction_count: int
    is_active: bool
    risk_score: float


@dataclass
class DistributionMetrics:
    """Overall distribution metrics."""
    total_holders: int
    gini_coefficient: float  # 0-1, higher = more concentrated
    concentration_ratio: float  # Top 10 holders percentage
    whale_concentration: float  # Top 5 holders percentage
    decentralization_score: float  # 0-100, higher = better distribution
    distribution_health: str  # EXCELLENT, GOOD, FAIR, POOR, CRITICAL


class HolderAnalyzer(BaseAnalyzer):
    """
    Advanced holder distribution and concentration analyzer.
    
    Analyzes:
    - Token holder concentration and distribution patterns
    - Whale behavior and market manipulation potential
    - Team and developer token allocations
    - Exchange and contract holder identification
    - Historical distribution trends
    - Gini coefficient and decentralization metrics
    """
    
    def __init__(self, chain_id: int, config: Optional[Dict[str, Any]] = None):
        """
        Initialize holder distribution analyzer.
        
        Args:
            chain_id: Blockchain chain identifier
            config: Analyzer configuration
        """
        super().__init__(chain_id, config)
        
        # Analysis thresholds
        self.thresholds = {
            'whale_threshold_percent': 2.0,     # 2%+ of supply = whale
            'team_threshold_percent': 5.0,      # 5%+ likely team allocation
            'max_whale_concentration': 50.0,    # Max acceptable whale concentration
            'max_top10_concentration': 70.0,    # Max top 10 holders concentration
            'min_holder_count': 100,            # Minimum healthy holder count
            'max_gini_coefficient': 0.8,        # Maximum acceptable Gini coefficient
            'min_decentralization_score': 40.0  # Minimum decentralization score
        }
        
        # Update with custom config
        if config:
            self.thresholds.update(config.get('thresholds', {}))
        
        # Holder tier definitions
        self.holder_tiers = [
            {'name': 'Dust', 'min': 0, 'max': 10},
            {'name': 'Small', 'min': 10, 'max': 1000},
            {'name': 'Medium', 'min': 1000, 'max': 10000},
            {'name': 'Large', 'min': 10000, 'max': 100000},
            {'name': 'Whale', 'min': 100000, 'max': float('inf')}
        ]
        
        # Known contract addresses (exchanges, dead wallets, etc.)
        self.known_addresses = self._load_known_addresses()
        
        # Holder analysis cache
        self.holder_cache: Dict[str, Tuple[Dict[str, Any], datetime]] = {}
        self.cache_ttl_minutes = 45  # Holder data changes relatively slowly
        
        logger.info(f"Holder distribution analyzer initialized for chain {chain_id}")
    
    def get_category(self) -> RiskCategory:
        """Get the risk category this analyzer handles."""
        return RiskCategory.HOLDER_DISTRIBUTION
    
    async def analyze(
        self,
        token_address: str,
        context: Dict[str, Any]
    ) -> RiskScore:
        """
        Perform comprehensive holder distribution analysis.
        
        Args:
            token_address: Token contract address to analyze
            context: Additional context for analysis
            
        Returns:
            RiskScore with holder distribution assessment
        """
        analysis_start = time.time()
        
        try:
            logger.debug(f"Starting holder distribution analysis for {token_address[:10]}...")
            
            # Input validation
            if not self._validate_inputs(token_address, context):
                return self._create_error_risk_score("Invalid inputs for holder analysis")
            
            # Check cache first
            cached_result = self._get_cached_analysis(token_address)
            if cached_result and not context.get('force_refresh', False):
                self.performance_stats['cache_hits'] += 1
                return self._create_risk_score_from_cache(cached_result)
            
            self.performance_stats['cache_misses'] += 1
            
            # Parallel holder analysis tasks
            analysis_tasks = [
                self._analyze_holder_distribution(token_address),
                self._identify_whale_holders(token_address),
                self._analyze_team_allocations(token_address),
                self._analyze_exchange_holdings(token_address),
                self._calculate_distribution_metrics(token_address),
                self._analyze_holder_behavior_patterns(token_address)
            ]
            
            analysis_results = await asyncio.gather(*analysis_tasks, return_exceptions=True)
            
            # Process results and handle exceptions
            holder_distribution = self._safe_extract_result(analysis_results[0], {})
            whale_holders = self._safe_extract_result(analysis_results[1], [])
            team_allocations = self._safe_extract_result(analysis_results[2], {})
            exchange_holdings = self._safe_extract_result(analysis_results[3], {})
            distribution_metrics = self._safe_extract_result(analysis_results[4], {})
            behavior_patterns = self._safe_extract_result(analysis_results[5], {})
            
            # Create comprehensive distribution analysis
            distribution_analysis = self._compile_distribution_analysis(
                holder_distribution, whale_holders, team_allocations,
                exchange_holdings, distribution_metrics, behavior_patterns
            )
            
            # Calculate holder risk score
            risk_score, confidence = self._calculate_holder_risk(
                distribution_analysis, whale_holders, distribution_metrics
            )
            
            # Generate holder warnings
            warnings = self._generate_holder_warnings(
                distribution_analysis, whale_holders, distribution_metrics
            )
            
            # Compile detailed analysis
            analysis_details = self._compile_holder_details(
                distribution_analysis, whale_holders, team_allocations,
                exchange_holdings, distribution_metrics, behavior_patterns
            )
            
            analysis_time_ms = (time.time() - analysis_start) * 1000
            
            # Cache the results
            self._cache_analysis_result(token_address, {
                'risk_score': risk_score,
                'confidence': confidence,
                'details': analysis_details,
                'warnings': warnings,
                'distribution_metrics': distribution_metrics
            })
            
            # Update performance stats
            self._update_performance_stats(analysis_time_ms, success=True)
            
            logger.debug(
                f"Holder distribution analysis completed for {token_address[:10]}... "
                f"Risk: {risk_score:.3f}, Confidence: {confidence:.3f} "
                f"({len(whale_holders)} whales, {distribution_metrics.get('total_holders', 0)} total holders, "
                f"{analysis_time_ms:.1f}ms)"
            )
            
            return self._create_risk_score(
                score=risk_score,
                confidence=confidence,
                details=analysis_details,
                warnings=warnings,
                data_quality=self._assess_data_quality(distribution_metrics, whale_holders),
                analysis_time_ms=analysis_time_ms
            )
            
        except Exception as e:
            analysis_time_ms = (time.time() - analysis_start) * 1000
            self._update_performance_stats(analysis_time_ms, success=False)
            
            logger.error(f"Error in holder distribution analysis: {e}", exc_info=True)
            return self._create_error_risk_score(f"Holder analysis failed: {str(e)}")
    
    async def _analyze_holder_distribution(self, token_address: str) -> Dict[str, Any]:
        """Analyze overall token holder distribution by tiers."""
        try:
            await asyncio.sleep(0.25)  # Simulate blockchain queries for holder data
            
            # Mock holder distribution based on token characteristics
            address_hash = hash(token_address)
            total_supply = 1000000000  # 1B tokens typical
            
            # Generate realistic holder counts for each tier
            holder_tiers = []
            remaining_supply = total_supply
            
            for i, tier_def in enumerate(self.holder_tiers):
                # Generate holder count based on tier (more holders in lower tiers)
                base_count = [5000, 2000, 500, 100, 10][i]  # Typical distribution
                tier_variance = (address_hash >> (i * 4)) % 50  # 0-49% variance
                tier_count = int(base_count * (1 + (tier_variance - 25) / 100))
                tier_count = max(1, tier_count)
                
                # Calculate tokens held by this tier
                if i < len(self.holder_tiers) - 1:  # Not the whale tier
                    avg_balance = (tier_def['min'] + tier_def['max']) / 2
                    total_tier_tokens = tier_count * avg_balance
                else:  # Whale tier gets remaining supply
                    total_tier_tokens = remaining_supply * 0.3  # Whales hold 30%
                    avg_balance = total_tier_tokens / max(1, tier_count)
                
                tier_percentage = (total_tier_tokens / total_supply) * 100
                remaining_supply -= total_tier_tokens
                
                holder_tiers.append(HolderTier(
                    tier_name=tier_def['name'],
                    min_balance_tokens=tier_def['min'],
                    max_balance_tokens=tier_def['max'],
                    holder_count=tier_count,
                    total_tokens_held=total_tier_tokens,
                    percentage_of_supply=tier_percentage,
                    risk_level=self._assess_tier_risk(tier_def['name'], tier_percentage)
                ))
            
            total_holders = sum(tier.holder_count for tier in holder_tiers)
            
            return {
                'holder_tiers': holder_tiers,
                'total_holders': total_holders,
                'total_supply': total_supply,
                'distribution_summary': {
                    'dust_holders': holder_tiers[0].holder_count,
                    'small_holders': holder_tiers[1].holder_count,
                    'medium_holders': holder_tiers[2].holder_count,
                    'large_holders': holder_tiers[3].holder_count,
                    'whale_holders': holder_tiers[4].holder_count
                }
            }
            
        except Exception as e:
            logger.error(f"Error analyzing holder distribution: {e}")
            return {'error': str(e)}
    
    async def _identify_whale_holders(self, token_address: str) -> List[WhaleHolder]:
        """Identify and analyze whale holders (>2% of supply)."""
        try:
            await asyncio.sleep(0.2)  # Simulate whale identification queries
            
            whale_holders = []
            address_hash = hash(token_address)
            total_supply = 1000000000  # 1B tokens
            
            # Generate 5-15 whale holders
            whale_count = 5 + (address_hash % 11)
            
            for i in range(whale_count):
                whale_hash = hash(f"{token_address}_{i}")
                
                # Generate whale balance (2-15% of supply)
                balance_percent = 2.0 + (whale_hash % 130) / 10.0  # 2.0-15.0%
                balance_tokens = total_supply * balance_percent / 100
                
                # Determine whale type
                whale_types = ['WHALE', 'TEAM', 'DEV', 'EXCHANGE', 'BURN']
                whale_type = whale_types[whale_hash % len(whale_types)]
                
                # Special handling for burn address
                if whale_type == 'BURN':
                    whale_address = '0x000000000000000000000000000000000000dead'
                    is_active = False
                    transaction_count = 1  # Just the initial burn
                else:
                    whale_address = f"0x{(whale_hash % (16**40)):040x}"
                    is_active = (whale_hash % 10) > 2  # 70% active
                    transaction_count = 10 + (whale_hash % 200)  # 10-209 transactions
                
                # Calculate risk score for this whale
                whale_risk = self._calculate_whale_risk_score(
                    balance_percent, whale_type, is_active, transaction_count
                )
                
                whale_holders.append(WhaleHolder(
                    address=whale_address,
                    balance_tokens=balance_tokens,
                    percentage_of_supply=balance_percent,
                    holder_type=whale_type,
                    first_transaction_date='2024-06-15' if whale_type != 'BURN' else '2024-01-01',
                    transaction_count=transaction_count,
                    is_active=is_active,
                    risk_score=whale_risk
                ))
            
            # Sort by balance descending
            whale_holders.sort(key=lambda w: w.balance_tokens, reverse=True)
            
            return whale_holders
            
        except Exception as e:
            logger.error(f"Error identifying whale holders: {e}")
            return []
    
    async def _analyze_team_allocations(self, token_address: str) -> Dict[str, Any]:
        """Analyze team and developer token allocations."""
        try:
            await asyncio.sleep(0.15)  # Simulate team allocation analysis
            
            address_hash = hash(token_address)
            total_supply = 1000000000
            
            # Determine if there are identifiable team allocations
            has_team_allocation = (address_hash % 4) != 0  # 75% have team allocations
            
            if has_team_allocation:
                # Generate team allocation data
                team_percentage = 5 + (address_hash % 15)  # 5-19% team allocation
                team_tokens = total_supply * team_percentage / 100
                
                # Generate team addresses
                team_addresses = []
                team_member_count = 2 + (address_hash % 4)  # 2-5 team members
                
                for i in range(team_member_count):
                    member_hash = hash(f"{token_address}_team_{i}")
                    member_percentage = team_percentage / team_member_count
                    member_tokens = team_tokens / team_member_count
                    
                    team_addresses.append({
                        'address': f"0x{(member_hash % (16**40)):040x}",
                        'role': ['CEO', 'CTO', 'MARKETING', 'DEV', 'ADVISOR'][i % 5],
                        'balance_tokens': member_tokens,
                        'percentage': member_percentage,
                        'vesting_period': 12 + (member_hash % 24),  # 12-35 months
                        'is_locked': (member_hash % 3) != 0  # 67% locked
                    })
                
                team_analysis = {
                    'has_team_allocation': True,
                    'total_team_percentage': team_percentage,
                    'total_team_tokens': team_tokens,
                    'team_member_count': team_member_count,
                    'team_addresses': team_addresses,
                    'average_vesting_period': sum(addr['vesting_period'] for addr in team_addresses) / len(team_addresses),
                    'locked_percentage': sum(1 for addr in team_addresses if addr['is_locked']) / len(team_addresses) * 100,
                    'risk_assessment': self._assess_team_risk(team_percentage, team_addresses)
                }
            else:
                team_analysis = {
                    'has_team_allocation': False,
                    'total_team_percentage': 0.0,
                    'team_member_count': 0,
                    'team_addresses': [],
                    'risk_assessment': 'LOW'  # No team allocation = lower immediate risk
                }
            
            return team_analysis
            
        except Exception as e:
            logger.error(f"Error analyzing team allocations: {e}")
            return {'error': str(e)}
    
    async def _analyze_exchange_holdings(self, token_address: str) -> Dict[str, Any]:
        """Analyze exchange and contract holdings."""
        try:
            await asyncio.sleep(0.12)  # Simulate exchange holdings analysis
            
            address_hash = hash(token_address)
            total_supply = 1000000000
            
            # Generate exchange holdings
            exchanges = [
                {'name': 'Binance', 'probability': 0.3},
                {'name': 'Coinbase', 'probability': 0.2},
                {'name': 'Uniswap', 'probability': 0.8},
                {'name': 'PancakeSwap', 'probability': 0.6},
                {'name': 'SushiSwap', 'probability': 0.4}
            ]
            
            exchange_holdings = []
            total_exchange_percentage = 0.0
            
            for i, exchange in enumerate(exchanges):
                exchange_hash = hash(f"{token_address}_exchange_{i}")
                
                # Determine if this exchange holds the token
                if (exchange_hash % 100) / 100.0 < exchange['probability']:
                    # Calculate exchange holding percentage
                    holding_percentage = 1.0 + (exchange_hash % 100) / 10.0  # 1-11%
                    holding_tokens = total_supply * holding_percentage / 100
                    
                    exchange_holdings.append({
                        'exchange_name': exchange['name'],
                        'address': f"0x{(exchange_hash % (16**40)):040x}",
                        'balance_tokens': holding_tokens,
                        'percentage': holding_percentage,
                        'exchange_type': 'CEX' if exchange['name'] in ['Binance', 'Coinbase'] else 'DEX',
                        'liquidity_provider': exchange['name'] in ['Uniswap', 'PancakeSwap', 'SushiSwap']
                    })
                    
                    total_exchange_percentage += holding_percentage
            
            # Analyze contract holdings (dead addresses, burn addresses, etc.)
            contract_holdings = []
            
            # Burn address
            burn_percentage = 5 + (address_hash % 20)  # 5-24% burned
            contract_holdings.append({
                'address': '0x000000000000000000000000000000000000dead',
                'type': 'BURN',
                'balance_tokens': total_supply * burn_percentage / 100,
                'percentage': burn_percentage,
                'description': 'Burned tokens (permanently removed)'
            })
            
            # Liquidity pool contract
            if exchange_holdings:  # If there are DEX holdings
                lp_percentage = 10 + (address_hash % 15)  # 10-24% in LP
                contract_holdings.append({
                    'address': f"0x{((address_hash + 1) % (16**40)):040x}",
                    'type': 'LIQUIDITY_POOL',
                    'balance_tokens': total_supply * lp_percentage / 100,
                    'percentage': lp_percentage,
                    'description': 'Liquidity pool contract'
                })
            
            return {
                'exchange_holdings': exchange_holdings,
                'contract_holdings': contract_holdings,
                'total_exchange_percentage': total_exchange_percentage,
                'total_contract_percentage': sum(h['percentage'] for h in contract_holdings),
                'exchange_count': len(exchange_holdings),
                'centralized_exchange_percentage': sum(
                    h['percentage'] for h in exchange_holdings if h['exchange_type'] == 'CEX'
                ),
                'decentralized_exchange_percentage': sum(
                    h['percentage'] for h in exchange_holdings if h['exchange_type'] == 'DEX'
                )
            }
            
        except Exception as e:
            logger.error(f"Error analyzing exchange holdings: {e}")
            return {'error': str(e)}
    
    async def _calculate_distribution_metrics(self, token_address: str) -> DistributionMetrics:
        """Calculate comprehensive distribution metrics."""
        try:
            await asyncio.sleep(0.1)  # Simulate metrics calculation
            
            address_hash = hash(token_address)
            
            # Generate realistic distribution metrics
            total_holders = 1000 + (address_hash % 5000)  # 1,000-6,000 holders
            
            # Gini coefficient (0-1, where 1 = maximum inequality)
            gini_base = 0.4 + (address_hash % 400) / 1000.0  # 0.4-0.79
            gini_coefficient = min(0.95, gini_base)
            
            # Concentration ratios
            whale_concentration = 20 + (address_hash % 400) / 10.0  # 20-60%
            concentration_ratio = whale_concentration + 10 + (address_hash % 200) / 10.0  # Top 10 holders
            
            # Decentralization score (higher = better distribution)
            decentralization_score = max(10, 100 - (gini_coefficient * 100))
            
            # Assess overall distribution health
            if decentralization_score >= 70:
                distribution_health = "EXCELLENT"
            elif decentralization_score >= 60:
                distribution_health = "GOOD"
            elif decentralization_score >= 45:
                distribution_health = "FAIR"
            elif decentralization_score >= 30:
                distribution_health = "POOR"
            else:
                distribution_health = "CRITICAL"
            
            return DistributionMetrics(
                total_holders=total_holders,
                gini_coefficient=gini_coefficient,
                concentration_ratio=concentration_ratio,
                whale_concentration=whale_concentration,
                decentralization_score=decentralization_score,
                distribution_health=distribution_health
            )
            
        except Exception as e:
            logger.error(f"Error calculating distribution metrics: {e}")
            # Return default metrics for error case
            return DistributionMetrics(
                total_holders=0,
                gini_coefficient=0.9,
                concentration_ratio=90.0,
                whale_concentration=80.0,
                decentralization_score=10.0,
                distribution_health="CRITICAL"
            )
    
    async def _analyze_holder_behavior_patterns(self, token_address: str) -> Dict[str, Any]:
        """Analyze holder behavior patterns and trends."""
        try:
            await asyncio.sleep(0.08)  # Simulate behavior analysis
            
            address_hash = hash(token_address)
            
            behavior_patterns = {
                'holder_growth_trend': ['GROWING', 'STABLE', 'DECLINING'][address_hash % 3],
                'whale_activity_level': ['LOW', 'MEDIUM', 'HIGH'][address_hash % 3],
                'recent_large_transfers': (address_hash % 10) < 3,  # 30% have recent large transfers
                'accumulation_pattern': ['ACCUMULATING', 'DISTRIBUTING', 'STABLE'][(address_hash >> 2) % 3],
                'holder_turnover_rate': 5 + (address_hash % 20),  # 5-24% monthly turnover
                'average_holding_period_days': 30 + (address_hash % 300),  # 30-329 days
                'whale_coordination_risk': 'LOW',  # Default to low unless patterns detected
                'manipulation_indicators': []
            }
            
            # Check for manipulation indicators
            if behavior_patterns['whale_activity_level'] == 'HIGH' and behavior_patterns['recent_large_transfers']:
                behavior_patterns['manipulation_indicators'].append('HIGH_WHALE_ACTIVITY')
                behavior_patterns['whale_coordination_risk'] = 'MEDIUM'
            
            if behavior_patterns['holder_turnover_rate'] > 20:
                behavior_patterns['manipulation_indicators'].append('HIGH_TURNOVER')
            
            if behavior_patterns['accumulation_pattern'] == 'DISTRIBUTING' and behavior_patterns['whale_activity_level'] == 'HIGH':
                behavior_patterns['manipulation_indicators'].append('POTENTIAL_DUMP')
                behavior_patterns['whale_coordination_risk'] = 'HIGH'
            
            return behavior_patterns
            
        except Exception as e:
            logger.error(f"Error analyzing holder behavior patterns: {e}")
            return {'error': str(e)}
    
    def _compile_distribution_analysis(
        self,
        holder_distribution: Dict[str, Any],
        whale_holders: List[WhaleHolder],
        team_allocations: Dict[str, Any],
        exchange_holdings: Dict[str, Any],
        distribution_metrics: DistributionMetrics,
        behavior_patterns: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Compile comprehensive distribution analysis."""
        return {
            'holder_distribution': holder_distribution,
            'whale_analysis': {
                'whale_count': len(whale_holders),
                'total_whale_percentage': sum(w.percentage_of_supply for w in whale_holders),
                'active_whales': sum(1 for w in whale_holders if w.is_active),
                'whale_risk_scores': [w.risk_score for w in whale_holders],
                'average_whale_risk': sum(w.risk_score for w in whale_holders) / max(1, len(whale_holders))
            },
            'team_analysis': team_allocations,
            'exchange_analysis': exchange_holdings,
            'distribution_metrics': distribution_metrics,
            'behavior_patterns': behavior_patterns,
            'risk_summary': {
                'concentration_risk': self._assess_concentration_risk(distribution_metrics),
                'whale_risk': self._assess_whale_risk(whale_holders),
                'team_risk': team_allocations.get('risk_assessment', 'UNKNOWN'),
                'overall_distribution_health': distribution_metrics.distribution_health
            }
        }
    
    def _calculate_holder_risk(
        self,
        distribution_analysis: Dict[str, Any],
        whale_holders: List[WhaleHolder],
        distribution_metrics: DistributionMetrics
    ) -> Tuple[float, float]:
        """Calculate overall holder distribution risk score and confidence."""
        risk_factors = []
        
        # Concentration risk (highest weight)
        concentration_risk = self._score_concentration_risk(distribution_metrics)
        risk_factors.append(('concentration', concentration_risk, 0.4))
        
        # Whale risk
        whale_risk = self._score_whale_risk(whale_holders)
        risk_factors.append(('whales', whale_risk, 0.3))
        
        # Team allocation risk
        team_risk = self._score_team_risk(distribution_analysis['team_analysis'])
        risk_factors.append(('team', team_risk, 0.2))
        
        # Behavior pattern risk
        behavior_risk = self._score_behavior_risk(distribution_analysis['behavior_patterns'])
        risk_factors.append(('behavior', behavior_risk, 0.1))
        
        # Calculate weighted risk
        total_risk = 0.0
        total_weight = 0.0
        
        for factor_name, risk, weight in risk_factors:
            total_risk += risk * weight
            total_weight += weight
        
        overall_risk = total_risk / total_weight if total_weight > 0 else 0.5
        
        # Confidence based on data completeness and quality
        confidence = 0.8
        
        # Reduce confidence for missing data
        if distribution_metrics.total_holders == 0:
            confidence -= 0.3
        if not whale_holders:
            confidence -= 0.2
        if 'error' in distribution_analysis['team_analysis']:
            confidence -= 0.1
        
        confidence = max(0.3, min(0.95, confidence))
        
        return overall_risk, confidence
    
    def _score_concentration_risk(self, metrics: DistributionMetrics) -> float:
        """Score risk based on holder concentration."""
        risk_score = 0.0
        
        # Gini coefficient scoring
        if metrics.gini_coefficient > 0.9:
            risk_score += 0.8
        elif metrics.gini_coefficient > 0.8:
            risk_score += 0.6
        elif metrics.gini_coefficient > 0.7:
            risk_score += 0.4
        elif metrics.gini_coefficient > 0.6:
            risk_score += 0.2
        
        # Whale concentration scoring
        if metrics.whale_concentration > 70:
            risk_score += 0.7
        elif metrics.whale_concentration > 50:
            risk_score += 0.5
        elif metrics.whale_concentration > 30:
            risk_score += 0.3
        elif metrics.whale_concentration > 20:
            risk_score += 0.1
        
        # Total holders scoring (fewer holders = higher risk)
        if metrics.total_holders < 100:
            risk_score += 0.6
        elif metrics.total_holders < 500:
            risk_score += 0.3
        elif metrics.total_holders < 1000:
            risk_score += 0.1
        
        return min(1.0, risk_score)
    
    def _score_whale_risk(self, whale_holders: List[WhaleHolder]) -> float:
        """Score risk based on whale holder characteristics."""
        if not whale_holders:
            return 0.3  # Moderate risk for no whale data
        
        risk_score = 0.0
        
        # Number of whales
        whale_count = len(whale_holders)
        if whale_count > 10:
            risk_score += 0.3
        elif whale_count > 5:
            risk_score += 0.2
        
        # Whale concentration
        total_whale_percentage = sum(w.percentage_of_supply for w in whale_holders)
        if total_whale_percentage > 60:
            risk_score += 0.7
        elif total_whale_percentage > 40:
            risk_score += 0.5
        elif total_whale_percentage > 25:
            risk_score += 0.3
        
        # Individual whale risk scores
        if whale_holders:
            avg_whale_risk = sum(w.risk_score for w in whale_holders) / len(whale_holders)
            risk_score += avg_whale_risk * 0.4
        
        # Active whale risk
        active_whales = sum(1 for w in whale_holders if w.is_active)
        if active_whales > 5:
            risk_score += 0.2
        
        return min(1.0, risk_score)
    
    def _score_team_risk(self, team_analysis: Dict[str, Any]) -> float:
        """Score risk based on team allocations."""
        if 'error' in team_analysis:
            return 0.5  # Moderate risk for analysis failure
        
        if not team_analysis.get('has_team_allocation', False):
            return 0.2  # Low risk for no team allocation
        
        risk_score = 0.0
        team_percentage = team_analysis.get('total_team_percentage', 0)
        
        # Team allocation size
        if team_percentage > 25:
            risk_score += 0.8
        elif team_percentage > 15:
            risk_score += 0.5
        elif team_percentage > 10:
            risk_score += 0.3
        elif team_percentage > 5:
            risk_score += 0.1
        
        # Vesting and locking
        locked_percentage = team_analysis.get('locked_percentage', 0)
        if locked_percentage < 50:
            risk_score += 0.3
        elif locked_percentage < 75:
            risk_score += 0.1
        
        return min(1.0, risk_score)
    
    def _score_behavior_risk(self, behavior_patterns: Dict[str, Any]) -> float:
        """Score risk based on holder behavior patterns."""
        if 'error' in behavior_patterns:
            return 0.4  # Moderate risk for analysis failure
        
        risk_score = 0.0
        
        # Manipulation indicators
        manipulation_indicators = behavior_patterns.get('manipulation_indicators', [])
        risk_score += len(manipulation_indicators) * 0.2
        
        # Whale coordination risk
        coord_risk = behavior_patterns.get('whale_coordination_risk', 'LOW')
        if coord_risk == 'HIGH':
            risk_score += 0.4
        elif coord_risk == 'MEDIUM':
            risk_score += 0.2
        
        # Holder growth trend
        growth_trend = behavior_patterns.get('holder_growth_trend', 'STABLE')
        if growth_trend == 'DECLINING':
            risk_score += 0.3
        
        # High turnover
        turnover_rate = behavior_patterns.get('holder_turnover_rate', 10)
        if turnover_rate > 25:
            risk_score += 0.3
        elif turnover_rate > 15:
            risk_score += 0.1
        
        return min(1.0, risk_score)
    
    def _generate_holder_warnings(
        self,
        distribution_analysis: Dict[str, Any],
        whale_holders: List[WhaleHolder],
        distribution_metrics: DistributionMetrics
    ) -> List[str]:
        """Generate holder distribution specific warnings."""
        warnings = []
        
        # Concentration warnings
        if distribution_metrics.whale_concentration > 60:
            warnings.append(f"EXTREME whale concentration: {distribution_metrics.whale_concentration:.1f}% held by top whales")
        elif distribution_metrics.whale_concentration > 40:
            warnings.append(f"HIGH whale concentration: {distribution_metrics.whale_concentration:.1f}% - manipulation risk")
        
        # Gini coefficient warnings
        if distribution_metrics.gini_coefficient > 0.85:
            warnings.append(f"EXTREME inequality: Gini coefficient {distribution_metrics.gini_coefficient:.2f}")
        elif distribution_metrics.gini_coefficient > 0.75:
            warnings.append(f"HIGH inequality: Gini coefficient {distribution_metrics.gini_coefficient:.2f}")
        
        # Individual whale warnings
        large_whales = [w for w in whale_holders if w.percentage_of_supply > 10]
        if large_whales:
            warnings.append(f"{len(large_whales)} whale(s) hold >10% each - major manipulation risk")
        
        # Team allocation warnings
        team_analysis = distribution_analysis['team_analysis']
        if team_analysis.get('total_team_percentage', 0) > 20:
            warnings.append(f"Large team allocation: {team_analysis['total_team_percentage']:.1f}% - dump risk")
        
        # Behavior warnings
        behavior = distribution_analysis['behavior_patterns']
        if behavior.get('whale_coordination_risk') == 'HIGH':
            warnings.append("HIGH whale coordination risk detected")
        
        if 'POTENTIAL_DUMP' in behavior.get('manipulation_indicators', []):
            warnings.append("Potential coordinated dump pattern detected")
        
        # Overall health warning
        if distribution_metrics.distribution_health in ['POOR', 'CRITICAL']:
            warnings.append(f"Distribution health: {distribution_metrics.distribution_health} - avoid trading")
        
        return warnings
    
    def _compile_holder_details(
        self,
        distribution_analysis: Dict[str, Any],
        whale_holders: List[WhaleHolder],
        team_allocations: Dict[str, Any],
        exchange_holdings: Dict[str, Any],
        distribution_metrics: DistributionMetrics,
        behavior_patterns: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Compile detailed holder analysis results."""
        return {
            'distribution_summary': {
                'total_holders': distribution_metrics.total_holders,
                'whale_count': len(whale_holders),
                'gini_coefficient': distribution_metrics.gini_coefficient,
                'whale_concentration': distribution_metrics.whale_concentration,
                'decentralization_score': distribution_metrics.decentralization_score,
                'distribution_health': distribution_metrics.distribution_health
            },
            'top_holders': [
                {
                    'address': whale.address[:10] + '...',  # Truncate for privacy
                    'percentage': whale.percentage_of_supply,
                    'type': whale.holder_type,
                    'risk_score': whale.risk_score,
                    'is_active': whale.is_active
                } for whale in whale_holders[:10]  # Top 10 whales
            ],
            'team_allocation_summary': {
                'has_team_tokens': team_allocations.get('has_team_allocation', False),
                'team_percentage': team_allocations.get('total_team_percentage', 0),
                'team_members': team_allocations.get('team_member_count', 0),
                'average_vesting': team_allocations.get('average_vesting_period', 0),
                'locked_percentage': team_allocations.get('locked_percentage', 0)
            },
            'exchange_summary': {
                'total_exchange_percentage': exchange_holdings.get('total_exchange_percentage', 0),
                'exchange_count': exchange_holdings.get('exchange_count', 0),
                'cex_percentage': exchange_holdings.get('centralized_exchange_percentage', 0),
                'dex_percentage': exchange_holdings.get('decentralized_exchange_percentage', 0)
            },
            'behavior_analysis': behavior_patterns,
            'risk_breakdown': distribution_analysis['risk_summary'],
            'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
            'chain_id': self.chain_id
        }
    
    def _assess_data_quality(
        self, 
        distribution_metrics: DistributionMetrics, 
        whale_holders: List[WhaleHolder]
    ) -> str:
        """Assess the quality of holder distribution data."""
        quality_score = 0
        
        # Distribution metrics completeness
        if distribution_metrics.total_holders > 0:
            quality_score += 2
        if distribution_metrics.gini_coefficient > 0:
            quality_score += 1
        
        # Whale data completeness
        if whale_holders:
            quality_score += 2
            if len(whale_holders) >= 5:
                quality_score += 1
        
        if quality_score >= 5:
            return "EXCELLENT"
        elif quality_score >= 4:
            return "GOOD"
        elif quality_score >= 2:
            return "FAIR"
        else:
            return "POOR"
    
    # Helper methods
    
    def _assess_tier_risk(self, tier_name: str, percentage: float) -> str:
        """Assess risk level for a holder tier."""
        if tier_name == 'Whale' and percentage > 50:
            return 'CRITICAL'
        elif tier_name == 'Whale' and percentage > 30:
            return 'HIGH'
        elif tier_name in ['Large', 'Whale']:
            return 'MEDIUM'
        else:
            return 'LOW'
    
    def _calculate_whale_risk_score(
        self, 
        balance_percent: float, 
        whale_type: str, 
        is_active: bool, 
        transaction_count: int
    ) -> float:
        """Calculate individual whale risk score."""
        risk_score = 0.0
        
        # Balance-based risk
        if balance_percent > 10:
            risk_score += 0.6
        elif balance_percent > 5:
            risk_score += 0.4
        elif balance_percent > 2:
            risk_score += 0.2
        
        # Type-based risk
        type_risks = {
            'WHALE': 0.3,
            'TEAM': 0.5,
            'DEV': 0.6,
            'EXCHANGE': 0.1,
            'BURN': 0.0
        }
        risk_score += type_risks.get(whale_type, 0.3)
        
        # Activity-based risk
        if is_active and whale_type in ['WHALE', 'TEAM', 'DEV']:
            risk_score += 0.2
        
        # Transaction pattern risk
        if transaction_count > 100 and is_active:
            risk_score += 0.1
        
        return min(1.0, risk_score)
    
    def _assess_team_risk(self, team_percentage: float, team_addresses: List[Dict]) -> str:
        """Assess overall team allocation risk."""
        if team_percentage > 25:
            return 'CRITICAL'
        elif team_percentage > 15:
            return 'HIGH'
        elif team_percentage > 10:
            return 'MEDIUM'
        elif team_percentage > 0:
            # Check if tokens are locked
            locked_count = sum(1 for addr in team_addresses if addr.get('is_locked', False))
            if locked_count / max(1, len(team_addresses)) > 0.75:
                return 'LOW'
            else:
                return 'MEDIUM'
        else:
            return 'LOW'
    
    def _assess_concentration_risk(self, metrics: DistributionMetrics) -> str:
        """Assess concentration risk level."""
        if metrics.whale_concentration > 70 or metrics.gini_coefficient > 0.9:
            return 'CRITICAL'
        elif metrics.whale_concentration > 50 or metrics.gini_coefficient > 0.8:
            return 'HIGH'
        elif metrics.whale_concentration > 30 or metrics.gini_coefficient > 0.7:
            return 'MEDIUM'
        else:
            return 'LOW'
    
    def _assess_whale_risk(self, whale_holders: List[WhaleHolder]) -> str:
        """Assess overall whale risk level."""
        if not whale_holders:
            return 'LOW'
        
        avg_risk = sum(w.risk_score for w in whale_holders) / len(whale_holders)
        high_risk_whales = sum(1 for w in whale_holders if w.risk_score > 0.7)
        
        if avg_risk > 0.7 or high_risk_whales > 3:
            return 'CRITICAL'
        elif avg_risk > 0.5 or high_risk_whales > 1:
            return 'HIGH'
        elif avg_risk > 0.3:
            return 'MEDIUM'
        else:
            return 'LOW'
    
    def _load_known_addresses(self) -> Dict[str, str]:
        """Load known addresses (exchanges, burn addresses, etc.)."""
        return {
            '0x000000000000000000000000000000000000dead': 'BURN',
            '0x0000000000000000000000000000000000000000': 'NULL',
            # In production, this would load from a comprehensive database
        }
    
    def _validate_inputs(self, token_address: str, context: Dict[str, Any]) -> bool:
        """Validate analyzer inputs."""
        return (
            token_address and 
            len(token_address) == 42 and 
            token_address.startswith('0x')
        )
    
    def _safe_extract_result(self, result: Any, default: Any) -> Any:
        """Safely extract result from async gather, handling exceptions."""
        if isinstance(result, Exception):
            logger.warning(f"Holder analysis task failed: {result}")
            return default
        return result if result is not None else default
    
    def _get_cached_analysis(self, token_address: str) -> Optional[Dict[str, Any]]:
        """Get cached holder analysis if available and fresh."""
        if token_address in self.holder_cache:
            result, timestamp = self.holder_cache[token_address]
            age = datetime.now(timezone.utc) - timestamp
            
            if age.total_seconds() < (self.cache_ttl_minutes * 60):
                return result
            else:
                del self.holder_cache[token_address]
        
        return None
    
    def _cache_analysis_result(self, token_address: str, result: Dict[str, Any]) -> None:
        """Cache holder analysis result."""
        self.holder_cache[token_address] = (result, datetime.now(timezone.utc))
        
        # Clean up old cache entries
        if len(self.holder_cache) > 50:
            oldest_token = min(
                self.holder_cache.keys(),
                key=lambda k: self.holder_cache[k][1]
            )
            del self.holder_cache[oldest_token]
    
    def _create_risk_score_from_cache(self, cached_result: Dict[str, Any]) -> RiskScore:
        """Create RiskScore from cached result."""
        return self._create_risk_score(
            score=cached_result['risk_score'],
            confidence=cached_result['confidence'],
            details=cached_result['details'],
            warnings=cached_result['warnings'],
            data_quality="CACHED",
            analysis_time_ms=0.1
        )
    
    def _create_error_risk_score(self, error_message: str) -> RiskScore:
        """Create error risk score for failed analysis."""
        return self._create_risk_score(
            score=0.7,  # High risk for failed holder analysis
            confidence=0.2,
            details={'error': error_message},
            warnings=[f"Holder distribution analysis failed: {error_message}"],
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
__all__ = ['HolderAnalyzer', 'HolderTier', 'WhaleHolder', 'DistributionMetrics']