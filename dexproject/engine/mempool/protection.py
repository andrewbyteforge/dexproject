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
from ...shared.schemas import (
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
                    await self._send_threat_alerts(threats, recommendation)
            
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
        Detect MEV threats targeting the given transaction.
        
        Args:
            target_tx: Transaction to protect
            mempool: Current mempool state
            
        Returns:
            List of detected MEV threats
        """
        threats = []
        
        # Only analyze DEX transactions for MEV threats
        if not target_tx.is_dex_interaction:
            return threats
        
        # Detect sandwich attacks
        sandwich_threats = await self._detect_sandwich_attacks(target_tx, mempool)
        threats.extend(sandwich_threats)
        
        # Detect frontrunning attempts
        frontrun_threats = await self._detect_frontrunning(target_tx, mempool)
        threats.extend(frontrun_threats)
        
        # Detect backrunning opportunities (less critical)
        backrun_threats = await self._detect_backrunning(target_tx, mempool)
        threats.extend(backrun_threats)
        
        # Filter threats by confidence threshold
        high_confidence_threats = [
            threat for threat in threats 
            if threat.confidence >= 0.6
        ]
        
        return high_confidence_threats
    
    async def _detect_sandwich_attacks(
        self,
        target_tx: PendingTransaction,
        mempool: List[PendingTransaction]
    ) -> List[MEVThreat]:
        """
        Detect sandwich attack patterns targeting the transaction.
        
        Args:
            target_tx: Target transaction
            mempool: Current mempool state
            
        Returns:
            List of sandwich attack threats
        """
        threats = []
        
        if not target_tx.target_token:
            return threats
        
        # Look for transactions that could be sandwich components
        potential_front = []
        potential_back = []
        
        for tx in mempool:
            if (tx.hash != target_tx.hash and 
                tx.is_dex_interaction and 
                tx.target_token == target_tx.target_token):
                
                # Check if this could be front-running transaction
                if (tx.gas_price > target_tx.gas_price and
                    tx.timestamp <= target_tx.timestamp):
                    potential_front.append(tx)
                
                # Check if this could be back-running transaction
                elif (tx.gas_price < target_tx.gas_price and
                      tx.timestamp > target_tx.timestamp):
                    potential_back.append(tx)
        
        # Analyze potential sandwich patterns
        for front_tx in potential_front:
            for back_tx in potential_back:
                # Check if front and back transactions are from same address
                if front_tx.from_address == back_tx.from_address:
                    # Calculate sandwich profitability
                    confidence = self._calculate_sandwich_confidence(
                        front_tx, target_tx, back_tx
                    )
                    
                    if confidence >= 0.6:
                        threat = MEVThreat(
                            threat_type=MEVThreatType.SANDWICH_ATTACK,
                            severity=self._calculate_threat_severity(confidence),
                            confidence=confidence,
                            target_transaction=target_tx.hash,
                            threatening_transactions=[front_tx.hash, back_tx.hash],
                            metadata={
                                "front_tx": front_tx.hash,
                                "back_tx": back_tx.hash,
                                "attacker_address": front_tx.from_address,
                                "token_address": target_tx.target_token,
                                "gas_price_difference": float(front_tx.gas_price - target_tx.gas_price)
                            }
                        )
                        threats.append(threat)
        
        return threats
    
    async def _detect_frontrunning(
        self,
        target_tx: PendingTransaction,
        mempool: List[PendingTransaction]
    ) -> List[MEVThreat]:
        """
        Detect frontrunning attempts against the transaction.
        
        Args:
            target_tx: Target transaction
            mempool: Current mempool state
            
        Returns:
            List of frontrunning threats
        """
        threats = []
        
        if not target_tx.is_dex_interaction:
            return threats
        
        # Look for transactions with similar parameters but higher gas prices
        for tx in mempool:
            if (tx.hash != target_tx.hash and
                tx.is_dex_interaction and
                tx.target_token == target_tx.target_token and
                tx.gas_price > target_tx.gas_price * Decimal('1.1')):
                
                # Calculate similarity and frontrun probability
                confidence = self._calculate_frontrun_confidence(tx, target_tx)
                
                if confidence >= 0.7:
                    threat = MEVThreat(
                        threat_type=MEVThreatType.FRONTRUNNING,
                        severity=self._calculate_threat_severity(confidence),
                        confidence=confidence,
                        target_transaction=target_tx.hash,
                        threatening_transactions=[tx.hash],
                        metadata={
                            "frontrunner_tx": tx.hash,
                            "frontrunner_address": tx.from_address,
                            "gas_price_advantage": float(tx.gas_price - target_tx.gas_price),
                            "time_advantage_ms": (target_tx.timestamp - tx.timestamp).total_seconds() * 1000
                        }
                    )
                    threats.append(threat)
        
        return threats
    
    async def _detect_backrunning(
        self,
        target_tx: PendingTransaction,
        mempool: List[PendingTransaction]
    ) -> List[MEVThreat]:
        """
        Detect backrunning opportunities (lower severity).
        
        Args:
            target_tx: Target transaction
            mempool: Current mempool state
            
        Returns:
            List of backrunning threats
        """
        threats = []
        
        # Backrunning is generally less harmful but worth tracking
        for tx in mempool:
            if (tx.hash != target_tx.hash and
                tx.is_dex_interaction and
                tx.target_token == target_tx.target_token and
                tx.gas_price < target_tx.gas_price and
                tx.timestamp > target_tx.timestamp):
                
                confidence = 0.5  # Lower confidence as it's less harmful
                
                threat = MEVThreat(
                    threat_type=MEVThreatType.BACKRUNNING,
                    severity=SeverityLevel.LOW,
                    confidence=confidence,
                    target_transaction=target_tx.hash,
                    threatening_transactions=[tx.hash],
                    metadata={
                        "backrunner_tx": tx.hash,
                        "backrunner_address": tx.from_address,
                    }
                )
                threats.append(threat)
        
        return threats
    
    def _calculate_sandwich_confidence(
        self,
        front_tx: PendingTransaction,
        target_tx: PendingTransaction,
        back_tx: PendingTransaction
    ) -> float:
        """
        Calculate confidence level for sandwich attack detection.
        
        Args:
            front_tx: Front-running transaction
            target_tx: Target transaction
            back_tx: Back-running transaction
            
        Returns:
            Confidence score (0.0 to 1.0)
        """
        confidence = 0.0
        
        # Same attacker address (strong indicator)
        if front_tx.from_address == back_tx.from_address:
            confidence += 0.4
        
        # Gas price pattern analysis
        if (front_tx.gas_price > target_tx.gas_price and
            back_tx.gas_price < target_tx.gas_price):
            confidence += 0.3
        
        # Timing analysis (transactions should be close in time)
        time_span = (back_tx.timestamp - front_tx.timestamp).total_seconds()
        if time_span < 15:  # Within 1 block
            confidence += 0.2
        elif time_span < 60:  # Within ~4 blocks
            confidence += 0.1
        
        # Amount analysis (if available)
        if (front_tx.swap_amount_in and target_tx.swap_amount_in and
            back_tx.swap_amount_out):
            # Check if amounts suggest profitable sandwich
            confidence += 0.1
        
        return min(confidence, 1.0)
    
    def _calculate_frontrun_confidence(
        self,
        frontrun_tx: PendingTransaction,
        target_tx: PendingTransaction
    ) -> float:
        """
        Calculate confidence level for frontrunning detection.
        
        Args:
            frontrun_tx: Potential frontrunning transaction
            target_tx: Target transaction
            
        Returns:
            Confidence score (0.0 to 1.0)
        """
        confidence = 0.0
        
        # Gas price advantage (strong indicator)
        gas_advantage = float(frontrun_tx.gas_price / target_tx.gas_price)
        if gas_advantage > 1.5:
            confidence += 0.4
        elif gas_advantage > 1.2:
            confidence += 0.3
        elif gas_advantage > 1.1:
            confidence += 0.2
        
        # Same target token
        if frontrun_tx.target_token == target_tx.target_token:
            confidence += 0.2
        
        # Similar transaction data
        if frontrun_tx.data[:10] == target_tx.data[:10]:  # Same function selector
            confidence += 0.2
        
        # Timing (frontrunner should be submitted around same time)
        time_diff = abs((frontrun_tx.timestamp - target_tx.timestamp).total_seconds())
        if time_diff < 5:
            confidence += 0.2
        elif time_diff < 15:
            confidence += 0.1
        
        return min(confidence, 1.0)
    
    def _calculate_threat_severity(self, confidence: float) -> SeverityLevel:
        """
        Calculate threat severity based on confidence and potential impact.
        
        Args:
            confidence: Threat confidence score
            
        Returns:
            Severity level
        """
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
        target_tx: PendingTransaction,
        threats: List[MEVThreat]
    ) -> ProtectionRecommendation:
        """
        Generate MEV protection recommendation based on detected threats.
        
        Args:
            target_tx: Transaction to protect
            threats: Detected MEV threats
            
        Returns:
            Protection recommendation
        """
        # Default safe recommendation
        if not threats:
            return ProtectionRecommendation(
                action=ProtectionAction.PRIVATE_RELAY,
                priority_level=PriorityLevel.MEDIUM,
                gas_price_multiplier=1.0,
                use_private_relay=True,
                reasoning="No specific threats detected, using private relay as precaution"
            )
        
        # Analyze threat severity
        max_severity = max(threat.severity for threat in threats)
        threat_types = {threat.threat_type for threat in threats}
        max_confidence = max(threat.confidence for threat in threats)
        
        # Determine protection strategy based on threats
        if SeverityLevel.CRITICAL in [threat.severity for threat in threats]:
            # Critical threats require immediate private relay + gas increase
            return ProtectionRecommendation(
                action=ProtectionAction.PRIVATE_RELAY,
                priority_level=PriorityLevel.CRITICAL,
                gas_price_multiplier=1.5,
                use_private_relay=True,
                reasoning=f"Critical MEV threats detected: {', '.join(t.value for t in threat_types)}"
            )
        
        elif MEVThreatType.SANDWICH_ATTACK in threat_types:
            # Sandwich attacks require private relay
            return ProtectionRecommendation(
                action=ProtectionAction.PRIVATE_RELAY,
                priority_level=PriorityLevel.HIGH,
                gas_price_multiplier=1.2,
                use_private_relay=True,
                reasoning="Sandwich attack detected, using private relay for protection"
            )
        
        elif MEVThreatType.FRONTRUNNING in threat_types:
            # Frontrunning can be countered with gas increase or private relay
            if max_confidence > 0.8:
                return ProtectionRecommendation(
                    action=ProtectionAction.PRIVATE_RELAY,
                    priority_level=PriorityLevel.HIGH,
                    gas_price_multiplier=1.3,
                    use_private_relay=True,
                    reasoning="High-confidence frontrunning detected"
                )
            else:
                return ProtectionRecommendation(
                    action=ProtectionAction.INCREASE_GAS,
                    priority_level=PriorityLevel.MEDIUM,
                    gas_price_multiplier=1.4,
                    use_private_relay=False,
                    reasoning="Potential frontrunning, increasing gas price"
                )
        
        else:
            # Lower severity threats
            return ProtectionRecommendation(
                action=ProtectionAction.PRIVATE_RELAY,
                priority_level=PriorityLevel.MEDIUM,
                gas_price_multiplier=1.1,
                use_private_relay=True,
                reasoning=f"MEV threats detected: {', '.join(t.value for t in threat_types)}"
            )
    
    async def apply_protection_recommendation(
        self,
        transaction: TxParams,
        recommendation: ProtectionRecommendation
    ) -> TxParams:
        """
        Apply protection recommendation to transaction parameters.
        
        Args:
            transaction: Original transaction parameters
            recommendation: Protection recommendation to apply
            
        Returns:
            Modified transaction parameters
        """
        protected_tx = transaction.copy()
        
        try:
            # Apply gas price modifications
            if recommendation.gas_price_multiplier != 1.0:
                if 'gasPrice' in protected_tx:
                    current_gas = Decimal(str(protected_tx['gasPrice']))
                    new_gas = int(current_gas * Decimal(str(recommendation.gas_price_multiplier)))
                    protected_tx['gasPrice'] = new_gas
                    
                elif 'maxFeePerGas' in protected_tx:
                    current_fee = Decimal(str(protected_tx['maxFeePerGas']))
                    new_fee = int(current_fee * Decimal(str(recommendation.gas_price_multiplier)))
                    protected_tx['maxFeePerGas'] = new_fee
            
            # Track protection action
            self._protection_actions_taken[recommendation.action] += 1
            
            self.logger.info(
                f"Applied MEV protection: {recommendation.action.value}, "
                f"gas multiplier: {recommendation.gas_price_multiplier}"
            )
            
            return protected_tx
            
        except Exception as e:
            self.logger.error(f"Failed to apply protection recommendation: {e}")
            return transaction
    
    async def _send_threat_alerts(
        self,
        threats: List[MEVThreat],
        recommendation: ProtectionRecommendation
    ) -> None:
        """Send MEV threat alerts to Django backend."""
        if not self._django_bridge:
            return
        
        try:
            alert_data = {
                "component": "mev_protection",
                "timestamp": datetime.utcnow().isoformat(),
                "threats_detected": len(threats),
                "max_severity": max(threat.severity.value for threat in threats),
                "threat_types": [threat.threat_type.value for threat in threats],
                "protection_action": recommendation.action.value,
                "threats": [threat.to_dict() for threat in threats],
                "recommendation": recommendation.to_dict()
            }
            
            # Send through Django bridge
            self.logger.debug(f"Sending MEV threat alert to Django: {alert_data}")
            
        except Exception as e:
            self.logger.error(f"Failed to send threat alert to Django: {e}")
    
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
            "gas_price_samples": len(self._gas_price_history)
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
    'PendingTransaction',
    'MEVThreatType',
    'ProtectionAction',
    'SeverityLevel',
    'create_mev_protection_engine'
]