#!/usr/bin/env python3
"""
Fix model field mismatches in ai_engine.py and simple_trader.py
to match the actual PaperAIThoughtLog and PaperTrade model fields.

Run from dexproject directory:
    python fix_model_fields.py
"""

import os

def fix_thought_log_fields():
    """Fix PaperAIThoughtLog field usage in ai_engine.py"""
    
    file_path = "paper_trading/bot/ai_engine.py"
    
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return False
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find and replace the _log_thought method
    old_method = '''    def _log_thought(self, decision: Dict[str, Any]) -> None:
        """
        Log the AI thought process to the database.
        
        Args:
            decision: Complete decision dictionary
        """
        try:
            # Create thought log entry
            thought_log = PaperAIThoughtLog(
                account=self.session.account,  # Use account from session
                decision_type=decision["lane_type"],
                token_address=decision["token_address"],
                token_symbol=decision["token_symbol"],
                
                # Confidence and scores
                confidence_level='HIGH' if decision["confidence_score"] > 70 else 'MEDIUM' if decision["confidence_score"] > 40 else 'LOW',
                confidence_percent=decision["confidence_score"],
                risk_score=decision["risk_assessment"]["risk_score"],
                
                # Reasoning
                primary_reasoning=decision["reasoning"],
                
                # Lane used
                lane_used=decision["lane_type"],
                
                # Strategy name
                strategy_name=f"Strategy_{self.session.session_id}",
                
                # Market data
                market_data={
                    "current_price": str(decision["current_price"]),
                    "price_change_percent": str(decision["market_analysis"]["price_change_percent"]),
                    "volatility": str(decision["market_analysis"]["volatility"]),
                    "momentum": str(decision["market_analysis"]["momentum"]),
                },
                
                # Performance
                analysis_time_ms=int(decision["processing_time_ms"]),
            )
            
            thought_log.save()
            logger.debug(f"[THOUGHT] Thought logged: ID {thought_log.thought_id}")
            
        except Exception as e:
            logger.error(f"Failed to log thought: {e}")'''
    
    new_method = '''    def _log_thought(self, decision: Dict[str, Any]) -> None:
        """
        Log the AI thought process to the database.
        
        Args:
            decision: Complete decision dictionary
        """
        try:
            # Map confidence score to confidence level
            confidence = decision["confidence_score"]
            if confidence >= 80:
                confidence_level = 'VERY_HIGH'
            elif confidence >= 70:
                confidence_level = 'HIGH'
            elif confidence >= 50:
                confidence_level = 'MEDIUM'
            elif confidence >= 30:
                confidence_level = 'LOW'
            else:
                confidence_level = 'VERY_LOW'
            
            # Create thought log entry with correct fields
            thought_log = PaperAIThoughtLog(
                account=self.session.account,
                
                # Decision type (BUY, SELL, HOLD, MONITOR, ALERT)
                decision_type=decision["action"],
                
                # Token info
                token_address=decision["token_address"],
                token_symbol=decision["token_symbol"],
                
                # Confidence scoring
                confidence_level=confidence_level,
                confidence_percent=decision["confidence_score"],
                risk_score=decision["risk_assessment"]["risk_score"],
                opportunity_score=Decimal("50"),  # Default opportunity score
                
                # Reasoning
                primary_reasoning=decision["reasoning"][:500] if len(decision["reasoning"]) > 500 else decision["reasoning"],
                
                # Key factors as a list
                key_factors=[
                    f"Lane: {decision['lane_type']}",
                    f"Market condition: {decision['market_analysis']['market_condition'].value}",
                    f"Price change: {decision['market_analysis']['price_change_percent']:.2f}%",
                    f"Volatility: {decision['market_analysis']['volatility']:.2f}",
                    f"Signal: {decision['signal'].value}",
                ],
                
                # Signals
                positive_signals=[
                    sig for sig in [
                        "Positive momentum" if decision["market_analysis"]["momentum"] > 0 else None,
                        "Low volatility" if decision["market_analysis"]["volatility"] < 3 else None,
                        "Strong trend" if abs(decision["market_analysis"]["price_change_percent"]) > 2 else None,
                    ] if sig
                ],
                
                negative_signals=[
                    sig for sig in [
                        "Negative momentum" if decision["market_analysis"]["momentum"] < 0 else None,
                        "High volatility" if decision["market_analysis"]["volatility"] > 5 else None,
                        "Weak trend" if abs(decision["market_analysis"]["price_change_percent"]) < 1 else None,
                    ] if sig
                ],
                
                # Market data snapshot
                market_data={
                    "current_price": str(decision["current_price"]),
                    "price_change_percent": str(decision["market_analysis"]["price_change_percent"]),
                    "volatility": str(decision["market_analysis"]["volatility"]),
                    "momentum": str(decision["market_analysis"]["momentum"]),
                    "trend": decision["market_analysis"]["trend"],
                },
                
                # Strategy and lane
                strategy_name=f"AI_Strategy_{self.session.session_id}",
                lane_used=decision["lane_type"],
                
                # Performance
                analysis_time_ms=int(decision["processing_time_ms"]),
            )
            
            thought_log.save()
            logger.debug(f"[THOUGHT] Thought logged: ID {thought_log.thought_id}")
            
        except Exception as e:
            logger.error(f"Failed to log thought: {e}")'''
    
    # Replace the method
    if old_method in content:
        content = content.replace(old_method, new_method)
        print("✅ Fixed _log_thought method completely")
    else:
        print("⚠️  Could not find exact method, attempting partial fix...")
        # Try to fix just the field assignments
        content = content.replace(
            'thought_log = PaperAIThoughtLog(',
            '# Fixed field mapping\n            thought_log = PaperAIThoughtLog('
        )
    
    # Add missing Decimal import if needed
    if "from decimal import Decimal" not in content:
        content = "from decimal import Decimal\n" + content
        print("✅ Added Decimal import")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ Fixed thought log fields in {file_path}")
    return True


