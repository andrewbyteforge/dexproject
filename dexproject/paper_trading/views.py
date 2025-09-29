"""
Paper Trading Views - Dashboard and Page Views

This module provides all dashboard and page views for the paper trading system.
Includes portfolio display, trade history, and configuration management pages.
API endpoints have been moved to api_views.py

File: dexproject/paper_trading/views.py
"""

import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Dict, Any

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Avg, Count
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import connection

# Import all models
from .models import (
    PaperTradingAccount,
    PaperTrade,
    PaperPosition,
    PaperTradingConfig,
    PaperAIThoughtLog,
    PaperStrategyConfiguration,
    PaperTradingSession,
    PaperPerformanceMetrics
)

logger = logging.getLogger(__name__)


# =============================================================================
# DASHBOARD VIEWS
# =============================================================================


def paper_trading_dashboard(request: HttpRequest) -> HttpResponse:
    """
    Main paper trading dashboard view.
    
    Displays portfolio summary, active positions, recent trades,
    and performance metrics with AI thought logs.
    
    Args:
        request: Django HTTP request
        
    Returns:
        Rendered dashboard template with context data
    """
    try:
        logger.debug(f"Loading paper trading dashboard for user: {request.user}")
        from django.contrib.auth.models import User
        
        # Get demo user for now (will be replaced with actual user)
        try:
            demo_user = User.objects.get(username='demo_user')
        except User.DoesNotExist:
            # Create demo user if it doesn't exist
            demo_user = User.objects.create_user(
                username='demo_user',
                email='demo@example.com',
                password='demo_password'
            )
            logger.info("Created demo_user for paper trading")
        
        # Get or create paper trading account
        account, created = PaperTradingAccount.objects.get_or_create(
            user=demo_user,
            is_active=True,
            defaults={
                'name': 'Demo Paper Trading Account',
                'initial_balance_usd': Decimal('10000.00'),
                'current_balance_usd': Decimal('10000.00')
            }
        )
        
        if created:
            logger.info(f"Created new paper trading account: {account.account_id}")
        
        # Get active session if exists
        active_session = PaperTradingSession.objects.filter(
            account=account,
            status="ACTIVE"
        ).first()
        
        # Get recent trades with error handling
        try:
            recent_trades = PaperTrade.objects.filter(
                account=account
            ).order_by('-created_at')[:10]
        except Exception as e:
            logger.warning(f"Error fetching recent trades: {e}")
            recent_trades = []
        
        # Get open positions with error handling
        try:
            open_positions = PaperPosition.objects.filter(
                account=account,
                is_open=True
            ).order_by('-current_value_usd')
        except Exception as e:
            logger.warning(f"Error fetching open positions: {e}")
            open_positions = []
        
        # Get recent AI thoughts
        recent_thoughts = PaperAIThoughtLog.objects.filter(
            account=account
        ).order_by('-created_at')[:5]
        
        # Get performance metrics
        performance = None
        if active_session:
            try:
                performance = PaperPerformanceMetrics.objects.filter(
                    session=active_session
                ).order_by('-calculated_at').first()
            except Exception as e:
                logger.warning(f"Error fetching performance metrics: {e}")
        
        # Calculate summary statistics with error handling
        total_trades = account.total_trades or 0
        successful_trades = account.successful_trades or 0
        
        # Get 24h stats with error handling
        time_24h_ago = timezone.now() - timedelta(hours=24)
        try:
            trades_24h = PaperTrade.objects.filter(
                account=account,
                created_at__gte=time_24h_ago
            ).aggregate(
                count=Count('trade_id'),
                total_volume=Sum('amount_in_usd', default=Decimal('0'))
            )
        except Exception as e:
            logger.warning(f"Error calculating 24h stats: {e}")
            trades_24h = {'count': 0, 'total_volume': 0}
        
        context = {
            'page_title': 'Paper Trading Dashboard',
            'account': account,
            'active_session': active_session,
            'recent_trades': recent_trades,
            'open_positions': open_positions,
            'performance': performance,
            'recent_thoughts': recent_thoughts,
            'total_trades': total_trades,
            'successful_trades': successful_trades,
            'win_rate': (successful_trades / total_trades * 100) if total_trades > 0 else 0,
            'trades_24h': trades_24h.get('count', 0),
            'volume_24h': trades_24h.get('total_volume', 0),
            'current_balance': account.current_balance_usd,
            'initial_balance': account.initial_balance_usd,
            'total_pnl': account.total_pnl_usd,
            'return_percent': account.total_return_percent,
        }
        
        logger.info(f"Successfully loaded dashboard for account {account.account_id}")
        return render(request, 'paper_trading/dashboard.html', context)
        
    except Exception as e:
        logger.error(f"Error loading paper trading dashboard: {e}", exc_info=True)
        messages.error(request, f"Error loading dashboard: {str(e)}")
        return render(request, 'paper_trading/error.html', {"error": str(e)})


