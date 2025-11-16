"""
Diagnostic Command: Trace Sell Decisions

This command traces through the sell decision logic for ONE position
to show exactly why positions aren't being sold.

Usage:
    python manage.py diagnose_sell_decisions
    python manage.py diagnose_sell_decisions --token BRETT
    python manage.py diagnose_sell_decisions --position-id <uuid>

File: paper_trading/management/commands/diagnose_sell_decisions.py
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from decimal import Decimal
import logging

from paper_trading.models import PaperPosition, PaperTrade
from paper_trading.intelligence.strategies.decision_maker import DecisionMaker
from paper_trading.intelligence.analyzers.base import CompositeMarketAnalyzer

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Diagnose why positions aren't being sold."""
    
    help = 'Trace sell decision logic for a position to debug why sells are skipped'

    def add_arguments(self, parser) -> None:
        """Add command arguments."""
        parser.add_argument(
            '--token',
            type=str,
            help='Token symbol to diagnose (e.g., BRETT)'
        )
        parser.add_argument(
            '--position-id',
            type=str,
            help='Specific position ID to diagnose'
        )

    def handle(self, *args, **options) -> None:
        """Execute the diagnostic."""
        self.stdout.write("\n" + "="*80)
        self.stdout.write(self.style.SUCCESS("🔍 SELL DECISION DIAGNOSTIC"))
        self.stdout.write("="*80 + "\n")

        # Get position to diagnose
        position = self._get_position(options)
        
        if not position:
            self.stdout.write(self.style.ERROR("❌ No position found to diagnose"))
            return

        # Display position details
        self._display_position_info(position)
        
        # Check field accessibility
        self._check_field_access(position)
        
        # Calculate metrics
        self._calculate_metrics(position)
        
        # Simulate decision making
        self._simulate_decision(position)
        
        # Check recent trades
        self._check_trade_history(position)
        
        self.stdout.write("\n" + "="*80)
        self.stdout.write(self.style.SUCCESS("✅ DIAGNOSTIC COMPLETE"))
        self.stdout.write("="*80 + "\n")

    def _get_position(self, options: dict) -> PaperPosition:
        """Get position to diagnose."""
        position_id = options.get('position_id')
        token = options.get('token')
        
        self.stdout.write("📍 Finding position...\n")
        
        if position_id:
            try:
                position = PaperPosition.objects.get(position_id=position_id)
                self.stdout.write(f"  ✅ Found position by ID: {position_id[:8]}\n")
                return position
            except PaperPosition.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"  ❌ Position {position_id} not found\n"))
                return None
        
        if token:
            position = PaperPosition.objects.filter(
                token_symbol=token,
                is_open=True
            ).first()
            
            if position:
                self.stdout.write(f"  ✅ Found open position for {token}\n")
                return position
            else:
                self.stdout.write(self.style.ERROR(f"  ❌ No open position for {token}\n"))
                return None
        
        # Get first open position
        position = PaperPosition.objects.filter(is_open=True).first()
        
        if position:
            self.stdout.write(f"  ✅ Using first open position: {position.token_symbol}\n")
            return position
        
        self.stdout.write(self.style.ERROR("  ❌ No open positions found\n"))
        return None

    def _display_position_info(self, position: PaperPosition) -> None:
        """Display basic position information."""
        self.stdout.write("\n📊 POSITION INFORMATION")
        self.stdout.write("-" * 80)
        
        self.stdout.write(f"  Token: {position.token_symbol}")
        self.stdout.write(f"  Address: {position.token_address}")
        self.stdout.write(f"  Position ID: {position.position_id}")
        self.stdout.write(f"  Is Open: {position.is_open}")
        self.stdout.write(f"  Opened At: {position.opened_at}")
        
        # Calculate age
        age_delta = timezone.now() - position.opened_at
        age_hours = age_delta.total_seconds() / 3600
        age_days = age_delta.days
        
        self.stdout.write(f"  Age: {age_days} days, {age_hours:.2f} hours")
        self.stdout.write("")

    def _check_field_access(self, position: PaperPosition) -> None:
        """Check if code can access fields correctly."""
        self.stdout.write("\n🔑 FIELD ACCESS CHECK")
        self.stdout.write("-" * 80)
        
        # Check database fields
        self.stdout.write("  DATABASE FIELDS:")
        self.stdout.write(f"    ✅ average_entry_price_usd: ${position.average_entry_price_usd}")
        self.stdout.write(f"    ✅ quantity: {position.quantity}")
        self.stdout.write(f"    ✅ total_invested_usd: ${position.total_invested_usd}")
        self.stdout.write(f"    ✅ current_price_usd: ${position.current_price_usd}")
        self.stdout.write(f"    ✅ unrealized_pnl_usd: ${position.unrealized_pnl_usd}")
        self.stdout.write(f"    ✅ is_open: {position.is_open}")
        
        # Check if properties exist
        self.stdout.write("\n  PROPERTY ACCESS (what code expects):")
        
        try:
            status = position.status if hasattr(position, 'status') else "❌ NOT FOUND"
            self.stdout.write(f"    status: {status}")
        except Exception as e:
            self.stdout.write(f"    ❌ status: ERROR - {e}")
        
        try:
            entry_price = position.entry_price if hasattr(position, 'entry_price') else "❌ NOT FOUND"
            self.stdout.write(f"    entry_price: ${entry_price}")
        except Exception as e:
            self.stdout.write(f"    ❌ entry_price: ERROR - {e}")
        
        try:
            amount = position.amount if hasattr(position, 'amount') else "❌ NOT FOUND"
            self.stdout.write(f"    amount: {amount}")
        except Exception as e:
            self.stdout.write(f"    ❌ amount: ERROR - {e}")
        
        try:
            amount_invested = position.amount_invested_usd if hasattr(position, 'amount_invested_usd') else "❌ NOT FOUND"
            self.stdout.write(f"    amount_invested_usd: ${amount_invested}")
        except Exception as e:
            self.stdout.write(f"    ❌ amount_invested_usd: ERROR - {e}")
        
        self.stdout.write("")

    def _calculate_metrics(self, position: PaperPosition) -> None:
        """Calculate and display metrics."""
        self.stdout.write("\n📈 CALCULATED METRICS")
        self.stdout.write("-" * 80)
        
        # P&L Calculation
        pnl_usd = position.unrealized_pnl_usd
        pnl_percent = Decimal('0')
        
        if position.total_invested_usd > 0:
            pnl_percent = (pnl_usd / position.total_invested_usd) * Decimal('100')
        
        self.stdout.write(f"  Entry Price: ${position.average_entry_price_usd}")
        self.stdout.write(f"  Current Price: ${position.current_price_usd}")
        self.stdout.write(f"  Invested: ${position.total_invested_usd}")
        self.stdout.write(f"  Current Value: ${position.current_value_usd}")
        self.stdout.write(f"  Unrealized P&L: ${pnl_usd} ({pnl_percent:.2f}%)")
        
        # Age
        age_delta = timezone.now() - position.opened_at
        age_hours = age_delta.total_seconds() / 3600
        
        self.stdout.write(f"  Hold Time: {age_hours:.2f} hours")
        
        # Price change
        if position.average_entry_price_usd > 0:
            price_change = ((position.current_price_usd - position.average_entry_price_usd) 
                          / position.average_entry_price_usd * Decimal('100'))
            self.stdout.write(f"  Price Change: {price_change:.2f}%")
        
        self.stdout.write("")

    def _simulate_decision(self, position: PaperPosition) -> None:
        """Simulate what the decision maker would decide."""
        self.stdout.write("\n🤖 SIMULATED DECISION MAKER")
        self.stdout.write("-" * 80)
        
        # Calculate what the decision maker sees
        age_delta = timezone.now() - position.opened_at
        hold_time_hours = age_delta.total_seconds() / 3600
        
        pnl_percent = Decimal('0')
        if position.total_invested_usd > 0:
            pnl_percent = (position.unrealized_pnl_usd / position.total_invested_usd) * Decimal('100')
        
        self.stdout.write(f"  What decision maker sees:")
        self.stdout.write(f"    has_position: True")
        self.stdout.write(f"    entry_price: ${position.average_entry_price_usd}")
        self.stdout.write(f"    invested: ${position.total_invested_usd}")
        self.stdout.write(f"    hold_time: {hold_time_hours:.4f} hours")
        self.stdout.write(f"    pnl_percent: {pnl_percent:.2f}%")
        
        self.stdout.write(f"\n  Sell criteria evaluation:")
        
        # Check take profit (default 20%)
        take_profit_threshold = Decimal('20.0')
        if pnl_percent >= take_profit_threshold:
            self.stdout.write(f"    ✅ TAKE PROFIT: {pnl_percent:.2f}% >= {take_profit_threshold}%")
        else:
            self.stdout.write(f"    ❌ Take profit not met: {pnl_percent:.2f}% < {take_profit_threshold}%")
        
        # Check stop loss (default -10%)
        stop_loss_threshold = Decimal('-10.0')
        if pnl_percent <= stop_loss_threshold:
            self.stdout.write(f"    ✅ STOP LOSS: {pnl_percent:.2f}% <= {stop_loss_threshold}%")
        else:
            self.stdout.write(f"    ❌ Stop loss not triggered: {pnl_percent:.2f}% > {stop_loss_threshold}%")
        
        # Check minimum hold time (default 1 hour)
        min_hold_hours = Decimal('1.0')
        if hold_time_hours < float(min_hold_hours):
            self.stdout.write(f"    ⏱️ Too young to sell: {hold_time_hours:.2f}h < {min_hold_hours}h")
        else:
            self.stdout.write(f"    ✅ Hold time sufficient: {hold_time_hours:.2f}h >= {min_hold_hours}h")
        
        self.stdout.write("")

    def _check_trade_history(self, position: PaperPosition) -> None:
        """Check trade history for this token."""
        self.stdout.write("\n📜 TRADE HISTORY")
        self.stdout.write("-" * 80)
        
        # Find trades for this token
        buy_trades = PaperTrade.objects.filter(
            account=position.account,
            token_out_symbol=position.token_symbol,
            trade_type='buy'
        ).order_by('-created_at')[:3]
        
        sell_trades = PaperTrade.objects.filter(
            account=position.account,
            token_in_symbol=position.token_symbol,
            trade_type='sell'
        ).order_by('-created_at')[:3]
        
        self.stdout.write(f"  Recent BUY trades for {position.token_symbol}:")
        if buy_trades:
            for trade in buy_trades:
                self.stdout.write(f"    • {trade.created_at}: ${trade.amount_in_usd} @ status={trade.status}")
        else:
            self.stdout.write(f"    No BUY trades found")
        
        self.stdout.write(f"\n  Recent SELL trades for {position.token_symbol}:")
        if sell_trades:
            for trade in sell_trades:
                self.stdout.write(f"    • {trade.created_at}: ${trade.amount_in_usd} @ status={trade.status}")
        else:
            self.stdout.write(f"    ⚠️ NO SELL TRADES FOUND - This is the problem!")
        
        self.stdout.write("")