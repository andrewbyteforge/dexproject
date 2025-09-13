"""
Shared Pydantic schemas for communication between async engine and Django backend.

This module defines the data models used for Redis pub/sub messaging and seamless
communication between the high-speed async engine and the Django trading bot backend.
"""

import logging
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field, validator


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
            UUID: lambda v: str(v)
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


# =============================================================================
# DISCOVERY MESSAGES (Engine → Django)
# =============================================================================

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


# =============================================================================
# RISK ASSESSMENT MESSAGES
# =============================================================================

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


class ComprehensiveRiskAssessment(BaseMessage):
    """Comprehensive risk assessment results from Django/Celery."""
    
    message_type: MessageType = Field(default=MessageType.COMPREHENSIVE_RISK_COMPLETE)
    pair_address: str = Field(..., description="Assessed pair address")
    token_address: str = Field(..., description="Primary token address being assessed")
    chain_id: int = Field(..., description="Blockchain network ID")
    
    # Django model references
    risk_assessment_id: str = Field(..., description="Django RiskAssessment model ID")
    risk_profile_used: str = Field(..., description="Risk profile used for assessment")
    
    # Overall assessment
    overall_risk_level: RiskLevel = Field(..., description="Overall risk assessment")
    overall_score: Decimal = Field(..., description="Overall risk score (0-100)")
    confidence_score: Decimal = Field(..., description="Overall confidence (0-100)")
    is_tradeable: bool = Field(..., description="Whether token passes comprehensive checks")
    
    # Detailed results
    checks_performed: List[RiskCheckResult] = Field(..., description="All check results")
    processing_time_ms: int = Field(..., description="Total processing time")
    celery_task_ids: List[str] = Field(default_factory=list, description="Celery task IDs used")
    
    # Trading recommendation
    trade_recommendation: str = Field(..., description="Trading recommendation")
    recommended_position_size_usd: Optional[Decimal] = Field(None, description="Recommended position size")
    max_slippage_percent: Optional[Decimal] = Field(None, description="Maximum recommended slippage")


# =============================================================================
# TRADING DECISION MESSAGES (Engine → Django)
# =============================================================================

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
    counterfactuals: List[str] = Field(default_factory=list, description="Alternative scenarios considered")
    
    # Technical Analysis
    fast_risk_score: Decimal = Field(..., description="Fast risk assessment score")
    comprehensive_risk_score: Optional[Decimal] = Field(None, description="Comprehensive risk score")
    liquidity_analysis: Dict[str, Any] = Field(default_factory=dict, description="Liquidity analysis results")
    market_structure: Dict[str, Any] = Field(default_factory=dict, description="Market structure analysis")
    
    # Integration with Django
    django_risk_assessment_id: Optional[str] = Field(None, description="Related Django RiskAssessment ID")
    strategy_id: Optional[str] = Field(None, description="Django Strategy ID used")


# =============================================================================
# EXECUTION MESSAGES (Engine → Django)
# =============================================================================

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


# =============================================================================
# STATUS & MONITORING MESSAGES (Engine → Django)
# =============================================================================

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


class EngineHeartbeat(BaseMessage):
    """Lightweight heartbeat message for engine health monitoring."""
    
    message_type: MessageType = Field(default=MessageType.ENGINE_HEARTBEAT)
    engine_id: str = Field(..., description="Engine instance ID")
    status: str = Field(..., description="Engine status")
    uptime_seconds: int = Field(..., description="Engine uptime")
    
    # Quick metrics
    active_pairs: int = Field(default=0, description="Currently monitored pairs")
    pending_assessments: int = Field(default=0, description="Pending risk assessments")
    open_positions: int = Field(default=0, description="Open trading positions")
    
    # Health indicators
    memory_usage_mb: Optional[int] = Field(None, description="Memory usage in MB")
    cpu_usage_percent: Optional[float] = Field(None, description="CPU usage percentage")
    last_trade_timestamp: Optional[datetime] = Field(None, description="Last trade execution time")


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


# =============================================================================
# CONFIGURATION MESSAGES (Django → Engine)
# =============================================================================

