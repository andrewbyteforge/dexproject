"""
Django admin configuration for the analytics app.
"""

from django.contrib import admin
from shared.admin.base import BaseModelAdmin
from django.utils.html import format_html
from .models import (
    DecisionContext, DecisionFeature, ThoughtLog, DecisionMetrics,
    LearningSession, ModelPerformance, FeatureImportance
)

@admin.register(DecisionContext)
class DecisionContextAdmin(BaseModelAdmin):
    list_display = ['context_id_short', 'decision_type', 'pair', 'token', 'strategy', 'discovery_latency_ms', 'created_at']
    list_filter = ['decision_type', 'pair__dex', 'strategy', 'created_at']
    search_fields = ['context_id', 'token__symbol', 'pair__token0__symbol']
    readonly_fields = ['context_id', 'created_at']
    ordering = ['-created_at']
    
    def context_id_short(self, obj):
        return str(obj.context_id)[:8] + '...'
    context_id_short.short_description = 'Context ID'

@admin.register(DecisionFeature)
class DecisionFeatureAdmin(BaseModelAdmin):
    list_display = ['feature_id_short', 'context', 'name', 'category', 'data_type', 'weight', 'confidence']
    list_filter = ['category', 'data_type', 'created_at']
    search_fields = ['feature_id', 'name', 'context__context_id']
    readonly_fields = ['feature_id', 'created_at']
    ordering = ['-created_at']
    
    def feature_id_short(self, obj):
        return str(obj.feature_id)[:8] + '...'
    feature_id_short.short_description = 'Feature ID'

@admin.register(ThoughtLog)
class ThoughtLogAdmin(BaseModelAdmin):
    list_display = ['thought_id_short', 'decision_outcome', 'confidence_percent', 'overall_score', 'trade_link', 'model_version', 'created_at']
    list_filter = ['decision_outcome', 'model_version', 'priority_level', 'created_at']
    search_fields = ['thought_id', 'primary_reasoning', 'context__token__symbol']
    readonly_fields = ['thought_id', 'created_at', 'updated_at']
    ordering = ['-created_at']
    
    def thought_id_short(self, obj):
        return str(obj.thought_id)[:8] + '...'
    thought_id_short.short_description = 'Thought ID'
    
    def trade_link(self, obj):
        if obj.trade:
            return format_html('<a href="/admin/trading/trade/{}/change/">View Trade</a>', obj.trade.pk)
        return '-'
    trade_link.short_description = 'Trade'

@admin.register(DecisionMetrics)
class DecisionMetricsAdmin(BaseModelAdmin):
    list_display = ['metrics_id_short', 'thought_log', 'overall_quality_score', 'pnl_24hr_usd', 'decision_latency_ms', 'created_at']
    list_filter = ['overall_quality_score', 'created_at']
    search_fields = ['metrics_id', 'thought_log__thought_id']
    readonly_fields = ['metrics_id', 'created_at', 'updated_at']
    ordering = ['-created_at']
    
    def metrics_id_short(self, obj):
        return str(obj.metrics_id)[:8] + '...'
    metrics_id_short.short_description = 'Metrics ID'

@admin.register(LearningSession)
class LearningSessionAdmin(BaseModelAdmin):
    list_display = ['session_id_short', 'name', 'session_type', 'status', 'total_decisions', 'success_rate_display', 'total_pnl_usd', 'started_at']
    list_filter = ['session_type', 'status', 'started_at']
    search_fields = ['session_id', 'name']
    readonly_fields = ['session_id', 'started_at', 'ended_at']
    ordering = ['-started_at']










    
    
        
    
@admin.register(ModelPerformance)
class ModelPerformanceAdmin(BaseModelAdmin):
    list_display = ['performance_id_short', 'model_version', 'time_window', 'period_start', 'win_rate_percent', 'total_pnl_usd', 'sharpe_ratio']
    list_filter = ['model_version', 'time_window', 'period_start']
    search_fields = ['performance_id', 'model_version']
    readonly_fields = ['performance_id', 'created_at']
    ordering = ['-period_start']
    
    def performance_id_short(self, obj):
        return str(obj.performance_id)[:8] + '...'
    performance_id_short.short_description = 'Performance ID'

@admin.register(FeatureImportance)
class FeatureImportanceAdmin(BaseModelAdmin):
    list_display = ['importance_id_short', 'feature_name', 'feature_category', 'importance_score', 'usage_count', 'predictive_power', 'created_at']
    list_filter = ['feature_category', 'model_version', 'trend_direction', 'created_at']
    search_fields = ['importance_id', 'feature_name']
    readonly_fields = ['importance_id', 'created_at']
    ordering = ['-importance_score']
    
    def importance_id_short(self, obj):
        return str(obj.importance_id)[:8] + '...'
    importance_id_short.short_description = 'Importance ID'


# These are the missing methods that need to be added to the admin files

# 1. For analytics/admin.py - Add these methods to LearningSessionAdmin:

def session_id_short(self, obj):
    return str(obj.session_id)[:8] + '...'
session_id_short.short_description = 'Session ID'

def success_rate_display(self, obj):
    if obj.total_decisions > 0:
        rate = (obj.successful_decisions / obj.total_decisions) * 100
        color = 'green' if rate >= 70 else 'orange' if rate >= 50 else 'red'
        return format_html('<span style="color: {};">{:.1f}%</span>', color, rate)
    return '-'
success_rate_display.short_description = 'Success Rate'

# 2. For dashboard/admin.py - Add these methods to TradingSessionAdmin:

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

# 3. For trading/admin.py - Add this method to TokenAdmin:

def address_short(self, obj):
    return f"{obj.address[:10]}...{obj.address[-8:]}"
address_short.short_description = 'Address'

# 4. For wallet/admin.py - Add this method to WalletAdmin:

def address_short(self, obj):
    return f"{obj.address[:10]}...{obj.address[-8:]}"
address_short.short_description = 'Address'