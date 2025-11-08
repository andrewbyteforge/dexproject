"""
Gas Optimization Engine Module

This module provides intelligent gas pricing and optimization strategies for the
Fast Lane execution path. It integrates with MEV protection recommendations and
real-time network conditions to ensure optimal transaction execution costs while
maintaining speed and security requirements.

Key Features:
- Dynamic gas pricing based on network conditions
- MEV protection-aware gas strategy selection
- EIP-1559 priority fee optimization
- Historical gas price analysis and prediction
- Multi-chain gas strategy support
- Cost-benefit analysis for execution decisions
- Integration with private relay requirements

File: dexproject/engine/execution/gas_optimizer.py
Django App: N/A (Pure engine component)
"""

import asyncio
import logging
import time
import statistics
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any, Union
from datetime import datetime, timedelta
from collections import defaultdict, deque

import aiohttp
from web3 import Web3
from web3.types import TxParams, Wei, BlockData
from eth_typing import HexStr

# Import engine components
from ..config import EngineConfig, get_config
from ..mempool.protection import ProtectionRecommendation, PriorityLevel, ProtectionAction
from ..communications.django_bridge import DjangoBridge
from shared.schemas import ChainType


logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS & CONSTANTS
# =============================================================================

class GasStrategy(str, Enum):
    """Gas pricing strategy types."""
    SPEED_OPTIMIZED = "speed_optimized"          # Maximum speed, higher cost
    COST_OPTIMIZED = "cost_optimized"            # Minimum cost, slower
    BALANCED = "balanced"                        # Balance of speed and cost
    MEV_PROTECTED = "mev_protected"              # MEV protection focused
    PRIVATE_RELAY = "private_relay"              # Private relay optimized
    AGGRESSIVE = "aggressive"                    # High gas for critical trades


class NetworkCongestion(str, Enum):
    """Network congestion levels."""
    LOW = "low"                 # <30% of block gas limit
    MEDIUM = "medium"           # 30-70% of block gas limit  
    HIGH = "high"               # 70-90% of block gas limit
    CRITICAL = "critical"       # >90% of block gas limit


class GasType(str, Enum):
    """Gas pricing mechanism types."""
    LEGACY = "legacy"           # Pre-EIP-1559 gasPrice
    EIP_1559 = "eip_1559"       # maxFeePerGas + maxPriorityFeePerGas


# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class GasMetrics:
    """Current network gas metrics."""
    
    base_fee: Decimal
    priority_fee_percentiles: Dict[int, Decimal]  # e.g., {10: 1.5, 50: 2.1, 90: 5.0}
    gas_used_ratio: float  # Percentage of block gas limit used
    congestion_level: NetworkCongestion
    block_number: int
    timestamp: datetime
    
    # Historical data
    avg_base_fee_1h: Optional[Decimal] = None
    avg_base_fee_24h: Optional[Decimal] = None
    base_fee_trend: Optional[str] = None  # "rising", "falling", "stable"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/storage."""
        return {
            "base_fee": str(self.base_fee),
            "priority_fee_percentiles": {k: str(v) for k, v in self.priority_fee_percentiles.items()},
            "gas_used_ratio": self.gas_used_ratio,
            "congestion_level": self.congestion_level.value,
            "block_number": self.block_number,
            "timestamp": self.timestamp.isoformat(),
            "avg_base_fee_1h": str(self.avg_base_fee_1h) if self.avg_base_fee_1h else None,
            "avg_base_fee_24h": str(self.avg_base_fee_24h) if self.avg_base_fee_24h else None,
            "base_fee_trend": self.base_fee_trend
        }


