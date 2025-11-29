"""
Paper Trading Admin Interface - Updated for New Model Structure

Django admin configuration for all paper trading models including
Auto Pilot models, with correct field names matching the new structure.

File: dexproject/paper_trading/admin.py
"""

from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Sum, Avg, Count
from .models import (
    # Core models
    PaperTradingAccount,
    PaperTrade,
    PaperPosition,
    PaperTradingConfig,
    # Intelligence models
    PaperAIThoughtLog,
    PaperStrategyConfiguration,
    # Performance models
    PaperPerformanceMetrics,
    PaperTradingSession,
    # Auto Pilot models
    AutoPilotLog,
    AutoPilotPerformanceSnapshot,
)


# =============================================================================
# CORE MODEL ADMINS
# =============================================================================

@admin.register(PaperTradingAccount)
class PaperTradingAccountAdmin(admin.ModelAdmin):
    """Admin interface for Paper Trading Accounts."""
    
    list_display = [
        'name', 'user', 'current_balance_usd', 
        'total_profit_loss_usd', 'win_rate_display', 'is_active',
        'total_trades', 'created_at'
    ]
    list_filter = ['is_active', 'created_at', 'user']
    search_fields = ['name', 'user__username']
    readonly_fields = [
        'account_id', 'created_at', 'last_activity',
        'total_trades', 'winning_trades', 'losing_trades',
        'total_profit_loss_usd'
    ]
    
    fieldsets = (
        ('Account Info', {
            'fields': ('account_id', 'user', 'name', 'description', 'is_active')
        }),
        ('Balances', {
            'fields': (
                'initial_balance_usd', 'current_balance_usd'
            )
        }),
        ('Performance', {
            'fields': (
                'total_trades', 'winning_trades', 'losing_trades',
                'total_profit_loss_usd'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'last_activity')
        })
    )
    
    def win_rate_display(self, obj):
        """Display win rate with color coding."""
        rate = obj.get_win_rate()
        if rate >= 60:
            color = 'green'
        elif rate >= 40:
            color = 'orange'
        else:
            color = 'red'
        return format_html(
            '<span style="color: {};">{:.1f}%</span>',
            color, rate
        )
    win_rate_display.short_description = 'Win Rate'


@admin.register(PaperTrade)
class PaperTradeAdmin(admin.ModelAdmin):
    """Admin interface for Paper Trades."""
    
    list_display = [
        'trade_id_short', 'account', 'trade_type', 'token_out_symbol',
        'amount_in_usd', 'status', 'simulated_slippage_percent',
        'created_at'
    ]
    list_filter = ['status', 'trade_type', 'created_at', 'account']
    search_fields = [
        'trade_id', 'token_in_symbol', 'token_out_symbol',
        'mock_tx_hash'
    ]
    readonly_fields = [
        'trade_id', 'created_at', 'executed_at',
        'mock_tx_hash', 'mock_block_number'
    ]
    
    fieldsets = (
        ('Trade Identity', {
            'fields': ('trade_id', 'account', 'trade_type', 'status')
        }),
        ('Token Details', {
            'fields': (
                'token_in_address', 'token_in_symbol',
                'token_out_address', 'token_out_symbol'
            )
        }),
        ('Amounts', {
            'fields': (
                'amount_in', 'amount_in_usd',
                'expected_amount_out', 'actual_amount_out'
            )
        }),
        ('Execution Details', {
            'fields': (
                'simulated_gas_price_gwei', 'simulated_gas_used',
                'simulated_gas_cost_usd', 'simulated_slippage_percent',
                'execution_time_ms'
            )
        }),
        ('Transaction Info', {
            'fields': (
                'mock_tx_hash', 'mock_block_number',
                'strategy_name', 'error_message', 'metadata'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'executed_at')
        })
    )
    
    def trade_id_short(self, obj):
        """Display shortened trade ID."""
        return str(obj.trade_id)[:8] + '...'
    trade_id_short.short_description = 'Trade ID'


