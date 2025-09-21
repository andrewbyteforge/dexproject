"""
Fast Lane Views - Dedicated Fast Lane Configuration and Status

Separate views specifically for Fast Lane configuration and status to avoid conflicts
with Smart Lane functionality.

File: dashboard/views/fast_lane.py
"""

import logging
from typing import Dict, Any, Optional

from django.shortcuts import render, redirect
from django.http import HttpResponse, HttpRequest, JsonResponse
from django.contrib import messages
from django.contrib.auth.models import User
from django.db import IntegrityError
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required

from ..models import BotConfiguration
from ..engine_service import engine_service

logger = logging.getLogger(__name__)


def handle_anonymous_user(request: HttpRequest) -> None:
    """Handle anonymous users by creating a demo user."""
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
            logger.info("Created demo user for Fast Lane configuration")


def fast_lane_config(request: HttpRequest) -> HttpResponse:
    """
    Dedicated Fast Lane configuration page.
    
    Handles both GET (display form) and POST (save configuration) requests
    specifically for Fast Lane configuration without any Smart Lane interference.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        HttpResponse with Fast Lane configuration template
    """
    handle_anonymous_user(request)
    
    try:
        logger.info(f"Fast Lane configuration accessed by user: {request.user.username}")
        
        if request.method == 'POST':
            return _handle_fast_lane_save(request)
        else:
            return _handle_fast_lane_display(request)
            
    except Exception as e:
        logger.error(f"Error in fast_lane_config: {e}", exc_info=True)
        messages.error(request, "Error loading Fast Lane configuration.")
        return redirect('dashboard:home')


@require_http_methods(["GET"])
@login_required
def get_fast_lane_status(request: HttpRequest) -> JsonResponse:
    """
    Fast Lane status API endpoint.
    
    Returns JSON response with current Fast Lane engine status, performance metrics,
    and system health information specifically for Fast Lane operations.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JsonResponse with Fast Lane status data
    """
    try:
        logger.debug(f"Fast Lane status API called by user: {request.user.username}")
        
        # Get Fast Lane status from engine service
        fast_lane_status = engine_service.get_engine_status()
        fast_lane_metrics = engine_service.get_performance_metrics()
        
        # Determine Fast Lane specific status
        is_operational = (
            fast_lane_status.get('status') == 'OPERATIONAL' and
            fast_lane_status.get('fast_lane_active', False)
        )
        
        # Compile Fast Lane focused status
        status_data = {
            'timestamp': fast_lane_status.get('timestamp', ''),
            'fast_lane': {
                'status': fast_lane_status.get('status', 'UNKNOWN'),
                'active': fast_lane_status.get('fast_lane_active', False),
                'initialized': fast_lane_status.get('engine_initialized', False),
                'operational': is_operational,
                'execution_time_ms': fast_lane_metrics.get('execution_time_ms', 0),
                'success_rate': fast_lane_metrics.get('success_rate', 0),
                'trades_per_minute': fast_lane_metrics.get('trades_per_minute', 0),
                'mempool_connected': fast_lane_status.get('mempool_connected', False),
                'circuit_breaker_state': fast_lane_status.get('circuit_breaker_state', 'UNKNOWN'),
                'uptime_seconds': fast_lane_status.get('uptime_seconds', 0),
                'data_source': 'LIVE' if not fast_lane_metrics.get('_mock', False) else 'MOCK',
                'mev_protection_active': fast_lane_status.get('mev_protection_active', False),
                'gas_optimization_enabled': fast_lane_status.get('gas_optimization_enabled', True),
                'risk_management_active': fast_lane_status.get('risk_management_active', True)
            },
            'capabilities': {
                'max_execution_time_ms': 500,  # Fast Lane target
                'supported_chains': ['base-sepolia', 'ethereum-sepolia'],
                'mev_protection': True,
                'mempool_monitoring': fast_lane_status.get('mempool_connected', False),
                'gas_optimization': True,
                'circuit_breaker': True
            },
            'performance': {
                'target_execution_time': 200,  # Target <200ms
                'current_execution_time': fast_lane_metrics.get('execution_time_ms', 0),
                'performance_ratio': _calculate_performance_ratio(fast_lane_metrics.get('execution_time_ms', 0)),
                'speed_advantage': _calculate_speed_advantage(fast_lane_metrics.get('execution_time_ms', 0)),
                'reliability_score': fast_lane_metrics.get('success_rate', 0)
            }
        }
        
        return JsonResponse({
            'success': True,
            'data': status_data,
            'message': 'Fast Lane status retrieved successfully'
        })
        
    except Exception as e:
        logger.error(f"Error in get_fast_lane_status: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to get Fast Lane status',
            'data': {
                'fast_lane': {
                    'status': 'ERROR',
                    'active': False,
                    'operational': False,
                    'data_source': 'UNAVAILABLE'
                }
            }
        }, status=500)