def trade_history(request: HttpRequest) -> HttpResponse:
    """
    Display detailed trade history with filtering and pagination.
    
    Args:
        request: Django HTTP request with optional filters
        
    Returns:
        Rendered trade history template
    """
    try:
        logger.debug("Loading trade history page")
        from django.contrib.auth.models import User
        
        try:
            demo_user = User.objects.get(username='demo_user')
        except User.DoesNotExist:
            logger.warning("Demo user not found for trade history")
            messages.error(request, "Demo user not found")
            return redirect('paper_trading:dashboard')
        
        account = get_object_or_404(
            PaperTradingAccount,
            user=demo_user,
            is_active=True
        )
        
        # Build query with filters
        trades_query = PaperTrade.objects.filter(account=account)
        
        # Apply filters with validation
        status_filter = request.GET.get('status')
        if status_filter:
            trades_query = trades_query.filter(status=status_filter)
            logger.debug(f"Applied status filter: {status_filter}")
        
        trade_type = request.GET.get('type')
        if trade_type:
            trades_query = trades_query.filter(trade_type=trade_type)
            logger.debug(f"Applied trade type filter: {trade_type}")
        
        token_symbol = request.GET.get('token')
        if token_symbol:
            trades_query = trades_query.filter(
                Q(token_in_symbol__icontains=token_symbol) | 
                Q(token_out_symbol__icontains=token_symbol)
            )
            logger.debug(f"Applied token filter: {token_symbol}")
        
        # Date range filter with validation
        date_from = request.GET.get('date_from')
        if date_from:
            try:
                trades_query = trades_query.filter(created_at__gte=date_from)
                logger.debug(f"Applied date from filter: {date_from}")
            except Exception as e:
                logger.warning(f"Invalid date_from format: {date_from}, error: {e}")
        
        date_to = request.GET.get('date_to')
        if date_to:
            try:
                trades_query = trades_query.filter(created_at__lte=date_to)
                logger.debug(f"Applied date to filter: {date_to}")
            except Exception as e:
                logger.warning(f"Invalid date_to format: {date_to}, error: {e}")
        
        # Order by creation date
        trades_query = trades_query.order_by('-created_at')
        
        # Pagination with error handling
        paginator = Paginator(trades_query, 25)
        page_number = request.GET.get('page', 1)
        try:
            page_obj = paginator.get_page(page_number)
        except Exception as e:
            logger.warning(f"Pagination error: {e}")
            page_obj = paginator.get_page(1)
        
        # Calculate summary stats with error handling
        try:
            summary_stats = trades_query.aggregate(
                total_trades=Count('trade_id'),
                total_volume=Sum('amount_in_usd', default=Decimal('0')),
                avg_trade_size=Avg('amount_in_usd', default=Decimal('0')),
                successful_trades=Count('trade_id', filter=Q(status='COMPLETED'))
            )
        except Exception as e:
            logger.error(f"Error calculating summary stats: {e}")
            summary_stats = {
                'total_trades': 0,
                'total_volume': 0,
                'avg_trade_size': 0,
                'successful_trades': 0
            }
        
        context = {
            'page_title': 'Trade History',
            'account': account,
            'page_obj': page_obj,
            'trades': page_obj,
            'filters': {
                'status': status_filter,
                'type': trade_type,
                'token': token_symbol,
                'date_from': date_from,
                'date_to': date_to,
            },
            'summary': summary_stats,
        }
        
        logger.info(f"Successfully loaded trade history: {summary_stats['total_trades']} trades")
        return render(request, 'paper_trading/trade_history.html', context)
        
    except Exception as e:
        logger.error(f"Error loading trade history: {e}", exc_info=True)
        messages.error(request, f"Error loading trade history: {str(e)}")
        return redirect('paper_trading:dashboard')


