#!/usr/bin/env python3
"""
Fix the token_in_address variable scope issue in trade execution.

Run from dexproject directory:
    python fix_token_vars.py
"""

import os
import re

def fix_token_variables():
    file_path = "paper_trading/bot/simple_trader.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find the _execute_trade method and replace it with a corrected version
    # This pattern finds the entire method
    pattern = r'(def _execute_trade\(self.*?\n)(.*?)(\n    def |\nclass |\Z)'
    
    def replacement(match):
        method_signature = match.group(1)
        method_end = match.group(3)
        
        # New method body with properly scoped variables
        new_method_body = '''        """
        Execute a paper trade based on AI decision.
        
        Args:
            symbol: Token symbol
            decision: AI decision dictionary
        """
        action = decision['action']
        position_size_percent = decision['position_size_percent']
        current_price = decision['current_price']
        
        # Calculate trade amount
        portfolio_value = self.account.current_balance_usd
        trade_value = portfolio_value * (position_size_percent / 100)
        
        # Check if we have enough balance
        if action == 'BUY' and trade_value > self.account.current_balance_usd:
            logger.warning(f"[WARN] Insufficient balance for {symbol} purchase")
            return
        
        # Check if we have position to sell
        if action == 'SELL' and symbol not in self.positions:
            logger.warning(f"[WARN] No position to sell for {symbol}")
            return
        
        try:
            with transaction.atomic():
                # Define token variables BEFORE using them
                if action == 'BUY':
                    # Buy trade - USD to token
                    token_in = 'USDC'
                    token_in_address = '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'  # USDC
                    token_out = symbol
                    token_out_address = decision['token_address']
                    amount_in_usd = trade_value
                    amount_out = trade_value / current_price
                    amount_in = trade_value
                else:
                    # Sell trade - token to USD
                    position = self.positions[symbol]
                    token_in = symbol
                    token_in_address = decision['token_address']
                    token_out = 'USDC'
                    token_out_address = '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'  # USDC
                    amount_in = position.quantity
                    amount_out = position.quantity * current_price
                    amount_in_usd = amount_out
                
                # Create the trade record
                trade = PaperTrade.objects.create(
                    account=self.account,
                    trade_type=action.lower(),  # 'buy' or 'sell'
                    token_in_address=token_in_address,
                    token_in_symbol=token_in,
                    token_out_address=token_out_address,
                    token_out_symbol=token_out,
                    amount_in=amount_in,
                    amount_in_usd=amount_in_usd,
                    expected_amount_out=amount_out,
                    actual_amount_out=amount_out * Decimal("0.995"),  # 0.5% slippage
                    simulated_gas_price_gwei=Decimal("30"),
                    simulated_gas_used=150000,
                    simulated_gas_cost_usd=Decimal("5.00"),
                    simulated_slippage_percent=Decimal("0.5"),
                    status='completed',
                    executed_at=timezone.now(),
                    execution_time_ms=500,
                    strategy_name=decision['lane_type'],
                    mock_tx_hash=f"0x{uuid.uuid4().hex[:64]}"
                )
                
                # Update position
                if action == 'BUY':
                    # Create or update position
                    if symbol in self.positions:
                        position = self.positions[symbol]
                        # Average the entry price
                        total_value = (position.quantity * position.average_entry_price_usd) + trade_value
                        position.quantity += amount_out
                        position.average_entry_price_usd = total_value / position.quantity
                        position.current_price_usd = current_price
                        position.total_invested_usd += trade_value
                        position.last_updated = timezone.now()
                        position.save()
                    else:
                        position = PaperPosition.objects.create(
                            account=self.account,
                            token_address=decision['token_address'],
                            token_symbol=symbol,
                            quantity=amount_out,
                            average_entry_price_usd=current_price,
                            current_price_usd=current_price,
                            total_invested_usd=trade_value,
                            is_open=True
                        )
                        self.positions[symbol] = position
                    
                    # Update account balance
                    self.account.current_balance_usd -= trade_value
                    
                else:  # SELL
                    position = self.positions[symbol]
                    
                    # Calculate P&L
                    pnl = (current_price - position.average_entry_price_usd) * position.quantity
                    pnl_percent = (pnl / position.total_invested_usd) * 100 if position.total_invested_usd > 0 else 0
                    
                    # Update position for closure
                    position.current_price_usd = current_price
                    position.realized_pnl_usd = pnl
                    position.is_open = False
                    position.closed_at = timezone.now()
                    position.save()
                    
                    # Remove from active positions
                    del self.positions[symbol]
                    
                    # Update account balance
                    self.account.current_balance_usd += amount_out - Decimal("5.00")  # Minus gas
                    
                    # Track performance
                    if pnl > 0:
                        self.successful_trades += 1
                
                # Save account changes
                self.account.total_trades += 1
                self.account.save()
                
                # Update metrics
                self.trades_executed += 1
                self.last_trade_time = datetime.now()
                
                # Log trade execution
                logger.info(f"[OK] {action} executed: {amount_out:.6f} {symbol} @ ${current_price:.6f}")
                logger.info(f"[MONEY] Value: ${trade_value:.2f}, New balance: ${self.account.current_balance_usd:.2f}")
                
                if action == 'SELL':
                    logger.info(f"[DATA] P&L: ${pnl:.2f} ({pnl_percent:.2f}%)")
                
                # Update AI performance metrics
                if action == 'SELL':
                    self.ai_engine.update_performance_metrics({
                        'profitable': pnl > 0,
                        'pnl': pnl
                    })
                
        except Exception as e:
            logger.error(f"[ERROR] Trade execution failed: {e}")
'''
        
        return method_signature + new_method_body + method_end
    
    # Apply the replacement
    content = re.sub(pattern, replacement, content, flags=re.DOTALL)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Fixed token variable scoping in _execute_trade method")

def main():
    print("Fixing token variable scope issue...")
    print("=" * 60)
    
    fix_token_variables()
    
    print("\n✅ Fix complete!")
    print("\nThe _execute_trade method now properly defines all variables before use.")
    print("\nRun the bot again:")
    print("  python manage.py run_paper_bot")
    print("\nYou should now see trades executing successfully!")

if __name__ == "__main__":
    main()