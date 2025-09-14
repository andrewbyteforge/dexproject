"""
Smart Lane Analyzers Package

Modular risk analysis components for comprehensive token evaluation.
Each analyzer focuses on a specific risk category and provides
standardized risk scores with detailed analysis data.

Path: engine/smart_lane/analyzers/__init__.py
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime, timezone

from .. import RiskScore, RiskCategory

logger = logging.getLogger(__name__)


class BaseAnalyzer(ABC):
    """
    Base class for all Smart Lane risk analyzers.
    
    Provides common functionality and interface standardization
    for all risk assessment components.
    """
    
    def __init__(self, chain_id: int, config: Optional[Dict[str, Any]] = None):
        """
        Initialize base analyzer.
        
        Args:
            chain_id: Blockchain chain identifier
            config: Analyzer-specific configuration
        """
        self.chain_id = chain_id
        self.config = config or {}
        self.analysis_count = 0
        self.performance_stats = {
            'total_analyses': 0,
            'successful_analyses': 0,
            'failed_analyses': 0,
            'average_analysis_time_ms': 0.0,
            'cache_hits': 0,
            'cache_misses': 0
        }
        
        # Analyzer metadata
        self.analyzer_name = self.__class__.__name__
        self.version = "1.0.0"
        self.supported_chains = [1, 56, 137, 42161, 10, 8453]  # ETH, BSC, MATIC, ARB, OP, BASE
        
        logger.debug(f"{self.analyzer_name} initialized for chain {chain_id}")
    
    @abstractmethod
    async def analyze(
        self,
        token_address: str,
        context: Dict[str, Any]
    ) -> RiskScore:
        """
        Perform risk analysis for the specified token.
        
        Args:
            token_address: Token contract address to analyze
            context: Additional context data for analysis
            
        Returns:
            RiskScore with analysis results
        """
        pass
    
    @abstractmethod
    def get_category(self) -> RiskCategory:
        """Get the risk category this analyzer handles."""
        pass
    
    def is_chain_supported(self, chain_id: int) -> bool:
        """Check if analyzer supports the specified chain."""
        return chain_id in self.supported_chains
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get analyzer performance metrics."""
        success_rate = 0.0
        if self.performance_stats['total_analyses'] > 0:
            success_rate = (
                self.performance_stats['successful_analyses'] / 
                self.performance_stats['total_analyses']
            ) * 100
        
        cache_hit_rate = 0.0
        total_cache_requests = self.performance_stats['cache_hits'] + self.performance_stats['cache_misses']
        if total_cache_requests > 0:
            cache_hit_rate = (self.performance_stats['cache_hits'] / total_cache_requests) * 100
        
        return {
            'analyzer_name': self.analyzer_name,
            'version': self.version,
            'total_analyses': self.performance_stats['total_analyses'],
            'success_rate_percent': success_rate,
            'average_analysis_time_ms': self.performance_stats['average_analysis_time_ms'],
            'cache_hit_rate_percent': cache_hit_rate,
            'supported_chains': self.supported_chains,
            'chain_id': self.chain_id
        }
    
    def _update_performance_stats(self, analysis_time_ms: float, success: bool) -> None:
        """Update performance tracking statistics."""
        self.performance_stats['total_analyses'] += 1
        
        if success:
            self.performance_stats['successful_analyses'] += 1
        else:
            self.performance_stats['failed_analyses'] += 1
        
        # Update rolling average analysis time
        total = self.performance_stats['total_analyses']
        current_avg = self.performance_stats['average_analysis_time_ms']
        
        new_avg = ((current_avg * (total - 1)) + analysis_time_ms) / total
        self.performance_stats['average_analysis_time_ms'] = new_avg
    
    def _create_risk_score(
        self,
        score: float,
        confidence: float,
        details: Dict[str, Any],
        warnings: List[str] = None,
        analysis_time_ms: float = 0.0,
        data_quality: str = "GOOD"
    ) -> RiskScore:
        """
        Create standardized RiskScore object.
        
        Args:
            score: Risk score (0-1, where 1 is maximum risk)
            confidence: Confidence in the analysis (0-1)
            details: Category-specific analysis details
            warnings: List of warnings or concerns
            analysis_time_ms: Time taken for analysis
            data_quality: Quality of source data
            
        Returns:
            Standardized RiskScore object
        """
        return RiskScore(
            category=self.get_category(),
            score=max(0.0, min(1.0, score)),  # Clamp to 0-1 range
            confidence=max(0.0, min(1.0, confidence)),  # Clamp to 0-1 range
            details=details,
            analysis_time_ms=analysis_time_ms,
            warnings=warnings or [],
            data_quality=data_quality,
            last_updated=datetime.now(timezone.utc).isoformat()
        )
    
    def _validate_token_address(self, token_address: str) -> bool:
        """Validate token address format."""
        if not token_address:
            return False
        
        # Check if it's a valid Ethereum address format
        if not token_address.startswith('0x'):
            return False
        
        if len(token_address) != 42:
            return False
        
        # Check if it contains only hex characters
        try:
            int(token_address, 16)
            return True
        except ValueError:
            return False
    
    def _get_chain_name(self, chain_id: int) -> str:
        """Get human-readable chain name."""
        chain_names = {
            1: "Ethereum",
            56: "BSC",
            137: "Polygon",
            42161: "Arbitrum",
            10: "Optimism",
            8453: "Base"
        }
        return chain_names.get(chain_id, f"Chain {chain_id}")


