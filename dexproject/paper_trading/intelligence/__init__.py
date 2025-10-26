"""
Intelligence Module for Paper Trading Bot

This module provides the intelligence system for making trading decisions
based on configurable intelligence levels (1-10).

Main Components:
- IntelSliderEngine: Main orchestrator for intelligence system
- CompositeMarketAnalyzer: Comprehensive market analysis with real blockchain data
- DecisionMaker: Trading decision logic
- MLFeatureCollector: ML training data collection (Level 10)
- IntelLevelConfig: Configuration for each intelligence level
- PriceHistory: Historical price tracking

File: dexproject/paper_trading/intelligence/__init__.py
"""

from paper_trading.intelligence.base import (
    IntelligenceEngine,
    IntelligenceLevel,
    MarketContext,
    TradingDecision
)

from paper_trading.intelligence.intel_config import (
    IntelLevelConfig,
    INTEL_CONFIGS
)

from paper_trading.intelligence.price_history import PriceHistory

from paper_trading.intelligence.decision_maker import DecisionMaker

from paper_trading.intelligence.ml_features import MLFeatureCollector

from paper_trading.intelligence.intel_slider import IntelSliderEngine

__all__ = [
    # Base classes
    'IntelligenceEngine',
    'IntelligenceLevel',
    'MarketContext',
    'TradingDecision',
    
    # Configuration
    'IntelLevelConfig',
    'INTEL_CONFIGS',
    
    # Data classes
    'PriceHistory',
    
    # Component classes
    'DecisionMaker',
    'MLFeatureCollector',
    
    # Main engine
    'IntelSliderEngine',
]