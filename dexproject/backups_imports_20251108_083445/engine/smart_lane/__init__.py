"""
Smart Lane Intelligence Module for DEX Trading Bot

This module provides comprehensive analysis capabilities for strategic trading
positions, including risk assessment, technical analysis, and AI-powered
decision making with full transparency through thought logs.

Path: engine/smart_lane/__init__.py
"""

import logging
from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass

# Configure module-level logging
logger = logging.getLogger(__name__)


class AnalysisDepth(Enum):
    """Analysis depth levels for Smart Lane processing."""
    BASIC = "BASIC"              # 2-3 core checks (~1s)
    COMPREHENSIVE = "COMPREHENSIVE"  # All 8 categories (~3-5s)
    DEEP_DIVE = "DEEP_DIVE"      # Extended analysis (~8-12s)


class RiskCategory(Enum):
    """Risk analysis categories for comprehensive assessment."""
    HONEYPOT_DETECTION = "HONEYPOT_DETECTION"
    LIQUIDITY_ANALYSIS = "LIQUIDITY_ANALYSIS"
    SOCIAL_SENTIMENT = "SOCIAL_SENTIMENT"
    TECHNICAL_ANALYSIS = "TECHNICAL_ANALYSIS"
    TOKEN_TAX_ANALYSIS = "TOKEN_TAX_ANALYSIS"
    CONTRACT_SECURITY = "CONTRACT_SECURITY"
    HOLDER_DISTRIBUTION = "HOLDER_DISTRIBUTION"
    MARKET_STRUCTURE = "MARKET_STRUCTURE"


class DecisionConfidence(Enum):
    """Confidence levels for Smart Lane decisions."""
    LOW = "LOW"          # <40% confidence
    MEDIUM = "MEDIUM"    # 40-70% confidence
    HIGH = "HIGH"        # 70-90% confidence
    VERY_HIGH = "VERY_HIGH"  # >90% confidence


class SmartLaneAction(Enum):
    """Possible actions from Smart Lane analysis."""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    AVOID = "AVOID"
    PARTIAL_BUY = "PARTIAL_BUY"
    PARTIAL_SELL = "PARTIAL_SELL"
    WAIT_FOR_BETTER_ENTRY = "WAIT_FOR_BETTER_ENTRY"
    SCALE_IN = "SCALE_IN"
    SCALE_OUT = "SCALE_OUT"


@dataclass
class SmartLaneConfig:
    """Configuration for Smart Lane analysis pipeline."""
    # Analysis settings
    analysis_depth: AnalysisDepth = AnalysisDepth.COMPREHENSIVE
    enabled_categories: List[RiskCategory] = None
    max_analysis_time_seconds: float = 5.0
    
    # AI Thought Log settings
    thought_log_enabled: bool = True
    thought_log_detail_level: str = "FULL"  # BASIC, DETAILED, FULL
    include_reasoning_steps: bool = True
    include_confidence_scores: bool = True
    
    # Risk thresholds
    max_acceptable_risk_score: float = 0.7  # 0-1 scale
    min_confidence_threshold: float = 0.5   # 0-1 scale
    
    # Position sizing
    enable_dynamic_sizing: bool = True
    max_position_size_percent: float = 10.0  # % of portfolio
    risk_per_trade_percent: float = 2.0      # % of portfolio at risk
    
    # Technical analysis
    technical_timeframes: List[str] = None   # ["5m", "15m", "1h", "4h"]
    
    def __post_init__(self):
        """Initialize default values after creation."""
        if self.enabled_categories is None:
            self.enabled_categories = list(RiskCategory)
        
        if self.technical_timeframes is None:
            self.technical_timeframes = ["5m", "30m", "4h"]


@dataclass
class RiskScore:
    """Individual risk category score with details."""
    category: RiskCategory
    score: float  # 0-1 scale, 1 = maximum risk
    confidence: float  # 0-1 scale, 1 = maximum confidence
    details: Dict[str, Any]  # Category-specific details
    analysis_time_ms: float
    warnings: List[str]
    
    # Additional context
    data_quality: str = "GOOD"  # POOR, FAIR, GOOD, EXCELLENT
    last_updated: Optional[str] = None


@dataclass
class TechnicalSignal:
    """Technical analysis signal from multi-timeframe analysis."""
    timeframe: str  # "5m", "30m", "4h", etc.
    signal: str     # "BUY", "SELL", "NEUTRAL"
    strength: float # 0-1 scale
    indicators: Dict[str, float]  # RSI, MACD, etc.
    price_targets: Dict[str, float]  # support, resistance levels
    confidence: float


@dataclass
class SmartLaneAnalysis:
    """Complete Smart Lane analysis result."""
    # Identification
    token_address: str
    chain_id: int
    analysis_id: str
    timestamp: str
    
    # Risk Assessment
    risk_scores: Dict[RiskCategory, RiskScore]
    overall_risk_score: float  # Weighted average
    overall_confidence: float
    
    # Technical Analysis
    technical_signals: List[TechnicalSignal]
    technical_summary: Dict[str, Any]
    
    # Strategic Recommendation
    recommended_action: SmartLaneAction
    position_size_percent: float
    confidence_level: DecisionConfidence
    
    # Exit Strategy
    stop_loss_percent: Optional[float]
    take_profit_targets: List[float]
    max_hold_time_hours: Optional[int]
    
    # Performance Metrics
    total_analysis_time_ms: float
    cache_hit_ratio: float
    data_freshness_score: float  # 0-1 scale
    
    # Warnings and Alerts
    critical_warnings: List[str]
    informational_notes: List[str]


# Version information
__version__ = "1.0.0"
__author__ = "DEX Trading Bot - Smart Lane Team"

# Module-level constants
DEFAULT_CONFIG = SmartLaneConfig()
SUPPORTED_CHAINS = [1, 56, 137, 42161, 10, 8453]  # ETH, BSC, MATIC, ARB, OP, BASE
MAX_CONCURRENT_ANALYSES = 10

# Export key classes and functions
__all__ = [
    'AnalysisDepth',
    'RiskCategory', 
    'DecisionConfidence',
    'SmartLaneAction',
    'SmartLaneConfig',
    'RiskScore',
    'TechnicalSignal',
    'SmartLaneAnalysis',
    'DEFAULT_CONFIG',
    'SUPPORTED_CHAINS',
    'MAX_CONCURRENT_ANALYSES'
]

logger.info(f"Smart Lane module initialized - version {__version__}")