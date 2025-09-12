"""
Celery configuration for the DEX auto-trading bot.

Updated to support the new modular risk assessment system.
This module sets up task queues for:
- risk.urgent: Fast risk checks before trade execution
- risk.normal: Standard risk assessments and monitoring
- risk.background: Bulk assessments and maintenance
- execution.critical: Trade submission, sell exits, stop-losses  
- analytics.background: PnL, reporting, long-running intelligence

Usage:
    celery -A dexproject worker --loglevel=info
    celery -A dexproject worker -Q risk.urgent --loglevel=info
    celery -A dexproject worker -Q execution.critical --loglevel=info
    celery -A dexproject worker -Q analytics.background --loglevel=info
"""

import os
import logging
from celery import Celery
from celery.signals import setup_logging
from django.conf import settings

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')

# Create the Celery app
app = Celery('dexproject')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Enhanced Celery configuration for the trading bot
app.conf.update(
    # Task routing configuration
    task_routes={
        # Main risk assessment tasks - high priority, fast execution
        'risk.tasks.assess_token_risk': {'queue': 'risk.urgent'},
        'risk.tasks.quick_honeypot_check': {'queue': 'risk.normal'},
        'risk.tasks.system_health_check': {'queue': 'risk.normal'},
        
        # Individual risk check tasks - high priority
        'risk.tasks.honeypot_check': {'queue': 'risk.urgent'},
        'risk.tasks.liquidity_check': {'queue': 'risk.urgent'},
        'risk.tasks.ownership_check': {'queue': 'risk.urgent'},
        'risk.tasks.tax_analysis': {'queue': 'risk.urgent'},
        'risk.tasks.contract_security_check': {'queue': 'risk.urgent'},
        'risk.tasks.holder_analysis': {'queue': 'risk.urgent'},
        
        # Bulk assessment tasks - background processing
        'risk.tasks.bulk_assessment': {'queue': 'risk.background'},
        'risk.tasks.bulk_honeypot_scan': {'queue': 'risk.background'},
        'risk.tasks.portfolio_risk_scan': {'queue': 'risk.background'},
        
        # Risk maintenance and cleanup tasks - background
        'risk.tasks.cleanup_old_assessments': {'queue': 'risk.background'},
        'risk.tasks.update_risk_statistics': {'queue': 'risk.background'},
        'risk.tasks.generate_risk_report': {'queue': 'risk.background'},
        
        # Trading execution tasks - critical priority, immediate execution
        'trading.tasks.execute_buy_order': {'queue': 'execution.critical'},
        'trading.tasks.execute_sell_order': {'queue': 'execution.critical'},
        'trading.tasks.emergency_exit': {'queue': 'execution.critical'},
        'trading.tasks.update_stop_loss': {'queue': 'execution.critical'},
        'trading.tasks.monitor_position': {'queue': 'execution.critical'},
        'trading.tasks.check_slippage': {'queue': 'execution.critical'},
        'trading.tasks.validate_transaction': {'queue': 'execution.critical'},
        
        # Analytics and reporting tasks - background processing
        'analytics.tasks.calculate_pnl': {'queue': 'analytics.background'},
        'analytics.tasks.generate_report': {'queue': 'analytics.background'},
        'analytics.tasks.update_metrics': {'queue': 'analytics.background'},
        'analytics.tasks.feature_importance_analysis': {'queue': 'analytics.background'},
        'analytics.tasks.model_performance_evaluation': {'queue': 'analytics.background'},
        'analytics.tasks.risk_model_training': {'queue': 'analytics.background'},
        'analytics.tasks.backtest_strategies': {'queue': 'analytics.background'},
        
        # Dashboard tasks - background processing
        'dashboard.tasks.update_system_status': {'queue': 'analytics.background'},
        'dashboard.tasks.send_notification': {'queue': 'analytics.background'},
        'dashboard.tasks.update_portfolio_display': {'queue': 'analytics.background'},
        'dashboard.tasks.generate_dashboard_data': {'queue': 'analytics.background'},
        
        # Wallet tasks - medium priority
        'wallet.tasks.sync_balance': {'queue': 'risk.normal'},
        'wallet.tasks.validate_transaction': {'queue': 'risk.normal'},
        'wallet.tasks.estimate_gas': {'queue': 'risk.normal'},
        'wallet.tasks.check_allowance': {'queue': 'risk.normal'},
        
        # Health check tasks - distributed across queues
        'dexproject.health_check_risk_queue': {'queue': 'risk.urgent'},
        'dexproject.health_check_execution_queue': {'queue': 'execution.critical'},
        'dexproject.health_check_analytics_queue': {'queue': 'analytics.background'},
    },
    
    # Queue configuration
    task_default_queue = 'default',
    task_default_exchange = 'default',
    task_default_exchange_type = 'direct',
    task_default_routing_key = 'default',
    
    # Worker configuration
    worker_prefetch_multiplier = 1,  # One task at a time for critical queues
    worker_max_tasks_per_child = 1000,  # Restart worker after 1000 tasks
    worker_disable_rate_limits = False,
    worker_log_color = False,  # Consistent with production
    
    # Task execution configuration
    task_acks_late = True,  # Acknowledge tasks only after completion
    task_reject_on_worker_lost = True,  # Re-queue tasks if worker dies
    task_track_started = True,  # Track when tasks start
    task_time_limit = 300,  # Global 5-minute timeout
    task_soft_time_limit = 270,  # Global 4.5-minute soft timeout
    
    # Retry configuration with improved settings for our modular structure
    task_annotations = {
        # Main assessment tasks - fast retries, moderate timeout
        'risk.tasks.assess_token_risk': {
            'rate_limit': '200/m',  # Increased for modular efficiency
            'time_limit': 30,
            'soft_time_limit': 25,
            'retry_kwargs': {'max_retries': 2, 'countdown': 1},
        },
        'risk.tasks.quick_honeypot_check': {
            'rate_limit': '500/m',  # Higher rate for quick checks
            'time_limit': 10,
            'soft_time_limit': 8,
            'retry_kwargs': {'max_retries': 2, 'countdown': 0.5},
        },
        
        # Individual risk check tasks - fast execution
        'risk.tasks.honeypot_check': {
            'rate_limit': '300/m',
            'time_limit': 15,
            'soft_time_limit': 12,
            'retry_kwargs': {'max_retries': 3, 'countdown': 1},
        },
        'risk.tasks.liquidity_check': {
            'rate_limit': '300/m',
            'time_limit': 15,
            'soft_time_limit': 12,
            'retry_kwargs': {'max_retries': 3, 'countdown': 1},
        },
        'risk.tasks.ownership_check': {
            'rate_limit': '200/m',  # Slower due to contract analysis
            'time_limit': 20,
            'soft_time_limit': 17,
            'retry_kwargs': {'max_retries': 3, 'countdown': 2},
        },
        'risk.tasks.tax_analysis': {
            'rate_limit': '200/m',
            'time_limit': 25,
            'soft_time_limit': 22,
            'retry_kwargs': {'max_retries': 3, 'countdown': 2},
        },
        'risk.tasks.contract_security_check': {
            'rate_limit': '100/m',  # Most intensive check
            'time_limit': 30,
            'soft_time_limit': 27,
            'retry_kwargs': {'max_retries': 2, 'countdown': 3},
        },
        
        # Bulk assessment tasks - longer timeout, fewer retries
        'risk.tasks.bulk_assessment': {
            'rate_limit': '10/m',
            'time_limit': 600,  # 10 minutes for bulk processing
            'soft_time_limit': 570,
            'retry_kwargs': {'max_retries': 1, 'countdown': 60},
        },
        
        # System tasks - moderate settings
        'risk.tasks.system_health_check': {
            'rate_limit': '60/m',
            'time_limit': 30,
            'soft_time_limit': 25,
            'retry_kwargs': {'max_retries': 1, 'countdown': 5},
        },
        
        # Execution tasks - immediate retries, very short timeout
        'trading.tasks.*': {
            'rate_limit': '100/m',  # Increased trading capacity
            'time_limit': 60,
            'soft_time_limit': 50,
            'retry_kwargs': {'max_retries': 2, 'countdown': 0.5},
        },
        
        # Analytics tasks - longer timeout, fewer retries
        'analytics.tasks.*': {
            'rate_limit': '20/m',  # Increased analytics capacity
            'time_limit': 600,  # 10 minutes
            'soft_time_limit': 570,
            'retry_kwargs': {'max_retries': 2, 'countdown': 60},
        },
        
        # Wallet tasks - medium priority
        'wallet.tasks.*': {
            'rate_limit': '200/m',
            'time_limit': 30,
            'soft_time_limit': 25,
            'retry_kwargs': {'max_retries': 3, 'countdown': 2},
        },
        
        # Dashboard tasks - low priority
        'dashboard.tasks.*': {
            'rate_limit': '30/m',
            'time_limit': 120,
            'soft_time_limit': 100,
            'retry_kwargs': {'max_retries': 1, 'countdown': 30},
        },
    },
    
    # Result backend configuration
    result_expires = 3600,  # Results expire after 1 hour
    result_persistent = True,  # Store results persistently
    result_compression = 'gzip',  # Compress large results
    
    # Serialization
    task_serializer = 'json',
    result_serializer = 'json',
    accept_content = ['json'],
    
    # Timezone configuration
    timezone = 'UTC',
    enable_utc = True,
    
    # Monitoring and debugging
    task_send_sent_event = True,
    worker_send_task_events = True,
    task_always_eager = False,  # Ensure tasks run asynchronously
    
    # Security
    worker_hijack_root_logger = False,
    
    # Performance optimizations for our modular structure
    task_ignore_result = False,  # We want results for monitoring
    result_cache_max = 10000,  # Cache more results for dashboard
    worker_max_memory_per_child = 200000,  # 200MB per worker before restart
)

