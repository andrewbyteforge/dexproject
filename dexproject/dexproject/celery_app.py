"""
Enhanced Celery Configuration with Risk-Integrated Trading Tasks

Updated to include the new risk-integrated trading workflows and proper task routing
for the complete Phase 5.1C integration.

File: dexproject/celery_app.py
"""

import os
import logging
from celery import Celery
from celery.signals import setup_logging
from django.conf import settings
import sys

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')

# Create the Celery app
app = Celery('dexproject')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Enhanced Celery configuration for the trading bot with risk integration
app.conf.update(
    worker_pool='gevent' if sys.platform == 'win32' else 'prefork',
    worker_pool_restarts=True,
    # Task routing configuration
    task_routes={
        # =============================================================================
        # RISK ASSESSMENT TASKS - HIGH PRIORITY
        # =============================================================================
        
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
        
        # =============================================================================
        # RISK-INTEGRATED TRADING EXECUTION TASKS - CRITICAL PRIORITY
        # =============================================================================
        
        # NEW: Risk-integrated trading tasks (Phase 5.1C)
        'trading.tasks.execute_buy_order_with_risk': {'queue': 'execution.critical'},
        'trading.tasks.execute_sell_order_with_risk': {'queue': 'execution.critical'},
        'trading.tasks.smart_lane_trading_workflow': {'queue': 'risk.urgent'},  # Risk queue for analysis phase
        'trading.tasks.fast_lane_trading_workflow': {'queue': 'execution.critical'},
        
        # Legacy trading execution tasks (now aliases)
        'trading.tasks.execute_buy_order': {'queue': 'execution.critical'},
        'trading.tasks.execute_sell_order': {'queue': 'execution.critical'},
        'trading.tasks.emergency_exit': {'queue': 'execution.critical'},
        
        # Portfolio and position management
        'trading.tasks.update_portfolio_positions': {'queue': 'execution.critical'},
        'trading.tasks.calculate_portfolio_analytics': {'queue': 'analytics.background'},
        'trading.tasks.update_stop_loss': {'queue': 'execution.critical'},
        'trading.tasks.monitor_position': {'queue': 'execution.critical'},
        'trading.tasks.check_slippage': {'queue': 'execution.critical'},
        'trading.tasks.validate_transaction': {'queue': 'execution.critical'},
        
        # =============================================================================
        # PAPER TRADING TASKS - NEW SECTION
        # =============================================================================
        
        # Paper trading bot control tasks
        'paper_trading.tasks.run_paper_trading_bot': {'queue': 'paper_trading'},
        'paper_trading.tasks.stop_paper_trading_bot': {'queue': 'paper_trading'},
        'paper_trading.tasks.get_bot_status': {'queue': 'paper_trading'},
        'paper_trading.tasks.cleanup_old_sessions': {'queue': 'paper_trading'},
        'paper_trading.tasks.monitor_orders_task': {'queue': 'paper_trading'},  # Phase 7A order monitoring
        
        # =============================================================================
        # ANALYTICS AND REPORTING TASKS - BACKGROUND PROCESSING
        # =============================================================================
        
        # Analytics and reporting tasks - background processing
        'analytics.tasks.calculate_pnl': {'queue': 'analytics.background'},
        'analytics.tasks.generate_report': {'queue': 'analytics.background'},
        'analytics.tasks.update_metrics': {'queue': 'analytics.background'},
        'analytics.tasks.feature_importance_analysis': {'queue': 'analytics.background'},
        'analytics.tasks.model_performance_evaluation': {'queue': 'analytics.background'},
        'analytics.tasks.risk_model_training': {'queue': 'analytics.background'},
        'analytics.tasks.backtest_strategies': {'queue': 'analytics.background'},
        
        # =============================================================================
        # DASHBOARD AND SYSTEM TASKS - BACKGROUND PROCESSING
        # =============================================================================
        
        # Dashboard tasks - background processing
        'dashboard.tasks.update_system_status': {'queue': 'analytics.background'},
        'dashboard.tasks.send_notification': {'queue': 'analytics.background'},
        'dashboard.tasks.update_portfolio_display': {'queue': 'analytics.background'},
        'dashboard.tasks.generate_dashboard_data': {'queue': 'analytics.background'},
        'dashboard.tasks.refresh_real_time_metrics': {'queue': 'analytics.background'},
        
        # =============================================================================
        # WALLET AND INFRASTRUCTURE TASKS - MEDIUM PRIORITY
        # =============================================================================
        
        # Wallet tasks - medium priority
        'wallet.tasks.sync_balance': {'queue': 'risk.normal'},
        'wallet.tasks.validate_transaction': {'queue': 'risk.normal'},
        'wallet.tasks.estimate_gas': {'queue': 'risk.normal'},
        'wallet.tasks.check_allowance': {'queue': 'risk.normal'},
        'wallet.tasks.update_wallet_balances': {'queue': 'risk.normal'},
        
        # =============================================================================
        # HEALTH CHECK AND MONITORING TASKS - DISTRIBUTED
        # =============================================================================
        
        # Health check tasks - distributed across queues
        'dexproject.health_check_risk_queue': {'queue': 'risk.urgent'},
        'dexproject.health_check_execution_queue': {'queue': 'execution.critical'},
        'dexproject.health_check_analytics_queue': {'queue': 'analytics.background'},
        
        # System monitoring
        'system.tasks.monitor_queue_health': {'queue': 'risk.normal'},
        'system.tasks.log_system_metrics': {'queue': 'analytics.background'},
        'system.tasks.cleanup_old_logs': {'queue': 'analytics.background'},
    },
    
    # Queue configuration for optimal performance
    task_default_queue='risk.normal',
    worker_prefetch_multiplier=1,  # Prevent workers from grabbing too many tasks
    task_acks_late=True,  # Acknowledge tasks only after completion
    worker_disable_rate_limits=True,  # Disable rate limits for trading speed
    
    # Task time limits
    task_time_limit=300,  # 5 minutes global timeout
    task_soft_time_limit=240,  # 4 minutes soft timeout
    
    # Risk assessment specific timeouts
    task_annotations={
        'risk.tasks.assess_token_risk': {
            'time_limit': 60,  # 1 minute for comprehensive risk assessment
            'soft_time_limit': 45,
        },
        'trading.tasks.execute_buy_order_with_risk': {
            'time_limit': 120,  # 2 minutes for risk + execution
            'soft_time_limit': 90,
        },
        'trading.tasks.execute_sell_order_with_risk': {
            'time_limit': 90,  # 1.5 minutes for lighter risk + execution
            'soft_time_limit': 60,
        },
        'trading.tasks.smart_lane_trading_workflow': {
            'time_limit': 180,  # 3 minutes for full Smart Lane workflow
            'soft_time_limit': 150,
        },
        'trading.tasks.fast_lane_trading_workflow': {
            'time_limit': 30,  # 30 seconds for Fast Lane (when implemented)
            'soft_time_limit': 20,
        },
        # Paper trading specific timeouts
        'paper_trading.tasks.run_paper_trading_bot': {
            'time_limit': 7200,  # 2 hours hard limit
            'soft_time_limit': 7000,  # Just under 2 hours soft limit
        },
        'paper_trading.tasks.stop_paper_trading_bot': {
            'time_limit': 60,  # 1 minute
            'soft_time_limit': 45,
        },
    },    
    
    # Result backend configuration
    result_expires=3600,  # Results expire after 1 hour
    result_backend_transport_options={
        'socket_keepalive': True,
        'socket_keepalive_options': {},  # Empty for Windows compatibility
    },

    # Broker configuration
    broker_transport_options={
        'socket_keepalive': True,
        'socket_keepalive_options': {},  # Empty for Windows compatibility
    },
    
    # Task serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    
    # Concurrency settings for different queue types
    worker_concurrency=4,  # Base concurrency
    
    # Queue priority settings
    task_queue_ha_policy='all',
    
    # Error handling
    task_reject_on_worker_lost=True,
    task_ignore_result=False,
    
    # Task result compression
    result_compression='gzip',
    
    # Monitoring and logging
    worker_send_task_events=True,
    task_send_sent_event=True,
    
    # Custom configuration for trading bot
    task_create_missing_queues=True,
    task_default_retry_delay=5,
    task_max_retries=3,
)

