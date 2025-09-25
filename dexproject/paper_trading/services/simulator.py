"""
Paper Trading Simulator Service (Simplified)

A simplified simulator that works without Phase 6B dependencies for testing.

File: dexproject/paper_trading/services/simulator.py
"""

import logging
import random
import time
from typing import Dict, Any, Optional, Tuple
from decimal import Decimal
from datetime import datetime, timezone
from dataclasses import dataclass
import uuid

from django.contrib.auth.models import User
from django.db import transaction as db_transaction

from ..models import (
    PaperTradingAccount,
    PaperTrade,
    PaperPosition,
    PaperTradingConfig
)

logger = logging.getLogger(__name__)


@dataclass
class SimplePaperTradeRequest:
    """Simple request to execute a paper trade."""
    
    account: PaperTradingAccount
    trade_type: str  # 'buy', 'sell', 'swap'
    token_in: str
    token_out: str
    amount_in_usd: Decimal
    slippage_tolerance: Decimal = Decimal('0.005')  # 0.5%


@dataclass
class SimplePaperTradeResult:
    """Result of a paper trade execution."""
    
    success: bool
    trade_id: str
    trade: Optional[PaperTrade] = None
    position: Optional[PaperPosition] = None
    execution_time_ms: float = 0.0
    gas_cost_usd: Decimal = Decimal('0')
    slippage_percent: Decimal = Decimal('0')
    error_message: Optional[str] = None
    transaction_hash: Optional[str] = None


class SimplePaperTradingSimulator:
    """
    Simplified paper trading simulator for testing.
    
    Features:
    - Basic slippage simulation
    - Simple gas cost estimation
    - Position tracking
    - P&L calculation
    """
    
    def __init__(self):
        """Initialize the simulator."""
        self.logger = logging.getLogger('paper_trading.simulator')
        
    def execute_trade(self, request: SimplePaperTradeRequest) -> SimplePaperTradeResult:
        """
        Execute a paper trade with basic simulation.
        
        Args:
            request: Paper trade request parameters
            
        Returns:
            SimplePaperTradeResult with execution details
        """
        start_time = time.time()
        trade_id = str(uuid.uuid4())
        
        try:
            self.logger.info(
                f"[PAPER] Executing paper trade: {request.trade_type} "
                f"${request.amount_in_usd} of {request.token_in}"
            )
            
            # Validate trade
            if request.account.current_balance_usd < request.amount_in_usd:
                return SimplePaperTradeResult(
                    success=False,
                    trade_id=trade_id,
                    error_message="Insufficient balance"
                )
            
            # Create paper trade record
            paper_trade = PaperTrade(
                trade_id=trade_id,
                account=request.account,
                trade_type=request.trade_type,
                token_in_address=request.token_in,
                token_in_symbol=self._get_token_symbol(request.token_in),
                token_out_address=request.token_out,
                token_out_symbol=self._get_token_symbol(request.token_out),
                amount_in=self._usd_to_wei(request.amount_in_usd),
                amount_in_usd=request.amount_in_usd,
                expected_amount_out=self._usd_to_wei(request.amount_in_usd),
                status='executing'
            )
            
            # Simulate gas costs (simplified)
            gas_cost = Decimal('5.00')  # Fixed $5 gas cost
            paper_trade.simulated_gas_price_gwei = Decimal('20')
            paper_trade.simulated_gas_used = 150000
            paper_trade.simulated_gas_cost_usd = gas_cost
            
            # Simulate slippage
            slippage = self._simulate_slippage(request.amount_in_usd)
            paper_trade.simulated_slippage_percent = slippage
            
            # Calculate actual amount with slippage
            slippage_factor = Decimal('1') - (slippage / Decimal('100'))
            paper_trade.actual_amount_out = paper_trade.expected_amount_out * slippage_factor
            
            # Random failure (2% chance)
            if random.random() < 0.02:
                paper_trade.status = 'failed'
                paper_trade.error_message = "Transaction failed: insufficient liquidity"
                paper_trade.save()
                
                return SimplePaperTradeResult(
                    success=False,
                    trade_id=trade_id,
                    trade=paper_trade,
                    error_message=paper_trade.error_message
                )
            
            # Update account balances
            with db_transaction.atomic():
                request.account.current_balance_usd -= (request.amount_in_usd + gas_cost)
                request.account.total_fees_paid_usd += gas_cost
                request.account.total_trades += 1
                request.account.successful_trades += 1
                request.account.save()
            
            # Update position (simplified)
            position = self._update_position(
                request.account,
                request.token_out,
                request.amount_in_usd
            )
            
            # Complete trade
            paper_trade.status = 'completed'
            paper_trade.executed_at = datetime.now(timezone.utc)
            paper_trade.execution_time_ms = int((time.time() - start_time) * 1000)
            paper_trade.mock_tx_hash = self._generate_mock_tx_hash()
            paper_trade.mock_block_number = random.randint(18000000, 18100000)
            paper_trade.save()
            
            self.logger.info(
                f"[SUCCESS] Paper trade completed: {trade_id} "
                f"(slippage: {slippage}%, gas: ${gas_cost})"
            )
            
            return SimplePaperTradeResult(
                success=True,
                trade_id=trade_id,
                trade=paper_trade,
                position=position,
                execution_time_ms=paper_trade.execution_time_ms,
                gas_cost_usd=gas_cost,
                slippage_percent=slippage,
                transaction_hash=paper_trade.mock_tx_hash
            )
            
        except Exception as e:
            self.logger.error(f"[ERROR] Paper trade failed: {e}")
            return SimplePaperTradeResult(
                success=False,
                trade_id=trade_id,
                error_message=str(e)
            )
    
    def _simulate_slippage(self, amount_usd: Decimal) -> Decimal:
        """Simulate basic slippage."""
        base_slippage = 0.5
        size_impact = min(float(amount_usd) / 10000 * 0.5, 2.0)
        volatility = random.uniform(-0.2, 0.8)
        total_slippage = max(0, base_slippage + size_impact + volatility)
        return Decimal(str(min(total_slippage, 5.0)))
    
    def _update_position(
        self,
        account: PaperTradingAccount,
        token_address: str,
        amount_usd: Decimal
    ) -> Optional[PaperPosition]:
        """Update or create position (simplified)."""
        with db_transaction.atomic():
            position, created = PaperPosition.objects.get_or_create(
                account=account,
                token_address=token_address,
                is_open=True,
                defaults={
                    'token_symbol': self._get_token_symbol(token_address),
                    'quantity': Decimal('0'),
                    'average_entry_price_usd': Decimal('1'),
                    'total_invested_usd': Decimal('0')
                }
            )
            
            # Simple position update
            position.quantity += amount_usd  # Simplified: using USD as quantity
            position.total_invested_usd += amount_usd
            position.save()
            
            return position
    
    def _get_token_symbol(self, address: str) -> str:
        """Get token symbol from address."""
        symbols = {
            'WETH': 'WETH',
            'USDC': 'USDC',
            'USDT': 'USDT',
        }
        return symbols.get(address.upper(), address[:6].upper())
    
    def _usd_to_wei(self, usd_amount: Decimal) -> Decimal:
        """Convert USD to wei (simplified)."""
        return usd_amount * Decimal('1e18')
    
    def _generate_mock_tx_hash(self) -> str:
        """Generate mock transaction hash."""
        return f"0x{''.join(random.choices('0123456789abcdef', k=64))}"


# Singleton instance
_simulator = None

def get_simulator() -> SimplePaperTradingSimulator:
    """Get simulator instance."""
    global _simulator
    if _simulator is None:
        _simulator = SimplePaperTradingSimulator()
    return _simulator
