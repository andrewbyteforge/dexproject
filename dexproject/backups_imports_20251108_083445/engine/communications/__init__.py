"""
Engine communications module for Redis pub/sub integration with Django.

This module provides the communication layer between the async engine
and the Django backend, handling message routing and event coordination.
"""

from .django_bridge import DjangoBridge

__all__ = [
    'DjangoBridge',
]