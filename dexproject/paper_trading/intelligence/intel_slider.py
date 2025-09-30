"""
Intel Slider System for Paper Trading Bot

Implements the 1-10 intelligence level slider that controls all bot behaviors,
integrating with the existing paper trading infrastructure.

File: dexproject/paper_trading/intelligence/intel_slider.py
"""

import logging
import uuid
from decimal import Decimal
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass

from paper_trading.intelligence.base import (
    IntelligenceEngine,
    IntelligenceLevel,
    MarketContext,
    TradingDecision
)
from paper_trading.intelligence.analyzers import CompositeMarketAnalyzer

logger = logging.getLogger(__name__)


@dataclass
class IntelLevelConfig:
    """Configuration for each intelligence level."""
    
    level: int
    name: str
    description: str
    risk_tolerance: Decimal
    max_position_percent: Decimal
    min_confidence_required: Decimal
    use_mev_protection: bool
    gas_aggressiveness: str
    trade_frequency: str
    decision_speed: str


# Intel level configurations
INTEL_CONFIGS = {
    1: IntelLevelConfig(
        level=1,
        name="Ultra Cautious - Maximum Safety",
        description="Extreme caution, misses opportunities for safety",
        risk_tolerance=Decimal('20'),
        max_position_percent=Decimal('2'),
        min_confidence_required=Decimal('95'),
        use_mev_protection=True,
        gas_aggressiveness="minimal",
        trade_frequency="very_low",
        decision_speed="slow"
    ),
    2: IntelLevelConfig(
        level=2,
        name="Very Cautious - High Safety",
        description="Very conservative, only obvious opportunities",
        risk_tolerance=Decimal('25'),
        max_position_percent=Decimal('3'),
        min_confidence_required=Decimal('90'),
        use_mev_protection=True,
        gas_aggressiveness="low",
        trade_frequency="low",
        decision_speed="slow"
    ),
    3: IntelLevelConfig(
        level=3,
        name="Cautious - Safety First",
        description="Conservative approach with careful risk management",
        risk_tolerance=Decimal('30'),
        max_position_percent=Decimal('5'),
        min_confidence_required=Decimal('85'),
        use_mev_protection=True,
        gas_aggressiveness="standard",
        trade_frequency="low",
        decision_speed="moderate"
    ),
    4: IntelLevelConfig(
        level=4,
        name="Moderately Cautious",
        description="Balanced but leaning towards safety",
        risk_tolerance=Decimal('40'),
        max_position_percent=Decimal('7'),
        min_confidence_required=Decimal('75'),
        use_mev_protection=True,
        gas_aggressiveness="standard",
        trade_frequency="moderate",
        decision_speed="moderate"
    ),
    5: IntelLevelConfig(
        level=5,
        name="Balanced - Default",
        description="Equal weight to risk and opportunity",
        risk_tolerance=Decimal('50'),
        max_position_percent=Decimal('10'),
        min_confidence_required=Decimal('65'),
        use_mev_protection=True,
        gas_aggressiveness="adaptive",
        trade_frequency="moderate",
        decision_speed="moderate"
    ),
    6: IntelLevelConfig(
        level=6,
        name="Moderately Aggressive",
        description="Balanced but seeking opportunities",
        risk_tolerance=Decimal('60'),
        max_position_percent=Decimal('12'),
        min_confidence_required=Decimal('55'),
        use_mev_protection=False,  # Only when needed
        gas_aggressiveness="adaptive",
        trade_frequency="moderate_high",
        decision_speed="fast"
    ),
    7: IntelLevelConfig(
        level=7,
        name="Aggressive - Opportunity Seeker",
        description="Actively pursues opportunities, accepts risks",
        risk_tolerance=Decimal('70'),
        max_position_percent=Decimal('15'),
        min_confidence_required=Decimal('45'),
        use_mev_protection=False,
        gas_aggressiveness="aggressive",
        trade_frequency="high",
        decision_speed="fast"
    ),
    8: IntelLevelConfig(
        level=8,
        name="Very Aggressive",
        description="High risk tolerance, competitive execution",
        risk_tolerance=Decimal('80'),
        max_position_percent=Decimal('20'),
        min_confidence_required=Decimal('35'),
        use_mev_protection=False,
        gas_aggressiveness="aggressive",
        trade_frequency="high",
        decision_speed="very_fast"
    ),
    9: IntelLevelConfig(
        level=9,
        name="Ultra Aggressive - Maximum Risk",
        description="Extreme risk-taking for maximum profits",
        risk_tolerance=Decimal('90'),
        max_position_percent=Decimal('25'),
        min_confidence_required=Decimal('25'),
        use_mev_protection=False,
        gas_aggressiveness="ultra_aggressive",
        trade_frequency="very_high",
        decision_speed="ultra_fast"
    ),
    10: IntelLevelConfig(
        level=10,
        name="Fully Autonomous - AI Optimized",
        description="Bot determines optimal approach using ML",
        risk_tolerance=Decimal('0'),  # Dynamic
        max_position_percent=Decimal('0'),  # Dynamic
        min_confidence_required=Decimal('0'),  # Dynamic
        use_mev_protection=False,  # Dynamic
        gas_aggressiveness="dynamic",
        trade_frequency="dynamic",
        decision_speed="optimal"
    )
}


