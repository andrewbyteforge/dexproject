"""
Django communication bridge for the async trading engine.

This module integrates Redis pub/sub communication with the existing engine,
providing seamless coordination between the async engine and Django backend.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Import shared components
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared import (
    RedisClient, REDIS_CHANNELS, 
    NewPairDiscovered, FastRiskAssessment, TradingDecision, 
    ExecutionResult, EngineStatus, AlertTriggered,
    serialize_message, create_correlation_id
)

# Import engine components
from ..discovery import NewPairEvent
from ..risk import RiskAssessmentResult
from ..execution import TradeExecution, TradeDecision


logger = logging.getLogger(__name__)


# =============================================================================
# DJANGO BRIDGE CLASS
# =============================================================================

class DjangoBridge:
    """
    Communication bridge between the async engine and Django backend.
    
    This class handles:
    - Converting engine events to Redis messages for Django
    - Processing Django messages and triggering engine actions
    - Maintaining engine status and health reporting
    - Coordinating risk assessments between fast (engine) and comprehensive (Django)
    """
    
    def __init__(self, redis_url: str, engine_id: str):
        """
        Initialize Django communication bridge.
        
        Args:
            redis_url: Redis connection URL
            engine_id: Unique engine instance identifier
        """
        self.redis_client = RedisClient(redis_url)
        self.engine_id = engine_id
        self.logger = logger.getChild(self.__class__.__name__)
        
        # State tracking
        self._connected = False
        self._engine_status = "initializing"
        self._startup_time = None
        self._statistics = {
            'pairs_discovered': 0,
            'fast_assessments': 0,
            'decisions_made': 0,
            'trades_executed': 0,
            'messages_sent': 0,
            'messages_received': 0,
        }
        
        # Callback handlers (set by engine)
        self.on_comprehensive_risk_complete = None
        self.on_config_update = None
        self.on_emergency_stop = None
        
        # Correlation tracking for request/response flows
        self._pending_assessments: Dict[str, dict] = {}
    
    async def initialize(self) -> None:
        """Initialize Redis connection and set up subscriptions."""
        try:
            await self.redis_client.connect()
            
            # Set up subscriptions for messages from Django
            await self._setup_django_subscriptions()
            
            self._connected = True
            self._startup_time = datetime.now(timezone.utc)
            self._engine_status = "running"
            
            # Notify Django that engine is starting
            await self.redis_client.notify_engine_startup(
                self.engine_id, 
                self._get_engine_config()
            )
            
            self.logger.info("Django bridge initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Django bridge: {e}")
            raise
    
    async def shutdown(self) -> None:
        """Shutdown the Django bridge and clean up resources."""
        try:
            self._engine_status = "shutting_down"
            
            # Notify Django of shutdown
            await self.redis_client.notify_engine_shutdown(
                self.engine_id, 
                "normal_shutdown"
            )
            
            # Disconnect from Redis
            await self.redis_client.disconnect()
            self._connected = False
            
            self.logger.info("Django bridge shutdown complete")
            
        except Exception as e:
            self.logger.error(f"Error during Django bridge shutdown: {e}")
    
    def is_connected(self) -> bool:
        """Check if the bridge is connected and ready."""
        return self._connected and self.redis_client.is_connected()
    
    # =========================================================================
    # ENGINE → DJANGO MESSAGING
    # =========================================================================
    
    async def send_pair_discovered(self, pair_event: NewPairEvent) -> str:
        """
        Send new pair discovery notification to Django.
        
        Args:
            pair_event: New pair event from engine discovery
            
        Returns:
            Correlation ID for tracking
        """
        correlation_id = create_correlation_id()
        
        try:
            # Convert engine event to shared schema
            message = NewPairDiscovered(
                source_service="engine",
                engine_id=self.engine_id,
                correlation_id=correlation_id,
                chain_id=pair_event.chain_id,
                pair_info={
                    "pair_address": pair_event.pair_address,
                    "token0": {
                        "address": pair_event.token0_address,
                        "symbol": pair_event.token0_symbol,
                        "name": pair_event.token0_name,
                        "decimals": pair_event.token0_decimals,
                    },
                    "token1": {
                        "address": pair_event.token1_address,
                        "symbol": pair_event.token1_symbol,
                        "name": pair_event.token1_name,
                        "decimals": pair_event.token1_decimals,
                    },
                    "dex_name": pair_event.dex_name,
                    "fee_tier": pair_event.fee_tier,
                    "liquidity_usd": pair_event.initial_liquidity_usd,
                    "block_number": pair_event.block_number,
                    "transaction_hash": pair_event.transaction_hash,
                },
                source="websocket",  # Assuming WebSocket discovery
                discovery_metadata={
                    "discovery_timestamp": pair_event.timestamp.isoformat(),
                    "block_timestamp": pair_event.block_timestamp.isoformat() if pair_event.block_timestamp else None,
                }
            )
            
            await self.redis_client.publish_to_django(message)
            self._statistics['pairs_discovered'] += 1
            self._statistics['messages_sent'] += 1
            
            self.logger.info(f"Sent pair discovery to Django: {pair_event.pair_address}")
            return correlation_id
            
        except Exception as e:
            self.logger.error(f"Failed to send pair discovery: {e}")
            raise
    
    async def send_fast_risk_complete(
        self, 
        assessment_result: RiskAssessmentResult,
        correlation_id: Optional[str] = None
    ) -> None:
        """
        Send fast risk assessment results to Django.
        
        Args:
            assessment_result: Risk assessment from engine
            correlation_id: Optional correlation ID for tracking
        """
        try:
            # Convert engine risk result to shared schema
            check_results = []
            for check_name, check_result in assessment_result.check_results.items():
                check_results.append({
                    "check_name": check_result.check_name,
                    "check_type": check_result.check_name.split('_')[0].upper(),
                    "passed": check_result.status.value == "PASSED",
                    "score": check_result.score or 0,
                    "confidence": 85,  # Default confidence for fast checks
                    "details": check_result.details,
                    "execution_time_ms": int(check_result.execution_time_ms),
                    "error_message": check_result.error_message,
                    "is_blocking": check_result.is_blocking,
                })
            
            message = FastRiskAssessment(
                source_service="engine",
                engine_id=self.engine_id,
                correlation_id=correlation_id or create_correlation_id(),
                pair_address=assessment_result.pair_event.pair_address,
                token_address=assessment_result.pair_event.token0_address,  # Assuming token0 is the new token
                chain_id=assessment_result.pair_event.chain_id,
                overall_risk_level=assessment_result.risk_level.lower(),
                overall_score=assessment_result.overall_risk_score,
                confidence_score=75,  # Default confidence for fast assessment
                is_tradeable=assessment_result.is_tradeable,
                checks_performed=check_results,
                processing_time_ms=int(assessment_result.assessment_time_ms),
                blocking_issues=assessment_result.blocking_issues,
                requires_comprehensive_assessment=True,  # Always require comprehensive for now
                recommended_action="comprehensive_risk_assessment",
            )
            
            await self.redis_client.publish_to_django(message)
            self._statistics['fast_assessments'] += 1
            self._statistics['messages_sent'] += 1
            
            self.logger.info(f"Sent fast risk assessment to Django: {assessment_result.pair_event.pair_address}")
            
        except Exception as e:
            self.logger.error(f"Failed to send fast risk assessment: {e}")
            raise
    
    async def send_trading_decision(
        self, 
        decision: TradeDecision,
        correlation_id: Optional[str] = None
    ) -> None:
        """
        Send trading decision to Django for recording.
        
        Args:
            decision: Trading decision from engine
            correlation_id: Optional correlation ID for tracking
        """
        try:
            # Convert engine decision to shared schema
            signals = []
            
            # Create signals from risk assessment
            if decision.risk_assessment:
                signals.append({
                    "signal_name": "overall_risk_score",
                    "signal_type": "risk",
                    "value": float(decision.risk_assessment.overall_risk_score),
                    "weight": 0.4,
                    "confidence": 80,
                    "rationale": f"Fast risk assessment scored {decision.risk_assessment.overall_risk_score}/100"
                })
            
            # Add liquidity signal
            if decision.position_size_usd:
                signals.append({
                    "signal_name": "position_size",
                    "signal_type": "execution",
                    "value": float(decision.position_size_usd),
                    "weight": 0.3,
                    "confidence": 90,
                    "rationale": f"Recommended position size based on risk profile"
                })
            
            message = TradingDecision(
                source_service="engine",
                engine_id=self.engine_id,
                correlation_id=correlation_id or create_correlation_id(),
                pair_address=decision.pair_address,
                token_address=decision.token_address,
                chain_id=decision.chain_id,
                decision=decision.action.lower(),
                confidence=decision.confidence_score,
                position_size_eth=None,  # Engine works in USD
                position_size_usd=decision.position_size_usd,
                max_slippage_percent=decision.max_slippage_percent,
                signals_analyzed=signals,
                narrative_summary=f"Engine decided to {decision.action} based on fast risk assessment",
                risk_factors=[],  # TODO: Extract from risk assessment
                opportunity_factors=[],
                counterfactuals=[],
                fast_risk_score=decision.risk_assessment.overall_risk_score if decision.risk_assessment else 50,
                liquidity_analysis={},
                market_structure={},
            )
            
            await self.redis_client.publish_to_django(message)
            self._statistics['decisions_made'] += 1
            self._statistics['messages_sent'] += 1
            
            self.logger.info(f"Sent trading decision to Django: {decision.action} for {decision.token_address}")
            
        except Exception as e:
            self.logger.error(f"Failed to send trading decision: {e}")
            raise
    
    async def send_execution_result(
        self, 
        execution: TradeExecution,
        correlation_id: Optional[str] = None
    ) -> None:
        """
        Send trade execution result to Django.
        
        Args:
            execution: Trade execution result from engine
            correlation_id: Optional correlation ID for tracking
        """
        try:
            message = ExecutionResult(
                source_service="engine",
                engine_id=self.engine_id,
                correlation_id=correlation_id or create_correlation_id(),
                pair_address=execution.decision.pair_address,
                token_address=execution.decision.token_address,
                chain_id=execution.decision.chain_id,
                decision_type=execution.decision.action.lower(),
                success=execution.status.value == "COMPLETED",
                transaction_hash=execution.transaction_hash,
                block_number=execution.block_number,
                gas_used=execution.gas_used,
                gas_price_gwei=execution.gas_price_gwei,
                actual_slippage_percent=execution.actual_slippage_percent,
                tokens_received=execution.amount_out,
                eth_spent=None,  # Engine tracks USD
                usd_value=execution.amount_in,
                execution_time_ms=int(execution.execution_time_ms),
                error_message=None,  # TODO: Add error tracking to engine
                retry_count=0,
                is_paper_trade=True,  # Assuming paper trading for now
                paper_trade_notes=execution.simulation_notes,
            )
            
            await self.redis_client.publish_to_django(message)
            self._statistics['trades_executed'] += 1
            self._statistics['messages_sent'] += 1
            
            self.logger.info(f"Sent execution result to Django: {execution.trade_id}")
            
        except Exception as e:
            self.logger.error(f"Failed to send execution result: {e}")
            raise
    
    async def send_engine_status(self) -> None:
        """Send periodic engine status update to Django."""
        try:
            uptime_seconds = 0
            if self._startup_time:
                uptime_seconds = int((datetime.now(timezone.utc) - self._startup_time).total_seconds())
            
            message = EngineStatus(
                source_service="engine",
                engine_id=self.engine_id,
                status=self._engine_status,
                uptime_seconds=uptime_seconds,
                pairs_discovered_1h=self._statistics['pairs_discovered'],  # Simplified
                risk_assessments_1h=self._statistics['fast_assessments'],
                decisions_made_1h=self._statistics['decisions_made'],
                trades_executed_1h=self._statistics['trades_executed'],
                service_health=[
                    {
                        "service_name": "redis_client",
                        "status": "healthy" if self.redis_client.is_connected() else "unhealthy",
                        "uptime_seconds": uptime_seconds,
                        "last_activity": datetime.now(timezone.utc),
                        "error_count_1h": 0,
                        "performance_metrics": await self.redis_client.get_connection_info()
                    }
                ],
                trading_mode="PAPER",  # TODO: Get from engine config
                supported_chains=[1, 8453],  # TODO: Get from engine config
            )
            
            await self.redis_client.publish_to_django(message)
            self._statistics['messages_sent'] += 1
            
            self.logger.debug("Sent engine status update to Django")
            
        except Exception as e:
            self.logger.error(f"Failed to send engine status: {e}")
    
    async def send_alert(
        self, 
        alert_type: str, 
        severity: str, 
        title: str, 
        description: str,
        **kwargs
    ) -> None:
        """
        Send alert to Django.
        
        Args:
            alert_type: Type of alert
            severity: Alert severity level
            title: Alert title
            description: Alert description
            **kwargs: Additional alert metadata
        """
        try:
            message = AlertTriggered(
                source_service="engine",
                engine_id=self.engine_id,
                alert_id=create_correlation_id(),
                alert_type=alert_type,
                severity=severity,
                title=title,
                description=description,
                metadata=kwargs
            )
            
            await self.redis_client.publish_to_django(message)
            self._statistics['messages_sent'] += 1
            
            self.logger.warning(f"Sent alert to Django: {title}")
            
        except Exception as e:
            self.logger.error(f"Failed to send alert: {e}")
    
    # =========================================================================
    # DJANGO → ENGINE MESSAGE HANDLERS
    # =========================================================================
    
    async def _setup_django_subscriptions(self) -> None:
        """Set up subscriptions for messages from Django."""
        handlers = {
            REDIS_CHANNELS['comprehensive_risk_complete']: self._handle_comprehensive_risk_complete,
            REDIS_CHANNELS['trading_config_update']: self._handle_config_update,
            REDIS_CHANNELS['emergency_stop']: self._handle_emergency_stop,
        }
        
        await self.redis_client.setup_engine_subscriptions(handlers)
        self.logger.info("Set up Django subscriptions")
    
    async def _handle_comprehensive_risk_complete(self, message_data: dict) -> None:
        """
        Handle comprehensive risk assessment results from Django.
        
        Args:
            message_data: Message data from Django
        """
        try:
            self.logger.info(f"Received comprehensive risk result from Django: {message_data.get('token_address')}")
            self._statistics['messages_received'] += 1
            
            # Call engine callback if registered
            if self.on_comprehensive_risk_complete:
                await self.on_comprehensive_risk_complete(message_data)
            
        except Exception as e:
            self.logger.error(f"Error handling comprehensive risk result: {e}")
    
    async def _handle_config_update(self, message_data: dict) -> None:
        """
        Handle configuration updates from Django.
        
        Args:
            message_data: Configuration update message
        """
        try:
            self.logger.info(f"Received config update from Django: {message_data.get('config_type')}")
            self._statistics['messages_received'] += 1
            
            # Call engine callback if registered
            if self.on_config_update:
                await self.on_config_update(message_data)
            
        except Exception as e:
            self.logger.error(f"Error handling config update: {e}")
    
    async def _handle_emergency_stop(self, message_data: dict) -> None:
        """
        Handle emergency stop commands from Django.
        
        Args:
            message_data: Emergency stop message
        """
        try:
            self.logger.critical(f"Received emergency stop from Django: {message_data.get('reason')}")
            self._statistics['messages_received'] += 1
            
            # Call engine callback if registered
            if self.on_emergency_stop:
                await self.on_emergency_stop(message_data)
            
        except Exception as e:
            self.logger.error(f"Error handling emergency stop: {e}")
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def _get_engine_config(self) -> dict:
        """Get engine configuration for status reporting."""
        return {
            "engine_id": self.engine_id,
            "trading_mode": "PAPER",  # TODO: Get from engine config
            "supported_chains": [1, 8453],  # TODO: Get from engine config
            "discovery_enabled": True,
            "risk_timeout_ms": 2000,
            "max_position_size_usd": 1000,
        }
    
    def get_statistics(self) -> dict:
        """Get engine statistics."""
        return {
            **self._statistics,
            "uptime_seconds": int((datetime.now(timezone.utc) - self._startup_time).total_seconds()) if self._startup_time else 0,
            "status": self._engine_status,
            "connected": self.is_connected(),
        }
    
    async def health_check(self) -> dict:
        """Perform health check and return status."""
        return {
            "status": self._engine_status,
            "connected": self.is_connected(),
            "redis_info": await self.redis_client.get_connection_info(),
            "statistics": self.get_statistics(),
        }