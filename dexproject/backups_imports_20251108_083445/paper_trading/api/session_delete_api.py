"""
Paper Trading API - Session Delete Endpoint

Endpoint for deleting individual trading sessions.

File: dexproject/paper_trading/api/session_delete_api.py
"""

import logging
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from ..models import PaperTradingSession
from ..utils import get_single_trading_account

logger = logging.getLogger(__name__)


@require_http_methods(["POST"])
def api_delete_session(request, session_id: str) -> JsonResponse:
    """
    Delete a specific trading session.
    
    This endpoint permanently deletes a session and all its related data
    including trades, positions, and performance metrics.
    
    Args:
        request: Django HTTP request
        session_id: UUID of the session to delete
        
    Returns:
        JsonResponse with success status
        
    Example:
        POST /paper-trading/api/sessions/<session_id>/delete/
        
        Response:
        {
            "success": true,
            "message": "Session deleted successfully",
            "session_id": "uuid-here"
        }
    """
    try:
        # Get the single account
        account = get_single_trading_account()
        
        logger.info(f"Delete session request for session {session_id}")
        
        # Get the session
        try:
            session = PaperTradingSession.objects.get(
                session_id=session_id,
                account=account
            )
        except PaperTradingSession.DoesNotExist:
            logger.warning(f"Session {session_id} not found for account {account.account_id}")
            return JsonResponse({
                'success': False,
                'error': 'Session not found'
            }, status=404)
        
        # Don't allow deleting active sessions
        if session.status in ['STARTING', 'RUNNING', 'PAUSED']:
            logger.warning(f"Attempt to delete active session {session_id}")
            return JsonResponse({
                'success': False,
                'error': 'Cannot delete active session. Please stop the session first.'
            }, status=400)
        
        # Store session name for logging
        session_name = session.metadata.get('name', str(session_id)[:8])
        
        # Delete the session (cascade will delete related records)
        session.delete()
        
        logger.info(f"Session {session_id} ({session_name}) deleted successfully")
        
        return JsonResponse({
            'success': True,
            'message': 'Session deleted successfully',
            'session_id': str(session_id)
        })
        
    except Exception as e:
        logger.error(f"Error deleting session {session_id}: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Error deleting session: {str(e)}'
        }, status=500)


# Log module initialization
logger.info("Session delete API endpoint loaded")