# Queue configuration
app.conf.task_create_missing_queues = True

# Autodiscover tasks in Django apps
app.autodiscover_tasks(['paper_trading'])


# Custom logging setup for trading operations
@setup_logging.connect
def config_loggers(*args, **kwargs):
    """Configure custom loggers for trading operations."""
    from logging.config import dictConfig
    
    dictConfig({
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'detailed': {
                'format': '[{asctime}] {levelname} {name} {process:d} {thread:d} {message}',
                'style': '{',
            },
            'trading': {
                'format': '[{asctime}] 🔥 TRADING {levelname} {name} - {message}',
                'style': '{',
            },
            'risk': {
                'format': '[{asctime}] 🛡️ RISK {levelname} {name} - {message}',
                'style': '{',
            },
            'paper': {
                'format': '[{asctime}] 📝 PAPER {levelname} {name} - {message}',
                'style': '{',
            },
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'detailed',
                'level': 'INFO',
            },
            'trading_file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': 'logs/trading.log',
                'maxBytes': 10485760,  # 10MB
                'backupCount': 5,
                'formatter': 'trading',
                'level': 'DEBUG',
            },
            'risk_file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': 'logs/risk.log',
                'maxBytes': 10485760,  # 10MB
                'backupCount': 5,
                'formatter': 'risk',
                'level': 'DEBUG',
            },
            'paper_file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': 'logs/paper_trading.log',
                'maxBytes': 10485760,  # 10MB
                'backupCount': 5,
                'formatter': 'paper',
                'level': 'DEBUG',
            },
        },
        'loggers': {
            'trading': {
                'handlers': ['console', 'trading_file'],
                'level': 'DEBUG',
                'propagate': False,
            },
            'risk': {
                'handlers': ['console', 'risk_file'],
                'level': 'DEBUG',
                'propagate': False,
            },
            'paper_trading': {
                'handlers': ['console', 'paper_file'],
                'level': 'DEBUG',
                'propagate': False,
            },
            'portfolio': {
                'handlers': ['console', 'trading_file'],
                'level': 'DEBUG',
                'propagate': False,
            },
            'celery': {
                'handlers': ['console'],
                'level': 'INFO',
                'propagate': False,
            },
        },
    })


