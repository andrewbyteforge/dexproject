"""
Paper Trading Defaults - Configuration Default Values

This module contains default configuration values that rarely change.
These can be overridden by environment variables or database settings.

Location: paper_trading/defaults.py

Usage:
    from paper_trading.defaults import TradingDefaults, IntelligenceDefaults

    initial_balance = TradingDefaults.INITIAL_BALANCE_USD
"""

from decimal import Decimal
from typing import Final


# =============================================================================
# TRADING DEFAULTS
# =============================================================================

class TradingDefaults:
    """
    Default values for trading parameters.

    These are sensible defaults for paper trading that can be overridden
    via environment variables or database configuration.
    """
    # Account settings
    INITIAL_BALANCE_USD: Final[Decimal] = Decimal('10000.00')

    # Position sizing
    MAX_POSITION_SIZE_PERCENT: Final[Decimal] = Decimal('10.0')
    MIN_POSITION_SIZE_USD: Final[Decimal] = Decimal('10.00')

    # Risk management
    DEFAULT_STOP_LOSS_PERCENT: Final[Decimal] = Decimal('2.0')
    DEFAULT_TAKE_PROFIT_PERCENT: Final[Decimal] = Decimal('5.0')
    MAX_DAILY_LOSS_PERCENT: Final[Decimal] = Decimal('5.0')

    # Trade limits
    MAX_DAILY_TRADES: Final[int] = 50
    MIN_TRADE_INTERVAL_MINUTES: Final[int] = 5

    # Execution parameters
    DEFAULT_TICK_INTERVAL_SECONDS: Final[int] = 60
    MAX_TOKENS_PER_TICK: Final[int] = 5


# =============================================================================
# INTELLIGENCE DEFAULTS
# =============================================================================
class IntelligenceDefaults:
    """
    Default values for intelligence and analysis parameters.
    """
    # Intelligence levels
    DEFAULT_INTEL_LEVEL: Final[int] = 3
    MIN_INTEL_LEVEL: Final[int] = 1
    MAX_INTEL_LEVEL: Final[int] = 5

    # Analysis thresholds
    MIN_CONFIDENCE_TO_TRADE: Final[Decimal] = Decimal('70.0')
    MIN_OPPORTUNITY_SCORE: Final[Decimal] = Decimal('50.0')
    MAX_RISK_SCORE: Final[Decimal] = Decimal('70.0')

    # Market data
    PRICE_HISTORY_SIZE: Final[int] = 100
    LIQUIDITY_CHECK_DEPTH: Final[int] = 5

    # Chain configuration
    DEFAULT_CHAIN_ID: Final[int] = 8453  # Base mainnet

    # Lane configuration
    DEFAULT_LANE: Final[str] = 'FAST'

    # =========================================================================
    # DATA QUALITY REQUIREMENTS
    # =========================================================================

    # Minimum data quality to execute trades
    MIN_DATA_QUALITY_TO_TRADE: Final[str] = 'GOOD'
    """Only trade when data quality is GOOD or better (EXCELLENT, GOOD, FAIR, POOR)"""

    # Required data sources (fail if unavailable)
    REQUIRE_REAL_LIQUIDITY_DATA: Final[bool] = True
    """Require real liquidity data from DEX pools to trade"""

    REQUIRE_REAL_VOLATILITY_DATA: Final[bool] = True
    """Require real price history for volatility calculations"""

    REQUIRE_REAL_GAS_DATA: Final[bool] = True
    """Require real blockchain gas price data"""

    # Fail-safe behavior
    SKIP_TRADE_ON_MISSING_DATA: Final[bool] = True
    """Skip trades when required data is unavailable (recommended: True)"""

    # Data quality thresholds
    DATA_QUALITY_GOOD_MIN_SAMPLES: Final[int] = 10
    """Minimum price samples needed for 'GOOD' data quality rating"""

    DATA_QUALITY_FAIR_MIN_SAMPLES: Final[int] = 2
    """Minimum price samples needed for 'FAIR' data quality rating"""


