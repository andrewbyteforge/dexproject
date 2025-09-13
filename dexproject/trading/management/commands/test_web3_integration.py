"""
Management command to test Web3 integration and trading tasks

This command provides comprehensive testing of the Web3 integration,
wallet management, and trading tasks in a safe testnet environment.

File: dexproject/trading/management/commands/test_web3_integration.py
"""

import asyncio
import time
from typing import Dict, Any
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from celery import current_app

from engine.config import config
from engine.testnet_config import (
    get_testnet_chain_configs, 
    get_testnet_info, 
    get_testnet_faucet_instructions,
    validate_testnet_environment,
    TestnetSetupGuide
)

# Import trading tasks
from trading.tasks import (
    execute_buy_order,
    execute_sell_order, 
    emergency_exit,
    check_wallet_status,
    estimate_trade_cost
)

# Import risk tasks
from risk.tasks import assess_token_risk


class Command(BaseCommand):
    help = 'Test Web3 integration and trading tasks with comprehensive validation'

    def add_arguments(self, parser):
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
        self.verbosity = options['verbosity']
        self.verbose = options['verbose']
        chain_id = options['chain_id']
        
        self.stdout.write(
            self.style.SUCCESS('🚀 DEX Trading Bot - Web3 Integration Test')
        )
        self.stdout.write('=' * 60)
        
        try:
            # Step 1: Environment validation
            if not options['skip_setup']:
                self.validate_environment()
                self.show_setup_guide(chain_id)
            
            # Step 2: Basic connectivity tests
            self.test_basic_connectivity()
            
            # Step 3: Wallet status tests  
            self.test_wallet_status(chain_id)
            
            # Step 4: Cost estimation tests
            self.test_cost_estimation(chain_id, options['amount_eth'])
            
            # Step 5: Risk assessment tests
            if options['test_risk']:
                self.test_risk_assessment(chain_id)
            
            # Step 6: Trading task tests
            if options['test_trading']:
                self.test_trading_tasks(chain_id, options['amount_eth'])
            
            # Step 7: Summary
            self.show_test_summary()
            
        except Exception as e:
            raise CommandError(f'Test failed: {str(e)}')

    def validate_environment(self):
        """Validate environment configuration."""
        self.stdout.write('\n🔍 Validating Environment Configuration...')
        
        validation = validate_testnet_environment()
        
        if validation['errors']:
            self.stdout.write(self.style.ERROR('❌ Environment Errors:'))
            for error in validation['errors']:
                self.stdout.write(f'   • {error}')
            raise CommandError('Environment validation failed')
        
        if validation['warnings']:
            self.stdout.write(self.style.WARNING('⚠️  Environment Warnings:'))
            for warning in validation['warnings']:
                self.stdout.write(f'   • {warning}')
        
        if validation['recommendations']:
            self.stdout.write(self.style.NOTICE('💡 Recommendations:'))
            for rec in validation['recommendations']:
                self.stdout.write(f'   • {rec}')
        
        if validation['is_valid']:
            self.stdout.write(self.style.SUCCESS('✅ Environment validation passed'))
        
    def show_setup_guide(self, chain_id: int):
        """Show setup guide for the specified chain."""
        self.stdout.write('\n📋 Setup Guide:')
        
        testnet_info = get_testnet_info(chain_id)
        if not testnet_info:
            self.stdout.write(self.style.ERROR(f'❌ Unknown chain ID: {chain_id}'))
            return
        
        instructions = get_testnet_faucet_instructions(chain_id)
        
        self.stdout.write(f'   Chain: {testnet_info.name} (ID: {chain_id})')
        self.stdout.write(f'   Currency: {testnet_info.currency_symbol}')
        self.stdout.write(f'   Explorer: {testnet_info.block_explorer}')
        
        self.stdout.write('\n💰 Get Testnet Funds:')
        for i, url in enumerate(instructions['faucet_urls'], 1):
            self.stdout.write(f'   {i}. {url}')
        
        self.stdout.write('\n📝 Instructions:')
        for instruction in instructions['instructions']:
            self.stdout.write(f'   {instruction}')

    def test_basic_connectivity(self):
        """Test basic Celery and Redis connectivity."""
        self.stdout.write('\n🔌 Testing Basic Connectivity...')
        
        # Test Celery connection
        try:
            i = current_app.control.inspect()
            stats = i.stats()
            if stats:
                active_workers = len(stats)
                self.stdout.write(f'✅ Celery: {active_workers} workers active')
            else:
                self.stdout.write(self.style.WARNING('⚠️  Celery: No workers found'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Celery connection failed: {e}'))
        
        # Test Redis connection (via Celery)
        try:
            from celery import current_app
            current_app.broker_connection().connect()
            self.stdout.write('✅ Redis: Connection successful')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Redis connection failed: {e}'))

    def test_wallet_status(self, chain_id: int):
        """Test wallet status and balance checking."""
        self.stdout.write(f'\n💼 Testing Wallet Status (Chain {chain_id})...')
        
        try:
            # Test wallet status task
            result = check_wallet_status.delay(chain_id=chain_id)
            status_data = result.get(timeout=30)
            
            if status_data['status'] == 'completed':
                self.stdout.write('✅ Wallet status check successful')
                
                if self.verbose:
                    manager_status = status_data['manager_status']
                    self.stdout.write(f'   Wallets: {manager_status["total_wallets"]}')
                    self.stdout.write(f'   Trading enabled: {manager_status["trading_enabled_wallets"]}')
                    self.stdout.write(f'   Web3 connected: {manager_status["web3_connected"]}')
                
                # Show wallet balances
                for wallet in status_data.get('wallet_balances', []):
                    balance_info = wallet['balance_info']
                    if balance_info['status'] == 'success':
                        eth_balance = balance_info['eth_balance']
                        self.stdout.write(
                            f'   Wallet {wallet["address"][:10]}...: '
                            f'{eth_balance} ETH'
                        )
                        
                        # Warn if balance is low
                        if Decimal(eth_balance) < Decimal('0.01'):
                            self.stdout.write(
                                self.style.WARNING(
                                    f'   ⚠️  Low balance! Get testnet funds from faucet'
                                )
                            )
                    else:
                        self.stdout.write(
                            self.style.ERROR(
                                f'   ❌ Failed to get balance: {balance_info.get("error")}'
                            )
                        )
            else:
                self.stdout.write(
                    self.style.ERROR(f'❌ Wallet status check failed: {status_data.get("error")}')
                )
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Wallet status test failed: {e}'))

    def test_cost_estimation(self, chain_id: int, amount_eth: str):
        """Test trade cost estimation."""
        self.stdout.write(f'\n💰 Testing Cost Estimation...')
        
        # Use placeholder addresses for testing
        test_pair = '0x1234567890123456789012345678901234567890'
        test_token = '0x0987654321098765432109876543210987654321'
        
        try:
            result = estimate_trade_cost.delay(
                pair_address=test_pair,
                token_address=test_token,
                amount_eth=amount_eth,
                trade_type='BUY',
                chain_id=chain_id
            )
            
            cost_data = result.get(timeout=30)
            
            if cost_data['status'] == 'completed':
                self.stdout.write('✅ Cost estimation successful')
                
                if self.verbose:
                    estimates = cost_data['cost_estimates']
                    self.stdout.write('   Gas price estimates:')
                    for level, data in estimates.items():
                        self.stdout.write(
                            f'     {level.capitalize()}: {data["gas_price_gwei"]} gwei '
                            f'(Total: {data["total_cost_eth"]} ETH)'
                        )
            else:
                self.stdout.write(
                    self.style.ERROR(f'❌ Cost estimation failed: {cost_data.get("error")}')
                )
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Cost estimation test failed: {e}'))

    def test_risk_assessment(self, chain_id: int):
        """Test risk assessment functionality."""
        self.stdout.write(f'\n🛡️  Testing Risk Assessment...')
        
        # Use placeholder addresses for testing
        test_token = '0x1234567890123456789012345678901234567890'
        test_pair = '0x0987654321098765432109876543210987654321'
        
        try:
            result = assess_token_risk.delay(
                token_address=test_token,
                pair_address=test_pair,
                risk_profile='Conservative'
            )
            
            risk_data = result.get(timeout=60)  # Risk assessment can take longer
            
            if risk_data['status'] == 'completed':
                self.stdout.write('✅ Risk assessment successful')
                
                if self.verbose:
                    self.stdout.write(f'   Overall risk score: {risk_data.get("overall_risk_score", "N/A")}')
                    self.stdout.write(f'   Risk level: {risk_data.get("risk_level", "N/A")}')
                    self.stdout.write(f'   Trading decision: {risk_data.get("trading_decision", "N/A")}')
                    
                    # Show individual check results
                    check_results = risk_data.get('check_results', [])
                    if check_results:
                        self.stdout.write('   Individual checks:')
                        for check in check_results:
                            status = check.get('status', 'UNKNOWN')
                            check_type = check.get('check_type', 'UNKNOWN')
                            risk_score = check.get('risk_score', 0)
                            self.stdout.write(f'     {check_type}: {status} (Score: {risk_score})')
            else:
                self.stdout.write(
                    self.style.ERROR(f'❌ Risk assessment failed: {risk_data.get("error")}')
                )
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Risk assessment test failed: {e}'))

    def test_trading_tasks(self, chain_id: int, amount_eth: str):
        """Test actual trading task execution."""
        self.stdout.write(f'\n🔄 Testing Trading Tasks...')
        
        # Confirm with user before running trading tests
        if not settings.TRADING_MODE == 'PAPER':
            self.stdout.write(
                self.style.ERROR('❌ Trading tests require TRADING_MODE=PAPER for safety')
            )
            return
        
        # Use placeholder addresses for testing
        test_pair = '0x1234567890123456789012345678901234567890' 
        test_token = '0x0987654321098765432109876543210987654321'
        
        self.stdout.write(
            self.style.WARNING(
                f'⚠️  Running paper trading tests with {amount_eth} ETH on chain {chain_id}'
            )
        )
        
        # Test buy order
        try:
            self.stdout.write('   Testing buy order...')
            result = execute_buy_order.delay(
                pair_address=test_pair,
                token_address=test_token,
                amount_eth=amount_eth,
                slippage_tolerance=0.05,
                chain_id=chain_id
            )
            
            buy_data = result.get(timeout=60)
            
            if buy_data['status'] == 'completed':
                self.stdout.write('   ✅ Buy order test successful')
                if self.verbose:
                    tx_hash = buy_data.get('transaction_hash', 'N/A')
                    mode = buy_data.get('mode', 'UNKNOWN')
                    self.stdout.write(f'      Mode: {mode}')
                    self.stdout.write(f'      TX Hash: {tx_hash}')
            else:
                self.stdout.write(
                    self.style.ERROR(f'   ❌ Buy order failed: {buy_data.get("error")}')
                )
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ❌ Buy order test failed: {e}'))
        
        # Test sell order
        try:
            self.stdout.write('   Testing sell order...')
            result = execute_sell_order.delay(
                pair_address=test_pair,
                token_address=test_token,
                token_amount='1000',  # 1000 tokens
                slippage_tolerance=0.05,
                is_emergency=False,
                chain_id=chain_id
            )
            
            sell_data = result.get(timeout=60)
            
            if sell_data['status'] == 'completed':
                self.stdout.write('   ✅ Sell order test successful')
                if self.verbose:
                    tx_hash = sell_data.get('transaction_hash', 'N/A')
                    mode = sell_data.get('mode', 'UNKNOWN')
                    self.stdout.write(f'      Mode: {mode}')
                    self.stdout.write(f'      TX Hash: {tx_hash}')
            else:
                self.stdout.write(
                    self.style.ERROR(f'   ❌ Sell order failed: {sell_data.get("error")}')
                )
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ❌ Sell order test failed: {e}'))
        
        # Test emergency exit
        try:
            self.stdout.write('   Testing emergency exit...')
            result = emergency_exit.delay(
                position_id='test-position-123',
                reason='Testing emergency exit functionality',
                max_slippage=0.15,
                chain_id=chain_id
            )
            
            exit_data = result.get(timeout=60)
            
            if exit_data['status'] == 'completed':
                self.stdout.write('   ✅ Emergency exit test successful')
                if self.verbose:
                    sell_result = exit_data.get('sell_order_result', {})
                    self.stdout.write(f'      Emergency reason: {exit_data.get("reason")}')
                    self.stdout.write(f'      Sell status: {sell_result.get("status", "N/A")}')
            else:
                self.stdout.write(
                    self.style.ERROR(f'   ❌ Emergency exit failed: {exit_data.get("error")}')
                )
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ❌ Emergency exit test failed: {e}'))

    def show_test_summary(self):
        """Show test summary and next steps."""
        self.stdout.write('\n📊 Test Summary:')
        self.stdout.write(self.style.SUCCESS('✅ Web3 integration tests completed'))
        
        self.stdout.write('\n🚀 Next Steps:')
        self.stdout.write('1. If tests passed: Your Web3 integration is working!')
        self.stdout.write('2. Fund your testnet wallet if balances are low')
        self.stdout.write('3. Run risk assessment tests: --test-risk')
        self.stdout.write('4. Run trading tests: --test-trading')
        self.stdout.write('5. Monitor logs for detailed execution information')
        self.stdout.write('6. When ready, configure for mainnet (TESTNET_MODE=False)')
        
        self.stdout.write('\n📚 Useful Commands:')
        self.stdout.write('   # Test specific chain')
        self.stdout.write('   python manage.py test_web3_integration --chain-id 11155111')
        self.stdout.write('   ')
        self.stdout.write('   # Full test suite')
        self.stdout.write('   python manage.py test_web3_integration --test-risk --test-trading --verbose')
        self.stdout.write('   ')
        self.stdout.write('   # Check Celery workers')
        self.stdout.write('   celery -A dexproject worker --loglevel=info')
        
        if settings.TESTNET_MODE:
            testnet_info = get_testnet_info(settings.DEFAULT_CHAIN_ID)
            if testnet_info:
                self.stdout.write(f'\n🌐 Block Explorer: {testnet_info.block_explorer}')
                self.stdout.write('   Monitor your transactions and wallet activity')