"""
Enhanced Paper Trading Bot with Intel Slider System

This is the main paper trading bot that integrates the Intel Slider (1-10) system
for intelligent decision making. It replaces multiple bot implementations with
a single, unified system.

Key Features:
- Intel Slider system (1-10 intelligence levels)
- Modular market analyzers
- Comprehensive thought logging
- WebSocket real-time updates
- Performance tracking
- Clean separation of concerns

File: dexproject/paper_trading/bot/simple_trader.py
"""

import os
import sys
import time
import signal
import logging
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
import random
import uuid

# ============================================================================
# DJANGO SETUP
# ============================================================================
# Add project root to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Django setup
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
django.setup()

from django.utils import timezone
from django.db import transaction
from asgiref.sync import async_to_sync

# ============================================================================
# MODEL IMPORTS
# ============================================================================
from paper_trading.models import (
    PaperTradingAccount,
    PaperTrade,
    PaperPosition,
    PaperTradingSession,
    PaperAIThoughtLog,
    PaperStrategyConfiguration,
    PaperPerformanceMetrics
)

# ============================================================================
# INTELLIGENCE SYSTEM IMPORTS
# ============================================================================
from paper_trading.intelligence.intel_slider import IntelSliderEngine
from paper_trading.intelligence.base import (
    IntelligenceLevel,
    MarketContext,
    TradingDecision
)

# ============================================================================
# SERVICE IMPORTS - Use global instance
# ============================================================================
from paper_trading.services.websocket_service import websocket_service

# ============================================================================
# LEGACY AI ENGINE IMPORT (for backward compatibility during transition)
# ============================================================================
from paper_trading.bot.ai_engine import (
    TradingSignal as LegacyTradingSignal,
    MarketCondition
)

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('paper_trading_bot.log')
    ]
)
logger = logging.getLogger(__name__)


