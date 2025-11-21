"""
Decision Engine for Intel Slider System
Handles all trading decision-making logic.

This module orchestrates:
- Trading decision creation (BUY/SELL/HOLD/SKIP)
- Position exit evaluation
- Risk and opportunity score calculation
- Decision reasoning generation
- ML feature collection (Level 10)

File: dexproject/paper_trading/intelligence/core/decision_engine.py
"""
import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional

from django.utils import timezone

from paper_trading.intelligence.core.base import (
    MarketContext,
    TradingDecision
)
from paper_trading.intelligence.strategies.decision_maker import DecisionMaker
from paper_trading.intelligence.data.ml_features import MLFeatureCollector


logger = logging.getLogger(__name__)


class DecisionEngine:
    """
    Orchestrates trading decision-making process.

    This class coordinates the decision-making pipeline:
    1. Validates data quality
    2. Checks position limits
    3. Builds decisions using DecisionMaker
    4. Collects ML features (Level 10)
    5. Tracks historical decisions

    Attributes:
        decision_maker: DecisionMaker instance for strategy logic
        ml_collector: MLFeatureCollector for Level 10
        intel_level: Current intelligence level (1-10)
        historical_decisions: Past trading decisions
        logger: Logger instance for structured logging
    """

    def __init__(
        self,
        decision_maker: DecisionMaker,
        ml_collector: MLFeatureCollector,
        intel_level: int = 5
    ):
        """
        Initialize the Decision Engine.

        Args:
            decision_maker: DecisionMaker instance
            ml_collector: MLFeatureCollector instance
            intel_level: Intelligence level (1-10)
        """
        self.decision_maker = decision_maker
        self.ml_collector = ml_collector
        self.intel_level = intel_level
        self.historical_decisions: List[TradingDecision] = []
        self.logger = logger

    async def make_decision(
        self,
        market_context: MarketContext,
        account_balance: Decimal,
        existing_positions: List[Any],
        portfolio_value: Optional[Decimal] = None,
        token_address: Optional[str] = None,
        token_symbol: Optional[str] = None,
        position_entry_price: Optional[Decimal] = None,
        position_current_value: Optional[Decimal] = None,
        position_invested: Optional[Decimal] = None,
        position_hold_time_hours: Optional[float] = None
    ) -> TradingDecision:
        """
        Make a trading decision based on analyzed market context.

        This method implements the abstract method from IntelligenceEngine.
        It uses the DecisionMaker to create a trading decision and then
        applies intel-level adjustments.

        BACKWARD COMPATIBILITY: Accepts deprecated 'portfolio_value' parameter
        for compatibility with legacy code. The base class uses 'account_balance'
        as the primary parameter.

        PHASE 1: Checks position limits before making BUY decisions (handled by caller).

        Args:
            market_context: Analyzed market context with comprehensive data
            account_balance: Current account balance in USD (base class parameter)
            existing_positions: List of existing positions (base class parameter)
            portfolio_value: DEPRECATED - uses account_balance instead
            token_address: DEPRECATED - already in market_context
            token_symbol: DEPRECATED - already in market_context
            position_entry_price: Optional entry price for position evaluation
            position_current_value: Optional current value for position evaluation
            position_invested: Optional invested amount for position evaluation
            position_hold_time_hours: Optional hold time for position evaluation

        Returns:
            Complete trading decision with reasoning and execution strategy

        Raises:
            Exception: If decision-making fails critically
        """
        try:
            # Use account_balance as the primary portfolio value
            portfolio_val = account_balance

            self.logger.debug(
                f"[MAKE_DECISION] Using account_balance: ${account_balance:.2f}"
            )

            # If portfolio_value was provided, log a deprecation warning
            if portfolio_value is not None and portfolio_value != account_balance:
                self.logger.warning(
                    f"[MAKE_DECISION] DEPRECATED: portfolio_value parameter ignored. "
                    f"Using account_balance=${account_balance:.2f} instead of "
                    f"portfolio_value=${portfolio_value:.2f}"
                )

            # Log if legacy parameters were provided
            if existing_positions is not None and len(existing_positions) > 0:
                self.logger.debug(
                    f"[MAKE_DECISION] Received {len(existing_positions)} existing positions"
                )

            if token_address and token_address != market_context.token_address:
                self.logger.debug(
                    "[MAKE_DECISION] DEPRECATED: Token address parameter provided "
                    "but using value from market_context"
                )

            if token_symbol and token_symbol != market_context.token_symbol:
                self.logger.debug(
                    "[MAKE_DECISION] DEPRECATED: Token symbol parameter provided "
                    "but using value from market_context"
                )

            self.logger.info(
                f"[MAKE_DECISION] Creating decision for {market_context.token_symbol} "
                f"(Portfolio: ${portfolio_val:.2f})"
            )

            # Step 1: Check if we should skip due to poor data quality
            if market_context.confidence_in_data < 40.0:
                self.logger.warning(
                    f"[MAKE_DECISION] Low data confidence "
                    f"({market_context.confidence_in_data:.1f}%), skipping trade"
                )
                return self.create_skip_decision(
                    market_context,
                    f"Data confidence too low: {market_context.confidence_in_data:.1f}%"
                )

            # Step 2: Build decision using DecisionMaker components
            # Pass position data if we have it
            decision = self.build_decision_from_context(
                market_context=market_context,
                portfolio_value=portfolio_val,
                position_entry_price=position_entry_price,
                position_current_value=position_current_value,
                position_invested=position_invested,
                position_hold_time_hours=position_hold_time_hours
            )

            self.logger.debug(
                f"[MAKE_DECISION] Base decision: {decision.action}, "
                f"Confidence={decision.overall_confidence}%, "
                f"Risk={decision.risk_score}, Opportunity={decision.opportunity_score}"
            )

            # Step 3: Store decision in history for learning
            self.historical_decisions.append(decision)
            if len(self.historical_decisions) > 100:
                self.historical_decisions.pop(0)

            # Step 4: Collect ML features if Level 10
            if self.intel_level == 10:
                try:
                    # Attempt to collect ML features
                    if hasattr(self.ml_collector, 'collect_features'):
                        self.ml_collector.collect_features(
                            context=market_context,
                            decision=decision
                        )
                    else:
                        self.logger.debug(
                            "[MAKE_DECISION] ML collector has no collect_features method"
                        )
                except Exception as ml_error:
                    self.logger.warning(
                        f"[MAKE_DECISION] ML feature collection failed: {ml_error}"
                    )

            self.logger.info(
                f"[MAKE_DECISION] Final decision: {decision.action} "
                f"{market_context.token_symbol} "
                f"(Confidence: {decision.overall_confidence:.1f}%)"
            )

            return decision

        except Exception as decision_error:
            self.logger.error(
                f"[MAKE_DECISION] Fatal error in decision making: {decision_error}",
                exc_info=True
            )

            # Return safe skip decision
            return self.create_skip_decision(
                market_context,
                f"Decision making error: {str(decision_error)}"
            )

    async def evaluate_position_exit(
        self,
        market_context: MarketContext,
        position_data: Dict[str, Any],
        account_balance: Decimal,
        existing_positions: Dict[str, Any]
    ) -> TradingDecision:
        """
        Evaluate whether to exit an existing position (SELL decision).

        This method analyzes an existing position and decides whether it's time
        to sell based on:
        - Market conditions changing
        - Position P&L performance
        - Risk increasing
        - Better opportunities elsewhere

        Args:
            market_context: Current market context for the token
            position_data: Information about the existing position
            account_balance: Current account balance
            existing_positions: All existing positions

        Returns:
            TradingDecision with SELL, HOLD, or SKIP action
        """
        try:
            # Extract position information
            entry_price = Decimal(str(position_data.get('entry_price', 0)))
            current_price = Decimal(str(position_data.get('current_price', 0)))
            invested_usd = Decimal(str(position_data.get('invested_usd', 0)))
            current_value_usd = Decimal(str(position_data.get('current_value_usd', 0)))
            hold_time_hours = float(position_data.get('hold_time_hours', 0))

            self.logger.info(
                f"[EVALUATE EXIT] Analyzing position for {market_context.token_symbol}: "
                f"Entry=${entry_price:.4f}, Current=${current_price:.4f}, "
                f"Hold time={hold_time_hours:.1f}h"
            )

            # Use make_decision with position parameters to determine exit
            decision = await self.make_decision(
                market_context=market_context,
                account_balance=account_balance,
                existing_positions=list(existing_positions.values()) if existing_positions else [],
                position_entry_price=entry_price,
                position_current_value=current_value_usd,
                position_invested=invested_usd,
                position_hold_time_hours=hold_time_hours
            )

            self.logger.info(
                f"[EVALUATE EXIT] Decision for {market_context.token_symbol}: "
                f"{decision.action} (Confidence: {decision.overall_confidence:.1f}%)"
            )

            return decision

        except Exception as exit_error:
            self.logger.error(
                f"[EVALUATE EXIT] Error evaluating position exit: {exit_error}",
                exc_info=True
            )
            return self.create_skip_decision(
                market_context,
                f"Position exit evaluation error: {str(exit_error)}"
            )

    def build_decision_from_context(
        self,
        market_context: MarketContext,
        portfolio_value: Decimal,
        position_entry_price: Optional[Decimal] = None,
        position_current_value: Optional[Decimal] = None,
        position_invested: Optional[Decimal] = None,
        position_hold_time_hours: Optional[float] = None
    ) -> TradingDecision:
        """
        Build a trading decision from market context using DecisionMaker.

        This is a helper method that delegates to DecisionMaker components
        to build a complete trading decision.

        Args:
            market_context: Analyzed market context
            portfolio_value: Current portfolio value
            position_entry_price: Optional entry price for SELL evaluation
            position_current_value: Optional current value for SELL evaluation
            position_invested: Optional invested amount for SELL evaluation
            position_hold_time_hours: Optional hold time for SELL evaluation

        Returns:
            Complete TradingDecision object
        """
        # Build comprehensive analysis dict from context
        comprehensive_analysis = {
            'gas_analysis': {
                'current_gas_gwei': float(market_context.gas_price_gwei),
                'network_congestion': market_context.network_congestion
            },
            'liquidity': {
                'pool_liquidity_usd': float(market_context.pool_liquidity_usd),
                'expected_slippage_percent': float(market_context.expected_slippage),
                'liquidity_depth_score': market_context.liquidity_depth_score
            },
            'volatility': {
                'volatility_index': market_context.volatility_index,
                'trend_direction': market_context.trend_direction
            },
            'mev_analysis': {
                'threat_level': market_context.mev_threat_level,
                'sandwich_attack_risk': market_context.sandwich_risk,
                'frontrun_probability': market_context.frontrun_probability
            },
            'market_state': {
                'chaos_event_detected': market_context.chaos_event_detected
            }
        }

        # Calculate risk and opportunity scores
        risk_score = self.decision_maker.calculate_risk_score(
            market_context,
            comprehensive_analysis
        )
        opp_score = self.decision_maker.calculate_opportunity_score(
            market_context,
            comprehensive_analysis
        )

        # Calculate overall confidence
        conf_score = self.decision_maker.calculate_confidence_score(
            risk_score,
            opp_score,
            market_context
        )

        # Determine if there is an existing position
        has_position = (position_entry_price is not None and position_invested is not None)

        # DEBUG: Log position data
        self.logger.info(
            f"[BUILD DECISION] has_position={has_position}, "
            f"entry_price={position_entry_price}, "
            f"invested={position_invested}, "
            f"hold_time={position_hold_time_hours}"
        )

        # Determine action (with position data for SELL evaluation)
        action = self.decision_maker.determine_action(
            risk_score=risk_score,
            opportunity_score=opp_score,
            confidence_score=conf_score,
            context=market_context,
            has_position=has_position,
            position_entry_price=position_entry_price,
            position_current_value=position_current_value,
            position_invested=position_invested,
            position_hold_time_hours=position_hold_time_hours
        )

        # Position sizing
        # Position sizing
        pos_pct = Decimal('0')
        pos_usd = Decimal('0')

        if action == 'BUY':
            pos_pct = self.decision_maker.calculate_position_size(
                risk_score,
                opp_score,
                market_context
            )
            pos_usd = (pos_pct / Decimal('100')) * portfolio_value

            # Apply max_trade_size_usd limit if configured
            if hasattr(self.decision_maker, 'strategy_config') and self.decision_maker.strategy_config and hasattr(self.decision_maker.strategy_config, 'max_trade_size_usd'):
                max_trade_usd = Decimal(str(self.decision_maker.strategy_config.max_trade_size_usd))
                if max_trade_usd > 0 and pos_usd > max_trade_usd:
                    self.logger.info(
                        f"[POSITION SIZE] 💰 USD limit applied: ${max_trade_usd:.2f} "
                        f"(was ${pos_usd:.2f} from {pos_pct:.2f}% of portfolio)"
                    )
                    pos_usd = max_trade_usd
                    # Recalculate percentage based on capped USD amount
                    pos_pct = (pos_usd / portfolio_value) * Decimal('100')

        # 🆕 CRITICAL FIX: For SELL decisions, use the position's current value
        elif action == 'SELL':
            if position_current_value is not None:
                pos_usd = Decimal(str(position_current_value))
                if portfolio_value > 0:
                    pos_pct = (pos_usd / portfolio_value) * Decimal('100')
                self.logger.info(
                    f"[POSITION SIZE] SELL position size: ${pos_usd:.2f} "
                    f"({pos_pct:.2f}% of portfolio)"
                )
            else:
                self.logger.warning(
                    "[POSITION SIZE] SELL decision but no position_current_value provided!"
                )

        # Execution parameters
        stop_loss = self.decision_maker.calculate_stop_loss(risk_score)

        # Determine execution strategy
        exec_strategy = self.decision_maker.determine_execution_strategy(
            market_context,
            action
        )

        # Extract values from dictionary
        exec_mode = exec_strategy.get('mode', 'SMART_LANE')
        priv_relay = exec_strategy.get('use_private_relay', True)
        gas_strat = exec_strategy.get('gas_strategy', 'standard')
        max_gas = exec_strategy.get('max_gas_gwei', Decimal('30'))

        # Reasoning
        reason = self.decision_maker.generate_reasoning(
            action,
            risk_score,
            opp_score,
            conf_score,
            market_context
        )
        risk_facts = self.decision_maker.identify_risk_factors(market_context)
        opp_facts = self.decision_maker.identify_opportunity_factors(market_context)
        mitigations = self.decision_maker.generate_mitigation_strategies(market_context)
        time_sens = self.decision_maker.assess_time_sensitivity(market_context)

        # Build and return TradingDecision
        return TradingDecision(
            action=action,
            token_address=market_context.token_address or "",
            token_symbol=market_context.token_symbol,
            position_size_percent=pos_pct,
            position_size_usd=pos_usd,
            stop_loss_percent=stop_loss,
            take_profit_targets=[],
            execution_mode=exec_mode,
            use_private_relay=priv_relay,
            gas_strategy=gas_strat,
            max_gas_price_gwei=max_gas,
            overall_confidence=conf_score,
            risk_score=risk_score,
            opportunity_score=opp_score,
            primary_reasoning=reason,
            risk_factors=risk_facts,
            opportunity_factors=opp_facts,
            mitigation_strategies=mitigations,
            intel_level_used=self.intel_level,
            intel_adjustments={},
            time_sensitivity=time_sens,
            max_execution_time_ms=5000 if time_sens == 'critical' else 15000,
            processing_time_ms=0
        )

    def create_skip_decision(
        self,
        market_context: MarketContext,
        reason: str
    ) -> TradingDecision:
        """
        Create a SKIP decision with the given reason.

        Args:
            market_context: Market context for the decision
            reason: Reason for skipping

        Returns:
            TradingDecision with action='SKIP'
        """
        return TradingDecision(
            action='SKIP',
            token_address=market_context.token_address or "",
            token_symbol=market_context.token_symbol,
            position_size_percent=Decimal('0'),
            position_size_usd=Decimal('0'),
            stop_loss_percent=Decimal('0'),
            take_profit_targets=[],
            execution_mode='standard',
            use_private_relay=False,
            gas_strategy='standard',
            max_gas_price_gwei=Decimal('50'),
            overall_confidence=Decimal('0'),
            risk_score=Decimal('100'),
            opportunity_score=Decimal('0'),
            primary_reasoning=reason,
            risk_factors=[reason],
            opportunity_factors=[],
            mitigation_strategies=[],
            intel_level_used=self.intel_level,
            intel_adjustments={},
            time_sensitivity='low',
            max_execution_time_ms=15000,
            processing_time_ms=0
        )

    def get_ml_training_data(self) -> List[Dict[str, Any]]:
        """
        Get ML training data (Level 10 only).

        Returns:
            List of ML training samples
        """
        return self.ml_collector.get_training_data()

    def get_historical_decisions(self) -> List[TradingDecision]:
        """
        Get historical decisions for analysis.

        Returns:
            List of past trading decisions
        """
        return self.historical_decisions

    def clear_history(self) -> None:
        """Clear historical decisions."""
        self.historical_decisions.clear()
        self.logger.info("[DECISION ENGINE] Cleared historical decisions")