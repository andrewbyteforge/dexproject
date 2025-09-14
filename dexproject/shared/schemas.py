"""
Shared schemas for communication between async engine and Django backend.

This module defines the data models used for Redis pub/sub messaging and seamless
communication between the high-speed async engine and the Django trading bot backend.

Uses Pydantic when available, falls back to dataclasses for import safety.
"""

import json
import logging
import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Union

# Try to import Pydantic, fall back to dataclasses if not available
try:
    from pydantic import BaseModel, Field, validator
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    from dataclasses import dataclass, asdict
    
    # Create minimal Field replacement
    def Field(default=None, description=None, **kwargs):
        return default

logger = logging.getLogger(__name__)

# =============================================================================
# ENUMS & CONSTANTS
# =============================================================================

class ChainType(str, Enum):
    """Supported blockchain networks."""
    ETHEREUM = "ethereum"
    BASE = "base"
    POLYGON = "polygon"
    BSC = "bsc"
    ARBITRUM = "arbitrum"
    OPTIMISM = "optimism"

class PairSource(str, Enum):
    """Sources for pair discovery."""
    WEBSOCKET = "websocket"
    MEMPOOL = "mempool"
    HTTP_POLL = "http_poll"
    DEX_SCREENER = "dex_screener"
    MANUAL = "manual"

