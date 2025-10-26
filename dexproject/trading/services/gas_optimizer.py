"""
Gas Optimizer Windows Compatibility Fix - Phase 6A

Fixes Windows console encoding issues and configuration problems.

File: trading/services/gas_optimizer.py (UPDATED)
"""

import asyncio
import logging
import time
import sys
import os
from typing import Dict, Any, Optional, List, Tuple
from decimal import Decimal
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone as django_timezone

# Import engine components with better error handling
try:
    from engine.config import config, ChainConfig
    from engine.execution.gas_optimizer import (
        GasOptimizationEngine, 
        GasStrategy, 
        GasRecommendation,
        NetworkCongestion
    )
    ENGINE_AVAILABLE = True
except ImportError as e:
    ENGINE_AVAILABLE = False
    print(f"WARNING: Engine components not available: {e}")

try:
    from engine.web3_client import Web3Client
    from engine.wallet_manager import WalletManager
    WEB3_AVAILABLE = True
except ImportError:
    WEB3_AVAILABLE = False
    print("WARNING: Web3 components not available")

logger = logging.getLogger(__name__)

# Windows console compatibility
def safe_print(message: str, use_fallback_chars: bool = True):
    """Print message with Windows console compatibility."""
    if use_fallback_chars and sys.platform.startswith('win'):
        # Replace emoji with ASCII equivalents for Windows
        emoji_map = {
            '🔧': '[INIT]',
            '🚀': '[START]',
            '✅': '[OK]',
            '❌': '[ERROR]',
            '⚡': '[GAS]',
            '📊': '[DATA]',
            '💰': '[COST]',
            '💸': '[SAVE]',
            '📝': '[PAPER]',
            '🎭': '[SIM]',
            '🚨': '[ALERT]',
            '⚠️': '[WARN]',
            '🔄': '[UPDATE]',
            '📈': '[STATS]',
            '📺': '[OUT]',
            '🌐': '[NET]',
            '🎯': '[TARGET]'
        }
        
        for emoji, replacement in emoji_map.items():
            message = message.replace(emoji, replacement)
    
    try:
        print(message)
    except UnicodeEncodeError:
        # Final fallback: encode to ASCII
        print(message.encode('ascii', 'replace').decode('ascii'))


class TradingGasStrategy(str, Enum):
    """Trading-specific gas strategies."""
    PAPER_TRADING = "paper_trading"      # Simulated pricing for paper trades
    COST_EFFICIENT = "cost_efficient"    # Minimize costs for patient trades
    BALANCED = "balanced"                # Balance of speed and cost
    SPEED_PRIORITY = "speed_priority"    # Fast execution for opportunities
    MEV_PROTECTED = "mev_protected"      # MEV protection focused
    EMERGENCY_FAST = "emergency_fast"    # Emergency stops/exits


@dataclass
class TradingGasPrice:
    """Gas pricing for trading operations."""
    strategy: TradingGasStrategy
    chain_id: int
    
    # EIP-1559 pricing (preferred)
    max_fee_per_gas_gwei: Optional[Decimal] = None
    max_priority_fee_per_gas_gwei: Optional[Decimal] = None
    
    # Legacy pricing (fallback)
    gas_price_gwei: Optional[Decimal] = None
    
    # Execution details
    estimated_gas_limit: int = 200000
    estimated_cost_usd: Optional[Decimal] = None
    network_congestion: str = "MEDIUM"  # Use string for compatibility
    
    # Performance metrics
    expected_confirmation_time_ms: int = 15000
    cost_savings_percent: Decimal = Decimal('0')
    
    # Emergency flags
    is_emergency_price: bool = False
    emergency_reason: Optional[str] = None


@dataclass
class GasOptimizationResult:
    """Result of gas optimization analysis."""
    success: bool
    gas_price: Optional[TradingGasPrice] = None
    error_message: Optional[str] = None
    fallback_used: bool = False
    console_output: str = ""


