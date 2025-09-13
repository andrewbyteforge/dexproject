#!/usr/bin/env python
"""
Simple fix script to resolve Django server startup issues.
Unicode-safe version for Windows.

Run this script from the dexproject directory to fix:
1. Missing REDIS_CHANNELS in shared/constants.py
2. JSON logging formatter issues  
3. Missing testnet configuration function

Usage: python simple_fix.py
"""

import os
import re
from pathlib import Path

def fix_shared_constants():
    """Fix shared/constants.py to add missing REDIS_CHANNELS."""
    constants_file = Path("shared/constants.py")
    
    if not constants_file.exists():
        print(f"ERROR: {constants_file} not found!")
        return False
    
    # Read current content with explicit encoding
    try:
        with open(constants_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"ERROR reading {constants_file}: {e}")
        return False
    
    # Check if REDIS_CHANNELS already exists
    if "REDIS_CHANNELS" in content:
        print("OK: REDIS_CHANNELS already exists in shared/constants.py")
        return True
    
    # Add REDIS_CHANNELS at the end (ASCII safe)
    redis_channels_code = '''

# Redis Channels for pub/sub communication between Engine and Django
REDIS_CHANNELS = {
    # Engine to Django channels
    'pair_discovery': 'dex:pair_discovery',
    'fast_risk_complete': 'dex:fast_risk_complete', 
    'trading_decision': 'dex:trading_decision',
    'trade_execution': 'dex:trade_execution',
    'engine_status': 'dex:engine_status',
    'engine_alerts': 'dex:engine_alerts',
    
    # Django to Engine channels
    'comprehensive_risk_complete': 'dex:comprehensive_risk_complete',
    'trading_config_update': 'dex:trading_config_update',
    'emergency_stop': 'dex:emergency_stop',
    'risk_profile_update': 'dex:risk_profile_update',
}

# Redis Keys for caching and data storage
REDIS_KEYS = {
    'engine_status': 'dex:engine_status',
    'risk_cache': 'dex:risk_cache',
    'price_cache': 'dex:price_cache',
    'trade_cache': 'dex:trade_cache',
    'pair_cache': 'dex:pair_cache',
    'wallet_cache': 'dex:wallet_cache',
    'gas_cache': 'dex:gas_cache',
    'config_cache': 'dex:config_cache',
}
'''
    
    # Append the REDIS_CHANNELS configuration
    updated_content = content + redis_channels_code
    
    # Write back with explicit encoding
    try:
        with open(constants_file, 'w', encoding='utf-8') as f:
            f.write(updated_content)
        print("SUCCESS: Added REDIS_CHANNELS to shared/constants.py")
        return True
    except Exception as e:
        print(f"ERROR writing {constants_file}: {e}")
        return False

def fix_logging_config():
    """Fix JSON logging formatter in settings.py."""
    settings_file = Path("dexproject/settings.py")
    
    if not settings_file.exists():
        print(f"ERROR: {settings_file} not found!")
        return False
    
    try:
        with open(settings_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"ERROR reading {settings_file}: {e}")
        return False
    
    # Find and fix the JSON formatter
    if '"timestamp"' in content and "'json'" in content:
        # Replace the problematic JSON format string
        old_format = '\'{"timestamp": "{asctime}", "level": "{levelname}", "logger": "{name}", "message": "{message}", "module": "{module}", "function": "{funcName}", "line": {lineno}}\''
        new_format = '\'{{"timestamp": "{asctime}", "level": "{levelname}", "logger": "{name}", "message": "{message}", "module": "{module}", "function": "{funcName}", "line": {lineno}}}\''
        
        if old_format in content:
            content = content.replace(old_format, new_format)
        else:
            # Try a more general replacement
            import re
            content = re.sub(
                r'(\'format\': \')[^\']*"timestamp"[^\']*\'',
                r'\1{{"timestamp": "{asctime}", "level": "{levelname}", "logger": "{name}", "message": "{message}", "module": "{module}", "function": "{funcName}", "line": {lineno}}}\'',
                content
            )
        
        try:
            with open(settings_file, 'w', encoding='utf-8') as f:
                f.write(content)
            print("SUCCESS: Fixed JSON logging formatter in settings.py")
            return True
        except Exception as e:
            print(f"ERROR writing {settings_file}: {e}")
            return False
    else:
        print("WARNING: JSON logging formatter pattern not found - may already be fixed")
        return True

