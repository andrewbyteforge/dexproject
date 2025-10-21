"""
Real Price Service Integration for Paper Trading Bot

This module bridges the paper trading bot with real blockchain price data,
replacing mock/hardcoded prices with actual market data from multiple sources.

Features:
- Real-time price fetching from Alchemy, CoinGecko, and DEX routers
- Automatic fallback to mock data on API failures
- Token list management with price updates
- Async price fetching with sync wrapper for bot compatibility
- Comprehensive error handling and logging

File: dexproject/paper_trading/bot/price_service_integration.py
"""

import logging
import asyncio
from decimal import Decimal
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from asgiref.sync import async_to_sync

from django.core.cache import cache
from django.utils import timezone

# Import the real price feed service we created earlier
from paper_trading.services.price_feed_service import (
    PriceFeedService,
    get_default_price_feed_service,
    get_token_price_simple
)

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

# Default token list for paper trading (Base Sepolia testnet addresses)
DEFAULT_TOKEN_LIST = [
    {
        'symbol': 'WETH',
        'address': '0x4200000000000000000000000000000000000006',  # Base WETH
        'price': Decimal('2500'),  # Fallback mock price
        'decimals': 18,
        'coingecko_id': 'ethereum'
    },
    {
        'symbol': 'USDC',
        'address': '0x036CbD53842c5426634e7929541eC2318f3dCF7e',  # Base Sepolia USDC
        'price': Decimal('1.00'),  # Stablecoin
        'decimals': 6,
        'coingecko_id': 'usd-coin'
    },
    {
        'symbol': 'DAI',
        'address': '0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb',  # Base Sepolia DAI
        'price': Decimal('1.00'),  # Stablecoin
        'decimals': 18,
        'coingecko_id': 'dai'
    },
    {
        'symbol': 'WBTC',
        'address': '0x0000000000000000000000000000000000000000',  # Placeholder
        'price': Decimal('45000'),  # Fallback mock price
        'decimals': 8,
        'coingecko_id': 'wrapped-bitcoin'
    },
    {
        'symbol': 'UNI',
        'address': '0x0000000000000000000000000000000000000001',  # Placeholder
        'price': Decimal('6.50'),  # Fallback mock price
        'decimals': 18,
        'coingecko_id': 'uniswap'
    },
    {
        'symbol': 'AAVE',
        'address': '0x0000000000000000000000000000000000000002',  # Placeholder
        'price': Decimal('95'),  # Fallback mock price
        'decimals': 18,
        'coingecko_id': 'aave'
    },
    {
        'symbol': 'LINK',
        'address': '0x0000000000000000000000000000000000000003',  # Placeholder
        'price': Decimal('15'),  # Fallback mock price
        'decimals': 18,
        'coingecko_id': 'chainlink'
    },
    {
        'symbol': 'MATIC',
        'address': '0x0000000000000000000000000000000000000004',  # Placeholder
        'price': Decimal('0.85'),  # Fallback mock price
        'decimals': 18,
        'coingecko_id': 'matic-network'
    },
    {
        'symbol': 'ARB',
        'address': '0x0000000000000000000000000000000000000005',  # Placeholder
        'price': Decimal('1.20'),  # Fallback mock price
        'decimals': 18,
        'coingecko_id': 'arbitrum'
    }
]

# Price update interval (seconds)
PRICE_UPDATE_INTERVAL = 5  # Update prices every 5 seconds

# Mock price simulation settings
MOCK_PRICE_VOLATILITY = 0.05  # +/- 5% max price change when simulating


# =============================================================================
# REAL PRICE MANAGER CLASS
# =============================================================================

