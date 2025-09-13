#!/usr/bin/env python3
"""
Mempool Configuration Checker

Quick diagnostic script to check if your configuration is ready for mempool integration.
Validates API keys, endpoints, and Django settings without running full tests.

Usage:
    python scripts/check_mempool_config.py [--fix]
    
Options:
    --fix     Try to fix common configuration issues
    --verbose Show detailed configuration information

Path: scripts/check_mempool_config.py
"""

import sys
import os
from pathlib import Path
import argparse
from typing import Dict, List, Any

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import Django setup
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')

try:
    django.setup()
    from django.conf import settings
except Exception as e:
    print(f"❌ Django setup failed: {e}")
    print("Make sure you're running from the project root and have proper environment setup")
    sys.exit(1)


class ConfigurationChecker:
    """Configuration checker for mempool integration."""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.issues = []
        self.warnings = []
        self.recommendations = []
    
    def check_all(self) -> bool:
        """Run all configuration checks."""
        print("🔍 Mempool Configuration Check")
        print("=" * 50)
        
        # Check Django configuration
        self._check_django_settings()
        
        # Check API keys and endpoints
        self._check_api_configuration()
        
        # Check environment variables
        self._check_environment_variables()
        
        # Check dependencies
        self._check_dependencies()
        
        # Check file permissions and structure
        self._check_file_structure()
        
        # Generate report
        self._generate_report()
        
        return len(self.issues) == 0
    
    def _check_django_settings(self) -> None:
        """Check Django settings for mempool integration."""
        print("🔧 Checking Django configuration...")
        
        # Check if required apps are installed
        required_apps = ['shared', 'trading', 'risk', 'wallet', 'analytics']
        for app in required_apps:
            if app not in settings.INSTALLED_APPS:
                self.issues.append(f"Required Django app '{app}' not in INSTALLED_APPS")
        
        # Check Redis configuration
        if not hasattr(settings, 'REDIS_URL'):
            self.issues.append("REDIS_URL not configured in Django settings")
        elif settings.REDIS_URL == 'redis://localhost:6379/0':
            self.warnings.append("Using default Redis URL - ensure Redis is running")
        
        # Check Celery configuration  
        if not hasattr(settings, 'CELERY_BROKER_URL'):
            self.issues.append("Celery broker URL not configured")
        
        # Check database configuration
        if settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3':
            self.warnings.append("Using SQLite - consider PostgreSQL for production")
        
        print("   ✅ Django configuration checked")
    
    def _check_api_configuration(self) -> None:
        """Check API keys and RPC endpoints."""
        print("🔑 Checking API configuration...")
        
        # Check Alchemy API key
        alchemy_key = getattr(settings, 'ALCHEMY_API_KEY', '') or os.getenv('ALCHEMY_API_KEY', '')
        if not alchemy_key:
            self.issues.append("ALCHEMY_API_KEY not set")
        elif alchemy_key == 'demo' or len(alchemy_key) < 20:
            self.warnings.append("ALCHEMY_API_KEY appears to be demo/test key")
        
        # Check Ankr API key
        ankr_key = getattr(settings, 'ANKR_API_KEY', '') or os.getenv('ANKR_API_KEY', '')
        if not ankr_key:
            self.warnings.append("ANKR_API_KEY not set (optional but recommended for failover)")
        
        # Check Infura project ID
        infura_id = getattr(settings, 'INFURA_PROJECT_ID', '') or os.getenv('INFURA_PROJECT_ID', '')
        if not infura_id:
            self.warnings.append("INFURA_PROJECT_ID not set (optional but recommended)")
        
        # Check if testnet mode is configured
        testnet_mode = getattr(settings, 'TESTNET_MODE', False)
        if testnet_mode:
            print("   ℹ️  Running in testnet mode")
        else:
            self.warnings.append("Running in mainnet mode - ensure you have sufficient API credits")
        
        print("   ✅ API configuration checked")
    
    def _check_environment_variables(self) -> None:
        """Check environment variables for mempool configuration."""
        print("🌍 Checking environment variables...")
        
        # Environment variables for mempool configuration
        env_vars = [
            ('MEMPOOL_MIN_VALUE_ETH', '0.01', 'Minimum transaction value to monitor'),
            ('MEMPOOL_MIN_GAS_GWEI', '10.0', 'Minimum gas price to monitor'),
            ('MEMPOOL_MAX_AGE_SECONDS', '300.0', 'Maximum transaction age to keep'),
            ('MEMPOOL_TRACK_DEX_ONLY', 'True', 'Track only DEX transactions'),
            ('MEMPOOL_MAX_PENDING', '10000', 'Maximum pending transactions in memory'),
        ]
        
        missing_vars = []
        for var_name, default_value, description in env_vars:
            value = os.getenv(var_name)
            if not value:
                missing_vars.append(f"{var_name}={default_value}  # {description}")
        
        if missing_vars:
            self.recommendations.append(
                "Consider setting mempool environment variables:\n" + 
                "\n".join(f"  {var}" for var in missing_vars)
            )
        
        print("   ✅ Environment variables checked")
    
    def _check_dependencies(self) -> None:
        """Check if required Python packages are installed."""
        print("📦 Checking Python dependencies...")
        
        required_packages = [
            ('websockets', 'WebSocket support for mempool monitoring'),
            ('web3', 'Ethereum blockchain interaction'),
            ('redis', 'Redis client for caching'),
            ('celery', 'Task queue for background processing'),
        ]
        
        missing_packages = []
        for package, description in required_packages:
            try:
                __import__(package)
            except ImportError:
                missing_packages.append(f"{package} - {description}")
        
        if missing_packages:
            self.issues.append(
                "Missing required packages:\n" + 
                "\n".join(f"  {pkg}" for pkg in missing_packages)
            )
        
        # Check optional but recommended packages
        optional_packages = [
            ('aioredis', 'Async Redis client for better performance'),
            ('ujson', 'Fast JSON parsing'),
        ]
        
        missing_optional = []
        for package, description in optional_packages:
            try:
                __import__(package)
            except ImportError:
                missing_optional.append(f"{package} - {description}")
        
        if missing_optional:
            self.recommendations.append(
                "Consider installing optional packages for better performance:\n" + 
                "\n".join(f"  pip install {pkg.split(' - ')[0]}" for pkg in missing_optional)
            )
        
        print("   ✅ Dependencies checked")
    
    def _check_file_structure(self) -> None:
        """Check if required files and directories exist."""
        print("📁 Checking file structure...")
        
        project_root = Path(__file__).parent.parent
        
        required_paths = [
            'engine/mempool/__init__.py',
            'engine/mempool/monitor.py',
            'engine/mempool/analyzer.py',
            'shared/schemas.py',
            'shared/models/mixins.py',
        ]
        
        missing_files = []
        for path in required_paths:
            if not (project_root / path).exists():
                missing_files.append(path)
        
        if missing_files:
            self.issues.append(
                "Missing required files:\n" + 
                "\n".join(f"  {file}" for file in missing_files)
            )
        
        # Check directories
        required_dirs = [
            'logs',
            'engine',
            'shared',
        ]
        
        missing_dirs = []
        for dir_path in required_dirs:
            if not (project_root / dir_path).exists():
                missing_dirs.append(dir_path)
        
        if missing_dirs:
            self.recommendations.append(
                "Create missing directories:\n" + 
                "\n".join(f"  mkdir {d}" for d in missing_dirs)
            )
        
        print("   ✅ File structure checked")
    
    def _generate_report(self) -> None:
        """Generate final configuration report."""
        print("\n" + "=" * 60)
        print("📋 CONFIGURATION REPORT")
        print("=" * 60)
        
        if not self.issues and not self.warnings:
            print("🎯 ✅ Configuration looks good for mempool integration!")
            print("\nNext steps:")
            print("  1. Run: python scripts/quick_mempool_test.py connection-test")
            print("  2. Run: python scripts/quick_mempool_test.py quick-test")
        else:
            if self.issues:
                print(f"❌ {len(self.issues)} CRITICAL ISSUES:")
                for i, issue in enumerate(self.issues, 1):
                    print(f"\n{i}. {issue}")
            
            if self.warnings:
                print(f"\n⚠️  {len(self.warnings)} WARNINGS:")
                for i, warning in enumerate(self.warnings, 1):
                    print(f"\n{i}. {warning}")
        
        if self.recommendations:
            print(f"\n💡 RECOMMENDATIONS:")
            for i, rec in enumerate(self.recommendations, 1):
                print(f"\n{i}. {rec}")
        
        print("\n" + "=" * 60)
    
    def fix_common_issues(self) -> bool:
        """Attempt to fix common configuration issues."""
        print("🔧 Attempting to fix common issues...")
        
        fixed_count = 0
        project_root = Path(__file__).parent.parent
        
        # Create missing directories
        dirs_to_create = ['logs', 'engine/mempool']
        for dir_path in dirs_to_create:
            full_path = project_root / dir_path
            if not full_path.exists():
                try:
                    full_path.mkdir(parents=True, exist_ok=True)
                    print(f"   ✅ Created directory: {dir_path}")
                    fixed_count += 1
                except Exception as e:
                    print(f"   ❌ Failed to create {dir_path}: {e}")
        
        # Create sample environment file
        env_file = project_root / '.env.sample'
        if not env_file.exists():
            try:
                sample_env = """# Mempool Integration Environment Variables
ALCHEMY_API_KEY=your_alchemy_api_key_here
ANKR_API_KEY=your_ankr_api_key_here
INFURA_PROJECT_ID=your_infura_project_id_here

# Mempool Configuration
MEMPOOL_MIN_VALUE_ETH=0.01
MEMPOOL_MIN_GAS_GWEI=10.0
MEMPOOL_MAX_AGE_SECONDS=300.0
MEMPOOL_TRACK_DEX_ONLY=True
MEMPOOL_MAX_PENDING=10000

# Redis Configuration
REDIS_URL=redis://localhost:6379/0

# Database Configuration (optional)
DB_ENGINE=django.db.backends.postgresql
DB_NAME=dexproject
DB_USER=dexproject
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432
"""
                env_file.write_text(sample_env)
                print(f"   ✅ Created sample environment file: .env.sample")
                fixed_count += 1
            except Exception as e:
                print(f"   ❌ Failed to create .env.sample: {e}")
        
        if fixed_count > 0:
            print(f"\n✅ Fixed {fixed_count} issues")
            return True
        else:
            print("\n   No fixable issues found")
            return False


def main():
    """Main CLI interface."""
    parser = argparse.ArgumentParser(description="Check mempool integration configuration")
    parser.add_argument("--fix", action="store_true", help="Try to fix common issues")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    checker = ConfigurationChecker(verbose=args.verbose)
    
    # Run fixes first if requested
    if args.fix:
        checker.fix_common_issues()
        print()
    
    # Run configuration checks
    is_ready = checker.check_all()
    
    if is_ready:
        print("\n🚀 Ready to test mempool integration!")
        print("Run: python scripts/quick_mempool_test.py")
    else:
        print("\n⚠️  Please fix the issues above before testing")
    
    sys.exit(0 if is_ready else 1)


if __name__ == "__main__":
    main()