# Custom logging configuration
@setup_logging.connect
def config_loggers(*args, **kwargs):
    """Configure structured logging for Celery workers."""
    from logging.config import dictConfig
    
    dictConfig({
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'detailed': {
                'format': '[%(asctime)s] %(levelname)s [%(name)s:%(lineno)s] %(message)s',
                'datefmt': '%Y-%m-%d %H:%M:%S',
            },
            'json': {
                'format': '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s", "module": "%(module)s", "function": "%(funcName)s", "line": %(lineno)d}',
                'datefmt': '%Y-%m-%dT%H:%M:%S',
            },
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'level': 'INFO',
                'formatter': 'detailed',
                'stream': 'ext://sys.stdout',
            },
            'file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'level': 'DEBUG',
                'formatter': 'json',
                'filename': 'logs/celery.log',
                'maxBytes': 10485760,  # 10MB
                'backupCount': 10,
                'encoding': 'utf8',
            },
        },
        'loggers': {
            'celery': {
                'level': 'INFO',
                'handlers': ['console', 'file'],
                'propagate': False,
            },
            'celery.task': {
                'level': 'INFO',
                'handlers': ['console', 'file'],
                'propagate': False,
            },
            'dexproject': {
                'level': 'DEBUG',
                'handlers': ['console', 'file'],
                'propagate': False,
            },
            # Add specific loggers for our modular risk system
            'risk.tasks': {
                'level': 'DEBUG',
                'handlers': ['console', 'file'],
                'propagate': False,
            },
            'risk.tasks.profiles': {
                'level': 'INFO',
                'handlers': ['console', 'file'],
                'propagate': False,
            },
            'risk.tasks.execution': {
                'level': 'INFO',
                'handlers': ['console', 'file'],
                'propagate': False,
            },
            'risk.tasks.scoring': {
                'level': 'INFO',
                'handlers': ['console', 'file'],
                'propagate': False,
            },
        },
        'root': {
            'level': 'INFO',
            'handlers': ['console'],
        },
    })

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Define queue-specific worker classes for optimal performance
@app.task(bind=True)
def debug_task(self):
    """Debug task to test Celery configuration."""
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f'Celery debug task executed')
    logger.info(f'Request: {self.request!r}')
    logger.info(f'Current queues: {list(app.conf.task_routes.keys())}')
    
    return {
        'worker_id': self.request.id,
        'hostname': self.request.hostname,
        'queues': list(app.conf.task_routes.keys()),
        'status': 'ok',
        'modular_risk_system': 'enabled'
    }