@admin.register(PaperPosition)
class PaperPositionAdmin(admin.ModelAdmin):
    """Admin interface for Paper Positions."""
    
    list_display = [
        'position_id_short', 'account', 'token_symbol', 'quantity',
        'unrealized_pnl_display', 'is_open', 'opened_at'
    ]
    list_filter = ['is_open', 'opened_at', 'account']
    search_fields = ['position_id', 'token_symbol', 'token_address']
    readonly_fields = [
        'position_id', 'opened_at', 'closed_at', 'last_updated',
        'realized_pnl_usd', 'unrealized_pnl_usd'
    ]
    
    def position_id_short(self, obj):
        """Display shortened position ID."""
        return str(obj.position_id)[:8] + '...'
    position_id_short.short_description = 'Position ID'
    
    def unrealized_pnl_display(self, obj):
        """Display unrealized P&L with color coding."""
        pnl = obj.unrealized_pnl_usd
        if pnl > 0:
            color = 'green'
            prefix = '+'
        elif pnl < 0:
            color = 'red'
            prefix = ''
        else:
            color = 'gray'
            prefix = ''
        return format_html(
            '<span style="color: {};">{}{:.2f} USD</span>',
            color, prefix, pnl
        )
    unrealized_pnl_display.short_description = 'Unrealized P&L'


@admin.register(PaperTradingConfig)
class PaperTradingConfigAdmin(admin.ModelAdmin):
    """Admin interface for Paper Trading Config."""
    
    list_display = [
        'account', 'base_slippage_percent', 'gas_price_multiplier',
        'max_position_size_percent', 'max_daily_trades'
    ]
    list_filter = ['simulate_network_issues', 'simulate_mev']
    search_fields = ['account__name']


# =============================================================================
# INTELLIGENCE MODEL ADMINS
# =============================================================================

@admin.register(PaperAIThoughtLog)
class PaperAIThoughtLogAdmin(admin.ModelAdmin):
    """Admin interface for AI Thought Logs."""
    
    list_display = [
        'thought_id_short', 'account', 'decision_type', 'token_symbol',
        'confidence_display', 'lane_used', 'created_at'
    ]
    list_filter = [
        'decision_type', 'lane_used', 'created_at', 'account'
    ]
    search_fields = [
        'thought_id', 'token_symbol', 'token_address',
        'strategy_name', 'reasoning'
    ]
    readonly_fields = [
        'thought_id', 'created_at', 'analysis_time_ms'
    ]
    
    fieldsets = (
        ('Identity', {
            'fields': ('thought_id', 'account', 'paper_trade')
        }),
        ('Decision Details', {
            'fields': (
                'decision_type', 'token_address', 'token_symbol',
                'lane_used', 'strategy_name'
            )
        }),
        ('Confidence & Scoring', {
            'fields': (
                'confidence_level', 'risk_assessment'
            )
        }),
        ('Reasoning', {
            'fields': (
                'reasoning', 'key_factors',
                'positive_signals', 'negative_signals'
            ),
            'classes': ('collapse',)
        }),
        ('Market Data', {
            'fields': ('market_data',),
            'classes': ('collapse',)
        }),
        ('Timing', {
            'fields': ('created_at', 'analysis_time_ms')
        })
    )
    
    def thought_id_short(self, obj):
        """Display shortened thought ID."""
        return str(obj.thought_id)[:8] + '...'
    thought_id_short.short_description = 'Thought ID'
    
    def confidence_display(self, obj):
        """Display confidence with color."""
        conf = obj.confidence_level
        if conf >= 80:
            color = 'green'
        elif conf >= 60:
            color = 'orange'
        else:
            color = 'red'
        return format_html(
            '<span style="color: {};">{:.1f}%</span>',
            color, conf
        )
    confidence_display.short_description = 'Confidence'


