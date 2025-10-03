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
    """Complete market context for decision making."""
    
    # Network conditions
    gas_price_gwei: Decimal
    network_congestion: float  # 0-100
    pending_tx_count: int
    
    # MEV environment
    mev_threat_level: float  # 0-100
    sandwich_risk: float  # 0-100
    frontrun_probability: float  # 0-100
    
    # Competition
    competing_bots_detected: int
    average_bot_gas_price: Decimal
    bot_success_rate: float  # 0-100
    
    # Liquidity
    pool_liquidity_usd: Decimal
    expected_slippage: Decimal
    liquidity_depth_score: float  # 0-100
    
    # Market state
    volatility_index: float  # 0-100
    chaos_event_detected: bool
    trend_direction: str  # 'bullish', 'bearish', 'neutral'
    volume_24h_change: Decimal
    
    # Historical data
    recent_failures: int
    success_rate_1h: float
    average_profit_1h: Decimal
    
    # Metadata
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
        
    def _calculate_risk_threshold(self) -> Decimal:
        """Calculate risk threshold based on intel level."""
        if self.intel_level <= 3:
            return Decimal('30')  # Very low risk tolerance
        elif self.intel_level <= 6:
            return Decimal('60')  # Moderate risk tolerance
        elif self.intel_level <= 9:
            return Decimal('80')  # High risk tolerance
        else:
            return Decimal('100')  # Autonomous - dynamic risk
    
    def _calculate_opportunity_threshold(self) -> Decimal:
        """Calculate opportunity threshold based on intel level."""
        if self.intel_level <= 3:
            return Decimal('80')  # Only very high opportunity
        elif self.intel_level <= 6:
            return Decimal('50')  # Moderate opportunity
        elif self.intel_level <= 9:
            return Decimal('30')  # Lower threshold
        else:
            return Decimal('20')  # Autonomous - considers all
    
    def _calculate_confidence_threshold(self) -> Decimal:
        """Calculate confidence threshold based on intel level."""
        if self.intel_level <= 3:
            return Decimal('90')  # Very high confidence required
        elif self.intel_level <= 6:
            return Decimal('60')  # Moderate confidence
        elif self.intel_level <= 9:
            return Decimal('40')  # Lower confidence acceptable
        else:
            return Decimal('30')  # Autonomous - adaptive
    
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
    
    def adjust_for_intel_level(self, base_decision: TradingDecision) -> TradingDecision:
        """
        Adjust decision based on intelligence level.
        
        Args:
            base_decision: Initial trading decision
            
        Returns:
            Adjusted decision based on intel level
        """
        decision = base_decision
        
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
        
        # Balanced levels (4-6): Moderate adjustments
        elif self.intel_level <= 6:
            decision.position_size_percent *= Decimal('0.8')
            if decision.risk_score > 70:
                decision.use_private_relay = True
            
            if decision.risk_score > 60:
                decision.gas_strategy = 'standard'
            else:
                decision.gas_strategy = 'aggressive'
        
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
            'confidence_threshold_used': float(self.confidence_threshold)
        }
        
        return decision
    
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
        # Placeholder for ML integration
        # In production, this would:
        # 1. Query historical performance data
        # 2. Run ML models for prediction
        # 3. Optimize based on personal trading patterns
        # 4. Adapt to current market regime
        
        self.logger.info("Autonomous mode: Optimizing decision with advanced algorithms")
        
        # For now, make balanced adjustments
        if decision.risk_score < 40 and decision.opportunity_score > 70:
            decision.position_size_percent *= Decimal('1.5')
            decision.gas_strategy = 'ultra_aggressive'
            decision.primary_reasoning = (
                "Autonomous AI: Exceptional opportunity detected with low risk. "
                "Maximizing position based on historical patterns and current market regime."
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
        thoughts = []
        
        # Header
        thoughts.append(f"=== AI Trading Decision - Intel Level {self.intel_level} ===")
        thoughts.append(f"Token: {decision.token_symbol} ({decision.token_address[:10]}...)")
        thoughts.append(f"Decision: {decision.action}")
        thoughts.append("")
        
        # Risk Assessment
        thoughts.append("[RISK ASSESSMENT]")
        thoughts.append(f"Risk Score: {decision.risk_score}/100")
        for factor in decision.risk_factors[:3]:
            thoughts.append(f"  • {factor}")
        thoughts.append("")
        
        # Opportunity Analysis
        thoughts.append("[OPPORTUNITY ANALYSIS]")
        thoughts.append(f"Opportunity Score: {decision.opportunity_score}/100")
        for factor in decision.opportunity_factors[:3]:
            thoughts.append(f"  • {factor}")
        thoughts.append("")
        
        # Decision Reasoning
        thoughts.append("[DECISION REASONING]")
        thoughts.append(decision.primary_reasoning)
        thoughts.append("")
        
        # Execution Strategy
        thoughts.append("[EXECUTION STRATEGY]")
        thoughts.append(f"Mode: {decision.execution_mode}")
        thoughts.append(f"Position Size: {decision.position_size_percent}% of portfolio")
        thoughts.append(f"Gas Strategy: {decision.gas_strategy}")
        if decision.use_private_relay:
            thoughts.append("MEV Protection: ENABLED (Private Relay)")
        thoughts.append("")
        
        # Intel Level Impact
        thoughts.append("[INTELLIGENCE ADJUSTMENTS]")
        thoughts.append(f"Intel Level {self.intel_level} Impact:")
        for key, value in decision.intel_adjustments.items():
            thoughts.append(f"  • {key}: {value}")
        
        return "\n".join(thoughts)