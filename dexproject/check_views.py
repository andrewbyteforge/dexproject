"""
Diagnostic script to check which view functions are available in dashboard.views

Run this from your Django project root directory:
python check_views.py

File: check_views.py (save in D:\dex-django\dexproject\)
"""

import os
import sys
import django

# Add the project directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Setup Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
django.setup()

# Now import and check the views
try:
    from dashboard import views
    
    print("=" * 80)
    print("DASHBOARD VIEWS MODULE INSPECTION")
    print("=" * 80)
    
    # Get all functions/attributes from the views module
    all_attributes = dir(views)
    
    # Filter to get only view functions (callable, not private)
    view_functions = [
        attr for attr in all_attributes 
        if callable(getattr(views, attr)) and not attr.startswith('_')
    ]
    
    print(f"\nFound {len(view_functions)} view functions in dashboard.views:\n")
    
    # Check for specific functions we're interested in
    functions_to_check = [
        'dashboard_home',
        'mode_selection',
        'configuration_panel',
        'configuration_summary',
        'configuration_list',
        'delete_configuration',
        'smart_lane_demo',
        'smart_lane_stream',
        'dashboard_live_feed',
        'metrics_stream',
        'api_engine_status',
        'api_performance_metrics',
        'api_set_trading_mode',
        'api_smart_lane_analyze',
        'health_check',
        'engine_test'
    ]
    
    print("Checking for expected view functions:")
    print("-" * 40)
    
    for func_name in functions_to_check:
        if hasattr(views, func_name):
            func = getattr(views, func_name)
            if callable(func):
                # Try to get the function's docstring first line
                doc = func.__doc__
                if doc:
                    first_line = doc.strip().split('\n')[0][:60]
                else:
                    first_line = "No docstring"
                print(f"✓ {func_name:30} - {first_line}")
            else:
                print(f"✗ {func_name:30} - EXISTS but NOT CALLABLE")
        else:
            print(f"✗ {func_name:30} - NOT FOUND")
    
    print("\n" + "-" * 40)
    print("\nAll available view functions:")
    print("-" * 40)
    
    for func_name in sorted(view_functions):
        print(f"  - {func_name}")
    
    print("\n" + "=" * 80)
    print("RECOMMENDATION:")
    print("=" * 80)
    
    if not hasattr(views, 'smart_lane_demo'):
        if hasattr(views, 'smart_lane_stream'):
            print("\n⚠️  'smart_lane_demo' not found, but 'smart_lane_stream' exists.")
            print("   Update urls.py to use 'smart_lane_stream' instead.")
        else:
            print("\n⚠️  Neither 'smart_lane_demo' nor 'smart_lane_stream' found.")
            print("   You may need to add the missing view function to views.py")
            print("   or comment out the URL pattern temporarily.")
    else:
        print("\n✓ 'smart_lane_demo' function exists and should work.")
        print("  If you're still getting errors, try:")
        print("  1. Restart the Django development server")
        print("  2. Check for import errors in views.py")
        print("  3. Ensure views.py is saved and not corrupted")
    
except ImportError as e:
    print(f"Error importing dashboard.views: {e}")
    print("\nMake sure you're running this script from the project root directory")
    print("and that the dashboard app is properly configured.")
    
except Exception as e:
    print(f"Unexpected error: {e}")
    import traceback
    traceback.print_exc()