# =============================================================================
# CELERY BEAT CONFIGURATION (PERIODIC TASKS)
# =============================================================================

from celery.schedules import crontab

app.conf.beat_schedule = {
    # System health checks
    'system-health-check': {
        'task': 'risk.tasks.system_health_check',
        'schedule': crontab(minute='*/5'),  # Every 5 minutes
        'options': {'queue': 'risk.normal'}
    },
    
    # Portfolio updates
    'update-portfolio-positions': {
        'task': 'trading.tasks.update_portfolio_positions',
        'schedule': crontab(minute='*/10'),  # Every 10 minutes
        'options': {'queue': 'analytics.background'}
    },
    
    # Clean up old risk assessments
    'cleanup-old-assessments': {
        'task': 'risk.tasks.cleanup_old_assessments',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
        'options': {'queue': 'risk.background'}
    },
    
    # Paper trading cleanup - daily at 3 AM
    'cleanup-paper-trading-sessions': {
        'task': 'paper_trading.tasks.cleanup_old_sessions',
        'schedule': crontab(hour=3, minute=0),  # Daily at 3 AM
        'options': {'queue': 'paper_trading'},
        'kwargs': {'days': 30}  # Keep sessions for 30 days
    },

    # Phase 7A - Monitor orders every 30 seconds
    'monitor-paper-trading-orders': {
        'task': 'paper_trading.tasks.monitor_orders_task',
        'schedule': 30.0,  # Every 30 seconds
        'options': {'queue': 'paper_trading'},
        'kwargs': {'chain_id': 84532}  # Base Sepolia
    },
    
    # Update risk statistics
    'update-risk-statistics': {
        'task': 'risk.tasks.update_risk_statistics',
        'schedule': crontab(minute='*/30'),  # Every 30 minutes
        'options': {'queue': 'risk.background'}
    },
    
    # Wallet balance synchronization
    'sync-wallet-balances': {
        'task': 'wallet.tasks.update_wallet_balances',
        'schedule': crontab(minute='*/15'),  # Every 15 minutes
        'options': {'queue': 'risk.normal'}
    },
    
    # Dashboard metrics update
    'refresh-dashboard-metrics': {
        'task': 'dashboard.tasks.refresh_real_time_metrics',
        'schedule': crontab(minute='*/2'),  # Every 2 minutes
        'options': {'queue': 'analytics.background'}
    },
}

