"""
Django admin configuration for the dashboard app.
"""

from django.contrib import admin
from shared.admin.base import BaseModelAdmin
from django.utils.html import format_html
from .models import (
    UserProfile, BotConfiguration, TokenWhitelistEntry,
    TokenBlacklistEntry, TradingSession, Alert, SystemStatus
)

@admin.register(UserProfile)
class UserProfileAdmin(BaseModelAdmin):
    list_display = ['user', 'display_name', 'experience_level', 'risk_tolerance', 'onboarding_completed', 'two_factor_enabled', 'created_at']
    list_filter = ['experience_level', 'risk_tolerance', 'onboarding_completed', 'two_factor_enabled', 'api_access_enabled', 'created_at']
    search_fields = ['user__username', 'display_name', 'user__email']
    readonly_fields = ['profile_id', 'created_at', 'updated_at']
    ordering = ['-created_at']

@admin.register(BotConfiguration)
class BotConfigurationAdmin(BaseModelAdmin):
    list_display = ['name', 'user', 'status', 'trading_mode', 'strategy', 'max_position_size_usd', 'is_default', 'last_used_at']
    list_filter = ['status', 'trading_mode', 'is_default', 'auto_execution_enabled', 'require_manual_approval', 'created_at']
    search_fields = ['name', 'description', 'user__username']
    readonly_fields = ['config_id', 'version', 'created_at', 'updated_at', 'last_used_at']
    ordering = ['-last_used_at', '-updated_at']

@admin.register(TokenWhitelistEntry)
class TokenWhitelistEntryAdmin(BaseModelAdmin):
    list_display = ['config', 'token', 'max_position_size_usd', 'max_slippage_percent', 'added_by', 'added_at']
    list_filter = ['config', 'token__chain', 'added_at']
    search_fields = ['token__symbol', 'token__name', 'config__name']
    readonly_fields = ['added_at']
    ordering = ['-added_at']

@admin.register(TokenBlacklistEntry)
class TokenBlacklistEntryAdmin(BaseModelAdmin):
    list_display = ['config', 'token', 'reason', 'is_permanent', 'is_active_display', 'risk_score', 'added_at']
    list_filter = ['reason', 'is_permanent', 'config', 'token__chain', 'added_at']
    search_fields = ['token__symbol', 'token__name', 'description']
    readonly_fields = ['added_at', 'reviewed_at']
    ordering = ['-added_at']
    
    def is_active_display(self, obj):
        is_active = obj.is_active
        color = 'red' if is_active else 'gray'
        text = 'Active' if is_active else 'Expired'
        return format_html('<span style="color: {};">{}</span>', color, text)
    is_active_display.short_description = 'Status'

@admin.register(TradingSession)
class TradingSessionAdmin(BaseModelAdmin):
    list_display = ['session_id_short', 'name', 'user', 'status', 'trading_mode', 'success_rate_display', 'total_pnl_usd', 'started_at']
    list_filter = ['status', 'trading_mode', 'daily_limit_hit', 'emergency_stop_triggered', 'started_at']
    search_fields = ['session_id', 'name', 'user__username']
    readonly_fields = ['session_id', 'started_at', 'paused_at', 'stopped_at', 'last_activity_at']
    ordering = ['-started_at']
    actions = ['emergency_stop_sessions', 'pause_sessions']
    
    def session_id_short(self, obj):
        return str(obj.session_id)[:8] + '...'
    session_id_short.short_description = 'Session ID'
    
    def success_rate_display(self, obj):
        success_rate = obj.success_rate_percent
        if success_rate is not None:
            color = 'green' if success_rate >= 70 else 'orange' if success_rate >= 50 else 'red'
            return format_html('<span style="color: {};">{:.1f}%</span>', color, success_rate)
        return '-'
    success_rate_display.short_description = 'Success Rate'
    
    def emergency_stop_sessions(self, request, queryset):
        queryset.update(status='EMERGENCY_STOP', emergency_stop_triggered=True)
        self.message_user(request, f"Emergency stopped {queryset.count()} sessions.")
    emergency_stop_sessions.short_description = "Emergency stop sessions"
    
    def pause_sessions(self, request, queryset):
        from django.utils import timezone
        queryset.update(status='PAUSED', paused_at=timezone.now())
        self.message_user(request, f"Paused {queryset.count()} sessions.")
    pause_sessions.short_description = "Pause sessions"
    
        
        
    def emergency_stop_sessions(self, request, queryset):
        queryset.update(status='EMERGENCY_STOP', emergency_stop_triggered=True)
        self.message_user(request, f"Emergency stopped {queryset.count()} sessions.")
    emergency_stop_sessions.short_description = "Emergency stop sessions"
    
    def pause_sessions(self, request, queryset):
        from django.utils import timezone
        queryset.update(status='PAUSED', paused_at=timezone.now())
        self.message_user(request, f"Paused {queryset.count()} sessions.")
    pause_sessions.short_description = "Pause sessions"