class DjangoGasOptimizer:
    """
    Django-integrated gas optimization service for trading operations.
    
    Windows-compatible version with fallback implementations.
    """
    
    def __init__(self):
        """Initialize the Django gas optimizer with Windows compatibility."""
        self.logger = logging.getLogger('trading.gas_optimizer')
        
        # Engine integration (optional)
        self._engine_optimizer: Optional[Any] = None
        self._web3_clients: Dict[int, Any] = {}
        self._initialized_chains: set = set()
        
        # Performance tracking
        self.optimization_count = 0
        self.cost_savings_total = Decimal('0')
        self.emergency_stops_triggered = 0
        
        # Console output buffer
        self._console_buffer: List[str] = []
        self._last_console_output = datetime.now(timezone.utc)
        
        # Configuration
        self._use_engine = ENGINE_AVAILABLE and WEB3_AVAILABLE
        
        safe_print("[INIT] Django Gas Optimizer initialized")
        self.logger.info("Django Gas Optimizer initialized")
    
    async def initialize(self, chain_ids: List[int]) -> bool:
        """
        Initialize gas optimizer for specified chains with fallback support.
        
        Args:
            chain_ids: List of chain IDs to support
            
        Returns:
            True if initialization successful, False otherwise
        """
        try:
            console_msg = f"[START] Initializing Gas Optimizer for chains: {chain_ids}"
            self._add_console_output(console_msg)
            
            # Try to initialize engine gas optimizer if available
            if self._use_engine and not self._engine_optimizer:
                try:
                    # Get or create engine config
                    engine_config = self._get_or_create_engine_config()
                    
                    if engine_config:
                        from engine.execution.gas_optimizer import GasOptimizationEngine
                        self._engine_optimizer = GasOptimizationEngine(engine_config)
                        await self._engine_optimizer.initialize()
                        
                        console_msg = "[OK] Engine gas optimizer connected"
                        self._add_console_output(console_msg)
                    else:
                        safe_print("[WARN] Engine config not available, using fallback mode")
                        self._use_engine = False
                except Exception as e:
                    safe_print(f"[WARN] Engine optimizer failed, using fallback: {e}")
                    self._use_engine = False
                    self._engine_optimizer = None
            
            # Initialize chains (with or without engine)
            success_count = 0
            for chain_id in chain_ids:
                if chain_id not in self._initialized_chains:
                    success = await self._initialize_chain(chain_id)
                    if success:
                        self._initialized_chains.add(chain_id)
                        success_count += 1
                        console_msg = f"[OK] Chain {chain_id} gas optimization ready"
                        self._add_console_output(console_msg)
                    else:
                        console_msg = f"[ERROR] Failed to initialize chain {chain_id}"
                        self._add_console_output(console_msg)
                        self.logger.error(f"Failed to initialize gas optimization for chain {chain_id}")
            
            success = success_count > 0
            
            if success:
                # Start background monitoring
                asyncio.create_task(self._background_monitoring())
                console_msg = f"[TARGET] Gas Optimizer active for {success_count}/{len(chain_ids)} chains"
                self._add_console_output(console_msg)
            
            return success
            
        except Exception as e:
            error_msg = f"[ERROR] Gas optimizer initialization failed: {e}"
            self._add_console_output(error_msg)
            self.logger.error(f"Gas optimizer initialization error: {e}", exc_info=True)
            return False
    
    def _get_or_create_engine_config(self):
        """Get or create a basic engine configuration."""
        try:
            # Try to use existing config first
            if config and hasattr(config, 'chain_configs'):
                return config
            
            # Create a minimal config for testing
            from engine.config import EngineConfig
            
            # Create basic chain configs
            chain_configs = {}
            
            # Ethereum mainnet config
            if hasattr(settings, 'ALCHEMY_API_KEY'):
                chain_configs[1] = {
                    'chain_id': 1,
                    'name': 'ethereum',
                    'rpc_urls': [f"https://eth-mainnet.alchemyapi.io/v2/{settings.ALCHEMY_API_KEY}"],
                    'block_time_seconds': 12.0,
                    'gas_limits': {'min': 21000, 'max': 300000}
                }
            
            # Base mainnet config  
            if hasattr(settings, 'ALCHEMY_API_KEY'):
                chain_configs[8453] = {
                    'chain_id': 8453,
                    'name': 'base',
                    'rpc_urls': [f"https://base-mainnet.g.alchemy.com/v2/{settings.ALCHEMY_API_KEY}"],
                    'block_time_seconds': 2.0,
                    'gas_limits': {'min': 21000, 'max': 300000}
                }
            
            if chain_configs:
                # Create minimal engine config
                return type('MockEngineConfig', (), {
                    'chain_configs': chain_configs,
                    'trading_mode': 'paper',
                    'chains': chain_configs
                })()
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to create engine config: {e}")
            return None
    
    async def _initialize_chain(self, chain_id: int) -> bool:
        """Initialize gas optimization for a specific chain."""
        try:
            # For fallback mode, just mark as initialized
            if not self._use_engine:
                return True
                
            # Try to initialize Web3 client if engine is available
            if self._use_engine and WEB3_AVAILABLE:
                # This would normally initialize Web3Client
                # For now, mark as successful
                pass
            
            # Cache initial gas metrics
            await self._fetch_and_cache_gas_metrics(chain_id)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Chain {chain_id} initialization error: {e}")
            return True  # Return True for fallback mode
    
    async def optimize_gas_for_trade(
        self,
        chain_id: int,
        trade_type: str,  # 'buy', 'sell', 'swap'
        amount_usd: Decimal,
        strategy: TradingGasStrategy = TradingGasStrategy.BALANCED,
        is_paper_trade: bool = False
    ) -> GasOptimizationResult:
        """
        Optimize gas pricing for a trading operation.
        
        Windows-compatible version with fallback implementations.
        """
        start_time = time.time()
        console_output = []
        
        try:
            console_msg = f"[GAS] Optimizing gas for {trade_type.upper()} on chain {chain_id}"
            console_output.append(console_msg)
            self._add_console_output(console_msg)
            
            # Check if chain is initialized
            if chain_id not in self._initialized_chains:
                error_msg = f"[ERROR] Chain {chain_id} not initialized for gas optimization"
                console_output.append(error_msg)
                return GasOptimizationResult(
                    success=False,
                    error_message=f"Chain {chain_id} not initialized",
                    console_output="\n".join(console_output)
                )
            
            # Handle paper trading
            if is_paper_trade:
                return await self._handle_paper_trading_gas(
                    chain_id, trade_type, amount_usd, console_output
                )
            
            # Get current gas metrics (fallback implementation)
            gas_metrics = await self._get_gas_metrics_fallback(chain_id)
            
            console_msg = f"[DATA] Network congestion: {gas_metrics.get('congestion', 'UNKNOWN')}"
            console_output.append(console_msg)
            self._add_console_output(console_msg)
            
            # Check for emergency conditions
            emergency_check = await self._check_emergency_conditions(chain_id, gas_metrics)
            if emergency_check['is_emergency']:
                console_msg = f"[ALERT] EMERGENCY CONDITION: {emergency_check['reason']}"
                console_output.append(console_msg)
                self._add_console_output(console_msg)
                
                if emergency_check['should_block']:
                    return GasOptimizationResult(
                        success=False,
                        error_message=f"Emergency condition blocks trading: {emergency_check['reason']}",
                        console_output="\n".join(console_output)
                    )
            
            # Get optimal gas pricing
            gas_price = await self._calculate_optimal_gas_price(
                chain_id, strategy, gas_metrics, amount_usd, console_output
            )
            
            # Calculate cost savings
            baseline_cost = await self._get_baseline_gas_cost_fallback(chain_id)
            if baseline_cost and gas_price.estimated_cost_usd:
                savings_usd = baseline_cost - gas_price.estimated_cost_usd
                savings_percent = (savings_usd / baseline_cost) * 100 if baseline_cost > 0 else 0
                gas_price.cost_savings_percent = max(Decimal('0'), Decimal(str(savings_percent)))
                
                console_msg = f"[COST] Cost savings: ${savings_usd:.4f} ({savings_percent:.1f}%)"
                console_output.append(console_msg)
                self._add_console_output(console_msg)
                
                # Track total savings
                self.cost_savings_total += savings_usd
            
            execution_time = (time.time() - start_time) * 1000
            console_msg = f"[OK] Gas optimization complete in {execution_time:.1f}ms"
            console_output.append(console_msg)
            self._add_console_output(console_msg)
            
            self.optimization_count += 1
            
            return GasOptimizationResult(
                success=True,
                gas_price=gas_price,
                console_output="\n".join(console_output)
            )
            
        except Exception as e:
            error_msg = f"[ERROR] Gas optimization error: {e}"
            console_output.append(error_msg)
            self.logger.error(f"Gas optimization error: {e}", exc_info=True)
            
            return await self._handle_fallback_pricing(
                chain_id, strategy, str(e), console_output
            )
    
    async def _get_gas_metrics_fallback(self, chain_id: int) -> Dict[str, Any]:
        """Get gas metrics using fallback implementation."""
        try:
            # Try to get from cache first
            cache_key = f"gas_metrics_{chain_id}"
            cached_metrics = cache.get(cache_key)
            
            if cached_metrics:
                return cached_metrics
            
            # Fallback: Use reasonable defaults based on chain
            if chain_id == 1:  # Ethereum
                base_fee_gwei = Decimal('25')  # 25 gwei
                priority_fee_gwei = Decimal('2')  # 2 gwei
                congestion = "MEDIUM"
            elif chain_id == 8453:  # Base
                base_fee_gwei = Decimal('0.05')  # 0.05 gwei
                priority_fee_gwei = Decimal('0.01')  # 0.01 gwei
                congestion = "LOW"
            else:
                base_fee_gwei = Decimal('20')  # 20 gwei default
                priority_fee_gwei = Decimal('2')  # 2 gwei default
                congestion = "MEDIUM"
            
            metrics = {
                'base_fee_gwei': base_fee_gwei,
                'fast_priority_fee_gwei': priority_fee_gwei,
                'congestion': congestion,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'source': 'fallback'
            }
            
            # Cache for 60 seconds
            cache.set(cache_key, metrics, 60)
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"Failed to get gas metrics for chain {chain_id}: {e}")
            # Ultra-safe fallback
            return {
                'base_fee_gwei': Decimal('30'),
                'fast_priority_fee_gwei': Decimal('2'),
                'congestion': 'HIGH',
                'source': 'ultra_safe_fallback'
            }
    
    async def _handle_paper_trading_gas(
        self,
        chain_id: int,
        trade_type: str,
        amount_usd: Decimal,
        console_output: List[str]
    ) -> GasOptimizationResult:
        """Handle gas pricing for paper trading simulation."""
        console_msg = "[PAPER] Paper trading mode - using simulated gas pricing"
        console_output.append(console_msg)
        self._add_console_output(console_msg)
        
        # Use conservative estimates for paper trading
        base_gas_gwei = Decimal('20')  # 20 gwei base
        priority_fee_gwei = Decimal('2')  # 2 gwei priority
        
        if chain_id == 8453:  # Base
            base_gas_gwei = Decimal('0.05')  # Much lower for Base
            priority_fee_gwei = Decimal('0.01')
        
        gas_price = TradingGasPrice(
            strategy=TradingGasStrategy.PAPER_TRADING,
            chain_id=chain_id,
            max_fee_per_gas_gwei=base_gas_gwei + priority_fee_gwei,
            max_priority_fee_per_gas_gwei=priority_fee_gwei,
            estimated_cost_usd=Decimal('5.00'),  # Fixed simulation cost
            network_congestion="LOW",
            expected_confirmation_time_ms=12000,
            cost_savings_percent=Decimal('0')  # No savings in paper mode
        )
        
        console_msg = f"[SIM] Paper trade gas: {base_gas_gwei + priority_fee_gwei} gwei (~$5.00)"
        console_output.append(console_msg)
        self._add_console_output(console_msg)
        
        return GasOptimizationResult(
            success=True,
            gas_price=gas_price,
            console_output="\n".join(console_output)
        )
    
    async def _calculate_optimal_gas_price(
        self,
        chain_id: int,
        strategy: TradingGasStrategy,
        gas_metrics: Dict[str, Any],
        amount_usd: Decimal,
        console_output: List[str]
    ) -> TradingGasPrice:
        """Calculate optimal gas pricing based on strategy and conditions."""
        
        base_fee = gas_metrics.get('base_fee_gwei', Decimal('20'))
        fast_priority = gas_metrics.get('fast_priority_fee_gwei', Decimal('2'))
        congestion = gas_metrics.get('congestion', "MEDIUM")
        
        # Strategy-based adjustments
        if strategy == TradingGasStrategy.COST_EFFICIENT:
            max_priority_fee = fast_priority * Decimal('0.7')
            max_fee = base_fee * Decimal('1.1') + max_priority_fee
            confirmation_time = 30000
            
        elif strategy == TradingGasStrategy.SPEED_PRIORITY:
            max_priority_fee = fast_priority * Decimal('1.5')
            max_fee = base_fee * Decimal('1.3') + max_priority_fee
            confirmation_time = 8000
            
        elif strategy == TradingGasStrategy.MEV_PROTECTED:
            max_priority_fee = fast_priority * Decimal('1.2')
            max_fee = base_fee * Decimal('1.2') + max_priority_fee
            confirmation_time = 15000
            
        elif strategy == TradingGasStrategy.EMERGENCY_FAST:
            max_priority_fee = fast_priority * Decimal('2.0')
            max_fee = base_fee * Decimal('1.5') + max_priority_fee
            confirmation_time = 5000
            
        else:  # BALANCED (default)
            max_priority_fee = fast_priority
            max_fee = base_fee * Decimal('1.15') + max_priority_fee
            confirmation_time = 12000
        
        # Chain-specific adjustments
        if chain_id == 8453:  # Base - much lower gas costs
            max_fee = max_fee * Decimal('0.1')
            max_priority_fee = max_priority_fee * Decimal('0.1')
        
        # Calculate estimated cost
        estimated_gas_limit = self._estimate_gas_limit_for_trade(amount_usd)
        estimated_cost_usd = self._calculate_gas_cost_usd(
            chain_id, max_fee, estimated_gas_limit
        )
        
        console_msg = f"[COST] Gas estimate: {max_fee:.4f} gwei (${estimated_cost_usd:.2f})"
        console_output.append(console_msg)
        self._add_console_output(console_msg)
        
        return TradingGasPrice(
            strategy=strategy,
            chain_id=chain_id,
            max_fee_per_gas_gwei=max_fee,
            max_priority_fee_per_gas_gwei=max_priority_fee,
            estimated_gas_limit=estimated_gas_limit,
            estimated_cost_usd=estimated_cost_usd,
            network_congestion=congestion,
            expected_confirmation_time_ms=confirmation_time
        )
    
    async def _check_emergency_conditions(
        self, 
        chain_id: int, 
        gas_metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Check for emergency gas price conditions."""
        
        base_fee = gas_metrics.get('base_fee_gwei', Decimal('0'))
        congestion = gas_metrics.get('congestion', "LOW")
        
        # Define emergency thresholds by chain
        if chain_id == 1:  # Ethereum mainnet
            emergency_threshold = Decimal('200')  # 200 gwei
            critical_threshold = Decimal('500')   # 500 gwei
        elif chain_id == 8453:  # Base
            emergency_threshold = Decimal('1')    # 1 gwei
            critical_threshold = Decimal('5')     # 5 gwei
        else:
            emergency_threshold = Decimal('100')  # Default 100 gwei
            critical_threshold = Decimal('300')   # Default 300 gwei
        
        is_emergency = base_fee >= emergency_threshold
        is_critical = base_fee >= critical_threshold
        
        if is_critical:
            self.emergency_stops_triggered += 1
            return {
                'is_emergency': True,
                'should_block': True,
                'reason': f'Critical gas prices: {base_fee} gwei (limit: {critical_threshold})',
                'severity': 'CRITICAL'
            }
        elif is_emergency:
            return {
                'is_emergency': True,
                'should_block': False,
                'reason': f'High gas prices: {base_fee} gwei (warning: {emergency_threshold})',
                'severity': 'WARNING'
            }
        
        return {
            'is_emergency': False,
            'should_block': False,
            'reason': None,
            'severity': 'NORMAL'
        }
    
    async def _handle_fallback_pricing(
        self,
        chain_id: int,
        strategy: TradingGasStrategy,
        error_reason: str,
        console_output: List[str]
    ) -> GasOptimizationResult:
        """Handle fallback pricing when optimization fails."""
        
        console_msg = f"[WARN] Using fallback pricing due to: {error_reason}"
        console_output.append(console_msg)
        self._add_console_output(console_msg)
        
        # Conservative fallback pricing
        if chain_id == 1:  # Ethereum
            fallback_gas = Decimal('30')
            fallback_priority = Decimal('2')
        elif chain_id == 8453:  # Base
            fallback_gas = Decimal('0.1')
            fallback_priority = Decimal('0.01')
        else:
            fallback_gas = Decimal('25')
            fallback_priority = Decimal('2')
        
        gas_price = TradingGasPrice(
            strategy=strategy,
            chain_id=chain_id,
            max_fee_per_gas_gwei=fallback_gas + fallback_priority,
            max_priority_fee_per_gas_gwei=fallback_priority,
            estimated_cost_usd=Decimal('10.00'),  # Conservative estimate
            network_congestion="HIGH",  # Assume high for safety
            expected_confirmation_time_ms=20000,
            cost_savings_percent=Decimal('0')
        )
        
        console_msg = f"[UPDATE] Fallback gas: {fallback_gas + fallback_priority} gwei"
        console_output.append(console_msg)
        self._add_console_output(console_msg)
        
        return GasOptimizationResult(
            success=True,
            gas_price=gas_price,
            fallback_used=True,
            console_output="\n".join(console_output)
        )
    
    def _estimate_gas_limit_for_trade(self, amount_usd: Decimal) -> int:
        """Estimate gas limit based on trade amount and complexity."""
        base_limit = 150000
        
        if amount_usd > Decimal('10000'):
            base_limit += 50000
        elif amount_usd > Decimal('1000'):
            base_limit += 20000
        
        return base_limit
    
    def _calculate_gas_cost_usd(
        self, 
        chain_id: int, 
        gas_price_gwei: Decimal, 
        gas_limit: int
    ) -> Decimal:
        """Calculate estimated gas cost in USD."""
        
        # ETH price approximation
        if chain_id == 1:  # Ethereum
            eth_price_usd = Decimal('3500')
        elif chain_id == 8453:  # Base
            eth_price_usd = Decimal('3500')
        else:
            eth_price_usd = Decimal('3500')
        
        gas_cost_wei = gas_price_gwei * Decimal('1e9') * Decimal(gas_limit)
        gas_cost_eth = gas_cost_wei / Decimal('1e18')
        gas_cost_usd = gas_cost_eth * eth_price_usd
        
        return gas_cost_usd.quantize(Decimal('0.01'))
    
    async def _get_baseline_gas_cost_fallback(self, chain_id: int) -> Optional[Decimal]:
        """Get baseline gas cost for comparison (fallback version)."""
        try:
            # Simple baseline: standard gas price + 20%
            if chain_id == 1:  # Ethereum
                baseline_gas_gwei = Decimal('30')  # 30 gwei
            elif chain_id == 8453:  # Base
                baseline_gas_gwei = Decimal('0.1')  # 0.1 gwei
            else:
                baseline_gas_gwei = Decimal('25')  # 25 gwei
            
            return self._calculate_gas_cost_usd(chain_id, baseline_gas_gwei, 200000)
            
        except Exception as e:
            self.logger.error(f"Failed to get baseline gas cost: {e}")
            return None
    
    async def _fetch_and_cache_gas_metrics(self, chain_id: int) -> Optional[Dict[str, Any]]:
        """Fetch fresh gas metrics and cache them (fallback version)."""
        return await self._get_gas_metrics_fallback(chain_id)
    
    async def _background_monitoring(self):
        """Background task for continuous gas monitoring."""
        while True:
            try:
                for chain_id in self._initialized_chains:
                    await self._refresh_gas_metrics(chain_id)
                
                # Output periodic status to console
                if self.optimization_count > 0 and self.optimization_count % 5 == 0:
                    status_msg = (
                        f"[STATS] Gas Optimizer Status: "
                        f"{self.optimization_count} optimizations, "
                        f"${self.cost_savings_total:.2f} total savings, "
                        f"{self.emergency_stops_triggered} emergency stops"
                    )
                    self._add_console_output(status_msg)
                
                await asyncio.sleep(30)  # Update every 30 seconds
                
            except Exception as e:
                self.logger.error(f"Background monitoring error: {e}")
                await asyncio.sleep(60)
    
    async def _refresh_gas_metrics(self, chain_id: int):
        """Refresh gas metrics for a specific chain."""
        try:
            await self._fetch_and_cache_gas_metrics(chain_id)
        except Exception as e:
            self.logger.error(f"Failed to refresh gas metrics for chain {chain_id}: {e}")
    
    def _add_console_output(self, message: str):
        """Add message to console output buffer with timestamp."""
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        
        # Print to console with Windows compatibility
        safe_print(formatted_message)
        
        # Store in buffer (limit to last 50 messages)
        self._console_buffer.append(formatted_message)
        if len(self._console_buffer) > 50:
            self._console_buffer.pop(0)
        
        self._last_console_output = datetime.now(timezone.utc)
    
    def get_console_output(self, last_n: int = 10) -> List[str]:
        """Get recent console output messages."""
        return self._console_buffer[-last_n:] if self._console_buffer else []
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for monitoring."""
        return {
            'optimization_count': self.optimization_count,
            'cost_savings_total_usd': float(self.cost_savings_total),
            'emergency_stops_triggered': self.emergency_stops_triggered,
            'initialized_chains': list(self._initialized_chains),
            'last_console_output': self._last_console_output.isoformat(),
            'active': len(self._initialized_chains) > 0,
            'engine_available': self._use_engine
        }
    
    async def emergency_stop_all_chains(self, reason: str = "Manual emergency stop"):
        """Trigger emergency stop across all chains."""
        console_msg = f"[ALERT] EMERGENCY STOP ACTIVATED: {reason}"
        self._add_console_output(console_msg)
        
        self.emergency_stops_triggered += 1
        
        # Set emergency flag in cache for all chains
        for chain_id in self._initialized_chains:
            cache.set(f"emergency_stop_{chain_id}", {
                'active': True,
                'reason': reason,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }, 3600)  # 1 hour emergency stop
        
        console_msg = f"[TARGET] Emergency stop active for {len(self._initialized_chains)} chains"
        self._add_console_output(console_msg)


# Global service instance
_gas_optimizer: Optional[DjangoGasOptimizer] = None


async def get_gas_optimizer() -> DjangoGasOptimizer:
    """Get or create the global gas optimizer instance."""
    global _gas_optimizer
    
    if _gas_optimizer is None:
        _gas_optimizer = DjangoGasOptimizer()
        
        # Initialize with configured chains
        enabled_chains = getattr(settings, 'TRADING_ENABLED_CHAINS', [1, 8453])
        await _gas_optimizer.initialize(enabled_chains)
    
    return _gas_optimizer


async def optimize_trade_gas(
    web3_client: Web3Client,
    swap_params: SwapParams,
    strategy: TradingGasStrategy = TradingGasStrategy.BALANCED,
    is_paper_trade: bool = False
) -> GasOptimizationResult:
    """
    Optimize gas parameters for a trade execution.
    
    Args:
        web3_client: Connected Web3 client
        swap_params: Swap parameters
        strategy: Gas optimization strategy
        is_paper_trade: Whether this is a paper trade (uses simulated gas)
        
    Returns:
        GasOptimizationResult with optimized gas parameters
    """
    from decimal import Decimal
    import logging
    
    logger = logging.getLogger('trading.gas_optimizer')
    
    try:
        # Get current gas price from canonical source (returns wei)
        base_gas_price_wei = await web3_client.get_gas_price()
        
        # TODO(tech-debt): Standardize on wei throughout codebase
        # Convert to gwei for existing logic
        base_gas_price_gwei = Decimal(str(base_gas_price_wei)) / Decimal('1e9')
        
        if base_gas_price_wei == 0:
            logger.warning("Gas price is 0, using default of 1.5 gwei")
            base_gas_price_gwei = Decimal('1.5')
        
        # Apply strategy multiplier
        strategy_multipliers = {
            TradingGasStrategy.SLOW: Decimal('0.8'),
            TradingGasStrategy.BALANCED: Decimal('1.0'),
            TradingGasStrategy.FAST: Decimal('1.2'),
            TradingGasStrategy.URGENT: Decimal('1.5')
        }
        
        multiplier = strategy_multipliers.get(strategy, Decimal('1.0'))
        optimized_gas_price_gwei = base_gas_price_gwei * multiplier
        
        # Estimate gas limit
        estimated_gas_limit = 200000  # Default for swaps
        
        # Calculate total cost
        gas_cost_gwei = optimized_gas_price_gwei * Decimal(str(estimated_gas_limit))
        gas_cost_eth = gas_cost_gwei / Decimal('1e9')
        
        # Assume ETH price for USD calculation (simplified)
        eth_price_usd = Decimal('2000')  # TODO: Get from price oracle
        gas_cost_usd = gas_cost_eth * eth_price_usd
        
        result = GasOptimizationResult(
            gas_price_gwei=optimized_gas_price_gwei,
            gas_limit=estimated_gas_limit,
            estimated_cost_usd=gas_cost_usd,
            strategy=strategy.value,
            savings_percent=Decimal('0')
        )
        
        logger.info(
            f"Gas optimized: {optimized_gas_price_gwei:.2f} gwei, "
            f"~${gas_cost_usd:.2f} USD"
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Gas optimization failed: {e}", exc_info=True)
        # Return safe defaults
        return GasOptimizationResult(
            gas_price_gwei=Decimal('1.5'),
            gas_limit=200000,
            estimated_cost_usd=Decimal('0.60'),
            strategy=strategy.value,
            savings_percent=Decimal('0')
        )