def _handle_fast_lane_display(request: HttpRequest) -> HttpResponse:
    """Handle GET request for Fast Lane configuration display."""
    try:
        # Get user's existing Fast Lane configurations
        user_configs = BotConfiguration.objects.filter(
            user=request.user,
            trading_mode='FAST_LANE'
        ).order_by('-updated_at')
        
        # Wallet info for validation
        wallet_info = {
            'is_connected': True,  # Default for demo
            'address': '0x...',
            'balance_eth': 0.5,
            'balance_usd': 1200.0
        }
        
        context = {
            'user': request.user,
            'configurations': user_configs,
            'wallet_info': wallet_info,
            'page_title': 'Fast Lane Configuration',
            # Fast Lane specific options
            'risk_levels': [
                {'value': 'LOW', 'label': 'Low - Conservative trading'},
                {'value': 'MEDIUM', 'label': 'Medium - Balanced approach'},
                {'value': 'HIGH', 'label': 'High - Aggressive trading'}
            ],
            'target_pairs': [
                {'value': 'WETH/USDC', 'label': 'WETH/USDC', 'popular': True},
                {'value': 'WETH/USDT', 'label': 'WETH/USDT', 'popular': True},
                {'value': 'WBTC/USDC', 'label': 'WBTC/USDC', 'popular': False},
                {'value': 'WBTC/WETH', 'label': 'WBTC/WETH', 'popular': False}
            ],
            'execution_timeouts': [
                {'value': 100, 'label': '100ms - Ultra Fast'},
                {'value': 250, 'label': '250ms - Very Fast'},
                {'value': 500, 'label': '500ms - Balanced'},
                {'value': 1000, 'label': '1000ms - Safe'},
                {'value': 2000, 'label': '2000ms - Conservative'}
            ]
        }
        
        logger.debug(f"Fast Lane display context prepared for user: {request.user.username}")
        return render(request, 'dashboard/fast_lane_config.html', context)
        
    except Exception as e:
        logger.error(f"Error loading Fast Lane display: {e}", exc_info=True)
        messages.error(request, f"Error loading Fast Lane configuration: {str(e)}")
        return render(request, 'dashboard/error.html', {'error': str(e)})


def _handle_fast_lane_save(request: HttpRequest) -> HttpResponse:
    """Handle POST request for saving Fast Lane configuration."""
    try:
        logger.info(f"Saving Fast Lane configuration for user: {request.user.username}")
        
        # Extract configuration from form data
        config_data = _extract_fast_lane_config(request.POST)
        
        # Validate configuration
        validation_errors = _validate_fast_lane_config(config_data)
        if validation_errors:
            for error in validation_errors:
                messages.error(request, error)
            return _handle_fast_lane_display(request)
        
        # Save configuration to database
        config = BotConfiguration.objects.create(
            user=request.user,
            name=request.POST.get('config_name', 'Fast Lane Config'),
            trading_mode='FAST_LANE',
            config_data=config_data,
            is_active=request.POST.get('set_active') == 'on'
        )
        
        logger.info(f"Fast Lane configuration saved successfully: {config.id}")
        messages.success(request, f"Fast Lane configuration '{config.name}' saved successfully!")
        
        # Redirect to configuration list or dashboard
        return redirect('dashboard:home')
        
    except IntegrityError:
        messages.error(request, "Configuration name already exists. Please choose a different name.")
        return _handle_fast_lane_display(request)
    
    except Exception as e:
        logger.error(f"Error saving Fast Lane configuration: {e}", exc_info=True)
        messages.error(request, f"Error saving configuration: {str(e)}")
        return _handle_fast_lane_display(request)


