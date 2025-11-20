"""
Professional Trading Bot Settings - Unibot/Maestro Best Practices

This module defines professional-grade trading bot configuration based on successful
commercial bots like Unibot and Maestro. These settings have been proven in production
environments and represent industry best practices for automated trading.

Key Philosophy:
- Risk management first (protect capital)
- Clear entry/exit rules (no emotion)
- Position limits (prevent over-diversification)
- Multi-tier exits (lock in profits incrementally)
- Fast exits, patient entries

File: dexproject/paper_trading/bot/professional_settings.py
"""

from decimal import Decimal
from typing import Final, List, Tuple


# =============================================================================
# POSITION MANAGEMENT
# =============================================================================

class PositionLimits:
    """Position sizing and limits (Unibot/Maestro standard)."""
    
    # Maximum number of simultaneous open positions
    # Pro bots typically use 3-5 to prevent over-diversification
    MAX_OPEN_POSITIONS: Final[int] = 5
    
    # Maximum position size as percentage of portfolio
    # 20% = 5 positions max at full size, balanced risk
    MAX_POSITION_SIZE_PERCENT: Final[Decimal] = Decimal('20.0')
    
    # Minimum position size in USD
    # Below this, gas costs eat into profits too much
    MIN_POSITION_SIZE_USD: Final[Decimal] = Decimal('50.0')
    
    # Maximum position size in USD (absolute limit)
    # Even if 20% of portfolio is higher, cap at this amount
    MAX_POSITION_SIZE_USD: Final[Decimal] = Decimal('10000.0')


# =============================================================================
# DOLLAR-COST AVERAGING (DCA) SETTINGS
# =============================================================================

class DCASettings:
    """Settings for adding to existing positions."""
    
    # Enable DCA (adding to positions)
    # Pro bots allow this to compound winning trades
    ALLOW_DCA: Final[bool] = True
    
    # Maximum number of DCA additions per position
    # Total entries = initial + DCA additions
    # Example: 1 initial + 2 DCA = 3 total entries max
    MAX_DCA_ADDITIONS: Final[int] = 2
    
    # Minimum profit before allowing DCA
    # Only add to winning positions (never average down)
    MIN_PROFIT_FOR_DCA_PERCENT: Final[Decimal] = Decimal('5.0')
    
    # DCA position size (percentage of original position)
    # Example: 50% means each DCA is half the original entry
    DCA_SIZE_PERCENT: Final[Decimal] = Decimal('50.0')
    
    # Minimum time between DCA additions (minutes)
    # Prevents rapid-fire additions
    MIN_TIME_BETWEEN_DCA_MINUTES: Final[int] = 30


# =============================================================================
# EXIT STRATEGY - MULTI-TIER TAKE-PROFIT
# =============================================================================

class ExitStrategy:
    """Multi-tier take-profit and stop-loss settings."""
    
    # Stop-loss percentage (negative number)
    # -5% is moderate risk, professional standard
    # Conservative: -3%, Aggressive: -8%
    STOP_LOSS_PERCENT: Final[Decimal] = Decimal('-5.0')
    
    # Multi-tier take-profit levels
    # Format: [(profit_percent, position_percent_to_sell)]
    # This is how pro bots lock in profits incrementally
    TAKE_PROFIT_TIERS: Final[List[Tuple[Decimal, Decimal]]] = [
        (Decimal('15.0'), Decimal('30.0')),  # At +15%, sell 30% of position
        (Decimal('30.0'), Decimal('40.0')),  # At +30%, sell 40% of position
        (Decimal('50.0'), Decimal('30.0')),  # At +50%, sell remaining 30%
    ]
    
    # Trailing stop-loss (optional, not implemented yet)
    # Once position hits first take-profit, move stop-loss to breakeven
    ENABLE_TRAILING_STOP: Final[bool] = False
    TRAILING_STOP_ACTIVATION_PERCENT: Final[Decimal] = Decimal('15.0')
    
    # Maximum hold time in hours
    # Active trading: 24-48h, Swing trading: 72-168h (3-7 days)
    MAX_HOLD_TIME_HOURS: Final[int] = 48
    
    # Auto-review positions after this many hours
    # Forces re-evaluation even if no triggers hit
    AUTO_REVIEW_AFTER_HOURS: Final[int] = 12


