"""
Enhanced Simple Paper Trading Bot with More Activity

File: paper_trading/bot/simple_trader.py
"""

import logging
import time
import random
from typing import Optional, Dict, Any
from decimal import Decimal
from datetime import datetime

from django.utils import timezone as django_timezone
from django.db import transaction

from paper_trading.models import (
    PaperTradingAccount,
    PaperTrade,
    PaperStrategyConfiguration,
    PaperTradingSession,
    PaperAIThoughtLog,
    PaperPosition
)

logger = logging.getLogger(__name__)


class SimplePaperBot:
    """Enhanced paper trading bot with more activity."""
    
    def __init__(self, account_id: str, strategy_config_id: Optional[str] = None):
        """Initialize the bot."""
        self.account_id = account_id
        self.strategy_config_id = strategy_config_id
        self.is_running = False
        self.is_paused = False
        self.session = None
        self.account = None
        self.strategy_config = None
        self.check_interval = 10  # Reduced to 10 seconds for more activity
        self.trades_today = 0
        self.cycle_count = 0
        self.error_count = 0
        self.logger = logging.getLogger(f'paper_bot.{account_id[:8]}')
        
        # Load configuration
        self._load_configuration()
    
    def _load_configuration(self):
        """Load account and strategy configuration."""
        try:
            self.account = PaperTradingAccount.objects.get(
                account_id=self.account_id
            )
            
            if self.strategy_config_id:
                self.strategy_config = PaperStrategyConfiguration.objects.get(
                    config_id=self.strategy_config_id
                )
            else:
                self.strategy_config = PaperStrategyConfiguration.objects.filter(
                    account=self.account,
                    is_active=True
                ).first()
                
                if not self.strategy_config:
                    self.strategy_config = self._create_default_strategy()
            
            self.logger.info(f"[OK] Loaded config for {self.account.name}")
            self.logger.info(f"   Balance: ${self.account.current_balance_usd:.2f}")
            self.logger.info(f"   Strategy: {self.strategy_config.name if self.strategy_config else 'Default'}")
            
        except Exception as e:
            self.logger.error(f"[ERROR] Failed to load config: {e}")
            raise
    
    def _create_default_strategy(self):
        """Create default strategy."""
        return PaperStrategyConfiguration.objects.create(
            account=self.account,
            name="Default Trading Strategy",
            trading_mode='MODERATE',
            use_fast_lane=True,
            confidence_threshold=Decimal('60')
        )
    
    def start(self):
        """Start the bot."""
        if self.is_running:
            return
        
        self.logger.info("=" * 60)
        self.logger.info(">>> STARTING PAPER TRADING BOT")
        self.logger.info("=" * 60)
        
        # Create session
        self.session = PaperTradingSession.objects.create(
            account=self.account,
            strategy_config=self.strategy_config,
            name=f"Bot Session {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            status='RUNNING',
            starting_balance_usd=self.account.current_balance_usd,
            config_snapshot=self._get_config_snapshot()
        )
        
        self.is_running = True
        self.logger.info(f"[INFO] Session ID: {self.session.session_id}")
        self.logger.info(f"[INFO] Check Interval: {self.check_interval} seconds")
        self.logger.info(f"[INFO] Starting Balance: ${self.account.current_balance_usd:.2f}")
        self.logger.info("-" * 60)
        
        # Run trading loop
        self._run_trading_loop()
    
    def _run_trading_loop(self):
        """Main trading loop."""
        while self.is_running:
            try:
                self.cycle_count += 1
                
                if not self.is_paused:
                    self.logger.info(f"\n>>> CYCLE #{self.cycle_count} - {datetime.now().strftime('%H:%M:%S')}")
                    self.logger.info("-" * 40)
                    
                    # Update heartbeat
                    if self.session:
                        self.session.update_heartbeat()
                    
                    # Check for trading opportunities (higher probability for demo)
                    opportunity_found = self._check_trading_opportunities()
                    
                    # Update positions
                    self._update_positions()
                    
                    # Check exit conditions
                    self._check_exit_conditions()
                    
                    # Display status
                    self._display_status()
                
                # Wait before next check
                self.logger.info(f"   Waiting {self.check_interval} seconds...")
                time.sleep(self.check_interval)
                
            except KeyboardInterrupt:
                self.logger.info("\n\n[STOP] Shutdown signal received")
                break
            except Exception as e:
                self.logger.error(f"[ERROR] Error in trading loop: {e}")
                self.error_count += 1
                
                if self.error_count > 10:
                    self.logger.critical("Too many errors, stopping bot")
                    break
                
                time.sleep(5)
        
        self.stop("Trading loop ended")
    
    def _check_trading_opportunities(self) -> bool:
        """Check for trading opportunities."""
        # Check daily trade limit
        if self.trades_today >= 20:  # Hardcoded limit for simplicity
            self.logger.info("   [LIMIT] Daily trade limit reached")
            return False
        
        # Higher probability for demonstration (30% chance)
        if random.random() < 0.3:
            self.logger.info("   [SIGNAL] Trading opportunity detected!")
            self._execute_random_trade()
            return True
        else:
            self.logger.info("   [SCAN] No trading opportunities found")
            return False
    
    @transaction.atomic
    def _execute_random_trade(self):
        """Execute a random paper trade."""
        try:
            # Token selection
            tokens = [
                ('0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48', 'USDC'),
                ('0xdAC17F958D2ee523a2206206994597C13D831ec7', 'USDT'),
                ('0x514910771AF9Ca656af840dff83E8264EcF986CA', 'LINK'),
                ('0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984', 'UNI'),
                ('0x6B175474E89094C44Da98b954EedeAC495271d0F', 'DAI'),
            ]
            
            token_address, token_symbol = random.choice(tokens)
            trade_type = 'buy' if random.random() > 0.3 else 'sell'  # 70% buy, 30% sell
            amount_usd = Decimal(str(random.uniform(100, 500)))
            
            self.logger.info(f"   [TRADE] Executing {trade_type.upper()} order:")
            self.logger.info(f"      Token: {token_symbol}")
            self.logger.info(f"      Amount: ${amount_usd:.2f}")
            
            # Create trade
            trade = PaperTrade.objects.create(
                account=self.account,
                trade_type=trade_type,
                token_in_address='0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',
                token_in_symbol='WETH',
                token_out_address=token_address,
                token_out_symbol=token_symbol,
                amount_in=Decimal('0.1'),
                amount_in_usd=amount_usd,
                expected_amount_out=amount_usd / Decimal(str(random.uniform(1, 100))),
                actual_amount_out=amount_usd / Decimal(str(random.uniform(1, 100))) * Decimal('0.995'),
                simulated_gas_price_gwei=Decimal(str(random.uniform(20, 50))),
                simulated_gas_used=random.randint(100000, 200000),
                simulated_gas_cost_usd=Decimal(str(random.uniform(5, 15))),
                simulated_slippage_percent=Decimal(str(random.uniform(0.1, 0.5))),
                status='completed',
                executed_at=django_timezone.now(),
                execution_time_ms=random.randint(200, 800),
                strategy_name=self.strategy_config.name if self.strategy_config else 'Default',
                mock_tx_hash=f"0x{''.join(random.choices('0123456789abcdef', k=64))}"
            )
            
            # Create AI thought log
            confidence = Decimal(str(random.uniform(60, 95)))
            PaperAIThoughtLog.objects.create(
                account=self.account,
                paper_trade=trade,
                decision_type='BUY' if trade_type == 'buy' else 'SELL',
                token_address=token_address,
                token_symbol=token_symbol,
                confidence_level=self._get_confidence_level(confidence),
                confidence_percent=confidence,
                risk_score=Decimal(str(random.uniform(20, 60))),
                opportunity_score=Decimal(str(random.uniform(50, 90))),
                primary_reasoning=f"Market analysis indicates {trade_type} opportunity",
                key_factors=["Technical signals", "Market momentum", "Volume analysis"],
                positive_signals=["Bullish trend", "Strong support"],
                negative_signals=["Market volatility"],
                strategy_name=self.strategy_config.name if self.strategy_config else 'Default',
                lane_used='FAST',
                analysis_time_ms=random.randint(50, 200)
            )
            
            # Update account
            self.account.total_trades += 1
            self.account.successful_trades += 1
            self.account.total_fees_paid_usd += trade.simulated_gas_cost_usd
            
            if trade_type == 'buy':
                self.account.current_balance_usd -= (trade.amount_in_usd + trade.simulated_gas_cost_usd)
            else:
                self.account.current_balance_usd += trade.amount_in_usd - trade.simulated_gas_cost_usd
            
            self.account.save()
            
            # Update session
            if self.session:
                self.session.total_trades_executed += 1
                self.session.successful_trades += 1
                self.session.session_pnl_usd = (
                    self.account.current_balance_usd - 
                    self.session.starting_balance_usd
                )
                self.session.save()
            
            self.trades_today += 1
            
            self.logger.info(f"   [SUCCESS] Trade executed successfully!")
            self.logger.info(f"      Confidence: {confidence:.1f}%")
            self.logger.info(f"      Gas Cost: ${trade.simulated_gas_cost_usd:.2f}")
            self.logger.info(f"      Slippage: {trade.simulated_slippage_percent:.2f}%")
            
        except Exception as e:
            self.logger.error(f"   [ERROR] Trade execution failed: {e}")
            self.error_count += 1
    
    def _update_positions(self):
        """Update open positions."""
        try:
            open_positions = PaperPosition.objects.filter(
                account=self.account,
                is_open=True
            ).count()
            
            if open_positions > 0:
                self.logger.info(f"   [UPDATE] Updating {open_positions} open position(s)")
                
                # Simulate price updates
                for position in PaperPosition.objects.filter(account=self.account, is_open=True):
                    if position.current_price_usd:
                        price_change = random.uniform(-0.02, 0.02)  # ±2%
                        new_price = position.current_price_usd * Decimal(str(1 + price_change))
                        position.update_price(new_price)
            
        except Exception as e:
            self.logger.error(f"   [ERROR] Failed to update positions: {e}")
    
    def _check_exit_conditions(self):
        """Check for stop loss and take profit."""
        # Simplified for now
        pass
    
    def _display_status(self):
        """Display current status."""
        self.logger.info("\n   [STATUS]:")
        self.logger.info(f"      Balance: ${self.account.current_balance_usd:.2f}")
        self.logger.info(f"      Trades Today: {self.trades_today}")
        self.logger.info(f"      Total Trades: {self.account.total_trades}")
        
        if self.session and self.session.session_pnl_usd:
            pnl = self.session.session_pnl_usd
            pnl_status = "[+]" if pnl >= 0 else "[-]"
            self.logger.info(f"      Session P&L: {pnl_status} ${pnl:.2f}")
    
    def _get_confidence_level(self, confidence: Decimal) -> str:
        """Get confidence level category."""
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
        """Get config snapshot."""
        if not self.strategy_config:
            return {}
        
        return {
            'trading_mode': self.strategy_config.trading_mode,
            'use_fast_lane': self.strategy_config.use_fast_lane,
            'use_smart_lane': self.strategy_config.use_smart_lane,
            'confidence_threshold': float(self.strategy_config.confidence_threshold),
            'max_daily_trades': self.strategy_config.max_daily_trades
        }
    
    def stop(self, reason: str = ""):
        """Stop the bot."""
        self.is_running = False
        
        self.logger.info("\n" + "=" * 60)
        self.logger.info(">>> STOPPING PAPER TRADING BOT")
        self.logger.info("=" * 60)
        
        if self.session:
            self.session.status = 'STOPPED'
            self.session.ended_at = django_timezone.now()
            self.session.ending_balance_usd = self.account.current_balance_usd
            self.session.session_pnl_usd = (
                self.session.ending_balance_usd - 
                self.session.starting_balance_usd
            )
            self.session.save()
            
            # Display final statistics
            self.logger.info(f"[STATISTICS] FINAL REPORT:")
            self.logger.info(f"   Total Trades: {self.session.total_trades_executed}")
            self.logger.info(f"   Successful: {self.session.successful_trades}")
            self.logger.info(f"   Starting Balance: ${self.session.starting_balance_usd:.2f}")
            self.logger.info(f"   Ending Balance: ${self.session.ending_balance_usd:.2f}")
            self.logger.info(f"   Session P&L: ${self.session.session_pnl_usd:.2f}")
        
        self.logger.info(f"\n[COMPLETE] Bot stopped: {reason}")
        self.logger.info("=" * 60)