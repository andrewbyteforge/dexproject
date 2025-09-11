"""
Minimal Django settings for dexproject - GUARANTEED TO WORK

This is a simplified version that removes all problematic config() calls
and just uses direct values for initial testing.
"""

import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-test-key-for-development-only'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1']

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

# Database configuration - SQLite for development
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Redis configuration
REDIS_URL = 'redis://localhost:6379/0'

# Cache configuration (fallback to dummy cache if Redis not available)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# Celery configuration
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'

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

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework configuration
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',  # Simplified for testing
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

# CORS configuration
CORS_ALLOWED_ORIGINS = [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
]

# =============================================================================
# BLOCKCHAIN & RPC CONFIGURATION (Simplified)
# =============================================================================

# Ethereum RPC Configuration
ETH_RPC_URL = 'https://cloudflare-eth.com'
ETH_RPC_URL_FALLBACK = 'https://rpc.ankr.com/eth'

# Base Chain RPC Configuration  
BASE_RPC_URL = 'https://mainnet.base.org'
BASE_RPC_URL_FALLBACK = 'https://base.blockpi.network/v1/rpc/public'

# Arbitrum RPC Configuration
ARBITRUM_RPC_URL = 'https://arb1.arbitrum.io/rpc'
ARBITRUM_RPC_URL_FALLBACK = 'https://arbitrum.blockpi.network/v1/rpc/public'

# API Keys for Enhanced Services (empty for testing)
ALCHEMY_API_KEY = ''
INFURA_PROJECT_ID = ''
TENDERLY_API_KEY = ''

# =============================================================================
# TRADING ENGINE CONFIGURATION (Direct values, no config() calls)
# =============================================================================

# Trading Mode Configuration
TRADING_MODE = 'PAPER'
ENABLE_MOCK_MODE = True

# Risk Assessment Configuration
RISK_TIMEOUT_SECONDS = 10
RISK_PARALLEL_CHECKS = 4
RISK_MAX_RETRIES = 3

# Honeypot Detection Configuration
HONEYPOT_SIMULATION_AMOUNT_ETH = 0.01
HONEYPOT_SIMULATION_TIMEOUT = 15
HONEYPOT_USE_ADVANCED_CHECKS = True

# Transaction Simulation Configuration
SIMULATION_PROVIDER = 'alchemy'
SIMULATION_API_URL = 'https://api.alchemy.com/v2/{api_key}/simulate'

# Portfolio and Risk Management
MAX_PORTFOLIO_SIZE_USD = 10000.0
MAX_POSITION_SIZE_USD = 1000.0
DAILY_LOSS_LIMIT_PERCENT = 5.0
CIRCUIT_BREAKER_LOSS_PERCENT = 10.0

# Gas and Execution Configuration
DEFAULT_SLIPPAGE_PERCENT = 1.0
MAX_GAS_PRICE_GWEI = 50.0
EXECUTION_TIMEOUT_SECONDS = 30

# =============================================================================
# DEX ROUTER ADDRESSES
# =============================================================================

# Uniswap V2/V3 Router Addresses
UNISWAP_V2_ROUTER = '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D'
UNISWAP_V3_ROUTER = '0xE592427A0AEce92De3Edee1F18E0157C05861564'

# Base Chain DEX Routers  
BASE_UNISWAP_V3_ROUTER = '0x2626664c2603336E57B271c5C0b26F421741e481'
BASE_SUSHISWAP_ROUTER = '0x6BDED42c6DA8FBf0d2bA55B2fa120C5e0c8D7891'

# Common Token Addresses
WETH_ADDRESS = '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'
WETH_BASE_ADDRESS = '0x4200000000000000000000000000000000000006'
USDC_ADDRESS = '0xA0b86a33E6417aB1a83a8C3af4fF14D6BbE06B3D'
USDC_BASE_ADDRESS = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================

# Create logs directory if it doesn't exist
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '[{asctime}] {levelname} {name} - {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'dexproject.log',
            'maxBytes': 1024*1024*5,  # 5MB
            'backupCount': 3,
            'formatter': 'simple',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'risk': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'risk.tasks.honeypot': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}