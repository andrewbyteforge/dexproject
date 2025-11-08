"""
Paper Trading Views - Sessions History

Sessions history view for comparing performance across different trading sessions.
Displays interactive charts and session comparison tools.

File: dexproject/paper_trading/views_sessions.py
"""

import logging
from django.shortcuts import render
from django.http import HttpRequest, HttpResponse
from django.contrib import messages

from .models import PaperTradingAccount
from .utils import get_single_trading_account

logger = logging.getLogger(__name__)


def sessions_history_view(request: HttpRequest) -> HttpResponse:
    """
    Sessions history view for comparing performance across trading sessions.
    
    Displays an interactive chart comparing multiple trading sessions,
    allows users to select which sessions to compare, and shows detailed
    statistics for each session.
    
    The actual session data is loaded via JavaScript from the
    /api/sessions/history/ endpoint.
    
    Args:
        request: Django HTTP request
        
    Returns:
        Rendered sessions history template
    """
    try:
        # Get the single account
        account: PaperTradingAccount = get_single_trading_account()
        user = account.user
        
        logger.debug(f"Loading sessions history view for account {account.account_id}")
        
        # Prepare context - the JavaScript will fetch session data via API
        context = {
            'user': user,
            'account': account,
            'page_title': 'Sessions History',
        }
        
        return render(request, 'paper_trading/sessions_analysis.html', context)
        
    except Exception as e:
        logger.error(f"Error loading sessions history view: {e}", exc_info=True)
        messages.error(request, f"Error loading sessions history: {str(e)}")
        # Fallback to dashboard if error
        from django.shortcuts import redirect
        return redirect('paper_trading:dashboard')


# Log module initialization
logger.info("Paper trading sessions history view loaded")