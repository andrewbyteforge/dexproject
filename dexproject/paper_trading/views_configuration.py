"""
Paper Trading Views - Configuration Management - ENHANCED WITH PHASE 7B STRATEGIES

Strategy configuration management view with pagination, CRUD operations,
and configuration activation. Handles trading strategy settings.

ENHANCED: 
- Detailed "from X to Y" logging for every configuration change
- Phase 7B: Support for DCA, Grid, TWAP, VWAP strategy preferences

File: dexproject/paper_trading/views_configuration.py
"""

import logging
from decimal import Decimal
from typing import Dict, Any, Optional
import requests
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
from .utils import get_single_trading_account

logger = logging.getLogger(__name__)


# =============================================================================
# LOGGING HELPERS
# =============================================================================

def log_configuration_changes(old_config: Optional[PaperStrategyConfiguration], new_data: Dict[str, Any], config_name: str) -> None:
    """
    Log detailed configuration changes showing "from X to Y" for each field.

    This logging will appear in the Django server logs (IDE console/terminal).

    Args:
        old_config: Previous configuration (None if creating new)
        new_data: New configuration data being saved
        config_name: Name of the configuration being saved
    """
    logger.info("=" * 80)
    logger.info(f"📝 CONFIGURATION CHANGE: {config_name}")
    logger.info("=" * 80)

    if not old_config:
        logger.info("🆕 Creating NEW configuration")
        logger.info("")
        logger.info("Configuration Settings:")
        log_new_configuration_values(new_data)
    else:
        logger.info(f"🔄 Updating EXISTING configuration (ID: {old_config.config_id})")
        logger.info("")
        logger.info("Changes:")
        log_configuration_differences(old_config, new_data)

    logger.info("=" * 80)


def log_new_configuration_values(config_data: Dict[str, Any]) -> None:
    """Log all values for a new configuration."""
    logger.info(f"  📝 Name: {config_data.get('name', 'N/A')}")
    logger.info(f"  🎯 Trading Mode: {config_data.get('trading_mode', 'N/A')}")
    logger.info(f"  ⚡ Fast Lane: {'✓ ENABLED' if config_data.get('use_fast_lane') else '✗ DISABLED'}")
    logger.info(f"  🧠 Smart Lane: {'✓ ENABLED' if config_data.get('use_smart_lane') else '✗ DISABLED'}")
    logger.info(f"  💵 Fast Lane Threshold: ${config_data.get('fast_lane_threshold_usd', 'N/A')}")
    logger.info(f"  💰 Max Position Size: {config_data.get('max_position_size_percent', 'N/A')}%")
    logger.info(f"  🛡️ Stop Loss: {config_data.get('stop_loss_percent', 'N/A')}%")
    logger.info(f"  🎯 Take Profit: {config_data.get('take_profit_percent', 'N/A')}%")
    logger.info(f"  ⏰ Max Hold Hours: {config_data.get('max_hold_hours', 'N/A')} hours")
    logger.info(f"  📊 Max Daily Trades: {config_data.get('max_daily_trades', 'N/A')}")
    logger.info(f"  📈 Max Concurrent Positions: {config_data.get('max_concurrent_positions', 'N/A')}")
    logger.info(f"  💧 Min Liquidity: ${config_data.get('min_liquidity_usd', 'N/A')}")
    logger.info(f"  📉 Max Slippage: {config_data.get('max_slippage_percent', 'N/A')}%")
    logger.info(f"  🎲 Confidence Threshold: {config_data.get('confidence_threshold', 'N/A')}%")
    # Phase 7B: Advanced Strategies
    logger.info(f"  💰 DCA Strategy: {'✓ ENABLED' if config_data.get('enable_dca') else '✗ DISABLED'}")
    if config_data.get('enable_dca'):
        logger.info(f"     └─ Intervals: {config_data.get('dca_num_intervals', 'N/A')}")
        logger.info(f"     └─ Interval Hours: {config_data.get('dca_interval_hours', 'N/A')}")
    logger.info(f"  📊 Grid Strategy: {'✓ ENABLED' if config_data.get('enable_grid') else '✗ DISABLED'}")
    if config_data.get('enable_grid'):
        logger.info(f"     └─ Levels: {config_data.get('grid_num_levels', 'N/A')}")
        logger.info(f"     └─ Profit Target: {config_data.get('grid_profit_target_percent', 'N/A')}%")
    logger.info(f"  ⏰ TWAP Strategy: {'✓ ENABLED' if config_data.get('enable_twap') else '✗ DISABLED'}")
    logger.info(f"  📈 VWAP Strategy: {'✓ ENABLED' if config_data.get('enable_vwap') else '✗ DISABLED'}")


