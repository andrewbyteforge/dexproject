"""
Enhanced Paper Trading Bot with Intel Slider System

This is the main paper trading bot that integrates the Intel Slider (1-10) system
for intelligent decision making. It replaces multiple bot implementations with
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
from typing import Dict, Any, Optional, List, Tuple
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
# SERVICE IMPORTS
# ============================================================================
from paper_trading.services.websocket_service import WebSocketNotificationService

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
    
    def __init__(self, account_id: int, intel_level: int = 5):
        """
        Initialize the enhanced paper trading bot.
        
        Args:
            account_id: ID of the paper trading account to use
            intel_level: Intelligence level (1-10) controlling bot behavior
                1-3: Ultra cautious
                4-6: Balanced
                7-9: Aggressive
                10: Fully autonomous with ML
        """
        # ====================================================================
        # CORE CONFIGURATION
        # ====================================================================
        self.account_id = account_id
        self.intel_level = intel_level
        self.account = None
        self.session = None
        self.running = False
        
        # ====================================================================
        # INTELLIGENCE SYSTEM
        # ====================================================================
        self.intelligence_engine = None  # Will be initialized in initialize()
        self.websocket_service = WebSocketNotificationService()
        
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
            self.session = PaperTradingSession.objects.create(
                account=self.account,
                name=f"Intel_{self.intel_level}_Session_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                status='RUNNING',
                starting_balance_usd=self.account.current_balance_usd,
                session_type='ENHANCED_BOT',
                intel_level=self.intel_level  # Store intel level with session
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
            # INITIALIZE PRICE HISTORY
            # ================================================================
            self._initialize_price_history()
            
            # ================================================================
            # SEND INITIALIZATION NOTIFICATION
            # ================================================================
            self._send_bot_status_update('initialized')
            
            # ================================================================
            # LOG INITIAL THOUGHT
            # ================================================================
            self._log_thought(
                action="STARTUP",
                reasoning=f"Bot initialized with Intel Level {self.intel_level}. "
                         f"Strategy: {self.intelligence_engine.config.name}. "
                         f"Risk tolerance: {self.intelligence_engine.config.risk_tolerance}%. "
                         f"Starting balance: ${self.account.current_balance_usd:.2f}",
                confidence=100,
                decision_type="SYSTEM"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] Initialization failed: {e}", exc_info=True)
            return False
    
    def _setup_strategy_configuration(self):
        """
        Set up strategy configuration based on intel level.
        
        Creates or updates the strategy configuration to match
        the selected intelligence level settings.
        """
        config = self.intelligence_engine.config
        
        self.strategy_config, created = PaperStrategyConfiguration.objects.update_or_create(
            account=self.account,
            name=f"Intel_Level_{self.intel_level}",
            defaults={
                'is_active': True,
                'trading_mode': self._get_trading_mode(),
                'use_fast_lane': self.intel_level >= 7,  # Fast lane for aggressive
                'use_smart_lane': True,  # Always available
                'max_position_size_percent': config.max_position_percent,
                'stop_loss_percent': Decimal('5'),
                'take_profit_percent': Decimal('10'),
                'max_daily_trades': self._get_max_daily_trades(),
                'confidence_threshold': config.min_confidence_required,
                'intel_level': self.intel_level,
                'metadata': {
                    'risk_tolerance': float(config.risk_tolerance),
                    'gas_aggressiveness': config.gas_aggressiveness,
                    'use_mev_protection': config.use_mev_protection
                }
            }
        )
        
        if created:
            logger.info(f"[CONFIG] Created new strategy: {self.strategy_config.name}")
        else:
            logger.info(f"[CONFIG] Updated strategy: {self.strategy_config.name}")
    
    def _get_trading_mode(self) -> str:
        """Get trading mode based on intel level."""
        if self.intel_level <= 3:
            return 'CONSERVATIVE'
        elif self.intel_level <= 6:
            return 'MODERATE'
        else:
            return 'AGGRESSIVE'
    
    def _get_max_daily_trades(self) -> int:
        """Get max daily trades based on intel level."""
        if self.intel_level <= 3:
            return 10
        elif self.intel_level <= 6:
            return 25
        elif self.intel_level <= 9:
            return 50
        else:
            return 100  # Autonomous
    
    def _load_positions(self):
        """
        Load existing open positions for the account.
        
        Populates the positions dictionary with current open positions.
        """
        open_positions = PaperPosition.objects.filter(
            account=self.account,
            is_open=True
        )
        
        for position in open_positions:
            self.positions[position.token_symbol] = position
            logger.info(f"[POSITION] Loaded: {position.token_symbol} - {position.quantity} @ ${position.average_entry_price_usd}")
    
    def _initialize_price_history(self):
        """
        Initialize price history with simulated data.
        
        Creates initial price data for tokens we'll be trading.
        """
        # Simulated tokens for paper trading
        tokens = ['TEST1', 'TEST2', 'TEST3']
        
        for token in tokens:
            # Generate random starting price between $10 and $1000
            base_price = Decimal(str(random.uniform(10, 1000)))
            
            # Create price history with some variance
            self.price_history[token] = []
            for i in range(10):
                variance = Decimal(str(random.uniform(-0.05, 0.05)))
                price = base_price * (Decimal('1') + variance)
                self.price_history[token].append(price)
            
            logger.info(f"[PRICE] Initialized {token} at ${self.price_history[token][-1]:.2f}")
    
    def run(self):
        """
        Main bot execution loop.
        
        Runs continuously until stopped, checking markets and making
        trading decisions based on the intelligence level.
        """
        logger.info("[START] Bot starting main execution loop...")
        
        # ====================================================================
        # SETUP SIGNAL HANDLERS
        # ====================================================================
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        
        self.running = True
        
        try:
            while self.running:
                # ============================================================
                # MARKET ANALYSIS TICK
                # ============================================================
                self._tick()
                
                # ============================================================
                # SLEEP BETWEEN TICKS
                # ============================================================
                time.sleep(self.tick_interval)
                
        except Exception as e:
            logger.error(f"[ERROR] Bot crashed: {e}", exc_info=True)
        finally:
            # ============================================================
            # CLEANUP ON EXIT
            # ============================================================
            self._cleanup()
    
    def _tick(self):
        """
        Single market analysis tick.
        
        This method:
        1. Updates market prices
        2. Analyzes each token
        3. Makes trading decisions
        4. Executes trades
        5. Updates performance metrics
        """
        try:
            # ================================================================
            # UPDATE SIMULATED PRICES
            # ================================================================
            self._update_prices()
            
            # ================================================================
            # ANALYZE EACH TOKEN
            # ================================================================
            for token_symbol in self.price_history.keys():
                self._analyze_and_trade(token_symbol)
            
            # ================================================================
            # UPDATE PERFORMANCE METRICS
            # ================================================================
            self._update_performance_metrics()
            
            # ================================================================
            # SEND STATUS UPDATE
            # ================================================================
            if self.trades_executed % 5 == 0:  # Every 5 trades
                self._send_bot_status_update('running')
            
        except Exception as e:
            logger.error(f"[ERROR] Tick error: {e}", exc_info=True)
    
    async def _analyze_and_trade(self, token_symbol: str):
        """
        Analyze a token and make trading decision.
        
        Uses the intelligence engine to analyze market conditions
        and decide whether to trade.
        
        Args:
            token_symbol: Symbol of token to analyze
        """
        try:
            current_price = self.price_history[token_symbol][-1]
            
            # ================================================================
            # PREPARE TOKEN DATA
            # ================================================================
            token_data = {
                'address': '0x' + 'a' * 40,  # Simulated address
                'symbol': token_symbol,
                'liquidity_usd': Decimal('500000'),  # Simulated liquidity
                'volume_24h': Decimal('100000')  # Simulated volume
            }
            
            # ================================================================
            # ANALYZE MARKET USING INTELLIGENCE ENGINE
            # ================================================================
            market_context = await self.intelligence_engine.analyze_market(
                token_address=token_data['address'],
                trade_size_usd=self.account.current_balance_usd * Decimal('0.1'),
                liquidity_usd=token_data['liquidity_usd'],
                volume_24h=token_data['volume_24h'],
                recent_failures=self.failed_trades,
                success_rate_1h=self._calculate_recent_success_rate()
            )
            
            # ================================================================
            # MAKE TRADING DECISION
            # ================================================================
            existing_positions = [
                {
                    'token_symbol': pos.token_symbol,
                    'quantity': float(pos.quantity),
                    'invested_usd': float(pos.total_invested_usd)
                }
                for pos in self.positions.values()
            ]
            
            decision = await self.intelligence_engine.make_decision(
                market_context=market_context,
                account_balance=self.account.current_balance_usd,
                existing_positions=existing_positions,
                token_address=token_data['address'],
                token_symbol=token_symbol
            )
            
            # ================================================================
            # LOG THOUGHT PROCESS
            # ================================================================
            thought_log = self.intelligence_engine.generate_thought_log(decision)
            self._log_thought(
                action=decision.action,
                reasoning=thought_log,
                confidence=float(decision.overall_confidence),
                decision_type="TRADE_DECISION",
                metadata={
                    'token': token_symbol,
                    'intel_level': self.intel_level,
                    'risk_score': float(decision.risk_score),
                    'opportunity_score': float(decision.opportunity_score)
                }
            )
            
            # ================================================================
            # EXECUTE TRADE IF DECIDED
            # ================================================================
            if decision.action in ['BUY', 'SELL']:
                # Check minimum trade interval
                if self._can_trade():
                    self._execute_trade(decision, token_symbol, current_price)
            
            # Store decision for tracking
            self.last_decisions[token_symbol] = decision
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to analyze {token_symbol}: {e}", exc_info=True)
    
    def _execute_trade(self, decision: TradingDecision, token_symbol: str, current_price: Decimal):
        """
        Execute a paper trade based on the decision.
        
        Args:
            decision: Trading decision from intelligence engine
            token_symbol: Token to trade
            current_price: Current token price
        """
        try:
            # ================================================================
            # CREATE TRADE RECORD
            # ================================================================
            trade = PaperTrade.objects.create(
                account=self.account,
                session=self.session,
                trade_type=decision.action,
                token_in_address='0x' + '0' * 40 if decision.action == 'BUY' else decision.token_address,
                token_in_symbol='USDC' if decision.action == 'BUY' else token_symbol,
                token_out_address=decision.token_address if decision.action == 'BUY' else '0x' + '0' * 40,
                token_out_symbol=token_symbol if decision.action == 'BUY' else 'USDC',
                amount_in=decision.position_size_usd,
                amount_out=decision.position_size_usd / current_price if decision.action == 'BUY' else decision.position_size_usd,
                amount_in_usd=decision.position_size_usd,
                amount_out_usd=decision.position_size_usd,
                strategy_name=f"INTEL_{self.intel_level}",
                strategy_lane=decision.execution_mode,
                gas_price_gwei=decision.max_gas_price_gwei,
                mev_protection_used=decision.use_private_relay,
                slippage_percent=Decimal('1'),  # Simulated
                status='SUCCESS',  # Simulated success
                execution_time_ms=int(decision.processing_time_ms),
                metadata={
                    'intel_level': self.intel_level,
                    'confidence': float(decision.overall_confidence),
                    'risk_score': float(decision.risk_score)
                }
            )
            
            # ================================================================
            # UPDATE POSITION
            # ================================================================
            if decision.action == 'BUY':
                self._open_or_add_position(token_symbol, decision, current_price)
            else:
                self._close_or_reduce_position(token_symbol, decision, current_price)
            
            # ================================================================
            # UPDATE METRICS
            # ================================================================
            self.trades_executed += 1
            self.successful_trades += 1  # Simulated success
            self.last_trade_time = datetime.now()
            
            # ================================================================
            # SEND WEBSOCKET NOTIFICATION
            # ================================================================
            self._send_trade_notification(trade, decision)
            
            logger.info(
                f"[TRADE] Executed: {decision.action} {token_symbol} "
                f"Size: ${decision.position_size_usd:.2f} "
                f"Intel: {self.intel_level} "
                f"Confidence: {decision.overall_confidence:.1f}%"
            )
            
        except Exception as e:
            logger.error(f"[ERROR] Trade execution failed: {e}", exc_info=True)
            self.failed_trades += 1
    
    def _can_trade(self) -> bool:
        """Check if enough time has passed since last trade."""
        if not self.last_trade_time:
            return True
        
        time_since_last = (datetime.now() - self.last_trade_time).seconds
        return time_since_last >= self.min_trade_interval
    
    def _open_or_add_position(self, token_symbol: str, decision: TradingDecision, price: Decimal):
        """Open new position or add to existing."""
        quantity = decision.position_size_usd / price
        
        if token_symbol in self.positions:
            # Add to existing position
            position = self.positions[token_symbol]
            position.quantity += quantity
            position.total_invested_usd += decision.position_size_usd
            position.average_entry_price_usd = position.total_invested_usd / position.quantity
            position.save()
        else:
            # Create new position
            position = PaperPosition.objects.create(
                account=self.account,
                token_address=decision.token_address,
                token_symbol=token_symbol,
                quantity=quantity,
                entry_price_usd=price,
                average_entry_price_usd=price,
                total_invested_usd=decision.position_size_usd,
                current_price_usd=price,
                current_value_usd=decision.position_size_usd,
                is_open=True
            )
            self.positions[token_symbol] = position
    
    def _close_or_reduce_position(self, token_symbol: str, decision: TradingDecision, price: Decimal):
        """Close or reduce existing position."""
        if token_symbol not in self.positions:
            logger.warning(f"[POSITION] No position to sell for {token_symbol}")
            return
        
        position = self.positions[token_symbol]
        
        # Calculate P&L
        exit_value = position.quantity * price
        pnl = exit_value - position.total_invested_usd
        
        # Update position
        position.realized_pnl_usd = pnl
        position.is_open = False
        position.closed_at = timezone.now()
        position.save()
        
        # Update total P&L
        self.total_pnl += pnl
        
        # Remove from active positions
        del self.positions[token_symbol]
        
        logger.info(f"[POSITION] Closed {token_symbol}: P&L ${pnl:.2f}")
    
    def _update_prices(self):
        """
        Update simulated market prices.
        
        Simulates price movements for paper trading.
        """
        for token_symbol in self.price_history.keys():
            prices = self.price_history[token_symbol]
            last_price = prices[-1]
            
            # Determine trend
            if len(prices) >= 2:
                trend = 1 if prices[-1] > prices[-2] else -1
            else:
                trend = random.choice([-1, 1])
            
            # Continue trend with probability
            if random.random() < self.trend_probability:
                change_direction = trend
            else:
                change_direction = -trend
            
            # Calculate price change
            change_percent = Decimal(str(random.uniform(0, float(self.price_volatility))))
            change_amount = last_price * change_percent * change_direction
            
            # New price
            new_price = max(last_price + change_amount, Decimal('0.01'))
            
            # Update history
            prices.append(new_price)
            if len(prices) > self.max_history_length:
                prices.pop(0)
    
    def _calculate_recent_success_rate(self) -> float:
        """Calculate recent trading success rate."""
        if self.trades_executed == 0:
            return 50.0
        
        return (self.successful_trades / self.trades_executed) * 100
    
    def _update_performance_metrics(self):
        """Update and save performance metrics."""
        try:
            metrics, created = PaperPerformanceMetrics.objects.update_or_create(
                account=self.account,
                session=self.session,
                defaults={
                    'total_trades': self.trades_executed,
                    'winning_trades': self.successful_trades,
                    'losing_trades': self.failed_trades,
                    'win_rate': Decimal(str(self._calculate_recent_success_rate())),
                    'total_pnl_usd': self.total_pnl,
                    'metadata': {
                        'intel_level': self.intel_level,
                        'session_id': str(self.session.session_id)
                    }
                }
            )
            
            # Send performance update via WebSocket
            if self.trades_executed % 10 == 0:  # Every 10 trades
                self._send_performance_update(metrics)
                
        except Exception as e:
            logger.error(f"[ERROR] Failed to update metrics: {e}", exc_info=True)
    
    def _log_thought(self, action: str, reasoning: str, confidence: float,
                     decision_type: str = "ANALYSIS", metadata: Optional[Dict] = None):
        """
        Log AI thought process to database and WebSocket.
        
        Args:
            action: Action taken or considered
            reasoning: Detailed reasoning
            confidence: Confidence percentage (0-100)
            decision_type: Type of decision
            metadata: Additional metadata
        """
        try:
            # ================================================================
            # CREATE DATABASE RECORD
            # ================================================================
            thought_log = PaperAIThoughtLog.objects.create(
                account=self.account,
                session=self.session,
                decision_type=decision_type,
                action=action,
                confidence_percent=Decimal(str(confidence)),
                primary_reasoning=reasoning[:1000],  # Limit to 1000 chars
                metadata=metadata or {},
                intel_level=self.intel_level
            )
            
            # ================================================================
            # SEND WEBSOCKET NOTIFICATION
            # ================================================================
            self.websocket_service.send_thought_log(
                user_id=self.account.user.id,
                thought_data={
                    'id': str(thought_log.thought_id),
                    'action': action,
                    'reasoning': reasoning,
                    'confidence_score': confidence,
                    'decision_type': decision_type,
                    'intel_level': self.intel_level,
                    'timestamp': thought_log.created_at.isoformat()
                }
            )
            
            logger.debug(f"[THOUGHT] Logged: {action} ({confidence:.1f}% confidence)")
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to log thought: {e}", exc_info=True)
    
    def _send_trade_notification(self, trade: PaperTrade, decision: TradingDecision):
        """Send trade notification via WebSocket."""
        try:
            self.websocket_service.send_trade_update(
                user_id=self.account.user.id,
                trade_data={
                    'id': str(trade.trade_id),
                    'trade_type': trade.trade_type,
                    'token_in': trade.token_in_symbol,
                    'token_out': trade.token_out_symbol,
                    'amount_usd': float(trade.amount_in_usd),
                    'status': trade.status,
                    'intel_level': self.intel_level,
                    'confidence': float(decision.overall_confidence),
                    'risk_score': float(decision.risk_score),
                    'timestamp': trade.created_at.isoformat()
                }
            )
        except Exception as e:
            logger.error(f"[ERROR] Failed to send trade notification: {e}")
    
    def _send_bot_status_update(self, status: str):
        """Send bot status update via WebSocket."""
        try:
            self.websocket_service.send_bot_status_update(
                user_id=self.account.user.id,
                status_data={
                    'status': status,
                    'intel_level': self.intel_level,
                    'trades_executed': self.trades_executed,
                    'success_rate': self._calculate_recent_success_rate(),
                    'total_pnl': float(self.total_pnl),
                    'session_id': str(self.session.session_id) if self.session else None
                }
            )
        except Exception as e:
            logger.error(f"[ERROR] Failed to send status update: {e}")
    
    def _send_performance_update(self, metrics: PaperPerformanceMetrics):
        """Send performance update via WebSocket."""
        try:
            self.websocket_service.send_performance_update(
                user_id=self.account.user.id,
                performance_data={
                    'total_trades': metrics.total_trades,
                    'win_rate': float(metrics.win_rate),
                    'total_pnl': float(metrics.total_pnl_usd),
                    'winning_trades': metrics.winning_trades,
                    'losing_trades': metrics.losing_trades,
                    'intel_level': self.intel_level
                }
            )
        except Exception as e:
            logger.error(f"[ERROR] Failed to send performance update: {e}")
    
    def _handle_shutdown(self, signum, frame):
        """
        Handle shutdown signals gracefully.
        
        Args:
            signum: Signal number
            frame: Current stack frame
        """
        logger.info("\n[STOP] Shutdown signal received...")
        self.running = False
    
    def _cleanup(self):
        """
        Cleanup resources and close session.
        
        This method:
        1. Updates final session status
        2. Saves final position values
        3. Logs final metrics
        4. Sends shutdown notification
        """
        try:
            # ================================================================
            # UPDATE SESSION STATUS
            # ================================================================
            if self.session:
                self.session.status = 'STOPPED'
                self.session.ended_at = timezone.now()
                self.session.ending_balance_usd = self.account.current_balance_usd
                self.session.save()
                logger.info(f"[SESSION] Session {self.session.session_id} ended")
            
            # ================================================================
            # UPDATE FINAL POSITION VALUES
            # ================================================================
            for token_symbol, position in self.positions.items():
                try:
                    if token_symbol in self.price_history:
                        current_price = self.price_history[token_symbol][-1]
                        position.current_price_usd = current_price
                        position.current_value_usd = position.quantity * current_price
                        position.unrealized_pnl_usd = (
                            position.current_value_usd - position.total_invested_usd
                        )
                        position.save()
                        logger.info(
                            f"[POSITION] Final update for {token_symbol}: "
                            f"${current_price:.2f}"
                        )
                except Exception as e:
                    logger.error(f"[ERROR] Failed to update position {token_symbol}: {e}")
            
            # ================================================================
            # LOG FINAL THOUGHT
            # ================================================================
            self._log_thought(
                action="SHUTDOWN",
                reasoning=f"Bot shutting down. Intel Level: {self.intel_level}. "
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
        type=int,
        default=1,
        help='Paper trading account ID to use'
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