# =============================================================================
# COOLDOWN PERIODS
# =============================================================================

class CooldownSettings:
    """Cooldown periods to prevent overtrading."""
    
    # BUY cooldown for same token (minutes)
    # Prevents FOMO buying the same token repeatedly
    BUY_COOLDOWN_SAME_TOKEN_MINUTES: Final[int] = 15
    
    # BUY cooldown for any token (minutes)
    # Prevents rapid-fire buying of different tokens
    BUY_COOLDOWN_ANY_TOKEN_MINUTES: Final[int] = 3
    
    # SELL cooldown (minutes)
    # Pro bots use 0 = no cooldown for exits (exit fast when needed)
    SELL_COOLDOWN_MINUTES: Final[int] = 0
    
    # Failed trade cooldown (minutes)
    # After a failed trade, wait before trying again
    FAILED_TRADE_COOLDOWN_MINUTES: Final[int] = 5


# =============================================================================
# RISK MANAGEMENT
# =============================================================================

class RiskManagement:
    """Risk management thresholds and limits."""
    
    # Minimum liquidity required (USD)
    # Don't trade tokens with low liquidity (high slippage risk)
    MIN_LIQUIDITY_USD: Final[Decimal] = Decimal('50000.0')
    
    # Maximum slippage tolerance (percentage)
    # Pro bots use 2% max, anything higher is too risky
    MAX_SLIPPAGE_PERCENT: Final[Decimal] = Decimal('2.0')
    
    # Minimum confidence for BUY (percentage)
    # Only enter trades with high confidence
    MIN_CONFIDENCE_FOR_BUY: Final[Decimal] = Decimal('70.0')
    
    # Minimum confidence for SELL (percentage)
    # Easier to exit than enter (more lenient)
    MIN_CONFIDENCE_FOR_SELL: Final[Decimal] = Decimal('60.0')
    
    # MEV protection threshold (USD)
    # Use MEV protection (Flashbots) for trades above this amount
    MEV_PROTECTION_THRESHOLD_USD: Final[Decimal] = Decimal('1000.0')
    
    # Maximum gas price willing to pay (gwei)
    # Don't overpay for gas
    MAX_GAS_PRICE_GWEI: Final[Decimal] = Decimal('50.0')
    
    # Circuit breaker: Max portfolio loss (percentage)
    # Stop all trading if portfolio drops this much
    CIRCUIT_BREAKER_MAX_LOSS_PERCENT: Final[Decimal] = Decimal('15.0')
    
    # Circuit breaker: Max daily trades
    # Prevent overtrading on volatile days
    CIRCUIT_BREAKER_MAX_DAILY_TRADES: Final[int] = 50
    
    # Circuit breaker: Max consecutive failures
    # Stop trading after this many failed trades in a row
    CIRCUIT_BREAKER_MAX_CONSECUTIVE_FAILURES: Final[int] = 5


# =============================================================================
# INTELLIGENCE & ANALYSIS
# =============================================================================

class AnalysisSettings:
    """Settings for market analysis and decision making."""
    
    # Price history lookback periods (hours)
    # Used for volatility and trend analysis
    PRICE_HISTORY_LOOKBACK_HOURS: Final[int] = 24
    
    # Minimum data quality score (0-100)
    # Don't trade on poor quality data
    MIN_DATA_QUALITY_SCORE: Final[int] = 60
    
    # Market analysis timeout (seconds)
    # How long to wait for analysis before giving up
    ANALYSIS_TIMEOUT_SECONDS: Final[int] = 30
    
    # Enable arbitrage detection
    # Pro bots check for cross-DEX arbitrage opportunities
    ENABLE_ARBITRAGE_DETECTION: Final[bool] = True
    
    # Minimum arbitrage spread (percentage)
    # Need at least this much spread to cover gas + slippage
    MIN_ARBITRAGE_SPREAD_PERCENT: Final[Decimal] = Decimal('0.5')
    
    # Minimum arbitrage profit (USD)
    # Not worth executing for less than this
    MIN_ARBITRAGE_PROFIT_USD: Final[Decimal] = Decimal('10.0')


# =============================================================================
# EXECUTION SETTINGS
# =============================================================================

