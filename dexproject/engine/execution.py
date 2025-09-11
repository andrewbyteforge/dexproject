"""
Execution Engine

Handles trade execution in paper trading mode with realistic simulation.
Implements portfolio management, circuit breakers, and risk limits.
Designed to be extended to live trading in future phases.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
import time
import random

from .config import config, ChainConfig
from .utils import ProviderManager, safe_decimal, format_currency, calculate_slippage
from .risk import RiskAssessmentResult
from . import TradingMode, EngineStatus

logger = logging.getLogger(__name__)


class TradeType(Enum):
    """Type of trade execution."""
    BUY = "BUY"
    SELL = "SELL"


class TradeStatus(Enum):
    """Status of trade execution."""
    PENDING = "PENDING"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ExitReason(Enum):
    """Reason for trade exit."""
    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LOSS = "STOP_LOSS"
    MANUAL = "MANUAL"
    CIRCUIT_BREAKER = "CIRCUIT_BREAKER"
    TIME_LIMIT = "TIME_LIMIT"


@dataclass
class TradeDecision:
    """Represents a trading decision from the risk assessment."""
    pair_address: str
    chain_id: int
    token_address: str
    token_symbol: str
    action: str  # "BUY", "SELL", "SKIP"
    confidence_score: Decimal
    position_size_usd: Decimal
    max_slippage_percent: Decimal
    risk_assessment: RiskAssessmentResult
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class TradeExecution:
    """Represents an executed or simulated trade."""
    trade_id: str
    decision: TradeDecision
    trade_type: TradeType
    status: TradeStatus
    
    # Execution details
    amount_in: Optional[Decimal] = None
    amount_out: Optional[Decimal] = None
    expected_amount_out: Optional[Decimal] = None
    actual_slippage_percent: Optional[Decimal] = None
    gas_used: Optional[int] = None
    gas_price_gwei: Optional[Decimal] = None
    transaction_hash: Optional[str] = None
    block_number: Optional[int] = None
    
    # Timing
    execution_time_ms: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    executed_at: Optional[datetime] = None
    
    # Paper trading simulation
    simulated_price: Optional[Decimal] = None
    simulated_latency_ms: int = 0
    simulation_notes: str = ""


@dataclass
class Position:
    """Represents an open trading position."""
    position_id: str
    token_address: str
    token_symbol: str
    chain_id: int
    
    # Position details
    entry_price_usd: Decimal
    current_price_usd: Optional[Decimal] = None
    quantity: Decimal = Decimal('0')
    initial_value_usd: Decimal = Decimal('0')
    current_value_usd: Optional[Decimal] = None
    
    # Performance
    unrealized_pnl_usd: Optional[Decimal] = None
    unrealized_pnl_percent: Optional[Decimal] = None
    
    # Risk management
    stop_loss_price: Optional[Decimal] = None
    take_profit_price: Optional[Decimal] = None
    max_loss_percent: Decimal = Decimal('10')
    
    # Timing
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def update_current_price(self, new_price: Decimal) -> None:
        """Update current price and recalculate metrics."""
        self.current_price_usd = new_price
        self.current_value_usd = self.quantity * new_price
        
        if self.initial_value_usd > 0:
            self.unrealized_pnl_usd = self.current_value_usd - self.initial_value_usd
            self.unrealized_pnl_percent = (self.unrealized_pnl_usd / self.initial_value_usd) * 100
        
        self.last_updated = datetime.now(timezone.utc)


class PaperTradingSimulator:
    """
    Simulates trade execution with realistic market conditions.
    
    Models slippage, latency, and market impact to provide
    realistic paper trading experience.
    """
    
    def __init__(self, chain_config: ChainConfig):
        """Initialize paper trading simulator."""
        self.chain_config = chain_config
        self.logger = logging.getLogger(f'engine.paper.{chain_config.name.lower()}')
    
    async def simulate_trade(self, decision: TradeDecision) -> TradeExecution:
        """Simulate a trade execution."""
        start_time = time.time()
        
        trade_execution = TradeExecution(
            trade_id=self._generate_trade_id(),
            decision=decision,
            trade_type=TradeType.BUY if decision.action == "BUY" else TradeType.SELL,
            status=TradeStatus.PENDING
        )
        
        try:
            trade_execution.status = TradeStatus.EXECUTING
            
            # Simulate network latency
            latency_ms = self._simulate_latency()
            await asyncio.sleep(latency_ms / 1000)
            trade_execution.simulated_latency_ms = latency_ms
            
            # Simulate price discovery
            simulated_price = await self._simulate_price_discovery(decision)
            trade_execution.simulated_price = simulated_price
            
            # Calculate trade amounts
            if decision.action == "BUY":
                trade_execution.amount_in = decision.position_size_usd
                trade_execution.expected_amount_out = decision.position_size_usd / simulated_price
                
                # Apply simulated slippage
                slippage = self._simulate_slippage(decision.position_size_usd)
                actual_slippage = min(slippage, float(decision.max_slippage_percent))
                
                trade_execution.amount_out = trade_execution.expected_amount_out * (
                    Decimal('1') - Decimal(str(actual_slippage / 100))
                )
                trade_execution.actual_slippage_percent = Decimal(str(actual_slippage))
            
            # Simulate gas costs
            trade_execution.gas_used = random.randint(150000, 250000)
            trade_execution.gas_price_gwei = Decimal(str(random.uniform(1, 20)))  # Base chain gas
            
            # Generate mock transaction hash
            trade_execution.transaction_hash = f"0x{''.join(random.choices('0123456789abcdef', k=64))}"
            trade_execution.block_number = random.randint(10000000, 10010000)
            
            trade_execution.status = TradeStatus.COMPLETED
            trade_execution.executed_at = datetime.now(timezone.utc)
            trade_execution.simulation_notes = f"Paper trade simulated with {actual_slippage:.2f}% slippage"
            
            self.logger.info(
                f"Paper trade executed: {decision.action} {decision.token_symbol} "
                f"for {format_currency(decision.position_size_usd)} "
                f"(slippage: {actual_slippage:.2f}%)"
            )
            
        except Exception as e:
            trade_execution.status = TradeStatus.FAILED
            trade_execution.simulation_notes = f"Simulation failed: {str(e)}"
            self.logger.error(f"Paper trade simulation failed: {e}")
        
        trade_execution.execution_time_ms = (time.time() - start_time) * 1000
        return trade_execution
    
    def _generate_trade_id(self) -> str:
        """Generate unique trade ID."""
        timestamp = int(time.time() * 1000)
        random_suffix = random.randint(1000, 9999)
        return f"paper_{timestamp}_{random_suffix}"
    
    def _simulate_latency(self) -> int:
        """Simulate network and execution latency."""
        base_latency = config.paper_mode_latency_ms
        # Add random variance ±50%
        variance = random.uniform(-0.5, 0.5)
        return int(base_latency * (1 + variance))
    
    async def _simulate_price_discovery(self, decision: TradeDecision) -> Decimal:
        """Simulate price discovery for the token."""
        # In a real implementation, this would query actual DEX prices
        # For paper trading, we'll simulate reasonable prices
        
        if decision.token_symbol == "WETH":
            return Decimal('2500')  # Mock ETH price
        elif "USD" in decision.token_symbol.upper():
            return Decimal('1')  # Stablecoin
        else:
            # Random price for new tokens (very simplified)
            return Decimal(str(random.uniform(0.0001, 1.0)))
    
    def _simulate_slippage(self, trade_size_usd: Decimal) -> float:
        """Simulate slippage based on trade size and market conditions."""
        base_slippage = float(config.paper_mode_slippage)
        
        # Larger trades have more slippage
        size_impact = min(float(trade_size_usd) / 10000 * 0.5, 2.0)  # Max 2% additional
        
        # Add random market volatility
        volatility = random.uniform(-0.2, 0.5)  # Can be negative (favorable slippage)
        
        total_slippage = max(0, base_slippage + size_impact + volatility)
        return min(total_slippage, 5.0)  # Cap at 5%


class PortfolioManager:
    """
    Manages trading portfolio with risk limits and circuit breakers.
    
    Tracks positions, PnL, and enforces risk management rules.
    """
    
    def __init__(self, chain_config: ChainConfig):
        """Initialize portfolio manager."""
        self.chain_config = chain_config
        self.positions: Dict[str, Position] = {}
        self.trade_history: List[TradeExecution] = []
        self.daily_pnl = Decimal('0')
        self.total_portfolio_value = Decimal('0')
        self.available_capital = config.max_portfolio_size_usd
        self.logger = logging.getLogger(f'engine.portfolio.{chain_config.name.lower()}')
        
        # Risk management state
        self.circuit_breaker_triggered = False
        self.daily_loss_limit_hit = False
        self.last_reset_date = datetime.now(timezone.utc).date()
    
    def can_open_position(self, position_size_usd: Decimal) -> Tuple[bool, str]:
        """Check if a new position can be opened."""
        # Check circuit breaker
        if self.circuit_breaker_triggered:
            return False, "Circuit breaker is active"
        
        # Check daily loss limit
        if self.daily_loss_limit_hit:
            return False, "Daily loss limit reached"
        
        # Check position size limit
        if position_size_usd > config.max_position_size_usd:
            return False, f"Position size exceeds limit of {format_currency(config.max_position_size_usd)}"
        
        # Check available capital
        if position_size_usd > self.available_capital:
            return False, f"Insufficient capital: {format_currency(self.available_capital)} available"
        
        # Check portfolio concentration (max 20% in any single position)
        max_position_size = self.total_portfolio_value * Decimal('0.2')
        if position_size_usd > max_position_size and max_position_size > 0:
            return False, f"Position would exceed 20% portfolio concentration"
        
        return True, "OK"
    
    def open_position(self, trade_execution: TradeExecution) -> Optional[Position]:
        """Open a new position from a trade execution."""
        decision = trade_execution.decision
        
        # Validate we can open the position
        can_open, reason = self.can_open_position(decision.position_size_usd)
        if not can_open:
            self.logger.warning(f"Cannot open position: {reason}")
            return None
        
        # Create position
        position = Position(
            position_id=f"pos_{trade_execution.trade_id}",
            token_address=decision.token_address,
            token_symbol=decision.token_symbol,
            chain_id=decision.chain_id,
            entry_price_usd=trade_execution.simulated_price or Decimal('0'),
            quantity=trade_execution.amount_out or Decimal('0'),
            initial_value_usd=decision.position_size_usd,
            current_value_usd=decision.position_size_usd
        )
        
        # Set stop loss and take profit
        position.stop_loss_price = position.entry_price_usd * Decimal('0.9')  # 10% stop loss
        position.take_profit_price = position.entry_price_usd * Decimal('1.5')  # 50% take profit
        
        self.positions[position.position_id] = position
        self.available_capital -= decision.position_size_usd
        self.trade_history.append(trade_execution)
        
        self.logger.info(
            f"Opened position: {position.token_symbol} "
            f"for {format_currency(decision.position_size_usd)} "
            f"at {format_currency(position.entry_price_usd)}"
        )
        
        return position
    
    def close_position(self, position_id: str, exit_reason: ExitReason, exit_price: Decimal) -> Optional[TradeExecution]:
        """Close an existing position."""
        if position_id not in self.positions:
            return None
        
        position = self.positions[position_id]
        
        # Create sell trade execution
        sell_execution = TradeExecution(
            trade_id=f"sell_{int(time.time())}",
            decision=TradeDecision(
                pair_address=position.token_address,
                chain_id=position.chain_id,
                token_address=position.token_address,
                token_symbol=position.token_symbol,
                action="SELL",
                confidence_score=Decimal('100'),
                position_size_usd=position.current_value_usd or position.initial_value_usd,
                max_slippage_percent=Decimal('2'),
                risk_assessment=None  # Not needed for exit
            ),
            trade_type=TradeType.SELL,
            status=TradeStatus.COMPLETED,
            amount_in=position.quantity,
            amount_out=position.quantity * exit_price,
            simulated_price=exit_price,
            executed_at=datetime.now(timezone.utc)
        )
        
        # Calculate realized PnL
        realized_pnl = (exit_price - position.entry_price_usd) * position.quantity
        
        # Update portfolio metrics
        self.available_capital += sell_execution.amount_out or Decimal('0')
        self.daily_pnl += realized_pnl
        
        # Remove position
        del self.positions[position_id]
        self.trade_history.append(sell_execution)
        
        self.logger.info(
            f"Closed position: {position.token_symbol} "
            f"PnL: {format_currency(realized_pnl)} ({exit_reason.value})"
        )
        
        # Check if daily loss limit hit
        self._check_risk_limits()
        
        return sell_execution
    
    def update_position_prices(self, price_updates: Dict[str, Decimal]) -> None:
        """Update current prices for all positions."""
        for position in self.positions.values():
            if position.token_address in price_updates:
                position.update_current_price(price_updates[position.token_address])
        
        # Update total portfolio value
        self._calculate_portfolio_value()
        
        # Check for automatic exits
        self._check_position_exits()
    
    def _calculate_portfolio_value(self) -> None:
        """Calculate total portfolio value."""
        total_value = self.available_capital
        
        for position in self.positions.values():
            if position.current_value_usd:
                total_value += position.current_value_usd
        
        self.total_portfolio_value = total_value
    
    def _check_position_exits(self) -> None:
        """Check if any positions should be automatically closed."""
        positions_to_close = []
        
        for position in self.positions.values():
            if not position.current_price_usd:
                continue
            
            # Check stop loss
            if position.stop_loss_price and position.current_price_usd <= position.stop_loss_price:
                positions_to_close.append((position.position_id, ExitReason.STOP_LOSS, position.current_price_usd))
            
            # Check take profit
            elif position.take_profit_price and position.current_price_usd >= position.take_profit_price:
                positions_to_close.append((position.position_id, ExitReason.TAKE_PROFIT, position.current_price_usd))
        
        # Close positions that hit exit conditions
        for position_id, reason, price in positions_to_close:
            self.close_position(position_id, reason, price)
    
    def _check_risk_limits(self) -> None:
        """Check if risk limits are breached."""
        # Reset daily counters if new day
        today = datetime.now(timezone.utc).date()
        if today != self.last_reset_date:
            self.daily_pnl = Decimal('0')
            self.daily_loss_limit_hit = False
            self.last_reset_date = today
        
        # Check daily loss limit
        daily_loss_percent = abs(self.daily_pnl) / config.max_portfolio_size_usd * 100
        if self.daily_pnl < 0 and daily_loss_percent >= config.daily_loss_limit_percent:
            self.daily_loss_limit_hit = True
            self.logger.warning(f"Daily loss limit hit: {format_currency(self.daily_pnl)}")
        
        # Check circuit breaker
        circuit_breaker_loss = config.max_portfolio_size_usd * config.circuit_breaker_loss_percent / 100
        if self.daily_pnl < -circuit_breaker_loss:
            self.circuit_breaker_triggered = True
            self.logger.critical(f"CIRCUIT BREAKER TRIGGERED: Loss of {format_currency(self.daily_pnl)}")
            
            # Close all positions immediately
            for position in list(self.positions.values()):
                if position.current_price_usd:
                    self.close_position(position.position_id, ExitReason.CIRCUIT_BREAKER, position.current_price_usd)
    
    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get current portfolio summary."""
        total_unrealized_pnl = sum(
            pos.unrealized_pnl_usd or Decimal('0') 
            for pos in self.positions.values()
        )
        
        return {
            "total_value": float(self.total_portfolio_value),
            "available_capital": float(self.available_capital),
            "open_positions": len(self.positions),
            "daily_pnl": float(self.daily_pnl),
            "unrealized_pnl": float(total_unrealized_pnl),
            "circuit_breaker_active": self.circuit_breaker_triggered,
            "daily_loss_limit_hit": self.daily_loss_limit_hit,
            "positions": [
                {
                    "symbol": pos.token_symbol,
                    "value": float(pos.current_value_usd or pos.initial_value_usd),
                    "pnl": float(pos.unrealized_pnl_usd or 0),
                    "pnl_percent": float(pos.unrealized_pnl_percent or 0)
                }
                for pos in self.positions.values()
            ]
        }