class RiskLevel(str, Enum):
    """Risk assessment levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MINIMAL = "minimal"

class DecisionType(str, Enum):
    """Trading decision types."""
    BUY = "buy"
    SELL = "sell"
    SKIP = "skip"
    HOLD = "hold"

class MessageType(str, Enum):
    """Redis message types for Engine ↔ Django communication."""
    NEW_PAIR_DISCOVERED = "new_pair_discovered"
    FAST_RISK_COMPLETE = "fast_risk_complete"
    COMPREHENSIVE_RISK_COMPLETE = "comprehensive_risk_complete"
    TRADING_DECISION = "trading_decision"
    EXECUTION_COMPLETE = "execution_complete"
    ENGINE_STATUS = "engine_status"
    ENGINE_HEARTBEAT = "engine_heartbeat"
    ALERT_TRIGGERED = "alert_triggered"
    CONFIG_UPDATE = "config_update"
    EMERGENCY_STOP = "emergency_stop"

# =============================================================================
# BASE MODELS
# =============================================================================

if PYDANTIC_AVAILABLE:
    class BaseMessage(BaseModel):
        """Base class for all Redis messages."""
        
        message_type: MessageType
        timestamp: datetime = Field(default_factory=datetime.utcnow)
        correlation_id: Optional[str] = None
        source_service: str
        engine_id: Optional[str] = None
        
        class Config:
            """Pydantic configuration."""
            use_enum_values = True
            json_encoders = {
                datetime: lambda v: v.isoformat(),
                Decimal: lambda v: str(v),
            }

    class TokenInfo(BaseModel):
        """Token information model."""
        
        address: str = Field(..., description="Token contract address")
        symbol: Optional[str] = Field(None, description="Token symbol")
        name: Optional[str] = Field(None, description="Token name")
        decimals: Optional[int] = Field(None, description="Token decimals")
        total_supply: Optional[str] = Field(None, description="Total token supply")
        
        @validator('address')
        def validate_address(cls, v: str) -> str:
            """Validate Ethereum address format."""
            if not v.startswith('0x') or len(v) != 42:
                raise ValueError("Invalid Ethereum address format")
            return v.lower()

    class PairInfo(BaseModel):
        """DEX pair information model."""
        
        pair_address: str = Field(..., description="Pair contract address")
        token0: TokenInfo = Field(..., description="First token in pair")
        token1: TokenInfo = Field(..., description="Second token in pair")
        dex_name: str = Field(..., description="DEX name (e.g., 'uniswap_v3')")
        fee_tier: int = Field(..., description="Fee tier in basis points")
        liquidity_usd: Optional[Decimal] = Field(None, description="Total liquidity in USD")
        volume_24h_usd: Optional[Decimal] = Field(None, description="24h trading volume in USD")
        price_usd: Optional[Decimal] = Field(None, description="Current token price in USD")
        block_number: Optional[int] = Field(None, description="Block number when created")
        transaction_hash: Optional[str] = Field(None, description="Creation transaction hash")
        
        @validator('pair_address')
        def validate_pair_address(cls, v: str) -> str:
            """Validate pair address format."""
            if not v.startswith('0x') or len(v) != 42:
                raise ValueError("Invalid pair address format")
            return v.lower()

else:
    # Dataclass fallbacks when Pydantic is not available
    @dataclass
    class BaseMessage:
        """Base class for all Redis messages."""
        message_type: str
        timestamp: str
        correlation_id: str
        source_service: str
        engine_id: Optional[str] = None
        
        def to_dict(self) -> Dict[str, Any]:
            """Convert to dictionary for JSON serialization."""
            return asdict(self)
        
        @classmethod
        def from_dict(cls, data: Dict[str, Any]):
            """Create instance from dictionary."""
            return cls(**data)

    @dataclass 
    class TokenInfo:
        """Token information for messages."""
        address: str
        symbol: Optional[str] = None
        name: Optional[str] = None
        decimals: Optional[int] = None
        total_supply: Optional[str] = None

    @dataclass
    class PairInfo:
        """Trading pair information."""
        pair_address: str
        token0: TokenInfo
        token1: TokenInfo
        dex_name: str
        fee_tier: int
        liquidity_usd: Optional[str] = None
        volume_24h_usd: Optional[str] = None
        price_usd: Optional[str] = None
        block_number: Optional[int] = None
        transaction_hash: Optional[str] = None

# =============================================================================
# DISCOVERY MESSAGES (Engine → Django)
# =============================================================================

if PYDANTIC_AVAILABLE:
    class NewPairDiscovered(BaseMessage):
        """Message sent when a new trading pair is discovered by the engine."""
        
        message_type: MessageType = Field(default=MessageType.NEW_PAIR_DISCOVERED)
        chain_id: int = Field(..., description="Blockchain network ID")
        pair_info: PairInfo = Field(..., description="Discovered pair information")
        source: PairSource = Field(..., description="Discovery source")
        discovery_metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional discovery data")
        
        # Engine processing info
        discovery_latency_ms: Optional[int] = Field(None, description="Time from event to discovery")
        next_action: str = Field(default="fast_risk_assessment", description="Next processing step")
else:
    @dataclass
    class NewPairDiscovered(BaseMessage):
        """Message sent when engine discovers a new trading pair."""
        chain_id: int
        pair_info: Dict[str, Any]  # PairInfo as dict
        source: str
        discovery_metadata: Dict[str, Any] = None
        discovery_latency_ms: Optional[int] = None
        next_action: str = "fast_risk_assessment"
        
        def __post_init__(self):
            if self.discovery_metadata is None:
                self.discovery_metadata = {}

# =============================================================================
# RISK ASSESSMENT MESSAGES
# =============================================================================

if PYDANTIC_AVAILABLE:
    class RiskCheckResult(BaseModel):
        """Individual risk check result."""
        
        check_name: str = Field(..., description="Name of the risk check")
        check_type: str = Field(..., description="Type/category of risk check")
        passed: bool = Field(..., description="Whether the check passed")
        score: Decimal = Field(..., description="Risk score (0-100, lower is better)")
        confidence: Decimal = Field(..., description="Confidence in the result (0-100)")
        details: Dict[str, Any] = Field(default_factory=dict, description="Detailed check results")
        execution_time_ms: Optional[int] = Field(None, description="Check execution time in milliseconds")
        error_message: Optional[str] = Field(None, description="Error message if check failed")
        is_blocking: bool = Field(default=False, description="Whether this is a blocking check")

    class FastRiskAssessment(BaseMessage):
        """Fast risk assessment results from the engine (sub-second checks)."""
        
        message_type: MessageType = Field(default=MessageType.FAST_RISK_COMPLETE)
        pair_address: str = Field(..., description="Assessed pair address")
        token_address: str = Field(..., description="Primary token address being assessed")
        chain_id: int = Field(..., description="Blockchain network ID")
        
        # Overall assessment
        overall_risk_level: RiskLevel = Field(..., description="Overall risk assessment")
        overall_score: Decimal = Field(..., description="Overall risk score (0-100)")
        confidence_score: Decimal = Field(..., description="Overall confidence (0-100)")
        is_tradeable: bool = Field(..., description="Whether token passes fast risk checks")
        
        # Processing details
        checks_performed: List[RiskCheckResult] = Field(..., description="Individual check results")
        processing_time_ms: int = Field(..., description="Total processing time")
        blocking_issues: List[str] = Field(default_factory=list, description="Critical blocking issues found")
        
        # Next steps
        requires_comprehensive_assessment: bool = Field(default=True, description="Whether comprehensive checks are needed")
        recommended_action: str = Field(..., description="Recommended next action")
        
        # Integration with Django risk system
        django_risk_assessment_id: Optional[str] = Field(None, description="Related Django RiskAssessment ID")
else:
    @dataclass
    class RiskCheckResult:
        """Individual risk check result."""
        check_name: str
        check_type: str
        passed: bool
        score: float
        confidence: float
        details: Dict[str, Any] = None
        execution_time_ms: Optional[int] = None
        error_message: Optional[str] = None
        is_blocking: bool = False
        
        def __post_init__(self):
            if self.details is None:
                self.details = {}

    @dataclass
    class FastRiskAssessment(BaseMessage):
        """Message sent when fast risk assessment is complete."""
        pair_address: str
        token_address: str
        chain_id: int
        overall_risk_level: str
        overall_score: float
        confidence_score: float
        is_tradeable: bool
        checks_performed: List[Dict[str, Any]]
        processing_time_ms: int
        blocking_issues: List[str] = None
        requires_comprehensive_assessment: bool = True
        recommended_action: str = "comprehensive_assessment"
        django_risk_assessment_id: Optional[str] = None
        
        def __post_init__(self):
            if self.blocking_issues is None:
                self.blocking_issues = []

# =============================================================================
# TRADING DECISION MESSAGES (Engine → Django)
# =============================================================================

if PYDANTIC_AVAILABLE:
    class TradingSignal(BaseModel):
        """Individual trading signal."""
        
        signal_name: str = Field(..., description="Name of the signal")
        signal_type: str = Field(..., description="Type/category of signal")
        value: Union[str, int, float, bool, Decimal] = Field(..., description="Signal value")
        weight: Decimal = Field(..., description="Signal weight in decision making")
        confidence: Decimal = Field(..., description="Confidence in signal (0-100)")
        rationale: str = Field(..., description="Human-readable explanation")

    class TradingDecision(BaseMessage):
        """Trading decision with AI thought process from the engine."""
        
        message_type: MessageType = Field(default=MessageType.TRADING_DECISION)
        pair_address: str = Field(..., description="Target pair address")
        token_address: str = Field(..., description="Target token address")
        chain_id: int = Field(..., description="Blockchain network ID")
        
        # Decision details
        decision: DecisionType = Field(..., description="Trading decision")
        confidence: Decimal = Field(..., description="Decision confidence (0-100)")
        position_size_eth: Optional[Decimal] = Field(None, description="Recommended position size in ETH")
        position_size_usd: Optional[Decimal] = Field(None, description="Recommended position size in USD")
        max_slippage_percent: Optional[Decimal] = Field(None, description="Maximum allowed slippage")
        
        # AI Thought Process
        signals_analyzed: List[TradingSignal] = Field(..., description="All signals considered")
        narrative_summary: str = Field(..., description="AI reasoning narrative")
        risk_factors: List[str] = Field(default_factory=list, description="Key risk factors identified")
        opportunity_factors: List[str] = Field(default_factory=list, description="Key opportunity factors")
        
        # Technical Analysis
        fast_risk_score: Decimal = Field(..., description="Fast risk assessment score")
        comprehensive_risk_score: Optional[Decimal] = Field(None, description="Comprehensive risk score")
        
        # Integration with Django
        django_risk_assessment_id: Optional[str] = Field(None, description="Related Django RiskAssessment ID")
        strategy_id: Optional[str] = Field(None, description="Django Strategy ID used")
else:
    @dataclass
    class TradingSignal:
        """Individual trading signal."""
        signal_name: str
        signal_type: str
        value: Union[str, int, float, bool]
        weight: float
        confidence: float
        rationale: str

    @dataclass
    class TradingDecision(BaseMessage):
        """Message sent when trading decision is made."""
        pair_address: str
        token_address: str
        chain_id: int
        decision: str
        confidence: float
        position_size_eth: Optional[str] = None
        position_size_usd: Optional[str] = None
        max_slippage_percent: Optional[float] = None
        signals_analyzed: List[Dict[str, Any]] = None
        narrative_summary: str = ""
        risk_factors: List[str] = None
        opportunity_factors: List[str] = None
        fast_risk_score: float = 0.0
        comprehensive_risk_score: Optional[float] = None
        django_risk_assessment_id: Optional[str] = None
        strategy_id: Optional[str] = None
        
        def __post_init__(self):
            if self.signals_analyzed is None:
                self.signals_analyzed = []
            if self.risk_factors is None:
                self.risk_factors = []
            if self.opportunity_factors is None:
                self.opportunity_factors = []

# =============================================================================
# EXECUTION MESSAGES (Engine → Django)
# =============================================================================

if PYDANTIC_AVAILABLE:
    class ExecutionResult(BaseMessage):
        """Trade execution result from the engine."""
        
        message_type: MessageType = Field(default=MessageType.EXECUTION_COMPLETE)
        pair_address: str = Field(..., description="Traded pair address")
        token_address: str = Field(..., description="Traded token address")
        chain_id: int = Field(..., description="Blockchain network ID")
        decision_type: DecisionType = Field(..., description="Original decision type")
        
        # Django model references
        trade_id: Optional[str] = Field(None, description="Django Trade model ID")
        position_id: Optional[str] = Field(None, description="Django Position model ID")
        
        # Execution Details
        success: bool = Field(..., description="Whether execution was successful")
        transaction_hash: Optional[str] = Field(None, description="Blockchain transaction hash")
        block_number: Optional[int] = Field(None, description="Block number of execution")
        gas_used: Optional[int] = Field(None, description="Gas units consumed")
        gas_price_gwei: Optional[Decimal] = Field(None, description="Gas price in Gwei")
        actual_slippage_percent: Optional[Decimal] = Field(None, description="Actual slippage experienced")
        tokens_received: Optional[str] = Field(None, description="Tokens received from trade")
        eth_spent: Optional[Decimal] = Field(None, description="ETH spent on trade")
        usd_value: Optional[Decimal] = Field(None, description="USD value of trade")
        
        # Timing and Performance
        execution_time_ms: int = Field(..., description="Total execution time")
        latency_breakdown: Dict[str, int] = Field(default_factory=dict, description="Detailed latency breakdown")
        
        # Error Handling
        error_message: Optional[str] = Field(None, description="Error message if execution failed")
        retry_count: int = Field(default=0, description="Number of execution retries")
        
        # Paper Trading
        is_paper_trade: bool = Field(default=False, description="Whether this was a paper trade")
        paper_trade_notes: Optional[str] = Field(None, description="Paper trading simulation notes")
else:
    @dataclass
    class ExecutionResult(BaseMessage):
        """Message sent when trade execution is complete."""
        pair_address: str
        token_address: str
        chain_id: int
        decision_type: str
        trade_id: Optional[str] = None
        position_id: Optional[str] = None
        success: bool = False
        transaction_hash: Optional[str] = None
        block_number: Optional[int] = None
        gas_used: Optional[int] = None
        gas_price_gwei: Optional[str] = None
        actual_slippage_percent: Optional[float] = None
        tokens_received: Optional[str] = None
        eth_spent: Optional[str] = None
        usd_value: Optional[str] = None
        execution_time_ms: int = 0
        latency_breakdown: Dict[str, int] = None
        error_message: Optional[str] = None
        retry_count: int = 0
        is_paper_trade: bool = False
        paper_trade_notes: Optional[str] = None
        
        def __post_init__(self):
            if self.latency_breakdown is None:
                self.latency_breakdown = {}

# =============================================================================
# STATUS & MONITORING MESSAGES (Engine → Django)
# =============================================================================

if PYDANTIC_AVAILABLE:
    class ServiceHealthStatus(BaseModel):
        """Health status for a service component."""
        
        service_name: str = Field(..., description="Name of the service")
        status: str = Field(..., description="Status (healthy/degraded/unhealthy)")
        uptime_seconds: int = Field(..., description="Service uptime in seconds")
        last_activity: datetime = Field(..., description="Last activity timestamp")
        error_count_1h: int = Field(default=0, description="Error count in last hour")
        performance_metrics: Dict[str, Any] = Field(default_factory=dict, description="Performance metrics")

    class EngineStatus(BaseMessage):
        """Overall engine status report."""
        
        message_type: MessageType = Field(default=MessageType.ENGINE_STATUS)
        engine_id: str = Field(..., description="Engine instance ID")
        status: str = Field(..., description="Overall engine status")
        uptime_seconds: int = Field(..., description="Engine uptime")
        
        # Operational Metrics
        pairs_discovered_1h: int = Field(default=0, description="Pairs discovered in last hour")
        risk_assessments_1h: int = Field(default=0, description="Fast risk assessments in last hour")
        decisions_made_1h: int = Field(default=0, description="Trading decisions made in last hour")
        trades_executed_1h: int = Field(default=0, description="Trades executed in last hour")
        
        # Service Health
        service_health: List[ServiceHealthStatus] = Field(..., description="Component health status")
        
        # Performance Metrics
        avg_fast_risk_time_ms: Optional[int] = Field(None, description="Average fast risk assessment time")
        avg_decision_time_ms: Optional[int] = Field(None, description="Average decision making time")
        avg_execution_time_ms: Optional[int] = Field(None, description="Average trade execution time")
        
        # Configuration
        trading_mode: str = Field(..., description="Current trading mode (PAPER/LIVE)")
        supported_chains: List[int] = Field(..., description="Supported chain IDs")
        active_strategies: List[str] = Field(default_factory=list, description="Active strategy IDs")
else:
    @dataclass
    class ServiceHealthStatus:
        """Health status for a service component."""
        service_name: str
        status: str
        uptime_seconds: int
        last_activity: str  # datetime as string
        error_count_1h: int = 0
        performance_metrics: Dict[str, Any] = None
        
        def __post_init__(self):
            if self.performance_metrics is None:
                self.performance_metrics = {}

    @dataclass
    class EngineStatus(BaseMessage):
        """Message sent for engine status updates."""
        engine_id: str
        status: str
        uptime_seconds: int
        pairs_discovered_1h: int = 0
        risk_assessments_1h: int = 0
        decisions_made_1h: int = 0
        trades_executed_1h: int = 0
        service_health: List[Dict[str, Any]] = None
        avg_fast_risk_time_ms: Optional[int] = None
        avg_decision_time_ms: Optional[int] = None
        avg_execution_time_ms: Optional[int] = None
        trading_mode: str = "PAPER"
        supported_chains: List[int] = None
        active_strategies: List[str] = None
        
        def __post_init__(self):
            if self.service_health is None:
                self.service_health = []
            if self.supported_chains is None:
                self.supported_chains = []
            if self.active_strategies is None:
                self.active_strategies = []

# =============================================================================
# ALERT MESSAGES
# =============================================================================

if PYDANTIC_AVAILABLE:
    class AlertTriggered(BaseMessage):
        """Alert/warning message from the engine."""
        
        message_type: MessageType = Field(default=MessageType.ALERT_TRIGGERED)
        alert_id: str = Field(..., description="Unique alert identifier")
        alert_type: str = Field(..., description="Type of alert")
        severity: str = Field(..., description="Alert severity level")
        title: str = Field(..., description="Alert title")
        description: str = Field(..., description="Detailed alert description")
        
        # Context
        affected_components: List[str] = Field(default_factory=list, description="Affected system components")
        affected_pairs: List[str] = Field(default_factory=list, description="Affected trading pairs")
        chain_id: Optional[int] = Field(None, description="Related blockchain")
        
        # Action
        action_required: bool = Field(default=False, description="Whether user action is required")
        recommended_actions: List[str] = Field(default_factory=list, description="Recommended user actions")
        auto_resolution_attempted: bool = Field(default=False, description="Whether auto-resolution was attempted")
        
        # Additional data
        metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional alert metadata")
else:
    @dataclass
    class AlertTriggered(BaseMessage):
        """Message sent when alerts are triggered."""
        alert_id: str
        alert_type: str
        severity: str
        title: str
        description: str
        affected_components: List[str] = None
        affected_pairs: List[str] = None
        chain_id: Optional[int] = None
        action_required: bool = False
        recommended_actions: List[str] = None
        auto_resolution_attempted: bool = False
        metadata: Dict[str, Any] = None
        
        def __post_init__(self):
            if self.affected_components is None:
                self.affected_components = []
            if self.affected_pairs is None:
                self.affected_pairs = []
            if self.recommended_actions is None:
                self.recommended_actions = []
            if self.metadata is None:
                self.metadata = {}

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def create_correlation_id() -> str:
    """Generate a unique correlation ID for message tracking."""
    return str(uuid.uuid4())

def serialize_message(message) -> str:
    """
    Serialize message to JSON string.
    
    Args:
        message: Message object to serialize
        
    Returns:
        JSON string representation
    """
    try:
        if PYDANTIC_AVAILABLE and hasattr(message, 'json'):
            return message.json()
        else:
            # Handle dataclass serialization
            if hasattr(message, 'to_dict'):
                data = message.to_dict()
            else:
                data = asdict(message) if hasattr(message, '__dataclass_fields__') else message
            
            # Handle datetime serialization
            def json_serial(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                if isinstance(obj, Decimal):
                    return str(obj)
                raise TypeError(f"Type {type(obj)} not serializable")
            
            return json.dumps(data, default=json_serial)
    except Exception as e:
        logger.error(f"Error serializing message: {e}")
        raise

def deserialize_message(message_json: str, expected_type: Optional[type] = None):
    """
    Deserialize JSON string to message object.
    
    Args:
        message_json: JSON string to deserialize
        expected_type: Optional specific message class to use
        
    Returns:
        Message object or dictionary if class not specified
    """
    try:
        data = json.loads(message_json)
        
        if expected_type:
            if PYDANTIC_AVAILABLE and hasattr(expected_type, 'parse_raw'):
                return expected_type.parse_raw(message_json)
            elif hasattr(expected_type, 'from_dict'):
                return expected_type.from_dict(data)
            else:
                return expected_type(**data)
        
        return data
        
    except Exception as e:
        logger.error(f"Error deserializing message: {e}")
        raise

def create_base_message(
    message_type: MessageType,
    source_service: str,
    engine_id: Optional[str] = None,
    correlation_id: Optional[str] = None
):
    """
    Create a base message with common fields populated.
    
    Args:
        message_type: Type of message
        source_service: Service creating the message
        engine_id: Optional engine identifier
        correlation_id: Optional correlation ID
        
    Returns:
        BaseMessage instance
    """
    return BaseMessage(
        message_type=message_type.value if isinstance(message_type, MessageType) else message_type,
        timestamp=datetime.utcnow().isoformat(),
        correlation_id=correlation_id or create_correlation_id(),
        source_service=source_service,
        engine_id=engine_id
    )

# =============================================================================
# VALIDATION HELPERS
# =============================================================================

def validate_risk_score(score: Union[int, float, Decimal]) -> Union[Decimal, float]:
    """Validate and normalize a risk score to 0-100 range."""
    if PYDANTIC_AVAILABLE:
        score_decimal = Decimal(str(score))
        if score_decimal < 0:
            return Decimal('0')
        elif score_decimal > 100:
            return Decimal('100')
        return score_decimal
    else:
        score_float = float(score)
        if score_float < 0:
            return 0.0
        elif score_float > 100:
            return 100.0
        return score_float

def validate_confidence_score(confidence: Union[int, float, Decimal]) -> Union[Decimal, float]:
    """Validate and normalize a confidence score to 0-100 range."""
    if PYDANTIC_AVAILABLE:
        confidence_decimal = Decimal(str(confidence))
        if confidence_decimal < 0:
            return Decimal('0')
        elif confidence_decimal > 100:
            return Decimal('100')
        return confidence_decimal
    else:
        confidence_float = float(confidence)
        if confidence_float < 0:
            return 0.0
        elif confidence_float > 100:
            return 100.0
        return confidence_float

def validate_ethereum_address(address: str) -> bool:
    """Validate Ethereum address format."""
    return address.startswith('0x') and len(address) == 42

def validate_transaction_hash(tx_hash: str) -> bool:
    """Validate Ethereum transaction hash format."""
    return tx_hash.startswith('0x') and len(tx_hash) == 66

logger.info(f"Shared message schemas loaded successfully (Pydantic: {PYDANTIC_AVAILABLE})")