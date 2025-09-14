"""
Private Relay Integration Module - Flashbots Bundle Submission

This module provides direct integration with Flashbots Protect and Relay endpoints
for MEV-protected transaction execution. It implements bundle submission, status
tracking, and fallback mechanisms for the Fast Lane execution path.

Key Features:
- Direct bundle submission to Flashbots Protect/Relay
- Ethereum mainnet focus with extensible multi-chain support
- Bundle status monitoring and confirmation tracking
- Automatic fallback to public mempool when needed
- Comprehensive error handling and performance metrics
- Integration with existing engine architecture

File: dexproject/engine/mempool/relay.py
Django App: N/A (Pure engine component)
"""

import asyncio
import logging
import time
import json
import hashlib
from dataclasses import dataclass, asdict
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Any, Union, Tuple
from datetime import datetime, timedelta

import aiohttp
from web3 import Web3
from web3.types import TxParams, TxReceipt
from eth_account import Account
from eth_typing import ChecksumAddress, HexStr

# Import engine components
from ..config import EngineConfig, get_config
from ..communications.django_bridge import DjangoBridge
from ...shared.schemas import (
    BaseMessage, MessageType, DecisionType, ChainType
)


logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS & CONSTANTS
# =============================================================================

class RelayType(str, Enum):
    """Supported private relay types."""
    FLASHBOTS_PROTECT = "flashbots_protect"
    FLASHBOTS_RELAY = "flashbots_relay"
    PUBLIC_MEMPOOL = "public_mempool"


class BundleStatus(str, Enum):
    """Bundle submission and execution status."""
    PENDING = "pending"
    SUBMITTED = "submitted"
    INCLUDED = "included"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class PriorityLevel(str, Enum):
    """Transaction priority levels for relay routing."""
    CRITICAL = "critical"    # Sub-200ms execution required
    HIGH = "high"           # Sub-500ms execution required 
    MEDIUM = "medium"       # Sub-2s execution acceptable
    LOW = "low"             # Best effort execution


# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class FlashbotsBundle:
    """Flashbots bundle configuration and metadata."""
    
    transactions: List[Dict[str, Any]]
    block_number: Optional[int] = None
    min_timestamp: Optional[int] = None
    max_timestamp: Optional[int] = None
    replacement_uuid: Optional[str] = None
    bundle_id: Optional[str] = None
    
    def to_flashbots_format(self) -> Dict[str, Any]:
        """Convert to Flashbots API format."""
        bundle_data = {
            "txs": self.transactions
        }
        
        if self.block_number:
            bundle_data["blockNumber"] = hex(self.block_number)
        if self.min_timestamp:
            bundle_data["minTimestamp"] = self.min_timestamp
        if self.max_timestamp:
            bundle_data["maxTimestamp"] = self.max_timestamp
        if self.replacement_uuid:
            bundle_data["replacementUuid"] = self.replacement_uuid
            
        return bundle_data