@admin.register(PaperStrategyConfiguration)
class PaperStrategyConfigurationAdmin(admin.ModelAdmin):
    """Admin interface for Strategy Configuration with Auto Pilot."""
    
    list_display = [
        'name', 'account', 'trading_mode', 'autopilot_status',
        'is_active', 'created_at'
    ]
    list_filter = [
        'trading_mode', 'autopilot_enabled', 'is_active',
        'adaptation_aggressiveness', 'created_at'
    ]
    search_fields = ['name', 'account__name']
    readonly_fields = [
        'config_id', 'created_at', 'updated_at',
        'autopilot_started_at', 'autopilot_last_adjustment',
        'autopilot_adjustments_count'
    ]
    
    fieldsets = (
        ('Identity', {
            'fields': ('config_id', 'account', 'name', 'is_active')
        }),
        ('Trading Mode', {
            'fields': ('trading_mode', 'use_fast_lane', 'use_smart_lane', 'fast_lane_threshold_usd')
        }),
        ('Risk Management', {
            'fields': (
                'max_position_size_percent', 'stop_loss_percent',
                'take_profit_percent', 'max_daily_trades',
                'max_concurrent_positions'
            )
        }),
        ('Trading Parameters', {
            'fields': (
                'min_liquidity_usd', 'max_slippage_percent',
                'confidence_threshold'
            )
        }),
        ('Token Filters', {
            'fields': ('allowed_tokens', 'blocked_tokens', 'custom_parameters'),
            'classes': ('collapse',)
        }),
        ('Auto Pilot Configuration', {
            'fields': (
                'autopilot_enabled', 'autopilot_started_at',
                'autopilot_adjustments_count', 'autopilot_last_adjustment'
            )
        }),
        ('Auto Pilot Boundaries', {
            'fields': (
                'min_position_size_percent', 'max_position_size_percent_limit',
                'min_confidence_threshold', 'max_confidence_threshold_limit'
            ),
            'classes': ('collapse',)
        }),
        ('Learning Parameters', {
            'fields': (
                'learning_rate', 'adaptation_aggressiveness',
                'performance_window_trades', 'adjustment_cooldown_minutes'
            ),
            'classes': ('collapse',)
        }),
        ('Safety Limits', {
            'fields': (
                'max_daily_adjustments', 'auto_disable_after_failures'
            ),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        })
    )
    
    def autopilot_status(self, obj):
        """Display Auto Pilot status with emoji."""
        if obj.autopilot_enabled:
            return format_html('🤖 <span style="color: green;">ENABLED</span>')
        return format_html('👤 <span style="color: gray;">Manual</span>')
    autopilot_status.short_description = 'Auto Pilot'


# =============================================================================
# PERFORMANCE MODEL ADMINS
# =============================================================================

@admin.register(PaperPerformanceMetrics)
class PaperPerformanceMetricsAdmin(admin.ModelAdmin):
    """Admin interface for Performance Metrics."""
    
    list_display = [
        'metric_id_short', 'session', 'period_display',
        'win_rate_display', 'total_pnl_display',
        'sharpe_ratio', 'max_drawdown_percent'
    ]
    list_filter = ['period_end', 'win_rate']
    search_fields = ['metric_id', 'session__session_id']
    readonly_fields = [
        'metric_id', 'created_at', 'profit_factor'
    ]
    
    fieldsets = (
        ('Identity', {
            'fields': ('metric_id', 'session')
        }),
        ('Period', {
            'fields': ('period_start', 'period_end')
        }),
        ('Trade Statistics', {
            'fields': (
                'total_trades', 'winning_trades', 'losing_trades',
                'win_rate'
            )
        }),
        ('Financial Metrics', {
            'fields': (
                'total_pnl_usd', 'total_pnl_percent',
                'average_win_usd', 'average_loss_usd',
                'largest_win_usd', 'largest_loss_usd'
            )
        }),
        ('Risk Metrics', {
            'fields': (
                'sharpe_ratio', 'max_drawdown_percent',
                'profit_factor'
            )
        }),
        ('Metadata', {
            'fields': ('created_at',)
        })
    )
    
    def metric_id_short(self, obj):
        """Display shortened metrics ID."""
        return str(obj.metric_id)[:8] + '...'
    metric_id_short.short_description = 'Metric ID'
    
    def period_display(self, obj):
        """Display the period covered."""
        duration = obj.period_end - obj.period_start
        hours = duration.total_seconds() / 3600
        if hours < 24:
            return f"{hours:.1f} hours"
        else:
            days = hours / 24
            return f"{days:.1f} days"
    period_display.short_description = 'Period'
    
    def win_rate_display(self, obj):
        """Display win rate with color."""
        rate = obj.win_rate
        if rate >= 60:
            color = 'green'
        elif rate >= 40:
            color = 'orange'
        else:
            color = 'red'
        return format_html(
            '<span style="color: {};">{:.1f}%</span>',
            color, rate
        )
    win_rate_display.short_description = 'Win Rate'
    
    def total_pnl_display(self, obj):
        """Display total P&L with color."""
        pnl = obj.total_pnl_usd
        percent = obj.total_pnl_percent
        
        if pnl > 0:
            color = 'green'
            prefix = '+'
        elif pnl < 0:
            color = 'red'
            prefix = ''
        else:
            color = 'gray'
            prefix = ''
            
        return format_html(
            '<span style="color: {};">{}{:.2f} USD ({:.1f}%)</span>',
            color, prefix, pnl, percent
        )
    total_pnl_display.short_description = 'Total P&L'