def portfolio_view(request: HttpRequest) -> HttpResponse:
    """
    Display portfolio positions and allocation.
    
    Args:
        request: Django HTTP request
        
    Returns:
        Rendered portfolio template
    """
    try:
        logger.debug("Loading portfolio view")
        from django.contrib.auth.models import User
        
        try:
            demo_user = User.objects.get(username='demo_user')
        except User.DoesNotExist:
            logger.warning("Demo user not found for portfolio view")
            messages.error(request, "Demo user not found")
            return redirect('paper_trading:dashboard')
        
        account = get_object_or_404(
            PaperTradingAccount,
            user=demo_user,
            is_active=True
        )
        
        # Get positions with error handling
        try:
            open_positions = PaperPosition.objects.filter(
                account=account,
                is_open=True
            ).order_by('-current_value_usd')
        except Exception as e:
            logger.error(f"Error fetching open positions: {e}")
            open_positions = []
        
        try:
            closed_positions = PaperPosition.objects.filter(
                account=account,
                is_open=False
            ).order_by('-closed_at')[:20]
        except Exception as e:
            logger.error(f"Error fetching closed positions: {e}")
            closed_positions = []
        
        # Calculate portfolio metrics with safe defaults
        try:
            portfolio_value = account.current_balance_usd + sum(
                pos.current_value_usd or Decimal('0') for pos in open_positions
            )
        except Exception as e:
            logger.error(f"Error calculating portfolio value: {e}")
            portfolio_value = account.current_balance_usd
        
        try:
            total_invested = sum(
                (pos.average_entry_price_usd or Decimal('0')) * (pos.quantity or Decimal('0'))
                for pos in open_positions 
                if pos.average_entry_price_usd
            )
        except Exception as e:
            logger.error(f"Error calculating total invested: {e}")
            total_invested = Decimal('0')
        
        total_current_value = sum(pos.current_value_usd or Decimal('0') for pos in open_positions)
        unrealized_pnl = total_current_value - total_invested if total_invested > 0 else Decimal('0')
        
        # Position distribution for chart
        position_distribution = {}
        for pos in open_positions:
            try:
                if pos.token_symbol and portfolio_value > 0:
                    position_distribution[pos.token_symbol] = {
                        'value': float(pos.current_value_usd or 0),
                        'percentage': float(((pos.current_value_usd or 0) / portfolio_value * 100)),
                        'pnl': float(pos.unrealized_pnl_usd or 0)
                    }
            except Exception as e:
                logger.warning(f"Error calculating distribution for {pos.token_symbol}: {e}")
                continue
        
        context = {
            'page_title': 'Portfolio',
            'account': account,
            'open_positions': open_positions,
            'closed_positions': closed_positions,
            'portfolio_value': portfolio_value,
            'cash_balance': account.current_balance_usd,
            'total_invested': total_invested,
            'unrealized_pnl': unrealized_pnl,
            'position_distribution': json.dumps(position_distribution),
            'positions_count': len(open_positions),
        }
        
        logger.info(f"Successfully loaded portfolio with {len(open_positions)} open positions")
        return render(request, 'paper_trading/portfolio.html', context)
        
    except Exception as e:
        logger.error(f"Error loading portfolio: {e}", exc_info=True)
        messages.error(request, f"Error loading portfolio: {str(e)}")
        return redirect('paper_trading:dashboard')








"""
Enhanced configuration_view with pagination and delete functionality
Replace the existing configuration_view function in paper_trading/views.py

File Path: dexproject/paper_trading/views.py
Function: configuration_view (replace existing around line 385)
"""

