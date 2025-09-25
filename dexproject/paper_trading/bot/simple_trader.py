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
        
        logger.info("🤖 Enhanced Paper Trading Bot initialized")
    
    def initialize(self) -> bool:
        """
        Initialize bot components and create trading session.
        
        Returns:
            True if initialization successful, False otherwise
        """
        try:
            # Load account
            self.account = PaperTradingAccount.objects.get(id=self.account_id)
            logger.info(f"📊 Loaded account: {self.account.name}")
            
            # Create new trading session
            self.session = PaperTradingSession.objects.create(
                account=self.account,
                bot_type='ENHANCED_AI',
                status='RUNNING'
            )
            logger.info(f"🎮 Created trading session: {self.session.id}")
            
            # Initialize AI engine
            self.ai_engine = create_ai_engine(self.session)
            logger.info("🧠 AI Engine initialized")
            
            # Load existing positions
            self._load_positions()
            
            # Initialize price history with simulated data
            self._initialize_price_history()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Initialization failed: {e}")
            return False
    
    def _load_positions(self):
        """Load existing open positions for the account."""
        positions = PaperPosition.objects.filter(
            account=self.account,
            is_open=True
        )
        for position in positions:
            self.positions[position.token_symbol] = position
            logger.info(f"📦 Loaded position: {position.token_symbol} - {position.quantity} tokens")
    
    def _initialize_price_history(self):
        """Initialize price history with simulated historical data."""
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
            logger.debug(f"📈 Initialized price history for {symbol}")
    
    def run(self):
        """
        Main bot loop - analyze markets and execute trades.
        """
        logger.info("🚀 Starting enhanced paper trading bot...")
        self.running = True
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        tick_count = 0
        
        try:
            while self.running:
                tick_count += 1
                logger.info(f"\n{'='*60}")
                logger.info(f"📍 Market Tick #{tick_count} - {datetime.now().strftime('%H:%M:%S')}")
                
                # Update market prices
                self._update_market_prices()
                
                # Analyze each token
                for symbol in self.price_history.keys():
                    self._process_token(symbol)
                
                # Update session metrics
                self._update_session_metrics()
                
                # Display current status
                self._display_status()
                
                # Wait for next tick
                if self.running:
                    time.sleep(self.tick_interval)
                    
        except Exception as e:
            logger.error(f"❌ Bot error: {e}")
            self.running = False
            
        finally:
            self._cleanup()
    
    def _update_market_prices(self):
        """Simulate market price updates."""
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
                logger.info(f"💹 {symbol}: ${current_price:.6f} → ${new_price:.6f} ({price_change_pct:+.2f}%)")
    
    def _process_token(self, symbol: str):
        """
        Process a single token - analyze and potentially trade.
        
        Args:
            symbol: Token symbol to process
        """
        # Check if we can trade (time restriction)
        if self.last_trade_time:
            time_since_trade = (datetime.now() - self.last_trade_time).total_seconds()
            if time_since_trade < self.min_trade_interval:
                return
        
        # Get token info
        token_address = f"0x{symbol}..."  # Simulated address
        prices = self.price_history.get(symbol, [])
        
        if not prices:
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
        logger.info(f"🤔 AI Decision for {symbol}: {decision['action']} "
                   f"({decision['signal'].value}, {decision['confidence_score']:.0f}% confidence)")
        
        # Execute trade if signaled
        if decision['action'] in ['BUY', 'SELL']:
            self._execute_trade(symbol, decision)
    
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
        
        # Calculate trade amount
        portfolio_value = self.account.current_balance_usd
        trade_value = portfolio_value * (position_size_percent / 100)
        
        # Check if we have enough balance
        if action == 'BUY' and trade_value > self.account.current_balance_usd:
            logger.warning(f"⚠️ Insufficient balance for {symbol} purchase")
            return
        
        # Check if we have position to sell
        if action == 'SELL' and symbol not in self.positions:
            logger.warning(f"⚠️ No position to sell for {symbol}")
            return
        
        try:
            with transaction.atomic():
                # Create the trade
                trade = PaperTrade.objects.create(
                    account=self.account,
                    session=self.session,
                    trade_type=action,
                    token_address=decision['token_address'],
                    token_symbol=symbol,
                    quantity=trade_value / current_price if action == 'BUY' else self.positions[symbol].quantity,
                    price=current_price,
                    total_value=trade_value,
                    gas_fee=Decimal("5.00"),  # Simulated gas
                    slippage=Decimal("0.5"),  # Simulated slippage
                    
                    # AI metadata
                    strategy_used=decision['lane_type'],
                    confidence_score=decision['confidence_score'],
                    risk_score=decision['risk_assessment']['risk_score'],
                    
                    # Execution
                    status='COMPLETED',
                    executed_at=timezone.now()
                )
                
                # Update position
                if action == 'BUY':
                    # Create or update position
                    if symbol in self.positions:
                        position = self.positions[symbol]
                        # Average the entry price
                        total_value = (position.quantity * position.entry_price) + trade_value
                        position.quantity += trade.quantity
                        position.entry_price = total_value / position.quantity
                        position.last_updated = timezone.now()
                        position.save()
                    else:
                        position = PaperPosition.objects.create(
                            account=self.account,
                            token_address=decision['token_address'],
                            token_symbol=symbol,
                            quantity=trade.quantity,
                            entry_price=current_price,
                            current_price=current_price,
                            is_open=True
                        )
                        self.positions[symbol] = position
                    
                    # Update account balance
                    self.account.current_balance_usd -= trade_value
                    
                else:  # SELL
                    position = self.positions[symbol]
                    
                    # Calculate P&L
                    pnl = (current_price - position.entry_price) * position.quantity
                    trade.pnl = pnl
                    trade.pnl_percent = (pnl / (position.entry_price * position.quantity)) * 100
                    trade.save()
                    
                    # Update position
                    position.current_price = current_price
                    position.realized_pnl = pnl
                    position.is_open = False
                    position.closed_at = timezone.now()
                    position.save()
                    
                    # Remove from active positions
                    del self.positions[symbol]
                    
                    # Update account balance
                    self.account.current_balance_usd += trade_value
                    
                    # Track performance
                    if pnl > 0:
                        self.successful_trades += 1
                
                # Save account changes
                self.account.total_trades += 1
                self.account.save()
                
                # Update metrics
                self.trades_executed += 1
                self.last_trade_time = datetime.now()
                
                # Log trade execution
                logger.info(f"✅ {action} executed: {trade.quantity:.6f} {symbol} @ ${current_price:.6f}")
                logger.info(f"💰 Value: ${trade_value:.2f}, New balance: ${self.account.current_balance_usd:.2f}")
                
                if action == 'SELL' and pnl is not None:
                    logger.info(f"📊 P&L: ${pnl:.2f} ({trade.pnl_percent:.2f}%)")
                
                # Update AI performance metrics
                if action == 'SELL':
                    self.ai_engine.update_performance_metrics({
                        'profitable': pnl > 0,
                        'pnl': pnl
                    })
                
        except Exception as e:
            logger.error(f"❌ Trade execution failed: {e}")
    
    def _update_session_metrics(self):
        """Update trading session metrics."""
        try:
            # Calculate total P&L
            total_pnl = sum(
                position.realized_pnl or 0
                for position in PaperPosition.objects.filter(
                    account=self.account,
                    is_open=False
                )
            )
            
            # Update session
            self.session.total_trades = self.trades_executed
            self.session.profitable_trades = self.successful_trades
            self.session.total_pnl = total_pnl
            
            if self.trades_executed > 0:
                self.session.win_rate = (self.successful_trades / self.trades_executed) * 100
            
            self.session.save()
            
        except Exception as e:
            logger.error(f"Failed to update session metrics: {e}")
    
    def _display_status(self):
        """Display current bot status."""
        logger.info(f"\n📊 Bot Status:")
        logger.info(f"   Account Balance: ${self.account.current_balance_usd:.2f}")
        logger.info(f"   Open Positions: {len(self.positions)}")
        logger.info(f"   Trades Executed: {self.trades_executed}")
        
        if self.trades_executed > 0:
            win_rate = (self.successful_trades / self.trades_executed) * 100
            logger.info(f"   Win Rate: {win_rate:.1f}%")
        
        # Display positions
        if self.positions:
            logger.info(f"\n📦 Open Positions:")
            for symbol, position in self.positions.items():
                current_price = self.price_history[symbol][-1]
                unrealized_pnl = (current_price - position.entry_price) * position.quantity
                pnl_percent = (unrealized_pnl / (position.entry_price * position.quantity)) * 100
                
                logger.info(f"   {symbol}: {position.quantity:.6f} @ ${position.entry_price:.6f}")
                logger.info(f"      Current: ${current_price:.6f}, P&L: ${unrealized_pnl:.2f} ({pnl_percent:+.2f}%)")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info("\n🛑 Shutdown signal received...")
        self.running = False
    
    def _cleanup(self):
        """Cleanup resources and close session."""
        try:
            # Update final session status
            if self.session:
                self.session.status = 'STOPPED'
                self.session.ended_at = timezone.now()
                self.session.save()
                logger.info(f"📊 Session {self.session.id} ended")
            
            # Close any open positions (mark as closed in session)
            for symbol, position in self.positions.items():
                current_price = self.price_history[symbol][-1]
                position.current_price = current_price
                position.save()
                logger.info(f"📦 Position {symbol} marked with final price ${current_price:.6f}")
            
            logger.info("✅ Cleanup completed")
            
        except Exception as e:
            logger.error(f"Cleanup error: {e}")


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
        logger.info("✅ Bot initialized successfully")
        bot.run()
    else:
        logger.error("❌ Bot initialization failed")
        sys.exit(1)


if __name__ == "__main__":
    main()