@admin.register(PaperTradingSession)
class PaperTradingSessionAdmin(admin.ModelAdmin):
    """Admin interface for Trading Sessions."""
    
    list_display = [
        'session_id_short', 'account', 'status_display',
        'duration_display', 'trades_display',
        'started_at'
    ]
    list_filter = [
        'status', 'started_at', 'account'
    ]
    search_fields = [
        'session_id', 'account__name'
    ]
    readonly_fields = [
        'session_id', 'started_at', 'stopped_at',
        'last_activity'
    ]
    
    fieldsets = (
        ('Identity', {
            'fields': (
                'session_id', 'account', 'strategy_config'
            )
        }),
        ('Status', {
            'fields': (
                'status', 'last_activity'
            )
        }),
        ('Timing', {
            'fields': (
                'started_at', 'stopped_at'
            )
        }),
        ('Statistics', {
            'fields': (
                'total_trades', 'successful_trades',
                'failed_trades'
            )
        }),
        ('Error Tracking', {
            'fields': (
                'error_message',
            ),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        })
    )
    
    actions = ['stop_sessions']
    
    def session_id_short(self, obj):
        """Display shortened session ID."""
        return str(obj.session_id)[:8] + '...'
    session_id_short.short_description = 'Session ID'
    
    def status_display(self, obj):
        """Display status with emoji."""
        emoji = {
            'RUNNING': '✅',
            'PAUSED': '⏸️',
            'STOPPED': '⏹️',
            'COMPLETED': '🎉',
            'ERROR': '❌'
        }.get(obj.status, '❓')
        return format_html('{} {}', emoji, obj.get_status_display())
    status_display.short_description = 'Status'
    
    def duration_display(self, obj):
        """Display session duration."""
        duration = obj.get_duration_hours()
        if duration is None:
            return 'N/A'
        
        hours = int(duration)
        minutes = int((duration - hours) * 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"
    duration_display.short_description = 'Duration'
    
    def trades_display(self, obj):
        """Display trade statistics."""
        total = obj.total_trades
        success = obj.successful_trades
        if total > 0:
            rate = (success / total) * 100
            return format_html(
                '{} trades ({:.0f}% success)',
                total, rate
            )
        return '0 trades'
    trades_display.short_description = 'Trades'
    
    def stop_sessions(self, request, queryset):
        """Stop selected sessions."""
        for session in queryset.filter(status__in=['RUNNING', 'PAUSED']):
            session.stop_session(error="Stopped by admin")
        self.message_user(
            request,
            f"Stopped {queryset.count()} session(s)"
        )
    stop_sessions.short_description = "Stop selected sessions"


# =============================================================================
# AUTO PILOT MODEL ADMINS
# =============================================================================

@admin.register(AutoPilotLog)
class AutoPilotLogAdmin(admin.ModelAdmin):
    """Admin interface for Auto Pilot Adjustment Logs."""
    
    list_display = [
        'log_id_short', 'strategy_config', 'adjustment_type',
        'parameter_name', 'change_display', 'outcome_display',
        'timestamp'
    ]
    list_filter = [
        'adjustment_type', 'outcome', 'is_reversal', 'timestamp'
    ]
    search_fields = [
        'log_id', 'parameter_name', 'reason',
        'strategy_config__name'
    ]
    readonly_fields = [
        'log_id', 'timestamp', 'change_percent',
        'outcome_evaluated_at', 'trades_since_adjustment'
    ]
    
    fieldsets = (
        ('Identity', {
            'fields': ('log_id', 'strategy_config', 'session')
        }),
        ('Adjustment Details', {
            'fields': (
                'adjustment_type', 'parameter_name',
                'old_value', 'new_value', 'change_percent'
            )
        }),
        ('Reasoning', {
            'fields': (
                'reason', 'trigger_metric', 'trigger_value',
                'trigger_threshold', 'confidence_in_adjustment'
            )
        }),
        ('Performance Context', {
            'fields': (
                'performance_before', 'performance_after'
            ),
            'classes': ('collapse',)
        }),
        ('Outcome', {
            'fields': (
                'outcome', 'outcome_evaluated_at',
                'outcome_notes', 'trades_since_adjustment'
            )
        }),
        ('Market Context', {
            'fields': ('market_conditions',),
            'classes': ('collapse',)
        }),
        ('Reversal Info', {
            'fields': ('is_reversal', 'reverses_log'),
            'classes': ('collapse',)
        }),
        ('Timing', {
            'fields': ('timestamp',)
        })
    )
    
    def log_id_short(self, obj):
        """Display shortened log ID."""
        return str(obj.log_id)[:8] + '...'
    log_id_short.short_description = 'Log ID'
    
    def change_display(self, obj):
        """Display parameter change."""
        change = obj.change_percent
        if change > 0:
            color = 'green'
            prefix = '+'
        elif change < 0:
            color = 'red'
            prefix = ''
        else:
            color = 'gray'
            prefix = ''
        return format_html(
            '{} → {} (<span style="color: {};">{}{:.1f}%</span>)',
            obj.old_value, obj.new_value, color, prefix, change
        )
    change_display.short_description = 'Change'
    
    def outcome_display(self, obj):
        """Display outcome with emoji."""
        emoji = {
            'PENDING': '⏳',
            'POSITIVE': '✅',
            'NEUTRAL': '➖',
            'NEGATIVE': '❌',
            'UNKNOWN': '❓'
        }.get(obj.outcome, '❓')
        return format_html('{} {}', emoji, obj.get_outcome_display())
    outcome_display.short_description = 'Outcome'


@admin.register(AutoPilotPerformanceSnapshot)
class AutoPilotPerformanceSnapshotAdmin(admin.ModelAdmin):
    """Admin interface for Auto Pilot Performance Snapshots."""
    
    list_display = [
        'snapshot_id_short', 'strategy_config', 'autopilot_active',
        'win_rate_display', 'total_pnl_display',
        'adjustments_made_count', 'timestamp'
    ]
    list_filter = [
        'autopilot_active', 'market_trend', 'timestamp'
    ]
    search_fields = [
        'snapshot_id', 'strategy_config__name', 'notes'
    ]
    readonly_fields = [
        'snapshot_id', 'timestamp', 'win_rate',
        'average_profit_per_trade', 'profit_factor'
    ]
    
    fieldsets = (
        ('Identity', {
            'fields': ('snapshot_id', 'strategy_config', 'session')
        }),
        ('Auto Pilot Context', {
            'fields': (
                'autopilot_active', 'adjustments_made_count',
                'last_adjustment_type'
            )
        }),
        ('Parameters', {
            'fields': ('current_parameters',),
            'classes': ('collapse',)
        }),
        ('Performance Metrics', {
            'fields': (
                'win_rate', 'total_trades', 'winning_trades',
                'losing_trades', 'total_pnl_usd',
                'average_profit_per_trade'
            )
        }),
        ('Trade Details', {
            'fields': (
                'average_win_usd', 'average_loss_usd',
                'largest_win_usd', 'largest_loss_usd'
            ),
            'classes': ('collapse',)
        }),
        ('Risk Metrics', {
            'fields': (
                'max_drawdown_percent', 'sharpe_ratio',
                'profit_factor'
            )
        }),
        ('Market Conditions', {
            'fields': (
                'market_volatility', 'avg_gas_price_gwei',
                'market_trend', 'market_conditions_detail'
            ),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': (
                'snapshot_period_hours', 'notes', 'timestamp'
            )
        })
    )
    
    def snapshot_id_short(self, obj):
        """Display shortened snapshot ID."""
        return str(obj.snapshot_id)[:8] + '...'
    snapshot_id_short.short_description = 'Snapshot ID'
    
    def win_rate_display(self, obj):
        """Display win rate with color."""
        rate = obj.win_rate
        if rate >= 60:
            color = 'green'
        elif rate >= 40:
            color = 'orange'
        else:
            color = 'red'
        return format_html(
            '<span style="color: {};">{:.1f}%</span>',
            color, rate
        )
    win_rate_display.short_description = 'Win Rate'
    
    def total_pnl_display(self, obj):
        """Display total P&L with color."""
        pnl = obj.total_pnl_usd
        
        if pnl > 0:
            color = 'green'
            prefix = '+'
        elif pnl < 0:
            color = 'red'
            prefix = ''
        else:
            color = 'gray'
            prefix = ''
            
        return format_html(
            '<span style="color: {};">{}{:.2f} USD</span>',
            color, prefix, pnl
        )
    total_pnl_display.short_description = 'Total P&L'
    
    
    
    
