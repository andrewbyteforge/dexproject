"""
Diagnostic and Fix Script for PaperAIThoughtLog Cache Issue

This script will:
1. Clear all Python cache files
2. Verify the model definition
3. Test model creation with the failing fields
4. Provide a detailed diagnostic report

Run this from the dexproject directory:
    python fix_thought_log_cache.py

Author: Claude
Date: 2025-10-24
"""

import os
import sys
import shutil
import importlib
from pathlib import Path
from decimal import Decimal

# Color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_header(text: str):
    """Print a formatted header."""
    print(f"\n{Colors.BLUE}{Colors.BOLD}{'=' * 80}{Colors.END}")
    print(f"{Colors.BLUE}{Colors.BOLD}{text}{Colors.END}")
    print(f"{Colors.BLUE}{Colors.BOLD}{'=' * 80}{Colors.END}\n")

def print_success(text: str):
    """Print success message."""
    print(f"{Colors.GREEN}✅ {text}{Colors.END}")

def print_error(text: str):
    """Print error message."""
    print(f"{Colors.RED}❌ {text}{Colors.END}")

def print_warning(text: str):
    """Print warning message."""
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.END}")

def print_info(text: str):
    """Print info message."""
    print(f"ℹ️  {text}")

def clear_python_cache():
    """
    Clear all Python cache files and __pycache__ directories.
    
    Returns:
        tuple: (files_deleted, dirs_deleted)
    """
    print_header("STEP 1: CLEARING PYTHON CACHE")
    
    files_deleted = 0
    dirs_deleted = 0
    
    project_root = Path.cwd()
    
    print_info(f"Scanning project root: {project_root}")
    
    # Find and delete .pyc files
    for pyc_file in project_root.rglob("*.pyc"):
        try:
            pyc_file.unlink()
            files_deleted += 1
        except Exception as e:
            print_error(f"Failed to delete {pyc_file}: {e}")
    
    # Find and delete __pycache__ directories
    for pycache_dir in project_root.rglob("__pycache__"):
        try:
            shutil.rmtree(pycache_dir)
            dirs_deleted += 1
        except Exception as e:
            print_error(f"Failed to delete {pycache_dir}: {e}")
    
    print_success(f"Deleted {files_deleted} .pyc files")
    print_success(f"Deleted {dirs_deleted} __pycache__ directories")
    
    return files_deleted, dirs_deleted

def setup_django():
    """Setup Django environment."""
    print_header("STEP 2: SETTING UP DJANGO ENVIRONMENT")
    
    try:
        # Add project to path
        project_path = Path.cwd()
        if str(project_path) not in sys.path:
            sys.path.insert(0, str(project_path))
        
        # Setup Django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
        
        import django
        django.setup()
        
        print_success("Django environment setup complete")
        return True
    except Exception as e:
        print_error(f"Failed to setup Django: {e}")
        import traceback
        traceback.print_exc()
        return False

def verify_model_fields():
    """
    Verify that PaperAIThoughtLog has the required fields.
    
    Returns:
        tuple: (success, missing_fields, all_fields)
    """
    print_header("STEP 3: VERIFYING MODEL DEFINITION")
    
    try:
        # Force reload of the models module
        if 'paper_trading.models' in sys.modules:
            importlib.reload(sys.modules['paper_trading.models'])
        
        from paper_trading.models import PaperAIThoughtLog
        
        # Get all field names
        field_names = [f.name for f in PaperAIThoughtLog._meta.get_fields()]
        
        print_info(f"Total fields found: {len(field_names)}")
        
        # Check for the problematic fields
        required_fields = [
            'confidence_percent',
            'risk_score',
            'opportunity_score',
            'primary_reasoning'
        ]
        
        missing_fields = []
        for field in required_fields:
            if field in field_names:
                print_success(f"Field '{field}' exists in model")
            else:
                print_error(f"Field '{field}' MISSING from model")
                missing_fields.append(field)
        
        print_info("\nAll model fields:")
        for field in sorted(field_names):
            print(f"  • {field}")
        
        return len(missing_fields) == 0, missing_fields, field_names
        
    except Exception as e:
        print_error(f"Failed to verify model: {e}")
        import traceback
        traceback.print_exc()
        return False, [], []

