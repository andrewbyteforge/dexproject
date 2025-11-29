"""
Strategy Simulator - Backtesting Strategy Execution

Simulates trading strategies on historical data to evaluate performance.
Supports all 5 strategy types: SPOT, DCA, GRID, TWAP, VWAP.

Phase 7B - Day 12: Backtesting Engine

File: dexproject/paper_trading/backtesting/simulator.py
"""

import logging
from decimal import Decimal, ROUND_DOWN
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import pandas as pd
from django.utils import timezone

from paper_trading.constants import StrategyType


logger = logging.getLogger(__name__)


# =============================================================================
# SIMULATED TRADE
# =============================================================================

class SimulatedTrade:
    """
    Represents a single simulated trade execution.
    
    Attributes:
        timestamp: When the trade was executed
        side: 'BUY' or 'SELL'
        amount_usd: USD amount of trade
        price: Token price at execution
        tokens_received: Tokens acquired (for buys)
        tokens_sold: Tokens sold (for sells)
        fee_usd: Trading fee in USD
    """
    
    def __init__(
        self,
        timestamp: datetime,
        side: str,
        amount_usd: Decimal,
        price: Decimal,
        fee_percent: Decimal = Decimal('0.3')
    ) -> None:
        """
        Initialize a simulated trade.
        
        Args:
            timestamp: Trade execution time
            side: 'BUY' or 'SELL'
            amount_usd: Trade amount in USD
            price: Token price
            fee_percent: Trading fee percentage (default 0.3%)
        """
        self.timestamp: datetime = timestamp
        self.side: str = side
        self.amount_usd: Decimal = amount_usd
        self.price: Decimal = price
        
        # Calculate fee
        self.fee_usd: Decimal = (amount_usd * fee_percent / Decimal('100')).quantize(
            Decimal('0.01'), rounding=ROUND_DOWN
        )
        
        # Calculate tokens based on side
        if side == 'BUY':
            # Buying tokens with USD (subtract fee from USD before buying)
            net_usd = amount_usd - self.fee_usd
            self.tokens_received: Decimal = (net_usd / price).quantize(
                Decimal('0.00000001'), rounding=ROUND_DOWN
            )
            self.tokens_sold: Decimal = Decimal('0')
        else:  # SELL
            # Selling tokens for USD (fee deducted from USD received)
            self.tokens_sold = (amount_usd / price).quantize(
                Decimal('0.00000001'), rounding=ROUND_DOWN
            )
            self.tokens_received = Decimal('0')
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert trade to dictionary."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'side': self.side,
            'amount_usd': str(self.amount_usd),
            'price': str(self.price),
            'tokens_received': str(self.tokens_received),
            'tokens_sold': str(self.tokens_sold),
            'fee_usd': str(self.fee_usd),
        }


# =============================================================================
# STRATEGY SIMULATOR
# =============================================================================