@require_http_methods(["GET", "POST"])
def configuration_view(request: HttpRequest) -> HttpResponse:
    """
    Strategy configuration management view with pagination and delete.
    
    Handles display, updates, and deletion of trading strategy configurations.
    
    Args:
        request: Django HTTP request
        
    Returns:
        Rendered configuration template or redirect after action
    """
    try:
        logger.debug("Loading configuration view")
        from django.contrib.auth.models import User
        
        # Get demo user
        try:
            demo_user = User.objects.get(username='demo_user')
        except User.DoesNotExist:
            logger.warning("Demo user not found for configuration")
            messages.error(request, "Demo user not found")
            return redirect('paper_trading:dashboard')
        
        # Get account
        account = get_object_or_404(
            PaperTradingAccount,
            user=demo_user,
            is_active=True
        )
        
        # Handle delete action if requested
        if request.method == 'POST' and request.POST.get('action') == 'delete':
            config_id = request.POST.get('config_id')
            if config_id:
                try:
                    config_to_delete = PaperStrategyConfiguration.objects.get(
                        config_id=config_id,
                        account=account
                    )
                    # Don't delete if it's the only configuration or if it's active
                    total_configs = PaperStrategyConfiguration.objects.filter(account=account).count()
                    
                    if total_configs <= 1:
                        messages.warning(request, "Cannot delete the last configuration")
                    elif config_to_delete.is_active:
                        messages.warning(request, "Cannot delete active configuration. Please activate another configuration first.")
                    else:
                        config_name = config_to_delete.name
                        config_to_delete.delete()
                        messages.success(request, f'Configuration "{config_name}" deleted successfully')
                        logger.info(f"Deleted configuration {config_id} for account {account.account_id}")
                except PaperStrategyConfiguration.DoesNotExist:
                    messages.error(request, "Configuration not found")
                except Exception as e:
                    messages.error(request, f"Error deleting configuration: {str(e)}")
                    logger.error(f"Error deleting configuration: {e}", exc_info=True)
                
                return redirect('paper_trading:configuration')
        
        # Handle load/activate configuration
        if request.method == 'GET' and request.GET.get('load_config'):
            config_id = request.GET.get('load_config')
            try:
                config_to_load = PaperStrategyConfiguration.objects.get(
                    config_id=config_id,
                    account=account
                )
                # Deactivate all others and activate this one
                PaperStrategyConfiguration.objects.filter(
                    account=account
                ).update(is_active=False)
                
                config_to_load.is_active = True
                config_to_load.save()
                
                messages.success(request, f'Configuration "{config_to_load.name}" loaded and activated')
                logger.info(f"Loaded configuration {config_id} for account {account.account_id}")
                return redirect('paper_trading:configuration')
                
            except PaperStrategyConfiguration.DoesNotExist:
                messages.error(request, "Configuration not found")
            except Exception as e:
                messages.error(request, f"Error loading configuration: {str(e)}")
                logger.error(f"Error loading configuration: {e}", exc_info=True)
        
        # Get the active configuration
        config = PaperStrategyConfiguration.objects.filter(
            account=account,
            is_active=True
        ).order_by('-updated_at').first()
        
        # If no active config, get the most recent one
        if not config:
            config = PaperStrategyConfiguration.objects.filter(
                account=account
            ).order_by('-updated_at').first()
        
        # If still no config, create a new one with defaults
        if not config:
            config = PaperStrategyConfiguration.objects.create(
                account=account,
                name='Default Strategy',
                is_active=True,
                trading_mode='MODERATE',
                use_fast_lane=True,
                use_smart_lane=False,
                fast_lane_threshold_usd=Decimal('100'),
                max_position_size_percent=Decimal('25'),
                stop_loss_percent=Decimal('5'),
                take_profit_percent=Decimal('10'),
                max_daily_trades=20,
                max_concurrent_positions=10,
                min_liquidity_usd=Decimal('10000'),
                max_slippage_percent=Decimal('2'),
                confidence_threshold=Decimal('60'),
                allowed_tokens=[],
                blocked_tokens=[],
                custom_parameters={}
            )
            logger.info(f"Created new strategy configuration for account {account.account_id}")
        else:
            logger.info(f"Using existing configuration: {config.config_id}")
        
        # Handle configuration update (POST without delete action)
        if request.method == 'POST' and request.POST.get('action') != 'delete':
            try:
                # Check if creating new or updating existing
                save_as_new = request.POST.get('save_as_new') == 'true'
                
                if save_as_new:
                    # Create a new configuration
                    new_config = PaperStrategyConfiguration(account=account)
                    update_target = new_config
                    # Deactivate others if this will be active
                    if request.POST.get('is_active', 'true').lower() == 'true':
                        PaperStrategyConfiguration.objects.filter(
                            account=account
                        ).update(is_active=False)
                else:
                    update_target = config
                
                # Update configuration from form data
                update_target.name = request.POST.get('name', update_target.name if not save_as_new else 'New Strategy')
                update_target.trading_mode = request.POST.get('trading_mode', 'MODERATE')
                update_target.use_fast_lane = request.POST.get('use_fast_lane') == 'on'
                update_target.use_smart_lane = request.POST.get('use_smart_lane') == 'on'
                update_target.is_active = request.POST.get('is_active', 'true').lower() == 'true'
                
                # Update numeric fields with error handling
                try:
                    update_target.max_position_size_percent = Decimal(request.POST.get('max_position_size_percent', '25'))
                except (ValueError, InvalidOperation):
                    update_target.max_position_size_percent = Decimal('25')
                
                try:
                    update_target.max_daily_trades = int(request.POST.get('max_daily_trades', '20'))
                except ValueError:
                    update_target.max_daily_trades = 20
                
                try:
                    update_target.max_concurrent_positions = int(request.POST.get('max_concurrent_positions', '10'))
                except ValueError:
                    update_target.max_concurrent_positions = 10
                
                try:
                    update_target.confidence_threshold = Decimal(request.POST.get('confidence_threshold', '60'))
                except (ValueError, InvalidOperation):
                    update_target.confidence_threshold = Decimal('60')
                
                try:
                    update_target.stop_loss_percent = Decimal(request.POST.get('stop_loss_percent', '5'))
                except (ValueError, InvalidOperation):
                    update_target.stop_loss_percent = Decimal('5')
                
                try:
                    update_target.take_profit_percent = Decimal(request.POST.get('take_profit_percent', '10'))
                except (ValueError, InvalidOperation):
                    update_target.take_profit_percent = Decimal('10')
                
                try:
                    update_target.min_liquidity_usd = Decimal(request.POST.get('min_liquidity_usd', '10000'))
                except (ValueError, InvalidOperation):
                    update_target.min_liquidity_usd = Decimal('10000')
                
                try:
                    update_target.max_slippage_percent = Decimal(request.POST.get('max_slippage_percent', '2'))
                except (ValueError, InvalidOperation):
                    update_target.max_slippage_percent = Decimal('2')
                
                try:
                    update_target.fast_lane_threshold_usd = Decimal(request.POST.get('fast_lane_threshold_usd', '100'))
                except (ValueError, InvalidOperation):
                    update_target.fast_lane_threshold_usd = Decimal('100')
                
                # Save the configuration
                update_target.save()
                
                # If this config is set to active and not new, deactivate others
                if update_target.is_active and not save_as_new:
                    PaperStrategyConfiguration.objects.filter(
                        account=account
                    ).exclude(config_id=update_target.config_id).update(is_active=False)
                
                action_word = "created" if save_as_new else "updated"
                messages.success(request, f'Configuration "{update_target.name}" {action_word} successfully!')
                logger.info(f"{action_word.capitalize()} configuration {update_target.config_id} for account {account.account_id}")
                
                return redirect('paper_trading:configuration')
                
            except Exception as e:
                messages.error(request, f'Error saving configuration: {str(e)}')
                logger.error(f"Configuration save error: {e}", exc_info=True)
        
        # Get all configurations with pagination
        all_configs_query = PaperStrategyConfiguration.objects.filter(
            account=account
        ).order_by('-is_active', '-updated_at')  # Active first, then by update time
        
        # Pagination
        configs_per_page = 10  # Show 10 configs per page
        paginator = Paginator(all_configs_query, configs_per_page)
        page_number = request.GET.get('page', 1)
        
        try:
            all_configs = paginator.get_page(page_number)
        except Exception as e:
            logger.warning(f"Pagination error: {e}")
            all_configs = paginator.get_page(1)
        
        # Get active session for bot status
        active_session = PaperTradingSession.objects.filter(
            account=account,
            status="ACTIVE"
        ).first()
        
        # Load available strategies
        available_strategies = [
            {'name': 'smart_lane', 'display': 'Smart Lane Strategy'},
            {'name': 'momentum', 'display': 'Momentum Trading'},
            {'name': 'mean_reversion', 'display': 'Mean Reversion'},
            {'name': 'arbitrage', 'display': 'Arbitrage Bot'},
        ]
        
        # Prepare context
        context = {
            'page_title': 'Strategy Configuration',
            'account': account,
            'config': config,
            'available_strategies': available_strategies,
            'all_configs': all_configs,  # This is now a Page object
            'active_session': active_session,
            'total_configs': all_configs_query.count(),
            
            # Map actual model fields to template variables
            'strategy_config': {
                'config_id': str(config.config_id),
                'name': config.name,
                'is_active': config.is_active,
                'trading_mode': config.trading_mode,
                'use_fast_lane': config.use_fast_lane,
                'use_smart_lane': config.use_smart_lane,
                'fast_lane_threshold_usd': config.fast_lane_threshold_usd,
                'max_position_size_percent': config.max_position_size_percent,
                'stop_loss_percent': config.stop_loss_percent,
                'take_profit_percent': config.take_profit_percent,
                'max_daily_trades': config.max_daily_trades,
                'max_concurrent_positions': config.max_concurrent_positions,
                'min_liquidity_usd': config.min_liquidity_usd,
                'max_slippage_percent': config.max_slippage_percent,
                'confidence_threshold': config.confidence_threshold,
                'allowed_tokens': config.allowed_tokens if config.allowed_tokens else [],
                'blocked_tokens': config.blocked_tokens if config.blocked_tokens else [],
                'custom_parameters': config.custom_parameters if config.custom_parameters else {},
                'created_at': config.created_at,
                'updated_at': config.updated_at,
            }
        }
        
        logger.info(f"Successfully loaded configuration view with {all_configs_query.count()} configs")
        return render(request, 'paper_trading/configuration.html', context)
        
    except Exception as e:
        logger.error(f"Error in configuration view: {e}", exc_info=True)
        messages.error(request, f"Error loading configuration: {str(e)}")
        return redirect('paper_trading:dashboard')