@dataclass
class GasRecommendation:
    """Gas pricing recommendation for transaction execution."""
    
    strategy: GasStrategy
    gas_type: GasType
    
    # Legacy gas pricing
    gas_price: Optional[Decimal] = None
    
    # EIP-1559 gas pricing
    max_fee_per_gas: Optional[Decimal] = None
    max_priority_fee_per_gas: Optional[Decimal] = None
    
    # Gas limit
    gas_limit: int = 200000
    
    # Cost analysis
    estimated_cost_eth: Optional[Decimal] = None
    estimated_execution_time_ms: Optional[int] = None
    confidence_level: float = 0.85
    
    # Justification
    reasoning: str = ""
    success_probability: float = 0.95
    
    def to_tx_params(self) -> Dict[str, Any]:
        """Convert recommendation to transaction parameters."""
        params = {"gas": self.gas_limit}
        
        if self.gas_type == GasType.LEGACY and self.gas_price:
            params["gasPrice"] = int(self.gas_price)
        elif self.gas_type == GasType.EIP_1559:
            if self.max_fee_per_gas:
                params["maxFeePerGas"] = int(self.max_fee_per_gas)
            if self.max_priority_fee_per_gas:
                params["maxPriorityFeePerGas"] = int(self.max_priority_fee_per_gas)
        
        return params
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/storage."""
        return {
            "strategy": self.strategy.value,
            "gas_type": self.gas_type.value,
            "gas_price": str(self.gas_price) if self.gas_price else None,
            "max_fee_per_gas": str(self.max_fee_per_gas) if self.max_fee_per_gas else None,
            "max_priority_fee_per_gas": str(self.max_priority_fee_per_gas) if self.max_priority_fee_per_gas else None,
            "gas_limit": self.gas_limit,
            "estimated_cost_eth": str(self.estimated_cost_eth) if self.estimated_cost_eth else None,
            "estimated_execution_time_ms": self.estimated_execution_time_ms,
            "confidence_level": self.confidence_level,
            "reasoning": self.reasoning,
            "success_probability": self.success_probability
        }


@dataclass 
class ChainGasConfig:
    """Chain-specific gas configuration."""
    
    chain_id: int
    supports_eip_1559: bool
    min_gas_price: Decimal
    max_gas_price: Decimal
    default_gas_limit: int
    block_time_seconds: float
    
    # Strategy-specific multipliers
    strategy_multipliers: Dict[GasStrategy, float] = field(default_factory=lambda: {
        GasStrategy.SPEED_OPTIMIZED: 2.0,
        GasStrategy.COST_OPTIMIZED: 0.8,
        GasStrategy.BALANCED: 1.1,
        GasStrategy.MEV_PROTECTED: 1.3,
        GasStrategy.PRIVATE_RELAY: 1.0,  # Private relay doesn't need gas competition
        GasStrategy.AGGRESSIVE: 2.5
    })


# =============================================================================
# GAS OPTIMIZATION ENGINE
# =============================================================================

class GasOptimizationEngine:
    """
    Advanced gas optimization engine for high-frequency trading execution.
    
    This engine analyzes real-time network conditions, integrates with MEV
    protection recommendations, and provides optimal gas pricing strategies
    to ensure fast, cost-effective transaction execution.
    """
    
    def __init__(self, engine_config: EngineConfig):
        """
        Initialize the gas optimization engine.
        
        Args:
            engine_config: Engine configuration instance
        """
        self.config = engine_config
        self.logger = logging.getLogger(f"{__name__}.GasOptimizationEngine")
        
        # Chain-specific configurations
        self._chain_configs: Dict[int, ChainGasConfig] = {}
        
        # Gas metrics tracking
        self._current_metrics: Dict[int, GasMetrics] = {}
        self._metrics_history: Dict[int, deque] = defaultdict(lambda: deque(maxlen=100))
        
        # Gas price prediction
        self._base_fee_predictions: Dict[int, deque] = defaultdict(lambda: deque(maxlen=20))
        self._priority_fee_predictions: Dict[int, deque] = defaultdict(lambda: deque(maxlen=20))
        
        # Performance tracking
        self._recommendation_count = 0
        self._successful_executions = 0
        self._cost_savings: Dict[str, Decimal] = defaultdict(Decimal)
        self._execution_latencies: deque = deque(maxlen=50)
        
        # HTTP session for gas price APIs
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Django communication bridge
        self._django_bridge: Optional[DjangoBridge] = None
        
        # Initialize chain configurations
        self._initialize_chain_configs()
        
        self.logger.info("Gas optimization engine initialized")
    
    async def initialize(self) -> None:
        """Initialize async components of the gas optimization engine."""
        # Create HTTP session for external gas APIs
        timeout = aiohttp.ClientTimeout(total=10, connect=5)
        connector = aiohttp.TCPConnector(
            limit=50,
            limit_per_host=20,
            keepalive_timeout=30,
            enable_cleanup_closed=True
        )
        
        self._session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={'User-Agent': 'DEX-AutoTrading-Bot/1.0'}
        )
        
        # Initialize Django bridge if available
        try:
            self._django_bridge = DjangoBridge("gas_optimizer")
            await self._django_bridge.initialize()
            self.logger.info("Django bridge initialized for gas optimizer")
        except Exception as e:
            self.logger.warning(f"Could not initialize Django bridge: {e}")
        
        # Start gas metrics monitoring for enabled chains
        for chain_id in self.config.chain_configs.keys():
            asyncio.create_task(self._monitor_gas_metrics(chain_id))
        
        self.logger.info("Gas optimization engine async initialization complete")
    
    async def shutdown(self) -> None:
        """Cleanup resources and close connections."""
        if self._session:
            await self._session.close()
            
        if self._django_bridge:
            await self._django_bridge.disconnect()
        
        self.logger.info("Gas optimization engine shutdown complete")
    
    def _initialize_chain_configs(self) -> None:
        """Initialize chain-specific gas configurations."""
        # Ethereum Mainnet
        if 1 in self.config.chain_configs:
            self._chain_configs[1] = ChainGasConfig(
                chain_id=1,
                supports_eip_1559=True,
                min_gas_price=Decimal('1000000000'),    # 1 gwei
                max_gas_price=Decimal('500000000000'),  # 500 gwei
                default_gas_limit=200000,
                block_time_seconds=12.0
            )
        
        # Base Mainnet
        if 8453 in self.config.chain_configs:
            self._chain_configs[8453] = ChainGasConfig(
                chain_id=8453,
                supports_eip_1559=True,
                min_gas_price=Decimal('1000000'),       # 0.001 gwei
                max_gas_price=Decimal('10000000000'),   # 10 gwei
                default_gas_limit=200000,
                block_time_seconds=2.0
            )
        
        self.logger.info(f"Initialized gas configs for {len(self._chain_configs)} chains")
    
    async def get_optimal_gas_recommendation(
        self,
        chain_id: int,
        transaction: TxParams,
        mev_protection: Optional[ProtectionRecommendation] = None,
        target_execution_time_ms: Optional[int] = None
    ) -> GasRecommendation:
        """
        Get optimal gas recommendation for transaction execution.
        
        Args:
            chain_id: Target blockchain network
            transaction: Transaction parameters
            mev_protection: MEV protection recommendation (optional)
            target_execution_time_ms: Target execution time (optional)
            
        Returns:
            Optimal gas pricing recommendation
        """
        start_time = time.time()
        
        try:
            # Get current gas metrics for the chain
            metrics = await self._get_current_gas_metrics(chain_id)
            
            # Determine strategy based on MEV protection and requirements
            strategy = self._determine_gas_strategy(
                mev_protection, target_execution_time_ms, metrics
            )
            
            # Generate gas recommendation based on strategy
            recommendation = await self._generate_gas_recommendation(
                chain_id, strategy, metrics, transaction
            )
            
            # Apply MEV protection adjustments if needed
            if mev_protection:
                recommendation = self._apply_mev_adjustments(
                    recommendation, mev_protection
                )
            
            # Track performance
            latency_ms = (time.time() - start_time) * 1000
            self._execution_latencies.append(latency_ms)
            self._recommendation_count += 1
            
            self.logger.info(
                f"Generated gas recommendation for chain {chain_id}: "
                f"{recommendation.strategy.value}, "
                f"estimated cost: {recommendation.estimated_cost_eth} ETH"
            )
            
            # Send metrics to Django
            if self._django_bridge:
                await self._send_gas_metrics(chain_id, recommendation, metrics)
            
            return recommendation
            
        except Exception as e:
            self.logger.error(f"Gas optimization failed: {e}")
            
            # Return safe fallback recommendation
            return self._get_fallback_recommendation(chain_id, transaction)
    
    async def _get_current_gas_metrics(self, chain_id: int) -> GasMetrics:
        """
        Get current gas metrics for the specified chain.
        
        Args:
            chain_id: Target blockchain network
            
        Returns:
            Current gas metrics
        """
        # Check if we have recent cached metrics
        if chain_id in self._current_metrics:
            cached_metrics = self._current_metrics[chain_id]
            age = datetime.utcnow() - cached_metrics.timestamp
            
            if age.total_seconds() < 30:  # Use cached if less than 30 seconds old
                return cached_metrics
        
        # Fetch fresh metrics
        try:
            if chain_id == 1:  # Ethereum mainnet
                metrics = await self._fetch_ethereum_gas_metrics()
            elif chain_id == 8453:  # Base mainnet
                metrics = await self._fetch_base_gas_metrics()
            else:
                # Fallback to generic metrics
                metrics = await self._fetch_generic_gas_metrics(chain_id)
            
            # Cache the metrics
            self._current_metrics[chain_id] = metrics
            self._metrics_history[chain_id].append(metrics)
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"Failed to fetch gas metrics for chain {chain_id}: {e}")
            
            # Return last known metrics or defaults
            if chain_id in self._current_metrics:
                return self._current_metrics[chain_id]
            else:
                return self._get_default_gas_metrics(chain_id)
    
    async def _fetch_ethereum_gas_metrics(self) -> GasMetrics:
        """Fetch gas metrics for Ethereum mainnet."""
        # This would integrate with services like:
        # - Alchemy Gas Price API
        # - Etherscan Gas Tracker
        # - Direct Web3 calls to latest blocks
        
        # Placeholder implementation with realistic values
        base_fee = Decimal('25000000000')  # 25 gwei
        priority_fees = {
            10: Decimal('1000000000'),   # 1 gwei
            50: Decimal('2000000000'),   # 2 gwei
            90: Decimal('5000000000')    # 5 gwei
        }
        
        return GasMetrics(
            base_fee=base_fee,
            priority_fee_percentiles=priority_fees,
            gas_used_ratio=0.65,  # 65% block utilization
            congestion_level=NetworkCongestion.MEDIUM,
            block_number=18500000,
            timestamp=datetime.utcnow(),
            avg_base_fee_1h=Decimal('23000000000'),
            avg_base_fee_24h=Decimal('22000000000'),
            base_fee_trend="rising"
        )
    
    async def _fetch_base_gas_metrics(self) -> GasMetrics:
        """Fetch gas metrics for Base mainnet."""
        # Base typically has much lower gas costs
        base_fee = Decimal('50000000')  # 0.05 gwei
        priority_fees = {
            10: Decimal('10000000'),    # 0.01 gwei
            50: Decimal('50000000'),    # 0.05 gwei
            90: Decimal('100000000')    # 0.1 gwei
        }
        
        return GasMetrics(
            base_fee=base_fee,
            priority_fee_percentiles=priority_fees,
            gas_used_ratio=0.30,  # Lower congestion
            congestion_level=NetworkCongestion.LOW,
            block_number=8500000,
            timestamp=datetime.utcnow(),
            avg_base_fee_1h=Decimal('48000000'),
            avg_base_fee_24h=Decimal('45000000'),
            base_fee_trend="stable"
        )
    
    async def _fetch_generic_gas_metrics(self, chain_id: int) -> GasMetrics:
        """Fetch gas metrics for any chain using generic approach."""
        # This would use Web3 connection to fetch recent blocks
        # and calculate gas metrics
        
        chain_config = self._chain_configs.get(chain_id)
        if not chain_config:
            raise ValueError(f"No configuration for chain {chain_id}")
        
        # Placeholder implementation
        base_fee = chain_config.min_gas_price * 10
        priority_fees = {
            10: base_fee // 20,
            50: base_fee // 10,
            90: base_fee // 5
        }
        
        return GasMetrics(
            base_fee=base_fee,
            priority_fee_percentiles=priority_fees,
            gas_used_ratio=0.50,
            congestion_level=NetworkCongestion.MEDIUM,
            block_number=1000000,
            timestamp=datetime.utcnow()
        )
    
    def _get_default_gas_metrics(self, chain_id: int) -> GasMetrics:
        """Get default gas metrics when fetching fails."""
        chain_config = self._chain_configs.get(chain_id)
        if not chain_config:
            # Ultra-safe defaults
            base_fee = Decimal('20000000000')  # 20 gwei
        else:
            base_fee = chain_config.min_gas_price * 5
        
        priority_fees = {
            10: base_fee // 20,
            50: base_fee // 10,
            90: base_fee // 5
        }
        
        return GasMetrics(
            base_fee=base_fee,
            priority_fee_percentiles=priority_fees,
            gas_used_ratio=0.80,  # Assume high congestion for safety
            congestion_level=NetworkCongestion.HIGH,
            block_number=0,
            timestamp=datetime.utcnow()
        )
    
    def _determine_gas_strategy(
        self,
        mev_protection: Optional[ProtectionRecommendation],
        target_execution_time_ms: Optional[int],
        metrics: GasMetrics
    ) -> GasStrategy:
        """
        Determine the optimal gas strategy based on requirements and conditions.
        
        Args:
            mev_protection: MEV protection recommendation
            target_execution_time_ms: Target execution time
            metrics: Current gas metrics
            
        Returns:
            Recommended gas strategy
        """
        # MEV protection takes precedence
        if mev_protection:
            if mev_protection.use_private_relay:
                return GasStrategy.PRIVATE_RELAY
            elif mev_protection.priority_level == PriorityLevel.CRITICAL:
                return GasStrategy.AGGRESSIVE
            elif mev_protection.action == ProtectionAction.INCREASE_GAS:
                return GasStrategy.MEV_PROTECTED
        
        # Fast Lane requirements
        if target_execution_time_ms and target_execution_time_ms < 500:
            return GasStrategy.SPEED_OPTIMIZED
        elif target_execution_time_ms and target_execution_time_ms < 2000:
            return GasStrategy.BALANCED
        
        # Network congestion considerations
        if metrics.congestion_level == NetworkCongestion.CRITICAL:
            return GasStrategy.SPEED_OPTIMIZED
        elif metrics.congestion_level == NetworkCongestion.LOW:
            return GasStrategy.COST_OPTIMIZED
        
        # Default balanced approach
        return GasStrategy.BALANCED
    
    async def _generate_gas_recommendation(
        self,
        chain_id: int,
        strategy: GasStrategy,
        metrics: GasMetrics,
        transaction: TxParams
    ) -> GasRecommendation:
        """
        Generate gas recommendation based on strategy and metrics.
        
        Args:
            chain_id: Target blockchain
            strategy: Selected gas strategy
            metrics: Current gas metrics
            transaction: Transaction parameters
            
        Returns:
            Gas pricing recommendation
        """
        chain_config = self._chain_configs[chain_id]
        
        # Determine gas type
        gas_type = GasType.EIP_1559 if chain_config.supports_eip_1559 else GasType.LEGACY
        
        # Get strategy multiplier
        multiplier = chain_config.strategy_multipliers.get(strategy, 1.1)
        
        # Calculate gas parameters based on type
        if gas_type == GasType.EIP_1559:
            return await self._generate_eip1559_recommendation(
                strategy, metrics, multiplier, transaction
            )
        else:
            return await self._generate_legacy_recommendation(
                strategy, metrics, multiplier, transaction
            )
    
    async def _generate_eip1559_recommendation(
        self,
        strategy: GasStrategy,
        metrics: GasMetrics,
        multiplier: float,
        transaction: TxParams
    ) -> GasRecommendation:
        """Generate EIP-1559 gas recommendation."""
        base_fee = metrics.base_fee
        
        # Select priority fee based on strategy
        if strategy == GasStrategy.SPEED_OPTIMIZED:
            priority_fee = metrics.priority_fee_percentiles[90] * Decimal(str(multiplier))
        elif strategy == GasStrategy.AGGRESSIVE:
            priority_fee = metrics.priority_fee_percentiles[90] * Decimal('2.0')
        elif strategy == GasStrategy.PRIVATE_RELAY:
            # Private relay doesn't need high priority fees
            priority_fee = metrics.priority_fee_percentiles[10]
        elif strategy == GasStrategy.COST_OPTIMIZED:
            priority_fee = metrics.priority_fee_percentiles[10]
        else:  # BALANCED, MEV_PROTECTED
            priority_fee = metrics.priority_fee_percentiles[50] * Decimal(str(multiplier))
        
        # Calculate max fee per gas (base fee buffer + priority fee)
        base_fee_buffer = self._calculate_base_fee_buffer(base_fee, strategy)
        max_fee_per_gas = base_fee + base_fee_buffer + priority_fee
        
        # Estimate gas limit
        gas_limit = self._estimate_gas_limit(transaction)
        
        # Calculate cost estimate
        estimated_cost = (base_fee + priority_fee) * gas_limit / Decimal('1e18')
        
        # Estimate execution time based on strategy and congestion
        estimated_time_ms = self._estimate_execution_time(strategy, metrics)
        
        return GasRecommendation(
            strategy=strategy,
            gas_type=GasType.EIP_1559,
            max_fee_per_gas=max_fee_per_gas,
            max_priority_fee_per_gas=priority_fee,
            gas_limit=gas_limit,
            estimated_cost_eth=estimated_cost,
            estimated_execution_time_ms=estimated_time_ms,
            confidence_level=self._calculate_confidence_level(strategy, metrics),
            reasoning=self._generate_reasoning(strategy, metrics),
            success_probability=self._calculate_success_probability(strategy, metrics)
        )
    
    async def _generate_legacy_recommendation(
        self,
        strategy: GasStrategy,
        metrics: GasMetrics,
        multiplier: float,
        transaction: TxParams
    ) -> GasRecommendation:
        """Generate legacy gas price recommendation."""
        # For legacy chains, use base fee as gas price baseline
        base_gas_price = metrics.base_fee
        
        # Apply strategy-based adjustments
        if strategy == GasStrategy.SPEED_OPTIMIZED:
            gas_price = base_gas_price * Decimal('2.0') * Decimal(str(multiplier))
        elif strategy == GasStrategy.AGGRESSIVE:
            gas_price = base_gas_price * Decimal('3.0')
        elif strategy == GasStrategy.COST_OPTIMIZED:
            gas_price = base_gas_price * Decimal('0.9')
        else:  # BALANCED, MEV_PROTECTED, PRIVATE_RELAY
            gas_price = base_gas_price * Decimal(str(multiplier))
        
        # Estimate gas limit
        gas_limit = self._estimate_gas_limit(transaction)
        
        # Calculate cost estimate
        estimated_cost = gas_price * gas_limit / Decimal('1e18')
        
        # Estimate execution time
        estimated_time_ms = self._estimate_execution_time(strategy, metrics)
        
        return GasRecommendation(
            strategy=strategy,
            gas_type=GasType.LEGACY,
            gas_price=gas_price,
            gas_limit=gas_limit,
            estimated_cost_eth=estimated_cost,
            estimated_execution_time_ms=estimated_time_ms,
            confidence_level=self._calculate_confidence_level(strategy, metrics),
            reasoning=self._generate_reasoning(strategy, metrics),
            success_probability=self._calculate_success_probability(strategy, metrics)
        )
    
    def _calculate_base_fee_buffer(self, base_fee: Decimal, strategy: GasStrategy) -> Decimal:
        """
        Calculate base fee buffer for EIP-1559 transactions.
        
        Args:
            base_fee: Current base fee
            strategy: Gas strategy
            
        Returns:
            Buffer amount to add to base fee
        """
        if strategy == GasStrategy.SPEED_OPTIMIZED:
            return base_fee * Decimal('0.5')  # 50% buffer
        elif strategy == GasStrategy.AGGRESSIVE:
            return base_fee * Decimal('1.0')  # 100% buffer
        elif strategy == GasStrategy.PRIVATE_RELAY:
            return base_fee * Decimal('0.1')  # 10% buffer (less competition)
        elif strategy == GasStrategy.COST_OPTIMIZED:
            return base_fee * Decimal('0.125')  # 12.5% buffer (standard)
        else:  # BALANCED, MEV_PROTECTED
            return base_fee * Decimal('0.25')  # 25% buffer
    
    def _estimate_gas_limit(self, transaction: TxParams) -> int:
        """
        Estimate gas limit for the transaction.
        
        Args:
            transaction: Transaction parameters
            
        Returns:
            Estimated gas limit
        """
        # Check if gas limit is already specified
        if 'gas' in transaction:
            return int(transaction['gas'])
        
        # Estimate based on transaction type
        if transaction.get('data') and transaction['data'] != '0x':
            data_length = len(transaction['data']) // 2 - 1  # Remove 0x prefix
            
            # Complex contract interactions
            if data_length > 1000:
                return 300000
            elif data_length > 100:
                return 200000
            else:
                return 100000
        else:
            # Simple ETH transfers
            return 21000
    
    def _estimate_execution_time(
        self, 
        strategy: GasStrategy, 
        metrics: GasMetrics
    ) -> int:
        """
        Estimate transaction execution time in milliseconds.
        
        Args:
            strategy: Gas strategy
            metrics: Current network metrics
            
        Returns:
            Estimated execution time in milliseconds
        """
        # Base execution time based on network congestion
        base_time_map = {
            NetworkCongestion.LOW: 5000,      # 5 seconds
            NetworkCongestion.MEDIUM: 15000,  # 15 seconds
            NetworkCongestion.HIGH: 60000,    # 1 minute
            NetworkCongestion.CRITICAL: 300000 # 5 minutes
        }
        
        base_time = base_time_map.get(metrics.congestion_level, 15000)
        
        # Strategy-based adjustments
        strategy_multipliers = {
            GasStrategy.SPEED_OPTIMIZED: 0.2,
            GasStrategy.AGGRESSIVE: 0.1,
            GasStrategy.BALANCED: 0.5,
            GasStrategy.MEV_PROTECTED: 0.4,
            GasStrategy.PRIVATE_RELAY: 0.3,  # Private relays are typically faster
            GasStrategy.COST_OPTIMIZED: 1.5
        }
        
        multiplier = strategy_multipliers.get(strategy, 0.5)
        return int(base_time * multiplier)
    
    def _calculate_confidence_level(
        self, 
        strategy: GasStrategy, 
        metrics: GasMetrics
    ) -> float:
        """
        Calculate confidence level for the recommendation.
        
        Args:
            strategy: Gas strategy
            metrics: Current network metrics
            
        Returns:
            Confidence level (0.0 to 1.0)
        """
        base_confidence = 0.85
        
        # Adjust based on data quality
        if metrics.avg_base_fee_1h and metrics.base_fee_trend:
            base_confidence += 0.1  # Good historical data
        
        # Adjust based on network stability
        if metrics.congestion_level == NetworkCongestion.LOW:
            base_confidence += 0.05
        elif metrics.congestion_level == NetworkCongestion.CRITICAL:
            base_confidence -= 0.15
        
        # Strategy-specific confidence
        if strategy == GasStrategy.PRIVATE_RELAY:
            base_confidence += 0.1  # Private relays are more predictable
        elif strategy == GasStrategy.COST_OPTIMIZED:
            base_confidence -= 0.05  # Lower gas might delay execution
        
        return min(max(base_confidence, 0.5), 1.0)
    
    def _calculate_success_probability(
        self, 
        strategy: GasStrategy, 
        metrics: GasMetrics
    ) -> float:
        """
        Calculate probability of successful execution.
        
        Args:
            strategy: Gas strategy
            metrics: Current network metrics
            
        Returns:
            Success probability (0.0 to 1.0)
        """
        # Base success rate depends on strategy aggressiveness
        base_rates = {
            GasStrategy.AGGRESSIVE: 0.99,
            GasStrategy.SPEED_OPTIMIZED: 0.95,
            GasStrategy.MEV_PROTECTED: 0.93,
            GasStrategy.PRIVATE_RELAY: 0.97,
            GasStrategy.BALANCED: 0.90,
            GasStrategy.COST_OPTIMIZED: 0.75
        }
        
        base_rate = base_rates.get(strategy, 0.90)
        
        # Adjust based on network congestion
        congestion_penalties = {
            NetworkCongestion.LOW: 0.0,
            NetworkCongestion.MEDIUM: -0.02,
            NetworkCongestion.HIGH: -0.08,
            NetworkCongestion.CRITICAL: -0.15
        }
        
        penalty = congestion_penalties.get(metrics.congestion_level, -0.05)
        
        return max(base_rate + penalty, 0.5)
    
    def _generate_reasoning(self, strategy: GasStrategy, metrics: GasMetrics) -> str:
        """
        Generate human-readable reasoning for the gas recommendation.
        
        Args:
            strategy: Selected gas strategy
            metrics: Current network metrics
            
        Returns:
            Reasoning explanation
        """
        congestion_desc = {
            NetworkCongestion.LOW: "low network congestion",
            NetworkCongestion.MEDIUM: "moderate network congestion",
            NetworkCongestion.HIGH: "high network congestion",
            NetworkCongestion.CRITICAL: "critical network congestion"
        }.get(metrics.congestion_level, "unknown congestion")
        
        strategy_desc = {
            GasStrategy.SPEED_OPTIMIZED: "speed-optimized strategy for fast execution",
            GasStrategy.AGGRESSIVE: "aggressive strategy for critical transactions",
            GasStrategy.BALANCED: "balanced strategy for cost-effective execution",
            GasStrategy.MEV_PROTECTED: "MEV protection with increased gas price",
            GasStrategy.PRIVATE_RELAY: "private relay routing with optimized gas",
            GasStrategy.COST_OPTIMIZED: "cost-optimized strategy for patient execution"
        }.get(strategy, "standard strategy")
        
        base_fee_gwei = float(metrics.base_fee) / 1e9
        trend_info = f", base fee trending {metrics.base_fee_trend}" if metrics.base_fee_trend else ""
        
        return (
            f"Using {strategy_desc} based on {congestion_desc} "
            f"(base fee: {base_fee_gwei:.1f} gwei{trend_info})"
        )
    
    def _apply_mev_adjustments(
        self,
        recommendation: GasRecommendation,
        mev_protection: ProtectionRecommendation
    ) -> GasRecommendation:
        """
        Apply MEV protection adjustments to gas recommendation.
        
        Args:
            recommendation: Base gas recommendation
            mev_protection: MEV protection requirements
            
        Returns:
            Adjusted gas recommendation
        """
        # Apply gas price multiplier from MEV protection
        multiplier = Decimal(str(mev_protection.gas_price_multiplier))
        
        if recommendation.gas_type == GasType.EIP_1559:
            if recommendation.max_fee_per_gas:
                recommendation.max_fee_per_gas = recommendation.max_fee_per_gas * multiplier
            if recommendation.max_priority_fee_per_gas:
                recommendation.max_priority_fee_per_gas = recommendation.max_priority_fee_per_gas * multiplier
        else:
            if recommendation.gas_price:
                recommendation.gas_price = recommendation.gas_price * multiplier
        
        # Update cost estimate
        if recommendation.estimated_cost_eth:
            recommendation.estimated_cost_eth = recommendation.estimated_cost_eth * multiplier
        
        # Update reasoning
        recommendation.reasoning += f" | MEV protection applied (×{mev_protection.gas_price_multiplier})"
        
        return recommendation
    
    def _get_fallback_recommendation(
        self, 
        chain_id: int, 
        transaction: TxParams
    ) -> GasRecommendation:
        """
        Get safe fallback recommendation when optimization fails.
        
        Args:
            chain_id: Target blockchain
            transaction: Transaction parameters
            
        Returns:
            Safe fallback gas recommendation
        """
        chain_config = self._chain_configs.get(chain_id)
        
        if chain_config and chain_config.supports_eip_1559:
            # EIP-1559 fallback
            base_fee = chain_config.min_gas_price * 20  # Conservative estimate
            priority_fee = chain_config.min_gas_price * 2
            max_fee = base_fee * 2 + priority_fee
            
            return GasRecommendation(
                strategy=GasStrategy.BALANCED,
                gas_type=GasType.EIP_1559,
                max_fee_per_gas=max_fee,
                max_priority_fee_per_gas=priority_fee,
                gas_limit=self._estimate_gas_limit(transaction),
                reasoning="Fallback recommendation due to optimization failure"
            )
        else:
            # Legacy fallback
            gas_price = (chain_config.min_gas_price * 25 
                        if chain_config else Decimal('25000000000'))
            
            return GasRecommendation(
                strategy=GasStrategy.BALANCED,
                gas_type=GasType.LEGACY,
                gas_price=gas_price,
                gas_limit=self._estimate_gas_limit(transaction),
                reasoning="Fallback recommendation due to optimization failure"
            )
    
    async def _monitor_gas_metrics(self, chain_id: int) -> None:
        """
        Background task to monitor gas metrics for a specific chain.
        
        Args:
            chain_id: Chain to monitor
        """
        self.logger.info(f"Starting gas metrics monitoring for chain {chain_id}")
        
        while True:
            try:
                # Update gas metrics every 30 seconds
                await self._get_current_gas_metrics(chain_id)
                await asyncio.sleep(30)
                
            except Exception as e:
                self.logger.error(f"Gas metrics monitoring error for chain {chain_id}: {e}")
                await asyncio.sleep(60)  # Wait longer on error
    
    async def _send_gas_metrics(
        self,
        chain_id: int,
        recommendation: GasRecommendation,
        metrics: GasMetrics
    ) -> None:
        """Send gas metrics to Django backend."""
        if not self._django_bridge:
            return
        
        try:
            metrics_data = {
                "component": "gas_optimizer",
                "chain_id": chain_id,
                "timestamp": datetime.utcnow().isoformat(),
                "recommendation": recommendation.to_dict(),
                "network_metrics": metrics.to_dict(),
                "performance": {
                    "recommendation_count": self._recommendation_count,
                    "successful_executions": self._successful_executions,
                    "avg_latency_ms": (
                        sum(self._execution_latencies) / len(self._execution_latencies)
                        if self._execution_latencies else 0
                    )
                }
            }
            
            self.logger.debug(f"Sending gas metrics to Django: {metrics_data}")
            
        except Exception as e:
            self.logger.error(f"Failed to send gas metrics to Django: {e}")
    
    async def optimize_gas_for_batch(
        self,
        transactions: List[TxParams],
        chain_id: int,
        target_execution_time_ms: Optional[int] = None
    ) -> List[GasRecommendation]:
        """
        Optimize gas for a batch of transactions with shared strategy.
        
        Args:
            transactions: List of transactions to optimize
            chain_id: Target blockchain network
            target_execution_time_ms: Target execution time for batch
            
        Returns:
            List of gas recommendations for each transaction
        """
        recommendations = []
        
        # Get shared metrics to avoid redundant API calls
        metrics = await self._get_current_gas_metrics(chain_id)
        
        # Determine shared strategy for batch efficiency
        shared_strategy = self._determine_gas_strategy(
            None, target_execution_time_ms, metrics
        )
        
        # Generate recommendations for each transaction
        for transaction in transactions:
            try:
                recommendation = await self._generate_gas_recommendation(
                    chain_id, shared_strategy, metrics, transaction
                )
                recommendations.append(recommendation)
                
            except Exception as e:
                self.logger.error(f"Failed to optimize gas for transaction: {e}")
                fallback = self._get_fallback_recommendation(chain_id, transaction)
                recommendations.append(fallback)
        
        self.logger.info(f"Generated {len(recommendations)} gas recommendations for batch")
        return recommendations
    
    def get_optimization_statistics(self) -> Dict[str, Any]:
        """
        Get gas optimization performance statistics.
        
        Returns:
            Dictionary containing optimization statistics
        """
        avg_latency = (
            sum(self._execution_latencies) / len(self._execution_latencies)
            if self._execution_latencies else 0.0
        )
        
        success_rate = (
            self._successful_executions / self._recommendation_count
            if self._recommendation_count > 0 else 0.0
        )
        
        total_savings = sum(self._cost_savings.values())
        
        return {
            "recommendations_generated": self._recommendation_count,
            "successful_executions": self._successful_executions,
            "success_rate": success_rate,
            "average_latency_ms": avg_latency,
            "total_cost_savings_eth": str(total_savings),
            "chains_monitored": len(self._chain_configs),
            "active_gas_monitoring": len(self._current_metrics),
            "metrics_history_size": sum(len(history) for history in self._metrics_history.values())
        }
    
    def record_execution_success(
        self, 
        recommendation: GasRecommendation,
        actual_cost: Decimal,
        execution_time_ms: int
    ) -> None:
        """
        Record successful execution for performance tracking.
        
        Args:
            recommendation: Original gas recommendation
            actual_cost: Actual transaction cost
            execution_time_ms: Actual execution time
        """
        self._successful_executions += 1
        
        # Calculate cost savings compared to aggressive strategy
        if recommendation.estimated_cost_eth:
            # Estimate what aggressive strategy would have cost
            aggressive_cost = recommendation.estimated_cost_eth * Decimal('2.0')
            savings = aggressive_cost - actual_cost
            
            if savings > 0:
                strategy_key = recommendation.strategy.value
                self._cost_savings[strategy_key] += savings
        
        self.logger.info(
            f"Recorded successful execution: {recommendation.strategy.value}, "
            f"cost: {actual_cost} ETH, time: {execution_time_ms}ms"
        )


# =============================================================================
# GAS MONITORING UTILITIES
# =============================================================================

async def _monitor_gas_metrics(chain_id: int) -> None:
    """
    Background task to continuously monitor gas metrics.
    
    This function runs as a separate asyncio task to provide real-time
    gas price monitoring for the optimization engine.
    """
    logger.info(f"Starting continuous gas monitoring for chain {chain_id}")
    
    while True:
        try:
            # This would be implemented to fetch real-time gas data
            await asyncio.sleep(15)  # Update every 15 seconds
            
        except Exception as e:
            logger.error(f"Gas monitoring error for chain {chain_id}: {e}")
            await asyncio.sleep(60)


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

async def create_gas_optimization_engine() -> GasOptimizationEngine:
    """
    Factory function to create and initialize a GasOptimizationEngine.
    
    Returns:
        Fully initialized GasOptimizationEngine instance
    """
    config = await get_config()
    engine = GasOptimizationEngine(config)
    await engine.initialize()
    return engine


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    'GasOptimizationEngine',
    'GasRecommendation',
    'GasMetrics',
    'ChainGasConfig',
    'GasStrategy',
    'NetworkCongestion',
    'GasType',
    'create_gas_optimization_engine'
]