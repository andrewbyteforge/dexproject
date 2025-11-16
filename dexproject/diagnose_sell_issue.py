"""
Diagnostic script to identify why the bot isn't selling.

Run this from your Django shell:
python manage.py shell < diagnose_sell_issue.py

Or copy-paste into Django shell.
"""

from paper_trading.models import PaperPosition, PaperTrade, PaperStrategyConfiguration
from decimal import Decimal

print("\n" + "="*60)
print("SELL LOGIC DIAGNOSTIC REPORT")
print("="*60)

# 1. Check if there are any open positions
open_positions = PaperPosition.objects.filter(is_open=True)
print(f"\n1. OPEN POSITIONS: {open_positions.count()}")

if open_positions.count() > 0:
    for pos in open_positions[:5]:  # Show first 5
        pnl_pct = ((pos.current_price_usd - pos.average_entry_price_usd) / pos.average_entry_price_usd) * 100
        print(f"   - {pos.token_symbol}: Entry=${pos.average_entry_price_usd:.4f}, Current=${pos.current_price_usd:.4f}, P&L={pnl_pct:+.2f}%")
        
        # Check if should trigger auto-close
        print(f"     Should hit stop-loss (-5%)? {pnl_pct <= -5}")
        print(f"     Should hit take-profit (+10%)? {pnl_pct >= 10}")

# 2. Check strategy configuration
configs = PaperStrategyConfiguration.objects.all()
print(f"\n2. STRATEGY CONFIGURATIONS: {configs.count()}")

if configs.count() > 0:
    config = configs.first()
    print(f"   Stop Loss: {config.stop_loss_percent}%")
    print(f"   Take Profit: {config.take_profit_percent}%")
    print(f"   Max Hold Time: {config.max_hold_time_hours} hours")

# 3. Check for any SELL trades in history
sell_trades = PaperTrade.objects.filter(trade_type='sell')
print(f"\n3. HISTORICAL SELL TRADES: {sell_trades.count()}")

if sell_trades.count() > 0:
    latest_sell = sell_trades.order_by('-created_at').first()
    print(f"   Latest SELL: {latest_sell.token_symbol} at {latest_sell.created_at}")
else:
    print("   ⚠️  NO SELL TRADES FOUND - This is the problem!")

# 4. Check for SELL decisions in thought logs
from paper_trading.models import PaperAIThoughtLog

sell_thoughts = PaperAIThoughtLog.objects.filter(decision_type='SELL')
print(f"\n4. SELL DECISIONS IN THOUGHT LOGS: {sell_thoughts.count()}")

if sell_thoughts.count() > 0:
    latest_sell_thought = sell_thoughts.order_by('-created_at').first()
    print(f"   Latest SELL decision: {latest_sell_thought.created_at}")
    print(f"   Token: {latest_sell_thought.token_symbol}")
    print(f"   Reasoning: {latest_sell_thought.reasoning[:200]}...")
else:
    print("   ⚠️  NO SELL DECISIONS FOUND - Decision maker never triggering SELL!")

# 5. Check all trades - are they all BUY?
all_trades = PaperTrade.objects.all()
buy_count = all_trades.filter(trade_type='buy').count()
sell_count = all_trades.filter(trade_type='sell').count()

print(f"\n5. TRADE TYPE BREAKDOWN:")
print(f"   Total Trades: {all_trades.count()}")
print(f"   BUY: {buy_count}")
print(f"   SELL: {sell_count}")

# 6. Check decision types in thought logs
buy_decisions = PaperAIThoughtLog.objects.filter(decision_type='BUY').count()
sell_decisions = PaperAIThoughtLog.objects.filter(decision_type='SELL').count()
skip_decisions = PaperAIThoughtLog.objects.filter(decision_type='SKIP').count()
hold_decisions = PaperAIThoughtLog.objects.filter(decision_type='HOLD').count()

print(f"\n6. DECISION TYPE BREAKDOWN:")
print(f"   BUY: {buy_decisions}")
print(f"   SELL: {sell_decisions}")
print(f"   SKIP: {skip_decisions}")
print(f"   HOLD: {hold_decisions}")

print("\n" + "="*60)
print("DIAGNOSIS COMPLETE")
print("="*60 + "\n")