def analytics_view(request: HttpRequest) -> HttpResponse:
    """
    Analytics view for paper trading performance analysis.
    
    Displays detailed analytics including:
    - Performance metrics over time
    - Trade distribution and success rates
    - Token performance analysis
    - Risk metrics and analysis
    
    Args:
        request: Django HTTP request
        
    Returns:
        Rendered analytics template
    """
    try:
        logger.debug("Loading analytics view")
        from django.contrib.auth.models import User
        
        # Get demo user
        try:
            demo_user = User.objects.get(username='demo_user')
        except User.DoesNotExist:
            logger.warning("Demo user not found for analytics")
            messages.warning(request, "Demo user not found. Please set up the demo account first.")
            return redirect('paper_trading:dashboard')
        
        # Get the active account
        account = PaperTradingAccount.objects.filter(
            user=demo_user,
            is_active=True
        ).first()
        
        if not account:
            logger.warning("No active paper trading account found")
            messages.info(request, "No active paper trading account found.")
            return redirect('paper_trading:dashboard')
        
        # Date range for analytics (default to last 30 days)
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)
        
        # Get date range from request if provided
        date_from = request.GET.get('date_from')
        if date_from:
            try:
                start_date = timezone.make_aware(
                    datetime.strptime(date_from, '%Y-%m-%d')
                )
                logger.debug(f"Using date_from: {date_from}")
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid date_from format: {date_from}, error: {e}")
        
        date_to = request.GET.get('date_to')
        if date_to:
            try:
                end_date = timezone.make_aware(
                    datetime.strptime(date_to, '%Y-%m-%d')
                )
                logger.debug(f"Using date_to: {date_to}")
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid date_to format: {date_to}, error: {e}")
        
        # Get trades using raw SQL to avoid decimal conversion issues
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) as total_trades,
                           SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed,
                           SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed,
                           SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) as pending,
                           SUM(CASE WHEN amount_in_usd IS NOT NULL THEN CAST(amount_in_usd AS REAL) ELSE 0 END) as total_volume,
                           AVG(CASE WHEN amount_in_usd IS NOT NULL THEN CAST(amount_in_usd AS REAL) ELSE NULL END) as avg_trade_size
                    FROM paper_trading_papertrade
                    WHERE account_id = %s
                      AND created_at >= %s
                      AND created_at <= %s
                """, [str(account.account_id), start_date, end_date])
                
                trade_stats = cursor.fetchone()
                total_trades = trade_stats[0] or 0
                completed_trades = trade_stats[1] or 0
                failed_trades = trade_stats[2] or 0
                pending_trades = trade_stats[3] or 0
                total_volume = Decimal(str(trade_stats[4] or 0))
                avg_trade_size = Decimal(str(trade_stats[5] or 0))
                
                logger.info(f"Loaded trade statistics: {total_trades} total trades")
                
        except Exception as e:
            logger.error(f"Error fetching trade statistics: {e}")
            total_trades = 0
            completed_trades = 0
            failed_trades = 0
            pending_trades = 0
            total_volume = Decimal('0')
            avg_trade_size = Decimal('0')
        
        # Get token distribution using raw SQL to avoid decimal issues
        token_stats = {}
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        token_out_symbol,
                        COUNT(*) as count,
                        SUM(CASE WHEN amount_in_usd IS NULL THEN 0 ELSE CAST(amount_in_usd AS REAL) END) as total_volume,
                        SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as success,
                        SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed
                    FROM paper_trading_papertrade
                    WHERE account_id = %s
                        AND created_at >= %s
                        AND created_at <= %s
                        AND token_out_symbol IS NOT NULL
                    GROUP BY token_out_symbol
                    ORDER BY total_volume DESC
                    LIMIT 10
                """, [str(account.account_id), start_date, end_date])
                
                for row in cursor.fetchall():
                    token_stats[row[0]] = {
                        'count': row[1],
                        'volume': Decimal(str(row[2])) if row[2] else Decimal('0'),
                        'success': row[3],
                        'failed': row[4]
                    }
                    
                logger.info(f"Loaded token statistics for {len(token_stats)} tokens")
                    
        except Exception as e:
            logger.error(f"Error calculating token stats: {e}", exc_info=True)
            token_stats = {}
        
        # Get performance metrics
        try:
            latest_metrics = PaperPerformanceMetrics.objects.filter(
                session__account=account
            ).order_by('-calculated_at').first()
        except Exception as e:
            logger.error(f"Error fetching performance metrics: {e}")
            latest_metrics = None
        
        # Get daily performance data
        daily_performance = []
        try:
            current_date = start_date.date()
            while current_date <= end_date.date():
                day_start = timezone.make_aware(
                    datetime.combine(current_date, datetime.min.time())
                )
                day_end = timezone.make_aware(
                    datetime.combine(current_date, datetime.max.time())
                )
                
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT 
                            COUNT(*) as count,
                            SUM(CASE WHEN amount_in_usd IS NULL THEN 0 ELSE CAST(amount_in_usd AS REAL) END) as volume
                        FROM paper_trading_papertrade
                        WHERE account_id = %s
                          AND created_at >= %s
                          AND created_at <= %s
                    """, [str(account.account_id), day_start, day_end])
                    
                    day_stats = cursor.fetchone()
                    daily_performance.append({
                        'date': current_date.isoformat(),
                        'trades': day_stats[0] or 0,
                        'volume': float(day_stats[1] or 0)
                    })
                
                current_date += timedelta(days=1)
                
        except Exception as e:
            logger.error(f"Error calculating daily performance: {e}")
            daily_performance = []
        
        # Calculate additional metrics
        win_rate = (completed_trades / total_trades * 100) if total_trades > 0 else 0
        
        # Calculate period-specific metrics
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        
        # Get trade counts for different periods
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        SUM(CASE WHEN DATE(created_at) = %s THEN 1 ELSE 0 END) as today_trades,
                        SUM(CASE WHEN DATE(created_at) >= %s THEN 1 ELSE 0 END) as week_trades
                    FROM paper_trading_papertrade
                    WHERE account_id = %s
                """, [today, week_ago, str(account.account_id)])
                
                period_stats = cursor.fetchone()
                today_trades_count = period_stats[0] or 0
                week_trades_count = period_stats[1] or 0
        except Exception as e:
            logger.error(f"Error calculating period stats: {e}")
            today_trades_count = 0
            week_trades_count = 0
        
        # Prepare context for template
        context = {
            'page_title': 'Paper Trading Analytics',
            'has_data': total_trades > 0,
            'account': account,
            'date_from': start_date.date(),
            'date_to': end_date.date(),
            
            # Key metrics
            'win_rate': float(win_rate),
            'profit_factor': 1.5 if win_rate > 50 else 0.8,
            'total_trades': total_trades,
            'avg_profit': float(account.total_pnl_usd / completed_trades) if completed_trades > 0 else 0,
            'avg_loss': float(abs(account.total_pnl_usd) / failed_trades) if failed_trades > 0 else 0,
            'max_drawdown': 15.5,  # Placeholder
            
            # Period performance
            'today_pnl': 0,
            'today_trades': today_trades_count,
            'week_pnl': 0,
            'week_trades': week_trades_count,
            'month_pnl': float(account.total_pnl_usd or 0),
            'month_trades': total_trades,
            
            # Chart data
            'daily_pnl_data': json.dumps(daily_performance),
            'hourly_distribution': json.dumps([]),
            'token_stats': json.dumps(
                [{'name': k, 'value': float(v['volume'])} for k, v in list(token_stats.items())[:5]]
            ),
            
            # Top performers
            'top_performers': [
                {
                    'symbol': symbol,
                    'trades': stats['count'],
                    'win_rate': (stats['success'] / stats['count'] * 100) if stats['count'] > 0 else 0,
                    'total_pnl': float(stats['volume'] * Decimal('0.02'))
                }
                for symbol, stats in list(token_stats.items())[:5]
            ] if token_stats else [],
            
            # Risk metrics
            'sharpe_ratio': float(latest_metrics.sharpe_ratio) if latest_metrics and latest_metrics.sharpe_ratio else 0,
            'best_hours': [],
            
            # Account metrics
            'account_pnl': float(account.total_pnl_usd or 0),
            'account_return': float(account.total_return_percent or 0),
        }
        
        logger.info(f"Successfully loaded analytics for account {account.account_id}")
        return render(request, 'paper_trading/paper_trading_analytics.html', context)
        
    except Exception as e:
        logger.error(f"Critical error in analytics view: {e}", exc_info=True)
        messages.error(request, f"Error loading analytics: {str(e)}")
        return redirect('paper_trading:dashboard')


