"""
Management Command: Test Transaction Manager Pipeline - Phase 6B

Complete end-to-end testing of the transaction execution pipeline including:
- Transaction Manager initialization
- Gas optimization integration
- DEX router execution
- Portfolio tracking updates
- WebSocket status broadcasting

Usage:
    python manage.py test_transaction_manager --chain-id 1 --paper-mode
    python manage.py test_transaction_manager --chain-id 8453 --test-live
    python manage.py test_transaction_manager --full-pipeline

File: dexproject/trading/management/commands/test_transaction_manager.py
"""

import asyncio
import logging
import time
from decimal import Decimal
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings
from eth_utils import to_checksum_address

# Import transaction manager and related services
from trading.services.transaction_manager import (
    TransactionManager,
    TransactionSubmissionRequest,
    TransactionStatus,
    get_transaction_manager,
    create_transaction_submission_request
)
from trading.services.dex_router_service import (
    SwapType, DEXVersion, TradingGasStrategy
)
from trading.services.gas_optimizer import get_gas_optimizer

# Import engine components
from engine.config import config
from engine.web3_client import Web3Client
from engine.wallet_manager import WalletManager

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Test command for Transaction Manager pipeline validation."""
    
    help = 'Test the complete transaction manager pipeline with gas optimization'
    
    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            '--chain-id',
            type=int,
            default=1,
            help='Chain ID to test (1=Ethereum, 8453=Base)'
        )
        parser.add_argument(
            '--paper-mode',
            action='store_true',
            help='Run in paper trading mode (no real transactions)'
        )
        parser.add_argument(
            '--test-live',
            action='store_true',
            help='Test with live transaction (requires funds)'
        )
        parser.add_argument(
            '--full-pipeline',
            action='store_true',
            help='Run complete pipeline test with all features'
        )
        parser.add_argument(
            '--amount-usd',
            type=float,
            default=100.0,
            help='Trade amount in USD for testing'
        )
    
    def handle(self, *args, **options):
        """Execute the test command."""
        self.chain_id = options['chain_id']
        self.paper_mode = options['paper_mode']
        self.test_live = options['test_live']
        self.full_pipeline = options['full_pipeline']
        self.amount_usd = Decimal(str(options['amount_usd']))
        
        self.stdout.write(self.style.SUCCESS(
            f"\n{'=' * 80}\n"
            f"🚀 TRANSACTION MANAGER PIPELINE TEST - PHASE 6B\n"
            f"{'=' * 80}\n"
        ))
        
        # Run async test
        try:
            asyncio.run(self.run_tests())
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\n\n⚠️  Test interrupted by user"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ Test failed: {e}"))
            logger.error("Test error details:", exc_info=True)
    
    async def run_tests(self):
        """Run the transaction manager tests."""
        self.stdout.write(f"\n📋 Test Configuration:")
        self.stdout.write(f"  • Chain ID: {self.chain_id}")
        self.stdout.write(f"  • Paper Mode: {self.paper_mode}")
        self.stdout.write(f"  • Live Test: {self.test_live}")
        self.stdout.write(f"  • Full Pipeline: {self.full_pipeline}")
        self.stdout.write(f"  • Amount USD: ${self.amount_usd}")
        
        # Initialize transaction manager
        self.stdout.write(f"\n🔧 Initializing Transaction Manager...")
        tx_manager = await get_transaction_manager(self.chain_id)
        
        if not tx_manager:
            self.stdout.write(self.style.ERROR("Failed to initialize Transaction Manager"))
            return
        
        self.stdout.write(self.style.SUCCESS("✅ Transaction Manager initialized"))
        
        # Run test scenarios
        if self.full_pipeline:
            await self.test_full_pipeline(tx_manager)
        elif self.test_live:
            await self.test_live_transaction(tx_manager)
        else:
            await self.test_paper_trading(tx_manager)
        
        # Display performance metrics
        await self.display_metrics(tx_manager)
    
    async def test_paper_trading(self, tx_manager: TransactionManager):
        """Test paper trading mode."""
        self.stdout.write(f"\n📝 PAPER TRADING TEST")
        self.stdout.write(f"{'=' * 60}")
        
        # Get or create test user
        test_user, created = User.objects.get_or_create(
            username='test_trader',
            defaults={'email': 'test@example.com'}
        )
        
        # Create test swap request
        swap_request = await self.create_test_swap_request(
            test_user,
            is_paper_trade=True
        )
        
        self.stdout.write(f"\n🔄 Submitting paper trade...")
        self.stdout.write(f"  • Token In: WETH")
        self.stdout.write(f"  • Token Out: USDC")
        self.stdout.write(f"  • Amount: ${self.amount_usd}")
        self.stdout.write(f"  • Strategy: BALANCED")
        
        # Submit transaction
        result = await tx_manager.submit_transaction(swap_request)
        
        if result.success:
            self.stdout.write(self.style.SUCCESS(
                f"\n✅ Paper trade submitted successfully!"
            ))
            self.stdout.write(f"  • Transaction ID: {result.transaction_id}")
            
            # Monitor transaction status
            await self.monitor_transaction(tx_manager, result.transaction_id)
            
            # Display transaction state
            if result.transaction_state:
                await self.display_transaction_state(result.transaction_state)
        else:
            self.stdout.write(self.style.ERROR(
                f"\n❌ Paper trade failed: {result.error_message}"
            ))
    
    async def test_live_transaction(self, tx_manager: TransactionManager):
        """Test live transaction (requires funds)."""
        self.stdout.write(f"\n💰 LIVE TRANSACTION TEST")
        self.stdout.write(f"{'=' * 60}")
        
        if not self.confirm_live_test():
            self.stdout.write(self.style.WARNING("Live test cancelled by user"))
            return
        
        # Get or create test user
        test_user, created = User.objects.get_or_create(
            username='live_trader',
            defaults={'email': 'live@example.com'}
        )
        
        # Create live swap request with small amount
        swap_request = await self.create_test_swap_request(
            test_user,
            is_paper_trade=False,
            amount_override=Decimal('10')  # Use small amount for live test
        )
        
        self.stdout.write(f"\n🔄 Submitting live trade...")
        self.stdout.write(f"  • Amount: $10 (test amount)")
        self.stdout.write(f"  • Gas Strategy: COST_EFFICIENT")
        
        # Submit transaction
        result = await tx_manager.submit_transaction(swap_request)
        
        if result.success:
            self.stdout.write(self.style.SUCCESS(
                f"\n✅ Live trade submitted!"
            ))
            self.stdout.write(f"  • Transaction ID: {result.transaction_id}")
            
            # Monitor for confirmation
            await self.monitor_transaction(tx_manager, result.transaction_id, timeout=120)
            
            # Show gas savings
            if result.gas_savings_achieved:
                self.stdout.write(self.style.SUCCESS(
                    f"  • Gas Savings: {result.gas_savings_achieved:.2f}%"
                ))
        else:
            self.stdout.write(self.style.ERROR(
                f"\n❌ Live trade failed: {result.error_message}"
            ))
    
    async def test_full_pipeline(self, tx_manager: TransactionManager):
        """Test complete pipeline with all features."""
        self.stdout.write(f"\n🔬 FULL PIPELINE TEST")
        self.stdout.write(f"{'=' * 60}")
        
        # Test 1: Gas Optimization
        await self.test_gas_optimization()
        
        # Test 2: Transaction Submission
        await self.test_transaction_submission(tx_manager)
        
        # Test 3: Status Monitoring
        await self.test_status_monitoring(tx_manager)
        
        # Test 4: Portfolio Integration
        await self.test_portfolio_integration(tx_manager)
        
        # Test 5: WebSocket Updates
        await self.test_websocket_updates(tx_manager)
        
        # Test 6: Error Handling
        await self.test_error_handling(tx_manager)
        
        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Full pipeline test completed!"
        ))
    
    async def test_gas_optimization(self):
        """Test gas optimization integration."""
        self.stdout.write(f"\n⛽ Testing Gas Optimization...")
        
        gas_optimizer = await get_gas_optimizer()
        
        # Test different strategies
        strategies = [
            TradingGasStrategy.COST_EFFICIENT,
            TradingGasStrategy.BALANCED,
            TradingGasStrategy.SPEED_PRIORITY
        ]
        
        for strategy in strategies:
            result = await gas_optimizer.optimize_gas_for_trade(
                chain_id=self.chain_id,
                trade_type='buy',
                amount_usd=self.amount_usd,
                strategy=strategy,
                is_paper_trade=True
            )
            
            if result.success:
                self.stdout.write(
                    f"  ✓ {strategy.value}: "
                    f"{result.gas_price.gas_price_gwei:.2f} gwei "
                    f"(Savings: {result.gas_price.cost_savings_percent:.1f}%)"
                )
            else:
                self.stdout.write(
                    f"  ✗ {strategy.value}: Failed"
                )
    
    async def test_transaction_submission(self, tx_manager: TransactionManager):
        """Test transaction submission flow."""
        self.stdout.write(f"\n📤 Testing Transaction Submission...")
        
        # Create test user
        test_user, _ = User.objects.get_or_create(
            username='pipeline_tester',
            defaults={'email': 'pipeline@test.com'}
        )
        
        # Test different swap types
        swap_types = [
            (SwapType.EXACT_ETH_FOR_TOKENS, "ETH → Token"),
            (SwapType.EXACT_TOKENS_FOR_ETH, "Token → ETH"),
        ]
        
        for swap_type, description in swap_types:
            request = await self.create_test_swap_request(
                test_user,
                is_paper_trade=True,
                swap_type=swap_type
            )
            
            result = await tx_manager.submit_transaction(request)
            
            status = "✓" if result.success else "✗"
            self.stdout.write(f"  {status} {description}: {result.transaction_id[:8]}...")
    
    async def test_status_monitoring(self, tx_manager: TransactionManager):
        """Test transaction status monitoring."""
        self.stdout.write(f"\n👁️ Testing Status Monitoring...")
        
        # Check active transactions
        active_count = len(tx_manager._active_transactions)
        self.stdout.write(f"  • Active Transactions: {active_count}")
        
        # Display recent transaction statuses
        for tx_id, tx_state in list(tx_manager._active_transactions.items())[:3]:
            self.stdout.write(
                f"  • {tx_id[:8]}...: {tx_state.status.value}"
            )
    
    async def test_portfolio_integration(self, tx_manager: TransactionManager):
        """Test portfolio service integration."""
        self.stdout.write(f"\n📊 Testing Portfolio Integration...")
        
        if tx_manager._portfolio_service:
            self.stdout.write(self.style.SUCCESS("  ✓ Portfolio service connected"))
            
            # Get performance stats
            stats = tx_manager.get_performance_metrics()
            self.stdout.write(f"  • Success Rate: {stats['success_rate_percent']:.1f}%")
            self.stdout.write(f"  • Avg Gas Savings: {stats['average_gas_savings_percent']:.1f}%")
        else:
            self.stdout.write(self.style.WARNING("  ⚠ Portfolio service not initialized"))
    
    async def test_websocket_updates(self, tx_manager: TransactionManager):
        """Test WebSocket update broadcasting."""
        self.stdout.write(f"\n📡 Testing WebSocket Updates...")
        
        if tx_manager.channel_layer:
            self.stdout.write(self.style.SUCCESS("  ✓ WebSocket layer available"))
            self.stdout.write(f"  • Updates Enabled: {tx_manager.enable_websocket_updates}")
        else:
            self.stdout.write(self.style.WARNING("  ⚠ WebSocket layer not available"))
    
    async def test_error_handling(self, tx_manager: TransactionManager):
        """Test error handling scenarios."""
        self.stdout.write(f"\n🛡️ Testing Error Handling...")
        
        # Test with invalid parameters
        test_user, _ = User.objects.get_or_create(username='error_tester')
        
        # Create request with invalid token address
        invalid_request = TransactionSubmissionRequest(
            user=test_user,
            chain_id=self.chain_id,
            swap_params=None,  # Invalid params
            gas_strategy=TradingGasStrategy.BALANCED,
            is_paper_trade=True
        )
        
        try:
            result = await tx_manager.submit_transaction(invalid_request)
            if not result.success:
                self.stdout.write(self.style.SUCCESS("  ✓ Error handling works correctly"))
        except Exception as e:
            self.stdout.write(self.style.SUCCESS(f"  ✓ Exception caught: {type(e).__name__}")
    
    async def create_test_swap_request(
        self,
        user: User,
        is_paper_trade: bool = True,
        swap_type: SwapType = SwapType.EXACT_ETH_FOR_TOKENS,
        amount_override: Optional[Decimal] = None
    ) -> TransactionSubmissionRequest:
        """Create a test swap request."""
        
        # Use test tokens based on chain
        if self.chain_id == 1:  # Ethereum
            weth_address = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
            usdc_address = "0xA0b86991c5F71bc32B37d8E327695AD80C4579A1"
        else:  # Base or other chains
            weth_address = "0x4200000000000000000000000000000000000006"
            usdc_address = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
        
        amount_usd = amount_override or self.amount_usd
        amount_wei = int(amount_usd * 10**18 / 2000)  # Assuming ETH = $2000
        
        # Determine gas strategy
        if is_paper_trade:
            gas_strategy = TradingGasStrategy.PAPER_TRADING
        elif amount_usd < 50:
            gas_strategy = TradingGasStrategy.COST_EFFICIENT
        else:
            gas_strategy = TradingGasStrategy.BALANCED
        
        # Create request using helper function
        request = await create_transaction_submission_request(
            user=user,
            chain_id=self.chain_id,
            token_in=weth_address if swap_type == SwapType.EXACT_ETH_FOR_TOKENS else usdc_address,
            token_out=usdc_address if swap_type == SwapType.EXACT_ETH_FOR_TOKENS else weth_address,
            amount_in=amount_wei,
            amount_out_minimum=int(amount_wei * 0.95),  # 5% slippage
            swap_type=swap_type,
            dex_version=DEXVersion.UNISWAP_V3,
            gas_strategy=gas_strategy,
            is_paper_trade=is_paper_trade
        )
        
        return request
    
    async def monitor_transaction(
        self,
        tx_manager: TransactionManager,
        transaction_id: str,
        timeout: int = 30
    ):
        """Monitor transaction status until completion."""
        self.stdout.write(f"\n⏳ Monitoring transaction status...")
        
        start_time = time.time()
        last_status = None
        
        while time.time() - start_time < timeout:
            tx_state = await tx_manager.get_transaction_status(transaction_id)
            
            if tx_state and tx_state.status != last_status:
                self.stdout.write(
                    f"  • Status: {tx_state.status.value}"
                )
                last_status = tx_state.status
                
                if tx_state.status in [
                    TransactionStatus.COMPLETED,
                    TransactionStatus.FAILED,
                    TransactionStatus.CANCELLED
                ]:
                    break
            
            await asyncio.sleep(2)
        
        if last_status == TransactionStatus.COMPLETED:
            self.stdout.write(self.style.SUCCESS("✅ Transaction completed!"))
        elif last_status == TransactionStatus.FAILED:
            self.stdout.write(self.style.ERROR("❌ Transaction failed"))
        else:
            self.stdout.write(self.style.WARNING("⏱️ Monitoring timeout"))
    
    async def display_transaction_state(self, tx_state):
        """Display detailed transaction state."""
        self.stdout.write(f"\n📋 Transaction Details:")
        self.stdout.write(f"  • ID: {tx_state.transaction_id}")
        self.stdout.write(f"  • Status: {tx_state.status.value}")
        self.stdout.write(f"  • Chain: {tx_state.chain_id}")
        
        if tx_state.transaction_hash:
            self.stdout.write(f"  • Hash: {tx_state.transaction_hash}")
        
        if tx_state.gas_optimization_result:
            self.stdout.write(f"  • Gas Optimized: Yes")
            if tx_state.gas_savings_percent:
                self.stdout.write(f"  • Gas Savings: {tx_state.gas_savings_percent:.2f}%")
        
        if tx_state.execution_time_ms:
            self.stdout.write(f"  • Execution Time: {tx_state.execution_time_ms:.0f}ms")
    
    async def display_metrics(self, tx_manager: TransactionManager):
        """Display transaction manager metrics."""
        self.stdout.write(f"\n📈 Performance Metrics")
        self.stdout.write(f"{'=' * 60}")
        
        metrics = tx_manager.get_performance_metrics()
        
        self.stdout.write(f"  • Chain: {metrics['chain_name']} (ID: {metrics['chain_id']})")
        self.stdout.write(f"  • Total Transactions: {metrics['total_transactions']}")
        self.stdout.write(f"  • Successful: {metrics['successful_transactions']}")
        self.stdout.write(f"  • Success Rate: {metrics['success_rate_percent']:.1f}%")
        self.stdout.write(f"  • Average Gas Savings: {metrics['average_gas_savings_percent']:.2f}%")
        self.stdout.write(f"  • Total Gas Savings: {metrics['total_gas_savings_percent']:.2f}%")
        self.stdout.write(f"  • Active Transactions: {metrics['active_transactions']}")
        self.stdout.write(f"  • Avg Execution Time: {metrics['average_execution_time_ms']:.2f}ms")
        
        # Cleanup old transactions
        cleaned = await tx_manager.cleanup_completed_transactions(max_age_hours=1)
        if cleaned > 0:
            self.stdout.write(f"  • Cleaned Up: {cleaned} old transactions")
    
    def confirm_live_test(self) -> bool:
        """Confirm user wants to run live test."""
        self.stdout.write(self.style.WARNING(
            "\n⚠️  WARNING: Live test will execute a real transaction!"
        ))
        self.stdout.write("This requires:")
        self.stdout.write("  • Wallet with funds")
        self.stdout.write("  • Network gas fees")
        self.stdout.write("  • Token approvals")
        
        response = input("\nDo you want to continue? (yes/no): ")
        return response.lower() in ['yes', 'y']