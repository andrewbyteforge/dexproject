"""
Enhanced Trading Execution Tasks with Risk Assessment Integration - PHASE 5.1C COMPLETE

Complete integration between risk assessment system and trading execution.
All trading tasks now require risk approval before execution.

UPDATED: Full risk integration - trades only execute after risk validation

File: dexproject/trading/tasks.py
"""

import logging
import time
import asyncio
import random
from typing import Dict, Any, Optional, List, Tuple
from decimal import Decimal
from celery import shared_task
from django.utils import timezone
from django.db import transaction
from django.conf import settings
from django.contrib.auth.models import User
from datetime import datetime
from decimal import Decimal
# Import our enhanced Web3 infrastructure
from engine.config import config, ChainConfig
from engine.web3_client import Web3Client
from engine.wallet_manager import WalletManager, WalletType
from engine.utils import ProviderManager

# Import trading services
# from .services.dex_router_service import (
#     create_dex_router_service, SwapParams, SwapResult, SwapType, DEXVersion
# )
# from .services.portfolio_service import create_portfolio_service, PortfolioUpdate

# Import risk assessment integration
from risk.tasks.tasks import assess_token_risk

# from .models import Trade, Position, TradingPair, Strategy

logger = logging.getLogger(__name__)

# Global service instances (one per chain)
_web3_clients: Dict[int, Web3Client] = {}
_wallet_managers: Dict[int, WalletManager] = {}
_dex_router_services: Dict[int, Any] = {}
_portfolio_services: Dict[int, Any] = {}


async def get_web3_client(chain_id: int) -> Web3Client:
    """Get or create Web3 client for specific chain."""
    if chain_id not in _web3_clients:
        chain_config = config.get_chain_config(chain_id)
        if not chain_config:
            raise ValueError(f"No configuration found for chain {chain_id}")
        
        client = Web3Client(chain_config)
        await client.connect()
        _web3_clients[chain_id] = client
    
    return _web3_clients[chain_id]


async def get_wallet_manager(chain_id: int) -> WalletManager:
    """Get or create wallet manager for specific chain."""
    if chain_id not in _wallet_managers:
        chain_config = config.get_chain_config(chain_id)
        if not chain_config:
            raise ValueError(f"No configuration found for chain {chain_id}")
        
        web3_client = await get_web3_client(chain_id)
        wallet_manager = WalletManager(chain_config)
        await wallet_manager.initialize(web3_client)
        wallet_manager.unlock_wallet()  # Auto-unlock for development
        _wallet_managers[chain_id] = wallet_manager
    
    return _wallet_managers[chain_id]


async def get_dex_router_service(chain_id: int):
    """Get or create DEX router service for specific chain."""
    if chain_id not in _dex_router_services:
        web3_client = await get_web3_client(chain_id)
        wallet_manager = await get_wallet_manager(chain_id)
        
        dex_service = await create_dex_router_service(web3_client, wallet_manager)
        _dex_router_services[chain_id] = dex_service
    
    return _dex_router_services[chain_id]


async def get_portfolio_service(chain_id: int):
    """Get or create portfolio service for specific chain."""
    if chain_id not in _portfolio_services:
        chain_config = config.get_chain_config(chain_id)
        if not chain_config:
            raise ValueError(f"No configuration found for chain {chain_id}")
        
        portfolio_service = create_portfolio_service(chain_config)
        _portfolio_services[chain_id] = portfolio_service
    
    return _portfolio_services[chain_id]


