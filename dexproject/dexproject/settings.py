"""
Enhanced Django settings for dexproject with Web3 integration, SIWE support, and Channels

This settings file includes Web3 configuration, testnet support, SIWE wallet
authentication, Django Channels for WebSocket support, and enhanced trading 
engine settings for both development and production.

UPDATED: PTphase3 - Added Django Channels and WebSocket configuration
- Django Channels for real-time updates
- WebSocket support for paper trading dashboard
- Channel layers configuration
- ASGI application setup

File: dexproject/dexproject/settings.py
"""

import os
import sys
from pathlib import Path
import logging

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    # Load production environment file if it exists, otherwise regular .env
    production_env_file = Path(__file__).resolve().parent.parent / '.env.production'
    if production_env_file.exists():
        load_dotenv(production_env_file)
    else:
        load_dotenv()
except ImportError:
    # python-dotenv not installed - environment variables must be set manually
    pass

from decimal import Decimal

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
logger = logging.getLogger(__name__)

# =============================================================================
# HELPER FUNCTIONS FOR ENVIRONMENT VARIABLES
# =============================================================================

def get_env_int(key: str, default: str) -> int:
    """Safely convert environment variable to integer, handling float strings."""
    return int(float(os.getenv(key, default)))

def get_env_decimal(key: str, default: str) -> Decimal:
    """Safely convert environment variable to Decimal."""
    return Decimal(os.getenv(key, default))

def get_env_bool(key: str, default: str) -> bool:
    """Convert environment variable to boolean."""
    value = os.getenv(key, default).lower()
    return value in ('true', '1', 'yes', 'on')

def get_env_list(key: str, default: str = '') -> list:
    """Convert environment variable to list, filtering empty values."""
    value = os.getenv(key, default)
    if not value:
        return []
    return [item.strip() for item in value.split(',') if item.strip()]

# =============================================================================
# ENVIRONMENT DETECTION
# =============================================================================

# Detect if we're running in production mode
PRODUCTION_MODE = get_env_bool('PRODUCTION_MODE', 'False')
TRADING_ENVIRONMENT = os.getenv('TRADING_ENVIRONMENT', 'development')  # development, staging, production

# =============================================================================
# CORE DJANGO SETTINGS
# =============================================================================

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-test-key-for-development-only')

# Production secret key validation
if PRODUCTION_MODE and SECRET_KEY == 'django-insecure-test-key-for-development-only':
    raise ValueError("Production mode requires a secure SECRET_KEY to be set!")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = get_env_bool('DEBUG', 'True') and not PRODUCTION_MODE

# ALLOWED_HOSTS configuration - Enhanced for production
ALLOWED_HOSTS = ['localhost', '127.0.0.1']
additional_hosts = get_env_list('ALLOWED_HOSTS')
if additional_hosts:
    ALLOWED_HOSTS.extend(additional_hosts)

# Production security: Don't allow all hosts even in development when PRODUCTION_MODE=True
if not DEBUG and len(ALLOWED_HOSTS) <= 2 and not PRODUCTION_MODE:  # Only localhost and 127.0.0.1
    ALLOWED_HOSTS.append('*')  # Allow all hosts in development when DEBUG=False
    logger.warning("DEBUG=False with minimal ALLOWED_HOSTS - adding '*' for development")

# Application definition
DJANGO_APPS = [
    'daphne',  # Add at the top for ASGI/WebSocket support
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'corsheaders',
    'channels',  # Django Channels for WebSocket support
]

