"""
Paper Trading Auto-Trader Bot Core

Main bot logic for automated paper trading with mempool monitoring
and strategy execution.

File: dexproject/paper_trading/bot/auto_trader.py
"""

import logging
import asyncio
import time
import random
from typing import Dict, Any, Optional, List, Tuple
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
import uuid

from django.utils import timezone as django_timezone
from django.db import transaction
from django.core.cache import cache
from asgiref.sync import sync_to_async

from paper_trading.models import (
    PaperTradingAccount,
    PaperTrade,
    PaperPosition,
    PaperTradingConfig,
    PaperAIThoughtLog,
    PaperStrategyConfiguration,
    PaperTradingSession,
    PaperPerformanceMetrics
)

logger = logging.getLogger(__name__)


@dataclass
class TradingSignal:
    """Represents a trading signal from market analysis."""
    
    signal_type: str  # 'BUY', 'SELL', 'HOLD'
    token_address: str
    token_symbol: str
    confidence: Decimal
    risk_score: Decimal
    opportunity_score: Decimal
    suggested_amount_usd: Decimal
    lane: str  # 'FAST' or 'SMART'
    reasoning: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BotState:
    """Current state of the trading bot."""
    
    is_running: bool = False
    is_paused: bool = False
    session: Optional[PaperTradingSession] = None
    account: Optional[PaperTradingAccount] = None
    strategy_config: Optional[PaperStrategyConfiguration] = None
    trades_today: int = 0
    last_trade_time: Optional[datetime] = None
    error_count: int = 0
    start_time: Optional[datetime] = None


