#!/usr/bin/env python3
"""
Paper Trading Django App Setup Script

This script creates a complete paper trading app structure with:
- Models for paper trades and positions
- Services for trade simulation
- Management commands for testing
- Views for paper trading dashboard

Run this script to create the paper_trading app structure:
python scripts/create_paper_trading_app.py

File: dexproject/scripts/create_paper_trading_app.py
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))


def create_paper_trading_app():
    """Create the complete paper trading app structure."""
    
    print("🎮 Creating Paper Trading Django App...")
    
    # Base directory for the app
    app_dir = Path("paper_trading")
    app_dir.mkdir(exist_ok=True)
    
    # Create __init__.py
    (app_dir / "__init__.py").touch()
    
    # =========================================================================
    # 1. Create apps.py
    # =========================================================================
    apps_content = '''from django.apps import AppConfig


class PaperTradingConfig(AppConfig):
    """Paper Trading application configuration."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'paper_trading'
    verbose_name = 'Paper Trading Simulator'
    
    def ready(self):
        """Initialize app when Django starts."""
        # Import signal handlers if needed
        pass
'''
    
    with open(app_dir / "apps.py", "w") as f:
        f.write(apps_content)
    print("✅ Created apps.py")
    
    # =========================================================================
    # 2. Create models.py
    # =========================================================================
    models_content = '''"""
Paper Trading Models

Separate models for paper trading to keep simulation data
isolated from real trading data.

File: dexproject/paper_trading/models.py
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal
import uuid


class PaperTradingAccount(models.Model):
    """
    Virtual trading account for paper trading.
    
    Each user can have multiple paper trading accounts
    to test different strategies.
    """
    
    account_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='paper_accounts'
    )
    name = models.CharField(
        max_length=100,
        help_text="Account name (e.g., 'Conservative Strategy', 'High Risk')"
    )
    
    # Virtual balances
    initial_balance_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('10000.00'),
        help_text="Starting virtual USD balance"
    )
    current_balance_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('10000.00')
    )
    
    # Virtual ETH for gas
    eth_balance = models.DecimalField(
        max_digits=20,
        decimal_places=18,
        default=Decimal('1.0'),
        help_text="Virtual ETH for gas fees"
    )
    
    # Performance metrics
    total_trades = models.IntegerField(default=0)
    successful_trades = models.IntegerField(default=0)
    failed_trades = models.IntegerField(default=0)
    total_pnl_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0')
    )
    total_fees_paid_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0')
    )
    
    # Account status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    reset_count = models.IntegerField(
        default=0,
        help_text="Number of times account has been reset"
    )
    
    class Meta:
        db_table = 'paper_trading_accounts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.name}"
    
    def reset_account(self):
        """Reset account to initial state."""
        self.current_balance_usd = self.initial_balance_usd
        self.eth_balance = Decimal('1.0')
        self.total_trades = 0
        self.successful_trades = 0
        self.failed_trades = 0
        self.total_pnl_usd = Decimal('0')
        self.total_fees_paid_usd = Decimal('0')
        self.reset_count += 1
        self.save()
    
    @property
    def win_rate(self):
        """Calculate win rate percentage."""
        if self.total_trades == 0:
            return 0
        return (self.successful_trades / self.total_trades) * 100
    
    @property
    def total_return_percent(self):
        """Calculate total return percentage."""
        if self.initial_balance_usd == 0:
            return 0
        return ((self.current_balance_usd - self.initial_balance_usd) / 
                self.initial_balance_usd * 100)


class PaperTrade(models.Model):
    """
    Individual paper trade record.
    
    Stores all simulated trades with realistic execution details.
    """
    
    TRADE_STATUS = (
        ('pending', 'Pending'),
        ('executing', 'Executing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    )
    
    TRADE_TYPES = (
        ('buy', 'Buy'),
        ('sell', 'Sell'),
        ('swap', 'Swap'),
    )
    
    # Identity
    trade_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    account = models.ForeignKey(
        PaperTradingAccount,
        on_delete=models.CASCADE,
        related_name='trades'
    )
    
    # Trade details
    trade_type = models.CharField(
        max_length=10,
        choices=TRADE_TYPES
    )
    token_in_address = models.CharField(max_length=42)
    token_in_symbol = models.CharField(max_length=20)
    token_out_address = models.CharField(max_length=42)
    token_out_symbol = models.CharField(max_length=20)
    
    # Amounts
    amount_in = models.DecimalField(
        max_digits=36,
        decimal_places=18,
        help_text="Amount in (wei)"
    )
    amount_in_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2
    )
    expected_amount_out = models.DecimalField(
        max_digits=36,
        decimal_places=18
    )
    actual_amount_out = models.DecimalField(
        max_digits=36,
        decimal_places=18,
        null=True,
        blank=True
    )
    
    # Execution details
    simulated_gas_price_gwei = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )
    simulated_gas_used = models.IntegerField()
    simulated_gas_cost_usd = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )
    simulated_slippage_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2
    )
    
    # Timing
    created_at = models.DateTimeField(auto_now_add=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    execution_time_ms = models.IntegerField(
        null=True,
        blank=True,
        help_text="Simulated execution time in milliseconds"
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=TRADE_STATUS,
        default='pending'
    )
    error_message = models.TextField(blank=True)
    
    # Mock transaction details
    mock_tx_hash = models.CharField(
        max_length=66,
        blank=True,
        help_text="Simulated transaction hash"
    )
    mock_block_number = models.IntegerField(null=True, blank=True)
    
    # Strategy reference (optional)
    strategy_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Trading strategy used"
    )
    
    class Meta:
        db_table = 'paper_trades'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['account', 'status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['trade_type']),
        ]
    
    def __str__(self):
        return f"Paper Trade {self.trade_id} - {self.trade_type}"
    
    def calculate_pnl(self):
        """Calculate P&L for this trade."""
        if self.status != 'completed':
            return Decimal('0')
        
        # Calculate based on trade type
        if self.trade_type == 'sell':
            # For sells, P&L is the USD received minus gas
            return self.amount_in_usd - self.simulated_gas_cost_usd
        else:
            # For buys, we need position tracking (simplified here)
            return Decimal('0')


class PaperPosition(models.Model):
    """
    Open positions in paper trading account.
    
    Tracks simulated holdings and unrealized P&L.
    """
    
    position_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    account = models.ForeignKey(
        PaperTradingAccount,
        on_delete=models.CASCADE,
        related_name='positions'
    )
    
    # Token details
    token_address = models.CharField(max_length=42)
    token_symbol = models.CharField(max_length=20)
    
    # Position details
    quantity = models.DecimalField(
        max_digits=36,
        decimal_places=18
    )
    average_entry_price_usd = models.DecimalField(
        max_digits=20,
        decimal_places=6
    )
    current_price_usd = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        null=True,
        blank=True
    )
    
    # P&L tracking
    total_invested_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2
    )
    current_value_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        null=True,
        blank=True
    )
    unrealized_pnl_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0')
    )
    realized_pnl_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0')
    )
    
    # Risk management
    stop_loss_price = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        null=True,
        blank=True
    )
    take_profit_price = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        null=True,
        blank=True
    )
    
    # Status
    is_open = models.BooleanField(default=True)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'paper_positions'
        ordering = ['-opened_at']
        indexes = [
            models.Index(fields=['account', 'is_open']),
            models.Index(fields=['token_address']),
        ]
        unique_together = [
            ['account', 'token_address', 'is_open']
        ]
    
    def __str__(self):
        return f"{self.token_symbol} Position - {self.quantity}"
    
    def update_price(self, new_price_usd):
        """Update current price and calculate unrealized P&L."""
        self.current_price_usd = new_price_usd
        self.current_value_usd = self.quantity * new_price_usd
        self.unrealized_pnl_usd = self.current_value_usd - self.total_invested_usd
        self.last_updated = timezone.now()
        self.save()
    
    def close_position(self, exit_price_usd):
        """Close position and calculate realized P&L."""
        self.current_price_usd = exit_price_usd
        self.current_value_usd = self.quantity * exit_price_usd
        self.realized_pnl_usd = self.current_value_usd - self.total_invested_usd
        self.unrealized_pnl_usd = Decimal('0')
        self.is_open = False
        self.closed_at = timezone.now()
        self.save()


class PaperTradingConfig(models.Model):
    """
    Configuration for paper trading simulation parameters.
    
    Allows customization of simulation behavior per account.
    """
    
    account = models.OneToOneField(
        PaperTradingAccount,
        on_delete=models.CASCADE,
        related_name='config'
    )
    
    # Simulation parameters
    base_slippage_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.5'),
        help_text="Base slippage percentage for all trades"
    )
    gas_price_multiplier = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('1.0'),
        help_text="Multiplier for gas price simulation"
    )
    execution_delay_ms = models.IntegerField(
        default=500,
        help_text="Simulated execution delay in milliseconds"
    )
    
    # Risk limits
    max_position_size_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('10.0'),
        help_text="Max position size as % of portfolio"
    )
    max_daily_trades = models.IntegerField(
        default=50,
        help_text="Maximum trades per day"
    )
    stop_loss_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.0'),
        help_text="Default stop loss percentage"
    )
    
    # Realistic simulation
    simulate_network_issues = models.BooleanField(
        default=True,
        help_text="Simulate occasional network failures"
    )
    simulate_mev = models.BooleanField(
        default=True,
        help_text="Simulate MEV bot competition"
    )
    failure_rate_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('2.0'),
        help_text="Percentage of trades that should randomly fail"
    )
    
    class Meta:
        db_table = 'paper_trading_configs'
    
    def __str__(self):
        return f"Config for {self.account.name}"
'''
    
    with open(app_dir / "models.py", "w") as f:
        f.write(models_content)
    print("✅ Created models.py with Paper Trading models")
    
    # =========================================================================
    # 3. Create admin.py
    # =========================================================================
    admin_content = '''"""
