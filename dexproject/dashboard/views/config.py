"""
Configuration Management Views

Handles configuration listing, summary display, and deletion functionality.
Split from the original monolithic views.py file for better organization.

File: dashboard/views/config.py
"""

import logging
from typing import Dict, Any, Optional

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, HttpRequest
from django.contrib import messages
from django.urls import reverse
from django.core.paginator import Paginator
from django.db import IntegrityError

from ..models import BotConfiguration, TradingSession
from ..engine_service import engine_service

logger = logging.getLogger(__name__)


def configuration_list(request: HttpRequest) -> HttpResponse:
    """
    Display list of user's saved configurations with pagination and filtering.
    
    Shows all saved bot configurations for the current user with options to view,
    edit, or delete each configuration. Includes search and filtering capabilities.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        HttpResponse with rendered configuration list template
    """
    try:
        logger.info(f"Configuration list accessed by user: {request.user.username}")
        
        # Get user's configurations
        configurations = BotConfiguration.objects.filter(user=request.user).order_by('-created_at')
        
        # Apply search filter if provided
        search_query = request.GET.get('search', '').strip()
        if search_query:
            configurations = configurations.filter(name__icontains=search_query)
            logger.debug(f"Applied search filter: {search_query}")
        
        # Apply mode filter if provided
        mode_filter = request.GET.get('mode', '').strip()
        if mode_filter and mode_filter in ['FAST_LANE', 'SMART_LANE']:
            configurations = configurations.filter(trading_mode=mode_filter)
            logger.debug(f"Applied mode filter: {mode_filter}")
        
        # Pagination
        paginator = Paginator(configurations, 10)  # Show 10 configurations per page
        page_number = request.GET.get('page', 1)
        
        try:
            page_obj = paginator.get_page(page_number)
        except Exception as pagination_error:
            logger.warning(f"Pagination error: {pagination_error}")
            page_obj = paginator.get_page(1)
        
        # Get summary statistics
        stats = {
            'total_configs': configurations.count(),
            'fast_lane_configs': BotConfiguration.objects.filter(
                user=request.user, trading_mode='FAST_LANE'
            ).count(),
            'smart_lane_configs': BotConfiguration.objects.filter(
                user=request.user, trading_mode='SMART_LANE'
            ).count(),
        }
        
        context = {
            'page_title': 'My Configurations',
            'configurations': page_obj,
            'search_query': search_query,
            'mode_filter': mode_filter,
            'stats': stats,
            'user': request.user
        }
        
        return render(request, 'dashboard/configuration_list.html', context)
        
    except Exception as e:
        logger.error(f"Error in configuration_list: {e}", exc_info=True)
        messages.error(request, "Error loading configurations.")
        return redirect('dashboard:home')


def configuration_summary(request: HttpRequest, config_id: int) -> HttpResponse:
    """
    Display detailed summary of a specific configuration.
    
    Shows comprehensive details of a saved configuration including all settings,
    performance history, and options to edit, clone, or delete the configuration.
    
    Args:
        request: Django HTTP request object
        config_id: ID of the configuration to display
        
    Returns:
        HttpResponse with rendered configuration summary template
    """
    try:
        logger.info(f"Configuration summary requested for ID: {config_id} by user: {request.user.username}")
        
        # Get the configuration
        config = get_object_or_404(BotConfiguration, id=config_id, user=request.user)
        
        # Get related trading sessions
        related_sessions = TradingSession.objects.filter(
            user=request.user,
            configuration=config
        ).order_by('-created_at')[:10]  # Last 10 sessions
        
        # Get engine status for context
        try:
            engine_status = engine_service.get_engine_status()
        except Exception as engine_error:
            logger.warning(f"Could not get engine status: {engine_error}")
            engine_status = {'status': 'UNKNOWN', '_mock': True}
        
        # Calculate configuration statistics
        config_stats = _calculate_config_stats(config, related_sessions)
        
        # Format configuration data for display
        formatted_config = _format_config_for_display(config)
        
        context = {
            'page_title': f'Configuration: {config.name}',
            'config': config,
            'formatted_config': formatted_config,
            'related_sessions': related_sessions,
            'config_stats': config_stats,
            'engine_status': engine_status,
            'can_start_session': _can_start_session(config, engine_status),
            'user': request.user
        }
        
        return render(request, 'dashboard/configuration_summary.html', context)
        
    except BotConfiguration.DoesNotExist:
        logger.warning(f"Configuration {config_id} not found for user: {request.user.username}")
        messages.error(request, "Configuration not found.")
        return redirect('dashboard:configuration_list')
    except Exception as e:
        logger.error(f"Error in configuration_summary for ID {config_id}: {e}", exc_info=True)
        messages.error(request, "Error loading configuration details.")
        return redirect('dashboard:configuration_list')