from django.contrib import admin
# =============================================================================
# BACKTESTING ADMIN (Lazy import to avoid circular dependency)
# =============================================================================

# Import backtest models only when admin is ready
try:
    from paper_trading.backtesting.models.backtest import BacktestRun, BacktestResult
    
    @admin.register(BacktestRun)
    class BacktestRunAdmin(admin.ModelAdmin):
        """Admin interface for BacktestRun model."""
        
        list_display = [
            'backtest_id',
            'strategy_type',
            'token_symbol',
            'status',
            'initial_balance_usd',
            'created_at',
            'duration_display',
        ]
        
        list_filter = [
            'strategy_type',
            'token_symbol',
            'status',
            'created_at',
        ]
        
        search_fields = [
            'backtest_id',
            'token_symbol',
            'error_message',
        ]
        
        readonly_fields = [
            'backtest_id',
            'created_at',
            'completed_at',
            'duration_display',
        ]
        
        fieldsets = (
            ('Identification', {
                'fields': ('backtest_id', 'status')
            }),
            ('Configuration', {
                'fields': (
                    'strategy_type',
                    'token_symbol',
                    'start_date',
                    'end_date',
                    'interval',
                    'initial_balance_usd',
                    'fee_percent',
                    'strategy_params',
                )
            }),
            ('Results', {
                'fields': (
                    'data_points',
                    'error_message',
                )
            }),
            ('Timestamps', {
                'fields': (
                    'created_at',
                    'completed_at',
                    'duration_display',
                )
            }),
        )
        
        ordering = ['-created_at']


    @admin.register(BacktestResult)
    class BacktestResultAdmin(admin.ModelAdmin):
        """Admin interface for BacktestResult model."""
        
        list_display = [
            'backtest_run',
            'return_percent',
            'profit_loss_usd',
            'win_rate_percent',
            'sharpe_ratio',
            'num_trades',
            'performance_grade',
        ]
        
        list_filter = [
            'created_at',
        ]
        
        search_fields = [
            'backtest_run__backtest_id',
            'backtest_run__token_symbol',
        ]
        
        readonly_fields = [
            'backtest_run',
            'created_at',
            'performance_grade',
        ]
        
        fieldsets = (
            ('Results Summary', {
                'fields': (
                    'backtest_run',
                    'final_balance_usd',
                    'profit_loss_usd',
                    'return_percent',
                    'performance_grade',
                )
            }),
            ('Trade Statistics', {
                'fields': (
                    'num_trades',
                    'num_buys',
                    'num_sells',
                    'total_fees_usd',
                    'avg_entry_price',
                )
            }),
            ('Performance Metrics', {
                'fields': (
                    'win_rate_percent',
                    'profit_factor',
                    'max_drawdown_percent',
                    'sharpe_ratio',
                    'sortino_ratio',
                    'avg_holding_hours',
                )
            }),
            ('Consecutive Stats', {
                'fields': (
                    'max_consecutive_wins',
                    'max_consecutive_losses',
                )
            }),
            ('Detailed Data', {
                'fields': (
                    'trades_data',
                    'metrics_data',
                ),
                'classes': ('collapse',),
            }),
            ('Timestamps', {
                'fields': ('created_at',)
            }),
        )
        
        ordering = ['-created_at']

except ImportError:
    # Backtesting models not available yet
    pass

# End of dexproject/paper_trading/admin.py