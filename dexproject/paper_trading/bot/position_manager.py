"""
Position Manager for Paper Trading Bot

This module handles all position management operations for the paper trading bot,
including opening, closing, updating, and tracking positions and their P&L.

Responsibilities:
- Load positions from database
- Update position prices on market ticks
- Auto-close positions (stop-loss, take-profit, max hold time)
- Open new positions
- Close/reduce existing positions
- Calculate and update account P&L

File: dexproject/paper_trading/bot/position_manager.py
"""

import logging
from decimal import Decimal
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timedelta

from django.utils import timezone
from django.db import transaction

from paper_trading.models import (
    PaperTradingAccount,
    PaperPosition,
    PaperStrategyConfiguration
)

# Import intelligence types for type hints
from paper_trading.intelligence.base import TradingDecision

logger = logging.getLogger(__name__)


# =============================================================================
# POSITION MANAGER CLASS
# =============================================================================

class PositionManager:
    """
    Manages all position operations for paper trading bot.
    
    This class handles the complete lifecycle of positions:
    - Loading from database
    - Price updates
    - Auto-close triggers (stop-loss, take-profit)
    - Opening new positions
    - Closing/reducing positions
    - P&L calculations
    
    Example usage:
        manager = PositionManager(account, strategy_config)
        manager.load_positions()
        
        # Update prices on each tick
        manager.update_position_prices(token_list)
        
        # Check for auto-closes
        manager.check_auto_close_positions(token_list)
        
        # Open new position
        manager.open_or_add_position(token_symbol, decision, current_price)
    """
    
    def __init__(
        self,
        account: PaperTradingAccount,
        strategy_config: Optional[PaperStrategyConfiguration] = None
    ):
        """
        Initialize the Position Manager.
        
        Args:
            account: Paper trading account
            strategy_config: Strategy configuration (for stop-loss/take-profit)
        """
        self.account = account
        self.strategy_config = strategy_config
        self.positions: Dict[str, PaperPosition] = {}
        
        logger.info(
            f"[POSITION MANAGER] Initialized for account: {account.account_id}"
        )
    
    # =========================================================================
    # POSITION LOADING
    # =========================================================================
    
    def load_positions(self) -> int:
        """
        Load existing open positions from database.
        
        Returns:
            Number of positions loaded
        """
        try:
            positions = PaperPosition.objects.filter(
                account=self.account,
                is_open=True
            )
            
            for position in positions:
                self.positions[position.token_symbol] = position
            
            logger.info(
                f"[POSITION MANAGER] Loaded {len(self.positions)} open positions"
            )
            return len(self.positions)
            
        except Exception as e:
            logger.error(f"[POSITION MANAGER] Failed to load positions: {e}")
            return 0
    
    # =========================================================================
    # PRICE UPDATES
    # =========================================================================
    
    def update_position_prices(self, token_list: List[Dict[str, Any]]) -> int:
        """
        Update all open position prices with current market prices.
        
        This method should be called on every tick to keep position
        values current in the database for dashboard display.
        
        Args:
            token_list: List of tokens with current prices
        
        Returns:
            Number of positions updated
        """
        try:
            if not self.positions:
                return 0
            
            updated_count = 0
            
            for token_symbol, position in self.positions.items():
                # Get current price from token list
                current_token = next(
                    (t for t in token_list if t['symbol'] == token_symbol),
                    None
                )
                
                if not current_token:
                    continue
                
                # Update position with current price
                old_price = position.current_price_usd
                new_price = current_token['price']
                
                position.current_price_usd = new_price
                position.current_value_usd = position.quantity * new_price
                position.unrealized_pnl_usd = (
                    position.current_value_usd - position.total_invested_usd
                )
                position.last_updated = timezone.now()
                
                position.save(update_fields=[
                    'current_price_usd',
                    'current_value_usd',
                    'unrealized_pnl_usd',
                    'last_updated'
                ])
                
                updated_count += 1
                
                # Log significant price changes
                if old_price and old_price > 0:
                    price_change_pct = ((new_price - old_price) / old_price) * 100
                    if abs(price_change_pct) > 1:  # Log if >1% change
                        logger.debug(
                            f"[PRICE UPDATE] {token_symbol}: "
                            f"${old_price:.2f} → ${new_price:.2f} "
                            f"({price_change_pct:+.2f}%), "
                            f"Position value: ${position.current_value_usd:.2f}, "
                            f"P&L: ${position.unrealized_pnl_usd:+.2f}"
                        )
            
            if updated_count > 0:
                logger.debug(
                    f"[POSITION MANAGER] Updated prices for {updated_count} positions"
                )
                
                # Update account's total P&L after price updates
                self.update_account_pnl()
            
            return updated_count
            
        except Exception as e:
            logger.error(
                f"[POSITION MANAGER] Failed to update position prices: {e}",
                exc_info=True
            )
            return 0
    
    # =========================================================================
    # AUTO-CLOSE LOGIC
    # =========================================================================
    
    def check_auto_close_positions(
        self,
        token_list: List[Dict[str, Any]]
    ) -> List[Tuple[str, str, float]]:
        """
        Check all open positions for auto-close conditions.
        
        Automatically closes positions that have:
        - Hit stop-loss threshold (e.g., -5% loss)
        - Hit take-profit threshold (e.g., +10% gain)
        - Exceeded maximum hold time
        
        This ensures risk management rules are enforced even
        when circuit breakers are active.
        
        Args:
            token_list: List of tokens with current prices
        
        Returns:
            List of tuples: (token_symbol, reason, pnl_percent)
        """
        try:
            if not self.positions:
                return []
            
            positions_to_close = []
            
            for token_symbol, position in self.positions.items():
                # Calculate current P&L percentage
                if position.total_invested_usd > 0:
                    pnl_percent = (
                        (position.current_value_usd - position.total_invested_usd)
                        / position.total_invested_usd
                        * 100
                    )
                else:
                    continue
                
                # Get stop-loss and take-profit thresholds from strategy config
                stop_loss_threshold = -5.0  # Default -5%
                take_profit_threshold = 10.0  # Default +10%
                
                if self.strategy_config:
                    stop_loss_threshold = -float(
                        getattr(self.strategy_config, 'stop_loss_percent', 5)
                    )
                    take_profit_threshold = float(
                        getattr(self.strategy_config, 'take_profit_percent', 10)
                    )
                
                # Check stop-loss condition
                if pnl_percent <= stop_loss_threshold:
                    logger.warning(
                        f"[AUTO-CLOSE] Stop-loss triggered for {token_symbol}: "
                        f"P&L={pnl_percent:.2f}% "
                        f"(threshold={stop_loss_threshold:.2f}%)"
                    )
                    positions_to_close.append(
                        (token_symbol, 'STOP_LOSS', pnl_percent)
                    )
                    
                # Check take-profit condition
                elif pnl_percent >= take_profit_threshold:
                    logger.info(
                        f"[AUTO-CLOSE] Take-profit triggered for {token_symbol}: "
                        f"P&L={pnl_percent:.2f}% "
                        f"(threshold={take_profit_threshold:.2f}%)"
                    )
                    positions_to_close.append(
                        (token_symbol, 'TAKE_PROFIT', pnl_percent)
                    )
                
                # Check maximum hold time (24 hours default)
                if position.opened_at:
                    hold_duration = timezone.now() - position.opened_at
                    max_hold_hours = 24  # Default 24 hours
                    
                    if hold_duration.total_seconds() > (max_hold_hours * 3600):
                        logger.info(
                            f"[AUTO-CLOSE] Max hold time exceeded for {token_symbol}: "
                            f"Held for {hold_duration.total_seconds()/3600:.1f} hours"
                        )
                        positions_to_close.append(
                            (token_symbol, 'MAX_HOLD_TIME', pnl_percent)
                        )
            
            if positions_to_close:
                logger.info(
                    f"[AUTO-CLOSE] Found {len(positions_to_close)} positions "
                    f"to auto-close"
                )
            
            return positions_to_close
            
        except Exception as e:
            logger.error(
                f"[POSITION MANAGER] Failed to check auto-close positions: {e}",
                exc_info=True
            )
            return []
    
    # =========================================================================
    # POSITION OPENING/CLOSING
    # =========================================================================
    
    def open_or_add_position(
        self,
        token_symbol: str,
        token_address: str,
        position_size_usd: Decimal,
        current_price: Decimal
    ) -> Optional[PaperPosition]:
        """
        Open a new position or add to an existing position.
        
        Args:
            token_symbol: Token symbol (e.g., 'WETH')
            token_address: Token contract address
            position_size_usd: Amount to invest in USD
            current_price: Current token price in USD
        
        Returns:
            Updated or created PaperPosition, or None if failed
        """
        try:
            # Calculate quantity to buy
            quantity = position_size_usd / current_price
            
            if token_symbol in self.positions:
                # Add to existing position
                position = self.positions[token_symbol]
                
                position.quantity += quantity
                position.total_invested_usd += position_size_usd
                position.average_entry_price_usd = (
                    position.total_invested_usd / position.quantity
                )
                position.current_price_usd = current_price
                position.current_value_usd = position.quantity * current_price
                position.unrealized_pnl_usd = (
                    position.current_value_usd - position.total_invested_usd
                )
                position.last_updated = timezone.now()
                
                position.save()
                
                logger.info(
                    f"[POSITION] Added to {token_symbol}: "
                    f"+{quantity:.4f} tokens (${position_size_usd:.2f}), "
                    f"Total: {position.quantity:.4f} tokens "
                    f"(${position.total_invested_usd:.2f})"
                )
            else:
                # Create new position
                position = PaperPosition.objects.create(
                    account=self.account,
                    token_address=token_address,
                    token_symbol=token_symbol,
                    quantity=quantity,
                    average_entry_price_usd=current_price,
                    current_price_usd=current_price,
                    total_invested_usd=position_size_usd,
                    current_value_usd=position_size_usd,
                    unrealized_pnl_usd=Decimal('0'),
                    is_open=True
                )
                
                self.positions[token_symbol] = position
                
                logger.info(
                    f"[POSITION] Opened new {token_symbol} position: "
                    f"{quantity:.4f} tokens @ ${current_price:.2f} "
                    f"(${position_size_usd:.2f})"
                )
            
            # Update account P&L
            self.update_account_pnl()
            
            return position
            
        except Exception as e:
            logger.error(
                f"[POSITION MANAGER] Failed to open/add position for {token_symbol}: {e}",
                exc_info=True
            )
            return None
    
    def close_or_reduce_position(
        self,
        token_symbol: str,
        sell_amount_usd: Decimal,
        current_price: Decimal
    ) -> Optional[PaperPosition]:
        """
        Close or reduce an existing position.
        
        Args:
            token_symbol: Token symbol to sell
            sell_amount_usd: USD amount to sell
            current_price: Current token price in USD
        
        Returns:
            Updated PaperPosition, or None if failed/not found
        """
        try:
            if token_symbol not in self.positions:
                logger.warning(
                    f"[POSITION MANAGER] Position {token_symbol} not found"
                )
                return None
            
            position = self.positions[token_symbol]
            
            # Calculate quantity to sell
            sell_quantity = min(
                position.quantity,
                sell_amount_usd / current_price
            )
            
            # Calculate realized P&L from this sale
            sale_value = sell_quantity * current_price
            cost_basis = sell_quantity * position.average_entry_price_usd
            realized_pnl = sale_value - cost_basis
            
            # Update position
            position.quantity -= sell_quantity
            position.realized_pnl_usd += realized_pnl
            position.current_value_usd = position.quantity * current_price
            position.unrealized_pnl_usd = (
                position.current_value_usd - 
                (position.quantity * position.average_entry_price_usd)
            )
            position.last_updated = timezone.now()
            
            # Check if position should be closed
            if position.quantity <= Decimal('0.0001'):  # Essentially zero
                position.is_open = False
                position.closed_at = timezone.now()
                position.quantity = Decimal('0')
                position.current_value_usd = Decimal('0')
                position.unrealized_pnl_usd = Decimal('0')
                
                del self.positions[token_symbol]
                
                logger.info(
                    f"[POSITION] Closed {token_symbol} position: "
                    f"Realized P&L: ${realized_pnl:+.2f}"
                )
            else:
                logger.info(
                    f"[POSITION] Reduced {token_symbol} position: "
                    f"Sold {sell_quantity:.4f} tokens (${sale_value:.2f}), "
                    f"Remaining: {position.quantity:.4f} tokens, "
                    f"Realized P&L: ${realized_pnl:+.2f}"
                )
            
            position.save()
            
            # Update account P&L
            self.update_account_pnl()
            
            return position
            
        except Exception as e:
            logger.error(
                f"[POSITION MANAGER] Failed to close/reduce position for "
                f"{token_symbol}: {e}",
                exc_info=True
            )
            return None
    
    # =========================================================================
    # P&L CALCULATION
    # =========================================================================
    
    def update_account_pnl(self):
        """
        Update account's total P&L from all positions.
        
        This should be called after any position update to keep
        the account's total_pnl_usd in sync with position data.
        """
        try:
            # Calculate total unrealized P&L from all open positions
            total_unrealized_pnl = sum(
                pos.unrealized_pnl_usd
                for pos in self.positions.values()
            )
            
            # Calculate total realized P&L from closed positions
            closed_positions = PaperPosition.objects.filter(
                account=self.account,
                is_open=False
            )
            total_realized_pnl = sum(
                pos.realized_pnl_usd
                for pos in closed_positions
            )
            
            # Update account's total P&L
            self.account.total_pnl_usd = total_unrealized_pnl + total_realized_pnl
            self.account.save(update_fields=['total_pnl_usd'])
            
            logger.debug(
                f"[ACCOUNT P&L] Updated: "
                f"Unrealized=${total_unrealized_pnl:.2f}, "
                f"Realized=${total_realized_pnl:.2f}, "
                f"Total=${self.account.total_pnl_usd:.2f}"
            )
            
        except Exception as e:
            logger.error(
                f"[POSITION MANAGER] Failed to update account P&L: {e}",
                exc_info=True
            )
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def get_position(self, token_symbol: str) -> Optional[PaperPosition]:
        """
        Get a specific position by token symbol.
        
        Args:
            token_symbol: Token symbol to look up
        
        Returns:
            PaperPosition or None if not found
        """
        return self.positions.get(token_symbol)
    
    def get_all_positions(self) -> Dict[str, PaperPosition]:
        """
        Get all open positions.
        
        Returns:
            Dictionary mapping token symbols to positions
        """
        return self.positions.copy()
    
    def get_position_count(self) -> int:
        """
        Get the number of open positions.
        
        Returns:
            Count of open positions
        """
        return len(self.positions)
    
    def get_total_invested(self) -> Decimal:
        """
        Get total amount invested across all positions.
        
        Returns:
            Total invested USD
        """
        return sum(
            pos.total_invested_usd
            for pos in self.positions.values()
        )
    
    def get_total_value(self) -> Decimal:
        """
        Get total current value of all positions.
        
        Returns:
            Total current value in USD
        """
        return sum(
            pos.current_value_usd
            for pos in self.positions.values()
        )
    
    def get_total_unrealized_pnl(self) -> Decimal:
        """
        Get total unrealized P&L across all positions.
        
        Returns:
            Total unrealized P&L in USD
        """
        return sum(
            pos.unrealized_pnl_usd
            for pos in self.positions.values()
        )
    
    def has_position(self, token_symbol: str) -> bool:
        """
        Check if a position exists for a token.
        
        Args:
            token_symbol: Token symbol to check
        
        Returns:
            True if position exists
        """
        return token_symbol in self.positions