def delete_configuration(request: HttpRequest, config_id: int) -> HttpResponse:
    """
    Delete a configuration with confirmation and proper error handling.
    
    Handles both GET (show confirmation) and POST (perform deletion) requests.
    Includes logic to redirect appropriately based on remaining configurations.
    
    Args:
        request: Django HTTP request object
        config_id: ID of the configuration to delete
        
    Returns:
        Redirect to configuration list or confirmation page
    """
    try:
        logger.info(f"Delete request for configuration {config_id} by user: {request.user.username}")
        
        # Get the configuration
        config = get_object_or_404(BotConfiguration, id=config_id, user=request.user)
        
        if request.method == 'POST':
            # Confirm deletion
            config_name = config.name
            config_mode = config.get_trading_mode_display()
            
            # Check if this is the user's only configuration
            user_config_count = BotConfiguration.objects.filter(user=request.user).count()
            
            # Check for active sessions using this configuration
            active_sessions = TradingSession.objects.filter(
                configuration=config,
                is_active=True
            ).count()
            
            if active_sessions > 0:
                messages.error(request, 
                    f"Cannot delete configuration '{config_name}' - it has {active_sessions} active trading session(s). "
                    "Please stop all sessions first."
                )
                return redirect('dashboard:configuration_summary', config_id=config_id)
            
            config.delete()
            
            logger.info(f"Successfully deleted configuration: {config_name}")
            messages.success(request, f'Configuration "{config_name}" deleted successfully.')
            
            # Redirect to appropriate page
            if user_config_count > 1:
                return redirect('dashboard:configuration_list')
            else:
                # If this was their last config, redirect to mode selection
                messages.info(request, "Create a new configuration to get started.")
                return redirect('dashboard:mode_selection')
        else:
            # Show confirmation page
            # Check for active sessions
            active_sessions = TradingSession.objects.filter(
                configuration=config,
                is_active=True
            )
            
            context = {
                'config': config,
                'page_title': 'Delete Configuration',
                'cancel_url': reverse('dashboard:configuration_summary', kwargs={'config_id': config.id}),
                'active_sessions': active_sessions,
                'has_active_sessions': active_sessions.exists(),
            }
            return render(request, 'dashboard/confirm_delete_config.html', context)
            
    except BotConfiguration.DoesNotExist:
        logger.warning(f"Configuration {config_id} not found for deletion")
        messages.error(request, "Configuration not found.")
        return redirect('dashboard:configuration_list')
    except Exception as e:
        logger.error(f"Error deleting configuration {config_id}: {e}", exc_info=True)
        messages.error(request, "Error deleting configuration.")
        return redirect('dashboard:configuration_list')


def clone_configuration(request: HttpRequest, config_id: int) -> HttpResponse:
    """
    Clone an existing configuration with a new name.
    
    Creates a copy of the specified configuration with a new name,
    allowing users to quickly create variations of existing setups.
    
    Args:
        request: Django HTTP request object
        config_id: ID of the configuration to clone
        
    Returns:
        Redirect to new configuration summary or error page
    """
    try:
        logger.info(f"Clone request for configuration {config_id} by user: {request.user.username}")
        
        # Get the original configuration
        original_config = get_object_or_404(BotConfiguration, id=config_id, user=request.user)
        
        if request.method == 'POST':
            new_name = request.POST.get('clone_name', '').strip()
            
            if not new_name:
                messages.error(request, "Please provide a name for the cloned configuration.")
                return redirect('dashboard:configuration_summary', config_id=config_id)
            
            # Check if name already exists
            if BotConfiguration.objects.filter(user=request.user, name=new_name).exists():
                messages.error(request, f"Configuration name '{new_name}' already exists.")
                return redirect('dashboard:configuration_summary', config_id=config_id)
            
            # Create the clone
            cloned_config = BotConfiguration.objects.create(
                user=request.user,
                name=new_name,
                trading_mode=original_config.trading_mode,
                config_data=original_config.config_data.copy(),  # Copy the config data
                is_active=False  # New configs start inactive
            )
            
            logger.info(f"Successfully cloned configuration: {original_config.name} -> {new_name}")
            messages.success(request, f'Configuration cloned as "{new_name}" successfully!')
            
            return redirect('dashboard:configuration_summary', config_id=cloned_config.id)
        
        else:
            # Show clone form (or handle via modal)
            suggested_name = f"{original_config.name} (Copy)"
            
            context = {
                'original_config': original_config,
                'suggested_name': suggested_name,
                'page_title': 'Clone Configuration'
            }
            
            return render(request, 'dashboard/clone_configuration.html', context)
            
    except BotConfiguration.DoesNotExist:
        logger.warning(f"Configuration {config_id} not found for cloning")
        messages.error(request, "Configuration not found.")
        return redirect('dashboard:configuration_list')
    except IntegrityError as e:
        logger.error(f"Database integrity error cloning configuration: {e}")
        messages.error(request, "Error cloning configuration - name may already exist.")
        return redirect('dashboard:configuration_summary', config_id=config_id)
    except Exception as e:
        logger.error(f"Error cloning configuration {config_id}: {e}", exc_info=True)
        messages.error(request, "Error cloning configuration.")
        return redirect('dashboard:configuration_summary', config_id=config_id)


