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
        
        # Validate trading mode
        trading_mode = body_data.get(ConfigAPIFields.TRADING_MODE, TradingMode.MODERATE)
        if not validate_trading_mode(trading_mode):
            return JsonResponse({
                'success': False,
                'error': f'Invalid trading mode: {trading_mode}. Must be one of: {TradingMode.ALL}'
            }, status=400)
        
        # Extract configuration parameters
        config_name = body_data.get(ConfigAPIFields.NAME, 'Custom Strategy')
        
        # Create or update configuration
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
        
        action = 'created' if created else 'updated'
        logger.info(f"Configuration '{config_name}' {action} for account {account.account_id}")
        
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