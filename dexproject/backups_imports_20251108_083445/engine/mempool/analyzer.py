"""
Mempool transaction analysis and filtering for Fast Lane execution.

This module analyzes pending transactions from the mempool monitor to identify
trading opportunities and potential risks. Optimized for sub-300ms analysis
to support Fast Lane execution requirements.

Path: engine/mempool/analyzer.py
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple, Any
from enum import Enum
from decimal import Decimal

from web3 import Web3
from web3.contract import Contract

from engine.mempool.monitor import MempoolTransaction, MempoolEventType
from shared.schemas import ChainType


logger = logging.getLogger(__name__)


class TransactionType(Enum):
    """Types of DEX transactions we can identify."""
    SWAP_EXACT_ETH_FOR_TOKENS = "swap_exact_eth_for_tokens"
    SWAP_TOKENS_FOR_EXACT_ETH = "swap_tokens_for_exact_eth"
    SWAP_EXACT_TOKENS_FOR_TOKENS = "swap_exact_tokens_for_tokens"
    SWAP_TOKENS_FOR_EXACT_TOKENS = "swap_tokens_for_exact_tokens"
    ADD_LIQUIDITY = "add_liquidity"
    REMOVE_LIQUIDITY = "remove_liquidity"
    MULTICALL = "multicall"
    UNKNOWN_DEX = "unknown_dex"
    NON_DEX = "non_dex"


class RiskFlag(Enum):
    """Risk flags for fast analysis."""
    HONEYPOT_SUSPECT = "honeypot_suspect"
    SANDWICH_ATTACK = "sandwich_attack"
    HIGH_SLIPPAGE = "high_slippage"
    LOW_LIQUIDITY = "low_liquidity"
    FRONT_RUN_OPPORTUNITY = "front_run_opportunity"
    MEV_BUNDLE = "mev_bundle"
    FLASH_LOAN = "flash_loan"
    LARGE_TRADE = "large_trade"


@dataclass
class TransactionAnalysis:
    """
    Analysis results for a mempool transaction.
    Optimized for Fast Lane decision making.
    """
    transaction_hash: str
    transaction_type: TransactionType
    target_token: Optional[str] = None
    input_token: Optional[str] = None
    estimated_amount_in: Optional[int] = None  # Wei
    estimated_amount_out: Optional[int] = None  # Wei
    estimated_gas_cost: Optional[int] = None  # Wei
    estimated_impact: Optional[float] = None  # Price impact %
    
    # Risk assessment (fast checks only)
    risk_flags: Set[RiskFlag] = None
    risk_score: float = 0.0  # 0-1 scale, 1 = maximum risk
    
    # Opportunity assessment
    is_arbitrage_opportunity: bool = False
    is_front_run_opportunity: bool = False
    is_copy_trade_candidate: bool = False
    estimated_profit_eth: Optional[float] = None
    
    # Performance metrics
    analysis_time_ms: float = 0.0
    confidence_score: float = 0.0  # 0-1 scale, 1 = maximum confidence
    
    def __post_init__(self):
        if self.risk_flags is None:
            self.risk_flags = set()


class MempoolAnalyzer:
    """
    High-speed mempool transaction analyzer for Fast Lane execution.
    
    Performs rapid analysis of pending transactions to identify:
    - Trading opportunities (arbitrage, copy trading, front-running)
    - Risk factors (honeypots, sandwich attacks, high slippage)
    - Transaction classification and routing decisions
    """
    
    def __init__(self, provider_manager, chain_configs: Dict[int, Any]):
        """
        Initialize mempool analyzer.
        
        Args:
            provider_manager: Provider manager for Web3 calls
            chain_configs: Chain configuration mapping
        """
        self.provider_manager = provider_manager
        self.chain_configs = chain_configs
        
        # Cache for contract ABIs and metadata
        self.contract_cache: Dict[str, Dict] = {}
        self.token_cache: Dict[str, Dict] = {}
        self.pair_cache: Dict[str, Dict] = {}
        
        # Known function signatures for fast identification
        self.dex_function_sigs = {
            # Uniswap V2 Router
            '0x7ff36ab5': 'swapExactETHForTokens',
            '0x18cbafe5': 'swapExactTokensForETH',
            '0x38ed1739': 'swapExactTokensForTokens',
            '0x8803dbee': 'swapTokensForExactTokens',
            '0xf305d719': 'addLiquidityETH',
            '0xe8e33700': 'addLiquidity',
            '0x02751cec': 'removeLiquidityETH',
            '0xbaa2abde': 'removeLiquidity',
            
            # Uniswap V3 Router
            '0x414bf389': 'exactInputSingle',
            '0xc04b8d59': 'exactInput',
            '0xdb3e2198': 'exactOutputSingle',
            '0x09b81346': 'exactOutput',
            '0xac9650d8': 'multicall',
        }
        
        # Performance tracking
        self.stats = {
            'transactions_analyzed': 0,
            'analysis_time_total_ms': 0.0,
            'opportunities_identified': 0,
            'risk_flags_triggered': 0,
        }
        
        logger.info("MempoolAnalyzer initialized")
    
    async def analyze_transaction(self, transaction: MempoolTransaction) -> TransactionAnalysis:
        """
        Analyze a pending transaction for opportunities and risks.
        
        Args:
            transaction: Pending transaction to analyze
            
        Returns:
            TransactionAnalysis with results
        """
        start_time = time.perf_counter()
        
        try:
            analysis = TransactionAnalysis(
                transaction_hash=transaction.hash,
                transaction_type=TransactionType.NON_DEX
            )
            
            # Fast transaction type identification
            tx_type = self._identify_transaction_type(transaction)
            analysis.transaction_type = tx_type
            
            if tx_type != TransactionType.NON_DEX:
                # DEX transaction - perform detailed analysis
                await self._analyze_dex_transaction(transaction, analysis)
                
                # Risk assessment (fast checks only)
                await self._perform_risk_analysis(transaction, analysis)
                
                # Opportunity identification
                await self._identify_opportunities(transaction, analysis)
            
            # Calculate analysis time and update stats
            analysis.analysis_time_ms = (time.perf_counter() - start_time) * 1000
            self._update_stats(analysis)
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing transaction {transaction.hash}: {e}")
            analysis = TransactionAnalysis(
                transaction_hash=transaction.hash,
                transaction_type=TransactionType.UNKNOWN_DEX,
                analysis_time_ms=(time.perf_counter() - start_time) * 1000,
                risk_score=1.0  # Maximum risk for unknown errors
            )
            return analysis
    
    def _identify_transaction_type(self, transaction: MempoolTransaction) -> TransactionType:
        """
        Rapidly identify transaction type from input data.
        
        Args:
            transaction: Transaction to identify
            
        Returns:
            TransactionType enum value
        """
        if not transaction.input_data or len(transaction.input_data) < 10:
            return TransactionType.NON_DEX
        
        # Extract function signature (first 4 bytes)
        func_sig = transaction.input_data[:10].lower()
        
        # Check against known DEX function signatures
        if func_sig in self.dex_function_sigs:
            func_name = self.dex_function_sigs[func_sig]
            
            # Map function names to transaction types
            if 'swapExact' in func_name and 'ETH' in func_name and 'Tokens' in func_name:
                return TransactionType.SWAP_EXACT_ETH_FOR_TOKENS
            elif 'swapExact' in func_name and 'Tokens' in func_name and 'ETH' in func_name:
                return TransactionType.SWAP_TOKENS_FOR_EXACT_ETH
            elif 'swapExact' in func_name and 'Tokens' in func_name:
                return TransactionType.SWAP_EXACT_TOKENS_FOR_TOKENS
            elif 'swapTokens' in func_name:
                return TransactionType.SWAP_TOKENS_FOR_EXACT_TOKENS
            elif 'addLiquidity' in func_name:
                return TransactionType.ADD_LIQUIDITY
            elif 'removeLiquidity' in func_name:
                return TransactionType.REMOVE_LIQUIDITY
            elif func_name == 'multicall':
                return TransactionType.MULTICALL
            
        # Check if targeting known DEX router (fallback identification)
        if transaction.to_address:
            chain_config = self.chain_configs.get(transaction.chain_id)
            if chain_config:
                routers = [
                    chain_config.uniswap_v2_router.lower(),
                    chain_config.uniswap_v3_router.lower()
                ]
                if transaction.to_address.lower() in routers:
                    return TransactionType.UNKNOWN_DEX
        
        return TransactionType.NON_DEX
    
    async def _analyze_dex_transaction(self, transaction: MempoolTransaction, analysis: TransactionAnalysis) -> None:
        """
        Analyze DEX transaction details for routing and impact estimation.
        
        Args:
            transaction: Transaction to analyze
            analysis: Analysis object to populate
        """
        try:
            # Decode transaction input for token addresses and amounts
            await self._decode_transaction_params(transaction, analysis)
            
            # Estimate gas cost
            analysis.estimated_gas_cost = transaction.gas_limit * transaction.gas_price
            
            # Estimate price impact (simplified calculation)
            if analysis.estimated_amount_in and analysis.target_token:
                analysis.estimated_impact = await self._estimate_price_impact(
                    transaction.chain_id,
                    analysis.target_token,
                    analysis.estimated_amount_in
                )
            
            # Set confidence based on available data
            analysis.confidence_score = self._calculate_confidence(analysis)
            
        except Exception as e:
            logger.debug(f"Error in DEX transaction analysis: {e}")
            analysis.confidence_score = 0.0
    
    async def _decode_transaction_params(self, transaction: MempoolTransaction, analysis: TransactionAnalysis) -> None:
        """
        Decode transaction parameters to extract token addresses and amounts.
        
        This is a simplified implementation - in production, you'd want to use
        proper ABI decoding for accurate parameter extraction.
        """
        try:
            input_data = transaction.input_data
            
            if analysis.transaction_type == TransactionType.SWAP_EXACT_ETH_FOR_TOKENS:
                # Extract amountOutMin and path from function call
                # Simplified - proper ABI decoding would be more accurate
                if len(input_data) >= 138:  # Minimum length for this function
                    # Amount out min is typically at offset 32-64
                    analysis.estimated_amount_out = int(input_data[74:138], 16)
                    # Token address is in the path (last 40 chars of path)
                    if len(input_data) >= 202:
                        analysis.target_token = '0x' + input_data[162:202].lower()
                
            elif analysis.transaction_type == TransactionType.SWAP_EXACT_TOKENS_FOR_TOKENS:
                # Extract amounts and token addresses from path
                if len(input_data) >= 202:
                    analysis.estimated_amount_in = int(input_data[10:74], 16)
                    analysis.estimated_amount_out = int(input_data[74:138], 16)
                    # Extract token addresses from path
                    analysis.input_token = '0x' + input_data[202:242].lower()
                    if len(input_data) >= 282:
                        analysis.target_token = '0x' + input_data[242:282].lower()
            
            # For other transaction types, add similar decoding logic
            
        except (ValueError, IndexError) as e:
            logger.debug(f"Error decoding transaction parameters: {e}")
    
    async def _estimate_price_impact(self, chain_id: int, token_address: str, amount_in: int) -> float:
        """
        Estimate price impact for a trade (simplified calculation).
        
        Args:
            chain_id: Chain ID
            token_address: Target token address
            amount_in: Input amount in wei
            
        Returns:
            Estimated price impact as percentage
        """
        try:
            # This is a simplified estimation - production would use:
            # 1. Real liquidity data from pairs
            # 2. Uniswap V2/V3 math for accurate calculations
            # 3. Multi-hop path analysis
            
            # For now, use heuristic based on trade size
            amount_eth = amount_in / 1e18
            
            if amount_eth < 0.1:
                return 0.1  # Minimal impact
            elif amount_eth < 1:
                return 0.5
            elif amount_eth < 10:
                return 2.0
            elif amount_eth < 100:
                return 5.0
            else:
                return 10.0  # High impact
                
        except Exception:
            return 5.0  # Default moderate impact
    
    async def _perform_risk_analysis(self, transaction: MempoolTransaction, analysis: TransactionAnalysis) -> None:
        """
        Perform fast risk analysis on the transaction.
        
        Args:
            transaction: Transaction to analyze
            analysis: Analysis object to update
        """
        risk_flags = set()
        risk_score = 0.0
        
        # High gas price check (potential MEV)
        if transaction.gas_price > 100 * 1e9:  # > 100 gwei
            risk_flags.add(RiskFlag.MEV_BUNDLE)
            risk_score += 0.3
        
        # Large transaction check
        if transaction.value > 10 * 1e18:  # > 10 ETH
            risk_flags.add(RiskFlag.LARGE_TRADE)
            risk_score += 0.2
        
        # High slippage estimate
        if analysis.estimated_impact and analysis.estimated_impact > 5.0:
            risk_flags.add(RiskFlag.HIGH_SLIPPAGE)
            risk_score += 0.4
        
        # Potential front-running opportunity
        if (transaction.gas_price < 20 * 1e9 and  # Low gas price
            analysis.estimated_amount_in and 
            analysis.estimated_amount_in > 1 * 1e18):  # Large trade
            risk_flags.add(RiskFlag.FRONT_RUN_OPPORTUNITY)
            analysis.is_front_run_opportunity = True
        
        # Flash loan detection (simplified)
        if transaction.input_data and len(transaction.input_data) > 1000:
            # Complex transaction - might be flash loan
            risk_flags.add(RiskFlag.FLASH_LOAN)
            risk_score += 0.2
        
        analysis.risk_flags = risk_flags
        analysis.risk_score = min(risk_score, 1.0)
        
        if risk_flags:
            self.stats['risk_flags_triggered'] += len(risk_flags)
    
    async def _identify_opportunities(self, transaction: MempoolTransaction, analysis: TransactionAnalysis) -> None:
        """
        Identify trading opportunities from the transaction.
        
        Args:
            transaction: Transaction to analyze
            analysis: Analysis object to update
        """
        # Front-running opportunity (already set in risk analysis)
        
        # Copy trade candidate (large successful trader)
        if (analysis.estimated_amount_in and 
            analysis.estimated_amount_in > 5 * 1e18 and  # > 5 ETH trade
            analysis.risk_score < 0.3):  # Low risk
            analysis.is_copy_trade_candidate = True
        
        # Arbitrage opportunity detection (simplified)
        if (analysis.transaction_type in [
            TransactionType.SWAP_EXACT_ETH_FOR_TOKENS,
            TransactionType.SWAP_EXACT_TOKENS_FOR_TOKENS
        ] and analysis.estimated_impact and analysis.estimated_impact > 2.0):
            # Large price impact might create arbitrage opportunity
            analysis.is_arbitrage_opportunity = True
            # Rough profit estimate (very simplified)
            if analysis.estimated_amount_in:
                analysis.estimated_profit_eth = (analysis.estimated_amount_in / 1e18) * 0.01
        
        if (analysis.is_arbitrage_opportunity or 
            analysis.is_front_run_opportunity or 
            analysis.is_copy_trade_candidate):
            self.stats['opportunities_identified'] += 1
    
    def _calculate_confidence(self, analysis: TransactionAnalysis) -> float:
        """
        Calculate confidence score based on available data.
        
        Args:
            analysis: Analysis to calculate confidence for
            
        Returns:
            Confidence score (0-1)
        """
        confidence = 0.0
        
        # Base confidence from transaction type identification
        if analysis.transaction_type != TransactionType.UNKNOWN_DEX:
            confidence += 0.3
        
        # Additional confidence from decoded parameters
        if analysis.target_token:
            confidence += 0.3
        
        if analysis.estimated_amount_in:
            confidence += 0.2
        
        if analysis.estimated_impact:
            confidence += 0.2
        
        return min(confidence, 1.0)
    
    def _update_stats(self, analysis: TransactionAnalysis) -> None:
        """Update analyzer statistics."""
        self.stats['transactions_analyzed'] += 1
        self.stats['analysis_time_total_ms'] += analysis.analysis_time_ms
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get analyzer performance statistics."""
        stats = self.stats.copy()
        
        if stats['transactions_analyzed'] > 0:
            stats['average_analysis_time_ms'] = (
                stats['analysis_time_total_ms'] / stats['transactions_analyzed']
            )
        else:
            stats['average_analysis_time_ms'] = 0.0
        
        return stats
    
    async def get_cached_token_info(self, chain_id: int, token_address: str) -> Optional[Dict]:
        """
        Get cached token information or fetch if not available.
        
        Args:
            chain_id: Chain ID
            token_address: Token contract address
            
        Returns:
            Token information dict or None
        """
        cache_key = f"{chain_id}:{token_address.lower()}"
        
        if cache_key in self.token_cache:
            return self.token_cache[cache_key]
        
        # In Fast Lane, we don't fetch new data to maintain speed
        # This would be populated by background processes
        return None
    
    async def update_token_cache(self, chain_id: int, token_address: str, token_info: Dict) -> None:
        """
        Update token cache with new information.
        
        Args:
            chain_id: Chain ID
            token_address: Token contract address
            token_info: Token information to cache
        """
        cache_key = f"{chain_id}:{token_address.lower()}"
        self.token_cache[cache_key] = token_info
        
        logger.debug(f"Updated token cache for {cache_key}")


