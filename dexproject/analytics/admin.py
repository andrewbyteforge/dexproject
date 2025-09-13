"""
Django admin configuration for the analytics app.

This module configures Django admin interfaces for analytics models including
decision contexts, features, thought logs, metrics, learning sessions,
model performance tracking, and feature importance analysis.
"""
from django.contrib import admin
import logging
from typing import Optional
from django.contrib import admin
from django.utils.html import format_html
from shared.admin.base import BaseModelAdmin
from .models import (
    DecisionContext, DecisionFeature, ThoughtLog, DecisionMetrics,
    LearningSession, ModelPerformance, FeatureImportance
)

# Configure logging for this module
logger = logging.getLogger(__name__)


@admin.register(DecisionContext)
class DecisionContextAdmin(BaseModelAdmin):
    """
    Admin interface for DecisionContext model.
    
    Provides administrative access to decision context data including
    filtering by decision type, pair DEX, strategy, and creation date.
    """
    
    list_display = [
        'context_id_short', 'decision_type', 'pair', 'token', 'strategy', 
        'discovery_latency_ms', 'created_at'
    ]
    list_filter = ['decision_type', 'pair__dex', 'strategy', 'created_at']
    search_fields = ['context_id', 'token__symbol', 'pair__token0__symbol']
    readonly_fields = ['context_id', 'created_at']
    ordering = ['-created_at']
    
    def context_id_short(self, obj: DecisionContext) -> str:
        """Display shortened context ID for better readability."""
        try:
            return str(obj.context_id)[:8] + '...'
        except Exception as e:
            logger.error(f"Error formatting context_id for {obj}: {e}")
            return 'Error'
    
    context_id_short.short_description = 'Context ID'

@admin.display(description='Session ID')
@admin.register(DecisionFeature)
class DecisionFeatureAdmin(BaseModelAdmin):
    """
    Admin interface for DecisionFeature model.
    
    Manages decision features with filtering by category, data type,
    and creation date.
    """
    
    list_display = [
        'feature_id_short', 'context', 'name', 'category', 
        'data_type', 'weight', 'confidence'
    ]
    list_filter = ['category', 'data_type', 'created_at']
    search_fields = ['feature_id', 'name', 'context__context_id']
    readonly_fields = ['feature_id', 'created_at']
    ordering = ['-created_at']
    
    def feature_id_short(self, obj: DecisionFeature) -> str:
        """Display shortened feature ID for better readability."""
        try:
            return str(obj.feature_id)[:8] + '...'
        except Exception as e:
            logger.error(f"Error formatting feature_id for {obj}: {e}")
            return 'Error'
    
    feature_id_short.short_description = 'Feature ID'


@admin.register(ThoughtLog)
class ThoughtLogAdmin(BaseModelAdmin):
    """
    Admin interface for ThoughtLog model.
    
    Provides comprehensive view of AI decision-making process with
    filtering and searching capabilities.
    """
    
    list_display = [
        'thought_id_short', 'decision_outcome', 'confidence_percent', 
        'overall_score', 'trade_link', 'model_version', 'created_at'
    ]
    list_filter = ['decision_outcome', 'model_version', 'priority_level', 'created_at']
    search_fields = ['thought_id', 'primary_reasoning', 'context__token__symbol']
    readonly_fields = ['thought_id', 'created_at', 'updated_at']
    ordering = ['-created_at']
    
    def thought_id_short(self, obj: ThoughtLog) -> str:
        """Display shortened thought ID for better readability."""
        try:
            return str(obj.thought_id)[:8] + '...'
        except Exception as e:
            logger.error(f"Error formatting thought_id for {obj}: {e}")
            return 'Error'
    
    thought_id_short.short_description = 'Thought ID'
    
    def trade_link(self, obj: ThoughtLog) -> str:
        """Display link to related trade if exists."""
        try:
            if obj.trade:
                return format_html(
                    '<a href="/admin/trading/trade/{}/change/">View Trade</a>', 
                    obj.trade.pk
                )
            return '-'
        except Exception as e:
            logger.error(f"Error generating trade link for {obj}: {e}")
            return 'Error'
    
    trade_link.short_description = 'Trade'


