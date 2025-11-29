"""
Performance Metrics Calculator - Backtesting Analytics

Calculates comprehensive performance metrics for backtested strategies:
- Total Return %
- Win Rate %
- Max Drawdown %
- Sharpe Ratio
- Average Trade P&L
- Risk-adjusted returns

Phase 7B - Day 12: Backtesting Engine

File: dexproject/paper_trading/backtesting/metrics.py
"""

import logging
from decimal import Decimal, ROUND_DOWN
from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np


logger = logging.getLogger(__name__)


# =============================================================================
# PERFORMANCE METRICS CALCULATOR
# =============================================================================

class PerformanceMetricsCalculator:
    """
    Calculates advanced performance metrics for backtesting results.
    
    Metrics calculated:
    - Total Return %
    - Annualized Return %
    - Win Rate %
    - Profit Factor
    - Max Drawdown %
    - Sharpe Ratio
    - Sortino Ratio
    - Average Trade P&L
    - Best/Worst Trade
    - Consecutive Wins/Losses
    
    Example:
        calculator = PerformanceMetricsCalculator()
        metrics = calculator.calculate_metrics(
            simulation_results=results,
            risk_free_rate=Decimal('2.0')
        )
    """
    
    def __init__(self) -> None:
        """Initialize the metrics calculator."""
        logger.info("[BACKTEST] PerformanceMetricsCalculator initialized")
    
    # =========================================================================
    # PUBLIC METHODS
    # =========================================================================
    
    def calculate_metrics(
        self,
        simulation_results: Dict[str, Any],
        risk_free_rate: Decimal = Decimal('2.0')
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive performance metrics.
        
        Args:
            simulation_results: Results from strategy simulation
            risk_free_rate: Annual risk-free rate % (default 2%)
            
        Returns:
            Dictionary with all performance metrics
        """
        try:
            # Extract basic info
            initial_balance = Decimal(simulation_results['initial_balance_usd'])
            final_balance = Decimal(simulation_results['final_balance_usd'])
            trades = simulation_results['trades']
            
            if not trades:
                logger.warning("[BACKTEST] No trades to calculate metrics")
                return self._empty_metrics()
            
            # Calculate metrics
            metrics = {}
            
            # Basic metrics
            metrics['initial_balance_usd'] = str(initial_balance)
            metrics['final_balance_usd'] = str(final_balance)
            metrics['profit_loss_usd'] = simulation_results['profit_loss_usd']
            metrics['return_percent'] = simulation_results['return_percent']
            metrics['total_fees_usd'] = simulation_results['total_fees_usd']
            metrics['num_trades'] = simulation_results['num_trades']
            metrics['num_buys'] = simulation_results['num_buys']
            metrics['num_sells'] = simulation_results['num_sells']
            
            # Trade analysis
            trade_metrics = self._calculate_trade_metrics(trades)
            metrics.update(trade_metrics)
            
            # Win rate
            win_rate = self._calculate_win_rate(trades)
            metrics['win_rate_percent'] = str(win_rate)
            
            # Profit factor
            profit_factor = self._calculate_profit_factor(trades)
            metrics['profit_factor'] = str(profit_factor)
            
            # Max drawdown
            max_drawdown = self._calculate_max_drawdown(trades, initial_balance)
            metrics['max_drawdown_percent'] = str(max_drawdown)
            
            # Sharpe ratio
            sharpe = self._calculate_sharpe_ratio(
                trades=trades,
                initial_balance=initial_balance,
                risk_free_rate=risk_free_rate
            )
            metrics['sharpe_ratio'] = str(sharpe)
            
            # Sortino ratio
            sortino = self._calculate_sortino_ratio(
                trades=trades,
                initial_balance=initial_balance,
                risk_free_rate=risk_free_rate
            )
            metrics['sortino_ratio'] = str(sortino)
            
            # Average holding period
            avg_holding = self._calculate_avg_holding_period(trades)
            metrics['avg_holding_hours'] = str(avg_holding)
            
            # Consecutive stats
            consecutive = self._calculate_consecutive_stats(trades)
            metrics.update(consecutive)
            
            logger.info(
                f"[BACKTEST] Calculated metrics: "
                f"Return {metrics['return_percent']}%, "
                f"Win Rate {metrics['win_rate_percent']}%, "
                f"Sharpe {metrics['sharpe_ratio']}"
            )
            
            return metrics
            
        except Exception as e:
            logger.error(
                f"[BACKTEST] Error calculating metrics: {e}",
                exc_info=True
            )
            return self._empty_metrics()
    
    # =========================================================================
    # PRIVATE METHODS - Metric Calculations
    # =========================================================================
    
    def _calculate_trade_metrics(
        self,
        trades: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Calculate per-trade metrics.
        
        Args:
            trades: List of trade dictionaries
            
        Returns:
            Dictionary with trade metrics
        """
        if not trades:
            return {
                'avg_trade_pnl_usd': '0.00',
                'best_trade_pnl_usd': '0.00',
                'worst_trade_pnl_usd': '0.00',
                'avg_trade_size_usd': '0.00',
            }
        
        # Calculate P&L for each trade pair (buy + sell)
        buy_trades = [t for t in trades if t['side'] == 'BUY']
        sell_trades = [t for t in trades if t['side'] == 'SELL']
        
        trade_pnls: List[Decimal] = []
        trade_sizes: List[Decimal] = []
        
        # Match buys with sells to calculate P&L
        for i, buy in enumerate(buy_trades):
            if i < len(sell_trades):
                sell = sell_trades[i]
                
                buy_amount = Decimal(buy['amount_usd'])
                sell_amount = Decimal(sell['amount_usd'])
                
                # P&L = sell amount - buy amount - fees
                pnl = sell_amount - buy_amount
                trade_pnls.append(pnl)
                trade_sizes.append(buy_amount)
        
        if not trade_pnls:
            avg_pnl = Decimal('0')
            best_pnl = Decimal('0')
            worst_pnl = Decimal('0')
        else:
            avg_pnl = sum(trade_pnls) / Decimal(str(len(trade_pnls)))
            best_pnl = max(trade_pnls)
            worst_pnl = min(trade_pnls)
        
        avg_size = (
            sum(trade_sizes) / Decimal(str(len(trade_sizes)))
            if trade_sizes else Decimal('0')
        )
        
        return {
            'avg_trade_pnl_usd': str(avg_pnl.quantize(Decimal('0.01'))),
            'best_trade_pnl_usd': str(best_pnl.quantize(Decimal('0.01'))),
            'worst_trade_pnl_usd': str(worst_pnl.quantize(Decimal('0.01'))),
            'avg_trade_size_usd': str(avg_size.quantize(Decimal('0.01'))),
        }
    
    def _calculate_win_rate(
        self,
        trades: List[Dict[str, Any]]
    ) -> Decimal:
        """
        Calculate win rate percentage.
        
        Args:
            trades: List of trade dictionaries
            
        Returns:
            Win rate as percentage (0-100)
        """
        # Match buys with sells
        buy_trades = [t for t in trades if t['side'] == 'BUY']
        sell_trades = [t for t in trades if t['side'] == 'SELL']
        
        if not buy_trades or not sell_trades:
            return Decimal('0')
        
        wins = 0
        total_pairs = min(len(buy_trades), len(sell_trades))
        
        for i in range(total_pairs):
            buy_price = Decimal(buy_trades[i]['price'])
            sell_price = Decimal(sell_trades[i]['price'])
            
            if sell_price > buy_price:
                wins += 1
        
        if total_pairs == 0:
            return Decimal('0')
        
        win_rate = (Decimal(str(wins)) / Decimal(str(total_pairs))) * Decimal('100')
        return win_rate.quantize(Decimal('0.01'))
    
    def _calculate_profit_factor(
        self,
        trades: List[Dict[str, Any]]
    ) -> Decimal:
        """
        Calculate profit factor (gross profit / gross loss).
        
        Args:
            trades: List of trade dictionaries
            
        Returns:
            Profit factor ratio
        """
        buy_trades = [t for t in trades if t['side'] == 'BUY']
        sell_trades = [t for t in trades if t['side'] == 'SELL']
        
        gross_profit = Decimal('0')
        gross_loss = Decimal('0')
        
        for i, buy in enumerate(buy_trades):
            if i < len(sell_trades):
                sell = sell_trades[i]
                
                buy_amount = Decimal(buy['amount_usd'])
                sell_amount = Decimal(sell['amount_usd'])
                
                pnl = sell_amount - buy_amount
                
                if pnl > 0:
                    gross_profit += pnl
                else:
                    gross_loss += abs(pnl)
        
        if gross_loss == 0:
            return Decimal('999.99') if gross_profit > 0 else Decimal('0')
        
        profit_factor = gross_profit / gross_loss
        return profit_factor.quantize(Decimal('0.01'))
    
    def _calculate_max_drawdown(
        self,
        trades: List[Dict[str, Any]],
        initial_balance: Decimal
    ) -> Decimal:
        """
        Calculate maximum drawdown percentage.
        
        Args:
            trades: List of trade dictionaries
            initial_balance: Starting balance
            
        Returns:
            Max drawdown as percentage
        """
        if not trades:
            return Decimal('0')
        
        # Build equity curve
        equity = initial_balance
        equity_curve: List[Decimal] = [equity]
        
        for trade in trades:
            if trade['side'] == 'BUY':
                equity -= Decimal(trade['amount_usd'])
            else:  # SELL
                equity += Decimal(trade['amount_usd'])
            
            equity_curve.append(equity)
        
        # Calculate drawdown at each point
        max_drawdown = Decimal('0')
        peak = equity_curve[0]
        
        for value in equity_curve:
            if value > peak:
                peak = value
            
            drawdown = ((peak - value) / peak * Decimal('100')) if peak > 0 else Decimal('0')
            
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        return max_drawdown.quantize(Decimal('0.01'))
    
    def _calculate_sharpe_ratio(
        self,
        trades: List[Dict[str, Any]],
        initial_balance: Decimal,
        risk_free_rate: Decimal
    ) -> Decimal:
        """
        Calculate Sharpe Ratio (risk-adjusted return).
        
        Sharpe = (Portfolio Return - Risk Free Rate) / Std Dev of Returns
        
        Args:
            trades: List of trade dictionaries
            initial_balance: Starting balance
            risk_free_rate: Annual risk-free rate %
            
        Returns:
            Sharpe ratio
        """
        if len(trades) < 2:
            return Decimal('0')
        
        # Calculate returns for each trade pair
        returns: List[float] = []
        
        buy_trades = [t for t in trades if t['side'] == 'BUY']
        sell_trades = [t for t in trades if t['side'] == 'SELL']
        
        for i, buy in enumerate(buy_trades):
            if i < len(sell_trades):
                sell = sell_trades[i]
                
                buy_amount = Decimal(buy['amount_usd'])
                sell_amount = Decimal(sell['amount_usd'])
                
                # Calculate return %
                trade_return = ((sell_amount - buy_amount) / buy_amount * Decimal('100'))
                returns.append(float(trade_return))
        
        if not returns:
            return Decimal('0')
        
        # Calculate mean and std dev
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        
        if std_return == 0:
            return Decimal('0')
        
        # Annualize (assuming daily trades for simplicity)
        risk_free_daily = float(risk_free_rate) / 365
        
        sharpe = (mean_return - risk_free_daily) / std_return
        
        return Decimal(str(sharpe)).quantize(Decimal('0.01'))
    
    def _calculate_sortino_ratio(
        self,
        trades: List[Dict[str, Any]],
        initial_balance: Decimal,
        risk_free_rate: Decimal
    ) -> Decimal:
        """
        Calculate Sortino Ratio (downside risk-adjusted return).
        
        Similar to Sharpe but only penalizes downside volatility.
        
        Args:
            trades: List of trade dictionaries
            initial_balance: Starting balance
            risk_free_rate: Annual risk-free rate %
            
        Returns:
            Sortino ratio
        """
        if len(trades) < 2:
            return Decimal('0')
        
        # Calculate returns for each trade pair
        returns: List[float] = []
        
        buy_trades = [t for t in trades if t['side'] == 'BUY']
        sell_trades = [t for t in trades if t['side'] == 'SELL']
        
        for i, buy in enumerate(buy_trades):
            if i < len(sell_trades):
                sell = sell_trades[i]
                
                buy_amount = Decimal(buy['amount_usd'])
                sell_amount = Decimal(sell['amount_usd'])
                
                trade_return = ((sell_amount - buy_amount) / buy_amount * Decimal('100'))
                returns.append(float(trade_return))
        
        if not returns:
            return Decimal('0')
        
        # Calculate mean return
        mean_return = np.mean(returns)
        
        # Calculate downside deviation (only negative returns)
        negative_returns = [r for r in returns if r < 0]
        
        if not negative_returns:
            return Decimal('999.99')  # No downside risk
        
        downside_std = np.std(negative_returns)
        
        if downside_std == 0:
            return Decimal('0')
        
        # Annualize
        risk_free_daily = float(risk_free_rate) / 365
        
        sortino = (mean_return - risk_free_daily) / downside_std
        
        return Decimal(str(sortino)).quantize(Decimal('0.01'))
    
    def _calculate_avg_holding_period(
        self,
        trades: List[Dict[str, Any]]
    ) -> Decimal:
        """
        Calculate average holding period in hours.
        
        Args:
            trades: List of trade dictionaries
            
        Returns:
            Average hours held
        """
        buy_trades = [t for t in trades if t['side'] == 'BUY']
        sell_trades = [t for t in trades if t['side'] == 'SELL']
        
        if not buy_trades or not sell_trades:
            return Decimal('0')
        
        holding_periods: List[Decimal] = []
        
        for i, buy in enumerate(buy_trades):
            if i < len(sell_trades):
                sell = sell_trades[i]
                
                # Parse timestamps
                from datetime import datetime
                buy_time = datetime.fromisoformat(buy['timestamp'])
                sell_time = datetime.fromisoformat(sell['timestamp'])
                
                # Calculate hours
                hours = (sell_time - buy_time).total_seconds() / 3600
                holding_periods.append(Decimal(str(hours)))
        
        if not holding_periods:
            return Decimal('0')
        
        avg_hours = sum(holding_periods) / Decimal(str(len(holding_periods)))
        return avg_hours.quantize(Decimal('0.01'))
    
    def _calculate_consecutive_stats(
        self,
        trades: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Calculate consecutive wins/losses.
        
        Args:
            trades: List of trade dictionaries
            
        Returns:
            Dictionary with consecutive stats
        """
        buy_trades = [t for t in trades if t['side'] == 'BUY']
        sell_trades = [t for t in trades if t['side'] == 'SELL']
        
        if not buy_trades or not sell_trades:
            return {
                'max_consecutive_wins': 0,
                'max_consecutive_losses': 0,
                'current_streak': 0,
                'current_streak_type': 'none',
            }
        
        # Determine win/loss for each trade pair
        results: List[bool] = []  # True = win, False = loss
        
        for i, buy in enumerate(buy_trades):
            if i < len(sell_trades):
                sell = sell_trades[i]
                
                buy_price = Decimal(buy['price'])
                sell_price = Decimal(sell['price'])
                
                results.append(sell_price > buy_price)
        
        # Calculate consecutive streaks
        max_wins = 0
        max_losses = 0
        current_streak = 0
        current_streak_type = 'none'
        
        consecutive_wins = 0
        consecutive_losses = 0
        
        for is_win in results:
            if is_win:
                consecutive_wins += 1
                consecutive_losses = 0
                
                if consecutive_wins > max_wins:
                    max_wins = consecutive_wins
            else:
                consecutive_losses += 1
                consecutive_wins = 0
                
                if consecutive_losses > max_losses:
                    max_losses = consecutive_losses
        
        # Determine current streak
        if results:
            if results[-1]:
                current_streak = consecutive_wins
                current_streak_type = 'wins'
            else:
                current_streak = consecutive_losses
                current_streak_type = 'losses'
        
        return {
            'max_consecutive_wins': max_wins,
            'max_consecutive_losses': max_losses,
            'current_streak': current_streak,
            'current_streak_type': current_streak_type,
        }
    
    def _empty_metrics(self) -> Dict[str, Any]:
        """Return empty metrics dictionary."""
        return {
            'initial_balance_usd': '0.00',
            'final_balance_usd': '0.00',
            'profit_loss_usd': '0.00',
            'return_percent': '0.00',
            'total_fees_usd': '0.00',
            'num_trades': 0,
            'num_buys': 0,
            'num_sells': 0,
            'avg_trade_pnl_usd': '0.00',
            'best_trade_pnl_usd': '0.00',
            'worst_trade_pnl_usd': '0.00',
            'avg_trade_size_usd': '0.00',
            'win_rate_percent': '0.00',
            'profit_factor': '0.00',
            'max_drawdown_percent': '0.00',
            'sharpe_ratio': '0.00',
            'sortino_ratio': '0.00',
            'avg_holding_hours': '0.00',
            'max_consecutive_wins': 0,
            'max_consecutive_losses': 0,
            'current_streak': 0,
            'current_streak_type': 'none',
        }