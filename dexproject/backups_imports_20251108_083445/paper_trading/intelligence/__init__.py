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

from dexproject.paper_trading.intelligence.core.base import (
    IntelligenceEngine,
    IntelligenceLevel,
    MarketContext,
    TradingDecision
)

from dexproject.paper_trading.intelligence.config.intel_config import (
    IntelLevelConfig,
    INTEL_CONFIGS
)

from dexproject.paper_trading.intelligence.data.price_history import PriceHistory

from dexproject.paper_trading.intelligence.strategies.decision_maker import DecisionMaker

from dexproject.paper_trading.intelligence.data.ml_features import MLFeatureCollector

from dexproject.paper_trading.intelligence.core.intel_slider import IntelSliderEngine

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