class ConfigUpdate(BaseMessage):
    """Configuration update from Django to engine."""
    
    message_type: MessageType = Field(default=MessageType.CONFIG_UPDATE)
    config_type: str = Field(..., description="Type of configuration update")
    config_data: Dict[str, Any] = Field(..., description="Configuration data")
    requires_restart: bool = Field(default=False, description="Whether engine restart is required")
    
    # Validation
    config_version: str = Field(..., description="Configuration version")
    checksum: Optional[str] = Field(None, description="Configuration checksum for validation")


class EmergencyStop(BaseMessage):
    """Emergency stop command from Django to engine."""
    
    message_type: MessageType = Field(default=MessageType.EMERGENCY_STOP)
    reason: str = Field(..., description="Reason for emergency stop")
    stop_trading: bool = Field(default=True, description="Stop all trading")
    stop_discovery: bool = Field(default=False, description="Stop pair discovery")
    close_positions: bool = Field(default=False, description="Close all open positions")
    
    # Authorization
    authorized_by: str = Field(..., description="User who authorized the stop")
    authorization_token: Optional[str] = Field(None, description="Authorization token")


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def serialize_message(message: BaseMessage) -> str:
    """Serialize a message to JSON string for Redis."""
    try:
        return message.json()
    except Exception as e:
        logger.error(f"Error serializing message {type(message).__name__}: {e}")
        raise


def deserialize_message(message_json: str, expected_type: Optional[type] = None) -> BaseMessage:
    """Deserialize a JSON string to a message object."""
    try:
        # Parse basic JSON to determine message type
        import json
        data = json.loads(message_json)
        message_type = data.get('message_type')
        
        # Map message types to classes
        type_mapping = {
            MessageType.NEW_PAIR_DISCOVERED: NewPairDiscovered,
            MessageType.FAST_RISK_COMPLETE: FastRiskAssessment,
            MessageType.COMPREHENSIVE_RISK_COMPLETE: ComprehensiveRiskAssessment,
            MessageType.TRADING_DECISION: TradingDecision,
            MessageType.EXECUTION_COMPLETE: ExecutionResult,
            MessageType.ENGINE_STATUS: EngineStatus,
            MessageType.ENGINE_HEARTBEAT: EngineHeartbeat,
            MessageType.ALERT_TRIGGERED: AlertTriggered,
            MessageType.CONFIG_UPDATE: ConfigUpdate,
            MessageType.EMERGENCY_STOP: EmergencyStop,
        }
        
        # Get the appropriate class
        message_class = type_mapping.get(message_type)
        if not message_class:
            raise ValueError(f"Unknown message type: {message_type}")
        
        # Validate expected type if provided
        if expected_type and message_class != expected_type:
            raise ValueError(f"Expected {expected_type.__name__}, got {message_class.__name__}")
        
        return message_class.parse_raw(message_json)
        
    except Exception as e:
        logger.error(f"Error deserializing message: {e}")
        raise


# =============================================================================
# VALIDATION HELPERS
# =============================================================================

def validate_risk_score(score: Union[int, float, Decimal]) -> Decimal:
    """Validate and normalize a risk score to 0-100 range."""
    score_decimal = Decimal(str(score))
    if score_decimal < 0:
        return Decimal('0')
    elif score_decimal > 100:
        return Decimal('100')
    return score_decimal


def validate_confidence_score(confidence: Union[int, float, Decimal]) -> Decimal:
    """Validate and normalize a confidence score to 0-100 range."""
    confidence_decimal = Decimal(str(confidence))
    if confidence_decimal < 0:
        return Decimal('0')
    elif confidence_decimal > 100:
        return Decimal('100')
    return confidence_decimal


def create_correlation_id() -> str:
    """Create a correlation ID for message tracking."""
    import uuid
    return str(uuid.uuid4())


def validate_ethereum_address(address: str) -> bool:
    """Validate Ethereum address format."""
    return address.startswith('0x') and len(address) == 42


def validate_transaction_hash(tx_hash: str) -> bool:
    """Validate Ethereum transaction hash format."""
    return tx_hash.startswith('0x') and len(tx_hash) == 66