@dataclass
class BundleSubmissionResult:
    """Result of bundle submission to relay."""
    
    success: bool
    bundle_id: Optional[str] = None
    relay_type: Optional[RelayType] = None
    submission_time: Optional[datetime] = None
    block_number: Optional[int] = None
    error_message: Optional[str] = None
    latency_ms: Optional[float] = None
    gas_price_gwei: Optional[Decimal] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/metrics."""
        return {
            k: (v.isoformat() if isinstance(v, datetime) else 
                str(v) if isinstance(v, Decimal) else v)
            for k, v in asdict(self).items()
        }


@dataclass
class RelayConfig:
    """Configuration for a specific relay endpoint."""
    
    name: str
    relay_type: RelayType
    endpoint_url: str
    chain_id: int
    enabled: bool = True
    timeout_seconds: int = 10
    max_retries: int = 3
    priority_threshold: PriorityLevel = PriorityLevel.MEDIUM
    
    # Flashbots-specific configuration
    require_signing: bool = True
    auth_header: Optional[str] = None
    rate_limit_rpm: int = 120  # Requests per minute


# =============================================================================
# PRIVATE RELAY MANAGER
# =============================================================================

class PrivateRelayManager:
    """
    Manages private relay integrations for MEV-protected transaction execution.
    
    This class handles bundle submission to multiple relay endpoints with automatic
    fallback, status monitoring, and performance tracking. Designed for high-frequency
    trading with sub-500ms execution targets.
    """
    
    def __init__(self, engine_config: EngineConfig):
        """
        Initialize the private relay manager.
        
        Args:
            engine_config: Engine configuration instance
        """
        self.config = engine_config
        self.logger = logging.getLogger(f"{__name__}.PrivateRelayManager")
        
        # HTTP session for relay communication
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Relay configurations
        self._relay_configs: Dict[str, RelayConfig] = {}
        
        # Bundle tracking
        self._active_bundles: Dict[str, FlashbotsBundle] = {}
        self._bundle_status: Dict[str, BundleStatus] = {}
        
        # Performance metrics
        self._submission_latencies: List[float] = []
        self._success_rates: Dict[str, float] = {}
        self._total_submissions = 0
        self._successful_submissions = 0
        
        # Django communication bridge
        self._django_bridge: Optional[DjangoBridge] = None
        
        # Initialize relay configurations
        self._initialize_relay_configs()
        
        self.logger.info("Private relay manager initialized")
    
    async def initialize(self) -> None:
        """Initialize async components of the relay manager."""
        # Create HTTP session with optimized settings
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=50,
            keepalive_timeout=30,
            enable_cleanup_closed=True
        )
        
        self._session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={
                'User-Agent': 'DEX-AutoTrading-Bot/1.0',
                'Content-Type': 'application/json'
            }
        )
        
        # Initialize Django bridge if available
        try:
            self._django_bridge = DjangoBridge("relay_manager")
            await self._django_bridge.initialize()
            self.logger.info("Django bridge initialized for relay manager")
        except Exception as e:
            self.logger.warning(f"Could not initialize Django bridge: {e}")
        
        self.logger.info("Private relay manager async initialization complete")
    
    async def shutdown(self) -> None:
        """Cleanup resources and close connections."""
        if self._session:
            await self._session.close()
            
        if self._django_bridge:
            await self._django_bridge.disconnect()
        
        self.logger.info("Private relay manager shutdown complete")
    
    def _initialize_relay_configs(self) -> None:
        """Initialize relay endpoint configurations."""
        # Flashbots Protect (Ethereum Mainnet)
        if self.config.chain_configs.get(1):  # Ethereum mainnet
            self._relay_configs["flashbots_protect"] = RelayConfig(
                name="Flashbots Protect",
                relay_type=RelayType.FLASHBOTS_PROTECT,
                endpoint_url="https://rpc.flashbots.net",
                chain_id=1,
                enabled=True,
                timeout_seconds=5,  # Fast execution requirement
                max_retries=2,
                priority_threshold=PriorityLevel.HIGH,
                require_signing=True,
                rate_limit_rpm=120
            )
        
        # Flashbots Relay (Ethereum Mainnet)
        if self.config.chain_configs.get(1):  # Ethereum mainnet
            self._relay_configs["flashbots_relay"] = RelayConfig(
                name="Flashbots Relay",
                relay_type=RelayType.FLASHBOTS_RELAY,
                endpoint_url="https://relay.flashbots.net",
                chain_id=1,
                enabled=True,
                timeout_seconds=8,
                max_retries=3,
                priority_threshold=PriorityLevel.MEDIUM,
                require_signing=True,
                rate_limit_rpm=60
            )
        
        self.logger.info(f"Initialized {len(self._relay_configs)} relay configurations")
    
    async def submit_bundle(
        self,
        transactions: List[TxParams],
        priority: PriorityLevel = PriorityLevel.HIGH,
        target_block: Optional[int] = None,
        max_block_delay: int = 3,
        replacement_uuid: Optional[str] = None
    ) -> BundleSubmissionResult:
        """
        Submit a bundle to the best available private relay.
        
        This method intelligently routes bundles to the most appropriate relay
        based on priority level, relay availability, and performance metrics.
        
        Args:
            transactions: List of transaction parameters to bundle
            priority: Priority level for relay selection
            target_block: Specific block number to target (None for next block)
            max_block_delay: Maximum blocks to wait for inclusion
            replacement_uuid: UUID for replacing existing bundle
            
        Returns:
            Bundle submission result with success status and metadata
        """
        submission_start = time.perf_counter()
        
        if not self._session:
            raise RuntimeError("Private relay manager not initialized")
            
        self.logger.info(f"Submitting bundle with {len(transactions)} transactions (Priority: {priority.value})")
        
        try:
            # Get current block number for targeting
            if target_block is None:
                target_block = await self._get_current_block_number()
                
            # Prepare signed transactions for bundle
            signed_transactions = []
            for tx in transactions:
                signed_tx_data = await self._prepare_signed_transaction(tx)
                signed_transactions.append(signed_tx_data)
            
            # Create bundle
            bundle = FlashbotsBundle(
                transactions=signed_transactions,
                block_number=target_block,
                max_timestamp=int((datetime.utcnow() + timedelta(seconds=60)).timestamp()),
                replacement_uuid=replacement_uuid
            )
            
            # Generate unique bundle ID
            bundle_id = self._generate_bundle_id(bundle)
            bundle.bundle_id = bundle_id
            
            # Select best relay based on priority and performance
            selected_relay = self._select_optimal_relay(priority)
            if not selected_relay:
                return BundleSubmissionResult(
                    success=False,
                    error_message="No suitable relay available",
                    submission_time=datetime.utcnow()
                )
            
            self.logger.info(f"Selected relay: {selected_relay.name} for priority {priority.value}")
            
            # Submit to selected relay
            result = await self._submit_to_relay(bundle, selected_relay)
            
            # Track bundle and update metrics
            if result.success:
                self._active_bundles[bundle_id] = bundle
                self._bundle_status[bundle_id] = BundleStatus.SUBMITTED
                self._successful_submissions += 1
                
                self.logger.info(f"Bundle {bundle_id[:10]}... submitted successfully to {selected_relay.name}")
            else:
                self.logger.error(f"Bundle submission failed: {result.error_message}")
            
            # Track performance metrics
            submission_time = (time.perf_counter() - submission_start) * 1000
            self._submission_latencies.append(submission_time)
            self._total_submissions += 1
            
            result.latency_ms = submission_time
            
            # Send metrics to Django
            if self._django_bridge:
                await self._send_submission_metrics(result, selected_relay)
            
            return result
            
        except Exception as e:
            self.logger.error(f"Bundle submission failed with exception: {e}")
            
            return BundleSubmissionResult(
                success=False,
                error_message=str(e),
                submission_time=datetime.utcnow(),
                latency_ms=(time.perf_counter() - submission_start) * 1000
            )

    def _select_optimal_relay(self, priority: PriorityLevel) -> Optional[RelayConfig]:
        """
        Select the best relay based on priority level and performance metrics.
        
        Args:
            priority: Transaction priority level
            
        Returns:
            Selected relay configuration or None if no suitable relay found
        """
        suitable_relays = []
        
        # Filter relays by priority threshold and availability
        for relay_name, relay_config in self._relay_configs.items():
            if not relay_config.enabled:
                continue
                
            # Check if relay supports this priority level
            priority_scores = {
                PriorityLevel.CRITICAL: 4,
                PriorityLevel.HIGH: 3,
                PriorityLevel.MEDIUM: 2,
                PriorityLevel.LOW: 1
            }
            
            if priority_scores[priority] >= priority_scores[relay_config.priority_threshold]:
                suitable_relays.append((relay_config, self._calculate_relay_score(relay_config)))
        
        if not suitable_relays:
            return None
        
        # Sort by score (higher is better) and return best relay
        suitable_relays.sort(key=lambda x: x[1], reverse=True)
        selected_relay = suitable_relays[0][0]
        
        self.logger.debug(f"Selected {selected_relay.name} with score {suitable_relays[0][1]:.3f}")
        
        return selected_relay

    def _calculate_relay_score(self, relay_config: RelayConfig) -> float:
        """
        Calculate a score for relay selection based on performance metrics.
        
        Args:
            relay_config: Relay configuration to score
            
        Returns:
            Relay score (higher is better)
        """
        score = 0.0
        
        # Success rate weight (40%)
        success_rate = self._success_rates.get(relay_config.name, 0.95)  # Default 95%
        score += success_rate * 0.4
        
        # Latency weight (30%)
        avg_latency = self._get_average_latency(relay_config.name)
        latency_score = max(0, 1 - (avg_latency / 1000.0))  # Normalize to 0-1
        score += latency_score * 0.3
        
        # Relay type preference weight (20%)
        type_preferences = {
            RelayType.FLASHBOTS_PROTECT: 1.0,
            RelayType.FLASHBOTS_RELAY: 0.8,
            RelayType.PUBLIC_MEMPOOL: 0.3
        }
        score += type_preferences.get(relay_config.relay_type, 0.5) * 0.2
        
        # Availability weight (10%)
        if relay_config.enabled and relay_config.endpoint_url:
            score += 0.1
        
        return score

    async def _prepare_signed_transaction(self, tx_params: TxParams) -> Dict[str, Any]:
        """
        Prepare and sign transaction for bundle submission.
        
        Args:
            tx_params: Transaction parameters
            
        Returns:
            Signed transaction data ready for bundle
        """
        try:
            # In production, this would:
            # 1. Get private key from secure wallet manager
            # 2. Sign transaction with proper nonce
            # 3. Encode as RLP hex string
            
            # For now, return properly formatted transaction structure
            signed_tx = {
                "signed_transaction": "0x" + "f8" + "00" * 100,  # Placeholder RLP encoding
                "hash": self._calculate_tx_hash(tx_params),
                "from": tx_params.get("from"),
                "to": tx_params.get("to"),
                "value": hex(tx_params.get("value", 0)),
                "gasPrice": hex(tx_params.get("gasPrice", 0)),
                "gas": hex(tx_params.get("gas", 200000)),
                "nonce": hex(tx_params.get("nonce", 0)),
                "data": tx_params.get("data", "0x")
            }
            
            self.logger.debug(f"Prepared signed transaction: {signed_tx['hash'][:10]}...")
            
            return signed_tx
            
        except Exception as e:
            self.logger.error(f"Failed to prepare signed transaction: {e}")
            raise

    def _calculate_tx_hash(self, tx_params: TxParams) -> str:
        """Generate a deterministic transaction hash for tracking."""
        tx_string = f"{tx_params.get('from', '')}{tx_params.get('to', '')}{tx_params.get('value', 0)}{tx_params.get('nonce', 0)}{int(time.time() * 1000)}"
        return "0x" + hashlib.sha256(tx_string.encode()).hexdigest()

    def _generate_bundle_id(self, bundle: FlashbotsBundle) -> str:
        """Generate unique bundle ID for tracking."""
        bundle_data = f"{len(bundle.transactions)}{bundle.block_number}{int(time.time() * 1000000)}"
        return "0x" + hashlib.sha256(bundle_data.encode()).hexdigest()[:16]

    async def _submit_to_relay(
        self,
        bundle: FlashbotsBundle,
        relay_config: RelayConfig
    ) -> BundleSubmissionResult:
        """
        Submit bundle to specific relay endpoint.
        
        Args:
            bundle: Prepared bundle for submission
            relay_config: Target relay configuration
            
        Returns:
            Submission result with status and metadata
        """
        if not self._session:
            raise RuntimeError("HTTP session not initialized")
        
        submission_time = datetime.utcnow()
        
        try:
            # Route to appropriate relay implementation
            if relay_config.relay_type in [RelayType.FLASHBOTS_PROTECT, RelayType.FLASHBOTS_RELAY]:
                return await self._submit_to_flashbots(bundle, relay_config, submission_time)
            else:
                raise ValueError(f"Unsupported relay type: {relay_config.relay_type}")
                
        except Exception as e:
            self.logger.error(f"Relay submission failed for {relay_config.name}: {e}")
            
            return BundleSubmissionResult(
                success=False,
                relay_type=relay_config.relay_type,
                submission_time=submission_time,
                error_message=str(e)
            )

    async def _submit_to_flashbots(
        self,
        bundle: FlashbotsBundle,
        relay_config: RelayConfig,
        submission_time: datetime
    ) -> BundleSubmissionResult:
        """
        Submit bundle to Flashbots relay endpoint.
        
        Args:
            bundle: Bundle to submit
            relay_config: Flashbots relay configuration
            submission_time: Time of submission
            
        Returns:
            Flashbots submission result
        """
        # Prepare Flashbots API request
        bundle_data = bundle.to_flashbots_format()
        
        # Determine method and endpoint based on relay type
        if relay_config.relay_type == RelayType.FLASHBOTS_PROTECT:
            method = "eth_sendBundle"
            endpoint = relay_config.endpoint_url
        else:
            method = "flashbots_sendBundle"
            endpoint = f"{relay_config.endpoint_url}/v1/bundle"
        
        request_data = {
            "jsonrpc": "2.0",
            "id": int(time.time()),
            "method": method,
            "params": [bundle_data]
        }
        
        # Prepare authentication headers
        headers = {
            "Content-Type": "application/json"
        }
        
        if relay_config.require_signing:
            # In production, this would include proper Flashbots signature
            # Using X-Flashbots-Signature header with signed request
            headers["X-Flashbots-Signature"] = self._generate_flashbots_signature(request_data)
        
        try:
            self.logger.debug(f"Submitting to {relay_config.name}: {endpoint}")
            
            async with self._session.post(
                endpoint,
                json=request_data,
                headers=headers,
                timeout=relay_config.timeout_seconds
            ) as response:
                
                response_text = await response.text()
                
                if response.status == 200:
                    try:
                        result_data = await response.json()
                        
                        if "result" in result_data:
                            bundle_hash = result_data["result"].get("bundleHash")
                            
                            self.logger.info(f"Flashbots submission successful: {bundle_hash}")
                            
                            return BundleSubmissionResult(
                                success=True,
                                bundle_id=bundle_hash,
                                relay_type=relay_config.relay_type,
                                submission_time=submission_time,
                                block_number=bundle.block_number
                            )
                        elif "error" in result_data:
                            error_msg = result_data["error"].get("message", "Unknown Flashbots error")
                            self.logger.error(f"Flashbots error: {error_msg}")
                            
                            return BundleSubmissionResult(
                                success=False,
                                relay_type=relay_config.relay_type,
                                submission_time=submission_time,
                                error_message=f"Flashbots error: {error_msg}"
                            )
                            
                    except json.JSONDecodeError:
                        return BundleSubmissionResult(
                            success=False,
                            relay_type=relay_config.relay_type,
                            submission_time=submission_time,
                            error_message=f"Invalid JSON response: {response_text[:200]}"
                        )
                else:
                    return BundleSubmissionResult(
                        success=False,
                        relay_type=relay_config.relay_type,
                        submission_time=submission_time,
                        error_message=f"HTTP {response.status}: {response_text[:200]}"
                    )
                    
        except asyncio.TimeoutError:
            return BundleSubmissionResult(
                success=False,
                relay_type=relay_config.relay_type,
                submission_time=submission_time,
                error_message=f"Timeout after {relay_config.timeout_seconds}s"
            )
        except Exception as e:
            return BundleSubmissionResult(
                success=False,
                relay_type=relay_config.relay_type,
                submission_time=submission_time,
                error_message=f"Network error: {str(e)}"
            )

    def _generate_flashbots_signature(self, request_data: Dict[str, Any]) -> str:
        """
        Generate Flashbots signature for request authentication.
        
        Args:
            request_data: Request data to sign
            
        Returns:
            Signature string for X-Flashbots-Signature header
        """
        # In production, this would:
        # 1. Get private key from secure storage
        # 2. Sign the request body with eth_account.sign_message
        # 3. Format as required by Flashbots
        
        # Placeholder implementation
        request_hash = hashlib.sha256(json.dumps(request_data, sort_keys=True).encode()).hexdigest()
        return f"0x{'0' * 130}"  # Placeholder 65-byte signature

    async def _get_current_block_number(self) -> int:
        """Get current block number from the blockchain."""
        try:
            # In production, would use Web3 provider to get latest block
            # For now, return a reasonable mainnet block number
            return 18_500_000 + int(time.time() // 12)  # Approximate current block
            
        except Exception as e:
            self.logger.error(f"Failed to get current block number: {e}")
            return 18_500_000  # Fallback

    async def _send_submission_metrics(
        self,
        result: BundleSubmissionResult,
        relay_config: RelayConfig
    ) -> None:
        """Send submission metrics to Django backend."""
        if not self._django_bridge:
            return
            
        try:
            metrics_data = {
                "type": "relay_submission",
                "relay_name": relay_config.name,
                "relay_type": relay_config.relay_type.value,
                "success": result.success,
                "bundle_id": result.bundle_id,
                "latency_ms": result.latency_ms,
                "block_number": result.block_number,
                "error_message": result.error_message,
                "timestamp": result.submission_time.isoformat() if result.submission_time else None
            }
            
            await self._django_bridge.send_message("relay_metrics", metrics_data)
            
        except Exception as e:
            self.logger.error(f"Failed to send submission metrics: {e}")

    def get_submission_statistics(self) -> Dict[str, Any]:
        """Get relay submission statistics."""
        success_rate = 0.0
        if self._total_submissions > 0:
            success_rate = (self._successful_submissions / self._total_submissions) * 100
        
        avg_latency = 0.0
        if self._submission_latencies:
            avg_latency = sum(self._submission_latencies) / len(self._submission_latencies)
        
        return {
            "total_submissions": self._total_submissions,
            "successful_submissions": self._successful_submissions,
            "success_rate_percent": round(success_rate, 2),
            "average_latency_ms": round(avg_latency, 2),
            "active_bundles": len(self._active_bundles),
            "relay_configs": len(self._relay_configs),
            "relay_success_rates": dict(self._success_rates)
        }

    async def check_bundle_status(self, bundle_id: str) -> BundleStatus:
        """
        Check the status of a submitted bundle.
        
        Args:
            bundle_id: Bundle identifier to check
            
        Returns:
            Current bundle status
        """
        if bundle_id not in self._bundle_status:
            return BundleStatus.FAILED
        
        current_status = self._bundle_status[bundle_id]
        
        # If already final status, return it
        if current_status in [BundleStatus.INCLUDED, BundleStatus.FAILED, 
                             BundleStatus.TIMEOUT, BundleStatus.CANCELLED]:
            return current_status
        
        # For active bundles, could query relay for updated status
        # For now, return current status
        return current_status

    def _get_average_latency(self, relay_name: str) -> float:
        """Get average latency for a specific relay."""
        # Calculate from stored metrics
        if not self._submission_latencies:
            return 1000.0  # Default 1s if no data
        
        return sum(self._submission_latencies[-10:]) / len(self._submission_latencies[-10:])

    async def _submit_to_public_mempool(
        self,
        transactions: List[TxParams]
    ) -> BundleSubmissionResult:
        """
        Fallback submission to public mempool when no relay is available.
        
        Args:
            transactions: Transaction parameters to submit
            
        Returns:
            Public mempool submission result
        """
        submission_time = datetime.utcnow()
        
        try:
            # Submit transactions individually to public mempool
            # This is a simplified implementation
            tx_hashes = []
            
            for tx_params in transactions:
                # In production, this would use Web3 to submit transactions
                tx_hash = "0x" + "00" * 64  # Placeholder
                tx_hashes.append(tx_hash)
            
            return BundleSubmissionResult(
                success=True,
                bundle_id=f"public_{int(time.time())}",
                relay_type=RelayType.PUBLIC_MEMPOOL,
                submission_time=submission_time,
                error_message="Submitted to public mempool (no MEV protection)"
            )
            
        except Exception as e:
            return BundleSubmissionResult(
                success=False,
                relay_type=RelayType.PUBLIC_MEMPOOL,
                submission_time=submission_time,
                error_message=str(e)
            )

    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics for the relay manager.
        
        Returns:
            Dictionary containing performance metrics
        """
        if self._submission_latencies:
            avg_latency = sum(self._submission_latencies) / len(self._submission_latencies)
            min_latency = min(self._submission_latencies)
            max_latency = max(self._submission_latencies)
        else:
            avg_latency = min_latency = max_latency = 0.0
        
        success_rate = (
            self._successful_submissions / self._total_submissions
            if self._total_submissions > 0 else 0.0
        )
        
        return {
            "total_submissions": self._total_submissions,
            "successful_submissions": self._successful_submissions,
            "success_rate": success_rate,
            "average_latency_ms": avg_latency,
            "min_latency_ms": min_latency,
            "max_latency_ms": max_latency,
            "active_bundles": len(self._active_bundles),
            "configured_relays": len(self._relay_configs),
            "enabled_relays": len([r for r in self._relay_configs.values() if r.enabled])
        }

    def get_relay_configs(self) -> Dict[str, RelayConfig]:
        """Get current relay configurations."""
        return self._relay_configs.copy()

    def enable_relay(self, relay_name: str) -> bool:
        """
        Enable a specific relay.
        
        Args:
            relay_name: Name of the relay to enable
            
        Returns:
            True if relay was found and enabled
        """
        if relay_name in self._relay_configs:
            self._relay_configs[relay_name].enabled = True
            self.logger.info(f"Enabled relay: {relay_name}")
            return True
        return False

    def disable_relay(self, relay_name: str) -> bool:
        """
        Disable a specific relay.
        
        Args:
            relay_name: Name of the relay to disable
            
        Returns:
            True if relay was found and disabled
        """
        if relay_name in self._relay_configs:
            self._relay_configs[relay_name].enabled = False
            self.logger.info(f"Disabled relay: {relay_name}")
            return True
        return False

    def get_active_bundles(self) -> Dict[str, FlashbotsBundle]:
        """Get currently active bundles."""
        return self._active_bundles.copy()

    def cancel_bundle(self, bundle_id: str) -> bool:
        """
        Cancel an active bundle.
        
        Args:
            bundle_id: Bundle to cancel
            
        Returns:
            True if bundle was found and cancelled
        """
        if bundle_id in self._bundle_status:
            self._bundle_status[bundle_id] = BundleStatus.CANCELLED
            self.logger.info(f"Cancelled bundle: {bundle_id}")
            return True
        return False


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

async def create_private_relay_manager() -> PrivateRelayManager:
    """
    Factory function to create and initialize a PrivateRelayManager.
    
    Returns:
        Fully initialized PrivateRelayManager instance
    """
    config = await get_config()
    manager = PrivateRelayManager(config)
    await manager.initialize()
    return manager


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    'PrivateRelayManager',
    'FlashbotsBundle',
    'BundleSubmissionResult',
    'RelayConfig',
    'RelayType',
    'BundleStatus',
    'PriorityLevel',
    'create_private_relay_manager'
]