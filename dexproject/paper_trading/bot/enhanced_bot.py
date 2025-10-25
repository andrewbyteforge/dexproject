"""
Enhanced Paper Trading Bot - Main Orchestrator

This is the main bot class that coordinates all paper trading operations,
integrating the Intel Slider system, Transaction Manager, Circuit Breakers,
and real price feeds.

This module orchestrates:
- Bot initialization and setup
- Session and account management
- Intelligence engine coordination
- Main run loop with signal handling
- Graceful shutdown and cleanup

File: dexproject/paper_trading/bot/enhanced_bot.py
"""

# ============================================================================
# WINDOWS CONSOLE ENCODING FIX
# ============================================================================
import sys
import io

# Force UTF-8 encoding for Windows console to support emoji logging
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer,
        encoding='utf-8',
        errors='replace',
        line_buffering=True
    )
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer,
        encoding='utf-8',
        errors='replace',
        line_buffering=True
    )

import os
import time
import signal
import logging
import json
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
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
from django.contrib.auth.models import User
from asgiref.sync import async_to_sync

# ============================================================================
# MODEL IMPORTS
# ============================================================================
from paper_trading.models import (
    PaperTradingAccount,
    PaperTradingSession,
    PaperStrategyConfiguration
)

# ============================================================================
# BOT MODULE IMPORTS
# ============================================================================
from paper_trading.bot.price_service_integration import (
    create_price_manager,
    RealPriceManager
)
from paper_trading.bot.position_manager import PositionManager
from paper_trading.bot.trade_executor import TradeExecutor
from paper_trading.bot.market_analyzer import MarketAnalyzer

# ============================================================================
# INTELLIGENCE SYSTEM IMPORTS
# ============================================================================
from paper_trading.intelligence.intel_slider import IntelSliderEngine
from paper_trading.intelligence.base import IntelligenceLevel

# ============================================================================
# CIRCUIT BREAKER IMPORTS (Optional)
# ============================================================================
try:
    from engine.portfolio import CircuitBreakerManager
    CIRCUIT_BREAKER_AVAILABLE = True
except ImportError:
    CircuitBreakerManager = None  # type: ignore
    CIRCUIT_BREAKER_AVAILABLE = False

# ============================================================================
# TRANSACTION MANAGER IMPORTS (Optional)
# ============================================================================
try:
    from trading.services.transaction_manager import get_transaction_manager
    TRANSACTION_MANAGER_AVAILABLE = True