@admin.register(DecisionMetrics)
class DecisionMetricsAdmin(BaseModelAdmin):
    """
    Admin interface for DecisionMetrics model.
    
    Tracks quantitative metrics and performance data for decision analysis.
    """
    
    list_display = [
        'metrics_id_short', 'thought_log', 'overall_quality_score', 
        'pnl_24hr_usd', 'decision_latency_ms', 'created_at'
    ]
    list_filter = ['overall_quality_score', 'created_at']
    search_fields = ['metrics_id', 'thought_log__thought_id']
    readonly_fields = ['metrics_id', 'created_at', 'updated_at']
    ordering = ['-created_at']
    
    def metrics_id_short(self, obj: DecisionMetrics) -> str:
        """Display shortened metrics ID for better readability."""
        try:
            return str(obj.metrics_id)[:8] + '...'
        except Exception as e:
            logger.error(f"Error formatting metrics_id for {obj}: {e}")
            return 'Error'
    
    metrics_id_short.short_description = 'Metrics ID'


@admin.register(LearningSession)
class LearningSessionAdmin(BaseModelAdmin):
    """
    Admin interface for LearningSession model.
    
    Manages AI learning sessions with comprehensive tracking of decisions,
    success rates, and performance metrics.
    """
    
    list_display = [
        'session_id_short', 'name', 'session_type', 'status', 
        'total_decisions', 'success_rate_display', 'total_pnl_usd', 'started_at'
    ]
    list_filter = ['session_type', 'status', 'started_at']
    search_fields = ['session_id', 'name']
    readonly_fields = ['session_id', 'started_at', 'ended_at']
    ordering = ['-started_at']
    
    def session_id_short(self, obj: LearningSession) -> str:
        """Display shortened session ID for better readability."""
        try:
            return str(obj.session_id)[:8] + '...'
        except Exception as e:
            logger.error(f"Error formatting session_id for {obj}: {e}")
            return 'Error'
    
    session_id_short.short_description = 'Session ID'
    
    def success_rate_display(self, obj: LearningSession) -> str:
        """Display formatted success rate with color coding."""
        try:
            success_rate = obj.success_rate
            if success_rate is not None:
                # Color code based on success rate
                if success_rate >= 70:
                    color = 'green'
                elif success_rate >= 50:
                    color = 'orange'
                else:
                    color = 'red'
                
                return format_html(
                    '<span style="color: {}; font-weight: bold;">{:.1f}%</span>',
                    color, success_rate
                )
            return '-'
        except Exception as e:
            logger.error(f"Error calculating success_rate_display for {obj}: {e}")
            return 'Error'
    
    success_rate_display.short_description = 'Success Rate'


@admin.register(ModelPerformance)
class ModelPerformanceAdmin(BaseModelAdmin):
    """
    Admin interface for ModelPerformance model.
    
    Tracks model performance metrics over time for different versions
    and time windows.
    """
    
    list_display = [
        'performance_id_short', 'model_version', 'time_window', 
        'period_start', 'win_rate_percent', 'total_pnl_usd', 'sharpe_ratio'
    ]
    list_filter = ['model_version', 'time_window', 'period_start']
    search_fields = ['performance_id', 'model_version']
    readonly_fields = ['performance_id', 'created_at']
    ordering = ['-period_start']
    
    def performance_id_short(self, obj: ModelPerformance) -> str:
        """Display shortened performance ID for better readability."""
        try:
            return str(obj.performance_id)[:8] + '...'
        except Exception as e:
            logger.error(f"Error formatting performance_id for {obj}: {e}")
            return 'Error'
    
    performance_id_short.short_description = 'Performance ID'


@admin.register(FeatureImportance)
class FeatureImportanceAdmin(BaseModelAdmin):
    """
    Admin interface for FeatureImportance model.
    
    Manages feature importance tracking for model optimization
    and performance analysis.
    """
    
    list_display = [
        'importance_id_short', 'feature_name', 'feature_category', 
        'importance_score', 'usage_count', 'predictive_power', 'created_at'
    ]
    list_filter = ['feature_category', 'model_version', 'trend_direction', 'created_at']
    search_fields = ['importance_id', 'feature_name']
    readonly_fields = ['importance_id', 'created_at']
    ordering = ['-importance_score']
    
    def importance_id_short(self, obj: FeatureImportance) -> str:
        """Display shortened importance ID for better readability."""
        try:
            return str(obj.importance_id)[:8] + '...'
        except Exception as e:
            logger.error(f"Error formatting importance_id for {obj}: {e}")
            return 'Error'
    
    importance_id_short.short_description = 'Importance ID'