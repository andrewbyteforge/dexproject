"""
Paper Trading Admin Interface - Enhanced for PTphase1

Django admin configuration for all paper trading models including
the new enhanced models for AI thought logs, strategy configuration,
performance metrics, and trading sessions.

File: dexproject/paper_trading/admin.py
"""

from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Sum, Avg, Count
from .models import (
    # Existing models
    PaperTradingAccount,
    PaperTrade,
    PaperPosition,
    PaperTradingConfig,
    # New enhanced models for PTphase1
    PaperAIThoughtLog,
    PaperStrategyConfiguration,
    PaperPerformanceMetrics,
    PaperTradingSession
)


# =============================================================================
# EXISTING MODEL ADMINS
# =============================================================================

@admin.register(PaperTradingAccount)
class PaperTradingAccountAdmin(admin.ModelAdmin):
    """Admin interface for Paper Trading Accounts."""
    
    list_display = [
        'name', 'user', 'current_balance_usd', 
        'total_pnl_usd', 'win_rate_display', 'is_active',
        'total_trades', 'created_at'
    ]
    list_filter = ['is_active', 'created_at', 'user']
    search_fields = ['name', 'user__username']
    readonly_fields = [
        'account_id', 'created_at', 'updated_at',
        'total_trades', 'successful_trades', 'failed_trades',
        'win_rate', 'total_return_percent'
    ]
    
    fieldsets = (
        ('Account Info', {
            'fields': ('account_id', 'user', 'name', 'is_active')
        }),
        ('Balances', {
            'fields': (
                'initial_balance_usd', 'current_balance_usd',
                'eth_balance'
            )
        }),
        ('Performance', {
            'fields': (
                'total_trades', 'successful_trades', 'failed_trades',
                'total_pnl_usd', 'total_fees_paid_usd',
                'win_rate', 'total_return_percent'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'reset_count')
        })
    )
    
    actions = ['reset_accounts']
    
    def win_rate_display(self, obj):
        """Display win rate with color coding."""
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
    
    def reset_accounts(self, request, queryset):
        """Reset selected accounts to initial state."""
        for account in queryset:
            account.reset_account()
        self.message_user(
            request,
            f"Reset {queryset.count()} account(s)"
        )
    reset_accounts.short_description = "Reset selected accounts"


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
                'strategy_name', 'error_message'
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
# ENHANCED MODEL ADMINS FOR PTPHASE1
# =============================================================================

@admin.register(PaperAIThoughtLog)
class PaperAIThoughtLogAdmin(admin.ModelAdmin):
    """Admin interface for AI Thought Logs."""
    
    list_display = [
        'thought_id_short', 'account', 'decision_type', 'token_symbol',
        'confidence_display', 'risk_score_display', 'lane_used',
        'created_at'
    ]
    list_filter = [
        'decision_type', 'confidence_level', 'lane_used',
        'created_at', 'account'
    ]
    search_fields = [
        'thought_id', 'token_symbol', 'token_address',
        'strategy_name', 'primary_reasoning'
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
                'confidence_level', 'confidence_percent',
                'risk_score', 'opportunity_score'
            )
        }),
        ('Reasoning', {
            'fields': (
                'primary_reasoning', 'key_factors',
                'positive_signals', 'negative_signals'
            ),
            'classes': ('collapse',)
        }),
        ('Market Data', {
            'fields': ('market_data',),
            'classes': ('collapse',)
        }),
        ('Performance', {
            'fields': ('analysis_time_ms', 'created_at')
        })
    )
    
    def thought_id_short(self, obj):
        """Display shortened thought ID."""
        return str(obj.thought_id)[:8] + '...'
    thought_id_short.short_description = 'Thought ID'
    
    def confidence_display(self, obj):
        """Display confidence with emoji."""
        emoji = {
            'VERY_HIGH': '🟢',
            'HIGH': '🟢',
            'MEDIUM': '🟡',
            'LOW': '🟠',
            'VERY_LOW': '🔴'
        }.get(obj.confidence_level, '❓')
        return format_html(
            '{} {:.1f}%',
            emoji, obj.confidence_percent
        )
    confidence_display.short_description = 'Confidence'
    
    def risk_score_display(self, obj):
        """Display risk score with color."""
        score = obj.risk_score
        if score >= 70:
            color = 'red'
        elif score >= 40:
            color = 'orange'
        else:
            color = 'green'
        return format_html(
            '<span style="color: {};">{:.1f}</span>',
            color, score
        )
    risk_score_display.short_description = 'Risk Score'


@admin.register(PaperStrategyConfiguration)
class PaperStrategyConfigurationAdmin(admin.ModelAdmin):
    """Admin interface for Strategy Configurations."""
    
    list_display = [
        'name', 'account', 'trading_mode', 'is_active',
        'lanes_enabled', 'confidence_threshold',
        'max_position_size_percent', 'created_at'
    ]
    list_filter = [
        'is_active', 'trading_mode', 'use_fast_lane',
        'use_smart_lane', 'created_at'
    ]
    search_fields = ['name', 'account__name']
    readonly_fields = ['config_id', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Identity', {
            'fields': ('config_id', 'account', 'name', 'is_active')
        }),
        ('Trading Mode', {
            'fields': ('trading_mode',)
        }),
        ('Lane Configuration', {
            'fields': (
                'use_fast_lane', 'use_smart_lane',
                'fast_lane_threshold_usd'
            )
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
            'fields': ('allowed_tokens', 'blocked_tokens'),
            'classes': ('collapse',)
        }),
        ('Advanced Settings', {
            'fields': ('custom_parameters',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        })
    )
    
    def lanes_enabled(self, obj):
        """Display which lanes are enabled."""
        lanes = []
        if obj.use_fast_lane:
            lanes.append('⚡ Fast')
        if obj.use_smart_lane:
            lanes.append('🧠 Smart')
        return ' | '.join(lanes) if lanes else '❌ None'
    lanes_enabled.short_description = 'Lanes'


