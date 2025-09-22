"""
Windows-Compatible Django Management Command for Gas Optimizer Testing

Fixed version that handles Windows console encoding issues properly.

File: trading/management/commands/test_gas_optimizer.py (UPDATED)
"""

import asyncio
import time
import sys
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings


def safe_write(stdout, message, style=None):
    """Write message safely to stdout with Windows compatibility."""
    if sys.platform.startswith('win'):
        # Replace emoji with ASCII equivalents for Windows
        emoji_map = {
            '🔧': '[INIT]',
            '🚀': '[START]',  
            '✅': '[OK]',
            '❌': '[ERROR]',
            '⚡': '[GAS]',
            '📊': '[DATA]',
            '💰': '[COST]',
            '💸': '[SAVE]',
            '📝': '[PAPER]',
            '🎭': '[SIM]',
            '🚨': '[ALERT]',
            '⚠️': '[WARN]',
            '🔄': '[UPDATE]',
            '📈': '[STATS]',
            '📺': '[OUT]',
            '🌐': '[NET]',
            '🎯': '[TARGET]',
            '🧪': '[TEST]',
            '🏃‍♂️': '[QUICK]',
            '🎉': '[SUCCESS]'
        }
        
        for emoji, replacement in emoji_map.items():
            message = message.replace(emoji, replacement)
    
    try:
        if style:
            stdout.write(style(message))
        else:
            stdout.write(message)
    except UnicodeEncodeError:
        # Final fallback: encode to ASCII
        safe_message = message.encode('ascii', 'replace').decode('ascii')
        if style:
            stdout.write(style(safe_message))
        else:
            stdout.write(safe_message)


