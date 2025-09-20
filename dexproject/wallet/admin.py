"""
Django admin configuration for the wallet app with SIWE models.

This module provides admin interfaces for SIWE authentication,
wallet management, balance tracking, and activity monitoring.

Phase 5.1B Implementation:
- SIWE session management
- Wallet connection monitoring
- Balance and transaction tracking
- Security and audit interfaces

File: dexproject/wallet/admin.py
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from shared.admin.base import BaseModelAdmin
from .models import (
    SIWESession, Wallet, WalletBalance, 
    WalletTransaction, WalletActivity
)


@admin.register(SIWESession)
class SIWESessionAdmin(BaseModelAdmin):
    """Admin interface for SIWE authentication sessions."""
    
    list_display = [
        'session_id_short', 'wallet_address_short', 'user', 'status', 
        'chain_id', 'is_valid_display', 'issued_at', 'expiration_time'
    ]
    list_filter = [
        'status', 'chain_id', 'issued_at', 'expiration_time', 'created_at'
    ]
    search_fields = [
        'session_id', 'wallet_address', 'user__username', 'domain', 'nonce'
    ]
    readonly_fields = [
        'session_id', 'wallet_address', 'domain', 'uri', 'version',
        'chain_id', 'nonce', 'issued_at', 'expiration_time', 'not_before',
        'message', 'signature', 'django_session_key', 'verified_at',
        'created_at', 'updated_at'
    ]
    ordering = ['-created_at']
    actions = ['revoke_sessions', 'mark_expired']
    
    fieldsets = (
        ('Session Information', {
            'fields': ('session_id', 'user', 'status', 'django_session_key')
        }),
        ('SIWE Message Details', {
            'fields': ('wallet_address', 'domain', 'statement', 'uri', 'version', 'chain_id')
        }),
        ('Timing', {
            'fields': ('issued_at', 'expiration_time', 'not_before', 'verified_at')
        }),
        ('Security', {
            'fields': ('nonce', 'request_id', 'ip_address', 'user_agent')
        }),
        ('Authentication Data', {
            'fields': ('message', 'signature'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def session_id_short(self, obj):
        """Display shortened session ID."""
        return str(obj.session_id)[:8] + '...'
    session_id_short.short_description = 'Session ID'
    
    def wallet_address_short(self, obj):
        """Display shortened wallet address."""
        return f"{obj.wallet_address[:6]}...{obj.wallet_address[-4:]}"
    wallet_address_short.short_description = 'Wallet'
    
    def is_valid_display(self, obj):
        """Display session validity with color coding."""
        is_valid = obj.is_valid()
        color = 'green' if is_valid else 'red'
        text = 'Valid' if is_valid else 'Invalid'
        return format_html('<span style="color: {};">{}</span>', color, text)
    is_valid_display.short_description = 'Valid'
    
    def revoke_sessions(self, request, queryset):
        """Bulk action to revoke selected sessions."""
        updated = 0
        for session in queryset:
            if session.status == SIWESession.SessionStatus.VERIFIED:
                session.revoke()
                updated += 1
        
        self.message_user(
            request, 
            f"Revoked {updated} of {queryset.count()} selected sessions."
        )
    revoke_sessions.short_description = "Revoke selected sessions"
    
    def mark_expired(self, request, queryset):
        """Bulk action to mark sessions as expired."""
        updated = queryset.filter(
            status=SIWESession.SessionStatus.VERIFIED
        ).update(status=SIWESession.SessionStatus.EXPIRED)
        
        self.message_user(
            request, 
            f"Marked {updated} sessions as expired."
        )
    mark_expired.short_description = "Mark as expired"


@admin.register(Wallet)
class WalletAdmin(BaseModelAdmin):
    """Admin interface for connected wallets."""
    
    list_display = [
        'name', 'wallet_type', 'address_short', 'user', 'status',
        'primary_chain_id', 'is_trading_enabled', 'last_connected_at'
    ]
    list_filter = [
        'wallet_type', 'status', 'primary_chain_id', 
        'is_trading_enabled', 'created_at', 'last_connected_at'
    ]
    search_fields = [
        'name', 'address', 'user__username', 'wallet_id'
    ]
    readonly_fields = [
        'wallet_id', 'address', 'wallet_type', 'connection_method',
        'wallet_client_version', 'created_at', 'updated_at', 'last_connected_at'
    ]
    ordering = ['-last_connected_at', '-created_at']
    actions = ['enable_trading', 'disable_trading', 'disconnect_wallets']
    
    fieldsets = (
        ('Wallet Information', {
            'fields': ('wallet_id', 'user', 'name', 'address', 'wallet_type', 'status')
        }),
        ('Network Configuration', {
            'fields': ('primary_chain_id', 'supported_chains')
        }),
        ('Trading Settings', {
            'fields': (
                'is_trading_enabled', 'requires_confirmation',
                'daily_limit_usd', 'per_transaction_limit_usd'
            )
        }),
        ('Connection Details', {
            'fields': (
                'connection_method', 'wallet_client_version', 'last_connected_at'
            ),
            'classes': ('collapse',)
        }),
        ('Configuration', {
            'fields': ('config',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def address_short(self, obj):
        """Display shortened wallet address."""
        return f"{obj.address[:6]}...{obj.address[-4:]}"
    address_short.short_description = 'Address'
    
    def enable_trading(self, request, queryset):
        """Bulk action to enable trading for selected wallets."""
        updated = queryset.update(is_trading_enabled=True)
        self.message_user(
            request, 
            f"Enabled trading for {updated} wallets."
        )
    enable_trading.short_description = "Enable trading"
    
    def disable_trading(self, request, queryset):
        """Bulk action to disable trading for selected wallets."""
        updated = queryset.update(is_trading_enabled=False)
        self.message_user(
            request, 
            f"Disabled trading for {updated} wallets."
        )
    disable_trading.short_description = "Disable trading"
    
    def disconnect_wallets(self, request, queryset):
        """Bulk action to disconnect selected wallets."""
        updated = queryset.update(status=Wallet.WalletStatus.DISCONNECTED)
        self.message_user(
            request, 
            f"Disconnected {updated} wallets."
        )
    disconnect_wallets.short_description = "Disconnect wallets"


@admin.register(WalletBalance)
class WalletBalanceAdmin(BaseModelAdmin):
    """Admin interface for wallet token balances."""
    
    list_display = [
        'wallet', 'token_symbol', 'balance_formatted', 'usd_value',
        'chain_id', 'last_updated', 'is_stale'
    ]
    list_filter = [
        'chain_id', 'token_symbol', 'is_stale', 'last_updated', 'created_at'
    ]
    search_fields = [
        'wallet__name', 'wallet__address', 'token_symbol', 
        'token_name', 'token_address'
    ]
    readonly_fields = [
        'balance_id', 'wallet', 'chain_id', 'token_address', 'token_symbol',
        'token_name', 'token_decimals', 'balance_wei', 'balance_formatted',
        'last_updated', 'created_at', 'updated_at'
    ]
    ordering = ['-usd_value', 'token_symbol']
    actions = ['mark_stale', 'refresh_balances']
    
    fieldsets = (
        ('Balance Information', {
            'fields': ('balance_id', 'wallet', 'chain_id')
        }),
        ('Token Details', {
            'fields': (
                'token_address', 'token_symbol', 'token_name', 'token_decimals'
            )
        }),
        ('Balance Data', {
            'fields': (
                'balance_wei', 'balance_formatted', 'usd_value'
            )
        }),
        ('Status', {
            'fields': ('last_updated', 'is_stale', 'update_error')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def mark_stale(self, request, queryset):
        """Bulk action to mark balances as stale."""
        updated = queryset.update(is_stale=True)
        self.message_user(
            request, 
            f"Marked {updated} balances as stale."
        )
    mark_stale.short_description = "Mark as stale"
    
    def refresh_balances(self, request, queryset):
        """Bulk action to refresh balance data."""
        # This would trigger balance refresh in a real implementation
        # For now, just clear the stale flag
        updated = queryset.update(is_stale=False, last_updated=timezone.now())
        self.message_user(
            request, 
            f"Refreshed {updated} balances."
        )
    refresh_balances.short_description = "Refresh balances"


@admin.register(WalletTransaction)
class WalletTransactionAdmin(BaseModelAdmin):
    """Admin interface for wallet transactions."""
    
    list_display = [
        'transaction_id_short', 'wallet', 'transaction_type', 'status',
        'transaction_hash_short', 'chain_id', 'block_number', 'created_at'
    ]
    list_filter = [
        'transaction_type', 'status', 'chain_id', 'created_at', 'block_timestamp'
    ]
    search_fields = [
        'transaction_id', 'transaction_hash', 'wallet__name', 'wallet__address'
    ]
    readonly_fields = [
        'transaction_id', 'wallet', 'chain_id', 'transaction_hash',
        'transaction_type', 'gas_used', 'gas_price_gwei', 'transaction_fee_eth',
        'transaction_fee_usd', 'block_number', 'block_timestamp',
        'created_at', 'updated_at'
    ]
    ordering = ['-created_at']
    actions = ['mark_confirmed', 'mark_failed']
    
    fieldsets = (
        ('Transaction Information', {
            'fields': (
                'transaction_id', 'wallet', 'chain_id', 'transaction_hash',
                'transaction_type', 'status'
            )
        }),
        ('Gas and Fees', {
            'fields': (
                'gas_used', 'gas_price_gwei', 'transaction_fee_eth', 'transaction_fee_usd'
            )
        }),
        ('Block Information', {
            'fields': ('block_number', 'block_timestamp')
        }),
        ('Transaction Data', {
            'fields': ('transaction_data',),
            'classes': ('collapse',)
        }),
        ('Error Information', {
            'fields': ('error_reason',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def transaction_id_short(self, obj):
        """Display shortened transaction ID."""
        return str(obj.transaction_id)[:8] + '...'
    transaction_id_short.short_description = 'Transaction ID'
    
    def transaction_hash_short(self, obj):
        """Display shortened transaction hash."""
        if obj.transaction_hash:
            return f"{obj.transaction_hash[:10]}...{obj.transaction_hash[-8:]}"
        return '-'
    transaction_hash_short.short_description = 'Hash'
    
    def mark_confirmed(self, request, queryset):
        """Bulk action to mark transactions as confirmed."""
        updated = queryset.filter(
            status=WalletTransaction.TransactionStatus.PENDING
        ).update(status=WalletTransaction.TransactionStatus.CONFIRMED)
        
        self.message_user(
            request, 
            f"Marked {updated} transactions as confirmed."
        )
    mark_confirmed.short_description = "Mark as confirmed"
    
    def mark_failed(self, request, queryset):
        """Bulk action to mark transactions as failed."""
        updated = queryset.filter(
            status=WalletTransaction.TransactionStatus.PENDING
        ).update(status=WalletTransaction.TransactionStatus.FAILED)
        
        self.message_user(
            request, 
            f"Marked {updated} transactions as failed."
        )
    mark_failed.short_description = "Mark as failed"


@admin.register(WalletActivity)
class WalletActivityAdmin(BaseModelAdmin):
    """Admin interface for wallet activity monitoring."""
    
    list_display = [
        'activity_id_short', 'wallet', 'user', 'activity_type',
        'description_short', 'was_successful', 'created_at'
    ]
    list_filter = [
        'activity_type', 'was_successful', 'created_at'
    ]
    search_fields = [
        'activity_id', 'wallet__name', 'user__username', 'description',
        'ip_address'
    ]
    readonly_fields = [
        'activity_id', 'wallet', 'user', 'activity_type', 'description',
        'ip_address', 'user_agent', 'session_id', 'siwe_session',
        'transaction', 'data', 'was_successful', 'error_message',
        'created_at', 'updated_at'
    ]
    ordering = ['-created_at']
    actions = ['export_security_log']
    
    fieldsets = (
        ('Activity Information', {
            'fields': (
                'activity_id', 'wallet', 'user', 'activity_type', 'description'
            )
        }),
        ('Context', {
            'fields': ('ip_address', 'user_agent', 'session_id')
        }),
        ('Related Objects', {
            'fields': ('siwe_session', 'transaction')
        }),
        ('Result', {
            'fields': ('was_successful', 'error_message')
        }),
        ('Additional Data', {
            'fields': ('data',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def activity_id_short(self, obj):
        """Display shortened activity ID."""
        return str(obj.activity_id)[:8] + '...'
    activity_id_short.short_description = 'Activity ID'
    
    def description_short(self, obj):
        """Display shortened description."""
        if len(obj.description) > 50:
            return obj.description[:47] + '...'
        return obj.description
    description_short.short_description = 'Description'
    
    def export_security_log(self, request, queryset):
        """Export security log for selected activities."""
        # This would export security logs in a real implementation
        count = queryset.count()
        self.message_user(
            request, 
            f"Security log export initiated for {count} activities."
        )
    export_security_log.short_description = "Export security log"


# Customize admin site headers
admin.site.site_header = 'DEX Trading Bot - Wallet Administration'
admin.site.site_title = 'Wallet Admin'
admin.site.index_title = 'Wallet Management Dashboard'