def _extract_fast_lane_config(form_data) -> Dict[str, Any]:
    """Extract Fast Lane configuration from form data."""
    return {
        # Basic settings
        'position_size_usd': float(form_data.get('position_size', 100)),
        'execution_timeout_ms': int(form_data.get('execution_timeout', 500)),
        
        # Trading parameters
        'slippage_tolerance_percent': float(form_data.get('slippage_tolerance', 1.0)),
        'gas_price_gwei': float(form_data.get('gas_price', 20)),
        'min_liquidity_usd': float(form_data.get('min_liquidity', 10000)),
        
        # Risk management
        'risk_level': form_data.get('risk_level', 'MEDIUM'),
        
        # Security features
        'mev_protection_enabled': form_data.get('mev_protection') == 'on',
        'auto_approval_enabled': form_data.get('auto_approval') == 'on',
        
        # Trading pairs
        'target_pairs': form_data.getlist('target_pairs') or ['WETH/USDC', 'WETH/USDT'],
        
        # Metadata
        'config_version': '1.0',
        'engine_mode': 'FAST_LANE',
        'created_via': 'fast_lane_config_page'
    }


def _validate_fast_lane_config(config_data: Dict[str, Any]) -> list:
    """Validate Fast Lane configuration data."""
    errors = []
    
    # Position size validation
    position_size = config_data.get('position_size_usd', 0)
    if position_size <= 0:
        errors.append("Position size must be greater than 0")
    if position_size > 10000:
        errors.append("Position size cannot exceed $10,000 for safety")
    
    # Execution timeout validation
    timeout = config_data.get('execution_timeout_ms', 0)
    if timeout < 50:
        errors.append("Execution timeout must be at least 50ms")
    if timeout > 5000:
        errors.append("Execution timeout cannot exceed 5000ms for Fast Lane")
    
    # Slippage validation
    slippage = config_data.get('slippage_tolerance_percent', 0)
    if slippage < 0.1:
        errors.append("Slippage tolerance must be at least 0.1%")
    if slippage > 10:
        errors.append("Slippage tolerance cannot exceed 10%")
    
    # Gas price validation
    gas_price = config_data.get('gas_price_gwei', 0)
    if gas_price < 1:
        errors.append("Gas price must be at least 1 gwei")
    if gas_price > 200:
        errors.append("Gas price cannot exceed 200 gwei")
    
    # Trading pairs validation
    pairs = config_data.get('target_pairs', [])
    if not pairs:
        errors.append("At least one trading pair must be selected")
    
    return errors


def _calculate_performance_ratio(execution_time_ms: float) -> float:
    """Calculate performance ratio compared to target."""
    target_time = 200  # Fast Lane target: <200ms
    if execution_time_ms <= 0:
        return 0.0
    
    return min(100.0, (target_time / execution_time_ms) * 100)


def _calculate_speed_advantage(execution_time_ms: float) -> str:
    """Calculate speed advantage over competitors."""
    competitor_baseline = 300  # Unibot baseline
    if execution_time_ms <= 0:
        return "N/A"
    
    advantage = ((competitor_baseline - execution_time_ms) / competitor_baseline) * 100
    return f"{max(0, advantage):.0f}%"
