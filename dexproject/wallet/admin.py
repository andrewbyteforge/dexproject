"""
Django admin configuration for the wallet app.
"""

from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Wallet, WalletBalance, Transaction, TransactionReceipt,
    WalletAuthorization, WalletActivity
)

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ['name', 'wallet_type', 'address_short', 'chain', 'status', 'is_trading_enabled', 'daily_limit_usd', 'last_used_at']
    list_filter = ['wallet_type', 'status', 'chain', 'is_trading_enabled', 'created_at']
    search_fields = ['name', 'address', 'user__username']
    readonly_fields = ['wallet_id', 'created_at', 'updated_at', 'last_used_at']
    ordering = ['-last_used_at', '-created_at']
    actions = ['enable_trading', 'disable_trading', 'lock_wallets']
    
    def address_short(self, obj):
        return f"{obj.address[:10]}...{obj.address[-8:]}"
    address_short.short_description = 'Address'
    
    def enable_trading(self, request, queryset):
        queryset.update(is_trading_enabled=True)
        self.message_user(request, f"Enabled trading for {queryset.count()} wallets.")
    enable_trading.short_description = "Enable trading"
    
    def disable_trading(self, request, queryset):
        queryset.update(is_trading_enabled=False)
        self.message_user(request, f"Disabled trading for {queryset.count()} wallets.")
    disable_trading.short_description = "Disable trading"
    
    def lock_wallets(self, request, queryset):
        queryset.update(status='LOCKED')
        self.message_user(request, f"Locked {queryset.count()} wallets.")
    lock_wallets.short_description = "Lock wallets"

@admin.register(WalletBalance)
class WalletBalanceAdmin(admin.ModelAdmin):
    list_display = ['wallet', 'token', 'balance', 'balance_usd', 'available_balance', 'locked_balance', 'is_active', 'last_updated']
    list_filter = ['token__symbol', 'wallet__chain', 'is_active', 'last_updated']
    search_fields = ['wallet__name', 'token__symbol', 'wallet__address']
    readonly_fields = ['balance_id', 'last_updated', 'last_sync_block']
    ordering = ['-balance_usd', 'token__symbol']

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['transaction_id_short', 'wallet', 'transaction_type', 'status', 'to_address_short', 'value_eth', 'gas_used', 'submitted_at']
    list_filter = ['transaction_type', 'status', 'wallet__chain', 'submitted_at']
    search_fields = ['transaction_id', 'transaction_hash', 'wallet__name', 'to_address']
    readonly_fields = ['transaction_id', 'created_at', 'updated_at', 'submitted_at', 'confirmed_at', 'failed_at']
    ordering = ['-created_at']
    
    def transaction_id_short(self, obj):
        return str(obj.transaction_id)[:8] + '...'
    transaction_id_short.short_description = 'Transaction ID'
    
    def to_address_short(self, obj):
        return f"{obj.to_address[:10]}...{obj.to_address[-8:]}"
    to_address_short.short_description = 'To Address'
    
    def value_eth(self, obj):
        if obj.value_wei:
            return float(obj.value_wei) / 10**18
        return 0
    value_eth.short_description = 'Value (ETH)'

@admin.register(TransactionReceipt)
class TransactionReceiptAdmin(admin.ModelAdmin):
    list_display = ['receipt_id_short', 'transaction', 'status', 'cumulative_gas_used', 'effective_gas_price', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['receipt_id', 'transaction__transaction_hash']
    readonly_fields = ['receipt_id', 'created_at']
    
    def receipt_id_short(self, obj):
        return str(obj.receipt_id)[:8] + '...'
    receipt_id_short.short_description = 'Receipt ID'

@admin.register(WalletAuthorization)
class WalletAuthorizationAdmin(admin.ModelAdmin):
    list_display = ['authorization_id_short', 'wallet', 'user', 'authorization_type', 'status', 'is_valid_display', 'spending_limit_usd', 'created_at']
    list_filter = ['authorization_type', 'status', 'created_at']
    search_fields = ['authorization_id', 'wallet__name', 'user__username']
    readonly_fields = ['authorization_id', 'created_at', 'approved_at', 'last_used_at']
    ordering = ['-created_at']
    
    def authorization_id_short(self, obj):
        return str(obj.authorization_id)[:8] + '...'
    authorization_id_short.short_description = 'Authorization ID'
    
    def is_valid_display(self, obj):
        is_valid = obj.is_valid
        color = 'green' if is_valid else 'red'
        text = 'Valid' if is_valid else 'Invalid'
        return format_html('<span style="color: {};">{}</span>', color, text)
    is_valid_display.short_description = 'Valid'

@admin.register(WalletActivity)
class WalletActivityAdmin(admin.ModelAdmin):
    list_display = ['activity_id_short', 'wallet', 'user', 'activity_type', 'description', 'was_successful', 'created_at']
    list_filter = ['activity_type', 'was_successful', 'created_at']
    search_fields = ['activity_id', 'wallet__name', 'user__username', 'description']
    readonly_fields = ['activity_id', 'created_at']
    ordering = ['-created_at']
    
    def activity_id_short(self, obj):
        return str(obj.activity_id)[:8] + '...'
    activity_id_short.short_description = 'Activity ID'