@admin.register(Alert)
class AlertAdmin(BaseModelAdmin):
    list_display = ['alert_id_short', 'user', 'alert_type', 'severity', 'title', 'status', 'action_required', 'created_at']
    list_filter = ['alert_type', 'severity', 'status', 'action_required', 'email_sent', 'sms_sent', 'push_sent', 'created_at']
    search_fields = ['alert_id', 'title', 'message', 'user__username']
    readonly_fields = ['alert_id', 'created_at', 'read_at', 'dismissed_at']
    ordering = ['-created_at']
    actions = ['mark_as_read', 'mark_as_dismissed', 'mark_as_unread']
    
    def alert_id_short(self, obj):
        return str(obj.alert_id)[:8] + '...'
    alert_id_short.short_description = 'Alert ID'
    
    def mark_as_read(self, request, queryset):
        from django.utils import timezone
        queryset.update(status='READ', read_at=timezone.now())
        self.message_user(request, f"Marked {queryset.count()} alerts as read.")
    mark_as_read.short_description = "Mark as read"
    
    def mark_as_dismissed(self, request, queryset):
        from django.utils import timezone
        queryset.update(status='DISMISSED', dismissed_at=timezone.now())
        self.message_user(request, f"Dismissed {queryset.count()} alerts.")
    mark_as_dismissed.short_description = "Mark as dismissed"
    
    def mark_as_unread(self, request, queryset):
        queryset.update(status='UNREAD', read_at=None, dismissed_at=None)
        self.message_user(request, f"Marked {queryset.count()} alerts as unread.")
    mark_as_unread.short_description = "Mark as unread"

@admin.register(SystemStatus)
class SystemStatusAdmin(BaseModelAdmin):
    list_display = ['status_id_short', 'overall_status_display', 'trading_engine_status', 'active_sessions', 'active_users', 'uptime_percent', 'created_at']
    list_filter = ['trading_engine_status', 'risk_engine_status', 'wallet_service_status', 'api_service_status', 'created_at']
    search_fields = ['status_id', 'status_message', 'incident_id']
    readonly_fields = ['status_id', 'created_at']
    ordering = ['-created_at']
    
    def status_id_short(self, obj):
        return str(obj.status_id)[:8] + '...'
    status_id_short.short_description = 'Status ID'
    
    def overall_status_display(self, obj):
        status = obj.overall_status
        color_map = {
            'OPERATIONAL': 'green',
            'DEGRADED': 'orange',
            'PARTIAL_OUTAGE': 'red',
            'MAJOR_OUTAGE': 'darkred',
            'MAINTENANCE': 'blue'
        }
        color = color_map.get(status, 'black')
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, status.replace('_', ' ').title())
    overall_status_display.short_description = 'Overall Status'



from .models import FundAllocation

@admin.register(FundAllocation)
class FundAllocationAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'allocation_method', 'allocation_percentage', 'allocation_fixed_amount',
        'risk_level', 'daily_spending_limit', 'is_active', 'last_modified_by_user'
    ]
    list_filter = [
        'allocation_method', 'risk_level', 'is_active', 'auto_rebalance_enabled',
        'stop_loss_enabled', 'last_daily_reset', 'created_at'
    ]
    search_fields = ['user__username', 'user__email', 'notes']
    readonly_fields = [
        'allocation_id', 'risk_level', 'daily_spent_today', 'last_daily_reset',
        'total_allocated_eth', 'created_at', 'updated_at'
    ]
    ordering = ['-last_modified_by_user']