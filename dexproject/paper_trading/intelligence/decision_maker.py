"""
Decision Maker for Paper Trading Bot

This module provides the DecisionMaker class that handles:
- Risk score calculation
- Opportunity assessment
- Confidence scoring
- Position sizing
- Stop loss determination
- Execution strategy selection

File: dexproject/paper_trading/intelligence/decision_maker.py
"""

import logging
from decimal import Decimal
from typing import Dict, Any, List
from datetime import datetime

# Django imports
from django.utils import timezone

# Import type utilities
from paper_trading.utils.type_utils import TypeConverter, MarketDataNormalizer

# Import base classes
from paper_trading.intelligence.base import MarketContext, TradingDecision
from paper_trading.intelligence.intel_config import IntelLevelConfig

logger = logging.getLogger(__name__)


class DecisionMaker:
    """
    Makes trading decisions based on market context and intelligence level.
    
    This class handles all decision-making operations including:
    - Risk and opportunity assessment
    - Action determination (BUY/SKIP)
    - Position sizing
    - Stop loss and take profit calculation
    - Execution strategy selection
    
    Attributes:
        config: Intelligence level configuration
        intel_level: Current intelligence level (1-10)
        converter: Type converter utility
        normalizer: Market data normalizer
        logger: Logger instance
    """
    
    def __init__(self, config: IntelLevelConfig, intel_level: int):
        """
        Initialize the decision maker.
        
        Args:
            config: Intelligence level configuration
            intel_level: Intelligence level (1-10)
        """
        self.config = config
        self.intel_level = intel_level
        self.converter = TypeConverter()
        self.normalizer = MarketDataNormalizer()
        self.logger = logging.getLogger(f'{__name__}.DecisionMaker')
        
        self.logger.info(
            f"[DECISION MAKER] Initialized for Level {intel_level} ({config.name})"
        )
    
    def calculate_risk_score(
        self,
        context: MarketContext,
        comprehensive_analysis: Dict[str, Any]
    ) -> Decimal:
        """
        Calculate comprehensive risk score (0-100).
        
        Args:
            context: Market context with risk data
            comprehensive_analysis: Results from CompositeMarketAnalyzer
            
        Returns:
            Risk score from 0 to 100
        """
        try:
            context = self.normalizer.normalize_context(context)
            risk_score = Decimal('0')
            
            # MEV risk (25% weight)
            mev_threat = self.converter.to_decimal(
                context.mev_threat_level,
                Decimal('0')
            )
            risk_score += mev_threat * Decimal('0.25')
            
            # Volatility risk (20% weight)
            volatility = self.converter.to_decimal(
                context.volatility_index,
                Decimal('0')
            )
            risk_score += volatility * Decimal('0.20')
            
            # Liquidity risk (20% weight) - inverse relationship
            liquidity_score = self.converter.to_decimal(
                context.liquidity_depth_score,
                Decimal('100')
            )
            liquidity_risk = Decimal('100') - liquidity_score
            risk_score += liquidity_risk * Decimal('0.20')
            
            # Network risk (15% weight)
            congestion = self.converter.to_decimal(
                context.network_congestion,
                Decimal('0')
            )
            risk_score += congestion * Decimal('0.15')
            
            # Competition risk (10% weight)
            competing_bots = self.converter.to_decimal(
                context.competing_bots_detected,
                Decimal('0')
            )
            competition_score = min(Decimal('100'), competing_bots * Decimal('10'))
            risk_score += competition_score * Decimal('0.10')
            
            # Chaos event (10% weight)
            if context.chaos_event_detected:
                risk_score += Decimal('10')
            
            # Ensure within bounds
            risk_score = max(Decimal('0'), min(Decimal('100'), risk_score))
            
            self.logger.debug(
                f"[RISK SCORE] {context.token_symbol}: {risk_score:.1f}/100 "
                f"(MEV={mev_threat:.1f}, Vol={volatility:.1f}, Liq={liquidity_score:.1f})"
            )
            
            return risk_score
            
        except Exception as e:
            self.logger.error(
                f"[RISK SCORE] Error calculating risk: {e}",
                exc_info=True
            )
            return Decimal('75')  # Conservative on error
    
    def calculate_opportunity_score(
        self,
        context: MarketContext,
        comprehensive_analysis: Dict[str, Any]
    ) -> Decimal:
        """
        Calculate comprehensive opportunity score (0-100).
        
        Args:
            context: Market context with opportunity indicators
            comprehensive_analysis: Results from CompositeMarketAnalyzer
            
        Returns:
            Opportunity score from 0 to 100
        """
        try:
            context = self.normalizer.normalize_context(context)
            opportunity_score = Decimal('0')
            
            # Price trend (30% weight)
            trend_score = Decimal('50')  # Neutral baseline
            if context.trend_direction == 'bullish':
                trend_score = Decimal('80')
            elif context.trend_direction == 'bearish':
                trend_score = Decimal('20')
            opportunity_score += trend_score * Decimal('0.30')
            
            # Momentum (25% weight)
            momentum_score = self._calculate_momentum_score(context)
            opportunity_score += momentum_score * Decimal('0.25')
            
            # Volume (20% weight)
            volume_change = self.converter.to_decimal(
                context.volume_24h_change,
                Decimal('0')
            )
            volume_score = min(Decimal('100'), Decimal('50') + volume_change)
            opportunity_score += volume_score * Decimal('0.20')
            
            # Liquidity (15% weight)
            liquidity_score = self._assess_liquidity_score(context)
            opportunity_score += liquidity_score * Decimal('0.15')
            
            # Network conditions (10% weight) - low congestion is good
            congestion = self.converter.to_decimal(
                context.network_congestion,
                Decimal('50')
            )
            network_score = Decimal('100') - congestion
            opportunity_score += network_score * Decimal('0.10')
            
            # Ensure within bounds
            opportunity_score = max(Decimal('0'), min(Decimal('100'), opportunity_score))
            
            self.logger.debug(
                f"[OPPORTUNITY] {context.token_symbol}: {opportunity_score:.1f}/100 "
                f"(Trend={trend_score:.1f}, Momentum={momentum_score:.1f}, Vol={volume_score:.1f})"
            )
            
            return opportunity_score
            
        except Exception as e:
            self.logger.error(
                f"[OPPORTUNITY] Error calculating opportunity: {e}",
                exc_info=True
            )
            return Decimal('50')  # Neutral on error
    
    def _calculate_momentum_score(self, context: MarketContext) -> Decimal:
        """
        Calculate price momentum score (0-100).
        
        Helper method that calculates momentum based on trend direction,
        volume changes, and price momentum.
        
        Args:
            context: Market context with momentum data
            
        Returns:
            Momentum score from 0 to 100
        """
        try:
            momentum_score = Decimal('50')  # Neutral starting point
            
            # Factor 1: Price trend
            if context.trend == "bullish":
                momentum_score += Decimal('20')
            elif context.trend == "bearish":
                momentum_score -= Decimal('20')
            
            # Factor 2: Volume change
            if context.volume_24h_change > 0:
                volume_boost = min(
                    Decimal('15'),
                    context.volume_24h_change / Decimal('10')
                )
                momentum_score += volume_boost
            
            # Factor 3: Price momentum
            momentum_score += context.momentum
            
            # Clamp to 0-100
            momentum_score = max(Decimal('0'), min(Decimal('100'), momentum_score))
            
            self.logger.debug(
                f"[MOMENTUM] Calculated momentum score: {momentum_score:.1f}/100"
            )
            
            return momentum_score
            
        except Exception as e:
            self.logger.error(
                f"[MOMENTUM] Error calculating momentum: {e}",
                exc_info=True
            )
            return Decimal('50')  # Neutral on error
    
    def _assess_liquidity_score(self, context: MarketContext) -> Decimal:
        """
        Assess liquidity quality score (0-100).
        
        Helper method that evaluates liquidity based on pool size,
        trading volume, and depth score.
        
        Args:
            context: Market context with liquidity data
            
        Returns:
            Liquidity quality score from 0 to 100
        """
        try:
            liquidity_score = Decimal('0')
            
            # Factor 1: Pool liquidity USD (higher is better)
            if context.pool_liquidity_usd >= Decimal('1000000'):  # $1M+
                liquidity_score += Decimal('40')
            elif context.pool_liquidity_usd >= Decimal('100000'):  # $100K+
                liquidity_score += Decimal('25')
            elif context.pool_liquidity_usd >= Decimal('10000'):  # $10K+
                liquidity_score += Decimal('10')
            
            # Factor 2: 24h volume (indicates active trading)
            if context.volume_24h >= Decimal('500000'):  # $500K+
                liquidity_score += Decimal('30')
            elif context.volume_24h >= Decimal('50000'):  # $50K+
                liquidity_score += Decimal('20')
            elif context.volume_24h >= Decimal('5000'):  # $5K+
                liquidity_score += Decimal('10')
            
            # Factor 3: Liquidity depth score
            liquidity_score += Decimal(str(context.liquidity_depth_score)) * Decimal('0.3')
            
            # Factor 4: Expected slippage (lower is better)
            if context.expected_slippage < Decimal('1'):  # <1%
                liquidity_score += Decimal('10')
            elif context.expected_slippage < Decimal('3'):  # <3%
                liquidity_score += Decimal('5')
            
            # Clamp to 0-100
            liquidity_score = max(Decimal('0'), min(Decimal('100'), liquidity_score))
            
            self.logger.debug(
                f"[LIQUIDITY] Calculated liquidity score: {liquidity_score:.1f}/100 "
                f"(Pool=${context.pool_liquidity_usd:.0f}, Vol=${context.volume_24h:.0f})"
            )
            
            return liquidity_score
            
        except Exception as e:
            self.logger.error(
                f"[LIQUIDITY] Error assessing liquidity: {e}",
                exc_info=True
            )
            return Decimal('0')  # Conservative on error
    
    def calculate_confidence_score(
        self,
        risk_score: Decimal,
        opportunity_score: Decimal,
        context: MarketContext
    ) -> Decimal:
        """
        Calculate overall confidence in the decision (0-100).
        
        Args:
            risk_score: Calculated risk score
            opportunity_score: Calculated opportunity score
            context: Market context for data confidence
            
        Returns:
            Confidence score from 0 to 100
        """
        try:
            # Convert inputs to Decimal
            risk_score = self.converter.to_decimal(risk_score)
            opportunity_score = self.converter.to_decimal(opportunity_score)
            
            # Base confidence from risk/opportunity balance
            if opportunity_score > risk_score:
                base_confidence = opportunity_score - (risk_score / Decimal('2'))
            else:
                base_confidence = Decimal('50') - (risk_score - opportunity_score)
            
            # Adjust for data confidence
            data_confidence = self.converter.to_decimal(
                context.confidence_in_data,
                Decimal('100')
            )
            confidence_multiplier = data_confidence / Decimal('100')
            
            # Adjust for price data availability
            if context.current_price > 0:
                confidence_multiplier *= Decimal('1.1')  # 10% boost for real prices
            
            # Final confidence
            confidence_score = base_confidence * confidence_multiplier
            
            # Ensure within bounds
            confidence_score = max(Decimal('0'), min(Decimal('100'), confidence_score))
            
            self.logger.debug(
                f"[CONFIDENCE] {context.token_symbol}: {confidence_score:.1f}% "
                f"(Base={base_confidence:.1f}, Data={data_confidence:.1f}%)"
            )
            
            return confidence_score
            
        except Exception as e:
            self.logger.error(
                f"[CONFIDENCE] Error calculating confidence: {e}",
                exc_info=True
            )
            return Decimal('50')  # Neutral on error
    
    def determine_action(
        self,
        risk_score: Decimal,
        opportunity_score: Decimal,
        confidence_score: Decimal,
        context: MarketContext
    ) -> str:
        """
        Determine BUY or SKIP action based on scores.
        
        Args:
            risk_score: Risk assessment score
            opportunity_score: Opportunity assessment score
            confidence_score: Overall confidence score
            context: Market context for validation
            
        Returns:
            Action string: 'BUY' or 'SKIP'
        """
        try:
            risk_score = self.converter.to_decimal(risk_score)
            opportunity_score = self.converter.to_decimal(opportunity_score)
            confidence_score = self.converter.to_decimal(confidence_score)
            
            # Check minimum requirements
            if confidence_score < self.config.min_confidence_required:
                self.logger.debug(
                    f"[ACTION] SKIP - Low confidence "
                    f"({confidence_score:.1f} < {self.config.min_confidence_required})"
                )
                return 'SKIP'
            
            if risk_score > self.config.risk_tolerance:
                self.logger.debug(
                    f"[ACTION] SKIP - High risk "
                    f"({risk_score:.1f} > {self.config.risk_tolerance})"
                )
                return 'SKIP'
            
            # Price-based decision: Only buy if we have a valid price
            if not context.current_price or context.current_price <= 0:
                self.logger.warning(
                    "[ACTION] SKIP - No valid price data available"
                )
                return 'SKIP'
            
            # Opportunity must exceed risk
            if opportunity_score <= risk_score:
                self.logger.debug(
                    f"[ACTION] SKIP - Opportunity "
                    f"({opportunity_score:.1f}) <= Risk ({risk_score:.1f})"
                )
                return 'SKIP'
            
            # All checks passed
            self.logger.info(
                f"[ACTION] BUY - {context.token_symbol}: "
                f"Opportunity={opportunity_score:.1f}, "
                f"Risk={risk_score:.1f}, Confidence={confidence_score:.1f}"
            )
            return 'BUY'
            
        except Exception as e:
            self.logger.error(
                f"[ACTION] Error determining action: {e}",
                exc_info=True
            )
            return 'SKIP'  # Safe default
    
    def calculate_position_size(
        self,
        risk_score: Decimal,
        opportunity_score: Decimal,
        context: MarketContext
    ) -> Decimal:
        """
        Calculate position size as percentage of portfolio.
        
        Args:
            risk_score: Risk assessment score
            opportunity_score: Opportunity assessment score
            context: Market context for volatility adjustment
            
        Returns:
            Position size percentage (e.g., 5.0 for 5%)
        """
        try:
            risk_score = self.converter.to_decimal(risk_score)
            opportunity_score = self.converter.to_decimal(opportunity_score)
            
            # Base size from config
            base_size = self.config.max_position_percent
            
            # Adjust based on opportunity/risk ratio
            ratio = opportunity_score / max(risk_score, Decimal('1'))
            
            if ratio > Decimal('2'):  # Great opportunity
                position_size = base_size * Decimal('1.0')
            elif ratio > Decimal('1.5'):  # Good opportunity
                position_size = base_size * Decimal('0.8')
            elif ratio > Decimal('1.2'):  # Moderate opportunity
                position_size = base_size * Decimal('0.6')
            else:  # Minimal opportunity
                position_size = base_size * Decimal('0.4')            
           
            # Adjust for volatility (higher volatility = smaller position)
            # Handle both MarketContext object and raw Decimal values
            if hasattr(context, 'volatility_index'):
                volatility = self.converter.to_decimal(
                    context.volatility_index,
                    Decimal('50')
                )
            else:
                # If context is not a MarketContext, use default volatility
                volatility = Decimal('50')
                
            if volatility > 70:
                position_size *= Decimal('0.7')
            elif volatility > 50:
                position_size *= Decimal('0.85')
            
            # Ensure within bounds
            # Ensure within bounds
            position_size = max(Decimal('1'), min(base_size, position_size))

            # Safe logging - handle both MarketContext and Decimal types
            token_symbol = getattr(context, 'token_symbol', 'UNKNOWN')
            self.logger.debug(
                f"[POSITION SIZE] {token_symbol}: {position_size:.2f}% "
                f"(Ratio={ratio:.2f}, Volatility={volatility:.1f})"
            )

            return position_size.quantize(Decimal('0.01'))
            
        except Exception as e:
            self.logger.error(
                f"[POSITION SIZE] Error calculating: {e}",
                exc_info=True
            )
            return Decimal('5')  # Safe default
    
    def calculate_stop_loss(self, risk_score: Decimal) -> Decimal:
        """
        Calculate stop loss percentage based on risk.
        
        Args:
            risk_score: Risk assessment score
            
        Returns:
            Stop loss percentage (e.g., 5.0 for 5%)
        """
        try:
            risk_score = self.converter.to_decimal(risk_score)
            
            # Higher risk = tighter stop loss
            if risk_score > 70:
                stop_loss = Decimal('3')  # 3% stop loss
            elif risk_score > 50:
                stop_loss = Decimal('5')  # 5% stop loss
            elif risk_score > 30:
                stop_loss = Decimal('7')  # 7% stop loss
            else:
                stop_loss = Decimal('10')  # 10% stop loss
            
            self.logger.debug(
                f"[STOP LOSS] {stop_loss}% (Risk={risk_score:.1f})"
            )
            
            return stop_loss
            
        except Exception as e:
            self.logger.error(
                f"[STOP LOSS] Error calculating: {e}",
                exc_info=True
            )
            return Decimal('5')  # Safe default
    
    def determine_execution_strategy(
        self,
        context: MarketContext,
        action: str
    ) -> Dict[str, Any]:
        """
        Determine execution strategy based on intel level and market conditions.
        
        Args:
            context: Market context with network and MEV data
            action: Trading action ('BUY', 'SKIP', etc.)
            
        Returns:
            Dictionary with execution strategy details
        """
        try:
            context = self.normalizer.normalize_context(context)
            
            if action in ['SKIP', 'HOLD']:
                return {
                    'mode': 'NONE',
                    'use_private_relay': False,
                    'gas_strategy': 'standard',
                    'max_gas_gwei': self.converter.to_decimal(
                        context.gas_price_gwei
                    )
                }
            
            # Determine gas strategy based on config
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
                congestion = self.converter.to_decimal(
                    context.network_congestion,
                    Decimal('50')
                )
                if congestion > 70:
                    gas_strategy = 'aggressive'
                    gas_multiplier = Decimal('1.5')
                else:
                    gas_strategy = 'standard'
                    gas_multiplier = Decimal('1.1')
            
            # Determine execution mode
            if self.config.decision_speed in ['ultra_fast', 'very_fast']:
                mode = 'FAST_LANE'
            elif self.converter.to_decimal(context.mev_threat_level, Decimal('50')) > 60:
                mode = 'SMART_LANE'
            else:
                mode = 'HYBRID'
            
            # MEV protection
            mev_threat = self.converter.to_decimal(
                context.mev_threat_level,
                Decimal('0')
            )
            sandwich_risk = self.converter.to_decimal(
                context.sandwich_risk,
                Decimal('0')
            )
            use_relay = (
                self.config.use_mev_protection or
                mev_threat > 70 or
                sandwich_risk > 60
            )
            
            self.logger.debug(
                f"[EXECUTION] Mode={mode}, Gas={gas_strategy}, Relay={use_relay}"
            )
            
            return {
                'mode': mode,
                'use_private_relay': use_relay,
                'gas_strategy': gas_strategy,
                'max_gas_gwei': self.converter.safe_multiply(
                    self.converter.to_decimal(context.gas_price_gwei),
                    gas_multiplier
                )
            }
            
        except Exception as e:
            self.logger.error(
                f"[EXECUTION] Error determining strategy: {e}",
                exc_info=True
            )
            return {
                'mode': 'SMART_LANE',
                'use_private_relay': True,
                'gas_strategy': 'standard',
                'max_gas_gwei': Decimal('30')
            }
    
    def generate_reasoning(
        self,
        action: str,
        risk_score: Decimal,
        opportunity_score: Decimal,
        confidence_score: Decimal,
        context: MarketContext
    ) -> str:
        """
        Generate detailed reasoning for the decision.
        
        Args:
            action: Trading action
            risk_score: Risk assessment score
            opportunity_score: Opportunity assessment score
            confidence_score: Confidence score
            context: Market context
            
        Returns:
            Detailed reasoning string
        """
        try:
            reasoning = f"Intel Level {self.intel_level} ({self.config.name}) Decision:\n"
            reasoning += f"Action: {action}\n"
            reasoning += f"Risk Assessment: {risk_score:.1f}/100\n"
            reasoning += f"Opportunity Score: {opportunity_score:.1f}/100\n"
            reasoning += f"Confidence: {confidence_score:.1f}/100\n"
            
            # Add price context if available
            if hasattr(context, 'current_price') and context.current_price:
                reasoning += f"Current Price: ${context.current_price:.2f}\n"
            if hasattr(context, 'trend'):
                reasoning += f"Price Trend: {context.trend}\n"
            if hasattr(context, 'momentum') and context.momentum:
                reasoning += f"1H Change: {context.momentum:+.2f}%\n"
            
            reasoning += "\n"
            
            if action == 'BUY':
                reasoning += "Rationale: Favorable opportunity with acceptable risk. "
                if context.trend_direction == 'bullish':
                    reasoning += "Bullish trend supports entry. "
                if hasattr(context, 'trend') and context.trend == 'bullish':
                    reasoning += "Price momentum is positive. "
                liquidity_score = self.converter.to_decimal(
                    context.liquidity_depth_score,
                    Decimal('0')
                )
                if liquidity_score > 70:
                    reasoning += "Good liquidity minimizes slippage. "
            elif action == 'SKIP':
                reasoning += "Rationale: "
                if risk_score > self.config.risk_tolerance:
                    reasoning += f"Risk ({risk_score:.1f}) exceeds tolerance ({self.config.risk_tolerance}). "
                if confidence_score < self.config.min_confidence_required:
                    reasoning += f"Insufficient confidence ({confidence_score:.1f} < {self.config.min_confidence_required}). "
            
            return reasoning
            
        except Exception as e:
            self.logger.error(
                f"[REASONING] Error generating reasoning: {e}",
                exc_info=True
            )
            return f"Decision: {action}"
    
    def identify_risk_factors(self, context: MarketContext) -> List[str]:
        """
        Identify key risk factors from market context.
        
        Args:
            context: Market context
            
        Returns:
            List of risk factor descriptions
        """
        try:
            context = self.normalizer.normalize_context(context)
            factors = []
            
            mev_threat = self.converter.to_decimal(
                context.mev_threat_level,
                Decimal('0')
            )
            volatility = self.converter.to_decimal(
                context.volatility_index,
                Decimal('0')
            )
            liquidity_score = self.converter.to_decimal(
                context.liquidity_depth_score,
                Decimal('100')
            )
            competing_bots = self.converter.to_decimal(
                context.competing_bots_detected,
                Decimal('0')
            )
            
            if mev_threat > 60:
                factors.append(f"High MEV threat ({mev_threat:.1f}/100)")
            if volatility > 70:
                factors.append(f"High volatility ({volatility:.1f}/100)")
            if liquidity_score < 40:
                factors.append(f"Poor liquidity depth ({liquidity_score:.1f}/100)")
            if context.chaos_event_detected:
                factors.append("Chaos event detected in market")
            if competing_bots > 5:
                factors.append(f"{int(competing_bots)} competing bots detected")
            
            return factors[:5]  # Top 5 risks
            
        except Exception as e:
            self.logger.error(
                f"[RISK FACTORS] Error identifying: {e}",
                exc_info=True
            )
            return []
    
    def identify_opportunity_factors(self, context: MarketContext) -> List[str]:
        """
        Identify opportunity factors from market context.
        
        Args:
            context: Market context
            
        Returns:
            List of opportunity factor descriptions
        """
        try:
            context = self.normalizer.normalize_context(context)
            factors = []
            
            volume_change = self.converter.to_decimal(
                context.volume_24h_change,
                Decimal('0')
            )
            liquidity_score = self.converter.to_decimal(
                context.liquidity_depth_score,
                Decimal('0')
            )
            congestion = self.converter.to_decimal(
                context.network_congestion,
                Decimal('100')
            )
            bot_success = self.converter.to_decimal(
                context.bot_success_rate,
                Decimal('100')
            )
            
            if context.trend_direction == 'bullish':
                factors.append("Bullish market trend")
            if hasattr(context, 'trend') and context.trend == 'bullish':
                factors.append("Positive price momentum")
            if volume_change > 50:
                factors.append(f"Volume surge ({volume_change:.1f}%)")
            if liquidity_score > 70:
                factors.append(f"Excellent liquidity ({liquidity_score:.1f}/100)")
            if congestion < 30:
                factors.append("Low network congestion")
            if bot_success < 40:
                factors.append("Low bot competition")
            
            return factors[:5]  # Top 5 opportunities
            
        except Exception as e:
            self.logger.error(
                f"[OPPORTUNITY FACTORS] Error identifying: {e}",
                exc_info=True
            )
            return []
    
    def generate_mitigation_strategies(self, context: MarketContext) -> List[str]:
        """
        Generate risk mitigation strategies.
        
        Args:
            context: Market context with risk indicators
            
        Returns:
            List of mitigation strategy descriptions
        """
        try:
            context = self.normalizer.normalize_context(context)
            strategies = []
            
            mev_threat = self.converter.to_decimal(
                context.mev_threat_level,
                Decimal('0')
            )
            volatility = self.converter.to_decimal(
                context.volatility_index,
                Decimal('0')
            )
            slippage = self.converter.to_decimal(
                context.expected_slippage,
                Decimal('0')
            )
            competing_bots = self.converter.to_decimal(
                context.competing_bots_detected,
                Decimal('0')
            )
            
            if mev_threat > 60:
                strategies.append("Use private relay for MEV protection")
            if volatility > 70:
                strategies.append("Reduce position size for volatility")
            if slippage > 3:
                strategies.append("Split trade to reduce slippage")
            if competing_bots > 5:
                strategies.append("Increase gas for competitive execution")
            
            return strategies
            
        except Exception as e:
            self.logger.error(
                f"[MITIGATION] Error generating strategies: {e}",
                exc_info=True
            )
            return []
    
    def assess_time_sensitivity(self, context: MarketContext) -> str:
        """
        Assess time sensitivity of the opportunity.
        
        Args:
            context: Market context
            
        Returns:
            Time sensitivity level: 'critical', 'high', 'medium', or 'low'
        """
        try:
            context = self.normalizer.normalize_context(context)
            
            volatility = self.converter.to_decimal(
                context.volatility_index,
                Decimal('0')
            )
            competing_bots = self.converter.to_decimal(
                context.competing_bots_detected,
                Decimal('0')
            )
            volume_change = self.converter.to_decimal(
                context.volume_24h_change,
                Decimal('0')
            )
            
            if context.chaos_event_detected:
                return 'critical'
            elif volatility > 70 or competing_bots > 10:
                return 'high'
            elif volume_change > 100 or competing_bots > 5:
                return 'medium'
            else:
                return 'low'
                
        except Exception as e:
            self.logger.error(
                f"[TIME SENSITIVITY] Error assessing: {e}",
                exc_info=True
            )
            return 'medium'  # Safe default