"""
Paper Trading Views - Helper Functions

Template formatting and utility functions used across multiple views.
Provides safe data formatting for template display and portfolio calculations.

File: dexproject/paper_trading/views_helpers.py
"""

import logging
from decimal import Decimal
from typing import Dict, Any, Optional
from django.db import connection

from .models import PaperTradingAccount, PaperPosition
from .utils import to_decimal

logger = logging.getLogger(__name__)


# =============================================================================
# TEMPLATE FORMATTING HELPERS
# =============================================================================

def format_trade_for_template(trade) -> Dict[str, Any]:
    """
    Format a trade object for safe template display.
    
    Converts wei values to human-readable format and ensures
    all decimal values are safe for template rendering.
    
    Args:
        trade: PaperTrade object
        
    Returns:
        Dictionary with formatted trade data safe for templates
    """
    try:
        return {
            'trade_id': str(trade.trade_id),
            'created_at': trade.created_at,
            'trade_type': trade.trade_type,
            'token_in_symbol': trade.token_in_symbol or 'Unknown',
            'token_out_symbol': trade.token_out_symbol or 'Unknown',
            'token_in_address': trade.token_in_address or '',
            'token_out_address': trade.token_out_address or '',
            'amount_in': to_decimal(trade.amount_in, Decimal('0')),
            'amount_out': to_decimal(trade.amount_out, Decimal('0')),
            'amount_in_usd': to_decimal(trade.amount_in_usd, Decimal('0')),
            'gas_cost_usd': to_decimal(trade.gas_cost_usd, Decimal('0')),
            'slippage_percent': to_decimal(trade.slippage_percent, Decimal('0')),
            'status': trade.status,
            'execution_time_ms': trade.execution_time_ms or 0,
            '_original': trade
        }
    except Exception as e:
        logger.error(f"Error formatting trade: {e}")
        # Return minimal safe data on error
        return {
            'trade_id': str(getattr(trade, 'trade_id', 'Unknown')),
            'created_at': getattr(trade, 'created_at', None),
            'trade_type': getattr(trade, 'trade_type', 'Unknown'),
            'token_in_symbol': 'Unknown',
            'token_out_symbol': 'Unknown',
            'token_in_address': '',
            'token_out_address': '',
            'amount_in': Decimal('0'),
            'amount_out': Decimal('0'),
            'amount_in_usd': Decimal('0'),
            'gas_cost_usd': Decimal('0'),
            'slippage_percent': Decimal('0'),
            'status': 'error',
            'execution_time_ms': 0,
            '_original': trade
        }


def format_position_for_template(position: PaperPosition) -> Dict[str, Any]:
    """
    Format a position object for safe template display.
    
    Converts position data to template-safe format with proper decimal handling.
    
    Args:
        position: PaperPosition object
        
    Returns:
        Dictionary with formatted position data
    """
    try:
        return {
            'position_id': str(position.position_id),
            'token_symbol': position.token_symbol or 'Unknown',
            'token_address': position.token_address or '',
            'quantity': to_decimal(position.quantity, Decimal('0')),
            'average_entry_price_usd': to_decimal(position.average_entry_price_usd, Decimal('0')),
            'current_price_usd': to_decimal(position.current_price_usd, Decimal('0')),
            'total_invested_usd': to_decimal(position.total_invested_usd, Decimal('0')),
            'current_value_usd': to_decimal(position.current_value_usd, Decimal('0')),
            'unrealized_pnl_usd': to_decimal(position.unrealized_pnl_usd, Decimal('0')),
            'realized_pnl_usd': to_decimal(position.realized_pnl_usd, Decimal('0')),
            'is_open': position.is_open,
            'opened_at': position.opened_at,
            'closed_at': position.closed_at,
            '_original': position
        }
    except Exception as e:
        logger.error(f"Error formatting position: {e}")
        return {
            'position_id': str(getattr(position, 'position_id', 'Unknown')),
            'token_symbol': 'Unknown',
            'token_address': '',
            'quantity': Decimal('0'),
            'average_entry_price_usd': Decimal('0'),
            'current_price_usd': Decimal('0'),
            'total_invested_usd': Decimal('0'),
            'current_value_usd': Decimal('0'),
            'unrealized_pnl_usd': Decimal('0'),
            'realized_pnl_usd': Decimal('0'),
            'is_open': False,
            'opened_at': None,
            'closed_at': None,
            '_original': position
        }


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def calculate_portfolio_metrics(account: PaperTradingAccount) -> Dict[str, Any]:
    """
    Calculate detailed portfolio metrics.
    
    FIXED: Now correctly calculates winning/losing trades from PaperPosition.realized_pnl_usd
    instead of incorrectly using PaperTrade.status='completed'.
    
    Helper function to calculate various performance metrics for an account.
    Uses raw SQL queries for better performance with complex calculations.
    
    Args:
        account: PaperTradingAccount instance
        
    Returns:
        Dictionary containing portfolio metrics
    """
    try:
        with connection.cursor() as cursor:
            # Get total trade executions
            cursor.execute("""
                SELECT COUNT(*) as total_trades
                FROM paper_trading_papertrade
                WHERE account_id = %s
            """, [str(account.account_id)])
            
            total_trades = cursor.fetchone()[0] or 0
            
            # Get winning/losing trades from closed positions (FIXED)
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_closed,
                    SUM(CASE WHEN realized_pnl_usd > 0 THEN 1 ELSE 0 END) as winning,
                    SUM(CASE WHEN realized_pnl_usd < 0 THEN 1 ELSE 0 END) as losing
                FROM paper_positions
                WHERE account_id = %s AND is_open = FALSE
            """, [str(account.account_id)])
            
            position_stats = cursor.fetchone()
            if position_stats is not None:
                total_closed_positions = position_stats[0] or 0
                winning_trades = position_stats[1] or 0
                losing_trades = position_stats[2] or 0
            else:
                total_closed_positions = 0
                winning_trades = 0
                losing_trades = 0
            
            # Calculate win rate
            win_rate = (winning_trades / total_closed_positions * 100) if total_closed_positions > 0 else 0
            
            # Get total volume traded
            cursor.execute("""
                SELECT COALESCE(SUM(amount_in_usd), 0) as total_volume
                FROM paper_trading_papertrade
                WHERE account_id = %s AND status = 'completed'
            """, [str(account.account_id)])
            
            total_volume = cursor.fetchone()[0] or 0
            
            # Get average trade size
            avg_trade_size = (total_volume / total_trades) if total_trades > 0 else 0
            
            return {
                'total_trades': total_trades,
                'total_closed_positions': total_closed_positions,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'win_rate': float(win_rate),
                'total_volume': float(total_volume),
                'avg_trade_size': float(avg_trade_size),
            }
            
    except Exception as e:
        logger.error(f"Error calculating portfolio metrics: {e}", exc_info=True)
        return {
            'total_trades': 0,
            'total_closed_positions': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0.0,
            'total_volume': 0.0,
            'avg_trade_size': 0.0,
        }