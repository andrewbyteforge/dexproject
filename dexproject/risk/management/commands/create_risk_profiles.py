"""
Django management command to create initial risk profiles.

This command creates default risk profiles (Conservative, Moderate, Aggressive)
with appropriate risk tolerances and check configurations.
"""

import logging
from decimal import Decimal
from typing import Dict, List

from django.core.management.base import BaseCommand
from shared.management.commands.base import BaseDexCommand, CommandError
from django.db import transaction

from ...models import RiskProfile, RiskCheckType, RiskProfileCheckConfig


logger = logging.getLogger(__name__)


class Command(BaseDexCommand):
    """Management command to create risk profiles."""
    
    help = 'Create initial risk profiles for the trading bot'
    
    def add_arguments(self, parser) -> None:
        """Add command line arguments."""
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recreation of existing risk profiles (will delete existing)',
        )
        parser.add_argument(
            '--profile',
            type=str,
            help='Only create specific profile',
            choices=['conservative', 'moderate', 'aggressive', 'experimental']
        )
    
    def handle(self, *args, **options) -> None:
        """Execute the command."""
        self.verbosity = options.get('verbosity', 1)
        force = options.get('force', False)
        profile_filter = options.get('profile')
        
        try:
            with transaction.atomic():
                if force:
                    self._clear_existing_profiles()
                
                profiles_created = self._create_risk_profiles(profile_filter)
                self._log_success(f"Created {profiles_created} risk profiles")
                
                configs_created = self._configure_profile_checks()
                self._log_success(f"Created {configs_created} profile check configurations")
                
                self._log_success("Risk profiles creation completed successfully!")
                
        except Exception as e:
            logger.error(f"Failed to create risk profiles: {e}")
            raise CommandError(f"Command failed: {e}")
    
    def _clear_existing_profiles(self) -> None:
        """Clear existing risk profiles if force flag is used."""
        self._log_info("Clearing existing risk profiles...")
        
        config_count = RiskProfileCheckConfig.objects.count()
        profile_count = RiskProfile.objects.count()
        
        RiskProfileCheckConfig.objects.all().delete()
        RiskProfile.objects.all().delete()
        
        self._log_info(f"Deleted {profile_count} profiles and {config_count} configurations")
    
    def _create_risk_profiles(self, profile_filter: str = None) -> int:
        """Create risk profiles."""
        self._log_info("Creating risk profiles...")
        
        profiles_data = self._get_risk_profiles_data()
        
        # Filter by profile if specified
        if profile_filter:
            profiles_data = [
                profile for profile in profiles_data 
                if profile['name'].lower() == profile_filter.lower()
            ]
        
        profiles_created = 0
        
        for profile_data in profiles_data:
            profile, created = RiskProfile.objects.get_or_create(
                name=profile_data['name'],
                defaults=profile_data
            )
            
            if created:
                profiles_created += 1
                self._log_info(f"Created risk profile: {profile.name}")
            else:
                self._log_info(f"Risk profile already exists: {profile.name}")
        
        return profiles_created
    
    def _configure_profile_checks(self) -> int:
        """Configure risk checks for each profile."""
        self._log_info("Configuring profile check settings...")
        
        configs_created = 0
        
        for profile in RiskProfile.objects.all():
            profile_configs = self._get_profile_check_configs(profile.name)
            
            for check_name, config in profile_configs.items():
                try:
                    check_type = RiskCheckType.objects.get(name=check_name)
                    
                    profile_config, created = RiskProfileCheckConfig.objects.get_or_create(
                        risk_profile=profile,
                        check_type=check_type,
                        defaults=config
                    )
                    
                    if created:
                        configs_created += 1
                        self._log_info(f"Configured {check_name} for {profile.name}")
                        
                except RiskCheckType.DoesNotExist:
                    logger.warning(f"Risk check '{check_name}' not found, skipping configuration")
                    continue
        
        return configs_created
    
    def _get_risk_profiles_data(self) -> List[Dict]:
        """Get risk profile configuration data."""
        return [
            {
                'name': 'Conservative',
                'description': 'Low-risk profile with strict safety requirements and minimal exposure',
                'max_risk_score': Decimal('30.0'),
                'min_confidence_score': Decimal('85.0'),
                'liquidity_threshold_usd': Decimal('100000.0'),
                'max_holder_concentration_percent': Decimal('15.0'),
                'max_buy_tax_percent': Decimal('2.0'),
                'max_sell_tax_percent': Decimal('2.0'),
                'is_active': True,
                'config': {
                    'max_position_size_eth': '0.05',
                    'require_verified_contract': True,
                    'require_doxxed_team': False,
                    'min_liquidity_lock_days': 90,
                    'max_whale_concentration': 10.0,
                    'enable_social_checks': True
                }
            },
            {
                'name': 'Moderate',
                'description': 'Balanced risk profile suitable for most trading scenarios',
                'max_risk_score': Decimal('60.0'),
                'min_confidence_score': Decimal('70.0'),
                'liquidity_threshold_usd': Decimal('50000.0'),
                'max_holder_concentration_percent': Decimal('25.0'),
                'max_buy_tax_percent': Decimal('5.0'),
                'max_sell_tax_percent': Decimal('5.0'),
                'is_active': True,
                'config': {
                    'max_position_size_eth': '0.1',
                    'require_verified_contract': False,
                    'require_doxxed_team': False,
                    'min_liquidity_lock_days': 30,
                    'max_whale_concentration': 20.0,
                    'enable_social_checks': True
                }
            },
            {
                'name': 'Aggressive',
                'description': 'High-risk profile for experienced traders seeking higher returns',
                'max_risk_score': Decimal('80.0'),
                'min_confidence_score': Decimal('60.0'),
                'liquidity_threshold_usd': Decimal('25000.0'),
                'max_holder_concentration_percent': Decimal('35.0'),
                'max_buy_tax_percent': Decimal('8.0'),
                'max_sell_tax_percent': Decimal('8.0'),
                'is_active': True,
                'config': {
                    'max_position_size_eth': '0.2',
                    'require_verified_contract': False,
                    'require_doxxed_team': False,
                    'min_liquidity_lock_days': 7,
                    'max_whale_concentration': 30.0,
                    'enable_social_checks': False
                }
            },
            {
                'name': 'Experimental',
                'description': 'Experimental profile for testing new strategies (paper trading only)',
                'max_risk_score': Decimal('95.0'),
                'min_confidence_score': Decimal('50.0'),
                'liquidity_threshold_usd': Decimal('10000.0'),
                'max_holder_concentration_percent': Decimal('50.0'),
                'max_buy_tax_percent': Decimal('15.0'),
                'max_sell_tax_percent': Decimal('15.0'),
                'is_active': False,
                'config': {
                    'max_position_size_eth': '0.01',
                    'require_verified_contract': False,
                    'require_doxxed_team': False,
                    'min_liquidity_lock_days': 0,
                    'max_whale_concentration': 50.0,
                    'enable_social_checks': False,
                    'paper_trading_only': True
                }
            }
        ]
    
    def _get_profile_check_configs(self, profile_name: str) -> Dict[str, Dict]:
        """Get check configurations for a specific profile."""
        
        base_configs = {
            'Conservative': {
                # Critical blocking checks - enabled with high weights
                'Honeypot Detection': {
                    'is_enabled': True,
                    'is_blocking': True,
                    'weight': Decimal('10.0'),
                    'timeout_seconds': 20
                },
                'Ownership Renounced Check': {
                    'is_enabled': True,
                    'is_blocking': True,
                    'weight': Decimal('8.0')
                },
                'LP Lock Verification': {
                    'is_enabled': True,
                    'is_blocking': True,
                    'weight': Decimal('9.0')
                },
                
                # High priority checks
                'Buy Tax Analysis': {
                    'is_enabled': True,
                    'is_blocking': False,
                    'weight': Decimal('4.0')
                },
                'Sell Tax Analysis': {
                    'is_enabled': True,
                    'is_blocking': False,
                    'weight': Decimal('5.0')
                },
                'Admin Function Analysis': {
                    'is_enabled': True,
                    'is_blocking': False,
                    'weight': Decimal('5.0')
                },
                
                # Medium priority checks
                'Holder Concentration Check': {
                    'is_enabled': True,
                    'is_blocking': False,
                    'weight': Decimal('3.0')
                },
                'Liquidity Depth Analysis': {
                    'is_enabled': True,
                    'is_blocking': False,
                    'weight': Decimal('2.5')
                },
                'Contract Verification Check': {
                    'is_enabled': True,
                    'is_blocking': False,
                    'weight': Decimal('2.0')
                },
                
                # Low priority checks
                'Social Media Presence': {
                    'is_enabled': True,
                    'is_blocking': False,
                    'weight': Decimal('1.0')
                }
            },
            
            'Moderate': {
                # Critical blocking checks
                'Honeypot Detection': {
                    'is_enabled': True,
                    'is_blocking': True,
                    'weight': Decimal('10.0')
                },
                'Ownership Renounced Check': {
                    'is_enabled': True,
                    'is_blocking': True,
                    'weight': Decimal('6.0')
                },
                'LP Lock Verification': {
                    'is_enabled': True,
                    'is_blocking': True,
                    'weight': Decimal('7.0')
                },
                
                # High priority checks
                'Buy Tax Analysis': {
                    'is_enabled': True,
                    'is_blocking': False,
                    'weight': Decimal('3.0')
                },
                'Sell Tax Analysis': {
                    'is_enabled': True,
                    'is_blocking': False,
                    'weight': Decimal('4.0')
                },
                'Admin Function Analysis': {
                    'is_enabled': True,
                    'is_blocking': False,
                    'weight': Decimal('3.0')
                },
                
                # Medium priority checks
                'Holder Concentration Check': {
                    'is_enabled': True,
                    'is_blocking': False,
                    'weight': Decimal('2.0')
                },
                'Liquidity Depth Analysis': {
                    'is_enabled': True,
                    'is_blocking': False,
                    'weight': Decimal('2.0')
                }
            },
            
            'Aggressive': {
                # Only critical blocking checks
                'Honeypot Detection': {
                    'is_enabled': True,
                    'is_blocking': True,
                    'weight': Decimal('10.0'),
                    'timeout_seconds': 10  # Faster timeout
                },
                'LP Lock Verification': {
                    'is_enabled': True,
                    'is_blocking': True,
                    'weight': Decimal('5.0')
                },
                
                # Reduced weight checks
                'Buy Tax Analysis': {
                    'is_enabled': True,
                    'is_blocking': False,
                    'weight': Decimal('2.0')
                },
                'Sell Tax Analysis': {
                    'is_enabled': True,
                    'is_blocking': False,
                    'weight': Decimal('2.0')
                },
                'Holder Concentration Check': {
                    'is_enabled': True,
                    'is_blocking': False,
                    'weight': Decimal('1.0')
                }
            },
            
            'Experimental': {
                # Minimal checks for testing
                'Honeypot Detection': {
                    'is_enabled': True,
                    'is_blocking': True,
                    'weight': Decimal('10.0'),
                    'timeout_seconds': 5
                },
                'Buy Tax Analysis': {
                    'is_enabled': True,
                    'is_blocking': False,
                    'weight': Decimal('1.0')
                }
            }
        }
        
        return base_configs.get(profile_name, {})    def _log_success(self, message: str) -> None:
        """Log success message."""
        if self.verbosity >= 1:
            self.stdout.write(self.style.SUCCESS(message))
        logger.info(message)