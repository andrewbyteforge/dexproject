#!/usr/bin/env python3
"""
Automated Import Updater for Intelligence Folder Reorganization

This script automatically updates all imports after reorganizing the
paper_trading/intelligence folder structure from flat to Option 1 structure.

Option 1 Structure:
    intelligence/
    ├── config/         (intel_config.py)
    ├── core/           (base.py, intel_slider.py)
    ├── strategies/     (decision_maker.py, arbitrage_engine.py)
    ├── data/           (price_history.py, ml_features.py)
    ├── dex/            (dex_integrations.py, dex_price_comparator.py)
    │   └── protocols/  (uniswap_v3.py, sushiswap.py, curve.py)
    └── analyzers/      (unchanged)

Usage:
    # Dry run (preview changes only)
    python update_intelligence_imports.py --dry-run
    
    # Apply changes with backups
    python update_intelligence_imports.py
    
    # Apply changes without backups
    python update_intelligence_imports.py --no-backup

File: update_intelligence_imports.py
"""

import os
import re
import shutil
import argparse
from pathlib import Path
from typing import List, Tuple, Dict
from datetime import datetime


# =============================================================================
# IMPORT MAPPING - OLD PATH → NEW PATH
# =============================================================================

IMPORT_MAPPINGS = {
    # IMPORTANT: More specific paths MUST come before general ones
    # Otherwise "dex_integrations.base" would match "dex_integrations" first
    
    # DEX Protocols (subfolder rename) - MUST BE FIRST
    'paper_trading.intelligence.dex_integrations.base': 'paper_trading.intelligence.dex.protocols.base',
    'paper_trading.intelligence.dex_integrations.constants': 'paper_trading.intelligence.dex.protocols.constants',
    'paper_trading.intelligence.dex_integrations.uniswap_v3': 'paper_trading.intelligence.dex.protocols.uniswap_v3',
    'paper_trading.intelligence.dex_integrations.sushiswap': 'paper_trading.intelligence.dex.protocols.sushiswap',
    'paper_trading.intelligence.dex_integrations.curve': 'paper_trading.intelligence.dex.protocols.curve',
    'paper_trading.intelligence.dex_integrations.__init__': 'paper_trading.intelligence.dex.protocols.__init__',
    
    # Configuration
    'paper_trading.intelligence.intel_config': 'paper_trading.intelligence.config.intel_config',
    
    # Core
    'paper_trading.intelligence.base': 'paper_trading.intelligence.core.base',
    'paper_trading.intelligence.intel_slider': 'paper_trading.intelligence.core.intel_slider',
    
    # Strategies
    'paper_trading.intelligence.decision_maker': 'paper_trading.intelligence.strategies.decision_maker',
    'paper_trading.intelligence.arbitrage_engine': 'paper_trading.intelligence.strategies.arbitrage_engine',
    'paper_trading.intelligence.arbitrage_detector': 'paper_trading.intelligence.strategies.arbitrage_engine',  # Merged
    
    # Data
    'paper_trading.intelligence.price_history': 'paper_trading.intelligence.data.price_history',
    'paper_trading.intelligence.ml_features': 'paper_trading.intelligence.data.ml_features',
    
    # DEX - AFTER specific dex_integrations paths
    'paper_trading.intelligence.dex_integrations': 'paper_trading.intelligence.dex.protocols',
    'paper_trading.intelligence.dex_price_comparator': 'paper_trading.intelligence.dex.dex_price_comparator',
    
    # Analyzers - unchanged but need to be in mapping for completeness
    'paper_trading.intelligence.analyzers': 'paper_trading.intelligence.analyzers',
}


# =============================================================================
# FILE SCANNER
# =============================================================================

def find_python_files(root_dir: Path) -> List[Path]:
    """
    Find all Python files in the project.
    
    Args:
        root_dir: Root directory to search from
        
    Returns:
        List of Python file paths
    """
    python_files = []
    
    # Directories to search
    search_dirs = [
        root_dir / 'paper_trading',
        root_dir / 'trading',
        root_dir / 'engine',
        root_dir / 'shared',
    ]
    
    for search_dir in search_dirs:
        if search_dir.exists():
            for py_file in search_dir.rglob('*.py'):
                # Skip __pycache__ and migrations
                if '__pycache__' not in str(py_file) and 'migrations' not in str(py_file):
                    python_files.append(py_file)
    
    return python_files


# =============================================================================
# IMPORT DETECTION AND UPDATE
# =============================================================================

def detect_intelligence_imports(content: str) -> List[Tuple[str, str, int]]:
    """
    Detect all imports from paper_trading.intelligence.
    
    Args:
        content: File content
        
    Returns:
        List of (import_statement, old_path, line_number) tuples
    """
    imports = []
    lines = content.split('\n')
    
    for line_num, line in enumerate(lines, start=1):
        # Match: from paper_trading.intelligence.X import Y
        match1 = re.match(r'^(\s*)from\s+(paper_trading\.intelligence\.[a-zA-Z0-9_.]+)\s+import\s+(.+)$', line)
        if match1:
            imports.append((line.strip(), match1.group(2), line_num))
            continue
        
        # Match: import paper_trading.intelligence.X
        match2 = re.match(r'^(\s*)import\s+(paper_trading\.intelligence\.[a-zA-Z0-9_.]+)(\s+as\s+.+)?$', line)
        if match2:
            imports.append((line.strip(), match2.group(2), line_num))
            continue
    
    return imports


