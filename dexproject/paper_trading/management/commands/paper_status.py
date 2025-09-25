"""
Management command to display paper trading system status.

Provides a comprehensive overview of the paper trading system
including active sessions, recent trades, and performance metrics.

File: dexproject/paper_trading/management/commands/paper_status.py
"""

import logging
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Sum, Avg, Count, Q

from paper_trading.models import (
    PaperTradingAccount,
    PaperTrade,
    PaperPosition,
    PaperTradingConfig,
    PaperAIThoughtLog,
    PaperStrategyConfiguration,
    PaperPerformanceMetrics,
    PaperTradingSession
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Display comprehensive paper trading system status."""
    
    help = 'Shows detailed status of the paper trading system'
    
    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            '--detailed',
            action='store_true',
            help='Show detailed information'
        )
    
    def handle(self, *args, **options):
        """Execute the status command."""
        self.detailed = options.get('detailed', False)
        
        self.display_header()
        self.display_system_overview()
        self.display_active_sessions()
        self.display_recent_activity()
        self.display_ai_insights()
        self.display_performance_summary()
        
        if self.detailed:
            self.display_detailed_metrics()
        
        self.display_footer()
    
    def display_header(self):
        """Display header."""
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(self.style.SUCCESS("PAPER TRADING SYSTEM STATUS"))
        self.stdout.write("=" * 80)
        self.stdout.write(f"Timestamp: {timezone.now().strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    def display_system_overview(self):
        """Display system overview."""
        self.stdout.write("\n📊 SYSTEM OVERVIEW")
        self.stdout.write("-" * 40)
        
        # Count all entities
        accounts = PaperTradingAccount.objects.count()
        active_accounts = PaperTradingAccount.objects.filter(is_active=True).count()
        total_trades = PaperTrade.objects.count()
        completed_trades = PaperTrade.objects.filter(status='completed').count()
        open_positions = PaperPosition.objects.filter(is_open=True).count()
        strategies = PaperStrategyConfiguration.objects.filter(is_active=True).count()
        
        self.stdout.write(f"  Total Accounts: {accounts} ({active_accounts} active)")
        self.stdout.write(f"  Total Trades: {total_trades} ({completed_trades} completed)")
        self.stdout.write(f"  Open Positions: {open_positions}")
        self.stdout.write(f"  Active Strategies: {strategies}")
    
    def display_active_sessions(self):
        """Display active trading sessions."""
        self.stdout.write("\n⚡ ACTIVE SESSIONS")
        self.stdout.write("-" * 40)
        
        active_sessions = PaperTradingSession.objects.filter(
            status__in=['STARTING', 'RUNNING', 'PAUSED']
        ).select_related('account', 'strategy_config')
        
        if not active_sessions:
            self.stdout.write("  No active sessions")
            return
        
        for session in active_sessions:
            status_emoji = {
                'STARTING': '🚀',
                'RUNNING': '✅',
                'PAUSED': '⏸️'
            }.get(session.status, '❓')
            
            duration = session.duration_seconds
            if duration:
                hours = duration // 3600
                minutes = (duration % 3600) // 60
                duration_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
            else:
                duration_str = "N/A"
            
            self.stdout.write(
                f"  {status_emoji} Session: {session.name or session.session_id[:8]}"
            )
            self.stdout.write(f"     Account: {session.account.name}")
            self.stdout.write(f"     Status: {session.get_status_display()}")
            self.stdout.write(f"     Duration: {duration_str}")
            self.stdout.write(f"     Trades: {session.total_trades_executed}")
            self.stdout.write(f"     P&L: ${session.session_pnl_usd:.2f}")
            
            if session.strategy_config:
                self.stdout.write(f"     Strategy: {session.strategy_config.name}")
    
    def display_recent_activity(self):
        """Display recent trading activity."""
        self.stdout.write("\n📈 RECENT ACTIVITY (Last 24 Hours)")
        self.stdout.write("-" * 40)
        
        last_24h = timezone.now() - timezone.timedelta(hours=24)
        
        recent_trades = PaperTrade.objects.filter(
            created_at__gte=last_24h
        ).count()
        
        recent_buys = PaperTrade.objects.filter(
            created_at__gte=last_24h,
            trade_type='buy'
        ).count()
        
        recent_sells = PaperTrade.objects.filter(
            created_at__gte=last_24h,
            trade_type='sell'
        ).count()
        
        volume_usd = PaperTrade.objects.filter(
            created_at__gte=last_24h
        ).aggregate(
            total=Sum('amount_in_usd')
        )['total'] or Decimal('0')
        
        self.stdout.write(f"  Total Trades: {recent_trades}")
        self.stdout.write(f"  Buy Orders: {recent_buys}")
        self.stdout.write(f"  Sell Orders: {recent_sells}")
        self.stdout.write(f"  Volume: ${volume_usd:.2f}")
        
        # Show last 3 trades - use values() to avoid decimal conversion issues
        try:
            last_trades = PaperTrade.objects.order_by('-created_at').values(
                'trade_type', 'token_out_symbol', 'amount_in_usd', 'status'
            )[:3]
            
            if last_trades:
                self.stdout.write("\n  Last 3 Trades:")
                for trade in last_trades:
                    status_emoji = '✅' if trade['status'] == 'completed' else '⏳'
                    amount = float(trade['amount_in_usd']) if trade['amount_in_usd'] else 0
                    self.stdout.write(
                        f"    {status_emoji} {trade['trade_type'].upper()} "
                        f"{trade['token_out_symbol']} - ${amount:.2f}"
                    )
        except Exception as e:
            logger.warning(f"Error displaying recent trades: {e}")
            self.stdout.write("  (Recent trades display unavailable)")
    
    def display_ai_insights(self):
        """Display AI decision insights."""
        self.stdout.write("\n🧠 AI DECISION INSIGHTS")
        self.stdout.write("-" * 40)
        
        total_thoughts = PaperAIThoughtLog.objects.count()
        
        if total_thoughts == 0:
            self.stdout.write("  No AI thoughts recorded yet")
            return
        
        # Decision distribution
        decision_stats = PaperAIThoughtLog.objects.values(
            'decision_type'
        ).annotate(
            count=Count('thought_id')
        )
        
        self.stdout.write(f"  Total Decisions: {total_thoughts}")
        self.stdout.write("\n  Decision Distribution:")
        for stat in decision_stats:
            self.stdout.write(f"    {stat['decision_type']}: {stat['count']}")
        
        # Average confidence
        avg_confidence = PaperAIThoughtLog.objects.aggregate(
            avg=Avg('confidence_percent')
        )['avg'] or 0
        
        avg_risk = PaperAIThoughtLog.objects.aggregate(
            avg=Avg('risk_score')
        )['avg'] or 0
        
        self.stdout.write(f"\n  Average Confidence: {avg_confidence:.1f}%")
        self.stdout.write(f"  Average Risk Score: {avg_risk:.1f}")
        
        # Lane usage
        fast_lane = PaperAIThoughtLog.objects.filter(lane_used='FAST').count()
        smart_lane = PaperAIThoughtLog.objects.filter(lane_used='SMART').count()
        
        if fast_lane or smart_lane:
            self.stdout.write("\n  Lane Usage:")
            self.stdout.write(f"    Fast Lane: {fast_lane} decisions")
            self.stdout.write(f"    Smart Lane: {smart_lane} decisions")
    
    def display_performance_summary(self):
        """Display performance summary."""
        self.stdout.write("\n💰 PERFORMANCE SUMMARY")
        self.stdout.write("-" * 40)
        
        # Get all accounts with trades
        accounts_with_trades = PaperTradingAccount.objects.filter(
            total_trades__gt=0
        )
        
        if not accounts_with_trades:
            self.stdout.write("  No trading performance data yet")
            return
        
        try:
            total_pnl = accounts_with_trades.aggregate(
                total=Sum('total_pnl_usd')
            )['total'] or Decimal('0')
            
            total_fees = accounts_with_trades.aggregate(
                total=Sum('total_fees_paid_usd')
            )['total'] or Decimal('0')
            
            # Calculate average win rate
            win_rates = []
            for account in accounts_with_trades:
                if account.total_trades > 0:
                    win_rate = float(account.win_rate) if hasattr(account, 'win_rate') else 0
                    win_rates.append(win_rate)
            
            avg_win_rate = sum(win_rates) / len(win_rates) if win_rates else 0
            
            # Convert Decimal to float for display
            total_pnl_float = float(total_pnl)
            total_fees_float = float(total_fees)
            net_pnl = total_pnl_float - total_fees_float
            
            self.stdout.write(f"  Total P&L: ${total_pnl_float:.2f}")
            self.stdout.write(f"  Total Fees: ${total_fees_float:.2f}")
            self.stdout.write(f"  Net P&L: ${net_pnl:.2f}")
            self.stdout.write(f"  Average Win Rate: {avg_win_rate:.1f}%")
            
            # Best performing account
            best_account = accounts_with_trades.order_by('-total_pnl_usd').first()
            if best_account:
                best_pnl = float(best_account.total_pnl_usd)
                self.stdout.write(
                    f"\n  Best Account: {best_account.name} "
                    f"(+${best_pnl:.2f})"
                )
        except Exception as e:
            logger.warning(f"Error in performance summary: {e}")
            self.stdout.write("  Performance calculation unavailable")
    
    def display_detailed_metrics(self):
        """Display detailed metrics when --detailed flag is used."""
        self.stdout.write("\n📊 DETAILED METRICS")
        self.stdout.write("-" * 40)
        
        # Get latest performance metrics
        latest_metrics = PaperPerformanceMetrics.objects.order_by(
            '-period_end'
        ).first()
        
        if not latest_metrics:
            self.stdout.write("  No detailed metrics available yet")
            return
        
        self.stdout.write(f"\n  Latest Metrics Period:")
        self.stdout.write(f"    Start: {latest_metrics.period_start}")
        self.stdout.write(f"    End: {latest_metrics.period_end}")
        
        self.stdout.write(f"\n  Trading Performance:")
        self.stdout.write(f"    Win Rate: {latest_metrics.win_rate:.1f}%")
        self.stdout.write(f"    Profit Factor: {latest_metrics.profit_factor or 'N/A'}")
        self.stdout.write(f"    Sharpe Ratio: {latest_metrics.sharpe_ratio or 'N/A'}")
        self.stdout.write(f"    Max Drawdown: {latest_metrics.max_drawdown_percent:.1f}%")
        
        self.stdout.write(f"\n  Execution Quality:")
        self.stdout.write(f"    Avg Execution Time: {latest_metrics.avg_execution_time_ms}ms")
        self.stdout.write(f"    Avg Slippage: {latest_metrics.avg_slippage_percent:.2f}%")
        self.stdout.write(f"    Gas Fees: ${latest_metrics.total_gas_fees_usd:.2f}")
    
    def display_footer(self):
        """Display footer."""
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(self.style.SUCCESS("✅ Paper Trading System is Operational"))
        self.stdout.write("=" * 80 + "\n")
        
        # Provide next steps
        self.stdout.write("Next Steps:")
        self.stdout.write("  1. Start a trading session: python manage.py run_paper_bot")
        self.stdout.write("  2. View in admin: http://localhost:8000/admin/paper_trading/")
        self.stdout.write("  3. Check dashboard: http://localhost:8000/paper-trading/")