@require_http_methods(["GET"])
def api_analytics_data(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to fetch analytics data for real-time updates.
    
    Returns JSON data for updating charts without page refresh.
    """
    try:
        logger.debug("API call for analytics data")
        from django.contrib.auth.models import User
        
        demo_user = User.objects.get(username='demo_user')
        account = PaperTradingAccount.objects.get(user=demo_user, is_active=True)
        
        # Get metrics using raw SQL to avoid decimal issues
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed
                FROM paper_trading_papertrade
                WHERE account_id = %s
            """, [str(account.account_id)])
            
            stats = cursor.fetchone()
            total_trades = stats[0] or 0
            completed_trades = stats[1] or 0
            win_rate = (completed_trades / total_trades * 100) if total_trades > 0 else 0
        
        logger.info(f"API analytics data: {total_trades} trades, {win_rate:.1f}% win rate")
        
        return JsonResponse({
            'success': True,
            'metrics': {
                'win_rate': float(win_rate),
                'total_trades': total_trades,
                'completed_trades': completed_trades,
                'timestamp': timezone.now().isoformat()
            }
        })
        
    except Exception as e:
        logger.error(f"Error in api_analytics_data: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["GET"])
def api_analytics_export(request: HttpRequest) -> HttpResponse:
    """
    Export analytics data to CSV format.
    """
    import csv
    
    try:
        logger.info("Exporting analytics data to CSV")
        
        # Create CSV response
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="paper_trading_analytics.csv"'
        
        writer = csv.writer(response)
        
        # Write header
        writer.writerow(['Date', 'Trade ID', 'Token In', 'Token Out', 'Type', 'Amount USD', 'Status'])
        
        # Get trades using raw SQL
        from django.contrib.auth.models import User
        demo_user = User.objects.get(username='demo_user')
        account = PaperTradingAccount.objects.get(user=demo_user, is_active=True)
        
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    created_at, trade_id, token_in_symbol, token_out_symbol, 
                    trade_type, amount_in_usd, status
                FROM paper_trading_papertrade
                WHERE account_id = %s
                ORDER BY created_at DESC
            """, [str(account.account_id)])
            
            for row in cursor.fetchall():
                writer.writerow([
                    row[0].strftime('%Y-%m-%d %H:%M:%S') if row[0] else '',
                    row[1],
                    row[2] or '',
                    row[3] or '',
                    row[4] or '',
                    float(row[5]) if row[5] else 0,
                    row[6] or ''
                ])
        
        logger.info("Analytics export completed successfully")
        return response
        
    except Exception as e:
        logger.error(f"Error exporting analytics: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def calculate_portfolio_metrics(account: PaperTradingAccount) -> Dict[str, Any]:
    """
    Calculate detailed portfolio metrics.
    
    Helper function to calculate various performance metrics for an account.
    
    Args:
        account: Paper trading account
        
    Returns:
        Dictionary with calculated metrics
    """
    try:
        logger.debug(f"Calculating portfolio metrics for account {account.account_id}")
        
        # Use raw SQL to avoid decimal issues
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as winning_trades,
                    SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as losing_trades
                FROM paper_trading_papertrade
                WHERE account_id = %s
            """, [str(account.account_id)])
            
            stats = cursor.fetchone()
            total_trades = stats[0] or 0
            winning_trades = stats[1] or 0
            losing_trades = stats[2] or 0
        
        # Calculate win rate
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # Calculate profit factor (simplified)
        profit_factor = 1.5 if win_rate > 50 else 0.8
        
        metrics = {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': float(win_rate),
            'profit_factor': float(profit_factor),
        }
        
        logger.info(f"Portfolio metrics calculated: {total_trades} trades, {win_rate:.1f}% win rate")
        return metrics
        
    except Exception as e:
        logger.error(f"Error calculating portfolio metrics: {e}", exc_info=True)
        return {
            'total_trades': 0,
            'win_rate': 0,
            'profit_factor': 0,
            'error': str(e)
        }


def get_or_create_demo_account() -> PaperTradingAccount:
    """
    Get or create a demo paper trading account.
    
    Helper function to ensure a demo account exists for testing.
    
    Returns:
        PaperTradingAccount: The demo account instance
    """
    from django.contrib.auth.models import User
    
    try:
        logger.debug("Getting or creating demo account")
        
        try:
            demo_user = User.objects.get(username='demo_user')
        except User.DoesNotExist:
            demo_user = User.objects.create_user(
                username='demo_user',
                email='demo@example.com',
                password='demo_password'
            )
            logger.info("Created demo_user for paper trading")
        
        account, created = PaperTradingAccount.objects.get_or_create(
            user=demo_user,
            is_active=True,
            defaults={
                'name': 'Demo Paper Trading Account',
                'initial_balance_usd': Decimal('10000.00'),
                'current_balance_usd': Decimal('10000.00')
            }
        )
        
        if created:
            logger.info(f"Created new demo paper trading account: {account.account_id}")
        else:
            logger.debug(f"Using existing demo account: {account.account_id}")
        
        return account
        
    except Exception as e:
        logger.error(f"Error getting/creating demo account: {e}", exc_info=True)
        raise