LOCAL_APPS = [
    'shared',       # Add shared app for common utilities
    'dashboard',
    'trading',
    'risk',
    'wallet',
    'analytics',
    'paper_trading',
    'shared.circuit_breakers',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# Enhanced middleware for production
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'wallet.auth.SIWESessionMiddleware',  # SIWE session validation middleware
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# Add performance monitoring middleware in production
if PRODUCTION_MODE:
    MIDDLEWARE.insert(-1, 'shared.middleware.PerformanceMonitoringMiddleware')

# =============================================================================
# ANALYTICS MONITORING MIDDLEWARE
# =============================================================================

# Add analytics metrics middleware for automatic request tracking
MIDDLEWARE.append('analytics.middleware.MetricsMiddleware')

# Add database metrics middleware in DEBUG mode
if DEBUG:
    MIDDLEWARE.append('analytics.middleware.DatabaseMetricsMiddleware')

logger.info("📊 Analytics monitoring middleware enabled")

ROOT_URLCONF = 'dexproject.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# ASGI configuration for WebSocket support
WSGI_APPLICATION = 'dexproject.wsgi.application'
ASGI_APPLICATION = 'dexproject.asgi.application'


# =============================================================================
# SSE (SERVER-SENT EVENTS) CONFIGURATION
# =============================================================================

# Control SSE streaming for dashboard metrics
SSE_ENABLED = get_env_bool('SSE_ENABLED', 'False')  # Disable by default to prevent hanging
SSE_MAX_ITERATIONS = get_env_int('SSE_MAX_ITERATIONS', '10')  # Reduced from 100
DASHBOARD_SSE_UPDATE_INTERVAL = get_env_int('DASHBOARD_SSE_UPDATE_INTERVAL', '5')  # Increased from 2

# Log SSE configuration
logger.info(f"📡 SSE Configuration: Enabled={SSE_ENABLED}, Max Iterations={SSE_MAX_ITERATIONS}, Interval={DASHBOARD_SSE_UPDATE_INTERVAL}s")



# =============================================================================
# DJANGO CHANNELS CONFIGURATION (WebSocket Support)
# =============================================================================

# Channel Layers - For WebSocket message passing
# Development: Use in-memory channel layer
# Production: Use Redis channel layer for scalability

REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# Check if Redis is available
REDIS_AVAILABLE = False
try:
    import redis
    r = redis.Redis.from_url(REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
    r.ping()
    REDIS_AVAILABLE = True
    logger.info("Redis connection successful for Channel Layer")
except Exception as e:
    logger.warning(f"Redis not available for Channel Layer ({e}) - using in-memory")

# Configure Channel Layers based on Redis availability and environment
if REDIS_AVAILABLE and PRODUCTION_MODE:
    # Production with Redis
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                "hosts": [REDIS_URL],  # ✅ CORRECT - no parentheses, just brackets
                "capacity": 1500,
                "expiry": 10,
            },
        },
    }
    logger.info("Using Redis Channel Layer for WebSockets")
elif REDIS_AVAILABLE:
    # Development with Redis available
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                "hosts": [REDIS_URL],  # ✅ CORRECT
            },
        },
    }
    logger.info("Using Redis Channel Layer for WebSockets (development)")
else:
    # Fallback to in-memory (development only)
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer'
        }
    }
    logger.info("Using In-Memory Channel Layer for WebSockets")

# WebSocket configuration
WEBSOCKET_ACCEPT_ALL = get_env_bool('WEBSOCKET_ACCEPT_ALL', 'True') if DEBUG else False

# =============================================================================
# AUTHENTICATION CONFIGURATION
# =============================================================================

# Authentication backends - Add SIWE support while maintaining Django auth
AUTHENTICATION_BACKENDS = [
    'wallet.auth.SIWEAuthenticationBackend',  # SIWE authentication
    'django.contrib.auth.backends.ModelBackend',  # Default Django auth
]

# =============================================================================
# DATABASE CONFIGURATION - ENHANCED FOR PRODUCTION
# =============================================================================

# Database URL from environment or default SQLite
DATABASE_URL = os.getenv('DATABASE_URL', f'sqlite:///{BASE_DIR}/db.sqlite3')

if DATABASE_URL.startswith('postgresql'):
    # PostgreSQL configuration for serious trading
    try:
        import dj_database_url
        DATABASES = {
            'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600)
        }
        
        # Production PostgreSQL optimizations
        DATABASES['default'].update({
            'ATOMIC_REQUESTS': True,
            'CONN_MAX_AGE': 0 if PRODUCTION_MODE else 600,  # No persistent connections in production
            'OPTIONS': {
                'MAX_CONNS': 20,
                'isolation_level': 'read committed',
                'autocommit': True,
            }
        })
        
        logger.info("Using PostgreSQL database for production trading")
        
    except ImportError:
        logger.error("dj-database-url required for PostgreSQL. Install with: pip install dj-database-url")
        raise
        
