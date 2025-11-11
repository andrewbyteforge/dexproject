"""
Strategy Executor Service - Central Strategy Management

This service provides centralized execution and management for all trading strategies.
It routes strategy execution to the appropriate strategy class, manages lifecycle
operations (start/pause/resume/cancel), validates configurations, and tracks performance.

Supported Strategies:
- DCA (Dollar Cost Averaging)
- Grid Trading
- TWAP (Time-Weighted Average Price) - Coming Soon
- VWAP (Volume-Weighted Average Price) - Coming Soon
- Custom (User-Defined Rules) - Coming Soon

Key Responsibilities:
- Route strategy requests to correct strategy class
- Validate strategy configurations before execution
- Create and manage StrategyRun database records
- Start/pause/resume/cancel strategies
- Calculate performance metrics
- Send WebSocket notifications
- Integrate with Celery background tasks

Phase 7B - Day 4: Strategy Executor Service

File: dexproject/paper_trading/services/strategy_executor.py
"""

import logging
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

from django.utils import timezone
from django.db import transaction
from django.db.models import Q, Sum, Avg, Count

from paper_trading.models import (
    PaperTradingAccount,
    StrategyRun,
    StrategyOrder,
    PaperOrder,
)
from paper_trading.constants import (
    StrategyType,
    StrategyStatus,
    OrderStatus,
)

# Import strategy classes
from paper_trading.strategies.dca_strategy import DCAStrategy
from paper_trading.strategies.grid_strategy import GridStrategy

# Import Celery tasks
from paper_trading.tasks.strategy_execution import (
    execute_dca_interval,
    execute_grid_strategy,
    monitor_grid_orders,
    send_strategy_notification,
)

# Import WebSocket service for notifications
from paper_trading.services.websocket_service import websocket_service


logger = logging.getLogger(__name__)


# =============================================================================
# STRATEGY EXECUTOR SERVICE CLASS
# =============================================================================

