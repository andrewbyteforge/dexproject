"""
Portfolio Views Module - NEW FOR PHASE 5.1C

Contains the new portfolio tracking and trading API views that integrate with
the existing dashboard structure. This module provides the missing API functions
referenced in the URLs.

File: dexproject/dashboard/views/portfolio.py
"""

import json
import logging
import time
from typing import Dict, Any, Optional, List
from decimal import Decimal
from datetime import datetime, timedelta

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Sum, Count, Avg, Q
from django.contrib.auth.models import User

# Import trading models for portfolio data
try:
    from trading.models import Trade, Position, TradingPair, Strategy, Token
    from wallet.models import WalletBalance
    from risk.models import RiskAssessment
    TRADING_MODELS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Trading models not available: {e}")
    TRADING_MODELS_AVAILABLE = False

# Import dashboard models
from ..models import BotConfiguration, TradingSession

logger = logging.getLogger(__name__)


def handle_anonymous_user(request: HttpRequest) -> None:
    """Handle anonymous users by creating demo user."""
    if not request.user.is_authenticated:
        user, created = User.objects.get_or_create(
            username='demo_user',
            defaults={
                'first_name': 'Demo',
                'last_name': 'User',
                'email': 'demo@example.com'
            }
        )
        request.user = user
        if created:
            logger.info("Created demo user for anonymous session")


def _get_portfolio_data(user) -> Dict[str, Any]:
    """
    Get portfolio data for a user with graceful fallback if models aren't available.
    """
    if not TRADING_MODELS_AVAILABLE:
        # Return demo data if trading models aren't available
        return {
            'total_value_usd': 150.75,
            'total_pnl_usd': 25.30,
            'total_roi_percent': 20.1,
            'eth_balance': 0.5,
            'position_count': 2,
            'positions': [
                {
                    'symbol': 'DEMO/USDC',
                    'current_value': 75.25,
                    'invested': 65.00,
                    'pnl': 10.25,
                    'roi_percent': 15.8,
                    'status': 'OPEN',
                    'opened_days': 3
                },
                {
                    'symbol': 'TEST/ETH',
                    'current_value': 75.50,
                    'invested': 60.45,
                    'pnl': 15.05,
                    'roi_percent': 24.9,
                    'status': 'OPEN',
                    'opened_days': 7
                }
            ],
            'has_positions': True,
            'last_updated': timezone.now().isoformat(),
            'demo_mode': True
        }
    
    try:
        if user and user.is_authenticated:
            # Get open positions
            positions = Position.objects.filter(
                user=user,
                status__in=['OPEN', 'PARTIALLY_CLOSED']
            ).select_related('pair__token0', 'pair__token1')
            
            # Get wallet balances
            balances = WalletBalance.objects.filter(wallet__user=user)
        else:
            # Show demo data for anonymous users
            positions = Position.objects.filter(user__isnull=True).select_related(
                'pair__token0', 'pair__token1'
            )[:5]
            balances = WalletBalance.objects.none()
        
        # Calculate portfolio metrics
        total_value_usd = Decimal('0')
        total_invested = Decimal('0')
        total_pnl = Decimal('0')
        
        position_breakdown = []
        for position in positions:
            pos_data = {
                'symbol': f"{position.pair.token0.symbol}/{position.pair.token1.symbol}",
                'current_value': float(position.total_amount_in + position.total_pnl_usd),
                'invested': float(position.total_amount_in),
                'pnl': float(position.total_pnl_usd),
                'roi_percent': float(position.roi_percent) if position.roi_percent else 0,
                'status': position.status,
                'opened_days': (timezone.now() - position.opened_at).days
            }
            position_breakdown.append(pos_data)
            
            total_value_usd += (position.total_amount_in + position.total_pnl_usd)
            total_invested += position.total_amount_in
            total_pnl += position.total_pnl_usd
        
        # Calculate overall portfolio metrics
        total_roi_percent = float((total_pnl / total_invested * 100)) if total_invested > 0 else 0
        
        # Get ETH balance
        eth_balance = Decimal('0')
        for balance in balances:
            if balance.token.symbol == 'ETH':
                eth_balance = balance.balance
                break
        
        return {
            'total_value_usd': float(total_value_usd),
            'total_invested_usd': float(total_invested),
            'total_pnl_usd': float(total_pnl),
            'total_roi_percent': total_roi_percent,
            'eth_balance': float(eth_balance),
            'position_count': len(position_breakdown),
            'positions': position_breakdown,
            'has_positions': len(position_breakdown) > 0,
            'last_updated': timezone.now().isoformat(),
            'demo_mode': False
        }
        
    except Exception as e:
        logger.error(f"Error getting portfolio data: {e}")
        # Return empty portfolio data on error
        return {
            'total_value_usd': 0,
            'total_invested_usd': 0,
            'total_pnl_usd': 0,
            'total_roi_percent': 0,
            'eth_balance': 0,
            'position_count': 0,
            'positions': [],
            'has_positions': False,
            'error': str(e),
            'demo_mode': False
        }


