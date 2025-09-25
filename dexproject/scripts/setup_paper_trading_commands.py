"""
Script to create the management commands directory structure for paper trading.

Run this to set up the management commands folder.

File: dexproject/scripts/setup_paper_trading_commands.py
"""

import os
from pathlib import Path


def create_management_structure():
    """Create the management commands directory structure."""
    
    print("Creating paper_trading management commands structure...")
    
    # Base path for paper_trading app
    base_path = Path("paper_trading")
    
    # Create management directory
    management_dir = base_path / "management"
    management_dir.mkdir(exist_ok=True)
    (management_dir / "__init__.py").touch()
    print(f"✅ Created: {management_dir}")
    
    # Create commands directory
    commands_dir = management_dir / "commands"
    commands_dir.mkdir(exist_ok=True)
    (commands_dir / "__init__.py").touch()
    print(f"✅ Created: {commands_dir}")
    
    print("\n✅ Management structure created successfully!")
    print("\nYou can now:")
    print("1. Copy verify_paper_trading.py to paper_trading/management/commands/")
    print("2. Run: python manage.py verify_paper_trading --create-test-data")
    print("3. Check Django admin at http://localhost:8000/admin/")
    
    return True


if __name__ == "__main__":
    create_management_structure()