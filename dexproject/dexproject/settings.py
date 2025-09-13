"""
Enhanced Django settings for dexproject with Web3 integration

This settings file includes Web3 configuration, testnet support, and 
enhanced trading engine settings for both development and production.

File: dexproject/dexproject/settings.py
"""

import os
from pathlib import Path
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
# BLOCKCHAIN RPC CONFIGURATION 
# =============================================================================

# API Keys
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
# WALLET CONFIGURATION
# =============================================================================

# Wallet Management
WALLET_PRIVATE_KEY = os.getenv('WALLET_PRIVATE_KEY', '')  # Private key for trading wallet
WALLET_DAILY_LIMIT_USD = Decimal(os.getenv('WALLET_DAILY_LIMIT', '500.0' if TESTNET_MODE else '5000.0'))
WALLET_TX_LIMIT_USD = Decimal(os.getenv('WALLET_TX_LIMIT', '50.0' if TESTNET_MODE else '500.0'))

# Hardware wallet support (future)
HARDWARE_WALLET_SUPPORT = os.getenv('HARDWARE_WALLET_SUPPORT', 'False').lower() == 'true'
REQUIRE_HARDWARE_WALLET = os.getenv('REQUIRE_HARDWARE_WALLET', 'False').lower() == 'true'

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

# Create logs directory if it doesn't exist
(BASE_DIR / 'logs').mkdir(exist_ok=True)

# =============================================================================
# DJANGO REST FRAMEWORK CONFIGURATION
# =============================================================================

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
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
        'user': '1000/hour'
    }
}

# =============================================================================
# CORS CONFIGURATION
# =============================================================================

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",  # React development server
    "http://127.0.0.1:3000",
    "http://localhost:8000",  # Django development server
    "http://127.0.0.1:8000",
]

CORS_ALLOW_CREDENTIALS = True

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
# SECURITY SETTINGS
# =============================================================================

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

# Final validation
if TRADING_MODE == 'LIVE' and TESTNET_MODE:
    raise ValueError("Cannot use LIVE trading mode with TESTNET_MODE=True")

if not TESTNET_MODE and DEFAULT_CHAIN_ID in [11155111, 84532, 421614]:
    raise ValueError(f"Testnet chain ID {DEFAULT_CHAIN_ID} requires TESTNET_MODE=True")

# Print configuration summary for development
if DEBUG:
    print(f"🔧 DEX Trading Bot Configuration:")
    print(f"   Trading Mode: {TRADING_MODE}")
    print(f"   Testnet Mode: {TESTNET_MODE}")
    print(f"   Default Chain: {DEFAULT_CHAIN_ID}")
    print(f"   Supported Chains: {SUPPORTED_CHAINS}")
    print(f"   Max Portfolio: ${MAX_PORTFOLIO_SIZE_USD}")
    print(f"   Has Alchemy Key: {'Yes' if ALCHEMY_API_KEY else 'No'}")
    print(f"   Has Wallet Key: {'Yes' if WALLET_PRIVATE_KEY else 'No (will create dev wallet)'}")