# =============================================================================
# NETWORK DEFAULTS
# =============================================================================

class NetworkDefaults:
    """
    Default values for network and blockchain parameters.
    """
    # Gas defaults
    DEFAULT_GAS_PRICE_GWEI: Final[Decimal] = Decimal('0.1')
    MAX_GAS_PRICE_GWEI: Final[Decimal] = Decimal('10.0')
    GAS_PRICE_PERCENTILE: Final[int] = 50  # Use median gas price

    # Slippage
    DEFAULT_SLIPPAGE_PERCENT: Final[Decimal] = Decimal('0.5')
    MAX_SLIPPAGE_PERCENT: Final[Decimal] = Decimal('5.0')

    # Timeouts
    WEB3_CONNECTION_TIMEOUT_SECONDS: Final[int] = 30
    TRANSACTION_CONFIRMATION_TIMEOUT_SECONDS: Final[int] = 300

    # RPC configuration
    MAX_RPC_RETRIES: Final[int] = 3
    RPC_RETRY_DELAY_SECONDS: Final[int] = 2


# =============================================================================
# PERFORMANCE DEFAULTS
# =============================================================================

class PerformanceDefaults:
    """
    Default values for performance monitoring and optimization.
    """
    # Cache settings
    PRICE_CACHE_TTL_SECONDS: Final[int] = 300  # 5 minutes
    RISK_CACHE_TTL_SECONDS: Final[int] = 3600  # 1 hour
    MARKET_DATA_CACHE_TTL_SECONDS: Final[int] = 60  # 1 minute

    # Fast Lane targets
    FAST_LANE_TARGET_MS: Final[int] = 500
    FAST_LANE_SLA_MS: Final[int] = 300

    # Smart Lane targets
    SMART_LANE_TARGET_MS: Final[int] = 5000
    SMART_LANE_SLA_MS: Final[int] = 3000

    # Circuit breaker settings
    CIRCUIT_BREAKER_THRESHOLD: Final[int] = 5
    CIRCUIT_BREAKER_RECOVERY_TIME_SECONDS: Final[int] = 60


# =============================================================================
# SESSION DEFAULTS
# =============================================================================

class SessionDefaults:
    """
    Default values for trading session configuration.
    """
    # Session duration
    DEFAULT_SESSION_DURATION_HOURS: Final[int] = 24
    MAX_SESSION_DURATION_HOURS: Final[int] = 168  # 1 week

    # Monitoring
    HEALTH_CHECK_INTERVAL_SECONDS: Final[int] = 30
    METRICS_UPDATE_INTERVAL_SECONDS: Final[int] = 60

    # Dashboard updates
    DASHBOARD_UPDATE_INTERVAL_SECONDS: Final[int] = 2


# =============================================================================
# CONFIGURATION HELPER
# =============================================================================

