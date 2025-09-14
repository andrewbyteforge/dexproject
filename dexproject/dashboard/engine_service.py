"""
Dashboard Engine Service Layer

Provides abstraction between dashboard UI and Fast Lane engine.
Includes error handling, circuit breaker pattern, and fallback data.

UPDATED: Now integrates with real Fast Lane execution engine for live metrics.

File: dexproject/dashboard/engine_service.py
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

# Import Fast Lane engine components
try:
    from engine.execution.fast_engine import FastLaneExecutionEngine, FastLaneStatus
    from engine.cache.risk_cache import FastRiskCache
    from engine.config import config as engine_config
    from engine.execution.gas_optimizer import GasOptimizationEngine
    from engine.execution.nonce_manager import NonceManager
    FAST_LANE_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Fast Lane engine not available: {e}")
    FAST_LANE_AVAILABLE = False

logger = logging.getLogger(__name__)


class EngineServiceError(Exception):
    """Base exception for engine service errors."""
    pass


class EngineCircuitBreaker:
    """Circuit breaker pattern for engine failures."""
    
    def __init__(self, failure_threshold: int = 5, recovery_time: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN
    
    def call_allowed(self) -> bool:
        """Check if calls to engine are allowed."""
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
        """Record successful engine call."""
        self.failure_count = 0
        self.state = 'CLOSED'
    
    def record_failure(self):
        """Record failed engine call."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            self.state = 'OPEN'
            logger.warning(f"Engine circuit breaker OPEN after {self.failure_count} failures")


