from django.contrib import admin
from django.utils.html import format_html


class BaseModelAdmin(admin.ModelAdmin):
    """
    Base admin class with common functionality.
    """
ECHO is off.
    def short_id(self, obj):
        """Display shortened ID for UUID fields."""
        if hasattr(obj, 'id') and obj.id:
            return str(obj.id)[:8] + '...'
        return '-'
    short_id.short_description = 'ID'
ECHO is off.
    def colored_status(self, obj, status_field='status'):
        """Display colored status field."""
        status = getattr(obj, status_field, None)
        if not status:
            return '-'
ECHO is off.
        colors = {
            'ACTIVE': 'green',
            'INACTIVE': 'red',
            'PENDING': 'orange',
            'SUCCESS': 'green',
            'FAILED': 'red',
            'ERROR': 'red',
            'WARNING': 'orange'
        }
ECHO is off.
        color = colors.get(status.upper(), 'black')
        return format_html(
            color,
            status
        )
ECHO is off.
    def get_readonly_fields(self, request, obj=None):
        """Make timestamp fields readonly."""
        readonly = list(super().get_readonly_fields(request, obj))
        timestamp_fields = ['created_at', 'updated_at', 'deleted_at']
        for field in timestamp_fields:
            if hasattr(self.model, field) and field not in readonly:
                readonly.append(field)
        return readonly
