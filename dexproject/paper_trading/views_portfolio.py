"""
Paper Trading Views - Portfolio

Portfolio positions and allocation view displaying open and closed positions,
portfolio distribution, and comprehensive P&L metrics.

File: dexproject/paper_trading/views_portfolio.py
"""

import json
import logging
from decimal import Decimal
from typing import Dict, Any

from django.shortcuts import render, redirect
from django.http import HttpRequest, HttpResponse
from django.contrib import messages

from .models import PaperTradingAccount, PaperPosition
from .utils import get_single_trading_account, to_decimal
from .views_helpers import format_position_for_template

logger = logging.getLogger(__name__)


def portfolio_view(request: HttpRequest) -> HttpResponse:
    """
    Display portfolio positions and allocation.
    
    Shows comprehensive portfolio view with open and closed positions,
    value distribution, and performance metrics.
    
    Args:
        request: Django HTTP request
        
    Returns:
        Rendered portfolio template
    """
    try:
        # Get the single account
        account: PaperTradingAccount = get_single_trading_account()
        user = account.user
        
        logger.debug(f"Loading portfolio view for account {account.account_id}")
        
        # Get positions with error handling and formatting
        try:
            raw_open_positions = PaperPosition.objects.filter(
                account=account,
                is_open=True
            ).order_by('-current_value_usd')
            open_positions = [format_position_for_template(pos) for pos in raw_open_positions]
        except Exception as e:
            logger.error(f"Error fetching open positions: {e}")
            open_positions = []
        
        try:
            raw_closed_positions = PaperPosition.objects.filter(
                account=account,
                is_open=False
            ).order_by('-closed_at')[:20]
            closed_positions = [format_position_for_template(pos) for pos in raw_closed_positions]
        except Exception as e:
            logger.error(f"Error fetching closed positions: {e}")
            closed_positions = []
        
        # Calculate portfolio metrics with safe decimal handling
        try:
            portfolio_value = to_decimal(account.current_balance_usd) + sum(
                to_decimal(pos['current_value_usd']) for pos in open_positions
            )
        except Exception as e:
            logger.error(f"Error calculating portfolio value: {e}")
            portfolio_value = to_decimal(account.current_balance_usd)
        
        try:
            total_invested = sum(
                to_decimal(pos['total_invested_usd']) for pos in open_positions
            )
        except Exception as e:
            logger.error(f"Error calculating total invested: {e}")
            total_invested = Decimal('0')
        
        total_current_value = sum(to_decimal(pos['current_value_usd']) for pos in open_positions)
        unrealized_pnl = total_current_value - total_invested if total_invested > 0 else Decimal('0')
        
        # Position distribution for chart
        position_distribution = {}
        for pos in open_positions:
            try:
                if pos['token_symbol'] and portfolio_value > 0:
                    position_distribution[pos['token_symbol']] = {
                        'value': float(pos['current_value_usd']),
                        'percentage': float((pos['current_value_usd'] / portfolio_value * 100)),
                        'pnl': float(pos['unrealized_pnl_usd'])
                   }
            except Exception as e:
                logger.warning(f"Error calculating distribution for {pos['token_symbol']}: {e}")
                continue
        
        context = {
            'page_title': 'Portfolio',
            'account': account,
            'open_positions': open_positions,
            'closed_positions': closed_positions,
            'portfolio_value': portfolio_value,
            'cash_balance': to_decimal(account.current_balance_usd),
            'total_invested': total_invested,
            'unrealized_pnl': unrealized_pnl,
            'position_distribution': json.dumps(position_distribution),
            'positions_count': len(open_positions),
            'user': user,
        }
        
        logger.info(f"Successfully loaded portfolio with {len(open_positions)} open positions")
        return render(request, 'paper_trading/portfolio.html', context)
        
    except Exception as e:
        logger.error(f"Error loading portfolio: {e}", exc_info=True)
        messages.error(request, f"Error loading portfolio: {str(e)}")
        return redirect('paper_trading:dashboard')