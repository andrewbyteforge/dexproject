#!/usr/bin/env python3
"""
Fix Environment Variable Loading in Django

This script fixes the Django settings to properly load the .env file
so that environment variables are available to the configuration checker.

Usage:
    python scripts/fix_env_loading.py

Path: scripts/fix_env_loading.py
"""

import os
import sys
from pathlib import Path


def fix_django_settings():
    """Fix Django settings.py to load .env file properly."""
    
    project_root = Path(__file__).parent.parent
    settings_file = project_root / 'dexproject' / 'settings.py'
    
    print("🔧 Fixing Django Environment Variable Loading")
    print("=" * 60)
    
    if not settings_file.exists():
        print(f"❌ Settings file not found: {settings_file}")
        return False
    
    # Read current settings
    with open(settings_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check if python-dotenv is already imported
    if 'from dotenv import load_dotenv' in content:
        print("✅ python-dotenv already configured in settings.py")
        return True
    
    # Find the import section and add dotenv loading
    lines = content.split('\n')
    new_lines = []
    
    # Find where to insert the dotenv import (after pathlib import)
    insert_index = 0
    for i, line in enumerate(lines):
        new_lines.append(line)
        
        # Insert after pathlib import
        if 'from pathlib import Path' in line:
            insert_index = i + 1
            break
    
    # Insert dotenv loading code
    dotenv_code = [
        '',
        '# Load environment variables from .env file',
        'try:',
        '    from dotenv import load_dotenv',
        '    load_dotenv()',
        'except ImportError:',
        '    # python-dotenv not installed - environment variables must be set manually',
        '    pass',
        ''
    ]
    
    # Insert the dotenv code
    for line in dotenv_code:
        new_lines.insert(insert_index, line)
        insert_index += 1
    
    # Add remaining lines
    new_lines.extend(lines[len(new_lines) - len(dotenv_code):])
    
    # Write back to file
    with open(settings_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_lines))
    
    print("✅ Added python-dotenv loading to Django settings")
    return True


def install_python_dotenv():
    """Install python-dotenv package."""
    print("📦 Installing python-dotenv...")
    
    import subprocess
    
    try:
        result = subprocess.run([
            sys.executable, '-m', 'pip', 'install', 'python-dotenv'
        ], capture_output=True, text=True, check=True)
        
        print("✅ python-dotenv installed successfully")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install python-dotenv: {e}")
        print(f"stdout: {e.stdout}")
        print(f"stderr: {e.stderr}")
        return False


