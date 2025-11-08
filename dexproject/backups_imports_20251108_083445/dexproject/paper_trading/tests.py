"""
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