except ImportError:
    get_transaction_manager = None  # type: ignore
    TRANSACTION_MANAGER_AVAILABLE = False

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('paper_trading_bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


# =============================================================================
# ENHANCED PAPER TRADING BOT CLASS
# =============================================================================

class EnhancedPaperTradingBot:
    """
    Unified Paper Trading Bot with Intel Slider System, Transaction Manager,
    Circuit Breakers, and Real Price Feeds.
    
    This is the main orchestrator that coordinates all bot operations by
    delegating responsibilities to specialized managers:
    - PriceServiceIntegration: Real-time price feeds
    - PositionManager: Position lifecycle management
    - TradeExecutor: Trade execution and logging
    - MarketAnalyzer: Market analysis and tick coordination
    
    Example usage:
        bot = EnhancedPaperTradingBot(
            account_name='AI_Paper_Bot',
            intel_level=5
        )
        
        if bot.initialize():
            bot.run()
    """
    
    def __init__(
        self,
        account_name: str,
        intel_level: int = 5,
        use_real_prices: bool = True,
        chain_id: int = 84532  # Base Sepolia default
    ):
        """
        Initialize the enhanced paper trading bot.
        
        Args:
            account_name: Name of the paper trading account
            intel_level: Intelligence level (1-10)
            use_real_prices: Whether to use real price feeds
            chain_id: Blockchain network ID for price fetching
        """
        self.account_name = account_name
        self.intel_level = intel_level
        self.use_real_prices = use_real_prices
        self.chain_id = chain_id
        
        # Core components (initialized in initialize())
        self.account: Optional[PaperTradingAccount] = None
        self.session: Optional[PaperTradingSession] = None
        self.strategy_config: Optional[PaperStrategyConfiguration] = None
        
        # Manager instances
        self.price_manager: Optional[RealPriceManager] = None
        self.position_manager: Optional[PositionManager] = None
        self.trade_executor: Optional[TradeExecutor] = None
        self.market_analyzer: Optional[MarketAnalyzer] = None
        
        # Intelligence engine
        self.intelligence_engine: Optional[IntelSliderEngine] = None
        
        # Circuit breaker
        self.circuit_breaker_manager: Optional[Any] = None
        self.circuit_breaker_enabled = CIRCUIT_BREAKER_AVAILABLE
        
        # Transaction Manager
        self.use_tx_manager = TRANSACTION_MANAGER_AVAILABLE
        
        # Control flags
        self.running = False
        self.tick_interval = 15  # seconds between market checks
        
        log_msg = f"[BOT] Enhanced Paper Trading Bot initialized with Intel Level {intel_level}"
        if self.use_tx_manager:
            log_msg += " (Transaction Manager ENABLED - Gas Optimization Active)"
        else:
            log_msg += " (Transaction Manager DISABLED - Legacy Mode)"
        if self.circuit_breaker_enabled:
            log_msg += " (Circuit Breakers ENABLED - Risk Protection Active)"
        if use_real_prices:
            log_msg += f" (REAL PRICE FEEDS - Chain ID: {chain_id})"
        else:
            log_msg += " (MOCK PRICE SIMULATION)"
        
        logger.info(log_msg)
    
    # =========================================================================
    # INITIALIZATION
    # =========================================================================
    
    def initialize(self) -> bool:
        """
        Initialize bot components and connections.
        
        Returns:
            True if initialization successful
        """
        try:
            logger.info("[BOT] Starting initialization...")
            
            # Step 1: Load or create account
            self._load_account()
            assert self.account is not None, "Account initialization failed"
            
            # Step 2: Create trading session
            self._create_session()
            assert self.session is not None, "Session initialization failed"
            
            # Step 3: Clean up duplicates AFTER session is created
            self._cleanup_duplicate_accounts()
            
            # Step 4: Initialize intelligence engine
            self._initialize_intelligence()
            assert self.intelligence_engine is not None, "Intelligence engine initialization failed"
            
            # Step 5: Setup strategy configuration
            self._setup_strategy_configuration()
            assert self.strategy_config is not None, "Strategy configuration initialization failed"
            
            # Step 6: Initialize circuit breaker manager
            self._initialize_circuit_breaker()
            
            # Step 7: Initialize price manager
            self._initialize_price_manager()
            assert self.price_manager is not None, "Price manager initialization failed"
            
            # Step 8: Initialize position manager
            self._initialize_position_manager()
            assert self.position_manager is not None, "Position manager initialization failed"
            
            # Step 9: Initialize trade executor
            self._initialize_trade_executor()
            assert self.trade_executor is not None, "Trade executor initialization failed"
            
            # Step 10: Initialize market analyzer
            self._initialize_market_analyzer()
            assert self.market_analyzer is not None, "Market analyzer initialization failed"
            
            # Step 11: Log initial thought
            self._log_startup_thought()
            
            logger.info("[BOT] ✅ Initialization complete!")
            return True
            
        except Exception as e:
            logger.error(f"[BOT] ❌ Initialization failed: {e}", exc_info=True)
            return False
    
    def _load_account(self) -> None:
        """
        Load the single paper trading account for this user.
        Always uses the same account regardless of parameters.
        """
        # Always use the same user
        user, _ = User.objects.get_or_create(
            username='demo_user',
            defaults={'email': 'demo@example.com'}
        )
        
        # Get the first existing account for this user, or create one
        existing_accounts = PaperTradingAccount.objects.filter(
            user=user
        ).order_by('created_at')
        
        if existing_accounts.exists():
            # Always use the first (oldest) account
            self.account = existing_accounts.first()
            assert self.account is not None, "Failed to retrieve account from database"
            
            logger.info(
                f"[ACCOUNT] Using existing account: {self.account.name} "
                f"(ID: {self.account.account_id})"
            )
            
            # Only log duplicates, don't delete them yet
            if existing_accounts.count() > 1:
                logger.info(
                    f"[ACCOUNT] Found {existing_accounts.count() - 1} "
                    f"duplicate accounts (will clean up later)"
                )
        else:
            # Create the one and only account
            self.account = PaperTradingAccount.objects.create(
                name='My_Trading_Account',
                user=user,
                current_balance_usd=Decimal('10000'),
                initial_balance_usd=Decimal('10000')
            )
            logger.info(
                f"[ACCOUNT] Created new account: {self.account.name} "
                f"(ID: {self.account.account_id})"
            )
        
        logger.info(f"[ACCOUNT] Balance: ${self.account.current_balance_usd:,.2f}")
        
        # Override the account_name to match what we're actually using
        self.account_name = self.account.name
    
    def _cleanup_duplicate_accounts(self) -> None:
        """Clean up duplicate accounts AFTER session is created successfully."""
        assert self.account is not None, "Account must be initialized before cleanup"
        
        try:
            user = User.objects.get(username='demo_user')
            
            existing_accounts = PaperTradingAccount.objects.filter(
                user=user
            ).order_by('created_at')
            
            if existing_accounts.count() > 1:
                # Keep the first (oldest) account, delete the rest
                duplicates = existing_accounts[1:]
                for dup in duplicates:
                    # Make sure it's not the active account
                    if dup.account_id != self.account.account_id:
                        logger.warning(
                            f"[ACCOUNT] Cleaning up duplicate account: {dup.name} "
                            f"(ID: {dup.account_id})"
                        )
                        dup.delete()
                logger.info(
                    f"[ACCOUNT] Cleaned up {len(duplicates)} duplicate accounts"
                )
        except Exception as e:
            logger.error(f"[ACCOUNT] Error cleaning up duplicates: {e}")
    
    def _create_session(self) -> None:
        """
        Create or resume a trading session for today.
        Only one active session per day is allowed.
        """
        assert self.account is not None, "Account must be initialized before creating session"
        
        def json_safe(data: Any) -> Any:
            """Recursively convert non-serializable types to safe formats."""
            if isinstance(data, dict):
                return {k: json_safe(v) for k, v in data.items()}
            if isinstance(data, list):
                return [json_safe(v) for v in data]
            if isinstance(data, uuid.UUID):
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
            assert self.session is not None, "Failed to retrieve session from database"
            
            logger.info(
                f"[SESSION] Resuming existing session from today: "
                f"{self.session.session_id}"
            )
            logger.info(
                f"[SESSION] Session started at: "
                f"{self.session.started_at.strftime('%H:%M:%S')}"
            )
            
            # Update session config to reflect current bot settings
            config_snapshot = {
                "bot_version": "3.0.0",
                "intel_level": self.intel_level,
                "account_name": self.account_name,
                "account_id": str(self.account.account_id),
                "session_uuid": str(self.session.session_id),
                "user_id": str(self.account.user.id),  # type: ignore[attr-defined]
                "transaction_manager_enabled": self.use_tx_manager,
                "circuit_breaker_enabled": self.circuit_breaker_enabled,
                "use_real_prices": self.use_real_prices,
                "chain_id": self.chain_id,
                "resumed_at": timezone.now().isoformat()
            }
            
            # Store config in metadata instead of config_snapshot
            if not self.session.metadata:
                self.session.metadata = {}
            self.session.metadata.update(json_safe(config_snapshot))
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
                old_session.stopped_at = timezone.now()
                
                # Store ending balance and P&L in metadata
                if not old_session.metadata:
                    old_session.metadata = {}
                    
                old_session.metadata['ending_balance_usd'] = float(self.account.current_balance_usd)
                
                # Calculate P&L using starting balance from metadata
                starting_balance = old_session.metadata.get('starting_balance_usd', 0)
                session_pnl = float(self.account.current_balance_usd) - starting_balance
                old_session.metadata['session_pnl_usd'] = session_pnl
                
                old_session.save()
                logger.info(
                    f"[SESSION] Closed old session from "
                    f"{old_session.started_at.date()}: {old_session.session_id}"
                )
            
            # Create new session for today
            config_snapshot = {
                "bot_version": "3.0.0",
                "intel_level": self.intel_level,
                "account_name": self.account_name,
                "account_id": str(self.account.account_id),
                "session_uuid": str(uuid.uuid4()),
                "user_id": str(self.account.user.id),  # type: ignore[attr-defined]
                "transaction_manager_enabled": self.use_tx_manager,
                "circuit_breaker_enabled": self.circuit_breaker_enabled,
                "use_real_prices": self.use_real_prices,
                "chain_id": self.chain_id
            }
            
            safe_snapshot = json_safe(config_snapshot)
            
            session_name = (
                f"Bot_Session_{today.strftime('%Y%m%d')}_Intel_{self.intel_level}"
            )
            
            self.session = PaperTradingSession.objects.create(
                account=self.account,
                status="RUNNING",
                metadata={  # Store everything in metadata
                    'session_name': session_name,
                    'starting_balance_usd': float(self.account.current_balance_usd),
                    **safe_snapshot  # Merge config into metadata
                }
            )
            logger.info(
                f"[SESSION] Created new session for today: {self.session.session_id}"
            )
            logger.info(f"[SESSION] Session name: {session_name}")
    
    def _initialize_intelligence(self) -> None:
        """Initialize the intelligence engine."""
        assert self.account is not None, "Account must be initialized before intelligence engine"
        
        active_config = PaperStrategyConfiguration.objects.filter(
            account=self.account,
            is_active=True
        ).first()
        
        self.intelligence_engine = IntelSliderEngine(
            intel_level=self.intel_level,
            account_id=str(self.account.account_id),
            strategy_config=active_config
        )
        logger.info(
            f"[INTEL] Intelligence Engine initialized at Level {self.intel_level}"
        )
    
    def _setup_strategy_configuration(self) -> None:
        """Set up or load a valid PaperStrategyConfiguration for this account."""
        assert self.account is not None, "Account must be initialized before strategy config"
        assert self.intelligence_engine is not None, "Intelligence engine must be initialized before strategy config"
        
        def json_safe(value: Any) -> Any:
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
            
            max_pos_size = getattr(
                config,
                "max_position_percent",  # ✅ FIXED
                getattr(config, "max_position_size_percent", 10)
            )
            confidence_threshold = getattr(config, "confidence_threshold", 60)
            risk_tolerance = getattr(config, "risk_tolerance", 50)
            trade_freq = getattr(
                getattr(config, "trade_frequency", None),
                "value",
                "Moderate"
            )
            
            custom_parameters = {
                "intel_level": self.intel_level,
                "use_tx_manager": self.use_tx_manager,
                "circuit_breaker_enabled": self.circuit_breaker_enabled,
                "use_real_prices": self.use_real_prices,
                "chain_id": self.chain_id,
                "intel_config_summary": {
                    "risk_tolerance": risk_tolerance,
                    "trade_frequency": trade_freq,
                    "max_position_size": float(max_pos_size),
                    "confidence_threshold": float(confidence_threshold),
                },
            }
            
            custom_parameters = json_safe(custom_parameters)
            
            # Token list for allowed tokens
            token_addresses = [
                '0x4200000000000000000000000000000000000006',  # WETH
                '0x036CbD53842c5426634e7929541eC2318f3dCF7e',  # USDC
                '0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb',  # DAI
            ]
            
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
                    "allowed_tokens": token_addresses,
                    "blocked_tokens": [],
                    "custom_parameters": custom_parameters,
                },
            )
            
            if not created:
                strategy_config.custom_parameters = custom_parameters
                strategy_config.save()
            
            logger.info(
                f"[CONFIG] Strategy configuration "
                f"{'created' if created else 'updated'}"
            )
            self.strategy_config = strategy_config
            
        except Exception as e:
            logger.error(
                f"[CONFIG] Failed to setup strategy configuration: {e}",
                exc_info=True
            )
            raise
    
    def _initialize_circuit_breaker(self) -> None:
        """Initialize circuit breaker manager for risk management."""
        if not CIRCUIT_BREAKER_AVAILABLE or CircuitBreakerManager is None:
            self.circuit_breaker_enabled = False
            return
        
        try:
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
    
    def _initialize_price_manager(self) -> None:
        """Initialize the price manager for real/mock price feeds."""
        try:
            self.price_manager = create_price_manager(
                use_real_prices=self.use_real_prices,
                chain_id=self.chain_id
            )
            logger.info(
                f"[PRICE] Price manager initialized: "
                f"Mode={'REAL' if self.use_real_prices else 'MOCK'}, "
                f"Chain={self.chain_id}"
            )
        except Exception as e:
            logger.error(f"[PRICE] Failed to initialize price manager: {e}")
            raise
    
    def _initialize_position_manager(self) -> None:
        """Initialize the position manager."""
        assert self.account is not None, "Account must be initialized before position manager"
        assert self.strategy_config is not None, "Strategy config must be initialized before position manager"
        
        try:
            self.position_manager = PositionManager(
                account=self.account,
                strategy_config=self.strategy_config
            )
            self.position_manager.load_positions()
            logger.info("[POSITION] Position manager initialized")
        except Exception as e:
            logger.error(f"[POSITION] Failed to initialize position manager: {e}")
            raise
    
    def _initialize_trade_executor(self) -> None:
        """Initialize the trade executor."""
        assert self.account is not None, "Account must be initialized before trade executor"
        assert self.session is not None, "Session must be initialized before trade executor"
        assert self.strategy_config is not None, "Strategy config must be initialized before trade executor"
        
        try:
            self.trade_executor = TradeExecutor(
                account=self.account,
                session=self.session,
                strategy_config=self.strategy_config,
                intel_level=self.intel_level,
                use_tx_manager=self.use_tx_manager,
                circuit_breaker_manager=self.circuit_breaker_manager,
                chain_id=self.chain_id
            )
            
            # Initialize Transaction Manager if enabled
            if self.use_tx_manager and get_transaction_manager is not None:
                async def init_tx_manager() -> bool:
                    # Type guard for async function closure
                    if self.trade_executor is None:
                        return False
                    
                    self.trade_executor.tx_manager = await get_transaction_manager(  # type: ignore[assignment]
                        self.chain_id
                    )
                    return self.trade_executor.tx_manager is not None
                
                success = async_to_sync(init_tx_manager)()
                
                if success:
                    logger.info(
                        "[TX MANAGER] Transaction Manager initialized successfully"
                    )
                    logger.info(
                        "[TX MANAGER] Gas optimization enabled - targeting 23.1% savings"
                    )
                else:
                    logger.warning(
                        "[TX MANAGER] Failed to initialize - falling back to legacy mode"
                    )
                    self.use_tx_manager = False
            
            logger.info("[TRADE] Trade executor initialized")
        except Exception as e:
            logger.error(f"[TRADE] Failed to initialize trade executor: {e}")
            raise
    
    def _initialize_market_analyzer(self) -> None:
        """Initialize the market analyzer."""
        assert self.account is not None, "Account must be initialized before market analyzer"
        assert self.session is not None, "Session must be initialized before market analyzer"
        assert self.intelligence_engine is not None, "Intelligence engine must be initialized before market analyzer"
        assert self.strategy_config is not None, "Strategy config must be initialized before market analyzer"
        
        try:
            self.market_analyzer = MarketAnalyzer(
                account=self.account,
                session=self.session,
                intelligence_engine=self.intelligence_engine,
                strategy_config=self.strategy_config,
                circuit_breaker_manager=self.circuit_breaker_manager,
                use_tx_manager=self.use_tx_manager
            )
            self.market_analyzer.tick_interval = self.tick_interval
            logger.info("[MARKET] Market analyzer initialized")
        except Exception as e:
            logger.error(f"[MARKET] Failed to initialize market analyzer: {e}")
            raise
    
    def _log_startup_thought(self) -> None:
        """
        Log a startup thought to track bot initialization.
        
        This creates a thought log entry documenting the bot's configuration
        and initialization parameters for auditing and debugging purposes.
        """
        assert self.account is not None, "Account must be initialized before logging startup thought"
        assert self.intelligence_engine is not None, "Intelligence engine must be initialized before logging startup thought"
        
        try:
            from paper_trading.models import PaperAIThoughtLog
            
            # Build reasoning text
            reasoning = (
                f"Bot initialized with Intel Level {self.intel_level}. "
                f"Strategy: {self.intelligence_engine.config.name}. "
                f"Risk tolerance: {self.intelligence_engine.config.risk_tolerance}%. "
                f"Transaction Manager: {'ENABLED' if self.use_tx_manager else 'DISABLED'}. "
                f"Circuit Breakers: {'ENABLED' if self.circuit_breaker_enabled else 'DISABLED'}. "
                f"Price Feeds: {'REAL' if self.use_real_prices else 'MOCK'}. "
                f"Starting balance: ${self.account.current_balance_usd:.2f}"
            )
            
            # Build market data with all metrics
            market_data = {
                'intel_level': self.intel_level,
                'tx_manager_enabled': self.use_tx_manager,
                'circuit_breaker_enabled': self.circuit_breaker_enabled,
                'use_real_prices': self.use_real_prices,
                'starting_balance': float(self.account.current_balance_usd),
                'risk_score': 0,  # No risk at startup
                'opportunity_score': 100,  # Full opportunity ahead
                'confidence': 100,  # High confidence in configuration
                'event_type': 'BOT_STARTUP'
            }
            
            # Create thought log with CORRECT field names
            PaperAIThoughtLog.objects.create(
                account=self.account,
                paper_trade=None,
                decision_type='SKIP',  # System event, not a trade
                token_address='0x' + '0' * 40,  # System address
                token_symbol='SYSTEM',
                confidence_level=Decimal('100'),  # FIXED: Use Decimal, not string
                reasoning=reasoning[:500],  # FIXED: Use 'reasoning', not 'primary_reasoning'
                risk_assessment="Risk Score: 0, Opportunity Score: 100 - Bot startup with optimal configuration",  
                key_factors=[
                    f"Intel Level: {self.intel_level}",
                    f"TX Manager: {'Enabled' if self.use_tx_manager else 'Disabled'}",
                    f"Circuit Breaker: {'Enabled' if self.circuit_breaker_enabled else 'Disabled'}",
                    f"Price Feeds: {'Real' if self.use_real_prices else 'Mock'}",
                    f"Starting Balance: ${self.account.current_balance_usd:.2f}"
                ],
                positive_signals=[
                    "Bot successfully initialized",
                    "All systems operational",
                    "Configuration validated"
                ],
                negative_signals=[],
                market_data=market_data
            )
            
            logger.info("[THOUGHT] Startup thought logged successfully")
            
        except Exception as e:
            logger.error(f"[THOUGHT] Failed to log startup thought: {e}", exc_info=True)
    
    # =========================================================================
    # MAIN RUN LOOP
    # =========================================================================
    
    def run(self) -> None:
        """
        Main bot run loop - handles signals and coordinates market ticks.
        
        This method runs the main bot loop, coordinating all managers
        and handling graceful shutdown on interrupt signals.
        """
        # Type guards for components that must be initialized
        assert self.price_manager is not None, "Price manager must be initialized before running"
        assert self.position_manager is not None, "Position manager must be initialized before running"
        assert self.trade_executor is not None, "Trade executor must be initialized before running"
        assert self.market_analyzer is not None, "Market analyzer must be initialized before running"
        
        # Setup signal handlers for graceful shutdown
        def signal_handler(signum: int, frame: Any) -> None:
            """Handle shutdown signals gracefully."""
            logger.info(f"[BOT] Received signal {signum} - initiating graceful shutdown...")
            self.running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        self.running = True
        logger.info("[BOT] Starting main run loop...")
        
        try:
            while self.running:
                # Run one market tick
                self.market_analyzer.tick(
                    price_manager=self.price_manager,
                    position_manager=self.position_manager,
                    trade_executor=self.trade_executor
                )
                
                # Sleep for tick interval
                if self.running:
                    time.sleep(self.tick_interval)
        
        except KeyboardInterrupt:
            logger.info("[BOT] Keyboard interrupt received - shutting down...")
        except Exception as e:
            logger.error(f"[BOT] Error in main run loop: {e}", exc_info=True)
        finally:
            self.cleanup()
    
    # =========================================================================
    # CLEANUP AND SHUTDOWN
    # =========================================================================
    
    def cleanup(self) -> None:
        """
        Cleanup bot resources and finalize session.
        
        This method handles graceful shutdown, closing all connections
        and finalizing session data.
        """
        try:
            logger.info("[CLEANUP] Starting bot cleanup...")
            self.running = False
            
            # Finalize session if it exists
            if self.session and self.account:
                self.session.status = 'STOPPED'
                self.session.stopped_at = timezone.now()
                
                # Store ending balance and P&L in metadata
                if not self.session.metadata:
                    self.session.metadata = {}
                    
                self.session.metadata['ending_balance_usd'] = float(self.account.current_balance_usd)
                
                # Calculate P&L using starting balance from metadata
                starting_balance = self.session.metadata.get('starting_balance_usd', 0)
                session_pnl = float(self.account.current_balance_usd) - starting_balance
                self.session.metadata['session_pnl_usd'] = session_pnl
                
                self.session.save()
            
            # Log final TX Manager stats if enabled
            if self.trade_executor and self.use_tx_manager and hasattr(
                    self.trade_executor, 'trades_with_tx_manager') and self.trade_executor.trades_with_tx_manager > 0:
                avg_savings = (
                    self.trade_executor.total_gas_savings /
                    self.trade_executor.trades_with_tx_manager
                )
                logger.info(
                    f"[TX MANAGER] Final Stats: "
                    f"{self.trade_executor.trades_with_tx_manager} trades executed"
                )
                logger.info(
                    f"[TX MANAGER] Total gas savings: "
                    f"{self.trade_executor.total_gas_savings:.2f}%"
                )
                logger.info(
                    f"[TX MANAGER] Average gas savings per trade: "
                    f"{avg_savings:.2f}%"
                )
            
            # Log final circuit breaker stats if enabled
            if self.trade_executor and self.circuit_breaker_enabled and hasattr(self.trade_executor, 'daily_trades_count'):
                logger.info(
                    f"[CB] Final Stats: "
                    f"{self.trade_executor.daily_trades_count} trades today"
                )
                logger.info(
                    f"[CB] Consecutive failures at shutdown: "
                    f"{self.trade_executor.consecutive_failures}"
                )
            
            # Close price manager
            if self.price_manager:
                async_to_sync(self.price_manager.close)()
            
            logger.info("[CLEANUP] Bot shutdown complete")
        except Exception as e:
            logger.error(f"[ERROR] Cleanup failed: {e}")


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def main() -> None:
    """Main entry point for the bot."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Enhanced Paper Trading Bot v3.0 with Real Price Feeds'
    )
    parser.add_argument(
        '--account',
        default='AI_Paper_Bot',
        help='Account name (default: AI_Paper_Bot)'
    )
    parser.add_argument(
        '--intel',
        type=int,
        default=5,
        choices=range(1, 11),
        help='Intelligence level 1-10 (default: 5 - Balanced)'
    )
    parser.add_argument(
        '--tick-interval',
        type=int,
        default=15,
        help='Seconds between market ticks (default: 15)'
    )
    parser.add_argument(
        '--disable-circuit-breaker',
        action='store_true',
        help='Disable circuit breaker protection'
    )
    parser.add_argument(
        '--use-mock-prices',
        action='store_true',
        help='Use mock price simulation instead of real prices'
    )
    parser.add_argument(
        '--chain-id',
        type=int,
        default=84532,
        help='Blockchain network ID (default: 84532 - Base Sepolia)'
    )
    
    args = parser.parse_args()
    
    print("\n╔════════════════════════════════════════════════════════════════════╗")
    print("║     ENHANCED PAPER TRADING BOT v3.0 - WITH REAL PRICE FEEDS       ║")
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
    print(f"💰 Price Mode: {'MOCK SIMULATION' if args.use_mock_prices else 'REAL BLOCKCHAIN DATA'}")
    
    if not args.use_mock_prices:
        chain_names = {
            1: "Ethereum Mainnet",
            8453: "Base Mainnet",
            11155111: "Ethereum Sepolia",
            84532: "Base Sepolia"
        }
        print(f"⛓️  Chain: {chain_names.get(args.chain_id, f'Chain ID {args.chain_id}')}")
    
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
        intel_level=args.intel,
        use_real_prices=not args.use_mock_prices,
        chain_id=args.chain_id
    )
    
    if args.disable_circuit_breaker:
        bot.circuit_breaker_enabled = False
    
    bot.tick_interval = args.tick_interval
    
    print("=" * 60)
    print("📋 BOT CONFIGURATION")
    print("=" * 60)
    
    if bot.initialize():
        # Type guards to ensure components are initialized
        assert bot.account is not None, "Account initialization failed"
        assert bot.intelligence_engine is not None, "Intelligence engine initialization failed"
        
        print(f"  Account         : {bot.account.name}")
        print(f"  User            : {bot.account.user.username}")
        print(f"  Balance         : ${bot.account.current_balance_usd:,.2f}")
        print(f"  Tick Interval   : {args.tick_interval} seconds\n")
        print(f"  INTELLIGENCE    : Level {args.intel}/10")
        print("  Controlled by Intel Level:")
        print(f"    • Risk Tolerance    : {bot.intelligence_engine.config.risk_tolerance}%")
        print(f"    • Max Position Size : {bot.intelligence_engine.config.max_position_percent:.1f}%")
        print(f"    • Trade Frequency   : {bot.intelligence_engine.config.trade_frequency}")  # ✅ FIXED
        # print(f"    • Gas Strategy      : {bot.intelligence_engine.config.gas_strategy}")      # ✅ FIXED
        # print(f"    • MEV Protection    : {'Always On' if bot.intelligence_engine.config.use_mev_protection else 'Off'}")
        # print(f"    • Decision Speed    : {bot.intelligence_engine.config.decision_speed}")    # ✅ FIXED
        
        print("\n  PRICE FEEDS:")
        if bot.use_real_prices:
            print("    • Mode              : REAL BLOCKCHAIN DATA ✅")
            print(f"    • Chain ID          : {bot.chain_id}")
            print("    • Sources           : Alchemy, CoinGecko, DEX")
            print("    • Update Interval   : 5 seconds")
        else:
            print("    • Mode              : MOCK SIMULATION")
            print("    • Volatility        : ±5% per tick")
        
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
        print("\n✅ Bot initialized successfully\n")
        print("🏃 Bot is running... Press Ctrl+C to stop\n")
        
        bot.run()
    else:
        print("❌ Failed to initialize bot")
        sys.exit(1)


if __name__ == "__main__":
    main()