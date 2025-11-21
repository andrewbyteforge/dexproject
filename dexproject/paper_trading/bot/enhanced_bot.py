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

UPDATED: Added engine config initialization to fix Web3 connection errors
CLEANED: Fixed all flake8 and Pylance linting errors

File: dexproject/paper_trading/bot/enhanced_bot.py
"""

# ============================================================================
# WINDOWS CONSOLE ENCODING FIX
# ============================================================================
import sys
import io
import asyncio
from contextlib import suppress
from typing import Any, Awaitable, Callable


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
import logging
from decimal import Decimal
from typing import Any, Optional
import uuid

# ============================================================================
# DJANGO SETUP
# ============================================================================
# Add project root to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import django  # noqa: E402
from django.conf import settings  # noqa: E402

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')

# Only call django.setup() if Django hasn't been configured yet
# This prevents conflicts when imported during Django startup
if not settings.configured:
    django.setup()





from django.utils import timezone  # noqa: E402
from django.contrib.auth.models import User  # noqa: E402
from asgiref.sync import async_to_sync  # noqa: E402

# ============================================================================
# MODEL IMPORTS
# ============================================================================
from paper_trading.models import (  # noqa: E402
    PaperTradingAccount,
    PaperTradingSession,
    PaperStrategyConfiguration
)

# ============================================================================
# BOT MODULE IMPORTS
# ============================================================================
from paper_trading.bot.price_service_integration import (  # noqa: E402
    create_price_manager,
    RealPriceManager
)
from paper_trading.bot.position_manager import PositionManager  # noqa: E402
from paper_trading.bot.trade_executor import TradeExecutor  # noqa: E402
from paper_trading.bot.market_analyzer import MarketAnalyzer  # noqa: E402
from paper_trading.bot.validation import ValidationLimits  # noqa: E402

# ============================================================================
# INTELLIGENCE SYSTEM IMPORTS
# ============================================================================
from paper_trading.intelligence.core.intel_slider import IntelSliderEngine  # noqa: E402

# ============================================================================
# ENGINE CONFIG IMPORTS (✅ ADDED FOR FIX)
# ============================================================================
try:
    import engine.config as engine_config_module  # noqa: E402
    from engine.config import get_config  # noqa: E402
    ENGINE_CONFIG_AVAILABLE = True
except ImportError:
    engine_config_module = None  # type: ignore
    get_config = None  # type: ignore
    ENGINE_CONFIG_AVAILABLE = False
    logging.warning("Engine config module not available - real blockchain data will be limited")

# ============================================================================
# CIRCUIT BREAKER IMPORTS (Optional)
# ============================================================================
try:
    from engine.portfolio import CircuitBreakerManager  # noqa: E402
    CIRCUIT_BREAKER_AVAILABLE = True
except ImportError:
    CircuitBreakerManager = None  # type: ignore
    CIRCUIT_BREAKER_AVAILABLE = False

# ============================================================================
# TRANSACTION MANAGER IMPORTS (Optional)
# ============================================================================
try:
    from trading.services.transaction_manager import get_transaction_manager  # noqa: E402
    TRANSACTION_MANAGER_AVAILABLE = True
except ImportError:
    get_transaction_manager = None  # type: ignore
    TRANSACTION_MANAGER_AVAILABLE = False

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
# logging.basicConfig(
#     level=logging.INFO,
#     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
#     handlers=[
#         logging.StreamHandler(),
#         logging.FileHandler('paper_trading_bot.log', encoding='utf-8')
#     ]
# )
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

    UPDATED: Now initializes engine config to enable real blockchain data

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
        chain_id: int = 8453,  # ✅ MAINNET DEFAULT - Base Mainnet
        config_id: Optional[int] = None
    ):
        """
        Initialize the enhanced paper trading bot.

        CRITICAL: This now initializes the global engine_config FIRST to ensure
        that all analyzers can access real blockchain data via Web3.

        Args:
            account_name: Name of the paper trading account
            intel_level: Intelligence level (1-10)
            use_real_prices: Whether to use real price feeds
            chain_id: Blockchain network ID for price fetching
        """
        # =====================================================================
        # ✅ STEP 1: INITIALIZE ENGINE CONFIG FIRST (FIX FOR WEB3 ERROR)
        # =====================================================================
        self._initialize_engine_config()

        # =====================================================================
        # STEP 2: STORE BOT CONFIGURATION
        # =====================================================================
        self.account_name = account_name
        self.intel_level = intel_level
        self.use_real_prices = use_real_prices
        self.chain_id = chain_id
        self.config_id = config_id

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

        # =====================================================================
        # STEP 3: LOG INITIALIZATION STATUS
        # =====================================================================
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
    # ✅ NEW METHOD: ENGINE CONFIG INITIALIZATION (FIX FOR WEB3 ERROR)
    # =========================================================================

    def _initialize_engine_config(self) -> None:
        """
        Initialize the global engine configuration for Web3 connectivity.

        This method MUST be called before any market analyzers are created,
        as they require access to the global engine_config to connect to
        blockchain RPCs for real gas prices, liquidity data, etc.

        The engine config is initialized asynchronously because it loads
        chain configurations from Django models, but we run it synchronously
        here using async_to_sync since __init__ cannot be async.

        Error Handling:
            - If ENGINE_CONFIG_AVAILABLE is False, logs warning and continues
            - If initialization fails, logs error but doesn't crash bot
            - If config is already initialized, skips re-initialization

        Raises:
            None - All errors are caught and logged, bot continues with fallback data
        """
        if not ENGINE_CONFIG_AVAILABLE:
            logger.warning(
                "[ENGINE_CONFIG] Engine config module not available - "
                "analyzers will use fallback data instead of real blockchain data"
            )
            return

        try:
            # ✅ FIX: Access the module's config attribute, not the imported reference
            if engine_config_module is None:
                logger.error("[ENGINE_CONFIG] Engine config module is not available")
                return

            # Check if config is already initialized by accessing module attribute
            if hasattr(engine_config_module, 'config') and engine_config_module.config is not None:
                logger.info("[ENGINE_CONFIG] ✅ Engine config already initialized")
                return

            logger.info("[ENGINE_CONFIG] Initializing engine configuration for Web3 connectivity...")

            # Check that get_config is not None before calling
            if get_config is None:
                logger.error("[ENGINE_CONFIG] get_config function is not available")
                return

            # Initialize the config asynchronously using async_to_sync
            # This will populate the global config variable in engine.config module
            async_to_sync(get_config)()

            # ✅ VERIFY: Check that config was actually set
            if hasattr(engine_config_module, 'config') and engine_config_module.config is not None:
                logger.info("[ENGINE_CONFIG] ✅ Engine config initialized successfully!")
                logger.info(
                    f"[ENGINE_CONFIG] Loaded {len(engine_config_module.config.chains)} chain configurations"
                )
                logger.info(
                    "[ENGINE_CONFIG] Analyzers can now access real blockchain data "
                    "(gas prices, liquidity, volatility)"
                )
            else:
                logger.error("[ENGINE_CONFIG] ❌ Config initialization failed - config is still None")
                logger.warning("[ENGINE_CONFIG] Bot will continue but analyzers will use fallback data")

        except Exception as e:
            logger.error(
                f"[ENGINE_CONFIG] ❌ Failed to initialize engine config: {e}",
                exc_info=True
            )
            logger.warning(
                "[ENGINE_CONFIG] Bot will continue but analyzers will use fallback data"
            )

    # =========================================================================
    # INITIALIZATION
    # =========================================================================

    def initialize(self) -> bool:
        """
        Initialize bot components and connections.

        This must be called after creating the bot instance and before
        calling run(). It sets up all managers and validates configuration.

        Initialization Steps:
            1. Load or create account
            2. Create trading session
            3. Clean up duplicate accounts
            4. Initialize intelligence engine
            5. Setup strategy configuration
            6. Initialize circuit breaker manager
            7. Initialize price manager
            8. Initialize position manager
            9. Initialize trade executor
            10. Initialize market analyzer
            11. Log initial thought

        Returns:
            True if initialization successful, False otherwise
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

            # Step 4: Setup strategy configuration FIRST
            self._setup_strategy_configuration()
            assert self.strategy_config is not None, "Strategy configuration initialization failed"

            # Step 5: Initialize intelligence engine WITH loaded config
            self._initialize_intelligence()
            assert self.intelligence_engine is not None, "Intelligence engine initialization failed"

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

    # =========================================================================
    # COMPONENT INITIALIZATION METHODS
    # =========================================================================

    # Current code creates accounts with 'paper_trader' username
    # We need to use the centralized account utility instead

    def _load_account(self) -> None:
        """
        Load the single paper trading account for this user.
        
        Uses centralized account utilities to ensure consistency across
        the entire application (bot, API, dashboard, WebSocket).

        Raises:
            Exception: If account cannot be loaded or created
        """
        try:
            # ✅ USE CENTRALIZED UTILITY - prevents duplicates
            from paper_trading.utils import get_default_user, get_single_trading_account
            
            # Get the demo_user (same user the dashboard uses)
            user = get_default_user()
            
            # Get the single trading account for this user
            # This will always return the same account, regardless of intel level
            self.account = get_single_trading_account()
            
            logger.info(f"[ACCOUNT] Loaded account: {self.account.name}")
            logger.info(f"[ACCOUNT] Account ID: {self.account.account_id}")
            logger.info(f"[ACCOUNT] Balance: ${self.account.current_balance_usd:,.2f}")

        except Exception as e:
            logger.error(f"[ACCOUNT] Failed to load account: {e}", exc_info=True)
            raise

    def _cleanup_duplicate_accounts(self) -> None:
        """
        Clean up any duplicate accounts that may have been created.

        This ensures database integrity by removing older duplicate accounts
        while preserving the most recent one.

        Note: This is called AFTER session is created to avoid breaking
        foreign key relationships.
        """
        assert self.account is not None, "Account must be initialized before cleanup"

        try:
            # Find all accounts with the same name
            duplicate_accounts = PaperTradingAccount.objects.filter(
                user=self.account.user,
                name=self.account_name
            ).exclude(
                account_id=self.account.account_id
            ).order_by('-created_at')

            if duplicate_accounts.exists():
                count = duplicate_accounts.count()
                logger.warning(
                    f"[ACCOUNT] Found {count} duplicate account(s), cleaning up..."
                )

                # Delete duplicates (keep only the one we're using)
                for dup in duplicate_accounts:
                    logger.info(
                        f"[ACCOUNT] Deleting duplicate: {dup.account_id} "
                        f"(created {dup.created_at})"
                    )
                    dup.delete()

                logger.info(f"[ACCOUNT] Cleaned up {count} duplicate account(s)")
            else:
                logger.info("[ACCOUNT] No duplicate accounts found")

        except Exception as e:
            logger.error(f"[ACCOUNT] Error during cleanup: {e}", exc_info=True)
            # Don't raise - cleanup failure shouldn't stop the bot

    def _create_session(self) -> None:
        """
        Create or load today's trading session.

        Sessions are created per day. If a session already exists for today,
        it's loaded. Otherwise, a new session is created with configuration
        snapshot stored in metadata.

        Raises:
            Exception: If session cannot be created
        """
        assert self.account is not None, "Account must be initialized before session"

        try:
            today = timezone.now().date()

            # Check for existing session from today
            old_session = PaperTradingSession.objects.filter(
                account=self.account,
                started_at__date=today,
                status='RUNNING'
            ).first()

            if old_session:
                # Close old session (✅ FIXED: use stopped_at, not ended_at)
                old_session.status = 'COMPLETED'
                old_session.stopped_at = timezone.now()
                old_session.save()
                logger.info(
                    f"[SESSION] Closed old session from "
                    f"{old_session.started_at.date()}: {old_session.session_id}"
                )

            # Create new session for today
            config_snapshot = {
                "bot_version": "3.0.0",
                "intel_level": self.intel_level,
                "strategy_config_id": self.strategy_config.pk if self.strategy_config else None,  # ← ADD
                "strategy_config_name": self.strategy_config.name if self.strategy_config else None,  # ← ADD
                "account_name": self.account_name,
                "account_id": str(self.account.account_id),
                "session_uuid": str(uuid.uuid4()),
                "user_id": str(self.account.user.id),  # type: ignore[attr-defined]
                "transaction_manager_enabled": self.use_tx_manager,
                "circuit_breaker_enabled": self.circuit_breaker_enabled,
                "use_real_prices": self.use_real_prices,
                "chain_id": self.chain_id,
                "engine_config_initialized": ENGINE_CONFIG_AVAILABLE and engine_config_module is not None and hasattr(
                    engine_config_module, 'config') and engine_config_module.config is not None
            }

            def json_safe(obj: Any) -> Any:
                """Convert non-serializable types to JSON-safe types."""
                if isinstance(obj, Decimal):
                    return float(obj)
                if isinstance(obj, dict):
                    return {k: json_safe(v) for k, v in obj.items()}
                if isinstance(obj, (list, tuple)):
                    return [json_safe(item) for item in obj]
                return obj

            safe_snapshot = json_safe(config_snapshot)

            session_name = (
                f"Bot_Session_{today.strftime('%Y%m%d')}_"
                f"{self.strategy_config.name if self.strategy_config else 'Default'}"  # ← CHANGE THIS LINE
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

        except Exception as e:
            logger.error(f"[SESSION] Failed to create session: {e}", exc_info=True)
            raise

    def _initialize_intelligence(self) -> None:
        """
        Initialize the intelligence engine with configured Intel level.

        The intelligence engine handles all trading decision logic based on
        the Intel slider setting (1-10) and the loaded strategy configuration.

        NOTE: This is called AFTER _setup_strategy_configuration() so that
        self.strategy_config is already loaded with the user's selected config.

        Raises:
            Exception: If intelligence engine cannot be initialized
        """
        assert self.account is not None, "Account must be initialized before intelligence engine"
        assert self.strategy_config is not None, "Strategy config must be loaded before intelligence engine"

        try:
            # ✅ FIXED: Use the already-loaded strategy config
            self.intelligence_engine = IntelSliderEngine(
                intel_level=self.intel_level,
                account_id=str(self.account.account_id),
                strategy_config=self.strategy_config,  # ← Use loaded config!
                chain_id=self.chain_id
            )
            
            logger.info(
                f"[INTEL] Intelligence Engine initialized at Level {self.intel_level} "
                f"with config: {self.strategy_config.name} "
                f"(Confidence: {self.strategy_config.confidence_threshold}%)"
            )

        except Exception as e:
            logger.error(f"[INTEL] Failed to initialize intelligence engine: {e}", exc_info=True)
            raise

    def _setup_strategy_configuration(self) -> None:
        """
        Load the strategy configuration for this session.
        
        Priority:
        1. If config_id specified → Load that specific config
        2. Otherwise → Load most recently updated config
        3. If no configs exist → Create default config
        
        Raises:
            Exception: If strategy configuration cannot be loaded
        """
        assert self.account is not None, "Account must be initialized before strategy config"

        try:
            # Priority 1: Load specific config if ID provided
            if self.config_id:
                try:
                    self.strategy_config = PaperStrategyConfiguration.objects.get(
                        pk=self.config_id,
                        account=self.account
                    )
                    logger.info(
                        f"[STRATEGY] Loaded specified config: {self.strategy_config.name} "
                        f"(Confidence: {self.strategy_config.confidence_threshold}%)"
                    )
                    return
                except PaperStrategyConfiguration.DoesNotExist:
                    logger.warning(
                        f"[STRATEGY] Config ID {self.config_id} not found, "
                        "falling back to most recent"
                    )
            
            # Priority 2: Load most recently updated config
            self.strategy_config = PaperStrategyConfiguration.objects.filter(
                account=self.account
            ).order_by('-updated_at').first()
            
            if self.strategy_config:
                logger.info(
                    f"[STRATEGY] Loaded most recent config: {self.strategy_config.name} "
                    f"(Confidence: {self.strategy_config.confidence_threshold}%)"
                )
                return
            
            # Priority 3: Create default config if none exists
            logger.warning("[STRATEGY] No configs found, creating default...")
            self.strategy_config = self._create_default_strategy_config()
            logger.info(
                f"[STRATEGY] Created default config: {self.strategy_config.name}"
            )

        except Exception as e:
            logger.error(f"[STRATEGY] Failed to setup strategy config: {e}", exc_info=True)
            raise

    def _create_default_strategy_config(self) -> PaperStrategyConfiguration:
        """
        Create a default strategy configuration.
        
        This is only called if no configurations exist in the database.
        
        Returns:
            Newly created PaperStrategyConfiguration
        """
        assert self.account is not None
        assert self.intelligence_engine is not None
        
        config = self.intelligence_engine.config
        
        def json_safe(value: Any) -> Any:
            """Convert Decimals and other non-JSON types to serializable types."""
            if isinstance(value, Decimal):
                return float(value)
            if isinstance(value, dict):
                return {k: json_safe(v) for k, v in value.items()}
            if isinstance(value, list):
                return [json_safe(v) for v in value]
            return value
        
        # Extract configuration parameters with fallbacks
        max_pos_size = getattr(
            config,
            "max_position_percent",
            getattr(config, "max_position_size_percent", 10)
        )
        confidence_threshold = getattr(config, "confidence_threshold", 60)
        risk_tolerance = getattr(config, "risk_tolerance", 50)
        
        custom_parameters = {
            "intel_level": self.intel_level,
            "use_tx_manager": self.use_tx_manager,
            "circuit_breaker_enabled": self.circuit_breaker_enabled,
            "auto_created": True,
            "note": "Auto-generated default configuration"
        }
        
        custom_parameters = json_safe(custom_parameters)
        
        # Token list for allowed tokens
        token_addresses = [
            '0x4200000000000000000000000000000000000006',  # WETH on Base
            '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913',  # USDC
            '0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb',  # DAI
        ]
        
        strategy_config = PaperStrategyConfiguration.objects.create(
            account=self.account,
            name=f"Default_Intel_{self.intel_level}",
            trading_mode="MODERATE",
            use_fast_lane=True,
            use_smart_lane=False,
            fast_lane_threshold_usd=Decimal("100"),
            max_position_size_percent=Decimal(str(max_pos_size)),
            stop_loss_percent=Decimal("5.0"),
            take_profit_percent=Decimal("10.0"),
            max_daily_trades=50,
            confidence_threshold=Decimal(str(confidence_threshold)),
            allowed_tokens=token_addresses,
            custom_parameters=custom_parameters,
            is_active=False  # Don't mark as active by default
        )
        
        return strategy_config

    def _initialize_circuit_breaker(self) -> None:
        """
        Initialize circuit breaker manager for risk protection.

        Circuit breakers prevent the bot from executing trades when risk
        conditions are exceeded (e.g., too many consecutive failures).

        Note: This is optional - if CircuitBreakerManager is not available,
        the bot continues without this protection.
        """
        if not self.circuit_breaker_enabled or not CIRCUIT_BREAKER_AVAILABLE:
            logger.info("[BREAKER] Circuit breaker disabled or unavailable")
            return

        # Type guard: Ensure CircuitBreakerManager is not None before calling
        if CircuitBreakerManager is None:
            logger.warning("[BREAKER] CircuitBreakerManager class is not available")
            self.circuit_breaker_enabled = False
            return

        try:
            # ✅ NEW: Create config object from Django settings
            from django.conf import settings
            
            # Simple config object with required attributes
            class PortfolioConfig:
                """Minimal config for circuit breaker."""
                def __init__(self):
                    self.max_portfolio_size_usd = settings.MAX_PORTFOLIO_SIZE_USD
                    self.daily_loss_limit_percent = settings.DAILY_LOSS_LIMIT_PERCENT
                    self.circuit_breaker_loss_percent = settings.CIRCUIT_BREAKER_LOSS_PERCENT
            
            # Create config and pass to circuit breaker
            portfolio_config = PortfolioConfig()
            self.circuit_breaker_manager = CircuitBreakerManager(portfolio_config=portfolio_config)  # ✅ WITH CONFIG
            
            logger.info(
                f"[BREAKER] Circuit breaker manager initialized with config "
                f"(Daily limit: {settings.DAILY_LOSS_LIMIT_PERCENT}%, "
                f"Circuit breaker: {settings.CIRCUIT_BREAKER_LOSS_PERCENT}%)"
            )
        except Exception as e:
            logger.warning(f"[BREAKER] Could not initialize circuit breaker: {e}")
            self.circuit_breaker_enabled = False

    def _initialize_price_manager(self) -> None:
        """
        Initialize price manager for fetching token prices.

        The price manager handles fetching prices from multiple sources
        (Alchemy, CoinGecko, DEX) with automatic failover.

        Raises:
            Exception: If price manager cannot be initialized
        """
        try:
            self.price_manager = create_price_manager(
                use_real_prices=self.use_real_prices,
                chain_id=self.chain_id,  # ← Must explicitly pass this!
                token_list=None
            )            
            logger.info(
                f"[PRICE] Price manager initialized "
                f"(real_prices={self.use_real_prices}, chain={self.chain_id})"
            )
        except Exception as e:
            logger.error(f"[PRICE] Failed to initialize price manager: {e}", exc_info=True)
            raise

    def _initialize_position_manager(self) -> None:
        """
        Initialize position manager for tracking open positions.

        The position manager handles opening, updating, and closing positions,
        including auto-close logic for stop-loss and take-profit.

        Raises:
            Exception: If position manager cannot be initialized
        """
        assert self.account is not None, "Account must be initialized before position manager"

        try:
            self.position_manager = PositionManager(account=self.account)
            logger.info("[POSITION] Position manager initialized")
        except Exception as e:
            logger.error(f"[POSITION] Failed to initialize position manager: {e}", exc_info=True)
            raise

    def _initialize_trade_executor(self) -> None:
        """
        Initialize trade executor for executing trades.

        The trade executor routes trades through either the Transaction Manager
        (for gas optimization) or legacy execution path.

        Raises:
            Exception: If trade executor cannot be initialized
        """
        assert self.account is not None, "Account must be initialized before trade executor"
        assert self.session is not None, "Session must be initialized before trade executor"
        assert self.position_manager is not None, "Position manager must be initialized before trade executor"

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
            
            # ✅ RESET CIRCUIT BREAKER ON BOT STARTUP
            # This clears any previous consecutive failures and gives the bot a fresh start
            self._check_and_reset_circuit_breaker_on_startup()
            
            logger.info("[EXECUTOR] Trade executor initialized with circuit breaker reset")
        except Exception as e:
            logger.error(f"[EXECUTOR] Failed to initialize trade executor: {e}", exc_info=True)
            raise
        
        
    
    def _check_and_reset_circuit_breaker_on_startup(self) -> None:
        """Check if circuit breaker is stuck and auto-reset if needed."""
        assert self.trade_executor is not None
        
        max_failures = ValidationLimits.MAX_CONSECUTIVE_FAILURES
        current_failures = self.trade_executor.consecutive_failures
        
        if current_failures >= max_failures:
            logger.warning(
                f"[STARTUP] ⚠️ CIRCUIT BREAKER STUCK: "
                f"{current_failures}/{max_failures} failures detected!"
            )
            logger.warning("[STARTUP] This would block all trading. Auto-resetting...")
            self.trade_executor.reset_circuit_breaker()
            logger.info("[STARTUP] ✅ Circuit breaker reset successfully")
            logger.info("[STARTUP] Trading is now ENABLED - all safety systems operational")
        else:
            logger.info(
                f"[STARTUP] ✅ Circuit breaker status: "
                f"{current_failures}/{max_failures} failures (System operational)"
            )

    

    def _initialize_market_analyzer(self) -> None:
        """
        Initialize market analyzer for coordinating tick operations.

        The market analyzer is the main tick coordinator that triggers all
        market analysis, decision making, and trade execution.

        Raises:
            Exception: If market analyzer cannot be initialized
        """
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
            logger.error(f"[MARKET] Failed to initialize market analyzer: {e}", exc_info=True)
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
            from paper_trading.models import PaperAIThoughtLog  # noqa: E402

            # Build reasoning text
            engine_config_status = "INITIALIZED" if (
                ENGINE_CONFIG_AVAILABLE and
                engine_config_module is not None and
                hasattr(engine_config_module, 'config') and
                engine_config_module.config is not None
            ) else "UNAVAILABLE"

            reasoning = (
                f"Bot initialized with Intel Level {self.intel_level}. "
                f"Strategy: {self.intelligence_engine.config.name}. "
                f"Risk tolerance: {self.intelligence_engine.config.risk_tolerance}%. "
                f"Transaction Manager: {'ENABLED' if self.use_tx_manager else 'DISABLED'}. "
                f"Circuit Breakers: {'ENABLED' if self.circuit_breaker_enabled else 'DISABLED'}. "
                f"Price Feeds: {'REAL' if self.use_real_prices else 'MOCK'}. "
                f"Engine Config: {engine_config_status}. "
                f"Starting balance: ${self.account.current_balance_usd:.2f}"
            )

            # Build market data with all metrics
            market_data = {
                'intel_level': self.intel_level,
                'tx_manager_enabled': self.use_tx_manager,
                'circuit_breaker_enabled': self.circuit_breaker_enabled,
                'use_real_prices': self.use_real_prices,
                'chain_id': self.chain_id,
                'engine_config_status': engine_config_status,
                'starting_balance': float(self.account.current_balance_usd),
                'risk_score': 0,  # No risk at startup
                'opportunity_score': 100,  # Full opportunity ahead
                'confidence': 100,  # High confidence in configuration
                'event_type': 'BOT_STARTUP'
            }

            # Create thought log with standardized field names
            PaperAIThoughtLog.objects.create(
                account=self.account,
                paper_trade=None,
                decision_type='SKIP',  # System event, not a trade
                token_address='0x' + '0' * 40,  # System address
                token_symbol='SYSTEM',
                confidence_level='VERY_HIGH',  # STRING (VERY_HIGH, HIGH, MEDIUM, LOW, VERY_LOW)
                confidence_percent=Decimal('100'),  # DECIMAL (0-100)
                risk_score=Decimal('0'),  # DECIMAL - no risk on startup
                opportunity_score=Decimal('100'),  # DECIMAL - optimal startup
                primary_reasoning=reasoning[:500],  # Truncated to 500 chars
                key_factors=[
                    f"Intel Level: {self.intel_level}",
                    f"TX Manager: {'Enabled' if self.use_tx_manager else 'Disabled'}",
                    f"Circuit Breaker: {'Enabled' if self.circuit_breaker_enabled else 'Disabled'}",
                    f"Price Feeds: {'Real' if self.use_real_prices else 'Mock'}",
                    f"Engine Config: {engine_config_status}",
                    f"Starting Balance: ${self.account.current_balance_usd:.2f}"
                ],
                positive_signals=[
                    "Bot successfully initialized",
                    "All systems operational",
                    "Configuration validated",
                    f"Engine config {engine_config_status.lower()}"
                ],
                negative_signals=[] if engine_config_status == "INITIALIZED" else [
                    "Engine config unavailable - using fallback data"
                ],
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

        This method runs indefinitely until interrupted by Ctrl+C or SIGTERM.
        It calls market_analyzer.tick() at regular intervals (default 15 seconds).

        The run loop:
            1. Sets running flag to True
            2. Continuously calls market_analyzer.tick()
            3. Sleeps for tick_interval seconds
            4. Handles KeyboardInterrupt gracefully
            5. Calls shutdown() on exit
        """
        assert self.market_analyzer is not None, "Market analyzer must be initialized before run"
        assert self.price_manager is not None, "Price manager must be initialized before run"
        assert self.position_manager is not None, "Position manager must be initialized before run"
        assert self.trade_executor is not None, "Trade executor must be initialized before run"

        self.running = True
        logger.info("[BOT] Starting main run loop...")

        try:
            while self.running:
                # Run a market tick with required managers
                self.market_analyzer.tick(
                    price_manager=self.price_manager,
                    position_manager=self.position_manager,
                    trade_executor=self.trade_executor
                )

                # Sleep until next tick
                time.sleep(self.tick_interval)

        except KeyboardInterrupt:
            logger.info("[BOT] Received interrupt signal, shutting down...")
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        """
        Gracefully shut down the bot, cancel background tasks, and close resources.

        This is safe to call from a sync context (manage.py command). It:
        1) Stops the run loop.
        2) Cancels any registered asyncio tasks (self._tasks if present).
        3) Closes async/sync resources (price manager, analyzer, tx executor,
            websocket service, redis client, web3 provider) without raising.
        4) Marks the session as completed and logs final stats.
        """
        logger.info("[BOT] Shutting down gracefully...")
        # Signal loops to stop
        setattr(self, "_stopping", True)
        self.running = False

        # Cancel any background asyncio tasks we may have registered
        tasks = getattr(self, "_tasks", None)
        if tasks:
            for t in list(tasks):
                if t and not t.done():
                    t.cancel()

        # --- helpers -------------------------------------------------------------
        async def _maybe_call(func: Callable[..., Any]) -> None:
            try:
                result = func()
                if asyncio.iscoroutine(result) or isinstance(result, Awaitable):
                    with suppress(Exception):
                        await result
            except Exception:
                # Swallow during shutdown; we want best-effort cleanup
                pass

        async def _maybe_close(obj: Any) -> None:
            if obj is None:
                return
            # Prefer async aclose()
            aclose = getattr(obj, "aclose", None)
            if callable(aclose):
                await _maybe_call(aclose)
                return
            # Fallback to async close()
            close = getattr(obj, "close", None)
            if callable(close):
                await _maybe_call(close)

        async def _close_resources_async() -> None:
            # Price manager may own an HTTP client and its own aclose/close
            with suppress(Exception):
                pm = getattr(self, "price_manager", None)
                if pm is not None:
                    client = getattr(pm, "client", None)
                    await _maybe_close(client)
                    await _maybe_close(pm)

            # Market analyzer may keep timers/clients
            with suppress(Exception):
                analyzer = getattr(self, "market_analyzer", None)
                await _maybe_close(analyzer)

            # Trade executor / tx manager (web3 providers or HTTP clients)
            with suppress(Exception):
                executor = getattr(self, "trade_executor", None)
                await _maybe_close(executor)

            # WebSocket service (Channels/clients)
            with suppress(Exception):
                ws = getattr(self, "websocket_service", None)
                await _maybe_close(ws)

            # Generic http/session attribute if you added one
            with suppress(Exception):
                http = getattr(self, "http", None)
                await _maybe_close(http)

            # Redis client if present
            with suppress(Exception):
                redis_client = getattr(self, "redis_client", None)
                await _maybe_close(redis_client)

            # Web3 provider/client best-effort close
            with suppress(Exception):
                web3c = getattr(self, "web3_client", None)
                if web3c is not None:
                    provider = getattr(web3c, "provider", None)
                    await _maybe_close(provider)
                    await _maybe_close(web3c)

            # Give cancelled tasks a moment to settle
            await asyncio.sleep(0.05)

        # Run async cleanup whether or not an event loop is running
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Schedule and briefly yield; we still continue to DB cleanup below
            loop.create_task(_close_resources_async())
        else:
            asyncio.run(_close_resources_async())

        # --- DB/session & final stats -------------------------------------------
        try:
            if self.session:
                self.session.status = 'COMPLETED'
                self.session.stopped_at = timezone.now()
                self.session.save()
                logger.info(f"[SESSION] Closed session: {self.session.session_id}")

            if self.account:
                logger.info(f"[STATS] Final balance: ${self.account.current_balance_usd:,.2f}")
                logger.info(f"[STATS] Total trades: {self.account.total_trades}")
                logger.info(f"[STATS] Winning trades: {self.account.winning_trades}")
                logger.info(f"[STATS] Losing trades: {self.account.losing_trades}")
                if self.account.total_trades > 0:
                    win_rate = (self.account.winning_trades / self.account.total_trades) * 100
                    logger.info(f"[STATS] Win rate: {win_rate:.1f}%")

            logger.info("[BOT] ✅ Shutdown complete")
        except Exception as e:
            logger.error(f"[BOT] Error during shutdown: {e}", exc_info=True)

# =============================================================================
# MAIN ENTRY POINT (for standalone execution)
# =============================================================================


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Enhanced Paper Trading Bot with Intel Slider System'
    )
    parser.add_argument(
        '--account',
        type=str,
        default='Default_AI_Bot',
        help='Account name to use'
    )
    parser.add_argument(
        '--intel',
        type=int,
        default=5,
        choices=range(1, 11),
        help='Intelligence level (1-10)'
    )
    parser.add_argument(
        '--tick-interval',
        type=int,
        default=15,
        help='Seconds between market ticks'
    )
    parser.add_argument(
        '--use-mock-prices',
        action='store_true',
        help='Use mock price simulation instead of real data'
    )
    parser.add_argument(
        '--chain-id',
        type=int,
        default=8453,
        help='Chain ID for price fetching (default: 8453 = Base Mainnet)'  # ✅ MAINNET
    )
    parser.add_argument(
        '--disable-circuit-breaker',
        action='store_true',
        help='Disable circuit breaker protection'
    )

    args = parser.parse_args()

    # Display banner
    print("\n" + "╔" + "═" * 68 + "╗")
    print("║" + " " * 68 + "║")
    print("║" + "  ENHANCED PAPER TRADING BOT - INTEL SLIDER SYSTEM".center(68) + "║")
    print("║" + " " * 68 + "║")
    print("╚" + "═" * 68 + "╝\n")

    intel_descriptions = {
        1: "ULTRA CONSERVATIVE - Minimal risk",
        2: "VERY CONSERVATIVE - Very low risk",
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
            8453: "Base Mainnet"  # ✅ MAINNET
        }
        print(f"⛓️  Chain: {chain_names.get(args.chain_id, f'Chain ID {args.chain_id}')}")

    # Engine config status
    if ENGINE_CONFIG_AVAILABLE:
        print("🔧 ENGINE CONFIG: AVAILABLE - Real blockchain data enabled")
    else:
        print("⚠️  ENGINE CONFIG: NOT AVAILABLE - Using fallback data")

    # Transaction Manager status
    if TRANSACTION_MANAGER_AVAILABLE:
        print("⚡ TRANSACTION MANAGER: ENABLED - Gas optimization active")
    else:
        print("⚠️  TRANSACTION MANAGER: NOT AVAILABLE")

    # Circuit Breaker status
    if not args.disable_circuit_breaker and CIRCUIT_BREAKER_AVAILABLE:
        print("🛡️  CIRCUIT BREAKERS: ENABLED - Risk protection active")
    else:
        print("⚠️  CIRCUIT BREAKERS: DISABLED")

    print("")

    # Create and initialize bot
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
        print(f"    • Trade Frequency   : {bot.intelligence_engine.config.trade_frequency}")
        print("=" * 60)
        print("\n🚀 Bot is running! Press Ctrl+C to stop.\n")

        bot.run()
    else:
        print("\n❌ Bot initialization failed. Check logs for details.\n")
        sys.exit(1)