def get_default_config() -> dict:
    """
    Get complete default configuration as dictionary.

    This can be used to initialize configuration objects or as a reference
    for what values are available.

    Returns:
        Dictionary of default configuration values organized by category
    """
    return {
        'trading': {
            'initial_balance_usd': float(TradingDefaults.INITIAL_BALANCE_USD),
            'max_position_size_percent': float(TradingDefaults.MAX_POSITION_SIZE_PERCENT),
            'min_position_size_usd': float(TradingDefaults.MIN_POSITION_SIZE_USD),
            'default_stop_loss_percent': float(TradingDefaults.DEFAULT_STOP_LOSS_PERCENT),
            'default_take_profit_percent': float(TradingDefaults.DEFAULT_TAKE_PROFIT_PERCENT),
            'max_daily_loss_percent': float(TradingDefaults.MAX_DAILY_LOSS_PERCENT),
            'max_daily_trades': TradingDefaults.MAX_DAILY_TRADES,
            'min_trade_interval_minutes': TradingDefaults.MIN_TRADE_INTERVAL_MINUTES,
            'default_tick_interval_seconds': TradingDefaults.DEFAULT_TICK_INTERVAL_SECONDS,
            'max_tokens_per_tick': TradingDefaults.MAX_TOKENS_PER_TICK,
        },
        'intelligence': {
            'default_intel_level': IntelligenceDefaults.DEFAULT_INTEL_LEVEL,
            'min_intel_level': IntelligenceDefaults.MIN_INTEL_LEVEL,
            'max_intel_level': IntelligenceDefaults.MAX_INTEL_LEVEL,
            'min_confidence_to_trade': float(IntelligenceDefaults.MIN_CONFIDENCE_TO_TRADE),
            'min_opportunity_score': float(IntelligenceDefaults.MIN_OPPORTUNITY_SCORE),
            'max_risk_score': float(IntelligenceDefaults.MAX_RISK_SCORE),
            'price_history_size': IntelligenceDefaults.PRICE_HISTORY_SIZE,
            'liquidity_check_depth': IntelligenceDefaults.LIQUIDITY_CHECK_DEPTH,
            'default_chain_id': IntelligenceDefaults.DEFAULT_CHAIN_ID,
            'default_lane': IntelligenceDefaults.DEFAULT_LANE,
            'min_data_quality_to_trade': IntelligenceDefaults.MIN_DATA_QUALITY_TO_TRADE,
            'require_real_liquidity_data': IntelligenceDefaults.REQUIRE_REAL_LIQUIDITY_DATA,
            'require_real_volatility_data': IntelligenceDefaults.REQUIRE_REAL_VOLATILITY_DATA,
            'require_real_gas_data': IntelligenceDefaults.REQUIRE_REAL_GAS_DATA,
            'skip_trade_on_missing_data': IntelligenceDefaults.SKIP_TRADE_ON_MISSING_DATA,
        },
        'network': {
            'default_gas_price_gwei': float(NetworkDefaults.DEFAULT_GAS_PRICE_GWEI),
            'max_gas_price_gwei': float(NetworkDefaults.MAX_GAS_PRICE_GWEI),
            'gas_price_percentile': NetworkDefaults.GAS_PRICE_PERCENTILE,
            'default_slippage_percent': float(NetworkDefaults.DEFAULT_SLIPPAGE_PERCENT),
            'max_slippage_percent': float(NetworkDefaults.MAX_SLIPPAGE_PERCENT),
            'web3_connection_timeout_seconds': NetworkDefaults.WEB3_CONNECTION_TIMEOUT_SECONDS,
            'transaction_confirmation_timeout_seconds': NetworkDefaults.TRANSACTION_CONFIRMATION_TIMEOUT_SECONDS,
            'max_rpc_retries': NetworkDefaults.MAX_RPC_RETRIES,
            'rpc_retry_delay_seconds': NetworkDefaults.RPC_RETRY_DELAY_SECONDS,
        },
        'performance': {
            'price_cache_ttl_seconds': PerformanceDefaults.PRICE_CACHE_TTL_SECONDS,
            'risk_cache_ttl_seconds': PerformanceDefaults.RISK_CACHE_TTL_SECONDS,
            'market_data_cache_ttl_seconds': PerformanceDefaults.MARKET_DATA_CACHE_TTL_SECONDS,
            'fast_lane_target_ms': PerformanceDefaults.FAST_LANE_TARGET_MS,
            'fast_lane_sla_ms': PerformanceDefaults.FAST_LANE_SLA_MS,
            'smart_lane_target_ms': PerformanceDefaults.SMART_LANE_TARGET_MS,
            'smart_lane_sla_ms': PerformanceDefaults.SMART_LANE_SLA_MS,
            'circuit_breaker_threshold': PerformanceDefaults.CIRCUIT_BREAKER_THRESHOLD,
            'circuit_breaker_recovery_time_seconds': PerformanceDefaults.CIRCUIT_BREAKER_RECOVERY_TIME_SECONDS,
        },
        'session': {
            'default_session_duration_hours': SessionDefaults.DEFAULT_SESSION_DURATION_HOURS,
            'max_session_duration_hours': SessionDefaults.MAX_SESSION_DURATION_HOURS,
            'health_check_interval_seconds': SessionDefaults.HEALTH_CHECK_INTERVAL_SECONDS,
            'metrics_update_interval_seconds': SessionDefaults.METRICS_UPDATE_INTERVAL_SECONDS,
            'dashboard_update_interval_seconds': SessionDefaults.DASHBOARD_UPDATE_INTERVAL_SECONDS,
        }
    }


