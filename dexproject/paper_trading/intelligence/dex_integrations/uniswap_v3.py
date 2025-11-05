"""
Uniswap V3 DEX Integration for Real Price Queries

This module implements the Uniswap V3 integration for Phase 2 multi-DEX price comparison.
It queries real Uniswap V3 pools on-chain for accurate price and liquidity data.

Phase 2: Multi-DEX Price Comparison
File: paper_trading/intelligence/dex_integrations/uniswap_v3.py

PROPERLY FIXED: Correct price calculation with proper token identification
"""

import logging
import time
from decimal import Decimal
from typing import Optional, Dict, Any, List, Tuple

from django.utils import timezone

# Import base DEX class
from .base_dex import BaseDEX, DEXPrice

# Import Uniswap V3 constants
from paper_trading.intelligence.analyzers.constants import (
    UNISWAP_V3_FACTORY,
    FACTORY_ABI,
    POOL_ABI,
    FEE_TIERS
)

# Import defaults
from paper_trading.defaults import DEXComparisonDefaults

logger = logging.getLogger(__name__)


# =============================================================================
# ERC20 ABI FOR TOKEN QUERIES
# =============================================================================

# Minimal ERC20 ABI for getting balances and decimals
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    }
]


# =============================================================================
# UNISWAP V3 DEX INTEGRATION
# =============================================================================