def log_configuration_differences(old_config: PaperStrategyConfiguration, new_data: Dict[str, Any]) -> None:
    """
    Log differences between old and new configuration with "from X to Y" format.

    This is the key function that shows what changed in the IDE console.
    """
    changes_detected = False

    # Configuration Name
    if old_config.name != new_data.get('name'):
        logger.info(f"  📝 Name: '{old_config.name}' → '{new_data.get('name')}'")
        changes_detected = True

    # Trading Mode
    if old_config.trading_mode != new_data.get('trading_mode'):
        logger.info(f"  🎯 Trading Mode: {old_config.trading_mode} → {new_data.get('trading_mode')}")
        changes_detected = True

    # Fast Lane
    old_fast_lane = '✓ ENABLED' if old_config.use_fast_lane else '✗ DISABLED'
    new_fast_lane = '✓ ENABLED' if new_data.get('use_fast_lane') else '✗ DISABLED'
    if old_config.use_fast_lane != new_data.get('use_fast_lane'):
        logger.info(f"  ⚡ Fast Lane: {old_fast_lane} → {new_fast_lane}")
        changes_detected = True

    # Smart Lane
    old_smart_lane = '✓ ENABLED' if old_config.use_smart_lane else '✗ DISABLED'
    new_smart_lane = '✓ ENABLED' if new_data.get('use_smart_lane') else '✗ DISABLED'
    if old_config.use_smart_lane != new_data.get('use_smart_lane'):
        logger.info(f"  🧠 Smart Lane: {old_smart_lane} → {new_smart_lane}")
        changes_detected = True

    # Fast Lane Threshold
    if old_config.fast_lane_threshold_usd != new_data.get('fast_lane_threshold_usd'):
        logger.info(f"  💵 Fast Lane Threshold: ${old_config.fast_lane_threshold_usd} → ${new_data.get('fast_lane_threshold_usd')}")
        changes_detected = True

    # Max Position Size
    if old_config.max_position_size_percent != new_data.get('max_position_size_percent'):
        logger.info(f"  💰 Max Position Size: {old_config.max_position_size_percent}% → {new_data.get('max_position_size_percent')}%")
        changes_detected = True

    # Stop Loss
    if old_config.stop_loss_percent != new_data.get('stop_loss_percent'):
        logger.info(f"  🛡️ Stop Loss: {old_config.stop_loss_percent}% → {new_data.get('stop_loss_percent')}%")
        changes_detected = True

    # Take Profit
    if old_config.take_profit_percent != new_data.get('take_profit_percent'):
        logger.info(f"  🎯 Take Profit: {old_config.take_profit_percent}% → {new_data.get('take_profit_percent')}%")
        changes_detected = True
    
    # Max Hold Hours
    if old_config.max_hold_hours != new_data.get('max_hold_hours'):
        logger.info(f"  ⏰ Max Hold Hours: {old_config.max_hold_hours} hours → {new_data.get('max_hold_hours')} hours")
        changes_detected = True

    # Max Daily Trades
    if old_config.max_daily_trades != new_data.get('max_daily_trades'):
        logger.info(f"  📊 Max Daily Trades: {old_config.max_daily_trades} → {new_data.get('max_daily_trades')}")
        changes_detected = True

    # Max Concurrent Positions
    if old_config.max_concurrent_positions != new_data.get('max_concurrent_positions'):
        logger.info(f"  📈 Max Concurrent Positions: {old_config.max_concurrent_positions} → {new_data.get('max_concurrent_positions')}")
        changes_detected = True

    # Min Liquidity
    if old_config.min_liquidity_usd != new_data.get('min_liquidity_usd'):
        logger.info(f"  💧 Min Liquidity: ${old_config.min_liquidity_usd} → ${new_data.get('min_liquidity_usd')}")
        changes_detected = True

    # Max Slippage
    if old_config.max_slippage_percent != new_data.get('max_slippage_percent'):
        logger.info(f"  📉 Max Slippage: {old_config.max_slippage_percent}% → {new_data.get('max_slippage_percent')}%")
        changes_detected = True

    # Confidence Threshold
    if old_config.confidence_threshold != new_data.get('confidence_threshold'):
        logger.info(f"  🎲 Confidence Threshold: {old_config.confidence_threshold}% → {new_data.get('confidence_threshold')}%")
        changes_detected = True

    # Phase 7B: Advanced Strategies
    # DCA Strategy
    old_dca = '✓ ENABLED' if old_config.enable_dca else '✗ DISABLED'
    new_dca = '✓ ENABLED' if new_data.get('enable_dca') else '✗ DISABLED'
    if old_config.enable_dca != new_data.get('enable_dca'):
        logger.info(f"  💰 DCA Strategy: {old_dca} → {new_dca}")
        changes_detected = True
    
    if old_config.dca_num_intervals != new_data.get('dca_num_intervals'):
        logger.info(f"     └─ DCA Intervals: {old_config.dca_num_intervals} → {new_data.get('dca_num_intervals')}")
        changes_detected = True
    
    if old_config.dca_interval_hours != new_data.get('dca_interval_hours'):
        logger.info(f"     └─ DCA Interval Hours: {old_config.dca_interval_hours} → {new_data.get('dca_interval_hours')}")
        changes_detected = True
    
    # Grid Strategy
    old_grid = '✓ ENABLED' if old_config.enable_grid else '✗ DISABLED'
    new_grid = '✓ ENABLED' if new_data.get('enable_grid') else '✗ DISABLED'
    if old_config.enable_grid != new_data.get('enable_grid'):
        logger.info(f"  📊 Grid Strategy: {old_grid} → {new_grid}")
        changes_detected = True
    
    if old_config.grid_num_levels != new_data.get('grid_num_levels'):
        logger.info(f"     └─ Grid Levels: {old_config.grid_num_levels} → {new_data.get('grid_num_levels')}")
        changes_detected = True
    
    if old_config.grid_profit_target_percent != new_data.get('grid_profit_target_percent'):
        logger.info(f"     └─ Grid Profit Target: {old_config.grid_profit_target_percent}% → {new_data.get('grid_profit_target_percent')}%")
        changes_detected = True
    
    # TWAP Strategy
    old_twap = '✓ ENABLED' if old_config.enable_twap else '✗ DISABLED'
    new_twap = '✓ ENABLED' if new_data.get('enable_twap') else '✗ DISABLED'
    if old_config.enable_twap != new_data.get('enable_twap'):
        logger.info(f"  ⏰ TWAP Strategy: {old_twap} → {new_twap}")
        changes_detected = True
    
    # VWAP Strategy
    old_vwap = '✓ ENABLED' if old_config.enable_vwap else '✗ DISABLED'
    new_vwap = '✓ ENABLED' if new_data.get('enable_vwap') else '✗ DISABLED'
    if old_config.enable_vwap != new_data.get('enable_vwap'):
        logger.info(f"  📈 VWAP Strategy: {old_vwap} → {new_vwap}")
        changes_detected = True

    if not changes_detected:
        logger.info("  ℹ️  No changes detected - all values remain the same")


