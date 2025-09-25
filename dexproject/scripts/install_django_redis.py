"""
Script to install and configure django-redis package

This script will help install the django-redis package which is needed
for proper Redis cache integration with Django.

File: scripts/install_django_redis.py
"""

import subprocess
import sys
import os


def check_django_redis():
    """Check if django-redis is installed."""
    try:
        import django_redis
        print("✓ django-redis is already installed")
        print(f"  Version: {django_redis.__version__}")
        return True
    except ImportError:
        print("✗ django-redis is not installed")
        return False


def install_django_redis():
    """Install django-redis package."""
    print("\nInstalling django-redis...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "django-redis"])
        print("✓ django-redis installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to install django-redis: {e}")
        return False


def update_requirements():
    """Add django-redis to requirements.txt if not present."""
    req_file = "requirements.txt"
    
    if not os.path.exists(req_file):
        print(f"✗ {req_file} not found")
        return False
    
    with open(req_file, 'r') as f:
        content = f.read()
    
    if 'django-redis' not in content:
        print(f"\nAdding django-redis to {req_file}...")
        with open(req_file, 'a') as f:
            f.write('\n# Redis cache backend for Django\n')
            f.write('django-redis>=5.3.0\n')
        print(f"✓ Added django-redis to {req_file}")
    else:
        print(f"✓ django-redis already in {req_file}")
    
    return True


def main():
    """Main installation process."""
    print("=" * 60)
    print("Django Redis Installation Script")
    print("=" * 60)
    
    # Check if already installed
    if check_django_redis():
        print("\nNo installation needed!")
        return
    
    # Install the package
    print("\ndjango-redis is required for proper Redis cache integration.")
    response = input("Do you want to install it now? (y/n): ")
    
    if response.lower() == 'y':
        if install_django_redis():
            # Update requirements.txt
            update_requirements()
            
            print("\n" + "=" * 60)
            print("Installation Complete!")
            print("=" * 60)
            print("\nNext steps:")
            print("1. Make sure Redis server is running")
            print("2. Update your settings.py with the fixed cache configuration")
            print("3. Restart your Django server")
        else:
            print("\n✗ Installation failed. Please install manually:")
            print("  pip install django-redis")
    else:
        print("\nPlease install django-redis manually:")
        print("  pip install django-redis")


if __name__ == "__main__":
    main()