class RealPriceManager:
    """
    Manages real-time price fetching for paper trading bot.
    
    This class coordinates between real price feeds and mock data,
    providing a seamless interface for the bot regardless of data source.
    
    Features:
    - Automatic real price fetching from multiple sources
    - Fallback to mock prices on API failures
    - Price history tracking
    - Async/sync compatibility
    - Error recovery
    
    Example usage:
        manager = RealPriceManager(use_real_prices=True, chain_id=84532)
        await manager.initialize()
        
        # Update all token prices
        await manager.update_all_prices()
        
        # Get token list with current prices
        tokens = manager.get_token_list()
    """
    
    def __init__(
        self,
        use_real_prices: bool = True,
        chain_id: int = 84532,  # Base Sepolia default
        token_list: Optional[List[Dict[str, Any]]] = None
    ):
        """
        Initialize the Real Price Manager.
        
        Args:
            use_real_prices: If True, fetch real prices; if False, use mock simulation
            chain_id: Blockchain network ID for price fetching
            token_list: Custom token list (uses DEFAULT_TOKEN_LIST if None)
        """
        self.use_real_prices = use_real_prices
        self.chain_id = chain_id
        self.token_list = token_list or self._clone_token_list(DEFAULT_TOKEN_LIST)
        
        # Price feed service (initialized lazily)
        self._price_service: Optional[PriceFeedService] = None
        
        # Price update tracking
        self.last_update_time: Optional[datetime] = None
        self.update_count = 0
        self.failed_updates = 0
        
        # Price history for each token (last 100 prices)
        self.price_history: Dict[str, List[Decimal]] = {}
        
        logger.info(
            f"[PRICE MANAGER] Initialized: "
            f"Mode={'REAL' if use_real_prices else 'MOCK'}, "
            f"Chain={chain_id}, Tokens={len(self.token_list)}"
        )
    
    def _clone_token_list(self, original: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create a deep copy of the token list to avoid mutation."""
        return [token.copy() for token in original]
    
    async def initialize(self, web3_client=None) -> bool:
        """
        Initialize the price manager and price feed service.
        
        Args:
            web3_client: Optional Web3Client for DEX quotes
        """
        try:
            if self.use_real_prices:
                # Initialize price feed service with DEX quote support
                self._price_service = PriceFeedService(
                    chain_id=self.chain_id,
                    web3_client=web3_client  # ✅ Enable DEX quotes
                )
                logger.info(
                    f"[PRICE MANAGER] Real price service initialized "
                    f"(DEX quotes: {'ENABLED' if web3_client else 'DISABLED'})"
                )
    
    async def close(self):
        """Close the price feed service and cleanup resources."""
        try:
            if self._price_service:
                await self._price_service.close()
                logger.info("[PRICE MANAGER] Price service closed")
        except Exception as e:
            logger.error(f"[PRICE MANAGER] Error during cleanup: {e}")
    
    # =========================================================================
    # PRICE UPDATE METHODS
    # =========================================================================
    
    async def update_all_prices(self) -> Dict[str, bool]:
        """
        Update prices for all tokens in the token list.
        
        Returns:
            Dictionary mapping token symbols to update success status
        """
        results = {}
        
        try:
            logger.debug(
                f"[PRICE MANAGER] Updating prices for {len(self.token_list)} tokens..."
            )
            
            for token in self.token_list:
                symbol = token['symbol']
                
                if self.use_real_prices:
                    success = await self._update_token_price_real(token)
                else:
                    success = self._update_token_price_mock(token)
                
                results[symbol] = success
            
            # Update tracking
            self.last_update_time = timezone.now()
            self.update_count += 1
            
            # Count successes
            success_count = sum(1 for success in results.values() if success)
            
            logger.info(
                f"[PRICE MANAGER] Updated {success_count}/{len(self.token_list)} "
                f"token prices (Mode: {'REAL' if self.use_real_prices else 'MOCK'})"
            )
            
            return results
            
        except Exception as e:
            logger.error(f"[PRICE MANAGER] Failed to update prices: {e}", exc_info=True)
            self.failed_updates += 1
            return results
    
    async def _update_token_price_real(self, token: Dict[str, Any]) -> bool:
        """
        Update a single token price from real data sources.
        
        Args:
            token: Token dictionary to update
        
        Returns:
            True if update successful
        """
        try:
            if not self._price_service:
                logger.warning("[PRICE MANAGER] Price service not initialized")
                return False
            
            symbol = token['symbol']
            address = token['address']
            
            # Fetch real price
            real_price = await self._price_service.get_token_price(
                token_address=address,
                token_symbol=symbol
            )
            
            if real_price is not None and real_price > 0:
                # Update token price
                old_price = token['price']
                token['price'] = real_price
                
                # Update price history
                if symbol not in self.price_history:
                    self.price_history[symbol] = []
                
                self.price_history[symbol].append(real_price)
                
                # Keep only last 100 prices
                if len(self.price_history[symbol]) > 100:
                    self.price_history[symbol].pop(0)
                
                # Log significant changes
                if old_price > 0:
                    change_pct = ((real_price - old_price) / old_price) * 100
                    if abs(change_pct) > 1:  # Log if >1% change
                        logger.info(
                            f"[PRICE UPDATE] {symbol}: "
                            f"${old_price:.2f} → ${real_price:.2f} "
                            f"({change_pct:+.2f}%)"
                        )
                
                return True
            else:
                logger.warning(
                    f"[PRICE MANAGER] Failed to fetch real price for {symbol}, "
                    f"keeping last known price: ${token['price']:.2f}"
                )
                return False
                
        except Exception as e:
            logger.error(
                f"[PRICE MANAGER] Error updating {token['symbol']}: {e}",
                exc_info=True
            )
            return False
    
    def _update_token_price_mock(self, token: Dict[str, Any]) -> bool:
        """
        Update a single token price using mock price simulation.
        
        Simulates realistic price movements with volatility.
        
        Args:
            token: Token dictionary to update
        
        Returns:
            True (always succeeds for mock data)
        """
        try:
            import random
            
            symbol = token['symbol']
            old_price = token['price']
            
            # Stablecoins don't move
            if symbol in ['USDC', 'USDT', 'DAI']:
                return True
            
            # Simulate price movement
            change = Decimal(str(random.uniform(
                -MOCK_PRICE_VOLATILITY,
                MOCK_PRICE_VOLATILITY
            )))
            
            new_price = old_price * (Decimal('1') + change)
            token['price'] = new_price
            
            # Update price history
            if symbol not in self.price_history:
                self.price_history[symbol] = []
            
            self.price_history[symbol].append(new_price)
            
            # Keep only last 100 prices
            if len(self.price_history[symbol]) > 100:
                self.price_history[symbol].pop(0)
            
            # Log significant changes
            if abs(change) > Decimal('0.02'):  # >2% change
                logger.debug(
                    f"[MOCK PRICE] {symbol}: "
                    f"${old_price:.2f} → ${new_price:.2f} "
                    f"({change*100:+.2f}%)"
                )
            
            return True
            
        except Exception as e:
            logger.error(f"[PRICE MANAGER] Mock update error for {token['symbol']}: {e}")
            return False
    
    # =========================================================================
    # GETTER METHODS
    # =========================================================================
    
    def get_token_list(self) -> List[Dict[str, Any]]:
        """
        Get the current token list with latest prices.
        
        Returns:
            List of token dictionaries with current prices
        """
        return self.token_list
    
    def get_token_price(self, symbol: str) -> Optional[Decimal]:
        """
        Get the current price for a specific token.
        
        Args:
            symbol: Token symbol (e.g., 'WETH')
        
        Returns:
            Current price or None if token not found
        """
        for token in self.token_list:
            if token['symbol'] == symbol:
                return token['price']
        
        logger.warning(f"[PRICE MANAGER] Token {symbol} not found in token list")
        return None
    
    def get_price_history(self, symbol: str, limit: int = 100) -> List[Decimal]:
        """
        Get price history for a token.
        
        Args:
            symbol: Token symbol
            limit: Maximum number of historical prices to return
        
        Returns:
            List of historical prices (newest last)
        """
        history = self.price_history.get(symbol, [])
        return history[-limit:] if history else []
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get price manager statistics.
        
        Returns:
            Dictionary with update statistics
        """
        return {
            'mode': 'REAL' if self.use_real_prices else 'MOCK',
            'chain_id': self.chain_id,
            'total_tokens': len(self.token_list),
            'update_count': self.update_count,
            'failed_updates': self.failed_updates,
            'last_update': self.last_update_time.isoformat() if self.last_update_time else None,
            'uptime_seconds': (
                (timezone.now() - self.last_update_time).total_seconds()
                if self.last_update_time else 0
            )
        }


# =============================================================================
# SYNCHRONOUS WRAPPER FUNCTIONS (for bot compatibility)
# =============================================================================

def create_price_manager(
    use_real_prices: bool = True,
    chain_id: int = 84532,
    token_list: Optional[List[Dict[str, Any]]] = None
) -> RealPriceManager:
    """
    Create and initialize a price manager (sync wrapper).
    
    Args:
        use_real_prices: If True, fetch real prices
        chain_id: Blockchain network ID
        token_list: Custom token list (optional)
    
    Returns:
        Initialized RealPriceManager instance
    """
    manager = RealPriceManager(
        use_real_prices=use_real_prices,
        chain_id=chain_id,
        token_list=token_list
    )
    
    # Initialize synchronously
    async_to_sync(manager.initialize)()
    
    return manager


def update_prices_sync(manager: RealPriceManager) -> Dict[str, bool]:
    """
    Update all prices synchronously (for use in bot's tick loop).
    
    Args:
        manager: RealPriceManager instance
    
    Returns:
        Dictionary of update results
    """
    return async_to_sync(manager.update_all_prices)()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def should_update_prices(last_update: Optional[datetime]) -> bool:
    """
    Check if prices should be updated based on time interval.
    
    Args:
        last_update: Timestamp of last price update
    
    Returns:
        True if prices should be updated
    """
    if last_update is None:
        return True
    
    elapsed = (timezone.now() - last_update).total_seconds()
    return elapsed >= PRICE_UPDATE_INTERVAL


def get_token_by_symbol(
    token_list: List[Dict[str, Any]],
    symbol: str
) -> Optional[Dict[str, Any]]:
    """
    Find a token in the list by symbol.
    
    Args:
        token_list: List of token dictionaries
        symbol: Token symbol to find
    
    Returns:
        Token dictionary or None if not found
    """
    for token in token_list:
        if token['symbol'].upper() == symbol.upper():
            return token
    return None


def get_token_by_address(
    token_list: List[Dict[str, Any]],
    address: str
) -> Optional[Dict[str, Any]]:
    """
    Find a token in the list by contract address.
    
    Args:
        token_list: List of token dictionaries
        address: Token contract address
    
    Returns:
        Token dictionary or None if not found
    """
    address_lower = address.lower()
    for token in token_list:
        if token['address'].lower() == address_lower:
            return token
    return None