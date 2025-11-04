# Generated migration to fix decimal field defaults
# This migration updates the PaperTrade model fields to have proper defaults
# that match validation rules, preventing decimal.InvalidOperation errors.
#
# File: paper_trading/migrations/0004_fix_decimal_defaults.py

from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('paper_trading', '0003_add_max_trade_size_usd'),
    ]

    operations = [
        # Fix amount_in_usd: Change default from 0 to 10.00
        migrations.AlterField(
            model_name='papertrade',
            name='amount_in_usd',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('10.00'),
                help_text='Amount in USD',
                max_digits=20
            ),
        ),
        
        # Fix simulated_gas_used: Add missing default
        migrations.AlterField(
            model_name='papertrade',
            name='simulated_gas_used',
            field=models.IntegerField(
                default=21000,
                help_text='Simulated gas units used'
            ),
        ),
        
        # Fix simulated_gas_cost_usd: Change default from 0 to 0.50
        migrations.AlterField(
            model_name='papertrade',
            name='simulated_gas_cost_usd',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0.50'),
                help_text='Simulated gas cost in USD',
                max_digits=10
            ),
        ),
        
        # Fix simulated_slippage_percent: Ensure consistent default of 0.50
        migrations.AlterField(
            model_name='papertrade',
            name='simulated_slippage_percent',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0.50'),
                help_text='Simulated slippage percentage',
                max_digits=5
            ),
        ),
    ]