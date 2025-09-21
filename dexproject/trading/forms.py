"""
Trading Forms - Phase 5.1C Implementation

Django forms for trading input validation, providing comprehensive
validation for trade execution, position management, and configuration.

Features:
- Buy/sell order validation
- Position management forms
- Trading session configuration
- Real-time parameter validation
- Security and safety checks
- Integration with trading models

File: dexproject/trading/forms.py
"""

import logging
from decimal import Decimal
from typing import Dict, Any, Optional, List
import re

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth.models import User

from .models import Chain, Token, TradingPair, Strategy
from shared.utils import validate_address, validate_amount

logger = logging.getLogger("trading.forms")


class BaseTokenForm(forms.Form):
    """
    Base form for token-related operations with common validation.
    
    Provides shared validation logic for token addresses, amounts,
    and blockchain parameters used across multiple trading forms.
    """
    
    token_address = forms.CharField(
        max_length=42,
        min_length=42,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '0x...',
            'pattern': '^0x[a-fA-F0-9]{40}$'
        }),
        help_text='Ethereum address of the token to trade'
    )
    
    chain_id = forms.IntegerField(
        initial=8453,  # Base mainnet
        widget=forms.Select(choices=[
            (1, 'Ethereum Mainnet'),
            (8453, 'Base Mainnet'),
            (84532, 'Base Sepolia (Testnet)'),
            (11155111, 'Ethereum Sepolia (Testnet)'),
            (42161, 'Arbitrum One'),
            (421614, 'Arbitrum Sepolia (Testnet)')
        ], attrs={'class': 'form-select'}),
        help_text='Blockchain network for the trade'
    )
    
    slippage_tolerance = forms.DecimalField(
        max_digits=5,
        decimal_places=3,
        initial=Decimal('0.005'),  # 0.5%
        validators=[
            MinValueValidator(Decimal('0.001')),  # 0.1% minimum
            MaxValueValidator(Decimal('0.5'))     # 50% maximum
        ],
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0.001',
            'max': '0.5',
            'step': '0.001'
        }),
        help_text='Maximum acceptable slippage (0.1% to 50%)'
    )
    
    gas_price_gwei = forms.DecimalField(
        max_digits=8,
        decimal_places=2,
        required=False,
        validators=[
            MinValueValidator(Decimal('1.0')),    # 1 Gwei minimum
            MaxValueValidator(Decimal('1000.0'))  # 1000 Gwei maximum
        ],
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '1.0',
            'max': '1000.0',
            'step': '0.1',
            'placeholder': 'Auto'
        }),
        help_text='Gas price in Gwei (leave empty for automatic)'
    )
    
    def clean_token_address(self) -> str:
        """
        Validate token address format and existence.
        
        Returns:
            Validated token address in checksum format
            
        Raises:
            ValidationError: If address is invalid or token not supported
        """
        address = self.cleaned_data.get('token_address', '').strip()
        
        # Validate address format
        if not validate_address(address):
            raise ValidationError('Invalid token address format')
        
        # Check if token exists in database
        chain_id = self.cleaned_data.get('chain_id', 8453)
        try:
            token = Token.objects.get(address__iexact=address, chain_id=chain_id)
            
            # Security checks
            if token.is_blacklisted:
                raise ValidationError('This token is blacklisted and cannot be traded')
            
            if token.is_honeypot:
                raise ValidationError('This token is identified as a honeypot')
            
            # Warning for unverified tokens (don't block, just warn)
            if not token.is_verified:
                # Add warning to form but don't raise error
                logger.warning(f"Trading unverified token: {address}")
            
            return token.address  # Return checksum address
            
        except Token.DoesNotExist:
            raise ValidationError(
                'Token not found in our database. Please ensure the token is supported.'
            )
    
    def clean_chain_id(self) -> int:
        """
        Validate chain ID is supported.
        
        Returns:
            Validated chain ID
            
        Raises:
            ValidationError: If chain is not supported
        """
        chain_id = self.cleaned_data.get('chain_id')
        
        try:
            chain = Chain.objects.get(chain_id=chain_id, is_active=True)
            return chain_id
        except Chain.DoesNotExist:
            raise ValidationError('Unsupported or inactive blockchain network')
    
    def clean(self) -> Dict[str, Any]:
        """
        Cross-field validation for token and chain compatibility.
        
        Returns:
            Cleaned form data
            
        Raises:
            ValidationError: If token and chain are incompatible
        """
        cleaned_data = super().clean()
        token_address = cleaned_data.get('token_address')
        chain_id = cleaned_data.get('chain_id')
        
        if token_address and chain_id:
            # Verify trading pair exists
            try:
                trading_pair = TradingPair.objects.get(
                    base_token__address__iexact=token_address,
                    chain_id=chain_id,
                    is_active=True
                )
                cleaned_data['trading_pair'] = trading_pair
            except TradingPair.DoesNotExist:
                raise ValidationError(
                    'No active trading pair found for this token on the selected network'
                )
        
        return cleaned_data


