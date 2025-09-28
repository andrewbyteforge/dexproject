"""
Enhanced Paper Trading Bot - PTphase2

This module implements an intelligent paper trading bot that uses the AI decision engine
to analyze markets and execute trades. It integrates thought logging, Fast/Smart lane
strategies, and comprehensive performance tracking.

Features:
- AI-driven decision making
- Fast Lane and Smart Lane trading strategies
- Detailed thought logging for every decision
- Real-time performance metrics
- Graceful shutdown handling
- Configurable trading parameters

File: dexproject/paper_trading/bot/simple_trader.py
"""

import uuid
import os
import sys
import time
import signal
import logging
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import random

# Add project root to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Django setup
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
django.setup()

from django.utils import timezone
from django.db import transaction

from paper_trading.models import (
    PaperTradingAccount,
    PaperTrade,
    PaperPosition,
    PaperTradingSession,
    PaperAIThoughtLog,
    PaperStrategyConfiguration,
    PaperPerformanceMetrics
)

# Import the AI engine
from paper_trading.bot.ai_engine import (
    create_ai_engine,
    PaperTradingAIEngine,
    TradingSignal
)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('paper_trading_bot.log')
    ]
)
logger = logging.getLogger(__name__)


class EnhancedPaperTradingBot:
    """
    Enhanced paper trading bot with AI-driven decision making.
    
    This bot uses the AI engine to analyze markets, make intelligent trading decisions,
    and maintain detailed logs of its reasoning process.
    """
    
    def __init__(self, account_id: int):
        """
        Initialize the enhanced paper trading bot.
        
        Args:
            account_id: ID of the paper trading account to use
        """
        self.account_id = account_id
        self.account = None
        self.session = None
        self.ai_engine = None
        self.running = False
        self.positions = {}  # token_symbol -> PaperPosition
        
        # Trading parameters
        self.tick_interval = 5  # seconds between market checks
        self.min_trade_interval = 10  # minimum seconds between trades
        self.last_trade_time = None
        
        # Market simulation parameters
        self.price_volatility = Decimal("0.05")  # 5% max price change per tick
        self.trend_probability = 0.6  # 60% chance to continue trend
        
        # Price tracking
        self.price_history = {}  # token_symbol -> List[Decimal]
        self.max_history_length = 20
        
        # Performance tracking
        self.trades_executed = 0
        self.successful_trades = 0
        
        logger.info("[BOT] Enhanced Paper Trading Bot initialized")
    
    def initialize(self) -> bool:
        """
        Initialize bot components and create trading session.
        
        Returns:
            True if initialization successful, False otherwise
        """
        try:
            # Load account
            self.account = PaperTradingAccount.objects.get(pk=self.account_id)
            logger.info(f"[DATA] Loaded account: {self.account.name}")
            
            # Create new trading session
            self.session = PaperTradingSession.objects.create(
                account=self.account,
                name=f"AI_Bot_Session_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                status='RUNNING',
                starting_balance_usd=self.account.current_balance_usd
            )
            logger.info(f"[GAME] Created trading session: {self.session.session_id}")
            
            # Initialize AI engine
            self.ai_engine = create_ai_engine(self.session)
            logger.info("[AI] AI Engine initialized")
            
            # Load existing positions
            self._load_positions()
            
            # Initialize price history with simulated data
            self._initialize_price_history()
            
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] Initialization failed: {e}", exc_info=True)
            return False
    
    def _load_positions(self):
        """Load existing open positions for the account."""
        try:
            positions = PaperPosition.objects.filter(
                account=self.account,
                is_open=True
            )
            for position in positions:
                self.positions[position.token_symbol] = position
                logger.info(f"[POS] Loaded position: {position.token_symbol} - {position.quantity} tokens")
        except Exception as e:
            logger.error(f"[ERROR] Failed to load positions: {e}", exc_info=True)
    
    def _initialize_price_history(self):
        """Initialize price history with simulated historical data."""
        try:
            # Simulate some popular tokens
            tokens = [
                ("0x1234...WETH", "WETH", Decimal("2500.00")),
                ("0x5678...USDC", "USDC", Decimal("1.00")),
                ("0x9abc...PEPE", "PEPE", Decimal("0.000001")),
                ("0xdef0...SHIB", "SHIB", Decimal("0.00001")),
                ("0x1111...DOGE", "DOGE", Decimal("0.08")),
            ]
            
            for address, symbol, base_price in tokens:
                # Generate historical prices
                history = []
                price = base_price
                for _ in range(10):
                    # Random walk
                    change = price * Decimal(random.uniform(-0.02, 0.02))
                    price = max(price + change, price * Decimal("0.5"))  # Prevent negative
                    history.append(price)
                
                self.price_history[symbol] = history
                logger.debug(f"[UP] Initialized price history for {symbol}")
        except Exception as e:
            logger.error(f"[ERROR] Failed to initialize price history: {e}", exc_info=True)
    
    def run(self):
        """
        Main bot loop - analyze markets and execute trades.
        """
        logger.info("[START] Starting enhanced paper trading bot...")
        self.running = True
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        tick_count = 0
        
        try:
            while self.running:
                tick_count += 1
                logger.info(f"\n{'='*60}")
                logger.info(f"[TICK] Market Tick #{tick_count} - {datetime.now().strftime('%H:%M:%S')}")
                
                # Update market prices
                self._update_market_prices()
                
                # Analyze each token
                for symbol in self.price_history.keys():
                    try:
                        self._process_token(symbol)
                    except Exception as e:
                        logger.error(f"[ERROR] Failed to process {symbol}: {e}", exc_info=True)
                
                # Update session metrics
                self._update_session_metrics()
                
                # Display current status
                self._display_status()
                
                # Wait for next tick
                if self.running:
                    time.sleep(self.tick_interval)
                    
        except Exception as e:
            logger.error(f"[ERROR] Bot error: {e}", exc_info=True)
            self.running = False
            
        finally:
            self._cleanup()
    
    def _update_market_prices(self):
        """Simulate market price updates."""
        try:
            for symbol, prices in self.price_history.items():
                current_price = prices[-1] if prices else Decimal("1.0")
                
                # Determine trend continuation
                if len(prices) >= 2:
                    trend = prices[-1] - prices[-2]
                    if random.random() < self.trend_probability and trend != 0:
                        # Continue trend
                        change_factor = abs(trend) / prices[-2] * Decimal(random.uniform(0.5, 1.5))
                        change = current_price * change_factor * (1 if trend > 0 else -1)
                    else:
                        # Random change
                        change = current_price * Decimal(random.uniform(-0.03, 0.03))
                else:
                    # Random change
                    change = current_price * Decimal(random.uniform(-0.03, 0.03))
                
                # Apply change with volatility
                volatility_factor = Decimal(random.uniform(0.5, 1.5))
                new_price = current_price + (change * volatility_factor)
                new_price = max(new_price, current_price * Decimal("0.5"))  # Prevent crash
                
                # Update history
                prices.append(new_price)
                if len(prices) > self.max_history_length:
                    prices.pop(0)
                
                # Log significant changes
                price_change_pct = ((new_price - current_price) / current_price * 100) if current_price > 0 else 0
                if abs(price_change_pct) > 2:
                    logger.info(f"[PRICE] {symbol}: ${current_price:.6f} -> ${new_price:.6f} ({price_change_pct:+.2f}%)")
        except Exception as e:
            logger.error(f"[ERROR] Failed to update market prices: {e}", exc_info=True)
    
    def _process_token(self, symbol: str):
        """
        Process a single token - analyze and potentially trade.
        
        Args:
            symbol: Token symbol to process
        """
        try:
            # Check if we can trade (time restriction)
            if self.last_trade_time:
                time_since_trade = (datetime.now() - self.last_trade_time).total_seconds()
                if time_since_trade < self.min_trade_interval:
                    return
            
            # Get token info
            token_address = f"0x{symbol}..."  # Simulated address
            prices = self.price_history.get(symbol, [])
            
            if not prices:
                logger.warning(f"[WARN] No price history for {symbol}")
                return
            
            current_price = prices[-1]
            
            # Get AI decision
            decision = self.ai_engine.generate_decision(
                token_address=token_address,
                token_symbol=symbol,
                current_price=current_price,
                price_history=prices[:-1]  # Don't include current price in history
            )
            
            # Log the decision
            logger.info(f"[THINK] AI Decision for {symbol}: {decision['action']} "
                       f"({decision['signal'].value}, {decision['confidence_score']:.0f}% confidence)")
            
            # Execute trade if signaled
            if decision['action'] in ['BUY', 'SELL']:
                self._execute_trade(symbol, decision)
        except Exception as e:
            logger.error(f"[ERROR] Failed to process token {symbol}: {e}", exc_info=True)
    
    def _execute_trade(self, symbol: str, decision: Dict[str, Any]):
        """
        Execute a paper trade based on AI decision.
        
        Args:
            symbol: Token symbol
            decision: AI decision dictionary
        """
        action = decision['action']
        position_size_percent = decision['position_size_percent']
        current_price = decision['current_price']
        
        logger.debug(f"[TRADE] Attempting {action} for {symbol} at ${current_price}")
        
        try:
            # Calculate trade amount
            portfolio_value = self.account.current_balance_usd
            trade_value = portfolio_value * (position_size_percent / 100)
            
            # Check if we have enough balance for BUY
            if action == 'BUY' and trade_value > self.account.current_balance_usd:
                logger.warning(f"[WARN] Insufficient balance for {symbol} purchase: need ${trade_value:.2f}, have ${self.account.current_balance_usd:.2f}")
                return
            
            # Check if we have position to sell
            if action == 'SELL' and symbol not in self.positions:
                logger.warning(f"[WARN] No position to sell for {symbol}")
                return
            
            with transaction.atomic():
                # Define token variables BEFORE using them
                if action == 'BUY':
                    # Buy trade - USD to token
                    token_in = 'USDC'
                    token_in_address = '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'  # USDC
                    token_out = symbol
                    token_out_address = decision['token_address']
                    amount_in_usd = trade_value
                    amount_out = trade_value / current_price
                    amount_in = trade_value
                else:
                    # Sell trade - token to USD
                    position = self.positions[symbol]
                    token_in = symbol
                    token_in_address = decision['token_address']
                    token_out = 'USDC'
                    token_out_address = '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'  # USDC
                    amount_in = position.quantity
                    amount_out = position.quantity * current_price
                    amount_in_usd = amount_out
                
                # Create the trade record
                trade = PaperTrade.objects.create(
                    account=self.account,
                    trade_type=action.lower(),  # 'buy' or 'sell'
                    token_in_address=token_in_address,
                    token_in_symbol=token_in,
                    token_out_address=token_out_address,
                    token_out_symbol=token_out,
                    amount_in=amount_in,
                    amount_in_usd=amount_in_usd,
                    expected_amount_out=amount_out,
                    actual_amount_out=amount_out * Decimal("0.995"),  # 0.5% slippage
                    simulated_gas_price_gwei=Decimal("30"),
                    simulated_gas_used=150000,
                    simulated_gas_cost_usd=Decimal("5.00"),
                    simulated_slippage_percent=Decimal("0.5"),
                    status='completed',
                    executed_at=timezone.now(),
                    execution_time_ms=500,
                    strategy_name=decision['lane_type'],
                    mock_tx_hash=f"0x{uuid.uuid4().hex[:64]}"
                )
                
                logger.debug(f"[TRADE] Trade record created: {trade.trade_id}")
                
                # Update position based on action
                if action == 'BUY':
                    self._handle_buy_position(symbol, amount_out, current_price, trade_value, decision)
                else:  # SELL
                    self._handle_sell_position(symbol, current_price, amount_out)
                
                # Save account changes
                self.account.total_trades += 1
                self.account.save()
                
                # Update metrics
                self.trades_executed += 1
                self.last_trade_time = datetime.now()
                
                logger.info(f"[OK] {action} executed: {amount_out:.6f} {token_out} @ ${current_price:.6f}")
                logger.info(f"[MONEY] Value: ${trade_value:.2f}, New balance: ${self.account.current_balance_usd:.2f}")
                
        except Exception as e:
            logger.error(f"[ERROR] Trade execution failed: {e}", exc_info=True)
    
    def _handle_buy_position(self, symbol: str, amount_out: Decimal, current_price: Decimal, 
                            trade_value: Decimal, decision: Dict[str, Any]):
        """
        Handle BUY trade - create or update position.
        
        Args:
            symbol: Token symbol
            amount_out: Amount of tokens purchased
            current_price: Current token price
            trade_value: USD value of trade
            decision: AI decision dictionary
        """
        try:
            if symbol in self.positions:
                # Update existing position
                position = self.positions[symbol]
                
                # Calculate new average entry price
                total_value = (position.quantity * position.average_entry_price_usd) + trade_value
                new_quantity = position.quantity + amount_out
                new_avg_price = total_value / new_quantity
                
                position.quantity = new_quantity
                position.average_entry_price_usd = new_avg_price
                position.current_price_usd = current_price
                position.total_invested_usd += trade_value
                position.current_value_usd = new_quantity * current_price
                position.unrealized_pnl_usd = (current_price - new_avg_price) * new_quantity
                position.last_updated = timezone.now()
                position.save(update_fields=[
                    'current_price_usd',
                    'current_value_usd', 
                    'realized_pnl_usd',
                    'unrealized_pnl_usd',
                    'is_open',
                    'closed_at'
                ])
                
                logger.debug(f"[POS] Updated position for {symbol}: {new_quantity:.6f} @ ${new_avg_price:.6f}")
            else:
                # Create new position
                position = PaperPosition.objects.create(
                    account=self.account,
                    token_address=decision['token_address'],
                    token_symbol=symbol,
                    quantity=amount_out,
                    average_entry_price_usd=current_price,
                    current_price_usd=current_price,
                    total_invested_usd=trade_value,
                    current_value_usd=amount_out * current_price,
                    unrealized_pnl_usd=Decimal("0"),
                    realized_pnl_usd=Decimal("0"),
                    is_open=True
                )
                self.positions[symbol] = position
                
                logger.debug(f"[POS] Created new position for {symbol}: {amount_out:.6f} @ ${current_price:.6f}")
            
            # Update account balance (deduct trade value + gas)
            self.account.current_balance_usd -= (trade_value + Decimal("5.00"))
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to handle buy position for {symbol}: {e}", exc_info=True)
            raise
    
    def _handle_sell_position(self, symbol: str, current_price: Decimal, amount_out: Decimal):
        """
        Handle SELL trade - close position.
        
        Args:
            symbol: Token symbol
            current_price: Current token price
            amount_out: USD value received from sale
        """
        try:
            position = self.positions[symbol]
            
            # Calculate P&L
            pnl = (current_price - position.average_entry_price_usd) * position.quantity
            pnl_percent = (pnl / position.total_invested_usd) * 100 if position.total_invested_usd > 0 else 0
            
            logger.info(f"[DATA] P&L for {symbol}: ${pnl:.2f} ({pnl_percent:+.2f}%)")
            
            # WORKAROUND: Delete any old closed positions for this token first
            # This prevents unique constraint violations

            
            # Now close the current position
            PaperPosition.objects.filter(
                account=self.account,
                token_symbol=symbol,
                is_open=True
            ).update(
                current_price_usd=current_price,
                current_value_usd=position.quantity * current_price,
                realized_pnl_usd=pnl,
                unrealized_pnl_usd=Decimal("0"),
                is_open=False,
                closed_at=timezone.now()
            )
            
            logger.debug(f"[POS] Closed position for {symbol}: P&L=${pnl:.2f}")
            
            # Remove from active positions
            del self.positions[symbol]
            
            # Update account balance (add sale proceeds minus gas)
            self.account.current_balance_usd += (amount_out - Decimal("5.00"))
            
            # Track performance
            if pnl > 0:
                self.successful_trades += 1
                logger.info(f"[WIN] Profitable trade: +${pnl:.2f}")
            else:
                logger.info(f"[LOSS] Unprofitable trade: ${pnl:.2f}")
            
            # Update AI performance metrics
            self.ai_engine.update_performance_metrics({
                'profitable': pnl > 0,
                'pnl': pnl
            })
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to handle sell position for {symbol}: {e}", exc_info=True)
            raise





    def _update_session_metrics(self):
        """Update trading session metrics."""
        try:
            # Calculate total realized P&L from closed positions
            closed_positions = PaperPosition.objects.filter(
                account=self.account,
                is_open=False
            )
            
            total_realized_pnl = sum(
                position.realized_pnl_usd or Decimal("0")  # FIXED: Use realized_pnl_usd
                for position in closed_positions
            )
            
            # Update session
            self.session.total_trades_executed = self.trades_executed
            self.session.successful_trades = self.successful_trades
            self.session.session_pnl_usd = total_realized_pnl
            self.session.last_heartbeat = timezone.now()
            
            # Calculate failed trades
            self.session.failed_trades = self.trades_executed - self.successful_trades
            
            self.session.save()
            
            logger.debug(f"[METRICS] Session updated: {self.trades_executed} trades, ${total_realized_pnl:.2f} P&L")
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to update session metrics: {e}", exc_info=True)
    
    def _display_status(self):
        """Display current bot status."""
        try:
            logger.info(f"\n[DATA] Bot Status:")
            logger.info(f"   Account Balance: ${self.account.current_balance_usd:.2f}")
            logger.info(f"   Open Positions: {len(self.positions)}")
            logger.info(f"   Trades Executed: {self.trades_executed}")
            
            if self.trades_executed > 0:
                win_rate = (self.successful_trades / self.trades_executed) * 100
                logger.info(f"   Win Rate: {win_rate:.1f}%")
            
            # Display positions
            if self.positions:
                logger.info(f"\n[POS] Open Positions:")
                for symbol, position in self.positions.items():
                    current_price = self.price_history[symbol][-1]
                    unrealized_pnl = (current_price - position.average_entry_price_usd) * position.quantity
                    pnl_percent = (unrealized_pnl / (position.average_entry_price_usd * position.quantity)) * 100
                    
                    logger.info(f"   {symbol}: {position.quantity:.6f} @ ${position.average_entry_price_usd:.6f}")
                    logger.info(f"      Current: ${current_price:.6f}, P&L: ${unrealized_pnl:.2f} ({pnl_percent:+.2f}%)")
        except Exception as e:
            logger.error(f"[ERROR] Failed to display status: {e}", exc_info=True)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info("\n[STOP] Shutdown signal received...")
        self.running = False
    
    def _cleanup(self):
        """Cleanup resources and close session."""
        try:
            # Update final session status
            if self.session:
                self.session.status = 'STOPPED'
                self.session.ended_at = timezone.now()
                self.session.ending_balance_usd = self.account.current_balance_usd
                self.session.save()
                logger.info(f"[DATA] Session {self.session.session_id} ended")
            
            # Update final prices for open positions
            for symbol, position in self.positions.items():
                try:
                    current_price = self.price_history[symbol][-1]
                    position.current_price_usd = current_price
                    position.current_value_usd = position.quantity * current_price
                    position.unrealized_pnl_usd = (current_price - position.average_entry_price_usd) * position.quantity
                    position.save()
                    logger.info(f"[POS] Position {symbol} marked with final price ${current_price:.6f}")
                except Exception as e:
                    logger.error(f"[ERROR] Failed to update final price for {symbol}: {e}")
            
            logger.info("[OK] Cleanup completed")
            
        except Exception as e:
            logger.error(f"[ERROR] Cleanup error: {e}", exc_info=True)


def main():
    """Main entry point for the enhanced paper trading bot."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Enhanced Paper Trading Bot with AI')
    parser.add_argument('--account-id', type=int, default=1,
                       help='Paper trading account ID to use')
    parser.add_argument('--tick-interval', type=int, default=5,
                       help='Seconds between market ticks')
    
    args = parser.parse_args()
    
    # Create and run bot
    bot = EnhancedPaperTradingBot(account_id=args.account_id)
    bot.tick_interval = args.tick_interval
    
    if bot.initialize():
        logger.info("[OK] Bot initialized successfully")
        bot.run()
    else:
        logger.error("[ERROR] Bot initialization failed")
        sys.exit(1)


if __name__ == "__main__":
    main()