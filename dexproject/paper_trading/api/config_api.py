"""
Paper Trading Configuration API

This module handles strategy configuration management including
GET (retrieve config) and POST (update config) operations.

File: paper_trading/api/config_api.py
"""

import json
import logging
from decimal import Decimal
from typing import Dict, Any

from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

# Import models
from ..models import (
    PaperTradingAccount,
    PaperStrategyConfiguration,
)

# Import constants for field names
from ..constants import (
    ConfigAPIFields,
    StrategyConfigFields,
    TradingMode,
    validate_trading_mode,
)

# Import utilities
from ..utils import get_default_user, get_single_trading_account

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION LOGGING HELPER
# =============================================================================

def log_configuration_changes(
    before_config: Dict[str, Any],
    after_config: Dict[str, Any],
    config_name: str
) -> None:
    """
    Log configuration changes with before/after comparison.
    Only logs fields that actually changed.
    
    Args:
        before_config: Original configuration values
        after_config: New configuration values
        config_name: Name of the configuration
    """
    logger.info("=" * 70)
    logger.info(f"📊 Configuration Saved: '{config_name}'")
    logger.info("=" * 70)
    
    # Define all fields to track with their display names and formatting
    fields_to_track = {
        'trading_mode': ('Trading Mode', ''),
        'use_fast_lane': ('Fast Lane', ''),
        'use_smart_lane': ('Smart Lane', ''),
        'max_position_size_percent': ('Max Position Size', '%'),
        'max_daily_trades': ('Max Daily Trades', ''),
        'confidence_threshold': ('Confidence Threshold', '%'),
        'stop_loss_percent': ('Stop Loss', '%'),
        'take_profit_percent': ('Take Profit', '%'),
        'max_hold_hours': ('Max Hold Time', ' hours'),
        'max_concurrent_positions': ('Max Concurrent Positions', ''),
        'min_liquidity_usd': ('Min Liquidity', ' USD'),
        'max_slippage_percent': ('Max Slippage', '%'),
        'fast_lane_threshold_usd': ('Fast Lane Threshold', ' USD'),
    }
    
    changes_detected = False
    
    for field_key, (field_label, suffix) in fields_to_track.items():
        before_val = before_config.get(field_key)
        after_val = after_config.get(field_key)
        
        # Skip if both are None or missing
        if before_val is None and after_val is None:
            continue
        
        # Convert to comparable types
        if before_val is not None and after_val is not None:
            # Handle boolean fields
            if isinstance(before_val, bool) or isinstance(after_val, bool):
                before_str = "✓ Enabled" if before_val else "✗ Disabled"
                after_str = "✓ Enabled" if after_val else "✗ Disabled"
                if before_val != after_val:
                    logger.info(f"  • {field_label:.<35} {before_str} → {after_str}")
                    changes_detected = True
                continue
            
            # Handle numeric fields
            try:
                before_num = float(before_val)
                after_num = float(after_val)
                
                if before_num != after_num:
                    # Determine direction indicator
                    if after_num > before_num:
                        indicator = "↗"
                    elif after_num < before_num:
                        indicator = "↘"
                    else:
                        indicator = "→"
                    
                    logger.info(
                        f"  • {field_label:.<35} "
                        f"{before_num}{suffix} {indicator} {after_num}{suffix}"
                    )
                    changes_detected = True
            except (ValueError, TypeError):
                # Handle string fields (like trading_mode)
                if str(before_val) != str(after_val):
                    logger.info(
                        f"  • {field_label:.<35} "
                        f"{before_val} → {after_val}"
                    )
                    changes_detected = True
        elif before_val is None and after_val is not None:
            # New field added
            logger.info(f"  • {field_label:.<35} NEW: {after_val}{suffix}")
            changes_detected = True
    
    if not changes_detected:
        logger.info("  • No changes detected")
    
    logger.info("=" * 70)


# =============================================================================
# CONFIGURATION API
# =============================================================================

