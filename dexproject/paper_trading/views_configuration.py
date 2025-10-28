"""
Paper Trading Views - Configuration Management

Strategy configuration management view with pagination, CRUD operations,
and configuration activation. Handles trading strategy settings.

File: dexproject/paper_trading/views_configuration.py
"""

import logging
from decimal import Decimal
from typing import Dict, Any

from django.shortcuts import render, redirect
from django.http import HttpRequest, HttpResponse
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator

from .models import (
    PaperTradingAccount,
    PaperStrategyConfiguration,
    PaperTradingSession
)
from .utils import get_single_trading_account, to_decimal

logger = logging.getLogger(__name__)


@require_http_methods(["GET", "POST"])
def configuration_view(request: HttpRequest) -> HttpResponse:
    """
    Strategy configuration management view with pagination and delete.
    
    Handles display, updates, and deletion of trading strategy configurations.
    Supports configuration activation, deactivation, and CRUD operations.
    
    Args:
        request: Django HTTP request
        
    Returns:
        Rendered configuration template or redirect after action
    """
    try:
        # Get the single account
        account: PaperTradingAccount = get_single_trading_account()
        user = account.user
        
        logger.debug(f"Loading configuration view for account {account.account_id}")
        
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
        
        # Handle POST request - configuration save/update
        if request.method == 'POST' and request.POST.get('action') != 'delete':
            try:
                # Determine if this is a new config or update
                update_config_id = request.POST.get('update_config_id')
                save_as_new = request.POST.get('save_as_new') == 'true'
                
                # Prepare configuration data from POST
                config_data = {
                    'name': request.POST.get('config_name', 'Default Configuration'),
                    'trading_mode': request.POST.get('trading_mode', 'MODERATE'),
                    'use_fast_lane': request.POST.get('use_fast_lane') == 'on',
                    'use_smart_lane': request.POST.get('use_smart_lane') == 'on',
                    'fast_lane_threshold_usd': Decimal(request.POST.get('fast_lane_threshold_usd', '100')),
                    'max_position_size_percent': Decimal(request.POST.get('max_position_size_percent', '10')),
                    'stop_loss_percent': Decimal(request.POST.get('stop_loss_percent', '5')),
                    'take_profit_percent': Decimal(request.POST.get('take_profit_percent', '15')),
                    'max_daily_trades': int(request.POST.get('max_daily_trades', '50')),
                    'max_concurrent_positions': int(request.POST.get('max_concurrent_positions', '10')),
                    'min_liquidity_usd': Decimal(request.POST.get('min_liquidity_usd', '1000')),
                    'max_slippage_percent': Decimal(request.POST.get('max_slippage_percent', '3')),
                    'confidence_threshold': Decimal(request.POST.get('confidence_threshold', '70')),
                }
                
                # Determine action: create new or update existing
                if save_as_new or not update_config_id:
                    # Create new configuration
                    update_target = PaperStrategyConfiguration.objects.create(
                        account=account,
                        **config_data
                    )
                    action_word = "created"
                else:
                    # Update existing configuration
                    update_target = PaperStrategyConfiguration.objects.get(
                        config_id=update_config_id,
                        account=account
                    )
                    for key, value in config_data.items():
                        setattr(update_target, key, value)
                    update_target.save()
                    action_word = "updated"
                
                messages.success(request, f'Configuration "{config_data["name"]}" {action_word} successfully')
                logger.info(f"{action_word.capitalize()} configuration {update_target.config_id} for account {account.account_id}")
                
                return redirect('paper_trading:configuration')
                
            except Exception as e:
                messages.error(request, f'Error saving configuration: {str(e)}')
                logger.error(f"Configuration save error: {e}", exc_info=True)
        
        # Get active/default configuration
        config = PaperStrategyConfiguration.objects.filter(
            account=account,
            is_active=True
        ).first()
        
        # If no active config, get any config or create a default one
        if not config:
            config = PaperStrategyConfiguration.objects.filter(account=account).first()
            if not config:
                # Create default configuration
                config = PaperStrategyConfiguration.objects.create(
                    account=account,
                    name="Default Configuration",
                    is_active=True
                )
                logger.info(f"Created default configuration for account {account.account_id}")
        
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
            status__in=["RUNNING", "STARTING", "PAUSED"]
        ).first()
        
        # Load available strategies
        available_strategies = [
            {'name': 'smart_lane', 'display': 'Smart Lane Strategy'},
            {'name': 'momentum', 'display': 'Momentum Trading'},
            {'name': 'mean_reversion', 'display': 'Mean Reversion'},
            {'name': 'arbitrage', 'display': 'Arbitrage Bot'},
        ]
        
        # Prepare context with safe decimal values
        context = {
            'page_title': 'Strategy Configuration',
            'account': account,
            'config': config,
            'available_strategies': available_strategies,
            'all_configs': all_configs,
            'active_session': active_session,
            'total_configs': all_configs_query.count(),
            'user': user,
            
            # Map actual model fields to template variables with safe decimals
            'strategy_config': {
                'config_id': str(config.config_id),
                'name': config.name,
                'is_active': config.is_active,
                'trading_mode': config.trading_mode,
                'use_fast_lane': config.use_fast_lane,
                'use_smart_lane': config.use_smart_lane,
                'fast_lane_threshold_usd': to_decimal(config.fast_lane_threshold_usd),
                'max_position_size_percent': to_decimal(config.max_position_size_percent),
                'stop_loss_percent': to_decimal(config.stop_loss_percent),
                'take_profit_percent': to_decimal(config.take_profit_percent),
                'max_daily_trades': config.max_daily_trades,
                'max_concurrent_positions': config.max_concurrent_positions,
                'min_liquidity_usd': to_decimal(config.min_liquidity_usd),
                'max_slippage_percent': to_decimal(config.max_slippage_percent),
                'confidence_threshold': to_decimal(config.confidence_threshold),
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