"""
Django admin configuration for the trading app.
"""

from django.contrib import admin
from .models import Chain, DEX, Token, TradingPair, Strategy, Trade, Position

@admin.register(Chain)
class ChainAdmin(admin.ModelAdmin):
    list_display = ['name', 'chain_id', 'rpc_url_short', 'gas_price_gwei', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'chain_id']
    readonly_fields = ['created_at', 'updated_at']
    
    def rpc_url_short(self, obj):
        if len(obj.rpc_url) > 50:
            return obj.rpc_url[:47] + '...'
        return obj.rpc_url
    rpc_url_short.short_description = 'RPC URL'

@admin.register(DEX)  
class DEXAdmin(admin.ModelAdmin):
    list_display = ['name', 'chain', 'router_address_short', 'fee_percentage', 'is_active', 'created_at']
    list_filter = ['chain', 'is_active', 'created_at']
    search_fields = ['name', 'router_address', 'factory_address']
    readonly_fields = ['created_at', 'updated_at']
    
    def router_address_short(self, obj):
        return f"{obj.router_address[:10]}...{obj.router_address[-8:]}"
    router_address_short.short_description = 'Router'

@admin.register(Token)
class TokenAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'name', 'chain', 'address_short', 'decimals', 'is_verified', 'is_honeypot', 'is_blacklisted']
    list_filter = ['chain', 'is_verified', 'is_honeypot', 'is_blacklisted', 'decimals']
    search_fields = ['symbol', 'name', 'address']
    readonly_fields = ['created_at', 'updated_at']
    actions = ['mark_as_verified', 'mark_as_honeypot', 'mark_as_blacklisted']
    
    def address_short(self, obj):
        return f"{obj.address[:10]}...{obj.address[-8:]}"
    address_short.short_description = 'Address'
    
    def mark_as_verified(self, request, queryset):
        queryset.update(is_verified=True)
        self.message_user(request, f"Marked {queryset.count()} tokens as verified.")
    mark_as_verified.short_description = "Mark as verified"
    
    def mark_as_honeypot(self, request, queryset):
        queryset.update(is_honeypot=True)
        self.message_user(request, f"Marked {queryset.count()} tokens as honeypots.")
    mark_as_honeypot.short_description = "Mark as honeypot"
    
    def mark_as_blacklisted(self, request, queryset):
        queryset.update(is_blacklisted=True)
        self.message_user(request, f"Marked {queryset.count()} tokens as blacklisted.")
    mark_as_blacklisted.short_description = "Mark as blacklisted"

@admin.register(TradingPair)
class TradingPairAdmin(admin.ModelAdmin):
    list_display = ['pair_name', 'dex', 'pair_address_short', 'liquidity_usd', 'volume_24h_usd', 'is_active', 'discovered_at']
    list_filter = ['dex', 'is_active', 'discovered_at']
    search_fields = ['token0__symbol', 'token1__symbol', 'pair_address']
    readonly_fields = ['discovered_at', 'last_updated']
    ordering = ['-liquidity_usd']
    
    def pair_name(self, obj):
        return f"{obj.token0.symbol}/{obj.token1.symbol}"
    pair_name.short_description = 'Pair'
    
    def pair_address_short(self, obj):
        return f"{obj.pair_address[:10]}...{obj.pair_address[-8:]}"
    pair_address_short.short_description = 'Address'

@admin.register(Strategy)
class StrategyAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'max_position_size_eth', 'max_slippage_percent', 'take_profit_percent', 'stop_loss_percent']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = ['trade_id_short', 'trade_type', 'pair', 'amount_in', 'price_usd', 'status', 'slippage_percent', 'created_at']
    list_filter = ['trade_type', 'status', 'pair__dex', 'created_at']
    search_fields = ['trade_id', 'transaction_hash', 'pair__token0__symbol', 'pair__token1__symbol']
    readonly_fields = ['trade_id', 'created_at', 'executed_at', 'confirmed_at']
    ordering = ['-created_at']
    
    def trade_id_short(self, obj):
        return str(obj.trade_id)[:8] + '...'
    trade_id_short.short_description = 'Trade ID'

@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ['position_id_short', 'pair', 'status', 'total_amount_in', 'current_amount', 'total_pnl_usd_display', 'opened_at']
    list_filter = ['status', 'pair__dex', 'opened_at']
    search_fields = ['position_id', 'pair__token0__symbol', 'pair__token1__symbol']
    readonly_fields = ['position_id', 'opened_at', 'closed_at', 'last_updated']
    ordering = ['-opened_at']
    
    def position_id_short(self, obj):
        return str(obj.position_id)[:8] + '...'
    position_id_short.short_description = 'Position ID'
    
    def total_pnl_usd_display(self, obj):
        pnl = obj.total_pnl_usd
        color = 'green' if pnl >= 0 else 'red'
        return f'<span style="color: {color};">${pnl:.2f}</span>'
    total_pnl_usd_display.short_description = 'Total PnL'
    total_pnl_usd_display.allow_tags = True