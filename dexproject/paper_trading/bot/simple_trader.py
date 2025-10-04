#!/usr/bin/env python
"""
Enhanced Paper Trading Bot with Intel Slider System

This is the primary paper trading bot implementation.
It replaces multiple bot implementations with
a single, unified system.

Key Features:
- Intel Slider system (1-10 intelligence levels)
- Modular market analyzers
- Comprehensive thought logging
- WebSocket real-time updates
- Performance tracking
- Clean separation of concerns

File: dexproject/paper_trading/bot/simple_trader.py
"""

import os
import sys
import time
import signal
import logging
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple, Union
import random
import uuid

# ============================================================================
# DJANGO SETUP
# ============================================================================
# Add project root to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Django setup
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
django.setup()

from django.utils import timezone
from django.db import transaction
from asgiref.sync import async_to_sync

# ============================================================================
# MODEL IMPORTS
# ============================================================================
from paper_trading.models import (
    PaperTradingAccount,
    PaperTrade,
    PaperPosition,
    PaperTradingSession,
    PaperAIThoughtLog,
    PaperStrategyConfiguration,
    PaperPerformanceMetrics
)

# ============================================================================
# INTELLIGENCE SYSTEM IMPORTS
# ============================================================================
from paper_trading.intelligence.intel_slider import IntelSliderEngine
from paper_trading.intelligence.base import (
    IntelligenceLevel,
    MarketContext,
    TradingDecision
)

# ============================================================================
# SERVICE IMPORTS - Use global instance
# ============================================================================
from paper_trading.services.websocket_service import websocket_service

