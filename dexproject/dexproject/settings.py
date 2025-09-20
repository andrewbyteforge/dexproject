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

# =============================================================================
# CORE DJANGO SETTINGS
# =============================================================================

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-test-key-for-development-only')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'

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
    'wallet.*': {'queue': 'risk.normal'},
}

CELERY_TASK_TIME_LIMIT = 300  # 5 minutes max
CELERY_TASK_SOFT_TIME_LIMIT = 240  # 4 minutes soft limit
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # Important for trading tasks
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_DISABLE_RATE_LIMITS = False

# =============================================================================
# TRADING ENGINE CONFIGURATION
# =============================================================================

# Core Trading Settings
TRADING_MODE = os.getenv('TRADING_MODE', 'PAPER')  # 'PAPER' or 'LIVE'
ENABLE_MOCK_MODE = os.getenv('ENABLE_MOCK_MODE', 'True').lower() == 'true'
TESTNET_MODE = os.getenv('TESTNET_MODE', 'True').lower() == 'true'

# Default chain configuration
DEFAULT_CHAIN_ID = int(os.getenv('DEFAULT_CHAIN_ID', '84532'))  # Base Sepolia default

# Supported chains (can be overridden by environment)
if TESTNET_MODE:
    # Testnet chains
    SUPPORTED_CHAINS = [
        11155111,  # Sepolia
        84532,     # Base Sepolia  
        421614,    # Arbitrum Sepolia
    ]
else:
    # Mainnet chains
    SUPPORTED_CHAINS = [
        1,         # Ethereum
        8453,      # Base
        42161,     # Arbitrum
    ]

# Risk Assessment Configuration
RISK_TIMEOUT_SECONDS = int(os.getenv('RISK_TIMEOUT_SECONDS', '10'))
RISK_PARALLEL_CHECKS = int(os.getenv('RISK_PARALLEL_CHECKS', '4'))
RISK_MAX_RETRIES = int(os.getenv('RISK_MAX_RETRIES', '3'))

# Portfolio and Risk Management
MAX_PORTFOLIO_SIZE_USD = Decimal(os.getenv('MAX_PORTFOLIO_SIZE_USD', '1000.0' if TESTNET_MODE else '10000.0'))
MAX_POSITION_SIZE_USD = Decimal(os.getenv('MAX_POSITION_SIZE_USD', '100.0' if TESTNET_MODE else '1000.0'))
DAILY_LOSS_LIMIT_PERCENT = Decimal(os.getenv('DAILY_LOSS_LIMIT_PERCENT', '50.0' if TESTNET_MODE else '5.0'))
CIRCUIT_BREAKER_LOSS_PERCENT = Decimal(os.getenv('CIRCUIT_BREAKER_LOSS_PERCENT', '75.0' if TESTNET_MODE else '10.0'))

# Gas and Execution Configuration
DEFAULT_SLIPPAGE_PERCENT = Decimal(os.getenv('DEFAULT_SLIPPAGE_PERCENT', '5.0' if TESTNET_MODE else '1.0'))
MAX_GAS_PRICE_GWEI = Decimal(os.getenv('MAX_GAS_PRICE_GWEI', '100.0' if TESTNET_MODE else '50.0'))
EXECUTION_TIMEOUT_SECONDS = int(os.getenv('EXECUTION_TIMEOUT_SECONDS', '60' if TESTNET_MODE else '30'))

# =============================================================================
# FAST LANE ENGINE CONFIGURATION
# =============================================================================

# Engine Operation Mode
ENGINE_MOCK_MODE = os.getenv('ENGINE_MOCK_MODE', 'True').lower() == 'true'

# Fast Lane Performance Configuration
FAST_LANE_ENABLED = os.getenv('FAST_LANE_ENABLED', 'True').lower() == 'true'
FAST_LANE_TARGET_MS = int(os.getenv('FAST_LANE_TARGET_MS', '500'))
FAST_LANE_SLA_MS = int(os.getenv('FAST_LANE_SLA_MS', '300'))

