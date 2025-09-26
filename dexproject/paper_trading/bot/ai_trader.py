"""
Update for paper_trading/bot/ai_trader.py to integrate WebSocket notifications.

Add these imports and modify the execute_trade method in your existing ai_trader.py file.

File: dexproject/paper_trading/bot/ai_trader.py (modifications)
"""

# Add to imports section:
from paper_trading.services.websocket_service import websocket_service

# Update the execute_trade method to send WebSocket notifications:
async def execute_trade(self, trade_signal: Dict[str, Any]) -> None:
    """
    Execute a paper trade based on the signal.
    
    Now includes WebSocket notifications for real-time dashboard updates.
    
    Args:
        trade_signal: Trading signal with decision details
    """
    try:
        # ... existing trade execution code ...
        
        # After creating the trade object:
        if trade:
            # Send WebSocket notification
            trade_data = {
                'id': trade.trade_id,
                'trade_type': trade.trade_type,
                'token_in': trade.token_in_symbol,
                'token_out': trade.token_out_symbol,
                'amount_in': float(trade.amount_in),
                'amount_out': float(trade.amount_out),
                'amount_usd': float(trade.amount_in_usd),
                'status': trade.status,
                'created_at': trade.created_at.isoformat(),
                'strategy': trade.strategy_name
            }
            
            # Send trade update via WebSocket
            websocket_service.send_trade_update(
                user_id=self.account.user_id,
                trade_data=trade_data
            )
            
            # Update portfolio via WebSocket
            positions = PaperPosition.objects.filter(
                account=self.account,
                is_open=True
            )
            
            portfolio_data = {
                'positions': [
                    {
                        'token_symbol': pos.token_symbol,
                        'quantity': float(pos.quantity),
                        'current_value': float(pos.current_value_usd),
                        'unrealized_pnl': float(pos.unrealized_pnl_usd),
                        'pnl_percent': float(pos.unrealized_pnl_percent)
                    }
                    for pos in positions
                ],
                'total_value': float(sum(pos.current_value_usd for pos in positions)),
                'position_count': len(positions)
            }
            
            websocket_service.send_portfolio_update(
                user_id=self.account.user_id,
                portfolio_data=portfolio_data
            )
            
            self.logger.info(f"Trade executed and WebSocket notification sent: {trade.trade_id}")
        
    except Exception as e:
        self.logger.error(f"Error in execute_trade with WebSocket: {e}", exc_info=True)

# Update the log_thought method to send WebSocket notifications:
def log_thought(self, action: str, reasoning: str, confidence: float,
                decision_type: str = 'ANALYSIS') -> None:
    """
    Log AI thought process with WebSocket notification.
    
    Args:
        action: Action taken or considered
        reasoning: Reasoning behind the decision
        confidence: Confidence score (0-100)
        decision_type: Type of decision
    """
    try:
        thought = PaperAIThoughtLog.objects.create(
            account=self.account,
            action=action,
            reasoning=reasoning,
            confidence_score=confidence,
            decision_type=decision_type,
            metadata={}
        )
        
        # Send thought log via WebSocket
        thought_data = {
            'action': action,
            'reasoning': reasoning,
            'confidence_score': confidence,
            'decision_type': decision_type
        }
        
        websocket_service.send_thought_log(
            user_id=self.account.user_id,
            thought_data=thought_data
        )
        
        self.logger.debug(f"Logged thought with WebSocket notification: {action}")
        
    except Exception as e:
        self.logger.error(f"Error logging thought with WebSocket: {e}", exc_info=True)