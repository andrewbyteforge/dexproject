"""
Configuration module for paper trading system.

This module provides type configuration, validation rules, and type-safe
configuration wrappers for the trading system.

File: dexproject/paper_trading/config/__init__.py
"""

from .type_config import (
    TypeConfig,
    ValidationRules,
    TypeSafeConfig,
)

__all__ = [
    'TypeConfig',
    'ValidationRules',
    'TypeSafeConfig',
]