Paper Trading Admin Interface

Django admin configuration for paper trading models.

File: dexproject/paper_trading/admin.py
"""

from django.contrib import admin
from .models import (
    PaperTradingAccount,
    PaperTrade,
    PaperPosition,
    PaperTradingConfig
)


@admin.register(PaperTradingAccount)
class PaperTradingAccountAdmin(admin.ModelAdmin):
    """Admin interface for Paper Trading Accounts."""
    
    list_display = [
        'name', 'user', 'current_balance_usd', 
        'total_pnl_usd', 'win_rate', 'is_active'
    ]
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'user__username']
    readonly_fields = [
        'account_id', 'created_at', 'updated_at',
        'total_trades', 'successful_trades', 'failed_trades'
    ]
    
    fieldsets = (
        ('Account Info', {
            'fields': ('account_id', 'user', 'name', 'is_active')
        }),
        ('Balances', {
            'fields': (
                'initial_balance_usd', 'current_balance_usd',
                'eth_balance'
            )
        }),
        ('Performance', {
            'fields': (
                'total_trades', 'successful_trades', 'failed_trades',
                'total_pnl_usd', 'total_fees_paid_usd'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'reset_count')
        })
    )
    
    actions = ['reset_accounts']
    
    def reset_accounts(self, request, queryset):
        """Reset selected accounts to initial state."""
        for account in queryset:
            account.reset_account()
        self.message_user(
            request,
            f"Reset {queryset.count()} account(s)"
        )
    reset_accounts.short_description = "Reset selected accounts"


@admin.register(PaperTrade)
class PaperTradeAdmin(admin.ModelAdmin):
    """Admin interface for Paper Trades."""
    
    list_display = [
        'trade_id', 'account', 'trade_type', 
        'token_in_symbol', 'token_out_symbol',
        'status', 'created_at'
    ]
    list_filter = ['status', 'trade_type', 'created_at']
    search_fields = [
        'trade_id', 'token_in_symbol', 'token_out_symbol',
        'account__name'
    ]
    readonly_fields = ['trade_id', 'created_at', 'executed_at']
    
    fieldsets = (
        ('Trade Identity', {
            'fields': ('trade_id', 'account', 'trade_type', 'status')
        }),
        ('Tokens', {
            'fields': (
                'token_in_address', 'token_in_symbol',
                'token_out_address', 'token_out_symbol'
            )
        }),
        ('Amounts', {
            'fields': (
                'amount_in', 'amount_in_usd',
                'expected_amount_out', 'actual_amount_out'
            )
        }),
        ('Execution Details', {
            'fields': (
                'simulated_gas_price_gwei', 'simulated_gas_used',
                'simulated_gas_cost_usd', 'simulated_slippage_percent',
                'execution_time_ms'
            )
        }),
        ('Transaction', {
            'fields': ('mock_tx_hash', 'mock_block_number')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'executed_at')
        })
    )


@admin.register(PaperPosition)
class PaperPositionAdmin(admin.ModelAdmin):
    """Admin interface for Paper Positions."""
    
    list_display = [
        'token_symbol', 'account', 'quantity',
        'unrealized_pnl_usd', 'is_open'
    ]
    list_filter = ['is_open', 'opened_at']
    search_fields = ['token_symbol', 'token_address', 'account__name']
    readonly_fields = [
        'position_id', 'opened_at', 'closed_at', 'last_updated'
    ]


@admin.register(PaperTradingConfig)
class PaperTradingConfigAdmin(admin.ModelAdmin):
    """Admin interface for Paper Trading Configuration."""
    
    list_display = [
        'account', 'base_slippage_percent',
        'max_position_size_percent', 'max_daily_trades'
    ]
    search_fields = ['account__name']
'''
    
    with open(app_dir / "admin.py", "w") as f:
        f.write(admin_content)
    print("✅ Created admin.py")
    
    # Create management directory
    mgmt_dir = app_dir / "management"
    mgmt_dir.mkdir(exist_ok=True)
    (mgmt_dir / "__init__.py").touch()
    
    cmd_dir = mgmt_dir / "commands"
    cmd_dir.mkdir(exist_ok=True)
    (cmd_dir / "__init__.py").touch()
    
    # Create views.py
    views_content = '''"""
