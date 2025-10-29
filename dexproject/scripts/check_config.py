#!/usr/bin/env python
"""
Simple Configuration Checker and Fixer

Checks your paper trading configuration and fixes the intel_level issue.

Run with:
    python scripts/check_config.py

Or from Django:
    python manage.py shell < scripts/check_config.py

File: dexproject/scripts/check_config.py
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
django.setup()

from paper_trading.models import PaperStrategyConfiguration
from paper_trading.constants import get_intel_level_from_trading_mode


def check_and_fix_config():
    """Check and fix paper trading configuration."""
    
    print("\n" + "=" * 70)
    print("PAPER TRADING CONFIGURATION CHECKER")
    print("=" * 70 + "\n")
    
    # Find all active configs
    active_configs = PaperStrategyConfiguration.objects.filter(is_active=True)
    count = active_configs.count()
    
    print(f"Found {count} active configuration(s):\n")
    
    if count == 0:
        print("❌ ERROR: No active configurations found!")
        print("   Create a configuration on the dashboard first.\n")
        return
    
    # Display all active configs
    for i, config in enumerate(active_configs, 1):
        intel_level_calc = get_intel_level_from_trading_mode(config.trading_mode)
        is_correct = config.intel_level == intel_level_calc
        
        print(f"[{i}] {config.name}")
        print(f"    Trading Mode: {config.trading_mode}")
        print(f"    Intel Level (Database): {config.intel_level}")
        print(f"    Intel Level (Expected): {intel_level_calc}")
        
        if is_correct:
            print(f"    Status: ✅ Correct")
        else:
            print(f"    Status: ⚠️  MISMATCH - DB has {config.intel_level}, should be {intel_level_calc}")
        
        print(f"    Updated: {config.updated_at}")
        print()
    
    # Check for issues
    issues = []
    
    if count > 1:
        issues.append(f"Multiple active configs ({count}) - should be only 1")
    
    for config in active_configs:
        intel_level_calc = get_intel_level_from_trading_mode(config.trading_mode)
        if config.intel_level != intel_level_calc:
            issues.append(
                f"Config '{config.name}' has intel_level={config.intel_level} "
                f"but {config.trading_mode} mode should be {intel_level_calc}"
            )
    
    # Report issues
    if issues:
        print("\n" + "=" * 70)
        print("⚠️  ISSUES FOUND:")
        print("=" * 70)
        for issue in issues:
            print(f"  • {issue}")
        print()
        
        # Ask to fix
        response = input("Do you want to fix these issues? (yes/no): ").lower().strip()
        
        if response == 'yes' or response == 'y':
            print("\nFixing issues...\n")
            
            # Keep the most recent config
            chosen_config = active_configs.order_by('-updated_at').first()
            print(f"✅ Keeping active: {chosen_config.name}")
            
            # Fix intel level
            correct_intel = get_intel_level_from_trading_mode(chosen_config.trading_mode)
            if chosen_config.intel_level != correct_intel:
                chosen_config.intel_level = correct_intel
                chosen_config.save(update_fields=['intel_level'])
                print(f"✅ Updated intel_level to {correct_intel}")
            
            # Deactivate others
            if count > 1:
                other_configs = active_configs.exclude(config_id=chosen_config.config_id)
                for config in other_configs:
                    config.is_active = False
                    config.save(update_fields=['is_active'])
                    print(f"✅ Deactivated: {config.name}")
            
            print("\n" + "=" * 70)
            print("✅ CONFIGURATION FIXED!")
            print("=" * 70)
            print(f"\nActive Configuration: {chosen_config.name}")
            print(f"  • Trading Mode: {chosen_config.trading_mode}")
            print(f"  • Intel Level: {chosen_config.intel_level}")
            
            intel_map = {
                3: "CONSERVATIVE - Skips trades with risk > 30%",
                5: "MODERATE - Skips trades with risk > 60%",
                8: "AGGRESSIVE - Only skips if risk > 90%"
            }
            behavior = intel_map.get(chosen_config.intel_level, f"Custom (Level {chosen_config.intel_level})")
            print(f"  • Bot Behavior: {behavior}")
            
            print("\nNext steps:")
            print("  1. Restart Celery workers")
            print("  2. Start bot from dashboard")
            print("  3. Verify logs show correct intel_level")
            print()
        else:
            print("\n❌ Fix cancelled. No changes made.\n")
    else:
        print("\n" + "=" * 70)
        print("✅ ALL GOOD!")
        print("=" * 70)
        print("Your configuration is correct. No issues found.\n")
    
    print("=" * 70 + "\n")


if __name__ == "__main__":
    try:
        check_and_fix_config()
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)