# Enhanced health check tasks for the new modular system
@app.task(bind=True, queue='risk.urgent')
def health_check_risk_queue(self):
    """Health check for risk queue with modular system verification."""
    import logging
    import time
    
    logger = logging.getLogger(__name__)
    start_time = time.time()
    
    logger.info(f'Risk queue health check started: {self.request.id}')
    
    # Test modular risk system imports
    try:
        from risk.tasks.profiles import get_risk_profile_config
        from risk.tasks.scoring import calculate_overall_risk_score
        from risk.tasks.execution import execute_parallel_risk_checks
        
        # Quick test of profile system
        conservative_config = get_risk_profile_config('Conservative')
        modules_available = True
        
    except ImportError as e:
        logger.error(f'Modular risk system import failed: {e}')
        modules_available = False
    
    # Simulate quick risk check
    time.sleep(0.1)
    
    duration = time.time() - start_time
    logger.info(f'Risk queue health check completed in {duration:.3f}s')
    
    return {
        'queue': 'risk.urgent',
        'task_id': self.request.id,
        'duration_seconds': duration,
        'modular_system_available': modules_available,
        'profile_configs_loaded': modules_available,
        'status': 'healthy' if modules_available else 'degraded'
    }

@app.task(bind=True, queue='execution.critical')  
def health_check_execution_queue(self):
    """Health check for execution queue."""
    import logging
    import time
    
    logger = logging.getLogger(__name__)
    start_time = time.time()
    
    logger.info(f'Execution queue health check started: {self.request.id}')
    
    # Simulate quick execution check
    time.sleep(0.05)
    
    duration = time.time() - start_time
    logger.info(f'Execution queue health check completed in {duration:.3f}s')
    
    return {
        'queue': 'execution.critical',
        'task_id': self.request.id,
        'duration_seconds': duration,
        'status': 'healthy'
    }

