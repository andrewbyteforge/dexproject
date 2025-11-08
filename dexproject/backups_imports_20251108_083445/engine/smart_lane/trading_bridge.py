"""
Smart Lane to Trading Integration Bridge - PHASE 5.1C COMPLETE

This module bridges the Smart Lane analysis system with the new risk-integrated
trading workflow. It monitors Smart Lane analysis results and triggers appropriate
trading actions based on the analysis recommendations.

NEW: Complete integration between Smart Lane intelligence and trading execution

File: dexproject/engine/smart_lane/trading_bridge.py
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass
from decimal import Decimal

# Import Smart Lane components
from . import SmartLaneAction, DecisionConfidence, SmartLaneAnalysis
from .pipeline import SmartLanePipeline

# Import Django integration
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    import django
    from django.conf import settings
    
    if not settings.configured:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
        django.setup()
    
    from trading.tasks import smart_lane_trading_workflow
    from trading.models import Strategy
    from django.contrib.auth.models import User
    
    DJANGO_AVAILABLE = True
    
except ImportError as e:
    logging.warning(f"Django not available for Smart Lane trading bridge: {e}")
    DJANGO_AVAILABLE = False
except Exception as e:
    logging.warning(f"Could not setup Django for Smart Lane trading bridge: {e}")
    DJANGO_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class TradingTrigger:
    """Configuration for when Smart Lane should trigger trades."""
    
    # Minimum confidence levels for trading actions
    min_confidence_buy: DecisionConfidence = DecisionConfidence.MEDIUM
    min_confidence_sell: DecisionConfidence = DecisionConfidence.LOW
    
    # Risk thresholds
    max_risk_score_for_buy: float = 0.6  # Maximum risk score to allow buys
    max_risk_score_for_sell: float = 0.9  # Maximum risk score to allow sells
    
    # Position sizing limits
    max_position_size_eth: Decimal = Decimal('0.1')  # Maximum position size
    min_position_size_eth: Decimal = Decimal('0.001')  # Minimum position size
    
    # Trading conditions
    require_user_approval: bool = False  # Whether to require manual approval
    enable_automated_trading: bool = True  # Whether to execute trades automatically
    
    # Filtering criteria
    min_liquidity_usd: float = 50000  # Minimum liquidity to consider trading
    min_volume_24h_usd: float = 10000  # Minimum 24h volume
    
    # Timing controls
    analysis_cooldown_seconds: int = 300  # Wait time between analyses of same token
    trading_cooldown_seconds: int = 600  # Wait time between trades of same token


class SmartLaneTradingBridge:
    """
    Integration bridge between Smart Lane analysis and trading execution.
    
    This class monitors Smart Lane analysis results and automatically triggers
    appropriate trading actions based on the analysis recommendations and
    configured trading triggers.
    """
    
    def __init__(
        self,
        pipeline: SmartLanePipeline,
        trading_trigger: TradingTrigger = None,
        default_user_id: Optional[int] = None,
        default_strategy_id: Optional[int] = None
    ):
        """
        Initialize the Smart Lane trading bridge.
        
        Args:
            pipeline: Smart Lane pipeline instance
            trading_trigger: Configuration for trading triggers
            default_user_id: Default user for automated trades
            default_strategy_id: Default strategy for automated trades
        """
        self.pipeline = pipeline
        self.trading_trigger = trading_trigger or TradingTrigger()
        self.default_user_id = default_user_id
        self.default_strategy_id = default_strategy_id
        
        # State tracking
        self.analysis_history: Dict[str, List[Dict[str, Any]]] = {}
        self.trading_history: Dict[str, List[Dict[str, Any]]] = {}
        self.cooldown_tracker: Dict[str, datetime] = {}
        
        # Performance metrics
        self.metrics = {
            'analyses_processed': 0,
            'trades_triggered': 0,
            'trades_successful': 0,
            'trades_failed': 0,
            'total_pnl': Decimal('0'),
            'last_activity': None,
            'errors': []
        }
        
        # Active monitoring
        self.is_monitoring = False
        self.monitoring_task: Optional[asyncio.Task] = None
        
        self.logger = logging.getLogger(f"{__name__}.SmartLaneTradingBridge")
        self.logger.info("Smart Lane Trading Bridge initialized")
    
    async def start_monitoring(self, check_interval_seconds: int = 10) -> None:
        """
        Start monitoring Smart Lane analyses for trading opportunities.
        
        Args:
            check_interval_seconds: How often to check for new analyses
        """
        if self.is_monitoring:
            self.logger.warning("Bridge is already monitoring")
            return
        
        self.is_monitoring = True
        self.monitoring_task = asyncio.create_task(
            self._monitoring_loop(check_interval_seconds)
        )
        
        self.logger.info(f"Started Smart Lane trading bridge monitoring (interval: {check_interval_seconds}s)")
    
    async def stop_monitoring(self) -> None:
        """Stop monitoring Smart Lane analyses."""
        self.is_monitoring = False
        
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Stopped Smart Lane trading bridge monitoring")
    
    async def _monitoring_loop(self, check_interval_seconds: int) -> None:
        """Main monitoring loop that checks for new analyses and triggers trades."""
        last_check = datetime.now(timezone.utc)
        
        while self.is_monitoring:
            try:
                # Get recent analyses from the pipeline
                # NOTE: This would normally use a shared queue or database
                # For now, we'll simulate by checking pipeline status
                
                current_time = datetime.now(timezone.utc)
                
                # Check for completed analyses since last check
                await self._check_for_new_analyses(last_check, current_time)
                
                # Update last check time
                last_check = current_time
                
                # Wait for next check
                await asyncio.sleep(check_interval_seconds)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                self.metrics['errors'].append({
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'error': str(e),
                    'context': 'monitoring_loop'
                })
                
                # Brief pause before continuing
                await asyncio.sleep(5)
    
    async def _check_for_new_analyses(self, since: datetime, until: datetime) -> None:
        """
        Check for new Smart Lane analyses and process them for trading opportunities.
        
        Args:
            since: Check for analyses since this time
            until: Check for analyses until this time
        """
        # In a real implementation, this would query a database or message queue
        # For now, we'll demonstrate the workflow with the pipeline's current state
        
        try:
            # Get pipeline metrics to see if there's new activity
            pipeline_metrics = getattr(self.pipeline, 'performance_metrics', {})
            
            # This is a simplified check - in production, you'd have proper event handling
            if pipeline_metrics.get('total_analyses', 0) > self.metrics['analyses_processed']:
                self.logger.info("Detected new Smart Lane analysis activity")
                
                # For demonstration, we'll trigger analysis for a sample token
                # In production, this would process actual completed analyses
                await self._simulate_analysis_processing()
        
        except Exception as e:
            self.logger.error(f"Error checking for new analyses: {e}")
    
    async def _simulate_analysis_processing(self) -> None:
        """
        Simulate processing a Smart Lane analysis result.
        
        NOTE: This is a demonstration implementation. In production, this would
        process actual analysis results from the Smart Lane pipeline.
        """
        # Sample analysis result for demonstration
        sample_analysis = {
            'token_address': '0x1234567890123456789012345678901234567890',
            'pair_address': '0x0987654321098765432109876543210987654321',
            'analysis_id': str(uuid.uuid4()),
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'action': SmartLaneAction.BUY,
            'confidence': DecisionConfidence.HIGH,
            'risk_score': 0.3,
            'position_size_recommendation': 0.05,
            'context': {
                'symbol': 'SAMPLE',
                'current_price': 1.25,
                'market_cap': 10000000,
                'liquidity_usd': 500000,
                'volume_24h': 100000
            },
            'reasoning': {
                'technical_signals': 'Strong upward momentum with volume confirmation',
                'risk_factors': 'Low risk token with good fundamentals',
                'market_conditions': 'Favorable market conditions for entry'
            }
        }
        
        # Process this analysis for potential trading
        await self.process_analysis_result(sample_analysis)
    
    async def process_analysis_result(self, analysis_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a Smart Lane analysis result and potentially trigger trading.
        
        Args:
            analysis_result: Complete analysis result from Smart Lane pipeline
            
        Returns:
            Processing result including any trading actions taken
        """
        start_time = time.time()
        token_address = analysis_result.get('token_address')
        pair_address = analysis_result.get('pair_address')
        
        self.logger.info(
            f"🧠 Processing Smart Lane analysis: {token_address[:10]}... "
            f"Action: {analysis_result.get('action')}, "
            f"Confidence: {analysis_result.get('confidence')}"
        )
        
        processing_result = {
            'analysis_id': analysis_result.get('analysis_id'),
            'token_address': token_address,
            'pair_address': pair_address,
            'processed_at': datetime.now(timezone.utc).isoformat(),
            'action_taken': 'none',
            'reason': '',
            'trading_task_id': None,
            'success': False
        }
        
        try:
            # Update metrics
            self.metrics['analyses_processed'] += 1
            self.metrics['last_activity'] = datetime.now(timezone.utc).isoformat()
            
            # Store analysis in history
            if token_address not in self.analysis_history:
                self.analysis_history[token_address] = []
            self.analysis_history[token_address].append(analysis_result)
            
            # Check if we should trade based on the analysis
            should_trade, trade_reason = self._should_execute_trade(analysis_result)
            
            if not should_trade:
                processing_result.update({
                    'action_taken': 'skipped',
                    'reason': trade_reason,
                    'success': True
                })
                self.logger.info(f"⏸️ Skipping trade: {trade_reason}")
                return processing_result
            
            # Check cooldown periods
            if self._is_in_cooldown(token_address):
                cooldown_reason = f"Token {token_address[:10]}... is in cooldown period"
                processing_result.update({
                    'action_taken': 'cooldown',
                    'reason': cooldown_reason,
                    'success': True
                })
                self.logger.info(f"⏳ {cooldown_reason}")
                return processing_result
            
            # Execute trading workflow
            trade_result = await self._execute_trading_workflow(analysis_result)
            
            if trade_result:
                processing_result.update({
                    'action_taken': 'trading_triggered',
                    'reason': f"Triggered {analysis_result.get('action')} based on Smart Lane analysis",
                    'trading_task_id': trade_result.get('task_id'),
                    'trading_result': trade_result,
                    'success': True
                })
                
                # Update cooldown
                self._update_cooldown(token_address)
                
                # Update metrics
                self.metrics['trades_triggered'] += 1
                
                self.logger.info(
                    f"✅ Trading workflow triggered: {trade_result.get('task_id')} "
                    f"for {token_address[:10]}..."
                )
            
            else:
                processing_result.update({
                    'action_taken': 'trading_failed',
                    'reason': 'Failed to trigger trading workflow',
                    'success': False
                })
                self.logger.error(f"❌ Failed to trigger trading workflow for {token_address[:10]}...")
            
            return processing_result
            
        except Exception as e:
            self.logger.error(f"Error processing analysis result: {e}")
            self.metrics['errors'].append({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': str(e),
                'context': 'process_analysis_result',
                'token_address': token_address
            })
            
            processing_result.update({
                'action_taken': 'error',
                'reason': f"Processing error: {str(e)}",
                'success': False
            })
            
            return processing_result
        
        finally:
            execution_time = time.time() - start_time
            self.logger.debug(f"Analysis processing completed in {execution_time:.3f}s")
    
    def _should_execute_trade(self, analysis_result: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Determine if a trade should be executed based on analysis result and trading triggers.
        
        Args:
            analysis_result: Smart Lane analysis result
            
        Returns:
            Tuple of (should_trade, reason)
        """
        action = analysis_result.get('action')
        confidence = analysis_result.get('confidence')
        risk_score = analysis_result.get('risk_score', 1.0)
        context = analysis_result.get('context', {})
        
        # Check if automated trading is enabled
        if not self.trading_trigger.enable_automated_trading:
            return False, "Automated trading is disabled"
        
        # Check if this action type is tradeable
        if action not in [SmartLaneAction.BUY, SmartLaneAction.PARTIAL_BUY, SmartLaneAction.SCALE_IN]:
            return False, f"Action {action} is not a tradeable action"
        
        # Check confidence level for buy actions
        if action in [SmartLaneAction.BUY, SmartLaneAction.PARTIAL_BUY, SmartLaneAction.SCALE_IN]:
            required_confidence = self.trading_trigger.min_confidence_buy
            if confidence.value < required_confidence.value:
                return False, f"Confidence {confidence} below required {required_confidence} for buy"
        
        # Check risk score
        if risk_score > self.trading_trigger.max_risk_score_for_buy:
            return False, f"Risk score {risk_score:.2f} exceeds maximum {self.trading_trigger.max_risk_score_for_buy}"
        
        # Check liquidity requirements
        liquidity = context.get('liquidity_usd', 0)
        if liquidity < self.trading_trigger.min_liquidity_usd:
            return False, f"Liquidity ${liquidity:,.0f} below minimum ${self.trading_trigger.min_liquidity_usd:,.0f}"
        
        # Check volume requirements
        volume_24h = context.get('volume_24h', 0)
        if volume_24h < self.trading_trigger.min_volume_24h_usd:
            return False, f"24h volume ${volume_24h:,.0f} below minimum ${self.trading_trigger.min_volume_24h_usd:,.0f}"
        
        # Check if user approval is required
        if self.trading_trigger.require_user_approval:
            return False, "User approval required for trading"
        
        # All checks passed
        return True, f"Analysis meets all trading criteria (action: {action}, confidence: {confidence}, risk: {risk_score:.2f})"
    
    def _is_in_cooldown(self, token_address: str) -> bool:
        """Check if a token is in cooldown period."""
        if token_address not in self.cooldown_tracker:
            return False
        
        last_activity = self.cooldown_tracker[token_address]
        cooldown_period = self.trading_trigger.analysis_cooldown_seconds
        
        return (datetime.now(timezone.utc) - last_activity).total_seconds() < cooldown_period
    
    def _update_cooldown(self, token_address: str) -> None:
        """Update cooldown period for a token."""
        self.cooldown_tracker[token_address] = datetime.now(timezone.utc)
    
    async def _execute_trading_workflow(self, analysis_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Execute the Smart Lane trading workflow.
        
        Args:
            analysis_result: Smart Lane analysis result
            
        Returns:
            Trading task result or None if failed
        """
        if not DJANGO_AVAILABLE:
            self.logger.error("Django not available - cannot execute trading workflow")
            return None
        
        try:
            token_address = analysis_result.get('token_address')
            pair_address = analysis_result.get('pair_address')
            action = analysis_result.get('action')
            
            # Prepare workflow parameters
            workflow_params = {
                'token_address': token_address,
                'pair_address': pair_address,
                'discovered_by': 'smart_lane',
                'user_id': self.default_user_id,
                'strategy_id': self.default_strategy_id,
                'analysis_context': {
                    'smart_lane_analysis': analysis_result,
                    'bridge_trigger_time': datetime.now(timezone.utc).isoformat(),
                    'action': action.value if hasattr(action, 'value') else str(action),
                    'confidence': analysis_result.get('confidence').value if hasattr(analysis_result.get('confidence'), 'value') else str(analysis_result.get('confidence')),
                    'risk_score': analysis_result.get('risk_score'),
                    'reasoning': analysis_result.get('reasoning')
                }
            }
            
            self.logger.info(f"🚀 Executing Smart Lane trading workflow for {token_address[:10]}...")
            
            # Trigger the Smart Lane trading workflow task
            task_result = smart_lane_trading_workflow.delay(**workflow_params)
            
            # Store task information
            trading_record = {
                'task_id': task_result.id,
                'token_address': token_address,
                'pair_address': pair_address,
                'action': str(action),
                'triggered_at': datetime.now(timezone.utc).isoformat(),
                'analysis_result': analysis_result,
                'workflow_params': workflow_params
            }
            
            # Store in trading history
            if token_address not in self.trading_history:
                self.trading_history[token_address] = []
            self.trading_history[token_address].append(trading_record)
            
            return {
                'task_id': task_result.id,
                'status': 'triggered',
                'trading_record': trading_record
            }
            
        except Exception as e:
            self.logger.error(f"Failed to execute trading workflow: {e}")
            return None
    
    def get_bridge_status(self) -> Dict[str, Any]:
        """Get comprehensive status of the trading bridge."""
        return {
            'is_monitoring': self.is_monitoring,
            'trading_trigger_config': {
                'automated_trading_enabled': self.trading_trigger.enable_automated_trading,
                'min_confidence_buy': str(self.trading_trigger.min_confidence_buy),
                'max_risk_score_buy': self.trading_trigger.max_risk_score_for_buy,
                'min_liquidity_usd': self.trading_trigger.min_liquidity_usd,
                'cooldown_seconds': self.trading_trigger.analysis_cooldown_seconds
            },
            'metrics': self.metrics.copy(),
            'tokens_tracked': len(self.analysis_history),
            'total_analyses': sum(len(analyses) for analyses in self.analysis_history.values()),
            'total_trades': sum(len(trades) for trades in self.trading_history.values()),
            'last_activity': self.metrics.get('last_activity'),
            'django_available': DJANGO_AVAILABLE
        }
    
    def get_token_history(self, token_address: str) -> Dict[str, Any]:
        """Get analysis and trading history for a specific token."""
        return {
            'token_address': token_address,
            'analyses': self.analysis_history.get(token_address, []),
            'trades': self.trading_history.get(token_address, []),
            'in_cooldown': self._is_in_cooldown(token_address),
            'cooldown_until': self.cooldown_tracker.get(token_address, {})
        }
    
    async def manual_trigger_analysis(
        self,
        token_address: str,
        pair_address: str,
        user_id: Optional[int] = None,
        strategy_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Manually trigger Smart Lane analysis and trading workflow for a token.
        
        Args:
            token_address: Token to analyze
            pair_address: Trading pair for the token
            user_id: User requesting the analysis
            strategy_id: Strategy to use for trading
            
        Returns:
            Result of the manual trigger
        """
        self.logger.info(f"🔍 Manual trigger: Smart Lane analysis for {token_address[:10]}...")
        
        try:
            # Run Smart Lane analysis
            analysis_result = await self.pipeline.analyze_token(
                token_address=token_address,
                pair_address=pair_address,
                context={
                    'symbol': 'MANUAL',
                    'manual_trigger': True,
                    'triggered_by_user': user_id
                }
            )
            
            if analysis_result:
                # Process the analysis result for trading
                processing_result = await self.process_analysis_result(analysis_result)
                
                return {
                    'success': True,
                    'analysis_result': analysis_result,
                    'processing_result': processing_result,
                    'message': f"Manual analysis completed for {token_address[:10]}..."
                }
            else:
                return {
                    'success': False,
                    'error': 'Smart Lane analysis failed',
                    'message': f"Analysis failed for {token_address[:10]}..."
                }
        
        except Exception as e:
            self.logger.error(f"Manual trigger failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': f"Manual trigger failed for {token_address[:10]}..."
            }


# =============================================================================
# BRIDGE FACTORY AND CONFIGURATION
# =============================================================================

def create_smart_lane_trading_bridge(
    pipeline: SmartLanePipeline,
    config_overrides: Optional[Dict[str, Any]] = None,
    default_user_id: Optional[int] = None,
    default_strategy_id: Optional[int] = None
) -> SmartLaneTradingBridge:
    """
    Factory function to create a configured Smart Lane trading bridge.
    
    Args:
        pipeline: Smart Lane pipeline instance
        config_overrides: Optional configuration overrides
        default_user_id: Default user for automated trades
        default_strategy_id: Default strategy for automated trades
        
    Returns:
        Configured SmartLaneTradingBridge instance
    """
    # Create trading trigger configuration
    trigger_config = TradingTrigger()
    
    # Apply any configuration overrides
    if config_overrides:
        for key, value in config_overrides.items():
            if hasattr(trigger_config, key):
                setattr(trigger_config, key, value)
    
    # Create and return the bridge
    bridge = SmartLaneTradingBridge(
        pipeline=pipeline,
        trading_trigger=trigger_config,
        default_user_id=default_user_id,
        default_strategy_id=default_strategy_id
    )
    
    logger.info("Smart Lane trading bridge created successfully")
    return bridge


# =============================================================================
# EXAMPLE USAGE AND TESTING
# =============================================================================

async def example_bridge_usage():
    """Example usage of the Smart Lane trading bridge."""
    try:
        # This would normally be imported from the Smart Lane module
        from .pipeline import SmartLanePipeline
        from . import SmartLaneConfig
        
        # Create Smart Lane pipeline
        config = SmartLaneConfig()
        pipeline = SmartLanePipeline(config=config, chain_id=1)
        
        # Create trading bridge with conservative settings
        conservative_config = {
            'min_confidence_buy': DecisionConfidence.HIGH,
            'max_risk_score_for_buy': 0.4,
            'min_liquidity_usd': 100000,
            'enable_automated_trading': False,  # Start with manual approval
            'require_user_approval': True
        }
        
        bridge = create_smart_lane_trading_bridge(
            pipeline=pipeline,
            config_overrides=conservative_config,
            default_user_id=1,  # Demo user
            default_strategy_id=1  # Conservative strategy
        )
        
        # Start monitoring
        await bridge.start_monitoring(check_interval_seconds=30)
        
        # Let it run for a bit
        await asyncio.sleep(60)
        
        # Get status
        status = bridge.get_bridge_status()
        print(f"Bridge Status: {status}")
        
        # Stop monitoring
        await bridge.stop_monitoring()
        
    except Exception as e:
        logger.error(f"Example usage failed: {e}")


if __name__ == "__main__":
    # Run example usage
    asyncio.run(example_bridge_usage())