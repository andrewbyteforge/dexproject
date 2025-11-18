"""
Market Helpers for Paper Trading Bot - Utility Functions Module

This module provides helper utilities for the paper trading bot including:
- Trade cooldown management
- Auto-close position checks (stop-loss/take-profit)
- AI thought logging
- JSON sanitization
- Confidence level calculations
- Arbitrage statistics

File: dexproject/paper_trading/bot/market_helpers.py
"""

import logging
import math
from decimal import Decimal
from typing import Dict, Optional, Any
from datetime import timedelta

from django.utils import timezone

from paper_trading.models import (
    PaperTradingAccount,
    PaperStrategyConfiguration,
    PaperAIThoughtLog
)

from paper_trading.intelligence.core.base import TradingDecision
from paper_trading.intelligence.core.intel_slider import IntelSliderEngine

logger = logging.getLogger(__name__)


class MarketHelpers:
    """
    Helper utilities for market analysis and trading operations.
    
    This class provides utility functions used across the trading system:
    - Cooldown management to prevent overtrading
    - Auto-close position checks for hard stop-loss/take-profit thresholds
    - AI thought logging for decision tracking
    - Data sanitization for JSON serialization
    - Confidence level calculations
    - Arbitrage statistics tracking
    """

    def __init__(
        self,
        account: PaperTradingAccount,
        intelligence_engine: IntelSliderEngine,
        strategy_config: Optional[PaperStrategyConfiguration] = None
    ) -> None:
        """
        Initialize Market Helpers.
        
        Args:
            account: Paper trading account
            intelligence_engine: Intelligence engine for decision making
            strategy_config: Optional strategy configuration
        """
        self.account = account
        self.intelligence_engine = intelligence_engine
        self.strategy_config = strategy_config
        
        # Trade cooldowns with separate timings for BUY vs SELL
        self.trade_cooldowns: Dict[str, Any] = {}  # token_symbol -> last_trade_time
        self.buy_cooldown_minutes = 5   # Moderate cooldown for entries
        self.sell_cooldown_minutes = 0  # No cooldown for exits - let positions close quickly
        
        logger.info(
            f"[MARKET HELPERS] Initialized with cooldown settings: "
            f"BUY={self.buy_cooldown_minutes}min, SELL={self.sell_cooldown_minutes}min"
        )

    # =========================================================================
    # TRADE COOLDOWN MANAGEMENT
    # =========================================================================

    def is_on_cooldown(self, token_symbol: str, trade_type: str = 'BUY') -> bool:
        """
        Check if token is on trade cooldown.
        
        Args:
            token_symbol: Token symbol to check
            trade_type: 'BUY' or 'SELL' (SELLs have shorter/no cooldown)
            
        Returns:
            True if on cooldown, False otherwise
        """
        if token_symbol not in self.trade_cooldowns:
            return False
        
        # Use different cooldowns for BUY vs SELL
        cooldown_minutes = (
            self.sell_cooldown_minutes if trade_type == 'SELL' 
            else self.buy_cooldown_minutes
        )
        
        if cooldown_minutes == 0:
            return False  # No cooldown
        
        last_trade_time = self.trade_cooldowns[token_symbol]
        cooldown_until = last_trade_time + timedelta(minutes=cooldown_minutes)
        
        return timezone.now() < cooldown_until

    def get_cooldown_remaining(self, token_symbol: str, trade_type: str = 'BUY') -> float:
        """
        Get remaining cooldown time in minutes.

        Args:
            token_symbol: Token symbol
            trade_type: 'BUY' or 'SELL' (SELLs have shorter/no cooldown)

        Returns:
            Remaining cooldown time in minutes
        """
        if token_symbol not in self.trade_cooldowns:
            return 0.0

        # Use different cooldowns for BUY vs SELL
        cooldown_minutes = (
            self.sell_cooldown_minutes if trade_type == 'SELL'
            else self.buy_cooldown_minutes
        )
        
        if cooldown_minutes == 0:
            return 0.0  # No cooldown

        last_trade_time = self.trade_cooldowns[token_symbol]
        cooldown_until = last_trade_time + timedelta(minutes=cooldown_minutes)
        remaining = cooldown_until - timezone.now()

        return max(0.0, remaining.total_seconds() / 60)

    def set_trade_cooldown(self, token_symbol: str) -> None:
        """
        Set trade cooldown for token.

        Args:
            token_symbol: Token symbol
        """
        self.trade_cooldowns[token_symbol] = timezone.now()
        logger.debug(
            f"[COOLDOWN] Set cooldown timestamp for {token_symbol}"
        )

    # =========================================================================
    # AUTO-CLOSE POSITIONS (STOP-LOSS / TAKE-PROFIT)
    # =========================================================================

    def check_auto_close_positions(
        self,
        price_manager: Any,
        position_manager: Any,
        trade_executor: Any
    ) -> None:
        """
        Check all open positions for stop-loss or take-profit triggers.

        This method runs on every tick to monitor position P&L and
        automatically close positions that hit configured thresholds.

        This is the SAFETY NET - hard thresholds that override intelligent decisions.
        The intelligent sell check runs first and makes smarter decisions based on
        market conditions.

        Args:
            price_manager: RealPriceManager instance
            position_manager: PositionManager instance
            trade_executor: TradeExecutor instance
        """
        try:
            positions = position_manager.get_all_positions()

            for token_symbol, position in positions.items():
                # Get current price
                token_data = price_manager.get_token_price(token_symbol)
                if not token_data:
                    continue

                # Handle both dict and Decimal return types
                if isinstance(token_data, dict):
                    current_price = token_data.get('price')
                else:
                    # token_data is already a Decimal
                    current_price = token_data

                if not current_price:
                    continue

                # Calculate P&L percentage
                entry_price = position.average_entry_price_usd
                pnl_percent = ((current_price - entry_price) / entry_price) * Decimal('100')

                # Get configured thresholds
                if self.strategy_config:
                    stop_loss = self.strategy_config.stop_loss_percent
                    take_profit = self.strategy_config.take_profit_percent
                else:
                    # Use defaults if no config
                    stop_loss = Decimal('5.0')
                    take_profit = Decimal('15.0')

                # Check stop-loss
                if pnl_percent <= -stop_loss:
                    logger.warning(
                        f"[AUTO-CLOSE] Stop-loss triggered for {token_symbol}: "
                        f"{pnl_percent:.2f}% (threshold: -{stop_loss}%)"
                    )

                    token_address = getattr(position, 'token_address', '')

                    # Log the auto-close decision
                    self.log_thought(
                        action='SELL',
                        reasoning=f"Stop-loss triggered at {pnl_percent:.2f}% loss",
                        confidence=100.0,  # Hard threshold = 100% confidence
                        decision_type="STOP_LOSS",
                        metadata={
                            'token': token_symbol,
                            'current_price': float(current_price),
                            'entry_price': float(entry_price),
                            'pnl_percent': float(pnl_percent),
                            'stop_loss_threshold': float(stop_loss)
                        }
                    )

                    # Create a simple SELL decision for executor
                    sell_decision = TradingDecision(
                        action='SELL',
                        token_address=token_address or '',
                        token_symbol=token_symbol,
                        position_size_percent=Decimal('0'),
                        position_size_usd=Decimal('0'),
                        stop_loss_percent=Decimal('0'),
                        take_profit_targets=[],
                        execution_mode='FAST_LANE',
                        use_private_relay=False,
                        gas_strategy='standard',
                        max_gas_price_gwei=Decimal('50'),
                        overall_confidence=Decimal('100'),
                        risk_score=Decimal('0'),
                        opportunity_score=Decimal('0'),
                        primary_reasoning=f"Stop-loss triggered at {pnl_percent:.2f}% loss",
                        risk_factors=[f"Stop-loss triggered at {pnl_percent:.2f}%"],
                        opportunity_factors=[],
                        mitigation_strategies=[],
                        intel_level_used=self.intelligence_engine.intel_level,
                        intel_adjustments={},
                        time_sensitivity='critical',
                        max_execution_time_ms=5000
                    )

                    trade_executor.execute_trade(
                        decision=sell_decision,
                        token_symbol=token_symbol,
                        current_price=current_price,
                        position_manager=position_manager
                    )

                # Check take-profit
                elif pnl_percent >= take_profit:
                    logger.info(
                        f"[AUTO-CLOSE] Take-profit triggered for {token_symbol}: "
                        f"{pnl_percent:.2f}% (threshold: +{take_profit}%)"
                    )

                    token_address = getattr(position, 'token_address', '')

                    # Log the auto-close decision
                    self.log_thought(
                        action='SELL',
                        reasoning=f"Take-profit triggered at {pnl_percent:.2f}% gain",
                        confidence=100.0,  # Hard threshold = 100% confidence
                        decision_type="TAKE_PROFIT",
                        metadata={
                            'token': token_symbol,
                            'current_price': float(current_price),
                            'entry_price': float(entry_price),
                            'pnl_percent': float(pnl_percent),
                            'take_profit_threshold': float(take_profit)
                        }
                    )

                    # Create a simple SELL decision for executor
                    sell_decision = TradingDecision(
                        action='SELL',
                        token_address=token_address or '',
                        token_symbol=token_symbol,
                        position_size_percent=Decimal('0'),
                        position_size_usd=Decimal('0'),
                        stop_loss_percent=None,  # No stop-loss for exit trade
                        take_profit_targets=[],
                        execution_mode='FAST_LANE',
                        use_private_relay=False,
                        gas_strategy='standard',
                        max_gas_price_gwei=Decimal('50'),
                        overall_confidence=Decimal('100'),
                        risk_score=Decimal('0'),
                        opportunity_score=Decimal('0'),
                        primary_reasoning=f"Take-profit triggered at {pnl_percent:.2f}% gain",
                        risk_factors=[],
                        opportunity_factors=[f"Take-profit target reached: {pnl_percent:.2f}%"],
                        mitigation_strategies=[],
                        intel_level_used=self.intelligence_engine.intel_level,
                        intel_adjustments={},
                        time_sensitivity='high',
                        max_execution_time_ms=10000
                    )

                    trade_executor.execute_trade(
                        decision=sell_decision,
                        token_symbol=token_symbol,
                        current_price=current_price,
                        position_manager=position_manager
                    )

        except Exception as e:
            logger.error(
                f"[MARKET HELPERS] Failed to check auto-close positions: {e}",
                exc_info=True
            )

    # =========================================================================
    # AI THOUGHT LOGGING
    # =========================================================================
    
    def sanitize_for_json(self, data: Any) -> Any:
        """
        Sanitize data for JSON serialization by converting NaN/Inf to None.
        
        Args:
            data: Data to sanitize (can be dict, list, or scalar)
            
        Returns:
            Sanitized data safe for JSON serialization
        """
        if isinstance(data, dict):
            return {k: self.sanitize_for_json(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.sanitize_for_json(item) for item in data]
        elif isinstance(data, float):
            if math.isnan(data) or math.isinf(data):
                return None
            return data
        elif isinstance(data, Decimal):
            if data.is_nan() or data.is_infinite():
                return None
            return float(data)
        else:
            return data

    def log_thought(
        self,
        action: str,
        reasoning: str,
        confidence: float,
        decision_type: str = "TRADE_DECISION",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log an AI trading thought/decision.

        Args:
            action: Action taken (BUY, SELL, HOLD)
            reasoning: Primary reasoning for the decision
            confidence: Confidence level (0-100)
            decision_type: Type of decision
            metadata: Additional metadata
        """
        try:
            metadata = metadata or {}
            token_symbol = metadata.get('token', 'UNKNOWN')
            token_address = metadata.get('token_address', '')

            # Calculate confidence level
            confidence_level = self.calculate_confidence_level(confidence)

            # Create thought log
            PaperAIThoughtLog.objects.create(
                account=self.account,
                decision_type=action,
                token_address=token_address,
                token_symbol=token_symbol,
                confidence_level=confidence_level,
                confidence_percent=Decimal(str(confidence)),
                risk_score=Decimal(str(metadata.get('risk_score', 0))),
                opportunity_score=Decimal(str(metadata.get('opportunity_score', 0))),
                primary_reasoning=reasoning,
                key_factors=[decision_type],
                positive_signals=metadata.get('positive_signals', []),
                negative_signals=metadata.get('negative_signals', []),
                market_data=self.sanitize_for_json(metadata),
                strategy_name=f"Intel Level {metadata.get('intel_level', 'Unknown')}",
                lane_used='SMART' if metadata.get('data_quality') == 'GOOD' else 'FAST',
                analysis_time_ms=0
            )

            logger.debug(
                f"[THOUGHT LOG] Logged {action} decision for {token_symbol}: "
                f"{confidence:.1f}% confidence"
            )

        except Exception as e:
            logger.error(
                f"[THOUGHT LOG] Failed to log thought: {e}",
                exc_info=True
            )

    def calculate_confidence_level(self, confidence_percent: float) -> str:
        """
        Calculate confidence level category from percentage.
        
        Args:
            confidence_percent: Confidence percentage (0-100)
            
        Returns:
            Confidence level string (VERY_HIGH, HIGH, MEDIUM, LOW, VERY_LOW)
        """
        if confidence_percent >= 90:
            return 'VERY_HIGH'
        elif confidence_percent >= 70:
            return 'HIGH'
        elif confidence_percent >= 50:
            return 'MEDIUM'
        elif confidence_percent >= 30:
            return 'LOW'
        else:
            return 'VERY_LOW'

    # =========================================================================
    # ARBITRAGE MANAGEMENT
    # =========================================================================

    def update_gas_price(
        self,
        gas_price_gwei: Decimal,
        arbitrage_detector: Optional[Any]
    ) -> None:
        """
        Update gas price for arbitrage calculations.

        This should be called periodically to keep arbitrage profit
        calculations accurate with current network conditions.

        Args:
            gas_price_gwei: Current gas price in gwei
            arbitrage_detector: Arbitrage detector instance
        """
        if arbitrage_detector:
            arbitrage_detector.update_gas_price(gas_price_gwei)
            logger.debug(f"[ARBITRAGE] Updated gas price to {gas_price_gwei} gwei")

    def get_arbitrage_stats(
        self,
        check_arbitrage: bool,
        arbitrage_opportunities_found: int,
        arbitrage_trades_executed: int,
        arbitrage_detector: Optional[Any],
        dex_comparator: Optional[Any]
    ) -> Dict[str, Any]:
        """
        Get arbitrage detection statistics.

        Args:
            check_arbitrage: Whether arbitrage detection is enabled
            arbitrage_opportunities_found: Number of opportunities found
            arbitrage_trades_executed: Number of trades executed
            arbitrage_detector: Arbitrage detector instance
            dex_comparator: DEX comparator instance

        Returns:
            Dictionary with arbitrage performance metrics
        """
        stats = {
            'enabled': check_arbitrage,
            'opportunities_found': arbitrage_opportunities_found,
            'trades_executed': arbitrage_trades_executed,
            'success_rate': 0.0
        }

        if arbitrage_opportunities_found > 0:
            stats['success_rate'] = (
                (arbitrage_trades_executed / arbitrage_opportunities_found) * 100
            )

        if arbitrage_detector:
            stats['detector_stats'] = arbitrage_detector.get_performance_stats()

        if dex_comparator:
            stats['comparator_stats'] = dex_comparator.get_performance_stats()

        return stats