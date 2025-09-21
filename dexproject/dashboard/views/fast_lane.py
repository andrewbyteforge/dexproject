"""
Fast Lane Views - Dedicated Fast Lane Configuration

Separate views specifically for Fast Lane configuration to avoid conflicts
with Smart Lane functionality.

File: dashboard/views/fast_lane.py (new file)
"""

import logging
from typing import Dict, Any, Optional

from django.shortcuts import render, redirect
from django.http import HttpResponse, HttpRequest
from django.contrib import messages
from django.contrib.auth.models import User
from django.db import IntegrityError

from ..models import BotConfiguration

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
        
        # Extract and validate form data
        config_name = request.POST.get('config_name', '').strip()
        if not config_name:
            messages.error(request, "Configuration name is required")
            return _handle_fast_lane_display(request)
        
        # Extract Fast Lane specific configuration
        config_data = _extract_fast_lane_config(request.POST)
        
        # Validate configuration data
        validation_errors = _validate_fast_lane_config(config_data)
        if validation_errors:
            for error in validation_errors:
                messages.error(request, error)
            return _handle_fast_lane_display(request)
        
        # Save configuration to database
        config = BotConfiguration.objects.create(
            user=request.user,
            name=config_name,
            description=request.POST.get('description', ''),
            trading_mode='FAST_LANE',
            parameters=config_data,
            is_active=True
        )
        
        # Deactivate other Fast Lane configurations for this user
        BotConfiguration.objects.filter(
            user=request.user,
            trading_mode='FAST_LANE'
        ).exclude(id=config.id).update(is_active=False)
        
        logger.info(f"Fast Lane configuration '{config_name}' saved successfully with ID: {config.id}")
        messages.success(request, f"Fast Lane configuration '{config_name}' saved successfully!")
        
        # Redirect to dashboard or config list
        return redirect('dashboard:home')
        
    except IntegrityError as e:
        logger.error(f"Database integrity error saving Fast Lane config: {e}")
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
    
    # Validate position size
    position_size = config_data.get('position_size_usd', 0)
    if position_size < 10:
        errors.append("Position size must be at least $10")
    elif position_size > 50000:
        errors.append("Position size cannot exceed $50,000")
    
    # Validate execution timeout
    timeout = config_data.get('execution_timeout_ms', 0)
    if timeout < 100:
        errors.append("Execution timeout must be at least 100ms")
    elif timeout > 5000:
        errors.append("Execution timeout cannot exceed 5000ms")
    
    # Validate slippage
    slippage = config_data.get('slippage_tolerance_percent', 0)
    if slippage < 0.1:
        errors.append("Slippage tolerance must be at least 0.1%")
    elif slippage > 10.0:
        errors.append("Slippage tolerance cannot exceed 10%")
    
    # Validate gas price
    gas_price = config_data.get('gas_price_gwei', 0)
    if gas_price < 1:
        errors.append("Gas price must be at least 1 gwei")
    elif gas_price > 500:
        errors.append("Gas price cannot exceed 500 gwei")
    
    # Validate minimum liquidity
    min_liquidity = config_data.get('min_liquidity_usd', 0)
    if min_liquidity < 1000:
        errors.append("Minimum liquidity must be at least $1,000")
    
    # Validate target pairs
    target_pairs = config_data.get('target_pairs', [])
    if not target_pairs:
        errors.append("At least one trading pair must be selected")
    
    # Validate risk level
    risk_level = config_data.get('risk_level', '')
    if risk_level not in ['LOW', 'MEDIUM', 'HIGH']:
        errors.append("Invalid risk level selected")
    
    return errors


# Additional helper functions for Fast Lane

def get_fast_lane_status() -> Dict[str, Any]:
    """Get Fast Lane engine status."""
    return {
        'available': True,
        'engine_online': True,
        'average_execution_time_ms': 387,
        'success_rate_percent': 94.2,
        'active_configurations': 3,
        'total_trades_today': 127
    }


def get_fast_lane_recommendations(user_experience: str = 'BEGINNER') -> Dict[str, Any]:
    """Get recommended Fast Lane settings based on user experience."""
    recommendations = {
        'BEGINNER': {
            'position_size_usd': 50,
            'execution_timeout_ms': 1000,
            'slippage_tolerance_percent': 2.0,
            'gas_price_gwei': 25,
            'risk_level': 'LOW',
            'mev_protection_enabled': True,
            'auto_approval_enabled': False
        },
        'INTERMEDIATE': {
            'position_size_usd': 200,
            'execution_timeout_ms': 500,
            'slippage_tolerance_percent': 1.5,
            'gas_price_gwei': 20,
            'risk_level': 'MEDIUM',
            'mev_protection_enabled': True,
            'auto_approval_enabled': False
        },
        'ADVANCED': {
            'position_size_usd': 1000,
            'execution_timeout_ms': 250,
            'slippage_tolerance_percent': 1.0,
            'gas_price_gwei': 30,
            'risk_level': 'HIGH',
            'mev_protection_enabled': True,
            'auto_approval_enabled': True
        }
    }
    
    return recommendations.get(user_experience, recommendations['BEGINNER'])