def _get_trading_activity(user, limit: int = 10) -> Dict[str, Any]:
    """Get recent trading activity for a user."""
    if not TRADING_MODELS_AVAILABLE:
        # Return demo trading data
        return {
            'recent_trades': [
                {
                    'trade_id': 'demo-001',
                    'type': 'BUY',
                    'symbol': 'DEMO/USDC',
                    'amount': 0.025,
                    'price_usd': 65.00,
                    'status': 'CONFIRMED',
                    'timestamp': (timezone.now() - timedelta(hours=2)).isoformat(),
                    'transaction_hash': '0xdemo123...'
                },
                {
                    'trade_id': 'demo-002',
                    'type': 'BUY',
                    'symbol': 'TEST/ETH',
                    'amount': 0.030,
                    'price_usd': 60.45,
                    'status': 'CONFIRMED',
                    'timestamp': (timezone.now() - timedelta(hours=8)).isoformat(),
                    'transaction_hash': '0xdemo456...'
                }
            ],
            'total_trades_30d': 5,
            'successful_trades_30d': 4,
            'success_rate_30d': 80.0,
            'has_activity': True,
            'demo_mode': True
        }
    
    try:
        if user and user.is_authenticated:
            # Get recent trades
            recent_trades = Trade.objects.filter(user=user).select_related(
                'pair__token0', 'pair__token1'
            ).order_by('-created_at')[:limit]
            
            # Get trade statistics for last 30 days
            last_30_days = timezone.now() - timedelta(days=30)
            trades_30d = Trade.objects.filter(
                user=user,
                created_at__gte=last_30_days
            )
        else:
            # Demo data for anonymous users
            recent_trades = Trade.objects.filter(user__isnull=True).select_related(
                'pair__token0', 'pair__token1'
            ).order_by('-created_at')[:limit]
            trades_30d = Trade.objects.filter(user__isnull=True)
        
        # Process recent trades
        trade_activity = []
        for trade in recent_trades:
            trade_data = {
                'trade_id': str(trade.trade_id),
                'type': trade.trade_type,
                'symbol': f"{trade.pair.token0.symbol}/{trade.pair.token1.symbol}",
                'amount': float(trade.amount_in),
                'price_usd': float(trade.price_usd) if trade.price_usd else None,
                'status': trade.status,
                'timestamp': trade.created_at.isoformat(),
                'transaction_hash': trade.transaction_hash[:10] + '...' if trade.transaction_hash else None
            }
            trade_activity.append(trade_data)
        
        # Calculate 30-day statistics
        total_trades_30d = trades_30d.count()
        successful_trades_30d = trades_30d.filter(status='CONFIRMED').count()
        success_rate = (successful_trades_30d / total_trades_30d * 100) if total_trades_30d > 0 else 0
        
        return {
            'recent_trades': trade_activity,
            'total_trades_30d': total_trades_30d,
            'successful_trades_30d': successful_trades_30d,
            'success_rate_30d': success_rate,
            'has_activity': len(trade_activity) > 0,
            'demo_mode': False
        }
        
    except Exception as e:
        logger.error(f"Error getting trading activity: {e}")
        return {
            'recent_trades': [],
            'total_trades_30d': 0,
            'successful_trades_30d': 0,
            'success_rate_30d': 0,
            'has_activity': False,
            'error': str(e),
            'demo_mode': False
        }


