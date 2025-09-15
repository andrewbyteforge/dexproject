"""
Configuration Panel View

Handles the configuration panel display for both Fast Lane and Smart Lane modes.

Path: dashboard/views/config.py
"""

import logging
from typing import Dict, Any
from decimal import Decimal

from django.shortcuts import render
from django.http import HttpRequest, HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from trading.models import BotConfiguration
from dashboard.engine_service import DashboardEngineService

logger = logging.getLogger(__name__)


@login_required
def configuration_panel(request: HttpRequest, mode: str = 'FAST_LANE') -> HttpResponse:
    """
    Display configuration panel for Fast Lane or Smart Lane.
    
    Args:
        request: HTTP request object
        mode: Trading mode ('FAST_LANE' or 'SMART_LANE')
        
    Returns:
        HttpResponse: Rendered configuration panel
    """
    try:
        logger.debug(f"Loading configuration panel for {mode} - User: {request.user.username}")
        
        # Validate mode
        if mode not in ['FAST_LANE', 'SMART_LANE']:
            mode = 'FAST_LANE'
        
        # Get user's configurations for this mode
        user_configs = BotConfiguration.objects.filter(
            user=request.user,
            mode=mode
        ).order_by('-created_at')
        
        # Get active configuration if exists
        active_config = user_configs.filter(is_active=True).first()
        
        # Get engine status
        engine_service = DashboardEngineService()
        
        # Mode-specific defaults
        if mode == 'FAST_LANE':
            default_config = {
                'mode': 'FAST_LANE',
                'execution_speed': 'ULTRA_FAST',
                'max_slippage': 2.0,
                'gas_price_multiplier': 1.2,
                'position_size': 100.0,
                'stop_loss': 5.0,
                'take_profit': 10.0,
                'max_positions': 3,
                'enable_flashbots': True,
                'enable_mev_protection': True,
                'auto_restart': False,
                'initial_capital': 1000.0,
            }
            
            engine_available = engine_service.fast_lane_available
            phase_status = "Operational"
            phase_number = "3 & 4"
            
        else:  # SMART_LANE
            default_config = {
                'mode': 'SMART_LANE',
                'analysis_depth': 'COMPREHENSIVE',
                'risk_tolerance': 'MODERATE',
                'position_sizing': 'DYNAMIC',
                'multi_timeframe': True,
                'technical_indicators': ['RSI', 'MACD', 'BB', 'EMA'],
                'fundamental_analysis': True,
                'sentiment_analysis': True,
                'ai_confidence_threshold': 75.0,
                'max_position_size': 25.0,
                'portfolio_rebalancing': True,
                'enable_thought_log': True,
                'initial_capital': 1000.0,
            }
            
            engine_available = engine_service.smart_lane_available
            phase_status = "Phase 5 Development"
            phase_number = "5"
        
        # Handle form submission
        if request.method == 'POST':
            action = request.POST.get('action')
            
            if action == 'save':
                # Save configuration
                config_name = request.POST.get('config_name', f'{mode} Config')
                
                # Build config data from form
                config_data = {}
                for key, default_value in default_config.items():
                    if key in request.POST:
                        value = request.POST.get(key)
                        # Convert to appropriate type
                        if isinstance(default_value, bool):
                            config_data[key] = value.lower() == 'true'
                        elif isinstance(default_value, float):
                            config_data[key] = float(value)
                        elif isinstance(default_value, int):
                            config_data[key] = int(value)
                        else:
                            config_data[key] = value
                    else:
                        config_data[key] = default_value
                
                # Create or update configuration
                if active_config and request.POST.get('update_existing') == 'true':
                    active_config.config_data = config_data
                    active_config.save()
                    messages.success(request, f'{mode.replace("_", " ").title()} configuration updated successfully')
                else:
                    BotConfiguration.objects.create(
                        user=request.user,
                        name=config_name,
                        mode=mode,
                        config_data=config_data,
                        is_active=True
                    )
                    messages.success(request, f'{mode.replace("_", " ").title()} configuration saved successfully')
                
                # Reload page
                return redirect('dashboard:configuration_panel', mode=mode)
            
            elif action == 'load':
                # Load selected configuration
                config_id = request.POST.get('config_id')
                try:
                    selected_config = BotConfiguration.objects.get(
                        id=config_id,
                        user=request.user
                    )
                    # Set as active
                    user_configs.update(is_active=False)
                    selected_config.is_active = True
                    selected_config.save()
                    
                    messages.success(request, f'Loaded configuration: {selected_config.name}')
                    return redirect('dashboard:configuration_panel', mode=mode)
                    
                except BotConfiguration.DoesNotExist:
                    messages.error(request, 'Configuration not found')
        
        # Prepare context
        context = {
            'user': request.user,
            'mode': mode,
            'is_fast_lane': mode == 'FAST_LANE',
            'is_smart_lane': mode == 'SMART_LANE',
            'configurations': user_configs,
            'active_config': active_config,
            'default_config': default_config,
            'current_config': active_config.config_data if active_config else default_config,
            'engine_available': engine_available,
            'phase_status': phase_status,
            'phase_number': phase_number,
            'config_count': user_configs.count(),
            
            # Form options
            'execution_speeds': ['ULTRA_FAST', 'FAST', 'BALANCED'],
            'risk_tolerances': ['CONSERVATIVE', 'MODERATE', 'AGGRESSIVE'],
            'position_sizing_modes': ['FIXED', 'DYNAMIC', 'KELLY_CRITERION'],
            'analysis_depths': ['BASIC', 'STANDARD', 'COMPREHENSIVE'],
            'technical_indicators': ['RSI', 'MACD', 'BB', 'EMA', 'SMA', 'VWAP', 'OBV', 'ADX'],
        }
        
        return render(request, 'dashboard/configuration_panel.html', context)
        
    except Exception as e:
        logger.error(f"Error loading configuration panel: {e}", exc_info=True)
        messages.error(request, f"Error loading configuration: {str(e)}")
        return render(request, 'dashboard/error.html', {'error': str(e)})


# Import at the end to avoid circular imports
from django.shortcuts import redirect