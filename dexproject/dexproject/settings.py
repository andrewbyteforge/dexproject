"""
Enhanced Django settings for dexproject with Web3 integration and SIWE support

This settings file includes Web3 configuration, testnet support, SIWE wallet
authentication, and enhanced trading engine settings for both development 
and production.

UPDATED: Phase 5.1B - Complete SIWE wallet authentication integration

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
    return os.getenv(key, default).lower() == 'true'

# =============================================================================
# CORE DJANGO SETTINGS
# =============================================================================

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-test-key-for-development-only')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = get_env_bool('DEBUG', 'True')

ALLOWED_HOSTS = ['localhost', '127.0.0.1'] + os.getenv('ALLOWED_HOSTS', '').split(',')

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

# Default to SQLite for development, PostgreSQL for production
DATABASES = {
    'default': {
        'ENGINE': os.getenv('DB_ENGINE', 'django.db.backends.sqlite3'),
        'NAME': os.getenv('DB_NAME', BASE_DIR / 'db.sqlite3'),
        'USER': os.getenv('DB_USER', ''),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', ''),
        'PORT': os.getenv('DB_PORT', ''),
    }
}

# =============================================================================
# REDIS AND CELERY CONFIGURATION
# =============================================================================

REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# Celery Configuration
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_ENABLE_UTC = True

# Enhanced Celery settings for trading
CELERY_TASK_ROUTES = {
    'risk.*': {'queue': 'risk.urgent'},
    'trading.*': {'queue': 'execution.critical'},
    'analytics.*': {'queue': 'analytics.background'},
    'dashboard.*': {'queue': 'analytics.background'},
    'wallet.*': {'queue': 'wallet.auth'},
}

# =============================================================================
# SIWE (SIGN-IN WITH ETHEREUM) CONFIGURATION
# Phase 5.1B Implementation
# =============================================================================

# SIWE Domain Configuration
SIWE_DOMAIN = os.getenv('SIWE_DOMAIN', 'localhost:8000')
SIWE_STATEMENT = "Sign in to DEX Auto-Trading Bot"
SIWE_VERSION = "1"

# SIWE Supported Chain IDs
SIWE_ALLOWED_CHAIN_IDS = [
    84532,      # Base Sepolia (primary for development)
    11155111,   # Ethereum Sepolia (testnet)
    1,          # Ethereum Mainnet (production)
    8453,       # Base Mainnet (production)
]

# SIWE Session Management
SIWE_SESSION_TTL_SECONDS = get_env_int('SIWE_SESSION_TTL_SECONDS', '86400')  # 24 hours
SIWE_NONCE_TTL_SECONDS = get_env_int('SIWE_NONCE_TTL_SECONDS', '600')       # 10 minutes
SIWE_MAX_SESSIONS_PER_USER = get_env_int('SIWE_MAX_SESSIONS_PER_USER', '5')

# SIWE Security Settings
SIWE_REQUIRE_HTTPS = not DEBUG  # Require HTTPS in production
SIWE_MAX_CLOCK_SKEW_SECONDS = 300  # 5 minutes tolerance for time validation

# =============================================================================
# SESSION CONFIGURATION (Enhanced for SIWE)
# =============================================================================

# Session engine configuration
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = SIWE_SESSION_TTL_SECONDS
SESSION_COOKIE_NAME = 'dex_sessionid'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_SAVE_EVERY_REQUEST = True  # Update session on every request for SIWE

# Session security
SESSION_COOKIE_SECURE = not DEBUG  # Secure cookies in production
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# Session rotation on authentication (security best practice)
SESSION_COOKIE_ROTATE_ON_AUTH = True

# =============================================================================
# CSRF CONFIGURATION (Enhanced for wallet connections)
# =============================================================================

# CSRF Token settings
CSRF_COOKIE_NAME = 'dex_csrftoken'
CSRF_COOKIE_HTTPONLY = False  # JavaScript needs access for wallet interactions
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_AGE = 31449600  # 1 year

# Trusted origins for wallet connections
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'https://localhost:8000',
    'https://127.0.0.1:8000',
] + [f"https://{host}" for host in ALLOWED_HOSTS if host not in ['*', 'localhost', '127.0.0.1']]

# Exempt SIWE auth endpoints from CSRF (they use signature verification)
CSRF_EXEMPT_URLS = [
    '/api/wallet/auth/siwe/generate/',
    '/api/wallet/auth/siwe/authenticate/',
]

# =============================================================================
# CORS CONFIGURATION (For wallet connections)
# =============================================================================

# CORS settings for wallet integration
CORS_ALLOWED_ORIGINS = [
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'https://localhost:8000',
    'https://127.0.0.1:8000',
]

# Allow credentials for SIWE authentication
CORS_ALLOW_CREDENTIALS = True

# Specific headers for wallet operations
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'x-wallet-address',  # Custom header for wallet identification
    'x-chain-id',        # Custom header for chain identification
]

# =============================================================================
# WEB3 AND BLOCKCHAIN CONFIGURATION
# =============================================================================

# Testnet mode configuration
TESTNET_MODE = get_env_bool('TESTNET_MODE', 'True')

# Default chain configuration
DEFAULT_CHAIN_ID = 84532 if TESTNET_MODE else 8453  # Base Sepolia or Base Mainnet
SUPPORTED_CHAINS = SIWE_ALLOWED_CHAIN_IDS

# Blockchain API Configuration
ALCHEMY_API_KEY = os.getenv('ALCHEMY_API_KEY', 'demo')
ANKR_API_KEY = os.getenv('ANKR_API_KEY', '')
INFURA_PROJECT_ID = os.getenv('INFURA_PROJECT_ID', '')

# Blockchain RPC URLs
if TESTNET_MODE:
    # Testnet URLs
    BASE_RPC_URL = f"https://base-sepolia.g.alchemy.com/v2/{ALCHEMY_API_KEY}"
    ETHEREUM_RPC_URL = f"https://eth-sepolia.g.alchemy.com/v2/{ALCHEMY_API_KEY}"
else:
    # Mainnet URLs  
    BASE_RPC_URL = f"https://base-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}"
    ETHEREUM_RPC_URL = f"https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}"

# Chain configurations
CHAIN_CONFIGS = {
    84532: {  # Base Sepolia
        'name': 'Base Sepolia',
        'rpc_url': BASE_RPC_URL,
        'testnet': True,
        'block_explorer': 'https://sepolia.basescan.org',
    },
    11155111: {  # Ethereum Sepolia
        'name': 'Ethereum Sepolia', 
        'rpc_url': ETHEREUM_RPC_URL,
        'testnet': True,
        'block_explorer': 'https://sepolia.etherscan.io',
    },
    8453: {  # Base Mainnet
        'name': 'Base',
        'rpc_url': f"https://base-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}",
        'testnet': False,
        'block_explorer': 'https://basescan.org',
    },
    1: {  # Ethereum Mainnet
        'name': 'Ethereum',
        'rpc_url': f"https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}",
        'testnet': False,
        'block_explorer': 'https://etherscan.io',
    },
}


# =============================================================================
# WALLET BALANCE TRACKING CONFIGURATION - NEW FOR PHASE 5.1C
# =============================================================================

# Default tracked tokens when database has no tracked tokens configured
# This provides a fallback list for each supported chain
DEFAULT_TRACKED_TOKENS = {
    # Base Sepolia (84532) - Primary testing chain
    84532: [
        {
            'address': '0x4200000000000000000000000000000000000006',
            'symbol': 'WETH',
            'name': 'Wrapped Ether',
            'decimals': 18
        },
        {
            'address': '0x036CbD53842c5426634e7929541eC2318f3dCF7e',
            'symbol': 'USDbC',
            'name': 'USD Base Coin (Sepolia)',
            'decimals': 6
        }
    ],
    
    # Ethereum Sepolia (11155111) - Secondary testing chain  
    11155111: [
        {
            'address': '0xfFf9976782d46CC05630D1f6eBAb18b2324d6B14',
            'symbol': 'WETH',
            'name': 'Wrapped Ether',
            'decimals': 18
        },
        {
            'address': '0x6f14C02Fc1F78322cFd7d707aB90f18baD3B54f5',
            'symbol': 'USDC',
            'name': 'USD Coin (Sepolia)',
            'decimals': 6
        },
        {
            'address': '0x3e622317f8C93f7328350cF0B56d9eD4C620C5d6',
            'symbol': 'DAI',
            'name': 'Dai Stablecoin (Sepolia)',
            'decimals': 18
        }
    ],
    
    # Arbitrum Sepolia (421614) - Additional testing chain
    421614: [
        {
            'address': '0x980B62Da83eFf3D4576C647993b0c1D7faf17c73',
            'symbol': 'WETH',
            'name': 'Wrapped Ether',
            'decimals': 18
        }
    ]
}

# Balance tracking configuration
WALLET_BALANCE_CACHE_TTL = 15  # Cache balance data for 15 seconds
WALLET_BALANCE_MAX_TOKENS = 20  # Maximum tokens to track per wallet
WALLET_BALANCE_TIMEOUT = 30  # Timeout for balance queries in seconds

# =============================================================================
# LOGGING CONFIGURATION (Enhanced for SIWE)
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
        'wallet': {
            'format': '[WALLET] {levelname} {asctime} {name} {message}',
            'style': '{',
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
            'level': 'INFO' if not DEBUG else 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'django.log',
            'formatter': 'verbose',
        },
        'wallet_file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler', 
            'filename': BASE_DIR / 'logs' / 'wallet.log',
            'formatter': 'wallet',
        },
        'siwe_file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'siwe.log', 
            'formatter': 'wallet',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': True,
        },
        'wallet': {
            'handlers': ['console', 'wallet_file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'wallet.auth': {
            'handlers': ['console', 'siwe_file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'wallet.services': {
            'handlers': ['console', 'siwe_file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'engine': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'trading': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'risk': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Create logs directory if it doesn't exist
(BASE_DIR / 'logs').mkdir(exist_ok=True)

# =============================================================================
# REST FRAMEWORK CONFIGURATION (Enhanced for wallet API)
# =============================================================================

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'wallet.auth.SIWETokenAuthentication',  # Custom SIWE token auth
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.FormParser',
        'rest_framework.parsers.MultiPartParser',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',      # Anonymous users (SIWE generation)
        'user': '1000/hour',     # Authenticated users
        'wallet': '200/hour',    # Wallet operations
    },
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    # 'EXCEPTION_HANDLER': 'shared.api.exception_handler',
}

# =============================================================================
# TRADING ENGINE CONFIGURATION
# =============================================================================

# Engine modes
ENGINE_MODE = os.getenv('ENGINE_MODE', 'development')  # development, staging, production
ENGINE_LIVE_DATA = get_env_bool('ENGINE_LIVE_DATA', 'True')

# Fast Lane engine settings
FAST_LANE_ENABLED = True
FAST_LANE_MAX_EXECUTION_TIME_MS = get_env_int('FAST_LANE_MAX_EXECUTION_TIME_MS', '500')
FAST_LANE_MAX_GAS_GWEI = get_env_decimal('FAST_LANE_MAX_GAS_GWEI', '100.0')

# Smart Lane engine settings  
SMART_LANE_ENABLED = True
SMART_LANE_MAX_ANALYSIS_TIME_MS = get_env_int('SMART_LANE_MAX_ANALYSIS_TIME_MS', '5000')
SMART_LANE_MIN_LIQUIDITY_USD = get_env_decimal('SMART_LANE_MIN_LIQUIDITY_USD', '10000.0')

# Risk management
RISK_MAX_POSITION_SIZE_ETH = get_env_decimal('RISK_MAX_POSITION_SIZE_ETH', '1.0')
RISK_MAX_SLIPPAGE_PERCENT = get_env_decimal('RISK_MAX_SLIPPAGE_PERCENT', '5.0')
RISK_HONEYPOT_CHECK_ENABLED = True

# Mempool monitoring
MEMPOOL_MONITORING_ENABLED = ENGINE_LIVE_DATA
MEMPOOL_MIN_VALUE_ETH = get_env_decimal('MEMPOOL_MIN_VALUE_ETH', '0.01')
MEMPOOL_MAX_AGE_SECONDS = get_env_int('MEMPOOL_MAX_AGE_SECONDS', '300')

# =============================================================================
# SECURITY CONFIGURATION (Enhanced for production)
# =============================================================================

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Additional security headers
if not DEBUG:
    # Production security settings
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    
    # Force HTTPS in production
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

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
    
    # Allow all origins for CORS in development
    CORS_ALLOW_ALL_ORIGINS = True

# =============================================================================
# CACHE CONFIGURATION
# =============================================================================

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
            'KEY_PREFIX': 'dex_cache',
            'TIMEOUT': 300,  # 5 minutes default
        },
        'session': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
            'KEY_PREFIX': 'dex_session',
            'TIMEOUT': SIWE_SESSION_TTL_SECONDS,
        },
        'wallet': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
            'KEY_PREFIX': 'dex_wallet',
            'TIMEOUT': 3600,  # 1 hour for wallet data
        },
    }
else:
    # Fallback to in-memory cache when Redis is not available
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'dex_cache',
            'TIMEOUT': 300,
        },
        'session': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'dex_session',
            'TIMEOUT': SIWE_SESSION_TTL_SECONDS,
        },
        'wallet': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'dex_wallet',
            'TIMEOUT': 3600,
        },
    }

# =============================================================================
# EMAIL CONFIGURATION (For notifications)
# =============================================================================

if DEBUG:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
    EMAIL_PORT = get_env_int('EMAIL_PORT', '587')
    EMAIL_USE_TLS = True
    EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')

DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'noreply@dex-trading-bot.com')

# =============================================================================
# CUSTOM SETTINGS VALIDATION
# =============================================================================

# Validate critical settings
if not SECRET_KEY or SECRET_KEY == 'django-insecure-test-key-for-development-only':
    if not DEBUG:
        raise ValueError("SECRET_KEY must be set in production!")

if not ALCHEMY_API_KEY or ALCHEMY_API_KEY == 'demo':
    if not DEBUG:
        raise ValueError("ALCHEMY_API_KEY must be set in production!")

# Validate SIWE configuration
if not SIWE_DOMAIN:
    raise ValueError("SIWE_DOMAIN must be configured!")

if not SIWE_ALLOWED_CHAIN_IDS:
    raise ValueError("SIWE_ALLOWED_CHAIN_IDS must be configured!")

# Log configuration summary
import logging
logger = logging.getLogger(__name__)
logger.info(f"Django settings loaded - DEBUG: {DEBUG}, TESTNET_MODE: {TESTNET_MODE}")
logger.info(f"SIWE Domain: {SIWE_DOMAIN}, Supported chains: {SIWE_ALLOWED_CHAIN_IDS}")
logger.info(f"Default chain: {DEFAULT_CHAIN_ID}, Engine live data: {ENGINE_LIVE_DATA}")