def _get_performance_analytics(user) -> Dict[str, Any]:
    """Get performance analytics for dashboard."""
    if not TRADING_MODELS_AVAILABLE:
        return {
            'win_rate_percent': 75.0,
            'total_trades': 5,
            'total_volume_usd': 325.45,
            'avg_trade_size_usd': 65.09,
            'sharpe_ratio': 1.25,
            'active_positions': 2,
            'max_drawdown_percent': -5.2,
            'profit_factor': 1.8,
            'demo_mode': True
        }
    
    try:
        if user and user.is_authenticated:
            trades = Trade.objects.filter(user=user, status='CONFIRMED')
            positions = Position.objects.filter(user=user)
        else:
            trades = Trade.objects.filter(user__isnull=True, status='CONFIRMED')
            positions = Position.objects.filter(user__isnull=True)
        
        # Calculate win rate
        profitable_positions = positions.filter(total_pnl_usd__gt=0).count()
        total_closed_positions = positions.filter(status='CLOSED').count()
        win_rate = (profitable_positions / total_closed_positions * 100) if total_closed_positions > 0 else 0
        
        # Calculate average trade metrics
        avg_trade_size = trades.aggregate(Avg('amount_in'))['amount_in__avg'] or Decimal('0')
        total_volume = trades.aggregate(Sum('amount_in'))['amount_in__sum'] or Decimal('0')
        
        return {
            'win_rate_percent': win_rate,
            'total_trades': trades.count(),
            'total_volume_usd': float(total_volume),
            'avg_trade_size_usd': float(avg_trade_size),
            'sharpe_ratio': 0,  # Would need historical data calculation
            'active_positions': positions.filter(status='OPEN').count(),
            'max_drawdown_percent': 0,  # Would need historical data calculation
            'profit_factor': 1.0,  # Would need win/loss ratio calculation
            'demo_mode': False
        }
        
    except Exception as e:
        logger.error(f"Error getting performance analytics: {e}")
        return {
            'win_rate_percent': 0,
            'total_trades': 0,
            'total_volume_usd': 0,
            'avg_trade_size_usd': 0,
            'sharpe_ratio': 0,
            'active_positions': 0,
            'max_drawdown_percent': 0,
            'profit_factor': 0,
            'error': str(e),
            'demo_mode': False
        }


def _get_risk_metrics(user) -> Dict[str, Any]:
    """Get risk metrics summary."""
    if not TRADING_MODELS_AVAILABLE:
        return {
            'avg_risk_score': 35.5,
            'total_assessments_7d': 12,
            'high_risk_tokens': 2,
            'blocked_tokens': 1,
            'approved_tokens': 9,
            'risk_system_active': True,
            'demo_mode': True
        }
    
    try:
        # Get recent risk assessments
        last_7_days = timezone.now() - timedelta(days=7)
        recent_assessments = RiskAssessment.objects.filter(
            created_at__gte=last_7_days
        ).order_by('-created_at')
        
        if recent_assessments.exists():
            avg_risk_score = recent_assessments.aggregate(
                avg_risk=Avg('overall_risk_score')
            )['avg_risk'] or 0
            
            high_risk_count = recent_assessments.filter(overall_risk_score__gte=70).count()
            blocked_count = recent_assessments.filter(trading_decision='BLOCK').count()
            approved_count = recent_assessments.filter(trading_decision='APPROVE').count()
        else:
            avg_risk_score = 0
            high_risk_count = 0
            blocked_count = 0
            approved_count = 0
        
        return {
            'avg_risk_score': float(avg_risk_score),
            'total_assessments_7d': recent_assessments.count(),
            'high_risk_tokens': high_risk_count,
            'blocked_tokens': blocked_count,
            'approved_tokens': approved_count,
            'risk_system_active': True,
            'demo_mode': False
        }
        
    except Exception as e:
        logger.error(f"Error getting risk metrics: {e}")
        return {
            'avg_risk_score': 0,
            'total_assessments_7d': 0,
            'high_risk_tokens': 0,
            'blocked_tokens': 0,
            'approved_tokens': 0,
            'risk_system_active': False,
            'error': str(e),
            'demo_mode': False
        }


# =============================================================================
# API ENDPOINTS - NEW FOR PHASE 5.1C
# =============================================================================

