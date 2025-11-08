"""
Enhanced Main Trading Engine with Redis Communication and Django SSOT

Coordinates all engine components and provides the main execution loop.
Now uses Django Chain/DEX models as single source of truth for configuration.
"""

import asyncio
import logging
import signal
import sys
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import time

from .config import get_config, EngineConfig  # Updated import
from .utils import setup_logging
from .discovery import MultiChainDiscoveryManager, NewPairEvent
from .risk import MultiChainRiskManager, RiskAssessmentResult
from .execution import MultiChainExecutionManager, TradeDecision, TradeExecution
from .portfolio import GlobalPortfolioManager
from .communications import DjangoBridge
from . import EngineStatus

logger = logging.getLogger(__name__)


class TradingEngine:
    """
    Enhanced main trading engine with Django integration and configuration SSOT.
    
    Now uses Django Chain/DEX models as the single source of truth for chain
    configuration, eliminating duplication and ensuring consistency.
    """
    
    def __init__(self, engine_id: str = None):
        """
        Initialize the enhanced trading engine.
        
        Args:
            engine_id: Unique identifier for this engine instance
        """
        self.engine_id = engine_id or f"engine-{int(time.time())}"
        self.status = EngineStatus.STOPPED
        self.start_time: Optional[datetime] = None
        self.shutdown_requested = False
        
        # Configuration will be loaded asynchronously
        self.config: Optional[EngineConfig] = None
        
        # Subsystems (initialized after config loads)
        self.discovery_manager = None
        self.risk_manager = None
        self.execution_manager = None
        self.portfolio_manager = None
        self.django_bridge = None
        
        # Statistics
        self.total_pairs_discovered = 0
        self.total_assessments_completed = 0
        self.total_trades_executed = 0
        
        # Django integration tracking
        self._pending_comprehensive_assessments: Dict[str, RiskAssessmentResult] = {}
        self._last_django_sync = None
        
        self.logger = logging.getLogger('engine.main')
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.shutdown_requested = True
    
    async def start(self) -> None:
        """Start the enhanced trading engine with Django SSOT configuration."""
        self.logger.info("=" * 80)
        self.logger.info("🚀 STARTING ENHANCED DEX TRADING ENGINE (Django SSOT)")
        self.logger.info("=" * 80)
        
        try:
            self.status = EngineStatus.STARTING
            self.start_time = datetime.now(timezone.utc)
            
            # Step 1: Load configuration from Django models
            self.logger.info("📥 Loading configuration from Django models...")
            self.config = await get_config()
            
            # Log configuration
            self.logger.info(f"Engine ID: {self.engine_id}")
            self.logger.info(f"Trading Mode: {self.config.trading_mode}")
            self.logger.info(f"Target Chains: {list(self.config.chains.keys())}")
            self.logger.info(f"Discovery Enabled: {self.config.discovery_enabled}")
            self.logger.info(f"Django Integration: ✅ Enabled")
            
            # Log chain details from Django
            for chain_id, chain_config in self.config.chains.items():
                self.logger.info(f"  📍 {chain_config.name} (ID: {chain_id}): {len(chain_config.rpc_providers)} providers")
            
            # Step 2: Initialize subsystems with Django-sourced config
            await self._initialize_subsystems()
            
            # Step 3: Start Django communication bridge
            self.logger.info("🔗 Initializing Django communication bridge...")
            self.django_bridge = DjangoBridge(self.config.redis_url, self.engine_id)
            await self.django_bridge.initialize()
            
            # Set up Django bridge callbacks
            self.django_bridge.on_comprehensive_risk_complete = self._on_comprehensive_risk_complete
            self.django_bridge.on_config_update = self._on_config_update
            self.django_bridge.on_emergency_stop = self._on_emergency_stop
            
            self.logger.info("✅ Django bridge initialized")
            
            # Step 4: Start all subsystems
            await self._start_subsystems()
            
            self.status = EngineStatus.RUNNING
            self.logger.info("✅ Enhanced trading engine started successfully with Django SSOT")
            
            # Send startup notification to Django
            await self._send_startup_notification()
            
            # Run main event loop
            await self._run_main_loop()
            
        except Exception as e:
            self.logger.error(f"❌ Failed to start trading engine: {e}")
            self.status = EngineStatus.ERROR
            
            # Send error alert to Django
            if self.django_bridge and self.django_bridge.is_connected():
                await self.django_bridge.send_alert(
                    alert_type="engine_startup_failed",
                    severity="critical",
                    title="Engine Startup Failed",
                    description=f"Trading engine failed to start: {str(e)}",
                    error=str(e)
                )
            raise
        finally:
            await self.stop()
    
    async def _initialize_subsystems(self) -> None:
        """Initialize subsystems with Django-sourced configuration."""
        self.logger.info("🔧 Initializing subsystems with Django configuration...")
        
        # Initialize subsystems with Django-loaded config
        self.discovery_manager = MultiChainDiscoveryManager(self._on_new_pair_discovered)
        self.risk_manager = MultiChainRiskManager(self._on_risk_assessment_complete)
        self.execution_manager = MultiChainExecutionManager()
        self.portfolio_manager = GlobalPortfolioManager()
        
        self.logger.info("✅ Subsystems initialized with Django configuration")
    
    async def _start_subsystems(self) -> None:
        """Start all engine subsystems."""
        self.logger.info("Starting subsystems...")
        
        # Start portfolio manager first
        await self.portfolio_manager.start()
        self.logger.info("✅ Portfolio manager started")
        
        # Start execution manager
        await self.execution_manager.start()
        self.logger.info("✅ Execution manager started")
        
        # Start discovery and risk in parallel
        discovery_task = asyncio.create_task(self._start_discovery())
        
        # Wait for discovery to be ready before proceeding
        await asyncio.sleep(2)
        
        # Start periodic Django sync
        if self.django_bridge and self.django_bridge.is_connected():
            asyncio.create_task(self._periodic_django_sync())
        
        self.logger.info("✅ All subsystems started")
    
    async def _start_discovery(self) -> None:
        """Start discovery service."""
        try:
            self.logger.info("🔍 Starting discovery services...")
            await self.discovery_manager.start()
        except Exception as e:
    
    # =========================================================================
    # CONFIGURATION UPDATE HANDLERS (NEW: Handle Django config changes)
    # =========================================================================
    
    async def _on_config_update(self, message_data: dict) -> None:
        """
        Handle configuration updates from Django.
        
        Args:
            message_data: Configuration update message
        """
        try:
            config_type = message_data.get('config_type')
            self.logger.info(f"📥 Config update from Django: {config_type}")
            
            if config_type == 'chain_config':
                # Refresh chain configurations from Django
                await self.config.refresh_chain_configs()
                self.logger.info("✅ Chain configurations refreshed from Django")
                
            elif config_type == 'risk_profile':
                # Update risk management configuration
                await self._update_risk_configuration(message_data.get('config_data', {}))
            elif config_type == 'trading_limits':
                # Update portfolio limits
                await self._update_trading_limits(message_data.get('config_data', {}))
            else:
                self.logger.warning(f"Unknown config update type: {config_type}")
                
        except Exception as e:
            self.logger.error(f"Error handling config update: {e}")
    
    async def _on_emergency_stop(self, message_data: dict) -> None:
        """
        Handle emergency stop commands from Django.
        
        Args:
            message_data: Emergency stop message
        """
        try:
            reason = message_data.get('reason', 'Unknown')
            stop_trading = message_data.get('stop_trading', True)
            close_positions = message_data.get('close_positions', False)
            
            self.logger.critical(f"🚨 EMERGENCY STOP from Django: {reason}")
            
            if stop_trading:
                # Stop all trading activity
                self.status = EngineStatus.PAUSED
                await self.execution_manager.pause_trading()
                self.logger.critical("🛑 Trading paused due to emergency stop")
            
            if close_positions:
                # Close all open positions
                await self.execution_manager.emergency_close_all_positions()
                self.logger.critical("🔴 All positions closed due to emergency stop")
            
            # Send acknowledgment back to Django
            await self.django_bridge.send_alert(
                alert_type="emergency_stop_acknowledged",
                severity="critical",
                title="Emergency Stop Acknowledged",
                description=f"Engine has processed emergency stop: {reason}",
                reason=reason,
                actions_taken={
                    "trading_stopped": stop_trading,
                    "positions_closed": close_positions
                }
            )
            
        except Exception as e:
            self.logger.error(f"Error handling emergency stop: {e}")
    
    # =========================================================================
    # HELPER METHODS (Enhanced with Django config awareness)
    # =========================================================================
    
    def _create_trading_decision(self, assessment: RiskAssessmentResult) -> TradeDecision:
        """Create a trading decision from fast risk assessment."""
        return TradeDecision(
            pair_address=assessment.pair_event.pair_address,
            chain_id=assessment.pair_event.chain_id,
            token_address=assessment.pair_event.token0_address,
            token_symbol=assessment.pair_event.token0_symbol,
            action="BUY" if assessment.is_tradeable else "SKIP",
            confidence_score=100 - assessment.overall_risk_score,
            position_size_usd=self.config.max_position_size_usd * 0.1,  # Conservative 10% of max
            max_slippage_percent=self.config.default_slippage_percent,
            risk_assessment=assessment
        )
    
    def _create_enhanced_trading_decision(
        self, 
        fast_assessment: RiskAssessmentResult, 
        comprehensive_data: dict
    ) -> TradeDecision:
        """Create enhanced trading decision with both fast and comprehensive risk data."""
        comprehensive_score = comprehensive_data.get('overall_score', 50)
        is_tradeable = comprehensive_data.get('is_tradeable', False)
        
        # Combine fast and comprehensive scores (weighted average)
        combined_score = (fast_assessment.overall_risk_score * 0.3 + comprehensive_score * 0.7)
        
        return TradeDecision(
            pair_address=fast_assessment.pair_event.pair_address,
            chain_id=fast_assessment.pair_event.chain_id,
            token_address=fast_assessment.pair_event.token0_address,
            token_symbol=fast_assessment.pair_event.token0_symbol,
            action="BUY" if is_tradeable else "SKIP",
            confidence_score=100 - combined_score,
            position_size_usd=comprehensive_data.get('recommended_position_size_usd', self.config.max_position_size_usd * 0.1),
            max_slippage_percent=comprehensive_data.get('max_slippage_percent', self.config.default_slippage_percent),
            risk_assessment=fast_assessment
        )
    
    async def _update_risk_configuration(self, config_data: dict) -> None:
        """Update risk management configuration."""
        try:
            # Update risk manager with new configuration
            if hasattr(self.risk_manager, 'update_configuration'):
                await self.risk_manager.update_configuration(config_data)
                self.logger.info("✅ Risk configuration updated")
            else:
                self.logger.warning("Risk manager does not support configuration updates")
        except Exception as e:
            self.logger.error(f"Failed to update risk configuration: {e}")
    
    async def _update_trading_limits(self, config_data: dict) -> None:
        """Update trading limits configuration."""
        try:
            # Update portfolio manager with new limits
            if hasattr(self.portfolio_manager, 'update_limits'):
                await self.portfolio_manager.update_limits(config_data)
                self.logger.info("✅ Trading limits updated")
            else:
                self.logger.warning("Portfolio manager does not support limit updates")
        except Exception as e:
            self.logger.error(f"Failed to update trading limits: {e}")
    
    async def _send_startup_notification(self) -> None:
        """Send startup notification to Django."""
        await self.django_bridge.send_alert(
            alert_type="engine_startup",
            severity="info",
            title="Trading Engine Started",
            description=f"Engine {self.engine_id} started with Django SSOT configuration",
            engine_config=self.django_bridge._get_engine_config(),
            chains_loaded=list(self.config.chains.keys())
        )
    
    async def _periodic_django_sync(self) -> None:
        """Periodic synchronization with Django."""
        while self.status == EngineStatus.RUNNING and not self.shutdown_requested:
            try:
                # Send engine status update every minute
                await self.django_bridge.send_engine_status()
                self._last_django_sync = datetime.now(timezone.utc)
                
                # Wait 60 seconds before next sync
                await asyncio.sleep(60)
                
            except Exception as e:
                self.logger.error(f"Error in periodic Django sync: {e}")
                await asyncio.sleep(30)  # Shorter retry interval on error
    
    # =========================================================================
    # ENHANCED LIFECYCLE METHODS (with Django SSOT and cleanup)
    # =========================================================================
    
    async def stop(self) -> None:
        """Stop the trading engine gracefully (enhanced with Django notification)."""
        if self.status == EngineStatus.STOPPED:
            return
        
        self.logger.info("🛑 Stopping enhanced trading engine...")
        self.status = EngineStatus.STOPPING
        
        try:
            # Notify Django of shutdown
            if self.django_bridge and self.django_bridge.is_connected():
                await self.django_bridge.send_alert(
                    alert_type="engine_shutdown",
                    severity="info",
                    title="Trading Engine Shutting Down",
                    description=f"Engine {self.engine_id} is shutting down gracefully",
                    final_statistics=self.get_statistics()
                )
            
            # Stop all subsystems in reverse order
            if self.discovery_manager:
                await self.discovery_manager.stop()
                self.logger.info("✅ Discovery manager stopped")
            
            if self.execution_manager:
                await self.execution_manager.stop()
                self.logger.info("✅ Execution manager stopped")
            
            if self.portfolio_manager:
                await self.portfolio_manager.stop()
                self.logger.info("✅ Portfolio manager stopped")
            
            # Stop Django bridge
            if self.django_bridge and self.django_bridge.is_connected():
                await self.django_bridge.shutdown()
                self.logger.info("✅ Django bridge stopped")
            
            # Shutdown configuration
            if self.config:
                await self.config.shutdown()
                self.logger.info("✅ Configuration shutdown complete")
            
            # Log final statistics
            uptime = datetime.now(timezone.utc) - self.start_time if self.start_time else None
            
            self.logger.info("=" * 80)
            self.logger.info("📈 FINAL STATISTICS")
            self.logger.info("=" * 80)
            self.logger.info(f"Engine ID: {self.engine_id}")
            self.logger.info(f"Total Runtime: {uptime}")
            self.logger.info(f"Pairs Discovered: {self.total_pairs_discovered}")
            self.logger.info(f"Risk Assessments: {self.total_assessments_completed}")
            self.logger.info(f"Trades Executed: {self.total_trades_executed}")
            
            # Django communication statistics
            if hasattr(self.django_bridge, 'get_statistics'):
                django_stats = self.django_bridge.get_statistics()
                self.logger.info(f"Messages Sent to Django: {django_stats.get('messages_sent', 0)}")
                self.logger.info(f"Messages Received from Django: {django_stats.get('messages_received', 0)}")
            
            if self.portfolio_manager:
                portfolio_summary = self.portfolio_manager.get_portfolio_summary()
                global_portfolio = portfolio_summary.get('global_portfolio', {})
                self.logger.info(f"Final Portfolio Value: ${global_portfolio.get('total_value', 0):,.2f}")
                self.logger.info(f"Total PnL: ${global_portfolio.get('total_pnl', 0):,.2f}")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
        finally:
            self.status = EngineStatus.STOPPED
            self.logger.info("✅ Enhanced trading engine stopped")
    
    async def get_comprehensive_status(self) -> Dict[str, Any]:
        """Get comprehensive status from all subsystems (enhanced with Django SSOT info)."""
        try:
            status = {
                "engine": {
                    "engine_id": self.engine_id,
                    "status": self.status,
                    "start_time": self.start_time.isoformat() if self.start_time else None,
                    "django_ssot": True,  # Indicates Django is SSOT for config
                },
                "statistics": {
                    "pairs_discovered": self.total_pairs_discovered,
                    "assessments_completed": self.total_assessments_completed,
                    "trades_executed": self.total_trades_executed
                }
            }
            
            # Add uptime
            if self.start_time:
                uptime_seconds = int((datetime.now(timezone.utc) - self.start_time).total_seconds())
                status["engine"]["uptime_seconds"] = uptime_seconds
            
            # Add configuration info
            if self.config:
                status["configuration"] = {
                    "trading_mode": self.config.trading_mode,
                    "target_chains": list(self.config.chains.keys()),
                    "chain_details": {
                        chain_id: {
                            "name": config.name,
                            "provider_count": len(config.rpc_providers),
                            "block_time_ms": config.block_time_ms,
                        }
                        for chain_id, config in self.config.chains.items()
                    }
                }
            
            # Get subsystem status
            if self.discovery_manager:
                status["subsystems"] = {"discovery": await self.discovery_manager.get_status()}
            if self.risk_manager:
                status["subsystems"]["risk"] = await self.risk_manager.get_status()
            if self.execution_manager:
                status["subsystems"]["execution"] = await self.execution_manager.get_status()
            if self.portfolio_manager:
                status["subsystems"]["portfolio"] = await self.portfolio_manager.get_status()
            
            # Add Django integration status
            if self.django_bridge and self.django_bridge.is_connected():
                status["django_integration"] = await self.django_bridge.health_check()
                status["pending_assessments"] = len(self._pending_comprehensive_assessments)
                status["last_django_sync"] = self._last_django_sync.isoformat() if self._last_django_sync else None
            else:
                status["django_integration"] = {"status": "disconnected", "reason": "Bridge not initialized or disconnected"}
            
            return status
            
        except Exception as e:
            self.logger.error(f"Error getting comprehensive status: {e}")
            return {"error": str(e)}
    
    async def _log_engine_status(self) -> None:
        """Log comprehensive engine status (enhanced with Django SSOT info)."""
        try:
            # Calculate uptime
            uptime = datetime.now(timezone.utc) - self.start_time if self.start_time else None
            
            self.logger.info("=" * 80)
            self.logger.info("📊 ENHANCED ENGINE STATUS REPORT (Django SSOT)")
            self.logger.info("=" * 80)
            self.logger.info(f"Engine ID: {self.engine_id}")
            self.logger.info(f"Status: {self.status}")
            self.logger.info(f"Uptime: {uptime}")
            self.logger.info(f"Pairs Discovered: {self.total_pairs_discovered}")
            self.logger.info(f"Risk Assessments: {self.total_assessments_completed}")
            self.logger.info(f"Trades Executed: {self.total_trades_executed}")
            
            # Configuration from Django
            if self.config and self.config.chains:
                self.logger.info(f"Chains Loaded from Django: {len(self.config.chains)}")
                for chain_id, chain_config in self.config.chains.items():
                    self.logger.info(f"  📍 {chain_config.name} (ID: {chain_id}): {len(chain_config.rpc_providers)} providers")
            
            # Django integration status
            if self.django_bridge and self.django_bridge.is_connected():
                django_stats = self.django_bridge.get_statistics()
                self.logger.info(f"Django Messages Sent: {django_stats.get('messages_sent', 0)}")
                self.logger.info(f"Django Messages Received: {django_stats.get('messages_received', 0)}")
                self.logger.info(f"Pending Comprehensive Assessments: {len(self._pending_comprehensive_assessments)}")
            else:
                self.logger.warning("Django Integration: ❌ Disconnected")
            
            # Portfolio summary
            if self.portfolio_manager:
                portfolio_status = await self.portfolio_manager.get_status()
                portfolio_summary = portfolio_status.get('portfolio_summary', {})
                global_portfolio = portfolio_summary.get('global_portfolio', {})
                
                self.logger.info(f"Portfolio Value: ${global_portfolio.get('total_value', 0):,.2f}")
                self.logger.info(f"Available Capital: ${global_portfolio.get('available_capital', 0):,.2f}")
                self.logger.info(f"Daily PnL: ${global_portfolio.get('daily_pnl', 0):,.2f}")
                
                # Trading status
                trading_status = portfolio_summary.get('trading_status', {})
                can_trade = trading_status.get('can_trade', False)
                self.logger.info(f"Can Trade: {'✅' if can_trade else '❌'}")
                
                if not can_trade:
                    restrictions = trading_status.get('restrictions', [])
                    self.logger.warning(f"Trading Restrictions: {'; '.join(restrictions)}")
            
            self.logger.info("=" * 80)
            
        except Exception as e:
            self.logger.error(f"Error logging engine status: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get engine statistics for reporting (enhanced with Django info)."""
        stats = {
            "engine_id": self.engine_id,
            "uptime_seconds": int((datetime.now(timezone.utc) - self.start_time).total_seconds()) if self.start_time else 0,
            "pairs_discovered": self.total_pairs_discovered,
            "assessments_completed": self.total_assessments_completed,
            "trades_executed": self.total_trades_executed,
            "status": self.status,
            "django_ssot": True,  # Indicates using Django as SSOT
        }
        
        # Add configuration info
        if self.config:
            stats.update({
                "trading_mode": self.config.trading_mode,
                "chains_loaded": list(self.config.chains.keys()),
                "total_rpc_providers": sum(len(c.rpc_providers) for c in self.config.chains.values()),
            })
        
        # Add Django statistics if available
        if self.django_bridge and self.django_bridge.is_connected():
            django_stats = self.django_bridge.get_statistics()
            stats.update({
                "django_messages_sent": django_stats.get('messages_sent', 0),
                "django_messages_received": django_stats.get('messages_received', 0),
                "django_connected": True,
                "pending_comprehensive_assessments": len(self._pending_comprehensive_assessments),
            })
        else:
            stats["django_connected"] = False
        
        return stats


async def main():
    """Main entry point for the enhanced trading engine with Django SSOT."""
    # Set up logging
    setup_logging()
    
    # Create and start the enhanced trading engine
    engine = TradingEngine()
    
    try:
        await engine.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Engine crashed: {e}")
        sys.exit(1)
    finally:
        await engine.stop()


if __name__ == "__main__":
    asyncio.run(main()) Failed to start trading engine: {e}")
            self.status = EngineStatus.ERROR
            
            # NEW: Send error alert to Django
            if self.django_bridge.is_connected():
                await self.django_bridge.send_alert(
                    alert_type="engine_startup_failed",
                    severity="critical",
                    title="Engine Startup Failed",
                    description=f"Trading engine failed to start: {str(e)}",
                    error=str(e)
                )
            raise
        finally:
            await self.stop()
    
    async def _start_subsystems(self) -> None:
        """Start all engine subsystems (your existing code enhanced)."""
        self.logger.info("Starting subsystems...")
        
        # Start portfolio manager first (your existing order)
        await self.portfolio_manager.start()
        self.logger.info("✅ Portfolio manager started")
        
        # Start execution manager
        await self.execution_manager.start()
        self.logger.info("✅ Execution manager started")
        
        # Start discovery and risk in parallel (your existing code)
        discovery_task = asyncio.create_task(self._start_discovery())
        
        # Wait for discovery to be ready before proceeding
        await asyncio.sleep(2)
        
        # NEW: Start periodic Django sync
        if self.django_bridge.is_connected():
            asyncio.create_task(self._periodic_django_sync())
        
        self.logger.info("✅ All subsystems started")
    
    async def _start_discovery(self) -> None:
        """Start discovery service (your existing code)."""
        try:
            self.logger.info("🔍 Starting discovery services...")
            await self.discovery_manager.start()
        except Exception as e:
            self.logger.error(f"Discovery service error: {e}")
            self.status = EngineStatus.ERROR
    
    async def _run_main_loop(self) -> None:
        """Run the enhanced main engine loop."""
        self.logger.info("🔄 Entering enhanced main event loop...")
        
        last_status_log = time.time()
        last_portfolio_update = time.time()
        
        while not self.shutdown_requested and self.status == EngineStatus.RUNNING:
            try:
                # Update portfolio state every 30 seconds (your existing code)
                if time.time() - last_portfolio_update > 30:
                    await self._update_portfolio_state()
                    last_portfolio_update = time.time()
                
                # Log status every 5 minutes (your existing code)
                if time.time() - last_status_log > 300:
                    await self._log_engine_status()
                    last_status_log = time.time()
                
                # Check for emergency conditions (your existing code)
                await self._check_emergency_conditions()
                
                # Sleep briefly to prevent busy waiting
                await asyncio.sleep(1)
                
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")
                
                # NEW: Send error alert to Django
                if self.django_bridge.is_connected():
                    await self.django_bridge.send_alert(
                        alert_type="main_loop_error",
                        severity="high",
                        title="Main Loop Error",
                        description=f"Error in main engine loop: {str(e)}",
                        error=str(e)
                    )
                
                await asyncio.sleep(5)
    
    async def _update_portfolio_state(self) -> None:
        """Update global portfolio state from all chains (your existing code)."""
        try:
            # Get portfolio states from all execution engines
            execution_status = await self.execution_manager.get_status()
            chain_portfolios = {}
            
            for chain_id, engine_status in execution_status.get('engines', {}).items():
                chain_portfolios[int(chain_id)] = engine_status.get('portfolio', {})
            
            # Update global portfolio manager
            await self.portfolio_manager.update_portfolio_state(chain_portfolios)
            
        except Exception as e:
            self.logger.error(f"Error updating portfolio state: {e}")
    
    async def _check_emergency_conditions(self) -> None:
        """Check for emergency conditions that require immediate action (your existing code enhanced)."""
        try:
            # Your existing emergency condition checks...
            portfolio_status = await self.portfolio_manager.get_status()
            
            # Check for circuit breaker conditions
            portfolio_summary = portfolio_status.get('portfolio_summary', {})
            trading_status = portfolio_summary.get('trading_status', {})
            
            if not trading_status.get('can_trade', True):
                restrictions = trading_status.get('restrictions', [])
                self.logger.warning(f"Trading restrictions detected: {restrictions}")
                
                # NEW: Send alert to Django
                if self.django_bridge.is_connected():
                    await self.django_bridge.send_alert(
                        alert_type="trading_restricted",
                        severity="medium",
                        title="Trading Restrictions Active",
                        description=f"Trading is currently restricted: {'; '.join(restrictions)}",
                        restrictions=restrictions
                    )
            
        except Exception as e:
            self.logger.error(f"Error checking emergency conditions: {e}")
    
    # =========================================================================
    # ENHANCED EVENT HANDLERS (your existing code + Django integration)
    # =========================================================================
    
    async def _on_new_pair_discovered(self, pair_event: NewPairEvent) -> None:
        """Handle new pair discovery event (enhanced with Django communication)."""
        self.total_pairs_discovered += 1
        
        self.logger.info(
            f"🔍 New pair discovered: {pair_event.token0_symbol}/{pair_event.token1_symbol} "
            f"on {config.chains[pair_event.chain_id].name} "
            f"(Fee: {pair_event.fee_tier/10000:.2f}%)"
        )
        
        # NEW: Send to Django for comprehensive risk assessment
        correlation_id = None
        if self.django_bridge.is_connected():
            try:
                correlation_id = await self.django_bridge.send_pair_discovered(pair_event)
                self.logger.info(f"📤 Sent pair discovery to Django (correlation: {correlation_id})")
            except Exception as e:
                self.logger.error(f"Failed to send pair discovery to Django: {e}")
        
        # Send to fast risk assessment (your existing code)
        try:
            await self.risk_manager.assess_pair(pair_event)
        except Exception as e:
            self.logger.error(f"Error sending pair to risk assessment: {e}")
    
    async def _on_risk_assessment_complete(self, assessment: RiskAssessmentResult) -> None:
        """Handle completed fast risk assessment (enhanced with Django communication)."""
        self.total_assessments_completed += 1
        
        pair_event = assessment.pair_event
        
        self.logger.info(
            f"🎯 Fast risk assessment complete: {pair_event.token0_symbol}/{pair_event.token1_symbol} "
            f"Score: {assessment.overall_risk_score:.1f} "
            f"Level: {assessment.risk_level} "
            f"Tradeable: {'✅' if assessment.is_tradeable else '❌'}"
        )
        
        # NEW: Send fast risk results to Django
        if self.django_bridge.is_connected():
            try:
                await self.django_bridge.send_fast_risk_complete(assessment)
                self.logger.info(f"📤 Sent fast risk results to Django")
                
                # Store assessment for when comprehensive results come back
                self._pending_comprehensive_assessments[pair_event.pair_address] = assessment
            except Exception as e:
                self.logger.error(f"Failed to send fast risk results to Django: {e}")
        
        # For now, continue with engine-only decision if critically unsafe
        if assessment.is_tradeable and assessment.overall_risk_score < 80:  # High threshold for autonomous action
            try:
                # Create trading decision
                decision = self._create_trading_decision(assessment)
                
                # NEW: Send decision to Django
                if self.django_bridge.is_connected():
                    await self.django_bridge.send_trading_decision(decision)
                
                # Execute trade (your existing code)
                await self.execution_manager.process_risk_assessment(assessment)
                self.total_trades_executed += 1
                
            except Exception as e:
                self.logger.error(f"Error processing risk assessment: {e}")
        else:
            if assessment.is_tradeable:
                self.logger.info(f"Waiting for comprehensive risk assessment before trading (score: {assessment.overall_risk_score})")
            else:
                self.logger.info(f"Skipping execution due to blocking issues: {assessment.blocking_issues}")
    
    # =========================================================================
    # NEW: DJANGO MESSAGE HANDLERS
    # =========================================================================
    
    async def _on_comprehensive_risk_complete(self, message_data: dict) -> None:
        """
        Handle comprehensive risk assessment results from Django.
        
        Args:
            message_data: Comprehensive risk assessment from Django
        """
        try:
            pair_address = message_data.get('pair_address')
            token_address = message_data.get('token_address')
            is_tradeable = message_data.get('is_tradeable', False)
            overall_score = message_data.get('overall_score', 100)
            
            self.logger.info(
                f"📥 Comprehensive risk complete from Django: {token_address} "
                f"Score: {overall_score} Tradeable: {'✅' if is_tradeable else '❌'}"
            )
            
            # Get the original fast assessment
            fast_assessment = self._pending_comprehensive_assessments.pop(pair_address, None)
            
            if fast_assessment and is_tradeable:
                # Create enhanced trading decision with both fast and comprehensive results
                decision = self._create_enhanced_trading_decision(fast_assessment, message_data)
                
                # Send decision to Django
                await self.django_bridge.send_trading_decision(decision)
                
                # Execute the trade
                await self.execution_manager.process_risk_assessment(fast_assessment)
                self.total_trades_executed += 1
                
                self.logger.info(f"✅ Executed trade based on comprehensive risk assessment")
            else:
                self.logger.info(f"❌ Skipping trade based on comprehensive risk assessment")
                
        except Exception as e:
            self.logger.error(f"Error handling comprehensive risk result: {e}")
    
    async def _on_config_update(self, message_data: dict) -> None:
        """
        Handle configuration updates from Django.
        
        Args:
            message_data: Configuration update message
        """
        try:
            config_type = message_data.get('config_type')
            self.logger.info(f"📥 Config update from Django: {config_type}")
            
            # Handle different types of config updates
            if config_type == 'risk_profile':
                # Update risk management configuration
                await self._update_risk_configuration(message_data.get('config_data', {}))
            elif config_type == 'trading_limits':
                # Update portfolio limits
                await self._update_trading_limits(message_data.get('config_data', {}))
            else:
                self.logger.warning(f"Unknown config update type: {config_type}")
                
        except Exception as e:
            self.logger.error(f"Error handling config update: {e}")
    
    async def _on_emergency_stop(self, message_data: dict) -> None:
        """
        Handle emergency stop commands from Django.
        
        Args:
            message_data: Emergency stop message
        """
        try:
            reason = message_data.get('reason', 'Unknown')
            stop_trading = message_data.get('stop_trading', True)
            close_positions = message_data.get('close_positions', False)
            
            self.logger.critical(f"🚨 EMERGENCY STOP from Django: {reason}")
            
            if stop_trading:
                # Stop all trading activity
                self.status = EngineStatus.PAUSED
                await self.execution_manager.pause_trading()
                self.logger.critical("🛑 Trading paused due to emergency stop")
            
            if close_positions:
                # Close all open positions
                await self.execution_manager.emergency_close_all_positions()
                self.logger.critical("🔴 All positions closed due to emergency stop")
            
            # Send acknowledgment back to Django
            await self.django_bridge.send_alert(
                alert_type="emergency_stop_acknowledged",
                severity="critical",
                title="Emergency Stop Acknowledged",
                description=f"Engine has processed emergency stop: {reason}",
                reason=reason,
                actions_taken={
                    "trading_stopped": stop_trading,
                    "positions_closed": close_positions
                }
            )
            
        except Exception as e:
            self.logger.error(f"Error handling emergency stop: {e}")
    
    # =========================================================================
    # NEW: HELPER METHODS
    # =========================================================================
    
    def _create_trading_decision(self, assessment: RiskAssessmentResult) -> TradeDecision:
        """Create a trading decision from fast risk assessment."""
        return TradeDecision(
            pair_address=assessment.pair_event.pair_address,
            chain_id=assessment.pair_event.chain_id,
            token_address=assessment.pair_event.token0_address,
            token_symbol=assessment.pair_event.token0_symbol,
            action="BUY" if assessment.is_tradeable else "SKIP",
            confidence_score=100 - assessment.overall_risk_score,  # Invert risk to confidence
            position_size_usd=config.max_position_size_usd * 0.1,  # Conservative 10% of max
            max_slippage_percent=config.default_slippage_percent,
            risk_assessment=assessment
        )
    
    def _create_enhanced_trading_decision(
        self, 
        fast_assessment: RiskAssessmentResult, 
        comprehensive_data: dict
    ) -> TradeDecision:
        """Create enhanced trading decision with both fast and comprehensive risk data."""
        comprehensive_score = comprehensive_data.get('overall_score', 50)
        is_tradeable = comprehensive_data.get('is_tradeable', False)
        
        # Combine fast and comprehensive scores (weighted average)
        combined_score = (fast_assessment.overall_risk_score * 0.3 + comprehensive_score * 0.7)
        
        return TradeDecision(
            pair_address=fast_assessment.pair_event.pair_address,
            chain_id=fast_assessment.pair_event.chain_id,
            token_address=fast_assessment.pair_event.token0_address,
            token_symbol=fast_assessment.pair_event.token0_symbol,
            action="BUY" if is_tradeable else "SKIP",
            confidence_score=100 - combined_score,
            position_size_usd=comprehensive_data.get('recommended_position_size_usd', config.max_position_size_usd * 0.1),
            max_slippage_percent=comprehensive_data.get('max_slippage_percent', config.default_slippage_percent),
            risk_assessment=fast_assessment
        )
    
    async def _update_risk_configuration(self, config_data: dict) -> None:
        """Update risk management configuration."""
        try:
            # Update risk manager with new configuration
            if hasattr(self.risk_manager, 'update_configuration'):
                await self.risk_manager.update_configuration(config_data)
                self.logger.info("✅ Risk configuration updated")
            else:
                self.logger.warning("Risk manager does not support configuration updates")
        except Exception as e:
            self.logger.error(f"Failed to update risk configuration: {e}")
    
    async def _update_trading_limits(self, config_data: dict) -> None:
        """Update trading limits configuration."""
        try:
            # Update portfolio manager with new limits
            if hasattr(self.portfolio_manager, 'update_limits'):
                await self.portfolio_manager.update_limits(config_data)
                self.logger.info("✅ Trading limits updated")
            else:
                self.logger.warning("Portfolio manager does not support limit updates")
        except Exception as e:
            self.logger.error(f"Failed to update trading limits: {e}")
    
    async def _send_startup_notification(self) -> None:
        """Send startup notification to Django."""
        await self.django_bridge.send_alert(
            alert_type="engine_startup",
            severity="info",
            title="Trading Engine Started",
            description=f"Engine {self.engine_id} has started successfully",
            engine_config=self.django_bridge._get_engine_config()
        )
    
    async def _periodic_django_sync(self) -> None:
        """Periodic synchronization with Django."""
        while self.status == EngineStatus.RUNNING and not self.shutdown_requested:
            try:
                # Send engine status update every minute
                await self.django_bridge.send_engine_status()
                self._last_django_sync = datetime.now(timezone.utc)
                
                # Wait 60 seconds before next sync
                await asyncio.sleep(60)
                
            except Exception as e:
                self.logger.error(f"Error in periodic Django sync: {e}")
                await asyncio.sleep(30)  # Shorter retry interval on error
    
    # =========================================================================
    # ENHANCED LIFECYCLE METHODS (your existing code with Django integration)
    # =========================================================================
    
    async def stop(self) -> None:
        """Stop the trading engine gracefully (enhanced with Django notification)."""
        if self.status == EngineStatus.STOPPED:
            return
        
        self.logger.info("🛑 Stopping enhanced trading engine...")
        self.status = EngineStatus.STOPPING
        
        try:
            # NEW: Notify Django of shutdown
            if self.django_bridge.is_connected():
                await self.django_bridge.send_alert(
                    alert_type="engine_shutdown",
                    severity="info",
                    title="Trading Engine Shutting Down",
                    description=f"Engine {self.engine_id} is shutting down gracefully",
                    final_statistics=self.get_statistics()
                )
            
            # Stop all subsystems in reverse order (your existing code)
            await self.discovery_manager.stop()
            self.logger.info("✅ Discovery manager stopped")
            
            await self.execution_manager.stop()
            self.logger.info("✅ Execution manager stopped")
            
            await self.portfolio_manager.stop()
            self.logger.info("✅ Portfolio manager stopped")
            
            # NEW: Stop Django bridge
            if self.django_bridge.is_connected():
                await self.django_bridge.shutdown()
                self.logger.info("✅ Django bridge stopped")
            
            # Log final statistics (your existing code)
            uptime = datetime.now(timezone.utc) - self.start_time if self.start_time else None
            
            self.logger.info("=" * 80)
            self.logger.info("📈 FINAL STATISTICS")
            self.logger.info("=" * 80)
            self.logger.info(f"Engine ID: {self.engine_id}")
            self.logger.info(f"Total Runtime: {uptime}")
            self.logger.info(f"Pairs Discovered: {self.total_pairs_discovered}")
            self.logger.info(f"Risk Assessments: {self.total_assessments_completed}")
            self.logger.info(f"Trades Executed: {self.total_trades_executed}")
            
            # NEW: Django communication statistics
            if hasattr(self.django_bridge, 'get_statistics'):
                django_stats = self.django_bridge.get_statistics()
                self.logger.info(f"Messages Sent to Django: {django_stats.get('messages_sent', 0)}")
                self.logger.info(f"Messages Received from Django: {django_stats.get('messages_received', 0)}")
            
            portfolio_summary = self.portfolio_manager.get_portfolio_summary()
            global_portfolio = portfolio_summary.get('global_portfolio', {})
            self.logger.info(f"Final Portfolio Value: ${global_portfolio.get('total_value', 0):,.2f}")
            self.logger.info(f"Total PnL: ${global_portfolio.get('total_pnl', 0):,.2f}")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
        finally:
            self.status = EngineStatus.STOPPED
            self.logger.info("✅ Enhanced trading engine stopped")
    
    async def get_comprehensive_status(self) -> Dict[str, Any]:
        """Get comprehensive status from all subsystems (enhanced with Django info)."""
        try:
            # Get status from all subsystems (your existing code)
            discovery_status = await self.discovery_manager.get_status()
            risk_status = await self.risk_manager.get_status()
            execution_status = await self.execution_manager.get_status()
            portfolio_status = await self.portfolio_manager.get_status()
            
            uptime_seconds = (
                (datetime.now(timezone.utc) - self.start_time).total_seconds()
                if self.start_time else 0
            )
            
            status = {
                "engine": {
                    "engine_id": self.engine_id,  # NEW
                    "status": self.status,
                    "uptime_seconds": uptime_seconds,
                    "start_time": self.start_time.isoformat() if self.start_time else None,
                    "trading_mode": config.trading_mode,
                    "target_chains": config.target_chains
                },
                "statistics": {
                    "pairs_discovered": self.total_pairs_discovered,
                    "assessments_completed": self.total_assessments_completed,
                    "trades_executed": self.total_trades_executed
                },
                "subsystems": {
                    "discovery": discovery_status,
                    "risk": risk_status,
                    "execution": execution_status,
                    "portfolio": portfolio_status
                }
            }
            
            # NEW: Add Django communication status
            if self.django_bridge.is_connected():
                status["django_integration"] = await self.django_bridge.health_check()
                status["pending_assessments"] = len(self._pending_comprehensive_assessments)
                status["last_django_sync"] = self._last_django_sync.isoformat() if self._last_django_sync else None
            else:
                status["django_integration"] = {"status": "disconnected", "reason": "Redis not configured"}
            
            return status
            
        except Exception as e:
            self.logger.error(f"Error getting comprehensive status: {e}")
            return {"error": str(e)}
    
    async def _log_engine_status(self) -> None:
        """Log comprehensive engine status (enhanced version)."""
        try:
            # Get status from all subsystems (your existing code)
            discovery_status = await self.discovery_manager.get_status()
            risk_status = await self.risk_manager.get_status()
            execution_status = await self.execution_manager.get_status()
            portfolio_status = await self.portfolio_manager.get_status()
            
            # Calculate uptime
            uptime = datetime.now(timezone.utc) - self.start_time if self.start_time else None
            
            self.logger.info("=" * 80)
            self.logger.info("📊 ENHANCED ENGINE STATUS REPORT")
            self.logger.info("=" * 80)
            self.logger.info(f"Engine ID: {self.engine_id}")
            self.logger.info(f"Status: {self.status}")
            self.logger.info(f"Uptime: {uptime}")
            self.logger.info(f"Pairs Discovered: {self.total_pairs_discovered}")
            self.logger.info(f"Risk Assessments: {self.total_assessments_completed}")
            self.logger.info(f"Trades Executed: {self.total_trades_executed}")
            
            # NEW: Django integration status
            if self.django_bridge.is_connected():
                django_stats = self.django_bridge.get_statistics()
                self.logger.info(f"Django Messages Sent: {django_stats.get('messages_sent', 0)}")
                self.logger.info(f"Django Messages Received: {django_stats.get('messages_received', 0)}")
                self.logger.info(f"Pending Comprehensive Assessments: {len(self._pending_comprehensive_assessments)}")
            else:
                self.logger.warning("Django Integration: ❌ Disconnected")
            
            # Portfolio summary (your existing code)
            portfolio_summary = portfolio_status.get('portfolio_summary', {})
            global_portfolio = portfolio_summary.get('global_portfolio', {})
            
            self.logger.info(f"Portfolio Value: ${global_portfolio.get('total_value', 0):,.2f}")
            self.logger.info(f"Available Capital: ${global_portfolio.get('available_capital', 0):,.2f}")
            self.logger.info(f"Daily PnL: ${global_portfolio.get('daily_pnl', 0):,.2f}")
            
            # Trading status
            trading_status = portfolio_summary.get('trading_status', {})
            can_trade = trading_status.get('can_trade', False)
            self.logger.info(f"Can Trade: {'✅' if can_trade else '❌'}")
            
            if not can_trade:
                restrictions = trading_status.get('restrictions', [])
                self.logger.warning(f"Trading Restrictions: {'; '.join(restrictions)}")
            
            self.logger.info("=" * 80)
            
        except Exception as e:
            self.logger.error(f"Error logging engine status: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get engine statistics for reporting."""
        stats = {
            "engine_id": self.engine_id,
            "uptime_seconds": int((datetime.now(timezone.utc) - self.start_time).total_seconds()) if self.start_time else 0,
            "pairs_discovered": self.total_pairs_discovered,
            "assessments_completed": self.total_assessments_completed,
            "trades_executed": self.total_trades_executed,
            "status": self.status,
        }
        
        # Add Django statistics if available
        if self.django_bridge.is_connected():
            django_stats = self.django_bridge.get_statistics()
            stats.update({
                "django_messages_sent": django_stats.get('messages_sent', 0),
                "django_messages_received": django_stats.get('messages_received', 0),
                "django_connected": True,
                "pending_comprehensive_assessments": len(self._pending_comprehensive_assessments),
            })
        else:
            stats["django_connected"] = False
        
        return stats


async def main():
    """Main entry point for the enhanced trading engine."""
    # Set up logging
    setup_logging()
    
    # Create and start the enhanced trading engine
    engine = TradingEngine()
    
    try:
        await engine.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Engine crashed: {e}")
        sys.exit(1)
    finally:
        await engine.stop()


if __name__ == "__main__":
    asyncio.run(main())