class ExecutionSettings:
    """Trade execution parameters."""
    
    # Use Transaction Manager for gas optimization
    # When enabled, routes trades through TX Manager for 23%+ gas savings
    USE_TRANSACTION_MANAGER: Final[bool] = True
    
    # Use private RPC for sensitive trades
    # Protects from MEV on medium-large trades
    USE_PRIVATE_RPC_ABOVE_USD: Final[Decimal] = Decimal('500.0')
    
    # Transaction deadline (seconds)
    # How long before transaction expires
    TRANSACTION_DEADLINE_SECONDS: Final[int] = 300
    
    # Gas strategy
    # Options: 'slow', 'standard', 'fast', 'instant'
    DEFAULT_GAS_STRATEGY: Final[str] = 'standard'
    
    # Retry failed transactions
    RETRY_FAILED_TRANSACTIONS: Final[bool] = True
    MAX_TRANSACTION_RETRIES: Final[int] = 3
    
    # Increase gas on retry (percentage)
    GAS_INCREASE_ON_RETRY_PERCENT: Final[Decimal] = Decimal('10.0')


# =============================================================================
# LOGGING & MONITORING
# =============================================================================

class MonitoringSettings:
    """Logging and monitoring configuration."""
    
    # Update performance metrics every N ticks
    METRICS_UPDATE_INTERVAL_TICKS: Final[int] = 20
    
    # Send WebSocket status updates every N seconds
    WEBSOCKET_UPDATE_INTERVAL_SECONDS: Final[int] = 15
    
    # Log AI thoughts for all decisions
    LOG_ALL_DECISIONS: Final[bool] = True
    
    # Verbose logging (includes debug info)
    VERBOSE_LOGGING: Final[bool] = False
    
    # Save trade history to database
    SAVE_TRADE_HISTORY: Final[bool] = True


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_all_settings() -> dict:
    """
    Get all professional settings as a dictionary.
    
    Useful for configuration export, debugging, or passing to other modules.
    
    Returns:
        Dictionary with all settings organized by category
    """
    return {
        'position_limits': {
            'max_open_positions': PositionLimits.MAX_OPEN_POSITIONS,
            'max_position_size_percent': float(PositionLimits.MAX_POSITION_SIZE_PERCENT),
            'min_position_size_usd': float(PositionLimits.MIN_POSITION_SIZE_USD),
            'max_position_size_usd': float(PositionLimits.MAX_POSITION_SIZE_USD),
        },
        'dca_settings': {
            'allow_dca': DCASettings.ALLOW_DCA,
            'max_dca_additions': DCASettings.MAX_DCA_ADDITIONS,
            'min_profit_for_dca_percent': float(DCASettings.MIN_PROFIT_FOR_DCA_PERCENT),
            'dca_size_percent': float(DCASettings.DCA_SIZE_PERCENT),
            'min_time_between_dca_minutes': DCASettings.MIN_TIME_BETWEEN_DCA_MINUTES,
        },
        'exit_strategy': {
            'stop_loss_percent': float(ExitStrategy.STOP_LOSS_PERCENT),
            'take_profit_tiers': [
                (float(profit), float(size))
                for profit, size in ExitStrategy.TAKE_PROFIT_TIERS
            ],
            'max_hold_time_hours': ExitStrategy.MAX_HOLD_TIME_HOURS,
            'auto_review_after_hours': ExitStrategy.AUTO_REVIEW_AFTER_HOURS,
        },
        'cooldown_settings': {
            'buy_cooldown_same_token_minutes': CooldownSettings.BUY_COOLDOWN_SAME_TOKEN_MINUTES,
            'buy_cooldown_any_token_minutes': CooldownSettings.BUY_COOLDOWN_ANY_TOKEN_MINUTES,
            'sell_cooldown_minutes': CooldownSettings.SELL_COOLDOWN_MINUTES,
            'failed_trade_cooldown_minutes': CooldownSettings.FAILED_TRADE_COOLDOWN_MINUTES,
        },
        'risk_management': {
            'min_liquidity_usd': float(RiskManagement.MIN_LIQUIDITY_USD),
            'max_slippage_percent': float(RiskManagement.MAX_SLIPPAGE_PERCENT),
            'min_confidence_for_buy': float(RiskManagement.MIN_CONFIDENCE_FOR_BUY),
            'min_confidence_for_sell': float(RiskManagement.MIN_CONFIDENCE_FOR_SELL),
            'mev_protection_threshold_usd': float(RiskManagement.MEV_PROTECTION_THRESHOLD_USD),
            'max_gas_price_gwei': float(RiskManagement.MAX_GAS_PRICE_GWEI),
        },
        'analysis_settings': {
            'enable_arbitrage_detection': AnalysisSettings.ENABLE_ARBITRAGE_DETECTION,
            'min_arbitrage_spread_percent': float(AnalysisSettings.MIN_ARBITRAGE_SPREAD_PERCENT),
            'min_arbitrage_profit_usd': float(AnalysisSettings.MIN_ARBITRAGE_PROFIT_USD),
        },
        'execution_settings': {
            'use_transaction_manager': ExecutionSettings.USE_TRANSACTION_MANAGER,
            'use_private_rpc_above_usd': float(ExecutionSettings.USE_PRIVATE_RPC_ABOVE_USD),
            'default_gas_strategy': ExecutionSettings.DEFAULT_GAS_STRATEGY,
        }
    }