# ============================================================================
# LEGACY AI ENGINE IMPORT (for backward compatibility during transition)
# ============================================================================
from paper_trading.bot.ai_engine import (
    TradingSignal as LegacyTradingSignal,
    MarketCondition
)

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
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
    Unified Paper Trading Bot with Intel Slider System.
    
    This bot consolidates all trading logic into a single implementation
    with configurable intelligence levels (1-10) that control:
    - Risk tolerance
    - Trading frequency
    - Gas strategies
    - MEV protection
    - Decision confidence thresholds
    """
    
    def __init__(self, account_id: Union[str, uuid.UUID, int], intel_level: int = 5):
        """
        Initialize the enhanced paper trading bot.
        
        Args:
            account_id: ID of the paper trading account to use (can be UUID, string, or int)
            intel_level: Intelligence level (1-10) controlling bot behavior
                1-3: Ultra cautious
                4-6: Balanced
                7-9: Aggressive
                10: Fully autonomous with ML
        """
        # ====================================================================
        # CORE CONFIGURATION
        # ====================================================================
        # Handle different account_id types (UUID, string, or int)
        self.account_id = account_id
        self.intel_level = intel_level
        self.account = None
        self.session = None
        self.running = False
        
        # ====================================================================
        # INTELLIGENCE SYSTEM
        # ====================================================================
        self.intelligence_engine = None  # Will be initialized in initialize()
        # Use the global websocket service instance
        self.websocket_service = websocket_service
        
        # ====================================================================
        # POSITION TRACKING
        # ====================================================================
        self.positions = {}  # token_symbol -> PaperPosition
        
        # ====================================================================
        # TRADING PARAMETERS (adjusted by intel level)
        # ====================================================================
        self.tick_interval = self._calculate_tick_interval()  # Seconds between checks
        self.min_trade_interval = 10  # Minimum seconds between trades
        self.last_trade_time = None
        
        # ====================================================================
        # MARKET SIMULATION PARAMETERS
        # ====================================================================
        self.price_volatility = Decimal("0.05")  # 5% max price change per tick
        self.trend_probability = 0.6  # 60% chance to continue trend
        
        # ====================================================================
        # PRICE TRACKING
        # ====================================================================
        self.price_history = {}  # token_symbol -> List[Decimal]
        self.max_history_length = 20
        
        # ====================================================================
        # PERFORMANCE METRICS
        # ====================================================================
        self.trades_executed = 0
        self.successful_trades = 0
        self.failed_trades = 0
        self.total_pnl = Decimal('0')
        
        # ====================================================================
        # DECISION TRACKING
        # ====================================================================
        self.last_decisions = {}  # token_symbol -> TradingDecision
        
        logger.info(f"[BOT] Enhanced Paper Trading Bot initialized with Intel Level {intel_level}")
    
    def _calculate_tick_interval(self) -> int:
        """
        Calculate tick interval based on intelligence level.
        
        Higher intelligence levels check markets more frequently.
        
        Returns:
            Seconds between market checks
        """
        if self.intel_level <= 3:
            return 30  # Cautious: Check every 30 seconds
        elif self.intel_level <= 6:
            return 15  # Balanced: Check every 15 seconds
        elif self.intel_level <= 9:
            return 5   # Aggressive: Check every 5 seconds
        else:
            return 3   # Autonomous: Check every 3 seconds
    
    def initialize(self) -> bool:
        """
        Initialize bot components and create trading session.
        
        This method:
        1. Loads the trading account
        2. Creates a new trading session
        3. Initializes the intelligence engine
        4. Loads existing positions
        5. Sets up price tracking
        
        Returns:
            True if initialization successful, False otherwise
        """
        try:
            # ================================================================
            # LOAD ACCOUNT
            # ================================================================
            self.account = PaperTradingAccount.objects.get(pk=self.account_id)
            logger.info(f"[DATA] Loaded account: {self.account.name}")
            
            # ================================================================
            # CREATE TRADING SESSION
            # ================================================================
            # Build bot configuration first
            self.bot_config = {
                'intel_level': self.intel_level,
                'tick_interval': self.tick_interval,
                'min_trade_interval': self.min_trade_interval,
                'price_volatility': float(self.price_volatility),
                'trend_probability': self.trend_probability,
            }

            # Now create the session with the config
            self.session = PaperTradingSession.objects.create(
                account=self.account,
                name=f"Intel Bot Session - Level {self.intel_level}",
                config_snapshot=self.bot_config,
                starting_balance_usd=self.account.current_balance_usd
            )
            logger.info(f"[SESSION] Created trading session: {self.session.session_id}")
            
            # ================================================================
            # INITIALIZE INTELLIGENCE ENGINE
            # ================================================================
            self.intelligence_engine = IntelSliderEngine(
                intel_level=self.intel_level,
                account_id=str(self.account.account_id)
            )
            logger.info(f"[INTEL] Intelligence Engine initialized at Level {self.intel_level}")
            
            # ================================================================
            # GET OR CREATE STRATEGY CONFIGURATION
            # ================================================================
            self._setup_strategy_configuration()
            
            # ================================================================
            # LOAD EXISTING POSITIONS
            # ================================================================
            self._load_positions()
            
            # ================================================================
            # INITIALIZE PRICE TRACKING
            # ================================================================
            self._initialize_price_tracking()
            
            # ================================================================
            # SEND INITIALIZATION NOTIFICATION
            # ================================================================
            self._send_bot_status_update('initialized')
            
            return True
            
        except PaperTradingAccount.DoesNotExist:
            logger.error(f"[ERROR] Account with ID {self.account_id} not found")
            return False
        except Exception as e:
            logger.error(f"[ERROR] Bot initialization failed: {e}", exc_info=True)
            return False
    
    def _setup_strategy_configuration(self):
        """Setup or get strategy configuration based on intel level."""
        try:
            # Map intel levels to trading modes
            if self.intel_level <= 3:
                trading_mode = 'CONSERVATIVE'
                description = 'Ultra-safe trading with minimal risk'
            elif self.intel_level <= 6:
                trading_mode = 'BALANCED'
                description = 'Balanced risk/reward approach'
            elif self.intel_level <= 9:
                trading_mode = 'AGGRESSIVE'
                description = 'High-risk high-reward trading'
            else:
                trading_mode = 'EXPERIMENTAL'
                description = 'ML-driven autonomous trading'
            
            # Get or create configuration
            self.strategy_config, created = PaperStrategyConfiguration.objects.get_or_create(
                account=self.account,
                name=f"Intel_{self.intel_level}_Config",
                defaults={
                    'trading_mode': trading_mode,
                    'description': description,
                    'is_active': True,
                    'config': {
                        'intel_level': self.intel_level,
                        'risk_tolerance': (self.intel_level / 10) * 100,
                        'max_position_size': 5 + (self.intel_level * 2),
                        'stop_loss_enabled': self.intel_level <= 7,
                        'stop_loss_percent': max(2, 10 - self.intel_level),
                        'take_profit_enabled': True,
                        'take_profit_percent': 5 + (self.intel_level * 2),
                        'use_mev_protection': True,
                        'max_gas_price_gwei': 50 + (self.intel_level * 10),
                        'slippage_tolerance': min(5, 1 + (self.intel_level * 0.5)),
                    }
                }
            )
            
            if created:
                logger.info(f"[CONFIG] Created new strategy configuration: {self.strategy_config.name}")
            else:
                logger.info(f"[CONFIG] Using existing configuration: {self.strategy_config.name}")
                
        except Exception as e:
            logger.error(f"[ERROR] Failed to setup strategy configuration: {e}")
            # Create default config in memory
            self.strategy_config = None
    
    def _load_positions(self):
        """Load existing positions for the account."""
        try:
            positions = PaperPosition.objects.filter(
                account=self.account,
                is_active=True
            )
            
            for position in positions:
                self.positions[position.token_symbol] = position
                logger.info(f"[POSITION] Loaded {position.token_symbol}: "
                          f"{position.quantity} @ ${position.average_entry_price_usd}")
            
            logger.info(f"[DATA] Loaded {len(self.positions)} active positions")
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to load positions: {e}")
    
    def _initialize_price_tracking(self):
        """Initialize price tracking for simulated market data."""
        # Start with some base prices for common tokens
        self.current_prices = {
            'WETH': Decimal('2500.00'),
            'USDC': Decimal('1.00'),
            'USDT': Decimal('1.00'),
            'DAI': Decimal('1.00'),
            'WBTC': Decimal('45000.00'),
            'LINK': Decimal('15.00'),
            'UNI': Decimal('6.50'),
            'AAVE': Decimal('95.00'),
            'MATIC': Decimal('0.85'),
            'ARB': Decimal('1.20'),
        }
        
        # Initialize price history
        for symbol, price in self.current_prices.items():
            self.price_history[symbol] = [price]
        
        logger.info(f"[MARKET] Initialized tracking for {len(self.current_prices)} tokens")
    
    def _send_bot_status_update(self, status: str):
        """Send bot status update via WebSocket."""
        try:
            message = {
                'type': 'bot_status',
                'status': status,
                'intel_level': self.intel_level,
                'account_id': str(self.account.account_id),
                'account_name': self.account.name,
                'balance': float(self.account.current_balance_usd),
                'positions': len(self.positions),
                'session_id': str(self.session.session_id) if self.session else None,
                'timestamp': timezone.now().isoformat()
            }
            
            async_to_sync(self.websocket_service.send_bot_update)(
                account_id=str(self.account.account_id),
                update_type='status',
                data=message
            )
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to send status update: {e}")
    
    def run(self):
        """
        Main bot execution loop.
        
        Continuously monitors markets and executes trades based on
        intelligence level and market conditions.
        """
        logger.info("[START] Bot starting main execution loop")
        self.running = True
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        tick_count = 0
        
        try:
            while self.running:
                tick_count += 1
                logger.info(f"\n{'='*60}")
                logger.info(f"[TICK] Market tick #{tick_count}")
                
                # ============================================================
                # UPDATE MARKET PRICES
                # ============================================================
                self._update_market_prices()
                
                # ============================================================
                # ANALYZE MARKETS
                # ============================================================
                opportunities = self._scan_for_opportunities()
                
                # ============================================================
                # MAKE TRADING DECISIONS
                # ============================================================
                if opportunities:
                    self._process_opportunities(opportunities)
                
                # ============================================================
                # UPDATE POSITIONS
                # ============================================================
                self._update_position_values()
                
                # ============================================================
                # CHECK STOP LOSSES / TAKE PROFITS
                # ============================================================
                self._check_exit_conditions()
                
                # ============================================================
                # SEND PERIODIC UPDATES
                # ============================================================
                if tick_count % 5 == 0:  # Every 5 ticks
                    self._send_performance_update()
                
                # ============================================================
                # SLEEP UNTIL NEXT TICK
                # ============================================================
                time.sleep(self.tick_interval)
                
        except KeyboardInterrupt:
            logger.info("[STOP] Received interrupt signal")
        except Exception as e:
            logger.error(f"[ERROR] Bot crashed: {e}", exc_info=True)
        finally:
            self.cleanup()
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"[SIGNAL] Received signal {signum}")
        self.running = False
    
    def _update_market_prices(self):
        """Simulate market price movements."""
        for symbol in self.current_prices:
            old_price = self.current_prices[symbol]
            
            # Determine price movement
            if random.random() < self.trend_probability and len(self.price_history[symbol]) > 1:
                # Continue trend
                last_change = self.price_history[symbol][-1] - self.price_history[symbol][-2]
                change_direction = 1 if last_change >= 0 else -1
            else:
                # Random movement
                change_direction = random.choice([-1, 1])
            
            # Calculate price change (0-5% based on volatility)
            change_percent = Decimal(str(random.uniform(0, float(self.price_volatility))))
            price_change = old_price * change_percent * change_direction
            
            # Update price
            new_price = max(Decimal('0.01'), old_price + price_change)
            self.current_prices[symbol] = new_price
            
            # Update history
            self.price_history[symbol].append(new_price)
            if len(self.price_history[symbol]) > self.max_history_length:
                self.price_history[symbol].pop(0)
            
            # Log significant changes
            if abs(price_change / old_price) > Decimal('0.02'):
                logger.info(f"[PRICE] {symbol}: ${old_price:.2f} -> ${new_price:.2f} "
                          f"({change_percent*100*change_direction:+.2f}%)")
    
    def _scan_for_opportunities(self) -> List[Dict[str, Any]]:
        """
        Scan markets for trading opportunities.
        
        Returns:
            List of potential opportunities
        """
        opportunities = []
        
        for symbol, price in self.current_prices.items():
            # Skip stablecoins
            if symbol in ['USDC', 'USDT', 'DAI']:
                continue
            
            # Get price history
            history = self.price_history.get(symbol, [])
            if len(history) < 3:
                continue
            
            # Simple momentum analysis
            recent_change = (history[-1] - history[-3]) / history[-3]
            
            # Check for opportunities based on intel level
            if self.intel_level <= 3:
                # Ultra cautious: Only strong trends with low volatility
                if abs(recent_change) > Decimal('0.03') and self._calculate_volatility(symbol) < Decimal('0.02'):
                    opportunities.append({
                        'symbol': symbol,
                        'price': price,
                        'signal': 'BUY' if recent_change > 0 else 'SELL',
                        'strength': float(abs(recent_change) * 100),
                        'reason': 'Strong trend with low volatility'
                    })
            elif self.intel_level <= 6:
                # Balanced: Moderate trends
                if abs(recent_change) > Decimal('0.02'):
                    opportunities.append({
                        'symbol': symbol,
                        'price': price,
                        'signal': 'BUY' if recent_change > 0 else 'SELL',
                        'strength': float(abs(recent_change) * 100),
                        'reason': 'Moderate trend detected'
                    })
            else:
                # Aggressive: Any movement
                if abs(recent_change) > Decimal('0.01'):
                    opportunities.append({
                        'symbol': symbol,
                        'price': price,
                        'signal': 'BUY' if recent_change > 0 else 'SELL',
                        'strength': float(abs(recent_change) * 100),
                        'reason': 'Market movement detected'
                    })
        
        return opportunities
    
    def _calculate_volatility(self, symbol: str) -> Decimal:
        """Calculate volatility for a symbol."""
        history = self.price_history.get(symbol, [])
        if len(history) < 2:
            return Decimal('0')
        
        # Simple volatility: average of absolute changes
        changes = []
        for i in range(1, len(history)):
            change = abs((history[i] - history[i-1]) / history[i-1])
            changes.append(change)
        
        return sum(changes) / len(changes) if changes else Decimal('0')
    
    def _process_opportunities(self, opportunities: List[Dict[str, Any]]):
        """Process trading opportunities and execute trades."""
        # Check if we can trade (respect minimum interval)
        if self.last_trade_time:
            time_since_last = (timezone.now() - self.last_trade_time).seconds
            if time_since_last < self.min_trade_interval:
                logger.info(f"[WAIT] Waiting {self.min_trade_interval - time_since_last}s before next trade")
                return
        
        # Sort opportunities by strength
        opportunities.sort(key=lambda x: x['strength'], reverse=True)
        
        # Process top opportunity
        for opp in opportunities[:1]:  # Only take best opportunity
            self._execute_opportunity(opp)
            break
    
    def _execute_opportunity(self, opportunity: Dict[str, Any]):
        """Execute a trading opportunity."""
        symbol = opportunity['symbol']
        signal = opportunity['signal']
        price = opportunity['price']
        
        try:
            # Log thought process
            self._log_thought(
                f"Analyzing {symbol} opportunity: {signal} signal with "
                f"{opportunity['strength']:.1f}% strength. {opportunity['reason']}",
                confidence=50 + opportunity['strength'],
                decision_type='ANALYSIS'
            )
            
            # Determine position size based on intel level
            max_position_pct = 5 + (self.intel_level * 2)  # 5-25%
            position_size_pct = min(max_position_pct, opportunity['strength'])
            position_size_usd = self.account.current_balance_usd * Decimal(position_size_pct) / 100
            
            # Check if we have an existing position
            existing_position = self.positions.get(symbol)
            
            if signal == 'BUY':
                if existing_position:
                    # Already have position
                    self._log_thought(
                        f"Already holding {symbol} position. Skipping additional buy.",
                        confidence=80,
                        decision_type='SKIP'
                    )
                    return
                
                # Execute buy
                self._execute_buy(symbol, price, position_size_usd)
                
            elif signal == 'SELL':
                if not existing_position:
                    # No position to sell
                    self._log_thought(
                        f"No {symbol} position to sell. Skipping.",
                        confidence=80,
                        decision_type='SKIP'
                    )
                    return
                
                # Execute sell
                self._execute_sell(symbol, price, existing_position)
                
        except Exception as e:
            logger.error(f"[ERROR] Failed to execute opportunity: {e}")
    
    def _execute_buy(self, symbol: str, price: Decimal, amount_usd: Decimal):
        """Execute a buy trade."""
        try:
            # Calculate quantities
            quantity = amount_usd / price
            gas_cost = Decimal('5.00')  # Simulated gas cost
            
            # Check balance
            if amount_usd + gas_cost > self.account.current_balance_usd:
                logger.warning(f"[INSUFFICIENT] Not enough balance for {symbol} buy")
                return
            
            # Create trade
            trade = PaperTrade.objects.create(
                account=self.account,
                session=self.session,
                trade_type='buy',
                token_in_address='0x' + '0' * 40,  # Mock ETH address
                token_in_symbol='ETH',
                token_out_address='0x' + '1' * 40,  # Mock token address
                token_out_symbol=symbol,
                amount_in=amount_usd,
                amount_in_usd=amount_usd,
                expected_amount_out=quantity,
                actual_amount_out=quantity,
                simulated_gas_price_gwei=Decimal('30'),
                simulated_gas_used=150000,
                simulated_gas_cost_usd=gas_cost,
                simulated_slippage_percent=Decimal('0.5'),
                status='completed',
                executed_at=timezone.now(),
                execution_time_ms=random.randint(100, 500),
                mock_tx_hash='0x' + os.urandom(32).hex(),
                strategy_name=f'Intel_{self.intel_level}'
            )
            
            # Create or update position
            position, created = PaperPosition.objects.get_or_create(
                account=self.account,
                token_symbol=symbol,
                defaults={
                    'token_address': '0x' + '1' * 40,
                    'quantity': quantity,
                    'average_entry_price_usd': price,
                    'total_invested_usd': amount_usd,
                    'current_price_usd': price,
                    'current_value_usd': amount_usd,
                }
            )
            
            if not created:
                # Update existing position (averaging)
                total_quantity = position.quantity + quantity
                total_invested = position.total_invested_usd + amount_usd
                position.quantity = total_quantity
                position.average_entry_price_usd = total_invested / total_quantity
                position.total_invested_usd = total_invested
                position.save()
            
            # Update account balance
            self.account.current_balance_usd -= (amount_usd + gas_cost)
            self.account.total_fees_paid_usd += gas_cost
            self.account.total_trades += 1
            self.account.successful_trades += 1
            self.account.save()
            
            # Update local tracking
            self.positions[symbol] = position
            self.last_trade_time = timezone.now()
            self.trades_executed += 1
            self.successful_trades += 1
            
            # Log success
            self._log_thought(
                f"Successfully bought {quantity:.4f} {symbol} at ${price:.2f} "
                f"for ${amount_usd:.2f}. Gas cost: ${gas_cost:.2f}",
                confidence=90,
                decision_type='EXECUTE'
            )
            
            # Send WebSocket update
            self._send_trade_update(trade)
            
            logger.info(f"[TRADE] BUY {quantity:.4f} {symbol} @ ${price:.2f}")
            
        except Exception as e:
            logger.error(f"[ERROR] Buy execution failed: {e}")
            self.failed_trades += 1
    
    def _execute_sell(self, symbol: str, price: Decimal, position: PaperPosition):
        """Execute a sell trade."""
        try:
            # Calculate values
            sell_value = position.quantity * price
            pnl = sell_value - position.total_invested_usd
            gas_cost = Decimal('5.00')
            
            # Create trade
            trade = PaperTrade.objects.create(
                account=self.account,
                session=self.session,
                trade_type='sell',
                token_in_address='0x' + '1' * 40,
                token_in_symbol=symbol,
                token_out_address='0x' + '0' * 40,
                token_out_symbol='ETH',
                amount_in=position.quantity,
                amount_in_usd=sell_value,
                expected_amount_out=sell_value,
                actual_amount_out=sell_value,
                simulated_gas_price_gwei=Decimal('30'),
                simulated_gas_used=150000,
                simulated_gas_cost_usd=gas_cost,
                simulated_slippage_percent=Decimal('0.5'),
                status='completed',
                executed_at=timezone.now(),
                execution_time_ms=random.randint(100, 500),
                mock_tx_hash='0x' + os.urandom(32).hex(),
                strategy_name=f'Intel_{self.intel_level}',
                pnl_usd=pnl
            )
            
            # Update position
            position.realized_pnl_usd += pnl
            position.is_active = False
            position.closed_at = timezone.now()
            position.save()
            
            # Update account
            self.account.current_balance_usd += (sell_value - gas_cost)
            self.account.total_pnl_usd += pnl
            self.account.total_fees_paid_usd += gas_cost
            self.account.total_trades += 1
            self.account.successful_trades += 1
            self.account.save()
            
            # Update tracking
            del self.positions[symbol]
            self.last_trade_time = timezone.now()
            self.trades_executed += 1
            self.successful_trades += 1
            self.total_pnl += pnl
            
            # Log success
            self._log_thought(
                f"Successfully sold {position.quantity:.4f} {symbol} at ${price:.2f} "
                f"for ${sell_value:.2f}. PnL: ${pnl:+.2f} "
                f"({'profit' if pnl > 0 else 'loss'})",
                confidence=90,
                decision_type='EXECUTE'
            )
            
            # Send update
            self._send_trade_update(trade)
            
            logger.info(f"[TRADE] SELL {position.quantity:.4f} {symbol} @ ${price:.2f} "
                       f"(PnL: ${pnl:+.2f})")
            
        except Exception as e:
            logger.error(f"[ERROR] Sell execution failed: {e}")
            self.failed_trades += 1
    
    def _update_position_values(self):
        """Update current values of all positions."""
        for symbol, position in self.positions.items():
            if symbol in self.current_prices:
                old_value = position.current_value_usd
                new_price = self.current_prices[symbol]
                new_value = position.quantity * new_price
                unrealized_pnl = new_value - position.total_invested_usd
                
                # Update position
                position.current_price_usd = new_price
                position.current_value_usd = new_value
                position.unrealized_pnl_usd = unrealized_pnl
                position.save()
                
                # Log significant changes
                if abs(new_value - old_value) > Decimal('50'):
                    logger.info(f"[POSITION] {symbol}: ${old_value:.2f} -> ${new_value:.2f} "
                              f"(Unrealized PnL: ${unrealized_pnl:+.2f})")
    
    def _check_exit_conditions(self):
        """Check stop loss and take profit conditions."""
        if not self.strategy_config:
            return
        
        config = self.strategy_config.config
        
        for symbol, position in list(self.positions.items()):
            current_price = self.current_prices.get(symbol)
            if not current_price:
                continue
            
            # Calculate percentage change
            pct_change = ((current_price - position.average_entry_price_usd) / 
                         position.average_entry_price_usd) * 100
            
            # Check stop loss
            if config.get('stop_loss_enabled') and pct_change <= -config.get('stop_loss_percent', 5):
                logger.info(f"[STOP LOSS] Triggered for {symbol} at {pct_change:.2f}%")
                self._log_thought(
                    f"Stop loss triggered for {symbol}. "
                    f"Price dropped {abs(pct_change):.2f}% from entry.",
                    confidence=100,
                    decision_type='RISK_MANAGEMENT'
                )
                self._execute_sell(symbol, current_price, position)
            
            # Check take profit
            elif config.get('take_profit_enabled') and pct_change >= config.get('take_profit_percent', 10):
                logger.info(f"[TAKE PROFIT] Triggered for {symbol} at {pct_change:.2f}%")
                self._log_thought(
                    f"Take profit triggered for {symbol}. "
                    f"Price increased {pct_change:.2f}% from entry.",
                    confidence=100,
                    decision_type='PROFIT_TAKING'
                )
                self._execute_sell(symbol, current_price, position)
    
    def _log_thought(self, thought: str, confidence: float = 50.0, decision_type: str = 'ANALYSIS'):
        """Log AI thought process."""
        try:
            PaperAIThoughtLog.objects.create(
                session=self.session,
                thought_type=decision_type,
                thought_content=thought,
                confidence_level=Decimal(str(confidence)),
                intel_level_used=self.intel_level,
                token_context={'prices': {k: str(v) for k, v in self.current_prices.items()}}
            )
            
            # Also send via WebSocket
            async_to_sync(self.websocket_service.send_bot_update)(
                account_id=str(self.account.account_id),
                update_type='thought',
                data={
                    'thought': thought,
                    'confidence': confidence,
                    'type': decision_type,
                    'intel_level': self.intel_level,
                    'timestamp': timezone.now().isoformat()
                }
            )
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to log thought: {e}")
    
    def _send_trade_update(self, trade: PaperTrade):
        """Send trade update via WebSocket."""
        try:
            async_to_sync(self.websocket_service.send_trade_update)(
                account_id=str(self.account.account_id),
                trade_data={
                    'trade_id': str(trade.trade_id),
                    'type': trade.trade_type,
                    'symbol': trade.token_out_symbol if trade.trade_type == 'buy' else trade.token_in_symbol,
                    'amount': float(trade.amount_in_usd),
                    'price': float(self.current_prices.get(
                        trade.token_out_symbol if trade.trade_type == 'buy' else trade.token_in_symbol,
                        0
                    )),
                    'pnl': float(trade.pnl_usd) if trade.pnl_usd else 0,
                    'timestamp': trade.executed_at.isoformat() if trade.executed_at else timezone.now().isoformat()
                }
            )
        except Exception as e:
            logger.error(f"[ERROR] Failed to send trade update: {e}")
    
    def _send_performance_update(self):
        """Send periodic performance update."""
        try:
            # Calculate metrics
            total_value = self.account.current_balance_usd
            for position in self.positions.values():
                total_value += position.current_value_usd
            
            metrics = {
                'account_balance': float(self.account.current_balance_usd),
                'total_value': float(total_value),
                'total_pnl': float(self.account.total_pnl_usd),
                'total_trades': self.trades_executed,
                'successful_trades': self.successful_trades,
                'failed_trades': self.failed_trades,
                'win_rate': (self.successful_trades / self.trades_executed * 100) if self.trades_executed > 0 else 0,
                'active_positions': len(self.positions),
                'intel_level': self.intel_level,
                'session_id': str(self.session.session_id) if self.session else None,
                'timestamp': timezone.now().isoformat()
            }
            
            # Send via WebSocket
            async_to_sync(self.websocket_service.send_bot_update)(
                account_id=str(self.account.account_id),
                update_type='performance',
                data=metrics
            )
            
            # Log performance
            logger.info(f"[PERFORMANCE] Balance: ${metrics['account_balance']:.2f}, "
                       f"Total Value: ${metrics['total_value']:.2f}, "
                       f"PnL: ${metrics['total_pnl']:+.2f}, "
                       f"Win Rate: {metrics['win_rate']:.1f}%")
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to send performance update: {e}")
    
    def _calculate_recent_success_rate(self) -> float:
        """Calculate recent success rate."""
        if self.trades_executed == 0:
            return 0.0
        return (self.successful_trades / self.trades_executed) * 100
    
    def cleanup(self):
        """Clean up resources and save final state."""
        try:
            logger.info("[CLEANUP] Shutting down bot...")
            
            # ================================================================
            # CLOSE TRADING SESSION
            # ================================================================
            if self.session:
                self.session.ended_at = timezone.now()
                self.session.final_balance_usd = self.account.current_balance_usd
                self.session.total_pnl_usd = self.account.total_pnl_usd
                self.session.is_active = False
                self.session.save()
                logger.info(f"[SESSION] Closed session {self.session.session_id}")
            
            # ================================================================
            # SAVE PERFORMANCE METRICS
            # ================================================================
            if self.session and self.trades_executed > 0:
                PaperPerformanceMetrics.objects.create(
                    session=self.session,
                    period_start=self.session.started_at,
                    period_end=timezone.now(),
                    total_trades=self.trades_executed,
                    winning_trades=self.successful_trades,
                    losing_trades=self.failed_trades,
                    win_rate=Decimal(str(self._calculate_recent_success_rate())),
                    total_pnl_usd=self.total_pnl,
                    total_pnl_percent=Decimal(str((self.total_pnl / self.account.initial_balance_usd) * 100))
                    if self.account.initial_balance_usd > 0 else Decimal('0')
                )
                logger.info("[METRICS] Saved performance metrics")
            
            # ================================================================
            # LOG FINAL THOUGHT
            # ================================================================
            self._log_thought(
                f"Bot shutting down. Intel Level: {self.intel_level}. "
                f"Session summary: Trades: {self.trades_executed}, "
                f"Success rate: {self._calculate_recent_success_rate():.1f}%, "
                f"Total P&L: ${self.total_pnl:.2f}",
                confidence=100,
                decision_type="SYSTEM"
            )
            
            # ================================================================
            # SEND SHUTDOWN NOTIFICATION
            # ================================================================
            self._send_bot_status_update('stopped')
            
            logger.info("[OK] Cleanup completed")
            
        except Exception as e:
            logger.error(f"[ERROR] Cleanup error: {e}", exc_info=True)


def main():
    """
    Main entry point for the enhanced paper trading bot.
    
    Can be run directly or via Django management command.
    """
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Enhanced Paper Trading Bot with Intel Slider System'
    )
    parser.add_argument(
        '--account-id',
        type=str,  # Changed to str to handle UUIDs
        default='1',
        help='Paper trading account ID to use (can be UUID or numeric)'
    )
    parser.add_argument(
        '--intel-level',
        type=int,
        default=5,
        choices=range(1, 11),
        help='Intelligence level (1-10): 1-3=Cautious, 4-6=Balanced, 7-9=Aggressive, 10=Autonomous'
    )
    
    args = parser.parse_args()
    
    # Create and run bot
    bot = EnhancedPaperTradingBot(
        account_id=args.account_id,
        intel_level=args.intel_level
    )
    
    if bot.initialize():
        logger.info("[OK] Bot initialized successfully")
        bot.run()
    else:
        logger.error("[ERROR] Bot initialization failed")
        sys.exit(1)


if __name__ == "__main__":
    main()