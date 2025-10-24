"""
Enhanced Intelligence Engine Base for Paper Trading Bot

This module provides the core intelligence infrastructure with separated
concerns for better maintainability and extensibility.

File: dexproject/paper_trading/intelligence/base.py
"""

import logging
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import IntEnum
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)


class IntelligenceLevel(IntEnum):
    """Intelligence level settings for the bot."""
    
    ULTRA_CAUTIOUS_1 = 1
    ULTRA_CAUTIOUS_2 = 2
    ULTRA_CAUTIOUS_3 = 3
    BALANCED_4 = 4
    BALANCED_5 = 5
    BALANCED_6 = 6
    AGGRESSIVE_7 = 7
    AGGRESSIVE_8 = 8
    AGGRESSIVE_9 = 9
    AUTONOMOUS_10 = 10


@dataclass
class MarketContext:
    """
    Complete market context for decision making.
    Combines token-level market data and network-level intelligence metrics.
    """
    
    # === Token-Level Data ===
    token_symbol: str
    token_address: Optional[str] = None
    current_price: Decimal = Decimal("0")
    price_24h_ago: Decimal = Decimal("0")
    volume_24h: Decimal = Decimal("0")
    liquidity_usd: Decimal = Decimal("0")
    holder_count: int = 0
    market_cap: Decimal = Decimal("0")
    volatility: Decimal = Decimal("0")
    trend: str = "neutral"
    momentum: Decimal = Decimal("0")
    support_levels: List[Decimal] = field(default_factory=list)
    resistance_levels: List[Decimal] = field(default_factory=list)

    # === Network Conditions ===
    gas_price_gwei: Decimal = Decimal("0")
    network_congestion: float = 0.0  # 0-100
    pending_tx_count: int = 0

    # === MEV Environment ===
    mev_threat_level: float = 0.0  # 0-100
    sandwich_risk: float = 0.0  # 0-100
    frontrun_probability: float = 0.0  # 0-100

    # === Competition ===
    competing_bots_detected: int = 0
    average_bot_gas_price: Decimal = Decimal("0")
    bot_success_rate: float = 0.0  # 0-100

    # === Liquidity ===
    pool_liquidity_usd: Decimal = Decimal("0")
    expected_slippage: Decimal = Decimal("0")
    liquidity_depth_score: float = 0.0  # 0-100

    # === Market State ===
    volatility_index: float = 0.0  # 0-100
    chaos_event_detected: bool = False
    trend_direction: str = "neutral"
    volume_24h_change: Decimal = Decimal("0")

    # === Historical Data ===
    recent_failures: int = 0
    success_rate_1h: float = 0.0
    average_profit_1h: Decimal = Decimal("0")

    # === Metadata ===
    timestamp: datetime = field(default_factory=datetime.now)
    confidence_in_data: float = 100.0  # 0-100


@dataclass
class TradingDecision:
    """Complete trading decision with reasoning."""
    
    # Core decision
    action: str  # 'BUY', 'SELL', 'HOLD', 'SKIP'
    token_address: str
    token_symbol: str
    
    # Sizing and risk
    position_size_percent: Decimal
    position_size_usd: Decimal
    stop_loss_percent: Optional[Decimal]
    take_profit_targets: List[Decimal]
    
    # Execution strategy
    execution_mode: str  # 'FAST_LANE', 'SMART_LANE', 'HYBRID'
    use_private_relay: bool
    gas_strategy: str  # 'standard', 'aggressive', 'ultra_aggressive'
    max_gas_price_gwei: Decimal
    
    # Confidence and reasoning
    overall_confidence: Decimal  # 0-100
    risk_score: Decimal  # 0-100
    opportunity_score: Decimal  # 0-100
    
    # Detailed reasoning
    primary_reasoning: str
    risk_factors: List[str]
    opportunity_factors: List[str]
    mitigation_strategies: List[str]
    
    # Intel level impact
    intel_level_used: int
    intel_adjustments: Dict[str, Any]
    
    # Timing
    time_sensitivity: str  # 'critical', 'high', 'medium', 'low'
    max_execution_time_ms: int
    
    # Metadata
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)
    processing_time_ms: float = 0


