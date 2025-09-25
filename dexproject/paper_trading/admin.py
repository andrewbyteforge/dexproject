"""
Paper Trading Admin Interface

Django admin configuration for paper trading models.

File: dexproject/paper_trading/admin.py
"""

from django.contrib import admin
from .models import (
    PaperTradingAccount,
    PaperTrade,
    PaperPosition,
    PaperTradingConfig
)


@admin.register(PaperTradingAccount)
class PaperTradingAccountAdmin(admin.ModelAdmin):
    """Admin interface for Paper Trading Accounts."""
    
    list_display = [
        'name', 'user', 'current_balance_usd', 
        'total_pnl_usd', 'win_rate', 'is_active'
    ]
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'user__username']
    readonly_fields = [
        'account_id', 'created_at', 'updated_at',
        'total_trades', 'successful_trades', 'failed_trades'
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
                'total_pnl_usd', 'total_fees_paid_usd'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'reset_count')
        })
    )
    
    actions = ['reset_accounts']
    
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
        'trade_id', 'account', 'trade_type', 
        'token_in_symbol', 'token_out_symbol',
        'status', 'created_at'
    ]
    list_filter = ['status', 'trade_type', 'created_at']
    search_fields = [
        'trade_id', 'token_in_symbol', 'token_out_symbol',
        'account__name'
    ]
    readonly_fields = ['trade_id', 'created_at', 'executed_at']
    
    fieldsets = (
        ('Trade Identity', {
            'fields': ('trade_id', 'account', 'trade_type', 'status')
        }),
        ('Tokens', {
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
        ('Transaction', {
            'fields': ('mock_tx_hash', 'mock_block_number')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'executed_at')
        })
    )


@admin.register(PaperPosition)
class PaperPositionAdmin(admin.ModelAdmin):
    """Admin interface for Paper Positions."""
    
    list_display = [
        'token_symbol', 'account', 'quantity',
        'unrealized_pnl_usd', 'is_open'
    ]
    list_filter = ['is_open', 'opened_at']
    search_fields = ['token_symbol', 'token_address', 'account__name']
    readonly_fields = [
        'position_id', 'opened_at', 'closed_at', 'last_updated'
    ]


@admin.register(PaperTradingConfig)
class PaperTradingConfigAdmin(admin.ModelAdmin):
    """Admin interface for Paper Trading Configuration."""
    
    list_display = [
        'account', 'base_slippage_percent',
        'max_position_size_percent', 'max_daily_trades'
    ]
    search_fields = ['account__name']