class StrategySimulator:
    """
    Simulates trading strategies on historical data.
    
    Executes strategy logic against historical prices to calculate
    what the performance would have been.
    
    Example:
        simulator = StrategySimulator(
            initial_balance_usd=Decimal('10000'),
            fee_percent=Decimal('0.3')
        )
        
        result = simulator.simulate_dca_strategy(
            historical_data=df,
            total_amount_usd=Decimal('1000'),
            num_intervals=10
        )
    """
    
    def __init__(
        self,
        initial_balance_usd: Decimal,
        fee_percent: Decimal = Decimal('0.3')
    ) -> None:
        """
        Initialize strategy simulator.
        
        Args:
            initial_balance_usd: Starting balance for backtest
            fee_percent: Trading fee percentage (default 0.3% like Uniswap)
        """
        self.initial_balance_usd: Decimal = initial_balance_usd
        self.fee_percent: Decimal = fee_percent
        
        # Portfolio state
        self.cash_balance_usd: Decimal = initial_balance_usd
        self.token_balance: Decimal = Decimal('0')
        self.trades: List[SimulatedTrade] = []
        
        logger.info(
            f"[BACKTEST] Initialized simulator with ${initial_balance_usd} "
            f"and {fee_percent}% fees"
        )
    
    # =========================================================================
    # STRATEGY SIMULATION METHODS
    # =========================================================================
    
    def simulate_spot_strategy(
        self,
        historical_data: pd.DataFrame,
        buy_amount_usd: Decimal,
        entry_index: int = 0,
        exit_index: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Simulate SPOT buy strategy (buy once, sell at end).
        
        Args:
            historical_data: DataFrame with price data
            buy_amount_usd: Amount to buy in USD
            entry_index: Index to enter position (default: first)
            exit_index: Index to exit position (default: last)
            
        Returns:
            Dictionary with simulation results
        """
        self._reset_portfolio()
        
        if exit_index is None:
            exit_index = len(historical_data) - 1
        
        # Execute buy
        entry_row = historical_data.iloc[entry_index]
        buy_trade = self._execute_buy(
            timestamp=entry_row['timestamp'],
            amount_usd=buy_amount_usd,
            price=Decimal(str(entry_row['close']))
        )
        
        # Execute sell at exit
        exit_row = historical_data.iloc[exit_index]
        sell_trade = self._execute_sell(
            timestamp=exit_row['timestamp'],
            tokens_to_sell=self.token_balance,
            price=Decimal(str(exit_row['close']))
        )
        
        return self._calculate_results('SPOT')
    
    def simulate_dca_strategy(
        self,
        historical_data: pd.DataFrame,
        total_amount_usd: Decimal,
        num_intervals: int
    ) -> Dict[str, Any]:
        """
        Simulate DCA (Dollar Cost Averaging) strategy.
        
        Args:
            historical_data: DataFrame with price data
            total_amount_usd: Total amount to invest
            num_intervals: Number of buy intervals
            
        Returns:
            Dictionary with simulation results
        """
        self._reset_portfolio()
        
        # Calculate amount per interval
        amount_per_interval = (total_amount_usd / Decimal(str(num_intervals))).quantize(
            Decimal('0.01'), rounding=ROUND_DOWN
        )
        
        # Calculate interval spacing (evenly distribute across data)
        data_length = len(historical_data)
        interval_spacing = max(1, data_length // num_intervals)
        
        # Execute buys at intervals
        for i in range(num_intervals):
            index = min(i * interval_spacing, data_length - 1)
            row = historical_data.iloc[index]
            
            self._execute_buy(
                timestamp=row['timestamp'],
                amount_usd=amount_per_interval,
                price=Decimal(str(row['close']))
            )
        
        # Sell all at end
        final_row = historical_data.iloc[-1]
        self._execute_sell(
            timestamp=final_row['timestamp'],
            tokens_to_sell=self.token_balance,
            price=Decimal(str(final_row['close']))
        )
        
        return self._calculate_results('DCA')
    
    def simulate_grid_strategy(
        self,
        historical_data: pd.DataFrame,
        total_amount_usd: Decimal,
        num_grids: int,
        price_range_percent: Decimal = Decimal('10')
    ) -> Dict[str, Any]:
        """
        Simulate GRID trading strategy.
        
        Places buy/sell orders at different price levels and profits
        from price oscillations.
        
        Args:
            historical_data: DataFrame with price data
            total_amount_usd: Total capital to allocate
            num_grids: Number of grid levels
            price_range_percent: Price range % around starting price
            
        Returns:
            Dictionary with simulation results
        """
        self._reset_portfolio()
        
        # Get starting price
        start_price = Decimal(str(historical_data.iloc[0]['close']))
        
        # Calculate grid levels
        range_multiplier = price_range_percent / Decimal('100')
        lower_bound = start_price * (Decimal('1') - range_multiplier)
        upper_bound = start_price * (Decimal('1') + range_multiplier)
        
        grid_step = (upper_bound - lower_bound) / Decimal(str(num_grids))
        grid_levels = [
            lower_bound + (grid_step * Decimal(str(i)))
            for i in range(num_grids + 1)
        ]
        
        # Amount per grid level
        amount_per_level = (total_amount_usd / Decimal(str(num_grids))).quantize(
            Decimal('0.01'), rounding=ROUND_DOWN
        )
        
        # Track which levels have been filled
        filled_levels: Dict[int, bool] = {i: False for i in range(len(grid_levels))}
        
        # Simulate grid trading
        for _, row in historical_data.iterrows():
            current_price = Decimal(str(row['close']))
            
            # Check each grid level
            for i, level_price in enumerate(grid_levels):
                # Buy if price crosses below grid level (not already filled)
                if current_price <= level_price and not filled_levels[i]:
                    if self.cash_balance_usd >= amount_per_level:
                        self._execute_buy(
                            timestamp=row['timestamp'],
                            amount_usd=amount_per_level,
                            price=current_price
                        )
                        filled_levels[i] = True
                
                # Sell if price crosses above grid level (was filled before)
                elif current_price >= level_price and filled_levels[i]:
                    # Sell a portion of tokens
                    tokens_to_sell = amount_per_level / level_price
                    if self.token_balance >= tokens_to_sell:
                        self._execute_sell(
                            timestamp=row['timestamp'],
                            tokens_to_sell=tokens_to_sell,
                            price=current_price
                        )
                        filled_levels[i] = False
        
        # Close any remaining position at end
        if self.token_balance > Decimal('0'):
            final_row = historical_data.iloc[-1]
            self._execute_sell(
                timestamp=final_row['timestamp'],
                tokens_to_sell=self.token_balance,
                price=Decimal(str(final_row['close']))
            )
        
        return self._calculate_results('GRID')
    
    def simulate_twap_strategy(
        self,
        historical_data: pd.DataFrame,
        total_amount_usd: Decimal,
        execution_window_hours: int,
        num_intervals: int
    ) -> Dict[str, Any]:
        """
        Simulate TWAP (Time-Weighted Average Price) strategy.
        
        Executes equal-sized chunks at regular intervals within a
        time window.
        
        Args:
            historical_data: DataFrame with price data
            total_amount_usd: Total amount to invest
            execution_window_hours: Hours to complete execution
            num_intervals: Number of execution intervals
            
        Returns:
            Dictionary with simulation results
        """
        self._reset_portfolio()
        
        # Calculate amount per interval
        amount_per_interval = (total_amount_usd / Decimal(str(num_intervals))).quantize(
            Decimal('0.01'), rounding=ROUND_DOWN
        )
        
        # Find data points within execution window
        start_time = historical_data.iloc[0]['timestamp']
        end_time = start_time + timedelta(hours=execution_window_hours)
        
        window_data = historical_data[
            (historical_data['timestamp'] >= start_time) &
            (historical_data['timestamp'] <= end_time)
        ]
        
        if len(window_data) < num_intervals:
            logger.warning(
                f"[BACKTEST] Not enough data points in {execution_window_hours}h window. "
                f"Need {num_intervals}, got {len(window_data)}"
            )
            # Use all available data
            interval_spacing = 1
        else:
            interval_spacing = len(window_data) // num_intervals
        
        # Execute buys at intervals
        for i in range(min(num_intervals, len(window_data))):
            index = min(i * interval_spacing, len(window_data) - 1)
            row = window_data.iloc[index]
            
            self._execute_buy(
                timestamp=row['timestamp'],
                amount_usd=amount_per_interval,
                price=Decimal(str(row['close']))
            )
        
        # Sell all at end of backtest period
        final_row = historical_data.iloc[-1]
        self._execute_sell(
            timestamp=final_row['timestamp'],
            tokens_to_sell=self.token_balance,
            price=Decimal(str(final_row['close']))
        )
        
        return self._calculate_results('TWAP')
    
    def simulate_vwap_strategy(
        self,
        historical_data: pd.DataFrame,
        total_amount_usd: Decimal,
        execution_window_hours: int,
        num_intervals: int
    ) -> Dict[str, Any]:
        """
        Simulate VWAP (Volume-Weighted Average Price) strategy.
        
        Executes chunks sized proportionally to volume distribution.
        
        Args:
            historical_data: DataFrame with price data
            total_amount_usd: Total amount to invest
            execution_window_hours: Hours to complete execution
            num_intervals: Number of execution intervals
            
        Returns:
            Dictionary with simulation results
        """
        self._reset_portfolio()
        
        # Find data points within execution window
        start_time = historical_data.iloc[0]['timestamp']
        end_time = start_time + timedelta(hours=execution_window_hours)
        
        window_data = historical_data[
            (historical_data['timestamp'] >= start_time) &
            (historical_data['timestamp'] <= end_time)
        ]
        
        if window_data.empty:
            logger.error("[BACKTEST] No data in execution window")
            return self._calculate_results('VWAP')
        
        # Calculate volume weights
        total_volume = window_data['volume'].sum()
        
        if total_volume == 0:
            # Fallback to TWAP if no volume data
            logger.warning("[BACKTEST] No volume data, falling back to TWAP")
            return self.simulate_twap_strategy(
                historical_data=historical_data,
                total_amount_usd=total_amount_usd,
                execution_window_hours=execution_window_hours,
                num_intervals=num_intervals
            )
        
        # Distribute intervals based on volume
        interval_spacing = len(window_data) // num_intervals
        
        for i in range(min(num_intervals, len(window_data))):
            index = min(i * interval_spacing, len(window_data) - 1)
            row = window_data.iloc[index]
            
            # Weight this interval by its volume proportion
            volume_weight = row['volume'] / total_volume
            amount_for_interval = (total_amount_usd * Decimal(str(volume_weight))).quantize(
                Decimal('0.01'), rounding=ROUND_DOWN
            )
            
            if amount_for_interval > Decimal('0.01'):  # Minimum $0.01
                self._execute_buy(
                    timestamp=row['timestamp'],
                    amount_usd=amount_for_interval,
                    price=Decimal(str(row['close']))
                )
        
        # Sell all at end
        final_row = historical_data.iloc[-1]
        self._execute_sell(
            timestamp=final_row['timestamp'],
            tokens_to_sell=self.token_balance,
            price=Decimal(str(final_row['close']))
        )
        
        return self._calculate_results('VWAP')
    
    # =========================================================================
    # PRIVATE METHODS - Trade Execution
    # =========================================================================
    
    def _execute_buy(
        self,
        timestamp: datetime,
        amount_usd: Decimal,
        price: Decimal
    ) -> SimulatedTrade:
        """
        Execute a simulated buy trade.
        
        Args:
            timestamp: Trade time
            amount_usd: USD amount to spend
            price: Token price
            
        Returns:
            SimulatedTrade object
        """
        # Check sufficient balance
        if self.cash_balance_usd < amount_usd:
            logger.warning(
                f"[BACKTEST] Insufficient balance for buy: "
                f"${self.cash_balance_usd} < ${amount_usd}"
            )
            amount_usd = self.cash_balance_usd
        
        # Create trade
        trade = SimulatedTrade(
            timestamp=timestamp,
            side='BUY',
            amount_usd=amount_usd,
            price=price,
            fee_percent=self.fee_percent
        )
        
        # Update portfolio
        self.cash_balance_usd -= amount_usd
        self.token_balance += trade.tokens_received
        self.trades.append(trade)
        
        logger.debug(
            f"[BACKTEST] BUY: ${amount_usd} @ ${price} = "
            f"{trade.tokens_received} tokens (fee: ${trade.fee_usd})"
        )
        
        return trade
    
    def _execute_sell(
        self,
        timestamp: datetime,
        tokens_to_sell: Decimal,
        price: Decimal
    ) -> SimulatedTrade:
        """
        Execute a simulated sell trade.
        
        Args:
            timestamp: Trade time
            tokens_to_sell: Number of tokens to sell
            price: Token price
            
        Returns:
            SimulatedTrade object
        """
        # Check sufficient tokens
        if self.token_balance < tokens_to_sell:
            logger.warning(
                f"[BACKTEST] Insufficient tokens for sell: "
                f"{self.token_balance} < {tokens_to_sell}"
            )
            tokens_to_sell = self.token_balance
        
        # Calculate USD value
        amount_usd = (tokens_to_sell * price).quantize(
            Decimal('0.01'), rounding=ROUND_DOWN
        )
        
        # Create trade
        trade = SimulatedTrade(
            timestamp=timestamp,
            side='SELL',
            amount_usd=amount_usd,
            price=price,
            fee_percent=self.fee_percent
        )
        
        # Update portfolio
        self.token_balance -= tokens_to_sell
        self.cash_balance_usd += (amount_usd - trade.fee_usd)
        self.trades.append(trade)
        
        logger.debug(
            f"[BACKTEST] SELL: {tokens_to_sell} tokens @ ${price} = "
            f"${amount_usd} (fee: ${trade.fee_usd})"
        )
        
        return trade
    
    def _calculate_results(self, strategy_type: str) -> Dict[str, Any]:
        """
        Calculate final results after simulation.
        
        Args:
            strategy_type: Type of strategy simulated
            
        Returns:
            Dictionary with performance metrics
        """
        final_balance = self.cash_balance_usd
        total_invested = sum(
            trade.amount_usd for trade in self.trades if trade.side == 'BUY'
        )
        total_fees = sum(trade.fee_usd for trade in self.trades)
        
        # Calculate return
        profit_loss = final_balance - self.initial_balance_usd
        return_percent = (
            (profit_loss / self.initial_balance_usd * Decimal('100'))
            if self.initial_balance_usd > 0
            else Decimal('0')
        )
        
        # Calculate average entry price
        total_tokens_bought = sum(
            trade.tokens_received for trade in self.trades if trade.side == 'BUY'
        )
        avg_entry_price = (
            (total_invested / total_tokens_bought)
            if total_tokens_bought > 0
            else Decimal('0')
        )
        
        # Count trades
        num_buys = sum(1 for trade in self.trades if trade.side == 'BUY')
        num_sells = sum(1 for trade in self.trades if trade.side == 'SELL')
        
        return {
            'strategy_type': strategy_type,
            'initial_balance_usd': str(self.initial_balance_usd),
            'final_balance_usd': str(final_balance),
            'profit_loss_usd': str(profit_loss),
            'return_percent': str(return_percent.quantize(Decimal('0.01'))),
            'total_invested_usd': str(total_invested),
            'total_fees_usd': str(total_fees),
            'avg_entry_price': str(avg_entry_price.quantize(Decimal('0.00000001'))),
            'num_trades': len(self.trades),
            'num_buys': num_buys,
            'num_sells': num_sells,
            'trades': [trade.to_dict() for trade in self.trades],
        }
    
    def _reset_portfolio(self) -> None:
        """Reset portfolio to initial state."""
        self.cash_balance_usd = self.initial_balance_usd
        self.token_balance = Decimal('0')
        self.trades = []