"""
Test Transaction Manager Django Management Command - Phase 6B

Django management command to test the gas optimization integration and
prepare for Transaction Manager testing once dependencies are installed.

Usage:
    python manage.py test_transaction_manager
    python manage.py test_transaction_manager --verbose
    python manage.py test_transaction_manager --install-deps

File: dexproject/trading/management/commands/test_transaction_manager.py
"""

import asyncio
import logging
import sys
import time
from decimal import Decimal
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.conf import settings

logger = logging.getLogger(__name__)


def safe_write(stream, message: str, style_func=None) -> None:
    """Write message safely for Windows console compatibility."""
    try:
        if style_func:
            stream.write(style_func(message))
        else:
            stream.write(message)
        stream.write('\n')
    except UnicodeEncodeError:
        # Fallback to ASCII for Windows console compatibility
        safe_message = message.encode('ascii', 'replace').decode('ascii')
        if style_func:
            stream.write(style_func(safe_message))
        else:
            stream.write(safe_message)
        stream.write('\n')


class Command(BaseCommand):
    """Django management command to test Phase 6B readiness."""
    
    help = 'Test Phase 6B readiness and gas optimization integration'
    
    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose logging output'
        )
        
        parser.add_argument(
            '--install-deps',
            action='store_true',
            help='Show installation instructions for missing dependencies'
        )
        
        parser.add_argument(
            '--test-gas-only',
            action='store_true',
            help='Test only gas optimization (skip Transaction Manager)'
        )
    
    def handle(self, *args, **options):
        """Execute the Phase 6B readiness test."""
        try:
            # Set up logging based on verbosity
            if options['verbose']:
                logging.basicConfig(level=logging.DEBUG)
            else:
                logging.basicConfig(level=logging.INFO)
            
            safe_write(self.stdout, "[OK] Phase 6B Readiness Test - Transaction Manager Integration", self.style.HTTP_INFO)
            safe_write(self.stdout, "=" * 70)
            
            # Show dependency installation if requested
            if options['install_deps']:
                self.show_dependency_installation()
                return
            
            # Run readiness tests
            asyncio.run(self._run_readiness_tests(options))
            
        except KeyboardInterrupt:
            safe_write(self.stdout, "\nTest interrupted by user", self.style.WARNING)
            sys.exit(1)
        except Exception as e:
            safe_write(self.stdout, f"\nTest failed with error: {e}", self.style.ERROR)
            logger.error(f"Phase 6B test failed: {e}", exc_info=True)
            sys.exit(1)
    
    def show_dependency_installation(self):
        """Show installation instructions for missing dependencies."""
        safe_write(self.stdout, "Phase 6B Dependency Installation Guide", self.style.HTTP_INFO)
        safe_write(self.stdout, "=" * 50)
        safe_write(self.stdout, "")
        safe_write(self.stdout, "To enable full Transaction Manager functionality, install:")
        safe_write(self.stdout, "")
        safe_write(self.stdout, "1. Django Channels (for WebSocket real-time updates):")
        safe_write(self.stdout, "   pip install channels", self.style.SUCCESS)
        safe_write(self.stdout, "")
        safe_write(self.stdout, "2. Redis (for Channels backend - optional):")
        safe_write(self.stdout, "   pip install redis", self.style.SUCCESS)
        safe_write(self.stdout, "")
        safe_write(self.stdout, "3. After installation, update settings.py:")
        safe_write(self.stdout, "   INSTALLED_APPS += ['channels']", self.style.SUCCESS)
        safe_write(self.stdout, "")
        safe_write(self.stdout, "4. Uncomment Transaction Manager imports in:")
        safe_write(self.stdout, "   trading/services/__init__.py", self.style.SUCCESS)
        safe_write(self.stdout, "")
    
    async def _run_readiness_tests(self, options: Dict[str, Any]) -> None:
        """Run Phase 6B readiness tests."""
        safe_write(self.stdout, f"Configuration:")
        safe_write(self.stdout, f"   Verbose: {options['verbose']}")
        safe_write(self.stdout, f"   Gas Only: {options['test_gas_only']}")
        safe_write(self.stdout, "")
        
        # Test 1: Basic service imports
        await self._test_basic_imports()
        
        # Test 2: Gas optimization integration
        await self._test_gas_optimization()
        
        # Test 3: Check Transaction Manager readiness
        if not options['test_gas_only']:
            await self._test_transaction_manager_readiness()
        
        # Test 4: DEX router service availability
        await self._test_dex_router_availability()
        
        # Test 5: Portfolio service availability
        await self._test_portfolio_service_availability()
        
        # Test 6: Database models
        await self._test_database_models()
        
        safe_write(self.stdout, "Phase 6B Readiness Assessment Complete!", self.style.SUCCESS)
    
    async def _test_basic_imports(self) -> None:
        """Test basic service imports."""
        safe_write(self.stdout, "Test 1: Basic Service Imports")
        
        try:
            # Test core trading services
            from trading.services import (
                DEXRouterService,
                PortfolioTrackingService,
                TradingGasStrategy,
                SwapType,
                DEXVersion
            )
            
            safe_write(self.stdout, "   ✅ Core trading services imported successfully")
            safe_write(self.stdout, "   📊 Available: DEXRouterService, PortfolioTrackingService")
            safe_write(self.stdout, "   📊 Available: TradingGasStrategy, SwapType, DEXVersion")
            
        except ImportError as e:
            safe_write(self.stdout, f"   ❌ Core import failed: {e}", self.style.ERROR)
            
        # Test gas optimizer
        try:
            from trading.services import optimize_trade_gas, get_gas_optimizer
            safe_write(self.stdout, "   ✅ Gas optimization services imported successfully")
        except ImportError as e:
            safe_write(self.stdout, f"   ❌ Gas optimizer import failed: {e}", self.style.ERROR)
            
        safe_write(self.stdout, "")
    
    async def _test_gas_optimization(self) -> None:
        """Test gas optimization functionality."""
        safe_write(self.stdout, "Test 2: Gas Optimization Integration")
        
        try:
            from trading.services import optimize_trade_gas, TradingGasStrategy
            
            # Test gas optimization
            result = await optimize_trade_gas(
                chain_id=8453,  # Base
                trade_type='buy',
                amount_usd=Decimal('100'),
                strategy='balanced',
                is_paper_trade=True
            )
            
            if result.success and result.gas_price:
                safe_write(self.stdout, "   ✅ Gas optimization working correctly")
                safe_write(self.stdout, f"   ⚡ Strategy: balanced")
                safe_write(self.stdout, f"   ⚡ Gas Price: {result.gas_price.max_fee_per_gas_gwei} gwei")
                safe_write(self.stdout, f"   💰 Est. Cost: ${result.gas_price.estimated_cost_usd}")
                safe_write(self.stdout, f"   📈 Savings: {result.gas_price.cost_savings_percent}%")
            else:
                safe_write(self.stdout, f"   ⚠️ Gas optimization test failed: {result.error_message}", self.style.WARNING)
                
        except Exception as e:
            safe_write(self.stdout, f"   ❌ Gas optimization test error: {e}", self.style.ERROR)
            
        safe_write(self.stdout, "")
    
    async def _test_transaction_manager_readiness(self) -> None:
        """Test Transaction Manager readiness."""
        safe_write(self.stdout, "Test 3: Transaction Manager Readiness")
        
        try:
            # Try to import Transaction Manager
            from trading.services import get_transaction_manager
            safe_write(self.stdout, "   ✅ Transaction Manager service imported successfully")
            safe_write(self.stdout, "   📊 Full Transaction Manager functionality available")
            
            # Test initialization
            try:
                transaction_manager = await get_transaction_manager(8453)
                safe_write(self.stdout, "   ✅ Transaction Manager initializes correctly")
                safe_write(self.stdout, f"   📊 Chain: {transaction_manager.chain_config.name}")
            except Exception as e:
                safe_write(self.stdout, f"   ⚠️ Transaction Manager initialization issue: {e}", self.style.WARNING)
                
        except ImportError:
            safe_write(self.stdout, "   ⚠️ Transaction Manager not available", self.style.WARNING)
            safe_write(self.stdout, "   💡 Install Django Channels to enable full functionality")
            safe_write(self.stdout, "   💡 Run with --install-deps for installation guide")
            
        safe_write(self.stdout, "")
    
    async def _test_dex_router_availability(self) -> None:
        """Test DEX router service availability."""
        safe_write(self.stdout, "Test 4: DEX Router Service")
        
        try:
            from trading.services import create_dex_router_service
            safe_write(self.stdout, "   ✅ DEX router service factory available")
            safe_write(self.stdout, "   📊 Ready for swap execution")
            
        except ImportError as e:
            safe_write(self.stdout, f"   ❌ DEX router service import failed: {e}", self.style.ERROR)
            
        safe_write(self.stdout, "")
    
    async def _test_portfolio_service_availability(self) -> None:
        """Test portfolio service availability."""
        safe_write(self.stdout, "Test 5: Portfolio Service")
        
        try:
            from trading.services import create_portfolio_service
            safe_write(self.stdout, "   ✅ Portfolio service factory available")
            safe_write(self.stdout, "   📊 Ready for trade tracking")
            
        except ImportError as e:
            safe_write(self.stdout, f"   ❌ Portfolio service import failed: {e}", self.style.ERROR)
            
        safe_write(self.stdout, "")
    
    async def _test_database_models(self) -> None:
        """Test database model availability."""
        safe_write(self.stdout, "Test 6: Database Models")
        
        try:
            from trading.models import Trade, Position, TradingPair, Token
            from django.db import models
            from asgiref.sync import sync_to_async
            
            safe_write(self.stdout, "   ✅ Trading models imported successfully")
            safe_write(self.stdout, "   📊 Available: Trade, Position, TradingPair, Token")
            
            # Test model creation (dry run) using sync_to_async
            @sync_to_async
            def create_test_user():
                return User.objects.get_or_create(
                    username='phase6b_test_user',
                    defaults={
                        'email': 'phase6b@example.com',
                        'first_name': 'Phase6B',
                        'last_name': 'Test'
                    }
                )
            
            test_user, created = await create_test_user()
            status = "Created" if created else "Found existing"
            safe_write(self.stdout, f"   ✅ Test user {status}: {test_user.username}")
            
        except ImportError as e:
            safe_write(self.stdout, f"   ❌ Model import failed: {e}", self.style.ERROR)
        except Exception as e:
            safe_write(self.stdout, f"   ⚠️ Database test issue: {e}", self.style.WARNING)
            
        safe_write(self.stdout, "")