elif DATABASE_URL.startswith('sqlite'):
    # Optimized SQLite configuration for trading operations
    db_path = BASE_DIR / 'db' / ('production.sqlite3' if PRODUCTION_MODE else 'development.sqlite3')
    
    # Ensure db directory exists
    db_path.parent.mkdir(exist_ok=True)
    
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': db_path,
            'OPTIONS': {
                'timeout': 20,
                'check_same_thread': False,
                'init_command': """
                    PRAGMA journal_mode=WAL;
                    PRAGMA synchronous=NORMAL;
                    PRAGMA cache_size=1000;
                    PRAGMA temp_store=MEMORY;
                    PRAGMA mmap_size=268435456;
                    PRAGMA foreign_keys=ON;
                """,
            },
            'ATOMIC_REQUESTS': True,
        }
    }
    
    logger.info(f"Using optimized SQLite database: {db_path}")
    
else:
    # Default SQLite fallback
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# =============================================================================
# WEB3 & BLOCKCHAIN CONFIGURATION
# =============================================================================

# Testnet Configuration
TESTNET_MODE = get_env_bool('TESTNET_MODE', 'True')
DEFAULT_CHAIN_ID = get_env_int('DEFAULT_CHAIN_ID', '84532')  # Base Sepolia
TARGET_CHAINS = get_env_list('TARGET_CHAINS', '84532,11155111')
SUPPORTED_CHAINS = [int(chain_id) for chain_id in TARGET_CHAINS if chain_id]

# Engine Configuration
TRADING_MODE = os.getenv('TRADING_MODE', 'PAPER')  # PAPER | SHADOW | LIVE
ENGINE_LIVE_DATA = get_env_bool('ENGINE_LIVE_DATA', 'True')

# API Keys validation in production
ALCHEMY_API_KEY = os.getenv('ALCHEMY_API_KEY', 'demo')
BASE_ALCHEMY_API_KEY = os.getenv('BASE_ALCHEMY_API_KEY', 'demo')
ANKR_API_KEY = os.getenv('ANKR_API_KEY', '')
INFURA_PROJECT_ID = os.getenv('INFURA_PROJECT_ID', '')

# Production API key validation
if PRODUCTION_MODE:
    if ALCHEMY_API_KEY == 'demo' or not ALCHEMY_API_KEY:
        raise ValueError("Production mode requires valid ALCHEMY_API_KEY!")
    if BASE_ALCHEMY_API_KEY == 'demo' or not BASE_ALCHEMY_API_KEY:
        raise ValueError("Production mode requires valid BASE_ALCHEMY_API_KEY!")

# RPC URLs - Base Sepolia (Default)
BASE_SEPOLIA_RPC_URL = os.getenv(
    'BASE_SEPOLIA_RPC_URL', 
    f'https://base-sepolia.g.alchemy.com/v2/{BASE_ALCHEMY_API_KEY}'
)
BASE_SEPOLIA_WS_URL = os.getenv(
    'BASE_SEPOLIA_WS_URL',
    f'wss://base-sepolia.g.alchemy.com/v2/{BASE_ALCHEMY_API_KEY}'
)

# Ethereum Sepolia
SEPOLIA_RPC_URL = os.getenv(
    'SEPOLIA_RPC_URL',
    f'https://eth-sepolia.g.alchemy.com/v2/{ALCHEMY_API_KEY}'
)
SEPOLIA_WS_URL = os.getenv(
    'SEPOLIA_WS_URL',
    f'wss://eth-sepolia.g.alchemy.com/v2/{ALCHEMY_API_KEY}'
)

# =============================================================================
# SIWE (SIGN-IN WITH ETHEREUM) CONFIGURATION
# =============================================================================

# SIWE Configuration
SIWE_DOMAIN = os.getenv('SIWE_DOMAIN', 'localhost:8000')
SIWE_ALLOWED_CHAIN_IDS = get_env_list('SIWE_ALLOWED_CHAIN_IDS', '1,11155111,84532,8453')

# Session timeout for SIWE authentication (hours)
SIWE_SESSION_TIMEOUT_HOURS = get_env_int('SIWE_SESSION_TIMEOUT_HOURS', '24')

# =============================================================================
# TRADING ENGINE CONFIGURATION - ENHANCED FOR PRODUCTION
# =============================================================================

