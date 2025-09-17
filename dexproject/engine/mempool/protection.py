"""
MEV Protection Mechanisms Module

This module implements comprehensive MEV (Maximal Extractable Value) protection
mechanisms including sandwich attack detection, frontrunning protection, and
priority fee optimization. Works in conjunction with the private relay manager
to ensure MEV-protected execution.

Key Features:
- Real-time sandwich attack detection and prevention
- Frontrunning protection with timing analysis
- Priority fee optimization based on MEV risk assessment
- Transaction pool analysis for MEV threats
- Integration with private relay routing decisions
- Performance metrics and alerting

File: dexproject/engine/mempool/protection.py
Django App: N/A (Pure engine component)
"""

import asyncio
import logging
import time
import json
import hashlib
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Any, Union
from datetime import datetime, timedelta
from collections import defaultdict, deque

import aiohttp
from web3 import Web3
from web3.types import TxParams, TxReceipt, BlockData
from eth_typing import ChecksumAddress, HexStr
from eth_utils import to_checksum_address, to_hex

# Import engine components
from ..config import EngineConfig, get_config
from .relay import PrivateRelayManager, PriorityLevel, RelayType
from ..communications.django_bridge import DjangoBridge
from shared.schemas import (
    BaseMessage, MessageType, RiskLevel, ChainType
)


logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS & CONSTANTS
# =============================================================================

class MEVThreatType(str, Enum):
    """Types of MEV threats detected."""
    SANDWICH_ATTACK = "sandwich_attack"
    FRONTRUNNING = "frontrunning"
    BACKRUNNING = "backrunning"
    JIT_LIQUIDITY = "jit_liquidity"
    LIQUIDATION_MEV = "liquidation_mev"
    ARBITRAGE_COMPETITION = "arbitrage_competition"


class ProtectionAction(str, Enum):
    """Actions taken for MEV protection."""
    PRIVATE_RELAY = "private_relay"
    DELAY_EXECUTION = "delay_execution"
    INCREASE_GAS = "increase_gas"
    CANCEL_TRANSACTION = "cancel_transaction"
    SPLIT_TRANSACTION = "split_transaction"
    NO_ACTION = "no_action"


class SeverityLevel(str, Enum):
    """MEV threat severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NEGLIGIBLE = "negligible"


# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class PendingTransaction:
    """Represents a pending transaction in the mempool."""
    
    hash: str
    from_address: str
    to_address: Optional[str]
    value: Decimal
    gas_price: Decimal
    gas_limit: int
    nonce: int
    data: str
    timestamp: datetime
    
    # Analysis fields
    is_dex_interaction: bool = False
    target_token: Optional[str] = None
    swap_amount_in: Optional[Decimal] = None
    swap_amount_out: Optional[Decimal] = None
    dex_name: Optional[str] = None
    
    def __post_init__(self):
        """Analyze transaction data after initialization."""
        if self.to_address and self.data and self.data != "0x":
            self._analyze_transaction_data()
    
    def _analyze_transaction_data(self) -> None:
        """Analyze transaction data to identify DEX interactions."""
        # Simplified DEX interaction detection
        # In production, this would use comprehensive ABI decoding
        
        # Common DEX function selectors
        dex_selectors = {
            "0x7ff36ab5": "swapExactETHForTokens",  # Uniswap V2
            "0x18cbafe5": "swapExactTokensForETH",  # Uniswap V2
            "0x38ed1739": "swapExactTokensForTokens",  # Uniswap V2
            "0x414bf389": "exactInputSingle",  # Uniswap V3
            "0xc04b8d59": "exactInput",  # Uniswap V3
        }
        
        if self.data and len(self.data) >= 10:
            selector = self.data[:10]
            if selector in dex_selectors:
                self.is_dex_interaction = True
                # Additional parsing would extract swap parameters


@dataclass
class MEVThreat:
    """Represents a detected MEV threat."""
    
    threat_type: MEVThreatType
    severity: SeverityLevel
    confidence: float  # 0.0 to 1.0
    target_transaction: str
    threatening_transactions: List[str]
    estimated_profit: Optional[Decimal] = None
    estimated_loss: Optional[Decimal] = None
    detection_time: datetime = field(default_factory=datetime.utcnow)
    
    # Threat-specific data
    attacker_address: Optional[str] = None
    frontrun_transaction: Optional[str] = None
    backrun_transaction: Optional[str] = None
    gas_price_advantage: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/storage."""
        return {
            "threat_type": self.threat_type.value,
            "severity": self.severity.value,
            "confidence": self.confidence,
            "target_transaction": self.target_transaction,
            "threatening_transactions": self.threatening_transactions,
            "estimated_profit": str(self.estimated_profit) if self.estimated_profit else None,
            "estimated_loss": str(self.estimated_loss) if self.estimated_loss else None,
            "detection_time": self.detection_time.isoformat(),
            "attacker_address": self.attacker_address,
            "frontrun_transaction": self.frontrun_transaction,
            "backrun_transaction": self.backrun_transaction,
            "gas_price_advantage": self.gas_price_advantage,
            "metadata": self.metadata
        }


