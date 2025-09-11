"""
Django management command to create default trading strategies.

This command creates foundational trading strategies that align with
different risk profiles and trading approaches.
"""

import logging
from decimal import Decimal
from typing import Dict, List

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ...models import Strategy


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Management command to create default trading strategies."""
    
    help = 'Create default trading strategies for the DEX auto-trading bot'
    
    def add_arguments(self, parser) -> None:
        """Add command line arguments."""
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recreation of existing strategies (will delete existing)',
        )
        parser.add_argument(
            '--strategy',
            type=str,
            help='Only create specific strategy',
            choices=['conservative_sniper', 'balanced_trader', 'aggressive_growth', 'scalp_hunter']
        )
    
    def handle(self, *args, **options) -> None:
        """Execute the command."""
        self.verbosity = options.get('verbosity', 1)
        force = options.get('force', False)
        strategy_filter = options.get('strategy')
        
        try:
            with transaction.atomic():
                if force:
                    self._clear_existing_strategies()
                
                strategies_created = self._create_strategies(strategy_filter)
                self._log_success(f"Created {strategies_created} trading strategies")
                
                self._log_success("Default strategies creation completed successfully!")
                
        except Exception as e:
            logger.error(f"Failed to create strategies: {e}")
            raise CommandError(f"Command failed: {e}")
    
    def _clear_existing_strategies(self) -> None:
        """Clear existing strategies if force flag is used."""
        self._log_info("Clearing existing strategies...")
        
        strategy_count = Strategy.objects.count()
        Strategy.objects.all().delete()
        
        self._log_info(f"Deleted {strategy_count} strategies")
    
    def _create_strategies(self, strategy_filter: str = None) -> int:
        """Create trading strategies."""
        self._log_info("Creating trading strategies...")
        
        strategies_data = self._get_strategies_data()
        
        # Filter by strategy if specified
        if strategy_filter:
            strategies_data = [
                strategy for strategy in strategies_data 
                if strategy['name'].lower().replace(' ', '_') == strategy_filter.lower()
            ]
        
        strategies_created = 0
        
        for strategy_data in strategies_data:
            strategy, created = Strategy.objects.get_or_create(
                name=strategy_data['name'],
                defaults=strategy_data
            )
            
            if created:
                strategies_created += 1
                active_text = " (ACTIVE)" if strategy.is_active else " (INACTIVE)"
                self._log_info(f"Created strategy: {strategy.name}{active_text}")
            else:
                self._log_info(f"Strategy already exists: {strategy.name}")
        
        return strategies_created
    
    def _get_strategies_data(self) -> List[Dict]:
        """Get trading strategy configuration data."""
        return [
            {
                'name': 'Conservative Sniper',
                'description': 'Low-risk strategy focusing on high-confidence opportunities with strict safety requirements. Targets established tokens with strong fundamentals.',
                'is_active': True,
                'max_position_size_eth': Decimal('0.05'),
                'max_slippage_percent': Decimal('1.5'),
                'max_gas_price_gwei': Decimal('40.0'),
                'min_liquidity_usd': Decimal('100000.0'),
                'max_buy_tax_percent': Decimal('2.0'),
                'max_sell_tax_percent': Decimal('2.0'),
                'take_profit_percent': Decimal('25.0'),
                'stop_loss_percent': Decimal('15.0'),
                'config': {
                    'entry_strategy': 'conservative',
                    'min_confidence_score': 85.0,
                    'max_risk_score': 30.0,
                    'position_sizing': 'fixed_small',
                    'exit_strategy': 'gradual_profit_taking',
                    'profit_taking_levels': [15.0, 25.0, 40.0],
                    'profit_taking_percentages': [30.0, 50.0, 20.0],
                    'trailing_stop_loss': True,
                    'trailing_stop_activation': 10.0,
                    'trailing_stop_distance': 8.0,
                    'max_holding_time_hours': 48,
                    'emergency_exit_conditions': {
                        'max_drawdown_percent': 12.0,
                        'volume_drop_threshold': 70.0,
                        'liquidity_drop_threshold': 50.0
                    },
                    'entry_filters': {
                        'require_verified_contract': True,
                        'min_holder_count': 200,
                        'max_whale_concentration': 15.0,
                        'require_locked_liquidity': True,
                        'min_lock_duration_days': 90
                    }
                }
            },
            {
                'name': 'Balanced Trader',
                'description': 'Well-rounded strategy balancing risk and reward. Suitable for most market conditions with moderate position sizes.',
                'is_active': True,
                'max_position_size_eth': Decimal('0.1'),
                'max_slippage_percent': Decimal('2.5'),
                'max_gas_price_gwei': Decimal('60.0'),
                'min_liquidity_usd': Decimal('50000.0'),
                'max_buy_tax_percent': Decimal('5.0'),
                'max_sell_tax_percent': Decimal('5.0'),
                'take_profit_percent': Decimal('50.0'),
                'stop_loss_percent': Decimal('20.0'),
                'config': {
                    'entry_strategy': 'balanced',
                    'min_confidence_score': 70.0,
                    'max_risk_score': 60.0,
                    'position_sizing': 'risk_adjusted',
                    'exit_strategy': 'dynamic_targets',
                    'profit_taking_levels': [25.0, 50.0, 100.0],
                    'profit_taking_percentages': [25.0, 50.0, 25.0],
                    'trailing_stop_loss': True,
                    'trailing_stop_activation': 15.0,
                    'trailing_stop_distance': 12.0,
                    'max_holding_time_hours': 72,
                    'emergency_exit_conditions': {
                        'max_drawdown_percent': 18.0,
                        'volume_drop_threshold': 60.0,
                        'liquidity_drop_threshold': 40.0
                    },
                    'entry_filters': {
                        'require_verified_contract': False,
                        'min_holder_count': 100,
                        'max_whale_concentration': 25.0,
                        'require_locked_liquidity': True,
                        'min_lock_duration_days': 30
                    },
                    'momentum_filters': {
                        'check_price_momentum': True,
                        'min_volume_increase': 2.0,
                        'max_recent_pump': 200.0
                    }
                }
            },
            {
                'name': 'Aggressive Growth',
                'description': 'High-risk, high-reward strategy targeting early opportunities with larger position sizes. For experienced traders only.',
                'is_active': True,
                'max_position_size_eth': Decimal('0.25'),
                'max_slippage_percent': Decimal('5.0'),
                'max_gas_price_gwei': Decimal('100.0'),
                'min_liquidity_usd': Decimal('25000.0'),
                'max_buy_tax_percent': Decimal('8.0'),
                'max_sell_tax_percent': Decimal('8.0'),
                'take_profit_percent': Decimal('100.0'),
                'stop_loss_percent': Decimal('25.0'),
                'config': {
                    'entry_strategy': 'aggressive',
                    'min_confidence_score': 60.0,
                    'max_risk_score': 80.0,
                    'position_sizing': 'momentum_based',
                    'exit_strategy': 'momentum_following',
                    'profit_taking_levels': [50.0, 100.0, 200.0, 500.0],
                    'profit_taking_percentages': [20.0, 30.0, 30.0, 20.0],
                    'trailing_stop_loss': True,
                    'trailing_stop_activation': 20.0,
                    'trailing_stop_distance': 15.0,
                    'max_holding_time_hours': 24,
                    'emergency_exit_conditions': {
                        'max_drawdown_percent': 22.0,
                        'volume_drop_threshold': 50.0,
                        'liquidity_drop_threshold': 30.0
                    },
                    'entry_filters': {
                        'require_verified_contract': False,
                        'min_holder_count': 50,
                        'max_whale_concentration': 35.0,
                        'require_locked_liquidity': True,
                        'min_lock_duration_days': 7
                    },
                    'momentum_filters': {
                        'check_price_momentum': True,
                        'min_volume_increase': 5.0,
                        'early_entry_bonus': True,
                        'social_momentum_weight': 0.3
                    },
                    'advanced_features': {
                        'copy_trading_detection': True,
                        'whale_tracking': True,
                        'smart_money_following': True
                    }
                }
            },
            {
                'name': 'Scalp Hunter',
                'description': 'Ultra-fast scalping strategy for quick profits on high-volatility opportunities. Requires excellent execution speed.',
                'is_active': False,  # Requires advanced execution engine
                'max_position_size_eth': Decimal('0.5'),
                'max_slippage_percent': Decimal('3.0'),
                'max_gas_price_gwei': Decimal('150.0'),
                'min_liquidity_usd': Decimal('75000.0'),
                'max_buy_tax_percent': Decimal('5.0'),
                'max_sell_tax_percent': Decimal('5.0'),
                'take_profit_percent': Decimal('15.0'),
                'stop_loss_percent': Decimal('8.0'),
                'config': {
                    'entry_strategy': 'scalping',
                    'min_confidence_score': 65.0,
                    'max_risk_score': 70.0,
                    'position_sizing': 'volatility_adjusted',
                    'exit_strategy': 'quick_scalp',
                    'profit_taking_levels': [8.0, 15.0, 25.0],
                    'profit_taking_percentages': [60.0, 30.0, 10.0],
                    'trailing_stop_loss': False,
                    'fixed_stop_loss': True,
                    'max_holding_time_minutes': 30,
                    'target_holding_time_minutes': 5,
                    'emergency_exit_conditions': {
                        'max_drawdown_percent': 6.0,
                        'volume_drop_threshold': 40.0,
                        'momentum_loss_threshold': 2.0
                    },
                    'entry_filters': {
                        'require_high_volatility': True,
                        'min_price_change_5min': 5.0,
                        'max_market_cap_millions': 50.0,
                        'require_momentum_confirmation': True
                    },
                    'execution_requirements': {
                        'max_execution_latency_ms': 500,
                        'require_private_mempool': True,
                        'gas_optimization': 'aggressive',
                        'mev_protection': True
                    },
                    'scalping_specific': {
                        'min_spread_bps': 10,
                        'max_spread_bps': 100,
                        'volume_confirmation_blocks': 2,
                        'price_action_confirmation': True
                    }
                }
            },
            {
                'name': 'Paper Trading',
                'description': 'Risk-free paper trading strategy for testing and learning. Simulates real trades without actual execution.',
                'is_active': True,
                'max_position_size_eth': Decimal('0.1'),
                'max_slippage_percent': Decimal('2.0'),
                'max_gas_price_gwei': Decimal('50.0'),
                'min_liquidity_usd': Decimal('10000.0'),
                'max_buy_tax_percent': Decimal('10.0'),
                'max_sell_tax_percent': Decimal('10.0'),
                'take_profit_percent': Decimal('30.0'),
                'stop_loss_percent': Decimal('15.0'),
                'config': {
                    'entry_strategy': 'educational',
                    'min_confidence_score': 50.0,
                    'max_risk_score': 90.0,
                    'position_sizing': 'educational',
                    'exit_strategy': 'educational',
                    'paper_trading_only': True,
                    'simulation_mode': True,
                    'educational_features': {
                        'show_reasoning': True,
                        'detailed_analytics': True,
                        'performance_tracking': True,
                        'risk_education': True
                    },
                    'simulation_parameters': {
                        'realistic_slippage': True,
                        'realistic_gas_costs': True,
                        'market_impact_modeling': True,
                        'latency_simulation': True
                    }
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