# Engine Integration Settings
ENGINE_AUTO_START = os.getenv('ENGINE_AUTO_START', 'False').lower() == 'true'
ENGINE_DEFAULT_CHAIN = int(os.getenv('ENGINE_DEFAULT_CHAIN', '84532'))  # Base Sepolia

# Risk Cache Configuration for Dashboard
RISK_CACHE_TTL = int(os.getenv('RISK_CACHE_TTL', '3600'))
RISK_CACHE_MAX_SIZE = int(os.getenv('RISK_CACHE_MAX_SIZE', '10000'))

# Circuit Breaker Configuration
ENGINE_CIRCUIT_BREAKER_THRESHOLD = int(os.getenv('ENGINE_CIRCUIT_BREAKER_THRESHOLD', '5'))
ENGINE_CIRCUIT_BREAKER_RECOVERY_TIME = int(os.getenv('ENGINE_CIRCUIT_BREAKER_RECOVERY_TIME', '60'))

# Dashboard Metrics Configuration
DASHBOARD_METRICS_CACHE_TIMEOUT = int(os.getenv('DASHBOARD_METRICS_CACHE_TIMEOUT', '30'))
DASHBOARD_SSE_UPDATE_INTERVAL = int(os.getenv('DASHBOARD_SSE_UPDATE_INTERVAL', '2'))

# Phase Development Control - Define these variables early
SMART_LANE_ENABLED = os.getenv('SMART_LANE_ENABLED', 'True').lower() == 'true'  # Phase 5
MEMPOOL_MONITORING_ENABLED = os.getenv('MEMPOOL_MONITORING_ENABLED', 'True').lower() == 'true'  # Phase 3

# Development and Testing
FORCE_MOCK_DATA = os.getenv('FORCE_MOCK_DATA', 'False').lower() == 'true'
ENGINE_DEBUG_LOGGING = os.getenv('ENGINE_DEBUG_LOGGING', 'False').lower() == 'true'

# Additional Phase 5 settings
SMART_LANE_MOCK_MODE = os.getenv('SMART_LANE_MOCK_MODE', 'True').lower() == 'true'
SMART_LANE_CACHE_TTL = int(os.getenv('SMART_LANE_CACHE_TTL', '300'))  # 5 minutes cache

# SSE Configuration for dashboard
SSE_MAX_ITERATIONS = int(os.getenv('SSE_MAX_ITERATIONS', '150'))  # Allow longer SSE streams

# =============================================================================
# BLOCKCHAIN RPC CONFIGURATION 
# =============================================================================

# API Keys for Web3 providers
ALCHEMY_API_KEY = os.getenv('ALCHEMY_API_KEY', '')
INFURA_PROJECT_ID = os.getenv('INFURA_PROJECT_ID', '')
ANKR_API_KEY = os.getenv('ANKR_API_KEY', '')

# Mainnet RPC URLs
ETH_RPC_URL = os.getenv('ETH_RPC_URL', f'https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}' if ALCHEMY_API_KEY else 'https://cloudflare-eth.com')
ETH_RPC_URL_FALLBACK = os.getenv('ETH_RPC_URL_FALLBACK', 'https://rpc.ankr.com/eth')

BASE_RPC_URL = os.getenv('BASE_RPC_URL', f'https://base-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}' if ALCHEMY_API_KEY else 'https://mainnet.base.org')
BASE_RPC_URL_FALLBACK = os.getenv('BASE_RPC_URL_FALLBACK', 'https://base.blockpi.network/v1/rpc/public')

ARBITRUM_RPC_URL = os.getenv('ARBITRUM_RPC_URL', 'https://arb1.arbitrum.io/rpc')
ARBITRUM_RPC_URL_FALLBACK = os.getenv('ARBITRUM_RPC_URL_FALLBACK', 'https://arbitrum.blockpi.network/v1/rpc/public')