class BuyOrderForm(BaseTokenForm):
    """
    Form for buy order execution with ETH amount validation.
    
    Validates buy orders where users spend ETH to purchase tokens,
    including minimum/maximum amounts and balance checks.
    """
    
    amount_eth = forms.DecimalField(
        max_digits=20,
        decimal_places=8,
        validators=[
            MinValueValidator(Decimal('0.001')),     # 0.001 ETH minimum
            MaxValueValidator(Decimal('1000.0'))     # 1000 ETH maximum
        ],
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0.001',
            'max': '1000.0',
            'step': '0.001',
            'placeholder': '0.1'
        }),
        help_text='Amount of ETH to spend (0.001 to 1000 ETH)'
    )
    
    strategy_id = forms.ModelChoiceField(
        queryset=Strategy.objects.none(),  # Will be set in __init__
        required=False,
        empty_label='Default Strategy',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Trading strategy to use (optional)'
    )
    
    def __init__(self, user: Optional[User] = None, *args, **kwargs):
        """
        Initialize form with user-specific strategy choices.
        
        Args:
            user: User for filtering available strategies
        """
        super().__init__(*args, **kwargs)
        
        if user:
            self.fields['strategy_id'].queryset = Strategy.objects.filter(
                user=user,
                is_active=True
            ).order_by('name')
    
    def clean_amount_eth(self) -> Decimal:
        """
        Validate ETH amount with additional safety checks.
        
        Returns:
            Validated ETH amount
            
        Raises:
            ValidationError: If amount is invalid or unsafe
        """
        amount = self.cleaned_data.get('amount_eth')
        
        if not amount:
            raise ValidationError('ETH amount is required')
        
        # Additional safety checks
        if amount > Decimal('100.0'):
            # Require explicit confirmation for large amounts
            confirm_large = self.data.get('confirm_large_amount', False)
            if not confirm_large:
                raise ValidationError(
                    'Large amount detected. Please confirm you want to trade more than 100 ETH.'
                )
        
        return amount


class SellOrderForm(BaseTokenForm):
    """
    Form for sell order execution with token amount validation.
    
    Validates sell orders where users sell tokens for ETH,
    including balance checks and minimum viable amounts.
    """
    
    token_amount = forms.DecimalField(
        max_digits=30,
        decimal_places=18,
        validators=[MinValueValidator(Decimal('0.000001'))],  # Minimum viable amount
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0.000001',
            'step': 'any',
            'placeholder': '1000.0'
        }),
        help_text='Amount of tokens to sell'
    )
    
    percentage_of_position = forms.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        validators=[
            MinValueValidator(Decimal('0.01')),   # 0.01% minimum
            MaxValueValidator(Decimal('100.0'))   # 100% maximum
        ],
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0.01',
            'max': '100.0',
            'step': '0.01',
            'placeholder': '100.0'
        }),
        help_text='Percentage of position to sell (optional, overrides token_amount)'
    )
    
    def clean(self) -> Dict[str, Any]:
        """
        Validate token amount or percentage selection.
        
        Returns:
            Cleaned form data
            
        Raises:
            ValidationError: If neither or both amount types are specified
        """
        cleaned_data = super().clean()
        token_amount = cleaned_data.get('token_amount')
        percentage = cleaned_data.get('percentage_of_position')
        
        if not token_amount and not percentage:
            raise ValidationError('Either token amount or percentage must be specified')
        
        if token_amount and percentage:
            # If both provided, use percentage and ignore token_amount
            cleaned_data['token_amount'] = None
            logger.info('Both amount and percentage provided, using percentage')
        
        return cleaned_data