class StrategyExecutor:
    """
    Central service for executing and managing trading strategies.
    
    This service acts as a router and coordinator for all strategy operations.
    It validates configurations, routes to the appropriate strategy class,
    manages strategy lifecycle, and provides performance metrics.
    
    Example usage:
        executor = StrategyExecutor()
        
        # Start a DCA strategy
        strategy_run = executor.start_strategy(
            account=account,
            strategy_type=StrategyType.DCA,
            config={
                'total_amount_usd': '1000.00',
                'interval_hours': 24,
                'num_intervals': 10,
                'token_address': '0x...',
                'token_symbol': 'WETH',
            }
        )
        
        # Pause the strategy
        executor.pause_strategy(strategy_run.strategy_id)
        
        # Resume the strategy
        executor.resume_strategy(strategy_run.strategy_id)
        
        # Get performance metrics
        metrics = executor.calculate_strategy_metrics(strategy_run.strategy_id)
    """
    
    def __init__(self):
        """Initialize the Strategy Executor service."""
        self.strategy_classes = {
            StrategyType.DCA: DCAStrategy,
            StrategyType.GRID: GridStrategy,
            # TWAP, VWAP, CUSTOM will be added in future phases
        }
        
        logger.info("StrategyExecutor initialized with strategy types: %s", 
                   list(self.strategy_classes.keys()))
    
    # =========================================================================
    # STRATEGY EXECUTION
    # =========================================================================
    
    def start_strategy(
        self,
        account: PaperTradingAccount,
        strategy_type: str,
        config: Dict[str, Any],
        notes: Optional[str] = None,
    ) -> StrategyRun:
        """
        Start a new trading strategy.
        
        This method:
        1. Validates the strategy type and configuration
        2. Creates a StrategyRun database record
        3. Routes to the appropriate strategy class for execution
        4. Starts background tasks for strategy monitoring
        5. Sends WebSocket notifications
        
        Args:
            account: Paper trading account to execute strategy on
            strategy_type: Type of strategy (DCA, GRID, TWAP, VWAP, CUSTOM)
            config: Strategy-specific configuration dictionary
            notes: Optional notes about the strategy
        
        Returns:
            StrategyRun instance with status RUNNING
        
        Raises:
            ValueError: If strategy type is invalid or configuration is invalid
            Exception: If strategy initialization fails
            
        Example:
            strategy_run = executor.start_strategy(
                account=account,
                strategy_type=StrategyType.DCA,
                config={
                    'total_amount_usd': '1000.00',
                    'interval_hours': 24,
                    'num_intervals': 10,
                    'token_address': '0x...',
                    'token_symbol': 'WETH',
                }
            )
        """
        logger.info(
            f"Starting {strategy_type} strategy for account {account.name}"
        )
        
        try:
            # Validate strategy type
            if strategy_type not in self.strategy_classes:
                raise ValueError(
                    f"Invalid strategy type: {strategy_type}. "
                    f"Supported types: {list(self.strategy_classes.keys())}"
                )
            
            # Get strategy class
            strategy_class = self.strategy_classes[strategy_type]
            
            # Validate configuration using strategy class
            is_valid, error_message = self._validate_strategy_config(
                strategy_type=strategy_type,
                config=config,
                account=account,
            )
            
            if not is_valid:
                raise ValueError(f"Invalid configuration: {error_message}")
            
            # Create StrategyRun record
            with transaction.atomic():
                strategy_run = StrategyRun.objects.create(
                    account=account,
                    strategy_type=strategy_type,
                    config=config,
                    status=StrategyStatus.PENDING,
                    progress_percent=Decimal('0.00'),
                    notes=notes or '',
                )
                
                logger.info(f"Created StrategyRun {strategy_run.strategy_id}")
            
            # Initialize strategy instance
            strategy_instance = strategy_class(strategy_run=strategy_run)
            
            # Execute the strategy (this schedules background Celery tasks)
            # Note: This should be a synchronous method that schedules async tasks
            try:
                execution_result = strategy_instance.execute()
                
                # Handle both dict and boolean return types
                if isinstance(execution_result, dict):
                    success = execution_result.get('success', False)
                    error_msg = execution_result.get('error', 'Unknown error')
                else:
                    # Boolean return type (legacy)
                    success = bool(execution_result)
                    error_msg = 'Strategy execution returned False'
                
                if not success:
                    logger.error(f"Strategy execution failed: {error_msg}")
                    
                    # Mark as failed
                    strategy_run.status = StrategyStatus.FAILED
                    strategy_run.error_message = error_msg
                    strategy_run.save()
                    
                    raise Exception(f"Strategy execution failed: {error_msg}")
                
                # Update status to RUNNING
                strategy_run.status = StrategyStatus.RUNNING
                strategy_run.started_at = timezone.now()
                strategy_run.save()
                
                logger.info(
                    f"Strategy {strategy_run.strategy_id} started successfully"
                )
                
                # Send WebSocket notification
                self._send_strategy_update(
                    strategy_run=strategy_run,
                    event_type='started',
                )
                
                return strategy_run
                
            except Exception as exec_error:
                logger.exception(f"Error executing strategy: {exec_error}")
                
                # Mark as failed
                strategy_run.status = StrategyStatus.FAILED
                strategy_run.error_message = str(exec_error)
                strategy_run.save()
                
                raise
        
        except Exception as e:
            logger.exception(f"Error starting strategy: {e}")
            raise
    
    def pause_strategy(self, strategy_id: str) -> bool:
        """
        Pause a running strategy.
        
        This stops all scheduled tasks and prevents new orders from being placed.
        Existing orders remain active but no new intervals/levels will be executed.
        
        Args:
            strategy_id: UUID of the StrategyRun to pause
        
        Returns:
            True if paused successfully, False otherwise
        
        Raises:
            ValueError: If strategy is not in a pauseable state
            
        Example:
            success = executor.pause_strategy('uuid-here')
        """
        logger.info(f"Pausing strategy {strategy_id}")
        
        try:
            with transaction.atomic():
                # Lock the strategy run
                strategy_run = StrategyRun.objects.select_for_update().get(
                    strategy_id=strategy_id
                )
                
                # Check if strategy can be paused
                if not strategy_run.can_pause():
                    raise ValueError(
                        f"Cannot pause strategy in status: {strategy_run.status}"
                    )
                
                # Get strategy class
                strategy_class = self.strategy_classes.get(strategy_run.strategy_type)
                
                if not strategy_class:
                    raise ValueError(
                        f"Unknown strategy type: {strategy_run.strategy_type}"
                    )
                
                # Initialize strategy instance
                strategy_instance = strategy_class(strategy_run=strategy_run)
                
                # Call pause method (synchronous)
                pause_result = strategy_instance.pause()
                
                # Handle both dict and boolean return types
                if isinstance(pause_result, dict):
                    success = pause_result.get('success', False)
                    error_msg = pause_result.get('error', 'Unknown error')
                else:
                    success = bool(pause_result)
                    error_msg = 'Pause operation returned False'
                
                if not success:
                    logger.error(f"Strategy pause failed: {error_msg}")
                    return False
                
                # Update status
                strategy_run.status = StrategyStatus.PAUSED
                strategy_run.paused_at = timezone.now()
                strategy_run.save()
                
                logger.info(f"Strategy {strategy_id} paused successfully")
                
                # Send notification
                self._send_strategy_update(
                    strategy_run=strategy_run,
                    event_type='paused',
                )
                
                return True
        
        except StrategyRun.DoesNotExist:
            logger.error(f"Strategy {strategy_id} not found")
            raise ValueError(f"Strategy {strategy_id} not found")
        
        except Exception as e:
            logger.exception(f"Error pausing strategy: {e}")
            raise
    
    def resume_strategy(self, strategy_id: str) -> bool:
        """
        Resume a paused strategy.
        
        This restarts scheduled tasks and allows new orders to be placed.
        The strategy continues from where it was paused.
        
        Args:
            strategy_id: UUID of the StrategyRun to resume
        
        Returns:
            True if resumed successfully, False otherwise
        
        Raises:
            ValueError: If strategy is not in a resumeable state
            
        Example:
            success = executor.resume_strategy('uuid-here')
        """
        logger.info(f"Resuming strategy {strategy_id}")
        
        try:
            with transaction.atomic():
                # Lock the strategy run
                strategy_run = StrategyRun.objects.select_for_update().get(
                    strategy_id=strategy_id
                )
                
                # Check if strategy can be resumed
                if not strategy_run.can_resume():
                    raise ValueError(
                        f"Cannot resume strategy in status: {strategy_run.status}"
                    )
                
                # Get strategy class
                strategy_class = self.strategy_classes.get(strategy_run.strategy_type)
                
                if not strategy_class:
                    raise ValueError(
                        f"Unknown strategy type: {strategy_run.strategy_type}"
                    )
                
                # Initialize strategy instance
                strategy_instance = strategy_class(strategy_run=strategy_run)
                
                # Call resume method (synchronous)
                resume_result = strategy_instance.resume()
                
                # Handle both dict and boolean return types
                if isinstance(resume_result, dict):
                    success = resume_result.get('success', False)
                    error_msg = resume_result.get('error', 'Unknown error')
                else:
                    success = bool(resume_result)
                    error_msg = 'Resume operation returned False'
                
                if not success:
                    logger.error(f"Strategy resume failed: {error_msg}")
                    return False
                
                # Update status
                strategy_run.status = StrategyStatus.RUNNING
                strategy_run.paused_at = None
                strategy_run.save()
                
                logger.info(f"Strategy {strategy_id} resumed successfully")
                
                # Send notification
                self._send_strategy_update(
                    strategy_run=strategy_run,
                    event_type='resumed',
                )
                
                return True
        
        except StrategyRun.DoesNotExist:
            logger.error(f"Strategy {strategy_id} not found")
            raise ValueError(f"Strategy {strategy_id} not found")
        
        except Exception as e:
            logger.exception(f"Error resuming strategy: {e}")
            raise
    
    def cancel_strategy(self, strategy_id: str) -> bool:
        """
        Cancel a strategy execution.
        
        This stops all scheduled tasks, cancels pending orders, and marks
        the strategy as CANCELLED. This action cannot be undone.
        
        Args:
            strategy_id: UUID of the StrategyRun to cancel
        
        Returns:
            True if cancelled successfully, False otherwise
        
        Raises:
            ValueError: If strategy cannot be cancelled
            
        Example:
            success = executor.cancel_strategy('uuid-here')
        """
        logger.info(f"Cancelling strategy {strategy_id}")
        
        try:
            with transaction.atomic():
                # Lock the strategy run
                strategy_run = StrategyRun.objects.select_for_update().get(
                    strategy_id=strategy_id
                )
                
                # Check if strategy is already terminal
                if strategy_run.is_terminal():
                    raise ValueError(
                        f"Cannot cancel strategy in terminal status: {strategy_run.status}"
                    )
                
                # Get strategy class
                strategy_class = self.strategy_classes.get(strategy_run.strategy_type)
                
                if not strategy_class:
                    raise ValueError(
                        f"Unknown strategy type: {strategy_run.strategy_type}"
                    )
                
                # Initialize strategy instance
                strategy_instance = strategy_class(strategy_run=strategy_run)
                
                # Call cancel method (synchronous)
                cancel_result = strategy_instance.cancel()
                
                # Handle both dict and boolean return types
                if isinstance(cancel_result, dict):
                    success = cancel_result.get('success', False)
                    error_msg = cancel_result.get('error', 'Unknown error')
                else:
                    success = bool(cancel_result)
                    error_msg = 'Cancel operation returned False'
                
                if not success:
                    logger.error(f"Strategy cancellation failed: {error_msg}")
                    return False
                
                # Cancel all pending orders
                pending_orders = PaperOrder.objects.filter(
                    strategyorder__strategy_run=strategy_run,
                    status=OrderStatus.PENDING,
                )
                
                cancelled_count = pending_orders.update(
                    status=OrderStatus.CANCELLED,
                    cancelled_at=timezone.now(),
                )
                
                logger.info(f"Cancelled {cancelled_count} pending orders")
                
                # Update status
                strategy_run.status = StrategyStatus.CANCELLED
                strategy_run.cancelled_at = timezone.now()
                strategy_run.save()
                
                logger.info(f"Strategy {strategy_id} cancelled successfully")
                
                # Send notification
                self._send_strategy_update(
                    strategy_run=strategy_run,
                    event_type='cancelled',
                )
                
                return True
        
        except StrategyRun.DoesNotExist:
            logger.error(f"Strategy {strategy_id} not found")
            raise ValueError(f"Strategy {strategy_id} not found")
        
        except Exception as e:
            logger.exception(f"Error cancelling strategy: {e}")
            raise
    
    # =========================================================================
    # STRATEGY QUERIES
    # =========================================================================
    
    def get_strategy_by_id(self, strategy_id: str) -> Optional[StrategyRun]:
        """
        Get a strategy by its ID.
        
        Args:
            strategy_id: UUID of the StrategyRun
        
        Returns:
            StrategyRun instance or None if not found
            
        Example:
            strategy = executor.get_strategy_by_id('uuid-here')
        """
        try:
            return StrategyRun.objects.select_related('account').get(
                strategy_id=strategy_id
            )
        except StrategyRun.DoesNotExist:
            logger.warning(f"Strategy {strategy_id} not found")
            return None
    
    def get_active_strategies(
        self,
        account: Optional[PaperTradingAccount] = None,
        strategy_type: Optional[str] = None,
    ) -> List[StrategyRun]:
        """
        Get all active strategies, optionally filtered by account and type.
        
        Active strategies are those in RUNNING or PAUSED status.
        
        Args:
            account: Filter by account (optional)
            strategy_type: Filter by strategy type (optional)
        
        Returns:
            List of active StrategyRun instances
            
        Example:
            # Get all active strategies
            strategies = executor.get_active_strategies()
            
            # Get active DCA strategies for an account
            strategies = executor.get_active_strategies(
                account=account,
                strategy_type=StrategyType.DCA
            )
        """
        queryset = StrategyRun.objects.filter(
            status__in=[StrategyStatus.RUNNING, StrategyStatus.PAUSED]
        ).select_related('account')
        
        if account:
            queryset = queryset.filter(account=account)
        
        if strategy_type:
            queryset = queryset.filter(strategy_type=strategy_type)
        
        return list(queryset.order_by('-created_at'))
    
    def get_strategy_history(
        self,
        account: PaperTradingAccount,
        limit: int = 50,
    ) -> List[StrategyRun]:
        """
        Get strategy execution history for an account.
        
        Args:
            account: Paper trading account
            limit: Maximum number of strategies to return (default: 50)
        
        Returns:
            List of StrategyRun instances, ordered by most recent first
            
        Example:
            history = executor.get_strategy_history(account=account, limit=20)
        """
        return list(
            StrategyRun.objects.filter(account=account)
            .select_related('account')
            .order_by('-created_at')[:limit]
        )
    
    # =========================================================================
    # PERFORMANCE METRICS
    # =========================================================================
    
    def calculate_strategy_metrics(self, strategy_id: str) -> Dict[str, Any]:
        """
        Calculate comprehensive performance metrics for a strategy.
        
        Metrics include:
        - Total invested amount
        - Average entry price
        - Current P&L
        - Completion percentage
        - Number of orders (total, completed, failed)
        - Win rate (for completed strategies)
        - Average profit per order
        - Time elapsed since start
        
        Args:
            strategy_id: UUID of the StrategyRun
        
        Returns:
            Dictionary with performance metrics
        
        Raises:
            ValueError: If strategy not found
            
        Example:
            metrics = executor.calculate_strategy_metrics('uuid-here')
            print(f"Progress: {metrics['completion_percent']}%")
            print(f"P&L: ${metrics['current_pnl']}")
        """
        try:
            strategy_run = StrategyRun.objects.select_related('account').get(
                strategy_id=strategy_id
            )
        except StrategyRun.DoesNotExist:
            raise ValueError(f"Strategy {strategy_id} not found")
        
        # Get performance data from the model
        performance = strategy_run.calculate_performance()
        
        # Add timing information
        time_elapsed = None
        if strategy_run.started_at:
            if strategy_run.completed_at:
                time_elapsed = (strategy_run.completed_at - strategy_run.started_at).total_seconds()
            else:
                time_elapsed = (timezone.now() - strategy_run.started_at).total_seconds()
        
        # Get order statistics
        strategy_orders = StrategyOrder.objects.filter(
            strategy_run=strategy_run
        ).select_related('order')
        
        total_orders = strategy_orders.count()
        filled_orders = strategy_orders.filter(order__status=OrderStatus.FILLED).count()
        pending_orders = strategy_orders.filter(order__status=OrderStatus.PENDING).count()
        
        # Calculate average profit per completed order
        filled_order_objs = [so.order for so in strategy_orders if so.order.status == OrderStatus.FILLED]
        
        avg_profit_per_order = Decimal('0.00')
        if filled_order_objs:
            total_profit = sum(
                (order.filled_price or Decimal('0')) - (order.limit_price or Decimal('0'))
                for order in filled_order_objs
                if order.filled_price and order.limit_price
            )
            avg_profit_per_order = total_profit / Decimal(str(len(filled_order_objs)))
        
        return {
            'strategy_id': str(strategy_run.strategy_id),
            'strategy_type': strategy_run.strategy_type,
            'status': strategy_run.status,
            'progress_percent': float(strategy_run.progress_percent),
            'current_step': strategy_run.current_step,
            
            # Order statistics
            'total_orders': total_orders,
            'completed_orders': filled_orders,
            'pending_orders': pending_orders,
            'failed_orders': strategy_run.failed_orders,
            'completion_rate': float(performance.get('completion_rate', 0)),
            'failure_rate': float(performance.get('failure_rate', 0)),
            
            # Financial metrics
            'total_invested': float(strategy_run.total_invested),
            'average_entry': float(strategy_run.average_entry) if strategy_run.average_entry else None,
            'current_pnl': float(strategy_run.current_pnl),
            'avg_profit_per_order': float(avg_profit_per_order),
            
            # Timing
            'created_at': strategy_run.created_at.isoformat(),
            'started_at': strategy_run.started_at.isoformat() if strategy_run.started_at else None,
            'completed_at': strategy_run.completed_at.isoformat() if strategy_run.completed_at else None,
            'time_elapsed_seconds': time_elapsed,
            
            # Additional info
            'notes': strategy_run.notes,
            'error_message': strategy_run.error_message,
        }
    
    def get_account_strategy_summary(
        self,
        account: PaperTradingAccount,
    ) -> Dict[str, Any]:
        """
        Get summary statistics for all strategies on an account.
        
        Args:
            account: Paper trading account
        
        Returns:
            Dictionary with summary statistics
            
        Example:
            summary = executor.get_account_strategy_summary(account)
            print(f"Active strategies: {summary['active_count']}")
            print(f"Total P&L: ${summary['total_pnl']}")
        """
        # Get all strategies for the account
        all_strategies = StrategyRun.objects.filter(account=account)
        
        # Count by status
        active_count = all_strategies.filter(
            status__in=[StrategyStatus.RUNNING, StrategyStatus.PAUSED]
        ).count()
        
        completed_count = all_strategies.filter(
            status=StrategyStatus.COMPLETED
        ).count()
        
        failed_count = all_strategies.filter(
            status=StrategyStatus.FAILED
        ).count()
        
        # Calculate totals
        aggregates = all_strategies.aggregate(
            total_invested=Sum('total_invested'),
            total_pnl=Sum('current_pnl'),
            avg_completion=Avg('progress_percent'),
        )
        
        # Count by type
        type_counts = {}
        for strategy_type in [StrategyType.DCA, StrategyType.GRID]:
            count = all_strategies.filter(strategy_type=strategy_type).count()
            type_counts[strategy_type] = count
        
        return {
            'account_id': str(account.account_id),
            'account_name': account.name,
            
            # Strategy counts
            'total_strategies': all_strategies.count(),
            'active_strategies': active_count,
            'completed_strategies': completed_count,
            'failed_strategies': failed_count,
            
            # By type
            'strategies_by_type': type_counts,
            
            # Financial summary
            'total_invested': float(aggregates['total_invested'] or 0),
            'total_pnl': float(aggregates['total_pnl'] or 0),
            'avg_completion_percent': float(aggregates['avg_completion'] or 0),
        }
    
    # =========================================================================
    # VALIDATION
    # =========================================================================
    
    def validate_strategy_config(
        self,
        strategy_type: str,
        config: Dict[str, Any],
        account: Optional[PaperTradingAccount] = None,
    ) -> Tuple[bool, str]:
        """
        Validate a strategy configuration without starting it.
        
        This is a public wrapper around _validate_strategy_config that
        can be used to check configurations before attempting to start.
        
        Args:
            strategy_type: Type of strategy (DCA, GRID, etc.)
            config: Strategy configuration dictionary
            account: Paper trading account (optional, for balance checks)
        
        Returns:
            Tuple of (is_valid: bool, error_message: str)
            
        Example:
            is_valid, error_msg = executor.validate_strategy_config(
                strategy_type=StrategyType.DCA,
                config={...}
            )
            if not is_valid:
                print(f"Configuration error: {error_msg}")
        """
        return self._validate_strategy_config(
            strategy_type=strategy_type,
            config=config,
            account=account,
        )
    
    def _validate_strategy_config(
        self,
        strategy_type: str,
        config: Dict[str, Any],
        account: Optional[PaperTradingAccount] = None,
    ) -> Tuple[bool, str]:
        """
        Internal validation method that delegates to strategy classes.
        
        Args:
            strategy_type: Type of strategy
            config: Configuration dictionary
            account: Optional account for balance validation
        
        Returns:
            Tuple of (is_valid: bool, error_message: str)
        """
        try:
            # Check if strategy type is supported
            if strategy_type not in self.strategy_classes:
                return False, f"Unsupported strategy type: {strategy_type}"
            
            # Get strategy class
            strategy_class = self.strategy_classes[strategy_type]
            
            # Create a temporary strategy run for validation
            # (not saved to database)
            temp_strategy_run = StrategyRun(
                account=account,
                strategy_type=strategy_type,
                config=config,
                status=StrategyStatus.PENDING,
            )
            
            # Initialize strategy instance
            strategy_instance = strategy_class(strategy_run=temp_strategy_run)
            
            # Call validate_config method (returns tuple: (is_valid, error_message))
            is_valid, error_message = strategy_instance.validate_config()
            
            if not is_valid:
                return False, error_message
            
            return True, ''
        
        except Exception as e:
            logger.exception(f"Error validating strategy config: {e}")
            return False, f"Validation error: {str(e)}"
    
    # =========================================================================
    # INTERNAL HELPERS
    # =========================================================================
    
    def _send_strategy_update(
        self,
        strategy_run: StrategyRun,
        event_type: str,
    ) -> None:
        """
        Send WebSocket notification for strategy event.
        
        Args:
            strategy_run: StrategyRun instance
            event_type: Type of event (started, paused, resumed, cancelled, etc.)
        """
        try:
            message = {
                'type': 'strategy_update',
                'event': event_type,
                'strategy_id': str(strategy_run.strategy_id),
                'strategy_type': strategy_run.strategy_type,
                'status': strategy_run.status,
                'progress_percent': float(strategy_run.progress_percent),
                'current_step': strategy_run.current_step,
            }
            
            websocket_service.send_update(
                account_id=strategy_run.account.account_id,
                message_type='strategy_update',
                data=message,
            )
            
            logger.debug(f"Sent WebSocket update for strategy {strategy_run.strategy_id}")
        
        except Exception as e:
            logger.exception(f"Error sending strategy update: {e}")
            # Don't raise - WebSocket failures shouldn't stop strategy execution


# =============================================================================
# SINGLETON INSTANCE HELPER
# =============================================================================

_strategy_executor_instance: Optional[StrategyExecutor] = None


def get_strategy_executor() -> StrategyExecutor:
    """
    Get or create the singleton StrategyExecutor instance.
    
    Returns:
        StrategyExecutor singleton instance
        
    Example:
        executor = get_strategy_executor()
        strategy = executor.start_strategy(...)
    """
    global _strategy_executor_instance
    
    if _strategy_executor_instance is None:
        _strategy_executor_instance = StrategyExecutor()
        logger.info("Created singleton StrategyExecutor instance")
    
    return _strategy_executor_instance