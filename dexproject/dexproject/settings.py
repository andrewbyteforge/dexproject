"""
Enhanced Django settings for dexproject with Web3 integration and SIWE support

This settings file includes Web3 configuration, testnet support, SIWE wallet
authentication, and enhanced trading engine settings for both development 
and production.

UPDATED: Phase 5.1C - Fixed ALLOWED_HOSTS error and environment variable loading

File: dexproject/dexproject/settings.py
"""

import os
from pathlib import Path
import logging

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
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
# CORE DJANGO SETTINGS
# =============================================================================

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-test-key-for-development-only')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = get_env_bool('DEBUG', 'True')

# ALLOWED_HOSTS configuration - Fixed to handle empty environment variables properly
ALLOWED_HOSTS = ['localhost', '127.0.0.1']
additional_hosts = get_env_list('ALLOWED_HOSTS')
if additional_hosts:
    ALLOWED_HOSTS.extend(additional_hosts)

# If DEBUG is False and no additional hosts specified, allow all for development
if not DEBUG and len(ALLOWED_HOSTS) <= 2:  # Only localhost and 127.0.0.1
    ALLOWED_HOSTS.append('*')  # Allow all hosts in development when DEBUG=False
    logger.warning("DEBUG=False with minimal ALLOWED_HOSTS - adding '*' for development")

# Application definition
DJANGO_APPS = [
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
]

LOCAL_APPS = [
    'shared',       # Add shared app for common utilities
    'dashboard',
    'trading',
    'risk',
    'wallet',
    'analytics',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

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

WSGI_APPLICATION = 'dexproject.wsgi.application'
ASGI_APPLICATION = 'dexproject.asgi.application'

# =============================================================================
# AUTHENTICATION CONFIGURATION
# =============================================================================

# Authentication backends - Add SIWE support while maintaining Django auth
AUTHENTICATION_BACKENDS = [
    'wallet.auth.SIWEAuthenticationBackend',  # SIWE authentication
    'django.contrib.auth.backends.ModelBackend',  # Default Django auth
]

# =============================================================================
# DATABASE CONFIGURATION
# =============================================================================

# Database URL from environment or default SQLite
DATABASE_URL = os.getenv('DATABASE_URL', f'sqlite:///{BASE_DIR}/db.sqlite3')

if DATABASE_URL.startswith('sqlite'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
elif DATABASE_URL.startswith('postgresql'):
    # Parse PostgreSQL URL
    import dj_database_url
    DATABASES = {
        'default': dj_database_url.parse(DATABASE_URL)
    }
else:
    # Default SQLite
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

# Engine Configuration
TRADING_MODE = os.getenv('TRADING_MODE', 'PAPER')  # PAPER | SHADOW | LIVE
ENGINE_LIVE_DATA = get_env_bool('ENGINE_LIVE_DATA', 'True')

# API Keys
ALCHEMY_API_KEY = os.getenv('ALCHEMY_API_KEY', 'demo')
BASE_ALCHEMY_API_KEY = os.getenv('BASE_ALCHEMY_API_KEY', 'demo')
ANKR_API_KEY = os.getenv('ANKR_API_KEY', '')
INFURA_PROJECT_ID = os.getenv('INFURA_PROJECT_ID', '')

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
# TRADING ENGINE CONFIGURATION
# =============================================================================

# Risk Management
MAX_PORTFOLIO_SIZE_USD = get_env_decimal('MAX_PORTFOLIO_SIZE_USD', '100')
MAX_POSITION_SIZE_USD = get_env_decimal('MAX_POSITION_SIZE_USD', '10')
DAILY_LOSS_LIMIT_PERCENT = get_env_decimal('DAILY_LOSS_LIMIT_PERCENT', '5.0')
CIRCUIT_BREAKER_LOSS_PERCENT = get_env_decimal('CIRCUIT_BREAKER_LOSS_PERCENT', '10.0')

# Trade Execution
DEFAULT_SLIPPAGE_PERCENT = get_env_decimal('DEFAULT_SLIPPAGE_PERCENT', '1.0')
MAX_GAS_PRICE_GWEI = get_env_decimal('MAX_GAS_PRICE_GWEI', '10')
EXECUTION_TIMEOUT = get_env_int('EXECUTION_TIMEOUT', '30')

# Paper Trading
PAPER_MODE_SLIPPAGE = get_env_decimal('PAPER_MODE_SLIPPAGE', '0.5')
PAPER_MODE_LATENCY_MS = get_env_int('PAPER_MODE_LATENCY_MS', '200')

# =============================================================================
# FAST LANE & MEMPOOL CONFIGURATION
# =============================================================================

# Fast Lane Performance Settings
FAST_LANE_TARGET_MS = get_env_int('FAST_LANE_TARGET_MS', '500')
FAST_LANE_SLA_MS = get_env_int('FAST_LANE_SLA_MS', '300')

# Risk Cache Settings
RISK_CACHE_TTL = get_env_int('RISK_CACHE_TTL', '3600')
RISK_CACHE_MAX_SIZE = get_env_int('RISK_CACHE_MAX_SIZE', '10000')

# Mempool Configuration
ENABLE_MEMPOOL_SCANNING = get_env_bool('ENABLE_MEMPOOL_SCANNING', 'True')
MEMPOOL_MAX_PENDING_TXS = get_env_int('MEMPOOL_MAX_PENDING_TXS', '1000')
MEMPOOL_SCAN_INTERVAL_MS = get_env_int('MEMPOOL_SCAN_INTERVAL_MS', '100')

# =============================================================================
# PROVIDER MANAGEMENT
# =============================================================================

PROVIDER_HEALTH_CHECK_INTERVAL = get_env_int('PROVIDER_HEALTH_CHECK_INTERVAL', '30')
PROVIDER_FAILOVER_THRESHOLD = get_env_int('PROVIDER_FAILOVER_THRESHOLD', '3')
PROVIDER_RECOVERY_TIME = get_env_int('PROVIDER_RECOVERY_TIME', '300')

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
}

# =============================================================================
# CORS CONFIGURATION
# =============================================================================

CORS_ALLOWED_ORIGINS = get_env_list('CORS_ALLOWED_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000')

# CORS settings for development
if DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True
    CORS_ALLOW_CREDENTIALS = True

# =============================================================================
# SECURITY SETTINGS
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

# Security settings for production
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

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
# CACHE CONFIGURATION
# =============================================================================

REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# Check if Redis is available
REDIS_AVAILABLE = True
try:
    import redis
    r = redis.Redis.from_url(REDIS_URL, socket_connect_timeout=1)
    r.ping()
except Exception:
    REDIS_AVAILABLE = False
    logger.warning("Redis not available - falling back to in-memory cache")

if REDIS_AVAILABLE:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
            'KEY_PREFIX': 'dexproject',
            'TIMEOUT': 300,
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'unique-snowflake',
        }
    }

