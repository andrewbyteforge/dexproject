"""
Strategy Models - Phase 7B Advanced Strategies

Database models for tracking automated trading strategies (DCA, Grid, TWAP, VWAP, Custom).
Includes strategy execution tracking, performance metrics, and order linkage.

Phase 7B - Advanced Strategies

File: dexproject/paper_trading/models/strategies.py
"""

import uuid
import logging
from decimal import Decimal
from typing import Optional, Dict, Any

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone

from paper_trading.constants import (
    StrategyType,
    StrategyStatus,
    StrategyRunFields,
    StrategyOrderFields,
    validate_strategy_type,
    validate_strategy_status,
)


logger = logging.getLogger(__name__)


# =============================================================================
# STRATEGY RUN MODEL
# =============================================================================

class StrategyRun(models.Model):
    """
    Tracks execution of automated trading strategies.
    
    Stores strategy configuration, execution status, performance metrics,
    and timing information for DCA, Grid, TWAP, VWAP, and Custom strategies.
    
    Each StrategyRun represents one execution of a strategy with specific
    configuration parameters. Strategies can be started, paused, resumed,
    cancelled, or may complete/fail.
    
    Relationships:
    - Belongs to PaperTradingAccount
    - Has many StrategyOrder (links to individual orders)
    
    Example:
        # Create DCA strategy
        strategy = StrategyRun.objects.create(
            account=account,
            strategy_type=StrategyType.DCA,
            config={
                'total_amount_usd': '1000.00',
                'interval_hours': 24,
                'num_intervals': 10,
                'token_address': '0x...',
                'token_symbol': 'ETH',
            },
            total_orders=10,
        )
    """
    
    # =========================================================================
    # IDENTITY FIELDS
    # =========================================================================
    
    strategy_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for this strategy run"
    )
    
    account = models.ForeignKey(
        'paper_trading.PaperTradingAccount',
        on_delete=models.CASCADE,
        related_name='strategy_runs',
        help_text="Account executing this strategy"
    )
    
    strategy_type = models.CharField(
        max_length=20,
        choices=[
            (StrategyType.DCA, 'Dollar Cost Averaging'),
            (StrategyType.GRID, 'Grid Trading'),
            (StrategyType.TWAP, 'Time-Weighted Average Price'),
            (StrategyType.VWAP, 'Volume-Weighted Average Price'),
            (StrategyType.CUSTOM, 'Custom Strategy'),
        ],
        help_text="Type of trading strategy"
    )
    
    # =========================================================================
    # CONFIGURATION
    # =========================================================================
    
    config = models.JSONField(
        default=dict,
        help_text="Strategy-specific configuration parameters"
    )
    
    # =========================================================================
    # EXECUTION STATUS
    # =========================================================================
    
    status = models.CharField(
        max_length=20,
        choices=[
            (StrategyStatus.PENDING, 'Pending'),
            (StrategyStatus.RUNNING, 'Running'),
            (StrategyStatus.PAUSED, 'Paused'),
            (StrategyStatus.COMPLETED, 'Completed'),
            (StrategyStatus.CANCELLED, 'Cancelled'),
            (StrategyStatus.FAILED, 'Failed'),
        ],
        default=StrategyStatus.PENDING,
        help_text="Current execution status"
    )
    
    progress_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Completion percentage (0-100)"
    )
    
    current_step = models.CharField(
        max_length=200,
        blank=True,
        default='',
        help_text="Current execution step description"
    )
    
    # =========================================================================
    # PERFORMANCE TRACKING
    # =========================================================================
    
    total_orders = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Total number of orders planned"
    )
    
    completed_orders = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Number of successfully completed orders"
    )
    
    failed_orders = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Number of failed orders"
    )
    
    total_invested = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text="Total USD amount invested so far"
    )
    
    average_entry = models.DecimalField(
        max_digits=30,
        decimal_places=18,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text="Average entry price across all orders"
    )
    
    current_pnl = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Current profit/loss in USD"
    )
    
    # =========================================================================
    # TIMING FIELDS
    # =========================================================================
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When strategy was created"
    )
    
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When strategy execution started"
    )
    
    paused_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When strategy was paused"
    )
    
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When strategy completed successfully"
    )
    
    cancelled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When strategy was cancelled"
    )
    
    # =========================================================================
    # METADATA
    # =========================================================================
    
    notes = models.TextField(
        blank=True,
        default='',
        help_text="User notes about this strategy"
    )
    
    error_message = models.TextField(
        blank=True,
        default='',
        help_text="Error message if strategy failed"
    )
    
    # =========================================================================
    # MODEL METHODS
    # =========================================================================
    
    def is_active(self) -> bool:
        """
        Check if strategy is currently active.
        
        Returns:
            True if strategy is running, False otherwise
        """
        return self.status in StrategyStatus.ACTIVE
    
    def is_terminal(self) -> bool:
        """
        Check if strategy has finished execution.
        
        Returns:
            True if strategy is in terminal state (completed/cancelled/failed)
        """
        return self.status in StrategyStatus.TERMINAL
    
    def can_pause(self) -> bool:
        """
        Check if strategy can be paused.
        
        Returns:
            True if strategy is running and can be paused
        """
        return self.status == StrategyStatus.RUNNING
    
    def can_resume(self) -> bool:
        """
        Check if strategy can be resumed.
        
        Returns:
            True if strategy is paused and can be resumed
        """
        return self.status == StrategyStatus.PAUSED
    
    def can_cancel(self) -> bool:
        """
        Check if strategy can be cancelled.
        
        Returns:
            True if strategy is running or paused
        """
        return self.status in [StrategyStatus.RUNNING, StrategyStatus.PAUSED, StrategyStatus.PENDING]
    
    def calculate_performance(self) -> Dict[str, Any]:
        """
        Calculate strategy performance metrics.
        
        Returns:
            Dictionary with performance metrics:
            - completion_rate: Percentage of orders completed
            - failure_rate: Percentage of orders failed
            - avg_entry_price: Average entry price
            - total_invested: Total amount invested
            - current_pnl: Current profit/loss
            - pnl_percent: P&L as percentage of invested amount
        """
        completion_rate = Decimal('0.00')
        failure_rate = Decimal('0.00')
        pnl_percent = Decimal('0.00')
        
        if self.total_orders > 0:
            completion_rate = (Decimal(str(self.completed_orders)) / Decimal(str(self.total_orders))) * Decimal('100')
            failure_rate = (Decimal(str(self.failed_orders)) / Decimal(str(self.total_orders))) * Decimal('100')
        
        if self.total_invested > 0:
            pnl_percent = (self.current_pnl / self.total_invested) * Decimal('100')
        
        return {
            'completion_rate': completion_rate,
            'failure_rate': failure_rate,
            'avg_entry_price': self.average_entry,
            'total_invested': self.total_invested,
            'current_pnl': self.current_pnl,
            'pnl_percent': pnl_percent,
        }
    
    def update_performance(self) -> None:
        """
        Update performance metrics based on linked orders.
        
        Recalculates:
        - completed_orders count
        - failed_orders count
        - total_invested amount
        - average_entry price
        - current_pnl
        """
        from paper_trading.constants import OrderStatus
        
        # Get all orders for this strategy
        strategy_orders = self.strategy_orders.select_related('order')
        
        completed_count = 0
        failed_count = 0
        total_invested = Decimal('0.00')
        total_tokens = Decimal('0.00')
        
        for strategy_order in strategy_orders:
            order = strategy_order.order
            
            if order.status == OrderStatus.FILLED:
                completed_count += 1
                total_invested += order.filled_amount_usd
                total_tokens += order.filled_amount_token
            elif order.status == OrderStatus.FAILED:
                failed_count += 1
        
        # Calculate average entry price
        avg_entry = Decimal('0.00')
        if total_tokens > 0:
            avg_entry = total_invested / total_tokens
        
        # Update fields
        self.completed_orders = completed_count
        self.failed_orders = failed_count
        self.total_invested = total_invested
        self.average_entry = avg_entry
        
        # Calculate P&L (simplified - would need current price in production)
        # For now, just set to 0 - will be updated by strategy logic
        
        self.save()
        
        logger.info(
            f"Updated performance for strategy {self.strategy_id}: "
            f"{completed_count} completed, {failed_count} failed, "
            f"${total_invested} invested"
        )
    
    def clean(self) -> None:
        """Validate model fields before saving."""
        super().clean()
        
        # Validate strategy type
        if not validate_strategy_type(self.strategy_type):
            from django.core.exceptions import ValidationError
            raise ValidationError(f"Invalid strategy type: {self.strategy_type}")
        
        # Validate status
        if not validate_strategy_status(self.status):
            from django.core.exceptions import ValidationError
            raise ValidationError(f"Invalid strategy status: {self.status}")
    
    class Meta:
        """Meta configuration."""
        db_table = 'paper_strategy_runs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['account', 'status']),
            models.Index(fields=['strategy_type', 'status']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['account', 'strategy_type']),
        ]
        verbose_name = 'Strategy Run'
        verbose_name_plural = 'Strategy Runs'
    
    def __str__(self) -> str:
        """String representation."""
        return f"{self.get_strategy_type_display()} - {self.status} ({self.progress_percent}%)"