class EnhancedPaperTradingBot:
    """
    Unified Paper Trading Bot with Intel Slider System.
    
    This bot replaces multiple implementations with a clean,
    modular design that uses the Intel Slider (1-10) for
    intelligent decision making.
    """
    
    def __init__(self, account_name: str, intel_level: int = 5):
        """
        Initialize the enhanced paper trading bot.
        
        Args:
            account_name: Name of the paper trading account
            intel_level: Intelligence level (1-10)
        """
        self.account_name = account_name
        self.intel_level = intel_level
        self.account = None
        self.session = None
        self.intelligence_engine = None
        
        # Market tracking
        self.token_list = [
            {'symbol': 'WETH', 'address': '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2', 'price': Decimal('2500')},
            {'symbol': 'USDC', 'address': '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48', 'price': Decimal('1')},
            {'symbol': 'USDT', 'address': '0xdac17f958d2ee523a2206206994597c13d831ec7', 'price': Decimal('1')},
            {'symbol': 'DAI', 'address': '0x6b175474e89094c44da98b954eedeac495271d0f', 'price': Decimal('1')},
            {'symbol': 'WBTC', 'address': '0x2260fac5e5542a773aa44fbcfedf7c193bc2c599', 'price': Decimal('45000')},
            {'symbol': 'UNI', 'address': '0x1f9840a85d5af5bf1d1762f925bdaddc4201f984', 'price': Decimal('6.50')},
            {'symbol': 'AAVE', 'address': '0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9', 'price': Decimal('95')},
            {'symbol': 'LINK', 'address': '0x514910771af9ca656af840dff83e8264ecf986ca', 'price': Decimal('15')},
            {'symbol': 'MATIC', 'address': '0x7d1afa7b718fb893db30a3abc0cfc608aacfebb0', 'price': Decimal('0.85')},
            {'symbol': 'ARB', 'address': '0xb50721bcf8d664c30412cfbc6cf7a15145234ad1', 'price': Decimal('1.20')}
        ]
        
        self.price_history = {}
        self.positions = {}
        self.last_decisions = {}
        
        # Control flags
        self.running = False
        self.tick_interval = 15  # seconds between market checks
        self.tick_count = 0
        
        logger.info(f"[BOT] Enhanced Paper Trading Bot initialized with Intel Level {intel_level}")
    
    def initialize(self) -> bool:
        """
        Initialize bot components and connections.
        
        Returns:
            True if initialization successful
        """
        try:
            # ================================================================
            # LOAD OR CREATE ACCOUNT
            # ================================================================
            self._load_account()
            
            # ================================================================
            # CREATE TRADING SESSION
            # ================================================================
            self._create_session()
            
            # ================================================================
            # INITIALIZE INTELLIGENCE ENGINE
            # ================================================================
            self._initialize_intelligence()
            
            # ================================================================
            # SETUP STRATEGY CONFIGURATION
            # ================================================================
            self._setup_strategy_configuration()
            
            # ================================================================
            # LOAD EXISTING POSITIONS
            # ================================================================
            self._load_positions()
            
            # ================================================================
            # INITIALIZE PRICE HISTORY
            # ================================================================
            self._initialize_price_history()
            
            # ================================================================
            # SEND INITIALIZATION NOTIFICATION
            # ================================================================
            self._send_bot_status_update('initialized')
            
            # ================================================================
            # LOG INITIAL THOUGHT
            # ================================================================
            self._log_thought(
                action="STARTUP",
                reasoning=f"Bot initialized with Intel Level {self.intel_level}. "
                         f"Strategy: {self.intelligence_engine.config.name}. "
                         f"Risk tolerance: {self.intelligence_engine.config.risk_tolerance}%. "
                         f"Starting balance: ${self.account.current_balance_usd:.2f}",
                confidence=100,
                decision_type="SYSTEM"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] Initialization failed: {e}", exc_info=True)
            return False
    
    def _setup_strategy_configuration(self):
        """
        Set up strategy configuration based on intel level.
        
        Creates or updates the strategy configuration to match
        the selected intelligence level settings.
        """
        try:
            # Get or create strategy configuration
            strategy_config, created = PaperStrategyConfiguration.objects.get_or_create(
                account=self.account,
                defaults={
                    'name': f"Intel_{self.intel_level}_Strategy",
                    'trading_mode': 'BALANCED',
                    'strategy_type': 'AI_DRIVEN',
                    'is_active': True,
                    'risk_tolerance_percent': self.intelligence_engine.config.risk_tolerance,
                    'max_position_size_percent': self.intelligence_engine.config.max_position_size,
                    'stop_loss_percent': Decimal('10'),
                    'take_profit_percent': Decimal('25'),
                    'enable_trailing_stop': True,
                    'trailing_stop_percent': Decimal('5'),
                    'rebalance_frequency_hours': 24,
                    'min_trade_amount_usd': Decimal('10'),
                    'max_trade_amount_usd': Decimal('1000'),
                    'max_daily_trades': 20,
                    'allowed_tokens': self._get_allowed_tokens(),
                    'enable_analytics': True,
                    'enable_notifications': True,
                    'custom_parameters': {  # Changed from strategy_parameters to custom_parameters
                        'intel_level': self.intel_level,
                        'intelligence_config': {
                            'name': self.intelligence_engine.config.name,
                            'description': self.intelligence_engine.config.description,
                            'risk_tolerance': float(self.intelligence_engine.config.risk_tolerance),
                            'max_position_size': float(self.intelligence_engine.config.max_position_size),
                            'trade_frequency': self.intelligence_engine.config.trade_frequency.value
                        }
                    }
                }
            )
            
            if not created:
                # Update existing config
                strategy_config.strategy_parameters = {
                    'intel_level': self.intel_level,
                    'intelligence_config': {
                        'name': self.intelligence_engine.config.name,
                        'description': self.intelligence_engine.config.description,
                        'risk_tolerance': float(self.intelligence_engine.config.risk_tolerance),
                        'max_position_size': float(self.intelligence_engine.config.max_position_size),
                        'trade_frequency': self.intelligence_engine.config.trade_frequency.value
                    }
                }
                strategy_config.save()
            
            logger.info(f"[CONFIG] Strategy configuration {'created' if created else 'updated'}")
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to setup strategy configuration: {e}")
            raise
    
    def _load_account(self):
        """Load or create paper trading account."""
        from django.contrib.auth.models import User
        
        user, _ = User.objects.get_or_create(
            username='demo_user',
            defaults={'email': 'demo@example.com'}
        )
        
        self.account, created = PaperTradingAccount.objects.get_or_create(
            name=self.account_name,
            user=user,
            defaults={
                'current_balance_usd': Decimal('10000'),
                'initial_balance_usd': Decimal('10000')
            }
        )
        
        if created:
            logger.info(f"[ACCOUNT] Created new account: {self.account_name}")
        else:
            logger.info(f"[ACCOUNT] Using existing account: {self.account_name}")
    
    def _create_session(self):
        """Create a new trading session."""
        self.session = PaperTradingSession.objects.create(
            account=self.account,
            status='RUNNING',
            starting_balance_usd=self.account.current_balance_usd,
            name=f"Bot Session - Intel Level {self.intel_level}",
            config_snapshot={
                'bot_version': '2.0.0',
                'intel_level': self.intel_level,
                'account_name': self.account_name,
                'account_id': str(self.account.account_id)  # Convert UUID to string
            }
        )
        logger.info(f"[SESSION] Created trading session: {self.session.session_id}")
    
    def _initialize_intelligence(self):
        """Initialize the intelligence engine."""
        self.intelligence_engine = IntelSliderEngine(
            intel_level=self.intel_level,
            account_id=str(self.account.account_id)
        )
        logger.info(f"[INTEL] Intelligence Engine initialized at Level {self.intel_level}")
    
    def _load_positions(self):
        """Load existing open positions."""
        try:
            positions = PaperPosition.objects.filter(
                account=self.account,
                is_open=True  # Use is_open instead of is_active
            )
            
            for position in positions:
                self.positions[position.token_symbol] = position
            
            logger.info(f"[POSITIONS] Loaded {len(self.positions)} open positions")
        except Exception as e:
            logger.error(f"[ERROR] Failed to load positions: {e}")
    
    def _initialize_price_history(self):
        """Initialize price history for all tokens."""
        for token in self.token_list:
            self.price_history[token['symbol']] = [token['price']]
    
    def _get_allowed_tokens(self) -> List[str]:
        """Get list of allowed token addresses."""
        return [token['address'] for token in self.token_list]
    
    def _send_bot_status_update(self, status: str):
        """Send bot status update via WebSocket."""
        try:
            # Note: The websocket_service doesn't have send_bot_update method
            # We'll use a different method that exists
            websocket_service.send_portfolio_update(
                account_id=str(self.account.account_id),
                portfolio_data={
                    'bot_status': status,
                    'intel_level': self.intel_level,
                    'account_balance': float(self.account.current_balance_usd),
                    'open_positions': len(self.positions),
                    'tick_count': self.tick_count
                }
            )
        except Exception as e:
            logger.error(f"[ERROR] Failed to send status update: {e}")
    
    def run(self):
        """
        Main bot execution loop.
        
        Runs continuously until stopped, checking markets and making
        trading decisions based on the intelligence level.
        """
        logger.info("[START] Bot starting main execution loop...")
        
        # ====================================================================
        # SETUP SIGNAL HANDLERS
        # ====================================================================
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        
        self.running = True
        
        try:
            while self.running:
                # ============================================================
                # MARKET ANALYSIS TICK
                # ============================================================
                self._tick()
                
                # ============================================================
                # SLEEP BETWEEN TICKS
                # ============================================================
                time.sleep(self.tick_interval)
                
        except Exception as e:
            logger.error(f"[ERROR] Bot crashed: {e}", exc_info=True)
        finally:
            # ============================================================
            # CLEANUP ON EXIT
            # ============================================================
            self._cleanup()
    
    def _tick(self):
        """
        Single market analysis tick.
        
        This method:
        1. Updates market prices
        2. Analyzes each token
        3. Makes trading decisions
        4. Executes trades
        5. Updates performance metrics
        """
        self.tick_count += 1
        logger.info("\n" + "=" * 60)
        logger.info(f"[TICK] Market tick #{self.tick_count}")
        
        # ====================================================================
        # UPDATE MARKET PRICES
        # ====================================================================
        self._update_market_prices()
        
        # ====================================================================
        # ANALYZE EACH TOKEN
        # ====================================================================
        for token_data in self.token_list:
            self._analyze_token(token_data)
        
        # ====================================================================
        # UPDATE PERFORMANCE METRICS
        # ====================================================================
        self._update_performance_metrics()
    
    def _update_market_prices(self):
        """Simulate market price changes."""
        for token in self.token_list:
            # Simulate price movement (-5% to +5%)
            change = Decimal(random.uniform(-0.05, 0.05))
            old_price = token['price']
            token['price'] = old_price * (Decimal('1') + change)
            
            # Update price history
            if token['symbol'] not in self.price_history:
                self.price_history[token['symbol']] = []
            self.price_history[token['symbol']].append(token['price'])
            
            # Keep only last 100 prices
            if len(self.price_history[token['symbol']]) > 100:
                self.price_history[token['symbol']].pop(0)
            
            # Log significant changes
            if abs(change) > Decimal('0.02'):
                logger.info(f"[PRICE] {token['symbol']}: ${old_price:.2f} -> ${token['price']:.2f} ({change*100:.2f}%)")
    
    def _analyze_token(self, token_data: Dict[str, Any]):
        """
        Analyze a single token for trading opportunities.
        
        Args:
            token_data: Token information dictionary
        """
        try:
            token_symbol = token_data['symbol']
            current_price = token_data['price']
            
            # ================================================================
            # PREPARE MARKET CONTEXT
            # ================================================================
            market_context = MarketContext(
                token_address=token_data['address'],
                token_symbol=token_symbol,
                current_price=current_price,
                price_24h_ago=self.price_history[token_symbol][0] if self.price_history[token_symbol] else current_price,
                volume_24h=Decimal('1000000'),  # Simulated
                liquidity_usd=Decimal('5000000'),  # Simulated
                holder_count=1000,  # Simulated
                market_cap=Decimal('50000000'),  # Simulated
                volatility=Decimal('0.15'),  # Simulated
                trend='neutral',
                momentum=Decimal('0'),
                support_levels=[],
                resistance_levels=[],
                timestamp=timezone.now()
            )
            
            # ================================================================
            # MAKE TRADING DECISION
            # ================================================================
            existing_positions = [
                {
                    'token_symbol': pos.token_symbol,
                    'quantity': float(pos.quantity),
                    'invested_usd': float(pos.total_invested_usd)
                }
                for pos in self.positions.values()
            ]
            
            # Use async_to_sync for make_decision
            decision = async_to_sync(self.intelligence_engine.make_decision)(
                market_context=market_context,
                account_balance=self.account.current_balance_usd,
                existing_positions=existing_positions,
                token_address=token_data['address'],
                token_symbol=token_symbol
            )
            
            # ================================================================
            # LOG THOUGHT PROCESS
            # ================================================================
            thought_log = self.intelligence_engine.generate_thought_log(decision)
            self._log_thought(
                action=decision.action,
                reasoning=thought_log,
                confidence=float(decision.overall_confidence),
                decision_type="TRADE_DECISION",
                metadata={
                    'token': token_symbol,
                    'token_address': token_data['address'],
                    'intel_level': self.intel_level,
                    'risk_score': float(decision.risk_score),
                    'opportunity_score': float(decision.opportunity_score),
                    'current_price': float(current_price)
                }
            )
            
            # ================================================================
            # EXECUTE TRADE IF DECIDED
            # ================================================================
            if decision.action in ['BUY', 'SELL']:
                if self._can_trade():
                    self._execute_trade(decision, token_symbol, current_price)
            
            # Store decision for tracking
            self.last_decisions[token_symbol] = decision
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to analyze {token_symbol}: {e}", exc_info=True)
    
    def _log_thought(self, action: str, reasoning: str, confidence: float, 
                     decision_type: str = "ANALYSIS", metadata: Dict[str, Any] = None):
        """
        Log AI thought process to database.
        
        Args:
            action: Action taken (BUY, SELL, HOLD, etc.)
            reasoning: Detailed reasoning for the decision
            confidence: Confidence level (0-100)
            decision_type: Type of decision
            metadata: Additional metadata
        """
        try:
            metadata = metadata or {}
            
            # Map action to decision type for PaperAIThoughtLog
            decision_type_map = {
                'BUY': 'BUY',
                'SELL': 'SELL',
                'HOLD': 'HOLD',
                'SKIP': 'SKIP',
                'STARTUP': 'SKIP',
                'TRADE_DECISION': 'HOLD'
            }
            
            # Get token info from metadata
            token_symbol = metadata.get('token', 'SYSTEM')
            token_address = metadata.get('token_address', '0x' + '0' * 40)
            
            # Create thought log record with correct fields
            thought_log = PaperAIThoughtLog.objects.create(
                account=self.account,
                paper_trade=None,  # Will be linked if trade is executed
                decision_type=decision_type_map.get(action, 'SKIP'),
                token_address=token_address,
                token_symbol=token_symbol,
                confidence_level=self._get_confidence_level(confidence),
                confidence_percent=Decimal(str(confidence)),
                risk_score=Decimal(str(metadata.get('risk_score', 50))),
                opportunity_score=Decimal(str(metadata.get('opportunity_score', 50))),
                primary_reasoning=reasoning[:500],  # Truncate if needed
                key_factors=[
                    f"Intel Level: {metadata.get('intel_level', self.intel_level)}",
                    f"Current Price: ${metadata.get('current_price', 0):.2f}" if 'current_price' in metadata else "System Event"
                ],
                positive_signals=[],
                negative_signals=[],
                market_data=metadata,
                strategy_name=f"Intel_{self.intel_level}",
                lane_used='SMART',
                analysis_time_ms=100  # Simulated
            )
            
            logger.info(f"[THOUGHT] Logged: {action} for {token_symbol} ({confidence:.0f}% confidence)")
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to log thought: {e}")
    
    def _get_confidence_level(self, confidence: float) -> str:
        """Convert confidence percentage to level category."""
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
    
    def _can_trade(self) -> bool:
        """Check if bot can execute a trade."""
        # Add any trade restrictions here
        return True
    
    def _execute_trade(self, decision: TradingDecision, token_symbol: str, current_price: Decimal):
        """
        Execute a paper trade based on the decision.
        
        Args:
            decision: Trading decision from intelligence engine
            token_symbol: Token to trade
            current_price: Current token price
        """
        try:
            # ================================================================
            # CREATE TRADE RECORD WITH CORRECT FIELDS
            # ================================================================
            trade = PaperTrade.objects.create(
                account=self.account,
                # Don't use 'session' field - use the correct field names
                trade_type=decision.action.lower(),  # 'buy' or 'sell'
                token_in_address='0x' + '0' * 40 if decision.action == 'BUY' else decision.token_address,
                token_in_symbol='USDC' if decision.action == 'BUY' else token_symbol,
                token_out_address=decision.token_address if decision.action == 'BUY' else '0x' + '0' * 40,
                token_out_symbol=token_symbol if decision.action == 'BUY' else 'USDC',
                amount_in=decision.position_size_usd,
                amount_out=decision.position_size_usd / current_price if decision.action == 'BUY' else decision.position_size_usd,
                amount_in_usd=decision.position_size_usd,
                amount_out_usd=decision.position_size_usd,
                price_per_token=current_price,
                gas_price_gwei=decision.max_gas_price_gwei,
                gas_used=21000,  # Simulated
                gas_cost_usd=Decimal('5'),  # Simulated
                slippage_percent=Decimal('1'),  # Simulated
                execution_time_ms=int(decision.processing_time_ms),
                status='SUCCESS',  # Simulated success
                transaction_hash='0x' + uuid.uuid4().hex,
                block_number=1000000,  # Simulated
                dex_used='UNISWAP_V3',
                metadata={
                    'intel_level': self.intel_level,
                    'confidence': float(decision.overall_confidence),
                    'risk_score': float(decision.risk_score),
                    'strategy_name': f"Intel_{self.intel_level}"
                }
            )
            
            # ================================================================
            # UPDATE POSITION
            # ================================================================
            if decision.action == 'BUY':
                self._open_or_add_position(token_symbol, decision, current_price, trade)
            else:
                self._close_or_reduce_position(token_symbol, decision, current_price, trade)
            
            # ================================================================
            # UPDATE ACCOUNT BALANCE
            # ================================================================
            if decision.action == 'BUY':
                self.account.current_balance_usd -= decision.position_size_usd
            else:
                self.account.current_balance_usd += decision.position_size_usd
            self.account.save()
            
            logger.info(f"[TRADE] Executed {decision.action} for {token_symbol}: ${decision.position_size_usd:.2f}")
            
        except Exception as e:
            logger.error(f"[ERROR] {decision.action} execution failed: {e}")
    
    def _open_or_add_position(self, token_symbol: str, decision: TradingDecision, 
                              current_price: Decimal, trade: PaperTrade):
        """Open new position or add to existing."""
        if token_symbol in self.positions:
            position = self.positions[token_symbol]
            position.quantity += decision.position_size_usd / current_price
            position.total_invested_usd += decision.position_size_usd
            position.average_entry_price_usd = position.total_invested_usd / position.quantity
            position.current_price_usd = current_price
            position.current_value_usd = position.quantity * current_price
            position.unrealized_pnl_usd = position.current_value_usd - position.total_invested_usd
            position.save()
        else:
            position = PaperPosition.objects.create(
                account=self.account,
                token_address=decision.token_address,
                token_symbol=token_symbol,
                quantity=decision.position_size_usd / current_price,
                average_entry_price_usd=current_price,
                current_price_usd=current_price,
                total_invested_usd=decision.position_size_usd,
                current_value_usd=decision.position_size_usd,
                unrealized_pnl_usd=Decimal('0'),
                is_open=True  # Use is_open instead of is_active
            )
            self.positions[token_symbol] = position
    
    def _close_or_reduce_position(self, token_symbol: str, decision: TradingDecision,
                                  current_price: Decimal, trade: PaperTrade):
        """Close or reduce existing position."""
        if token_symbol in self.positions:
            position = self.positions[token_symbol]
            sell_quantity = min(position.quantity, decision.position_size_usd / current_price)
            
            position.quantity -= sell_quantity
            position.current_value_usd = position.quantity * current_price
            position.realized_pnl_usd += (sell_quantity * current_price) - (sell_quantity * position.average_entry_price_usd)
            
            if position.quantity <= 0:
                position.is_open = False  # Use is_open instead of is_active
                position.closed_at = timezone.now()
                del self.positions[token_symbol]
            
            position.save()
    
    def _update_performance_metrics(self):
        """Update performance metrics for the session."""
        try:
            # Calculate metrics
            total_trades = PaperTrade.objects.filter(
                account=self.account,
                created_at__gte=self.session.started_at
            ).count()
            
            winning_trades = PaperTrade.objects.filter(
                account=self.account,
                created_at__gte=self.session.started_at,
                metadata__contains='profit'
            ).count()
            
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            # Create or update metrics
            metrics, created = PaperPerformanceMetrics.objects.get_or_create(
                session=self.session,
                period_start=self.session.started_at,
                period_end=timezone.now(),
                defaults={
                    'total_trades': total_trades,
                    'winning_trades': winning_trades,
                    'losing_trades': total_trades - winning_trades,
                    'win_rate': Decimal(str(win_rate)),
                    'total_pnl_usd': self.account.current_balance_usd - self.session.starting_balance_usd,
                    'total_pnl_percent': ((self.account.current_balance_usd / self.session.starting_balance_usd) - 1) * 100,
                    'best_trade_pnl_usd': Decimal('0'),
                    'worst_trade_pnl_usd': Decimal('0'),
                    'average_trade_pnl_usd': Decimal('0'),
                    'sharpe_ratio': Decimal('0'),
                    'max_drawdown_percent': Decimal('0'),
                    'total_fees_usd': Decimal('0'),
                    'metadata': {'tick_count': self.tick_count}
                }
            )
            
            if not created:
                metrics.total_trades = total_trades
                metrics.win_rate = Decimal(str(win_rate))
                metrics.total_pnl_usd = self.account.current_balance_usd - self.session.starting_balance_usd
                metrics.save()
                
        except Exception as e:
            logger.error(f"[ERROR] Failed to update performance metrics: {e}")
    
    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals."""
        logger.info("[SHUTDOWN] Received shutdown signal")
        self.running = False
    
    def _cleanup(self):
        """Clean up on exit."""
        try:
            if self.session:
                self.session.status = 'STOPPED'  # Use valid status from SessionStatus choices
                self.session.ended_at = timezone.now()
                self.session.ending_balance_usd = self.account.current_balance_usd
                self.session.session_pnl_usd = self.account.current_balance_usd - self.session.starting_balance_usd
                self.session.save()
                
            logger.info("[CLEANUP] Bot shutdown complete")
        except Exception as e:
            logger.error(f"[ERROR] Cleanup failed: {e}")


def main():
    """Main entry point for the bot."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Enhanced Paper Trading Bot')
    parser.add_argument('--account', default='Intel_Slider_Balanced', help='Account name')
    parser.add_argument('--intel', type=int, default=5, choices=range(1, 11), help='Intelligence level (1-10)')
    
    args = parser.parse_args()
    
    print("\n╔════════════════════════════════════════════════════════════════════╗")
    print("║          ENHANCED PAPER TRADING BOT - INTEL SLIDER SYSTEM         ║")
    print("╚════════════════════════════════════════════════════════════════════╝\n")
    
    # Intelligence level descriptions
    intel_descriptions = {
        1: "ULTRA CONSERVATIVE - Maximum caution",
        2: "VERY CONSERVATIVE - High caution",
        3: "CONSERVATIVE - Careful approach",
        4: "CAUTIOUS - Below average risk",
        5: "BALANCED - Equal risk/reward consideration",
        6: "MODERATE - Slightly aggressive",
        7: "AGGRESSIVE - Higher risk tolerance",
        8: "VERY AGGRESSIVE - Significant risks",
        9: "ULTRA AGGRESSIVE - Maximum risk",
        10: "YOLO MODE - No risk limits"
    }
    
    print(f"INTELLIGENCE LEVEL: ⚖️  Level {args.intel}: {intel_descriptions[args.intel].upper()}")
    print(f"✅ Using account: {args.account}\n")
    
    bot = EnhancedPaperTradingBot(
        account_name=args.account,
        intel_level=args.intel
    )
    
    print("=" * 60)
    print("📋 BOT CONFIGURATION")
    print("=" * 60)
    print(f"  Account         : {args.account}")
    
    if bot.initialize():
        print(f"  User            : {bot.account.user.username}")
        print(f"  Balance         : ${bot.account.current_balance_usd:,.2f}\n")
        print(f"  INTELLIGENCE    : Level {args.intel}/10")
        print("  Controlled by Intel Level:")
        print(f"    • Risk Tolerance    : {bot.intelligence_engine.config.risk_tolerance}%")
        print(f"    • Max Position Size : {bot.intelligence_engine.config.max_position_size:.1f}%")
        print(f"    • Trade Frequency   : {bot.intelligence_engine.config.trade_frequency.value}")
        print(f"    • Gas Strategy      : {bot.intelligence_engine.config.gas_strategy.value}")
        print(f"    • MEV Protection    : {'Always On' if bot.intelligence_engine.config.use_mev_protection else 'Off'}")
        print(f"    • Decision Speed    : {bot.intelligence_engine.config.decision_speed.value} ({bot.intelligence_engine.config.base_analysis_time}ms)")
        print("=" * 60)
        
        print("🤖 Initializing bot for account:", args.account)
        print("✅ Bot initialized successfully\n")
        print("🏃 Bot is running... Press Ctrl+C to stop\n")
        
        bot.run()
    else:
        print("❌ Failed to initialize bot")
        sys.exit(1)


if __name__ == "__main__":
    main()