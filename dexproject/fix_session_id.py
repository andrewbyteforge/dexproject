#!/usr/bin/env python3
"""
Fix the remaining session.id reference in ai_engine.py

Run from dexproject directory:
    python fix_session_id.py
"""

import os

def fix_ai_engine_session_id():
    """Fix session.id references in ai_engine.py"""
    
    file_path = "paper_trading/bot/ai_engine.py"
    
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return False
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Fix all session.id references
    replacements = [
        ("self.logger = logging.getLogger(f\"{__name__}.{session.id}\")",
         "self.logger = logging.getLogger(f\"{__name__}.{session.session_id}\")"),
        ("logger.info(f\"[BOT] AI Engine initialized for session {session.id}\")",
         "logger.info(f\"[BOT] AI Engine initialized for session {session.session_id}\")"),
    ]
    
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            print(f"✅ Fixed: {old[:50]}...")
    
    # Also check for any remaining .id references that should be .session_id
    if ".id}" in content and "session.id" in content:
        content = content.replace("session.id", "session.session_id")
        print("✅ Fixed remaining session.id references")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ Successfully fixed {file_path}")
    return True

def main():
    print("Fixing session ID references...")
    print("=" * 60)
    
    fix_ai_engine_session_id()
    
    print("\n✅ Fix complete!")
    print("\nNow run:")
    print("  python manage.py run_paper_bot")
    print("\nThe bot should work now!")

if __name__ == "__main__":
    main()