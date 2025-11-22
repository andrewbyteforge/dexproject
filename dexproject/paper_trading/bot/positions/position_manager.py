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

File: dexproject/paper_trading/bot/positions/position_manager.py
"""

import logging
from decimal import Decimal
from typing import Dict, List, Tuple, Optional, Any

from django.utils import timezone

from paper_trading.models import (
    PaperTradingAccount,
    PaperPosition,
    PaperStrategyConfiguration
)

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
            logger.error(
                f"[POSITION MANAGER] Failed to load positions: {e}",
                exc_info=True
            )
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

                # ✅ VALIDATE: Skip if price is invalid
                if not new_price or new_price <= 0:
                    logger.warning(
                        f"[PRICE UPDATE] Invalid price for {token_symbol}: {new_price}"
                    )
                    continue

                # ✅ VALIDATE: Convert to Decimal safely
                try:
                    new_price = Decimal(str(new_price))
                except (ValueError, TypeError, ArithmeticError):
                    logger.warning(
                        f"[PRICE UPDATE] Cannot convert price to Decimal for {token_symbol}: {new_price}"
                    )
                    continue

                # Calculate new values
                position.current_price_usd = new_price
                new_value = position.quantity * new_price
                new_pnl = new_value - position.total_invested_usd

                # ✅ CRITICAL: Normalize tiny values to zero (prevents scientific notation)
                # If P&L is smaller than 0.01 cents, it's a rounding error - set to zero
                if abs(new_pnl) < Decimal('0.0001'):
                    new_pnl = Decimal('0')

                # ✅ VALIDATE: Check for NaN/Infinity before saving
                if not (new_value.is_finite() and new_pnl.is_finite()):
                    logger.error(
                        f"[PRICE UPDATE] Invalid calculated values for {token_symbol}: "
                        f"value={new_value}, pnl={new_pnl}"
                    )
                    continue

                position.current_value_usd = new_value
                position.unrealized_pnl_usd = new_pnl
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

                # Check maximum hold time (configurable via strategy config)
                if position.opened_at:
                    hold_duration = timezone.now() - position.opened_at
                    
                    # Get max hold hours from strategy config, default to 72 hours
                    max_hold_hours = 72  # Default 72 hours (3 days)
                    if self.strategy_config:
                        max_hold_hours = int(
                            getattr(self.strategy_config, 'max_hold_hours', 72)
                        )

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

        This method handles both creating new positions and adding to existing ones,
        with full validation and normalization to prevent database corruption.

        Args:
            token_symbol: Token symbol (e.g., 'WETH')
            token_address: Token contract address
            position_size_usd: Amount to invest in USD
            current_price: Current token price in USD

        Returns:
            Updated or created PaperPosition, or None if failed
        """
        try:
            logger.info(
                f"[POSITION MANAGER] Opening/adding position: {token_symbol}, "
                f"Size=${position_size_usd:.2f}, Price=${current_price:.8f}"
            )

            # =================================================================
            # INPUT VALIDATION
            # =================================================================
            
            # Validate position size
            if position_size_usd <= 0:
                logger.error(
                    f"[POSITION MANAGER] Invalid position size: ${position_size_usd:.2f}"
                )
                return None

            # Validate current price
            if current_price <= 0:
                logger.error(
                    f"[POSITION MANAGER] Invalid price for {token_symbol}: ${current_price:.8f}"
                )
                return None

            # Validate token address
            if not token_address or token_address == '0x0000000000000000000000000000000000000000':
                logger.error(
                    f"[POSITION MANAGER] Invalid token address for {token_symbol}: {token_address}"
                )
                return None

            # Check for NaN or Infinity in inputs
            if not (position_size_usd.is_finite() and current_price.is_finite()):
                logger.error(
                    f"[POSITION MANAGER] Non-finite values detected: "
                    f"size={position_size_usd}, price={current_price}"
                )
                return None

            # =================================================================
            # CALCULATE QUANTITY
            # =================================================================
            
            try:
                quantity = position_size_usd / current_price
                
                # Validate calculated quantity
                if not quantity.is_finite() or quantity <= 0:
                    logger.error(
                        f"[POSITION MANAGER] Invalid calculated quantity: {quantity}"
                    )
                    return None
                    
                logger.debug(
                    f"[POSITION MANAGER] Calculated quantity: {quantity:.18f} tokens"
                )
                
            except (ArithmeticError, ZeroDivisionError) as e:
                logger.error(
                    f"[POSITION MANAGER] Failed to calculate quantity: {e}"
                )
                return None

            # =================================================================
            # FIND OR CREATE POSITION
            # =================================================================
            
            # Check if position exists in memory
            if token_symbol in self.positions:
                position = self.positions[token_symbol]
                logger.debug(
                    f"[POSITION MANAGER] Found {token_symbol} in memory"
                )
            else:
                # Check if position exists in database but not loaded
                try:
                    position = PaperPosition.objects.get(
                        account=self.account,
                        token_address=token_address,
                        is_open=True
                    )
                    # Load it into memory
                    self.positions[token_symbol] = position
                    logger.info(
                        f"[POSITION MANAGER] Loaded existing {token_symbol} position "
                        f"from database (ID: {position.position_id})"
                    )
                except PaperPosition.DoesNotExist:
                    position = None
                    logger.debug(
                        f"[POSITION MANAGER] No existing position found for {token_symbol}"
                    )

            # =================================================================
            # UPDATE EXISTING OR CREATE NEW POSITION
            # =================================================================
            
            if position:
                # =============================================================
                # ADD TO EXISTING POSITION
                # =============================================================
                
                logger.info(
                    f"[POSITION MANAGER] Adding to existing {token_symbol} position"
                )
                
                # Store old values for logging
                old_quantity = position.quantity
                old_invested = position.total_invested_usd
                
                # Update quantities
                position.quantity += quantity
                position.total_invested_usd += position_size_usd
                
                # Recalculate average entry price
                try:
                    position.average_entry_price_usd = (
                        position.total_invested_usd / position.quantity
                    )
                except (ArithmeticError, ZeroDivisionError):
                    logger.error(
                        f"[POSITION MANAGER] Failed to calculate average entry price"
                    )
                    return None
                
                # Update current values
                position.current_price_usd = current_price
                position.current_value_usd = position.quantity * current_price
                
                # Calculate unrealized P&L
                pnl = position.current_value_usd - position.total_invested_usd
                
                # ✅ CRITICAL: Normalize tiny P&L values to prevent scientific notation
                if abs(pnl) < Decimal('0.0001'):
                    logger.debug(
                        f"[POSITION MANAGER] Normalizing tiny P&L: {pnl} → 0"
                    )
                    pnl = Decimal('0')
                
                # Validate P&L is finite
                if not pnl.is_finite():
                    logger.error(
                        f"[POSITION MANAGER] Non-finite P&L calculated: {pnl}"
                    )
                    return None
                
                position.unrealized_pnl_usd = pnl
                position.last_updated = timezone.now()

                # Save to database
                try:
                    position.save()
                    logger.info(
                        f"[POSITION] ✅ Added to {token_symbol}: "
                        f"+{quantity:.8f} tokens (${position_size_usd:.2f}), "
                        f"Total: {old_quantity:.8f} → {position.quantity:.8f} tokens, "
                        f"Invested: ${old_invested:.2f} → ${position.total_invested_usd:.2f}, "
                        f"Avg Price: ${position.average_entry_price_usd:.8f}, "
                        f"P&L: ${pnl:+.2f}"
                    )
                except Exception as e:
                    logger.error(
                        f"[POSITION MANAGER] Failed to save updated position: {e}",
                        exc_info=True
                    )
                    return None
                    
            else:
                # =============================================================
                # CREATE NEW POSITION
                # =============================================================
                
                logger.info(
                    f"[POSITION MANAGER] Creating new {token_symbol} position"
                )
                
                # Calculate initial values
                current_value_usd = position_size_usd
                
                # ✅ Set initial P&L to exactly zero (no rounding errors)
                unrealized_pnl_usd = Decimal('0')
                
                try:
                    position = PaperPosition.objects.create(
                        account=self.account,
                        token_address=token_address,
                        token_symbol=token_symbol,
                        quantity=quantity,
                        average_entry_price_usd=current_price,
                        current_price_usd=current_price,
                        total_invested_usd=position_size_usd,
                        current_value_usd=current_value_usd,
                        unrealized_pnl_usd=unrealized_pnl_usd,
                        realized_pnl_usd=Decimal('0'),
                        is_open=True,
                        opened_at=timezone.now()
                    )

                    # Add to memory
                    self.positions[token_symbol] = position

                    logger.info(
                        f"[POSITION] ✅ Opened new {token_symbol} position: "
                        f"{quantity:.8f} tokens @ ${current_price:.8f}, "
                        f"Value=${position_size_usd:.2f}, "
                        f"ID={position.position_id}"
                    )
                    
                except Exception as e:
                    logger.error(
                        f"[POSITION MANAGER] Failed to create new position: {e}",
                        exc_info=True
                    )
                    return None

            # =================================================================
            # UPDATE ACCOUNT P&L
            # =================================================================
            
            try:
                self.update_account_pnl()
            except Exception as e:
                logger.error(
                    f"[POSITION MANAGER] Failed to update account P&L: {e}",
                    exc_info=True
                )
                # Don't return None here - position was created/updated successfully

            return position

        except Exception as e:
            logger.error(
                f"[POSITION MANAGER] Unexpected error in open_or_add_position "
                f"for {token_symbol}: {e}",
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

        Handles partial sells and full position closes with proper P&L calculation
        and database cleanup. Normalizes all values to prevent scientific notation.

        Args:
            token_symbol: Token symbol to sell
            sell_amount_usd: USD amount to sell
            current_price: Current token price in USD

        Returns:
            Updated PaperPosition, or None if failed/not found
        """
        try:
            logger.info(
                f"[POSITION MANAGER] Closing/reducing position: {token_symbol}, "
                f"Sell=${sell_amount_usd:.2f}, Price=${current_price:.8f}"
            )

            # =================================================================
            # INPUT VALIDATION
            # =================================================================
            
            # Check if position exists
            if token_symbol not in self.positions:
                logger.warning(
                    f"[POSITION MANAGER] Position {token_symbol} not found in memory"
                )
                return None

            # Validate sell amount
            if sell_amount_usd <= 0:
                logger.error(
                    f"[POSITION MANAGER] Invalid sell amount: ${sell_amount_usd:.2f}"
                )
                return None

            # Validate current price
            if current_price <= 0:
                logger.error(
                    f"[POSITION MANAGER] Invalid price for {token_symbol}: ${current_price:.8f}"
                )
                return None

            # Check for NaN or Infinity
            if not (sell_amount_usd.is_finite() and current_price.is_finite()):
                logger.error(
                    f"[POSITION MANAGER] Non-finite values detected: "
                    f"amount={sell_amount_usd}, price={current_price}"
                )
                return None

            # =================================================================
            # CALCULATE SELL QUANTITY
            # =================================================================
            
            position = self.positions[token_symbol]
            
            logger.debug(
                f"[POSITION MANAGER] Current position: "
                f"{position.quantity:.8f} tokens, "
                f"Entry=${position.average_entry_price_usd:.8f}, "
                f"Invested=${position.total_invested_usd:.2f}"
            )

            # Calculate quantity to sell (don't sell more than we have)
            try:
                requested_quantity = sell_amount_usd / current_price
                sell_quantity = min(position.quantity, requested_quantity)
                
                if sell_quantity <= 0:
                    logger.error(
                        f"[POSITION MANAGER] Invalid sell quantity: {sell_quantity}"
                    )
                    return None
                    
                logger.debug(
                    f"[POSITION MANAGER] Selling {sell_quantity:.8f} tokens "
                    f"(requested: {requested_quantity:.8f})"
                )
                
            except (ArithmeticError, ZeroDivisionError) as e:
                logger.error(
                    f"[POSITION MANAGER] Failed to calculate sell quantity: {e}"
                )
                return None

            # =================================================================
            # CALCULATE P&L
            # =================================================================
            
            try:
                # Calculate sale proceeds
                sale_value = sell_quantity * current_price
                
                # Calculate cost basis
                cost_basis = sell_quantity * position.average_entry_price_usd
                
                # Calculate realized P&L from this sale
                realized_pnl = sale_value - cost_basis
                
                # ✅ Normalize tiny realized P&L to zero
                if abs(realized_pnl) < Decimal('0.0001'):
                    logger.debug(
                        f"[POSITION MANAGER] Normalizing tiny realized P&L: {realized_pnl} → 0"
                    )
                    realized_pnl = Decimal('0')
                
                # Validate P&L is finite
                if not realized_pnl.is_finite():
                    logger.error(
                        f"[POSITION MANAGER] Non-finite realized P&L: {realized_pnl}"
                    )
                    return None
                
                logger.debug(
                    f"[POSITION MANAGER] P&L calculation: "
                    f"Sale=${sale_value:.2f}, Cost=${cost_basis:.2f}, "
                    f"Realized P&L=${realized_pnl:+.2f}"
                )
                
            except (ArithmeticError, ZeroDivisionError) as e:
                logger.error(
                    f"[POSITION MANAGER] Failed to calculate P&L: {e}"
                )
                return None

            # =================================================================
            # UPDATE POSITION
            # =================================================================
            
            # Store old values for logging
            old_quantity = position.quantity
            old_realized_pnl = position.realized_pnl_usd
            
            # Update position quantities
            position.quantity -= sell_quantity
            position.realized_pnl_usd += realized_pnl
            position.current_value_usd = position.quantity * current_price
            
            # Calculate unrealized P&L for remaining position
            try:
                unrealized_pnl = (
                    position.current_value_usd -
                    (position.quantity * position.average_entry_price_usd)
                )
                
                # ✅ CRITICAL: Normalize tiny unrealized P&L to zero
                if abs(unrealized_pnl) < Decimal('0.0001'):
                    logger.debug(
                        f"[POSITION MANAGER] Normalizing tiny unrealized P&L: {unrealized_pnl} → 0"
                    )
                    unrealized_pnl = Decimal('0')
                
                # Validate unrealized P&L is finite
                if not unrealized_pnl.is_finite():
                    logger.error(
                        f"[POSITION MANAGER] Non-finite unrealized P&L: {unrealized_pnl}"
                    )
                    return None
                
                position.unrealized_pnl_usd = unrealized_pnl
                
            except (ArithmeticError, ZeroDivisionError) as e:
                logger.error(
                    f"[POSITION MANAGER] Failed to calculate unrealized P&L: {e}"
                )
                return None
            
            position.last_updated = timezone.now()

            # =================================================================
            # SAVE OR CLOSE POSITION
            # =================================================================
            
            # Check if position should be fully closed
            if position.quantity <= Decimal('0.0001'):  # Essentially zero
                logger.info(
                    f"[POSITION MANAGER] Position quantity below threshold "
                    f"({position.quantity:.8f}), closing position"
                )
                
                # Set all fields for closing
                position.quantity = Decimal('0')
                position.current_value_usd = Decimal('0')
                position.unrealized_pnl_usd = Decimal('0')
                position.is_open = False
                position.closed_at = timezone.now()
                
                try:
                    # Save with ALL updated fields at once
                    position.save(update_fields=[
                        'is_open',
                        'closed_at',
                        'quantity',
                        'realized_pnl_usd',
                        'current_value_usd',
                        'unrealized_pnl_usd',
                        'last_updated'
                    ])
                    
                    # Remove from memory
                    del self.positions[token_symbol]
                    
                    logger.info(
                        f"[POSITION] ✅ Closed {token_symbol} position: "
                        f"Sold {sell_quantity:.8f} tokens (${sale_value:.2f}), "
                        f"Cost basis: ${cost_basis:.2f}, "
                        f"Realized P&L: ${realized_pnl:+.2f}, "
                        f"Total realized P&L: ${position.realized_pnl_usd:+.2f}"
                    )
                    
                except Exception as e:
                    logger.error(
                        f"[POSITION MANAGER] Failed to save closed position: {e}",
                        exc_info=True
                    )
                    return None
                    
            else:
                # Position remains open with reduced quantity
                logger.info(
                    f"[POSITION MANAGER] Reducing {token_symbol} position size"
                )
                
                try:
                    position.save()
                    
                    logger.info(
                        f"[POSITION] ✅ Reduced {token_symbol} position: "
                        f"Sold {sell_quantity:.8f} tokens (${sale_value:.2f}), "
                        f"Remaining: {old_quantity:.8f} → {position.quantity:.8f} tokens, "
                        f"Value: ${position.current_value_usd:.2f}, "
                        f"Realized P&L: ${realized_pnl:+.2f} "
                        f"(Total: ${old_realized_pnl:+.2f} → ${position.realized_pnl_usd:+.2f}), "
                        f"Unrealized P&L: ${position.unrealized_pnl_usd:+.2f}"
                    )
                    
                except Exception as e:
                    logger.error(
                        f"[POSITION MANAGER] Failed to save reduced position: {e}",
                        exc_info=True
                    )
                    return None

            # =================================================================
            # UPDATE ACCOUNT P&L
            # =================================================================
            
            try:
                self.update_account_pnl()
            except Exception as e:
                logger.error(
                    f"[POSITION MANAGER] Failed to update account P&L: {e}",
                    exc_info=True
                )
                # Don't return None here - position was updated successfully

            return position

        except Exception as e:
            logger.error(
                f"[POSITION MANAGER] Unexpected error in close_or_reduce_position "
                f"for {token_symbol}: {e}",
                exc_info=True
            )
            return None

    # =========================================================================
    # P&L CALCULATION
    # =========================================================================

    def update_account_pnl(self) -> None:
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
            self.account.total_profit_loss_usd = total_unrealized_pnl + total_realized_pnl
            self.account.save(update_fields=['total_profit_loss_usd'])

            logger.debug(
                f"[ACCOUNT P&L] Updated: "
                f"Unrealized=${total_unrealized_pnl:.2f}, "
                f"Realized=${total_realized_pnl:.2f}, "
                f"Total=${self.account.total_profit_loss_usd:.2f}"
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
            (pos.total_invested_usd for pos in self.positions.values()),
            Decimal('0')
        )

    def get_total_value(self) -> Decimal:
        """
        Get total current value of all positions.

        Returns:
            Total current value in USD
        """
        return sum(
            (pos.current_value_usd for pos in self.positions.values()),
            Decimal('0')
        )

    def get_total_unrealized_pnl(self) -> Decimal:
        """
        Get total unrealized P&L across all positions.

        Returns:
            Total unrealized P&L in USD
        """
        return sum(
            (pos.unrealized_pnl_usd for pos in self.positions.values()),
            Decimal('0')
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