# Risk Management - Enhanced for production
MAX_PORTFOLIO_SIZE_USD = get_env_decimal(
    'MAX_PORTFOLIO_SIZE_USD', 
    '1000' if PRODUCTION_MODE else '100'  # Higher limits in production
)
MAX_POSITION_SIZE_USD = get_env_decimal(
    'MAX_POSITION_SIZE_USD', 
    '100' if PRODUCTION_MODE else '10'
)
DAILY_LOSS_LIMIT_PERCENT = get_env_decimal('DAILY_LOSS_LIMIT_PERCENT', '5.0')
CIRCUIT_BREAKER_LOSS_PERCENT = get_env_decimal('CIRCUIT_BREAKER_LOSS_PERCENT', '10.0')

# Trade Execution - Production optimized
DEFAULT_SLIPPAGE_PERCENT = get_env_decimal('DEFAULT_SLIPPAGE_PERCENT', '1.0')
MAX_GAS_PRICE_GWEI = get_env_decimal(
    'MAX_GAS_PRICE_GWEI', 
    '50' if PRODUCTION_MODE else '10'  # Higher gas limits for production
)
EXECUTION_TIMEOUT = get_env_int('EXECUTION_TIMEOUT', '30')

# Paper Trading
PAPER_MODE_SLIPPAGE = get_env_decimal('PAPER_MODE_SLIPPAGE', '0.5')
PAPER_MODE_LATENCY_MS = get_env_int('PAPER_MODE_LATENCY_MS', '200')

ENGINE_MOCK_MODE = get_env_bool('ENGINE_MOCK_MODE', 'True') and not PRODUCTION_MODE

# =============================================================================
# FAST LANE & MEMPOOL CONFIGURATION
# =============================================================================

# Fast Lane Performance Settings - Enhanced for production
FAST_LANE_TARGET_MS = get_env_int('FAST_LANE_TARGET_MS', '500')
FAST_LANE_SLA_MS = get_env_int('FAST_LANE_SLA_MS', '300')

# Risk Cache Settings - Production optimized
RISK_CACHE_TTL = get_env_int('RISK_CACHE_TTL', '3600')
RISK_CACHE_MAX_SIZE = get_env_int(
    'RISK_CACHE_MAX_SIZE', 
    '50000' if PRODUCTION_MODE else '10000'  # Larger cache in production
)

# Mempool Configuration
ENABLE_MEMPOOL_SCANNING = get_env_bool('ENABLE_MEMPOOL_SCANNING', 'True')
MEMPOOL_MAX_PENDING_TXS = get_env_int(
    'MEMPOOL_MAX_PENDING_TXS', 
    '5000' if PRODUCTION_MODE else '1000'
)
MEMPOOL_SCAN_INTERVAL_MS = get_env_int('MEMPOOL_SCAN_INTERVAL_MS', '100')

# =============================================================================
# PROVIDER MANAGEMENT
# =============================================================================

PROVIDER_HEALTH_CHECK_INTERVAL = get_env_int('PROVIDER_HEALTH_CHECK_INTERVAL', '30')
PROVIDER_FAILOVER_THRESHOLD = get_env_int('PROVIDER_FAILOVER_THRESHOLD', '3')
PROVIDER_RECOVERY_TIME = get_env_int('PROVIDER_RECOVERY_TIME', '300')

# =============================================================================
# CACHE CONFIGURATION - FIXED FOR DJANGO REDIS
# =============================================================================

# Check if django-redis is available
DJANGO_REDIS_AVAILABLE = False
if REDIS_AVAILABLE:
    try:
        import django_redis
        DJANGO_REDIS_AVAILABLE = True
        logger.info("django-redis package available")
    except ImportError:
        logger.warning("django-redis package not installed - using basic Redis backend")

if REDIS_AVAILABLE and DJANGO_REDIS_AVAILABLE:
    # Use django-redis backend with full features
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': REDIS_URL,
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'CONNECTION_POOL_KWARGS': {
                    'max_connections': 50 if PRODUCTION_MODE else 20,
                    'retry_on_timeout': True,
                    'socket_keepalive': True,
                    'socket_keepalive_options': {},
                },
                'COMPRESSOR': 'django_redis.compressors.zlib.ZlibCompressor',
                'IGNORE_EXCEPTIONS': True,
            },
            'KEY_PREFIX': f'dexbot_{TRADING_ENVIRONMENT}',
            'VERSION': 1,
            'TIMEOUT': 300,  # 5 minutes default
        }
    }
    
