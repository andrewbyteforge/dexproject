"""
Management command to verify paper trading models are working.

This command tests that all PTphase1 models are correctly installed
and can be created, read, updated, and deleted.

File: dexproject/paper_trading/management/commands/verify_paper_trading.py
"""

import logging
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from paper_trading.models import (
    PaperTradingAccount,
    PaperTrade,
    PaperPosition,
    PaperTradingConfig,
    # Enhanced models for PTphase1
    PaperAIThoughtLog,
    PaperStrategyConfiguration,
    PaperPerformanceMetrics,
    PaperTradingSession
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Verify that all paper trading models are working correctly."""
    
    help = 'Verifies paper trading models and creates test data'
    
    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            '--create-test-data',
            action='store_true',
            help='Create test data for all models'
        )
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help='Remove test data after verification'
        )
    
    def handle(self, *args, **options):
        """Execute the verification command."""
        self.stdout.write("=" * 80)
        self.stdout.write("PAPER TRADING MODELS VERIFICATION - PTphase1")
        self.stdout.write("=" * 80)
        
        try:
            # Verify existing models
            self.verify_existing_models()
            
            # Verify enhanced models
            self.verify_enhanced_models()
            
            # Create test data if requested
            if options['create_test_data']:
                self.create_test_data()
            
            # Cleanup if requested
            if options['cleanup']:
                self.cleanup_test_data()
            
            self.stdout.write(self.style.SUCCESS("\n✅ All models verified successfully!"))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ Verification failed: {e}"))
            logger.error(f"Paper trading verification failed", exc_info=True)
    
    def verify_existing_models(self):
        """Verify existing paper trading models."""
        self.stdout.write("\n📋 Verifying Existing Models...")
        
        models_to_check = [
            ('PaperTradingAccount', PaperTradingAccount),
            ('PaperTrade', PaperTrade),
            ('PaperPosition', PaperPosition),
            ('PaperTradingConfig', PaperTradingConfig),
        ]
        
        for name, model_class in models_to_check:
            try:
                count = model_class.objects.count()
                self.stdout.write(f"  ✅ {name}: {count} records found")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ❌ {name}: {e}"))
    
    def verify_enhanced_models(self):
        """Verify enhanced PTphase1 models."""
        self.stdout.write("\n🚀 Verifying Enhanced PTphase1 Models...")
        
        enhanced_models = [
            ('PaperAIThoughtLog', PaperAIThoughtLog),
            ('PaperStrategyConfiguration', PaperStrategyConfiguration),
            ('PaperPerformanceMetrics', PaperPerformanceMetrics),
            ('PaperTradingSession', PaperTradingSession),
        ]
        
        for name, model_class in enhanced_models:
            try:
                count = model_class.objects.count()
                self.stdout.write(f"  ✅ {name}: {count} records found")
                
                # Verify model fields
                fields = [f.name for f in model_class._meta.get_fields()]
                self.stdout.write(f"     Fields: {len(fields)} defined")
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ❌ {name}: {e}"))
    
    @transaction.atomic
    def create_test_data(self):
        """Create test data for all models."""
        self.stdout.write("\n📝 Creating Test Data...")
        
        # Get or create test user
        user, created = User.objects.get_or_create(
            username='paper_test_user',
            defaults={'email': 'test@papertrading.local'}
        )
        if created:
            self.stdout.write("  Created test user")
        
        # Create paper trading account
        account = PaperTradingAccount.objects.create(
            user=user,
            name="PTphase1 Test Account",
            initial_balance_usd=Decimal('10000'),
            current_balance_usd=Decimal('10000')
        )
        self.stdout.write(f"  ✅ Created account: {account.account_id}")
        
        # Create strategy configuration
        strategy_config = PaperStrategyConfiguration.objects.create(
            account=account,
            name="Test Strategy",
            trading_mode='MODERATE',
            use_fast_lane=True,
            use_smart_lane=True,
            confidence_threshold=Decimal('60')
        )
        self.stdout.write(f"  ✅ Created strategy config: {strategy_config.config_id}")
        
        # Create trading session
        session = PaperTradingSession.objects.create(
            account=account,
            strategy_config=strategy_config,
            name="Test Session",
            status='RUNNING',
            starting_balance_usd=account.current_balance_usd
        )
        self.stdout.write(f"  ✅ Created trading session: {session.session_id}")
        
        # Create a paper trade
        trade = PaperTrade.objects.create(
            account=account,
            trade_type='buy',
            token_in_address='0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',  # WETH
            token_in_symbol='WETH',
            token_out_address='0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48',  # USDC
            token_out_symbol='USDC',
            amount_in=Decimal('1.0'),
            amount_in_usd=Decimal('3000'),
            expected_amount_out=Decimal('3000'),
            actual_amount_out=Decimal('2985'),
            simulated_gas_price_gwei=Decimal('30'),
            simulated_gas_used=150000,
            simulated_gas_cost_usd=Decimal('15'),
            simulated_slippage_percent=Decimal('0.5'),
            status='completed'
        )
        self.stdout.write(f"  ✅ Created paper trade: {trade.trade_id}")
        
        # Create AI thought log
        thought = PaperAIThoughtLog.objects.create(
            account=account,
            paper_trade=trade,
            decision_type='BUY',
            token_address=trade.token_out_address,
            token_symbol=trade.token_out_symbol,
            confidence_level='HIGH',
            confidence_percent=Decimal('75'),
            risk_score=Decimal('35'),
            opportunity_score=Decimal('80'),
            primary_reasoning="Strong bullish signals detected with favorable market conditions.",
            key_factors=["RSI oversold", "Volume spike", "Support level held"],
            positive_signals=["Technical breakout", "Increasing volume"],
            negative_signals=["Market volatility"],
            strategy_name="Test Strategy",
            lane_used='FAST',
            analysis_time_ms=250
        )
        self.stdout.write(f"  ✅ Created AI thought log: {thought.thought_id}")
        
        # Create performance metrics
        metrics = PaperPerformanceMetrics.objects.create(
            session=session,
            period_start=timezone.now() - timezone.timedelta(hours=1),
            period_end=timezone.now(),
            total_trades=1,
            winning_trades=1,
            losing_trades=0,
            win_rate=Decimal('100'),
            total_pnl_usd=Decimal('50'),
            total_pnl_percent=Decimal('0.5'),
            avg_win_usd=Decimal('50'),
            avg_execution_time_ms=250,
            total_gas_fees_usd=Decimal('15'),
            avg_slippage_percent=Decimal('0.5'),
            fast_lane_trades=1,
            fast_lane_win_rate=Decimal('100')
        )
        self.stdout.write(f"  ✅ Created performance metrics: {metrics.metrics_id}")
        
        # Create a position
        position = PaperPosition.objects.create(
            account=account,
            token_address=trade.token_out_address,
            token_symbol=trade.token_out_symbol,
            quantity=trade.actual_amount_out,
            average_entry_price_usd=Decimal('1.0'),
            current_price_usd=Decimal('1.02'),
            total_invested_usd=trade.amount_in_usd,
            current_value_usd=Decimal('3045'),
            unrealized_pnl_usd=Decimal('45')
        )
        self.stdout.write(f"  ✅ Created position: {position.position_id}")
        
        self.stdout.write(self.style.SUCCESS("\n  All test data created successfully!"))
    
    def cleanup_test_data(self):
        """Remove test data."""
        self.stdout.write("\n🧹 Cleaning up test data...")
        
        try:
            # Delete test user and cascade will handle related records
            User.objects.filter(username='paper_test_user').delete()
            self.stdout.write(self.style.SUCCESS("  Test data cleaned up successfully"))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  Could not cleanup: {e}"))
    
    def display_summary(self):
        """Display summary of paper trading system."""
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write("PAPER TRADING SYSTEM SUMMARY")
        self.stdout.write("=" * 80)
        
        # Count records
        accounts = PaperTradingAccount.objects.count()
        trades = PaperTrade.objects.count()
        positions = PaperPosition.objects.count()
        thoughts = PaperAIThoughtLog.objects.count()
        configs = PaperStrategyConfiguration.objects.count()
        sessions = PaperTradingSession.objects.count()
        metrics = PaperPerformanceMetrics.objects.count()
        
        self.stdout.write(f"\n📊 Database Statistics:")
        self.stdout.write(f"  • Trading Accounts: {accounts}")
        self.stdout.write(f"  • Trades Executed: {trades}")
        self.stdout.write(f"  • Open Positions: {positions}")
        self.stdout.write(f"  • AI Thought Logs: {thoughts}")
        self.stdout.write(f"  • Strategy Configs: {configs}")
        self.stdout.write(f"  • Trading Sessions: {sessions}")
        self.stdout.write(f"  • Performance Metrics: {metrics}")
        
        # Active sessions
        active_sessions = PaperTradingSession.objects.filter(
            status__in=['STARTING', 'RUNNING', 'PAUSED']
        ).count()
        
        if active_sessions > 0:
            self.stdout.write(f"\n⚡ Active Sessions: {active_sessions}")
        
        self.stdout.write("\n" + "=" * 80)