# Testnet RPC URLs (used when TESTNET_MODE=True)
SEPOLIA_RPC_URL = os.getenv('SEPOLIA_RPC_URL', f'https://eth-sepolia.g.alchemy.com/v2/{ALCHEMY_API_KEY}' if ALCHEMY_API_KEY else 'https://rpc.sepolia.org')
BASE_SEPOLIA_RPC_URL = os.getenv('BASE_SEPOLIA_RPC_URL', f'https://base-sepolia.g.alchemy.com/v2/{ALCHEMY_API_KEY}' if ALCHEMY_API_KEY else 'https://sepolia.base.org')
ARBITRUM_SEPOLIA_RPC_URL = os.getenv('ARBITRUM_SEPOLIA_RPC_URL', 'https://sepolia-rollup.arbitrum.io/rpc')

# =============================================================================
# DEX ROUTER AND CONTRACT ADDRESSES
# =============================================================================

if TESTNET_MODE:
    # Testnet contract addresses
    UNISWAP_V2_ROUTER = '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D'  # Same on testnets
    UNISWAP_V3_ROUTER = '0xE592427A0AEce92De3Edee1F18E0157C05861564'  # Same on testnets
    
    # Base Sepolia specific
    BASE_UNISWAP_V3_ROUTER = '0x2626664c2603336E57B271c5C0b26F421741e481'
    BASE_UNISWAP_V3_FACTORY = '0x4752ba5dbc23f44d87826276bf6fd6b1c372ad24'
else:
    # Mainnet contract addresses  
    UNISWAP_V2_ROUTER = '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D'
    UNISWAP_V3_ROUTER = '0xE592427A0AEce92De3Edee1F18E0157C05861564'
    
    # Base mainnet specific
    BASE_UNISWAP_V3_ROUTER = '0x2626664c2603336E57B271c5C0b26F421741e481'
    BASE_UNISWAP_V3_FACTORY = '0x33128a8fC17869897dcE68Ed026d694621f6FDfD'

# =============================================================================
# WALLET AND SIWE CONFIGURATION
# =============================================================================

# Legacy wallet management (Phase 5.1A and earlier)
WALLET_PRIVATE_KEY = os.getenv('WALLET_PRIVATE_KEY', '')  # Private key for trading wallet
WALLET_DAILY_LIMIT_USD = Decimal(os.getenv('WALLET_DAILY_LIMIT', '500.0' if TESTNET_MODE else '5000.0'))
WALLET_TX_LIMIT_USD = Decimal(os.getenv('WALLET_TX_LIMIT', '50.0' if TESTNET_MODE else '500.0'))

# Hardware wallet support (future)
HARDWARE_WALLET_SUPPORT = os.getenv('HARDWARE_WALLET_SUPPORT', 'False').lower() == 'true'
REQUIRE_HARDWARE_WALLET = os.getenv('REQUIRE_HARDWARE_WALLET', 'False').lower() == 'true'

# Phase 5.1B: SIWE (Sign-In with Ethereum) Configuration
SIWE_DOMAIN = os.getenv('SIWE_DOMAIN', 'localhost:8000')
SIWE_STATEMENT = "Sign in to DEX Auto-Trading Bot"
SIWE_SESSION_EXPIRES_HOURS = int(os.getenv('SIWE_SESSION_EXPIRES_HOURS', '24'))

# Supported blockchain networks for wallet integration
SUPPORTED_CHAINS_CONFIG = {
    84532: {  # Base Sepolia (Development)
        'name': 'Base Sepolia',
        'rpc_url': 'https://sepolia.base.org',
        'is_testnet': True,
        'native_currency': 'ETH',
        'explorer_url': 'https://sepolia.basescan.org'
    },
    1: {  # Ethereum Mainnet
        'name': 'Ethereum Mainnet', 
        'rpc_url': f'https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}' if ALCHEMY_API_KEY else 'https://ethereum.publicnode.com',
        'is_testnet': False,
        'native_currency': 'ETH',
        'explorer_url': 'https://etherscan.io'
    },
    8453: {  # Base Mainnet
        'name': 'Base Mainnet',
        'rpc_url': f'https://base-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}' if ALCHEMY_API_KEY else 'https://mainnet.base.org',
        'is_testnet': False,
        'native_currency': 'ETH', 
        'explorer_url': 'https://basescan.org'
    }
}