def print_settings_summary() -> None:
    """Print a human-readable summary of all professional settings."""
    print("\n" + "="*80)
    print("PROFESSIONAL TRADING BOT SETTINGS (Unibot/Maestro Standard)")
    print("="*80)
    
    print("\n📊 POSITION MANAGEMENT:")
    print(f"  • Max Open Positions: {PositionLimits.MAX_OPEN_POSITIONS}")
    print(f"  • Max Position Size: {PositionLimits.MAX_POSITION_SIZE_PERCENT}% of portfolio")
    print(f"  • Min/Max Size: ${PositionLimits.MIN_POSITION_SIZE_USD} - ${PositionLimits.MAX_POSITION_SIZE_USD}")
    
    print("\n💰 DCA (DOLLAR-COST AVERAGING):")
    print(f"  • DCA Enabled: {DCASettings.ALLOW_DCA}")
    print(f"  • Max Additions: {DCASettings.MAX_DCA_ADDITIONS} per position")
    print(f"  • Min Profit to DCA: +{DCASettings.MIN_PROFIT_FOR_DCA_PERCENT}%")
    print(f"  • DCA Size: {DCASettings.DCA_SIZE_PERCENT}% of original")
    
    print("\n📉 EXIT STRATEGY:")
    print(f"  • Stop-Loss: {ExitStrategy.STOP_LOSS_PERCENT}%")
    print(f"  • Take-Profit Tiers:")
    for profit, size in ExitStrategy.TAKE_PROFIT_TIERS:
        print(f"    - At +{profit}%: sell {size}% of position")
    print(f"  • Max Hold Time: {ExitStrategy.MAX_HOLD_TIME_HOURS} hours")
    
    print("\n⏱️  COOLDOWNS:")
    print(f"  • BUY (same token): {CooldownSettings.BUY_COOLDOWN_SAME_TOKEN_MINUTES} min")
    print(f"  • BUY (any token): {CooldownSettings.BUY_COOLDOWN_ANY_TOKEN_MINUTES} min")
    print(f"  • SELL: {CooldownSettings.SELL_COOLDOWN_MINUTES} min (no cooldown)")
    
    print("\n🛡️  RISK MANAGEMENT:")
    print(f"  • Min Liquidity: ${RiskManagement.MIN_LIQUIDITY_USD:,.0f}")
    print(f"  • Max Slippage: {RiskManagement.MAX_SLIPPAGE_PERCENT}%")
    print(f"  • Min Confidence (BUY): {RiskManagement.MIN_CONFIDENCE_FOR_BUY}%")
    print(f"  • Min Confidence (SELL): {RiskManagement.MIN_CONFIDENCE_FOR_SELL}%")
    print(f"  • MEV Protection: >${RiskManagement.MEV_PROTECTION_THRESHOLD_USD}")
    
    print("\n🔧 EXECUTION:")
    print(f"  • Transaction Manager: {ExecutionSettings.USE_TRANSACTION_MANAGER}")
    print(f"  • Private RPC: >${ExecutionSettings.USE_PRIVATE_RPC_ABOVE_USD}")
    print(f"  • Gas Strategy: {ExecutionSettings.DEFAULT_GAS_STRATEGY}")
    
    print("\n" + "="*80 + "\n")


# Example usage
if __name__ == "__main__":
    print_settings_summary()