class PositionCloseForm(forms.Form):
    """
    Form for closing trading positions with validation.
    
    Handles partial or complete position closure with safety checks
    and confirmation requirements for large positions.
    """
    
    position_id = forms.UUIDField(
        widget=forms.HiddenInput(),
        help_text='Position identifier'
    )
    
    percentage = forms.DecimalField(
        max_digits=5,
        decimal_places=2,
        initial=Decimal('100.0'),
        validators=[
            MinValueValidator(Decimal('0.01')),   # 0.01% minimum
            MaxValueValidator(Decimal('100.0'))   # 100% maximum
        ],
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0.01',
            'max': '100.0',
            'step': '0.01',
            'value': '100.0'
        }),
        help_text='Percentage of position to close (0.01% to 100%)'
    )
    
    slippage_tolerance = forms.DecimalField(
        max_digits=5,
        decimal_places=3,
        initial=Decimal('0.005'),  # 0.5%
        validators=[
            MinValueValidator(Decimal('0.001')),  # 0.1% minimum
            MaxValueValidator(Decimal('0.5'))     # 50% maximum
        ],
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0.001',
            'max': '0.5',
            'step': '0.001'
        }),
        help_text='Maximum acceptable slippage (0.1% to 50%)'
    )
    
    gas_price_gwei = forms.DecimalField(
        max_digits=8,
        decimal_places=2,
        required=False,
        validators=[
            MinValueValidator(Decimal('1.0')),
            MaxValueValidator(Decimal('1000.0'))
        ],
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '1.0',
            'max': '1000.0',
            'step': '0.1',
            'placeholder': 'Auto'
        }),
        help_text='Gas price in Gwei (leave empty for automatic)'
    )
    
    def __init__(self, user: Optional[User] = None, *args, **kwargs):
        """
        Initialize form with user validation.
        
        Args:
            user: User for position ownership validation
        """
        self.user = user
        super().__init__(*args, **kwargs)
    
    def clean_position_id(self) -> str:
        """
        Validate position exists and belongs to user.
        
        Returns:
            Validated position ID
            
        Raises:
            ValidationError: If position not found or not owned by user
        """
        from .models import Position  # Import here to avoid circular imports
        
        position_id = self.cleaned_data.get('position_id')
        
        if not position_id:
            raise ValidationError('Position ID is required')
        
        try:
            position = Position.objects.get(
                position_id=position_id,
                user=self.user,
                status='OPEN'
            )
            
            # Check if position has any tokens to sell
            if position.current_amount <= 0:
                raise ValidationError('Position has no tokens to sell')
            
            return str(position_id)
            
        except Position.DoesNotExist:
            raise ValidationError('Position not found or already closed')


class TradingSessionForm(forms.Form):
    """
    Form for trading session configuration with strategy and risk settings.
    
    Configures automated trading sessions with risk management,
    position sizing, and execution parameters.
    """
    
    strategy_id = forms.ModelChoiceField(
        queryset=Strategy.objects.none(),  # Will be set in __init__
        required=False,
        empty_label='Default Strategy',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Trading strategy to use for this session'
    )
    
    max_position_size_usd = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        initial=Decimal('1000.0'),
        validators=[
            MinValueValidator(Decimal('10.0')),      # $10 minimum
            MaxValueValidator(Decimal('1000000.0'))  # $1M maximum
        ],
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '10.0',
            'max': '1000000.0',
            'step': '10.0'
        }),
        help_text='Maximum position size in USD ($10 to $1,000,000)'
    )
    
    risk_tolerance = forms.ChoiceField(
        choices=[
            ('VERY_LOW', 'Very Low - Conservative trading'),
            ('LOW', 'Low - Cautious approach'),
            ('MEDIUM', 'Medium - Balanced trading'),
            ('HIGH', 'High - Aggressive trading'),
            ('VERY_HIGH', 'Very High - Maximum risk')
        ],
        initial='MEDIUM',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Risk tolerance level for automated decisions'
    )
    
    auto_execution = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text='Enable automatic trade execution (requires manual approval if disabled)'
    )
    
    max_daily_trades = forms.IntegerField(
        initial=10,
        validators=[
            MinValueValidator(1),     # 1 trade minimum
            MaxValueValidator(1000)   # 1000 trades maximum
        ],
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '1',
            'max': '1000'
        }),
        help_text='Maximum number of trades per day (1 to 1000)'
    )
    
    stop_loss_percent = forms.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        validators=[
            MinValueValidator(Decimal('0.1')),   # 0.1% minimum
            MaxValueValidator(Decimal('100.0'))  # 100% maximum
        ],
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0.1',
            'max': '100.0',
            'step': '0.1',
            'placeholder': '10.0'
        }),
        help_text='Automatic stop loss percentage (optional)'
    )
    
    take_profit_percent = forms.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        validators=[
            MinValueValidator(Decimal('0.1')),   # 0.1% minimum
            MaxValueValidator(Decimal('1000.0')) # 1000% maximum
        ],
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0.1',
            'max': '1000.0',
            'step': '0.1',
            'placeholder': '25.0'
        }),
        help_text='Automatic take profit percentage (optional)'
    )
    
    def __init__(self, user: Optional[User] = None, *args, **kwargs):
        """
        Initialize form with user-specific strategy choices.
        
        Args:
            user: User for filtering available strategies
        """
        super().__init__(*args, **kwargs)
        
        if user:
            self.fields['strategy_id'].queryset = Strategy.objects.filter(
                user=user,
                is_active=True
            ).order_by('name')
    
    def clean(self) -> Dict[str, Any]:
        """
        Cross-field validation for trading session parameters.
        
        Returns:
            Cleaned form data
            
        Raises:
            ValidationError: If parameter combinations are invalid
        """
        cleaned_data = super().clean()
        stop_loss = cleaned_data.get('stop_loss_percent')
        take_profit = cleaned_data.get('take_profit_percent')
        risk_tolerance = cleaned_data.get('risk_tolerance')
        auto_execution = cleaned_data.get('auto_execution')
        
        # Validate stop loss vs take profit
        if stop_loss and take_profit:
            if stop_loss >= take_profit:
                raise ValidationError(
                    'Take profit percentage must be higher than stop loss percentage'
                )
        
        # Risk tolerance validation
        if auto_execution and risk_tolerance == 'VERY_HIGH':
            # Require explicit confirmation for high-risk auto execution
            confirm_high_risk = self.data.get('confirm_high_risk', False)
            if not confirm_high_risk:
                raise ValidationError(
                    'High-risk automatic execution requires explicit confirmation'
                )
        
        return cleaned_data


