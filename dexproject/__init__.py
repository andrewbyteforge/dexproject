"""
Django project initialization for DEX auto-trading bot.

This module ensures that the Celery app is always imported when Django starts
so that shared_task will use this app.
"""

# Import the Celery app to ensure it's loaded when Django starts
from .celery import app as celery_app

__all__ = ('celery_app',)