"""
Django admin configuration for the analytics app.

This module configures Django admin interfaces for analytics models including
decision contexts, features, thought logs, metrics, learning sessions,
and model performance tracking.
"""
from django.contrib import admin
import logging
from typing import Optional
from django.contrib import admin
from django.utils.html import format_html
from shared.admin.base import BaseModelAdmin

# Only import models that actually exist in models.py
from .models import (
    DecisionContext, DecisionFeature, ThoughtLog, DecisionMetrics,
    LearningSession, ModelPerformance
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


@admin.register(DecisionFeature)
class DecisionFeatureAdmin(BaseModelAdmin):
    """
    Admin interface for DecisionFeature model.
    
    Manages decision features with filtering by category, importance,
    and creation date.
    """
    
    list_display = [
        'feature_id_short', 'context', 'name', 'category', 
        'importance_score', 'confidence_level', 'created_at'
    ]
    list_filter = ['category', 'created_at']
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
        'context', 'trade', 'model_version', 'created_at'
    ]
    list_filter = [
        'decision_outcome', 'priority', 'model_version', 
        'context__decision_type', 'created_at'
    ]
    search_fields = [
        'thought_id', 'context__context_id', 'context__token__symbol'
    ]
    readonly_fields = ['thought_id', 'created_at', 'updated_at']
    ordering = ['-created_at']
    
    fieldsets = (
        ('Identification', {
            'fields': ('thought_id', 'context', 'decision_outcome', 'confidence_percent')
        }),
        ('Reasoning', {
            'fields': ('reasoning_steps', 'key_factors', 'risk_concerns', 'alternative_scenarios'),
            'classes': ('collapse',)
        }),
        ('Recommendations', {
            'fields': (
                'recommended_position_size_usd', 'recommended_stop_loss_percent',
                'recommended_take_profit_percent', 'priority'
            )
        }),
        ('Execution', {
            'fields': ('trade',)
        }),
        ('Evaluation', {
            'fields': ('feedback_score', 'outcome_evaluation'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('model_version', 'feature_version', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def thought_id_short(self, obj: ThoughtLog) -> str:
        """Display shortened thought ID for better readability."""
        try:
            return str(obj.thought_id)[:8] + '...'
        except Exception as e:
            logger.error(f"Error formatting thought_id for {obj}: {e}")
            return 'Error'
    
    thought_id_short.short_description = 'Thought ID'
    
    def confidence_display(self, obj: ThoughtLog) -> str:
        """Display confidence with color coding."""
        try:
            confidence = obj.confidence_percent
            if confidence >= 80:
                color = 'green'
            elif confidence >= 60:
                color = 'orange'
            else:
                color = 'red'
            
            return format_html(
                '<span style="color: {}; font-weight: bold;">{:.1f}%</span>',
                color, confidence
            )
        except Exception as e:
            logger.error(f"Error formatting confidence for {obj}: {e}")
            return 'Error'
    
    confidence_display.short_description = 'Confidence'


@admin.register(DecisionMetrics)
class DecisionMetricsAdmin(BaseModelAdmin):
    """
    Admin interface for DecisionMetrics model.
    
    Tracks quantitative performance metrics for trading decisions.
    """
    
    list_display = [
        'metrics_id_short', 'thought_log', 'overall_quality_score',
        'pnl_24hr_usd', 'decision_latency_ms', 'created_at'
    ]
    list_filter = ['overall_quality_score', 'created_at']
    search_fields = ['metrics_id', 'thought_log__thought_id']
    readonly_fields = ['metrics_id', 'created_at', 'updated_at']
    ordering = ['-created_at']
    
    fieldsets = (
        ('Identification', {
            'fields': ('metrics_id', 'thought_log')
        }),
        ('Timing Metrics', {
            'fields': (
                'decision_latency_ms', 'execution_latency_ms', 'total_latency_ms'
            )
        }),
        ('Trading Metrics', {
            'fields': (
                'slippage_actual_percent', 'slippage_vs_expected_percent',
                'gas_efficiency_score'
            )
        }),
        ('Performance', {
            'fields': (
                'pnl_1hr_usd', 'pnl_24hr_usd', 'pnl_7d_usd',
                'max_drawdown_percent', 'overall_quality_score'
            )
        }),
        ('Comparisons', {
            'fields': ('vs_random_performance', 'vs_market_performance'),
            'classes': ('collapse',)
        }),
        ('Additional Data', {
            'fields': ('custom_metrics', 'last_evaluated_at'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
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
    
    fieldsets = (
        ('Identification', {
            'fields': ('session_id', 'name', 'session_type', 'status')
        }),
        ('Configuration', {
            'fields': ('strategy', 'model_version', 'config'),
            'classes': ('collapse',)
        }),
        ('Metrics', {
            'fields': (
                'total_decisions', 'successful_decisions', 
                'average_quality_score', 'total_pnl_usd'
            )
        }),
        ('Learning Outcomes', {
            'fields': ('lessons_learned', 'model_updates'),
            'classes': ('collapse',)
        }),
        ('Timeline', {
            'fields': ('started_at', 'ended_at')
        }),
        ('Related Data', {
            'fields': ('thought_logs',),
            'classes': ('collapse',)
        }),
    )
    
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
    readonly_fields = ['performance_id', 'created_at', 'updated_at']
    ordering = ['-period_start']
    
    fieldsets = (
        ('Identification', {
            'fields': ('performance_id', 'model_version', 'time_window')
        }),
        ('Time Period', {
            'fields': ('period_start', 'period_end')
        }),
        ('Decision Metrics', {
            'fields': (
                'total_decisions', 'successful_decisions', 'win_rate_percent'
            )
        }),
        ('Financial Performance', {
            'fields': (
                'total_pnl_usd', 'average_pnl_per_decision_usd',
                'max_drawdown_percent', 'sharpe_ratio'
            )
        }),
        ('Quality Metrics', {
            'fields': ('average_quality_score', 'average_confidence')
        }),
        ('Timing Metrics', {
            'fields': (
                'average_decision_latency_ms', 'average_execution_latency_ms'
            )
        }),
        ('Additional Data', {
            'fields': ('custom_metrics',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def performance_id_short(self, obj: ModelPerformance) -> str:
        """Display shortened performance ID for better readability."""
        try:
            return str(obj.performance_id)[:8] + '...'
        except Exception as e:
            logger.error(f"Error formatting performance_id for {obj}: {e}")
            return 'Error'
    
    performance_id_short.short_description = 'Performance ID'


# Note: FeatureImportance model is not currently in models.py
# Uncomment this section when FeatureImportance is added to models.py

# @admin.register(FeatureImportance)
# class FeatureImportanceAdmin(BaseModelAdmin):
#     """
#     Admin interface for FeatureImportance model.
#     
#     Manages feature importance tracking for model optimization
#     and performance analysis.
#     """
#     
#     list_display = [
#         'importance_id_short', 'feature_name', 'feature_category', 
#         'importance_score', 'usage_count', 'predictive_power', 'created_at'
#     ]
#     list_filter = ['feature_category', 'model_version', 'trend_direction', 'created_at']
#     search_fields = ['importance_id', 'feature_name']
#     readonly_fields = ['importance_id', 'created_at']
#     ordering = ['-importance_score']
#     
#     def importance_id_short(self, obj) -> str:
#         """Display shortened importance ID for better readability."""
#         try:
#             return str(obj.importance_id)[:8] + '...'
#         except Exception as e:
#             logger.error(f"Error formatting importance_id for {obj}: {e}")
#             return 'Error'
#     
#     importance_id_short.short_description = 'Importance ID'