@app.task(bind=True, queue='analytics.background')
def health_check_analytics_queue(self):
    """Health check for analytics queue."""
    import logging
    import time
    
    logger = logging.getLogger(__name__)
    start_time = time.time()
    
    logger.info(f'Analytics queue health check started: {self.request.id}')
    
    # Simulate longer analytics task
    time.sleep(0.5)
    
    duration = time.time() - start_time
    logger.info(f'Analytics queue health check completed in {duration:.3f}s')
    
    return {
        'queue': 'analytics.background', 
        'task_id': self.request.id,
        'duration_seconds': duration,
        'status': 'healthy'
    }

@app.task(bind=True, queue='risk.normal')
def health_check_risk_normal_queue(self):
    """Health check for normal risk queue."""
    import logging
    import time
    
    logger = logging.getLogger(__name__)
    start_time = time.time()
    
    logger.info(f'Risk normal queue health check started: {self.request.id}')
    
    # Test modular components
    try:
        from risk.tasks import quick_honeypot_check, system_health_check
        components_available = True
    except ImportError:
        components_available = False
    
    # Simulate normal risk task
    time.sleep(0.2)
    
    duration = time.time() - start_time
    logger.info(f'Risk normal queue health check completed in {duration:.3f}s')
    
    return {
        'queue': 'risk.normal',
        'task_id': self.request.id,
        'duration_seconds': duration,
        'components_available': components_available,
        'status': 'healthy' if components_available else 'degraded'
    }

@app.task(bind=True, queue='risk.background')
def health_check_risk_background_queue(self):
    """Health check for background risk queue."""
    import logging
    import time
    
    logger = logging.getLogger(__name__)
    start_time = time.time()
    
    logger.info(f'Risk background queue health check started: {self.request.id}')
    
    # Test bulk processing components
    try:
        from risk.tasks.batch import process_assessment_batch, generate_bulk_summary
        from risk.tasks.database import create_assessment_record
        bulk_components_available = True
    except ImportError:
        bulk_components_available = False
    
    # Simulate background task
    time.sleep(1.0)
    
    duration = time.time() - start_time
    logger.info(f'Risk background queue health check completed in {duration:.3f}s')
    
    return {
        'queue': 'risk.background',
        'task_id': self.request.id,
        'duration_seconds': duration,
        'bulk_components_available': bulk_components_available,
        'status': 'healthy' if bulk_components_available else 'degraded'
    }

# Comprehensive system health check task
@app.task(bind=True, queue='risk.normal')
def comprehensive_system_health_check(self):
    """Comprehensive health check for the entire modular risk system."""
    import logging
    import time
    from celery import group
    
    logger = logging.getLogger(__name__)
    start_time = time.time()
    
    logger.info(f'Comprehensive system health check started: {self.request.id}')
    
    try:
        # Run all queue health checks in parallel
        health_checks = group([
            health_check_risk_queue.s(),
            health_check_execution_queue.s(),
            health_check_analytics_queue.s(),
            health_check_risk_normal_queue.s(),
            health_check_risk_background_queue.s()
        ])
        
        # Execute with timeout
        job = health_checks.apply_async()
        results = job.get(timeout=30)
        
        # Analyze results
        all_healthy = all(result.get('status') == 'healthy' for result in results)
        queue_statuses = {result['queue']: result['status'] for result in results}
        
        duration = time.time() - start_time
        
        logger.info(f'Comprehensive health check completed in {duration:.3f}s - All healthy: {all_healthy}')
        
        return {
            'task_id': self.request.id,
            'duration_seconds': duration,
            'overall_status': 'healthy' if all_healthy else 'degraded',
            'queue_statuses': queue_statuses,
            'individual_results': results,
            'modular_system_operational': True,
            'timestamp': time.time()
        }
        
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f'Comprehensive health check failed: {e}')
        
        return {
            'task_id': self.request.id,
            'duration_seconds': duration,
            'overall_status': 'unhealthy',
            'error': str(e),
            'modular_system_operational': False,
            'timestamp': time.time()
        }