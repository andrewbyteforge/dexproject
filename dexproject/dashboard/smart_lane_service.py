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
            logger.warning(f"Smart Lane circuit breaker opened after {self.failure_count} failures")


class SmartLaneEngineService:
    """
    Smart Lane Engine Service providing dashboard integration capabilities.
    
    Manages Smart Lane pipeline lifecycle, analysis execution, metrics collection,
    and error handling with circuit breaker pattern.
    """
    
    def __init__(self):
        """Initialize Smart Lane service with configuration."""
        self.pipeline: Optional[SmartLanePipeline] = None
        self.cache: Optional[SmartLaneCache] = None
        self.thought_log_generator: Optional[ThoughtLogGenerator] = None
        self.position_sizer: Optional[PositionSizer] = None
        self.exit_strategy_manager: Optional[ExitStrategyManager] = None
        
        # Service state
        self.initialized = False
        self.mock_mode = getattr(settings, 'SMART_LANE_MOCK_MODE', True)
        self.circuit_breaker = SmartLaneCircuitBreaker()
        
        # Metrics tracking
        self.metrics = {
            'analyses_completed': 0,
            'successful_analyses': 0,
            'failed_analyses': 0,
            'average_analysis_time_ms': 0.0,
            'cache_hit_ratio': 0.0,
            'thought_logs_generated': 0,
            'risk_assessments_completed': 0,
            'last_analysis_timestamp': None,
            'active_analyses': 0,
            'total_errors': 0,
            'pipeline_status': 'UNINITIALIZED'
        }
        
        # Thought logs storage (in production, use database)
        self.thought_logs = {}
        
        # Cache for recent analysis results
        self.recent_analyses = []
        
        logger.info("Smart Lane Engine Service initialized")
    
    async def initialize(self) -> bool:
        """
        Initialize Smart Lane pipeline and components.
        
        Returns:
            bool: True if initialization successful, False otherwise
        """
        try:
            if not SMART_LANE_AVAILABLE:
                logger.info("Smart Lane components not available, using mock mode")
                self.mock_mode = True
                self.initialized = True
                return True
            
            if self.mock_mode:
                logger.info("Smart Lane service initialized in mock mode")
                self.initialized = True
                return True
            
            # Initialize Smart Lane components
            config = SmartLaneConfig(
                analysis_depth=AnalysisDepth.COMPREHENSIVE,
                enable_thought_log=True,
                cache_enabled=True,
                timeout_seconds=30
            )
            
            self.pipeline = SmartLanePipeline(config)
            self.cache = SmartLaneCache(strategy=CacheStrategy.BALANCED)
            self.thought_log_generator = ThoughtLogGenerator()
            self.position_sizer = PositionSizer()
            self.exit_strategy_manager = ExitStrategyManager()
            
            # Test pipeline functionality
            test_result = await self.pipeline.test_analyzers()
            if not test_result.success:
                logger.error(f"Smart Lane analyzer test failed: {test_result.errors}")
                self.mock_mode = True
            
            self.initialized = True
            self.metrics['pipeline_status'] = 'OPERATIONAL'
            logger.info("Smart Lane pipeline initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Smart Lane pipeline: {e}")
            self.mock_mode = True
            self.initialized = True
            self.metrics['pipeline_status'] = 'ERROR'
            return False
    
    def get_pipeline_status(self) -> Dict[str, Any]:
        """
        Get comprehensive Smart Lane pipeline status.
        
        Returns:
            Dict containing pipeline status and capabilities
        """
        if not self.initialized:
            return {
                'status': 'UNINITIALIZED',
                'pipeline_active': False,
                'analyzers_count': 0,
                'analysis_ready': False,
                'thought_log_enabled': False,
                '_mock': True
            }
        
        if self.mock_mode:
            return {
                'status': 'MOCK_MODE',
                'pipeline_active': True,
                'analyzers_count': 5,
                'analysis_ready': True,
                'thought_log_enabled': True,
                'capabilities': [
                    'HONEYPOT_DETECTION',
                    'LIQUIDITY_ANALYSIS', 
                    'SOCIAL_SENTIMENT',
                    'TECHNICAL_ANALYSIS',
                    'CONTRACT_SECURITY'
                ],
                '_mock': True
            }
        
        try:
            if not self.pipeline:
                return {
                    'status': 'PIPELINE_ERROR',
                    'pipeline_active': False,
                    'analyzers_count': 0,
                    'analysis_ready': False,
                    'thought_log_enabled': False,
                    'error': 'Pipeline not initialized',
                    '_mock': False
                }
            
            pipeline_status = self.pipeline.get_status()
            
            return {
                'status': pipeline_status.status.value,
                'pipeline_active': pipeline_status.active,
                'analyzers_count': len(pipeline_status.active_analyzers),
                'analysis_ready': pipeline_status.ready_for_analysis,
                'thought_log_enabled': self.thought_log_generator is not None,
                'capabilities': pipeline_status.capabilities,
                'circuit_breaker_state': self.circuit_breaker.state,
                '_mock': False
            }
            
        except Exception as e:
            logger.error(f"Error getting Smart Lane pipeline status: {e}")
            return {
                'status': 'ERROR',
                'pipeline_active': False,
                'analyzers_count': 0,
                'analysis_ready': False,
                'thought_log_enabled': False,
                'error': str(e),
                '_mock': True
            }
    
    def get_analysis_metrics(self) -> Dict[str, Any]:
        """
        Get Smart Lane analysis performance metrics.
        
        Returns:
            Dict containing comprehensive metrics
        """
        base_metrics = self.metrics.copy()
        
        if self.mock_mode:
            # Generate realistic mock metrics
            base_metrics.update({
                'analyses_completed': random.randint(150, 250),
                'successful_analyses': random.randint(140, 240),
                'failed_analyses': random.randint(5, 15),
                'average_analysis_time_ms': random.uniform(2000, 4500),
                'cache_hit_ratio': random.uniform(0.75, 0.95),
                'thought_logs_generated': random.randint(120, 200),
                'risk_assessments_completed': random.randint(140, 240),
                'last_analysis_timestamp': datetime.now().isoformat(),
                'active_analyses': random.randint(0, 3),
                'total_errors': random.randint(5, 15),
                'pipeline_status': 'MOCK_OPERATIONAL',
                '_mock': True
            })
        else:
            base_metrics['_mock'] = False
        
        # Calculate derived metrics
        if base_metrics['analyses_completed'] > 0:
            base_metrics['success_rate'] = (
                base_metrics['successful_analyses'] / 
                base_metrics['analyses_completed'] * 100
            )
        else:
            base_metrics['success_rate'] = 0.0
        
        return base_metrics
    
    async def run_analysis(self, token_address: str, analysis_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run Smart Lane analysis on a token.
        
        Args:
            token_address: Token contract address to analyze
            analysis_config: Configuration parameters for analysis
            
        Returns:
            Dict containing analysis results
        """
        start_time = datetime.now()
        analysis_id = f"analysis_{int(start_time.timestamp() * 1000)}"
        
        try:
            if not self.circuit_breaker.call_allowed():
                raise SmartLaneServiceError("Smart Lane circuit breaker is open")
            
            self.metrics['active_analyses'] += 1
            
            if self.mock_mode:
                # Generate mock analysis results
                await asyncio.sleep(random.uniform(2.0, 4.5))  # Simulate analysis time
                
                analysis_result = self._generate_mock_analysis(token_address, analysis_id)
                thought_log = self._generate_mock_thought_log(analysis_id, analysis_result)
                
                self.circuit_breaker.record_success()
                
            else:
                # Run real Smart Lane analysis
                if not self.pipeline:
                    raise SmartLaneServiceError("Smart Lane pipeline not initialized")
                
                analysis_result = await self.pipeline.analyze_token(
                    token_address=token_address,
                    depth=AnalysisDepth.COMPREHENSIVE
                )
                
                if self.thought_log_generator:
                    thought_log = await self.thought_log_generator.generate_log(
                        analysis_result,
                        include_reasoning=True
                    )
                else:
                    thought_log = None
                
                self.circuit_breaker.record_success()
            
            # Update metrics
            end_time = datetime.now()
            analysis_time_ms = (end_time - start_time).total_seconds() * 1000
            
            self.metrics['analyses_completed'] += 1
            self.metrics['successful_analyses'] += 1
            self.metrics['last_analysis_timestamp'] = end_time.isoformat()
            
            # Update rolling average
            if self.metrics['analyses_completed'] == 1:
                self.metrics['average_analysis_time_ms'] = analysis_time_ms
            else:
                alpha = 0.1  # Exponential moving average factor
                self.metrics['average_analysis_time_ms'] = (
                    alpha * analysis_time_ms + 
                    (1 - alpha) * self.metrics['average_analysis_time_ms']
                )
            
            # Store thought log
            if thought_log:
                self.thought_logs[analysis_id] = thought_log
                self.metrics['thought_logs_generated'] += 1
            
            # Add to recent analyses
            self.recent_analyses.append({
                'id': analysis_id,
                'timestamp': end_time.isoformat(),
                'token_address': token_address,
                'result': analysis_result,
                'analysis_time_ms': analysis_time_ms
            })
            
            # Keep only last 50 analyses
            if len(self.recent_analyses) > 50:
                self.recent_analyses = self.recent_analyses[-50:]
            
            logger.info(f"Smart Lane analysis completed for {token_address} in {analysis_time_ms:.2f}ms")
            
            return {
                'success': True,
                'analysis_id': analysis_id,
                'token_address': token_address,
                'result': analysis_result,
                'thought_log_id': analysis_id if thought_log else None,
                'analysis_time_ms': analysis_time_ms,
                'timestamp': end_time.isoformat(),
                '_mock': self.mock_mode
            }
            
        except Exception as e:
            logger.error(f"Smart Lane analysis failed for {token_address}: {e}")
            
            self.circuit_breaker.record_failure()
            self.metrics['failed_analyses'] += 1
            self.metrics['total_errors'] += 1
            
            return {
                'success': False,
                'analysis_id': analysis_id,
                'token_address': token_address,
                'error': str(e),
                'timestamp': datetime.now().isoformat(),
                '_mock': self.mock_mode
            }
            
        finally:
            self.metrics['active_analyses'] = max(0, self.metrics['active_analyses'] - 1)
    
    def get_thought_log(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve thought log for a specific analysis.
        
        Args:
            analysis_id: Analysis identifier
            
        Returns:
            Thought log data or None if not found
        """
        return self.thought_logs.get(analysis_id)
    
    def get_recent_thought_logs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent thought logs with metadata.
        
        Args:
            limit: Maximum number of logs to return
            
        Returns:
            List of recent thought logs
        """
        recent_logs = []
        
        for analysis in self.recent_analyses[-limit:]:
            analysis_id = analysis['id']
            if analysis_id in self.thought_logs:
                recent_logs.append({
                    'analysis_id': analysis_id,
                    'timestamp': analysis['timestamp'],
                    'token_address': analysis['token_address'],
                    'thought_log': self.thought_logs[analysis_id]
                })
        
        return recent_logs
    
    def get_recent_analyses(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get recent analysis results.
        
        Args:
            limit: Maximum number of analyses to return
            
        Returns:
            List of recent analyses
        """
        return self.recent_analyses[-limit:]
    
    def clear_cache(self) -> bool:
        """
        Clear Smart Lane caches and reset metrics.
        
        Returns:
            bool: True if successful
        """
        try:
            if self.cache and not self.mock_mode:
                self.cache.clear_all()
            
            # Reset metrics
            self.metrics.update({
                'analyses_completed': 0,
                'successful_analyses': 0,
                'failed_analyses': 0,
                'average_analysis_time_ms': 0.0,
                'cache_hit_ratio': 0.0,
                'thought_logs_generated': 0,
                'risk_assessments_completed': 0,
                'last_analysis_timestamp': None,
                'active_analyses': 0,
                'total_errors': 0
            })
            
            # Clear stored data
            self.thought_logs.clear()
            self.recent_analyses.clear()
            
            logger.info("Smart Lane cache and metrics cleared")
            return True
            
        except Exception as e:
            logger.error(f"Failed to clear Smart Lane cache: {e}")
            return False
    
    def _generate_mock_analysis(self, token_address: str, analysis_id: str) -> Dict[str, Any]:
        """Generate realistic mock analysis results."""
        risk_score = random.uniform(0.1, 0.9)
        
        return {
            'token_address': token_address,
            'analysis_id': analysis_id,
            'overall_risk_score': risk_score,
            'risk_category': 'LOW' if risk_score < 0.3 else 'MEDIUM' if risk_score < 0.7 else 'HIGH',
            'analyzers': {
                'honeypot_detection': {
                    'risk_score': random.uniform(0.0, 0.3),
                    'is_honeypot': random.choice([True, False]),
                    'confidence': random.uniform(0.8, 1.0)
                },
                'liquidity_analysis': {
                    'liquidity_score': random.uniform(0.4, 1.0),
                    'pool_size_usd': random.uniform(10000, 1000000),
                    'volume_24h': random.uniform(5000, 500000)
                },
                'social_sentiment': {
                    'sentiment_score': random.uniform(-1.0, 1.0),
                    'mention_count': random.randint(10, 1000),
                    'trend': random.choice(['BULLISH', 'BEARISH', 'NEUTRAL'])
                },
                'technical_analysis': {
                    'momentum_score': random.uniform(-1.0, 1.0),
                    'rsi': random.uniform(20, 80),
                    'trend_direction': random.choice(['UP', 'DOWN', 'SIDEWAYS'])
                },
                'contract_security': {
                    'security_score': random.uniform(0.6, 1.0),
                    'verified_contract': random.choice([True, False]),
                    'proxy_contract': random.choice([True, False])
                }
            },
            'recommendations': {
                'action': random.choice(['BUY', 'HOLD', 'SELL', 'AVOID']),
                'confidence': random.uniform(0.6, 0.95),
                'position_size_percentage': random.uniform(1.0, 10.0),
                'stop_loss_percentage': random.uniform(5.0, 20.0)
            },
            'timestamp': datetime.now().isoformat(),
            '_mock': True
        }
    
    def _generate_mock_thought_log(self, analysis_id: str, analysis_result: Dict[str, Any]) -> Dict[str, Any]:
        """Generate realistic mock thought log."""
        token_address = analysis_result['token_address']
        risk_category = analysis_result['risk_category']
        action = analysis_result['recommendations']['action']
        
        reasoning_steps = [
            f"Analyzing token {token_address[:10]}... for comprehensive risk assessment",
            f"Honeypot detection: {'CLEAR' if not analysis_result['analyzers']['honeypot_detection']['is_honeypot'] else 'DETECTED'}",
            f"Liquidity analysis: ${analysis_result['analyzers']['liquidity_analysis']['pool_size_usd']:,.0f} pool size detected",
            f"Social sentiment: {analysis_result['analyzers']['social_sentiment']['trend']} trend identified",
            f"Technical analysis: {analysis_result['analyzers']['technical_analysis']['trend_direction']} momentum",
            f"Contract security: {'VERIFIED' if analysis_result['analyzers']['contract_security']['verified_contract'] else 'UNVERIFIED'} contract",
            f"Overall risk assessment: {risk_category} risk profile",
            f"Recommendation: {action} with {analysis_result['recommendations']['confidence']:.1%} confidence",
            f"Position sizing: {analysis_result['recommendations']['position_size_percentage']:.1f}% of portfolio recommended"
        ]
        
        return {
            'analysis_id': analysis_id,
            'token_address': token_address,
            'reasoning_steps': reasoning_steps,
            'final_decision': action,
            'confidence_level': analysis_result['recommendations']['confidence'],
            'risk_factors': [
                'Liquidity depth analysis',
                'Contract verification status',
                'Social sentiment indicators',
                'Technical momentum signals',
                'Honeypot detection results'
            ],
            'timestamp': datetime.now().isoformat(),
            '_mock': True
        }


# Global Smart Lane service instance
smart_lane_service = SmartLaneEngineService()


# =========================================================================
# MODULE INITIALIZATION
# =========================================================================

logger.info("Smart Lane Engine Service module loaded successfully")