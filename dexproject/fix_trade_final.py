#!/usr/bin/env python3
"""
Final fix for trade execution - ensure variables are defined before use.

Run from dexproject directory:
    python fix_trade_final.py
"""

import os

def fix_trade_execution():
    file_path = "paper_trading/bot/simple_trader.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Find the _execute_trade method and fix the variable definitions
    new_lines = []
    in_execute_trade = False
    fixed = False
    
    for i, line in enumerate(lines):
        if 'def _execute_trade(self, symbol:' in line:
            in_execute_trade = True
            new_lines.append(line)
        elif in_execute_trade and 'try:' in line and not fixed:
            new_lines.append(line)
            # Add the next line (with transaction.atomic():)
            if i+1 < len(lines):
                new_lines.append(lines[i+1])
            
            # Now add the proper variable definitions right after "with transaction.atomic():"
            indent = "                "
            new_lines.append(f'{indent}# Calculate trade values\n')
            new_lines.append(f'{indent}if action == "BUY":\n')
            new_lines.append(f'{indent}    # Buy trade - USD to token\n')
            new_lines.append(f'{indent}    token_in = "USDC"\n')
            new_lines.append(f'{indent}    token_in_address = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"  # USDC\n')
            new_lines.append(f'{indent}    token_out = symbol\n')
            new_lines.append(f'{indent}    token_out_address = decision["token_address"]\n')
            new_lines.append(f'{indent}    amount_in_usd = trade_value\n')
            new_lines.append(f'{indent}    amount_out = trade_value / current_price\n')
            new_lines.append(f'{indent}else:\n')
            new_lines.append(f'{indent}    # Sell trade - token to USD\n')
            new_lines.append(f'{indent}    token_in = symbol\n')
            new_lines.append(f'{indent}    token_in_address = decision["token_address"]\n')
            new_lines.append(f'{indent}    token_out = "USDC"\n')
            new_lines.append(f'{indent}    token_out_address = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"  # USDC\n')
            new_lines.append(f'{indent}    if symbol in self.positions:\n')
            new_lines.append(f'{indent}        position = self.positions[symbol]\n')
            new_lines.append(f'{indent}        amount_out = position.quantity * current_price\n')
            new_lines.append(f'{indent}        amount_in_usd = amount_out\n')
            new_lines.append(f'{indent}    else:\n')
            new_lines.append(f'{indent}        amount_out = trade_value\n')
            new_lines.append(f'{indent}        amount_in_usd = trade_value\n')
            new_lines.append(f'{indent}\n')
            
            # Skip the next line as we already added it
            fixed = True
            continue
        elif in_execute_trade and '# Define token addresses' in line:
            # Skip the old variable definitions section
            skip_count = 0
            while skip_count < 20 and i + skip_count < len(lines):
                if '# Create the trade record' in lines[i + skip_count]:
                    break
                skip_count += 1
            # Skip to after the old definitions
            continue
        elif in_execute_trade and not line.strip().startswith('def '):
            new_lines.append(line)
        else:
            in_execute_trade = False
            new_lines.append(line)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    print("✅ Fixed trade execution variable definitions")

def main():
    print("Applying final trade execution fix...")
    print("=" * 60)
    
    fix_trade_execution()
    
    print("\n✅ Fix complete!")
    print("\nRun the bot again:")
    print("  python manage.py run_paper_bot")
    print("\nThe bot should now execute trades successfully!")

if __name__ == "__main__":
    main()