@require_http_methods(["GET"])
@csrf_exempt
def api_portfolio_summary(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for real-time portfolio summary data.
    
    NEW: Provides portfolio data for AJAX updates.
    """
    try:
        handle_anonymous_user(request)
        portfolio_data = _get_portfolio_data(request.user)
        
        return JsonResponse({
            'status': 'success',
            'data': portfolio_data,
            'timestamp': timezone.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error in portfolio summary API: {e}")
        return JsonResponse({
            'status': 'error',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=500)


@require_http_methods(["GET"])
@csrf_exempt
def api_trading_activity(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for recent trading activity.
    
    NEW: Provides trading activity data for AJAX updates.
    """
    try:
        handle_anonymous_user(request)
        limit = int(request.GET.get('limit', 10))
        trading_activity = _get_trading_activity(request.user, limit=limit)
        
        return JsonResponse({
            'status': 'success',
            'data': trading_activity,
            'timestamp': timezone.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error in trading activity API: {e}")
        return JsonResponse({
            'status': 'error',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=500)


@require_http_methods(["POST"])
@csrf_exempt
def api_manual_trade(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for manual trading actions.
    
    NEW: Enables manual buy/sell from the dashboard.
    """
    try:
        handle_anonymous_user(request)
        data = json.loads(request.body)
        
        action = data.get('action')  # 'buy' or 'sell'
        token_address = data.get('token_address')
        pair_address = data.get('pair_address')
        amount = data.get('amount')
        
        if not all([action, token_address, pair_address, amount]):
            return JsonResponse({
                'status': 'error',
                'error': 'Missing required parameters: action, token_address, pair_address, amount'
            }, status=400)
        
        # Validate addresses
        if not token_address.startswith('0x') or not pair_address.startswith('0x'):
            return JsonResponse({
                'status': 'error',
                'error': 'Invalid contract addresses. Must start with 0x'
            }, status=400)
        
        # For now, return a simulated response since we don't have Celery running
        # In a real implementation, this would trigger the trading tasks
        
        logger.info(f"Manual {action} order simulated: {amount} for {token_address[:10]}...")
        
        return JsonResponse({
            'status': 'success',
            'data': {
                'task_id': f'demo-task-{int(time.time())}',
                'message': f'{action.title()} order submitted for processing (demo mode)',
                'action': action,
                'token_address': token_address,
                'amount': amount,
                'demo_mode': True
            },
            'timestamp': timezone.now().isoformat()
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'error': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        logger.error(f"Error in manual trade API: {e}")
        return JsonResponse({
            'status': 'error',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=500)


# =============================================================================
# ENHANCED ANALYTICS VIEW
# =============================================================================

def enhanced_dashboard_analytics(request: HttpRequest) -> HttpResponse:
    """
    Enhanced analytics dashboard with real portfolio and trading data.
    
    NEW: This view replaces the "Coming Soon" analytics with real data.
    """
    handle_anonymous_user(request)
    
    try:
        # Get existing engine and performance metrics (if available)
        try:
            from ..engine_service import engine_service
            engine_status = engine_service.get_engine_status()
            performance_metrics = engine_service.get_performance_metrics()
        except ImportError:
            engine_status = {'status': 'UNKNOWN', 'fast_lane_active': False, 'smart_lane_active': False}
            performance_metrics = {'data_source': 'DEMO', '_mock': True}
        
        # Get wallet info (simplified)
        wallet_info = {
            'connected': False,  # Would check SIWE session in real implementation
            'address': None,
            'chain_id': None
        }
        
        # Get portfolio and trading data
        portfolio_data = _get_portfolio_data(request.user)
        trading_activity = _get_trading_activity(request.user)
        performance_analytics = _get_performance_analytics(request.user)
        risk_metrics = _get_risk_metrics(request.user)
        
        # Calculate P&L metrics (simplified)
        pnl_metrics = {
            'total_realized_pnl': portfolio_data.get('total_pnl_usd', 0) * 0.7,  # Approximation
            'total_unrealized_pnl': portfolio_data.get('total_pnl_usd', 0) * 0.3,  # Approximation
            'total_pnl': portfolio_data.get('total_pnl_usd', 0),
            'daily_pnl': [
                {'date': (timezone.now() - timedelta(days=i)).date().isoformat(), 'pnl': portfolio_data.get('total_pnl_usd', 0) / 7}
                for i in range(7, 0, -1)
            ]
        }
        
        # Get trading sessions (simplified)
        trading_sessions = TradingSession.objects.filter(
            user=request.user
        ).order_by('-created_at')[:20] if hasattr(request.user, 'id') else []
        
        context = {
            'page_title': 'Trading Analytics',
            'user': request.user,
            'engine_status': engine_status,
            'performance_metrics': performance_metrics,
            'wallet_info': wallet_info,
            
            # NEW: Real portfolio and trading data
            'portfolio_data': portfolio_data,
            'trading_activity': trading_activity,
            'pnl_metrics': pnl_metrics,
            'performance_analytics': performance_analytics,
            'risk_metrics': risk_metrics,
            
            # Data availability flags
            'has_portfolio_data': portfolio_data.get('has_positions', False),
            'has_trading_data': trading_activity.get('has_activity', False),
            'analytics_ready': portfolio_data.get('has_positions', False) or trading_activity.get('has_activity', False),
            
            # Existing data
            'trading_sessions': trading_sessions,
            'total_sessions': len(trading_sessions),
            'active_sessions': len([s for s in trading_sessions if getattr(s, 'is_active', False)]),
            'data_source': 'LIVE' if not performance_metrics.get('_mock', False) else 'DEMO',
            
            # Chart data for frontend
            'chart_data': {
                'pnl_timeline': pnl_metrics.get('daily_pnl', []),
                'portfolio_breakdown': [
                    {'name': pos['symbol'], 'value': pos['current_value']} 
                    for pos in portfolio_data.get('positions', [])
                ]
            }
        }
        
        return render(request, 'dashboard/analytics.html', context)
        
    except Exception as e:
        logger.error(f"Error loading enhanced analytics page: {e}", exc_info=True)
        return render(request, 'dashboard/error.html', {'error': str(e)})