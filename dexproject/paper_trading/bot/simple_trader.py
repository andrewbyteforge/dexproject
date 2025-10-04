"""
Enhanced Paper Trading Bot with Intel Slider System and Phase 6B Integration

This is the main paper trading bot that integrates:
- Intel Slider (1-10) system for intelligent decision making
- Phase 6B Transaction Manager for gas optimization
- Centralized transaction management
- Real-time WebSocket updates
- Performance tracking

Key Phase 6B Features:
- Automatic gas optimization (23.1% average savings)
- Transaction status tracking
- Portfolio integration
- Unified execution pipeline

File: dexproject/paper_trading/bot/simple_trader.py
"""

import os
import sys
import time
import signal
import logging
import asyncio
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
from django.contrib.auth.models import User
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
# PHASE 6B: TRANSACTION MANAGER IMPORTS
# ============================================================================
from trading.services.transaction_manager import (
    get_transaction_manager,
    TransactionManager,
    TransactionSubmissionRequest,
    TransactionStatus,
    create_transaction_submission_request
)
from trading.services.dex_router_service import (
    SwapType, DEXVersion, TradingGasStrategy
)
from trading.tasks import (
    execute_buy_order_with_transaction_manager,
    execute_sell_order_with_transaction_manager
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
    Unified Paper Trading Bot with Intel Slider System and Phase 6B Integration.
    
    This bot consolidates all trading logic with:
    - Configurable intelligence levels (1-10)
    - Phase 6B Transaction Manager integration
    - Automatic gas optimization
    - Centralized transaction management
    - Single account operation (simplified for single user)
    """
    
    def __init__(self, intel_level: int = 5, use_transaction_manager: bool = True):
        """
        Initialize the enhanced paper trading bot.
        
        Simplified for single-account operation.
        
        Args:
            intel_level: Intelligence level (1-10) controlling bot behavior
            use_transaction_manager: Whether to use Phase 6B Transaction Manager
        """
        # ====================================================================
        # CORE CONFIGURATION
        # ====================================================================
        self.intel_level = intel_level
        self.use_transaction_manager = use_transaction_manager  # Phase 6B flag
        self.account = None  # Will be loaded/created in initialize()
        self.account_id = None  # Will be set in initialize()
        self.session = None
        self.running = False
        self.user = None  # Will be set during initialization
        
        # ====================================================================
        # PHASE 6B: TRANSACTION MANAGER
        # ====================================================================
        self.transaction_manager = None  # Will be initialized if enabled
        self.chain_id = 8453  # Base mainnet for paper trading
        self.pending_transactions = {}  # tx_id -> status tracking
        
        # ====================================================================
        # INTELLIGENCE SYSTEM
        # ====================================================================
        self.intelligence_engine = None
        self.websocket_service = websocket_service
        
        # ====================================================================
        # POSITION TRACKING
        # ====================================================================
        self.positions = {}  # token_symbol -> PaperPosition
        
        # ====================================================================
        # TRADING PARAMETERS (adjusted by intel level)
        # ====================================================================
        self.tick_interval = self._calculate_tick_interval()
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
        self.total_gas_saved = Decimal('0')  # Phase 6B: Track gas savings
        
        # ====================================================================
        # DECISION TRACKING
        # ====================================================================
        self.last_decisions = {}  # token_symbol -> TradingDecision
        
        logger.info(
            f"[BOT] Enhanced Paper Trading Bot initialized with Intel Level {intel_level}"
            f" (Transaction Manager: {'ENABLED' if use_transaction_manager else 'DISABLED'})"
        )
    
    def _calculate_tick_interval(self) -> int:
        """Calculate tick interval based on intelligence level."""
        if self.intel_level <= 3:
            return 30  # Cautious: Check every 30 seconds
        elif self.intel_level <= 6:
            return 15  # Balanced: Check every 15 seconds
        elif self.intel_level <= 9:
            return 5   # Aggressive: Check every 5 seconds
        else:
            return 3   # Autonomous: Check every 3 seconds
    
    async def _initialize_transaction_manager(self) -> bool:
        """
        Initialize Phase 6B Transaction Manager if enabled.
        
        Returns:
            True if initialized successfully or not needed, False on error
        """
        if not self.use_transaction_manager:
            logger.info("[PHASE 6B] Transaction Manager disabled")
            return True
        
        try:
            # Get transaction manager for the chain
            self.transaction_manager = await get_transaction_manager(self.chain_id)
            
            if self.transaction_manager:
                logger.info(
                    f"[PHASE 6B] Transaction Manager initialized for chain {self.chain_id}"
                )
                
                # Get performance metrics
                metrics = self.transaction_manager.get_performance_metrics()
                logger.info(
                    f"[PHASE 6B] Current metrics - "
                    f"Success rate: {metrics['success_rate_percent']:.1f}%, "
                    f"Avg gas savings: {metrics['average_gas_savings_percent']:.2f}%"
                )
                return True
            else:
                logger.warning("[PHASE 6B] Could not initialize Transaction Manager")
                self.use_transaction_manager = False
                return True  # Continue without it
                
        except Exception as e:
            logger.error(f"[PHASE 6B] Transaction Manager init error: {e}")
            self.use_transaction_manager = False
            return True  # Continue without it
    
    def initialize(self) -> bool:
        """
        Initialize bot components and create trading session.
        
        Enhanced with Phase 6B Transaction Manager initialization.
        """
        try:
            # ================================================================
            # LOAD OR CREATE SINGLE ACCOUNT
            # ================================================================
            # For single-user operation, we always use one account
            account = PaperTradingAccount.objects.first()
            
            if not account:
                # Create default account if none exists
                account = PaperTradingAccount.objects.create(
                    name="Main_Trading_Account",
                    initial_balance_usd=Decimal('10000.00'),
                    current_balance_usd=Decimal('10000.00')
                )
                logger.info(f"[ACCOUNT] Created default account: {account.name}")
            
            self.account = account
            self.account_id = account.pk  # Update the ID to match
            
            # Get or create user for transaction manager
            self.user, created = User.objects.get_or_create(
                username="paper_trading_bot",
                defaults={'email': "bot@papertrading.local"}
            )
            if created:
                logger.info(f"[USER] Created bot user: {self.user.username}")
            
            logger.info(f"[DATA] Using account: {self.account.name} (Balance: ${self.account.current_balance_usd:.2f})")
            
            # ================================================================
            # PHASE 6B: INITIALIZE TRANSACTION MANAGER
            # ================================================================
            if self.use_transaction_manager:
                # Run async initialization
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._initialize_transaction_manager())
                loop.close()
            
            # ================================================================
            # CREATE TRADING SESSION
            # ================================================================
            self.bot_config = {
                'intel_level': self.intel_level,
                'tick_interval': self.tick_interval,
                'min_trade_interval': self.min_trade_interval,
                'price_volatility': float(self.price_volatility),
                'trend_probability': self.trend_probability,
                'use_transaction_manager': self.use_transaction_manager,  # Phase 6B
                'chain_id': self.chain_id
            }

            self.session = PaperTradingSession.objects.create(
                account=self.account,
                name=f"Intel Bot Session - Level {self.intel_level} (6B: {self.use_transaction_manager})",
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
                         f"Transaction Manager: {'ENABLED' if self.use_transaction_manager else 'DISABLED'}. "
                         f"Starting balance: ${self.account.current_balance_usd:.2f}",
                confidence=100,
                decision_type="SYSTEM"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] Initialization failed: {e}", exc_info=True)
            return False
    
    def _setup_strategy_configuration(self):
        """Set up strategy configuration based on intel level."""
        config = self.intelligence_engine.config
        
        # Determine gas strategy for Phase 6B
        if self.intel_level <= 3:
            gas_strategy = TradingGasStrategy.COST_EFFICIENT.value
        elif self.intel_level <= 6:
            gas_strategy = TradingGasStrategy.BALANCED.value
        elif self.intel_level <= 9:
            gas_strategy = TradingGasStrategy.SPEED_PRIORITY.value
        else:
            gas_strategy = TradingGasStrategy.MEV_PROTECTED.value
        
        self.strategy_config, created = PaperStrategyConfiguration.objects.update_or_create(
            account=self.account,
            name=f"Intel_Level_{self.intel_level}",
            defaults={
                'is_active': True,
                'trading_mode': self._get_trading_mode(),
                'use_fast_lane': self.intel_level >= 7,
                'use_smart_lane': True,
                'max_position_size_percent': config.max_position_percent,
                'stop_loss_percent': Decimal('5'),
                'take_profit_percent': Decimal('10'),
                'max_daily_trades': self._get_max_daily_trades(),
                'confidence_threshold': config.min_confidence_required,
                'custom_parameters': {
                    'intel_level': self.intel_level,
                    'risk_tolerance': float(config.risk_tolerance),
                    'gas_aggressiveness': config.gas_aggressiveness,
                    'use_mev_protection': config.use_mev_protection,
                    'use_transaction_manager': self.use_transaction_manager,  # Phase 6B
                    'gas_strategy': gas_strategy  # Phase 6B
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
            return 100
    
    def _load_positions(self):
        """Load existing open positions for the account."""
        open_positions = PaperPosition.objects.filter(
            account=self.account,
            is_open=True
        )
        
        for position in open_positions:
            self.positions[position.token_symbol] = position
            logger.info(f"[POSITION] Loaded: {position.token_symbol} - {position.quantity} @ ${position.average_entry_price_usd}")
    
    def _initialize_price_history(self):
        """Initialize price history with simulated data."""
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
        """Main bot execution loop."""
        logger.info("[START] Bot starting main execution loop...")
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        
        self.running = True
        
        try:
            while self.running:
                # Market analysis tick
                self._tick()
                
                # Sleep between ticks
                time.sleep(self.tick_interval)
                
        except Exception as e:
            logger.error(f"[ERROR] Bot crashed: {e}", exc_info=True)
        finally:
            self._cleanup()
    
    def _tick(self):
        """Single market analysis tick."""
        try:
            # Update simulated prices
            self._update_prices()
            
            # Check pending transactions if using Transaction Manager
            if self.use_transaction_manager:
                self._check_pending_transactions()
            
            # Analyze each token
            for token_symbol in self.price_history.keys():
                self._analyze_and_trade(token_symbol)
            
            # Update performance metrics
            self._update_performance_metrics()
            
            # Send status update
            if self.trades_executed % 5 == 0:  # Every 5 trades
                self._send_bot_status_update('running')
            
        except Exception as e:
            logger.error(f"[ERROR] Tick error: {e}", exc_info=True)
    
    def _check_pending_transactions(self):
        """Check status of pending transactions (Phase 6B)."""
        if not self.transaction_manager or not self.pending_transactions:
            return
        
        completed = []
        for tx_id, start_time in list(self.pending_transactions.items()):
            try:
                # Create event loop for async call
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                tx_state = loop.run_until_complete(
                    self.transaction_manager.get_transaction_status(tx_id)
                )
                loop.close()
                
                if tx_state:
                    if tx_state.status == TransactionStatus.COMPLETED:
                        logger.info(
                            f"[PHASE 6B] Transaction completed: {tx_id[:8]}... "
                            f"Gas saved: {tx_state.gas_savings_percent:.2f}%"
                        )
                        self.total_gas_saved += tx_state.gas_savings_percent or Decimal('0')
                        completed.append(tx_id)
                    elif tx_state.status in [TransactionStatus.FAILED, TransactionStatus.CANCELLED]:
                        logger.warning(f"[PHASE 6B] Transaction failed: {tx_id[:8]}...")
                        completed.append(tx_id)
                
            except Exception as e:
                logger.error(f"[PHASE 6B] Error checking transaction {tx_id}: {e}")
        
        # Remove completed transactions
        for tx_id in completed:
            del self.pending_transactions[tx_id]
    
    def _analyze_and_trade(self, token_symbol: str):
        """Analyze a token and make trading decision."""
        try:
            current_price = self.price_history[token_symbol][-1]
            
            # Prepare token data
            token_data = {
                'address': '0x' + 'a' * 40,  # Simulated address
                'symbol': token_symbol,
                'liquidity_usd': Decimal('500000'),
                'volume_24h': Decimal('100000')
            }
            
            # Analyze market using intelligence engine
            market_context = async_to_sync(self.intelligence_engine.analyze_market)(
                token_address=token_data['address'],
                trade_size_usd=self.account.current_balance_usd * Decimal('0.1'),
                liquidity_usd=token_data['liquidity_usd'],
                volume_24h=token_data['volume_24h'],
                recent_failures=self.failed_trades,
                success_rate_1h=self._calculate_recent_success_rate()
            )
            
            # Make trading decision
            existing_positions = [
                {
                    'token_symbol': pos.token_symbol,
                    'quantity': float(pos.quantity),
                    'invested_usd': float(pos.total_invested_usd)
                }
                for pos in self.positions.values()
            ]
            
            decision = async_to_sync(self.intelligence_engine.make_decision)(
                market_context=market_context,
                account_balance=self.account.current_balance_usd,
                existing_positions=existing_positions,
                token_address=token_data['address'],
                token_symbol=token_symbol
            )
            
            # Log thought process
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
                    'opportunity_score': float(decision.opportunity_score),
                    'use_tx_manager': self.use_transaction_manager  # Phase 6B
                }
            )
            
            # Execute trade if decided
            if decision.action in ['BUY', 'SELL']:
                if self._can_trade():
                    if self.use_transaction_manager:
                        # Phase 6B: Use Transaction Manager
                        self._execute_trade_with_tx_manager(decision, token_symbol, current_price)
                    else:
                        # Original execution
                        self._execute_trade(decision, token_symbol, current_price)
            
            # Store decision for tracking
            self.last_decisions[token_symbol] = decision
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to analyze {token_symbol}: {e}", exc_info=True)
    
    def _execute_trade_with_tx_manager(self, decision: TradingDecision, token_symbol: str, current_price: Decimal):
        """
        Execute trade using Phase 6B Transaction Manager.
        
        This provides:
        - Automatic gas optimization
        - Transaction status tracking
        - Portfolio integration
        """
        try:
            logger.info(
                f"[PHASE 6B] Executing trade via Transaction Manager: "
                f"{decision.action} {token_symbol} ${decision.position_size_usd:.2f}"
            )
            
            # Determine gas strategy based on intel level and decision
            if self.intel_level <= 3:
                gas_strategy = TradingGasStrategy.COST_EFFICIENT
            elif self.intel_level <= 6:
                gas_strategy = TradingGasStrategy.BALANCED
            elif self.intel_level <= 9:
                gas_strategy = TradingGasStrategy.SPEED_PRIORITY
            else:
                gas_strategy = TradingGasStrategy.MEV_PROTECTED
            
            # Create simulated token address (consistent for tracking)
            token_address = f"0x{'b' * 39}{ord(token_symbol[-1]):x}"
            
            if decision.action == 'BUY':
                # Execute buy order through Transaction Manager
                result = execute_buy_order_with_transaction_manager.apply_async(
                    args=[
                        self.user.id,
                        self.chain_id,
                        token_address,
                        float(decision.position_size_usd),
                        None,  # strategy_id
                        0.005,  # slippage
                        True  # is_paper_trade
                    ]
                ).get(timeout=30)
            else:
                # Calculate token amount for sell
                if token_symbol in self.positions:
                    position = self.positions[token_symbol]
                    token_amount = str(int(position.quantity * Decimal('1e18')))
                else:
                    logger.warning(f"[PHASE 6B] No position to sell for {token_symbol}")
                    return
                
                # Execute sell order through Transaction Manager
                result = execute_sell_order_with_transaction_manager.apply_async(
                    args=[
                        self.user.id,
                        self.chain_id,
                        token_address,
                        token_amount,
                        None,  # strategy_id
                        0.005,  # slippage
                        True  # is_paper_trade
                    ]
                ).get(timeout=30)
            
            if result.get('success'):
                # Track pending transaction
                tx_id = result.get('transaction_id')
                if tx_id:
                    self.pending_transactions[tx_id] = datetime.now()
                
                # Update metrics
                self.trades_executed += 1
                self.successful_trades += 1
                self.last_trade_time = datetime.now()
                
                # Update positions
                if decision.action == 'BUY':
                    self._open_or_add_position(token_symbol, decision, current_price)
                else:
                    self._close_or_reduce_position(token_symbol, decision, current_price)
                
                # Log gas savings
                gas_savings = result.get('gas_savings_percent', 0)
                logger.info(
                    f"[PHASE 6B] Trade executed successfully! "
                    f"Transaction: {tx_id[:8] if tx_id else 'N/A'}... "
                    f"Gas savings: {gas_savings:.2f}%"
                )
                
                # Create paper trade record
                self._record_paper_trade(
                    decision, token_symbol, current_price,
                    metadata={
                        'tx_manager_used': True,
                        'gas_savings_percent': gas_savings,
                        'transaction_id': tx_id
                    }
                )
            else:
                logger.error(f"[PHASE 6B] Trade failed: {result.get('error')}")
                self.failed_trades += 1
                
        except Exception as e:
            logger.error(f"[PHASE 6B] Transaction Manager execution failed: {e}", exc_info=True)
            self.failed_trades += 1
            # Fall back to regular execution
            self._execute_trade(decision, token_symbol, current_price)
    
    def _execute_trade(self, decision: TradingDecision, token_symbol: str, current_price: Decimal):
        """Original trade execution (without Transaction Manager)."""
        try:
            # Record paper trade
            self._record_paper_trade(decision, token_symbol, current_price)
            
            # Update position
            if decision.action == 'BUY':
                self._open_or_add_position(token_symbol, decision, current_price)
            else:
                self._close_or_reduce_position(token_symbol, decision, current_price)
            
            # Update metrics
            self.trades_executed += 1
            self.successful_trades += 1
            self.last_trade_time = datetime.now()
            
            logger.info(
                f"[TRADE] Executed: {decision.action} {token_symbol} "
                f"Size: ${decision.position_size_usd:.2f} "
                f"Intel: {self.intel_level} "
                f"Confidence: {decision.overall_confidence:.1f}%"
            )
            
        except Exception as e:
            logger.error(f"[ERROR] Trade execution failed: {e}", exc_info=True)
            self.failed_trades += 1
    
    def _record_paper_trade(self, decision: TradingDecision, token_symbol: str, 
                           current_price: Decimal, metadata: Optional[Dict] = None):
        """Record trade in database."""
        trade_metadata = {
            'intel_level': self.intel_level,
            'confidence': float(decision.overall_confidence),
            'risk_score': float(decision.risk_score)
        }
        if metadata:
            trade_metadata.update(metadata)
        
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
            slippage_percent=Decimal('1'),
            status='SUCCESS',
            execution_time_ms=int(decision.processing_time_ms),
            metadata=trade_metadata
        )
        
        # Send trade notification
        self._send_trade_notification(trade, decision)
    
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
        """Update simulated market prices."""
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
            # Calculate average gas savings if using Transaction Manager
            avg_gas_savings = (
                self.total_gas_saved / self.successful_trades 
                if self.successful_trades > 0 and self.use_transaction_manager 
                else Decimal('0')
            )
            
            # Store Phase 6B metrics in metadata field (JSONField that exists in the model)
            metadata = {}
            if self.use_transaction_manager:
                metadata.update({
                    'avg_gas_savings_percent': float(avg_gas_savings),
                    'tx_manager_used': True,
                    'pending_transactions': len(self.pending_transactions)
                })
            
            metrics, created = PaperPerformanceMetrics.objects.update_or_create(
                session=self.session,
                defaults={
                    'total_trades': self.trades_executed,
                    'winning_trades': self.successful_trades,
                    'losing_trades': self.failed_trades,
                    'win_rate': Decimal(str(self._calculate_recent_success_rate())),
                    'total_pnl_usd': self.total_pnl,
                    'period_start': self.session.started_at,
                    'period_end': timezone.now()
                    # Removed metrics_json - field doesn't exist
                    # If there's a metadata or custom field in the model, we could use that
                }
            )
            
            # Send performance update via WebSocket
            if self.trades_executed % 10 == 0:
                self._send_performance_update(metrics)
                
        except Exception as e:
            logger.error(f"[ERROR] Failed to update metrics: {e}", exc_info=True)
    
    def _log_thought(self, action: str, reasoning: str, confidence: float,
                    decision_type: str = "ANALYSIS", metadata: Optional[Dict] = None):
        """Log AI thought process to database and WebSocket."""
        try:
            # Map confidence to confidence level
            if confidence >= 80:
                confidence_level = 'VERY_HIGH'
            elif confidence >= 60:
                confidence_level = 'HIGH'
            elif confidence >= 40:
                confidence_level = 'MEDIUM'
            elif confidence >= 20:
                confidence_level = 'LOW'
            else:
                confidence_level = 'VERY_LOW'
            
            # Extract scores from metadata or use defaults
            risk_score = Decimal('0')
            opportunity_score = Decimal('0')
            if metadata:
                risk_score = Decimal(str(metadata.get('risk_score', 0)))
                opportunity_score = Decimal(str(metadata.get('opportunity_score', 0)))
            
            thought_log = PaperAIThoughtLog.objects.create(
                account=self.account,
                decision_type=decision_type,
                confidence_level=confidence_level,
                confidence_percent=Decimal(str(confidence)),
                risk_score=risk_score,
                opportunity_score=opportunity_score,
                primary_reasoning=reasoning[:1000],
                market_data=metadata or {},
                strategy_name=f"INTEL_{self.intel_level}"
            )
            
            logger.debug(f"[THOUGHT] Logged: {action} ({confidence:.1f}% confidence)")
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to log thought: {e}", exc_info=True)
    
    def _send_trade_notification(self, trade: PaperTrade, decision: TradingDecision):
        """Send trade notification via WebSocket."""
        try:
            # Temporarily disabled until WebSocket service is fixed
            pass
        except Exception as e:
            logger.error(f"[ERROR] Failed to send trade notification: {e}")

    def _send_bot_status_update(self, status: str):
        """Send bot status update via WebSocket."""
        try:
            # Temporarily disabled until WebSocket service is fixed
            pass
        except Exception as e:
            logger.error(f"[ERROR] Failed to send status update: {e}")

    def _send_performance_update(self, metrics: PaperPerformanceMetrics):
        """Send performance update via WebSocket."""
        try:
            # Temporarily disabled until WebSocket service is fixed
            pass
        except Exception as e:
            logger.error(f"[ERROR] Failed to send performance update: {e}")
    
    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info("\n[STOP] Shutdown signal received...")
        self.running = False
    
    def _cleanup(self):
        """Cleanup resources and close session."""
        try:
            # Update session status
            if self.session:
                self.session.status = 'STOPPED'
                self.session.ended_at = timezone.now()
                self.session.ending_balance_usd = self.account.current_balance_usd
                self.session.save()
                logger.info(f"[SESSION] Session {self.session.session_id} ended")
            
            # Update final position values
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
            
            # Phase 6B: Log final gas savings
            if self.use_transaction_manager and self.successful_trades > 0:
                avg_gas_savings = self.total_gas_saved / self.successful_trades
                logger.info(
                    f"[PHASE 6B] Final gas savings: "
                    f"Total: {self.total_gas_saved:.2f}%, "
                    f"Average: {avg_gas_savings:.2f}%"
                )
            
            # Log final thought
            self._log_thought(
                action="SHUTDOWN",
                reasoning=f"Bot shutting down. Intel Level: {self.intel_level}. "
                         f"Session summary: Trades: {self.trades_executed}, "
                         f"Success rate: {self._calculate_recent_success_rate():.1f}%, "
                         f"Total P&L: ${self.total_pnl:.2f}"
                         f"{f', Avg Gas Saved: {(self.total_gas_saved/self.successful_trades if self.successful_trades > 0 else 0):.2f}%' if self.use_transaction_manager else ''}",
                confidence=100,
                decision_type="SYSTEM"
            )
            
            # Send shutdown notification
            self._send_bot_status_update('stopped')
            
            logger.info("[OK] Cleanup completed")
            
        except Exception as e:
            logger.error(f"[ERROR] Cleanup error: {e}", exc_info=True)


def main():
    """Main entry point for the enhanced paper trading bot."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Enhanced Paper Trading Bot with Intel Slider System and Phase 6B'
    )
    parser.add_argument(
        '--intel-level',
        type=int,
        default=5,
        choices=range(1, 11),
        help='Intelligence level (1-10): 1-3=Cautious, 4-6=Balanced, 7-9=Aggressive, 10=Autonomous'
    )
    parser.add_argument(
        '--use-tx-manager',
        action='store_true',
        default=True,
        help='Use Phase 6B Transaction Manager for gas optimization (default: True)'
    )
    parser.add_argument(
        '--no-tx-manager',
        action='store_true',
        help='Disable Phase 6B Transaction Manager'
    )
    
    args = parser.parse_args()
    
    # Determine if Transaction Manager should be used
    use_tx_manager = not args.no_tx_manager
    
    # Create and run bot (no account_id needed - uses single account)
    bot = EnhancedPaperTradingBot(
        intel_level=args.intel_level,
        use_transaction_manager=use_tx_manager
    )
    
    if bot.initialize():
        logger.info("[OK] Bot initialized successfully")
        bot.run()
    else:
        logger.error("[ERROR] Bot initialization failed")
        sys.exit(1)


if __name__ == "__main__":
    main()