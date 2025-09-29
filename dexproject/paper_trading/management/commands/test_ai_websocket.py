"""
Management command to test WebSocket AI decision stream.

This command creates test AI thoughts and sends them via WebSocket
to verify the real-time updates are working.

File: dexproject/paper_trading/management/commands/test_ai_websocket.py
"""

import time
import random
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from paper_trading.models import (
    PaperTradingAccount,
    PaperAIThoughtLog
)
from paper_trading.services.websocket_service import websocket_service


class Command(BaseCommand):
    """Test command for WebSocket AI decision stream."""
    
    help = 'Test WebSocket AI decision stream by creating test thoughts'
    
    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            '--count',
            type=int,
            default=5,
            help='Number of test thoughts to create'
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=2,
            help='Seconds between each thought'
        )
        parser.add_argument(
            '--account-id',
            type=str,
            help='Specific account ID to use'
        )
    
    def handle(self, *args, **options):
        """Execute the test command."""
        count = options['count']
        interval = options['interval']
        account_id = options.get('account_id')
        
        self.stdout.write(self.style.SUCCESS(
            f"🚀 Testing WebSocket AI Decision Stream"
        ))
        self.stdout.write(f"   Creating {count} test thoughts with {interval}s interval")
        
        # Get or create test account
        if account_id:
            try:
                account = PaperTradingAccount.objects.get(account_id=account_id)
            except PaperTradingAccount.DoesNotExist:
                self.stdout.write(self.style.ERROR(
                    f"Account {account_id} not found"
                ))
                return
        else:
            # Use first available account or create one
            account = PaperTradingAccount.objects.first()
            if not account:
                self.stdout.write(self.style.ERROR(
                    "No paper trading accounts found. Create one first."
                ))
                return
        
        self.stdout.write(f"   Using account: {account.name} (ID: {account.account_id})")
        
        # Get user_id for WebSocket routing
        user_id = account.user_id if hasattr(account, 'user_id') else account.user.id
        
        # Test tokens for variety
        test_tokens = ['WETH', 'SHIB', 'PEPE', 'DOGE', 'AERO']
        decision_types = ['BUY', 'SELL', 'HOLD', 'ANALYSIS']
        lanes = ['FAST', 'SMART']
        
        self.stdout.write("\n📡 Sending test thoughts via WebSocket...\n")
        
        for i in range(1, count + 1):
            # Generate random test data
            token = random.choice(test_tokens)
            decision_type = random.choice(decision_types)
            lane = random.choice(lanes)
            confidence = Decimal(str(random.randint(30, 95)))
            risk_score = Decimal(str(random.randint(10, 80)))
            
            # Create thought log
            thought_log = PaperAIThoughtLog.objects.create(
                account=account,
                token_symbol=token,
                token_address=f"0x{''.join(random.choices('0123456789abcdef', k=40))}",
                decision_type=decision_type,
                confidence_percent=confidence,
                confidence_level=self._get_confidence_level(confidence),
                risk_score=risk_score,
                opportunity_score=Decimal(str(random.randint(-50, 50))),
                primary_reasoning=f"Test thought #{i}: Analyzing {token} market conditions. "
                                 f"{'Strong bullish signals detected.' if decision_type == 'BUY' else ''}"
                                 f"{'Bearish trend identified.' if decision_type == 'SELL' else ''}"
                                 f"{'Market consolidating, waiting for clearer signals.' if decision_type == 'HOLD' else ''}"
                                 f"{'Performing deep market analysis.' if decision_type == 'ANALYSIS' else ''}",
                key_factors=[
                    f"Test Factor 1: {random.choice(['Momentum', 'Volume', 'Trend'])}",
                    f"Test Factor 2: {random.choice(['Support', 'Resistance', 'MA Cross'])}",
                    f"Test Factor 3: Lane={lane}"
                ],
                positive_signals=[
                    f"Signal {j}: {random.choice(['Bullish divergence', 'Volume spike', 'Breaking resistance'])}"
                    for j in range(random.randint(1, 3))
                ],
                negative_signals=[
                    f"Risk {j}: {random.choice(['High volatility', 'Low volume', 'Overbought'])}"
                    for j in range(random.randint(0, 2))
                ],
                market_data={
                    'current_price': float(random.uniform(0.001, 3000)),
                    'price_change_percent': float(random.uniform(-20, 20)),
                    'volatility': float(random.uniform(0, 10)),
                    'momentum': float(random.uniform(-10, 10)),
                    'trend': random.choice(['bullish', 'bearish', 'neutral'])
                },
                strategy_name='Test Strategy',
                lane_used=lane,
                analysis_time_ms=random.randint(50, 500)
            )
            
            # Send WebSocket notification
            thought_data = {
                'thought_id': str(thought_log.thought_id),
                'token_symbol': thought_log.token_symbol,
                'decision_type': thought_log.decision_type,
                'confidence': float(thought_log.confidence_percent),
                'risk_score': float(thought_log.risk_score),
                'lane_used': thought_log.lane_used,
                'reasoning': thought_log.primary_reasoning[:200],
                'positive_signals': thought_log.positive_signals,
                'negative_signals': thought_log.negative_signals,
                'created_at': thought_log.created_at.isoformat()
            }
            
            # Send via WebSocket service
            websocket_service.send_thought_log_created(user_id, thought_data)
            
            # Also send as AI decision for variety
            if i % 2 == 0:
                websocket_service.send_ai_decision(user_id, {
                    'token_symbol': token,
                    'signal': decision_type.lower(),
                    'action': decision_type,
                    'confidence': float(confidence),
                    'lane_type': lane,
                    'position_size': float(random.uniform(5, 25)),
                    'reasoning': f"Test AI decision for {token}",
                    'current_price': float(random.uniform(0.001, 3000)),
                    'risk_score': float(risk_score)
                })
            
            # Display status
            status_emoji = {
                'BUY': '🟢',
                'SELL': '🔴',
                'HOLD': '🟡',
                'ANALYSIS': '🔵'
            }.get(decision_type, '⚪')
            
            self.stdout.write(
                f"{status_emoji} Thought #{i}: {decision_type} {token} "
                f"[{confidence:.0f}% confidence, {lane} lane]"
            )
            
            # Wait between thoughts
            if i < count:
                time.sleep(interval)
        
        self.stdout.write("\n" + "="*60)
        self.stdout.write(self.style.SUCCESS("✅ WebSocket test complete!"))
        self.stdout.write("\nCheck your dashboard to see if thoughts appeared in real-time.")
        self.stdout.write("If thoughts didn't appear:")
        self.stdout.write("  1. Ensure the dashboard is open in a browser")
        self.stdout.write("  2. Check browser console for WebSocket connection status")
        self.stdout.write("  3. Verify Redis/Channels is running: redis-cli ping")
        self.stdout.write("  4. Check Django logs for WebSocket errors")
        self.stdout.write("="*60)
    
    def _get_confidence_level(self, confidence: Decimal) -> str:
        """Get confidence level category."""
        if confidence >= 80:
            return 'VERY_HIGH'
        elif confidence >= 60:
            return 'HIGH'
        elif confidence >= 40:
            return 'MEDIUM'
        elif confidence >= 20:
            return 'LOW'
        else:
            return 'VERY_LOW'