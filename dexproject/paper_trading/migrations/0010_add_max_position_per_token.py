# Generated migration for adding max_position_size_per_token_percent
# File: paper_trading/migrations/0010_add_max_position_per_token.py

from django.db import migrations, models
import django.core.validators
from decimal import Decimal


class Migration(migrations.Migration):
    """
    Add max_position_size_per_token_percent field to PaperStrategyConfiguration.
    
    This field controls the maximum total position size (across all trades)
    for a single token, preventing over-concentration risk.
    
    Example:
    - If set to 15%, the bot will not buy more of a token if it already
      owns 15% or more of the portfolio in that token
    """

    dependencies = [
        ('paper_trading', '0009_add_max_hold_hours_to_strategy_config'),
    ]

    operations = [
        migrations.AddField(
            model_name='paperstrategyconfiguration',
            name='max_position_size_per_token_percent',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('15.0'),
                max_digits=5,
                validators=[
                    django.core.validators.MinValueValidator(Decimal('1.0')),
                    django.core.validators.MaxValueValidator(Decimal('50.0'))
                ],
                help_text='Maximum total position size per token as % of portfolio (1-50%)'
            ),
        ),
        migrations.AddIndex(
            model_name='paperstrategyconfiguration',
            index=models.Index(
                fields=['max_position_size_per_token_percent'],
                name='paper_strat_max_pos_token_idx'
            ),
        ),
    ]