def get_trading_defaults() -> dict:
    """Get only trading-specific defaults."""
    return get_default_config()['trading']


def get_intelligence_defaults() -> dict:
    """Get only intelligence-specific defaults."""
    return get_default_config()['intelligence']


def get_network_defaults() -> dict:
    """Get only network-specific defaults."""
    return get_default_config()['network']


def get_performance_defaults() -> dict:
    """Get only performance-specific defaults."""
    return get_default_config()['performance']


def get_session_defaults() -> dict:
    """Get only session-specific defaults."""
    return get_default_config()['session']





# =============================================================================
# PHASE 2: MULTI-DEX PRICE COMPARISON DEFAULTS
# =============================================================================
# Add these to paper_trading/defaults.py

from decimal import Decimal
from typing import Final, Dict, List


class DEXComparisonDefaults:
    """Default configuration for multi-DEX price comparison."""
    
    # =========================================================================
    # DEX SELECTION
    # =========================================================================
    
    # Enable/disable specific DEXs
    ENABLE_UNISWAP_V3: Final[bool] = True
    ENABLE_UNISWAP_V2: Final[bool] = False  # Disabled initially
    ENABLE_SUSHISWAP: Final[bool] = True
    ENABLE_CURVE: Final[bool] = True
    
    # DEX priority order (higher priority = queried first)
    DEX_PRIORITY: Final[Dict[str, int]] = {
        'uniswap_v3': 1,     # Highest liquidity, query first
        'sushiswap': 2,      # Good alternative
        'curve': 3,          # For stablecoins
        'uniswap_v2': 4      # Fallback
    }
    
    # =========================================================================
    # PRICE QUERY CONFIGURATION
    # =========================================================================
    
    # Timeouts
    SINGLE_DEX_TIMEOUT_SECONDS: Final[int] = 3
    TOTAL_COMPARISON_TIMEOUT_SECONDS: Final[int] = 10
    
    # Retry configuration
    MAX_RETRIES_PER_DEX: Final[int] = 2
    RETRY_DELAY_SECONDS: Final[float] = 0.5
    
    # Cache settings
    PRICE_CACHE_TTL_SECONDS: Final[int] = 30
    COMPARISON_CACHE_TTL_SECONDS: Final[int] = 15
    
    # Minimum required successful DEX queries
    MIN_SUCCESSFUL_DEX_QUOTES: Final[int] = 2
    
    # =========================================================================
    # ARBITRAGE DETECTION
    # =========================================================================
    
    # Minimum price spread to consider arbitrage (percentage)
    MIN_ARBITRAGE_SPREAD_PERCENT: Final[Decimal] = Decimal('1.0')  # 1%
    
    # Minimum net profit threshold (USD)
    MIN_ARBITRAGE_PROFIT_USD: Final[Decimal] = Decimal('5.00')
    
    # Maximum gas price for arbitrage execution (gwei)
    MAX_ARBITRAGE_GAS_PRICE_GWEI: Final[Decimal] = Decimal('50.0')
    
    # Slippage tolerance for arbitrage
    ARBITRAGE_SLIPPAGE_TOLERANCE_PERCENT: Final[Decimal] = Decimal('0.5')  # 0.5%
    
    # Time sensitivity (max age of price quotes for arbitrage)
    MAX_QUOTE_AGE_FOR_ARBITRAGE_SECONDS: Final[int] = 10
    
    # =========================================================================
    # RISK MANAGEMENT
    # =========================================================================
    
    # Maximum price deviation between DEXs to trust data
    MAX_PRICE_DEVIATION_PERCENT: Final[Decimal] = Decimal('20.0')  # 20%
    
    # Minimum liquidity per DEX
    # Minimum liquidity per DEX (mainnet thresholds)
    MIN_LIQUIDITY_USD_UNISWAP_V3: Final[Decimal] = Decimal('50000.00')  # $50k minimum
    MIN_LIQUIDITY_USD_SUSHISWAP: Final[Decimal] = Decimal('25000.00')   # $25k minimum  
    MIN_LIQUIDITY_USD_CURVE: Final[Decimal] = Decimal('100000.00')      # $100k minimum (stablecoins)
    MIN_DEX_LIQUIDITY_USD: Final[Decimal] = Decimal('50000.00')  # Generic fallback
    
    # Maximum concurrent DEX queries
    MAX_CONCURRENT_DEX_QUERIES: Final[int] = 5
    
    # Circuit breaker: consecutive failures before disabling DEX
    MAX_CONSECUTIVE_DEX_FAILURES: Final[int] = 5
    
    # Circuit breaker: cooldown period (seconds)
    DEX_FAILURE_COOLDOWN_SECONDS: Final[int] = 300  # 5 minutes
    
    # =========================================================================
    # PERFORMANCE OPTIMIZATION
    # =========================================================================
    
    # Parallel query execution
    USE_PARALLEL_QUERIES: Final[bool] = True
    
    # Skip slow DEXs after threshold
    SKIP_SLOW_DEX_THRESHOLD_MS: Final[int] = 5000  # 5 seconds
    
    # Rate limiting (queries per minute per DEX)
    MAX_QUERIES_PER_MINUTE_PER_DEX: Final[int] = 60
    
    # =========================================================================
    # LOGGING AND MONITORING
    # =========================================================================
    
    # Log all price comparisons
    LOG_ALL_COMPARISONS: Final[bool] = True
    
    # Log arbitrage opportunities (even if not executed)
    LOG_ARBITRAGE_OPPORTUNITIES: Final[bool] = True
    
    # Performance metrics tracking
    TRACK_DEX_PERFORMANCE: Final[bool] = True
    
    # =========================================================================
    # DEX-SPECIFIC SETTINGS
    # =========================================================================
    
    # Uniswap V3 fee tiers to check (in order)
    UNISWAP_V3_FEE_TIERS: Final[List[int]] = [3000, 500, 10000]  # 0.3%, 0.05%, 1%
    
    # SushiSwap router version
    SUSHISWAP_ROUTER_VERSION: Final[str] = 'v2'
    
    # Curve: Prefer stable pools for stablecoins
    CURVE_PREFER_STABLE_POOLS: Final[bool] = True