class ExecutionEngine:
    """
    Main execution engine that coordinates trading decisions.
    
    Processes risk assessments, makes trading decisions,
    and manages portfolio with paper trading simulation.
    """
    
    def __init__(self, chain_config: ChainConfig):
        """Initialize execution engine."""
        self.chain_config = chain_config
        self.paper_simulator = PaperTradingSimulator(chain_config)
        self.portfolio_manager = PortfolioManager(chain_config)
        self.status = EngineStatus.STOPPED
        self.logger = logging.getLogger(f'engine.execution.{chain_config.name.lower()}')
        
        # Trading statistics
        self.total_decisions = 0
        self.total_trades = 0
        self.successful_trades = 0
    
    async def process_risk_assessment(self, assessment: RiskAssessmentResult) -> None:
        """Process a risk assessment and make trading decision."""
        self.total_decisions += 1
        
        try:
            # Make trading decision
            decision = await self._make_trading_decision(assessment)
            
            if decision.action == "SKIP":
                self.logger.info(f"Skipping pair {assessment.pair_event.pair_address}: Low confidence or high risk")
                return
            
            # Check if we can execute the trade
            can_trade, reason = self.portfolio_manager.can_open_position(decision.position_size_usd)
            if not can_trade:
                self.logger.warning(f"Cannot execute trade: {reason}")
                return
            
            # Execute trade
            if config.is_paper_mode():
                await self._execute_paper_trade(decision)
            else:
                self.logger.warning("Live trading not implemented yet")
                
        except Exception as e:
            self.logger.error(f"Error processing risk assessment: {e}")
    
    async def _make_trading_decision(self, assessment: RiskAssessmentResult) -> TradeDecision:
        """Make a trading decision based on risk assessment."""
        pair_event = assessment.pair_event
        
        # Skip if not tradeable due to blocking risks
        if not assessment.is_tradeable:
            return TradeDecision(
                pair_address=pair_event.pair_address,
                chain_id=pair_event.chain_id,
                token_address=pair_event.token0_address,  # Will be refined
                token_symbol=pair_event.token0_symbol or "UNKNOWN",
                action="SKIP",
                confidence_score=Decimal('0'),
                position_size_usd=Decimal('0'),
                max_slippage_percent=Decimal('0'),
                risk_assessment=assessment
            )
        
        # Calculate confidence score based on risk level
        confidence_score = self._calculate_confidence_score(assessment)
        
        # Skip if confidence too low
        if confidence_score < 70:  # Require 70% confidence minimum
            return TradeDecision(
                pair_address=pair_event.pair_address,
                chain_id=pair_event.chain_id,
                token_address=pair_event.token0_address,
                token_symbol=pair_event.token0_symbol or "UNKNOWN",
                action="SKIP",
                confidence_score=confidence_score,
                position_size_usd=Decimal('0'),
                max_slippage_percent=Decimal('0'),
                risk_assessment=assessment
            )
        
        # Determine which token to trade (non-WETH token)
        token_address = (pair_event.token0_address 
                        if pair_event.token0_address.lower() != self.chain_config.weth_address.lower()
                        else pair_event.token1_address)
        token_symbol = (pair_event.token0_symbol 
                       if pair_event.token0_address.lower() != self.chain_config.weth_address.lower()
                       else pair_event.token1_symbol)
        
        # Calculate position size based on confidence and risk
        position_size = self._calculate_position_size(confidence_score, assessment)
        
        return TradeDecision(
            pair_address=pair_event.pair_address,
            chain_id=pair_event.chain_id,
            token_address=token_address,
            token_symbol=token_symbol or "UNKNOWN",
            action="BUY",
            confidence_score=confidence_score,
            position_size_usd=position_size,
            max_slippage_percent=config.default_slippage_percent,
            risk_assessment=assessment
        )
    
    def _calculate_confidence_score(self, assessment: RiskAssessmentResult) -> Decimal:
        """Calculate confidence score based on risk assessment."""
        # Start with base confidence
        confidence = Decimal('100')
        
        # Subtract based on overall risk score
        confidence -= assessment.overall_risk_score
        
        # Bonus for WETH pairs (more liquid)
        if assessment.pair_event.is_weth_pair:
            confidence += Decimal('10')
        
        # Penalty for failed checks
        for result in assessment.check_results.values():
            if result.status != result.status.PASSED:
                confidence -= Decimal('15')
        
        return max(Decimal('0'), min(Decimal('100'), confidence))
    
    def _calculate_position_size(self, confidence_score: Decimal, assessment: RiskAssessmentResult) -> Decimal:
        """Calculate position size based on confidence and risk."""
        # Base position size as percentage of max position
        base_size = config.max_position_size_usd * Decimal('0.5')  # Start with 50% of max
        
        # Scale by confidence (70-100% confidence maps to 0.5-1.0 multiplier)
        confidence_multiplier = (confidence_score - 70) / 30 * Decimal('0.5') + Decimal('0.5')
        
        # Scale by risk level
        risk_multipliers = {
            "LOW": Decimal('1.0'),
            "MEDIUM": Decimal('0.7'),
            "HIGH": Decimal('0.3'),
            "CRITICAL": Decimal('0.1')
        }
        risk_multiplier = risk_multipliers.get(assessment.risk_level, Decimal('0.5'))
        
        position_size = base_size * confidence_multiplier * risk_multiplier
        
        # Ensure within limits
        return min(position_size, config.max_position_size_usd)
    
    async def _execute_paper_trade(self, decision: TradeDecision) -> None:
        """Execute a paper trade."""
        try:
            # Simulate trade execution
            trade_execution = await self.paper_simulator.simulate_trade(decision)
            
            self.total_trades += 1
            
            if trade_execution.status == TradeStatus.COMPLETED:
                # Open position in portfolio
                position = self.portfolio_manager.open_position(trade_execution)
                
                if position:
                    self.successful_trades += 1
                    self.logger.info(
                        f"Paper trade successful: {decision.token_symbol} "
                        f"Position: {format_currency(decision.position_size_usd)}"
                    )
                else:
                    self.logger.warning("Failed to open position after successful trade execution")
            else:
                self.logger.warning(f"Paper trade failed: {trade_execution.simulation_notes}")
                
        except Exception as e:
            self.logger.error(f"Error executing paper trade: {e}")
    
    async def start(self) -> None:
        """Start the execution engine."""
        self.logger.info(f"Starting execution engine for {self.chain_config.name} in {config.trading_mode} mode")
        self.status = EngineStatus.RUNNING
    
    async def stop(self) -> None:
        """Stop the execution engine."""
        self.logger.info("Stopping execution engine")
        self.status = EngineStatus.STOPPING
        
        # Close all open positions
        for position in list(self.portfolio_manager.positions.values()):
            if position.current_price_usd:
                self.portfolio_manager.close_position(
                    position.position_id, 
                    ExitReason.MANUAL, 
                    position.current_price_usd
                )
        
        self.status = EngineStatus.STOPPED
    
    async def get_status(self) -> Dict[str, Any]:
        """Get execution engine status."""
        portfolio_summary = self.portfolio_manager.get_portfolio_summary()
        
        success_rate = (self.successful_trades / self.total_trades * 100) if self.total_trades > 0 else 0
        
        return {
            "engine": "execution",
            "chain": self.chain_config.name,
            "status": self.status,
            "trading_mode": config.trading_mode,
            "statistics": {
                "total_decisions": self.total_decisions,
                "total_trades": self.total_trades,
                "successful_trades": self.successful_trades,
                "success_rate_percent": round(success_rate, 2)
            },
            "portfolio": portfolio_summary
        }


