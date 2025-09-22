"""
Integrated Trading Example - Phase 6A

Demonstrates how the new gas optimizer integrates with existing 
DEX router and portfolio services for complete trading execution.

This shows the full trading pipeline:
Gas Optimization → DEX Execution → Portfolio Tracking

File: examples/integrated_trading_example.py
"""

import asyncio
import logging
from decimal import Decimal
from datetime import datetime
from typing import Dict, Any, Optional

from django.contrib.auth.models import User
from eth_utils import to_checksum_address

# Import existing services
from trading.services.dex_router_service import (
    create_dex_router_service,
    SwapParams,
    SwapType,
    DEXVersion
)
from trading.services.portfolio_service import (
    create_portfolio_service,
    PortfolioUpdate
)

# Import new gas optimizer - Phase 6A
from trading.services.gas_optimizer import (
    optimize_trade_gas,
    TradingGasStrategy,
    GasOptimizationResult
)

# Import engine components
from engine.config import config
from engine.web3_client import Web3Client
from engine.wallet_manager import WalletManager

logger = logging.getLogger(__name__)


class IntegratedTradingService:
    """
    Complete trading service that integrates gas optimization, DEX routing, and portfolio tracking.
    
    This demonstrates the full Phase 6 vision: from gas optimization to trade execution
    to portfolio updates, with real-time console output showing each step.
    """
    
    def __init__(self, chain_id: int):
        """Initialize the integrated trading service."""
        self.chain_id = chain_id
        self.chain_config = config.get_chain_config(chain_id)
        self.logger = logging.getLogger(f'integrated_trading.chain_{chain_id}')
        
        # Service instances
        self.web3_client: Optional[Web3Client] = None
        self.wallet_manager: Optional[WalletManager] = None
        self.dex_router_service = None
        self.portfolio_service = None
        
        self.logger.info(f"🔧 Integrated trading service initialized for chain {chain_id}")
    
    async def initialize(self) -> bool:
        """Initialize all trading components."""
        try:
            print(f"🚀 Initializing integrated trading service for chain {self.chain_id}")
            
            # Initialize Web3 client
            print("🌐 Connecting to blockchain...")
            self.web3_client = Web3Client(self.chain_config)
            await self.web3_client.connect()
            
            if not self.web3_client.is_connected:
                print("❌ Failed to connect to blockchain")
                return False
            print("✅ Blockchain connection established")
            
            # Initialize wallet manager
            print("👛 Setting up wallet manager...")
            self.wallet_manager = WalletManager(self.chain_config)
            await self.wallet_manager.initialize(self.web3_client)
            print("✅ Wallet manager ready")
            
            # Initialize DEX router service
            print("🔄 Setting up DEX router...")
            self.dex_router_service = await create_dex_router_service(
                self.web3_client, self.wallet_manager
            )
            print("✅ DEX router service ready")
            
            # Initialize portfolio service
            print("📊 Setting up portfolio tracking...")
            self.portfolio_service = create_portfolio_service(self.chain_config)
            print("✅ Portfolio service ready")
            
            print("🎯 Integrated trading service fully initialized")
            return True
            
        except Exception as e:
            print(f"❌ Initialization failed: {e}")
            self.logger.error(f"Service initialization failed: {e}", exc_info=True)
            return False
    
    async def execute_optimized_trade(
        self,
        trade_type: str,  # 'buy' or 'sell'
        token_address: str,
        amount_usd: Decimal,
        user: Optional[User] = None,
        strategy: str = 'balanced',
        is_paper_trade: bool = False
    ) -> Dict[str, Any]:
        """
        Execute a complete optimized trade with full pipeline integration.
        
        Pipeline:
        1. Gas Optimization (Phase 6A)
        2. DEX Route Calculation
        3. Trade Execution
        4. Portfolio Update
        5. Real-time Status Updates
        """
        
        print("\n" + "=" * 80)
        print(f"🚀 EXECUTING OPTIMIZED {trade_type.upper()} TRADE")
        print("=" * 80)
        print(f"Token: {token_address}")
        print(f"Amount: ${amount_usd}")
        print(f"Strategy: {strategy}")
        print(f"Paper Trade: {'Yes' if is_paper_trade else 'No'}")
        print(f"Chain: {self.chain_id}")
        
        trade_start_time = datetime.now()
        
        try:
            # =====================================
            # STEP 1: GAS OPTIMIZATION (Phase 6A)
            # =====================================
            print(f"\n📈 Step 1: Optimizing gas pricing...")
            
            gas_result = await optimize_trade_gas(
                chain_id=self.chain_id,
                trade_type=trade_type,
                amount_usd=amount_usd,
                strategy=strategy,
                is_paper_trade=is_paper_trade
            )
            
            if not gas_result.success:
                print(f"❌ Gas optimization failed: {gas_result.error_message}")
                return {
                    'success': False,
                    'error': 'Gas optimization failed',
                    'details': gas_result.error_message
                }
            
            gas_price = gas_result.gas_price
            print(f"✅ Gas optimized: {gas_price.max_fee_per_gas_gwei} gwei")
            print(f"💰 Estimated cost: ${gas_price.estimated_cost_usd}")
            print(f"💸 Savings: {gas_price.cost_savings_percent}%")
            
            # Show gas optimization console output
            if gas_result.console_output:
                print("📺 Gas Optimization Details:")
                for line in gas_result.console_output.split('\n'):
                    if line.strip():
                        print(f"   {line}")
            
            # =================================
            # STEP 2: TRADE SETUP & VALIDATION
            # =================================
            print(f"\n🔍 Step 2: Setting up trade parameters...")
            
            # Get wallet address (in production, this would come from SIWE session)
            wallet_address = self.wallet_manager.get_default_address()
            if not wallet_address:
                print("❌ No wallet address available")
                return {'success': False, 'error': 'No wallet address'}
            
            print(f"👛 Wallet: {wallet_address[:10]}...")
            
            # Prepare swap parameters
            token_address = to_checksum_address(token_address)
            
            if trade_type == 'buy':
                # ETH → Token
                swap_type = SwapType.EXACT_ETH_FOR_TOKENS
                token_in = to_checksum_address(self.chain_config.weth_address)
                token_out = token_address
                amount_in_wei = int(amount_usd * Decimal('1e15'))  # Rough ETH conversion
            else:
                # Token → ETH
                swap_type = SwapType.EXACT_TOKENS_FOR_ETH
                token_in = token_address
                token_out = to_checksum_address(self.chain_config.weth_address)
                # For sell, we need to query user's token balance
                amount_in_wei = int(amount_usd * Decimal('1e18'))  # Placeholder
            
            # Calculate minimum amount out (5% slippage tolerance)
            slippage = Decimal('0.05')
            amount_out_min = int(amount_in_wei * (Decimal('1') - slippage))
            
            # Prepare swap parameters with optimized gas
            swap_params = SwapParams(
                token_in=token_in,
                token_out=token_out,
                amount_in=amount_in_wei,
                amount_out_minimum=amount_out_min,
                swap_type=swap_type,
                dex_version=DEXVersion.UNISWAP_V3,
                recipient=to_checksum_address(wallet_address),
                deadline=int(datetime.now().timestamp()) + 1200,  # 20 minutes
                slippage_tolerance=slippage,
                gas_price_gwei=gas_price.max_priority_fee_per_gas_gwei,  # Use optimized gas
                gas_limit=gas_price.estimated_gas_limit
            )
            
            print(f"✅ Trade parameters configured")
            print(f"   Swap Type: {swap_type.value}")
            print(f"   Amount In: {amount_in_wei} wei")
            print(f"   Min Amount Out: {amount_out_min} wei")
            print(f"   Gas Limit: {gas_price.estimated_gas_limit}")
            
            # =====================================
            # STEP 3: TRADE EXECUTION
            # =====================================
            print(f"\n⚡ Step 3: Executing trade...")
            
            if is_paper_trade:
                # Paper trade simulation
                print("📝 Paper trade mode - simulating execution...")
                
                # Simulate execution time
                await asyncio.sleep(0.5)
                
                # Create mock swap result
                from trading.services.dex_router_service import SwapResult
                
                swap_result = SwapResult(
                    transaction_hash="0x" + "1234567890abcdef" * 4,
                    block_number=None,
                    gas_used=gas_price.estimated_gas_limit,
                    gas_price_gwei=gas_price.max_fee_per_gas_gwei,
                    amount_in=amount_in_wei,
                    amount_out=amount_out_min,
                    actual_slippage_percent=Decimal('2.1'),
                    execution_time_ms=500.0,
                    dex_version=DEXVersion.UNISWAP_V3,
                    success=True
                )
                
                print("✅ Paper trade simulated successfully")
            else:
                # Real trade execution
                print("💰 Executing real trade on blockchain...")
                
                swap_result = await self.dex_router_service.execute_swap(
                    swap_params,
                    wallet_address
                )
                
                if not swap_result.success:
                    print(f"❌ Trade execution failed: {swap_result.error_message}")
                    return {
                        'success': False,
                        'error': 'Trade execution failed',
                        'details': swap_result.error_message
                    }
                
                print("✅ Trade executed on blockchain")
            
            print(f"🎯 Transaction: {swap_result.transaction_hash}")
            print(f"⛽ Gas Used: {swap_result.gas_used}")
            print(f"📊 Slippage: {swap_result.actual_slippage_percent}%")
            print(f"⚡ Execution Time: {swap_result.execution_time_ms:.1f}ms")
            
            # =====================================
            # STEP 4: PORTFOLIO UPDATE
            # =====================================
            print(f"\n📊 Step 4: Updating portfolio...")
            
            portfolio_update = await self.portfolio_service.record_swap_trade(
                swap_result=swap_result,
                swap_type=swap_type,
                token_in_address=str(token_in),
                token_out_address=str(token_out),
                pair_address="",  # Would get from DEX
                user=user,
                strategy=None,  # Would map from strategy string
                trade_id=None
            )
            
            if portfolio_update.trade_created:
                print("✅ Trade recorded in portfolio")
                print(f"   Trade ID: {portfolio_update.trade_id}")
                if portfolio_update.position_id:
                    print(f"   Position ID: {portfolio_update.position_id}")
                if portfolio_update.realized_pnl:
                    print(f"   Realized P&L: ${portfolio_update.realized_pnl}")
            else:
                print(f"⚠️  Portfolio update warning: {portfolio_update.error_message}")
            
            # =====================================
            # STEP 5: FINAL SUMMARY
            # =====================================
            total_time = (datetime.now() - trade_start_time).total_seconds() * 1000
            
            print(f"\n🎉 TRADE COMPLETED SUCCESSFULLY")
            print("=" * 50)
            print(f"📈 Trade Type: {trade_type.upper()}")
            print(f"💰 Amount: ${amount_usd}")
            print(f"⛽ Gas Cost: ${gas_price.estimated_cost_usd}")
            print(f"💸 Gas Savings: {gas_price.cost_savings_percent}%")
            print(f"📊 Slippage: {swap_result.actual_slippage_percent}%")
            print(f"⚡ Total Time: {total_time:.1f}ms")
            print(f"🔗 Transaction: {swap_result.transaction_hash}")
            
            return {
                'success': True,
                'transaction_hash': swap_result.transaction_hash,
                'gas_used': swap_result.gas_used,
                'gas_cost_usd': float(gas_price.estimated_cost_usd),
                'gas_savings_percent': float(gas_price.cost_savings_percent),
                'slippage_percent': float(swap_result.actual_slippage_percent),
                'execution_time_ms': total_time,
                'trade_id': portfolio_update.trade_id,
                'position_id': portfolio_update.position_id,
                'is_paper_trade': is_paper_trade
            }
            
        except Exception as e:
            print(f"❌ Trade execution error: {e}")
            self.logger.error(f"Integrated trade execution failed: {e}", exc_info=True)
            return {
                'success': False,
                'error': 'Trade execution error',
                'details': str(e)
            }