class DashboardEngineService:
    """
    Service layer for dashboard to communicate with Fast Lane engine.
    
    UPDATED: Now provides real Fast Lane integration with fallback to mock data.
    
    Provides:
    - Error handling and graceful degradation
    - Circuit breaker pattern for reliability
    - Caching for performance and fallback data
    - Live Fast Lane engine integration
    - Mock data generation for development/fallback
    """
    
    def __init__(self):
        self.logger = logger
        self.circuit_breaker = EngineCircuitBreaker()
        
        # Determine operating mode
        self.mock_mode = getattr(settings, 'ENGINE_MOCK_MODE', not FAST_LANE_AVAILABLE)
        self.fast_lane_engine: Optional[FastLaneExecutionEngine] = None
        self.engine_initialized = False
        
        # Cache keys
        self.METRICS_CACHE_KEY = 'dashboard:metrics'
        self.STATUS_CACHE_KEY = 'dashboard:engine_status'
        self.CACHE_TIMEOUT = 30  # seconds
        
        # Performance tracking
        self.last_metrics_time = datetime.now()
        
        logger.info(f"Dashboard Engine Service initialized - Mock mode: {self.mock_mode}")
    
    # =========================================================================
    # ENGINE INITIALIZATION
    # =========================================================================
    
    async def initialize_engine(self, chain_id: int = 1) -> bool:
        """
        Initialize Fast Lane engine connection.
        
        Args:
            chain_id: Blockchain network identifier (default: Ethereum mainnet)
            
        Returns:
            True if engine initialized successfully, False otherwise
        """
        if self.mock_mode or not FAST_LANE_AVAILABLE:
            logger.info("Engine initialization skipped - running in mock mode")
            return True
        
        try:
            logger.info(f"Initializing Fast Lane engine for chain {chain_id}")
            
            # Create Fast Lane engine instance
            self.fast_lane_engine = FastLaneExecutionEngine(chain_id=chain_id)
            
            # Start the engine (this is async)
            success = await self.fast_lane_engine.start()
            
            if success:
                self.engine_initialized = True
                logger.info("Fast Lane engine initialized successfully")
                return True
            else:
                logger.error("Failed to start Fast Lane engine")
                return False
                
        except Exception as e:
            logger.error(f"Failed to initialize Fast Lane engine: {e}", exc_info=True)
            self.mock_mode = True  # Fallback to mock mode
            return False
    
    async def shutdown_engine(self) -> None:
        """Shutdown Fast Lane engine gracefully."""
        if self.fast_lane_engine and self.engine_initialized:
            try:
                await self.fast_lane_engine.stop()
                logger.info("Fast Lane engine shut down successfully")
            except Exception as e:
                logger.error(f"Error shutting down engine: {e}")
            finally:
                self.engine_initialized = False
    
    # =========================================================================
    # PUBLIC API METHODS
    # =========================================================================
    
    def get_engine_status(self) -> Dict[str, Any]:
        """
        Get current engine status with graceful error handling.
        
        Returns:
            Engine status data or cached/fallback data
        """
        try:
            if not self.circuit_breaker.call_allowed():
                return self._get_cached_status()
            
            if self.mock_mode or not self.engine_initialized:
                status = self._generate_mock_status()
            else:
                # Get real engine status asynchronously
                status = self._get_live_engine_status()
            
            # Cache successful response
            cache.set(self.STATUS_CACHE_KEY, status, self.CACHE_TIMEOUT)
            self.circuit_breaker.record_success()
            
            return status
            
        except Exception as e:
            self.logger.error(f"Failed to get engine status: {e}")
            self.circuit_breaker.record_failure()
            return self._get_cached_status()
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics with error handling.
        
        Returns:
            Performance metrics or cached/fallback data
        """
        try:
            if not self.circuit_breaker.call_allowed():
                return self._get_cached_metrics()
            
            if self.mock_mode or not self.engine_initialized:
                metrics = self._generate_mock_metrics()
            else:
                # Get real engine metrics
                metrics = self._get_live_performance_metrics()
            
            # Cache successful response
            cache.set(self.METRICS_CACHE_KEY, metrics, self.CACHE_TIMEOUT)
            self.circuit_breaker.record_success()
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"Failed to get performance metrics: {e}")
            self.circuit_breaker.record_failure()
            return self._get_cached_metrics()
    
    def get_trading_sessions(self) -> List[Dict[str, Any]]:
        """Get current trading sessions."""
        try:
            if self.mock_mode or not self.engine_initialized:
                return self._generate_mock_sessions()
            else:
                return self._get_live_trading_sessions()
        except Exception as e:
            self.logger.error(f"Failed to get trading sessions: {e}")
            return []
    
    def set_trading_mode(self, mode: str) -> bool:
        """
        Set trading mode (FAST_LANE or SMART_LANE).
        
        Args:
            mode: Trading mode to set
            
        Returns:
            True if mode set successfully, False otherwise
        """
        try:
            if mode not in ['FAST_LANE', 'SMART_LANE']:
                logger.warning(f"Invalid trading mode: {mode}")
                return False
            
            if self.mock_mode:
                logger.info(f"Mock mode: Setting trading mode to {mode}")
                cache.set('dashboard:trading_mode', mode, 300)
                return True
            
            if not self.engine_initialized:
                logger.warning("Cannot set trading mode - engine not initialized")
                return False
            
            # TODO: Implement actual engine mode switching
            logger.info(f"Setting Fast Lane engine mode to {mode}")
            cache.set('dashboard:trading_mode', mode, 300)
            return True
            
        except Exception as e:
            logger.error(f"Failed to set trading mode: {e}")
            return False
    
    # =========================================================================
    # LIVE ENGINE INTEGRATION
    # =========================================================================
    
    def _get_live_engine_status(self) -> Dict[str, Any]:
        """Get live engine status from Fast Lane engine."""
        if not self.fast_lane_engine:
            raise EngineServiceError("Engine not initialized")
        
        try:
            # Get engine status using async wrapper
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                status_data = loop.run_until_complete(self.fast_lane_engine.get_status())
            finally:
                loop.close()
            
            # Transform engine status to dashboard format
            return {
                'status': 'OPERATIONAL' if status_data['status'] == 'RUNNING' else 'DEGRADED',
                'message': f"Fast Lane engine {status_data['status'].lower()}",
                'fast_lane_active': status_data['status'] == 'RUNNING',
                'smart_lane_active': False,  # Phase 5 not implemented yet
                'mempool_connected': status_data['components']['provider_manager'],
                'risk_cache_status': 'HEALTHY' if status_data['components']['risk_cache'] else 'UNAVAILABLE',
                'provider_status': {
                    'alchemy': 'CONNECTED' if status_data['components']['provider_manager'] else 'DISCONNECTED',
                    'gas_optimizer': 'CONNECTED' if status_data['components']['gas_optimizer'] else 'DISCONNECTED',
                    'nonce_manager': 'CONNECTED' if status_data['components']['nonce_manager'] else 'DISCONNECTED'
                },
                'uptime_seconds': int(status_data['uptime_seconds']),
                'queue_status': {
                    'pending': status_data['queue']['pending'],
                    'max_size': status_data['queue']['max_size']
                },
                'wallet': {
                    'configured': status_data['wallet']['configured'],
                    'address': status_data['wallet']['address']
                },
                '_live': True,
                '_timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get live engine status: {e}")
            raise EngineServiceError(f"Live engine status error: {e}")
    
    def _get_live_performance_metrics(self) -> Dict[str, Any]:
        """Get live performance metrics from Fast Lane engine."""
        if not self.fast_lane_engine:
            raise EngineServiceError("Engine not initialized")
        
        try:
            # Get engine status with performance data
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                status_data = loop.run_until_complete(self.fast_lane_engine.get_status())
            finally:
                loop.close()
            
            perf_data = status_data['performance']
            
            return {
                'execution_time_ms': perf_data['last_execution_time_ms'],
                'average_execution_time_ms': perf_data['average_execution_time_ms'],
                'success_rate': perf_data['success_rate_percent'],
                'trades_per_minute': self._calculate_trades_per_minute(perf_data),
                'total_executions': perf_data['total_executions'],
                'successful_executions': perf_data['successful_executions'],
                'risk_cache_hits': 100,  # Placeholder - need to add this to engine
                'mempool_latency_ms': 1.5,  # Placeholder - need to add this to engine
                'gas_optimization_ms': 15.0,  # From Phase 4 test results
                'nonce_allocation_ms': 0.2,  # From Phase 4 test results
                'fast_lane_trades_today': perf_data['total_executions'],
                'smart_lane_trades_today': 0,  # Phase 5 not implemented
                '_live': True,
                '_timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get live performance metrics: {e}")
            raise EngineServiceError(f"Live metrics error: {e}")
    
    def _get_live_trading_sessions(self) -> List[Dict[str, Any]]:
        """Get live trading sessions from Fast Lane engine."""
        # TODO: Implement session management in engine
        return []
    
    def _calculate_trades_per_minute(self, perf_data: Dict[str, Any]) -> float:
        """Calculate trades per minute from performance data."""
        total_executions = perf_data.get('total_executions', 0)
        if total_executions == 0:
            return 0.0
        
        # Estimate based on recent activity
        # For now, use a simple calculation - this should be improved with real time tracking
        return min(total_executions / 60.0, 15.0)  # Cap at reasonable value
    
    # =========================================================================
    # CACHE AND FALLBACK METHODS
    # =========================================================================
    
    def _get_cached_status(self) -> Dict[str, Any]:
        """Get cached engine status or fallback."""
        cached = cache.get(self.STATUS_CACHE_KEY)
        if cached:
            cached['_cached'] = True
            cached['_cache_timestamp'] = datetime.now().isoformat()
            return cached
        
        # Fallback status
        return {
            'status': 'UNKNOWN',
            'message': 'Engine status unavailable - using fallback data',
            'fast_lane_active': False,
            'smart_lane_active': False,
            'mempool_connected': False,
            'risk_cache_status': 'UNKNOWN',
            '_fallback': True,
            '_cache_timestamp': datetime.now().isoformat()
        }
    
    def _get_cached_metrics(self) -> Dict[str, Any]:
        """Get cached metrics or fallback."""
        cached = cache.get(self.METRICS_CACHE_KEY)
        if cached:
            cached['_cached'] = True
            cached['_cache_timestamp'] = datetime.now().isoformat()
            return cached
        
        # Fallback metrics
        return {
            'execution_time_ms': 0,
            'success_rate': 0.0,
            'trades_per_minute': 0.0,
            'risk_cache_hits': 0,
            'mempool_latency_ms': 0,
            '_fallback': True,
            '_cache_timestamp': datetime.now().isoformat()
        }
    
    # =========================================================================
    # MOCK DATA GENERATION (Enhanced with real Phase 4 test results)
    # =========================================================================
    
    def _generate_mock_status(self) -> Dict[str, Any]:
        """Generate realistic mock engine status based on Phase 4 achievements."""
        return {
            'status': 'OPERATIONAL',
            'message': 'All systems operational (mock mode)',
            'fast_lane_active': True,
            'smart_lane_active': False,  # Phase 5 not ready
            'mempool_connected': True,
            'risk_cache_status': 'HEALTHY',
            'provider_status': {
                'alchemy': 'CONNECTED',
                'ankr': 'CONNECTED', 
                'infura': 'CONNECTED',
                'gas_optimizer': 'CONNECTED',
                'nonce_manager': 'CONNECTED'
            },
            'uptime_seconds': 3600 + random.randint(0, 7200),
            'queue_status': {
                'pending': random.randint(0, 5),
                'max_size': 1000
            },
            'wallet': {
                'configured': True,
                'address': '0x742d35Cc63C7aEc567d54C1a4b1E0De57D5Ce1D1'
            },
            'last_trade_timestamp': (datetime.now() - timedelta(minutes=random.randint(1, 10))).isoformat(),
            '_mock': True,
            '_timestamp': datetime.now().isoformat()
        }
    
    def _generate_mock_metrics(self) -> Dict[str, Any]:
        """Generate realistic mock performance metrics based on Phase 4 test results."""
        # Use actual Phase 4 test results as baseline (78ms execution, 94% success rate)
        base_execution_time = 78.0
        execution_time = base_execution_time + random.uniform(-10, 15)
        
        return {
            'execution_time_ms': round(execution_time, 2),
            'average_execution_time_ms': round(base_execution_time + random.uniform(-5, 5), 2),
            'success_rate': round(random.uniform(92, 98), 1),
            'trades_per_minute': round(random.uniform(8, 15), 1),
            'total_executions': random.randint(45, 120),
            'successful_executions': random.randint(40, 115),
            'risk_cache_hits': random.randint(95, 100),
            'mempool_latency_ms': round(random.uniform(0.5, 2.0), 2),
            'gas_optimization_ms': round(random.uniform(12, 18), 2),  # Phase 4 test: 15.42ms
            'nonce_allocation_ms': round(random.uniform(0.1, 0.5), 2),  # Phase 4 test: 0.00ms
            'fast_lane_trades_today': random.randint(45, 120),
            'smart_lane_trades_today': 0,  # Phase 5 not implemented
            '_mock': True,
            '_timestamp': datetime.now().isoformat()
        }
    
    def _generate_mock_sessions(self) -> List[Dict[str, Any]]:
        """Generate mock trading sessions."""
        return [
            {
                'id': 'session_001',
                'name': 'Fast Lane Strategy',
                'mode': 'FAST_LANE',
                'status': 'ACTIVE',
                'trades_today': random.randint(20, 30),
                'success_rate': round(random.uniform(90, 98), 1),
                'pnl_usd': round(random.uniform(100, 300), 2),
                'started_at': (datetime.now() - timedelta(hours=random.randint(1, 6))).isoformat(),
                '_mock': True
            },
            {
                'id': 'session_002', 
                'name': 'Smart Analysis (Coming Soon)',
                'mode': 'SMART_LANE',
                'status': 'DISABLED',
                'trades_today': 0,
                'success_rate': 0.0,
                'pnl_usd': 0.0,
                'started_at': None,
                '_mock': True,
                '_note': 'Available in Phase 5'
            }
        ]


# Global service instance
engine_service = DashboardEngineService()