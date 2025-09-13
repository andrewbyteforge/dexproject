"""
Integration example showing how to connect mempool monitoring with the existing discovery engine.

This demonstrates how the mempool integration fits into your current engine architecture,
connecting with the discovery manager and providing Fast Lane capabilities.

Path: engine/examples/mempool_integration_example.py
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from engine.mempool import (
    create_mempool_monitor,
    create_mempool_analyzer, 
    MempoolEventType,
    MempoolTransaction,
    TransactionAnalysis
)
from engine.discovery import MultiChainDiscoveryManager
from engine.provider_manager import ProviderManager
from shared.schemas import MessageType, BaseMessage


logger = logging.getLogger(__name__)


class MempoolIntegratedDiscoveryManager:
    """
    Enhanced discovery manager that integrates mempool monitoring for Fast Lane execution.
    
    This extends your existing discovery capabilities by adding real-time mempool analysis
    for identifying trading opportunities before they hit the blockchain.
    """
    
    def __init__(self, pair_callback, provider_manager, chain_configs):
        """
        Initialize mempool-integrated discovery manager.
        
        Args:
            pair_callback: Existing pair discovery callback
            provider_manager: Provider manager instance
            chain_configs: Chain configuration mapping
        """
        # Initialize existing discovery manager
        self.discovery_manager = MultiChainDiscoveryManager(pair_callback)
        
        # Initialize mempool components
        self.provider_manager = provider_manager
        self.chain_configs = chain_configs
        self.mempool_monitor = None
        self.mempool_analyzer = None
        
        # Fast Lane event tracking
        self.pending_opportunities = {}
        self.fast_lane_stats = {
            'transactions_analyzed': 0,
            'opportunities_found': 0,
            'front_run_candidates': 0,
            'copy_trade_candidates': 0,
        }
        
        self.logger = logging.getLogger('engine.discovery.mempool_integrated')
    
    async def start(self) -> None:
        """Start both discovery and mempool monitoring."""
        self.logger.info("🚀 Starting mempool-integrated discovery manager...")
        
        try:
            # Start existing discovery manager
            await self.discovery_manager.start()
            self.logger.info("✅ Discovery manager started")
            
            # Initialize and start mempool monitoring
            await self._start_mempool_monitoring()
            self.logger.info("✅ Mempool monitoring started")
            
            self.logger.info("🎯 Mempool-integrated discovery fully operational")
            
        except Exception as e:
            self.logger.error(f"Failed to start mempool-integrated discovery: {e}")
            raise
    
    async def _start_mempool_monitoring(self) -> None:
        """Start mempool monitor and analyzer."""
        try:
            # Create mempool monitor with event callback
            self.mempool_monitor = await create_mempool_monitor(
                self.provider_manager,
                event_callback=self._on_mempool_event
            )
            
            # Create mempool analyzer
            self.mempool_analyzer = await create_mempool_analyzer(
                self.provider_manager,
                self.chain_configs
            )
            
            # Start monitoring
            await self.mempool_monitor.start_monitoring()
            
            self.logger.info("Mempool monitoring active on chains: " +
                           ", ".join(str(cid) for cid in self.mempool_monitor.config.websocket_endpoints.keys()))
            
        except Exception as e:
            self.logger.error(f"Failed to start mempool monitoring: {e}")
            raise
    
    async def _on_mempool_event(self, event_type: MempoolEventType, transaction: MempoolTransaction) -> None:
        """
        Handle mempool events for Fast Lane analysis.
        
        Args:
            event_type: Type of mempool event
            transaction: Transaction data from mempool
        """
        try:
            if event_type == MempoolEventType.PENDING_TRANSACTION:
                # Analyze transaction for Fast Lane opportunities
                analysis = await self.mempool_analyzer.analyze_transaction(transaction)
                
                # Update statistics
                self.fast_lane_stats['transactions_analyzed'] += 1
                
                # Handle different types of opportunities
                if analysis.is_front_run_opportunity:
                    await self._handle_front_run_opportunity(transaction, analysis)
                
                if analysis.is_copy_trade_candidate:
                    await self._handle_copy_trade_opportunity(transaction, analysis)
                
                if analysis.is_arbitrage_opportunity:
                    await self._handle_arbitrage_opportunity(transaction, analysis)
                
                # Log high-value or high-risk transactions
                if analysis.risk_score > 0.7 or (analysis.estimated_profit_eth and analysis.estimated_profit_eth > 0.1):
                    self.logger.info(
                        f"💰 High-value mempool transaction: {transaction.hash[:10]}... "
                        f"Risk: {analysis.risk_score:.2f}, "
                        f"Profit Est: {analysis.estimated_profit_eth or 0:.3f} ETH, "
                        f"Type: {analysis.transaction_type.value}"
                    )
                
        except Exception as e:
            self.logger.error(f"Error processing mempool event: {e}")
    
    async def _handle_front_run_opportunity(self, transaction: MempoolTransaction, analysis: TransactionAnalysis) -> None:
        """
        Handle potential front-running opportunity.
        
        This is where Fast Lane execution would be triggered for time-sensitive trades.
        """
        self.fast_lane_stats['front_run_candidates'] += 1
        
        self.logger.info(
            f"⚡ Front-run opportunity detected: {transaction.hash[:10]}... "
            f"Gas: {transaction.gas_price / 1e9:.1f} gwei, "
            f"Value: {transaction.value / 1e18:.3f} ETH, "
            f"Impact: {analysis.estimated_impact or 0:.2f}%"
        )
        
        # Store opportunity for Fast Lane engine to process
        opportunity_id = f"frontrun_{transaction.hash}"
        self.pending_opportunities[opportunity_id] = {
            'type': 'front_run',
            'transaction': transaction,
            'analysis': analysis,
            'timestamp': datetime.now(timezone.utc),
            'processed': False
        }
        
        # In a full implementation, this would trigger Fast Lane execution
        # await self._trigger_fast_lane_execution(opportunity_id)
    
    async def _handle_copy_trade_opportunity(self, transaction: MempoolTransaction, analysis: TransactionAnalysis) -> None:
        """
        Handle copy trading opportunity from a successful trader.
        """
        self.fast_lane_stats['copy_trade_candidates'] += 1
        
        self.logger.info(
            f"👥 Copy trade opportunity: {transaction.hash[:10]}... "
            f"From: {transaction.from_address[:10]}..., "
            f"Amount: {analysis.estimated_amount_in / 1e18 if analysis.estimated_amount_in else 0:.3f} ETH, "
            f"Token: {analysis.target_token[:10] if analysis.target_token else 'Unknown'}..."
        )
        
        # Store for analysis and potential copying
        opportunity_id = f"copy_{transaction.hash}"
        self.pending_opportunities[opportunity_id] = {
            'type': 'copy_trade',
            'transaction': transaction,
            'analysis': analysis,
            'timestamp': datetime.now(timezone.utc),
            'processed': False
        }
    
    async def _handle_arbitrage_opportunity(self, transaction: MempoolTransaction, analysis: TransactionAnalysis) -> None:
        """
        Handle arbitrage opportunity created by large trade.
        """
        self.logger.info(
            f"🔄 Arbitrage opportunity: {transaction.hash[:10]}... "
            f"Impact: {analysis.estimated_impact or 0:.2f}%, "
            f"Est. Profit: {analysis.estimated_profit_eth or 0:.3f} ETH"
        )
        
        # Store for arbitrage execution
        opportunity_id = f"arb_{transaction.hash}"
        self.pending_opportunities[opportunity_id] = {
            'type': 'arbitrage',
            'transaction': transaction,
            'analysis': analysis,
            'timestamp': datetime.now(timezone.utc),
            'processed': False
        }
    
    async def stop(self) -> None:
        """Stop mempool monitoring and discovery."""
        self.logger.info("Stopping mempool-integrated discovery...")
        
        if self.mempool_monitor:
            await self.mempool_monitor.stop_monitoring()
        
        await self.discovery_manager.stop()
        
        self.logger.info("✅ Mempool-integrated discovery stopped")
    
    def get_mempool_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics including mempool data."""
        stats = {}
        
        # Get existing discovery stats
        if hasattr(self.discovery_manager, 'get_statistics'):
            stats.update(self.discovery_manager.get_statistics())
        
        # Add mempool-specific stats
        stats['mempool'] = self.fast_lane_stats.copy()
        
        if self.mempool_monitor:
            stats['mempool']['monitor'] = self.mempool_monitor.get_statistics()
        
        if self.mempool_analyzer:
            stats['mempool']['analyzer'] = self.mempool_analyzer.get_statistics()
        
        stats['mempool']['pending_opportunities'] = len(self.pending_opportunities)
        
        return stats
    
    async def get_pending_opportunities(self, opportunity_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Get current pending opportunities from mempool analysis.
        
        Args:
            opportunity_type: Filter by type ('front_run', 'copy_trade', 'arbitrage')
            
        Returns:
            Dictionary of pending opportunities
        """
        if opportunity_type:
            return {
                k: v for k, v in self.pending_opportunities.items()
                if v['type'] == opportunity_type and not v['processed']
            }
        
        return {
            k: v for k, v in self.pending_opportunities.items()
            if not v['processed']
        }
    
    async def mark_opportunity_processed(self, opportunity_id: str) -> None:
        """Mark an opportunity as processed."""
        if opportunity_id in self.pending_opportunities:
            self.pending_opportunities[opportunity_id]['processed'] = True
    
    def is_mempool_connected(self) -> bool:
        """Check if mempool monitoring is connected."""
        return self.mempool_monitor and self.mempool_monitor.is_connected()


# =============================================================================
# INTEGRATION WITH EXISTING MAIN ENGINE
# =============================================================================

async def integrate_mempool_with_engine(trading_engine) -> None:
    """
    Example function showing how to integrate mempool monitoring with your existing TradingEngine.
    
    This would be called during engine initialization to enable Fast Lane capabilities.
    """
    logger.info("🔧 Integrating mempool monitoring with trading engine...")
    
    try:
        # Replace the standard discovery manager with mempool-integrated version
        mempool_discovery = MempoolIntegratedDiscoveryManager(
            pair_callback=trading_engine._on_new_pair_discovered,
            provider_manager=trading_engine.provider_manager,
            chain_configs=trading_engine.config.chains
        )
        
        # Replace the discovery manager
        trading_engine.discovery_manager = mempool_discovery
        
        logger.info("✅ Mempool integration complete - Fast Lane enabled")
        
    except Exception as e:
        logger.error(f"Failed to integrate mempool monitoring: {e}")
        raise


# =============================================================================
# USAGE EXAMPLE
# =============================================================================

async def demo_mempool_integration():
    """
    Demo showing how mempool integration works with the discovery engine.
    """
    print("🚀 Starting Mempool Integration Demo...")
    
    # This would normally be done in your main engine initialization
    from engine.provider_manager import ProviderManager
    from engine.config import get_config
    
    # Get configuration and provider manager
    config = await get_config()
    provider_manager = ProviderManager(config.chains[list(config.chains.keys())[0]])
    
    # Create mempool-integrated discovery manager
    def dummy_pair_callback(pair_event):
        print(f"📈 New pair discovered: {pair_event.token0_symbol}/{pair_event.token1_symbol}")
    
    discovery = MempoolIntegratedDiscoveryManager(
        pair_callback=dummy_pair_callback,
        provider_manager=provider_manager,
        chain_configs=config.chains
    )
    
    try:
        # Start monitoring
        await discovery.start()
        
        # Run for demo duration
        print("💫 Monitoring mempool for 30 seconds...")
        await asyncio.sleep(30)
        
        # Show statistics
        stats = discovery.get_mempool_statistics()
        print("\n📊 Mempool Statistics:")
        print(f"   Transactions analyzed: {stats.get('mempool', {}).get('transactions_analyzed', 0)}")
        print(f"   Opportunities found: {stats.get('mempool', {}).get('opportunities_found', 0)}")
        print(f"   Front-run candidates: {stats.get('mempool', {}).get('front_run_candidates', 0)}")
        print(f"   Copy trade candidates: {stats.get('mempool', {}).get('copy_trade_candidates', 0)}")
        
        # Show pending opportunities
        opportunities = await discovery.get_pending_opportunities()
        print(f"   Pending opportunities: {len(opportunities)}")
        
    finally:
        await discovery.stop()
        print("✅ Demo completed")


if __name__ == "__main__":
    # Run the demo
    asyncio.run(demo_mempool_integration())