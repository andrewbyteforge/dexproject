"""
Main Trading Engine

Coordinates all engine components and provides the main execution loop.
Handles discovery, risk assessment, execution, and portfolio management.
"""

import asyncio
import logging
import signal
import sys
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import time

from .config import config
from .utils import setup_logging
from .discovery import MultiChainDiscoveryManager, NewPairEvent
from .risk import MultiChainRiskManager, RiskAssessmentResult
from .execution import MultiChainExecutionManager
from .portfolio import GlobalPortfolioManager
from . import EngineStatus

logger = logging.getLogger(__name__)


class TradingEngine:
    """
    Main trading engine that coordinates all subsystems.
    
    Orchestrates the complete trading pipeline from discovery
    to execution while maintaining risk controls and portfolio limits.
    """
    
    def __init__(self):
        """Initialize the trading engine."""
        self.status = EngineStatus.STOPPED
        self.start_time: Optional[datetime] = None
        self.shutdown_requested = False
        
        # Initialize subsystems
        self.discovery_manager = MultiChainDiscoveryManager(self._on_new_pair_discovered)
        self.risk_manager = MultiChainRiskManager(self._on_risk_assessment_complete)
        self.execution_manager = MultiChainExecutionManager()
        self.portfolio_manager = GlobalPortfolioManager()
        
        # Statistics
        self.total_pairs_discovered = 0
        self.total_assessments_completed = 0
        self.total_trades_executed = 0
        
        self.logger = logging.getLogger('engine.main')
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.shutdown_requested = True
    
    async def start(self) -> None:
        """Start the trading engine."""
        self.logger.info("=" * 80)
        self.logger.info("🚀 STARTING DEX TRADING ENGINE")
        self.logger.info("=" * 80)
        
        # Log configuration
        self.logger.info(f"Trading Mode: {config.trading_mode}")
        self.logger.info(f"Target Chains: {[config.chains[cid].name for cid in config.target_chains]}")
        self.logger.info(f"Discovery Enabled: {config.discovery_enabled}")
        self.logger.info(f"Max Portfolio Size: {config.max_portfolio_size_usd}")
        self.logger.info(f"Max Position Size: {config.max_position_size_usd}")
        
        try:
            self.status = EngineStatus.STARTING
            self.start_time = datetime.now(timezone.utc)
            
            # Start all subsystems
            await self._start_subsystems()
            
            self.status = EngineStatus.RUNNING
            self.logger.info("✅ Trading engine started successfully")
            
            # Run main event loop
            await self._run_main_loop()
            
        except Exception as e:
            self.logger.error(f"❌ Failed to start trading engine: {e}")
            self.status = EngineStatus.ERROR
            raise
        finally:
            await self.stop()
    
    async def _start_subsystems(self) -> None:
        """Start all engine subsystems."""
        self.logger.info("Starting subsystems...")
        
        # Start portfolio manager first
        await self.portfolio_manager.start()
        self.logger.info("✅ Portfolio manager started")
        
        # Start execution manager
        await self.execution_manager.start()
        self.logger.info("✅ Execution manager started")
        
        # Start discovery and risk in parallel (they run continuously)
        discovery_task = asyncio.create_task(self._start_discovery())
        
        # Wait for discovery to be ready before proceeding
        await asyncio.sleep(2)
        
        self.logger.info("✅ All subsystems started")
    
    async def _start_discovery(self) -> None:
        """Start discovery service (runs continuously)."""
        try:
            self.logger.info("🔍 Starting discovery services...")
            await self.discovery_manager.start()
        except Exception as e:
            self.logger.error(f"Discovery service error: {e}")
            self.status = EngineStatus.ERROR
    
    async def _run_main_loop(self) -> None:
        """Run the main engine loop."""
        self.logger.info("🔄 Entering main event loop...")
        
        last_status_log = time.time()
        last_portfolio_update = time.time()
        
        while not self.shutdown_requested and self.status == EngineStatus.RUNNING:
            try:
                # Update portfolio state every 30 seconds
                if time.time() - last_portfolio_update > 30:
                    await self._update_portfolio_state()
                    last_portfolio_update = time.time()
                
                # Log status every 5 minutes
                if time.time() - last_status_log > 300:
                    await self._log_engine_status()
                    last_status_log = time.time()
                
                # Check for emergency conditions
                await self._check_emergency_conditions()
                
                # Sleep briefly to prevent busy waiting
                await asyncio.sleep(1)
                
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(5)
    
    async def _update_portfolio_state(self) -> None:
        """Update global portfolio state from all chains."""
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
        """Check for emergency conditions that require immediate action."""
        try:
            portfolio_summary = self.portfolio_manager.get_portfolio_summary()
            
            # Check if circuit breakers are active
            circuit_breakers = portfolio_summary.get('circuit_breakers', {})
            active_breakers = circuit_breakers.get('active_breakers', [])
            
            if active_breakers:
                for breaker in active_breakers:
                    if breaker['type'] == 'PORTFOLIO_LOSS':
                        self.logger.critical("🚨 PORTFOLIO LOSS CIRCUIT BREAKER ACTIVE - EMERGENCY PROTOCOLS ENGAGED")
            
            # Check for excessive losses
            daily_pnl = portfolio_summary.get('global_portfolio', {}).get('daily_pnl', 0)
            if daily_pnl < -float(config.max_portfolio_size_usd) * 0.15:  # 15% daily loss
                self.logger.critical(f"🚨 EXCESSIVE DAILY LOSS: {daily_pnl}")
            
        except Exception as e:
            self.logger.error(f"Error checking emergency conditions: {e}")
    
    async def _log_engine_status(self) -> None:
        """Log comprehensive engine status."""
        try:
            # Get status from all subsystems
            discovery_status = await self.discovery_manager.get_status()
            risk_status = await self.risk_manager.get_status()
            execution_status = await self.execution_manager.get_status()
            portfolio_status = await self.portfolio_manager.get_status()
            
            # Calculate uptime
            uptime = datetime.now(timezone.utc) - self.start_time if self.start_time else None
            
            self.logger.info("=" * 80)
            self.logger.info("📊 ENGINE STATUS REPORT")
            self.logger.info("=" * 80)
            self.logger.info(f"Status: {self.status}")
            self.logger.info(f"Uptime: {uptime}")
            self.logger.info(f"Pairs Discovered: {self.total_pairs_discovered}")
            self.logger.info(f"Risk Assessments: {self.total_assessments_completed}")
            self.logger.info(f"Trades Executed: {self.total_trades_executed}")
            
            # Portfolio summary
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
    
    async def _on_new_pair_discovered(self, pair_event: NewPairEvent) -> None:
        """Handle new pair discovery event."""
        self.total_pairs_discovered += 1
        
        self.logger.info(
            f"🔍 New pair discovered: {pair_event.token0_symbol}/{pair_event.token1_symbol} "
            f"on {config.chains[pair_event.chain_id].name} "
            f"(Fee: {pair_event.fee_tier/10000:.2f}%)"
        )
        
        # Send to risk assessment
        try:
            await self.risk_manager.assess_pair(pair_event)
        except Exception as e:
            self.logger.error(f"Error sending pair to risk assessment: {e}")
    
    async def _on_risk_assessment_complete(self, assessment: RiskAssessmentResult) -> None:
        """Handle completed risk assessment."""
        self.total_assessments_completed += 1
        
        pair_event = assessment.pair_event
        
        self.logger.info(
            f"🎯 Risk assessment complete: {pair_event.token0_symbol}/{pair_event.token1_symbol} "
            f"Score: {assessment.overall_risk_score:.1f} "
            f"Level: {assessment.risk_level} "
            f"Tradeable: {'✅' if assessment.is_tradeable else '❌'}"
        )
        
        # Send to execution if tradeable
        if assessment.is_tradeable:
            try:
                await self.execution_manager.process_risk_assessment(assessment)
                self.total_trades_executed += 1
            except Exception as e:
                self.logger.error(f"Error sending assessment to execution: {e}")
        else:
            self.logger.info(f"Skipping execution due to blocking issues: {assessment.blocking_issues}")
    
    async def stop(self) -> None:
        """Stop the trading engine gracefully."""
        if self.status == EngineStatus.STOPPED:
            return
        
        self.logger.info("🛑 Stopping trading engine...")
        self.status = EngineStatus.STOPPING
        
        try:
            # Stop all subsystems in reverse order
            await self.discovery_manager.stop()
            self.logger.info("✅ Discovery manager stopped")
            
            await self.execution_manager.stop()
            self.logger.info("✅ Execution manager stopped")
            
            await self.portfolio_manager.stop()
            self.logger.info("✅ Portfolio manager stopped")
            
            # Log final statistics
            uptime = datetime.now(timezone.utc) - self.start_time if self.start_time else None
            
            self.logger.info("=" * 80)
            self.logger.info("📈 FINAL STATISTICS")
            self.logger.info("=" * 80)
            self.logger.info(f"Total Runtime: {uptime}")
            self.logger.info(f"Pairs Discovered: {self.total_pairs_discovered}")
            self.logger.info(f"Risk Assessments: {self.total_assessments_completed}")
            self.logger.info(f"Trades Executed: {self.total_trades_executed}")
            
            portfolio_summary = self.portfolio_manager.get_portfolio_summary()
            global_portfolio = portfolio_summary.get('global_portfolio', {})
            self.logger.info(f"Final Portfolio Value: ${global_portfolio.get('total_value', 0):,.2f}")
            self.logger.info(f"Total PnL: ${global_portfolio.get('total_pnl', 0):,.2f}")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
        finally:
            self.status = EngineStatus.STOPPED
            self.logger.info("✅ Trading engine stopped")
    
    async def get_comprehensive_status(self) -> Dict[str, Any]:
        """Get comprehensive status from all subsystems."""
        try:
            discovery_status = await self.discovery_manager.get_status()
            risk_status = await self.risk_manager.get_status()
            execution_status = await self.execution_manager.get_status()
            portfolio_status = await self.portfolio_manager.get_status()
            
            uptime_seconds = (
                (datetime.now(timezone.utc) - self.start_time).total_seconds()
                if self.start_time else 0
            )
            
            return {
                "engine": {
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
            
        except Exception as e:
            self.logger.error(f"Error getting comprehensive status: {e}")
            return {"error": str(e)}


async def main():
    """Main entry point for the trading engine."""
    # Set up logging
    setup_logging()
    
    # Create and start the trading engine
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