class UniswapV3DEX(BaseDEX):
    """
    Uniswap V3 integration for real price and liquidity queries.
    
    Features:
    - Queries real Uniswap V3 pools on-chain
    - Searches across all fee tiers (0.05%, 0.3%, 1%)
    - Calculates prices from actual pool token balances (balanceOf)
    - Returns liquidity data for risk assessment
    
    PROPERLY FIXED: Correct token identification and price calculation
    """
    
    def __init__(
        self,
        chain_id: int = 8453,
        cache_ttl_seconds: int = 30
    ):
        """
        Initialize Uniswap V3 DEX integration.
        
        Args:
            chain_id: Blockchain network ID
            cache_ttl_seconds: Cache TTL for price quotes
        """
        super().__init__(
            dex_name='uniswap_v3',
            chain_id=chain_id,
            cache_ttl_seconds=cache_ttl_seconds
        )
        
        # Uniswap V3 specific configuration
        self.factory_address = UNISWAP_V3_FACTORY.get(chain_id)
        self.fee_tiers = DEXComparisonDefaults.UNISWAP_V3_FEE_TIERS
        
        # Base tokens for price pairs with their known USD prices
        self.base_tokens = self._get_base_tokens(chain_id)
        
        self.logger.info(
            f"[UNISWAP V3] Initialized for chain {chain_id}, "
            f"Factory: {self.factory_address[:10] if self.factory_address else 'N/A'}..."
        )
    
    def _get_base_tokens(self, chain_id: int) -> List[Dict[str, Any]]:
        """
        Get base tokens for this chain with their USD prices.
        
        Args:
            chain_id: Blockchain network ID
            
        Returns:
            List of base token dictionaries with prices
        """
        base_tokens_by_chain = {
            84532: [  # Base Sepolia (testnet)
                {
                    'symbol': 'WETH',
                    'address': '0x4200000000000000000000000000000000000006',
                    'usd_price': Decimal('3400')  # Approximate
                },
                {
                    'symbol': 'USDC',
                    'address': '0x036CbD53842c5426634e7929541eC2318f3dCF7e',
                    'usd_price': Decimal('1.00')
                }
            ],
            8453: [  # Base Mainnet
                {
                    'symbol': 'WETH',
                    'address': '0x4200000000000000000000000000000000000006',
                    'usd_price': Decimal('3400')  # Updated regularly
                },
                {
                    'symbol': 'USDC',
                    'address': '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913',
                    'usd_price': Decimal('1.00')
                }
            ],
            1: [  # Ethereum Mainnet
                {
                    'symbol': 'WETH',
                    'address': '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',
                    'usd_price': Decimal('3400')
                },
                {
                    'symbol': 'USDC',
                    'address': '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48',
                    'usd_price': Decimal('1.00')
                }
            ]
        }
        
        return base_tokens_by_chain.get(chain_id, [])
    
    # =========================================================================
    # MAIN INTERFACE METHODS
    # =========================================================================
    
    async def get_token_price(
        self,
        token_address: str,
        token_symbol: str
    ) -> DEXPrice:
        """
        Get token price from Uniswap V3 pools.
        
        This method:
        1. Checks cache first
        2. Finds best pool across fee tiers
        3. Queries pool for actual token balances (balanceOf)
        4. Calculates price from reserves accounting for decimals
        5. Validates price is reasonable
        6. Caches result
        
        Args:
            token_address: Token contract address
            token_symbol: Token symbol
            
        Returns:
            DEXPrice with price and metadata
        """
        start_time = time.time()
        self.total_queries += 1
        
        # Check if DEX is disabled by circuit breaker
        if self._check_if_disabled():
            return DEXPrice(
                dex_name=self.dex_name,
                token_address=token_address,
                token_symbol=token_symbol,
                success=False,
                error_message="DEX temporarily disabled due to consecutive failures"
            )
        
        # Check cache first
        cached_price = self._get_cached_price(token_address)
        if cached_price:
            self.logger.debug(f"[UNISWAP V3] Cache hit for {token_symbol}")
            return cached_price
        
        try:
            # Ensure Web3 client is initialized
            web3_client = await self._ensure_web3_client()
            if not web3_client:
                raise Exception("Web3 client unavailable")
            
            # Find best pool for this token
            pool_info = await self._find_best_pool(
                web3_client,
                token_address,
                token_symbol
            )
            
            if not pool_info:
                self._record_failure()
                return DEXPrice(
                    dex_name=self.dex_name,
                    token_address=token_address,
                    token_symbol=token_symbol,
                    success=False,
                    error_message="No pool found with sufficient liquidity"
                )
            
            # Validate price is reasonable
            price_usd = pool_info['price_usd']
            if not self._validate_price(token_symbol, price_usd):
                self._record_failure()
                return DEXPrice(
                    dex_name=self.dex_name,
                    token_address=token_address,
                    token_symbol=token_symbol,
                    success=False,
                    error_message=f"Price validation failed: ${price_usd:.4f}"
                )
            
            # Create successful result
            query_time_ms = (time.time() - start_time) * 1000
            
            price_obj = DEXPrice(
                dex_name=self.dex_name,
                token_address=token_address,
                token_symbol=token_symbol,
                price_usd=price_usd,
                liquidity_usd=pool_info['liquidity_usd'],
                success=True,
                response_time_ms=query_time_ms
            )
            
            # Cache and log
            self._cache_price(price_obj)
            self._record_success()
            
            self.logger.info(
                f"[UNISWAP V3] {token_symbol} price: ${price_usd:.4f}, "
                f"Liquidity: ${pool_info['liquidity_usd']:,.0f}, "
                f"Response: {query_time_ms:.0f}ms"
            )
            
            return price_obj
        
        except Exception as e:
            self.logger.error(
                f"[UNISWAP V3] Error fetching price for {token_symbol}: {e}",
                exc_info=True
            )
            self._record_failure()
            
            return DEXPrice(
                dex_name=self.dex_name,
                token_address=token_address,
                token_symbol=token_symbol,
                success=False,
                error_message=str(e),
                response_time_ms=(time.time() - start_time) * 1000
            )
    
    async def get_liquidity(
        self,
        token_address: str
    ) -> Optional[Decimal]:
        """
        Get available liquidity for token.
        
        Args:
            token_address: Token contract address
            
        Returns:
            Liquidity in USD
        """
        # Get price (which includes liquidity)
        price_obj = await self.get_token_price(token_address, "UNKNOWN")
        return price_obj.liquidity_usd if price_obj.success else None
    
    async def is_available(self) -> bool:
        """Check if Uniswap V3 is available."""
        # Try to initialize Web3 client
        web3_client = await self._ensure_web3_client()
        return web3_client is not None
    
    # =========================================================================
    # UNISWAP V3 SPECIFIC METHODS
    # =========================================================================
    
    async def _find_best_pool(
        self,
        web3_client: Any,
        token_address: str,
        token_symbol: str
    ) -> Optional[Dict[str, Any]]:
        """
        Find best Uniswap V3 pool for token across all fee tiers.
        
        Searches for pools pairing with WETH and USDC across all
        configured fee tiers and returns the one with highest liquidity.
        
        Args:
            web3_client: Connected Web3 client
            token_address: Token contract address
            token_symbol: Token symbol
            
        Returns:
            Dictionary with pool info or None if not found
        """
        try:
            # Get factory contract
            factory_contract = web3_client.web3.eth.contract(
                address=web3_client.web3.to_checksum_address(self.factory_address),
                abi=FACTORY_ABI
            )
            
            best_pool = None
            best_liquidity = Decimal('0')
            
            # Check each base token
            for base_token in self.base_tokens:
                # Check each fee tier
                for fee_tier in self.fee_tiers:
                    try:
                        # Query factory for pool address
                        pool_address = factory_contract.functions.getPool(
                            web3_client.web3.to_checksum_address(token_address),
                            web3_client.web3.to_checksum_address(base_token['address']),
                            fee_tier
                        ).call()
                        
                        # Check if pool exists
                        if pool_address == '0x0000000000000000000000000000000000000000':
                            continue
                        
                        # Query pool for liquidity and price (FIXED METHOD)
                        pool_data = await self._query_pool_data(
                            web3_client,
                            pool_address,
                            token_address,
                            base_token,
                            fee_tier
                        )
                        
                        if pool_data and pool_data['liquidity_usd'] > best_liquidity:
                            best_liquidity = pool_data['liquidity_usd']
                            best_pool = pool_data
                    
                    except Exception as e:
                        self.logger.debug(
                            f"[UNISWAP V3] No pool found for {token_symbol}-"
                            f"{base_token['symbol']} at {fee_tier} fee tier"
                        )
                        continue
            
            if best_pool:
                self.logger.info(
                    f"[UNISWAP V3] Found pool for {token_symbol} with "
                    f"${best_liquidity:,.0f} liquidity"
                )
            
            return best_pool
        
        except Exception as e:
            self.logger.error(
                f"[UNISWAP V3] Error finding pool for {token_symbol}: {e}",
                exc_info=True
            )
            return None
    
    async def _query_pool_data(
        self,
        web3_client: Any,
        pool_address: str,
        token_address: str,
        base_token: Dict[str, Any],
        fee_tier: int
    ) -> Optional[Dict[str, Any]]:
        """
        Query Uniswap V3 pool for price and liquidity data.
        
        PROPERLY FIXED: Correct token identification and price calculation.
        
        This method:
        1. Gets token0 and token1 from the pool
        2. Identifies which is our token and which is the base token
        3. Gets actual balances using balanceOf
        4. Calculates price correctly based on which token is which
        5. Validates the result
        
        Args:
            web3_client: Connected Web3 client
            pool_address: Pool contract address
            token_address: Token being priced
            base_token: Base token info with USD price
            fee_tier: Pool fee tier
            
        Returns:
            Dictionary with price and liquidity data
        """
        try:
            # Get pool contract
            pool_contract = web3_client.web3.eth.contract(
                address=web3_client.web3.to_checksum_address(pool_address),
                abi=POOL_ABI
            )
            
            # Get token0 and token1 from pool
            token0_address = pool_contract.functions.token0().call()
            token1_address = pool_contract.functions.token1().call()
            
            # Normalize addresses for comparison
            token_address_lower = token_address.lower()
            base_token_address_lower = base_token['address'].lower()
            token0_lower = token0_address.lower()
            token1_lower = token1_address.lower()
            
            # Identify which token is which
            if token0_lower == token_address_lower and token1_lower == base_token_address_lower:
                # Our token is token0, base is token1
                our_token_address = token0_address
                base_token_address = token1_address
                our_is_token0 = True
            elif token1_lower == token_address_lower and token0_lower == base_token_address_lower:
                # Our token is token1, base is token0
                our_token_address = token1_address
                base_token_address = token0_address
                our_is_token0 = False
            else:
                # Pool doesn't match our token and base token
                self.logger.debug(
                    f"[UNISWAP V3] Pool {pool_address[:10]}... doesn't match "
                    f"expected token pair"
                )
                return None
            
            # Create ERC20 contracts
            our_token_contract = web3_client.web3.eth.contract(
                address=web3_client.web3.to_checksum_address(our_token_address),
                abi=ERC20_ABI
            )
            base_token_contract = web3_client.web3.eth.contract(
                address=web3_client.web3.to_checksum_address(base_token_address),
                abi=ERC20_ABI
            )
            
            # Get token decimals
            our_token_decimals = our_token_contract.functions.decimals().call()
            base_token_decimals = base_token_contract.functions.decimals().call()
            
            # Get actual token balances in the pool
            pool_address_checksum = web3_client.web3.to_checksum_address(pool_address)
            our_token_balance_raw = our_token_contract.functions.balanceOf(pool_address_checksum).call()
            base_token_balance_raw = base_token_contract.functions.balanceOf(pool_address_checksum).call()
            
            # Convert to actual amounts (accounting for decimals)
            our_token_amount = Decimal(our_token_balance_raw) / Decimal(10 ** our_token_decimals)
            base_token_amount = Decimal(base_token_balance_raw) / Decimal(10 ** base_token_decimals)
            
            # Safety check: ensure we have liquidity
            if our_token_amount == 0 or base_token_amount == 0:
                self.logger.debug(
                    f"[UNISWAP V3] Pool {pool_address[:10]}... has zero liquidity"
                )
                return None
            
            # Calculate price: How many base tokens per our token?
            # Price = base_token_amount / our_token_amount
            price_in_base_token = base_token_amount / our_token_amount
            
            # Convert to USD using base token's USD price
            base_token_usd_price = base_token['usd_price']
            price_usd = price_in_base_token * base_token_usd_price
            
            # Calculate total liquidity in USD
            # Total pool value = (base_token_amount * base_token_usd_price) * 2
            # We multiply by 2 because the pool has equal value in both tokens
            liquidity_usd = base_token_amount * base_token_usd_price * Decimal('2')
            
            self.logger.debug(
                f"[UNISWAP V3] Pool {pool_address[:10]}... | "
                f"Our token: {our_token_amount:.4f}, "
                f"Base token ({base_token['symbol']}): {base_token_amount:.4f}, "
                f"Price: ${price_usd:.4f}, "
                f"Liquidity: ${liquidity_usd:,.0f}"
            )
            
            return {
                'pool_address': pool_address,
                'fee_tier': fee_tier,
                'base_token': base_token['symbol'],
                'price_usd': price_usd,
                'liquidity_usd': liquidity_usd,
                'our_token_amount': our_token_amount,
                'base_token_amount': base_token_amount
            }
        
        except Exception as e:
            self.logger.debug(
                f"[UNISWAP V3] Error querying pool {pool_address[:10]}...: {e}"
            )
            return None
    
    def _validate_price(self, token_symbol: str, price_usd: Decimal) -> bool:
        """
        Validate that price is reasonable.
        
        Args:
            token_symbol: Token symbol
            price_usd: Calculated price in USD
            
        Returns:
            True if price is valid, False otherwise
        """
        # Stablecoins should be near $1
        stablecoins = ['USDC', 'USDT', 'DAI', 'FRAX', 'LUSD', 'BUSD']
        
        if token_symbol in stablecoins:
            # Stablecoins should be within 2% of $1
            if not (Decimal('0.98') <= price_usd <= Decimal('1.02')):
                self.logger.error(
                    f"[UNISWAP V3] ❌ REJECTED - Invalid stablecoin price: "
                    f"{token_symbol} at ${price_usd:.4f} (expected ~$1.00)"
                )
                return False
        
        # General sanity checks
        if price_usd <= 0:
            self.logger.error(
                f"[UNISWAP V3] ❌ REJECTED - Non-positive price: "
                f"{token_symbol} at ${price_usd:.4f}"
            )
            return False
        
        if price_usd > Decimal('1000000'):
            self.logger.error(
                f"[UNISWAP V3] ❌ REJECTED - Unrealistic price: "
                f"{token_symbol} at ${price_usd:.4f}"
            )
            return False
        
        return True