elif REDIS_AVAILABLE:
    # Use basic Redis backend without django-redis features
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
            'OPTIONS': {
                'CONNECTION_POOL_KWARGS': {
                    'max_connections': 50 if PRODUCTION_MODE else 20,
                    'retry_on_timeout': True,
                },
            },
            'KEY_PREFIX': f'dexbot_{TRADING_ENVIRONMENT}',
            'VERSION': 1,
            'TIMEOUT': 300,
        }
    }
    
else:
    # Fallback to in-memory cache
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': f'dexbot-{TRADING_ENVIRONMENT}',
            'OPTIONS': {
                'MAX_ENTRIES': 10000 if PRODUCTION_MODE else 1000,
            }
        }
    }
    logger.info("Using in-memory cache (no Redis available)")

# Use Redis for sessions in production if Redis is available
if PRODUCTION_MODE and REDIS_AVAILABLE:
    SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
    SESSION_CACHE_ALIAS = 'default'
    logger.info("Using Redis for session storage")

# =============================================================================
# REST FRAMEWORK CONFIGURATION
# =============================================================================

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'wallet.auth.SIWEAuthentication',  # SIWE authentication first
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
    'DATETIME_FORMAT': '%Y-%m-%dT%H:%M:%S.%fZ',
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour' if PRODUCTION_MODE else '1000/hour',
        'user': '1000/hour' if PRODUCTION_MODE else '10000/hour'
    }
}

# =============================================================================
# CORS CONFIGURATION
# =============================================================================

CORS_ALLOWED_ORIGINS = get_env_list('CORS_ALLOWED_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000')

# CORS settings - More restrictive in production
if DEBUG and not PRODUCTION_MODE:
    CORS_ALLOW_ALL_ORIGINS = True
    CORS_ALLOW_CREDENTIALS = True
else:
    CORS_ALLOW_CREDENTIALS = True
    CORS_ALLOWED_ORIGIN_REGEXES = [
        r"^https://\w+\.localhost$",
        r"^http://localhost:\d+$",
        r"^http://127\.0\.0\.1:\d+$",
    ]

# =============================================================================
# SECURITY SETTINGS - ENHANCED FOR PRODUCTION
# =============================================================================

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Enhanced security settings for production
if PRODUCTION_MODE or not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    
    # Session security
    SESSION_COOKIE_SECURE = False  # Set to True if using HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Strict'
    SESSION_EXPIRE_AT_BROWSER_CLOSE = True
    
    # CSRF protection
    CSRF_COOKIE_SECURE = False  # Set to True if using HTTPS
    CSRF_COOKIE_HTTPONLY = False
    CSRF_COOKIE_SAMESITE = 'Strict'

# =============================================================================
# CELERY CONFIGURATION - ENHANCED FOR PRODUCTION
# =============================================================================

CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', REDIS_URL)
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# Production Celery optimizations
if PRODUCTION_MODE:
    CELERY_TASK_ALWAYS_EAGER = False
    CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # For trading tasks
    CELERY_TASK_ACKS_LATE = True
    CELERY_WORKER_DISABLE_RATE_LIMITS = True
    CELERY_TASK_REJECT_ON_WORKER_LOST = True

# =============================================================================
# LOGGING CONFIGURATION - ENHANCED FOR TRADING OPERATIONS WITH UTF-8 SUPPORT
# =============================================================================

# Create logs directory structure
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

