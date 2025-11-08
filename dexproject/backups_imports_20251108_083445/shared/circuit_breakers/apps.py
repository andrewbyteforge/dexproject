"""
Django app configuration for Circuit Breakers module.

File: shared/circuit_breakers/apps.py
"""

from django.apps import AppConfig


class CircuitBreakersConfig(AppConfig):
    """
    Django app configuration for the circuit breakers module.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'shared.circuit_breakers'
    verbose_name = 'Circuit Breakers'
    
    def ready(self):
        """
        Called when Django is ready and all apps are loaded.
        Import models and signals here to avoid AppRegistryNotReady errors.
        """
        # Import models after Django is ready
        from . import _import_persistence
        _import_persistence()
        
        # Log that the app is ready
        import logging
        logger = logging.getLogger(__name__)
        logger.info("Circuit Breakers app ready")