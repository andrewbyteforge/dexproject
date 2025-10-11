"""
Enhanced Paper Trading Bot with Intel Slider System, Transaction Manager, and Circuit Breakers

This is the complete paper trading bot that integrates:
- Intel Slider (1-10) system for intelligent decision making
- Phase 6B Transaction Manager for gas optimization (23.1% savings)
- Circuit breaker protection for risk management
- Real-time transaction status tracking
- WebSocket updates for transaction lifecycle
- Comprehensive thought logging

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
# CIRCUIT BREAKER IMPORTS
# ============================================================================
try:
    from engine.portfolio import (
        CircuitBreakerManager,
        CircuitBreakerType,
        CircuitBreakerEvent
    )
    from trading.services.portfolio_service import create_portfolio_service
    CIRCUIT_BREAKER_AVAILABLE = True
except ImportError:
    CIRCUIT_BREAKER_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("Circuit breaker components not available - running without protection")

# ============================================================================
# SERVICE IMPORTS
# ============================================================================
from paper_trading.services.websocket_service import websocket_service

# ============================================================================
# TRANSACTION MANAGER IMPORTS (Phase 6B Integration)
# ============================================================================
try:
    from trading.services.transaction_manager import (
        get_transaction_manager,
        create_transaction_submission_request,
        TransactionStatus,
        TransactionSubmissionRequest,
        TransactionManagerResult
    )
    from trading.services.dex_router_service import (
        SwapType, 
        DEXVersion, 
        TradingGasStrategy,
        SwapParams
    )
    TRANSACTION_MANAGER_AVAILABLE = True
except ImportError:
    TRANSACTION_MANAGER_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("Transaction Manager not available - running in legacy mode")

# ============================================================================
# LEGACY AI ENGINE IMPORT (for backward compatibility)
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
    Unified Paper Trading Bot with Intel Slider System, Transaction Manager, and Circuit Breakers.
    
    This bot integrates:
    - Intel Slider (1-10) for intelligent decision making
    - Transaction Manager for gas optimization (Phase 6B)
    - Circuit breaker protection for risk management
    - Real-time WebSocket updates
    - Comprehensive thought logging
    """
    
    def __init__(self, account_name: str, intel_level: int = 5):
        """
        Initialize the enhanced paper trading bot.
        
        Args:
            account_name: Name of the paper trading account
            intel_level: Intelligence level (1-10)
        """
        self.account_name = account_name
        self.intel_level = intel_level
        self.use_tx_manager = TRANSACTION_MANAGER_AVAILABLE  # Always use if available
        self.account = None
        self.session = None
        self.intelligence_engine = None
        
        # Circuit breaker components
        self.circuit_breaker_manager = None
        self.circuit_breaker_enabled = CIRCUIT_BREAKER_AVAILABLE
        self.consecutive_failures = 0
        self.daily_trades_count = 0
        self.last_trade_date = None
        
        # Transaction Manager instance (initialized later if needed)
        self.tx_manager = None
        self.chain_id = 1  # Default to Ethereum mainnet
        
        # Performance tracking for Transaction Manager
        self.total_gas_savings = Decimal('0')
        self.trades_with_tx_manager = 0
        self.pending_transactions = {}  # Track pending TX manager transactions
        
        # Market tracking
        self.token_list = [
            {'symbol': 'WETH', 'address': '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2', 'price': Decimal('2500')},
            {'symbol': 'USDC', 'address': '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48', 'price': Decimal('1')},
            {'symbol': 'USDT', 'address': '0xdac17f958d2ee523a2206206994597c13d831ec7', 'price': Decimal('1')},
            {'symbol': 'DAI', 'address': '0x6b175474e89094c44da98b954eedeac495271d0f', 'price': Decimal('1')},
            {'symbol': 'WBTC', 'address': '0x2260fac5e5542a773aa44fbcfedf7c193bc2c599', 'price': Decimal('45000')},
            {'symbol': 'UNI', 'address': '0x1f9840a85d5af5bf1d1762f925bdaddc4201f984', 'price': Decimal('6.50')},
            {'symbol': 'AAVE', 'address': '0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9', 'price': Decimal('95')},
            {'symbol': 'LINK', 'address': '0x514910771af9ca656af840dff83e8264ecf986ca', 'price': Decimal('15')},
            {'symbol': 'MATIC', 'address': '0x7d1afa7b718fb893db30a3abc0cfc608aacfebb0', 'price': Decimal('0.85')},
            {'symbol': 'ARB', 'address': '0xb50721bcf8d664c30412cfbc6cf7a15145234ad1', 'price': Decimal('1.20')}
        ]
        
        self.price_history = {}
        self.positions = {}
        self.last_decisions = {}
        
        # Control flags
        self.running = False
        self.tick_interval = 15  # seconds between market checks
        self.tick_count = 0
        
        log_msg = f"[BOT] Enhanced Paper Trading Bot initialized with Intel Level {intel_level}"
        if self.use_tx_manager:
            log_msg += " (Transaction Manager ENABLED - Gas Optimization Active)"
        else:
            log_msg += " (Transaction Manager DISABLED - Legacy Mode)"
        if self.circuit_breaker_enabled:
            log_msg += " (Circuit Breakers ENABLED - Risk Protection Active)"
        logger.info(log_msg)
    
    def initialize(self) -> bool:
        """
        Initialize bot components and connections.
        
        Returns:
            True if initialization successful
        """
        try:
            # Load or create account
            self._load_account()
            
            # Create trading session
            self._create_session()
            
            # Initialize intelligence engine
            self._initialize_intelligence()
            
            # Initialize circuit breaker manager
            self._initialize_circuit_breaker()
            
            # Setup strategy configuration
            self._setup_strategy_configuration()
            
            # Initialize Transaction Manager if enabled
            if self.use_tx_manager:
                self._initialize_transaction_manager()
            
            # Load existing positions
            self._load_positions()
            
            # Initialize price history
            self._initialize_price_history()
            
            # Send initialization notification
            self._send_bot_status_update('initialized')
            
            # Log initial thought
            self._log_thought(
                action="STARTUP",
                reasoning=f"Bot initialized with Intel Level {self.intel_level}. "
                         f"Strategy: {self.intelligence_engine.config.name}. "
                         f"Risk tolerance: {self.intelligence_engine.config.risk_tolerance}%. "
                         f"Transaction Manager: {'ENABLED' if self.use_tx_manager else 'DISABLED'}. "
                         f"Circuit Breakers: {'ENABLED' if self.circuit_breaker_enabled else 'DISABLED'}. "
                         f"Starting balance: ${self.account.current_balance_usd:.2f}",
                confidence=100,
                decision_type="SYSTEM"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] Initialization failed: {e}", exc_info=True)
            return False
    
    def _initialize_circuit_breaker(self):
        """Initialize circuit breaker manager for risk management."""
        if not CIRCUIT_BREAKER_AVAILABLE:
            self.circuit_breaker_enabled = False
            return
            
        try:
            from engine.portfolio import CircuitBreakerManager
            
            self.circuit_breaker_manager = CircuitBreakerManager()
            logger.info("[CB] Circuit breaker manager initialized for bot")
            
            # Log initial circuit breaker status
            can_trade, reasons = self.circuit_breaker_manager.can_trade()
            if can_trade:
                logger.info("[CB] Circuit breakers clear - trading enabled")
            else:
                logger.warning(f"[CB] Circuit breakers active: {', '.join(reasons)}")
                
        except Exception as e:
            logger.error(f"[CB] Failed to initialize circuit breaker: {e}")
            self.circuit_breaker_enabled = False
    
    def _initialize_transaction_manager(self):
        """Initialize the Transaction Manager for gas optimization."""
        try:
            # Run async initialization in sync context
            async def init_tx_manager():
                self.tx_manager = await get_transaction_manager(self.chain_id)
                return self.tx_manager is not None
            
            success = async_to_sync(init_tx_manager)()
            
            if success:
                logger.info("[TX MANAGER] Transaction Manager initialized successfully")
                logger.info("[TX MANAGER] Gas optimization enabled - targeting 23.1% savings")
            else:
                logger.warning("[TX MANAGER] Failed to initialize - falling back to legacy mode")
                self.use_tx_manager = False
                
        except Exception as e:
            logger.error(f"[TX MANAGER] Initialization error: {e}")
            self.use_tx_manager = False
    
    def _setup_strategy_configuration(self):
        """
        Set up or load a valid PaperStrategyConfiguration for this account.
        """
        from decimal import Decimal
        from paper_trading.models import PaperStrategyConfiguration

        def json_safe(value):
            """Convert Decimals and other non-JSON types to serializable types."""
            if isinstance(value, Decimal):
                return float(value)
            if isinstance(value, dict):
                return {k: json_safe(v) for k, v in value.items()}
            if isinstance(value, list):
                return [json_safe(v) for v in value]
            return value

        try:
            config = self.intelligence_engine.config

            max_pos_size = getattr(config, "max_position_size", getattr(config, "max_position_size_percent", 10))
            confidence_threshold = getattr(config, "confidence_threshold", 60)
            risk_tolerance = getattr(config, "risk_tolerance", 50)
            trade_freq = getattr(getattr(config, "trade_frequency", None), "value", "Moderate")

            custom_parameters = {
                "intel_level": self.intel_level,
                "use_tx_manager": self.use_tx_manager,
                "circuit_breaker_enabled": self.circuit_breaker_enabled,
                "intel_config_summary": {
                    "risk_tolerance": risk_tolerance,
                    "trade_frequency": trade_freq,
                    "max_position_size": float(max_pos_size),
                    "confidence_threshold": float(confidence_threshold),
                },
            }

            custom_parameters = json_safe(custom_parameters)

            strategy_config, created = PaperStrategyConfiguration.objects.get_or_create(
                account=self.account,
                name=f"Intel_Level_{self.intel_level}_Strategy",
                defaults={
                    "trading_mode": "MODERATE",
                    "use_fast_lane": True,
                    "use_smart_lane": False,
                    "fast_lane_threshold_usd": Decimal("100"),
                    "max_position_size_percent": Decimal(str(max_pos_size)),
                    "stop_loss_percent": Decimal("5.0"),
                    "take_profit_percent": Decimal("10.0"),
                    "max_daily_trades": 20,
                    "max_concurrent_positions": 5,
                    "min_liquidity_usd": Decimal("10000"),
                    "max_slippage_percent": Decimal("1.0"),
                    "confidence_threshold": Decimal(str(confidence_threshold)),
                    "allowed_tokens": self._get_allowed_tokens(),
                    "blocked_tokens": [],
                    "custom_parameters": custom_parameters,
                },
            )

            if not created:
                strategy_config.custom_parameters = custom_parameters
                strategy_config.save()

            logger.info("[CONFIG] Strategy configuration %s", "created" if created else "updated")
            self.strategy_config = strategy_config

        except Exception as e:
            logger.error("[ERROR] Failed to setup strategy configuration: %s", e, exc_info=True)
            raise

    def _load_account(self):
        """
        Load the single paper trading account for this user.
        Always uses the same account regardless of parameters.
        """
        from django.contrib.auth.models import User
        
        # Always use the same user
        user, _ = User.objects.get_or_create(
            username='demo_user',
            defaults={'email': 'demo@example.com'}
        )
        
        # Get the first existing account for this user, or create one
        existing_accounts = PaperTradingAccount.objects.filter(user=user).order_by('created_at')
        
        if existing_accounts.exists():
            # Always use the first (oldest) account
            self.account = existing_accounts.first()
            logger.info(f"[ACCOUNT] Using existing account: {self.account.name} (ID: {self.account.account_id})")
            
            # Optional: Clean up any duplicate accounts
            if existing_accounts.count() > 1:
                duplicates = existing_accounts[1:]
                for dup in duplicates:
                    logger.warning(f"[ACCOUNT] Removing duplicate account: {dup.name} (ID: {dup.account_id})")
                    dup.delete()
                logger.info(f"[ACCOUNT] Cleaned up {len(duplicates)} duplicate accounts")
        else:
            # Create the one and only account
            self.account = PaperTradingAccount.objects.create(
                name='My_Trading_Bot',
                user=user,
                current_balance_usd=Decimal('10000'),
                initial_balance_usd=Decimal('10000')
            )
            logger.info(f"[ACCOUNT] Created new account: {self.account.name} (ID: {self.account.account_id})")
        
        logger.info(f"[ACCOUNT] Balance: ${self.account.current_balance_usd:,.2f}")
        
        # Override the account_name to match what we're actually using
        self.account_name = self.account.name


    def _create_session(self) -> None:
        """
        Create or resume a trading session for today.
        Only one active session per day is allowed.
        """
        import json
        from uuid import UUID
        from datetime import date

        def json_safe(data):
            """Recursively convert non-serializable types to safe formats."""
            if isinstance(data, dict):
                return {k: json_safe(v) for k, v in data.items()}
            if isinstance(data, list):
                return [json_safe(v) for v in data]
            if isinstance(data, UUID):
                return str(data)
            if isinstance(data, Decimal):
                return float(data)
            if isinstance(data, datetime):
                return data.isoformat()
            return data

        today = timezone.now().date()
        
        # Check for existing session today
        existing_sessions = PaperTradingSession.objects.filter(
            account=self.account,
            started_at__date=today,
            status='RUNNING'
        ).order_by('-started_at')
        
        if existing_sessions.exists():
            # Resume the most recent session from today
            self.session = existing_sessions.first()
            logger.info(f"[SESSION] Resuming existing session from today: {self.session.session_id}")
            logger.info(f"[SESSION] Session started at: {self.session.started_at.strftime('%H:%M:%S')}")
            
            # Update session config to reflect current bot settings
            config_snapshot = {
                "bot_version": "2.2.0",
                "intel_level": self.intel_level,
                "account_name": self.account_name,
                "account_id": str(self.account.account_id),
                "session_uuid": str(self.session.session_id),
                "user_id": str(self.account.user.id),
                "transaction_manager_enabled": self.use_tx_manager,
                "circuit_breaker_enabled": self.circuit_breaker_enabled,
                "resumed_at": timezone.now().isoformat()
            }
            
            self.session.config_snapshot = json_safe(config_snapshot)
            self.session.save()
            
        else:
            # Close any old running sessions from previous days
            old_sessions = PaperTradingSession.objects.filter(
                account=self.account,
                status='RUNNING',
                started_at__date__lt=today
            )
            
            for old_session in old_sessions:
                old_session.status = 'STOPPED'
                old_session.ended_at = timezone.now()
                old_session.ending_balance_usd = self.account.current_balance_usd
                old_session.session_pnl_usd = self.account.current_balance_usd - old_session.starting_balance_usd
                old_session.save()
                logger.info(f"[SESSION] Closed old session from {old_session.started_at.date()}: {old_session.session_id}")
            
            # Create new session for today
            config_snapshot = {
                "bot_version": "2.2.0",
                "intel_level": self.intel_level,
                "account_name": self.account_name,
                "account_id": str(self.account.account_id),
                "session_uuid": str(uuid.uuid4()),
                "user_id": str(self.account.user.id),
                "transaction_manager_enabled": self.use_tx_manager,
                "circuit_breaker_enabled": self.circuit_breaker_enabled,
            }

            safe_snapshot = json_safe(config_snapshot)
            
            session_name = f"Bot_Session_{today.strftime('%Y%m%d')}_Intel_{self.intel_level}"

            self.session = PaperTradingSession.objects.create(
                account=self.account,
                status="RUNNING",
                starting_balance_usd=self.account.current_balance_usd,
                name=session_name,
                config_snapshot=safe_snapshot,
            )
            logger.info(f"[SESSION] Created new session for today: {self.session.session_id}")
            logger.info(f"[SESSION] Session name: {session_name}")













    def _initialize_intelligence(self):
        """Initialize the intelligence engine."""
        self.intelligence_engine = IntelSliderEngine(
            intel_level=self.intel_level,
            account_id=str(self.account.account_id)
        )
        logger.info(f"[INTEL] Intelligence Engine initialized at Level {self.intel_level}")
    
    def _load_positions(self):
        """Load existing open positions."""
        try:
            positions = PaperPosition.objects.filter(
                account=self.account,
                is_open=True
            )
            
            for position in positions:
                self.positions[position.token_symbol] = position
            
            logger.info(f"[POSITIONS] Loaded {len(self.positions)} open positions")
        except Exception as e:
            logger.error(f"[ERROR] Failed to load positions: {e}")
    
    def _initialize_price_history(self):
        """Initialize price history for all tokens."""
        for token in self.token_list:
            self.price_history[token['symbol']] = [token['price']]
    
    def _get_allowed_tokens(self) -> List[str]:
        """Get list of allowed token addresses."""
        return [token['address'] for token in self.token_list]
    
    def _get_portfolio_state(self) -> Dict[str, Any]:
        """
        Get current portfolio state for circuit breaker evaluation.
        
        Returns:
            Dictionary with portfolio metrics
        """
        try:
            # Calculate current P&L
            current_balance = self.account.current_balance_usd
            starting_balance = self.session.starting_balance_usd if self.session else current_balance
            total_pnl = current_balance - starting_balance
            
            # Calculate daily P&L (simplified - in production would track properly)
            daily_pnl = total_pnl  # Simplified for paper trading
            
            # Count open positions value
            positions_value = sum(
                pos.current_value_usd for pos in self.positions.values()
            )
            
            portfolio_state = {
                'daily_pnl': daily_pnl,
                'total_pnl': total_pnl,
                'consecutive_losses': self.consecutive_failures,
                'portfolio_value': current_balance + positions_value,
                'cash_balance': current_balance,
                'positions_count': len(self.positions),
                'daily_trades': self.daily_trades_count
            }
            
            return portfolio_state
            
        except Exception as e:
            logger.error(f"[CB] Error getting portfolio state: {e}")
            return {
                'daily_pnl': Decimal('0'),
                'total_pnl': Decimal('0'),
                'consecutive_losses': 0,
                'portfolio_value': Decimal('10000')
            }
    
    def _send_bot_status_update(self, status: str):
        """Send bot status update via WebSocket."""
        try:
            websocket_service.send_portfolio_update(
                account_id=str(self.account.account_id),
                portfolio_data={
                    'bot_status': status,
                    'intel_level': self.intel_level,
                    'tx_manager_enabled': self.use_tx_manager,
                    'circuit_breaker_enabled': self.circuit_breaker_enabled,
                    'account_balance': float(self.account.current_balance_usd),
                    'open_positions': len(self.positions),
                    'tick_count': self.tick_count,
                    'total_gas_savings': float(self.total_gas_savings) if self.use_tx_manager else 0,
                    'pending_transactions': len(self.pending_transactions),
                    'consecutive_failures': self.consecutive_failures,
                    'daily_trades': self.daily_trades_count
                }
            )
        except Exception as e:
            logger.error(f"[ERROR] Failed to send status update: {e}")
    
    def run(self):
        """Main bot execution loop."""
        logger.info("[START] Bot starting main execution loop...")
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        
        self.running = True
        
        try:
            while self.running:
                # Check pending transactions if TX Manager is enabled
                if self.use_tx_manager and self.pending_transactions:
                    self._check_pending_transactions()
                
                # Market analysis tick
                self._tick()
                
                # Sleep between ticks
                time.sleep(self.tick_interval)
                
        except Exception as e:
            logger.error(f"[ERROR] Bot crashed: {e}", exc_info=True)
        finally:
            self._cleanup()
    
    def _check_pending_transactions(self):
        """Check status of pending transactions from Transaction Manager."""
        if not self.use_tx_manager or not self.tx_manager:
            return
        
        async def check_transactions():
            completed = []
            for tx_id, tx_info in self.pending_transactions.items():
                try:
                    tx_state = await self.tx_manager.get_transaction_status(tx_id)
                    if tx_state:
                        if tx_state.status == TransactionStatus.COMPLETED:
                            logger.info(f"[TX MANAGER] Transaction completed: {tx_id}")
                            if tx_state.gas_savings_percent:
                                self.total_gas_savings += tx_state.gas_savings_percent
                                logger.info(f"[TX MANAGER] Gas saved: {tx_state.gas_savings_percent:.2f}%")
                            completed.append(tx_id)
                        elif tx_state.status == TransactionStatus.FAILED:
                            logger.error(f"[TX MANAGER] Transaction failed: {tx_id}")
                            completed.append(tx_id)
                            self.consecutive_failures += 1
                        elif tx_state.status == TransactionStatus.BLOCKED_BY_CIRCUIT_BREAKER:
                            logger.warning(f"[TX MANAGER] Transaction blocked by circuit breaker: {tx_id}")
                            completed.append(tx_id)
                except Exception as e:
                    logger.error(f"[TX MANAGER] Error checking transaction {tx_id}: {e}")
            
            # Remove completed transactions
            for tx_id in completed:
                del self.pending_transactions[tx_id]
        
        async_to_sync(check_transactions)()
    
    def _tick(self):
        """Single market analysis tick with circuit breaker monitoring."""
        self.tick_count += 1
        logger.info("\n" + "=" * 60)
        logger.info(f"[TICK] Market tick #{self.tick_count}")
        
        # Check circuit breaker status
        if self.circuit_breaker_enabled and self.circuit_breaker_manager:
            can_trade, reasons = self.circuit_breaker_manager.can_trade()
            if not can_trade:
                logger.warning(f"[CB] Circuit breakers active: {', '.join(reasons)}")
                logger.info("[CB] Skipping trading analysis due to circuit breakers")
                
                # Still update market prices for tracking
                self._update_market_prices()
                
                # Send status update
                self._send_bot_status_update('circuit_breaker_active')
                return
        
        # Normal tick processing
        self._update_market_prices()
        
        # Analyze each token
        for token_data in self.token_list:
            self._analyze_token(token_data)
        
        # Update performance metrics
        self._update_performance_metrics()
    
    def _update_market_prices(self):
        """Simulate market price changes."""
        for token in self.token_list:
            # Simulate price movement (-5% to +5%)
            change = Decimal(random.uniform(-0.05, 0.05))
            old_price = token['price']
            token['price'] = old_price * (Decimal('1') + change)
            
            # Update price history
            if token['symbol'] not in self.price_history:
                self.price_history[token['symbol']] = []
            self.price_history[token['symbol']].append(token['price'])
            
            # Keep only last 100 prices
            if len(self.price_history[token['symbol']]) > 100:
                self.price_history[token['symbol']].pop(0)
            
            # Log significant changes
            if abs(change) > Decimal('0.02'):
                logger.info(f"[PRICE] {token['symbol']}: ${old_price:.2f} -> ${token['price']:.2f} ({change*100:.2f}%)")
    
    def _analyze_token(self, token_data: Dict[str, Any]):
        """Analyze a single token for trading opportunities."""
        try:
            token_symbol = token_data['symbol']
            current_price = token_data['price']
            
            # Prepare market context
            market_context = MarketContext(
                token_address=token_data['address'],
                token_symbol=token_symbol,
                current_price=current_price,
                price_24h_ago=self.price_history[token_symbol][0] if self.price_history[token_symbol] else current_price,
                volume_24h=Decimal('1000000'),  # Simulated
                liquidity_usd=Decimal('5000000'),  # Simulated
                holder_count=1000,  # Simulated
                market_cap=Decimal('50000000'),  # Simulated
                volatility=Decimal('0.15'),  # Simulated
                trend='neutral',
                momentum=Decimal('0'),
                support_levels=[],
                resistance_levels=[],
                timestamp=timezone.now()
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
                    'token_address': token_data['address'],
                    'intel_level': self.intel_level,
                    'risk_score': float(decision.risk_score),
                    'opportunity_score': float(decision.opportunity_score),
                    'current_price': float(current_price),
                    'tx_manager_enabled': self.use_tx_manager,
                    'circuit_breaker_enabled': self.circuit_breaker_enabled
                }
            )
            
            # Execute trade if decided
            if decision.action in ['BUY', 'SELL']:
                self._execute_trade(decision, token_symbol, current_price)
            
            # Store decision for tracking
            self.last_decisions[token_symbol] = decision
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to analyze {token_symbol}: {e}", exc_info=True)
    
    def _log_thought(self, action: str, reasoning: str, confidence: float, 
                     decision_type: str = "ANALYSIS", metadata: Dict[str, Any] = None):
        """Log AI thought process to database."""
        try:
            metadata = metadata or {}
            
            # Map action to decision type
            decision_type_map = {
                'BUY': 'BUY',
                'SELL': 'SELL',
                'HOLD': 'HOLD',
                'SKIP': 'SKIP',
                'STARTUP': 'SKIP',
                'TRADE_DECISION': 'HOLD',
                'BLOCKED': 'SKIP',
                'CB_RESET': 'SKIP'
            }
            
            # Get token info from metadata
            token_symbol = metadata.get('token', 'SYSTEM')
            token_address = metadata.get('token_address', '0x' + '0' * 40)
            
            # Create thought log record
            thought_log = PaperAIThoughtLog.objects.create(
                account=self.account,
                paper_trade=None,
                decision_type=decision_type_map.get(action, 'SKIP'),
                token_address=token_address,
                token_symbol=token_symbol,
                confidence_level=self._get_confidence_level(confidence),
                confidence_percent=Decimal(str(confidence)),
                risk_score=Decimal(str(metadata.get('risk_score', 50))),
                opportunity_score=Decimal(str(metadata.get('opportunity_score', 50))),
                primary_reasoning=reasoning[:500],
                key_factors=[
                    f"Intel Level: {metadata.get('intel_level', self.intel_level)}",
                    f"Current Price: ${metadata.get('current_price', 0):.2f}" if 'current_price' in metadata else "System Event",
                    f"TX Manager: {'Enabled' if metadata.get('tx_manager_enabled', False) else 'Disabled'}",
                    f"Circuit Breaker: {'Enabled' if metadata.get('circuit_breaker_enabled', False) else 'Disabled'}"
                ],
                positive_signals=[],
                negative_signals=[],
                market_data=metadata,
                strategy_name=f"Intel_{self.intel_level}",
                lane_used='SMART',
                analysis_time_ms=100
            )
            
            logger.info(f"[THOUGHT] Logged: {action} for {token_symbol} ({confidence:.0f}% confidence)")
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to log thought: {e}")
    
    def _get_confidence_level(self, confidence: float) -> str:
        """Convert confidence percentage to level category."""
        if confidence >= 90:
            return 'VERY_HIGH'
        elif confidence >= 70:
            return 'HIGH'
        elif confidence >= 50:
            return 'MEDIUM'
        elif confidence >= 30:
            return 'LOW'
        else:
            return 'VERY_LOW'
    
    def _can_trade(self) -> bool:
        """
        Check if bot can execute a trade based on circuit breakers and limits.
        
        Returns:
            True if trading is allowed, False otherwise
        """
        try:
            # Check if circuit breaker is enabled
            if not self.circuit_breaker_enabled or not self.circuit_breaker_manager:
                return True
            
            # Check portfolio circuit breakers
            can_trade, reasons = self.circuit_breaker_manager.can_trade()
            if not can_trade:
                logger.warning(f"[CB] Trading blocked by circuit breaker: {', '.join(reasons)}")
                
                # Log blocked trade attempt
                self._log_thought(
                    action="BLOCKED",
                    reasoning=f"Trade blocked by circuit breaker: {', '.join(reasons)}. "
                             f"Safety mechanisms have triggered to protect the portfolio.",
                    confidence=100,
                    decision_type="RISK_MANAGEMENT",
                    metadata={
                        'circuit_breaker_reasons': reasons,
                        'consecutive_failures': self.consecutive_failures,
                        'daily_trades': self.daily_trades_count
                    }
                )
                return False
            
            # Check daily trade limit
            current_date = timezone.now().date()
            if self.last_trade_date != current_date:
                self.daily_trades_count = 0
                self.last_trade_date = current_date
            
            max_daily_trades = getattr(self.strategy_config, 'max_daily_trades', 20)
            if self.daily_trades_count >= max_daily_trades:
                logger.warning(f"[CB] Daily trade limit reached: {self.daily_trades_count}/{max_daily_trades}")
                return False
            
            # Check consecutive failures (bot-specific)
            max_consecutive_failures = 5
            if self.consecutive_failures >= max_consecutive_failures:
                logger.warning(f"[CB] Too many consecutive failures: {self.consecutive_failures}")
                return False
            
            # Check account balance minimum
            min_balance = Decimal('100')  # Minimum $100 to trade
            if self.account.current_balance_usd < min_balance:
                logger.warning(f"[CB] Insufficient balance: ${self.account.current_balance_usd:.2f}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"[CB] Error checking trade permission: {e}")
            return True  # Fail open if circuit breaker check fails
    
    def _execute_trade(self, decision: TradingDecision, token_symbol: str, current_price: Decimal):
        """
        Execute a paper trade with circuit breaker and Transaction Manager integration.
        
        Args:
            decision: Trading decision from intelligence engine
            token_symbol: Token to trade
            current_price: Current token price
        """
        try:
            # Check circuit breakers before executing
            if not self._can_trade():
                logger.info(f"[TRADE] Trade blocked for {token_symbol} - circuit breaker active")
                return
            
            # Check portfolio state for circuit breaker updates
            if self.circuit_breaker_enabled and self.circuit_breaker_manager:
                portfolio_state = self._get_portfolio_state()
                new_breakers = self.circuit_breaker_manager.check_circuit_breakers(portfolio_state)
                
                if new_breakers:
                    for breaker in new_breakers:
                        logger.warning(f"[CB] New circuit breaker triggered: {breaker.breaker_type.value}")
                        logger.warning(f"[CB] Reason: {breaker.description}")
                    
                    # Stop trading if new breakers triggered
                    return
            
            # Execute trade (existing logic)
            trade_success = False
            
            # Use Transaction Manager if enabled
            if self.use_tx_manager and self.tx_manager:
                trade_success = self._execute_trade_with_tx_manager(decision, token_symbol, current_price)
            else:
                trade_success = self._execute_trade_legacy(decision, token_symbol, current_price)
            
            # Update failure tracking
            if trade_success:
                self.consecutive_failures = 0
                self.daily_trades_count += 1
                logger.info(f"[TRADE] Successfully executed {decision.action} for {token_symbol}")
            else:
                self.consecutive_failures += 1
                logger.warning(f"[TRADE] Failed to execute {decision.action} for {token_symbol} "
                              f"(Consecutive failures: {self.consecutive_failures})")
                
                # Check if circuit breakers should trigger after failure
                if self.circuit_breaker_enabled and self.circuit_breaker_manager:
                    portfolio_state = self._get_portfolio_state()
                    self.circuit_breaker_manager.check_circuit_breakers(portfolio_state)
                    
        except Exception as e:
            logger.error(f"[ERROR] {decision.action} execution failed: {e}")
            self.consecutive_failures += 1
    
    def _execute_trade_with_tx_manager(self, decision: TradingDecision, 
                                       token_symbol: str, current_price: Decimal) -> bool:
        """
        Execute trade using Transaction Manager for gas optimization.
        
        Returns:
            True if trade was successful, False otherwise
        """
        logger.info(f"[TX MANAGER] Executing {decision.action} via Transaction Manager")
        
        async def execute_with_tx_manager():
            try:
                # Determine swap parameters based on decision
                if decision.action == 'BUY':
                    token_in = '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'  # USDC
                    token_out = decision.token_address
                    swap_type = SwapType.EXACT_TOKENS_FOR_TOKENS
                else:  # SELL
                    token_in = decision.token_address
                    token_out = '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'  # USDC
                    swap_type = SwapType.EXACT_TOKENS_FOR_TOKENS
                
                # Calculate amounts (in wei units for simulation)
                amount_in = int(decision.position_size_usd * 10**6)  # USDC has 6 decimals
                amount_out_min = int(amount_in * 0.99)  # 1% slippage tolerance
                
                # Determine gas strategy based on intel level
                if self.intel_level <= 3:
                    gas_strategy = TradingGasStrategy.COST_EFFICIENT
                elif self.intel_level >= 7:
                    gas_strategy = TradingGasStrategy.AGGRESSIVE
                else:
                    gas_strategy = TradingGasStrategy.BALANCED
                
                # Create transaction submission request
                tx_request = await create_transaction_submission_request(
                    user=self.account.user,
                    chain_id=self.chain_id,
                    token_in=token_in,
                    token_out=token_out,
                    amount_in=amount_in,
                    amount_out_minimum=amount_out_min,
                    swap_type=swap_type,
                    gas_strategy=gas_strategy,
                    is_paper_trade=True,  # Always paper trade
                    slippage_tolerance=Decimal('0.01')
                )
                
                # Submit transaction through Transaction Manager
                result = await self.tx_manager.submit_transaction(tx_request)
                
                if result.success:
                    # Check if circuit breaker was triggered
                    if result.circuit_breaker_triggered:
                        logger.warning(f"[CB] Trade blocked by TX Manager circuit breaker")
                        return False
                    
                    logger.info(f"[TX MANAGER] Transaction submitted: {result.transaction_id}")
                    
                    # Track pending transaction
                    self.pending_transactions[result.transaction_id] = {
                        'token_symbol': token_symbol,
                        'action': decision.action,
                        'amount': decision.position_size_usd,
                        'submitted_at': timezone.now()
                    }
                    
                    # Update gas savings tracking
                    if result.gas_savings_achieved:
                        self.total_gas_savings += result.gas_savings_achieved
                        self.trades_with_tx_manager += 1
                        avg_savings = self.total_gas_savings / self.trades_with_tx_manager
                        logger.info(f"[TX MANAGER] Gas saved: {result.gas_savings_achieved:.2f}% "
                                  f"(Average: {avg_savings:.2f}%)")
                    
                    # Create paper trade record
                    self._create_paper_trade_record(
                        decision, token_symbol, current_price,
                        transaction_id=result.transaction_id,
                        gas_savings=result.gas_savings_achieved
                    )
                    
                    # Update positions
                    self._update_positions_after_trade(decision, token_symbol, current_price)
                    
                    return True
                    
                else:
                    logger.error(f"[TX MANAGER] Transaction failed: {result.error_message}")
                    return False
                    
            except Exception as e:
                logger.error(f"[TX MANAGER] Error: {e}")
                return False
        
        # Execute async function and return result
        return async_to_sync(execute_with_tx_manager)()
    
    def _execute_trade_legacy(self, decision: TradingDecision, 
                             token_symbol: str, current_price: Decimal) -> bool:
        """
        Legacy trade execution without Transaction Manager.
        
        Returns:
            True if trade was successful, False otherwise
        """
        try:
            logger.info(f"[LEGACY] Executing {decision.action} without Transaction Manager")
            
            # Create paper trade record
            self._create_paper_trade_record(decision, token_symbol, current_price)
            
            # Update positions
            self._update_positions_after_trade(decision, token_symbol, current_price)
            
            logger.info(f"[TRADE] Executed {decision.action} for {token_symbol}: ${decision.position_size_usd:.2f}")
            return True
            
        except Exception as e:
            logger.error(f"[LEGACY] Trade execution failed: {e}")
            return False
    
    def _create_paper_trade_record(self, decision: TradingDecision, token_symbol: str, 
                                   current_price: Decimal, transaction_id: str = None,
                                   gas_savings: Decimal = None):
        """Create paper trade record in database."""
        trade = PaperTrade.objects.create(
            account=self.account,
            trade_type=decision.action.lower(),
            token_in_address='0x' + '0' * 40 if decision.action == 'BUY' else decision.token_address,
            token_in_symbol='USDC' if decision.action == 'BUY' else token_symbol,
            token_out_address=decision.token_address if decision.action == 'BUY' else '0x' + '0' * 40,
            token_out_symbol=token_symbol if decision.action == 'BUY' else 'USDC',
            amount_in=decision.position_size_usd,
            amount_out=decision.position_size_usd / current_price if decision.action == 'BUY' else decision.position_size_usd,
            amount_in_usd=decision.position_size_usd,
            amount_out_usd=decision.position_size_usd,
            price_per_token=current_price,
            gas_price_gwei=decision.max_gas_price_gwei,
            gas_used=21000,
            gas_cost_usd=Decimal('5') * (Decimal('1') - (gas_savings or Decimal('0')) / 100),
            slippage_percent=Decimal('1'),
            execution_time_ms=int(decision.processing_time_ms),
            status='SUCCESS',
            transaction_hash=transaction_id or ('0x' + uuid.uuid4().hex),
            block_number=1000000,
            dex_used='UNISWAP_V3',
            metadata={
                'intel_level': self.intel_level,
                'confidence': float(decision.overall_confidence),
                'risk_score': float(decision.risk_score),
                'strategy_name': f"Intel_{self.intel_level}",
                'tx_manager_used': self.use_tx_manager,
                'gas_savings_percent': float(gas_savings) if gas_savings else 0,
                'circuit_breaker_enabled': self.circuit_breaker_enabled
            }
        )
        return trade
    
    def _update_positions_after_trade(self, decision: TradingDecision, 
                                      token_symbol: str, current_price: Decimal):
        """Update positions after trade execution."""
        if decision.action == 'BUY':
            self._open_or_add_position(token_symbol, decision, current_price)
        else:
            self._close_or_reduce_position(token_symbol, decision, current_price)
        
        # Update account balance
        if decision.action == 'BUY':
            self.account.current_balance_usd -= decision.position_size_usd
        else:
            self.account.current_balance_usd += decision.position_size_usd
        self.account.save()
    
    def _open_or_add_position(self, token_symbol: str, decision: TradingDecision, 
                              current_price: Decimal):
        """Open new position or add to existing."""
        if token_symbol in self.positions:
            position = self.positions[token_symbol]
            position.quantity += decision.position_size_usd / current_price
            position.total_invested_usd += decision.position_size_usd
            position.average_entry_price_usd = position.total_invested_usd / position.quantity
            position.current_price_usd = current_price
            position.current_value_usd = position.quantity * current_price
            position.unrealized_pnl_usd = position.current_value_usd - position.total_invested_usd
            position.save()
        else:
            position = PaperPosition.objects.create(
                account=self.account,
                token_address=decision.token_address,
                token_symbol=token_symbol,
                quantity=decision.position_size_usd / current_price,
                average_entry_price_usd=current_price,
                current_price_usd=current_price,
                total_invested_usd=decision.position_size_usd,
                current_value_usd=decision.position_size_usd,
                unrealized_pnl_usd=Decimal('0'),
                is_open=True
            )
            self.positions[token_symbol] = position
    
    def _close_or_reduce_position(self, token_symbol: str, decision: TradingDecision,
                                  current_price: Decimal):
        """Close or reduce existing position."""
        if token_symbol in self.positions:
            position = self.positions[token_symbol]
            sell_quantity = min(position.quantity, decision.position_size_usd / current_price)
            
            position.quantity -= sell_quantity
            position.current_value_usd = position.quantity * current_price
            position.realized_pnl_usd += (sell_quantity * current_price) - (sell_quantity * position.average_entry_price_usd)
            
            if position.quantity <= 0:
                position.is_open = False
                position.closed_at = timezone.now()
                del self.positions[token_symbol]
            
            position.save()
    
    def reset_circuit_breakers(self, breaker_type: Optional[str] = None):
        """
        Reset circuit breakers for the bot.
        
        Args:
            breaker_type: Specific breaker type to reset, or None for all
        """
        try:
            if self.circuit_breaker_manager:
                if breaker_type:
                    from engine.portfolio import CircuitBreakerType
                    breaker_enum = CircuitBreakerType[breaker_type.upper()]
                    success = self.circuit_breaker_manager.manual_reset(breaker_enum)
                else:
                    success = self.circuit_breaker_manager.manual_reset()
                
                if success:
                    logger.info(f"[CB] Circuit breakers reset successfully")
                    self.consecutive_failures = 0
                    
                    # Log reset event
                    self._log_thought(
                        action="CB_RESET",
                        reasoning=f"Circuit breakers manually reset. Trading can resume normally.",
                        confidence=100,
                        decision_type="SYSTEM"
                    )
            
        except Exception as e:
            logger.error(f"[CB] Failed to reset circuit breakers: {e}")
    
    def _update_performance_metrics(self):
        """Update performance metrics for the session."""
        try:
            # Calculate metrics
            total_trades = PaperTrade.objects.filter(
                account=self.account,
                created_at__gte=self.session.started_at
            ).count()
            
            winning_trades = int(total_trades * 0.6)  # Simulated win rate
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            # Calculate gas savings metrics if TX Manager is used
            avg_gas_savings = (self.total_gas_savings / self.trades_with_tx_manager 
                              if self.trades_with_tx_manager > 0 else Decimal('0'))
            
            # Create or update metrics
            metrics, created = PaperPerformanceMetrics.objects.get_or_create(
                session=self.session,
                period_start=self.session.started_at,
                period_end=timezone.now(),
                defaults={
                    'total_trades': total_trades,
                    'winning_trades': winning_trades,
                    'losing_trades': total_trades - winning_trades,
                    'win_rate': Decimal(str(win_rate)),
                    'total_pnl_usd': self.account.current_balance_usd - self.session.starting_balance_usd,
                    'total_pnl_percent': ((self.account.current_balance_usd / self.session.starting_balance_usd) - 1) * 100 if self.session.starting_balance_usd > 0 else 0,
                    'avg_win_usd': Decimal('0'),
                    'avg_loss_usd': Decimal('0'),
                    'largest_win_usd': Decimal('0'),
                    'largest_loss_usd': Decimal('0'),
                    'sharpe_ratio': None,
                    'max_drawdown_percent': Decimal('0'),
                    'profit_factor': None,
                    'avg_execution_time_ms': 100,
                    'total_gas_fees_usd': Decimal('5') * total_trades * (Decimal('1') - avg_gas_savings / 100),
                    'avg_slippage_percent': Decimal('1'),
                    'fast_lane_trades': 0,
                    'smart_lane_trades': total_trades,
                    'fast_lane_win_rate': Decimal('0'),
                    'smart_lane_win_rate': Decimal(str(win_rate))
                }
            )
            
            if not created:
                metrics.total_trades = total_trades
                metrics.winning_trades = winning_trades
                metrics.losing_trades = total_trades - winning_trades
                metrics.win_rate = Decimal(str(win_rate))
                metrics.total_pnl_usd = self.account.current_balance_usd - self.session.starting_balance_usd
                metrics.total_pnl_percent = ((self.account.current_balance_usd / self.session.starting_balance_usd) - 1) * 100 if self.session.starting_balance_usd > 0 else 0
                metrics.total_gas_fees_usd = Decimal('5') * total_trades * (Decimal('1') - avg_gas_savings / 100)
                metrics.save()
            
            # Log TX Manager performance if enabled
            if self.use_tx_manager and self.trades_with_tx_manager > 0:
                logger.info(f"[TX MANAGER] Performance: {self.trades_with_tx_manager} trades, "
                          f"Avg gas savings: {avg_gas_savings:.2f}%")
                
        except Exception as e:
            logger.error(f"[ERROR] Failed to update performance metrics: {e}")
    
    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals."""
        logger.info("[SHUTDOWN] Received shutdown signal")
        self.running = False
    
    def _cleanup(self):
        """Clean up on exit."""
        try:
            if self.session:
                self.session.status = 'STOPPED'
                self.session.ended_at = timezone.now()
                self.session.ending_balance_usd = self.account.current_balance_usd
                self.session.session_pnl_usd = self.account.current_balance_usd - self.session.starting_balance_usd
                self.session.save()
            
            # Log final TX Manager stats if enabled
            if self.use_tx_manager and self.trades_with_tx_manager > 0:
                avg_savings = self.total_gas_savings / self.trades_with_tx_manager
                logger.info(f"[TX MANAGER] Final Stats: {self.trades_with_tx_manager} trades executed")
                logger.info(f"[TX MANAGER] Total gas savings: {self.total_gas_savings:.2f}%")
                logger.info(f"[TX MANAGER] Average gas savings per trade: {avg_savings:.2f}%")
            
            # Log final circuit breaker stats if enabled
            if self.circuit_breaker_enabled:
                logger.info(f"[CB] Final Stats: {self.daily_trades_count} trades today")
                logger.info(f"[CB] Consecutive failures at shutdown: {self.consecutive_failures}")
                
            logger.info("[CLEANUP] Bot shutdown complete")
        except Exception as e:
            logger.error(f"[ERROR] Cleanup failed: {e}")


def main():
    """Main entry point for the bot."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Enhanced Paper Trading Bot with TX Manager and Circuit Breakers')
    parser.add_argument('--account', default='AI_Paper_Bot', help='Account name (default: AI_Paper_Bot)')
    parser.add_argument('--intel', type=int, default=5, choices=range(1, 11), help='Intelligence level 1-10 (default: 5 - Balanced)')
    parser.add_argument('--tick-interval', type=int, default=15, help='Seconds between market ticks (default: 15)')
    parser.add_argument('--disable-circuit-breaker', action='store_true', help='Disable circuit breaker protection')
    
    args = parser.parse_args()
    
    print("\n╔════════════════════════════════════════════════════════════════════╗")
    print("║  ENHANCED PAPER TRADING BOT - INTEL + TX MANAGER + CIRCUIT BREAKERS ║")
    print("╚════════════════════════════════════════════════════════════════════╝\n")
    
    # Intelligence level descriptions
    intel_descriptions = {
        1: "ULTRA CONSERVATIVE - Maximum caution",
        2: "VERY CONSERVATIVE - High caution",
        3: "CONSERVATIVE - Careful approach",
        4: "CAUTIOUS - Below average risk",
        5: "BALANCED - Equal risk/reward consideration",
        6: "MODERATE - Slightly aggressive",
        7: "AGGRESSIVE - Higher risk tolerance",
        8: "VERY AGGRESSIVE - Significant risks",
        9: "ULTRA AGGRESSIVE - Maximum risk",
        10: "YOLO MODE - No risk limits"
    }
    
    print(f"INTELLIGENCE LEVEL: ⚖️  Level {args.intel}: {intel_descriptions[args.intel].upper()}")
    print(f"✅ Using account: {args.account}")
    
    # Transaction Manager is always enabled when available
    if TRANSACTION_MANAGER_AVAILABLE:
        print("⚡ TRANSACTION MANAGER: ENABLED - Gas optimization active (targeting 23.1% savings)")
    else:
        print("⚠️  TRANSACTION MANAGER: NOT AVAILABLE - Required modules not installed")
    
    # Circuit Breaker status
    if not args.disable_circuit_breaker and CIRCUIT_BREAKER_AVAILABLE:
        print("🛡️  CIRCUIT BREAKERS: ENABLED - Risk protection active")
    else:
        print("⚠️  CIRCUIT BREAKERS: DISABLED - Trading without protection")
    
    print("")
    
    bot = EnhancedPaperTradingBot(
        account_name=args.account,
        intel_level=args.intel
    )
    
    if args.disable_circuit_breaker:
        bot.circuit_breaker_enabled = False
    
    bot.tick_interval = args.tick_interval
    
    print("=" * 60)
    print("📋 BOT CONFIGURATION")
    print("=" * 60)
    print(f"  Account         : {args.account}")
    
    if bot.initialize():
        print(f"  User            : {bot.account.user.username}")
        print(f"  Balance         : ${bot.account.current_balance_usd:,.2f}")
        print(f"  Tick Interval   : {args.tick_interval} seconds\n")
        print(f"  INTELLIGENCE    : Level {args.intel}/10")
        print("  Controlled by Intel Level:")
        print(f"    • Risk Tolerance    : {bot.intelligence_engine.config.risk_tolerance}%")
        print(f"    • Max Position Size : {bot.intelligence_engine.config.max_position_size:.1f}%")
        print(f"    • Trade Frequency   : {bot.intelligence_engine.config.trade_frequency.value}")
        print(f"    • Gas Strategy      : {bot.intelligence_engine.config.gas_strategy.value}")
        print(f"    • MEV Protection    : {'Always On' if bot.intelligence_engine.config.use_mev_protection else 'Off'}")
        print(f"    • Decision Speed    : {bot.intelligence_engine.config.decision_speed.value}")
        
        if bot.use_tx_manager:
            print("\n  TRANSACTION MANAGER:")
            print("    • Gas Optimization  : ACTIVE")
            print("    • Target Savings    : 23.1%")
            print("    • Status Tracking   : REAL-TIME")
            print("    • WebSocket Updates : ENABLED")
        
        if bot.circuit_breaker_enabled:
            print("\n  CIRCUIT BREAKERS:")
            print("    • Portfolio Loss    : ACTIVE")
            print("    • Daily Loss Limit  : ACTIVE")
            print("    • Consecutive Fails : ACTIVE (Max: 5)")
            print("    • Daily Trade Limit : 20 trades")
            print("    • Min Balance Check : $100")
        
        print("=" * 60)
        
        print("\n🤖 Initializing bot for account:", args.account)
        print("✅ Bot initialized successfully\n")
        print("🏃 Bot is running... Press Ctrl+C to stop\n")
        
        bot.run()
    else:
        print("❌ Failed to initialize bot")
        sys.exit(1)


if __name__ == "__main__":
    main()