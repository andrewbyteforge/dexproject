# Generated migration for FundAllocation model
# File: dashboard/migrations/0006_fundallocation.py

from django.conf import settings
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion
import uuid
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('dashboard', '0005_rename_dashboard_b_risk_to_idx_dashboard_b_risk_to_5d4eeb_idx_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='FundAllocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('allocation_id', models.UUIDField(default=uuid.uuid4, help_text='Unique allocation identifier', unique=True)),
                ('allocation_method', models.CharField(
                    choices=[
                        ('PERCENTAGE', 'Percentage Based'),
                        ('FIXED', 'Fixed Amount')
                    ],
                    default='PERCENTAGE',
                    help_text='Method for determining trading allocation',
                    max_length=20
                )),
                ('allocation_percentage', models.DecimalField(
                    decimal_places=2,
                    default=Decimal('10.00'),
                    help_text='Percentage of balance to allocate for trading',
                    max_digits=5,
                    validators=[
                        django.core.validators.MinValueValidator(Decimal('1.00')),
                        django.core.validators.MaxValueValidator(Decimal('50.00'))
                    ]
                )),
                ('allocation_fixed_amount', models.DecimalField(
                    decimal_places=8,
                    default=Decimal('0.10000000'),
                    help_text='Fixed amount in ETH to allocate for trading',
                    max_digits=18,
                    validators=[
                        django.core.validators.MinValueValidator(Decimal('0.00100000'))
                    ]
                )),
                ('daily_spending_limit', models.DecimalField(
                    decimal_places=8,
                    default=Decimal('1.00000000'),
                    help_text='Maximum daily spending limit in ETH',
                    max_digits=18,
                    validators=[
                        django.core.validators.MinValueValidator(Decimal('0.01000000'))
                    ]
                )),
                ('minimum_balance_reserve', models.DecimalField(
                    decimal_places=8,
                    default=Decimal('0.05000000'),
                    help_text='Minimum balance to keep in reserve (ETH)',
                    max_digits=18,
                    validators=[
                        django.core.validators.MinValueValidator(Decimal('0.00100000'))
                    ]
                )),
                ('auto_rebalance_enabled', models.BooleanField(
                    default=True,
                    help_text='Automatically rebalance allocation when wallet balance changes'
                )),
                ('stop_loss_enabled', models.BooleanField(
                    default=True,
                    help_text='Enable stop-loss protection'
                )),
                ('stop_loss_percentage', models.DecimalField(
                    decimal_places=2,
                    default=Decimal('5.00'),
                    help_text='Stop-loss percentage threshold',
                    max_digits=5,
                    validators=[
                        django.core.validators.MinValueValidator(Decimal('1.00')),
                        django.core.validators.MaxValueValidator(Decimal('25.00'))
                    ]
                )),
                ('is_active', models.BooleanField(
                    default=True,
                    help_text='Whether this allocation is currently active'
                )),
                ('created_at', models.DateTimeField(
                    auto_now_add=True,
                    help_text='When this allocation was created'
                )),
                ('updated_at', models.DateTimeField(
                    auto_now=True,
                    help_text='When this allocation was last updated'
                )),
                ('user', models.OneToOneField(
                    help_text='User this allocation belongs to',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='fund_allocation',
                    to=settings.AUTH_USER_MODEL
                )),
            ],
            options={
                'ordering': ['-updated_at'],
                'verbose_name': 'Fund Allocation',
                'verbose_name_plural': 'Fund Allocations',
            },
        ),
        migrations.AddIndex(
            model_name='fundallocation',
            index=models.Index(fields=['allocation_id'], name='dashboard_f_allocat_d5c3a2_idx'),
        ),
        migrations.AddIndex(
            model_name='fundallocation',
            index=models.Index(fields=['user'], name='dashboard_f_user_id_e8f1b4_idx'),
        ),
        migrations.AddIndex(
            model_name='fundallocation',
            index=models.Index(fields=['allocation_method'], name='dashboard_f_allocat_7a9b2c_idx'),
        ),
        migrations.AddIndex(
            model_name='fundallocation',
            index=models.Index(fields=['is_active'], name='dashboard_f_is_acti_4d5e6f_idx'),
        ),
        migrations.AddIndex(
            model_name='fundallocation',
            index=models.Index(fields=['created_at'], name='dashboard_f_created_8c9d1e_idx'),
        ),
        migrations.AddIndex(
            model_name='fundallocation',
            index=models.Index(fields=['updated_at'], name='dashboard_f_updated_f2a3b4_idx'),
        ),
    ]