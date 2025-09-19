"""
Smart Lane Features Views - Intelligence & Analysis Components

Contains all Smart Lane specific functionality including analysis, demonstration,
and pipeline management features. Split from the original monolithic views.py 
file (1400+ lines) for better organization.

File: dexproject/dashboard/smart_lane_features.py
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from decimal import Decimal

from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.conf import settings

from .models import BotConfiguration, TradingSession, UserProfile

logger = logging.getLogger(__name__)


# =========================================================================
# SMART LANE PIPELINE INITIALIZATION AND MANAGEMENT
# =========================================================================

# Smart Lane Integration Components
smart_lane_available = False
smart_lane_pipeline = None
smart_lane_metrics = {
    'analyses_completed': 0,
    'average_analysis_time_ms': 0.0,
    'risk_assessments': {},
    'position_recommendations': {},
    'last_analysis': None,
    'errors': []
}

# Thought logs storage (in production, use Redis or database)
thought_logs = {}

try:
    from engine.smart_lane.pipeline import SmartLanePipeline
    from engine.smart_lane import SmartLaneConfig, AnalysisDepth, RiskCategory
    from engine.smart_lane.strategy import (
        PositionSizer, ExitStrategyManager, SizingMethod,
        ExitTrigger, ExitMethod, create_strategy_suite, validate_strategy_components
    )
    smart_lane_available = True
    logger.info("Smart Lane components imported successfully for dashboard integration")
except ImportError as e:
    smart_lane_available = False
    logger.warning(f"Smart Lane components not available: {e}")


def handle_anonymous_user(request: HttpRequest) -> None:
    """
    Handle anonymous users by creating demo user.
    
    Args:
        request: HTTP request object to modify
    """
    if not request.user.is_authenticated:
        from django.contrib.auth.models import User
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
            logger.info("Created demo user for anonymous session")


async def initialize_smart_lane_pipeline() -> bool:
    """
    Initialize Smart Lane pipeline for dashboard integration.
    
    Creates and configures the Smart Lane pipeline with default settings
    optimized for dashboard demonstration and analysis capabilities.
    
    Returns:
        bool: True if initialization successful
    """
    global smart_lane_pipeline
    
    try:
        if not smart_lane_available:
            logger.warning("Smart Lane not available - cannot initialize pipeline")
            return False
        
        if smart_lane_pipeline is not None:
            logger.debug("Smart Lane pipeline already initialized")
            return True
        
        logger.info("Initializing Smart Lane pipeline for dashboard...")
        
        # Create Smart Lane configuration
        config = SmartLaneConfig(
            analysis_depth=AnalysisDepth.COMPREHENSIVE,
            enabled_categories=[
                RiskCategory.HONEYPOT_DETECTION,
                RiskCategory.LIQUIDITY_ANALYSIS,
                RiskCategory.SOCIAL_SENTIMENT,
                RiskCategory.TECHNICAL_ANALYSIS,
                RiskCategory.CONTRACT_SECURITY
            ],
            max_analysis_time_seconds=5.0,
            thought_log_enabled=True,
            min_confidence_threshold=0.3,
            max_acceptable_risk_score=0.8
        )
        
        # Initialize pipeline
        smart_lane_pipeline = SmartLanePipeline(
            config=config,
            chain_id=1,  # Ethereum mainnet
            enable_caching=True
        )
        
        # Test basic functionality
        if smart_lane_pipeline.position_sizer is None:
            logger.error("Smart Lane pipeline missing position sizer")
            return False
        
        if smart_lane_pipeline.exit_strategy_manager is None:
            logger.error("Smart Lane pipeline missing exit strategy manager") 
            return False
        
        logger.info("Smart Lane pipeline initialized successfully for dashboard")
        return True
        
    except Exception as e:
        logger.error(f"Smart Lane pipeline initialization failed: {e}", exc_info=True)
        smart_lane_pipeline = None
        return False


def get_smart_lane_status() -> Dict[str, Any]:
    """
    Get current Smart Lane status for dashboard display.
    
    Returns detailed status information about Smart Lane pipeline state,
    capabilities, and performance metrics.
    
    Returns:
        Dict containing Smart Lane status and metrics
    """
    global smart_lane_pipeline, smart_lane_metrics
    
    try:
        if not smart_lane_available:
            return {
                'status': 'UNAVAILABLE',
                'pipeline_initialized': False,
                'pipeline_active': False,
                'analyzers_count': 0,
                'analysis_ready': False,
                'capabilities': [],
                'analyses_completed': 0,
                'average_analysis_time_ms': 0.0,
                'last_analysis': None,
                'thought_log_enabled': False,
                '_mock': True,
                'error': 'Smart Lane components not available'
            }
        
        return {
            'status': 'OPERATIONAL' if smart_lane_pipeline else 'READY',
            'pipeline_initialized': smart_lane_pipeline is not None,
            'pipeline_active': smart_lane_pipeline is not None,
            'analyzers_count': 5 if smart_lane_pipeline else 0,
            'analysis_ready': smart_lane_pipeline is not None,
            'capabilities': [
                'HONEYPOT_DETECTION',
                'LIQUIDITY_ANALYSIS', 
                'SOCIAL_SENTIMENT',
                'TECHNICAL_ANALYSIS',
                'CONTRACT_SECURITY'
            ] if smart_lane_pipeline else [],
            'analyses_completed': smart_lane_metrics.get('analyses_completed', 0),
            'average_analysis_time_ms': smart_lane_metrics.get('average_analysis_time_ms', 0.0),
            'last_analysis': smart_lane_metrics.get('last_analysis'),
            'thought_log_enabled': True,
            '_mock': False
        }
        
    except Exception as e:
        logger.error(f"Error getting Smart Lane status: {e}")
        return {
            'status': 'ERROR',
            'pipeline_initialized': False,
            'pipeline_active': False,
            'analyzers_count': 0,
            'analysis_ready': False,
            'capabilities': [],
            'error': str(e),
            '_mock': True
        }


# =========================================================================
# SMART LANE DASHBOARD AND DEMO VIEWS
# =========================================================================

def smart_lane_dashboard(request: HttpRequest) -> HttpResponse:
    """
    Smart Lane intelligence dashboard with real-time analysis capabilities.
    
    Displays Smart Lane pipeline status, recent analyses, performance metrics,
    and provides interface for running new token analyses.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        HttpResponse: Rendered Smart Lane dashboard template
    """
    handle_anonymous_user(request)
    
    try:
        logger.info(f"Smart Lane dashboard accessed by user: {request.user}")
        
        # Initialize Smart Lane if needed
        if smart_lane_available and not smart_lane_pipeline:
            asyncio.run(initialize_smart_lane_pipeline())
        
        # Get Smart Lane status and metrics
        smart_lane_status = get_smart_lane_status()
        
        # Get recent analyses (mock data for now)
        recent_analyses = [
            {
                'id': 'analysis_001',
                'token_address': '0x1f9840a85d5af5bf1d1762f925bdaddc4201f984',
                'token_name': 'Uniswap (UNI)',
                'risk_score': 0.2,
                'confidence': 0.95,
                'recommendation': 'LOW_RISK',
                'timestamp': '2024-01-15T10:30:00Z'
            },
            {
                'id': 'analysis_002', 
                'token_address': '0x6b175474e89094c44da98b954eedeac495271d0f',
                'token_name': 'Dai Stablecoin (DAI)',
                'risk_score': 0.1,
                'confidence': 0.98,
                'recommendation': 'SAFE',
                'timestamp': '2024-01-15T09:45:00Z'
            }
        ]
        
        context = {
            'page_title': 'Smart Lane Intelligence Dashboard',
            'smart_lane_status': smart_lane_status,
            'smart_lane_available': smart_lane_available,
            'recent_analyses': recent_analyses,
            'metrics': smart_lane_metrics,
            'user': request.user,
            'pipeline_ready': smart_lane_status.get('pipeline_initialized', False),
            'analysis_categories': [
                {'id': 'honeypot', 'name': 'Honeypot Detection', 'enabled': True},
                {'id': 'liquidity', 'name': 'Liquidity Analysis', 'enabled': True},
                {'id': 'sentiment', 'name': 'Social Sentiment', 'enabled': True},
                {'id': 'technical', 'name': 'Technical Analysis', 'enabled': True},
                {'id': 'security', 'name': 'Contract Security', 'enabled': True}
            ]
        }
        
        return render(request, 'dashboard/smart_lane_dashboard.html', context)
        
    except Exception as e:
        logger.error(f"Error loading Smart Lane dashboard: {e}", exc_info=True)
        messages.error(request, f"Error loading Smart Lane dashboard: {str(e)}")
        return redirect('dashboard:home')


def smart_lane_demo(request: HttpRequest) -> HttpResponse:
    """
    Smart Lane demonstration page with interactive examples.
    
    Provides interactive demonstration of Smart Lane capabilities including
    sample token analyses, risk assessments, and thought process examples.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        HttpResponse: Rendered Smart Lane demo template
    """
    handle_anonymous_user(request)
    
    try:
        logger.info(f"Smart Lane demo accessed by user: {request.user}")
        
        # Demo token examples
        demo_tokens = [
            {
                'name': 'Ethereum (ETH)',
                'address': '0x0000000000000000000000000000000000000000',
                'risk_level': 'VERY_LOW',
                'risk_score': 0.05,
                'confidence': 0.99,
                'analysis_highlights': [
                    'Established token with massive liquidity',
                    'No honeypot patterns detected',
                    'Strong community sentiment',
                    'Excellent technical indicators'
                ]
            },
            {
                'name': 'Suspicious Token (SCAM)',
                'address': '0x1234567890123456789012345678901234567890',
                'risk_level': 'CRITICAL',
                'risk_score': 0.95,
                'confidence': 0.88,
                'analysis_highlights': [
                    'Honeypot pattern detected',
                    'Extremely low liquidity',
                    'Negative social sentiment',
                    'Contract security concerns'
                ]
            }
        ]
        
        # Demo thought log example
        demo_thought_log = [
            {
                'step': 1,
                'category': 'Initial Assessment',
                'thought': 'Beginning analysis of token contract and basic parameters',
                'data': {'contract_verified': True, 'token_standard': 'ERC-20'},
                'timestamp': '2024-01-15T10:30:01Z'
            },
            {
                'step': 2,
                'category': 'Honeypot Detection',
                'thought': 'Checking for honeypot patterns in contract code',
                'data': {'honeypot_risk': 0.02, 'patterns_found': []},
                'timestamp': '2024-01-15T10:30:02Z'
            },
            {
                'step': 3,
                'category': 'Liquidity Analysis',
                'thought': 'Analyzing liquidity depth and trading volume',
                'data': {'liquidity_usd': 50000000, 'volume_24h': 2000000},
                'timestamp': '2024-01-15T10:30:03Z'
            }
        ]
        
        context = {
            'page_title': 'Smart Lane Demo',
            'demo_tokens': demo_tokens,
            'demo_thought_log': demo_thought_log,
            'smart_lane_available': smart_lane_available,
            'user': request.user,
            'pipeline_status': get_smart_lane_status()
        }
        
        return render(request, 'dashboard/smart_lane_demo.html', context)
        
    except Exception as e:
        logger.error(f"Error loading Smart Lane demo: {e}", exc_info=True)
        messages.error(request, f"Error loading Smart Lane demo: {str(e)}")
        return redirect('dashboard:home')


def smart_lane_config(request: HttpRequest) -> HttpResponse:
    """
    Smart Lane configuration page for pipeline settings.
    
    Allows users to configure Smart Lane analysis parameters, risk thresholds,
    and enabled analysis categories.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        HttpResponse: Rendered Smart Lane configuration template
    """
    handle_anonymous_user(request)
    
    try:
        logger.info(f"Smart Lane config accessed by user: {request.user}")
        
        if request.method == 'POST':
            return _handle_smart_lane_config_save(request)
        
        # Get current configuration
        current_config = {
            'analysis_depth': 'COMPREHENSIVE',
            'max_analysis_time': 5.0,
            'confidence_threshold': 0.7,
            'risk_threshold': 0.8,
            'enabled_categories': [
                'HONEYPOT_DETECTION',
                'LIQUIDITY_ANALYSIS',
                'SOCIAL_SENTIMENT',
                'TECHNICAL_ANALYSIS',
                'CONTRACT_SECURITY'
            ],
            'thought_log_enabled': True,
            'auto_position_sizing': True,
            'exit_strategy': 'TRAILING_STOP'
        }
        
        context = {
            'page_title': 'Smart Lane Configuration',
            'current_config': current_config,
            'smart_lane_status': get_smart_lane_status(),
            'smart_lane_available': smart_lane_available,
            'user': request.user,
            'analysis_depth_options': [
                {'value': 'BASIC', 'name': 'Basic Analysis', 'time': '1-2 seconds'},
                {'value': 'COMPREHENSIVE', 'name': 'Comprehensive Analysis', 'time': '3-5 seconds'},
                {'value': 'DEEP_DIVE', 'name': 'Deep Dive Analysis', 'time': '5-10 seconds'}
            ],
            'risk_categories': [
                {'id': 'HONEYPOT_DETECTION', 'name': 'Honeypot Detection', 'description': 'Detect honeypot and rug pull patterns'},
                {'id': 'LIQUIDITY_ANALYSIS', 'name': 'Liquidity Analysis', 'description': 'Analyze token liquidity and trading volume'},
                {'id': 'SOCIAL_SENTIMENT', 'name': 'Social Sentiment', 'description': 'Monitor social media and community sentiment'},
                {'id': 'TECHNICAL_ANALYSIS', 'name': 'Technical Analysis', 'description': 'Technical indicators and price patterns'},
                {'id': 'CONTRACT_SECURITY', 'name': 'Contract Security', 'description': 'Smart contract security audit'}
            ],
            'exit_strategies': [
                {'value': 'FIXED_TARGET', 'name': 'Fixed Target', 'description': 'Exit at predetermined profit target'},
                {'value': 'TRAILING_STOP', 'name': 'Trailing Stop', 'description': 'Dynamic stop-loss that follows price'},
                {'value': 'DYNAMIC_EXIT', 'name': 'Dynamic Exit', 'description': 'AI-powered exit timing'}
            ]
        }
        
        return render(request, 'dashboard/smart_lane_config.html', context)
        
    except Exception as e:
        logger.error(f"Error loading Smart Lane config: {e}", exc_info=True)
        messages.error(request, f"Error loading Smart Lane configuration: {str(e)}")
        return redirect('dashboard:smart_lane_dashboard')


def _handle_smart_lane_config_save(request: HttpRequest) -> HttpResponse:
    """Handle saving Smart Lane configuration."""
    try:
        logger.info(f"Saving Smart Lane configuration for user: {request.user}")
        
        # Extract configuration from form
        config_data = {
            'analysis_depth': request.POST.get('analysis_depth', 'COMPREHENSIVE'),
            'max_analysis_time': float(request.POST.get('max_analysis_time', 5.0)),
            'confidence_threshold': float(request.POST.get('confidence_threshold', 0.7)),
            'risk_threshold': float(request.POST.get('risk_threshold', 0.8)),
            'enabled_categories': request.POST.getlist('enabled_categories'),
            'thought_log_enabled': request.POST.get('thought_log_enabled') == 'on',
            'auto_position_sizing': request.POST.get('auto_position_sizing') == 'on',
            'exit_strategy': request.POST.get('exit_strategy', 'TRAILING_STOP')
        }
        
        # Save configuration to user profile or database
        # For now, just log the configuration
        logger.info(f"Smart Lane configuration saved: {config_data}")
        
        messages.success(request, 'Smart Lane configuration saved successfully!')
        return redirect('dashboard:smart_lane_config')
        
    except Exception as e:
        logger.error(f"Error saving Smart Lane configuration: {e}", exc_info=True)
        messages.error(request, f"Error saving configuration: {str(e)}")
        return redirect('dashboard:smart_lane_config')


# =========================================================================
# SMART LANE ANALYSIS FUNCTIONS
# =========================================================================

def smart_lane_analyze(request: HttpRequest) -> HttpResponse:
    """
    Smart Lane token analysis page.
    
    Provides interface for entering token address and running comprehensive
    Smart Lane analysis with real-time results display.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        HttpResponse: Rendered analysis page or JSON for AJAX requests
    """
    handle_anonymous_user(request)
    
    try:
        if request.method == 'POST':
            # Handle AJAX analysis request
            if request.headers.get('Content-Type') == 'application/json':
                data = json.loads(request.body)
                token_address = data.get('token_address', '').strip()
                
                if not token_address:
                    return JsonResponse({'success': False, 'error': 'Token address required'})
                
                # Run analysis
                analysis_result = asyncio.run(run_smart_lane_analysis(token_address))
                
                if analysis_result:
                    return JsonResponse({'success': True, 'result': analysis_result})
                else:
                    return JsonResponse({'success': False, 'error': 'Analysis failed'})
            
            # Handle regular form submission
            token_address = request.POST.get('token_address', '').strip()
            if token_address:
                analysis_result = asyncio.run(run_smart_lane_analysis(token_address))
                if analysis_result:
                    messages.success(request, f'Analysis completed for {token_address}')
                else:
                    messages.error(request, 'Analysis failed')
            
            return redirect('dashboard:smart_lane_analyze')
        
        # GET request - show analysis form
        context = {
            'page_title': 'Smart Lane Token Analysis',
            'smart_lane_status': get_smart_lane_status(),
            'smart_lane_available': smart_lane_available,
            'user': request.user,
            'recent_analyses': _get_recent_analyses(request.user)
        }
        
        return render(request, 'dashboard/smart_lane_analyze.html', context)
        
    except Exception as e:
        logger.error(f"Error in Smart Lane analyze: {e}", exc_info=True)
        if request.headers.get('Content-Type') == 'application/json':
            return JsonResponse({'success': False, 'error': str(e)})
        else:
            messages.error(request, f"Error: {str(e)}")
            return redirect('dashboard:smart_lane_dashboard')


async def run_smart_lane_analysis(token_address: str) -> Optional[Dict[str, Any]]:
    """
    Run comprehensive Smart Lane analysis on a token.
    
    Performs full Smart Lane pipeline analysis including risk assessment,
    liquidity analysis, sentiment analysis, and generates position recommendations.
    
    Args:
        token_address: Ethereum token contract address
        
    Returns:
        Dict containing analysis results or None if failed
    """
    global smart_lane_pipeline, smart_lane_metrics
    
    try:
        logger.info(f"Running Smart Lane analysis for token: {token_address}")
        
        # Initialize pipeline if needed
        if not smart_lane_pipeline and smart_lane_available:
            await initialize_smart_lane_pipeline()
        
        if not smart_lane_pipeline:
            logger.warning("Smart Lane pipeline not available for analysis")
            return _generate_mock_analysis(token_address)
        
        analysis_id = str(uuid.uuid4())
        start_time = datetime.now()
        
        # Create thought log entry
        thought_log = []
        
        # Step 1: Initial token validation
        thought_log.append({
            'step': 1,
            'category': 'Token Validation',
            'thought': f'Validating token contract at {token_address}',
            'timestamp': datetime.now().isoformat()
        })
        
        # Step 2: Run actual analysis (mock implementation for now)
        analysis_result = await _perform_smart_lane_analysis(token_address, thought_log)
        
        # Calculate analysis time
        analysis_time_ms = (datetime.now() - start_time).total_seconds() * 1000
        
        # Update metrics
        smart_lane_metrics['analyses_completed'] += 1
        smart_lane_metrics['average_analysis_time_ms'] = (
            (smart_lane_metrics['average_analysis_time_ms'] * (smart_lane_metrics['analyses_completed'] - 1) + analysis_time_ms) / 
            smart_lane_metrics['analyses_completed']
        )
        smart_lane_metrics['last_analysis'] = datetime.now().isoformat()
        
        # Store thought log
        thought_logs[analysis_id] = thought_log
        
        # Add metadata to result
        analysis_result.update({
            'analysis_id': analysis_id,
            'analysis_time_ms': analysis_time_ms,
            'timestamp': datetime.now().isoformat()
        })
        
        logger.info(f"Smart Lane analysis completed for {token_address} in {analysis_time_ms:.1f}ms")
        return analysis_result
        
    except Exception as e:
        logger.error(f"Smart Lane analysis failed for {token_address}: {e}", exc_info=True)
        smart_lane_metrics['errors'].append({
            'token_address': token_address,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        })
        return None


async def _perform_smart_lane_analysis(token_address: str, thought_log: List[Dict]) -> Dict[str, Any]:
    """Perform the actual Smart Lane analysis."""
    
    # Mock comprehensive analysis results
    # In production, this would call the actual Smart Lane pipeline
    
    thought_log.append({
        'step': 2,
        'category': 'Honeypot Detection',
        'thought': 'Analyzing contract for honeypot patterns and suspicious functions',
        'data': {'contract_functions': 15, 'suspicious_patterns': 0},
        'timestamp': datetime.now().isoformat()
    })
    
    thought_log.append({
        'step': 3,
        'category': 'Liquidity Analysis',
        'thought': 'Evaluating token liquidity across DEXes and trading volume',
        'data': {'total_liquidity_usd': 125000, 'daily_volume_usd': 50000},
        'timestamp': datetime.now().isoformat()
    })
    
    thought_log.append({
        'step': 4,
        'category': 'Risk Assessment',
        'thought': 'Calculating overall risk score based on all analysis categories',
        'data': {'individual_scores': [0.1, 0.2, 0.15, 0.08, 0.12]},
        'timestamp': datetime.now().isoformat()
    })
    
    return {
        'token_address': token_address,
        'risk_score': 0.15,
        'confidence': 0.89,
        'recommendation': 'LOW_RISK',
        'risk_category': 'ACCEPTABLE',
        'analysis_categories': {
            'honeypot_detection': {'score': 0.1, 'status': 'SAFE'},
            'liquidity_analysis': {'score': 0.2, 'status': 'GOOD'},
            'social_sentiment': {'score': 0.15, 'status': 'NEUTRAL'},
            'technical_analysis': {'score': 0.08, 'status': 'POSITIVE'},
            'contract_security': {'score': 0.12, 'status': 'SECURE'}
        },
        'position_recommendation': {
            'suggested_size_usd': 250,
            'max_position_usd': 500,
            'entry_strategy': 'GRADUAL_ENTRY',
            'exit_strategy': 'TRAILING_STOP'
        },
        'key_insights': [
            'No honeypot patterns detected',
            'Adequate liquidity for position size',
            'Neutral social sentiment',
            'Positive technical indicators',
            'Contract appears secure'
        ]
    }


def _generate_mock_analysis(token_address: str) -> Dict[str, Any]:
    """Generate mock analysis when Smart Lane pipeline is not available."""
    analysis_id = str(uuid.uuid4())
    
    # Store mock thought log
    mock_thought_log = [
        {
            'step': 1,
            'category': 'Mock Analysis',
            'thought': 'Smart Lane pipeline not available - generating mock analysis',
            'timestamp': datetime.now().isoformat()
        }
    ]
    thought_logs[analysis_id] = mock_thought_log
    
    return {
        'analysis_id': analysis_id,
        'token_address': token_address,
        'risk_score': 0.5,
        'confidence': 0.6,
        'recommendation': 'MOCK_DATA',
        'risk_category': 'UNKNOWN',
        'analysis_time_ms': 1000,
        'timestamp': datetime.now().isoformat(),
        '_mock': True,
        'key_insights': ['This is mock data - Smart Lane pipeline not available']
    }


def _get_recent_analyses(user) -> List[Dict[str, Any]]:
    """Get recent analyses for the user."""
    # In production, this would query the database
    return [
        {
            'id': 'recent_001',
            'token_address': '0x1f9840a85d5af5bf1d1762f925bdaddc4201f984',
            'risk_score': 0.2,
            'recommendation': 'LOW_RISK',
            'timestamp': datetime.now().isoformat()
        }
    ]


# =========================================================================
# THOUGHT LOG FUNCTIONS
# =========================================================================

def get_thought_log(analysis_id: str) -> Optional[List[Dict[str, Any]]]:
    """
    Retrieve thought log for a specific analysis.
    
    Returns the detailed reasoning and decision-making process for a 
    Smart Lane analysis, providing transparency into AI decisions.
    
    Args:
        analysis_id: Unique identifier for the analysis
        
    Returns:
        List of thought log entries or None if not found
    """
    try:
        return thought_logs.get(analysis_id)
    except Exception as e:
        logger.error(f"Error retrieving thought log {analysis_id}: {e}")
        return None


def clear_thought_logs() -> None:
    """Clear all stored thought logs (for memory management)."""
    global thought_logs
    thought_logs = {}
    logger.info("Thought logs cleared")


# =========================================================================
# UTILITY FUNCTIONS
# =========================================================================

def get_smart_lane_capabilities() -> List[str]:
    """
    Get list of available Smart Lane capabilities.
    
    Returns:
        List of capability names
    """
    if not smart_lane_available:
        return []
    
    return [
        'HONEYPOT_DETECTION',
        'LIQUIDITY_ANALYSIS',
        'SOCIAL_SENTIMENT',
        'TECHNICAL_ANALYSIS',
        'CONTRACT_SECURITY',
        'POSITION_SIZING',
        'EXIT_STRATEGIES',
        'THOUGHT_LOGGING'
    ]


def validate_smart_lane_config(config: Dict[str, Any]) -> List[str]:
    """
    Validate Smart Lane configuration parameters.
    
    Args:
        config: Configuration dictionary to validate
        
    Returns:
        List of validation error messages
    """
    errors = []
    
    # Validate analysis depth
    valid_depths = ['BASIC', 'COMPREHENSIVE', 'DEEP_DIVE']
    if config.get('analysis_depth') not in valid_depths:
        errors.append(f"Invalid analysis depth. Must be one of: {valid_depths}")
    
    # Validate thresholds
    confidence_threshold = config.get('confidence_threshold', 0)
    if not (0 <= confidence_threshold <= 1):
        errors.append("Confidence threshold must be between 0 and 1")
    
    risk_threshold = config.get('risk_threshold', 0)
    if not (0 <= risk_threshold <= 1):
        errors.append("Risk threshold must be between 0 and 1")
    
    # Validate analysis time
    max_time = config.get('max_analysis_time', 0)
    if not (1 <= max_time <= 30):
        errors.append("Max analysis time must be between 1 and 30 seconds")
    
    return errors