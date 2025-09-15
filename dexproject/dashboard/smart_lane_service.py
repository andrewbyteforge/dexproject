"""
Smart Lane Engine Service Layer

Provides abstraction between dashboard UI and Smart Lane analysis pipeline.
Includes error handling, circuit breaker pattern, and fallback data.

Following the same pattern as dashboard/engine_service.py but for Smart Lane components.

File: dashboard/smart_lane_service.py
"""

import asyncio
import logging
import json
import random
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from decimal import Decimal
from django.core.cache import cache
from django.conf import settings

# Import Smart Lane components
try:
    from engine.smart_lane.pipeline import SmartLanePipeline, PipelineStatus
    from engine.smart_lane.cache import SmartLaneCache, CacheStrategy
    from engine.smart_lane import SmartLaneConfig, AnalysisDepth, SmartLaneAction
    from engine.smart_lane.thought_log import ThoughtLogGenerator
    from engine.smart_lane.strategy.position_sizing import PositionSizer
    from engine.smart_lane.strategy.exit_strategies import ExitStrategyManager
    SMART_LANE_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Smart Lane engine not available: {e}")
    SMART_LANE_AVAILABLE = False

logger = logging.getLogger(__name__)


class SmartLaneServiceError(Exception):
    """Base exception for Smart Lane service errors."""
    pass