Paper Trading Views

API endpoints for paper trading functionality.

File: dexproject/paper_trading/views.py
"""

from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
import json

# Views will be implemented based on requirements
'''
    
    with open(app_dir / "views.py", "w") as f:
        f.write(views_content)
    
    # Create urls.py
    urls_content = '''"""
Paper Trading URL Configuration

File: dexproject/paper_trading/urls.py
"""

from django.urls import path
from . import views

app_name = 'paper_trading'

urlpatterns = [
    # URLs will be added as views are implemented
]
'''
    
    with open(app_dir / "urls.py", "w") as f:
        f.write(urls_content)
    
    # Create services directory
    services_dir = app_dir / "services"
    services_dir.mkdir(exist_ok=True)
    (services_dir / "__init__.py").touch()
    
    # Create tests.py
    tests_content = '''"""
Paper Trading Tests

File: dexproject/paper_trading/tests.py
"""

from django.test import TestCase
from django.contrib.auth.models import User
from decimal import Decimal
from .models import PaperTradingAccount, PaperTrade


class PaperTradingAccountTestCase(TestCase):
    """Test paper trading account functionality."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.account = PaperTradingAccount.objects.create(
            user=self.user,
            name='Test Account'
        )
    
    def test_account_creation(self):
        """Test account is created with default values."""
        self.assertEqual(
            self.account.initial_balance_usd,
            Decimal('10000.00')
        )
        self.assertEqual(
            self.account.current_balance_usd,
            Decimal('10000.00')
        )
        self.assertTrue(self.account.is_active)
    
    def test_account_reset(self):
        """Test account reset functionality."""
        # Modify account
        self.account.current_balance_usd = Decimal('5000.00')
        self.account.total_trades = 10
        self.account.save()
        
        # Reset account
        self.account.reset_account()
        
        # Check reset
        self.assertEqual(
            self.account.current_balance_usd,
            Decimal('10000.00')
        )
        self.assertEqual(self.account.total_trades, 0)
        self.assertEqual(self.account.reset_count, 1)
'''
    
    with open(app_dir / "tests.py", "w") as f:
        f.write(tests_content)
    
    print("✅ Created all app files")
    print("\n📝 Next steps:")
    print("1. Add 'paper_trading' to INSTALLED_APPS in settings.py")
    print("2. Run: python manage.py makemigrations paper_trading")
    print("3. Run: python manage.py migrate")
    print("4. Create paper trading service and simulator")
    
    return True


if __name__ == "__main__":
    # Create the paper trading app
    success = create_paper_trading_app()
    
    if success:
        print("\n✅ Paper Trading app structure created successfully!")
        print("\n🎮 Paper Trading App Features:")
        print("- Separate models for paper trades")
        print("- Virtual account management")
        print("- Position tracking with P&L")
        print("- Configurable simulation parameters")
        print("- Admin interface for monitoring")
    else:
        print("\n❌ Failed to create paper trading app")