def create_env_file_if_missing():
    """Create .env file with the comprehensive configuration if it's missing."""
    
    project_root = Path(__file__).parent.parent
    env_file = project_root / '.env'
    
    if env_file.exists():
        print(f"✅ .env file already exists: {env_file}")
        return True
    
    print("📄 Creating .env file with comprehensive configuration...")
    
    env_content = '''# Enhanced DEX Trading Engine Configuration
# Updated with real API keys and mempool integration

# =============================================================================
# Engine Core Settings
# =============================================================================
TRADING_MODE=PAPER  # PAPER | SHADOW | LIVE
ENGINE_NAME=dex-trading-engine
LOG_LEVEL=INFO  # DEBUG | INFO | WARNING | ERROR

# Testnet Mode Configuration
TESTNET_MODE=True
DEFAULT_CHAIN_ID=84532  # Base Sepolia
TARGET_CHAINS=84532,11155111,421614  # Base Sepolia, Ethereum Sepolia, Arbitrum Sepolia

# =============================================================================
# API KEYS (Your Real Keys)
# =============================================================================
# Primary Alchemy API Keys
ALCHEMY_API_KEY=9GmgCWBG2aArsq7UR6Noc  # Ethereum mainnet key
BASE_ALCHEMY_API_KEY=QQVCZXxW7uTGFjLEWTV4B  # Base mainnet key

# Ankr API Key for failover
ANKR_API_KEY=e2a1bb30ced88fc7749c2edc3ed7d82a32cdbbc2e8622ec7bbf143814555d8bb

# Infura Project ID for additional failover
INFURA_PROJECT_ID=1ae88681246244a5a9ac097b920a42f4

# =============================================================================
# Testnet RPC Configuration
# =============================================================================

# Base Sepolia (Chain ID: 84532) - Your Default Chain
BASE_SEPOLIA_RPC_URL=https://base-sepolia.g.alchemy.com/v2/QQVCZXxW7uTGFjLEWTV4B
BASE_SEPOLIA_WS_URL=wss://base-sepolia.g.alchemy.com/v2/QQVCZXxW7uTGFjLEWTV4B
BASE_RPC_URL_FALLBACK=https://sepolia.base.org

# Ethereum Sepolia (Chain ID: 11155111)
SEPOLIA_RPC_URL=https://eth-sepolia.g.alchemy.com/v2/9GmgCWBG2aArsq7UR6Noc
SEPOLIA_WS_URL=wss://eth-sepolia.g.alchemy.com/v2/9GmgCWBG2aArsq7UR6Noc
ETH_RPC_URL_FALLBACK=https://rpc.sepolia.org

# Arbitrum Sepolia (Chain ID: 421614)
ARBITRUM_SEPOLIA_RPC_URL=https://sepolia-rollup.arbitrum.io/rpc

# Legacy naming for compatibility
ETH_RPC_URL=https://eth-sepolia.g.alchemy.com/v2/9GmgCWBG2aArsq7UR6Noc
BASE_RPC_URL=https://base-sepolia.g.alchemy.com/v2/QQVCZXxW7uTGFjLEWTV4B

# =============================================================================
# MEMPOOL CONFIGURATION (For Fast Lane)
# =============================================================================
# Minimum transaction value to monitor (lower for testnet)
MEMPOOL_MIN_VALUE_ETH=0.001

# Minimum gas price to monitor (lower for testnet)
MEMPOOL_MIN_GAS_GWEI=1.0

# Maximum transaction age to keep in memory
MEMPOOL_MAX_AGE_SECONDS=300.0

# Track only DEX transactions (recommended for performance)
MEMPOOL_TRACK_DEX_ONLY=True

# Maximum pending transactions in memory
MEMPOOL_MAX_PENDING=5000

# Connection settings for WebSocket monitoring
WEBSOCKET_TIMEOUT=30
WEBSOCKET_RECONNECT_DELAY=5

# =============================================================================
# Discovery & Monitoring Settings
# =============================================================================
DISCOVERY_ENABLED=true
HTTP_POLL_INTERVAL=5  # Fallback polling interval in seconds
MAX_PAIRS_PER_HOUR=100  # Rate limiting for new pair discovery
EVENT_BATCH_SIZE=50  # Process events in batches

# =============================================================================
# Risk Assessment Settings (Adjusted for Testnet)
# =============================================================================
RISK_TIMEOUT=15  # Seconds to wait for risk checks
RISK_PARALLEL_CHECKS=4  # Number of parallel risk assessments
MIN_LIQUIDITY_USD=100  # Lower minimum liquidity for testnet
MAX_BUY_TAX_PERCENT=5.0  # Maximum acceptable buy tax
MAX_SELL_TAX_PERCENT=5.0  # Maximum acceptable sell tax
MIN_HOLDER_COUNT=10  # Lower holder count for testnet

# =============================================================================
# Portfolio Management (Conservative for Testing)
# =============================================================================
MAX_PORTFOLIO_SIZE_USD=100  # Small portfolio for testing
MAX_POSITION_SIZE_USD=10  # Small position sizes for testing
DAILY_LOSS_LIMIT_PERCENT=5.0  # Daily loss limit
CIRCUIT_BREAKER_LOSS_PERCENT=10.0  # Emergency stop loss

# =============================================================================
# Trade Execution Settings
# =============================================================================
DEFAULT_SLIPPAGE_PERCENT=1.0  # Default slippage tolerance
MAX_GAS_PRICE_GWEI=10  # Lower gas price for testnet
EXECUTION_TIMEOUT=30  # Seconds to wait for transaction confirmation
NONCE_MANAGEMENT=auto  # auto | manual

# =============================================================================
# Paper Trading Settings
# =============================================================================
PAPER_MODE_SLIPPAGE=0.5  # Simulated slippage in paper mode
PAPER_MODE_LATENCY_MS=200  # Simulated execution latency

# =============================================================================
# Provider Management
# =============================================================================
PROVIDER_HEALTH_CHECK_INTERVAL=30  # Health check frequency in seconds
PROVIDER_FAILOVER_THRESHOLD=3  # Failures before failover
PROVIDER_RECOVERY_TIME=300  # Seconds before retrying failed provider

# =============================================================================
# Database & Caching
# =============================================================================
# Redis for caching and task queue (using default local Redis)
REDIS_URL=redis://localhost:6379/0

# SQLite Database (default for development)
# Uncomment below for PostgreSQL:
# DATABASE_URL=postgresql://user:password@localhost:5432/dexbot

# =============================================================================
# Django Settings
# =============================================================================
SECRET_KEY=your-super-secret-django-key-change-this-in-production
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# =============================================================================
# Celery Task Queue
# =============================================================================
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# =============================================================================
# DEX Contract Addresses (Testnet)
# =============================================================================
# Base Sepolia
BASE_UNISWAP_V3_ROUTER=0x2626664c2603336E57B271c5C0b26F421741e481
BASE_UNISWAP_V3_FACTORY=0x4752ba5dbc23f44d87826276bf6fd6b1c372ad24

# Ethereum Sepolia  
UNISWAP_V2_ROUTER=0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D
UNISWAP_V3_ROUTER=0xE592427A0AEce92De3Edee1F18E0157C05861564

# =============================================================================
# Fast Lane Performance Tuning
# =============================================================================
# Performance targets for Fast Lane
FAST_LANE_TARGET_MS=500  # Target execution time for Fast Lane
FAST_LANE_SLA_MS=300     # SLA for analysis time

# Risk cache settings for Fast Lane
RISK_CACHE_TTL=3600      # Risk cache TTL in seconds
RISK_CACHE_MAX_SIZE=10000 # Maximum risk cache entries

# =============================================================================
# Development & Debug Settings
# =============================================================================
# Detailed logging for development
DJANGO_LOG_LEVEL=INFO
ENGINE_LOG_LEVEL=DEBUG

# Enable additional debug features
ENGINE_DEBUG_MODE=True
MEMPOOL_DEBUG_MODE=False  # Can be noisy, enable for detailed mempool debugging
'''
    
    with open(env_file, 'w', encoding='utf-8') as f:
        f.write(env_content)
    
    print(f"✅ Created .env file: {env_file}")
    return True


def main():
    """Main function to fix environment loading."""
    
    success = True
    
    # Step 1: Install python-dotenv
    if not install_python_dotenv():
        success = False
    
    # Step 2: Create .env file if missing
    if not create_env_file_if_missing():
        success = False
    
    # Step 3: Fix Django settings
    if not fix_django_settings():
        success = False
    
    if success:
        print("\n🎯 Environment loading fixed successfully!")
        print("\nNext steps:")
        print("1. Restart any Django processes")
        print("2. Run: python scripts/check_mempool_config.py")
        print("3. Run: python scripts/quick_mempool_test.py connection-test")
    else:
        print("\n❌ Some fixes failed - please check the errors above")
    
    return success


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⏹️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)