async def demo_integrated_trading():
    """Demonstrate the complete integrated trading pipeline."""
    print("🚀 INTEGRATED TRADING DEMO - Phase 6A")
    print("=" * 80)
    
    # Initialize trading service for Ethereum
    service = IntegratedTradingService(chain_id=1)
    
    if not await service.initialize():
        print("❌ Service initialization failed")
        return
    
    print("\n🎯 Testing different trading scenarios...")
    
    # Test scenarios
    test_scenarios = [
        {
            'name': 'Small Paper Buy Trade',
            'trade_type': 'buy',
            'token_address': '0xA0b86a33E6441c5C7BCDBf1e3d9f013eC5B90003',  # WBTC
            'amount_usd': Decimal('100'),
            'strategy': 'cost_efficient',
            'is_paper_trade': True
        },
        {
            'name': 'Medium Paper Sell Trade',
            'trade_type': 'sell',
            'token_address': '0xA0b86a33E6441c5C7BCDBf1e3d9f013eC5B90003',  # WBTC
            'amount_usd': Decimal('500'),
            'strategy': 'balanced',
            'is_paper_trade': True
        }
    ]
    
    for i, scenario in enumerate(test_scenarios, 1):
        print(f"\n🧪 Test {i}: {scenario['name']}")
        print("-" * 60)
        
        result = await service.execute_optimized_trade(
            trade_type=scenario['trade_type'],
            token_address=scenario['token_address'],
            amount_usd=scenario['amount_usd'],
            strategy=scenario['strategy'],
            is_paper_trade=scenario['is_paper_trade']
        )
        
        if result['success']:
            print(f"✅ Test {i} completed successfully")
        else:
            print(f"❌ Test {i} failed: {result.get('error', 'Unknown error')}")
        
        await asyncio.sleep(1)  # Brief pause between tests
    
    print("\n🎉 INTEGRATED TRADING DEMO COMPLETED")


if __name__ == '__main__':
    # Run the demo
    asyncio.run(demo_integrated_trading())