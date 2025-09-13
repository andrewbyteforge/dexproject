import uuid
from django.db import models
from django.utils import timezone


class TimestampMixin(models.Model):
    """
    Abstract model mixin that provides timestamp fields.
    """
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
ECHO is off.
    class Meta:
        abstract = True


class UUIDMixin(models.Model):
    """
    Abstract model mixin that provides UUID primary key.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
ECHO is off.
    class Meta:
        abstract = True


class SoftDeleteMixin(models.Model):
    """
    Abstract model mixin that provides soft delete functionality.
    """
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
ECHO is off.
    def soft_delete(self):
        """Mark the object as deleted."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save()
ECHO is off.
    def restore(self):
        """Restore a soft-deleted object."""
        self.is_deleted = False
        self.deleted_at = None
        self.save()
ECHO is off.
    class Meta:
        abstract = True