# =============================================================================
# STRATEGY ORDER MODEL
# =============================================================================

class StrategyOrder(models.Model):
    """
    Links orders to strategy runs for tracking.
    
    This junction model connects individual PaperOrder instances to their
    parent StrategyRun, allowing us to track which orders belong to which
    strategy and in what sequence they were created.
    
    Relationships:
    - Belongs to StrategyRun
    - Belongs to PaperOrder
    
    Example:
        # Link order to strategy
        StrategyOrder.objects.create(
            strategy_run=strategy,
            order=order,
            order_sequence=1,
        )
    """
    
    id = models.BigAutoField(
        primary_key=True,
        help_text="Auto-incrementing ID"
    )
    
    strategy_run = models.ForeignKey(
        'StrategyRun',
        on_delete=models.CASCADE,
        related_name='strategy_orders',
        help_text="Strategy this order belongs to"
    )
    
    order = models.ForeignKey(
        'paper_trading.PaperOrder',
        on_delete=models.CASCADE,
        related_name='strategy_links',
        help_text="The actual order"
    )
    
    order_sequence = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text="Order sequence number within strategy (1, 2, 3...)"
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this link was created"
    )
    
    class Meta:
        """Meta configuration."""
        db_table = 'paper_strategy_orders'
        ordering = ['order_sequence']
        indexes = [
            models.Index(fields=['strategy_run', 'order_sequence']),
            models.Index(fields=['order', 'created_at']),
        ]
        unique_together = [
            ('strategy_run', 'order_sequence'),
            ('strategy_run', 'order'),
        ]
        verbose_name = 'Strategy Order'
        verbose_name_plural = 'Strategy Orders'
    
    def __str__(self) -> str:
        """String representation."""
        return f"Order #{self.order_sequence} for {self.strategy_run.strategy_type}"