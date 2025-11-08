"""
Shared SQLAlchemy async models for the FastAPI engine service.

These models provide async database access for the high-speed engine service,
complementing the Django ORM models used by the main application.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean, Column, DateTime, Integer, Numeric, String, Text, JSON,
    Index, ForeignKey, UniqueConstraint, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.sql import func


logger = logging.getLogger(__name__)


# Base class for all async models
Base = declarative_base()


# =============================================================================
# ASYNC DATABASE CONFIGURATION
# =============================================================================

class AsyncDatabaseManager:
    """Manages async database connections and sessions."""
    
    def __init__(self, database_url: str):
        """Initialize async database manager."""
        self.database_url = database_url
        self.engine = None
        self.session_factory = None
        self.logger = logging.getLogger(__name__)
    
    async def initialize(self) -> None:
        """Initialize async database engine and session factory."""
        try:
            self.engine = create_async_engine(
                self.database_url,
                echo=False,  # Set to True for SQL debugging
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                pool_recycle=300,  # 5 minutes
            )
            
            self.session_factory = sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            # Test the connection
            async with self.get_session() as session:
                await session.execute("SELECT 1")
                
            self.logger.info("Async database connection initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize async database: {e}")
            raise
    
    async def close(self) -> None:
        """Close database connections."""
        if self.engine:
            await self.engine.dispose()
            self.logger.info("Async database connections closed")
    
    def get_session(self) -> AsyncSession:
        """Get an async database session."""
        if not self.session_factory:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self.session_factory()


# Global database manager instance
db_manager = AsyncDatabaseManager("")


# =============================================================================
# DISCOVERY MODELS
# =============================================================================

class DiscoveredPair(Base):
    """Async model for tracking discovered trading pairs."""
    
    __tablename__ = 'engine_discovered_pairs'
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Pair identification
    pair_address = Column(String(42), nullable=False, index=True)
    token0_address = Column(String(42), nullable=False, index=True)
    token1_address = Column(String(42), nullable=False, index=True)
    chain_id = Column(Integer, nullable=False, index=True)
    dex_name = Column(String(50), nullable=False, index=True)
    fee_tier = Column(Integer, nullable=False)
    
    # Token information
    token0_symbol = Column(String(20))
    token0_name = Column(String(100))
    token0_decimals = Column(Integer)
    token1_symbol = Column(String(20))
    token1_name = Column(String(100))
    token1_decimals = Column(Integer)
    
    # Market data
    initial_liquidity_usd = Column(Numeric(20, 8))
    initial_volume_24h_usd = Column(Numeric(20, 8))
    initial_price_usd = Column(Numeric(30, 18))
    
    # Discovery metadata
    discovered_at = Column(DateTime(timezone=True), default=func.now(), nullable=False, index=True)
    discovery_source = Column(String(50), nullable=False)
    block_number = Column(Integer)
    transaction_hash = Column(String(66))
    discovery_metadata = Column(JSON, default=dict)
    
    # Processing status
    fast_risk_completed = Column(Boolean, default=False, index=True)
    comprehensive_risk_completed = Column(Boolean, default=False, index=True)
    trading_decision_made = Column(Boolean, default=False, index=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('pair_address', 'chain_id', name='uq_pair_chain'),
        CheckConstraint('fee_tier >= 0', name='check_fee_tier_positive'),
        Index('idx_discovery_processing', 'discovered_at', 'fast_risk_completed'),
        Index('idx_chain_dex', 'chain_id', 'dex_name'),
    )
    
    def __repr__(self) -> str:
        """String representation of discovered pair."""
        return (
            f"<DiscoveredPair("
            f"pair={self.pair_address[:10]}..., "
            f"chain={self.chain_id}, "
            f"tokens={self.token0_symbol}/{self.token1_symbol})>"
        )


# =============================================================================
# RISK ASSESSMENT MODELS
# =============================================================================

class FastRiskAssessment(Base):
    """Async model for fast risk assessment results."""
    
    __tablename__ = 'engine_fast_risk_assessments'
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Related pair
    pair_id = Column(UUID(as_uuid=True), ForeignKey('engine_discovered_pairs.id'), nullable=False, index=True)
    pair_address = Column(String(42), nullable=False, index=True)
    token_address = Column(String(42), nullable=False, index=True)  # Primary token being assessed
    
    # Overall assessment
    overall_risk_level = Column(String(20), nullable=False, index=True)
    overall_score = Column(Numeric(5, 2), nullable=False, index=True)  # 0-100
    confidence_score = Column(Numeric(5, 2), nullable=False, index=True)  # 0-100
    
    # Processing details
    processing_time_ms = Column(Integer, nullable=False)
    checks_performed_count = Column(Integer, nullable=False)
    requires_comprehensive_check = Column(Boolean, default=True, index=True)
    
    # Detailed results
    check_results = Column(JSON, nullable=False)  # List of individual check results
    blocking_issues = Column(JSON, default=list)  # List of critical blocking issues
    
    # Risk factors
    honeypot_risk = Column(Numeric(5, 2))  # Individual risk component scores
    liquidity_risk = Column(Numeric(5, 2))
    ownership_risk = Column(Numeric(5, 2))
    tax_risk = Column(Numeric(5, 2))
    contract_risk = Column(Numeric(5, 2))
    
    # Timestamps
    assessed_at = Column(DateTime(timezone=True), default=func.now(), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    
    # Relationships
    pair = relationship("DiscoveredPair", backref="fast_risk_assessments")
    
    # Constraints
    __table_args__ = (
        CheckConstraint('overall_score >= 0 AND overall_score <= 100', name='check_overall_score_range'),
        CheckConstraint('confidence_score >= 0 AND confidence_score <= 100', name='check_confidence_range'),
        CheckConstraint('processing_time_ms >= 0', name='check_processing_time_positive'),
        Index('idx_risk_score_level', 'overall_score', 'overall_risk_level'),
        Index('idx_assessment_time', 'assessed_at', 'processing_time_ms'),
    )
    
    def __repr__(self) -> str:
        """String representation of fast risk assessment."""
        return (
            f"<FastRiskAssessment("
            f"token={self.token_address[:10]}..., "
            f"score={self.overall_score}, "
            f"level={self.overall_risk_level})>"
        )


class RiskCheckResult(Base):
    """Async model for individual risk check results."""
    
    __tablename__ = 'engine_risk_check_results'
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Related assessment
    assessment_id = Column(UUID(as_uuid=True), ForeignKey('engine_fast_risk_assessments.id'), nullable=False, index=True)
    
    # Check identification
    check_name = Column(String(100), nullable=False, index=True)
    check_type = Column(String(50), nullable=False, index=True)
    check_version = Column(String(20), default='1.0')
    
    # Check results
    passed = Column(Boolean, nullable=False, index=True)
    score = Column(Numeric(5, 2), nullable=False)  # 0-100
    confidence = Column(Numeric(5, 2), nullable=False)  # 0-100
    execution_time_ms = Column(Integer)
    
    # Detailed results
    details = Column(JSON, default=dict)  # Detailed check-specific results
    error_message = Column(Text)
    
    # Timestamps
    executed_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    
    # Relationships
    assessment = relationship("FastRiskAssessment", backref="individual_checks")
    
    # Constraints
    __table_args__ = (
        CheckConstraint('score >= 0 AND score <= 100', name='check_score_range'),
        CheckConstraint('confidence >= 0 AND confidence <= 100', name='check_confidence_range'),
        Index('idx_check_type_passed', 'check_type', 'passed'),
        Index('idx_assessment_check', 'assessment_id', 'check_name'),
    )
    
    def __repr__(self) -> str:
        """String representation of risk check result."""
        return (
            f"<RiskCheckResult("
            f"check={self.check_name}, "
            f"passed={self.passed}, "
            f"score={self.score})>"
        )


# =============================================================================
# TRADING DECISION MODELS
# =============================================================================

class TradingDecision(Base):
    """Async model for AI trading decisions."""
    
    __tablename__ = 'engine_trading_decisions'
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Related entities
    pair_id = Column(UUID(as_uuid=True), ForeignKey('engine_discovered_pairs.id'), nullable=False, index=True)
    fast_risk_id = Column(UUID(as_uuid=True), ForeignKey('engine_fast_risk_assessments.id'), index=True)
    
    # Decision details
    decision_type = Column(String(20), nullable=False, index=True)  # BUY, SELL, SKIP, HOLD
    confidence = Column(Numeric(5, 2), nullable=False, index=True)  # 0-100
    position_size_eth = Column(Numeric(20, 8))
    max_slippage_percent = Column(Numeric(5, 2))
    
    # AI reasoning
    narrative_summary = Column(Text, nullable=False)
    signals_analyzed = Column(JSON, nullable=False)  # List of trading signals
    risk_factors = Column(JSON, default=list)
    opportunity_factors = Column(JSON, default=list)
    counterfactuals = Column(JSON, default=list)
    
    # Technical analysis
    fast_risk_score = Column(Numeric(5, 2), nullable=False)
    comprehensive_risk_score = Column(Numeric(5, 2))
    liquidity_analysis = Column(JSON, default=dict)
    market_structure = Column(JSON, default=dict)
    
    # Execution status
    execution_requested = Column(Boolean, default=False, index=True)
    execution_completed = Column(Boolean, default=False, index=True)
    execution_successful = Column(Boolean, index=True)
    
    # Timestamps
    decided_at = Column(DateTime(timezone=True), default=func.now(), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    
    # Relationships
    pair = relationship("DiscoveredPair", backref="trading_decisions")
    fast_risk = relationship("FastRiskAssessment", backref="trading_decisions")
    
    # Constraints
    __table_args__ = (
        CheckConstraint('confidence >= 0 AND confidence <= 100', name='check_confidence_range'),
        CheckConstraint('position_size_eth > 0', name='check_position_size_positive'),
        CheckConstraint('max_slippage_percent >= 0 AND max_slippage_percent <= 50', name='check_slippage_range'),
        Index('idx_decision_confidence', 'decision_type', 'confidence'),
        Index('idx_execution_status', 'execution_requested', 'execution_completed'),
        Index('idx_decision_time', 'decided_at', 'decision_type'),
    )
    
    def __repr__(self) -> str:
        """String representation of trading decision."""
        return (
            f"<TradingDecision("
            f"decision={self.decision_type}, "
            f"confidence={self.confidence}, "
            f"size={self.position_size_eth} ETH)>"
        )


# =============================================================================
# EXECUTION TRACKING MODELS
# =============================================================================

class ExecutionAttempt(Base):
    """Async model for tracking trade execution attempts."""
    
    __tablename__ = 'engine_execution_attempts'
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Related decision
    decision_id = Column(UUID(as_uuid=True), ForeignKey('engine_trading_decisions.id'), nullable=False, index=True)
    
    # Execution details
    attempt_number = Column(Integer, nullable=False, default=1)
    transaction_hash = Column(String(66), unique=True, index=True)
    gas_used = Column(Integer)
    gas_price_gwei = Column(Numeric(10, 2))
    actual_slippage_percent = Column(Numeric(5, 2))
    tokens_received = Column(String(50))
    eth_spent = Column(Numeric(20, 8))
    
    # Status
    status = Column(String(20), nullable=False, index=True)  # PENDING, SUCCESS, FAILED, REVERTED
    success = Column(Boolean, index=True)
    error_message = Column(Text)
    execution_time_ms = Column(Integer)
    
    # Blockchain details
    block_number = Column(Integer)
    block_timestamp = Column(DateTime(timezone=True))
    transaction_fee_eth = Column(Numeric(20, 8))
    
    # Timestamps
    attempted_at = Column(DateTime(timezone=True), default=func.now(), nullable=False, index=True)
    completed_at = Column(DateTime(timezone=True), index=True)
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    
    # Relationships
    decision = relationship("TradingDecision", backref="execution_attempts")
    
    # Constraints
    __table_args__ = (
        CheckConstraint('attempt_number > 0', name='check_attempt_number_positive'),
        CheckConstraint('actual_slippage_percent >= 0', name='check_slippage_positive'),
        Index('idx_execution_status_time', 'status', 'attempted_at'),
        Index('idx_decision_attempt', 'decision_id', 'attempt_number'),
    )
    
    def __repr__(self) -> str:
        """String representation of execution attempt."""
        return (
            f"<ExecutionAttempt("
            f"attempt={self.attempt_number}, "
            f"status={self.status}, "
            f"tx={self.transaction_hash[:10] if self.transaction_hash else None}...)>"
        )


# =============================================================================
# PERFORMANCE MONITORING MODELS
# =============================================================================

class PerformanceMetric(Base):
    """Async model for tracking system performance metrics."""
    
    __tablename__ = 'engine_performance_metrics'
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Metric identification
    metric_name = Column(String(100), nullable=False, index=True)
    metric_type = Column(String(50), nullable=False, index=True)
    component = Column(String(50), nullable=False, index=True)
    
    # Metric values
    value = Column(Numeric(20, 8), nullable=False)
    unit = Column(String(20), nullable=False)
    
    # Context
    tags = Column(JSON, default=dict)  # Additional context tags
    metadata = Column(JSON, default=dict)  # Additional metadata
    
    # Timestamps
    measured_at = Column(DateTime(timezone=True), default=func.now(), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    
    # Constraints
    __table_args__ = (
        Index('idx_metric_time', 'metric_name', 'measured_at'),
        Index('idx_component_metric', 'component', 'metric_type'),
    )
    
    def __repr__(self) -> str:
        """String representation of performance metric."""
        return (
            f"<PerformanceMetric("
            f"metric={self.metric_name}, "
            f"value={self.value} {self.unit}, "
            f"component={self.component})>"
        )


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

async def init_database(database_url: str) -> AsyncDatabaseManager:
    """Initialize the async database manager."""
    global db_manager
    db_manager = AsyncDatabaseManager(database_url)
    await db_manager.initialize()
    return db_manager


async def create_tables(database_url: str) -> None:
    """Create all tables in the database."""
    engine = create_async_engine(database_url)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    await engine.dispose()
    logger.info("All async database tables created successfully")


async def drop_tables(database_url: str) -> None:
    """Drop all tables from the database."""
    engine = create_async_engine(database_url)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()
    logger.info("All async database tables dropped successfully")


# =============================================================================
# DATABASE OPERATIONS
# =============================================================================

async def save_discovered_pair(
    pair_address: str,
    token0_address: str,
    token1_address: str,
    chain_id: int,
    dex_name: str,
    fee_tier: int,
    **kwargs
) -> DiscoveredPair:
    """Save a newly discovered pair to the database."""
    async with db_manager.get_session() as session:
        pair = DiscoveredPair(
            pair_address=pair_address,
            token0_address=token0_address,
            token1_address=token1_address,
            chain_id=chain_id,
            dex_name=dex_name,
            fee_tier=fee_tier,
            **kwargs
        )
        
        session.add(pair)
        await session.commit()
        await session.refresh(pair)
        
        logger.info(f"Saved discovered pair: {pair_address}")
        return pair


async def save_fast_risk_assessment(
    pair_id: str,
    pair_address: str,
    token_address: str,
    overall_risk_level: str,
    overall_score: Decimal,
    confidence_score: Decimal,
    processing_time_ms: int,
    check_results: List[Dict],
    **kwargs
) -> FastRiskAssessment:
    """Save a fast risk assessment to the database."""
    async with db_manager.get_session() as session:
        assessment = FastRiskAssessment(
            pair_id=pair_id,
            pair_address=pair_address,
            token_address=token_address,
            overall_risk_level=overall_risk_level,
            overall_score=overall_score,
            confidence_score=confidence_score,
            processing_time_ms=processing_time_ms,
            check_results=check_results,
            checks_performed_count=len(check_results),
            **kwargs
        )
        
        session.add(assessment)
        await session.commit()
        await session.refresh(assessment)
        
        logger.info(f"Saved fast risk assessment: {token_address} (score: {overall_score})")
        return assessment


async def save_trading_decision(
    pair_id: str,
    decision_type: str,
    confidence: Decimal,
    narrative_summary: str,
    signals_analyzed: List[Dict],
    fast_risk_score: Decimal,
    **kwargs
) -> TradingDecision:
    """Save a trading decision to the database."""
    async with db_manager.get_session() as session:
        decision = TradingDecision(
            pair_id=pair_id,
            decision_type=decision_type,
            confidence=confidence,
            narrative_summary=narrative_summary,
            signals_analyzed=signals_analyzed,
            fast_risk_score=fast_risk_score,
            **kwargs
        )
        
        session.add(decision)
        await session.commit()
        await session.refresh(decision)
        
        logger.info(f"Saved trading decision: {decision_type} (confidence: {confidence})")
        return decision