class ArbitrageDefaults:
    """Default configuration specific to arbitrage execution."""
    
    # =========================================================================
    # EXECUTION PARAMETERS
    # =========================================================================
    
    # Auto-execute arbitrage opportunities
    AUTO_EXECUTE_ARBITRAGE: Final[bool] = False  # Manual approval initially
    
    # Require manual approval above this amount
    MANUAL_APPROVAL_THRESHOLD_USD: Final[Decimal] = Decimal('50.00')
    
    # Maximum position size for arbitrage trades
    MAX_ARBITRAGE_POSITION_PERCENT: Final[Decimal] = Decimal('5.0')  # 5% of portfolio
    
    # Maximum daily arbitrage trades
    MAX_DAILY_ARBITRAGE_TRADES: Final[int] = 10
    
    # Cooldown between arbitrage trades (seconds)
    ARBITRAGE_TRADE_COOLDOWN_SECONDS: Final[int] = 60  # 1 minute
    
    # =========================================================================
    # GAS OPTIMIZATION
    # =========================================================================
    
    # Use MEV protection for arbitrage
    USE_MEV_PROTECTION: Final[bool] = True
    
    # Gas strategy for arbitrage trades
    DEFAULT_GAS_STRATEGY: Final[str] = 'fast'  # fast, standard, slow
    
    # Maximum gas cost as percentage of profit
    MAX_GAS_COST_PERCENT_OF_PROFIT: Final[Decimal] = Decimal('30.0')  # 30%
    
    # =========================================================================
    # PROFIT TAKING
    # =========================================================================
    
    # Take profit threshold (execute immediately)
    INSTANT_EXECUTE_PROFIT_THRESHOLD_USD: Final[Decimal] = Decimal('20.00')
    
    # Profit margin targets
    TARGET_PROFIT_MARGIN_PERCENT: Final[Decimal] = Decimal('2.0')  # 2%
    MINIMUM_PROFIT_MARGIN_PERCENT: Final[Decimal] = Decimal('0.5')  # 0.5%


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_dex_comparison_config() -> dict:
    """
    Get complete DEX comparison configuration as dictionary.
    
    Returns:
        Dictionary with all DEX comparison settings
    """
    return {
        'enabled_dexs': {
            'uniswap_v3': DEXComparisonDefaults.ENABLE_UNISWAP_V3,
            'uniswap_v2': DEXComparisonDefaults.ENABLE_UNISWAP_V2,
            'sushiswap': DEXComparisonDefaults.ENABLE_SUSHISWAP,
            'curve': DEXComparisonDefaults.ENABLE_CURVE,
        },
        'timeouts': {
            'single_dex': DEXComparisonDefaults.SINGLE_DEX_TIMEOUT_SECONDS,
            'total': DEXComparisonDefaults.TOTAL_COMPARISON_TIMEOUT_SECONDS,
        },
        'arbitrage': {
            'min_spread': DEXComparisonDefaults.MIN_ARBITRAGE_SPREAD_PERCENT,
            'min_profit': DEXComparisonDefaults.MIN_ARBITRAGE_PROFIT_USD,
            'max_gas_price': DEXComparisonDefaults.MAX_ARBITRAGE_GAS_PRICE_GWEI,
            'auto_execute': ArbitrageDefaults.AUTO_EXECUTE_ARBITRAGE,
        },
        'risk_management': {
            'max_deviation': DEXComparisonDefaults.MAX_PRICE_DEVIATION_PERCENT,
            'min_liquidity': DEXComparisonDefaults.MIN_DEX_LIQUIDITY_USD,
            'max_failures': DEXComparisonDefaults.MAX_CONSECUTIVE_DEX_FAILURES,
        }
    }