class PaperTradingBot:
    """
    Automated paper trading bot with strategy execution.
    
    Features:
    - Market monitoring
    - Signal generation
    - Strategy execution
    - Risk management
    - Performance tracking
    """
    
    def __init__(self, account_id: str, strategy_config_id: Optional[str] = None):
        """
        Initialize the paper trading bot.
        
        Args:
            account_id: UUID of the paper trading account
            strategy_config_id: Optional UUID of strategy configuration
        """
        self.account_id = account_id
        self.strategy_config_id = strategy_config_id
        self.state = BotState()
        self.logger = logging.getLogger(f'paper_bot.{account_id[:8]}')
        
        # Trading parameters
        self.check_interval = 30  # seconds between market checks
        self.min_confidence = Decimal('60')  # minimum confidence for trades
        self.max_risk_score = Decimal('70')  # maximum acceptable risk
        
        # Initialize components
        self._load_configuration()
    
    def _load_configuration(self):
        """Load account and strategy configuration."""
        try:
            # Load account
            self.state.account = PaperTradingAccount.objects.get(
                account_id=self.account_id
            )
            
            # Load or create strategy config
            if self.strategy_config_id:
                self.state.strategy_config = PaperStrategyConfiguration.objects.get(
                    config_id=self.strategy_config_id
                )
            else:
                # Use the first active strategy or create default
                self.state.strategy_config = PaperStrategyConfiguration.objects.filter(
                    account=self.state.account,
                    is_active=True
                ).first()
                
                if not self.state.strategy_config:
                    self.state.strategy_config = self._create_default_strategy()
            
            # Update parameters from config
            if self.state.strategy_config:
                self.min_confidence = self.state.strategy_config.confidence_threshold
                self.max_risk_score = Decimal('100') - self.min_confidence
                
            self.logger.info(f"Loaded configuration for {self.state.account.name}")
            
        except Exception as e:
            self.logger.error(f"Failed to load configuration: {e}")
            raise
    
    def _create_default_strategy(self) -> PaperStrategyConfiguration:
        """Create a default strategy configuration."""
        return PaperStrategyConfiguration.objects.create(
            account=self.state.account,
            name="Default Auto-Trading Strategy",
            trading_mode='MODERATE',
            use_fast_lane=True,
            use_smart_lane=False,
            confidence_threshold=Decimal('60'),
            max_position_size_percent=Decimal('5'),
            stop_loss_percent=Decimal('5'),
            take_profit_percent=Decimal('10'),
            max_daily_trades=20
        )
    
    async def start(self):
        """Start the trading bot."""
        if self.state.is_running:
            self.logger.warning("Bot is already running")
            return
        
        self.logger.info("Starting paper trading bot...")
        
        try:
            # Create new session (using sync_to_async for Django ORM)
            self.state.session = await sync_to_async(PaperTradingSession.objects.create)(
                account=self.state.account,
                strategy_config=self.state.strategy_config,
                name=f"Auto-Trading Session {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                status='STARTING',
                starting_balance_usd=self.state.account.current_balance_usd,
                config_snapshot=self._get_config_snapshot()
            )
            
            self.state.is_running = True
            self.state.start_time = datetime.now(timezone.utc)
            self.state.session.status = 'RUNNING'
            await sync_to_async(self.state.session.save)()
            
            self.logger.info(f"Bot started with session {self.state.session.session_id}")
            
            # Start main trading loop
            await self._trading_loop()
            
        except Exception as e:
            self.logger.error(f"Failed to start bot: {e}")
            self._handle_error(str(e))
            raise
    
    async def _trading_loop(self):
        """Main trading loop."""
        while self.state.is_running:
            try:
                if not self.state.is_paused:
                    # Update heartbeat
                    if self.state.session:
                        await sync_to_async(self.state.session.update_heartbeat)()
                    
                    # Check for trading opportunities
                    await self._check_trading_opportunities()
                    
                    # Update positions
                    await self._update_positions()
                    
                    # Check stop losses and take profits
                    await self._check_exit_conditions()
                    
                    # Calculate and save metrics periodically
                    if random.random() < 0.1:  # 10% chance each cycle
                        await self._calculate_metrics()
                
                # Wait before next check
                await asyncio.sleep(self.check_interval)
                
            except Exception as e:
                self.logger.error(f"Error in trading loop: {e}")
                await sync_to_async(self._handle_error)(str(e))
                
                if self.state.error_count > 10:
                    self.logger.critical("Too many errors, stopping bot")
                    await self.stop("Too many errors")
                    break
    
    async def _check_trading_opportunities(self):
        """Check for trading opportunities and execute trades."""
        # Check daily trade limit
        if self.state.trades_today >= self.state.strategy_config.max_daily_trades:
            return
        
        # Generate trading signals (simplified for paper trading)
        signals = await self._generate_signals()
        
        for signal in signals:
            if await self._should_execute_trade(signal):
                await self._execute_paper_trade(signal)
    
    async def _generate_signals(self) -> List[TradingSignal]:
        """
        Generate trading signals from market analysis.
        
        This is a simplified version for paper trading.
        In production, this would integrate with mempool monitoring
        and real market analysis.
        """
        signals = []
        
        # Simulate signal generation
        if random.random() < 0.1:  # 10% chance of signal
            # Generate random signal for testing
            signal_type = random.choice(['BUY', 'SELL'])
            
            # Popular tokens for simulation
            tokens = [
                ('0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48', 'USDC'),
                ('0xdAC17F958D2ee523a2206206994597C13D831ec7', 'USDT'),
                ('0x514910771AF9Ca656af840dff83E8264EcF986CA', 'LINK'),
                ('0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984', 'UNI'),
            ]
            
            token_address, token_symbol = random.choice(tokens)
            
            signal = TradingSignal(
                signal_type=signal_type,
                token_address=token_address,
                token_symbol=token_symbol,
                confidence=Decimal(str(random.uniform(50, 95))),
                risk_score=Decimal(str(random.uniform(20, 80))),
                opportunity_score=Decimal(str(random.uniform(40, 90))),
                suggested_amount_usd=Decimal(str(random.uniform(50, 500))),
                lane='FAST' if random.random() < 0.7 else 'SMART',
                reasoning=f"Market conditions favorable for {signal_type}",
                metadata={
                    'price': random.uniform(0.5, 100),
                    'volume_24h': random.uniform(100000, 10000000),
                    'liquidity': random.uniform(50000, 5000000)
                }
            )
            
            signals.append(signal)
        
        return signals
    
    async def _should_execute_trade(self, signal: TradingSignal) -> bool:
        """Determine if a trade should be executed based on the signal."""
        # Check confidence threshold
        if signal.confidence < self.min_confidence:
            return False
        
        # Check risk threshold
        if signal.risk_score > self.max_risk_score:
            return False
        
        # Check position limits
        open_positions = PaperPosition.objects.filter(
            account=self.state.account,
            is_open=True
        ).count()
        
        if open_positions >= self.state.strategy_config.max_concurrent_positions:
            return False
        
        # Check account balance
        if signal.suggested_amount_usd > self.state.account.current_balance_usd * self.state.strategy_config.max_position_size_percent / 100:
            # Adjust amount to fit position size limit
            signal.suggested_amount_usd = self.state.account.current_balance_usd * self.state.strategy_config.max_position_size_percent / 100
        
        return True
    
    @transaction.atomic
    async def _execute_paper_trade(self, signal: TradingSignal):
        """Execute a paper trade based on the signal."""
        try:
            # Create trade record
            trade = PaperTrade.objects.create(
                account=self.state.account,
                trade_type='buy' if signal.signal_type == 'BUY' else 'sell',
                token_in_address='0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',  # WETH
                token_in_symbol='WETH',
                token_out_address=signal.token_address,
                token_out_symbol=signal.token_symbol,
                amount_in=Decimal('0.1'),  # Simplified
                amount_in_usd=signal.suggested_amount_usd,
                expected_amount_out=signal.suggested_amount_usd / signal.metadata.get('price', 1),
                simulated_gas_price_gwei=Decimal(str(random.uniform(20, 50))),
                simulated_gas_used=random.randint(100000, 200000),
                simulated_gas_cost_usd=Decimal(str(random.uniform(5, 20))),
                simulated_slippage_percent=Decimal(str(random.uniform(0.1, 1.0))),
                status='executing',
                strategy_name=self.state.strategy_config.name
            )
            
            # Simulate execution delay
            await asyncio.sleep(random.uniform(0.5, 2.0))
            
            # Calculate actual amounts with slippage
            slippage_factor = 1 - (trade.simulated_slippage_percent / 100)
            trade.actual_amount_out = trade.expected_amount_out * slippage_factor
            trade.status = 'completed'
            trade.executed_at = django_timezone.now()
            trade.execution_time_ms = random.randint(200, 1000)
            trade.mock_tx_hash = f"0x{''.join(random.choices('0123456789abcdef', k=64))}"
            trade.mock_block_number = random.randint(10000000, 10010000)
            trade.save()
            
            # Create AI thought log
            thought_log = PaperAIThoughtLog.objects.create(
                account=self.state.account,
                paper_trade=trade,
                decision_type=signal.signal_type,
                token_address=signal.token_address,
                token_symbol=signal.token_symbol,
                confidence_level=self._get_confidence_level(signal.confidence),
                confidence_percent=signal.confidence,
                risk_score=signal.risk_score,
                opportunity_score=signal.opportunity_score,
                primary_reasoning=signal.reasoning,
                key_factors=[
                    f"Confidence: {signal.confidence:.1f}%",
                    f"Risk: {signal.risk_score:.1f}",
                    f"Opportunity: {signal.opportunity_score:.1f}"
                ],
                positive_signals=["Market momentum", "Good liquidity"],
                negative_signals=[f"Risk score: {signal.risk_score:.1f}"],
                market_data=signal.metadata,
                strategy_name=self.state.strategy_config.name,
                lane_used=signal.lane,
                analysis_time_ms=random.randint(50, 500)
            )
            
            # Update position
            if signal.signal_type == 'BUY':
                await self._update_or_create_position(trade)
            
            # Update account statistics
            self.state.account.total_trades += 1
            self.state.account.successful_trades += 1
            self.state.account.total_fees_paid_usd += trade.simulated_gas_cost_usd
            self.state.account.current_balance_usd -= (trade.amount_in_usd + trade.simulated_gas_cost_usd)
            self.state.account.save()
            
            # Update session statistics
            if self.state.session:
                self.state.session.total_trades_executed += 1
                self.state.session.successful_trades += 1
                self.state.session.save()
            
            # Update bot state
            self.state.trades_today += 1
            self.state.last_trade_time = datetime.now(timezone.utc)
            
            self.logger.info(
                f"Executed {signal.signal_type} trade for {signal.token_symbol}: "
                f"${signal.suggested_amount_usd:.2f} (confidence: {signal.confidence:.1f}%)"
            )
            
        except Exception as e:
            self.logger.error(f"Failed to execute trade: {e}")
            self._handle_error(str(e))
    
    async def _update_or_create_position(self, trade: PaperTrade):
        """Update or create a position after a buy trade."""
        try:
            position, created = PaperPosition.objects.get_or_create(
                account=self.state.account,
                token_address=trade.token_out_address,
                is_open=True,
                defaults={
                    'token_symbol': trade.token_out_symbol,
                    'quantity': trade.actual_amount_out,
                    'average_entry_price_usd': Decimal('1.0'),
                    'total_invested_usd': trade.amount_in_usd
                }
            )
            
            if not created:
                # Update existing position
                total_quantity = position.quantity + trade.actual_amount_out
                total_invested = position.total_invested_usd + trade.amount_in_usd
                position.quantity = total_quantity
                position.total_invested_usd = total_invested
                position.average_entry_price_usd = total_invested / total_quantity if total_quantity > 0 else Decimal('1.0')
                position.save()
            
            # Set stop loss and take profit
            if self.state.strategy_config:
                position.stop_loss_price = position.average_entry_price_usd * (1 - self.state.strategy_config.stop_loss_percent / 100)
                position.take_profit_price = position.average_entry_price_usd * (1 + self.state.strategy_config.take_profit_percent / 100)
                position.save()
            
        except Exception as e:
            self.logger.error(f"Failed to update position: {e}")
    
    async def _update_positions(self):
        """Update current prices and P&L for open positions."""
        open_positions = PaperPosition.objects.filter(
            account=self.state.account,
            is_open=True
        )
        
        for position in open_positions:
            # Simulate price changes
            price_change = random.uniform(-0.05, 0.05)  # ±5% price change
            new_price = position.current_price_usd or position.average_entry_price_usd
            new_price = new_price * Decimal(str(1 + price_change))
            position.update_price(new_price)
    
    async def _check_exit_conditions(self):
        """Check for stop loss and take profit conditions."""
        open_positions = PaperPosition.objects.filter(
            account=self.state.account,
            is_open=True
        )
        
        for position in open_positions:
            should_exit = False
            exit_reason = ""
            
            # Check stop loss
            if position.stop_loss_price and position.current_price_usd:
                if position.current_price_usd <= position.stop_loss_price:
                    should_exit = True
                    exit_reason = "Stop loss triggered"
            
            # Check take profit
            if position.take_profit_price and position.current_price_usd:
                if position.current_price_usd >= position.take_profit_price:
                    should_exit = True
                    exit_reason = "Take profit triggered"
            
            if should_exit:
                await self._close_position(position, exit_reason)
    
    async def _close_position(self, position: PaperPosition, reason: str):
        """Close a position and record the trade."""
        try:
            # Create sell trade
            trade = PaperTrade.objects.create(
                account=self.state.account,
                trade_type='sell',
                token_in_address=position.token_address,
                token_in_symbol=position.token_symbol,
                token_out_address='0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',  # WETH
                token_out_symbol='WETH',
                amount_in=position.quantity,
                amount_in_usd=position.current_value_usd or position.total_invested_usd,
                expected_amount_out=position.quantity * position.current_price_usd,
                actual_amount_out=position.quantity * position.current_price_usd * Decimal('0.995'),  # 0.5% slippage
                simulated_gas_price_gwei=Decimal(str(random.uniform(20, 50))),
                simulated_gas_used=random.randint(100000, 200000),
                simulated_gas_cost_usd=Decimal(str(random.uniform(5, 20))),
                simulated_slippage_percent=Decimal('0.5'),
                status='completed',
                executed_at=django_timezone.now(),
                execution_time_ms=random.randint(200, 1000),
                strategy_name=self.state.strategy_config.name,
                mock_tx_hash=f"0x{''.join(random.choices('0123456789abcdef', k=64))}"
            )
            
            # Close the position
            position.close_position(position.current_price_usd)
            
            # Update account
            realized_pnl = position.realized_pnl_usd - trade.simulated_gas_cost_usd
            self.state.account.current_balance_usd += position.current_value_usd - trade.simulated_gas_cost_usd
            self.state.account.total_pnl_usd += realized_pnl
            self.state.account.save()
            
            self.logger.info(f"Closed position {position.token_symbol}: {reason} (P&L: ${realized_pnl:.2f})")
            
        except Exception as e:
            self.logger.error(f"Failed to close position: {e}")
    
    async def _calculate_metrics(self):
        """Calculate and save performance metrics."""
        if not self.state.session:
            return
        
        try:
            # Calculate metrics for the last hour
            period_start = django_timezone.now() - timedelta(hours=1)
            period_end = django_timezone.now()
            
            # Get trades in period
            trades = PaperTrade.objects.filter(
                account=self.state.account,
                created_at__gte=period_start,
                created_at__lte=period_end
            )
            
            if not trades.exists():
                return
            
            # Calculate statistics
            total_trades = trades.count()
            winning_trades = trades.filter(status='completed').count()
            losing_trades = total_trades - winning_trades
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else Decimal('0')
            
            # Create metrics record
            PaperPerformanceMetrics.objects.create(
                session=self.state.session,
                period_start=period_start,
                period_end=period_end,
                total_trades=total_trades,
                winning_trades=winning_trades,
                losing_trades=losing_trades,
                win_rate=win_rate,
                total_pnl_usd=self.state.account.total_pnl_usd,
                total_gas_fees_usd=self.state.account.total_fees_paid_usd,
                fast_lane_trades=trades.filter(strategy_name__icontains='fast').count(),
                smart_lane_trades=trades.filter(strategy_name__icontains='smart').count()
            )
            
        except Exception as e:
            self.logger.error(f"Failed to calculate metrics: {e}")
    
    def _get_confidence_level(self, confidence: Decimal) -> str:
        """Get confidence level category from percentage."""
        if confidence >= 90:
            return 'VERY_HIGH'
        elif confidence >= 70:
            return 'HIGH'
        elif confidence >= 50:
            return 'MEDIUM'
        elif confidence >= 30:
            return 'LOW'
        else:
            return 'VERY_LOW'
    
    def _get_config_snapshot(self) -> Dict[str, Any]:
        """Get current configuration as a snapshot."""
        if not self.state.strategy_config:
            return {}
        
        return {
            'trading_mode': self.state.strategy_config.trading_mode,
            'use_fast_lane': self.state.strategy_config.use_fast_lane,
            'use_smart_lane': self.state.strategy_config.use_smart_lane,
            'confidence_threshold': float(self.state.strategy_config.confidence_threshold),
            'max_position_size_percent': float(self.state.strategy_config.max_position_size_percent),
            'stop_loss_percent': float(self.state.strategy_config.stop_loss_percent),
            'take_profit_percent': float(self.state.strategy_config.take_profit_percent),
            'max_daily_trades': self.state.strategy_config.max_daily_trades
        }
    
    def _handle_error(self, error_message: str):
        """Handle errors and update session."""
        self.state.error_count += 1
        
        if self.state.session:
            self.state.session.error_count += 1
            self.state.session.last_error_message = error_message
            self.state.session.last_error_time = django_timezone.now()
            self.state.session.save()
    
    async def pause(self):
        """Pause the trading bot."""
        self.state.is_paused = True
        if self.state.session:
            self.state.session.status = 'PAUSED'
            self.state.session.save()
        self.logger.info("Bot paused")
    
    async def resume(self):
        """Resume the trading bot."""
        self.state.is_paused = False
        if self.state.session:
            self.state.session.status = 'RUNNING'
            self.state.session.save()
        self.logger.info("Bot resumed")
    
    async def stop(self, reason: str = ""):
        """Stop the trading bot."""
        self.state.is_running = False
        
        if self.state.session:
            self.state.session.stop_session(reason)
            
            # Update final statistics
            self.state.session.ending_balance_usd = self.state.account.current_balance_usd
            self.state.session.session_pnl_usd = (
                self.state.session.ending_balance_usd - 
                self.state.session.starting_balance_usd
            )
            self.state.session.save()
        
        self.logger.info(f"Bot stopped: {reason}")