# =============================================================================
# MAIN VIEW
# =============================================================================

@require_http_methods(["GET", "POST"])
def configuration_view(request: HttpRequest) -> HttpResponse:
    """
    Strategy configuration management view with pagination and delete.

    ENHANCED: 
    - Detailed logging of all configuration changes
    - Phase 7B: Support for DCA, Grid, TWAP, VWAP strategy preferences

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
                    
                    # Only prevent deletion of the last configuration
                    total_configs = PaperStrategyConfiguration.objects.filter(account=account).count()
                    
                    if total_configs <= 1:
                        messages.warning(request, "Cannot delete the last configuration")
                    else:
                        config_name = config_to_delete.name
                        was_active = config_to_delete.is_active
                        
                        # Delete the configuration
                        config_to_delete.delete()
                        
                        # If we deleted the active config, activate another one
                        if was_active:
                            # Get any remaining config and make it active
                            replacement_config = PaperStrategyConfiguration.objects.filter(
                                account=account
                            ).first()
                            
                            if replacement_config:
                                replacement_config.is_active = True
                                replacement_config.save()
                                messages.success(
                                    request, 
                                    f'Configuration "{config_name}" deleted. '
                                    f'"{replacement_config.name}" is now selected.'
                                )
                                logger.info(
                                    f"🗑️  Deleted SELECTED configuration {config_id} ({config_name}). "
                                    f"Auto-selected {replacement_config.name} as replacement."
                                )
                            else:
                                messages.success(request, f'Configuration "{config_name}" deleted successfully')
                                logger.info(f"🗑️  Deleted configuration {config_id} ({config_name})")
                        else:
                            messages.success(request, f'Configuration "{config_name}" deleted successfully')
                            logger.info(f"🗑️  Deleted configuration {config_id} ({config_name})")
                            
                except PaperStrategyConfiguration.DoesNotExist:
                    messages.error(request, "Configuration not found")
                    return redirect('paper_trading:configuration')
                except Exception as e:
                    messages.error(request, f"Error loading configuration: {str(e)}")
                    logger.error(f"Error loading configuration: {e}", exc_info=True)
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
                logger.info(f"✅ Loaded and activated configuration {config_id} ({config_to_load.name}) for account {account.account_id}")
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
                    'name': request.POST.get('name', 'Default Configuration'),
                    'trading_mode': request.POST.get('trading_mode', 'MODERATE'),
                    'use_fast_lane': request.POST.get('use_fast_lane') == 'on',
                    'use_smart_lane': request.POST.get('use_smart_lane') == 'on',
                    'fast_lane_threshold_usd': Decimal(request.POST.get('fast_lane_threshold_usd', '100')),
                    'max_position_size_percent': Decimal(request.POST.get('max_position_size_percent', '10')),
                    'max_trade_size_usd': Decimal(request.POST.get('max_trade_size_usd', '1000')),
                    # 'max_position_size_per_token_percent': Decimal(request.POST.get('max_position_size_per_token_percent', '15')),
                    'stop_loss_percent': Decimal(request.POST.get('stop_loss_percent', '5')),
                    'take_profit_percent': Decimal(request.POST.get('take_profit_percent', '15')),
                    'max_hold_hours': int(request.POST.get('max_hold_hours', '72')),
                    'max_daily_trades': int(request.POST.get('max_daily_trades', '50')),
                    'max_concurrent_positions': int(request.POST.get('max_concurrent_positions', '10')),
                    'min_liquidity_usd': Decimal(request.POST.get('min_liquidity_usd', '1000')),
                    'max_slippage_percent': Decimal(request.POST.get('max_slippage_percent', '3')),
                    'confidence_threshold': Decimal(request.POST.get('confidence_threshold', '70')),
                    # Phase 7B: Advanced Strategies
                    'enable_dca': request.POST.get('enable_dca') == 'on',
                    'enable_grid': request.POST.get('enable_grid') == 'on',
                    'enable_twap': request.POST.get('enable_twap') == 'on',
                    'enable_vwap': request.POST.get('enable_vwap') == 'on',
                    'dca_num_intervals': int(request.POST.get('dca_num_intervals', '5')),
                    'dca_interval_hours': int(request.POST.get('dca_interval_hours', '2')),
                    'grid_num_levels': int(request.POST.get('grid_num_levels', '7')),
                    'grid_profit_target_percent': Decimal(request.POST.get('grid_profit_target_percent', '2.0')),
                }

                # Determine action: create new or update existing
                if save_as_new or not update_config_id:
                    # Create new configuration
                    # 🔍 LOG: Creating new configuration
                    log_configuration_changes(None, config_data, config_data['name'])

                    update_target, created = PaperStrategyConfiguration.objects.update_or_create(
                        account=account,
                        name=config_data['name'],
                        defaults={
                            'trading_mode': config_data['trading_mode'],
                            'use_fast_lane': config_data['use_fast_lane'],
                            'use_smart_lane': config_data['use_smart_lane'],
                            'fast_lane_threshold_usd': config_data['fast_lane_threshold_usd'],
                            'max_position_size_percent': config_data['max_position_size_percent'],
                            'max_trade_size_usd': config_data['max_trade_size_usd'],
                            # 'max_position_size_per_token_percent': config_data['max_position_size_per_token_percent'],
                            'stop_loss_percent': config_data['stop_loss_percent'],
                            'take_profit_percent': config_data['take_profit_percent'],
                            'max_hold_hours': config_data['max_hold_hours'],
                            'max_daily_trades': config_data['max_daily_trades'],
                            'max_concurrent_positions': config_data['max_concurrent_positions'],
                            'min_liquidity_usd': config_data['min_liquidity_usd'],
                            'max_slippage_percent': config_data['max_slippage_percent'],
                            'confidence_threshold': config_data['confidence_threshold'],
                            # Phase 7B: Advanced Strategies
                            'enable_dca': config_data['enable_dca'],
                            'enable_grid': config_data['enable_grid'],
                            'enable_twap': config_data['enable_twap'],
                            'enable_vwap': config_data['enable_vwap'],
                            'dca_num_intervals': config_data['dca_num_intervals'],
                            'dca_interval_hours': config_data['dca_interval_hours'],
                            'grid_num_levels': config_data['grid_num_levels'],
                            'grid_profit_target_percent': config_data['grid_profit_target_percent'],
                            'is_active': True,
                        }
                    )

                    # Log what happened
                    if created:
                        logger.info(f"✅ Created new configuration: {config_data['name']}")
                    else:
                        logger.info(f"✅ Updated existing configuration: {config_data['name']}")
                    action_word = "created"
                    logger.info(f"✅ Created configuration {update_target.config_id} for account {account.account_id}")
                else:
                    # Update existing configuration
                    update_target = PaperStrategyConfiguration.objects.get(
                        config_id=update_config_id,
                        account=account
                    )

                    # 🔍 LOG: Show what changed from old to new
                    log_configuration_changes(update_target, config_data, config_data['name'])

                    # Apply updates
                    for key, value in config_data.items():
                        setattr(update_target, key, value)
                    update_target.save()
                    action_word = "updated"
                    logger.info(f"✅ Updated configuration {update_target.config_id} for account {account.account_id}")

                messages.success(request, f'Configuration "{config_data["name"]}" {action_word} successfully')

                return redirect('paper_trading:configuration')

            except Exception as e:
                messages.error(request, f'Error saving configuration: {str(e)}')
                logger.error(f"❌ Configuration save error: {e}", exc_info=True)

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
                default_config_data = {
                    'account': account,
                    'name': 'Default Strategy',
                    'trading_mode': 'MODERATE',
                    'use_fast_lane': True,
                    'use_smart_lane': False,
                    'fast_lane_threshold_usd': Decimal('100'),
                    'max_position_size_percent': Decimal('10'),
                    'stop_loss_percent': Decimal('5'),
                    'take_profit_percent': Decimal('15'),
                    'max_hold_hours': 72,
                    'max_daily_trades': 50,
                    'max_concurrent_positions': 10,
                    'min_liquidity_usd': Decimal('1000'),
                    'max_slippage_percent': Decimal('3'),
                    'confidence_threshold': Decimal('70'),
                    # Phase 7B: Advanced Strategies defaults
                    'enable_dca': False,
                    'enable_grid': False,
                    'enable_twap': False,
                    'enable_vwap': False,
                    'dca_num_intervals': 5,
                    'dca_interval_hours': 2,
                    'grid_num_levels': 7,
                    'grid_profit_target_percent': Decimal('2.0'),
                    'is_active': True
                }
                config = PaperStrategyConfiguration.objects.create(**default_config_data)
                logger.info(f"Created default configuration for account {account.account_id}")

        # Get all configurations for this account with pagination
        all_configs = PaperStrategyConfiguration.objects.filter(
            account=account
        ).order_by('-updated_at')

        paginator = Paginator(all_configs, 10)  # 10 configs per page
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        # Get bot status (check if any session is running)
        # Get ALL active sessions
        active_sessions = PaperTradingSession.objects.filter(
            account=account,
            status__in=["RUNNING", "STARTING", "PAUSED"]
        ).select_related('strategy_config')

        active_session = active_sessions.first() if active_sessions else None

        # Calculate duration and P&L for each session
        for session in active_sessions:
            pass

        bot_running = active_session is not None

        context = {
            'strategy_config': config,
            'all_configs': page_obj,
            'total_configs': all_configs.count(),
            'account': account,
            'bot_running': bot_running,
            'active_session': active_session,
            'active_sessions': active_sessions,
            'page_obj': page_obj,
        }

        logger.info(f"✅ Successfully loaded configuration view with {all_configs.count()} configs")
        return render(request, 'paper_trading/configuration.html', context)

    except Exception as e:
        logger.error(f"❌ Error in configuration view: {e}", exc_info=True)
        messages.error(request, f"Error loading configuration page: {str(e)}")
        return redirect('paper_trading:dashboard')