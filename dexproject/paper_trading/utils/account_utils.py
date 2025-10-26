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


def get_single_trading_account(user: Optional[User] = None) -> "PaperTradingAccount":
    """
    Get or create the single paper trading account for the application.
    
    This ensures only one account exists and is consistently used across
    the entire application (bot, API, dashboard, WebSocket). Automatically
    cleans up any duplicate accounts if they exist.
    
    Args:
        user: The user to get account for. If None, uses demo_user.
        
    Returns:
        PaperTradingAccount: The single account for this user
        
    Raises:
        ImportError: If PaperTradingAccount model cannot be imported
        
    Note:
        - Uses consistent account name 'My_Trading_Account'
        - Default balance: $10,000 USD
        - Automatically removes duplicate accounts if found
        - Ensures account is always active
        - Lazy imports model to avoid circular dependencies
        
    Example:
        >>> account = get_single_trading_account()
        >>> print(account.name)
        'My_Trading_Account'
        >>> print(account.current_balance_usd)
        Decimal('10000.00')
    """
    # Lazy import to avoid circular dependency issues
    from paper_trading.models import PaperTradingAccount
    
    if user is None:
        user = get_default_user()
    
    # Get all accounts for this user, ordered by creation date
    accounts = PaperTradingAccount.objects.filter(user=user).order_by('created_at')
    
    if accounts.exists():
        # Use the first (oldest) account
        # Safe to cast because exists() guarantees at least one result
        account: "PaperTradingAccount" = cast("PaperTradingAccount", accounts.first())
        
        # Clean up any duplicates
        if accounts.count() > 1:
            logger.warning(
                f"Found {accounts.count()} accounts for user {user.username}, "
                f"cleaning up duplicates"
            )
            # Keep the first account, delete others
            duplicate_count = 0
            for duplicate in accounts[1:]:
                logger.info(
                    f"Removing duplicate account: {duplicate.name} "
                    f"({duplicate.account_id})"
                )
                duplicate.delete()
                duplicate_count += 1
            
            logger.info(f"Removed {duplicate_count} duplicate account(s)")
        
        # Ensure the account is active and has the consistent name
        needs_update = False
        if not account.is_active:
            account.is_active = True
            needs_update = True
            logger.info(f"Reactivated account {account.account_id}")
        
        if account.name != 'My_Trading_Account':
            old_name = account.name
            account.name = 'My_Trading_Account'
            needs_update = True
            logger.info(
                f"Updated account name from '{old_name}' to 'My_Trading_Account'"
            )
        
        if needs_update:
            account.save()
        
        logger.debug(
            f"Using existing account: {account.name} ({account.account_id})"
        )
        
    else:
        # No account exists, create the single account
        account: "PaperTradingAccount" = PaperTradingAccount.objects.create(
            user=user,
            name='My_Trading_Account',
            initial_balance_usd=Decimal('10000.00'),
            current_balance_usd=Decimal('10000.00'),
            is_active=True
        )
        logger.info(
            f"Created new paper trading account: {account.name} "
            f"({account.account_id}) for user {user.username}"
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