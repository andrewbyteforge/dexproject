# Generated migration for adding max_hold_hours to PaperStrategyConfiguration
# File: paper_trading/migrations/0009_add_max_hold_hours_to_strategy_config.py

from django.db import migrations, models
import django.core.validators
from decimal import Decimal


class Migration(migrations.Migration):
    """
    Add max_hold_hours field to PaperStrategyConfiguration.
    
    This migration adds a configurable maximum hold time field that controls
    how long positions can be held before automatic closure.
    """

    dependencies = [
        ('paper_trading', '0008_remove_paperstrategyconfiguration_paper_strat_intel_l_idx'),
    ]

    operations = [
        migrations.AddField(
            model_name='paperstrategyconfiguration',
            name='max_hold_hours',
            field=models.IntegerField(
                default=72,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(720)  # 30 days max
                ],
                help_text='Maximum hours to hold a position before auto-close (1-720 hours)'
            ),
        ),
    ]