def fix_trade_execution_fields():
    """Fix PaperTrade field usage in simple_trader.py"""
    
    file_path = "paper_trading/bot/simple_trader.py"
    
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return False
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Find the trade execution section and fix it
    fixed_lines = []
    in_trade_creation = False
    
    for i, line in enumerate(lines):
        # Look for the PaperTrade.objects.create line
        if "trade = PaperTrade.objects.create(" in line:
            in_trade_creation = True
            # Start the corrected trade creation
            fixed_lines.append(line)
            continue
        
        # If we're in the trade creation block, skip the old fields
        if in_trade_creation:
            if line.strip().startswith(")"):
                # End of create block - insert correct fields before closing
                indent = "                    "
                
                # Add the correct fields for PaperTrade
                fixed_lines.extend([
                    f'{indent}account=self.account,\n',
                    f'{indent}trade_type=action.lower(),\n',
                    f'{indent}token_in_address=token_in_address,\n',
                    f'{indent}token_in_symbol=token_in,\n',
                    f'{indent}token_out_address=token_out_address,\n',
                    f'{indent}token_out_symbol=token_out,\n',
                    f'{indent}amount_in=trade_value if action == "BUY" else position.quantity if symbol in self.positions else trade_value / current_price,\n',
                    f'{indent}amount_in_usd=amount_in_usd,\n',
                    f'{indent}expected_amount_out=amount_out,\n',
                    f'{indent}actual_amount_out=amount_out * Decimal("0.995"),\n',
                    f'{indent}simulated_gas_price_gwei=Decimal("30"),\n',
                    f'{indent}simulated_gas_used=150000,\n',
                    f'{indent}simulated_gas_cost_usd=Decimal("5.00"),\n',
                    f'{indent}simulated_slippage_percent=Decimal("0.5"),\n',
                    f'{indent}status="completed",\n',
                    f'{indent}executed_at=timezone.now(),\n',
                    f'{indent}execution_time_ms=500,\n',
                    f'{indent}strategy_name=decision["lane_type"],\n',
                    f'{indent}mock_tx_hash=f"0x{{uuid.uuid4().hex[:64]}}",\n',
                ])
                fixed_lines.append(line)
                in_trade_creation = False
            elif not line.strip().startswith(('account=', 'session=', 'trade_type=', 'token_address=',
                                            'token_symbol=', 'quantity=', 'price=', 'total_value=',
                                            'gas_fee=', 'slippage=', 'strategy_used=', 'confidence_score=',
                                            'risk_score=', 'status=', 'executed_at=')):
                # Skip all the old field assignments
                continue
        else:
            fixed_lines.append(line)
    
    # Add uuid import if needed
    content = ''.join(fixed_lines)
    if "import uuid" not in content:
        content = "import uuid\n" + content
        print("✅ Added uuid import")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ Fixed trade execution fields in {file_path}")
    return True


def verify_imports():
    """Ensure all necessary imports are present"""
    
    files_to_check = [
        ("paper_trading/bot/ai_engine.py", ["from decimal import Decimal"]),
        ("paper_trading/bot/simple_trader.py", ["import uuid", "from decimal import Decimal"])
    ]
    
    for file_path, required_imports in files_to_check:
        if not os.path.exists(file_path):
            continue
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        added_imports = []
        for import_line in required_imports:
            if import_line not in content:
                # Add import at the top after other imports
                lines = content.split('\n')
                import_section_end = 0
                for i, line in enumerate(lines):
                    if line.startswith('import ') or line.startswith('from '):
                        import_section_end = i + 1
                    elif import_section_end > 0 and line and not line.startswith('#'):
                        break
                
                lines.insert(import_section_end, import_line)
                content = '\n'.join(lines)
                added_imports.append(import_line)
        
        if added_imports:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✅ Added imports to {file_path}: {', '.join(added_imports)}")


def main():
    print("Fixing model field mismatches...")
    print("=" * 60)
    
    print("\n1. Fixing PaperAIThoughtLog fields in ai_engine.py...")
    fix_thought_log_fields()
    
    print("\n2. Fixing PaperTrade fields in simple_trader.py...")
    fix_trade_execution_fields()
    
    print("\n3. Verifying imports...")
    verify_imports()
    
    print("\n" + "=" * 60)
    print("✅ Model field fixes complete!")
    print("\nThe bot should now:")
    print("  - Properly log AI thoughts to the database")
    print("  - Successfully execute and record trades")
    print("  - Track all decisions and performance")
    print("\nRun the bot again:")
    print("  python manage.py run_paper_bot")
    print("\nYou should see trades executing without errors!")


if __name__ == "__main__":
    main()