"""
Fix PaperPosition unique constraint to only apply to open positions.

This allows multiple closed positions for the same token while preventing
duplicate open positions.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('paper_trading', '0002_alter_papertradingaccount_current_balance_usd_and_more'),
    ]

    operations = [
        # Remove the old unique_together constraint
        migrations.AlterUniqueTogether(
            name='paperposition',
            unique_together=set(),
        ),
        
        # Add a partial unique constraint (only for open positions)
        migrations.AddConstraint(
            model_name='paperposition',
            constraint=models.UniqueConstraint(
                fields=['account', 'token_address'],
                condition=models.Q(is_open=True),
                name='unique_open_position_per_token'
            ),
        ),
    ]