class Command(BaseCommand):
    """Windows-compatible Django management command for testing gas optimizer."""
    
    help = 'Test the Django Gas Optimization Service with live console output (Windows compatible)'
    
    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            '--mode',
            type=str,
            default='full',
            choices=['full', 'quick', 'monitor', 'emergency'],
            help='Test mode: full (all tests), quick (basic tests), monitor (live monitoring), emergency (emergency stop test)'
        )
        
        parser.add_argument(
            '--chain',
            type=int,
            default=None,
            help='Specific chain ID to test (default: test all configured chains)'
        )
        
        parser.add_argument(
            '--duration',
            type=int,
            default=30,
            help='Duration for monitoring mode in seconds (default: 30)'
        )
        
        parser.add_argument(
            '--paper-only',
            action='store_true',
            help='Run only paper trading tests (safer for production)'
        )
    
    def handle(self, *args, **options):
        """Handle the management command."""
        safe_write(self.stdout, '[START] Starting Gas Optimizer Testing...', self.style.SUCCESS)
        
        mode = options['mode']
        chain_id = options.get('chain')
        duration = options['duration']
        paper_only = options['paper_only']
        
        try:
            if mode == 'full':
                asyncio.run(self.run_full_test(chain_id, paper_only))
            elif mode == 'quick':
                asyncio.run(self.run_quick_test(chain_id, paper_only))
            elif mode == 'monitor':
                asyncio.run(self.run_monitoring_test(duration))
            elif mode == 'emergency':
                asyncio.run(self.run_emergency_test())
            
            safe_write(self.stdout, '[OK] Gas optimizer testing completed successfully', self.style.SUCCESS)
            
        except Exception as e:
            safe_write(self.stdout, f'[ERROR] Testing failed: {e}', self.style.ERROR)
            raise CommandError(f'Gas optimizer test failed: {e}')
    
    async def run_full_test(self, specific_chain=None, paper_only=False):
        """Run comprehensive gas optimizer tests."""
        safe_write(self.stdout, '=' * 80, self.style.HTTP_INFO)
        safe_write(self.stdout, '[TEST] COMPREHENSIVE GAS OPTIMIZER TEST', self.style.HTTP_INFO)
        safe_write(self.stdout, '=' * 80, self.style.HTTP_INFO)
        
        from trading.services.gas_optimizer import (
            get_gas_optimizer,
            optimize_trade_gas,
            TradingGasStrategy
        )
        
        # Initialize optimizer
        safe_write(self.stdout, '[INIT] Initializing gas optimizer...')
        optimizer = await get_gas_optimizer()
        
        if not optimizer:
            raise CommandError('Failed to initialize gas optimizer')
        
        safe_write(self.stdout, '[OK] Gas optimizer initialized', self.style.SUCCESS)
        
        # Wait for initialization
        await asyncio.sleep(2)
        
        # Define test chains
        test_chains = [specific_chain] if specific_chain else [1, 8453]  # ETH and Base
        
        # Define comprehensive test scenarios
        test_scenarios = []
        
        for chain_id in test_chains:
            chain_name = 'Ethereum' if chain_id == 1 else 'Base' if chain_id == 8453 else f'Chain {chain_id}'
            
            # Paper trading scenarios
            test_scenarios.extend([
                {
                    'name': f'Paper Trading - Small Buy ({chain_name})',
                    'chain_id': chain_id,
                    'trade_type': 'buy',
                    'amount_usd': Decimal('50'),
                    'strategy': 'balanced',
                    'is_paper_trade': True
                },
                {
                    'name': f'Paper Trading - Medium Sell ({chain_name})',
                    'chain_id': chain_id,
                    'trade_type': 'sell',
                    'amount_usd': Decimal('500'),
                    'strategy': 'cost_efficient',
                    'is_paper_trade': True
                }
            ])
            
            # Live trading scenarios (only if not paper-only mode)
            if not paper_only:
                test_scenarios.extend([
                    {
                        'name': f'Live Trading - Speed Priority ({chain_name})',
                        'chain_id': chain_id,
                        'trade_type': 'buy',
                        'amount_usd': Decimal('1000'),
                        'strategy': 'speed_priority',
                        'is_paper_trade': False
                    },
                    {
                        'name': f'Live Trading - MEV Protected Swap ({chain_name})',
                        'chain_id': chain_id,
                        'trade_type': 'swap',
                        'amount_usd': Decimal('2500'),
                        'strategy': 'mev_protected',
                        'is_paper_trade': False
                    }
                ])
        
        # Run test scenarios
        safe_write(self.stdout, f'\n[DATA] Running {len(test_scenarios)} test scenarios...')
        
        successful_tests = 0
        failed_tests = 0
        
        for i, scenario in enumerate(test_scenarios, 1):
            safe_write(self.stdout, f'\n[TEST] Test {i}/{len(test_scenarios)}: {scenario["name"]}')
            safe_write(self.stdout, '-' * 60)
            
            try:
                result = await optimize_trade_gas(
                    chain_id=scenario['chain_id'],
                    trade_type=scenario['trade_type'],
                    amount_usd=scenario['amount_usd'],
                    strategy=scenario['strategy'],
                    is_paper_trade=scenario['is_paper_trade']
                )
                
                if result.success:
                    successful_tests += 1
                    safe_write(self.stdout, '[OK] Optimization successful', self.style.SUCCESS)
                    
                    if result.gas_price:
                        gas_price = result.gas_price
                        safe_write(self.stdout, f'   [COST] Strategy: {gas_price.strategy.value}')
                        safe_write(self.stdout, f'   [GAS] Max Fee: {gas_price.max_fee_per_gas_gwei} gwei')
                        safe_write(self.stdout, f'   [GAS] Priority Fee: {gas_price.max_priority_fee_per_gas_gwei} gwei')
                        if gas_price.estimated_cost_usd:
                            safe_write(self.stdout, f'   [COST] Est. Cost: ${gas_price.estimated_cost_usd}')
                        safe_write(self.stdout, f'   [SAVE] Savings: {gas_price.cost_savings_percent}%')
                        safe_write(self.stdout, f'   [NET] Conf. Time: {gas_price.expected_confirmation_time_ms}ms')
                        
                        if result.fallback_used:
                            safe_write(self.stdout, '[WARN] Used fallback pricing', self.style.WARNING)
                    
                    # Show console output
                    if result.console_output:
                        lines = result.console_output.split('\n')
                        for line in lines:
                            if line.strip():
                                safe_write(self.stdout, f'   [OUT] {line}')
                else:
                    failed_tests += 1
                    safe_write(self.stdout, f'[ERROR] Optimization failed: {result.error_message}', self.style.ERROR)
                
            except Exception as e:
                failed_tests += 1
                safe_write(self.stdout, f'[ERROR] Test failed: {e}', self.style.ERROR)
            
            await asyncio.sleep(0.5)  # Brief pause between tests
        
        # Show final statistics
        safe_write(self.stdout, '\n' + '=' * 60)
        safe_write(self.stdout, '[STATS] TEST RESULTS SUMMARY', self.style.HTTP_INFO)
        safe_write(self.stdout, '=' * 60)
        
        safe_write(self.stdout, f'[OK] Successful Tests: {successful_tests}')
        safe_write(self.stdout, f'[ERROR] Failed Tests: {failed_tests}')
        safe_write(self.stdout, f'[DATA] Success Rate: {(successful_tests / len(test_scenarios)) * 100:.1f}%')
        
        # Show performance stats
        stats = optimizer.get_performance_stats()
        safe_write(self.stdout, f'[COST] Total Savings: ${stats["cost_savings_total_usd"]:.2f}')
        safe_write(self.stdout, f'[ALERT] Emergency Stops: {stats["emergency_stops_triggered"]}')
        
        # Show recent console output
        console_output = optimizer.get_console_output(last_n=10)
        if console_output:
            safe_write(self.stdout, '\n[OUT] Recent Console Output:')
            for line in console_output[-5:]:  # Show last 5 lines
                safe_write(self.stdout, f'   {line}')
    
    async def run_quick_test(self, specific_chain=None, paper_only=False):
        """Run quick gas optimizer test."""
        safe_write(self.stdout, '[QUICK] QUICK GAS OPTIMIZER TEST', self.style.HTTP_INFO)
        safe_write(self.stdout, '=' * 50)
        
        from trading.services.gas_optimizer import optimize_trade_gas
        
        # Single test scenario
        chain_id = specific_chain if specific_chain else 1
        
        safe_write(self.stdout, f'[TEST] Testing gas optimization on chain {chain_id}...')
        
        result = await optimize_trade_gas(
            chain_id=chain_id,
            trade_type='buy',
            amount_usd=Decimal('1000'),
            strategy='balanced',
            is_paper_trade=paper_only
        )
        
        if result.success:
            safe_write(self.stdout, '[OK] Quick test passed', self.style.SUCCESS)
            if result.gas_price:
                safe_write(self.stdout, f'[COST] Gas price: {result.gas_price.max_fee_per_gas_gwei} gwei')
                safe_write(self.stdout, f'[COST] Est. cost: ${result.gas_price.estimated_cost_usd}')
        else:
            safe_write(self.stdout, f'[ERROR] Quick test failed: {result.error_message}', self.style.ERROR)
    
    async def run_monitoring_test(self, duration_seconds):
        """Run continuous monitoring test."""
        safe_write(self.stdout, f'[DATA] CONTINUOUS MONITORING TEST ({duration_seconds}s)', self.style.HTTP_INFO)
        safe_write(self.stdout, '=' * 60)
        
        from trading.services.gas_optimizer import get_gas_optimizer, optimize_trade_gas
        
        optimizer = await get_gas_optimizer()
        
        if not optimizer:
            raise CommandError('Failed to initialize gas optimizer')
        
        safe_write(self.stdout, '[UPDATE] Starting continuous monitoring...')
        safe_write(self.stdout, '[NET] Watch for live gas price updates in the output below:')
        safe_write(self.stdout, '')
        
        start_time = time.time()
        iteration = 0
        
        while (time.time() - start_time) < duration_seconds:
            iteration += 1
            
            # Simulate trades on different chains
            chain_id = 1 if iteration % 2 == 0 else 8453
            amount = Decimal(str(100 + (iteration * 100)))
            
            safe_write(self.stdout, f'[GAS] Iteration {iteration}: Optimizing {amount} USD trade on chain {chain_id}')
            
            result = await optimize_trade_gas(
                chain_id=chain_id,
                trade_type='buy',
                amount_usd=amount,
                strategy='balanced',
                is_paper_trade=True
            )
            
            if result.success and result.gas_price:
                safe_write(self.stdout, f'   [STATS] Result: {result.gas_price.max_fee_per_gas_gwei} gwei, ${result.gas_price.estimated_cost_usd} cost')
            
            await asyncio.sleep(3)  # Update every 3 seconds
        
        safe_write(self.stdout, '\n[OK] Monitoring test completed', self.style.SUCCESS)
        
        # Show final stats
        stats = optimizer.get_performance_stats()
        safe_write(self.stdout, f'[DATA] Total optimizations during test: {iteration}')
        safe_write(self.stdout, f'[COST] Total savings tracked: ${stats["cost_savings_total_usd"]:.2f}')
    
    async def run_emergency_test(self):
        """Test emergency stop functionality."""
        safe_write(self.stdout, '[ALERT] EMERGENCY STOP TEST', self.style.HTTP_INFO)
        safe_write(self.stdout, '=' * 40)
        
        from trading.services.gas_optimizer import get_gas_optimizer
        
        optimizer = await get_gas_optimizer()
        
        if not optimizer:
            raise CommandError('Failed to initialize gas optimizer')
        
        safe_write(self.stdout, '[ALERT] Testing emergency stop functionality...')
        
        # Trigger emergency stop
        await optimizer.emergency_stop_all_chains("Management command test")
        
        safe_write(self.stdout, '[WARN] Emergency stop activated', self.style.WARNING)
        
        # Show stats
        stats = optimizer.get_performance_stats()
        safe_write(self.stdout, f'[ALERT] Emergency stops triggered: {stats["emergency_stops_triggered"]}')
        
        # Show recent console output
        console_output = optimizer.get_console_output(last_n=5)
        if console_output:
            safe_write(self.stdout, '\n[OUT] Emergency stop console output:')
            for line in console_output:
                safe_write(self.stdout, f'   {line}')
        
        safe_write(self.stdout, '[OK] Emergency stop test completed', self.style.SUCCESS)