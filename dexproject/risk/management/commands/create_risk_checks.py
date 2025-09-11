"""
Django management command to create initial risk check types.

This command creates the foundational risk checks needed for the DEX 
auto-trading bot's industrial-grade risk management system.
"""

import logging
from decimal import Decimal
from typing import Dict, List

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ...models import RiskCheckType


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Management command to create risk check types."""
    
    help = 'Create initial risk check types for the trading bot risk engine'
    
    def add_arguments(self, parser) -> None:
        """Add command line arguments."""
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recreation of existing risk checks (will delete existing)',
        )
        parser.add_argument(
            '--category',
            type=str,
            help='Only create checks for specific category',
            choices=[
                'HONEYPOT', 'LIQUIDITY', 'OWNERSHIP', 'TAX_ANALYSIS',
                'CONTRACT_SECURITY', 'HOLDER_ANALYSIS', 'MARKET_STRUCTURE', 'SOCIAL_SIGNALS'
            ]
        )
    
    def handle(self, *args, **options) -> None:
        """Execute the command."""
        self.verbosity = options.get('verbosity', 1)
        force = options.get('force', False)
        category_filter = options.get('category')
        
        try:
            with transaction.atomic():
                if force:
                    self._clear_existing_checks()
                
                checks_created = self._create_risk_checks(category_filter)
                self._log_success(f"Created {checks_created} risk checks")
                
                self._log_success("Risk checks creation completed successfully!")
                
        except Exception as e:
            logger.error(f"Failed to create risk checks: {e}")
            raise CommandError(f"Command failed: {e}")
    
    def _clear_existing_checks(self) -> None:
        """Clear existing risk checks if force flag is used."""
        self._log_info("Clearing existing risk checks...")
        
        check_count = RiskCheckType.objects.count()
        RiskCheckType.objects.all().delete()
        
        self._log_info(f"Deleted {check_count} risk checks")
    
    def _create_risk_checks(self, category_filter: str = None) -> int:
        """Create risk check types."""
        self._log_info("Creating risk check types...")
        
        risk_checks_data = self._get_risk_checks_data()
        
        # Filter by category if specified
        if category_filter:
            risk_checks_data = [
                check for check in risk_checks_data 
                if check['category'] == category_filter
            ]
        
        checks_created = 0
        
        for check_data in risk_checks_data:
            check, created = RiskCheckType.objects.get_or_create(
                name=check_data['name'],
                defaults=check_data
            )
            
            if created:
                checks_created += 1
                blocking_text = " (BLOCKING)" if check.is_blocking else ""
                self._log_info(f"Created risk check: {check.name}{blocking_text}")
            else:
                self._log_info(f"Risk check already exists: {check.name}")
        
        return checks_created
    
    def _get_risk_checks_data(self) -> List[Dict]:
        """Get risk check configuration data."""
        return [
            # HONEYPOT DETECTION
            {
                'name': 'Honeypot Detection',
                'category': 'HONEYPOT',
                'description': 'Detects honeypot tokens that prevent selling after purchase',
                'severity': 'CRITICAL',
                'is_blocking': True,
                'timeout_seconds': 15,
                'retry_count': 3,
                'weight': Decimal('10.0'),
                'config': {
                    'simulation_amount': '0.001',
                    'max_gas_limit': 500000,
                    'check_sell_simulation': True,
                    'check_transfer_simulation': True
                }
            },
            {
                'name': 'Buy Tax Analysis',
                'category': 'TAX_ANALYSIS',
                'description': 'Analyzes buy tax percentage and hidden fees',
                'severity': 'HIGH',
                'is_blocking': False,
                'timeout_seconds': 10,
                'retry_count': 2,
                'weight': Decimal('3.0'),
                'config': {
                    'max_acceptable_tax': 5.0,
                    'simulation_amount': '0.001',
                    'include_slippage': True
                }
            },
            {
                'name': 'Sell Tax Analysis',
                'category': 'TAX_ANALYSIS',
                'description': 'Analyzes sell tax percentage and exit fees',
                'severity': 'HIGH',
                'is_blocking': False,
                'timeout_seconds': 10,
                'retry_count': 2,
                'weight': Decimal('4.0'),
                'config': {
                    'max_acceptable_tax': 5.0,
                    'simulation_amount': '0.001',
                    'check_cooldown_period': True
                }
            },
            
            # OWNERSHIP CHECKS
            {
                'name': 'Ownership Renounced Check',
                'category': 'OWNERSHIP',
                'description': 'Verifies contract ownership has been renounced',
                'severity': 'HIGH',
                'is_blocking': True,
                'timeout_seconds': 8,
                'retry_count': 2,
                'weight': Decimal('5.0'),
                'config': {
                    'check_owner_address': True,
                    'acceptable_owner_addresses': [
                        '0x0000000000000000000000000000000000000000',
                        '0x000000000000000000000000000000000000dEaD'
                    ]
                }
            },
            {
                'name': 'Admin Function Analysis',
                'category': 'OWNERSHIP',
                'description': 'Checks for dangerous admin functions in contract',
                'severity': 'HIGH',
                'is_blocking': False,
                'timeout_seconds': 12,
                'retry_count': 2,
                'weight': Decimal('4.0'),
                'config': {
                    'dangerous_functions': [
                        'mint', 'burn', 'pause', 'setTax', 'blacklist',
                        'setMaxTx', 'excludeFromFee', 'setFee'
                    ],
                    'check_timelock': True
                }
            },
            
            # LIQUIDITY CHECKS
            {
                'name': 'LP Lock Verification',
                'category': 'LIQUIDITY',
                'description': 'Verifies liquidity pool tokens are locked',
                'severity': 'CRITICAL',
                'is_blocking': True,
                'timeout_seconds': 15,
                'retry_count': 3,
                'weight': Decimal('8.0'),
                'config': {
                    'min_lock_duration_days': 30,
                    'acceptable_lock_platforms': [
                        'team.finance', 'unicrypt', 'dxsale', 'pinksale'
                    ],
                    'check_lock_amount_percentage': 90.0
                }
            },
            {
                'name': 'Liquidity Depth Analysis',
                'category': 'LIQUIDITY',
                'description': 'Analyzes liquidity depth and market impact',
                'severity': 'MEDIUM',
                'is_blocking': False,
                'timeout_seconds': 8,
                'retry_count': 2,
                'weight': Decimal('2.0'),
                'config': {
                    'min_liquidity_usd': 50000,
                    'max_price_impact_1eth': 5.0,
                    'check_liquidity_distribution': True
                }
            },
            
            # HOLDER ANALYSIS
            {
                'name': 'Holder Concentration Check',
                'category': 'HOLDER_ANALYSIS',
                'description': 'Analyzes token holder concentration and whale presence',
                'severity': 'MEDIUM',
                'is_blocking': False,
                'timeout_seconds': 10,
                'retry_count': 2,
                'weight': Decimal('2.5'),
                'config': {
                    'max_top_holder_percentage': 20.0,
                    'max_top_10_percentage': 50.0,
                    'exclude_known_addresses': [
                        'burn_address', 'router_address', 'factory_address'
                    ],
                    'min_holders_count': 100
                }
            },
            {
                'name': 'Whale Wallet Analysis',
                'category': 'HOLDER_ANALYSIS',
                'description': 'Analyzes large holder wallets for suspicious activity',
                'severity': 'MEDIUM',
                'is_blocking': False,
                'timeout_seconds': 12,
                'retry_count': 2,
                'weight': Decimal('1.5'),
                'config': {
                    'whale_threshold_percentage': 5.0,
                    'check_wallet_history': True,
                    'check_multiple_tokens': True,
                    'max_recent_dumps': 3
                }
            },
            
            # CONTRACT SECURITY
            {
                'name': 'Contract Verification Check',
                'category': 'CONTRACT_SECURITY',
                'description': 'Verifies contract source code is published and verified',
                'severity': 'MEDIUM',
                'is_blocking': False,
                'timeout_seconds': 5,
                'retry_count': 1,
                'weight': Decimal('1.0'),
                'config': {
                    'require_verification': False,
                    'check_multiple_explorers': True,
                    'acceptable_compilers': ['0.8.0+']
                }
            },
            {
                'name': 'Proxy Contract Analysis',
                'category': 'CONTRACT_SECURITY',
                'description': 'Analyzes proxy contracts and upgrade mechanisms',
                'severity': 'HIGH',
                'is_blocking': False,
                'timeout_seconds': 10,
                'retry_count': 2,
                'weight': Decimal('3.5'),
                'config': {
                    'check_proxy_type': True,
                    'require_timelock': True,
                    'min_timelock_delay': 86400,  # 24 hours
                    'check_admin_key': True
                }
            },
            
            # MARKET STRUCTURE
            {
                'name': 'Market Cap Analysis',
                'category': 'MARKET_STRUCTURE',
                'description': 'Analyzes market cap and valuation metrics',
                'severity': 'LOW',
                'is_blocking': False,
                'timeout_seconds': 5,
                'retry_count': 1,
                'weight': Decimal('0.5'),
                'config': {
                    'min_market_cap_usd': 100000,
                    'max_market_cap_usd': 100000000,
                    'check_fdv_ratio': True
                }
            },
            {
                'name': 'Trading Volume Analysis',
                'category': 'MARKET_STRUCTURE',
                'description': 'Analyzes trading volume patterns and sustainability',
                'severity': 'LOW',
                'is_blocking': False,
                'timeout_seconds': 8,
                'retry_count': 1,
                'weight': Decimal('1.0'),
                'config': {
                    'min_24h_volume_usd': 10000,
                    'volume_to_liquidity_ratio': 0.5,
                    'check_volume_trend': True
                }
            },
            
            # SOCIAL SIGNALS
            {
                'name': 'Social Media Presence',
                'category': 'SOCIAL_SIGNALS',
                'description': 'Checks for legitimate social media presence and community',
                'severity': 'LOW',
                'is_blocking': False,
                'timeout_seconds': 10,
                'retry_count': 1,
                'weight': Decimal('0.5'),
                'config': {
                    'check_twitter': True,
                    'check_telegram': True,
                    'check_website': True,
                    'min_followers': 1000,
                    'check_account_age': True
                }
            },
            {
                'name': 'Team Doxx Status',
                'category': 'SOCIAL_SIGNALS',
                'description': 'Verifies team member identities and backgrounds',
                'severity': 'LOW',
                'is_blocking': False,
                'timeout_seconds': 15,
                'retry_count': 1,
                'weight': Decimal('0.5'),
                'config': {
                    'require_doxxed_team': False,
                    'check_linkedin': True,
                    'check_previous_projects': True,
                    'verify_credentials': False
                }
            }
        ]
    
    def _log_info(self, message: str) -> None:
        """Log info message based on verbosity."""
        if self.verbosity >= 1:
            self.stdout.write(message)
        logger.info(message)
    
    def _log_success(self, message: str) -> None:
        """Log success message."""
        if self.verbosity >= 1:
            self.stdout.write(self.style.SUCCESS(message))
        logger.info(message)