# Create subdirectories for different log types
for log_dir in ['trading', 'performance', 'security', 'debug', 'websocket']:
    (LOGS_DIR / log_dir).mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {name} {process:d} {thread:d} {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'simple': {
            'format': '[{levelname}] {asctime} {name} {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'trading': {
            'format': '[TRADE] {asctime} {levelname} {name} | {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'websocket': {
            'format': '[WS] {asctime} {levelname} {name} | {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'performance': {
            'format': '[PERF] {asctime} {levelname} {name} | {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'json': {
            'format': '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
            'datefmt': '%Y-%m-%dT%H:%M:%S',
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'stream': sys.stdout,  # Explicit stdout with UTF-8 encoding
            'formatter': 'simple',
            'level': 'INFO',
        },
        'console_debug': {
            'class': 'logging.StreamHandler',
            'stream': sys.stdout,  # Explicit stdout with UTF-8 encoding
            'formatter': 'verbose',
            'level': 'DEBUG',
            'filters': ['require_debug_true'],
        },
        'file_debug': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'debug' / 'debug.log',
            'maxBytes': 50 * 1024 * 1024,  # 50MB
            'backupCount': 10,
            'formatter': 'verbose',
            'level': 'DEBUG',
            'encoding': 'utf-8',  # UTF-8 encoding for file
        },
        'file_trading': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'trading' / 'trading.log',
            'maxBytes': 100 * 1024 * 1024,  # 100MB
            'backupCount': 20,
            'formatter': 'trading',
            'level': 'INFO',
            'encoding': 'utf-8',  # UTF-8 encoding for file
        },
        'file_websocket': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'websocket' / 'websocket.log',
            'maxBytes': 50 * 1024 * 1024,  # 50MB
            'backupCount': 10,
            'formatter': 'websocket',
            'level': 'INFO',
            'encoding': 'utf-8',  # UTF-8 encoding for file
        },
        'file_performance': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'performance' / 'performance.log',
            'maxBytes': 50 * 1024 * 1024,  # 50MB
            'backupCount': 10,
            'formatter': 'performance',
            'level': 'INFO',
            'encoding': 'utf-8',  # UTF-8 encoding for file
        },
        'file_error': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'error.log',
            'maxBytes': 50 * 1024 * 1024,  # 50MB
            'backupCount': 10,
            'formatter': 'verbose',
            'level': 'ERROR',
            'encoding': 'utf-8',  # UTF-8 encoding for file
        },
        'file_security': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'security' / 'security.log',
            'maxBytes': 50 * 1024 * 1024,  # 50MB
            'backupCount': 20,
            'formatter': 'json',
            'level': 'WARNING',
            'encoding': 'utf-8',  # UTF-8 encoding for file
        },
    },
    'root': {
        'handlers': ['console', 'file_debug', 'file_error'] if DEBUG else ['console', 'file_error'],
        'level': 'DEBUG' if DEBUG else 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file_debug'] if DEBUG else ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'channels': {
            'handlers': ['console', 'file_websocket'],
            'level': 'INFO',
            'propagate': False,
        },
        'daphne': {
            'handlers': ['console', 'file_websocket'],
            'level': 'INFO',
            'propagate': False,
        },
        'paper_trading.consumers': {
            'handlers': ['console', 'file_websocket', 'file_trading'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'paper_trading': {
            'handlers': ['console', 'file_trading', 'file_error'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'trading': {
            'handlers': ['console', 'file_trading', 'file_error'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'engine': {
            'handlers': ['console', 'file_trading', 'file_error'],
            'level': os.getenv('ENGINE_LOG_LEVEL', 'DEBUG'),
            'propagate': False,
        },
        'performance': {
            'handlers': ['file_performance'],
            'level': 'INFO',
            'propagate': False,
        },
        'security': {
            'handlers': ['file_security', 'console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'portfolio': {
            'handlers': ['console', 'file_trading', 'file_error'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'gas_optimizer': {
            'handlers': ['console', 'file_trading', 'file_performance'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'analytics': {
            'handlers': ['console', 'file_performance'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'analytics.metrics': {
            'handlers': ['console', 'file_performance'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# =============================================================================
# PROMETHEUS MONITORING CONFIGURATION
# =============================================================================

# Prometheus metrics collection
PROMETHEUS_ENABLED = True  # Set to False to disable Prometheus metrics

# Metrics collection settings
METRICS_AUTO_REFRESH_INTERVAL = 5  # seconds
METRICS_RETENTION_DAYS = 30  # days to keep historical metrics

logger.info(f"📈 Prometheus monitoring: {'Enabled' if PROMETHEUS_ENABLED else 'Disabled'}")

# =============================================================================
# INTERNATIONALIZATION
# =============================================================================

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# =============================================================================
# STATIC FILES CONFIGURATION
# =============================================================================

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# Production static file optimization
if PRODUCTION_MODE:
    STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'

# =============================================================================
# MEDIA FILES CONFIGURATION
# =============================================================================

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# =============================================================================
# DEFAULT AUTO FIELD
# =============================================================================

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# =============================================================================
# DEVELOPMENT-SPECIFIC SETTINGS
# =============================================================================

if DEBUG and TESTNET_MODE and not PRODUCTION_MODE:
    # Enable Django debug toolbar for development only
    try:
        import debug_toolbar
        INSTALLED_APPS.append('debug_toolbar')
        MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')
        INTERNAL_IPS = ['127.0.0.1', 'localhost']
        
        DEBUG_TOOLBAR_CONFIG = {
            'SHOW_TOOLBAR_CALLBACK': lambda request: True,
        }
    except ImportError:
        pass

# =============================================================================
# PRODUCTION-SPECIFIC SETTINGS
# =============================================================================

if PRODUCTION_MODE:
    # Production-specific apps
    try:
        import django_extensions
        INSTALLED_APPS.append('django_extensions')
    except ImportError:
        pass
    
    # Performance monitoring
    ENABLE_PERFORMANCE_MONITORING = True
    PERFORMANCE_MONITORING_SAMPLE_RATE = 0.1  # 10% sampling
    
    # Trading operation timeouts (stricter in production)
    TRADING_OPERATION_TIMEOUT = 60  # seconds
    GAS_OPTIMIZATION_TIMEOUT = 5    # seconds
    PORTFOLIO_UPDATE_TIMEOUT = 10   # seconds

# =============================================================================
# CONFIGURATION VALIDATION
# =============================================================================

# Validate critical settings
if PRODUCTION_MODE:
    if not ALCHEMY_API_KEY or ALCHEMY_API_KEY == 'demo':
        raise ValueError("ALCHEMY_API_KEY must be set in production!")
    
    if not BASE_ALCHEMY_API_KEY or BASE_ALCHEMY_API_KEY == 'demo':
        raise ValueError("BASE_ALCHEMY_API_KEY must be set in production!")

# Validate SIWE configuration
if not SIWE_DOMAIN:
    raise ValueError("SIWE_DOMAIN must be configured!")

if not SIWE_ALLOWED_CHAIN_IDS:
    raise ValueError("SIWE_ALLOWED_CHAIN_IDS must be configured!")

# Validate trading configuration
if PRODUCTION_MODE and TRADING_MODE == 'LIVE':
    logger.warning("⚠️  LIVE TRADING MODE ENABLED IN PRODUCTION!")
    logger.warning("⚠️  Real money will be used for trades!")

# =============================================================================
# CONFIGURATION SUMMARY LOGGING
# =============================================================================

# Log configuration summary
logger.info(f"🚀 Django settings loaded - Environment: {TRADING_ENVIRONMENT}")
logger.info(f"🔧 Configuration: DEBUG={DEBUG}, PRODUCTION_MODE={PRODUCTION_MODE}")
logger.info(f"🔗 TESTNET_MODE={TESTNET_MODE}, TRADING_MODE={TRADING_MODE}")
logger.info(f"🌐 ALLOWED_HOSTS: {ALLOWED_HOSTS}")
logger.info(f"🔑 SIWE Domain: {SIWE_DOMAIN}")
logger.info(f"⛓️  Default chain: {DEFAULT_CHAIN_ID}, Supported chains: {SIWE_ALLOWED_CHAIN_IDS}")
logger.info(f"📊 Engine live data: {ENGINE_LIVE_DATA}")
logger.info(f"💾 Database: {'PostgreSQL' if 'postgresql' in DATABASE_URL else 'SQLite'}")
logger.info(f"🗄️  Cache: {'Redis' if REDIS_AVAILABLE else 'Memory'}")
logger.info(f"📡 WebSocket Layer: {'Redis Channel Layer' if REDIS_AVAILABLE else 'In-Memory Channel Layer'}")
logger.info(f"🔄 ASGI Application: {ASGI_APPLICATION}")

if PRODUCTION_MODE:
    logger.info("🏭 Production mode optimizations enabled")
    logger.info(f"💰 Max portfolio: ${MAX_PORTFOLIO_SIZE_USD}, Max position: ${MAX_POSITION_SIZE_USD}")
    logger.info(f"⛽ Max gas price: {MAX_GAS_PRICE_GWEI} gwei")
    logger.info(f"🕒 Fast lane target: {FAST_LANE_TARGET_MS}ms")
    
# PTphase3 specific logging
logger.info("✅ PTphase3 WebSocket Support Configured")
logger.info(f"   - Django Channels: Installed")
logger.info(f"   - Channel Layer: {'Redis' if REDIS_AVAILABLE else 'In-Memory'}")
logger.info(f"   - WebSocket Logging: {LOGS_DIR / 'websocket'}")