@require_http_methods(["GET", "POST"])
@csrf_exempt
def api_configuration(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for strategy configuration management.
    
    GET: Returns current active configuration
    POST: Updates configuration with new settings
    
    Request Body (POST):
        {
            "name": "Strategy Name",
            "trading_mode": "CONSERVATIVE" | "MODERATE" | "AGGRESSIVE",
            "max_position_size_percent": 25.0,
            "stop_loss_percent": 5.0,
            "take_profit_percent": 10.0,
            "max_daily_trades": 20,
            "max_concurrent_positions": 10,
            "confidence_threshold": 60.0,
            "use_fast_lane": true,
            "use_smart_lane": false
        }
    
    Response (GET):
        {
            "success": true,
            "configuration": {...}
        }
    
    Response (POST):
        {
            "success": true,
            "config_id": "uuid",
            "message": "Configuration updated successfully"
        }
    
    Returns:
        JsonResponse: Configuration data or update confirmation
    """
    try:
        # Get default user and account
        user = get_default_user()
        account = get_single_trading_account()
        
        if request.method == 'GET':
            return _handle_get_configuration(account)
        elif request.method == 'POST':
            return _handle_post_configuration(request, account)
            
    except Exception as e:
        logger.error(f"Error in configuration API: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def _handle_get_configuration(account: PaperTradingAccount) -> JsonResponse:
    """
    Handle GET request - return current configuration.
    
    Args:
        account: Paper trading account
        
    Returns:
        JsonResponse with current configuration
    """
    try:
        # Get active configuration
        config = PaperStrategyConfiguration.objects.filter(
            account=account,
            is_active=True
        ).first()
        
        if config:
            config_data = {
                ConfigAPIFields.CONFIG_ID: str(config.config_id),
                ConfigAPIFields.NAME: config.name,
                ConfigAPIFields.TRADING_MODE: config.trading_mode,
                ConfigAPIFields.MAX_POSITION_SIZE_PERCENT: float(config.max_position_size_percent),
                ConfigAPIFields.STOP_LOSS_PERCENT: float(config.stop_loss_percent),
                ConfigAPIFields.TAKE_PROFIT_PERCENT: float(config.take_profit_percent),
                ConfigAPIFields.MAX_DAILY_TRADES: config.max_daily_trades,
                ConfigAPIFields.MAX_CONCURRENT_POSITIONS: config.max_concurrent_positions,
                ConfigAPIFields.CONFIDENCE_THRESHOLD: float(config.confidence_threshold),
                ConfigAPIFields.USE_FAST_LANE: config.use_fast_lane,
                ConfigAPIFields.USE_SMART_LANE: config.use_smart_lane,
                ConfigAPIFields.IS_ACTIVE: config.is_active,
                ConfigAPIFields.CREATED_AT: config.created_at.isoformat(),
                ConfigAPIFields.UPDATED_AT: config.updated_at.isoformat(),
            }
        else:
            # Return default config if none exists
            config_data = {
                ConfigAPIFields.NAME: 'Default Strategy',
                ConfigAPIFields.TRADING_MODE: TradingMode.MODERATE,
                ConfigAPIFields.MAX_POSITION_SIZE_PERCENT: 25.0,
                ConfigAPIFields.STOP_LOSS_PERCENT: 5.0,
                ConfigAPIFields.TAKE_PROFIT_PERCENT: 10.0,
                ConfigAPIFields.MAX_DAILY_TRADES: 20,
                ConfigAPIFields.MAX_CONCURRENT_POSITIONS: 10,
                ConfigAPIFields.CONFIDENCE_THRESHOLD: 60.0,
                ConfigAPIFields.USE_FAST_LANE: True,
                ConfigAPIFields.USE_SMART_LANE: False,
            }
        
        return JsonResponse({
            'success': True,
            'configuration': config_data
        })
        
    except Exception as e:
        logger.error(f"Error getting configuration: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def _handle_post_configuration(
    request: HttpRequest,
    account: PaperTradingAccount
) -> JsonResponse:
    """
    Handle POST request - update configuration.
    
    Args:
        request: HTTP request with JSON body
        account: Paper trading account
        
    Returns:
        JsonResponse with update confirmation
    """
    try:
        # Parse request body
        try:
            body_data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON in request body'
            }, status=400)
        
        # ================================================================
        # DEBUG: Log what we received in the POST request
        # ================================================================
        logger.info("=" * 70)
        logger.info("📥 RECEIVED POST DATA (Configuration Update Request)")
        logger.info("=" * 70)
        for key, value in body_data.items():
            logger.info(f"  • {key}: {value} (type: {type(value).__name__})")
        logger.info("=" * 70)
        
        # ================================================================
        # Capture BEFORE values (existing config or defaults)
        # ================================================================
        existing_config = PaperStrategyConfiguration.objects.filter(
            account=account,
            is_active=True
        ).first()
        
        if existing_config:
            before_values = {
                'name': existing_config.name,
                'trading_mode': existing_config.trading_mode,
                'use_fast_lane': existing_config.use_fast_lane,
                'use_smart_lane': existing_config.use_smart_lane,
                'max_position_size_percent': float(existing_config.max_position_size_percent),
                'stop_loss_percent': float(existing_config.stop_loss_percent),
                'take_profit_percent': float(existing_config.take_profit_percent),
                'max_daily_trades': existing_config.max_daily_trades,
                'confidence_threshold': float(existing_config.confidence_threshold),
                'max_concurrent_positions': existing_config.max_concurrent_positions,
            }
        else:
            # Default values if no existing config
            before_values = {
                'name': 'Default Strategy',
                'trading_mode': TradingMode.MODERATE,
                'use_fast_lane': True,
                'use_smart_lane': False,
                'max_position_size_percent': 25.0,
                'stop_loss_percent': 5.0,
                'take_profit_percent': 10.0,
                'max_hold_hours': 72,
                'max_daily_trades': 20,
                'confidence_threshold': 60.0,
                'max_concurrent_positions': 10,
            }
        
        # ================================================================
        # Validate trading mode
        # ================================================================
        trading_mode = body_data.get(ConfigAPIFields.TRADING_MODE, TradingMode.MODERATE)
        if not validate_trading_mode(trading_mode):
            return JsonResponse({
                'success': False,
                'error': f'Invalid trading mode: {trading_mode}. Must be one of: {TradingMode.ALL}'
            }, status=400)
        
        # Extract configuration parameters
        config_name = body_data.get(ConfigAPIFields.NAME, 'Custom Strategy')
        
        # ================================================================
        # DEBUG: Check for confidence_threshold specifically
        # ================================================================
        if ConfigAPIFields.CONFIDENCE_THRESHOLD in body_data:
            logger.info(f"⚠️  CONFIDENCE_THRESHOLD in POST data: {body_data[ConfigAPIFields.CONFIDENCE_THRESHOLD]}")
        else:
            logger.warning(f"⚠️  CONFIDENCE_THRESHOLD NOT in POST data!")
        
        # ================================================================
        # Create or update configuration
        # ================================================================
        config, created = PaperStrategyConfiguration.objects.update_or_create(
            account=account,
            is_active=True,
            defaults={
                StrategyConfigFields.NAME: config_name,
                StrategyConfigFields.TRADING_MODE: trading_mode,
                StrategyConfigFields.MAX_POSITION_SIZE_PERCENT: Decimal(
                    str(body_data.get(ConfigAPIFields.MAX_POSITION_SIZE_PERCENT, 25.0))
                ),
                StrategyConfigFields.STOP_LOSS_PERCENT: Decimal(
                    str(body_data.get(ConfigAPIFields.STOP_LOSS_PERCENT, 5.0))
                ),
                StrategyConfigFields.TAKE_PROFIT_PERCENT: Decimal(
                    str(body_data.get(ConfigAPIFields.TAKE_PROFIT_PERCENT, 10.0))
                ),
                StrategyConfigFields.MAX_HOLD_HOURS: int(
                    body_data.get(ConfigAPIFields.MAX_HOLD_HOURS, 72)
                ),
                StrategyConfigFields.MAX_DAILY_TRADES: int(
                    body_data.get(ConfigAPIFields.MAX_DAILY_TRADES, 20)
                ),
                StrategyConfigFields.MAX_CONCURRENT_POSITIONS: int(
                    body_data.get(ConfigAPIFields.MAX_CONCURRENT_POSITIONS, 10)
                ),
                StrategyConfigFields.CONFIDENCE_THRESHOLD: Decimal(
                    str(body_data.get(ConfigAPIFields.CONFIDENCE_THRESHOLD, 60.0))
                ),
                StrategyConfigFields.USE_FAST_LANE: bool(
                    body_data.get(ConfigAPIFields.USE_FAST_LANE, True)
                ),
                StrategyConfigFields.USE_SMART_LANE: bool(
                    body_data.get(ConfigAPIFields.USE_SMART_LANE, False)
                ),
            }
        )
        
        # ================================================================
        # Capture AFTER values and log changes
        # ================================================================
        after_values = {
            'name': config.name,
            'trading_mode': config.trading_mode,
            'use_fast_lane': config.use_fast_lane,
            'use_smart_lane': config.use_smart_lane,
            'max_position_size_percent': float(config.max_position_size_percent),
            'stop_loss_percent': float(config.stop_loss_percent),
            'take_profit_percent': float(config.take_profit_percent),
            'max_hold_hours': int(config.max_hold_hours),
            'max_daily_trades': config.max_daily_trades,
            'confidence_threshold': float(config.confidence_threshold),
            'max_concurrent_positions': config.max_concurrent_positions,
        }
        
        # Log the changes
        log_configuration_changes(before_values, after_values, config.name)
        
        action = 'created' if created else 'updated'
        logger.info(f"✅ Configuration '{config_name}' {action} for account {account.account_id}")
        
        return JsonResponse({
            'success': True,
            'config_id': str(config.config_id),
            'message': f'Configuration {action} successfully',
            'created': created
        })
        
    except ValueError as e:
        logger.error(f"Value error in configuration update: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Invalid parameter value: {str(e)}'
        }, status=400)
        
    except Exception as e:
        logger.error(f"Error updating configuration: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)