app.conf.timezone = 'UTC'


# =============================================================================
# CUSTOM TASK BASE CLASSES
# =============================================================================

from celery import Task
from celery.exceptions import Retry
import traceback


class RiskIntegratedTask(Task):
    """
    Base task class for risk-integrated trading operations.
    
    Provides common functionality for risk validation, error handling,
    and integration logging.
    """
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log task failures with detailed context."""
        logger = logging.getLogger('trading')
        logger.error(
            f"❌ Risk-integrated task failed: {self.name} (ID: {task_id})\n"
            f"Args: {args}\n"
            f"Kwargs: {kwargs}\n"
            f"Exception: {exc}\n"
            f"Traceback: {traceback.format_exc()}"
        )
    
    def on_success(self, retval, task_id, args, kwargs):
        """Log successful task completion."""
        logger = logging.getLogger('trading')
        
        # Handle None return values
        if retval is None:
            logger.info(f"✅ Task completed: {self.name} (ID: {task_id})")
            return
        
        # Extract key metrics for logging if retval is a dict
        if isinstance(retval, dict):
            operation = retval.get('operation', 'UNKNOWN')
            status = retval.get('status', 'unknown')
            execution_time = retval.get('execution_time_seconds', 0)
            
            logger.info(
                f"✅ Risk-integrated task completed: {self.name} (ID: {task_id})\n"
                f"Operation: {operation}, Status: {status}, Time: {execution_time:.2f}s"
            )
        else:
            logger.info(f"✅ Task completed: {self.name} (ID: {task_id}), Result: {retval}")
    
    def retry(self, args=None, kwargs=None, exc=None, throw=True, eta=None, countdown=None, max_retries=None, **options):
        """Enhanced retry with trading-specific logic."""
        logger = logging.getLogger('trading')
        
        # Don't retry if it's a risk assessment block
        if exc and 'blocked_by_risk' in str(exc):
            logger.warning(f"⚠️ Not retrying task blocked by risk assessment: {self.name}")
            return
        
        # Don't retry emergency sells
        if self.name == 'trading.tasks.execute_sell_order_with_risk' and kwargs and kwargs.get('is_emergency'):
            logger.warning(f"⚠️ Not retrying emergency sell: {self.name}")
            return
        
        # Standard retry for other cases
        logger.warning(f"🔄 Retrying task: {self.name} (attempt {self.request.retries + 1})")
        return super().retry(args, kwargs, exc, throw, eta, countdown, max_retries, **options)


# Apply custom base class to risk-integrated tasks
app.Task = RiskIntegratedTask


# =============================================================================
# STARTUP VALIDATION
# =============================================================================

@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """Setup additional periodic tasks and validation."""
    logger = logging.getLogger('celery')
    
    # Validate queue configuration
    required_queues = [
        'risk.urgent',
        'risk.normal', 
        'risk.background',
        'execution.critical',
        'analytics.background',
        'paper_trading'  # Added paper trading queue
    ]
    
    logger.info(f"✅ Celery configured with risk-integrated trading tasks")
    logger.info(f"📋 Required queues: {', '.join(required_queues)}")
    logger.info(f"🔄 Beat schedule configured with {len(app.conf.beat_schedule)} periodic tasks")


# =============================================================================
# WORKER STARTUP HOOK
# =============================================================================

@app.on_after_finalize.connect
def worker_ready(sender=None, **kwargs):
    """Hook called when worker is ready."""
    logger = logging.getLogger('celery')
    logger.info("🚀 Celery worker ready for risk-integrated trading operations")


if __name__ == '__main__':
    app.start()