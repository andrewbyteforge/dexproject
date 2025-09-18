"""
Fixed Configuration Panel with Correct Model Fields

This version uses the actual field names from your BotConfiguration model.

File: dashboard/views/config.py
"""

import logging
from django.http import JsonResponse, HttpResponse, HttpRequest
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.models import User
from django.conf import settings

logger = logging.getLogger(__name__)


def configuration_panel(request: HttpRequest, mode: str) -> HttpResponse:
    """Configuration panel that returns JSON for AJAX requests."""
    
    # Handle anonymous users
    if not request.user.is_authenticated:
        from django.contrib.auth.models import User
        user, created = User.objects.get_or_create(
            username='demo_user',
            defaults={'first_name': 'Demo', 'last_name': 'User', 'email': 'demo@example.com'}
        )
        request.user = user

    # Add debug logging
    if request.method == 'POST':
        logger.info(f"POST request to config panel - Mode: {mode}")
        logger.info(f"AJAX headers: X-Requested-With={request.headers.get('X-Requested-With')}")

    # Validate mode
    valid_modes = ['fast_lane', 'smart_lane']
    if mode not in valid_modes:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': f'Invalid mode: {mode}'})
        messages.error(request, f"Invalid mode: {mode}")
        return redirect('dashboard:mode_selection')

    # CRITICAL: Handle POST requests with JSON responses for AJAX
    if request.method == 'POST':
        # Check if this is an AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            try:
                logger.info(f"Processing AJAX configuration save for mode: {mode}")
                
                # Extract form data
                config_data = {
                    'name': request.POST.get('name', '').strip(),
                    'description': request.POST.get('description', '').strip(),
                    'max_position_size_usd': request.POST.get('max_position_size_usd', '100'),
                    'risk_tolerance': request.POST.get('risk_tolerance', 'MEDIUM'),
                    'auto_execution_enabled': request.POST.get('auto_execution_enabled') == 'on',
                    'require_manual_approval': request.POST.get('require_manual_approval') == 'on',
                }
                
                # Mode-specific data extraction
                if mode == 'fast_lane':
                    config_data.update({
                        'execution_timeout_ms': request.POST.get('execution_timeout_ms', '500'),
                        'max_slippage_percent': request.POST.get('max_slippage_percent', '2.0'),
                        'mev_protection_enabled': request.POST.get('mev_protection_enabled') == 'on'
                    })
                elif mode == 'smart_lane':
                    config_data.update({
                        'analysis_depth': request.POST.get('analysis_depth', 'COMPREHENSIVE'),
                        'ai_thought_log': request.POST.get('ai_thought_log', 'COMPREHENSIVE'),
                        'position_sizing_method': request.POST.get('position_sizing_method', 'RISK_BASED'),
                        'max_analysis_time_seconds': request.POST.get('max_analysis_time_seconds', '5')
                    })
                
                # Basic validation
                if not config_data['name']:
                    return JsonResponse({'success': False, 'error': 'Configuration name is required'})
                
                if len(config_data['name']) > 100:
                    return JsonResponse({'success': False, 'error': 'Configuration name must be 100 characters or less'})
                
                # Try to save the configuration
                try:
                    # Import your model
                    from dashboard.models import BotConfiguration
                    
                    # FIXED: Use correct field names from your model
                    config, created = BotConfiguration.objects.update_or_create(
                        user=request.user,
                        name=config_data['name'],
                        trading_mode=mode.upper(),
                        defaults={
                            'advanced_config': config_data,  # FIXED: Use 'advanced_config' instead of 'config_data'
                            'is_default': True               # FIXED: Use 'is_default' instead of 'is_active'
                        }
                    )
                    
                    # FIXED: Deactivate other configs using the correct field name
                    BotConfiguration.objects.filter(
                        user=request.user,
                        trading_mode=mode.upper()
                    ).exclude(id=config.id).update(is_default=False)
                    
                    action = 'created' if created else 'updated'
                    logger.info(f"Configuration {action}: {config.name} (ID: {config.id})")
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Configuration "{config_data["name"]}" {action} successfully!',
                        'config_id': config.id,
                        'redirect_url': '/dashboard/'
                    })
                    
                except Exception as db_error:
                    logger.error(f"Database error saving configuration: {db_error}")
                    return JsonResponse({
                        'success': False,
                        'error': f'Database error: {str(db_error)}'  # Show the actual error for debugging
                    })
                
            except Exception as e:
                logger.error(f"Error in AJAX configuration save: {e}", exc_info=True)
                return JsonResponse({
                    'success': False,
                    'error': f'Server error: {str(e)}'  # Show the actual error for debugging
                })
        else:
            # Handle non-AJAX POST requests (traditional form submission)
            logger.info("Processing traditional form submission")
            messages.info(request, "Please use the form interface to save configurations.")
            return redirect(request.path)
    
    # Handle GET requests (display the form)
    try:
        # Get user's existing configurations
        try:
            from dashboard.models import BotConfiguration
            user_configs = BotConfiguration.objects.filter(
                user=request.user,
                trading_mode=mode.upper()
            ).order_by('-created_at')
            # FIXED: Use correct field name
            active_config = user_configs.filter(is_default=True).first()
        except Exception as config_error:
            logger.error(f"Error loading configurations: {config_error}")
            user_configs = []
            active_config = None
        
        context = {
            'page_title': f'{mode.replace("_", " ").title()} Configuration',
            'mode': mode,
            'mode_display': mode.replace('_', ' ').title(),
            # FIXED: Use correct field name
            'config': active_config.advanced_config if active_config else {},
            'user_configs': user_configs,
            'user': request.user,
        }
        
        return render(request, 'dashboard/configuration_panel.html', context)
        
    except Exception as e:
        logger.error(f"Error loading configuration form: {e}", exc_info=True)
        messages.error(request, "Error loading configuration panel.")
        return redirect('dashboard:mode_selection')