class IntelligenceEngine(ABC):
    """
    Abstract base class for intelligence engines.
    
    This provides the interface that all intelligence implementations
    must follow, ensuring consistency across different intel levels.
    """
    
    def __init__(self, intel_level: int = 5):
        """
        Initialize the intelligence engine.
        
        Args:
            intel_level: Intelligence level (1-10)
        """
        self.intel_level = IntelligenceLevel(intel_level)
        self.logger = logging.getLogger(f'{__name__}.{self.__class__.__name__}')
        
        # Risk and opportunity thresholds based on intel level
        self.risk_threshold = self._calculate_risk_threshold()
        self.opportunity_threshold = self._calculate_opportunity_threshold()
        self.confidence_threshold = self._calculate_confidence_threshold()
        
        self.logger.info(
            f"Intelligence engine initialized: Level={intel_level}, "
            f"Risk threshold={self.risk_threshold}, "
            f"Opportunity threshold={self.opportunity_threshold}, "
            f"Confidence threshold={self.confidence_threshold}"
        )
        
    def _calculate_risk_threshold(self) -> Decimal:
        """Calculate risk threshold based on intel level."""
        try:
            if self.intel_level <= 3:
                return Decimal('30')  # Very low risk tolerance
            elif self.intel_level <= 6:
                return Decimal('60')  # Moderate risk tolerance
            elif self.intel_level <= 9:
                return Decimal('80')  # High risk tolerance
            else:
                return Decimal('100')  # Autonomous - dynamic risk
        except Exception as e:
            self.logger.error(f"Error calculating risk threshold: {e}", exc_info=True)
            return Decimal('60')  # Safe default
    
    def _calculate_opportunity_threshold(self) -> Decimal:
        """Calculate opportunity threshold based on intel level."""
        try:
            if self.intel_level <= 3:
                return Decimal('80')  # Only very high opportunity
            elif self.intel_level <= 6:
                return Decimal('50')  # Moderate opportunity
            elif self.intel_level <= 9:
                return Decimal('30')  # Lower threshold
            else:
                return Decimal('20')  # Autonomous - considers all
        except Exception as e:
            self.logger.error(f"Error calculating opportunity threshold: {e}", exc_info=True)
            return Decimal('50')  # Safe default
    
    def _calculate_confidence_threshold(self) -> Decimal:
        """Calculate confidence threshold based on intel level."""
        try:
            if self.intel_level <= 3:
                return Decimal('90')  # Very high confidence required
            elif self.intel_level <= 6:
                return Decimal('60')  # Moderate confidence
            elif self.intel_level <= 9:
                return Decimal('40')  # Lower confidence acceptable
            else:
                return Decimal('30')  # Autonomous - adaptive
        except Exception as e:
            self.logger.error(f"Error calculating confidence threshold: {e}", exc_info=True)
            return Decimal('60')  # Safe default
    
    @abstractmethod
    async def analyze_market(self, token_address: str) -> MarketContext:
        """
        Analyze current market conditions.
        
        Args:
            token_address: Token to analyze
            
        Returns:
            Complete market context
        """
        pass
    
    @abstractmethod
    async def make_decision(
        self,
        market_context: MarketContext,
        account_balance: Decimal,
        existing_positions: List[Dict[str, Any]]
    ) -> TradingDecision:
        """
        Make a trading decision based on market context.
        
        Args:
            market_context: Current market conditions
            account_balance: Available balance
            existing_positions: Current open positions
            
        Returns:
            Complete trading decision with reasoning
        """
        pass
    
    def update_market_context(self, market_context: MarketContext) -> None:
        """
        Update engine with latest market context for historical tracking.
        
        This method allows the intelligence engine to track market conditions
        over time, enabling trend analysis, pattern recognition, and better
        decision-making. Critical for Real Data Integration (Phase 4-5).
        
        Args:
            market_context: Latest market conditions with real-time data
        
        Notes:
            - Default implementation does nothing (base class behavior)
            - Subclasses like IntelSliderEngine override to enable tracking
            - Called by MarketAnalyzer after creating market context
            - Enables Level 10 autonomous learning
            - Non-blocking: errors are logged but don't stop execution
        
        Example:
            >>> engine = IntelSliderEngine(intel_level=5)
            >>> context = MarketContext(
            ...     token_symbol='WETH',
            ...     current_price=Decimal('2000'),
            ...     volatility=Decimal('0.15')
            ... )
            >>> engine.update_market_context(context)
            >>> # Engine now tracks this token's price history
        """
        try:
            # Default implementation: do nothing
            # Subclasses can override to add market tracking functionality
            self.logger.debug(
                f"[BASE] update_market_context called for {market_context.token_symbol} "
                f"(base implementation - no tracking)"
            )
        except Exception as e:
            # Catch any errors in logging to prevent crashes
            self.logger.error(
                f"[BASE] Error in update_market_context default implementation: {e}",
                exc_info=True
            )
    
    def adjust_for_intel_level(self, base_decision: TradingDecision) -> TradingDecision:
        """
        Adjust decision based on intelligence level.
        
        Args:
            base_decision: Initial trading decision
            
        Returns:
            Adjusted decision based on intel level
        """
        try:
            decision = base_decision
            
            self.logger.debug(
                f"[INTEL ADJUST] Adjusting decision for level {self.intel_level}: "
                f"Action={decision.action}, Risk={decision.risk_score}"
            )
            
            # Cautious levels (1-3): Reduce risk, increase safety
            if self.intel_level <= 3:
                decision.position_size_percent *= Decimal('0.5')  # Half position size
                decision.use_private_relay = True  # Always use protection
                decision.gas_strategy = 'standard'  # Don't compete on gas
                
                if decision.risk_score > 30:
                    decision.action = 'SKIP'
                    decision.primary_reasoning = (
                        f"Intel Level {self.intel_level} (Ultra Cautious): "
                        f"Risk score {decision.risk_score} exceeds threshold. "
                        "Skipping trade for safety."
                    )
                    self.logger.info(
                        f"[INTEL ADJUST] Ultra Cautious mode: Skipping trade due to "
                        f"risk score {decision.risk_score} > 30"
                    )
            
            # Balanced levels (4-6): Moderate adjustments
            elif self.intel_level <= 6:
                decision.position_size_percent *= Decimal('0.8')
                if decision.risk_score > 70:
                    decision.use_private_relay = True
                
                if decision.risk_score > 60:
                    decision.gas_strategy = 'standard'
                else:
                    decision.gas_strategy = 'aggressive'
                
                self.logger.debug(
                    f"[INTEL ADJUST] Balanced mode: Position size adjusted to "
                    f"{decision.position_size_percent}%, Gas={decision.gas_strategy}"
                )
            
            # Aggressive levels (7-9): Push boundaries
            elif self.intel_level <= 9:
                decision.position_size_percent *= Decimal('1.2')  # Increase size
                decision.gas_strategy = 'aggressive'
                
                # Only skip if extremely risky
                if decision.risk_score > 90:
                    decision.action = 'SKIP'
                    decision.primary_reasoning = (
                        f"Intel Level {self.intel_level} (Aggressive): "
                        f"Even for aggressive trading, risk score {decision.risk_score} "
                        "is too extreme."
                    )
                    self.logger.warning(
                        f"[INTEL ADJUST] Aggressive mode: Skipping extremely risky trade "
                        f"(risk score {decision.risk_score} > 90)"
                    )
                else:
                    self.logger.debug(
                        f"[INTEL ADJUST] Aggressive mode: Increasing position to "
                        f"{decision.position_size_percent}%"
                    )
            
            # Autonomous (10): Dynamic optimization
            else:
                # Use machine learning or advanced heuristics
                decision = self._autonomous_optimization(decision)
            
            # Record intel adjustments
            decision.intel_adjustments = {
                'original_position_size': float(base_decision.position_size_percent),
                'adjusted_position_size': float(decision.position_size_percent),
                'risk_threshold_used': float(self.risk_threshold),
                'opportunity_threshold_used': float(self.opportunity_threshold),
                'confidence_threshold_used': float(self.confidence_threshold),
                'intel_level': int(self.intel_level)
            }
            
            self.logger.info(
                f"[INTEL ADJUST] Decision adjusted: "
                f"Position {base_decision.position_size_percent}% → {decision.position_size_percent}%, "
                f"Action={decision.action}"
            )
            
            return decision
            
        except Exception as e:
            self.logger.error(
                f"[INTEL ADJUST] Error adjusting decision for intel level: {e}",
                exc_info=True
            )
            # Return original decision if adjustment fails
            return base_decision
    
    def _autonomous_optimization(self, decision: TradingDecision) -> TradingDecision:
        """
        Autonomous optimization for level 10.
        
        This method would integrate with machine learning models
        or advanced statistical analysis in production.
        
        Args:
            decision: Base trading decision
            
        Returns:
            Optimized decision
        """
        try:
            # Placeholder for ML integration
            # In production, this would:
            # 1. Query historical performance data
            # 2. Run ML models for prediction
            # 3. Optimize based on personal trading patterns
            # 4. Adapt to current market regime
            
            self.logger.info(
                "[AUTONOMOUS] Optimizing decision with advanced algorithms"
            )
            
            # For now, make balanced adjustments
            if decision.risk_score < 40 and decision.opportunity_score > 70:
                decision.position_size_percent *= Decimal('1.5')
                decision.gas_strategy = 'ultra_aggressive'
                decision.primary_reasoning = (
                    "Autonomous AI: Exceptional opportunity detected with low risk. "
                    "Maximizing position based on historical patterns and current market regime."
                )
                self.logger.info(
                    f"[AUTONOMOUS] Exceptional opportunity: Increasing position to "
                    f"{decision.position_size_percent}% (Risk={decision.risk_score}, "
                    f"Opportunity={decision.opportunity_score})"
                )
            else:
                self.logger.debug(
                    f"[AUTONOMOUS] Standard optimization applied "
                    f"(Risk={decision.risk_score}, Opportunity={decision.opportunity_score})"
                )
            
            return decision
            
        except Exception as e:
            self.logger.error(
                f"[AUTONOMOUS] Error in autonomous optimization: {e}",
                exc_info=True
            )
            return decision
    
    def generate_thought_log(self, decision: TradingDecision) -> str:
        """
        Generate a detailed thought log for the decision.
        
        Args:
            decision: Trading decision to explain
            
        Returns:
            Formatted thought log
        """
        try:
            thoughts = []
            
            # Header
            thoughts.append(f"=== AI Trading Decision - Intel Level {self.intel_level} ===")
            thoughts.append(f"Token: {decision.token_symbol} ({decision.token_address[:10]}...)")
            thoughts.append(f"Decision: {decision.action}")
            thoughts.append(f"Confidence: {decision.overall_confidence}%")
            thoughts.append("")
            
            # Risk Assessment
            thoughts.append("[RISK ASSESSMENT]")
            thoughts.append(f"Risk Score: {decision.risk_score}/100")
            if decision.risk_factors:
                for factor in decision.risk_factors[:3]:
                    thoughts.append(f"  • {factor}")
            else:
                thoughts.append("  • No specific risk factors identified")
            thoughts.append("")
            
            # Opportunity Analysis
            thoughts.append("[OPPORTUNITY ANALYSIS]")
            thoughts.append(f"Opportunity Score: {decision.opportunity_score}/100")
            if decision.opportunity_factors:
                for factor in decision.opportunity_factors[:3]:
                    thoughts.append(f"  • {factor}")
            else:
                thoughts.append("  • No specific opportunities identified")
            thoughts.append("")
            
            # Decision Reasoning
            thoughts.append("[DECISION REASONING]")
            thoughts.append(decision.primary_reasoning)
            thoughts.append("")
            
            # Execution Strategy
            thoughts.append("[EXECUTION STRATEGY]")
            thoughts.append(f"Mode: {decision.execution_mode}")
            thoughts.append(f"Position Size: {decision.position_size_percent}% of portfolio (${decision.position_size_usd:.2f})")
            thoughts.append(f"Gas Strategy: {decision.gas_strategy}")
            if decision.use_private_relay:
                thoughts.append("MEV Protection: ENABLED (Private Relay)")
            thoughts.append("")
            
            # Intel Level Impact
            thoughts.append("[INTELLIGENCE ADJUSTMENTS]")
            thoughts.append(f"Intel Level {self.intel_level} Impact:")
            for key, value in decision.intel_adjustments.items():
                thoughts.append(f"  • {key}: {value}")
            
            result = "\n".join(thoughts)
            
            self.logger.debug(
                f"[THOUGHT LOG] Generated log for {decision.token_symbol}: "
                f"{len(result)} characters"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(
                f"[THOUGHT LOG] Error generating thought log: {e}",
                exc_info=True
            )
            return f"Error generating thought log for {decision.token_symbol}"