# =============================================================================
# CELERY CONFIGURATION
# =============================================================================

CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', REDIS_URL)
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'django.log',
            'formatter': 'verbose',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'trading': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'engine': {
            'handlers': ['console', 'file'],
            'level': os.getenv('ENGINE_LOG_LEVEL', 'DEBUG'),
            'propagate': False,
        },
    },
}

# Create logs directory if it doesn't exist
(BASE_DIR / 'logs').mkdir(exist_ok=True)

# =============================================================================
# DEVELOPMENT-SPECIFIC SETTINGS
# =============================================================================

if DEBUG and TESTNET_MODE:
    # Enable Django debug toolbar for development
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
# CONFIGURATION VALIDATION
# =============================================================================

# Validate critical settings
if not ALCHEMY_API_KEY or ALCHEMY_API_KEY == 'demo':
    if not DEBUG:
        raise ValueError("ALCHEMY_API_KEY must be set in production!")

# Validate SIWE configuration
if not SIWE_DOMAIN:
    raise ValueError("SIWE_DOMAIN must be configured!")

if not SIWE_ALLOWED_CHAIN_IDS:
    raise ValueError("SIWE_ALLOWED_CHAIN_IDS must be configured!")

# Log configuration summary
logger.info(f"Django settings loaded - DEBUG: {DEBUG}, TESTNET_MODE: {TESTNET_MODE}")
logger.info(f"ALLOWED_HOSTS: {ALLOWED_HOSTS}")
logger.info(f"SIWE Domain: {SIWE_DOMAIN}, Supported chains: {SIWE_ALLOWED_CHAIN_IDS}")
logger.info(f"Default chain: {DEFAULT_CHAIN_ID}, Engine live data: {ENGINE_LIVE_DATA}")