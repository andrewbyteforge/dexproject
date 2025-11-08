"""
Portfolio Tracking Service for Phase 5.1C Trading Integration

This service manages the integration between DEX trades and the Django trading models,
providing real-time position tracking, P&L calculation, and portfolio management.

PHASE 5.1C: Critical component for trading execution integration

File: dexproject/trading/services/portfolio_service.py
"""

import logging
import uuid
from typing import Dict, Any, Optional, List, Tuple
from decimal import Decimal
from datetime import datetime, timezone
from dataclasses import dataclass

from django.db import transaction
from django.contrib.auth.models import User
from django.utils import timezone as django_timezone

from ..models import Trade, Position, TradingPair, Strategy, Token, DEX
from .dex_router_service import SwapResult, SwapType
from engine.config import ChainConfig

logger = logging.getLogger(__name__)


@dataclass
class PortfolioUpdate:
    """Result of a portfolio update operation."""
    trade_created: bool
    position_updated: bool
    trade_id: Optional[str] = None
    position_id: Optional[str] = None
    realized_pnl: Optional[Decimal] = None
    unrealized_pnl: Optional[Decimal] = None
    error_message: Optional[str] = None


class PortfolioTrackingService:
    """
    Service for tracking trading positions and P&L calculation.
    
    Features:
    - Real-time trade recording from DEX swaps
    - Position management and tracking
    - P&L calculation (realized and unrealized)
    - Portfolio analytics and reporting
    - Integration with Strategy and Risk models
    """
    
    def __init__(self, chain_config: ChainConfig):
        """
        Initialize portfolio tracking service.
        
        Args:
            chain_config: Chain configuration for this service instance
        """
        self.chain_config = chain_config
        self.logger = logging.getLogger(f'trading.portfolio.{chain_config.name.lower()}')
        
        # Cache for frequently accessed objects
        self._token_cache: Dict[str, Token] = {}
        self._pair_cache: Dict[str, TradingPair] = {}
        self._dex_cache: Dict[str, DEX] = {}
    
    async def record_swap_trade(
        self,
        swap_result: SwapResult,
        swap_type: SwapType,
        token_in_address: str,
        token_out_address: str,
        pair_address: str,
        user: Optional[User] = None,
        strategy: Optional[Strategy] = None,
        trade_id: Optional[str] = None
    ) -> PortfolioUpdate:
        """
        Record a completed DEX swap as a trade in the portfolio.
        
        Args:
            swap_result: Result from DEX router service
            swap_type: Type of swap executed
            token_in_address: Input token address
            token_out_address: Output token address
            pair_address: Trading pair address
            user: User who executed the trade (None for bot trades)
            strategy: Strategy used for the trade
            trade_id: Optional trade ID (will generate if not provided)
            
        Returns:
            PortfolioUpdate with operation results
        """
        try:
            with transaction.atomic():
                # Generate trade ID if not provided
                if trade_id is None:
                    trade_id = str(uuid.uuid4())
                
                # Get or create trading pair
                trading_pair = await self._get_or_create_trading_pair(
                    token_in_address, token_out_address, pair_address
                )
                
                # Determine trade type and amounts
                trade_type, amount_in, amount_out, price_usd = self._calculate_trade_details(
                    swap_result, swap_type, token_in_address, token_out_address
                )
                
                # Create trade record
                trade = Trade.objects.create(
                    trade_id=trade_id,
                    user=user,
                    strategy=strategy,
                    pair=trading_pair,
                    trade_type=trade_type,
                    amount_in=amount_in,
                    amount_out=amount_out,
                    price_usd=price_usd,
                    slippage_percent=swap_result.actual_slippage_percent,
                    gas_used=swap_result.gas_used or 0,
                    gas_price_gwei=swap_result.gas_price_gwei,
                    transaction_hash=swap_result.transaction_hash,
                    block_number=swap_result.block_number,
                    status=Trade.TradeStatus.COMPLETED if swap_result.success else Trade.TradeStatus.FAILED,
                    executed_at=django_timezone.now(),
                    confirmed_at=django_timezone.now(),
                    metadata={
                        'dex_version': swap_result.dex_version.value,
                        'execution_time_ms': swap_result.execution_time_ms,
                        'chain_id': self.chain_config.chain_id,
                        'swap_type': swap_type.value
                    }
                )
                
                # Update or create position
                position_result = await self._update_position(trade, user, strategy)
                
                self.logger.info(
                    f"✅ Trade recorded: {trade_type} {trading_pair} "
                    f"(ID: {trade_id[:8]}..., Amount: {amount_out})"
                )
                
                return PortfolioUpdate(
                    trade_created=True,
                    position_updated=position_result is not None,
                    trade_id=trade_id,
                    position_id=str(position_result.position_id) if position_result else None,
                    realized_pnl=position_result.realized_pnl_usd if position_result else None,
                    unrealized_pnl=position_result.unrealized_pnl_usd if position_result else None
                )
                
        except Exception as e:
            self.logger.error(f"Failed to record swap trade: {e}")
            return PortfolioUpdate(
                trade_created=False,
                position_updated=False,
                error_message=str(e)
            )
    
    async def _get_or_create_trading_pair(
        self,
        token_in_address: str,
        token_out_address: str,
        pair_address: str
    ) -> TradingPair:
        """Get or create trading pair for the trade."""
        cache_key = f"{token_in_address}:{token_out_address}:{pair_address}"
        
        if cache_key in self._pair_cache:
            return self._pair_cache[cache_key]
        
        try:
            # Get or create tokens
            token_in = await self._get_or_create_token(token_in_address)
            token_out = await self._get_or_create_token(token_out_address)
            
            # Get or create DEX
            dex = await self._get_or_create_dex()
            
            # Get or create trading pair
            trading_pair, created = TradingPair.objects.get_or_create(
                dex=dex,
                token0=token_in,
                token1=token_out,
                defaults={
                    'pair_address': pair_address,
                    'is_active': True
                }
            )
            
            if created:
                self.logger.info(f"Created new trading pair: {trading_pair}")
            
            # Cache the result
            self._pair_cache[cache_key] = trading_pair
            return trading_pair
            
        except Exception as e:
            self.logger.error(f"Failed to get or create trading pair: {e}")
            raise
    
    async def _get_or_create_token(self, token_address: str) -> Token:
        """Get or create token record."""
        if token_address in self._token_cache:
            return self._token_cache[token_address]
        
        try:
            # Check if it's WETH (use ETH symbol)
            if token_address.lower() == self.chain_config.weth_address.lower():
                symbol = "WETH"
                name = "Wrapped Ether"
                decimals = 18
                is_verified = True
            elif token_address.lower() == self.chain_config.usdc_address.lower():
                symbol = "USDC"
                name = "USD Coin"
                decimals = 6
                is_verified = True
            else:
                # For unknown tokens, use placeholder values
                symbol = f"TOKEN_{token_address[:6].upper()}"
                name = f"Unknown Token {token_address[:10]}"
                decimals = 18
                is_verified = False
            
            token, created = Token.objects.get_or_create(
                address=token_address,
                chain=self.chain_config.chain_id,
                defaults={
                    'symbol': symbol,
                    'name': name,
                    'decimals': decimals,
                    'is_verified': is_verified
                }
            )
            
            if created:
                self.logger.info(f"Created new token: {token.symbol} ({token_address[:10]}...)")
            
            # Cache the result
            self._token_cache[token_address] = token
            return token
            
        except Exception as e:
            self.logger.error(f"Failed to get or create token {token_address}: {e}")
            raise
    
    async def _get_or_create_dex(self) -> DEX:
        """Get or create DEX record for this chain."""
        cache_key = f"uniswap_v3_{self.chain_config.chain_id}"
        
        if cache_key in self._dex_cache:
            return self._dex_cache[cache_key]
        
        try:
            dex, created = DEX.objects.get_or_create(
                name="Uniswap V3",
                chain=self.chain_config.chain_id,
                defaults={
                    'version': "3.0",
                    'factory_address': self.chain_config.uniswap_v3_factory,
                    'router_address': self.chain_config.uniswap_v3_router,
                    'is_active': True,
                    'fee_tier': Decimal('0.3'),  # 0.3%
                    'config': {
                        'supports_v2': True,
                        'supports_v3': True,
                        'weth_address': self.chain_config.weth_address,
                        'usdc_address': self.chain_config.usdc_address
                    }
                }
            )
            
            if created:
                self.logger.info(f"Created new DEX record: {dex}")
            
            # Cache the result
            self._dex_cache[cache_key] = dex
            return dex
            
        except Exception as e:
            self.logger.error(f"Failed to get or create DEX: {e}")
            raise
    
    def _calculate_trade_details(
        self,
        swap_result: SwapResult,
        swap_type: SwapType,
        token_in_address: str,
        token_out_address: str
    ) -> Tuple[str, Decimal, Decimal, Optional[Decimal]]:
        """
        Calculate trade details from swap result.
        
        Returns:
            Tuple of (trade_type, amount_in, amount_out, price_usd)
        """
        try:
            # Determine trade type based on swap direction
            if swap_type == SwapType.EXACT_ETH_FOR_TOKENS:
                trade_type = Trade.TradeType.BUY
                amount_in = Decimal(str(swap_result.amount_in)) / Decimal('1e18')  # ETH amount
                amount_out = Decimal(str(swap_result.amount_out)) / Decimal('1e18')  # Token amount (assuming 18 decimals)
                # Price in USD per token (if we have ETH price, calculate token price)
                price_usd = None  # Will be enhanced with price feeds later
                
            elif swap_type == SwapType.EXACT_TOKENS_FOR_ETH:
                trade_type = Trade.TradeType.SELL
                amount_in = Decimal(str(swap_result.amount_in)) / Decimal('1e18')  # Token amount
                amount_out = Decimal(str(swap_result.amount_out)) / Decimal('1e18')  # ETH amount
                price_usd = None
                
            else:  # Token to Token
                trade_type = Trade.TradeType.BUY  # Default to BUY for token swaps
                amount_in = Decimal(str(swap_result.amount_in)) / Decimal('1e18')
                amount_out = Decimal(str(swap_result.amount_out)) / Decimal('1e18')
                price_usd = None
            
            return trade_type, amount_in, amount_out, price_usd
            
        except Exception as e:
            self.logger.error(f"Failed to calculate trade details: {e}")
            # Return safe defaults
            return Trade.TradeType.BUY, Decimal('0'), Decimal('0'), None
    
    async def _update_position(
        self,
        trade: Trade,
        user: Optional[User],
        strategy: Optional[Strategy]
    ) -> Optional[Position]:
        """Update or create position based on the trade."""
        try:
            if trade.trade_type == Trade.TradeType.BUY:
                return await self._handle_buy_position(trade, user, strategy)
            else:
                return await self._handle_sell_position(trade, user, strategy)
                
        except Exception as e:
            self.logger.error(f"Failed to update position: {e}")
            return None
    
    async def _handle_buy_position(
        self,
        trade: Trade,
        user: Optional[User],
        strategy: Optional[Strategy]
    ) -> Position:
        """Handle position update for buy trades."""
        try:
            # Find existing open position or create new one
            position = Position.objects.filter(
                user=user,
                pair=trade.pair,
                status=Position.PositionStatus.OPEN
            ).first()
            
            if position:
                # Update existing position
                position.total_amount_in += trade.amount_in
                position.current_amount += trade.amount_out
                position.entry_trades.add(trade)
                
                # Recalculate average entry price
                total_cost = sum(
                    entry_trade.amount_in for entry_trade in position.entry_trades.all()
                )
                total_tokens = sum(
                    entry_trade.amount_out for entry_trade in position.entry_trades.all()
                )
                
                if total_tokens > 0:
                    position.average_entry_price = total_cost / total_tokens
                
                position.save()
                self.logger.info(f"Updated existing position: {position.position_id}")
                
            else:
                # Create new position
                position = Position.objects.create(
                    user=user,
                    strategy=strategy,
                    pair=trade.pair,
                    status=Position.PositionStatus.OPEN,
                    total_amount_in=trade.amount_in,
                    average_entry_price=trade.price_usd or (trade.amount_in / trade.amount_out if trade.amount_out > 0 else None),
                    current_amount=trade.amount_out
                )
                position.entry_trades.add(trade)
                self.logger.info(f"Created new position: {position.position_id}")
            
            return position
            
        except Exception as e:
            self.logger.error(f"Failed to handle buy position: {e}")
            raise
    
    async def _handle_sell_position(
        self,
        trade: Trade,
        user: Optional[User],
        strategy: Optional[Strategy]
    ) -> Optional[Position]:
        """Handle position update for sell trades."""
        try:
            # Find existing open position
            position = Position.objects.filter(
                user=user,
                pair=trade.pair,
                status=Position.PositionStatus.OPEN
            ).first()
            
            if not position:
                self.logger.warning(f"No open position found for sell trade: {trade.trade_id}")
                return None
            
            # Calculate realized P&L for the portion being sold
            sell_portion = trade.amount_in / position.current_amount if position.current_amount > 0 else Decimal('0')
            cost_basis = position.total_amount_in * sell_portion
            realized_pnl = trade.amount_out - cost_basis
            
            # Update position
            position.current_amount -= trade.amount_in
            position.total_amount_in -= cost_basis
            position.realized_pnl_usd += realized_pnl
            position.exit_trades.add(trade)
            
            # Check if position should be closed
            if position.current_amount <= Decimal('0.001'):  # Small threshold for rounding
                position.status = Position.PositionStatus.CLOSED
                position.closed_at = django_timezone.now()
                position.current_amount = Decimal('0')
                
            position.save()
            
            self.logger.info(
                f"Updated position for sell: {position.position_id} "
                f"(Realized P&L: {realized_pnl:.4f})"
            )
            
            return position
            
        except Exception as e:
            self.logger.error(f"Failed to handle sell position: {e}")
            raise
    
    def get_portfolio_summary(self, user: User) -> Dict[str, Any]:
        """
        Get portfolio summary for a user.
        
        Args:
            user: User to get portfolio for
            
        Returns:
            Portfolio summary dictionary
        """
        try:
            # Get all positions for user
            positions = Position.objects.filter(user=user)
            open_positions = positions.filter(status=Position.PositionStatus.OPEN)
            closed_positions = positions.filter(status=Position.PositionStatus.CLOSED)
            
            # Calculate totals
            total_invested = sum(pos.total_amount_in for pos in positions)
            total_realized_pnl = sum(pos.realized_pnl_usd for pos in positions)
            total_unrealized_pnl = sum(pos.unrealized_pnl_usd for pos in open_positions)
            
            # Get recent trades
            recent_trades = Trade.objects.filter(user=user).order_by('-created_at')[:10]
            
            return {
                'total_positions': positions.count(),
                'open_positions': open_positions.count(),
                'closed_positions': closed_positions.count(),
                'total_invested': float(total_invested),
                'total_realized_pnl': float(total_realized_pnl),
                'total_unrealized_pnl': float(total_unrealized_pnl),
                'total_pnl': float(total_realized_pnl + total_unrealized_pnl),
                'recent_trades': [
                    {
                        'trade_id': str(trade.trade_id),
                        'type': trade.trade_type,
                        'pair': str(trade.pair),
                        'amount': float(trade.amount_out),
                        'price': float(trade.price_usd) if trade.price_usd else None,
                        'timestamp': trade.created_at.isoformat()
                    }
                    for trade in recent_trades
                ]
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get portfolio summary: {e}")
            return {
                'error': str(e),
                'total_positions': 0,
                'open_positions': 0,
                'closed_positions': 0,
                'total_invested': 0.0,
                'total_realized_pnl': 0.0,
                'total_unrealized_pnl': 0.0,
                'total_pnl': 0.0,
                'recent_trades': []
            }


# Factory function for easy integration
def create_portfolio_service(chain_config: ChainConfig) -> PortfolioTrackingService:
    """
    Factory function to create portfolio tracking service.
    
    Args:
        chain_config: Chain configuration for the service
        
    Returns:
        Ready-to-use PortfolioTrackingService instance
    """
    try:
        service = PortfolioTrackingService(chain_config)
        logger.info(f"✅ Portfolio Tracking Service created for {chain_config.name}")
        return service
        
    except Exception as e:
        logger.error(f"Failed to create portfolio service: {e}")
        raise