class SmartLaneCircuitBreaker:
    """Circuit breaker pattern for Smart Lane analysis failures."""
    
    def __init__(self, failure_threshold: int = 3, recovery_time: int = 120):
        """
        Initialize circuit breaker with different thresholds for Smart Lane.
        
        Args:
            failure_threshold: Number of failures before opening circuit (lower for Smart Lane)
            recovery_time: Time in seconds before trying again (longer for Smart Lane)
        """
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN
    
    def call_allowed(self) -> bool:
        """Check if calls to Smart Lane pipeline are allowed."""
        if self.state == 'CLOSED':
            return True
        
        if self.state == 'OPEN':
            # Check if recovery time has passed
            if self.last_failure_time and (datetime.now() - self.last_failure_time).seconds >= self.recovery_time:
                self.state = 'HALF_OPEN'
                return True
            return False
        
        # HALF_OPEN state allows one test call
        return True
    
    def record_success(self):
        """Record successful Smart Lane analysis."""
        self.failure_count = 0
        self.state = 'CLOSED'
    
    def record_failure(self):
        """Record failed Smart Lane analysis."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            self.state = 'OPEN'
            logger.warning(f"Smart Lane circuit breaker OPEN after {self.failure_count} failures")


class DashboardSmartLaneService:
    """
    Service layer for dashboard to communicate with Smart Lane analysis pipeline.
    
    Provides:
    - Error handling and graceful degradation
    - Circuit breaker pattern for reliability  
    - Caching for performance and fallback data
    - Live Smart Lane pipeline integration
    - Mock data generation for development/fallback
    """
    
    def __init__(self):
        self.logger = logger
        self.circuit_breaker = SmartLaneCircuitBreaker()
        
        # Determine operating mode
        self.mock_mode = getattr(settings, 'ENGINE_MOCK_MODE', not SMART_LANE_AVAILABLE)
        self.smart_lane_enabled = getattr(settings, 'SMART_LANE_ENABLED', False)
        self.pipeline: Optional[SmartLanePipeline] = None
        self.pipeline_initialized = False
        
        # Cache keys
        self.ANALYSIS_CACHE_KEY = 'smart_lane:analysis_metrics'
        self.STATUS_CACHE_KEY = 'smart_lane:pipeline_status'  
        self.THOUGHT_LOG_CACHE_KEY = 'smart_lane:thought_log'
        self.CACHE_TIMEOUT = 60  # seconds (longer than Fast Lane due to analysis complexity)
        
        # Performance tracking
        self.last_analysis_time = datetime.now()
        self.analysis_count = 0
        
        logger.info(f"Smart Lane Service initialized - Mock mode: {self.mock_mode}, Enabled: {self.smart_lane_enabled}")
    
    # =========================================================================
    # PIPELINE INITIALIZATION
    # =========================================================================
    
    async def initialize_pipeline(self, chain_id: int = 1) -> bool:
        """
        Initialize Smart Lane analysis pipeline.
        
        Args:
            chain_id: Blockchain chain ID
            
        Returns:
            bool: True if initialization successful
        """
        if self.mock_mode or not self.smart_lane_enabled:
            logger.info("Smart Lane pipeline initialization skipped (mock mode or disabled)")
            return True
            
        try:
            if not SMART_LANE_AVAILABLE:
                logger.warning("Smart Lane components not available, falling back to mock mode")
                self.mock_mode = True
                return True
            
            # Create Smart Lane configuration
            config = SmartLaneConfig(
                analysis_depth=AnalysisDepth.COMPREHENSIVE,
                max_analysis_time_seconds=5.0,
                thought_log_enabled=True,
                enable_dynamic_sizing=True
            )
            
            # Initialize pipeline
            self.pipeline = SmartLanePipeline(
                config=config,
                chain_id=chain_id,
                enable_caching=True
            )
            
            # Initialize pipeline components (async)
            await self.pipeline.initialize()
            
            self.pipeline_initialized = True
            logger.info(f"Smart Lane pipeline initialized successfully for chain {chain_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Smart Lane pipeline: {e}")
            self.mock_mode = True
            return False
    
    # =========================================================================
    # STATUS AND METRICS
    # =========================================================================
    
    def get_pipeline_status(self) -> Dict[str, Any]:
        """
        Get Smart Lane pipeline status with error handling.
        
        Returns:
            Pipeline status data or cached/fallback data
        """
        try:
            if not self.circuit_breaker.call_allowed():
                return self._get_cached_status()
            
            if self.mock_mode or not self.pipeline_initialized:
                status = self._generate_mock_status()
            else:
                # Get real pipeline status
                status = self._get_live_pipeline_status()
            
            # Cache successful response
            cache.set(self.STATUS_CACHE_KEY, status, self.CACHE_TIMEOUT)
            self.circuit_breaker.record_success()
            
            return status
            
        except Exception as e:
            self.logger.error(f"Failed to get Smart Lane status: {e}")
            self.circuit_breaker.record_failure()
            return self._get_cached_status()
    
    def get_analysis_metrics(self) -> Dict[str, Any]:
        """
        Get Smart Lane analysis performance metrics.
        
        Returns:
            Analysis metrics or cached/fallback data
        """
        try:
            if not self.circuit_breaker.call_allowed():
                return self._get_cached_metrics()
            
            if self.mock_mode or not self.pipeline_initialized:
                metrics = self._generate_mock_metrics()
            else:
                # Get real analysis metrics
                metrics = self._get_live_analysis_metrics()
            
            # Cache successful response  
            cache.set(self.ANALYSIS_CACHE_KEY, metrics, self.CACHE_TIMEOUT)
            self.circuit_breaker.record_success()
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"Failed to get Smart Lane metrics: {e}")
            self.circuit_breaker.record_failure()
            return self._get_cached_metrics()
    
    def get_recent_thought_logs(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get recent AI thought logs for dashboard display."""
        try:
            if self.mock_mode or not self.pipeline_initialized:
                return self._generate_mock_thought_logs(limit)
            else:
                return self._get_live_thought_logs(limit)
        except Exception as e:
            self.logger.error(f"Failed to get thought logs: {e}")
            return []
    
    async def analyze_token(self, token_address: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Perform Smart Lane token analysis.
        
        Args:
            token_address: Token contract address
            context: Additional analysis context
            
        Returns:
            Analysis results or error information
        """
        if self.mock_mode or not self.pipeline_initialized:
            return self._generate_mock_analysis_result(token_address)
            
        try:
            if not self.circuit_breaker.call_allowed():
                raise SmartLaneServiceError("Circuit breaker is open")
            
            # Perform real analysis
            analysis = await self.pipeline.analyze_token(
                token_address=token_address,
                context=context or {}
            )
            
            self.circuit_breaker.record_success()
            self.analysis_count += 1
            
            return {
                'success': True,
                'analysis': analysis,
                'analysis_time_ms': analysis.total_analysis_time_ms,
                'thought_log': analysis.thought_log if hasattr(analysis, 'thought_log') else None
            }
            
        except Exception as e:
            self.logger.error(f"Smart Lane analysis failed: {e}")
            self.circuit_breaker.record_failure()
            return {
                'success': False,
                'error': str(e),
                'fallback_data': self._generate_mock_analysis_result(token_address)
            }
    
    # =========================================================================
    # PRIVATE METHODS - LIVE DATA
    # =========================================================================
    
    def _get_live_pipeline_status(self) -> Dict[str, Any]:
        """Get status from live Smart Lane pipeline."""
        if not self.pipeline:
            raise SmartLaneServiceError("Pipeline not initialized")
            
        return {
            'status': self.pipeline.status,
            'pipeline_active': self.pipeline.status == PipelineStatus.RUNNING,
            'analyzers_count': len(self.pipeline.config.enabled_categories or []),
            'cache_enabled': self.pipeline.enable_caching,
            'analysis_depth': self.pipeline.config.analysis_depth.value,
            'thought_log_enabled': self.pipeline.config.thought_log_enabled,
            'total_analyses': self.pipeline.performance_metrics.get('total_analyses', 0),
            'successful_analyses': self.pipeline.performance_metrics.get('successful_analyses', 0),
            'average_analysis_time_ms': self.pipeline.performance_metrics.get('average_analysis_time_ms', 0),
            'uptime_seconds': (datetime.now() - self.last_analysis_time).total_seconds(),
            '_mock': False
        }
    
    def _get_live_analysis_metrics(self) -> Dict[str, Any]:
        """Get metrics from live Smart Lane pipeline."""
        if not self.pipeline:
            raise SmartLaneServiceError("Pipeline not initialized")
            
        return {
            'total_analyses': self.analysis_count,
            'successful_analyses': self.pipeline.performance_metrics.get('successful_analyses', 0),
            'failed_analyses': self.pipeline.performance_metrics.get('failed_analyses', 0),
            'average_analysis_time_ms': self.pipeline.performance_metrics.get('average_analysis_time_ms', 0),
            'cache_hit_ratio': self.pipeline.performance_metrics.get('cache_hit_ratio', 0),
            'analyzers_active': len(self.pipeline.config.enabled_categories or []),
            'thought_logs_generated': self.pipeline.performance_metrics.get('thought_logs_generated', 0),
            'risk_assessments_completed': self.pipeline.performance_metrics.get('risk_assessments_completed', 0),
            'position_sizings_calculated': self.pipeline.performance_metrics.get('position_sizings_calculated', 0),
            'last_analysis_time': self.last_analysis_time.isoformat(),
            '_mock': False
        }
    
    def _get_live_thought_logs(self, limit: int) -> List[Dict[str, Any]]:
        """Get recent thought logs from live pipeline."""
        if not self.pipeline:
            return []
            
        # This would integrate with actual thought log storage
        # For now, return empty list as thought logs are stored per analysis
        return []
    
    # =========================================================================
    # PRIVATE METHODS - MOCK DATA
    # =========================================================================
    
    def _generate_mock_status(self) -> Dict[str, Any]:
        """Generate mock Smart Lane status for development/fallback."""
        return {
            'status': 'RUNNING',
            'pipeline_active': True,
            'analyzers_count': 5,
            'cache_enabled': True,
            'analysis_depth': 'COMPREHENSIVE',
            'thought_log_enabled': True,
            'total_analyses': random.randint(50, 200),
            'successful_analyses': random.randint(45, 190),
            'average_analysis_time_ms': random.uniform(2500, 4500),
            'uptime_seconds': random.randint(3600, 86400),
            '_mock': True
        }
    
    def _generate_mock_metrics(self) -> Dict[str, Any]:
        """Generate mock Smart Lane metrics for development/fallback."""
        total = random.randint(20, 100)
        successful = random.randint(int(total * 0.8), total)
        
        return {
            'total_analyses': total,
            'successful_analyses': successful,
            'failed_analyses': total - successful,
            'average_analysis_time_ms': random.uniform(2000, 4800),
            'cache_hit_ratio': random.uniform(0.6, 0.9),
            'analyzers_active': 5,
            'thought_logs_generated': successful,
            'risk_assessments_completed': successful,
            'position_sizings_calculated': successful,
            'last_analysis_time': datetime.now().isoformat(),
            '_mock': True
        }
    
    def _generate_mock_thought_logs(self, limit: int) -> List[Dict[str, Any]]:
        """Generate mock thought logs for development/fallback."""
        thought_logs = []
        
        for i in range(min(limit, 3)):
            thought_logs.append({
                'id': f"mock_log_{i}",
                'timestamp': (datetime.now() - timedelta(minutes=i*10)).isoformat(),
                'token_address': f"0x{random.randint(1000000000000000, 9999999999999999):016x}",
                'decision': random.choice(['BUY', 'HOLD', 'AVOID']),
                'confidence': random.uniform(0.6, 0.95),
                'reasoning_summary': f"Mock analysis {i+1}: Risk assessment completed with {random.randint(3,5)} factors considered.",
                'risk_score': random.uniform(0.1, 0.8),
                'analysis_time_ms': random.uniform(2000, 4500)
            })
        
        return thought_logs
    
    def _generate_mock_analysis_result(self, token_address: str) -> Dict[str, Any]:
        """Generate mock analysis result for development/fallback."""
        return {
            'token_address': token_address,
            'overall_risk_score': random.uniform(0.2, 0.8),
            'recommended_action': random.choice(['BUY', 'HOLD', 'AVOID', 'PARTIAL_BUY']),
            'confidence': random.uniform(0.6, 0.9),
            'analysis_time_ms': random.uniform(2000, 4500),
            'risk_categories': {
                'honeypot_detection': random.uniform(0.1, 0.3),
                'social_sentiment': random.uniform(0.4, 0.8),
                'technical_analysis': random.uniform(0.3, 0.7),
                'contract_security': random.uniform(0.2, 0.5),
                'market_structure': random.uniform(0.3, 0.6)
            },
            'thought_log_summary': f"Comprehensive analysis of {token_address[:8]}... completed with multiple risk factors evaluated.",
            '_mock': True
        }
    
    # =========================================================================
    # PRIVATE METHODS - CACHING
    # =========================================================================
    
    def _get_cached_status(self) -> Dict[str, Any]:
        """Get cached Smart Lane status or generate fallback."""
        cached = cache.get(self.STATUS_CACHE_KEY)
        if cached:
            return cached
        return self._generate_mock_status()
    
    def _get_cached_metrics(self) -> Dict[str, Any]:
        """Get cached Smart Lane metrics or generate fallback."""
        cached = cache.get(self.ANALYSIS_CACHE_KEY)
        if cached:
            return cached
        return self._generate_mock_metrics()


# =========================================================================
# SERVICE INSTANCE
# =========================================================================

# Create global service instance
smart_lane_service = DashboardSmartLaneService()