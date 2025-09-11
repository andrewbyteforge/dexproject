"""
Django admin configuration for the risk app.
"""

from django.contrib import admin
from .models import RiskCheckType, RiskAssessment, RiskCheckResult, RiskProfile, RiskProfileCheckConfig, RiskEvent

@admin.register(RiskCheckType)
class RiskCheckTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'severity', 'is_blocking', 'is_active', 'weight', 'timeout_seconds']
    list_filter = ['category', 'severity', 'is_blocking', 'is_active']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    actions = ['enable_checks', 'disable_checks']
    
    def enable_checks(self, request, queryset):
        queryset.update(is_active=True)
        self.message_user(request, f"Enabled {queryset.count()} risk checks.")
    enable_checks.short_description = "Enable selected checks"
    
    def disable_checks(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, f"Disabled {queryset.count()} risk checks.")
    disable_checks.short_description = "Disable selected checks"

@admin.register(RiskAssessment)
class RiskAssessmentAdmin(admin.ModelAdmin):
    list_display = ['assessment_id_short', 'pair', 'token', 'status', 'risk_level', 'recommendation', 'overall_score', 'has_blocking_issues', 'started_at']
    list_filter = ['status', 'risk_level', 'recommendation', 'has_blocking_issues', 'started_at']
    search_fields = ['assessment_id', 'token__symbol', 'pair__token0__symbol']
    readonly_fields = ['assessment_id', 'started_at', 'completed_at']
    ordering = ['-started_at']
    
    def assessment_id_short(self, obj):
        return str(obj.assessment_id)[:8] + '...'
    assessment_id_short.short_description = 'Assessment ID'

@admin.register(RiskCheckResult)
class RiskCheckResultAdmin(admin.ModelAdmin):
    list_display = ['result_id_short', 'assessment', 'check_type', 'status', 'score', 'is_blocking', 'execution_time_ms']
    list_filter = ['status', 'is_blocking', 'check_type__category']
    search_fields = ['result_id', 'check_type__name']
    readonly_fields = ['result_id', 'started_at', 'completed_at']
    ordering = ['-started_at']
    
    def result_id_short(self, obj):
        return str(obj.result_id)[:8] + '...'
    result_id_short.short_description = 'Result ID'

@admin.register(RiskProfile)
class RiskProfileAdmin(admin.ModelAdmin):
    list_display = ['name', 'max_risk_score', 'min_confidence_score', 'liquidity_threshold_usd', 'is_active']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(RiskProfileCheckConfig)
class RiskProfileCheckConfigAdmin(admin.ModelAdmin):
    list_display = ['risk_profile', 'check_type', 'is_enabled', 'weight', 'is_blocking']
    list_filter = ['risk_profile', 'check_type__category', 'is_enabled']
    search_fields = ['risk_profile__name', 'check_type__name']

@admin.register(RiskEvent)
class RiskEventAdmin(admin.ModelAdmin):
    list_display = ['event_id_short', 'event_type', 'severity', 'title', 'token', 'is_resolved', 'created_at']
    list_filter = ['event_type', 'severity', 'is_resolved', 'created_at']
    search_fields = ['event_id', 'title', 'description']
    readonly_fields = ['event_id', 'created_at']
    actions = ['mark_resolved']
    
    def event_id_short(self, obj):
        return str(obj.event_id)[:8] + '...'
    event_id_short.short_description = 'Event ID'
    
    def mark_resolved(self, request, queryset):
        from django.utils import timezone
        queryset.update(is_resolved=True, resolved_at=timezone.now())
        self.message_user(request, f"Marked {queryset.count()} events as resolved.")
    mark_resolved.short_description = "Mark as resolved"