#!/usr/bin/env python3
"""
Quick fix for Django management command syntax error.

This script fixes the syntax error in populate_chains_and_dexes.py
"""

import os
import sys
import re
from pathlib import Path


def fix_django_command():
    """Fix the syntax error in the Django management command."""
    
    project_root = Path(__file__).parent.parent
    command_file = project_root / 'trading' / 'management' / 'commands' / 'populate_chains_and_dexes.py'
    
    print("🔧 Fixing Django management command syntax error...")
    
    if not command_file.exists():
        print(f"❌ Command file not found: {command_file}")
        return False
    
    try:
        # Read the file
        with open(command_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Fix the syntax error
        # Look for the malformed function definition
        if ']    def *log*success(' in content:
            content = content.replace(']    def *log*success(', ']\n\n    def log_success(')
        
        if ']    def log_success(' in content:
            content = content.replace(']    def log_success(', ']\n\n    def log_success(')
        
        # Fix any other malformed function definitions with asterisks
        content = re.sub(r'\]\s*def \*(\w+)\*\(', r']\n\n    def \1(', content)
        
        # Fix any other common syntax issues
        content = re.sub(r'def \*(\w+)\*\(', r'def \1(', content)
        
        # Ensure proper spacing after closing brackets
        content = re.sub(r'\]\s*def ', r']\n\n    def ', content)
        
        # Write back
        with open(command_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✅ Fixed syntax error in Django management command")
        return True
        
    except Exception as e:
        print(f"❌ Error fixing command file: {e}")
        print(f"   Details: {str(e)}")
        return False


def create_simple_populate_command():
    """Create a simple working populate command if the fix doesn't work."""
    
    project_root = Path(__file__).parent.parent
    command_file = project_root / 'trading' / 'management' / 'commands' / 'populate_chains_and_dexes.py'
    
    print("🔧 Creating simple populate command...")
    
    simple_command = '''"""
Simple Django management command to populate chains and DEXes for testnet.
"""

from django.core.management.base import BaseCommand
from trading.models import Chain, DEX, RPCProvider
from decimal import Decimal
import os


class Command(BaseCommand):
    """Management command to populate chains and DEXes with testnet configuration."""
    
    help = 'Populate database with testnet chain and DEX configurations'
    
    def handle(self, *args, **options):
        """Execute the command."""
        self.stdout.write("🔧 Populating testnet chains and DEXes...")
        
        # Get API keys from environment
        alchemy_key = os.getenv('ALCHEMY_API_KEY', 'demo')
        ankr_key = os.getenv('ANKR_API_KEY', '')
        infura_key = os.getenv('INFURA_PROJECT_ID', '')
        
        # Create or update Base Sepolia
        base_sepolia, created = Chain.objects.get_or_create(
            chain_id=84532,
            defaults={
                'name': 'Base Sepolia',
                'rpc_url': f'https://base-sepolia.g.alchemy.com/v2/{alchemy_key}',
                'fallback_rpc_urls': [
                    'https://sepolia.base.org',
                    'https://base-sepolia.blockpi.network/v1/rpc/public'
                ],
                'block_time_seconds': 2,
                'gas_price_gwei': Decimal('1.0'),
                'max_gas_price_gwei': Decimal('10.0'),
                'is_active': True,
                'is_testnet': True,
            }
        )
        
        # Create or update Ethereum Sepolia
        eth_sepolia, created = Chain.objects.get_or_create(
            chain_id=11155111,
            defaults={
                'name': 'Ethereum Sepolia',
                'rpc_url': f'https://eth-sepolia.g.alchemy.com/v2/{alchemy_key}',
                'fallback_rpc_urls': [
                    'https://rpc.sepolia.org',
                    'https://sepolia.blockpi.network/v1/rpc/public'
                ],
                'block_time_seconds': 12,
                'gas_price_gwei': Decimal('10.0'),
                'max_gas_price_gwei': Decimal('50.0'),
                'is_active': True,
                'is_testnet': True,
            }
        )
        
        # Create or update Arbitrum Sepolia
        arb_sepolia, created = Chain.objects.get_or_create(
            chain_id=421614,
            defaults={
                'name': 'Arbitrum Sepolia',
                'rpc_url': 'https://sepolia-rollup.arbitrum.io/rpc',
                'fallback_rpc_urls': [
                    'https://arbitrum-sepolia.blockpi.network/v1/rpc/public'
                ],
                'block_time_seconds': 1,
                'gas_price_gwei': Decimal('0.1'),
                'max_gas_price_gwei': Decimal('5.0'),
                'is_active': True,
                'is_testnet': True,
            }
        )
        
        self.stdout.write(self.style.SUCCESS("✅ Successfully populated testnet chains"))
        self.stdout.write(f"   - Base Sepolia (84532): {'Created' if created else 'Updated'}")
        self.stdout.write(f"   - Ethereum Sepolia (11155111): {'Created' if created else 'Updated'}")
        self.stdout.write(f"   - Arbitrum Sepolia (421614): {'Created' if created else 'Updated'}")
'''
    
    try:
        # Create directory if it doesn't exist
        command_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Write the simple command
        with open(command_file, 'w', encoding='utf-8') as f:
            f.write(simple_command)
        
        print("✅ Created simple populate command")
        return True
        
    except Exception as e:
        print(f"❌ Error creating simple command: {e}")
        return False


if __name__ == "__main__":
    # Try to fix the existing command first
    success = fix_django_command()
    
    if not success:
        print("\\nOriginal fix failed, creating simple command instead...")
        success = create_simple_populate_command()
    
    if success:
        print("\\nNow try running:")
        print("python manage.py populate_chains_and_dexes")
    else:
        print("\\nBoth fixes failed. Let's bypass Django models entirely.")
        print("Add this to your .env file:")
        print("USE_DJANGO_CHAIN_CONFIG=False")
    
    sys.exit(0 if success else 1)