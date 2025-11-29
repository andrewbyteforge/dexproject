"""
Backtesting Engine - Core Orchestrator

Main entry point for backtesting strategies. Orchestrates:
1. Historical data fetching
2. Strategy simulation
3. Performance metrics calculation
4. Results storage

Phase 7B - Day 12: Backtesting Engine

File: dexproject/paper_trading/backtesting/engine.py
"""

import logging
from decimal import Decimal
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from django.utils import timezone

from paper_trading.backtesting.data_fetcher import HistoricalDataFetcher
from paper_trading.backtesting.simulator import StrategySimulator
from paper_trading.backtesting.metrics import PerformanceMetricsCalculator
from paper_trading.constants import StrategyType


logger = logging.getLogger(__name__)


# =============================================================================
# BACKTESTING ENGINE
# =============================================================================

class BacktestEngine:
    """
    Main backtesting engine that orchestrates the entire backtest process.
    
    Features:
    - Fetches historical data
    - Simulates strategy execution
    - Calculates performance metrics
    - Validates inputs
    - Handles errors gracefully
    
    Example:
        engine = BacktestEngine()
        
        result = engine.run_backtest(
            strategy_type='DCA',
            token_symbol='ETH',
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
            initial_balance_usd=Decimal('10000'),
            strategy_params={
                'total_amount_usd': '1000',
                'num_intervals': 10
            }
        )
    """
    
    def __init__(self) -> None:
        """Initialize the backtesting engine."""
        self.data_fetcher = HistoricalDataFetcher()
        self.metrics_calculator = PerformanceMetricsCalculator()
        
        logger.info("[BACKTEST] BacktestEngine initialized")
    
    # =========================================================================
    # PUBLIC METHODS
    # =========================================================================
    
    def run_backtest(
        self,
        strategy_type: str,
        token_symbol: str,
        start_date: datetime,
        end_date: datetime,
        initial_balance_usd: Decimal,
        strategy_params: Dict[str, Any],
        interval: str = '1h',
        fee_percent: Decimal = Decimal('0.3')
    ) -> Optional[Dict[str, Any]]:
        """
        Run a complete backtest for a strategy.
        
        Args:
            strategy_type: Strategy type ('SPOT', 'DCA', 'GRID', 'TWAP', 'VWAP')
            token_symbol: Token symbol to backtest
            start_date: Start date for backtest
            end_date: End date for backtest
            initial_balance_usd: Starting balance
            strategy_params: Strategy-specific parameters
            interval: Data interval (default '1h')
            fee_percent: Trading fee % (default 0.3%)
            
        Returns:
            Dictionary with backtest results and metrics, or None if failed
        """
        try:
            logger.info(
                f"[BACKTEST] Starting backtest: {strategy_type} strategy "
                f"on {token_symbol} from {start_date.date()} to {end_date.date()}"
            )
            
            # Validate inputs
            validation_error = self._validate_inputs(
                strategy_type=strategy_type,
                token_symbol=token_symbol,
                start_date=start_date,
                end_date=end_date,
                initial_balance_usd=initial_balance_usd,
                strategy_params=strategy_params
            )
            
            if validation_error:
                logger.error(f"[BACKTEST] Validation failed: {validation_error}")
                return {
                    'success': False,
                    'error': validation_error,
                    'strategy_type': strategy_type,
                    'token_symbol': token_symbol,
                }
            
            # Step 1: Fetch historical data
            logger.info(f"[BACKTEST] Step 1: Fetching historical data for {token_symbol}")
            historical_data = self.data_fetcher.fetch_historical_data(
                token_symbol=token_symbol,
                start_date=start_date,
                end_date=end_date,
                interval=interval
            )
            
            if historical_data is None or historical_data.empty:
                error_msg = f"No historical data available for {token_symbol}"
                logger.error(f"[BACKTEST] {error_msg}")
                return {
                    'success': False,
                    'error': error_msg,
                    'strategy_type': strategy_type,
                    'token_symbol': token_symbol,
                }
            
            logger.info(
                f"[BACKTEST] ✅ Fetched {len(historical_data)} data points"
            )
            
            # Step 2: Simulate strategy
            logger.info(f"[BACKTEST] Step 2: Simulating {strategy_type} strategy")
            simulator = StrategySimulator(
                initial_balance_usd=initial_balance_usd,
                fee_percent=fee_percent
            )
            
            simulation_results = self._run_simulation(
                simulator=simulator,
                strategy_type=strategy_type,
                historical_data=historical_data,
                strategy_params=strategy_params
            )
            
            if simulation_results is None:
                error_msg = f"Strategy simulation failed for {strategy_type}"
                logger.error(f"[BACKTEST] {error_msg}")
                return {
                    'success': False,
                    'error': error_msg,
                    'strategy_type': strategy_type,
                    'token_symbol': token_symbol,
                }
            
            logger.info(
                f"[BACKTEST] ✅ Simulation complete: "
                f"{simulation_results['num_trades']} trades executed"
            )
            
            # Step 3: Calculate metrics
            logger.info("[BACKTEST] Step 3: Calculating performance metrics")
            metrics = self.metrics_calculator.calculate_metrics(
                simulation_results=simulation_results,
                risk_free_rate=Decimal('2.0')  # 2% annual risk-free rate
            )
            
            logger.info(
                f"[BACKTEST] ✅ Metrics calculated: "
                f"Return {metrics['return_percent']}%, "
                f"Sharpe {metrics['sharpe_ratio']}"
            )
            
            # Step 4: Build final result
            result = {
                'success': True,
                'strategy_type': strategy_type,
                'token_symbol': token_symbol,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'interval': interval,
                'data_points': len(historical_data),
                'simulation_results': simulation_results,
                'metrics': metrics,
                'timestamp': timezone.now().isoformat(),
            }
            
            logger.info(
                f"[BACKTEST] 🎉 Backtest complete for {strategy_type} on {token_symbol}: "
                f"Return {metrics['return_percent']}%"
            )
            
            return result
            
        except Exception as e:
            logger.error(
                f"[BACKTEST] Unexpected error during backtest: {e}",
                exc_info=True
            )
            return {
                'success': False,
                'error': str(e),
                'strategy_type': strategy_type,
                'token_symbol': token_symbol,
            }
    
    def run_multiple_backtests(
        self,
        strategy_types: List[str],
        token_symbol: str,
        start_date: datetime,
        end_date: datetime,
        initial_balance_usd: Decimal,
        strategy_params_list: List[Dict[str, Any]],
        interval: str = '1h'
    ) -> List[Dict[str, Any]]:
        """
        Run multiple backtests for comparison.
        
        Args:
            strategy_types: List of strategy types to test
            token_symbol: Token to backtest
            start_date: Start date
            end_date: End date
            initial_balance_usd: Starting balance
            strategy_params_list: List of strategy params (one per strategy)
            interval: Data interval
            
        Returns:
            List of backtest results
        """
        results: List[Dict[str, Any]] = []
        
        logger.info(
            f"[BACKTEST] Running {len(strategy_types)} backtests on {token_symbol}"
        )
        
        for i, strategy_type in enumerate(strategy_types):
            strategy_params = strategy_params_list[i] if i < len(strategy_params_list) else {}
            
            result = self.run_backtest(
                strategy_type=strategy_type,
                token_symbol=token_symbol,
                start_date=start_date,
                end_date=end_date,
                initial_balance_usd=initial_balance_usd,
                strategy_params=strategy_params,
                interval=interval
            )
            
            if result:
                results.append(result)
        
        logger.info(
            f"[BACKTEST] Completed {len(results)} backtests"
        )
        
        return results
    
    def compare_strategies(
        self,
        backtest_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Compare multiple backtest results and rank by performance.
        
        Args:
            backtest_results: List of backtest result dictionaries
            
        Returns:
            Dictionary with comparison and rankings
        """
        if not backtest_results:
            return {
                'num_strategies': 0,
                'rankings': [],
                'best_strategy': None,
            }
        
        # Extract key metrics for comparison
        comparisons: List[Dict[str, Any]] = []
        
        for result in backtest_results:
            if not result.get('success'):
                continue
            
            metrics = result.get('metrics', {})
            
            comparisons.append({
                'strategy_type': result['strategy_type'],
                'return_percent': Decimal(metrics.get('return_percent', '0')),
                'win_rate_percent': Decimal(metrics.get('win_rate_percent', '0')),
                'sharpe_ratio': Decimal(metrics.get('sharpe_ratio', '0')),
                'max_drawdown_percent': Decimal(metrics.get('max_drawdown_percent', '0')),
                'num_trades': metrics.get('num_trades', 0),
            })
        
        # Sort by return %
        comparisons_sorted = sorted(
            comparisons,
            key=lambda x: x['return_percent'],
            reverse=True
        )
        
        # Build rankings
        rankings = []
        for i, comp in enumerate(comparisons_sorted):
            rankings.append({
                'rank': i + 1,
                'strategy_type': comp['strategy_type'],
                'return_percent': str(comp['return_percent']),
                'win_rate_percent': str(comp['win_rate_percent']),
                'sharpe_ratio': str(comp['sharpe_ratio']),
                'max_drawdown_percent': str(comp['max_drawdown_percent']),
                'num_trades': comp['num_trades'],
            })
        
        best_strategy = rankings[0] if rankings else None
        
        logger.info(
            f"[BACKTEST] Strategy comparison complete: "
            f"Best = {best_strategy['strategy_type'] if best_strategy else 'None'}"
        )
        
        return {
            'num_strategies': len(rankings),
            'rankings': rankings,
            'best_strategy': best_strategy,
            'timestamp': timezone.now().isoformat(),
        }
    
    # =========================================================================
    # PRIVATE METHODS - Simulation
    # =========================================================================
    
    def _run_simulation(
        self,
        simulator: StrategySimulator,
        strategy_type: str,
        historical_data: Any,
        strategy_params: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Run the appropriate simulation based on strategy type.
        
        Args:
            simulator: StrategySimulator instance
            strategy_type: Strategy type
            historical_data: Historical price data
            strategy_params: Strategy parameters
            
        Returns:
            Simulation results or None if failed
        """
        try:
            strategy_type_upper = strategy_type.upper()
            
            if strategy_type_upper == 'SPOT':
                return simulator.simulate_spot_strategy(
                    historical_data=historical_data,
                    buy_amount_usd=Decimal(str(strategy_params.get('buy_amount_usd', '1000'))),
                    entry_index=int(strategy_params.get('entry_index', 0)),
                    exit_index=strategy_params.get('exit_index')
                )
            
            elif strategy_type_upper == 'DCA':
                return simulator.simulate_dca_strategy(
                    historical_data=historical_data,
                    total_amount_usd=Decimal(str(strategy_params.get('total_amount_usd', '1000'))),
                    num_intervals=int(strategy_params.get('num_intervals', 10))
                )
            
            elif strategy_type_upper == 'GRID':
                return simulator.simulate_grid_strategy(
                    historical_data=historical_data,
                    total_amount_usd=Decimal(str(strategy_params.get('total_amount_usd', '1000'))),
                    num_grids=int(strategy_params.get('num_grids', 10)),
                    price_range_percent=Decimal(str(strategy_params.get('price_range_percent', '10')))
                )
            
            elif strategy_type_upper == 'TWAP':
                return simulator.simulate_twap_strategy(
                    historical_data=historical_data,
                    total_amount_usd=Decimal(str(strategy_params.get('total_amount_usd', '1000'))),
                    execution_window_hours=int(strategy_params.get('execution_window_hours', 6)),
                    num_intervals=int(strategy_params.get('num_intervals', 12))
                )
            
            elif strategy_type_upper == 'VWAP':
                return simulator.simulate_vwap_strategy(
                    historical_data=historical_data,
                    total_amount_usd=Decimal(str(strategy_params.get('total_amount_usd', '1000'))),
                    execution_window_hours=int(strategy_params.get('execution_window_hours', 6)),
                    num_intervals=int(strategy_params.get('num_intervals', 12))
                )
            
            else:
                logger.error(f"[BACKTEST] Unknown strategy type: {strategy_type}")
                return None
                
        except Exception as e:
            logger.error(
                f"[BACKTEST] Error running simulation for {strategy_type}: {e}",
                exc_info=True
            )
            return None
    
    # =========================================================================
    # PRIVATE METHODS - Validation
    # =========================================================================
    
    def _validate_inputs(
        self,
        strategy_type: str,
        token_symbol: str,
        start_date: datetime,
        end_date: datetime,
        initial_balance_usd: Decimal,
        strategy_params: Dict[str, Any]
    ) -> Optional[str]:
        """
        Validate backtest inputs.
        
        Args:
            strategy_type: Strategy type
            token_symbol: Token symbol
            start_date: Start date
            end_date: End date
            initial_balance_usd: Initial balance
            strategy_params: Strategy parameters
            
        Returns:
            Error message if invalid, None if valid
        """
        # Validate strategy type
        valid_strategies = ['SPOT', 'DCA', 'GRID', 'TWAP', 'VWAP']
        if strategy_type.upper() not in valid_strategies:
            return f"Invalid strategy type '{strategy_type}'. Valid: {valid_strategies}"
        
        # Validate token symbol
        from paper_trading.backtesting import YAHOO_TICKER_MAPPING
        if token_symbol not in YAHOO_TICKER_MAPPING:
            return f"Unsupported token '{token_symbol}'. Supported: {list(YAHOO_TICKER_MAPPING.keys())}"
        
        # Validate dates
        if start_date >= end_date:
            return f"start_date must be before end_date"
        
        if end_date > timezone.now():
            return "end_date cannot be in the future"
        
        days_diff = (end_date - start_date).days
        if days_diff < 7:
            return "Backtest period must be at least 7 days"
        
        if days_diff > 365:
            return "Backtest period cannot exceed 365 days"
        
        # Validate initial balance
        if initial_balance_usd <= Decimal('0'):
            return "initial_balance_usd must be positive"
        
        if initial_balance_usd > Decimal('1000000'):
            return "initial_balance_usd cannot exceed $1,000,000"
        
        # Validate strategy-specific parameters
        strategy_type_upper = strategy_type.upper()
        
        if strategy_type_upper in ['DCA', 'TWAP', 'VWAP']:
            if 'total_amount_usd' not in strategy_params:
                return f"{strategy_type} requires 'total_amount_usd' parameter"
            
            total_amount = Decimal(str(strategy_params['total_amount_usd']))
            if total_amount > initial_balance_usd:
                return "total_amount_usd cannot exceed initial_balance_usd"
        
        if strategy_type_upper in ['DCA', 'TWAP', 'VWAP']:
            if 'num_intervals' not in strategy_params:
                return f"{strategy_type} requires 'num_intervals' parameter"
            
            num_intervals = int(strategy_params['num_intervals'])
            if num_intervals < 2:
                return "num_intervals must be at least 2"
            
            if num_intervals > 100:
                return "num_intervals cannot exceed 100"
        
        if strategy_type_upper == 'GRID':
            if 'num_grids' not in strategy_params:
                return "GRID requires 'num_grids' parameter"
            
            num_grids = int(strategy_params['num_grids'])
            if num_grids < 3:
                return "num_grids must be at least 3"
            
            if num_grids > 50:
                return "num_grids cannot exceed 50"
        
        # All validations passed
        return None