# Analyzer factory function
def create_analyzer(category: RiskCategory, chain_id: int, config: Optional[Dict[str, Any]] = None) -> BaseAnalyzer:
    """
    Factory function to create appropriate analyzer for risk category.
    
    Args:
        category: Risk category to analyze
        chain_id: Blockchain chain identifier
        config: Analyzer-specific configuration
        
    Returns:
        Appropriate analyzer instance
        
    Raises:
        ValueError: If category is not supported
    """
    try:
        if category == RiskCategory.HONEYPOT_DETECTION:
            from .honeypot_analyzer import HoneypotAnalyzer
            return HoneypotAnalyzer(chain_id, config)
            
        elif category == RiskCategory.LIQUIDITY_ANALYSIS:
            from .liquidity_analyzer import LiquidityAnalyzer
            return LiquidityAnalyzer(chain_id, config)
            
        elif category == RiskCategory.SOCIAL_SENTIMENT:
            from .social_analyzer import SocialAnalyzer
            return SocialAnalyzer(chain_id, config)
            
        elif category == RiskCategory.TECHNICAL_ANALYSIS:
            from .technical_analyzer import TechnicalAnalyzer
            return TechnicalAnalyzer(chain_id, config)
            
        elif category == RiskCategory.TOKEN_TAX_ANALYSIS:
            from .tax_analyzer import TaxAnalyzer
            return TaxAnalyzer(chain_id, config)
            
        elif category == RiskCategory.CONTRACT_SECURITY:
            from .contract_analyzer import ContractAnalyzer
            return ContractAnalyzer(chain_id, config)
            
        elif category == RiskCategory.HOLDER_DISTRIBUTION:
            from .holder_analyzer import HolderAnalyzer
            return HolderAnalyzer(chain_id, config)
            
        elif category == RiskCategory.MARKET_STRUCTURE:
            from .market_analyzer import MarketAnalyzer
            return MarketAnalyzer(chain_id, config)
            
        else:
            raise ValueError(f"Unsupported risk category: {category}")
            
    except ImportError as e:
        logger.error(f"Failed to import analyzer for {category.value}: {e}")
        raise ValueError(f"Analyzer not available for {category.value}")


# Analyzer registry for dynamic loading
ANALYZER_REGISTRY = {
    RiskCategory.HONEYPOT_DETECTION: "honeypot_analyzer.HoneypotAnalyzer",
    RiskCategory.LIQUIDITY_ANALYSIS: "liquidity_analyzer.LiquidityAnalyzer", 
    RiskCategory.SOCIAL_SENTIMENT: "social_analyzer.SocialAnalyzer",
    RiskCategory.TECHNICAL_ANALYSIS: "technical_analyzer.TechnicalAnalyzer",
    RiskCategory.TOKEN_TAX_ANALYSIS: "tax_analyzer.TaxAnalyzer",
    RiskCategory.CONTRACT_SECURITY: "contract_analyzer.ContractAnalyzer",
    RiskCategory.HOLDER_DISTRIBUTION: "holder_analyzer.HolderAnalyzer",
    RiskCategory.MARKET_STRUCTURE: "market_analyzer.MarketAnalyzer"
}


# Utility functions
def get_available_analyzers() -> List[RiskCategory]:
    """Get list of available analyzer categories."""
    return list(ANALYZER_REGISTRY.keys())


def get_analyzer_info(category: RiskCategory) -> Dict[str, str]:
    """Get information about a specific analyzer."""
    info = {
        RiskCategory.HONEYPOT_DETECTION: {
            'name': 'Honeypot Detection',
            'description': 'Detects potential honeypot scams and exit scams',
            'priority': 'CRITICAL'
        },
        RiskCategory.LIQUIDITY_ANALYSIS: {
            'name': 'Liquidity Analysis', 
            'description': 'Analyzes token liquidity depth and stability',
            'priority': 'HIGH'
        },
        RiskCategory.SOCIAL_SENTIMENT: {
            'name': 'Social Sentiment',
            'description': 'Evaluates community sentiment and social signals',
            'priority': 'MEDIUM'
        },
        RiskCategory.TECHNICAL_ANALYSIS: {
            'name': 'Technical Analysis',
            'description': 'Multi-timeframe technical chart analysis',
            'priority': 'MEDIUM'
        },
        RiskCategory.TOKEN_TAX_ANALYSIS: {
            'name': 'Token Tax Analysis',
            'description': 'Analyzes transaction taxes and fees',
            'priority': 'HIGH'
        },
        RiskCategory.CONTRACT_SECURITY: {
            'name': 'Contract Security',
            'description': 'Smart contract security and vulnerability assessment',
            'priority': 'CRITICAL'
        },
        RiskCategory.HOLDER_DISTRIBUTION: {
            'name': 'Holder Distribution',
            'description': 'Token holder concentration and distribution analysis',
            'priority': 'HIGH'
        },
        RiskCategory.MARKET_STRUCTURE: {
            'name': 'Market Structure',
            'description': 'Market manipulation and structure analysis',
            'priority': 'MEDIUM'
        }
    }
    
    return info.get(category, {
        'name': category.value,
        'description': 'Risk analysis component',
        'priority': 'UNKNOWN'
    })


# Export key classes and functions
__all__ = [
    'BaseAnalyzer',
    'create_analyzer',
    'get_available_analyzers',
    'get_analyzer_info',
    'ANALYZER_REGISTRY'
]

logger.info(f"Smart Lane analyzers package initialized with {len(ANALYZER_REGISTRY)} available analyzers")