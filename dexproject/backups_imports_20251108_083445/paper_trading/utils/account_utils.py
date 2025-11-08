"""
Account Management Utilities for Paper Trading

Centralized functions for user and account management to avoid code duplication.
This module provides single-user account access for the paper trading system.

File: dexproject/paper_trading/utils/account_utils.py
"""

import logging
from typing import Optional, TYPE_CHECKING, cast
from decimal import Decimal

from django.contrib.auth.models import User

# Forward reference for type hints to avoid circular imports
if TYPE_CHECKING:
    from paper_trading.models import PaperTradingAccount

logger = logging.getLogger(__name__)


def get_default_user() -> User:
    """
    Get or create the default user for single-user operation.
    
    This function ensures a consistent demo user exists across the entire
    application (bot, API, dashboard, WebSocket). No authentication required.
    
    Returns:
        User: The default demo user instance
        
    Note:
        - Uses 'demo_user' as the consistent username across the application
        - Email is set to 'demo@example.com' (consistent across all modules)
        - Creates user with default first/last name if not exists
        
    Example:
        >>> user = get_default_user()
        >>> print(user.username)
        'demo_user'
    """
    user, created = User.objects.get_or_create(
        username='demo_user',
        defaults={
            'email': 'demo@example.com',  # FIXED: Consistent email address
            'first_name': 'Demo',
            'last_name': 'User'
        }
    )
    if created:
        logger.info("Created default demo_user for paper trading")
    else:
        logger.debug("Retrieved existing demo_user")
    
    return user


def get_single_trading_account() -> "PaperTradingAccount":
    """
    Get or create THE SINGLE paper trading account for demo_user.
    
    This ensures only ONE account exists and is used across the entire system.
    Multiple accounts caused confusion with data showing in different places.
    
    Returns:
        PaperTradingAccount: The single account instance
        
    Raises:
        RuntimeError: If multiple accounts exist (shouldn't happen)
    """
    from paper_trading.models import PaperTradingAccount
    from django.contrib.auth.models import User
    
    # Get or create demo_user
    user, _ = User.objects.get_or_create(
        username='demo_user',
        defaults={
            'email': 'demo@papertrading.ai',
            'first_name': 'Demo',
            'last_name': 'User'
        }
    )
    
    # Get all accounts for demo_user
    accounts = PaperTradingAccount.objects.filter(user=user, is_active=True)
    
    if accounts.count() == 0:
        # No accounts exist - create the single account
        account = PaperTradingAccount.objects.create(
            user=user,
            name='My_Trading_Account',
            initial_balance_usd=Decimal('10000.00'),
            current_balance_usd=Decimal('10000.00'),
            is_active=True
        )
        logger.info(
            f"Created single paper trading account: {account.name} "
            f"({account.account_id})"
        )
        return account
    
    elif accounts.count() == 1:
        # Perfect - exactly one account
        account = accounts.first()
        
        # Standardize name if needed
        if account.name != 'My_Trading_Account':
            old_name = account.name
            account.name = 'My_Trading_Account'
            account.save()
            logger.info(f"Renamed account from '{old_name}' to 'My_Trading_Account'")
        
        return account
    
    else:
        # Multiple accounts exist - this shouldn't happen!
        # Return the first one but log a warning
        account = accounts.first()
        logger.warning(
            f"Found {accounts.count()} active accounts for demo_user! "
            f"Using first: {account.name} ({account.account_id}). "
            f"Run 'python manage.py cleanup_accounts' to fix."
        )
        return account


def get_account_by_id(account_id: str) -> "PaperTradingAccount":
    """
    Get a paper trading account by its UUID.
    
    Args:
        account_id: UUID string of the account
        
    Returns:
        PaperTradingAccount: The account instance
        
    Raises:
        PaperTradingAccount.DoesNotExist: If account not found
        
    Example:
        >>> account = get_account_by_id('550e8400-e29b-41d4-a716-446655440000')
    """
    # Lazy import to avoid circular dependency issues
    from paper_trading.models import PaperTradingAccount
    
    return PaperTradingAccount.objects.get(account_id=account_id)


def ensure_account_active(account: "PaperTradingAccount") -> bool:
    """
    Ensure an account is marked as active.
    
    Args:
        account: PaperTradingAccount instance
        
    Returns:
        bool: True if account was updated, False if already active
        
    Example:
        >>> was_updated = ensure_account_active(account)
        >>> if was_updated:
        ...     print("Account was reactivated")
    """
    if not account.is_active:
        account.is_active = True
        account.save()
        logger.info(f"Reactivated account {account.account_id}")
        return True
    return False