"""
Celery configuration for the DEX auto-trading bot.

This module sets up task queues for:
- risk.urgent: Fast risk checks before trade execution
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
        # Risk assessment tasks - high priority, fast execution
        'risk.tasks.honeypot_check': {'queue': 'risk.urgent'},
        'risk.tasks.liquidity_check': {'queue': 'risk.urgent'},
        'risk.tasks.ownership_check': {'queue': 'risk.urgent'},
        'risk.tasks.tax_analysis': {'queue': 'risk.urgent'},
        'risk.tasks.contract_security_check': {'queue': 'risk.urgent'},
        'risk.tasks.holder_analysis': {'queue': 'risk.urgent'},
        'risk.tasks.assess_token_risk': {'queue': 'risk.urgent'},
        
        # Trading execution tasks - critical priority, immediate execution
        'trading.tasks.execute_buy_order': {'queue': 'execution.critical'},
        'trading.tasks.execute_sell_order': {'queue': 'execution.critical'},
        'trading.tasks.emergency_exit': {'queue': 'execution.critical'},
        'trading.tasks.update_stop_loss': {'queue': 'execution.critical'},
        'trading.tasks.monitor_position': {'queue': 'execution.critical'},
        
        # Analytics and reporting tasks - background processing
        'analytics.tasks.calculate_pnl': {'queue': 'analytics.background'},
        'analytics.tasks.generate_report': {'queue': 'analytics.background'},
        'analytics.tasks.update_metrics': {'queue': 'analytics.background'},
        'analytics.tasks.feature_importance_analysis': {'queue': 'analytics.background'},
        'analytics.tasks.model_performance_evaluation': {'queue': 'analytics.background'},
        
        # Dashboard tasks - background processing
        'dashboard.tasks.update_system_status': {'queue': 'analytics.background'},
        'dashboard.tasks.send_notification': {'queue': 'analytics.background'},
        
        # Wallet tasks - medium priority
        'wallet.tasks.sync_balance': {'queue': 'risk.urgent'},
        'wallet.tasks.validate_transaction': {'queue': 'risk.urgent'},
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
    
    # Task execution configuration
    task_acks_late = True,  # Acknowledge tasks only after completion
    task_reject_on_worker_lost = True,  # Re-queue tasks if worker dies
    task_track_started = True,  # Track when tasks start
    
    # Retry configuration
    task_annotations = {
        # Risk tasks - fast retries, short timeout
        'risk.tasks.*': {
            'rate_limit': '100/m',  # 100 risk checks per minute max
            'time_limit': 30,  # 30 second hard timeout
            'soft_time_limit': 25,  # 25 second soft timeout
            'retry_kwargs': {'max_retries': 3, 'countdown': 1},
        },
        # Execution tasks - immediate retries, very short timeout
        'trading.tasks.*': {
            'rate_limit': '50/m',  # 50 trades per minute max
            'time_limit': 60,  # 60 second hard timeout
            'soft_time_limit': 50,  # 50 second soft timeout
            'retry_kwargs': {'max_retries': 2, 'countdown': 0.5},
        },
        # Analytics tasks - longer timeout, fewer retries
        'analytics.tasks.*': {
            'rate_limit': '10/m',  # 10 analytics tasks per minute max
            'time_limit': 300,  # 5 minute hard timeout
            'soft_time_limit': 270,  # 4.5 minute soft timeout
            'retry_kwargs': {'max_retries': 2, 'countdown': 60},
        },
    },
    
    # Result backend configuration
    result_expires = 3600,  # Results expire after 1 hour
    result_persistent = True,  # Store results persistently
    
    # Serialization
    task_serializer = 'json',
    result_serializer = 'json',
    accept_content = ['json'],
    
    # Timezone configuration
    timezone = 'UTC',
    enable_utc = True,
    
    # Monitoring and debugging
    task_send_sent_event = True,  # Enable sent events for monitoring
    worker_send_task_events = True,  # Send task events
    
    # Security
    worker_hijack_root_logger = False,  # Don't hijack root logger
    worker_log_color = False,  # Disable colored logs in production
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
        'status': 'ok'
    }

# Queue health check tasks
@app.task(bind=True, queue='risk.urgent')
def health_check_risk_queue(self):
    """Health check for risk queue."""
    import logging
    import time
    
    logger = logging.getLogger(__name__)
    start_time = time.time()
    
    logger.info(f'Risk queue health check started: {self.request.id}')
    
    # Simulate quick risk check
    time.sleep(0.1)
    
    duration = time.time() - start_time
    logger.info(f'Risk queue health check completed in {duration:.3f}s')
    
    return {
        'queue': 'risk.urgent',
        'task_id': self.request.id,
        'duration_seconds': duration,
        'status': 'healthy'
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