class IntelSliderEngine(IntelligenceEngine):
    """
    Intelligence engine controlled by the Intel slider.
    
    This engine adapts its behavior based on the selected intelligence
    level, providing a simple interface for users while handling
    complex decision-making internally.
    """
    
    def __init__(self, intel_level: int = 5, account_id: Optional[str] = None):
        """
        Initialize the Intel Slider engine.
        
        Args:
            intel_level: Intelligence level (1-10)
            account_id: Optional paper trading account ID
        """
        super().__init__(intel_level)
        self.config = INTEL_CONFIGS[intel_level]
        self.account_id = account_id
        self.analyzer = CompositeMarketAnalyzer()
        
        # Learning system data (for level 10)
        self.historical_decisions: List[TradingDecision] = []
        self.performance_history: List[Dict[str, Any]] = []
        
        self.logger.info(
            f"Intel Slider Engine initialized: Level {intel_level} - {self.config.name}"
        )
    
    async def analyze_market(self, token_address: str, **kwargs) -> MarketContext:
        """
        Analyze market conditions adapted to intel level.
        
        Args:
            token_address: Token to analyze
            **kwargs: Additional parameters
            
        Returns:
            Market context with intel-level adjustments
        """
        try:
            # Get comprehensive analysis
            analysis = await self.analyzer.analyze_comprehensive(
                token_address=token_address,
                trade_size_usd=kwargs.get('trade_size_usd', Decimal('1000')),
                liquidity_usd=kwargs.get('liquidity_usd', Decimal('100000')),
                volume_24h=kwargs.get('volume_24h', Decimal('50000'))
            )
            
            # Convert to MarketContext
            context = MarketContext(
                gas_price_gwei=Decimal(str(analysis['gas_analysis']['current_gas_gwei'])),
                network_congestion=analysis['gas_analysis']['network_congestion'],
                pending_tx_count=analysis['gas_analysis']['pending_tx_count'],
                mev_threat_level=analysis['mev_analysis']['threat_level'],
                sandwich_risk=analysis['mev_analysis']['sandwich_risk'],
                frontrun_probability=analysis['mev_analysis']['frontrun_probability'],
                competing_bots_detected=analysis['competition']['competing_bots'],
                average_bot_gas_price=Decimal(str(analysis['competition']['avg_bot_gas'])),
                bot_success_rate=analysis['competition']['bot_success_rate'],
                pool_liquidity_usd=Decimal(str(analysis['liquidity']['pool_liquidity_usd'])),
                expected_slippage=Decimal(str(analysis['liquidity']['expected_slippage'])),
                liquidity_depth_score=analysis['liquidity']['liquidity_depth_score'],
                volatility_index=analysis['market_state']['volatility_index'],
                chaos_event_detected=analysis['market_state']['chaos_event_detected'],
                trend_direction=analysis['market_state']['trend_direction'],
                volume_24h_change=Decimal(str(analysis['market_state']['volume_24h_change'])),
                recent_failures=kwargs.get('recent_failures', 0),
                success_rate_1h=kwargs.get('success_rate_1h', 50.0),
                average_profit_1h=kwargs.get('average_profit_1h', Decimal('0'))
            )
            
            # Adjust perception based on intel level
            context = self._adjust_market_perception(context)
            
            return context
            
        except Exception as e:
            self.logger.error(f"Error in market analysis: {e}")
            raise
    
    def _adjust_market_perception(self, context: MarketContext) -> MarketContext:
        """
        Adjust market perception based on intel level.
        
        Lower levels are more pessimistic, higher levels more optimistic.
        """
        if self.intel_level <= 3:
            # Cautious levels see more risk
            context.mev_threat_level *= 1.3
            context.sandwich_risk *= 1.3
            context.volatility_index *= 1.2
            context.confidence_in_data *= 0.8
        elif self.intel_level >= 7:
            # Aggressive levels downplay risks
            context.mev_threat_level *= 0.8
            context.sandwich_risk *= 0.8
            context.volatility_index *= 0.9
            context.confidence_in_data *= 1.1
        
        return context
    
    async def make_decision(
        self,
        market_context: MarketContext,
        account_balance: Decimal,
        existing_positions: List[Dict[str, Any]],
        token_address: str,
        token_symbol: str
    ) -> TradingDecision:
        """
        Make trading decision based on intel level.
        
        Args:
            market_context: Current market conditions
            account_balance: Available balance
            existing_positions: Current positions
            token_address: Token to trade
            token_symbol: Token symbol
            
        Returns:
            Complete trading decision
        """
        try:
            # Calculate base scores
            risk_score = self._calculate_risk_score(market_context)
            opportunity_score = self._calculate_opportunity_score(market_context)
            confidence_score = self._calculate_confidence_score(market_context, risk_score, opportunity_score)
            
            # Determine action based on intel level
            action = self._determine_action(risk_score, opportunity_score, confidence_score)
            
            # Calculate position size
            position_size = self._calculate_position_size(
                risk_score, opportunity_score, account_balance
            )
            
            # Determine execution strategy
            execution = self._determine_execution_strategy(market_context, action)
            
            # Generate reasoning
            reasoning = self._generate_reasoning(
                action, risk_score, opportunity_score, confidence_score, market_context
            )
            
            # Build decision
            decision = TradingDecision(
                action=action,
                token_address=token_address,
                token_symbol=token_symbol,
                position_size_percent=position_size,
                position_size_usd=account_balance * position_size / Decimal('100'),
                stop_loss_percent=self._calculate_stop_loss(risk_score),
                take_profit_targets=self._calculate_take_profits(opportunity_score),
                execution_mode=execution['mode'],
                use_private_relay=execution['use_private_relay'],
                gas_strategy=execution['gas_strategy'],
                max_gas_price_gwei=execution['max_gas_gwei'],
                overall_confidence=confidence_score,
                risk_score=risk_score,
                opportunity_score=opportunity_score,
                primary_reasoning=reasoning,
                risk_factors=self._identify_risk_factors(market_context),
                opportunity_factors=self._identify_opportunity_factors(market_context),
                mitigation_strategies=self._generate_mitigation_strategies(market_context),
                intel_level_used=self.intel_level,
                intel_adjustments={},
                time_sensitivity=self._assess_time_sensitivity(market_context),
                max_execution_time_ms=self._calculate_max_execution_time()
            )
            
            # Apply intel level adjustments
            decision = self.adjust_for_intel_level(decision)
            
            # Store for learning (level 10)
            if self.intel_level == 10:
                self.historical_decisions.append(decision)
            
            return decision
            
        except Exception as e:
            self.logger.error(f"Error making decision: {e}")
            raise
    
    def _calculate_risk_score(self, context: MarketContext) -> Decimal:
        """Calculate overall risk score."""
        risk = (
            context.mev_threat_level * Decimal('0.25') +
            context.volatility_index * Decimal('0.25') +
            context.bot_success_rate * Decimal('0.20') +
            (Decimal('100') - context.liquidity_depth_score) * Decimal('0.15') +
            context.expected_slippage * Decimal('10') * Decimal('0.15')
        )
        return min(risk, Decimal('100'))
    
    def _calculate_opportunity_score(self, context: MarketContext) -> Decimal:
        """Calculate opportunity score."""
        trend_bonus = Decimal('30') if context.trend_direction == 'bullish' else Decimal('0')
        
        opportunity = (
            context.liquidity_depth_score * Decimal('0.30') +
            (Decimal('100') - context.network_congestion) * Decimal('0.20') +
            (Decimal('100') - context.bot_success_rate) * Decimal('0.20') +
            trend_bonus +
            max(context.volume_24h_change, Decimal('0')) * Decimal('0.10')
        )
        return min(opportunity, Decimal('100'))
    
    def _calculate_confidence_score(
        self,
        context: MarketContext,
        risk_score: Decimal,
        opportunity_score: Decimal
    ) -> Decimal:
        """Calculate confidence in the decision."""
        if self.intel_level == 10:
            # Autonomous mode uses ML-based confidence
            return self._calculate_ml_confidence(context, risk_score, opportunity_score)
        
        base_confidence = (
            context.confidence_in_data * Decimal('0.30') +
            (Decimal('100') - context.volatility_index) * Decimal('0.30') +
            context.liquidity_depth_score * Decimal('0.20') +
            (Decimal('100') if not context.chaos_event_detected else Decimal('20')) * Decimal('0.20')
        )
        
        # Adjust for risk/opportunity balance
        if risk_score < self.config.risk_tolerance and opportunity_score > 50:
            base_confidence *= Decimal('1.2')
        elif risk_score > self.config.risk_tolerance:
            base_confidence *= Decimal('0.8')
        
        return min(base_confidence, Decimal('100'))
    
    def _calculate_ml_confidence(
        self,
        context: MarketContext,
        risk_score: Decimal,
        opportunity_score: Decimal
    ) -> Decimal:
        """
        Calculate confidence using machine learning (Level 10).
        
        In production, this would use actual ML models.
        """
        # Simulate ML confidence based on historical patterns
        if len(self.historical_decisions) > 10:
            # Use recent performance
            recent_success = sum(
                1 for d in self.historical_decisions[-10:]
                if d.opportunity_score > d.risk_score
            )
            ml_confidence = Decimal(str(recent_success * 10))
        else:
            # Default to balanced confidence
            ml_confidence = Decimal('60')
        
        return ml_confidence
    
    def _determine_action(
        self,
        risk_score: Decimal,
        opportunity_score: Decimal,
        confidence_score: Decimal
    ) -> str:
        """Determine trading action based on scores and intel level."""
        
        # Check minimum confidence
        if confidence_score < self.config.min_confidence_required:
            return 'SKIP'
        
        # Check risk tolerance
        if risk_score > self.config.risk_tolerance:
            if self.intel_level >= 7:
                # Aggressive levels might still trade
                if opportunity_score > 80:
                    return 'BUY'
            return 'SKIP'
        
        # Opportunity assessment
        if opportunity_score > 60:
            return 'BUY'
        elif opportunity_score < 40:
            return 'SELL' if risk_score > 50 else 'HOLD'
        else:
            return 'HOLD'
    
    def _calculate_position_size(
        self,
        risk_score: Decimal,
        opportunity_score: Decimal,
        account_balance: Decimal
    ) -> Decimal:
        """Calculate position size based on intel level and scores."""
        
        if self.intel_level == 10:
            # Autonomous sizing
            return self._calculate_ml_position_size(risk_score, opportunity_score)
        
        base_size = self.config.max_position_percent
        
        # Adjust for risk
        if risk_score > 70:
            base_size *= Decimal('0.5')
        elif risk_score > 50:
            base_size *= Decimal('0.8')
        
        # Adjust for opportunity
        if opportunity_score > 80:
            base_size *= Decimal('1.3')
        elif opportunity_score > 60:
            base_size *= Decimal('1.1')
        
        return min(base_size, self.config.max_position_percent)
    
    def _calculate_ml_position_size(
        self,
        risk_score: Decimal,
        opportunity_score: Decimal
    ) -> Decimal:
        """ML-based position sizing for level 10."""
        # Kelly Criterion simulation
        win_prob = opportunity_score / Decimal('100')
        loss_prob = risk_score / Decimal('100')
        
        if loss_prob > 0:
            kelly_fraction = (win_prob - loss_prob) / loss_prob
            position_size = min(kelly_fraction * Decimal('100'), Decimal('30'))
        else:
            position_size = Decimal('10')
        
        return max(position_size, Decimal('1'))
    
    def _determine_execution_strategy(
        self,
        context: MarketContext,
        action: str
    ) -> Dict[str, Any]:
        """Determine execution strategy based on intel level."""
        
        if action in ['SKIP', 'HOLD']:
            return {
                'mode': 'NONE',
                'use_private_relay': False,
                'gas_strategy': 'standard',
                'max_gas_gwei': context.gas_price_gwei
            }
        
        # Base strategy on intel config
        if self.config.gas_aggressiveness == "minimal":
            gas_strategy = 'standard'
            gas_multiplier = Decimal('1.0')
        elif self.config.gas_aggressiveness == "aggressive":
            gas_strategy = 'aggressive'
            gas_multiplier = Decimal('1.5')
        elif self.config.gas_aggressiveness == "ultra_aggressive":
            gas_strategy = 'ultra_aggressive'
            gas_multiplier = Decimal('2.0')
        else:  # adaptive or dynamic
            if context.network_congestion > 70:
                gas_strategy = 'aggressive'
                gas_multiplier = Decimal('1.5')
            else:
                gas_strategy = 'standard'
                gas_multiplier = Decimal('1.1')
        
        # Determine execution mode
        if self.config.decision_speed in ['ultra_fast', 'very_fast']:
            mode = 'FAST_LANE'
        elif context.mev_threat_level > 60:
            mode = 'SMART_LANE'
        else:
            mode = 'HYBRID'
        
        # MEV protection
        use_relay = (
            self.config.use_mev_protection or
            context.mev_threat_level > 70 or
            context.sandwich_risk > 60
        )
        
        return {
            'mode': mode,
            'use_private_relay': use_relay,
            'gas_strategy': gas_strategy,
            'max_gas_gwei': context.gas_price_gwei * gas_multiplier
        }
    
    def _calculate_stop_loss(self, risk_score: Decimal) -> Decimal:
        """Calculate stop loss based on risk."""
        if self.intel_level <= 3:
            return Decimal('3')  # Tight stop loss
        elif self.intel_level <= 6:
            return Decimal('5')
        elif self.intel_level <= 9:
            return Decimal('8')
        else:  # Level 10
            # Dynamic based on volatility
            return Decimal('3') if risk_score > 70 else Decimal('10')
    
    def _calculate_take_profits(self, opportunity_score: Decimal) -> List[Decimal]:
        """Calculate take profit targets."""
        if opportunity_score > 80:
            return [Decimal('5'), Decimal('10'), Decimal('20')]
        elif opportunity_score > 60:
            return [Decimal('3'), Decimal('7'), Decimal('12')]
        else:
            return [Decimal('2'), Decimal('5'), Decimal('8')]
    
    def _generate_reasoning(
        self,
        action: str,
        risk_score: Decimal,
        opportunity_score: Decimal,
        confidence_score: Decimal,
        context: MarketContext
    ) -> str:
        """Generate detailed reasoning for the decision."""
        
        reasoning = f"Intel Level {self.intel_level} ({self.config.name}) Decision:\n"
        reasoning += f"Action: {action}\n"
        reasoning += f"Risk Assessment: {risk_score:.1f}/100\n"
        reasoning += f"Opportunity Score: {opportunity_score:.1f}/100\n"
        reasoning += f"Confidence: {confidence_score:.1f}/100\n\n"
        
        if action == 'BUY':
            reasoning += "Rationale: Favorable opportunity with acceptable risk. "
            if context.trend_direction == 'bullish':
                reasoning += "Bullish trend supports entry. "
            if context.liquidity_depth_score > 70:
                reasoning += "Good liquidity minimizes slippage. "
        elif action == 'SKIP':
            reasoning += "Rationale: "
            if risk_score > self.config.risk_tolerance:
                reasoning += f"Risk ({risk_score:.1f}) exceeds tolerance ({self.config.risk_tolerance}). "
            if confidence_score < self.config.min_confidence_required:
                reasoning += f"Insufficient confidence ({confidence_score:.1f} < {self.config.min_confidence_required}). "
        
        return reasoning
    
    def _identify_risk_factors(self, context: MarketContext) -> List[str]:
        """Identify key risk factors."""
        factors = []
        
        if context.mev_threat_level > 60:
            factors.append(f"High MEV threat ({context.mev_threat_level:.1f}/100)")
        if context.volatility_index > 70:
            factors.append(f"High volatility ({context.volatility_index:.1f}/100)")
        if context.liquidity_depth_score < 40:
            factors.append(f"Poor liquidity depth ({context.liquidity_depth_score:.1f}/100)")
        if context.chaos_event_detected:
            factors.append("Chaos event detected in market")
        if context.competing_bots_detected > 5:
            factors.append(f"{context.competing_bots_detected} competing bots detected")
        
        return factors[:5]  # Top 5 risks
    
    def _identify_opportunity_factors(self, context: MarketContext) -> List[str]:
        """Identify opportunity factors."""
        factors = []
        
        if context.trend_direction == 'bullish':
            factors.append("Bullish market trend")
        if context.volume_24h_change > 50:
            factors.append(f"Volume surge ({context.volume_24h_change:.1f}%)")
        if context.liquidity_depth_score > 70:
            factors.append(f"Excellent liquidity ({context.liquidity_depth_score:.1f}/100)")
        if context.network_congestion < 30:
            factors.append("Low network congestion")
        if context.bot_success_rate < 40:
            factors.append("Low bot competition")
        
        return factors[:5]  # Top 5 opportunities
    
    def _generate_mitigation_strategies(self, context: MarketContext) -> List[str]:
        """Generate risk mitigation strategies."""
        strategies = []
        
        if context.mev_threat_level > 60:
            strategies.append("Use private relay for MEV protection")
        if context.volatility_index > 70:
            strategies.append("Reduce position size for volatility")
        if context.expected_slippage > 3:
            strategies.append("Split trade to reduce slippage")
        if context.competing_bots_detected > 5:
            strategies.append("Increase gas for competitive execution")
        
        return strategies
    
    def _assess_time_sensitivity(self, context: MarketContext) -> str:
        """Assess time sensitivity of the opportunity."""
        if context.chaos_event_detected:
            return 'critical'
        elif context.volatility_index > 70 or context.competing_bots_detected > 5:
            return 'high'
        elif context.trend_direction == 'bullish' and context.volume_24h_change > 50:
            return 'medium'
        else:
            return 'low'
    
    def _calculate_max_execution_time(self) -> int:
        """Calculate maximum execution time based on intel level."""
        if self.config.decision_speed == 'ultra_fast':
            return 100  # 100ms
        elif self.config.decision_speed == 'very_fast':
            return 200
        elif self.config.decision_speed == 'fast':
            return 500
        elif self.config.decision_speed == 'moderate':
            return 1000
        else:  # slow
            return 3000