class MultiChainExecutionManager:
    """
    Manages execution engines across multiple chains.
    
    Coordinates trade execution and portfolio management
    across all configured blockchains.
    """
    
    def __init__(self):
        """Initialize multi-chain execution manager."""
        self.execution_engines: Dict[int, ExecutionEngine] = {}
        self.logger = logging.getLogger('engine.execution.manager')
        
        # Initialize engines for each configured chain
        for chain_id in config.target_chains:
            chain_config = config.get_chain_config(chain_id)
            if chain_config:
                self.execution_engines[chain_id] = ExecutionEngine(chain_config)
    
    async def process_risk_assessment(self, assessment: RiskAssessmentResult) -> None:
        """Process risk assessment using appropriate chain's execution engine."""
        engine = self.execution_engines.get(assessment.pair_event.chain_id)
        if not engine:
            self.logger.error(f"No execution engine for chain {assessment.pair_event.chain_id}")
            return
        
        await engine.process_risk_assessment(assessment)
    
    async def start(self) -> None:
        """Start all execution engines."""
        self.logger.info(f"Starting execution for {len(self.execution_engines)} chains")
        
        for engine in self.execution_engines.values():
            await engine.start()
    
    async def stop(self) -> None:
        """Stop all execution engines."""
        self.logger.info("Stopping all execution engines")
        
        for engine in self.execution_engines.values():
            await engine.stop()
    
    async def get_status(self) -> Dict[str, Any]:
        """Get status of all execution engines."""
        engine_statuses = {}
        
        for chain_id, engine in self.execution_engines.items():
            engine_statuses[chain_id] = await engine.get_status()
        
        # Calculate aggregate portfolio metrics
        total_portfolio_value = sum(
            status["portfolio"]["total_value"] 
            for status in engine_statuses.values()
        )
        
        total_trades = sum(
            status["statistics"]["total_trades"] 
            for status in engine_statuses.values()
        )
        
        return {
            "manager": "multi_chain_execution",
            "total_engines": len(self.execution_engines),
            "aggregate_metrics": {
                "total_portfolio_value": total_portfolio_value,
                "total_trades": total_trades,
                "trading_mode": config.trading_mode
            },
            "engines": engine_statuses
        }