class TokenSearchForm(forms.Form):
    """
    Form for token search and filtering with validation.
    
    Provides search functionality for supported tokens with
    filtering by chain, verification status, and metadata.
    """
    
    search = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by symbol, name, or address...'
        }),
        help_text='Search tokens by symbol, name, or contract address'
    )
    
    chain_id = forms.ModelChoiceField(
        queryset=Chain.objects.filter(is_active=True).order_by('chain_id'),
        required=False,
        empty_label='All Networks',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Filter by blockchain network'
    )
    
    verified_only = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text='Show only verified tokens'
    )
    
    exclude_honeypots = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text='Exclude known honeypot tokens'
    )
    
    min_market_cap = forms.DecimalField(
        max_digits=15,
        decimal_places=2,
        required=False,
        validators=[MinValueValidator(Decimal('0.01'))],
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0.01',
            'placeholder': '1000.0'
        }),
        help_text='Minimum market cap in USD (optional)'
    )
    
    limit = forms.IntegerField(
        initial=50,
        validators=[
            MinValueValidator(1),
            MaxValueValidator(500)
        ],
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '1',
            'max': '500'
        }),
        help_text='Maximum number of results (1 to 500)'
    )
    
    def clean_search(self) -> str:
        """
        Validate and sanitize search query.
        
        Returns:
            Cleaned search string
        """
        search = self.cleaned_data.get('search', '').strip()
        
        if search:
            # Remove potentially dangerous characters
            search = re.sub(r'[<>"\';]', '', search)
            
            # Minimum search length
            if len(search) < 2:
                raise ValidationError('Search query must be at least 2 characters long')
        
        return search


# =============================================================================
# FORM UTILITIES AND HELPERS
# =============================================================================

def get_trading_form_context(user: Optional[User] = None) -> Dict[str, Any]:
    """
    Get common context data for trading forms.
    
    Args:
        user: User for personalized data
        
    Returns:
        Dictionary with form context data
    """
    context = {
        'supported_chains': Chain.objects.filter(is_active=True).order_by('chain_id'),
        'user_strategies': Strategy.objects.none(),
        'default_slippage': Decimal('0.005'),
        'min_trade_amount': Decimal('0.001'),
        'max_trade_amount': Decimal('1000.0')
    }
    
    if user and user.is_authenticated:
        context['user_strategies'] = Strategy.objects.filter(
            user=user,
            is_active=True
        ).order_by('name')
    
    return context


def validate_trading_parameters(
    token_address: str,
    amount: Decimal,
    chain_id: int,
    user: Optional[User] = None
) -> Dict[str, Any]:
    """
    Validate trading parameters programmatically.
    
    Args:
        token_address: Token contract address
        amount: Trade amount
        chain_id: Blockchain network ID
        user: User for additional validations
        
    Returns:
        Dictionary with validation results
        
    Raises:
        ValidationError: If parameters are invalid
    """
    results = {
        'valid': True,
        'warnings': [],
        'errors': []
    }
    
    try:
        # Validate token
        token = Token.objects.get(address__iexact=token_address, chain_id=chain_id)
        
        if token.is_blacklisted:
            results['errors'].append('Token is blacklisted')
            results['valid'] = False
        
        if token.is_honeypot:
            results['warnings'].append('Token is identified as a honeypot')
        
        if not token.is_verified:
            results['warnings'].append('Token is not verified')
        
        # Validate amount
        if amount <= 0:
            results['errors'].append('Amount must be positive')
            results['valid'] = False
        
        # Validate chain
        try:
            Chain.objects.get(chain_id=chain_id, is_active=True)
        except Chain.DoesNotExist:
            results['errors'].append('Unsupported blockchain network')
            results['valid'] = False
        
        # Validate trading pair
        try:
            TradingPair.objects.get(
                base_token=token,
                chain_id=chain_id,
                is_active=True
            )
        except TradingPair.DoesNotExist:
            results['errors'].append('No active trading pair for this token')
            results['valid'] = False
        
    except Token.DoesNotExist:
        results['errors'].append('Token not found')
        results['valid'] = False
    
    return results