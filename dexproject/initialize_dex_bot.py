"""
Django management command to initialize the DEX trading bot system.
"""

from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    """Initialize the DEX trading bot system."""
    
    help = 'Initialize the DEX trading bot system with all required data'
    
    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recreation of existing data',
        )
    
    def handle(self, *args, **options):
        """Execute the initialization."""
        self.stdout.write(self.style.SUCCESS("🚀 Initializing DEX Trading Bot System..."))
        force = options.get('force', False)
        
        try:
            # Step 1: Run migrations
            self.stdout.write("\n📋 Step 1: Running migrations...")
            call_command('migrate', verbosity=0)
            self.stdout.write(self.style.SUCCESS("✓ Migrations completed"))
            
            # Step 2: Populate chains and DEXes
            self.stdout.write("\n🔗 Step 2: Creating blockchain chains and DEXes...")
            args = ['--force'] if force else []
            call_command('populate_chains_and_dexes', *args, verbosity=1)
            self.stdout.write(self.style.SUCCESS("✓ Chains and DEXes created"))
            
            # Step 3: Create risk checks
            self.stdout.write("\n🛡️ Step 3: Creating risk check types...")
            args = ['--force'] if force else []
            call_command('create_risk_checks', *args, verbosity=1)
            self.stdout.write(self.style.SUCCESS("✓ Risk checks created"))
            
            # Step 4: Create risk profiles
            self.stdout.write("\n📊 Step 4: Creating risk profiles...")
            args = ['--force'] if force else []
            call_command('create_risk_profiles', *args, verbosity=1)
            self.stdout.write(self.style.SUCCESS("✓ Risk profiles created"))
            
            # Step 5: Create default strategies
            self.stdout.write("\n📈 Step 5: Creating default trading strategies...")
            args = ['--force'] if force else []
            call_command('create_default_strategies', *args, verbosity=1)
            self.stdout.write(self.style.SUCCESS("✓ Trading strategies created"))
            
            # Success message
            self.stdout.write(self.style.SUCCESS("\n🎉 DEX Trading Bot initialization completed successfully!"))
            
            self.stdout.write("\n" + "="*60)
            self.stdout.write(self.style.SUCCESS("SYSTEM READY FOR USE"))
            self.stdout.write("="*60)
            
            self.stdout.write("\n📝 Next steps:")
            self.stdout.write("1. Create superuser: python manage.py createsuperuser")
            self.stdout.write("2. Start server: python manage.py runserver")
            self.stdout.write("3. Access admin: http://localhost:8000/admin/")
            self.stdout.write("4. Review the created data in the admin panel")
            
            self.stdout.write("\n📊 What was created:")
            self.stdout.write("• 3 Blockchain networks (Ethereum, Base, Arbitrum)")
            self.stdout.write("• 6 DEX configurations (Uniswap V2/V3, SushiSwap, etc.)")
            self.stdout.write("• 13 Risk check types (Honeypot, LP Lock, Ownership, etc.)")
            self.stdout.write("• 4 Risk profiles (Conservative, Moderate, Aggressive, Experimental)")
            self.stdout.write("• 6 Trading strategies (Conservative Sniper, Balanced Trader, etc.)")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ Initialization failed: {e}"))
            self.stdout.write(f"Error details: {str(e)}")
            raise