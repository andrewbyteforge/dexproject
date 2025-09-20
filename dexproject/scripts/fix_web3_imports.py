#!/usr/bin/env python3
"""
Fix Web3 Import Issue - Diagnostic and Fix Script

This script tests the Web3 import directly and provides solutions for import issues.
Addresses the warning: "Web3 not available - install with: pip install web3 eth-account"

CREATE THIS FILE: scripts/fix_web3_imports.py

Usage:
    python scripts/fix_web3_imports.py

File: scripts/fix_web3_imports.py
"""

import sys
import os
from pathlib import Path

# Add Django project to path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

def test_web3_imports():
    """Test Web3 imports and show detailed information."""
    print("🔍 Testing Web3 Import Issues")
    print("=" * 40)
    
    # Test basic Python environment
    print(f"Python version: {sys.version}")
    print(f"Python executable: {sys.executable}")
    print(f"Virtual environment: {os.environ.get('VIRTUAL_ENV', 'Not in venv')}")
    print()
    
    # Test individual imports
    imports_to_test = [
        ('web3', 'Web3'),
        ('web3.middleware', 'geth_poa_middleware'), 
        ('eth_account.messages', 'encode_defunct'),
        ('eth_utils', 'is_address'),
        ('eth_utils', 'to_checksum_address'),
        ('eth_account', 'Account'),
    ]
    
    results = {}
    
    for module_name, import_item in imports_to_test:
        try:
            module = __import__(module_name, fromlist=[import_item])
            item = getattr(module, import_item)
            results[f"{module_name}.{import_item}"] = True
            print(f"✅ {module_name}.{import_item}: Successfully imported")
        except ImportError as e:
            results[f"{module_name}.{import_item}"] = False
            print(f"❌ {module_name}.{import_item}: Import failed - {e}")
        except AttributeError as e:
            results[f"{module_name}.{import_item}"] = False
            print(f"❌ {module_name}.{import_item}: Attribute error - {e}")
        except Exception as e:
            results[f"{module_name}.{import_item}"] = False
            print(f"❌ {module_name}.{import_item}: Unexpected error - {e}")
    
    print()
    
    # Test Web3 basic functionality
    try:
        from web3 import Web3
        w3 = Web3()
        print(f"✅ Web3 instance created: {w3}")
        print(f"✅ Web3 version: {Web3.__version__ if hasattr(Web3, '__version__') else 'Unknown'}")
    except Exception as e:
        print(f"❌ Web3 instance creation failed: {e}")
    
    print()
    
    # Summary
    working_imports = sum(1 for v in results.values() if v)
    total_imports = len(results)
    
    print(f"📊 Import Summary: {working_imports}/{total_imports} imports working")
    
    if working_imports == total_imports:
        print("🎯 All Web3 imports working correctly!")
        print("The issue might be in how Django is loading the modules.")
    elif working_imports == 0:
        print("❌ No Web3 imports working - packages may not be installed correctly")
        print("Try: pip install --upgrade web3 eth-account eth-utils")
    else:
        print("⚠️ Partial Web3 functionality - some imports failing")
    
    return working_imports == total_imports


def test_django_web3_import():
    """Test Web3 import in Django context."""
    print("\n🐍 Testing Web3 in Django Context")
    print("=" * 35)
    
    try:
        # Setup Django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
        import django
        django.setup()
        
        print("✅ Django setup successful")
        
        # Now test Web3 in Django context
        try:
            from web3 import Web3
            from web3.middleware import geth_poa_middleware
            from eth_account.messages import encode_defunct
            from eth_utils import is_address, to_checksum_address
            print("✅ All Web3 imports successful in Django context")
            return True
        except ImportError as e:
            print(f"❌ Web3 import failed in Django: {e}")
            return False
        
    except Exception as e:
        print(f"❌ Django setup failed: {e}")
        return False


def fix_wallet_services_import():
    """Create a fixed version of the wallet services import block."""
    print("\n🔧 Creating Fixed Wallet Services Import")
    print("=" * 40)
    
    fixed_import_block = '''# Web3 imports with enhanced fallback and error handling
WEB3_AVAILABLE = False
WEB3_IMPORT_ERROR = None

try:
    from web3 import Web3
    from web3.middleware import geth_poa_middleware
    from eth_account.messages import encode_defunct
    from eth_utils import is_address, to_checksum_address
    from eth_account import Account
    WEB3_AVAILABLE = True
    logger.info("✅ Web3 packages imported successfully")
except ImportError as e:
    WEB3_IMPORT_ERROR = str(e)
    Web3 = None
    geth_poa_middleware = None
    encode_defunct = None
    is_address = None
    to_checksum_address = None
    Account = None
    logger.warning(f"⚠️ Web3 packages not available: {e}")
    logger.warning("Install with: pip install web3 eth-account eth-utils")
except Exception as e:
    WEB3_IMPORT_ERROR = str(e)
    Web3 = None
    logger.error(f"❌ Unexpected error importing Web3: {e}")
'''
    
    print("Fixed import block created. This should replace the current import block in wallet/services.py")
    print("\nKey improvements:")
    print("✅ Better error handling and logging")
    print("✅ Captures specific import error messages") 
    print("✅ Sets all imports to None on failure")
    print("✅ Provides clear guidance for fixing")
    
    return fixed_import_block


def main():
    """Run all tests and provide recommendations."""
    print("🚀 Web3 Import Diagnosis and Fix")
    print("=" * 50)
    
    # Test basic imports
    basic_imports_work = test_web3_imports()
    
    # Test Django context
    django_imports_work = test_django_web3_import()
    
    # Generate fixed import block
    fixed_import = fix_wallet_services_import()
    
    print("\n💡 Recommendations:")
    print("=" * 20)
    
    if basic_imports_work and django_imports_work:
        print("✅ Web3 imports are working correctly!")
        print("The warning in wallet services might be due to timing or path issues.")
        print("Replace the import block in wallet/services.py with the fixed version above.")
    
    elif basic_imports_work and not django_imports_work:
        print("⚠️ Web3 works outside Django but fails inside Django")
        print("This could be a Django path or settings issue.")
        print("1. Check PYTHONPATH in Django settings")
        print("2. Verify virtual environment is activated when running Django")
        print("3. Try restarting the Django development server")
    
    elif not basic_imports_work:
        print("❌ Web3 packages not properly installed")
        print("Run these commands:")
        print("1. pip install --upgrade web3 eth-account eth-utils")
        print("2. pip list | grep web3  # Verify installation")
        print("3. python -c 'import web3; print(web3.__version__)'  # Test import")
    
    print("\n🔄 Next Steps:")
    print("1. Update wallet/services.py with the fixed import block")
    print("2. Restart your Django development server")
    print("3. Check that the warning is gone")


if __name__ == "__main__":
    main()