@admin.register(PaperPerformanceMetrics)
class PaperPerformanceMetricsAdmin(admin.ModelAdmin):
    """Admin interface for Performance Metrics."""
    
    list_display = [
        'metrics_id_short', 'session', 'period_display',
        'win_rate_display', 'total_pnl_display',
        'sharpe_ratio', 'max_drawdown_percent'
    ]
    list_filter = ['period_end', 'win_rate']
    search_fields = ['metrics_id', 'session__session_id']
    readonly_fields = [
        'metrics_id', 'calculated_at', 'profit_factor'
    ]
    
    fieldsets = (
        ('Identity', {
            'fields': ('metrics_id', 'session')
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
                'avg_win_usd', 'avg_loss_usd',
                'largest_win_usd', 'largest_loss_usd'
            )
        }),
        ('Risk Metrics', {
            'fields': (
                'sharpe_ratio', 'max_drawdown_percent',
                'profit_factor'
            )
        }),
        ('Execution Metrics', {
            'fields': (
                'avg_execution_time_ms', 'total_gas_fees_usd',
                'avg_slippage_percent'
            )
        }),
        ('Strategy Metrics', {
            'fields': (
                'fast_lane_trades', 'smart_lane_trades',
                'fast_lane_win_rate', 'smart_lane_win_rate'
            )
        }),
        ('Metadata', {
            'fields': ('calculated_at',)
        })
    )
    
    def metrics_id_short(self, obj):
        """Display shortened metrics ID."""
        return str(obj.metrics_id)[:8] + '...'
    metrics_id_short.short_description = 'Metrics ID'
    
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
        'session_id_short', 'account', 'name', 'status_display',
        'duration_display', 'trades_display', 'session_pnl_display',
        'started_at'
    ]
    list_filter = [
        'status', 'started_at', 'account'
    ]
    search_fields = [
        'session_id', 'name', 'account__name'
    ]
    readonly_fields = [
        'session_id', 'started_at', 'ended_at',
        'last_heartbeat', 'duration_seconds', 'is_active'
    ]
    
    fieldsets = (
        ('Identity', {
            'fields': (
                'session_id', 'account', 'strategy_config',
                'name'
            )
        }),
        ('Status', {
            'fields': (
                'status', 'is_active', 'last_heartbeat'
            )
        }),
        ('Timing', {
            'fields': (
                'started_at', 'ended_at', 'duration_seconds'
            )
        }),
        ('Statistics', {
            'fields': (
                'total_trades_executed', 'successful_trades',
                'failed_trades', 'session_pnl_usd',
                'starting_balance_usd', 'ending_balance_usd'
            )
        }),
        ('Error Tracking', {
            'fields': (
                'error_count', 'last_error_message',
                'last_error_time'
            ),
            'classes': ('collapse',)
        }),
        ('Configuration', {
            'fields': ('config_snapshot',),
            'classes': ('collapse',)
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('collapse',)
        })
    )
    
    actions = ['stop_sessions', 'pause_sessions', 'resume_sessions']
    
    def session_id_short(self, obj):
        """Display shortened session ID."""
        return str(obj.session_id)[:8] + '...'
    session_id_short.short_description = 'Session ID'
    
    def status_display(self, obj):
        """Display status with emoji."""
        emoji = {
            'STARTING': '🚀',
            'RUNNING': '✅',
            'PAUSED': '⏸️',
            'STOPPING': '🛑',
            'STOPPED': '⏹️',
            'ERROR': '❌'
        }.get(obj.status, '❓')
        return format_html('{} {}', emoji, obj.get_status_display())
    status_display.short_description = 'Status'
    
    def duration_display(self, obj):
        """Display session duration."""
        seconds = obj.duration_seconds
        if seconds is None:
            return 'N/A'
        
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"
    duration_display.short_description = 'Duration'
    
    def trades_display(self, obj):
        """Display trade statistics."""
        total = obj.total_trades_executed
        success = obj.successful_trades
        if total > 0:
            rate = (success / total) * 100
            return format_html(
                '{} trades ({:.0f}% success)',
                total, rate
            )
        return '0 trades'
    trades_display.short_description = 'Trades'
    
    def session_pnl_display(self, obj):
        """Display session P&L."""
        pnl = obj.session_pnl_usd
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
    session_pnl_display.short_description = 'Session P&L'
    
    def stop_sessions(self, request, queryset):
        """Stop selected sessions."""
        for session in queryset.filter(status__in=['RUNNING', 'PAUSED']):
            session.stop_session(reason="Stopped by admin")
        self.message_user(
            request,
            f"Stopped {queryset.count()} session(s)"
        )
    stop_sessions.short_description = "Stop selected sessions"
    
    def pause_sessions(self, request, queryset):
        """Pause selected sessions."""
        count = queryset.filter(status='RUNNING').update(
            status='PAUSED'
        )
        self.message_user(request, f"Paused {count} session(s)")
    pause_sessions.short_description = "Pause selected sessions"
    
    def resume_sessions(self, request, queryset):
        """Resume selected sessions."""
        count = queryset.filter(status='PAUSED').update(
            status='RUNNING'
        )
        self.message_user(request, f"Resumed {count} session(s)")
    resume_sessions.short_description = "Resume selected sessions"