# Default chain for development
DEFAULT_CHAIN_ID = 84532  # Base Sepolia

# Wallet Security Settings
WALLET_MAX_DAILY_LIMIT_USD = Decimal(os.getenv('WALLET_MAX_DAILY_LIMIT_USD', '10000'))
WALLET_MAX_TRANSACTION_LIMIT_USD = Decimal(os.getenv('WALLET_MAX_TRANSACTION_LIMIT_USD', '1000'))
WALLET_REQUIRE_CONFIRMATION = os.getenv('WALLET_REQUIRE_CONFIRMATION', 'True').lower() == 'true'

# Balance refresh settings
WALLET_BALANCE_CACHE_MINUTES = int(os.getenv('WALLET_BALANCE_CACHE_MINUTES', '5'))
WALLET_BALANCE_STALE_MINUTES = int(os.getenv('WALLET_BALANCE_STALE_MINUTES', '10'))

# Web3 provider settings
WEB3_PROVIDER_TIMEOUT = int(os.getenv('WEB3_PROVIDER_TIMEOUT', '30'))
WEB3_MAX_RETRIES = int(os.getenv('WEB3_MAX_RETRIES', '3'))

# =============================================================================
# HONEYPOT AND SIMULATION CONFIGURATION
# =============================================================================

HONEYPOT_SIMULATION_AMOUNT_ETH = Decimal(os.getenv('HONEYPOT_SIMULATION_AMOUNT_ETH', '0.001' if TESTNET_MODE else '0.01'))
HONEYPOT_SIMULATION_TIMEOUT = int(os.getenv('HONEYPOT_SIMULATION_TIMEOUT', '30' if TESTNET_MODE else '15'))
HONEYPOT_USE_ADVANCED_CHECKS = os.getenv('HONEYPOT_USE_ADVANCED_CHECKS', 'True').lower() == 'true'

# Transaction Simulation
SIMULATION_PROVIDER = os.getenv('SIMULATION_PROVIDER', 'alchemy')
SIMULATION_API_URL = f'https://api.alchemy.com/v2/{ALCHEMY_API_KEY}/simulate' if ALCHEMY_API_KEY else ''

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================

