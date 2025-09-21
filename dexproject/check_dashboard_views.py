"""
Dashboard Views Diagnostic Script

Run this from your Django project root directory to check which view functions 
are available and properly exported from the dashboard.views module.

Usage:
    python check_dashboard_views.py

File: check_dashboard_views.py (save in D:\dex-django\dexproject\)
"""

import os
import sys
import django

# Add the project directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Setup Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')

try:
    django.setup()
    print("✅ Django setup successful")
except Exception as e:
    print(f"❌ Django setup failed: {e}")
    sys.exit(1)

def check_views_module():
    """Check the dashboard.views module for available functions."""
    try:
        from dashboard import views
        print("\n" + "=" * 80)
        print("DASHBOARD VIEWS MODULE INSPECTION")
        print("=" * 80)
        
        # Get all functions/attributes from the views module
        all_attributes = dir(views)
        
        # Filter to get only view functions (callable, not private)
        view_functions = [
            attr for attr in all_attributes 
            if callable(getattr(views, attr)) and not attr.startswith('_')
        ]
        
        print(f"\n📊 Found {len(view_functions)} callable functions in dashboard.views")
        
        # Functions that URLs file is trying to use
        required_functions = [
            'dashboard_home',
            'mode_selection', 
            'configuration_panel',
            'dashboard_settings',
            'dashboard_analytics',
            'metrics_stream',
            'api_set_trading_mode',
            'smart_lane_dashboard',
            'smart_lane_demo',
            'smart_lane_analyze',
            'api_smart_lane_analyze',
            'api_get_thought_log',
            'save_configuration',
            'load_configuration',
            'delete_configuration',
            'get_configurations',
            'start_session',
            'stop_session',
            'get_session_status',
            'get_performance_metrics'
        ]
        
        print("\n🔍 Checking required functions:")
        print("-" * 60)
        
        available_count = 0
        missing_functions = []
        
        for func_name in required_functions:
            if hasattr(views, func_name):
                func = getattr(views, func_name)
                if callable(func):
                    available_count += 1
                    # Get function source information
                    try:
                        module = func.__module__
                        if hasattr(func, '__doc__') and func.__doc__:
                            doc = func.__doc__.strip().split('\n')[0][:50]
                        else:
                            doc = "No docstring"
                        print(f"✅ {func_name:25} - {doc}")
                    except:
                        print(f"✅ {func_name:25} - Available")
                else:
                    print(f"⚠️  {func_name:25} - EXISTS but NOT CALLABLE")
                    missing_functions.append(func_name)
            else:
                print(f"❌ {func_name:25} - NOT FOUND")
                missing_functions.append(func_name)
        
        print(f"\n📈 Summary: {available_count}/{len(required_functions)} required functions available")
        
        if missing_functions:
            print(f"\n❌ Missing functions ({len(missing_functions)}):")
            for func in missing_functions:
                print(f"   - {func}")
        
        print("\n🔧 All available functions:")
        print("-" * 60)
        for func_name in sorted(view_functions):
            print(f"   - {func_name}")
            
        return missing_functions
        
    except ImportError as e:
        print(f"❌ Failed to import dashboard.views: {e}")
        return None
    except Exception as e:
        print(f"❌ Error checking views module: {e}")
        return None

def check_fast_lane_module():
    """Check the dashboard.views.fast_lane module."""
    try:
        from dashboard.views import fast_lane
        print("\n" + "=" * 80)
        print("FAST LANE MODULE INSPECTION")
        print("=" * 80)
        
        fast_lane_functions = [
            attr for attr in dir(fast_lane)
            if callable(getattr(fast_lane, attr)) and not attr.startswith('_')
        ]
        
        print(f"\n📊 Found {len(fast_lane_functions)} functions in dashboard.views.fast_lane")
        
        required_fast_lane = ['fast_lane_config', 'get_fast_lane_status']
        
        print("\n🔍 Checking Fast Lane functions:")
        print("-" * 60)
        
        for func_name in required_fast_lane:
            if hasattr(fast_lane, func_name):
                print(f"✅ {func_name}")
            else:
                print(f"❌ {func_name} - NOT FOUND")
                
        print("\n🔧 All Fast Lane functions:")
        for func_name in sorted(fast_lane_functions):
            print(f"   - {func_name}")
            
    except ImportError as e:
        print(f"❌ Failed to import dashboard.views.fast_lane: {e}")
    except Exception as e:
        print(f"❌ Error checking fast_lane module: {e}")

def generate_recommendations(missing_functions):
    """Generate recommendations based on missing functions."""
    print("\n" + "=" * 80)
    print("RECOMMENDATIONS")
    print("=" * 80)
    
    if not missing_functions:
        print("✅ All required functions are available!")
        print("   You can use the full URL configuration.")
    else:
        print("⚠️  Some functions are missing. Here's what to do:")
        print("\n1. Use the minimal URLs configuration I provided")
        print("2. Gradually uncomment URL patterns as you implement the functions")
        print("\n3. Functions to implement:")
        for func in missing_functions:
            print(f"   - {func}")
            
        print("\n4. Or comment out the problematic URL patterns in urls.py")

def main():
    """Main diagnostic function."""
    print("🚀 Starting Dashboard Views Diagnostic...")
    
    # Check main views module
    missing_functions = check_views_module()
    
    # Check fast_lane module
    check_fast_lane_module()
    
    # Generate recommendations
    if missing_functions is not None:
        generate_recommendations(missing_functions)
    
    print("\n" + "=" * 80)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    main()