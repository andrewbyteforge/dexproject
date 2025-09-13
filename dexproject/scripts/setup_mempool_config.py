#!/usr/bin/env python3
"""
Mempool Configuration Setup Script

Interactive setup script to configure API keys and environment variables
for mempool integration testing.

Usage:
    python scripts/setup_mempool_config.py

Path: scripts/setup_mempool_config.py
"""

import os
import sys
from pathlib import Path
from typing import Dict, Optional


class MempoolConfigSetup:
    """Interactive configuration setup for mempool integration."""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.env_file = self.project_root / '.env'
        self.config_values = {}
    
    def run_interactive_setup(self) -> None:
        """Run interactive configuration setup."""
        print("🚀 Mempool Integration Configuration Setup")
        print("=" * 60)
        print("This will help you configure API keys and settings for mempool monitoring.")
        print("You can get free API keys from:")
        print("  • Alchemy: https://dashboard.alchemy.com/")
        print("  • Ankr: https://www.ankr.com/rpc/")
        print("  • Infura: https://infura.io/dashboard")
        print()
        
        # Check if .env file exists
        if self.env_file.exists():
            print("📄 Found existing .env file")
            overwrite = input("Do you want to update it? (y/N): ").lower().strip()
            if overwrite != 'y':
                print("Exiting without changes.")
                return
            print()
        
        # Collect API keys
        self._collect_api_keys()
        
        # Collect mempool configuration
        self._collect_mempool_config()
        
        # Collect optional configuration
        self._collect_optional_config()
        
        # Write configuration
        self._write_env_file()
        
        print("\n🎯 Configuration Complete!")
        print(f"✅ Settings saved to: {self.env_file}")
        print("\nNext steps:")
        print("1. Restart your Django development server")
        print("2. Run: python scripts/check_mempool_config.py")
        print("3. Run: python scripts/quick_mempool_test.py connection-test")
    
    def _collect_api_keys(self) -> None:
        """Collect API keys from user."""
        print("🔑 API Keys Configuration")
        print("-" * 30)
        
        # Alchemy API Key (required for mempool WebSocket)
        print("ALCHEMY API KEY (Required for mempool monitoring):")
        print("  Get free key at: https://dashboard.alchemy.com/")
        alchemy_key = input("Enter Alchemy API key (or 'demo' for testing): ").strip()
        
        if not alchemy_key:
            alchemy_key = 'demo'
            print("  ⚠️  Using 'demo' - limited functionality")
        elif alchemy_key != 'demo' and len(alchemy_key) < 20:
            print("  ⚠️  Key looks short - make sure it's correct")
        
        self.config_values['ALCHEMY_API_KEY'] = alchemy_key
        
        # Ankr API Key (optional, for failover)
        print("\nANKR API KEY (Optional - provides failover):")
        print("  Get free key at: https://www.ankr.com/rpc/")
        ankr_key = input("Enter Ankr API key (or press Enter to skip): ").strip()
        if ankr_key:
            self.config_values['ANKR_API_KEY'] = ankr_key
        
        # Infura Project ID (optional, for additional failover)
        print("\nINFURA PROJECT ID (Optional - additional failover):")
        print("  Get free key at: https://infura.io/dashboard")
        infura_id = input("Enter Infura project ID (or press Enter to skip): ").strip()
        if infura_id:
            self.config_values['INFURA_PROJECT_ID'] = infura_id
        
        print("  ✅ API keys configured")
    
    def _collect_mempool_config(self) -> None:
        """Collect mempool-specific configuration."""
        print("\n⚙️  Mempool Configuration")
        print("-" * 30)
        
        # Use defaults for testing
        defaults = {
            'MEMPOOL_MIN_VALUE_ETH': '0.001',  # Lower for testnet
            'MEMPOOL_MIN_GAS_GWEI': '1.0',     # Lower for testnet
            'MEMPOOL_MAX_AGE_SECONDS': '300.0',
            'MEMPOOL_TRACK_DEX_ONLY': 'True',
            'MEMPOOL_MAX_PENDING': '5000',     # Lower for testing
        }
        
        print("Using recommended settings for testnet:")
        for key, value in defaults.items():
            description = self._get_config_description(key)
            print(f"  {key}={value}  # {description}")
            self.config_values[key] = value
        
        print("  ✅ Mempool configuration set")
    
    def _collect_optional_config(self) -> None:
        """Collect optional configuration."""
        print("\n🔧 Optional Configuration")
        print("-" * 30)
        
        # Redis URL
        redis_url = input("Redis URL (default: redis://localhost:6379/0): ").strip()
        if not redis_url:
            redis_url = 'redis://localhost:6379/0'
        self.config_values['REDIS_URL'] = redis_url
        
        # Debug mode
        debug_mode = input("Enable debug mode? (Y/n): ").lower().strip()
        if debug_mode in ['', 'y', 'yes']:
            self.config_values['DEBUG'] = 'True'
        else:
            self.config_values['DEBUG'] = 'False'
        
        print("  ✅ Optional configuration set")
    
    def _get_config_description(self, key: str) -> str:
        """Get human-readable description for config key."""
        descriptions = {
            'MEMPOOL_MIN_VALUE_ETH': 'Minimum transaction value to monitor',
            'MEMPOOL_MIN_GAS_GWEI': 'Minimum gas price to monitor',
            'MEMPOOL_MAX_AGE_SECONDS': 'Maximum transaction age to keep',
            'MEMPOOL_TRACK_DEX_ONLY': 'Track only DEX transactions',
            'MEMPOOL_MAX_PENDING': 'Maximum pending transactions in memory',
        }
        return descriptions.get(key, 'Configuration parameter')
    
    def _write_env_file(self) -> None:
        """Write configuration to .env file."""
        print(f"\n💾 Writing configuration to {self.env_file}...")
        
        # Read existing .env if it exists
        existing_config = {}
        if self.env_file.exists():
            with open(self.env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        existing_config[key] = value
        
        # Merge with new configuration
        existing_config.update(self.config_values)
        
        # Write updated configuration
        with open(self.env_file, 'w') as f:
            f.write("# DEX Trading Bot Environment Configuration\n")
            f.write("# Generated by mempool configuration setup\n")
            f.write(f"# Created: {os.path.basename(__file__)}\n\n")
            
            # API Keys section
            f.write("# =============================================================================\n")
            f.write("# API KEYS\n")
            f.write("# =============================================================================\n")
            api_keys = ['ALCHEMY_API_KEY', 'ANKR_API_KEY', 'INFURA_PROJECT_ID']
            for key in api_keys:
                if key in existing_config:
                    f.write(f"{key}={existing_config[key]}\n")
            f.write("\n")
            
            # Mempool configuration section
            f.write("# =============================================================================\n")
            f.write("# MEMPOOL CONFIGURATION\n")
            f.write("# =============================================================================\n")
            mempool_keys = [k for k in existing_config.keys() if k.startswith('MEMPOOL_')]
            for key in mempool_keys:
                description = self._get_config_description(key)
                f.write(f"# {description}\n")
                f.write(f"{key}={existing_config[key]}\n")
            f.write("\n")
            
            # Other configuration
            f.write("# =============================================================================\n")
            f.write("# OTHER CONFIGURATION\n")
            f.write("# =============================================================================\n")
            other_keys = [k for k in existing_config.keys() 
                         if not k.startswith(('ALCHEMY_', 'ANKR_', 'INFURA_', 'MEMPOOL_'))]
            for key in other_keys:
                f.write(f"{key}={existing_config[key]}\n")
        
        print("  ✅ Configuration file written")
    
    def create_quick_setup(self) -> None:
        """Create a quick setup with demo keys for immediate testing."""
        print("🚀 Quick Demo Setup")
        print("=" * 40)
        print("Creating configuration with demo keys for immediate testing...")
        
        # Demo configuration
        demo_config = {
            'ALCHEMY_API_KEY': 'demo',
            'MEMPOOL_MIN_VALUE_ETH': '0.001',
            'MEMPOOL_MIN_GAS_GWEI': '1.0',
            'MEMPOOL_MAX_AGE_SECONDS': '300.0',
            'MEMPOOL_TRACK_DEX_ONLY': 'True',
            'MEMPOOL_MAX_PENDING': '5000',
            'REDIS_URL': 'redis://localhost:6379/0',
            'DEBUG': 'True',
        }
        
        self.config_values = demo_config
        self._write_env_file()
        
        print("\n✅ Demo configuration created!")
        print("⚠️  Using demo API key - limited functionality")
        print("\nTo get full functionality:")
        print("1. Get free Alchemy API key: https://dashboard.alchemy.com/")
        print("2. Run this script again to update configuration")
        print("\nNext steps:")
        print("1. Run: python scripts/check_mempool_config.py")
        print("2. Run: python scripts/quick_mempool_test.py demo-test")


def main():
    """Main CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Setup mempool configuration")
    parser.add_argument("--quick", action="store_true", help="Quick demo setup")
    
    args = parser.parse_args()
    
    setup = MempoolConfigSetup()
    
    if args.quick:
        setup.create_quick_setup()
    else:
        setup.run_interactive_setup()


if __name__ == "__main__":
    main()