LOG_LEVEL = os.getenv('LOG_LEVEL', 'DEBUG' if DEBUG else 'INFO')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {name} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '[{levelname}] {name}: {message}',
            'style': '{',
        },
        'json': {
            'format': '{{"timestamp": "{asctime}", "level": "{levelname}", "logger": "{name}", "message": "{message}", "module": "{module}", "function": "{funcName}", "line": {lineno}}}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': LOG_LEVEL,
            'formatter': 'verbose',
            'stream': 'ext://sys.stdout',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': 'DEBUG',
            'formatter': 'json',
            'filename': BASE_DIR / 'logs' / 'django.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 10,
            'encoding': 'utf-8',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'dexproject': {
            'handlers': ['console', 'file'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'engine': {
            'handlers': ['console', 'file'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'trading': {
            'handlers': ['console', 'file'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'risk': {
            'handlers': ['console', 'file'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'wallet': {
            'handlers': ['console', 'file'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'wallet.auth': {
            'handlers': ['console', 'file'],
            'level': 'INFO',  # Important auth events
            'propagate': False,
        },
        'wallet.services': {
            'handlers': ['console', 'file'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'analytics': {
            'handlers': ['console', 'file'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
}

# Add Fast Lane engine logging configuration
if ENGINE_DEBUG_LOGGING:
    LOGGING['loggers']['dashboard.engine_service'] = {
        'handlers': ['console', 'file'],
        'level': 'DEBUG',
        'propagate': False,
    }

# Create logs directory if it doesn't exist
(BASE_DIR / 'logs').mkdir(exist_ok=True)

# =============================================================================
# DJANGO REST FRAMEWORK CONFIGURATION
# =============================================================================

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
        # Note: SIWE authentication is handled by custom backend, not DRF
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
        'wallet_auth': '200/hour',  # Special rate for wallet auth endpoints
    },
    # SIWE-specific settings
    'DEFAULT_METADATA_CLASS': 'rest_framework.metadata.SimpleMetadata',
    'EXCEPTION_HANDLER': 'rest_framework.views.exception_handler',
}

# =============================================================================
# CORS CONFIGURATION
# =============================================================================

# CORS settings for wallet integration
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",  # React development server
    "http://127.0.0.1:3000",
    "http://localhost:8000",  # Django development server
    "http://127.0.0.1:8000",
    "http://localhost:3001",  # Alternative frontend port
    "http://127.0.0.1:3001",
]

CORS_ALLOW_CREDENTIALS = True

# Allow CORS for wallet connection headers
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
# SESSION CONFIGURATION FOR SIWE
# =============================================================================

# Session settings optimized for wallet authentication
SESSION_COOKIE_AGE = 60 * 60 * 24  # 24 hours (matches SIWE session)
SESSION_COOKIE_SECURE = not DEBUG  # True in production
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_SAVE_EVERY_REQUEST = False  # Don't extend session on every request
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# Use database sessions for better security with wallet auth
SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# =============================================================================
# SECURITY SETTINGS FOR WALLET INTEGRATION
# =============================================================================

# CSRF settings for API endpoints
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'

# Exempt wallet auth endpoints from CSRF (they use signature verification)
CSRF_EXEMPT_URLS = [
    '/api/wallet/auth/siwe/generate/',
    '/api/wallet/auth/siwe/authenticate/',
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
# ENVIRONMENT-SPECIFIC OVERRIDES
# =============================================================================

# Import testnet settings if in testnet mode
if TESTNET_MODE:
    try:
        from engine.testnet_config import create_testnet_settings_override
        testnet_overrides = create_testnet_settings_override()
        
        # Apply testnet overrides
        for key, value in testnet_overrides.items():
            if hasattr(locals(), key):
                locals()[key] = value
            else:
                globals()[key] = value
                
    except ImportError as e:
        print(f"Warning: Could not import testnet configuration: {e}")

# =============================================================================
# FINAL VALIDATION AND CONFIGURATION SUMMARY
# =============================================================================

# Final validation
if TRADING_MODE == 'LIVE' and TESTNET_MODE:
    raise ValueError("Cannot use LIVE trading mode with TESTNET_MODE=True")

if not TESTNET_MODE and DEFAULT_CHAIN_ID in [11155111, 84532, 421614]:
    raise ValueError(f"Testnet chain ID {DEFAULT_CHAIN_ID} requires TESTNET_MODE=True")

# Print configuration summary for development
if DEBUG:
    print(f"DEX Trading Bot Configuration:")
    print(f"   Trading Mode: {TRADING_MODE}")
    print(f"   Testnet Mode: {TESTNET_MODE}")
    print(f"   Engine Mock Mode: {ENGINE_MOCK_MODE}")
    print(f"   Fast Lane Enabled: {FAST_LANE_ENABLED}")
    print(f"   Default Chain: {DEFAULT_CHAIN_ID}")
    print(f"   Supported Chains: {SUPPORTED_CHAINS}")
    print(f"   Max Portfolio: ${MAX_PORTFOLIO_SIZE_USD}")
    print(f"   Has Alchemy Key: {'Yes' if ALCHEMY_API_KEY else 'No'}")
    print(f"   Has Wallet Key: {'Yes' if WALLET_PRIVATE_KEY else 'No (will create dev wallet)'}")
    print(f"   Fast Lane Target: {FAST_LANE_TARGET_MS}ms")
    print(f"   Smart Lane: {'Enabled' if SMART_LANE_ENABLED else 'Phase 5 Pending'}")
    print(f"   Smart Lane Mock Mode: {'Yes' if SMART_LANE_MOCK_MODE else 'No'}")
    print(f"   SSE Max Iterations: {SSE_MAX_ITERATIONS}")
    print(f"   SIWE Authentication: Enabled")
    print(f"   SIWE Domain: {SIWE_DOMAIN}")
    print(f"   SIWE Session Hours: {SIWE_SESSION_EXPIRES_HOURS}")
    print(f"   Wallet Auth Enabled: Phase 5.1B Ready")