def get_arbitrage_config() -> dict:
    """
    Get complete arbitrage configuration as dictionary.
    
    Returns:
        Dictionary with all arbitrage settings
    """
    return {
        'execution': {
            'auto_execute': ArbitrageDefaults.AUTO_EXECUTE_ARBITRAGE,
            'manual_threshold': ArbitrageDefaults.MANUAL_APPROVAL_THRESHOLD_USD,
            'max_position': ArbitrageDefaults.MAX_ARBITRAGE_POSITION_PERCENT,
            'cooldown': ArbitrageDefaults.ARBITRAGE_TRADE_COOLDOWN_SECONDS,
        },
        'gas': {
            'use_mev_protection': ArbitrageDefaults.USE_MEV_PROTECTION,
            'strategy': ArbitrageDefaults.DEFAULT_GAS_STRATEGY,
            'max_cost_percent': ArbitrageDefaults.MAX_GAS_COST_PERCENT_OF_PROFIT,
        },
        'profit': {
            'instant_execute': ArbitrageDefaults.INSTANT_EXECUTE_PROFIT_THRESHOLD_USD,
            'target_margin': ArbitrageDefaults.TARGET_PROFIT_MARGIN_PERCENT,
            'minimum_margin': ArbitrageDefaults.MINIMUM_PROFIT_MARGIN_PERCENT,
        }
    }