# =========================================================================
# HELPER FUNCTIONS
# =========================================================================

def _calculate_config_stats(config: BotConfiguration, related_sessions) -> Dict[str, Any]:
    """Calculate statistics for a configuration."""
    if not related_sessions:
        return {
            'total_sessions': 0,
            'successful_sessions': 0,
            'success_rate': 0,
            'total_trades': 0,
            'avg_session_duration': 0
        }
    
    total_sessions = len(related_sessions)
    successful_sessions = sum(1 for session in related_sessions if session.is_successful)
    success_rate = (successful_sessions / total_sessions * 100) if total_sessions > 0 else 0
    
    # Calculate other stats
    total_trades = sum(session.trades_executed for session in related_sessions)
    
    # Calculate average session duration (in minutes)
    durations = []
    for session in related_sessions:
        if session.ended_at and session.created_at:
            duration = (session.ended_at - session.created_at).total_seconds() / 60
            durations.append(duration)
    
    avg_session_duration = sum(durations) / len(durations) if durations else 0
    
    return {
        'total_sessions': total_sessions,
        'successful_sessions': successful_sessions,
        'success_rate': success_rate,
        'total_trades': total_trades,
        'avg_session_duration': avg_session_duration
    }


def _format_config_for_display(config: BotConfiguration) -> Dict[str, Any]:
    """Format configuration data for template display."""
    formatted = {
        'basic_info': {
            'Name': config.name,
            'Trading Mode': config.get_trading_mode_display(),
            'Created': config.created_at.strftime('%Y-%m-%d %H:%M'),
            'Last Updated': config.updated_at.strftime('%Y-%m-%d %H:%M'),
            'Status': 'Active' if config.is_active else 'Inactive'
        }
    }
    
    # Add mode-specific configuration details
    if config.trading_mode == 'FAST_LANE':
        formatted['fast_lane_settings'] = {
            'Slippage Tolerance': f"{config.config_data.get('slippage_tolerance', 'N/A')}%",
            'Gas Price': f"{config.config_data.get('gas_price_gwei', 'N/A')} Gwei",
            'Max Priority Fee': f"{config.config_data.get('max_priority_fee_gwei', 'N/A')} Gwei",
            'Use Flashbots': 'Yes' if config.config_data.get('use_flashbots') else 'No',
            'MEV Protection': 'Yes' if config.config_data.get('mev_protection') else 'No',
            'Execution Deadline': f"{config.config_data.get('execution_deadline_seconds', 'N/A')} seconds"
        }
    elif config.trading_mode == 'SMART_LANE':
        formatted['smart_lane_settings'] = {
            'Analysis Depth': config.config_data.get('analysis_depth', 'N/A'),
            'Risk Tolerance': config.config_data.get('risk_tolerance', 'N/A'),
            'Max Analysis Time': f"{config.config_data.get('max_analysis_time', 'N/A')} seconds",
            'AI Insights': 'Enabled' if config.config_data.get('enable_ai_insights') else 'Disabled',
            'Position Sizing': config.config_data.get('position_sizing_method', 'N/A'),
            'Exit Strategy': config.config_data.get('exit_strategy', 'N/A')
        }
    
    return formatted


def _can_start_session(config: BotConfiguration, engine_status: Dict[str, Any]) -> bool:
    """Check if a trading session can be started with this configuration."""
    # Check if engine is available
    if engine_status.get('status') not in ['RUNNING', 'READY']:
        return False
    
    # Check mode-specific availability
    if config.trading_mode == 'FAST_LANE':
        return engine_status.get('fast_lane_active', False)
    elif config.trading_mode == 'SMART_LANE':
        return engine_status.get('smart_lane_active', False)
    
    return False