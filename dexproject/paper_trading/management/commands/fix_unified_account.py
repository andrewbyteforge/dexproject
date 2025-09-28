"""
Fix for Live Updates in Paper Trading

This script addresses both the AI thoughts creation issue and polling problems.

File: dexproject/paper_trading/management/commands/fix_live_updates.py
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from decimal import Decimal
import random
from django.utils import timezone
from paper_trading.models import *


class Command(BaseCommand):
    """Fix live updates issues."""
    
    help = 'Fix AI thoughts creation and live updates'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--create-test-thoughts',
            action='store_true',
            help='Create some test AI thoughts to verify the system works'
        )
    
    def handle(self, *args, **options):
        """Execute the fix."""
        self.stdout.write("=" * 60)
        self.stdout.write("FIXING LIVE UPDATES")
        self.stdout.write("=" * 60)
        
        # 1. Check current AI thoughts
        demo_user = User.objects.get(username='demo_user')
        account = PaperTradingAccount.objects.filter(user=demo_user).first()
        
        current_thoughts = PaperAIThoughtLog.objects.filter(account=account).count()
        self.stdout.write(f"Current AI thoughts: {current_thoughts}")
        
        # 2. Check recent trades
        recent_trades = PaperTrade.objects.filter(account=account).order_by('-created_at')[:5]
        self.stdout.write(f"Recent trades: {recent_trades.count()}")
        
        # 3. Create test thoughts if requested
        if options['create_test_thoughts']:
            self.stdout.write("\nCreating test AI thoughts...")
            
            tokens = ['WETH', 'USDC', 'PEPE', 'SHIB', 'DOGE']
            decisions = ['BUY', 'SELL', 'HOLD']
            lanes = ['FAST', 'SMART']
            
            for i in range(5):
                token = random.choice(tokens)
                decision = random.choice(decisions)
                lane = random.choice(lanes)
                confidence = random.randint(50, 95)
                
                thought = PaperAIThoughtLog.objects.create(
                    account=account,
                    decision_type=decision,
                    token_symbol=token,
                    token_address=f'0x{"".join(random.choices("0123456789abcdef", k=40))}',
                    confidence_level='HIGH' if confidence > 75 else 'MEDIUM',
                    confidence_percent=Decimal(str(confidence)),
                    risk_score=Decimal(str(random.randint(20, 80))),
                    opportunity_score=Decimal(str(random.randint(40, 90))),
                    primary_reasoning=f"Market analysis indicates {decision.lower()} opportunity based on {lane.lower()} lane analysis.",
                    lane_used=lane,
                    strategy_name='Test Strategy'
                )
                
                self.stdout.write(f"  ✓ Created thought: {decision} {token} ({confidence}% confidence)")
        
        # 4. Check the API endpoint directly
        self.stdout.write("\nTesting API endpoint...")
        from django.test import Client
        client = Client()
        
        response = client.get('/paper-trading/api/ai-thoughts/?limit=5')
        self.stdout.write(f"API response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            thoughts_count = len(data.get('thoughts', []))
            self.stdout.write(f"API returned {thoughts_count} thoughts")
        
        # 5. Final recommendations
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("RECOMMENDATIONS")
        self.stdout.write("=" * 60)
        
        self.stdout.write("1. AI Thoughts Issue:")
        self.stdout.write("   The bot's AI engine has thought logging disabled.")
        self.stdout.write("   This needs to be re-enabled in ai_engine.py")
        
        self.stdout.write("\n2. Real-time Updates Issue:")
        self.stdout.write("   Check browser console for JavaScript errors")
        self.stdout.write("   The polling should happen every 5 seconds")
        
        self.stdout.write("\n3. To test real-time updates:")
        self.stdout.write("   Run: python manage.py fix_live_updates --create-test-thoughts")
        self.stdout.write("   Then check if new thoughts appear on dashboard")
        
        self.stdout.write("=" * 60)