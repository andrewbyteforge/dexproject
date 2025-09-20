"""
Management command to test Web3 integration and trading tasks

This command provides comprehensive testing of the Web3 integration,
wallet management, and trading tasks in a safe testnet environment.

File: trading/management/commands/test_web3_integration.py
"""

import asyncio
import time
from typing import Dict, Any
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from celery import current_app

# Import trading tasks
from trading.tasks import (
    execute_buy_order,
    execute_sell_order, 
    emergency_exit,
    check_wallet_status,
    estimate_trade_cost
)


class Command(BaseCommand):
    """Test Web3 integration and trading tasks with comprehensive validation."""
    
    help = 'Test Web3 integration and trading tasks with comprehensive validation'

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            '--chain-id',
            type=int,
            default=84532,  # Base Sepolia
            help='Chain ID to test (default: 84532 - Base Sepolia)'
        )
        
        parser.add_argument(
            '--skip-setup',
            action='store_true',
            help='Skip setup instructions and validation'
        )
        
        parser.add_argument(
            '--test-trading',
            action='store_true',
            help='Run actual trading task tests (requires funded wallet)'
        )
        
        parser.add_argument(
            '--test-risk',
            action='store_true',
            help='Run risk assessment tests'
        )
        
        parser.add_argument(
            '--amount-eth',
            type=str,
            default='0.001',
            help='Amount of ETH to use for test trades (default: 0.001)'
        )
        
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose output'
        )

    def handle(self, *args, **options):
        """Main command handler."""
        self.verbosity = options.get('verbosity', 1)
        self.verbose = options.get('verbose', False)
        
        chain_id = options.get('chain_id', 84532)
        test_trading = options.get('test_trading', False)
        test_risk = options.get('test_risk', False)
        amount_eth = options.get('amount_eth', '0.001')
        
        self.stdout.write(
            self.style.SUCCESS("🚀 Trading Web3 Integration Test")
        )
        self.stdout.write("=" * 60)
        
        # Validate environment
        self._validate_environment()
        
        # Validate Celery
        self._validate_celery()
        
        # Test wallet status
        self._test_wallet_status(chain_id)
        
        # Test trading if requested
        if test_trading:
            self._test_trading_tasks(chain_id, amount_eth)
        
        # Test risk assessment if requested
        if test_risk:
            self._test_risk_assessment()
        
        # Show summary
        self._show_test_summary()
    
    def _validate_environment(self):
        """Validate environment configuration."""
        self.stdout.write("🔍 Validating Environment...")
        
        # Check trading mode
        trading_mode = getattr(settings, 'TRADING_MODE', 'UNKNOWN')
        if trading_mode not in ['PAPER', 'LIVE']:
            raise CommandError(f"Invalid TRADING_MODE: {trading_mode}. Set TRADING_MODE=PAPER for testing.")
        
        # Check testnet mode
        testnet_mode = getattr(settings, 'TESTNET_MODE', False)
        if not testnet_mode:
            self.stdout.write(
                self.style.WARNING("⚠️  Running in mainnet mode - be careful!")
            )
        
        self.stdout.write(
            self.style.SUCCESS(f"✅ Environment: {trading_mode} mode, Testnet: {testnet_mode}")
        )
    
    def _validate_celery(self):
        """Validate Celery configuration."""
        self.stdout.write("🔍 Validating Celery...")
        
        try:
            # Check if Celery is configured
            app = current_app
            self.stdout.write(
                self.style.SUCCESS(f"✅ Celery configured: {app.main}")
            )
            
            # Check if worker is running (optional)
            try:
                inspect = app.control.inspect()
                stats = inspect.stats()
                if stats:
                    worker_count = len(stats)
                    self.stdout.write(
                        self.style.SUCCESS(f"✅ Celery workers active: {worker_count}")
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING("⚠️  No active Celery workers detected")
                    )
                    self.stdout.write("   Start workers: celery -A dexproject worker --loglevel=info")
            except Exception:
                self.stdout.write(
                    self.style.WARNING("⚠️  Could not check worker status")
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Celery validation failed: {e}")
            )
    
    def _test_wallet_status(self, chain_id: int):
        """Test wallet status checking."""
        self.stdout.write("👛 Testing Wallet Status...")
        
        try:
            # Use a test wallet address
            test_address = "0x742d35Cc4Bf8b5263F84e3fb527f5b4aF38877B6"
            
            result = check_wallet_status.delay(
                wallet_address=test_address,
                chain_id=chain_id
            )
            
            wallet_data = result.get(timeout=30)
            
            if wallet_data.get('status') == 'completed':
                self.stdout.write("   ✅ Wallet status check successful")
                if self.verbose:
                    self.stdout.write(f"      Address: {test_address}")
                    self.stdout.write(f"      Chain: {chain_id}")
            else:
                self.stdout.write(
                    self.style.WARNING(f"   ⚠️  Wallet status check returned: {wallet_data.get('status')}")
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"   ❌ Wallet status test failed: {e}")
            )
    
    def _test_trading_tasks(self, chain_id: int, amount_eth: str):
        """Test trading task execution."""
        self.stdout.write(f"🔄 Testing Trading Tasks...")
        
        # Confirm with user before running trading tests
        trading_mode = getattr(settings, 'TRADING_MODE', 'UNKNOWN')
        if trading_mode != 'PAPER':
            self.stdout.write(
                self.style.ERROR('❌ Trading tests require TRADING_MODE=PAPER for safety')
            )
            return
        
        # Use placeholder addresses for testing
        test_pair = '0x1234567890123456789012345678901234567890' 
        test_token = '0x0987654321098765432109876543210987654321'
        
        self.stdout.write(
            self.style.WARNING(
                f"⚠️  Running paper trading tests with {amount_eth} ETH on chain {chain_id}"
            )
        )
        
        # Test buy order
        try:
            self.stdout.write("   Testing buy order...")
            result = execute_buy_order.delay(
                pair_address=test_pair,
                token_address=test_token,
                amount_eth=amount_eth,
                slippage_tolerance=0.05,
                chain_id=chain_id
            )
            
            buy_data = result.get(timeout=60)
            
            if buy_data.get('status') == 'completed':
                self.stdout.write("   ✅ Buy order test successful")
                if self.verbose:
                    tx_hash = buy_data.get('transaction_hash', 'N/A')
                    mode = buy_data.get('mode', 'UNKNOWN')
                    self.stdout.write(f"      Mode: {mode}")
                    self.stdout.write(f"      TX Hash: {tx_hash[:10]}...")
                    tokens_received = buy_data.get('tokens_received', 'N/A')
                    self.stdout.write(f"      Tokens: {tokens_received}")
            else:
                self.stdout.write(
                    self.style.ERROR(f"   ❌ Buy order failed: {buy_data.get('error', 'Unknown error')}")
                )
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ❌ Buy order test failed: {e}"))
        
        # Test sell order
        try:
            self.stdout.write("   Testing sell order...")
            result = execute_sell_order.delay(
                pair_address=test_pair,
                token_address=test_token,
                token_amount='1000000000000000000000',  # 1000 tokens (18 decimals)
                slippage_tolerance=0.05,
                is_emergency=False,
                chain_id=chain_id
            )
            
            sell_data = result.get(timeout=60)
            
            if sell_data.get('status') == 'completed':
                self.stdout.write("   ✅ Sell order test successful")
                if self.verbose:
                    tx_hash = sell_data.get('transaction_hash', 'N/A')
                    mode = sell_data.get('mode', 'UNKNOWN')
                    self.stdout.write(f"      Mode: {mode}")
                    self.stdout.write(f"      TX Hash: {tx_hash[:10]}...")
                    eth_received = sell_data.get('eth_received', 'N/A')
                    self.stdout.write(f"      ETH: {eth_received}")
            else:
                self.stdout.write(
                    self.style.ERROR(f"   ❌ Sell order failed: {sell_data.get('error', 'Unknown error')}")
                )
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ❌ Sell order test failed: {e}"))
        
        # Test emergency exit
        try:
            self.stdout.write("   Testing emergency exit...")
            result = emergency_exit.delay(
                position_id='test-position-123',
                reason='Testing emergency exit functionality',
                max_slippage=0.15,
                chain_id=chain_id
            )
            
            exit_data = result.get(timeout=60)
            
            if exit_data.get('status') == 'completed':
                self.stdout.write("   ✅ Emergency exit test successful")
                if self.verbose:
                    reason = exit_data.get('reason', 'N/A')
                    self.stdout.write(f"      Reason: {reason}")
                    sell_result = exit_data.get('sell_result', {})
                    self.stdout.write(f"      Sell status: {sell_result.get('status', 'N/A')}")
            else:
                self.stdout.write(
                    self.style.ERROR(f"   ❌ Emergency exit failed: {exit_data.get('error', 'Unknown error')}")
                )
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ❌ Emergency exit test failed: {e}"))
        
        # Test trade cost estimation
        try:
            self.stdout.write("   Testing trade cost estimation...")
            result = estimate_trade_cost.delay(
                token_address=test_token,
                amount_eth=amount_eth,
                operation='BUY',
                chain_id=chain_id
            )
            
            cost_data = result.get(timeout=30)
            
            if cost_data.get('status') == 'completed':
                self.stdout.write("   ✅ Trade cost estimation successful")
                if self.verbose:
                    estimated_gas = cost_data.get('estimated_gas', 'N/A')
                    gas_cost = cost_data.get('gas_cost_eth', {})
                    self.stdout.write(f"      Estimated gas: {estimated_gas}")
                    self.stdout.write(f"      Gas cost (fast): {gas_cost.get('fast', 'N/A')} ETH")
            else:
                self.stdout.write(
                    self.style.ERROR(f"   ❌ Cost estimation failed: {cost_data.get('error', 'Unknown error')}")
                )
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ❌ Cost estimation test failed: {e}"))

    def _test_risk_assessment(self):
        """Test risk assessment functionality."""
        self.stdout.write("🛡️  Testing Risk Assessment...")
        
        try:
            # Try to import and test risk assessment
            from risk.tasks import assess_token_risk
            
            test_token = "0x1234567890123456789012345678901234567890"
            test_pair = "0x0987654321098765432109876543210987654321"
            
            self.stdout.write("   Testing token risk assessment...")
            
            result = assess_token_risk.delay(
                token_address=test_token,
                pair_address=test_pair,
                assessment_id='test-assessment-123',
                risk_profile='Conservative'
            )
            
            risk_data = result.get(timeout=60)
            
            if risk_data.get('status') == 'completed':
                self.stdout.write("   ✅ Risk assessment test successful")
                if self.verbose:
                    risk_level = risk_data.get('overall_risk_level', 'N/A')
                    confidence = risk_data.get('confidence_score', 'N/A')
                    self.stdout.write(f"      Risk level: {risk_level}")
                    self.stdout.write(f"      Confidence: {confidence}")
            else:
                self.stdout.write(
                    self.style.WARNING(f"   ⚠️  Risk assessment returned: {risk_data.get('status')}")
                )
                
        except ImportError:
            self.stdout.write(
                self.style.WARNING("   ⚠️  Risk assessment module not available")
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"   ❌ Risk assessment test failed: {e}")
            )

    def _show_test_summary(self):
        """Show test summary and next steps."""
        self.stdout.write("\n📊 Test Summary:")
        self.stdout.write(self.style.SUCCESS("✅ Trading Web3 integration tests completed"))
        
        self.stdout.write("\n🚀 Next Steps:")
        self.stdout.write("1. If tests passed: Your trading system is working!")
        self.stdout.write("2. Fund your testnet wallet if balances are low")
        self.stdout.write("3. Test with real DEX pairs for live validation")
        self.stdout.write("4. Monitor logs for detailed execution information")
        self.stdout.write("5. When ready, switch to mainnet (TESTNET_MODE=False)")
        
        self.stdout.write("\n📚 Useful Commands:")
        self.stdout.write("   # Test trading functionality")
        self.stdout.write("   python manage.py test_web3_integration --test-trading --verbose")
        self.stdout.write("")
        self.stdout.write("   # Test risk assessment")
        self.stdout.write("   python manage.py test_web3_integration --test-risk --verbose")
        self.stdout.write("")
        self.stdout.write("   # Full test suite")
        self.stdout.write("   python manage.py test_web3_integration --test-trading --test-risk --verbose")
        self.stdout.write("")
        self.stdout.write("   # Start Celery workers")
        self.stdout.write("   celery -A dexproject worker --loglevel=info")
        
        testnet_mode = getattr(settings, 'TESTNET_MODE', False)
        if testnet_mode:
            self.stdout.write("\n🌐 Testnet Resources:")
            self.stdout.write("   Base Sepolia: https://sepolia.basescan.org/")
            self.stdout.write("   Ethereum Sepolia: https://sepolia.etherscan.io/")
            self.stdout.write("   Monitor your transactions and wallet activity")