def test_model_creation():
    """
    Test creating a PaperAIThoughtLog instance with the problematic fields.
    
    Returns:
        bool: True if creation succeeds
    """
    print_header("STEP 4: TESTING MODEL CREATION")
    
    try:
        # Force reload
        if 'paper_trading.models' in sys.modules:
            importlib.reload(sys.modules['paper_trading.models'])
        
        from paper_trading.models import (
            PaperAIThoughtLog,
            PaperTradingAccount
        )
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        
        # Get or create test user
        user, _ = User.objects.get_or_create(
            username='demo_user',
            defaults={'email': 'demo@example.com'}
        )
        
        # Get or create test account
        account, _ = PaperTradingAccount.objects.get_or_create(
            user=user,
            is_active=True,
            defaults={
                'name': 'Test_Account',
                'initial_balance_usd': Decimal('10000.00'),
                'current_balance_usd': Decimal('10000.00')
            }
        )
        
        print_info(f"Using test account: {account.account_id}")
        
        # Test data - exactly as used in market_analyzer.py
        test_data = {
            'account': account,
            'paper_trade': None,
            'decision_type': 'SKIP',
            'token_address': '0x' + '0' * 40,
            'token_symbol': 'TEST',
            'confidence_level': 'MEDIUM',
            'confidence_percent': Decimal('50.00'),  # ⚠️ PROBLEMATIC FIELD #1
            'risk_score': Decimal('50.00'),  # ⚠️ PROBLEMATIC FIELD #2
            'opportunity_score': Decimal('50.00'),  # ⚠️ PROBLEMATIC FIELD #3
            'primary_reasoning': 'Test reasoning',  # ⚠️ PROBLEMATIC FIELD #4
            'key_factors': ['Test factor 1', 'Test factor 2'],
            'positive_signals': [],
            'negative_signals': [],
            'market_data': {'test': 'data'},
            'strategy_name': 'Test_Strategy',
            'lane_used': 'SMART',
            'analysis_time_ms': 100
        }
        
        print_info("Creating test PaperAIThoughtLog with problematic fields...")
        
        # Attempt to create the object
        thought_log = PaperAIThoughtLog.objects.create(**test_data)
        
        print_success(f"Successfully created thought log: {thought_log.thought_id}")
        print_success(f"  confidence_percent: {thought_log.confidence_percent}")
        print_success(f"  risk_score: {thought_log.risk_score}")
        print_success(f"  opportunity_score: {thought_log.opportunity_score}")
        print_success(f"  primary_reasoning: {thought_log.primary_reasoning[:50]}...")
        
        # Clean up test object
        thought_log.delete()
        print_info("Test object deleted successfully")
        
        return True
        
    except Exception as e:
        print_error(f"Failed to create model instance: {e}")
        print_error(f"Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return False

def check_database_schema():
    """Check if database schema matches the model."""
    print_header("STEP 5: CHECKING DATABASE SCHEMA")
    
    try:
        from django.db import connection
        
        with connection.cursor() as cursor:
            # Check if table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='paper_ai_thought_logs'
            """)
            
            result = cursor.fetchone()
            
            if result:
                print_success("Table 'paper_ai_thought_logs' exists")
                
                # Get table info
                cursor.execute("PRAGMA table_info(paper_ai_thought_logs)")
                columns = cursor.fetchall()
                
                print_info(f"\nDatabase columns ({len(columns)} total):")
                
                column_names = []
                for col in columns:
                    col_name = col[1]
                    col_type = col[2]
                    column_names.append(col_name)
                    print(f"  • {col_name} ({col_type})")
                
                # Check for problematic fields
                required_fields = [
                    'confidence_percent',
                    'risk_score',
                    'opportunity_score',
                    'primary_reasoning'
                ]
                
                print_info("\nChecking problematic fields in database:")
                all_present = True
                for field in required_fields:
                    if field in column_names:
                        print_success(f"Field '{field}' exists in database")
                    else:
                        print_error(f"Field '{field}' MISSING from database")
                        all_present = False
                
                return all_present
            else:
                print_error("Table 'paper_ai_thought_logs' does NOT exist")
                return False
                
    except Exception as e:
        print_error(f"Failed to check database schema: {e}")
        import traceback
        traceback.print_exc()
        return False

def generate_report(cache_cleared, model_verified, creation_succeeded, schema_ok):
    """Generate final diagnostic report."""
    print_header("DIAGNOSTIC REPORT")
    
    print(f"\n{Colors.BOLD}Results Summary:{Colors.END}")
    print(f"  1. Python Cache Cleared: {Colors.GREEN + '✅ YES' + Colors.END if cache_cleared else Colors.RED + '❌ NO' + Colors.END}")
    print(f"  2. Model Fields Verified: {Colors.GREEN + '✅ YES' + Colors.END if model_verified else Colors.RED + '❌ NO' + Colors.END}")
    print(f"  3. Model Creation Test: {Colors.GREEN + '✅ PASSED' + Colors.END if creation_succeeded else Colors.RED + '❌ FAILED' + Colors.END}")
    print(f"  4. Database Schema OK: {Colors.GREEN + '✅ YES' + Colors.END if schema_ok else Colors.RED + '❌ NO' + Colors.END}")
    
    print(f"\n{Colors.BOLD}Recommendation:{Colors.END}")
    
    if all([cache_cleared, model_verified, creation_succeeded, schema_ok]):
        print_success("ALL CHECKS PASSED! ✨")
        print_info("\nNext steps:")
        print("  1. Restart your paper trading bot")
        print("  2. The error should be resolved")
        print("  3. Monitor the logs to confirm")
    else:
        print_warning("SOME CHECKS FAILED!")
        print_info("\nTroubleshooting:")
        
        if not model_verified:
            print("  • Model definition issue detected")
            print("    → Check paper_trading/models.py")
            print("    → Ensure all fields are properly defined")
        
        if not schema_ok:
            print("  • Database schema mismatch detected")
            print("    → Run: python manage.py migrate paper_trading")
            print("    → If that fails, may need to recreate migrations")
        
        if not creation_succeeded:
            print("  • Model instantiation is failing")
            print("    → This is the root cause of your bot error")
            print("    → Check the error traceback above for details")
    
    print("\n" + "=" * 80 + "\n")

def main():
    """Main execution function."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}")
    print("╔═══════════════════════════════════════════════════════════════════════════╗")
    print("║         PaperAIThoughtLog Diagnostic & Fix Script                         ║")
    print("║         Resolving: 'got unexpected keyword arguments' error              ║")
    print("╚═══════════════════════════════════════════════════════════════════════════╝")
    print(f"{Colors.END}")
    
    # Step 1: Clear cache
    files_deleted, dirs_deleted = clear_python_cache()
    cache_cleared = files_deleted > 0 or dirs_deleted > 0
    
    # Step 2: Setup Django
    if not setup_django():
        print_error("Cannot proceed without Django setup")
        return 1
    
    # Step 3: Verify model fields
    model_verified, missing_fields, all_fields = verify_model_fields()
    
    # Step 4: Test model creation
    creation_succeeded = test_model_creation()
    
    # Step 5: Check database schema
    schema_ok = check_database_schema()
    
    # Generate report
    generate_report(cache_cleared, model_verified, creation_succeeded, schema_ok)
    
    # Return exit code
    if all([cache_cleared or (files_deleted == 0 and dirs_deleted == 0), 
            model_verified, creation_succeeded, schema_ok]):
        return 0
    else:
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)