def update_import_statement(line: str, old_path: str, new_path: str) -> str:
    """
    Update a single import statement.
    
    Args:
        line: Original import line
        old_path: Old import path
        new_path: New import path
        
    Returns:
        Updated import line
    """
    # Preserve whitespace
    leading_whitespace = len(line) - len(line.lstrip())
    indent = ' ' * leading_whitespace
    
    # Replace old path with new path
    updated_line = line.replace(old_path, new_path)
    
    return updated_line


def update_file_imports(file_path: Path, dry_run: bool = False) -> Tuple[int, List[str]]:
    """
    Update all intelligence imports in a file.
    
    Args:
        file_path: Path to Python file
        dry_run: If True, don't actually modify file
        
    Returns:
        Tuple of (number of changes, list of change descriptions)
    """
    try:
        # Read file content
        with open(file_path, 'r', encoding='utf-8') as f:
            original_content = f.read()
        
        # Detect imports
        imports = detect_intelligence_imports(original_content)
        
        if not imports:
            return 0, []
        
        # Update content
        updated_content = original_content
        changes = []
        
        for import_stmt, old_path, line_num in imports:
            # Find matching new path
            new_path = None
            for old_pattern, new_pattern in IMPORT_MAPPINGS.items():
                if old_path.startswith(old_pattern):
                    # Handle sub-imports (e.g., paper_trading.intelligence.analyzers.base)
                    new_path = old_path.replace(old_pattern, new_pattern, 1)
                    break
            
            if new_path and new_path != old_path:
                # Update the import
                updated_content = updated_content.replace(
                    f'{old_path}',
                    f'{new_path}'
                )
                
                changes.append(
                    f"  Line {line_num}: {old_path} → {new_path}"
                )
        
        # Write updated content (if not dry run)
        if changes and not dry_run:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(updated_content)
        
        return len(changes), changes
        
    except Exception as e:
        print(f"ERROR processing {file_path}: {e}")
        return 0, []


# =============================================================================
# BACKUP FUNCTIONALITY
# =============================================================================

def create_backup(file_path: Path, backup_dir: Path) -> Path:
    """
    Create a backup of a file.
    
    Args:
        file_path: File to backup
        backup_dir: Directory to store backups
        
    Returns:
        Path to backup file
    """
    # Create backup directory structure
    rel_path = file_path.relative_to(file_path.parent.parent.parent)
    backup_path = backup_dir / rel_path
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Copy file
    shutil.copy2(file_path, backup_path)
    
    return backup_path


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description='Update intelligence imports after folder reorganization'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without applying them'
    )
    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Skip creating backups (not recommended)'
    )
    parser.add_argument(
        '--root-dir',
        type=str,
        default='.',
        help='Root directory of the project (default: current directory)'
    )
    
    args = parser.parse_args()
    
    # Get project root
    root_dir = Path(args.root_dir).resolve()
    
    # Check if we're in the right directory
    paper_trading_dir = root_dir / 'paper_trading'
    if not paper_trading_dir.exists():
        print(f"ERROR: paper_trading directory not found in {root_dir}")
        print("Please run this script from the dexproject root directory")
        return 1
    
    print("=" * 80)
    print("INTELLIGENCE IMPORTS UPDATE SCRIPT")
    print("=" * 80)
    print(f"Root directory: {root_dir}")
    print(f"Dry run: {args.dry_run}")
    print(f"Create backups: {not args.no_backup}")
    print()
    
    # Create backup directory
    backup_dir = None
    if not args.dry_run and not args.no_backup:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = root_dir / f'backups_imports_{timestamp}'
        backup_dir.mkdir(parents=True, exist_ok=True)
        print(f"Backup directory: {backup_dir}")
        print()
    
    # Find all Python files
    print("Scanning for Python files...")
    python_files = find_python_files(root_dir)
    print(f"Found {len(python_files)} Python files")
    print()
    
    # Process each file
    print("Processing files...")
    print("-" * 80)
    
    total_changes = 0
    files_modified = 0
    
    for file_path in python_files:
        # Create backup if needed
        if backup_dir and not args.dry_run:
            try:
                create_backup(file_path, backup_dir)
            except Exception as e:
                print(f"WARNING: Could not backup {file_path}: {e}")
        
        # Update imports
        num_changes, changes = update_file_imports(file_path, dry_run=args.dry_run)
        
        if num_changes > 0:
            files_modified += 1
            total_changes += num_changes
            
            rel_path = file_path.relative_to(root_dir)
            print(f"\n{rel_path}:")
            for change in changes:
                print(change)
    
    # Summary
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Files scanned: {len(python_files)}")
    print(f"Files modified: {files_modified}")
    print(f"Total changes: {total_changes}")
    
    if args.dry_run:
        print()
        print("DRY RUN - No files were actually modified")
        print("Run without --dry-run to apply changes")
    else:
        print()
        print("✓ All imports updated successfully!")
        if backup_dir:
            print(f"✓ Backups saved to: {backup_dir}")
    
    print()
    return 0


if __name__ == '__main__':
    exit(main())