# =============================================================================
# BATCH ANALYSIS FUNCTIONS
# =============================================================================

async def analyze_transaction_batch(
    analyzer: MempoolAnalyzer,
    transactions: List[MempoolTransaction]
) -> List[TransactionAnalysis]:
    """
    Analyze a batch of transactions concurrently.
    
    Args:
        analyzer: MempoolAnalyzer instance
        transactions: List of transactions to analyze
        
    Returns:
        List of analysis results
    """
    if not transactions:
        return []
    
    start_time = time.perf_counter()
    
    # Create analysis tasks
    tasks = [analyzer.analyze_transaction(tx) for tx in transactions]
    
    # Execute concurrently with timeout
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=5.0  # 5 second timeout for batch
        )
        
        # Filter out exceptions and log errors
        analyses = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error analyzing transaction {transactions[i].hash}: {result}")
            else:
                analyses.append(result)
        
        batch_time = (time.perf_counter() - start_time) * 1000
        logger.debug(f"Analyzed batch of {len(transactions)} transactions in {batch_time:.2f}ms")
        
        return analyses
        
    except asyncio.TimeoutError:
        logger.warning(f"Timeout analyzing batch of {len(transactions)} transactions")
        return []


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================

async def create_mempool_analyzer(provider_manager, chain_configs: Dict[int, Any]) -> MempoolAnalyzer:
    """
    Factory function to create a properly configured mempool analyzer.
    
    Args:
        provider_manager: Provider manager instance
        chain_configs: Chain configuration mapping
        
    Returns:
        Configured MempoolAnalyzer instance
    """
    return MempoolAnalyzer(provider_manager, chain_configs)