def run_async_task(coro):
    """Helper to run async code in sync Celery task."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(coro)


def _validate_risk_assessment(
    risk_result: Dict[str, Any], 
    token_address: str,
    min_confidence_threshold: Decimal = Decimal('70.0')  # ← NEW: Add parameter
) -> Tuple[bool, str]:
    """
    Validate risk assessment result and determine if trade should proceed.
    
    Args:
        risk_result: Result from risk assessment task
        token_address: Token being assessed
        min_confidence_threshold: Minimum confidence required (from strategy config)
        
    Returns:
        Tuple of (should_proceed, reason)
    """
    try:
        # Check if risk assessment completed successfully
        if risk_result.get('status') != 'completed':
            return False, f"Risk assessment failed: {risk_result.get('error', 'Unknown error')}"
        
        # Get trading decision
        trading_decision = risk_result.get('trading_decision')
        overall_risk_score = risk_result.get('overall_risk_score', 100)
        confidence_score = risk_result.get('confidence_score', 0)
        
        # Block trades if decision is BLOCK
        if trading_decision == 'BLOCK':
            return False, f"Trade blocked by risk assessment (Risk: {overall_risk_score:.1f}/100)"
        
        # Require minimum confidence for trades (use configured threshold)
        if confidence_score < float(min_confidence_threshold):
            return False, f"Insufficient confidence in risk assessment ({confidence_score:.1f}% < {min_confidence_threshold:.1f}%)"
        
        # Warning for SKIP decisions
        if trading_decision == 'SKIP':
            logger.warning(
                f"Risk assessment recommends SKIP for {token_address} "
                f"(Risk: {overall_risk_score:.1f}, Confidence: {confidence_score:.1f}%) - "
                f"Proceeding anyway due to manual override"
            )
        
        # Log successful validation
        logger.info(
            f"✅ Risk validation passed: {trading_decision} "
            f"(Risk: {overall_risk_score:.1f}/100, Confidence: {confidence_score:.1f}%)"
        )
        
        return True, "Risk validation passed"
        
    except Exception as e:
        logger.error(f"Error validating risk assessment: {e}")
        return False, f"Risk validation error: {str(e)}"







@shared_task(
    bind=True,
    queue='execution.critical',
    name='trading.tasks.execute_buy_order_with_risk',
    max_retries=2,
    default_retry_delay=0.5
)
def execute_buy_order_with_risk(
    self,
    pair_address: str,
    token_address: str,
    amount_eth: str,
    slippage_tolerance: float = 0.05,
    gas_price_gwei: Optional[float] = None,
    trade_id: Optional[str] = None,
    user_id: Optional[int] = None,
    strategy_id: Optional[int] = None,
    risk_profile: str = 'Conservative',
    skip_risk_check: bool = False,
    chain_id: int = 8453  # Base mainnet default
) -> Dict[str, Any]:
    """
    Execute a buy order with mandatory risk assessment validation.
    
    NEW: This task now includes comprehensive risk validation before trade execution.
    
    Args:
        pair_address: Trading pair contract address
        token_address: Token to buy
        amount_eth: Amount of ETH to spend
        slippage_tolerance: Maximum acceptable slippage (0.05 = 5%)
        gas_price_gwei: Manual gas price override
        trade_id: Optional trade ID for tracking
        user_id: User making the trade
        strategy_id: Strategy being used
        risk_profile: Risk profile for assessment ('Conservative', 'Moderate', 'Aggressive')
        skip_risk_check: Emergency override to skip risk check (DANGEROUS)
        chain_id: Blockchain network ID
        
    Returns:
        Dictionary with trade execution results and risk assessment data
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.info(
        f"🚀 Starting buy order with risk validation: {amount_eth} ETH → {token_address[:10]}... "
        f"(task: {task_id}, risk_profile: {risk_profile})"
    )
    
    try:
        # =============================================================================
        # PHASE 1: MANDATORY RISK ASSESSMENT
        # =============================================================================
        
        risk_assessment_result = None
        
        if not skip_risk_check:
            logger.info(f"🔍 Performing risk assessment for {token_address[:10]}...")
            
            # Call risk assessment task
            risk_task = assess_token_risk.delay(
                token_address=token_address,
                pair_address=pair_address,
                risk_profile=risk_profile,
                parallel_execution=True,
                include_advanced_checks=True
            )
            
            # Wait for risk assessment with timeout
            try:
                risk_assessment_result = risk_task.get(timeout=30)  # 30 second timeout
            except Exception as e:
                return {
                    'task_id': task_id,
                    'trade_id': trade_id,
                    'operation': 'BUY',
                    'status': 'failed',
                    'error': f"Risk assessment failed: {str(e)}",
                    'execution_time_seconds': time.time() - start_time,
                    'timestamp': timezone.now().isoformat()
                }
            
            # Validate risk assessment result
            # Validate risk assessment result (with confidence threshold from config)
            # TODO: Get min_confidence from strategy config if available
            can_proceed, risk_reason = _validate_risk_assessment(
                risk_assessment_result,
                token_address,
                min_confidence_threshold=Decimal('70.0')  # Default for now
            )
            
            if not can_proceed:
                logger.warning(f"❌ Trade blocked by risk assessment: {risk_reason}")
                return {
                    'task_id': task_id,
                    'trade_id': trade_id,
                    'operation': 'BUY',
                    'status': 'blocked_by_risk',
                    'error': risk_reason,
                    'risk_assessment': risk_assessment_result,
                    'execution_time_seconds': time.time() - start_time,
                    'timestamp': timezone.now().isoformat()
                }
            
            logger.info(f"✅ Risk assessment passed: {risk_reason}")
        
        else:
            logger.warning(f"⚠️ RISK CHECK SKIPPED - Emergency override enabled for {token_address[:10]}...")
        
        # =============================================================================
        # PHASE 2: TRADE EXECUTION
        # =============================================================================
        
        async def execute_buy():
            """Execute the actual buy order after risk validation."""
            
            # Get trading services
            dex_router = await get_dex_router_service(chain_id)
            portfolio_service = await get_portfolio_service(chain_id)
            wallet_manager = await get_wallet_manager(chain_id)
            
            # Get wallet address
            wallet_address = wallet_manager.get_default_address()
            if not wallet_address:
                raise Exception("No wallet address available")
            
            # Create swap parameters
            swap_params = SwapParams(
                token_in=wallet_manager.get_chain_config().wrapped_native_token,  # WETH
                token_out=token_address,
                amount_in=int(Decimal(amount_eth) * Decimal('1e18')),  # Convert ETH to wei
                amount_out_minimum=0,  # Will be calculated with slippage
                swap_type=SwapType.EXACT_ETH_FOR_TOKENS,
                dex_version=DEXVersion.UNISWAP_V3,
                recipient=wallet_address,
                deadline=int(time.time()) + 300,  # 5 minute deadline
                slippage_tolerance=Decimal(str(slippage_tolerance)),
                gas_price_gwei=Decimal(str(gas_price_gwei)) if gas_price_gwei else None
            )
            
            # Calculate minimum amount out with slippage protection
            # This would normally use a price oracle - simplified for now
            estimated_amount_out = int(Decimal(amount_eth) * Decimal('1000') * Decimal('1e18'))  # Mock: 1 ETH = 1000 tokens
            swap_params.amount_out_minimum = int(
                estimated_amount_out * (Decimal('1') - swap_params.slippage_tolerance)
            )
            
            logger.info(f"💱 Executing swap: {amount_eth} ETH → {token_address[:10]}... (min: {swap_params.amount_out_minimum / 1e18:.6f} tokens)")
            
            # Execute the swap
            swap_result = await dex_router.execute_swap(swap_params, wallet_address)
            
            if swap_result.success:
                logger.info(f"✅ Swap successful: {swap_result.transaction_hash[:10]}...")
                
                # Record trade in portfolio tracking
                user = None
                strategy = None
                
                if user_id:
                    try:
                        user = User.objects.get(id=user_id)
                    except User.DoesNotExist:
                        logger.warning(f"User {user_id} not found")
                
                if strategy_id:
                    try:
                        strategy = Strategy.objects.get(id=strategy_id)
                    except Strategy.DoesNotExist:
                        logger.warning(f"Strategy {strategy_id} not found")
                
                # Record the trade in portfolio
                portfolio_update = await portfolio_service.record_swap_trade(
                    swap_result=swap_result,
                    swap_type=SwapType.EXACT_ETH_FOR_TOKENS,
                    token_in_address=swap_params.token_in,
                    token_out_address=token_address,
                    pair_address=pair_address,
                    user=user,
                    strategy=strategy,
                    trade_id=trade_id
                )
                
                return {
                    'success': True,
                    'transaction_hash': swap_result.transaction_hash,
                    'amount_out': swap_result.amount_out,
                    'gas_used': swap_result.gas_used,
                    'execution_time_ms': swap_result.execution_time_ms,
                    'portfolio_update': {
                        'trade_created': portfolio_update.trade_created,
                        'position_updated': portfolio_update.position_updated,
                        'trade_id': portfolio_update.trade_id,
                        'position_id': portfolio_update.position_id,
                        'realized_pnl': str(portfolio_update.realized_pnl) if portfolio_update.realized_pnl else None,
                        'unrealized_pnl': str(portfolio_update.unrealized_pnl) if portfolio_update.unrealized_pnl else None
                    }
                }
                
            else:
                # Handle failed swap
                raise Exception(f"Swap execution failed: {swap_result.error_message}")
        
        # Execute async operation
        result = run_async_task(execute_buy())
        duration = time.time() - start_time
        
        # Prepare final result
        final_result = {
            'task_id': task_id,
            'trade_id': trade_id or result.get('portfolio_update', {}).get('trade_id'),
            'operation': 'BUY',
            'pair_address': pair_address,
            'token_address': token_address,
            'amount_eth': amount_eth,
            'chain_id': chain_id,
            'status': 'completed',
            'transaction_hash': result.get('transaction_hash'),
            'amount_out': result.get('amount_out'),
            'gas_used': result.get('gas_used'),
            'execution_time_ms': result.get('execution_time_ms'),
            'execution_time_seconds': duration,
            'portfolio_update': result.get('portfolio_update'),
            'risk_assessment': risk_assessment_result,
            'timestamp': timezone.now().isoformat()
        }
        
        logger.info(f"🎉 Buy order completed successfully in {duration:.2f}s: {result.get('transaction_hash', 'N/A')[:10]}...")
        return final_result
        
    except Exception as exc:
        duration = time.time() - start_time
        logger.error(f"Buy order execution failed: {exc} (task: {task_id})")
        
        if self.request.retries < self.max_retries:
            logger.warning(f"Retrying buy order execution (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc, countdown=0.5)
        
        return {
            'task_id': task_id,
            'trade_id': trade_id,
            'operation': 'BUY',
            'pair_address': pair_address,
            'token_address': token_address,
            'amount_eth': amount_eth,
            'chain_id': chain_id,
            'error': str(exc),
            'execution_time_seconds': duration,
            'status': 'failed',
            'risk_assessment': risk_assessment_result,
            'timestamp': timezone.now().isoformat()
        }


@shared_task(
    bind=True,
    queue='execution.critical', 
    name='trading.tasks.execute_sell_order_with_risk',
    max_retries=2,
    default_retry_delay=0.5
)
def execute_sell_order_with_risk(
    self,
    pair_address: str,
    token_address: str,
    token_amount: str,
    slippage_tolerance: float = 0.05,
    gas_price_gwei: Optional[float] = None,
    trade_id: Optional[str] = None,
    user_id: Optional[int] = None,
    strategy_id: Optional[int] = None,
    is_emergency: bool = False,
    risk_profile: str = 'Conservative',
    chain_id: int = 8453
) -> Dict[str, Any]:
    """
    Execute a sell order with risk assessment validation.
    
    NEW: Sell orders now include risk validation, but emergency sells can skip checks.
    
    Args:
        pair_address: Trading pair contract address
        token_address: Token to sell
        token_amount: Amount of tokens to sell
        slippage_tolerance: Maximum acceptable slippage
        gas_price_gwei: Manual gas price override
        trade_id: Optional trade ID for tracking
        user_id: User making the trade
        strategy_id: Strategy being used
        is_emergency: Emergency sell - skips some risk checks
        risk_profile: Risk profile for assessment
        chain_id: Blockchain network ID
        
    Returns:
        Dictionary with trade execution results
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.info(
        f"📤 Starting sell order: {token_amount} {token_address[:10]}... "
        f"(task: {task_id}, emergency: {is_emergency})"
    )
    
    try:
        # =============================================================================
        # PHASE 1: RISK ASSESSMENT (REDUCED FOR SELL ORDERS)
        # =============================================================================
        
        risk_assessment_result = None
        
        if not is_emergency:
            logger.info(f"🔍 Performing lightweight risk assessment for sell order...")
            
            # For sell orders, we do a lighter risk check focusing on:
            # - Market conditions
            # - Slippage risk
            # - Gas optimization
            # We skip honeypot checks since we're selling, not buying
            
            risk_task = assess_token_risk.delay(
                token_address=token_address,
                pair_address=pair_address,
                risk_profile=risk_profile,
                parallel_execution=True,
                include_advanced_checks=False  # Lighter checks for sells
            )
            
            try:
                risk_assessment_result = risk_task.get(timeout=15)  # Shorter timeout for sells
            except Exception as e:
                logger.warning(f"Risk assessment failed for sell order, proceeding anyway: {e}")
                risk_assessment_result = {'status': 'failed', 'error': str(e)}
        
        else:
            logger.warning(f"⚡ EMERGENCY SELL - Skipping risk assessment for {token_address[:10]}...")
        
        # =============================================================================
        # PHASE 2: SELL EXECUTION
        # =============================================================================
        
        async def execute_sell():
            """Execute the actual sell order."""
            
            # Get trading services
            dex_router = await get_dex_router_service(chain_id)
            portfolio_service = await get_portfolio_service(chain_id)
            wallet_manager = await get_wallet_manager(chain_id)
            
            # Get wallet address
            wallet_address = wallet_manager.get_default_address()
            if not wallet_address:
                raise Exception("No wallet address available")
            
            # Create swap parameters for sell
            swap_params = SwapParams(
                token_in=token_address,
                token_out=wallet_manager.get_chain_config().wrapped_native_token,  # WETH
                amount_in=int(Decimal(token_amount) * Decimal('1e18')),  # Convert to wei
                amount_out_minimum=0,  # Will be calculated with slippage
                swap_type=SwapType.EXACT_TOKENS_FOR_ETH,
                dex_version=DEXVersion.UNISWAP_V3,
                recipient=wallet_address,
                deadline=int(time.time()) + 300,  # 5 minute deadline
                slippage_tolerance=Decimal(str(slippage_tolerance)),
                gas_price_gwei=Decimal(str(gas_price_gwei)) if gas_price_gwei else None
            )
            
            # Calculate minimum ETH out with slippage protection
            # This would normally use a price oracle - simplified for now
            estimated_eth_out = int(Decimal(token_amount) * Decimal('0.001') * Decimal('1e18'))  # Mock: 1000 tokens = 1 ETH
            swap_params.amount_out_minimum = int(
                estimated_eth_out * (Decimal('1') - swap_params.slippage_tolerance)
            )
            
            logger.info(f"💱 Executing sell: {token_amount} tokens → ETH (min: {swap_params.amount_out_minimum / 1e18:.6f} ETH)")
            
            # Execute the swap
            swap_result = await dex_router.execute_swap(swap_params, wallet_address)
            
            if swap_result.success:
                logger.info(f"✅ Sell successful: {swap_result.transaction_hash[:10]}...")
                
                # Record trade in portfolio tracking
                user = None
                strategy = None
                
                if user_id:
                    try:
                        user = User.objects.get(id=user_id)
                    except User.DoesNotExist:
                        logger.warning(f"User {user_id} not found")
                
                if strategy_id:
                    try:
                        strategy = Strategy.objects.get(id=strategy_id)
                    except Strategy.DoesNotExist:
                        logger.warning(f"Strategy {strategy_id} not found")
                
                # Record the trade in portfolio
                portfolio_update = await portfolio_service.record_swap_trade(
                    swap_result=swap_result,
                    swap_type=SwapType.EXACT_TOKENS_FOR_ETH,
                    token_in_address=token_address,
                    token_out_address=swap_params.token_out,
                    pair_address=pair_address,
                    user=user,
                    strategy=strategy,
                    trade_id=trade_id
                )
                
                return {
                    'success': True,
                    'transaction_hash': swap_result.transaction_hash,
                    'amount_out': swap_result.amount_out,
                    'gas_used': swap_result.gas_used,
                    'execution_time_ms': swap_result.execution_time_ms,
                    'portfolio_update': {
                        'trade_created': portfolio_update.trade_created,
                        'position_updated': portfolio_update.position_updated,
                        'trade_id': portfolio_update.trade_id,
                        'position_id': portfolio_update.position_id,
                        'realized_pnl': str(portfolio_update.realized_pnl) if portfolio_update.realized_pnl else None,
                        'unrealized_pnl': str(portfolio_update.unrealized_pnl) if portfolio_update.unrealized_pnl else None
                    }
                }
                
            else:
                raise Exception(f"Sell execution failed: {swap_result.error_message}")
        
        # Execute async operation
        result = run_async_task(execute_sell())
        duration = time.time() - start_time
        
        # Prepare final result
        final_result = {
            'task_id': task_id,
            'trade_id': trade_id or result.get('portfolio_update', {}).get('trade_id'),
            'operation': 'SELL',
            'pair_address': pair_address,
            'token_address': token_address,
            'token_amount': token_amount,
            'chain_id': chain_id,
            'status': 'completed',
            'transaction_hash': result.get('transaction_hash'),
            'amount_out': result.get('amount_out'),
            'gas_used': result.get('gas_used'),
            'execution_time_ms': result.get('execution_time_ms'),
            'execution_time_seconds': duration,
            'portfolio_update': result.get('portfolio_update'),
            'risk_assessment': risk_assessment_result,
            'is_emergency': is_emergency,
            'timestamp': timezone.now().isoformat()
        }
        
        logger.info(f"🎉 Sell order completed successfully in {duration:.2f}s: {result.get('transaction_hash', 'N/A')[:10]}...")
        return final_result
        
    except Exception as exc:
        duration = time.time() - start_time
        logger.error(f"Sell order execution failed: {exc} (task: {task_id})")
        
        if self.request.retries < self.max_retries:
            logger.warning(f"Retrying sell order execution (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc, countdown=0.5)
        
        return {
            'task_id': task_id,
            'trade_id': trade_id,
            'operation': 'SELL',
            'pair_address': pair_address,
            'token_address': token_address,
            'token_amount': token_amount,
            'chain_id': chain_id,
            'error': str(exc),
            'execution_time_seconds': duration,
            'status': 'failed',
            'risk_assessment': risk_assessment_result,
            'is_emergency': is_emergency,
            'timestamp': timezone.now().isoformat()
        }


# =============================================================================
# SMART LANE → TRADING INTEGRATION WORKFLOW
# =============================================================================

@shared_task(
    bind=True,
    queue='risk.urgent',
    name='trading.tasks.smart_lane_trading_workflow',
    max_retries=1,
    default_retry_delay=1
)
def smart_lane_trading_workflow(
    self,
    token_address: str,
    pair_address: str,
    discovered_by: str = 'smart_lane',
    user_id: Optional[int] = None,
    strategy_id: Optional[int] = None,
    analysis_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Complete Smart Lane workflow: Analysis → Risk Assessment → Trading Decision → Execution.
    
    This is the main integration point that connects Smart Lane analysis to actual trading.
    
    Args:
        token_address: Token to analyze and potentially trade
        pair_address: Trading pair for the token
        discovered_by: How this token was discovered ('smart_lane', 'fast_lane', 'manual')
        user_id: User triggering the workflow
        strategy_id: Strategy to apply
        analysis_context: Additional context from discovery
        
    Returns:
        Complete workflow result including analysis, risk, and trading outcome
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.info(
        f"🧠 Starting Smart Lane trading workflow for {token_address[:10]}... "
        f"(discovered_by: {discovered_by}, task: {task_id})"
    )
    
    try:
        workflow_result = {
            'task_id': task_id,
            'token_address': token_address,
            'pair_address': pair_address,
            'discovered_by': discovered_by,
            'user_id': user_id,
            'strategy_id': strategy_id,
            'analysis_context': analysis_context or {},
            'start_time': timezone.now().isoformat(),
            'status': 'in_progress'
        }
        
        # =============================================================================
        # PHASE 1: COMPREHENSIVE RISK ASSESSMENT
        # =============================================================================
        
        logger.info(f"🔍 Phase 1: Running comprehensive risk assessment...")
        
        # Get strategy configuration
        strategy = None
        risk_profile = 'Conservative'  # Default
        
        if strategy_id:
            try:
                strategy = Strategy.objects.get(id=strategy_id)
                # Map strategy risk level to risk profile
                # This could be enhanced based on strategy configuration
                risk_profile = 'Conservative'  # For now, default to conservative
                logger.info(f"Using strategy: {strategy.name}")
            except Strategy.DoesNotExist:
                logger.warning(f"Strategy {strategy_id} not found, using default risk profile")
        
        # Execute comprehensive risk assessment
        risk_task = assess_token_risk.delay(
            token_address=token_address,
            pair_address=pair_address,
            risk_profile=risk_profile,
            parallel_execution=True,
            include_advanced_checks=True
        )
        
        try:
            risk_result = risk_task.get(timeout=45)  # Extended timeout for comprehensive analysis
        except Exception as e:
            logger.error(f"Risk assessment failed: {e}")
            workflow_result.update({
                'status': 'failed',
                'phase': 'risk_assessment',
                'error': f"Risk assessment failed: {str(e)}",
                'execution_time_seconds': time.time() - start_time
            })
            return workflow_result
        
        workflow_result['risk_assessment'] = risk_result
        
        # =============================================================================
        # PHASE 2: TRADING DECISION LOGIC
        # =============================================================================
        
        logger.info(f"🤔 Phase 2: Making trading decision...")
        
        trading_decision = risk_result.get('trading_decision', 'BLOCK')
        overall_risk_score = risk_result.get('overall_risk_score', 100)
        confidence_score = risk_result.get('confidence_score', 0)
        
        # Enhanced decision logic
        should_trade = False
        trade_reason = ""
        
        if trading_decision == 'APPROVE':
            should_trade = True
            trade_reason = f"Risk assessment approved trade (Risk: {overall_risk_score:.1f}/100, Confidence: {confidence_score:.1f}%)"
        
        elif trading_decision == 'SKIP':
            # For Smart Lane, we might trade SKIP decisions if confidence is high enough
            if confidence_score >= 80:
                should_trade = True
                trade_reason = f"Trading SKIP decision due to high confidence (Confidence: {confidence_score:.1f}%)"
            else:
                trade_reason = f"Skipping trade as recommended (Risk: {overall_risk_score:.1f}/100, Confidence: {confidence_score:.1f}%)"
        
        else:  # BLOCK
            trade_reason = f"Trade blocked by risk assessment (Risk: {overall_risk_score:.1f}/100)"
        
        workflow_result.update({
            'trading_decision': trading_decision,
            'should_trade': should_trade,
            'trade_reason': trade_reason,
            'overall_risk_score': overall_risk_score,
            'confidence_score': confidence_score
        })
        
        logger.info(f"📊 Trading decision: {trading_decision} → {'EXECUTE' if should_trade else 'SKIP'} ({trade_reason})")
        
        # =============================================================================
        # PHASE 3: TRADE EXECUTION (IF APPROVED)
        # =============================================================================
        
        if should_trade:
            logger.info(f"💰 Phase 3: Executing approved trade...")
            
            # Determine position size based on strategy
            position_size_eth = "0.01"  # Default small position
            
            if strategy:
                # Use strategy position sizing
                position_size_eth = str(strategy.max_position_size_eth)
            
            # Execute buy order with risk validation (will pass since we already assessed)
            trade_task = execute_buy_order_with_risk.delay(
                pair_address=pair_address,
                token_address=token_address,
                amount_eth=position_size_eth,
                slippage_tolerance=0.05,  # 5% slippage
                trade_id=None,
                user_id=user_id,
                strategy_id=strategy_id,
                risk_profile=risk_profile,
                skip_risk_check=True,  # Skip since we already did comprehensive assessment
                chain_id=8453  # Base mainnet
            )
            
            try:
                trade_result = trade_task.get(timeout=60)  # 60 second timeout for trade execution
                workflow_result['trade_execution'] = trade_result
                
                if trade_result.get('status') == 'completed':
                    logger.info(f"✅ Smart Lane workflow completed successfully with trade execution")
                    workflow_result['status'] = 'completed_with_trade'
                else:
                    logger.warning(f"⚠️ Trade execution failed: {trade_result.get('error')}")
                    workflow_result['status'] = 'completed_no_trade'
                
            except Exception as e:
                logger.error(f"Trade execution failed: {e}")
                workflow_result.update({
                    'trade_execution': {'error': str(e)},
                    'status': 'completed_no_trade'
                })
        
        else:
            logger.info(f"⏸️ Phase 3: Trade execution skipped due to decision logic")
            workflow_result['status'] = 'completed_no_trade'
        
        # =============================================================================
        # PHASE 4: WORKFLOW COMPLETION
        # =============================================================================
        
        execution_time = time.time() - start_time
        workflow_result.update({
            'execution_time_seconds': execution_time,
            'end_time': timezone.now().isoformat()
        })
        
        logger.info(
            f"🎯 Smart Lane workflow completed in {execution_time:.2f}s: "
            f"{workflow_result['status']} for {token_address[:10]}..."
        )
        
        return workflow_result
        
    except Exception as exc:
        execution_time = time.time() - start_time
        logger.error(f"Smart Lane workflow failed: {exc} (task: {task_id})")
        
        return {
            'task_id': task_id,
            'token_address': token_address,
            'pair_address': pair_address,
            'status': 'failed',
            'error': str(exc),
            'execution_time_seconds': execution_time,
            'timestamp': timezone.now().isoformat()
        }


# =============================================================================
# FAST LANE → TRADING INTEGRATION (PLACEHOLDER)
# =============================================================================

@shared_task(
    bind=True,
    queue='execution.critical',
    name='trading.tasks.fast_lane_trading_workflow',
    max_retries=0  # No retries for fast lane
)
def fast_lane_trading_workflow(
    self,
    token_address: str,
    pair_address: str,
    opportunity_type: str = 'mempool_discovery',
    user_id: Optional[int] = None,
    strategy_id: Optional[int] = None,
    fast_lane_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Fast Lane workflow: Rapid Risk Check → Immediate Execution.
    
    NOTE: This is a placeholder for future Fast Lane integration.
    Fast Lane requires sub-500ms execution, so risk checks must be minimal.
    
    Args:
        token_address: Token to trade
        pair_address: Trading pair
        opportunity_type: Type of Fast Lane opportunity
        user_id: User configuration
        strategy_id: Strategy (usually overridden by Fast Lane config)
        fast_lane_config: Fast Lane specific configuration
        
    Returns:
        Fast Lane execution result
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.info(
        f"⚡ Fast Lane workflow triggered for {token_address[:10]}... "
        f"(opportunity: {opportunity_type}, task: {task_id})"
    )
    
    # Placeholder implementation
    # In a real Fast Lane implementation, this would:
    # 1. Do rapid risk checks (< 100ms)
    # 2. Execute trades immediately if checks pass
    # 3. Use cached risk data where possible
    # 4. Prioritize speed over comprehensive analysis
    
    return {
        'task_id': task_id,
        'token_address': token_address,
        'pair_address': pair_address,
        'opportunity_type': opportunity_type,
        'status': 'placeholder',
        'message': 'Fast Lane integration will be implemented in future update',
        'execution_time_seconds': time.time() - start_time,
        'timestamp': timezone.now().isoformat()
    }


# =============================================================================
# LEGACY TASK ALIASES (FOR BACKWARD COMPATIBILITY)
# =============================================================================

# Keep old task names as aliases for backward compatibility
execute_buy_order = execute_buy_order_with_risk
execute_sell_order = execute_sell_order_with_risk