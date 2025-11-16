from paper_trading.models import PaperPosition, PaperTrade, PaperStrategyConfiguration, PaperAIThoughtLog
from decimal import Decimal

print("\n" + "="*60)
print("SELL DIAGNOSTIC REPORT")
print("="*60)

# 1. Open positions
open_pos = PaperPosition.objects.filter(is_open=True)
print(f"\n1. OPEN POSITIONS: {open_pos.count()}")
if open_pos.count() > 0:
    for p in open_pos[:10]:
        pnl = ((p.current_price_usd - p.average_entry_price_usd) / p.average_entry_price_usd) * 100
        print(f"   {p.token_symbol}: Entry=${p.average_entry_price_usd:.4f}, Current=${p.current_price_usd:.4f}, P&L={pnl:+.2f}%")
        print(f"      Should hit stop-loss (-5%)? {pnl <= -5}")
        print(f"      Should hit take-profit (+10%)? {pnl >= 10}")

# 2. Strategy config
config = PaperStrategyConfiguration.objects.first()
print(f"\n2. STRATEGY CONFIG:")
if config:
    print(f"   Stop Loss: {config.stop_loss_percent}%")
    print(f"   Take Profit: {config.take_profit_percent}%")
    print(f"   Max Hold Time: {config.max_hold_time_hours}h")
else:
    print("   No config found!")

# 3. Sell trades
sell_trades = PaperTrade.objects.filter(trade_type='sell')
print(f"\n3. SELL TRADES: {sell_trades.count()}")
if sell_trades.count() > 0:
    for t in sell_trades[:5]:
        print(f"   {t.token_symbol} at {t.created_at}")

# 4. Sell decisions
sell_decisions = PaperAIThoughtLog.objects.filter(decision_type='SELL')
print(f"\n4. SELL DECISIONS IN LOGS: {sell_decisions.count()}")
if sell_decisions.count() > 0:
    latest = sell_decisions.order_by('-created_at').first()
    print(f"   Latest: {latest.token_symbol} at {latest.created_at}")
    print(f"   Reasoning: {latest.reasoning[:150]}...")

# 5. Trade breakdown
all_trades = PaperTrade.objects.all()
buy_count = all_trades.filter(trade_type='buy').count()
sell_count = all_trades.filter(trade_type='sell').count()
print(f"\n5. TRADE BREAKDOWN:")
print(f"   Total: {all_trades.count()}")
print(f"   BUY: {buy_count}")
print(f"   SELL: {sell_count}")

# 6. Decision breakdown
all_decisions = PaperAIThoughtLog.objects.all()
buy_dec = all_decisions.filter(decision_type='BUY').count()
sell_dec = all_decisions.filter(decision_type='SELL').count()
skip_dec = all_decisions.filter(decision_type='SKIP').count()
hold_dec = all_decisions.filter(decision_type='HOLD').count()
print(f"\n6. DECISION BREAKDOWN:")
print(f"   BUY: {buy_dec}")
print(f"   SELL: {sell_dec}")
print(f"   SKIP: {skip_dec}")
print(f"   HOLD: {hold_dec}")

print("\n" + "="*60)
print("DIAGNOSIS COMPLETE")
print("="*60 + "\n")