@dataclass
class ProtectionRecommendation:
    """Recommendation for MEV protection action."""
    
    action: ProtectionAction
    priority_level: PriorityLevel
    gas_price_multiplier: float
    delay_seconds: Optional[int] = None
    use_private_relay: bool = True
    split_into_parts: Optional[int] = None
    
    # Justification
    reasoning: str = ""
    expected_cost: Optional[Decimal] = None
    expected_savings: Optional[Decimal] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/storage."""
        return {
            "action": self.action.value,
            "priority_level": self.priority_level.value,
            "gas_price_multiplier": self.gas_price_multiplier,
            "delay_seconds": self.delay_seconds,
            "use_private_relay": self.use_private_relay,
            "split_into_parts": self.split_into_parts,
            "reasoning": self.reasoning,
            "expected_cost": str(self.expected_cost) if self.expected_cost else None,
            "expected_savings": str(self.expected_savings) if self.expected_savings else None
        }


@dataclass
class ProtectionAnalysis:
    """Complete MEV analysis result for a transaction."""
    transaction_hash: str
    threats: List[MEVThreat]
    recommendation: ProtectionRecommendation
    analysis_time_ms: float
    timestamp: datetime
    
    # Analysis metadata
    mempool_size_analyzed: int = 0
    confidence_threshold_used: float = 0.6
    analysis_version: str = "1.0"


# =============================================================================
# MEV PROTECTION ENGINE
# =============================================================================

class MEVProtectionEngine:
    """
    Advanced MEV protection engine that detects and mitigates MEV threats.
    
    This engine analyzes pending transactions, detects various MEV attack patterns,
    and recommends protection strategies including private relay routing, gas
    optimization, and timing adjustments.
    """
    
    def __init__(self, engine_config: EngineConfig):
        """
        Initialize the MEV protection engine.
        
        Args:
            engine_config: Engine configuration instance
        """
        self.config = engine_config
        self.logger = logging.getLogger(f"{__name__}.MEVProtectionEngine")
        
        # Mempool state tracking
        self._pending_transactions: Dict[str, PendingTransaction] = {}
        self._transaction_history: deque = deque(maxlen=1000)
        
        # MEV threat detection
        self._active_threats: Dict[str, MEVThreat] = {}
        self._threat_patterns: Dict[MEVThreatType, List[Dict]] = {}
        
        # Gas price analysis
        self._gas_price_history: deque = deque(maxlen=100)
        self._priority_fee_history: deque = deque(maxlen=100)
        
        # Protection statistics
        self._threats_detected = 0
        self._threats_prevented = 0
        self._protection_actions_taken: Dict[ProtectionAction, int] = defaultdict(int)
        
        # Performance tracking
        self._analysis_latencies: deque = deque(maxlen=50)
        self._detection_accuracy: List[float] = []
        
        # Integration components
        self._django_bridge: Optional[DjangoBridge] = None
        self._private_relay: Optional[PrivateRelayManager] = None
        
        # Initialize threat detection patterns
        self._initialize_threat_patterns()
        
        self.logger.info("MEV protection engine initialized")
    
    async def initialize(self, private_relay: PrivateRelayManager) -> None:
        """
        Initialize async components of the MEV protection engine.
        
        Args:
            private_relay: Private relay manager instance
        """
        self._private_relay = private_relay
        
        # Initialize Django bridge if available
        try:
            self._django_bridge = DjangoBridge("mev_protection")
            await self._django_bridge.initialize()
            self.logger.info("Django bridge initialized for MEV protection")
        except Exception as e:
            self.logger.warning(f"Could not initialize Django bridge: {e}")
        
        self.logger.info("MEV protection engine async initialization complete")
    
    async def shutdown(self) -> None:
        """Cleanup resources and close connections."""
        if self._django_bridge:
            await self._django_bridge.disconnect()
        
        self.logger.info("MEV protection engine shutdown complete")
    
    def _initialize_threat_patterns(self) -> None:
        """Initialize MEV threat detection patterns."""
        # Sandwich attack patterns
        self._threat_patterns[MEVThreatType.SANDWICH_ATTACK] = [
            {
                "name": "classic_sandwich",
                "description": "Buy-victim-sell pattern with same token pair",
                "min_confidence": 0.7,
                "time_window_ms": 500,
                "gas_price_threshold_multiplier": 1.1
            },
            {
                "name": "multi_block_sandwich",
                "description": "Sandwich attack spanning multiple blocks",
                "min_confidence": 0.6,
                "time_window_ms": 15000,
                "gas_price_threshold_multiplier": 1.05
            }
        ]
        
        # Frontrunning patterns
        self._threat_patterns[MEVThreatType.FRONTRUNNING] = [
            {
                "name": "copy_trade_frontrun",
                "description": "Copying profitable trade with higher gas price",
                "min_confidence": 0.8,
                "time_window_ms": 200,
                "gas_price_threshold_multiplier": 1.2
            },
            {
                "name": "arbitrage_frontrun",
                "description": "Frontrunning arbitrage opportunities",
                "min_confidence": 0.75,
                "time_window_ms": 300,
                "gas_price_threshold_multiplier": 1.15
            }
        ]
        
        self.logger.info(f"Initialized {len(self._threat_patterns)} threat pattern categories")
    
    async def analyze_pending_transaction(self, transaction: PendingTransaction) -> Optional['ProtectionAnalysis']:
        """
        Analyze a pending transaction for MEV threats and generate protection recommendations.
        
        Args:
            transaction: Transaction to analyze for MEV risks
            
        Returns:
            ProtectionAnalysis containing threats and recommendations, or None if analysis fails
        """
        start_time = time.perf_counter()
        
        try:
            self.logger.debug(f"Analyzing transaction {transaction.hash[:10]}... for MEV threats")
            
            # Get current mempool state for context
            current_mempool = list(self._pending_transactions.values())
            
            # Detect MEV threats
            threats = await self._detect_mev_threats(transaction, current_mempool)
            
            # Generate protection recommendation based on threats
            recommendation = await self._generate_protection_recommendation(transaction, threats)
            
            # Track analysis performance
            analysis_time_ms = (time.perf_counter() - start_time) * 1000
            self._analysis_latencies.append(analysis_time_ms)
            
            # Update statistics
            if threats:
                self._threats_detected += len(threats)
                threat_types = [threat.threat_type.value for threat in threats]
                self.logger.info(
                    f"MEV threats detected for {transaction.hash[:10]}...: {threat_types} "
                    f"(Analysis: {analysis_time_ms:.2f}ms)"
                )
                
                # Send threat notifications to Django
                if self._django_bridge:
                    await self._send_threat_notifications(transaction, threats, recommendation)
            
            # Create analysis result
            analysis = ProtectionAnalysis(
                transaction_hash=transaction.hash,
                threats=threats,
                recommendation=recommendation,
                analysis_time_ms=analysis_time_ms,
                timestamp=datetime.utcnow()
            )
            
            return analysis
            
        except Exception as e:
            self.logger.error(f"MEV analysis failed for {transaction.hash[:10]}...: {e}")
            
            # Return safe default recommendation
            default_recommendation = ProtectionRecommendation(
                action=ProtectionAction.PRIVATE_RELAY,
                priority_level=PriorityLevel.HIGH,
                gas_price_multiplier=1.2,
                use_private_relay=True,
                reasoning="Analysis failed, using conservative protection"
            )
            
            return ProtectionAnalysis(
                transaction_hash=transaction.hash,
                threats=[],
                recommendation=default_recommendation,
                analysis_time_ms=(time.perf_counter() - start_time) * 1000,
                timestamp=datetime.utcnow()
            )

    async def analyze_transaction_for_mev_threats(
        self,
        transaction: TxParams,
        current_mempool: List[PendingTransaction]
    ) -> Tuple[List[MEVThreat], ProtectionRecommendation]:
        """
        Analyze a transaction for MEV threats and generate protection recommendations.
        
        Args:
            transaction: Transaction to analyze
            current_mempool: Current mempool state
            
        Returns:
            Tuple of (detected threats, protection recommendation)
        """
        start_time = time.time()
        
        try:
            # Convert transaction to internal format for analysis
            pending_tx = self._convert_tx_params_to_pending(transaction)
            
            # Update mempool state
            self._update_mempool_state(current_mempool)
            
            # Detect MEV threats
            threats = await self._detect_mev_threats(pending_tx, current_mempool)
            
            # Generate protection recommendation
            recommendation = await self._generate_protection_recommendation(
                pending_tx, threats
            )
            
            # Update statistics
            analysis_time = (time.time() - start_time) * 1000
            self._analysis_latencies.append(analysis_time)
            
            if threats:
                self._threats_detected += len(threats)
                self.logger.info(
                    f"Detected {len(threats)} MEV threats for tx {pending_tx.hash[:10]}... "
                    f"Recommendation: {recommendation.action.value}"
                )
                
                # Send threat alerts to Django
                if self._django_bridge:
                    await self._send_threat_notifications(pending_tx, threats, recommendation)
            
            return threats, recommendation
            
        except Exception as e:
            self.logger.error(f"MEV analysis failed: {e}")
            
            # Return safe default recommendation
            safe_recommendation = ProtectionRecommendation(
                action=ProtectionAction.PRIVATE_RELAY,
                priority_level=PriorityLevel.HIGH,
                gas_price_multiplier=1.2,
                use_private_relay=True,
                reasoning="Analysis failed, using safe defaults"
            )
            
            return [], safe_recommendation
    
    def _convert_tx_params_to_pending(self, transaction: TxParams) -> PendingTransaction:
        """Convert TxParams to PendingTransaction for analysis."""
        return PendingTransaction(
            hash=f"pending_{int(time.time() * 1000000)}",  # Temporary hash
            from_address=transaction.get('from', ''),
            to_address=transaction.get('to'),
            value=Decimal(transaction.get('value', 0)),
            gas_price=Decimal(transaction.get('gasPrice', 0)),
            gas_limit=transaction.get('gas', 200000),
            nonce=transaction.get('nonce', 0),
            data=transaction.get('data', '0x'),
            timestamp=datetime.utcnow()
        )
    
    def _update_mempool_state(self, current_mempool: List[PendingTransaction]) -> None:
        """Update internal mempool state with current data."""
        # Clear old transactions
        current_time = datetime.utcnow()
        cutoff_time = current_time - timedelta(seconds=30)
        
        # Remove old transactions
        old_hashes = [
            tx_hash for tx_hash, tx in self._pending_transactions.items()
            if tx.timestamp < cutoff_time
        ]
        
        for tx_hash in old_hashes:
            del self._pending_transactions[tx_hash]
        
        # Add new transactions
        for tx in current_mempool:
            self._pending_transactions[tx.hash] = tx
            
            # Track gas price trends
            if tx.is_dex_interaction:
                self._gas_price_history.append(tx.gas_price)

    async def _detect_mev_threats(
        self, 
        target_tx: PendingTransaction, 
        mempool: List[PendingTransaction]
    ) -> List[MEVThreat]:
        """
        Detect various MEV threat types against a target transaction.
        
        Args:
            target_tx: Transaction being analyzed
            mempool: Current mempool state
            
        Returns:
            List of detected MEV threats
        """
        threats = []
        
        try:
            # Concurrent threat detection for performance
            threat_detection_tasks = [
                self._detect_sandwich_attacks(target_tx, mempool),
                self._detect_frontrunning(target_tx, mempool),
                self._detect_backrunning(target_tx, mempool),
                self._detect_jit_liquidity(target_tx, mempool),
            ]
            
            # Execute all detection algorithms concurrently
            results = await asyncio.gather(*threat_detection_tasks, return_exceptions=True)
            
            # Collect results from all detectors
            for result in results:
                if isinstance(result, Exception):
                    self.logger.error(f"Threat detection failed: {result}")
                    continue
                if isinstance(result, list):
                    threats.extend(result)
            
            # Remove duplicates and sort by severity
            unique_threats = self._deduplicate_threats(threats)
            sorted_threats = sorted(
                unique_threats, 
                key=lambda t: self._get_severity_score(t.severity), 
                reverse=True
            )
            
            return sorted_threats
            
        except Exception as e:
            self.logger.error(f"MEV threat detection failed: {e}")
            return []

    async def _detect_sandwich_attacks(
        self, 
        target_tx: PendingTransaction, 
        mempool: List[PendingTransaction]
    ) -> List[MEVThreat]:
        """
        Detect sandwich attack patterns in the mempool.
        
        Args:
            target_tx: Target transaction to protect
            mempool: Current mempool transactions
            
        Returns:
            List of sandwich attack threats
        """
        threats = []
        
        if not target_tx.is_dex_interaction:
            return threats
            
        try:
            # Find potential sandwich transactions
            frontrun_candidates = []
            backrun_candidates = []
            
            for tx in mempool:
                if tx.hash == target_tx.hash or not tx.is_dex_interaction:
                    continue
                    
                # Check for same token pair interaction
                if not self._involves_same_token_pair(target_tx, tx):
                    continue
                    
                # Frontrunning candidate: higher gas price, earlier timestamp
                if (tx.gas_price > target_tx.gas_price and 
                    tx.timestamp <= target_tx.timestamp):
                    frontrun_candidates.append(tx)
                    
                # Backrunning candidate: lower gas price, later timestamp
                elif (tx.gas_price < target_tx.gas_price and 
                      tx.timestamp >= target_tx.timestamp):
                    backrun_candidates.append(tx)
            
            # Detect sandwich patterns
            for frontrun_tx in frontrun_candidates:
                for backrun_tx in backrun_candidates:
                    # Check if same attacker (same from address)
                    if frontrun_tx.from_address == backrun_tx.from_address:
                        
                        # Calculate confidence based on pattern strength
                        confidence = self._calculate_sandwich_confidence(
                            frontrun_tx, target_tx, backrun_tx
                        )
                        
                        if confidence >= 0.6:  # Minimum confidence threshold
                            threat = MEVThreat(
                                threat_type=MEVThreatType.SANDWICH_ATTACK,
                                target_transaction=target_tx.hash,
                                attacker_address=frontrun_tx.from_address,
                                frontrun_transaction=frontrun_tx.hash,
                                backrun_transaction=backrun_tx.hash,
                                confidence=confidence,
                                severity=self._determine_threat_severity(confidence),
                                estimated_profit=self._estimate_sandwich_profit(
                                    frontrun_tx, target_tx, backrun_tx
                                ),
                                detection_time=datetime.utcnow(),
                                threatening_transactions=[frontrun_tx.hash, backrun_tx.hash]
                            )
                            
                            threats.append(threat)
            
            return threats
            
        except Exception as e:
            self.logger.error(f"Sandwich attack detection failed: {e}")
            return []

    async def _detect_frontrunning(
        self, 
        target_tx: PendingTransaction, 
        mempool: List[PendingTransaction]
    ) -> List[MEVThreat]:
        """
        Detect frontrunning patterns in the mempool.
        
        Args:
            target_tx: Target transaction to protect
            mempool: Current mempool transactions
            
        Returns:
            List of frontrunning threats
        """
        threats = []
        
        if not target_tx.is_dex_interaction:
            return threats
            
        try:
            # Look for transactions with similar intent but higher gas prices
            for tx in mempool:
                if tx.hash == target_tx.hash:
                    continue
                    
                # Must be same token interaction with higher gas price
                if (self._involves_same_token_pair(target_tx, tx) and
                    tx.gas_price > target_tx.gas_price):
                    
                    # Calculate confidence based on similarity and timing
                    confidence = self._calculate_frontrun_confidence(target_tx, tx)
                    
                    if confidence >= 0.7:  # Higher threshold for frontrunning
                        
                        threat = MEVThreat(
                            threat_type=MEVThreatType.FRONTRUNNING,
                            target_transaction=target_tx.hash,
                            attacker_address=tx.from_address,
                            frontrun_transaction=tx.hash,
                            confidence=confidence,
                            severity=self._determine_threat_severity(confidence),
                            gas_price_advantage=float(tx.gas_price - target_tx.gas_price),
                            detection_time=datetime.utcnow(),
                            threatening_transactions=[tx.hash]
                        )
                        
                        threats.append(threat)
            
            return threats
            
        except Exception as e:
            self.logger.error(f"Frontrunning detection failed: {e}")
            return []

    async def _detect_backrunning(
        self, 
        target_tx: PendingTransaction, 
        mempool: List[PendingTransaction]
    ) -> List[MEVThreat]:
        """
        Detect backrunning/arbitrage patterns that might affect the target transaction.
        
        Args:
            target_tx: Target transaction to protect
            mempool: Current mempool transactions
            
        Returns:
            List of backrunning threats
        """
        threats = []
        
        if not target_tx.is_dex_interaction:
            return threats
            
        try:
            # Look for transactions that could exploit price changes from target tx
            for tx in mempool:
                if tx.hash == target_tx.hash:
                    continue
                    
                # Check for arbitrage opportunities that follow our transaction
                if (tx.timestamp > target_tx.timestamp and
                    self._could_be_arbitrage_followup(target_tx, tx)):
                    
                    confidence = self._calculate_backrun_confidence(target_tx, tx)
                    
                    if confidence >= 0.6:
                        threat = MEVThreat(
                            threat_type=MEVThreatType.BACKRUNNING,
                            target_transaction=target_tx.hash,
                            attacker_address=tx.from_address,
                            backrun_transaction=tx.hash,
                            confidence=confidence,
                            severity=self._determine_threat_severity(confidence),
                            detection_time=datetime.utcnow(),
                            threatening_transactions=[tx.hash]
                        )
                        
                        threats.append(threat)
            
            return threats
            
        except Exception as e:
            self.logger.error(f"Backrunning detection failed: {e}")
            return []

    async def _detect_jit_liquidity(
        self, 
        target_tx: PendingTransaction, 
        mempool: List[PendingTransaction]
    ) -> List[MEVThreat]:
        """
        Detect Just-In-Time liquidity provision patterns.
        
        Args:
            target_tx: Target transaction to protect
            mempool: Current mempool transactions
            
        Returns:
            List of JIT liquidity threats
        """
        threats = []
        
        try:
            # Look for liquidity provision followed by removal around target tx
            liquidity_adds = []
            liquidity_removes = []
            
            for tx in mempool:
                if tx.hash == target_tx.hash:
                    continue
                    
                # Identify liquidity provision transactions
                if self._is_liquidity_provision(tx):
                    if tx.timestamp <= target_tx.timestamp:
                        liquidity_adds.append(tx)
                    else:
                        liquidity_removes.append(tx)
            
            # Match adds and removes from same address
            for add_tx in liquidity_adds:
                for remove_tx in liquidity_removes:
                    if (add_tx.from_address == remove_tx.from_address and
                        self._involves_same_pool(add_tx, remove_tx, target_tx)):
                        
                        confidence = self._calculate_jit_confidence(add_tx, target_tx, remove_tx)
                        
                        if confidence >= 0.5:
                            threat = MEVThreat(
                                threat_type=MEVThreatType.JIT_LIQUIDITY,
                                target_transaction=target_tx.hash,
                                attacker_address=add_tx.from_address,
                                frontrun_transaction=add_tx.hash,
                                backrun_transaction=remove_tx.hash,
                                confidence=confidence,
                                severity=self._determine_threat_severity(confidence),
                                detection_time=datetime.utcnow(),
                                threatening_transactions=[add_tx.hash, remove_tx.hash]
                            )
                            
                            threats.append(threat)
            
            return threats
            
        except Exception as e:
            self.logger.error(f"JIT liquidity detection failed: {e}")
            return []
    
    # Helper methods for transaction analysis
    def _involves_same_token_pair(self, tx1: PendingTransaction, tx2: PendingTransaction) -> bool:
        """Check if two transactions involve the same token pair."""
        # This is a simplified implementation
        # In production, would parse transaction data to extract token addresses
        return (tx1.to_address == tx2.to_address and 
                tx1.data[:10] == tx2.data[:10])  # Same function signature

    def _calculate_sandwich_confidence(
        self, 
        frontrun_tx: PendingTransaction, 
        target_tx: PendingTransaction, 
        backrun_tx: PendingTransaction
    ) -> float:
        """Calculate confidence score for sandwich attack pattern."""
        confidence = 0.0
        
        # Gas price ordering (frontrun > target > backrun)
        if frontrun_tx.gas_price > target_tx.gas_price > backrun_tx.gas_price:
            confidence += 0.4
        
        # Time ordering
        if frontrun_tx.timestamp <= target_tx.timestamp <= backrun_tx.timestamp:
            confidence += 0.3
        
        # Same attacker address
        if frontrun_tx.from_address == backrun_tx.from_address:
            confidence += 0.3
        
        return min(confidence, 1.0)

    def _calculate_frontrun_confidence(self, target_tx: PendingTransaction, suspect_tx: PendingTransaction) -> float:
        """Calculate confidence score for frontrunning pattern."""
        confidence = 0.0
        
        # Higher gas price
        gas_advantage = float(suspect_tx.gas_price - target_tx.gas_price) / float(target_tx.gas_price)
        if gas_advantage > 0.1:  # 10% higher gas
            confidence += 0.4
        
        # Similar transaction data
        if target_tx.data[:10] == suspect_tx.data[:10]:  # Same function
            confidence += 0.4
        
        # Time proximity
        time_diff = abs((suspect_tx.timestamp - target_tx.timestamp).total_seconds())
        if time_diff < 60:  # Within 1 minute
            confidence += 0.2
        
        return min(confidence, 1.0)

    def _determine_threat_severity(self, confidence: float) -> SeverityLevel:
        """Determine threat severity based on confidence score."""
        if confidence >= 0.9:
            return SeverityLevel.CRITICAL
        elif confidence >= 0.8:
            return SeverityLevel.HIGH
        elif confidence >= 0.6:
            return SeverityLevel.MEDIUM
        elif confidence >= 0.4:
            return SeverityLevel.LOW
        else:
            return SeverityLevel.NEGLIGIBLE

    async def _generate_protection_recommendation(
        self, 
        transaction: PendingTransaction, 
        threats: List[MEVThreat]
    ) -> ProtectionRecommendation:
        """
        Generate protection recommendation based on detected threats.
        
        Args:
            transaction: Transaction to protect
            threats: List of detected threats
            
        Returns:
            Protection recommendation
        """
        if not threats:
            # No threats detected - minimal protection
            return ProtectionRecommendation(
                action=ProtectionAction.NO_ACTION,
                priority_level=PriorityLevel.LOW,
                gas_price_multiplier=1.0,
                use_private_relay=False,
                reasoning="No MEV threats detected"
            )
        
        # Analyze threat severity
        max_severity = max(threats, key=lambda t: self._get_severity_score(t.severity))
        threat_types = {threat.threat_type for threat in threats}
        
        # Generate recommendation based on threat analysis
        if SeverityLevel.CRITICAL in [t.severity for t in threats]:
            # Critical threats - maximum protection
            return ProtectionRecommendation(
                action=ProtectionAction.PRIVATE_RELAY,
                priority_level=PriorityLevel.CRITICAL,
                gas_price_multiplier=1.5,
                use_private_relay=True,
                delay_seconds=0,
                reasoning=f"Critical MEV threat detected: {list(threat_types)}"
            )
        
        elif MEVThreatType.SANDWICH_ATTACK in threat_types:
            # Sandwich attacks - private relay strongly recommended
            return ProtectionRecommendation(
                action=ProtectionAction.PRIVATE_RELAY,
                priority_level=PriorityLevel.HIGH,
                gas_price_multiplier=1.3,
                use_private_relay=True,
                reasoning="Sandwich attack detected - using private relay"
            )
        
        elif MEVThreatType.FRONTRUNNING in threat_types:
            # Frontrunning - increase gas price or use private relay
            high_confidence_frontrun = any(
                t.threat_type == MEVThreatType.FRONTRUNNING and t.confidence > 0.8 
                for t in threats
            )
            
            if high_confidence_frontrun:
                return ProtectionRecommendation(
                    action=ProtectionAction.PRIVATE_RELAY,
                    priority_level=PriorityLevel.HIGH,
                    gas_price_multiplier=1.4,
                    use_private_relay=True,
                    reasoning="High-confidence frontrunning detected"
                )
            else:
                return ProtectionRecommendation(
                    action=ProtectionAction.INCREASE_GAS,
                    priority_level=PriorityLevel.MEDIUM,
                    gas_price_multiplier=1.2,
                    use_private_relay=False,
                    reasoning="Potential frontrunning detected - increasing gas price"
                )
        
        else:
            # Medium threats - moderate protection
            return ProtectionRecommendation(
                action=ProtectionAction.INCREASE_GAS,
                priority_level=PriorityLevel.MEDIUM,
                gas_price_multiplier=1.1,
                use_private_relay=False,
                reasoning=f"Medium MEV threats detected: {list(threat_types)}"
            )

    def _get_severity_score(self, severity: SeverityLevel) -> int:
        """Convert severity level to numeric score for comparison."""
        severity_scores = {
            SeverityLevel.CRITICAL: 5,
            SeverityLevel.HIGH: 4,
            SeverityLevel.MEDIUM: 3,
            SeverityLevel.LOW: 2,
            SeverityLevel.NEGLIGIBLE: 1
        }
        return severity_scores.get(severity, 0)

    def _deduplicate_threats(self, threats: List[MEVThreat]) -> List[MEVThreat]:
        """Remove duplicate threats based on transaction hash and type."""
        seen = set()
        unique_threats = []
        
        for threat in threats:
            threat_key = (threat.threat_type, threat.target_transaction, threat.attacker_address)
            if threat_key not in seen:
                seen.add(threat_key)
                unique_threats.append(threat)
        
        return unique_threats

    async def _send_threat_notifications(
        self, 
        transaction: PendingTransaction, 
        threats: List[MEVThreat], 
        recommendation: ProtectionRecommendation
    ) -> None:
        """Send threat notifications to Django backend."""
        if not self._django_bridge:
            return
            
        try:
            notification = {
                'type': 'mev_threat_detected',
                'transaction_hash': transaction.hash,
                'threats': [
                    {
                        'type': threat.threat_type.value,
                        'severity': threat.severity.value,
                        'confidence': threat.confidence,
                        'attacker_address': threat.attacker_address
                    }
                    for threat in threats
                ],
                'recommendation': {
                    'action': recommendation.action.value,
                    'priority_level': recommendation.priority_level.value,
                    'gas_multiplier': recommendation.gas_price_multiplier,
                    'use_private_relay': recommendation.use_private_relay,
                    'reasoning': recommendation.reasoning
                },
                'timestamp': datetime.utcnow().isoformat()
            }
            
            await self._django_bridge.send_message('mev_threats', notification)
            
        except Exception as e:
            self.logger.error(f"Failed to send threat notifications: {e}")

    # Additional helper methods
    def _could_be_arbitrage_followup(self, target_tx: PendingTransaction, suspect_tx: PendingTransaction) -> bool:
        """Check if suspect transaction could be arbitrage following target transaction."""
        # Simple heuristic: different DEX interaction after our transaction
        return (suspect_tx.is_dex_interaction and 
                suspect_tx.to_address != target_tx.to_address and
                suspect_tx.timestamp > target_tx.timestamp)

    def _calculate_backrun_confidence(self, target_tx: PendingTransaction, suspect_tx: PendingTransaction) -> float:
        """Calculate confidence for backrunning pattern."""
        confidence = 0.0
        
        # Time ordering (suspect after target)
        if suspect_tx.timestamp > target_tx.timestamp:
            confidence += 0.3
        
        # Different DEX (arbitrage pattern)
        if suspect_tx.to_address != target_tx.to_address:
            confidence += 0.4
        
        # Value correlation
        if abs(float(suspect_tx.value - target_tx.value)) / float(target_tx.value) < 0.5:
            confidence += 0.3
        
        return min(confidence, 1.0)

    def _is_liquidity_provision(self, tx: PendingTransaction) -> bool:
        """Check if transaction is liquidity provision."""
        # Common LP function signatures
        lp_signatures = [
            '0xe8e33700',  # addLiquidity
            '0xf305d719',  # addLiquidityETH
            '0xbaa2abde',  # addLiquidityETH (V3)
            '0x0c49ccbe',  # mint (V3)
        ]
        
        if len(tx.data) >= 10:
            function_sig = tx.data[:10].lower()
            return function_sig in lp_signatures
        
        return False

    def _involves_same_pool(self, add_tx: PendingTransaction, remove_tx: PendingTransaction, target_tx: PendingTransaction) -> bool:
        """Check if transactions involve the same liquidity pool."""
        # Simplified check - in production would parse transaction data
        return (add_tx.to_address == remove_tx.to_address and
                self._involves_same_token_pair(add_tx, target_tx))

    def _calculate_jit_confidence(self, add_tx: PendingTransaction, target_tx: PendingTransaction, remove_tx: PendingTransaction) -> float:
        """Calculate confidence for JIT liquidity pattern."""
        confidence = 0.0
        
        # Time ordering (add before target, remove after)
        if add_tx.timestamp <= target_tx.timestamp <= remove_tx.timestamp:
            confidence += 0.4
        
        # Same attacker
        if add_tx.from_address == remove_tx.from_address:
            confidence += 0.4
        
        # Pool involvement
        if self._involves_same_pool(add_tx, remove_tx, target_tx):
            confidence += 0.2
        
        return min(confidence, 1.0)

    def _estimate_sandwich_profit(self, frontrun_tx: PendingTransaction, target_tx: PendingTransaction, backrun_tx: PendingTransaction) -> Decimal:
        """Estimate potential profit from sandwich attack."""
        # Simplified calculation based on transaction values
        # In production would use more sophisticated price impact models
        target_value = target_tx.value
        estimated_slippage = Decimal('0.005')  # 0.5% estimated slippage
        return target_value * estimated_slippage

    async def apply_protection_recommendation(
        self, 
        transaction: TxParams, 
        recommendation: ProtectionRecommendation
    ) -> TxParams:
        """
        Apply MEV protection recommendation to a transaction.
        
        Args:
            transaction: Original transaction parameters
            recommendation: Protection recommendation to apply
            
        Returns:
            Modified transaction parameters with protection applied
        """
        protected_tx = transaction.copy()
        
        try:
            if recommendation.action == ProtectionAction.INCREASE_GAS:
                # Increase gas price by multiplier
                current_gas_price = protected_tx.get('gasPrice', 0)
                new_gas_price = int(current_gas_price * recommendation.gas_price_multiplier)
                protected_tx['gasPrice'] = new_gas_price
                
                self.logger.info(f"Applied gas increase: {current_gas_price} -> {new_gas_price} wei")
                
            elif recommendation.action == ProtectionAction.DELAY_EXECUTION:
                # Add timing delay (would be handled by caller)
                protected_tx['_mev_delay'] = recommendation.delay_seconds
                
            elif recommendation.action == ProtectionAction.PRIVATE_RELAY:
                # Mark for private relay routing
                protected_tx['_use_private_relay'] = True
                protected_tx['_priority_level'] = recommendation.priority_level.value
                
                self.logger.info(f"Marked for private relay with priority: {recommendation.priority_level.value}")
            
            # Track action taken
            self._protection_actions_taken[recommendation.action] += 1
            
            return protected_tx
            
        except Exception as e:
            self.logger.error(f"Failed to apply protection recommendation: {e}")
            return transaction

    def get_protection_statistics(self) -> Dict[str, Any]:
        """
        Get MEV protection performance statistics.
        
        Returns:
            Dictionary containing protection statistics
        """
        avg_analysis_time = (
            sum(self._analysis_latencies) / len(self._analysis_latencies)
            if self._analysis_latencies else 0.0
        )
        
        return {
            "threats_detected": self._threats_detected,
            "threats_prevented": self._threats_prevented,
            "active_threats": len(self._active_threats),
            "protection_actions": dict(self._protection_actions_taken),
            "average_analysis_time_ms": avg_analysis_time,
            "mempool_transactions_tracked": len(self._pending_transactions),
            "gas_price_samples": len(self._gas_price_history),
            "detection_accuracy": sum(self._detection_accuracy) / len(self._detection_accuracy) if self._detection_accuracy else 0.0
        }


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

async def create_mev_protection_engine(
    private_relay: PrivateRelayManager
) -> MEVProtectionEngine:
    """
    Factory function to create and initialize an MEV protection engine.
    
    Args:
        private_relay: Private relay manager instance
        
    Returns:
        Fully initialized MEVProtectionEngine instance
    """
    config = await get_config()
    engine = MEVProtectionEngine(config)
    await engine.initialize(private_relay)
    return engine


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    'MEVProtectionEngine',
    'MEVThreat',
    'ProtectionRecommendation',
    'ProtectionAnalysis',
    'PendingTransaction',
    'MEVThreatType',
    'ProtectionAction',
    'SeverityLevel',
    'create_mev_protection_engine'
]