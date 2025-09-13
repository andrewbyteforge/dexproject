#!/usr/bin/env python3
"""
Comprehensive Duplication Fixer Script

This script systematically fixes the major duplication issues identified
in the Django project by updating management commands to use the shared
base class and applying other deduplication fixes.

Usage:
    python scripts/fix_duplications.py [--dry-run] [--verbose]
"""

import os
import sys
import shutil
import re
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Tuple
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DuplicationFixer:
    """
    Fixes code duplications in the Django project.
    """
    
    def __init__(self, project_root: str, dry_run: bool = False, verbose: bool = False):
        """
        Initialize the duplication fixer.
        
        Args:
            project_root: Root directory of the Django project
            dry_run: If True, show what would be changed without making changes
            verbose: Enable verbose output
        """
        self.project_root = Path(project_root)
        self.dry_run = dry_run
        self.verbose = verbose
        
        # Ensure we can find the shared base class
        self.shared_base_path = self.project_root / "shared" / "management" / "commands" / "base.py"
        
        # Management commands that need to be updated
        self.management_commands = [
            "risk/management/commands/create_risk_checks.py",
            "risk/management/commands/create_risk_profiles.py", 
            "trading/management/commands/create_default_strategies.py",
            "trading/management/commands/populate_chains_and_dexes.py"
        ]
        
        # Track changes made
        self.changes_made = []
        
        if verbose:
            logger.setLevel(logging.DEBUG)
    
    def create_backup(self) -> str:
        """Create a backup of the project before making changes."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self.project_root / "backups" / f"duplication_fix_{timestamp}"
        
        if not self.dry_run:
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy all Python files
            for py_file in self.project_root.rglob("*.py"):
                if "backups" in str(py_file) or ".venv" in str(py_file) or "__pycache__" in str(py_file):
                    continue
                
                rel_path = py_file.relative_to(self.project_root)
                backup_file = backup_dir / rel_path
                backup_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(py_file, backup_file)
        
        logger.info(f"Backup created at: {backup_dir}")
        return str(backup_dir)
    
    def verify_shared_base_exists(self) -> bool:
        """Verify that the shared base class exists."""
        if not self.shared_base_path.exists():
            logger.error(f"Shared base class not found at: {self.shared_base_path}")
            logger.error("Please run the duplication fixer tool first to create shared base classes")
            return False
        
        logger.info("✓ Shared base class found")
        return True
    
    def fix_management_command(self, command_path: str) -> bool:
        """
        Fix a single management command to use BaseDexCommand.
        
        Args:
            command_path: Relative path to the management command file
            
        Returns:
            True if changes were made, False otherwise
        """
        file_path = self.project_root / command_path
        
        if not file_path.exists():
            logger.warning(f"Management command not found: {file_path}")
            return False
        
        logger.info(f"Processing: {command_path}")
        
        try:
            # Read the file
            content = file_path.read_text(encoding='utf-8')
            original_content = content
            
            # Check if already updated
            if "from shared.management.commands.base import BaseDexCommand" in content:
                logger.info(f"  ✓ Already updated: {command_path}")
                return False
            
            # 1. Update the import
            content = re.sub(
                r'from django\.core\.management\.base import BaseCommand',
                'from django.core.management.base import BaseCommand\nfrom shared.management.commands.base import BaseDexCommand',
                content
            )
            
            # 2. Update class inheritance
            content = re.sub(
                r'class Command\(BaseCommand\):',
                'class Command(BaseDexCommand):',
                content
            )
            
            # 3. Change handle method to execute_command
            content = re.sub(
                r'def handle\(self, \*args, \*\*options\):',
                'def execute_command(self, *args, **options):',
                content
            )
            
            # 4. Remove duplicate _log_info method
            content = re.sub(
                r'\s+def _log_info\(self, message: str\) -> None:.*?logger\.info\(message\)\s*\n',
                '',
                content,
                flags=re.DOTALL
            )
            
            # 5. Remove duplicate _log_success method  
            content = re.sub(
                r'\s+def _log_success\(self, message: str\) -> None:.*?logger\.info\(message\)\s*\n',
                '',
                content,
                flags=re.DOTALL
            )
            
            # Check if any changes were made
            if content == original_content:
                logger.info(f"  → No changes needed for: {command_path}")
                return False
            
            # Write the updated content
            if not self.dry_run:
                file_path.write_text(content, encoding='utf-8')
                logger.info(f"  ✓ Updated: {command_path}")
            else:
                logger.info(f"  → Would update: {command_path}")
            
            self.changes_made.append(f"Updated management command: {command_path}")
            return True
            
        except Exception as e:
            logger.error(f"  ✗ Error processing {command_path}: {e}")
            return False
    
    def fix_model_mixins(self) -> int:
        """
        Update models to use shared mixins for common fields.
        
        Returns:
            Number of files updated
        """
        logger.info("Fixing model mixins...")
        
        model_files = [
            "dashboard/models.py",
            "trading/models.py", 
            "risk/models.py",
            "wallet/models.py",
            "analytics/models.py"
        ]
        
        files_updated = 0
        
        for model_file in model_files:
            file_path = self.project_root / model_file
            
            if not file_path.exists():
                continue
                
            try:
                content = file_path.read_text(encoding='utf-8')
                original_content = content
                
                # Add import for shared mixins if not present
                if "from shared.models.mixins import" not in content:
                    # Find Django imports
                    django_import_match = re.search(r'(from django\.db import models)', content)
                    if django_import_match:
                        content = content.replace(
                            django_import_match.group(1),
                            f"{django_import_match.group(1)}\nfrom shared.models.mixins import TimestampMixin, UUIDMixin"
                        )
                
                # Replace common timestamp fields with mixin
                # Look for models with created_at and updated_at fields
                timestamp_pattern = r'(\s+created_at = models\.DateTimeField\(auto_now_add=True.*?\n\s+updated_at = models\.DateTimeField\(auto_now=True.*?\n)'
                
                if re.search(timestamp_pattern, content, re.DOTALL):
                    # Replace the fields with mixin inheritance
                    content = re.sub(timestamp_pattern, '', content, flags=re.DOTALL)
                    
                    # Add TimestampMixin to model inheritance
                    content = re.sub(
                        r'class (\w+)\(models\.Model\):',
                        r'class \1(TimestampMixin):',
                        content
                    )
                
                if content != original_content:
                    if not self.dry_run:
                        file_path.write_text(content, encoding='utf-8')
                        logger.info(f"  ✓ Updated model mixins in: {model_file}")
                    else:
                        logger.info(f"  → Would update model mixins in: {model_file}")
                    
                    files_updated += 1
                    self.changes_made.append(f"Updated model mixins: {model_file}")
                
            except Exception as e:
                logger.error(f"  ✗ Error processing {model_file}: {e}")
        
        return files_updated
    
    def fix_admin_duplications(self) -> int:
        """
        Fix admin class duplications.
        
        Returns:
            Number of files updated
        """
        logger.info("Fixing admin duplications...")
        
        admin_files = [
            "dashboard/admin.py",
            "analytics/admin.py",
            "wallet/admin.py",
            "trading/admin.py"
        ]
        
        files_updated = 0
        
        for admin_file in admin_files:
            file_path = self.project_root / admin_file
            
            if not file_path.exists():
                continue
                
            try:
                content = file_path.read_text(encoding='utf-8')
                original_content = content
                
                # Add import for shared admin base if not present
                if "from shared.admin.base import BaseModelAdmin" not in content:
                    django_admin_match = re.search(r'(from django\.contrib import admin)', content)
                    if django_admin_match:
                        content = content.replace(
                            django_admin_match.group(1),
                            f"{django_admin_match.group(1)}\nfrom shared.admin.base import BaseModelAdmin"
                        )
                
                # Replace common admin method patterns
                # Look for session_id_short and similar methods
                common_methods = [
                    r'def session_id_short\(self, obj\):.*?session_id_short\.short_description = .*?\n',
                    r'def success_rate_display\(self, obj\):.*?success_rate_display\.short_description = .*?\n',
                    r'def address_short\(self, obj\):.*?address_short\.short_description = .*?\n'
                ]
                
                for method_pattern in common_methods:
                    if re.search(method_pattern, content, re.DOTALL):
                        content = re.sub(method_pattern, '', content, flags=re.DOTALL)
                        
                        # Inherit from BaseModelAdmin instead of admin.ModelAdmin
                        content = re.sub(
                            r'class (\w+Admin)\(admin\.ModelAdmin\):',
                            r'class \1(BaseModelAdmin):',
                            content
                        )
                
                if content != original_content:
                    if not self.dry_run:
                        file_path.write_text(content, encoding='utf-8')
                        logger.info(f"  ✓ Updated admin duplications in: {admin_file}")
                    else:
                        logger.info(f"  → Would update admin duplications in: {admin_file}")
                    
                    files_updated += 1
                    self.changes_made.append(f"Updated admin duplications: {admin_file}")
                
            except Exception as e:
                logger.error(f"  ✗ Error processing {admin_file}: {e}")
        
        return files_updated
    
    def fix_test_duplications(self) -> int:
        """
        Fix test class duplications.
        
        Returns:
            Number of files updated
        """
        logger.info("Fixing test duplications...")
        
        test_files = list(self.project_root.rglob("test_*.py"))
        files_updated = 0
        
        for test_file in test_files:
            if "shared" in str(test_file) or "backups" in str(test_file):
                continue
                
            try:
                content = test_file.read_text(encoding='utf-8')
                original_content = content
                
                # Add import for shared test base if not present
                if "from shared.tests.base import BaseDexTestCase" not in content:
                    django_test_match = re.search(r'(from django\.test import TestCase)', content)
                    if django_test_match:
                        content = content.replace(
                            django_test_match.group(1),
                            f"{django_test_match.group(1)}\nfrom shared.tests.base import BaseDexTestCase"
                        )
                
                # Replace common test patterns
                if "class" in content and "TestCase" in content:
                    # Replace TestCase inheritance with BaseDexTestCase
                    content = re.sub(
                        r'class (\w+)\(TestCase\):',
                        r'class \1(BaseDexTestCase):',
                        content
                    )
                    
                    # Remove duplicate setUp methods that just call super()
                    content = re.sub(
                        r'\s+def setUp\(self\):\s*\n\s*super\(\)\.setUp\(\)\s*\n',
                        '',
                        content
                    )
                
                if content != original_content:
                    if not self.dry_run:
                        test_file.write_text(content, encoding='utf-8')
                        logger.info(f"  ✓ Updated test duplications in: {test_file.name}")
                    else:
                        logger.info(f"  → Would update test duplications in: {test_file.name}")
                    
                    files_updated += 1
                    self.changes_made.append(f"Updated test duplications: {test_file}")
                
            except Exception as e:
                logger.error(f"  ✗ Error processing {test_file}: {e}")
        
        return files_updated
    
    def fix_constant_duplications(self) -> int:
        """
        Fix constant duplications by using shared constants.
        
        Returns:
            Number of files updated
        """
        logger.info("Fixing constant duplications...")
        
        python_files = list(self.project_root.rglob("*.py"))
        files_updated = 0
        
        # Common constants to replace
        constant_replacements = {
            "CRITICAL = 'CRITICAL'": "from shared.constants import RISK_LEVELS",
            "HIGH = 'HIGH'": "from shared.constants import RISK_LEVELS", 
            "MEDIUM = 'MEDIUM'": "from shared.constants import RISK_LEVELS",
            "LOW = 'LOW'": "from shared.constants import RISK_LEVELS"
        }
        
        for py_file in python_files:
            if ("shared" in str(py_file) or "backups" in str(py_file) or 
                ".venv" in str(py_file) or "__pycache__" in str(py_file)):
                continue
                
            try:
                content = py_file.read_text(encoding='utf-8')
                original_content = content
                
                # Replace constant definitions with imports
                for old_constant, new_import in constant_replacements.items():
                    if old_constant in content and new_import not in content:
                        content = content.replace(old_constant, "")
                        
                        # Add import at the top
                        import_match = re.search(r'(import.*?\n\n)', content, re.DOTALL)
                        if import_match:
                            content = content.replace(
                                import_match.group(1),
                                f"{import_match.group(1)}{new_import}\n"
                            )
                
                if content != original_content:
                    if not self.dry_run:
                        py_file.write_text(content, encoding='utf-8')
                        logger.debug(f"  ✓ Updated constants in: {py_file.relative_to(self.project_root)}")
                    
                    files_updated += 1
                
            except Exception as e:
                logger.debug(f"  ✗ Error processing {py_file}: {e}")
        
        if files_updated > 0:
            self.changes_made.append(f"Updated constants in {files_updated} files")
            
        return files_updated
    
    def run_all_fixes(self) -> bool:
        """
        Run all duplication fixes.
        
        Returns:
            True if all fixes completed successfully
        """
        logger.info("Starting comprehensive duplication fixes...")
        
        if not self.dry_run:
            # Create backup
            backup_path = self.create_backup()
            logger.info(f"Project backed up to: {backup_path}")
        
        # Verify prerequisites
        if not self.verify_shared_base_exists():
            return False
        
        success = True
        total_changes = 0
        
        try:
            # Fix management commands
            logger.info("\n=== Fixing Management Commands ===")
            for command_path in self.management_commands:
                if self.fix_management_command(command_path):
                    total_changes += 1
            
            # Fix model mixins
            logger.info("\n=== Fixing Model Mixins ===")
            model_changes = self.fix_model_mixins()
            total_changes += model_changes
            
            # Fix admin duplications
            logger.info("\n=== Fixing Admin Duplications ===")
            admin_changes = self.fix_admin_duplications()
            total_changes += admin_changes
            
            # Fix test duplications
            logger.info("\n=== Fixing Test Duplications ===")
            test_changes = self.fix_test_duplications()
            total_changes += test_changes
            
            # Fix constant duplications
            logger.info("\n=== Fixing Constant Duplications ===")
            constant_changes = self.fix_constant_duplications()
            total_changes += constant_changes
            
            # Summary
            logger.info(f"\n=== SUMMARY ===")
            logger.info(f"Total changes made: {total_changes}")
            
            if self.dry_run:
                logger.info("DRY RUN - No files were actually modified")
            else:
                logger.info("All fixes applied successfully!")
                
            for change in self.changes_made:
                logger.info(f"  ✓ {change}")
            
            logger.info("\nRun the duplication detector again to see improvements:")
            logger.info("  python scripts/duplication_detector.py")
            
        except Exception as e:
            logger.error(f"Error during fix process: {e}")
            success = False
        
        return success


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Fix code duplications in Django project")
    parser.add_argument("--project-root", default=".", help="Project root directory")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be changed without making changes")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    # Initialize fixer
    fixer = DuplicationFixer(
        project_root=args.project_root,
        dry_run=args.dry_run,
        verbose=args.verbose
    )
    
    # Run all fixes
    success = fixer.run_all_fixes()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()