def create_minimal_engine_config():
    """Create minimal engine configuration to prevent import errors."""
    engine_dir = Path("engine")
    engine_dir.mkdir(exist_ok=True)
    
    # Create __init__.py if it doesn't exist
    init_file = engine_dir / "__init__.py"
    if not init_file.exists():
        with open(init_file, 'w', encoding='utf-8') as f:
            f.write("# Engine module\n")
    
    # Create minimal testnet_config.py
    testnet_file = engine_dir / "testnet_config.py"
    minimal_config = '''"""
Minimal testnet configuration to prevent import errors.
"""

def create_testnet_settings_override():
    """Create minimal testnet settings override."""
    return {
        'TRADING_MODE': 'PAPER',
        'TESTNET_MODE': True,
        'DEFAULT_CHAIN_ID': 84532,  # Base Sepolia
        'MAX_PORTFOLIO_SIZE_USD': 1000.0,
        'MAX_POSITION_SIZE_USD': 100.0,
        'DAILY_LOSS_LIMIT_PERCENT': 50.0,
        'MAX_GAS_PRICE_GWEI': 100.0,
        'DEFAULT_SLIPPAGE_PERCENT': 5.0,
    }

def get_testnet_chain_configs():
    """Get minimal testnet chain configs."""
    return {}

def is_testnet(chain_id):
    """Check if chain ID is testnet."""
    testnet_chains = {11155111, 84532, 421614}
    return chain_id in testnet_chains

def validate_testnet_environment():
    """Validate testnet environment."""
    return {'is_valid': True, 'warnings': [], 'errors': []}
'''
    
    try:
        with open(testnet_file, 'w', encoding='utf-8') as f:
            f.write(minimal_config)
        print("SUCCESS: Created minimal engine/testnet_config.py")
        return True
    except Exception as e:
        print(f"ERROR creating {testnet_file}: {e}")
        return False

def comment_out_problematic_imports():
    """Comment out problematic imports in settings.py."""
    settings_file = Path("dexproject/settings.py")
    
    if not settings_file.exists():
        return False
    
    try:
        with open(settings_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"ERROR reading {settings_file}: {e}")
        return False
    
    # Comment out the problematic testnet import section if it exists
    if "from engine.testnet_config import create_testnet_settings_override" in content:
        lines = content.split('\n')
        fixed_lines = []
        in_testnet_block = False
        
        for line in lines:
            if "if TESTNET_MODE:" in line and "try:" in lines[lines.index(line) + 1]:
                # Start of testnet block
                fixed_lines.append("# TEMPORARILY DISABLED - testnet config import")
                fixed_lines.append("# " + line)
                in_testnet_block = True
            elif in_testnet_block and (line.startswith('    ') or line.strip() == ''):
                # Inside testnet block
                if line.strip():
                    fixed_lines.append("#" + line)
                else:
                    fixed_lines.append("#")
            elif in_testnet_block and not line.startswith('    '):
                # End of testnet block
                in_testnet_block = False
                fixed_lines.append(line)
            else:
                fixed_lines.append(line)
        
        content = '\n'.join(fixed_lines)
        
        try:
            with open(settings_file, 'w', encoding='utf-8') as f:
                f.write(content)
            print("SUCCESS: Commented out problematic testnet imports")
            return True
        except Exception as e:
            print(f"ERROR writing {settings_file}: {e}")
            return False
    
    print("INFO: No problematic imports found to comment out")
    return True

def main():
    """Run all fixes."""
    print("DEX Trading Bot - Simple Fix Script")
    print("=" * 40)
    
    # Check if we're in the right directory
    if not Path("manage.py").exists():
        print("ERROR: Run this script from the dexproject directory (where manage.py is located)")
        return False
    
    success_count = 0
    total_fixes = 4
    
    # Fix 1: Shared constants
    print("\n1. Fixing shared/constants.py...")
    if fix_shared_constants():
        success_count += 1
    
    # Fix 2: Logging configuration
    print("\n2. Fixing logging configuration...")
    if fix_logging_config():
        success_count += 1
    
    # Fix 3: Create engine configuration
    print("\n3. Creating engine configuration...")
    if create_minimal_engine_config():
        success_count += 1
    
    # Fix 4: Comment out problematic imports
    print("\n4. Commenting out problematic imports...")
    if comment_out_problematic_imports():
        success_count += 1
    
    print("\n" + "=" * 40)
    if success_count == total_fixes:
        print("SUCCESS: All fixes applied successfully!")
        print("\nTry running the server again:")
        print("   python manage.py runserver")
    else:
        print(f"PARTIAL SUCCESS: {success_count}/{total_fixes} fixes applied.")
        print("Check the output above for any errors.")
    
    print("\nWhat was fixed:")
    print("   - Added missing REDIS_CHANNELS to shared/constants.py")
    print("   - Fixed JSON logging formatter escaping")
    print("   - Created minimal testnet configuration")
    print("   - Commented out problematic imports")
    
    return success_count == total_fixes

if __name__ == "__main__":
    main()