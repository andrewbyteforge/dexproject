"""
Modular Market Analyzers for Paper Trading Intelligence

Separate analyzer modules for different aspects of market analysis,
making the system easier to maintain and extend.

File: dexproject/paper_trading/intelligence/analyzers/__init__.py
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, Optional, cast, List, TYPE_CHECKING
from abc import ABC, abstractmethod

# Import Web3 infrastructure for real data (optional)
if TYPE_CHECKING:
    # Only import for type checking, not at runtime
    from engine.web3_client import Web3Client

try:
    from engine.config import config as engine_config
    from engine.web3_client import Web3Client as Web3ClientRuntime
    WEB3_AVAILABLE = True
except ImportError:
    engine_config = None  # type: ignore
    Web3ClientRuntime = None  # type: ignore
    WEB3_AVAILABLE = False

logger = logging.getLogger(__name__)


# =============================================================================
# UNISWAP V3 CONSTANTS
# =============================================================================

# Uniswap V3 Factory addresses by chain
UNISWAP_V3_FACTORY = {
    84532: '0x4752ba5dbc23f44d87826276bf6fd6b1c372ad24',  # Base Sepolia
    11155111: '0x0227628f3F023bb0B980b67D528571c95c6DaC1c',  # Ethereum Sepolia  
    8453: '0x33128a8fC17869897dcE68Ed026d694621f6FDfD',  # Base Mainnet
    1: '0x1F98431c8aD98523631AE4a59f267346ea31F984',  # Ethereum Mainnet
}

# Uniswap V3 Factory ABI (minimal - just what we need)
FACTORY_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenA", "type": "address"},
            {"internalType": "address", "name": "tokenB", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"}
        ],
        "name": "getPool",
        "outputs": [{"internalType": "address", "name": "pool", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    }
]

# Uniswap V3 Pool ABI (minimal)
POOL_ABI = [
    {
        "inputs": [],
        "name": "liquidity",
        "outputs": [{"internalType": "uint128", "name": "", "type": "uint128"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
            {"internalType": "int24", "name": "tick", "type": "int24"},
            {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"},
            {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"},
            {"internalType": "bool", "name": "unlocked", "type": "bool"}
        ],
        "stateMutability": "view",
        "type": "function"
    }
]

# Common fee tiers for Uniswap V3
FEE_TIERS = [500, 3000, 10000]  # 0.05%, 0.3%, 1%


# =============================================================================
# BASE ANALYZER CLASS
# =============================================================================

class BaseAnalyzer(ABC):
    """Base class for all market analyzers."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize analyzer with optional configuration.
        
        Args:
            config: Optional configuration dictionary
        """
        self.config = config or {}
        self.logger = logging.getLogger(f'{__name__}.{self.__class__.__name__}')
        # Use object type to avoid type issues with conditional imports
        self._web3_client: Optional[object] = None
        self._web3_initialized = False
    
    async def _ensure_web3_client(self, chain_id: int = 84532) -> Optional[Web3Client]:
        """
        Ensure Web3 client is initialized.
        
        Args:
            chain_id: Chain ID for Web3 connection
            
        Returns:
            Web3Client instance or None if unavailable
        """
        if not WEB3_AVAILABLE:
            self.logger.warning("Web3 infrastructure not available")
            return None
        
        if self._web3_initialized and self._web3_client:
            # Type guard: we know it's Web3Client at this point
            return cast(Web3Client, self._web3_client)
        
        try:
            # Type guard: engine_config is not None when WEB3_AVAILABLE is True
            assert engine_config is not None, "engine_config should be available"
            
            # Get chain config
            chain_config = engine_config.get_chain_config(chain_id)
            if not chain_config:
                self.logger.error(f"No config for chain {chain_id}")
                return None
            
            # Type guard: Web3Client is not None when WEB3_AVAILABLE is True
            assert Web3Client is not None, "Web3Client should be available"
            
            # Initialize Web3 client
            self._web3_client = Web3Client(chain_config)
            
            # Type guard for mypy/pylance
            client = cast(Web3Client, self._web3_client)
            await client.connect()
            
            if not client.is_connected:
                self.logger.error(f"Failed to connect to chain {chain_id}")
                return None
            
            self._web3_initialized = True
            self.logger.info(f"[WEB3] Connected to chain {chain_id}")
            return client
            
        except Exception as e:
            self.logger.error(f"Error initializing Web3 client: {e}")
            return None
    
    @abstractmethod
    async def analyze(self, token_address: str, **kwargs) -> Dict[str, Any]:
        """
        Perform analysis on the given token.
        
        Args:
            token_address: Token to analyze
            **kwargs: Additional parameters
            
        Returns:
            Analysis results dictionary
        """
        pass


# =============================================================================
# REAL GAS ANALYZER
# =============================================================================

class RealGasAnalyzer(BaseAnalyzer):
    """
    Analyzes network gas conditions using REAL blockchain data.
    
    Replaces simulated gas prices with actual blockchain queries.
    """
    
    async def analyze(self, token_address: str, **kwargs) -> Dict[str, Any]:
        """
        Analyze REAL gas conditions from blockchain.
        
        Args:
            token_address: Token address to analyze
            **kwargs: Additional parameters (chain_id)
        
        Returns:
            Dict containing:
            - current_gas_gwei: REAL current gas price
            - network_congestion: Congestion level (0-100)
            - recommended_gas_gwei: Suggested gas price
            - gas_strategy: Recommended strategy
            - estimated_cost_usd: Estimated transaction cost
            - data_quality: Quality rating of the data
        """
        try:
            chain_id = kwargs.get('chain_id', 84532)
            
            # Try to get REAL gas price from blockchain
            web3_client = await self._ensure_web3_client(chain_id)
            
            if web3_client is not None:
                # Type guard: at this point we know it's a Web3ClientType
                client = cast(Web3Client, web3_client)
                
                if client.is_connected:
                    # ✅ REAL DATA: Query actual blockchain
                    gas_price_wei = await client.web3.eth.gas_price  # type: ignore[attr-defined]
                    current_gas_gwei = Decimal(gas_price_wei) / Decimal(10**9)
                    data_quality = "EXCELLENT"
                    self.logger.info(
                        f"[GAS] Real data: {current_gas_gwei:.2f} gwei from chain {chain_id}"
                    )
                else:
                    # Fallback to conservative estimates
                    current_gas_gwei = self._get_fallback_gas_price(chain_id)
                    data_quality = "FALLBACK"
                    self.logger.warning(
                        f"[GAS] Using fallback: {current_gas_gwei:.2f} gwei for chain {chain_id}"
                    )
            else:
                # Fallback to conservative estimates
                current_gas_gwei = self._get_fallback_gas_price(chain_id)
                data_quality = "FALLBACK"
                self.logger.warning(
                    f"[GAS] Using fallback: {current_gas_gwei:.2f} gwei for chain {chain_id}"
                )
            
            # Calculate congestion based on gas price
            network_congestion = self._calculate_congestion(current_gas_gwei, chain_id)
            
            # Recommend gas price strategy
            recommended_gas_gwei = current_gas_gwei * Decimal('1.1')  # 10% buffer
            
            # Determine strategy
            gas_strategy = self._determine_gas_strategy(network_congestion)
            
            # Estimate cost (assumes ~200k gas for swap)
            estimated_cost_usd = self._estimate_cost_usd(
                current_gas_gwei,
                gas_units=200000
            )
            
            result = {
                'current_gas_gwei': float(current_gas_gwei),
                'network_congestion': network_congestion,
                'recommended_gas_gwei': float(recommended_gas_gwei),
                'gas_strategy': gas_strategy,
                'estimated_cost_usd': float(estimated_cost_usd),
                'data_quality': data_quality,
                'chain_id': chain_id
            }
            
            self.logger.debug(
                f"[GAS] Analysis complete: {current_gas_gwei:.2f} gwei, "
                f"congestion={network_congestion:.1f}%, quality={data_quality}"
            )
            return result
            
        except Exception as e:
            self.logger.error(f"Error in gas analysis: {e}", exc_info=True)
            # Return safe fallback values
            return {
                'current_gas_gwei': 0.1,
                'network_congestion': 50.0,
                'recommended_gas_gwei': 0.15,
                'gas_strategy': 'standard',
                'estimated_cost_usd': 0.50,
                'data_quality': 'ERROR_FALLBACK',
                'chain_id': kwargs.get('chain_id', 84532)
            }
    
    def _get_fallback_gas_price(self, chain_id: int) -> Decimal:
        """
        Get conservative fallback gas prices by chain.
        
        Args:
            chain_id: Blockchain network ID
            
        Returns:
            Conservative gas price estimate in gwei
        """
        # Base Sepolia and Base are typically low-cost
        if chain_id in [84532, 8453]:
            return Decimal('0.1')  # Base chains
        # Ethereum chains are more expensive
        elif chain_id in [1, 11155111]:
            return Decimal('30.0')  # Ethereum chains
        else:
            return Decimal('10.0')  # Unknown chain - medium estimate
    
    def _calculate_congestion(self, gas_price_gwei: Decimal, chain_id: int) -> float:
        """
        Calculate network congestion level from gas price.
        
        Args:
            gas_price_gwei: Current gas price in gwei
            chain_id: Blockchain network ID
            
        Returns:
            Congestion percentage (0-100)
        """
        # Define base prices by chain (normal conditions)
        base_prices = {
            84532: Decimal('0.05'),   # Base Sepolia
            8453: Decimal('0.05'),    # Base Mainnet
            11155111: Decimal('20'),  # Ethereum Sepolia
            1: Decimal('20'),         # Ethereum Mainnet
        }
        
        base_price = base_prices.get(chain_id, Decimal('10'))
        
        # Calculate congestion (0-100%)
        # Formula: (current - base) / base * 50
        # Caps at 100%
        if gas_price_gwei <= base_price:
            return 0.0
        
        congestion = float((gas_price_gwei - base_price) / base_price * 50)
        return min(congestion, 100.0)
    
    def _determine_gas_strategy(self, congestion: float) -> str:
        """
        Determine recommended gas strategy based on congestion.
        
        Args:
            congestion: Network congestion level (0-100)
            
        Returns:
            Strategy name: 'low', 'standard', 'fast', or 'urgent'
        """
        if congestion < 20:
            return 'low'
        elif congestion < 50:
            return 'standard'
        elif congestion < 80:
            return 'fast'
        else:
            return 'urgent'
    
    def _estimate_cost_usd(
        self,
        gas_price_gwei: Decimal,
        gas_units: int = 200000
    ) -> Decimal:
        """
        Estimate transaction cost in USD.
        
        Args:
            gas_price_gwei: Gas price in gwei
            gas_units: Estimated gas units needed
            
        Returns:
            Estimated cost in USD
        """
        # Convert to ETH (1 gwei = 0.000000001 ETH)
        cost_eth = gas_price_gwei * Decimal(gas_units) / Decimal(10**9)
        
        # Estimate USD (assume $2000/ETH for rough estimate)
        # In production, this should use real price feeds
        eth_price_usd = Decimal('2000')
        cost_usd = cost_eth * eth_price_usd
        
        return cost_usd


# =============================================================================
# REAL LIQUIDITY ANALYZER
# =============================================================================

class RealLiquidityAnalyzer(BaseAnalyzer):
    """
    Analyzes pool liquidity using REAL Uniswap V3 data.
    
    Queries actual on-chain pool contracts for liquidity information.
    """
    
    async def analyze(self, token_address: str, **kwargs) -> Dict[str, Any]:
        """
        Analyze REAL pool liquidity from Uniswap V3.
        
        Args:
            token_address: Token address to analyze
            **kwargs: Additional parameters (chain_id, trade_size_usd)
        
        Returns:
            Dict containing:
            - pool_liquidity_usd: REAL pool liquidity in USD
            - expected_slippage: Calculated slippage percentage
            - liquidity_depth_score: Quality score (0-100)
            - pool_address: Uniswap V3 pool address
            - data_quality: Quality rating of the data
        """
        try:
            chain_id = kwargs.get('chain_id', 84532)
            trade_size_usd = Decimal(str(kwargs.get('trade_size_usd', 100)))
            
            # Try to get REAL liquidity from Uniswap V3
            web3_client = await self._ensure_web3_client(chain_id)
            
            if web3_client is not None:
                # Type guard
                client = cast(Web3Client, web3_client)
                
                # ✅ REAL DATA: Query Uniswap V3 pool
                liquidity_data = await self._get_real_pool_liquidity(
                    client,
                    token_address,
                    chain_id
                )
                
                if liquidity_data:
                    pool_liquidity_usd = liquidity_data['liquidity_usd']
                    pool_address = liquidity_data['pool_address']
                    data_quality = "EXCELLENT"
                    
                    self.logger.info(
                        f"[LIQUIDITY] Real pool found: ${pool_liquidity_usd:,.0f} "
                        f"at {pool_address[:10]}..."
                    )
                else:
                    # Pool not found - use heuristics
                    pool_liquidity_usd = self._estimate_liquidity_fallback(token_address)
                    pool_address = "0x0000000000000000000000000000000000000000"
                    data_quality = "ESTIMATED"
                    
                    self.logger.warning(
                        f"[LIQUIDITY] No pool found, using estimate: ${pool_liquidity_usd:,.0f}"
                    )
            else:
                # Web3 not available - use conservative estimate
                pool_liquidity_usd = Decimal('50000')  # Conservative
                pool_address = "0x0000000000000000000000000000000000000000"
                data_quality = "FALLBACK"
                
                self.logger.warning(
                    f"[LIQUIDITY] Web3 unavailable, using fallback: ${pool_liquidity_usd:,.0f}"
                )
            
            # Calculate slippage based on trade size vs liquidity
            expected_slippage = self._calculate_slippage(
                trade_size_usd,
                pool_liquidity_usd
            )
            
            # Calculate liquidity depth score
            liquidity_depth_score = self._calculate_depth_score(pool_liquidity_usd)
            
            result = {
                'pool_liquidity_usd': float(pool_liquidity_usd),
                'expected_slippage': float(expected_slippage),
                'liquidity_depth_score': liquidity_depth_score,
                'pool_address': pool_address,
                'data_quality': data_quality,
                'trade_impact_percent': float(expected_slippage),
                'chain_id': chain_id
            }
            
            self.logger.debug(
                f"[LIQUIDITY] Analysis complete: ${pool_liquidity_usd:,.0f}, "
                f"slippage={expected_slippage:.2f}%, score={liquidity_depth_score:.1f}"
            )
            return result
            
        except Exception as e:
            self.logger.error(f"Error in liquidity analysis: {e}", exc_info=True)
            # Return safe fallback
            return {
                'pool_liquidity_usd': 50000.0,
                'expected_slippage': 1.0,
                'liquidity_depth_score': 50.0,
                'pool_address': "0x0000000000000000000000000000000000000000",
                'data_quality': 'ERROR_FALLBACK',
                'trade_impact_percent': 1.0,
                'chain_id': kwargs.get('chain_id', 84532)
            }
    
    async def _get_real_pool_liquidity(
        self,
        web3_client: Web3Client,
        token_address: str,
        chain_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Query REAL liquidity from Uniswap V3 pool.
        
        Args:
            web3_client: Connected Web3 client
            token_address: Token to query
            chain_id: Blockchain network ID
            
        Returns:
            Dictionary with liquidity data or None if pool not found
        """
        try:
            # Get factory address for this chain
            factory_address = UNISWAP_V3_FACTORY.get(chain_id)
            if not factory_address:
                self.logger.warning(f"No Uniswap V3 factory for chain {chain_id}")
                return None
            
            # Get WETH address for this chain
            weth_address = self._get_weth_address(chain_id)
            if not weth_address:
                self.logger.warning(f"No WETH address for chain {chain_id}")
                return None
            
            # Create factory contract
            factory_contract = web3_client.web3.eth.contract(  # type: ignore[attr-defined]
                address=web3_client.web3.to_checksum_address(factory_address),  # type: ignore[attr-defined]
                abi=FACTORY_ABI
            )
            
            # Try each fee tier to find pool
            for fee_tier in FEE_TIERS:
                try:
                    pool_address = await factory_contract.functions.getPool(
                        web3_client.web3.to_checksum_address(token_address),  # type: ignore[attr-defined]
                        web3_client.web3.to_checksum_address(weth_address),  # type: ignore[attr-defined]
                        fee_tier
                    ).call()
                    
                    # Check if pool exists (non-zero address)
                    if pool_address != '0x0000000000000000000000000000000000000000':
                        # Found pool - get liquidity
                        pool_contract = web3_client.web3.eth.contract(  # type: ignore[attr-defined]
                            address=pool_address,
                            abi=POOL_ABI
                        )
                        
                        liquidity = await pool_contract.functions.liquidity().call()
                        
                        # Convert to USD estimate
                        # This is simplified - real calculation would use sqrtPriceX96
                        liquidity_usd = Decimal(liquidity) / Decimal(10**18) * Decimal('2000')
                        
                        self.logger.info(
                            f"[UNISWAP V3] Found pool at {pool_address} "
                            f"with ${liquidity_usd:,.0f} liquidity"
                        )
                        
                        return {
                            'pool_address': pool_address,
                            'liquidity_raw': liquidity,
                            'liquidity_usd': liquidity_usd,
                            'fee_tier': fee_tier
                        }
                        
                except Exception as e:
                    logger.error(f"Error querying pool at fee {fee_tier}: {e}")                    
                    # Pool doesn't exist for this fee tier, try next
                    continue
            
            self.logger.warning(
                f"[UNISWAP V3] No pool found for token {token_address[:10]}..."
            )
            return None
            
        except Exception as e:
            self.logger.error(f"Error querying Uniswap V3 pool: {e}")
            return None
    
    def _get_weth_address(self, chain_id: int) -> Optional[str]:
        """
        Get WETH address for chain.
        
        Args:
            chain_id: Blockchain network ID
            
        Returns:
            WETH address or None if not available
        """
        weth_addresses = {
            84532: '0x4200000000000000000000000000000000000006',  # Base Sepolia
            8453: '0x4200000000000000000000000000000000000006',  # Base Mainnet
            11155111: '0xfFf9976782d46CC05630D1f6eBAb18b2324d6B14',  # Ethereum Sepolia
            1: '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',  # Ethereum Mainnet
        }
        return weth_addresses.get(chain_id)
    
    def _estimate_liquidity_fallback(self, token_address: str) -> Decimal:
        """
        Estimate liquidity using heuristics when pool data unavailable.
        
        Args:
            token_address: Token address
            
        Returns:
            Estimated liquidity in USD
        """
        # Use conservative estimate
        # Well-known tokens have higher liquidity
        known_tokens = {
            '0x4200000000000000000000000000000000000006': Decimal('1000000'),  # WETH
            '0x036cbd53842c5426634e7929541ec2318f3dcf7e': Decimal('500000'),   # USDC
        }
        
        return known_tokens.get(token_address.lower(), Decimal('50000'))
    
    def _calculate_slippage(
        self, 
        trade_size_usd: Decimal, 
        pool_liquidity_usd: Decimal
    ) -> Decimal:
        """
        Calculate expected slippage based on trade size vs pool liquidity.
        
        Args:
            trade_size_usd: Trade size in USD
            pool_liquidity_usd: Pool liquidity in USD
            
        Returns:
            Expected slippage percentage
        """
        if pool_liquidity_usd <= 0:
            return Decimal('5.0')  # High slippage for no liquidity
        
        # Calculate trade impact as percentage of pool
        impact_ratio = trade_size_usd / pool_liquidity_usd
        
        # Slippage grows non-linearly with impact
        # Small trades: ~0.1-0.5%
        # Medium trades (0.5-2% impact): 0.5-2%
        # Large trades (2%+ impact): 2-10%+
        if impact_ratio < Decimal('0.005'):  # <0.5% impact
            slippage = Decimal('0.1')
        elif impact_ratio < Decimal('0.01'):  # 0.5-1% impact
            slippage = Decimal('0.3')
        elif impact_ratio < Decimal('0.02'):  # 1-2% impact
            slippage = Decimal('0.8')
        elif impact_ratio < Decimal('0.05'):  # 2-5% impact
            slippage = Decimal('2.0')
        else:  # >5% impact
            slippage = min(impact_ratio * Decimal('100'), Decimal('10.0'))
        
        return slippage
    
    def _calculate_depth_score(self, liquidity_usd: Decimal) -> float:
        """
        Calculate liquidity depth score (0-100).
        
        Args:
            liquidity_usd: Pool liquidity in USD
            
        Returns:
            Score from 0 (very low liquidity) to 100 (excellent liquidity)
        """
        # Score based on liquidity ranges
        if liquidity_usd >= Decimal('1000000'):  # $1M+
            return 90.0
        elif liquidity_usd >= Decimal('500000'):  # $500k+
            return 80.0
        elif liquidity_usd >= Decimal('250000'):  # $250k+
            return 70.0
        elif liquidity_usd >= Decimal('100000'):  # $100k+
            return 60.0
        elif liquidity_usd >= Decimal('50000'):   # $50k+
            return 50.0
        elif liquidity_usd >= Decimal('25000'):   # $25k+
            return 40.0
        elif liquidity_usd >= Decimal('10000'):   # $10k+
            return 30.0
        else:
            # Scale from 0-30 for <$10k
            return float(liquidity_usd / Decimal('10000') * 30)


# =============================================================================
# REAL VOLATILITY ANALYZER
# =============================================================================

class RealVolatilityAnalyzer(BaseAnalyzer):
    """
    Analyzes price volatility using REAL historical price data.
    
    Calculates actual volatility from price history instead of simulating.
    """
    
    async def analyze(self, token_address: str, **kwargs) -> Dict[str, Any]:
        """
        Analyze REAL volatility from price history.
        
        Args:
            token_address: Token address to analyze
            **kwargs: Additional parameters (price_history, current_price)
        
        Returns:
            Dict containing:
            - volatility_index: Volatility score (0-100)
            - volatility_24h_percent: 24-hour volatility percentage
            - trend_direction: Price trend ('bullish', 'bearish', 'neutral')
            - data_quality: Quality rating of the data
            - price_samples: Number of price samples analyzed
        """
        try:
            # Get price history
            price_history = kwargs.get('price_history', [])
            current_price = kwargs.get('current_price', Decimal('0'))
            
            if not price_history or len(price_history) < 2:
                # No price data - use conservative estimates
                self.logger.warning(
                    "[VOLATILITY] No price history available, using estimates"
                )
                return {
                    'volatility_index': 30.0,
                    'volatility_24h_percent': 15.0,
                    'trend_direction': 'neutral',
                    'data_quality': 'ESTIMATED',
                    'price_samples': 0
                }
            
            # Convert to Decimal if needed
            prices = [Decimal(str(p)) for p in price_history]
            
            # ✅ REAL DATA: Calculate actual volatility from price history
            volatility_24h = self._calculate_volatility(prices)
            
            # Calculate trend from price history
            trend = self._calculate_trend(prices, current_price)
            
            # Convert to index (0-100)
            volatility_index = self._volatility_to_index(volatility_24h)
            
            data_quality = "GOOD" if len(prices) >= 10 else "FAIR"
            
            result = {
                'volatility_index': volatility_index,
                'volatility_24h_percent': float(volatility_24h),
                'trend_direction': trend,
                'data_quality': data_quality,
                'price_samples': len(prices)
            }
            
            self.logger.debug(
                f"[VOLATILITY] Analysis complete: index={volatility_index:.1f}, "
                f"24h={volatility_24h:.1f}%, trend={trend}"
            )
            return result
            
        except Exception as e:
            self.logger.error(f"Error in volatility analysis: {e}", exc_info=True)
            # Return moderate fallback
            return {
                'volatility_index': 30.0,
                'volatility_24h_percent': 15.0,
                'trend_direction': 'neutral',
                'data_quality': 'ERROR_FALLBACK',
                'price_samples': 0
            }
    
    def _calculate_volatility(self, prices: List[Decimal]) -> Decimal:
        """
        Calculate price volatility (standard deviation of returns).
        
        Args:
            prices: List of historical prices
            
        Returns:
            Volatility as percentage
        """
        if len(prices) < 2:
            return Decimal('15.0')
        
        # Calculate price returns (percentage changes)
        returns: List[Decimal] = []
        for i in range(1, len(prices)):
            if prices[i-1] > 0:
                ret = ((prices[i] - prices[i-1]) / prices[i-1]) * 100
                returns.append(ret)
        
        if not returns:
            return Decimal('15.0')
        
        # Calculate standard deviation using Decimal throughout
        mean_return = sum(returns) / Decimal(len(returns))
        
        # Calculate variance using Decimal
        variance_sum = Decimal('0')
        for r in returns:
            diff = r - mean_return
            variance_sum += diff * diff  # Use multiplication instead of **2
        
        variance = variance_sum / Decimal(len(returns))
        
        # Calculate standard deviation (square root)
        # Convert to float for sqrt, then back to Decimal
        std_dev = Decimal(str(float(variance) ** 0.5))
        
        return abs(std_dev)
    
    def _calculate_trend(
        self, 
        prices: List[Decimal], 
        current_price: Decimal
    ) -> str:
        """
        Determine price trend direction.
        
        Args:
            prices: Historical prices
            current_price: Current price
            
        Returns:
            Trend direction: 'bullish', 'bearish', or 'neutral'
        """
        if len(prices) < 2:
            return 'neutral'
        
        # Compare current price to moving average
        avg_price = sum(prices) / Decimal(len(prices))
        
        if current_price > avg_price * Decimal('1.02'):  # >2% above average
            return 'bullish'
        elif current_price < avg_price * Decimal('0.98'):  # >2% below average
            return 'bearish'
        else:
            return 'neutral'
    
    def _volatility_to_index(self, volatility_percent: Decimal) -> float:
        """
        Convert volatility percentage to 0-100 index.
        
        Args:
            volatility_percent: Volatility as percentage
            
        Returns:
            Index from 0 (stable) to 100 (very volatile)
        """
        # Scale: 0-5% = low (0-20), 5-20% = medium (20-60), 20%+ = high (60-100)
        if volatility_percent <= Decimal('5'):
            return float(volatility_percent) * 4  # 0-20
        elif volatility_percent <= Decimal('20'):
            return float((volatility_percent - Decimal('5')) * Decimal('2.67') + Decimal('20'))  # 20-60
        else:
            return min(float((volatility_percent - Decimal('20')) * 2 + 60), 100.0)  # 60-100


# =============================================================================
# SMART MEV DETECTOR
# =============================================================================

class SmartMEVDetector(BaseAnalyzer):
    """
    Detects MEV threats using smart heuristics based on REAL data.
    
    Uses actual liquidity and volume to assess MEV risk instead of random values.
    """
    
    async def analyze(self, token_address: str, **kwargs) -> Dict[str, Any]:
        """
        Analyze MEV threats using smart heuristics.
        
        Args:
            token_address: Token address to analyze
            **kwargs: Additional parameters (liquidity_usd, volume_24h, trade_size_usd)
        
        Returns:
            Dict containing:
            - threat_level: Overall MEV threat (0-100)
            - sandwich_risk: Risk of sandwich attacks (0-100)
            - frontrun_probability: Likelihood of frontrunning (0-100)
            - detected_bots: Estimated number of MEV bots
            - recommended_protection: Suggested protection method
        """
        try:
            # Get real market data
            liquidity_usd = Decimal(str(kwargs.get('liquidity_usd', 100000)))
            volume_24h = Decimal(str(kwargs.get('volume_24h', 50000)))
            trade_size_usd = Decimal(str(kwargs.get('trade_size_usd', 100)))
            
            # ✅ SMART HEURISTICS: MEV risk based on real market conditions
            
            # Factor 1: Liquidity (higher = more bots interested)
            if liquidity_usd >= Decimal('1000000'):  # $1M+
                liquidity_risk = 70.0
            elif liquidity_usd >= Decimal('500000'):  # $500k+
                liquidity_risk = 50.0
            elif liquidity_usd >= Decimal('100000'):  # $100k+
                liquidity_risk = 30.0
            else:
                liquidity_risk = 10.0
            
            # Factor 2: Volume (higher = more MEV opportunities)
            if volume_24h >= Decimal('500000'):  # $500k+ daily
                volume_risk = 60.0
            elif volume_24h >= Decimal('100000'):  # $100k+ daily
                volume_risk = 40.0
            elif volume_24h >= Decimal('50000'):   # $50k+ daily
                volume_risk = 20.0
            else:
                volume_risk = 5.0
            
            # Factor 3: Trade impact (larger trades = more MEV attractive)
            trade_impact = float((trade_size_usd / liquidity_usd) * 100) if liquidity_usd > 0 else 0.0
            if trade_impact >= 1.0:  # 1%+ impact
                impact_risk = 70.0
            elif trade_impact >= 0.5:  # 0.5%+ impact
                impact_risk = 40.0
            elif trade_impact >= 0.1:  # 0.1%+ impact
                impact_risk = 20.0
            else:
                impact_risk = 5.0
            
            # Calculate overall threat level
            threat_level = (
                liquidity_risk * 0.4 +
                volume_risk * 0.3 +
                impact_risk * 0.3
            )
            
            # Estimate specific MEV risks
            sandwich_risk = min(impact_risk * 1.2, 100.0)  # Sandwich depends on trade size
            frontrun_probability = min(volume_risk * 1.3, 100.0)  # Frontrun depends on volume
            
            # Estimate MEV bots based on market activity
            if liquidity_usd >= Decimal('1000000') and volume_24h >= Decimal('500000'):
                detected_bots = 8  # High activity pools
            elif liquidity_usd >= Decimal('500000'):
                detected_bots = 5  # Medium activity pools
            elif liquidity_usd >= Decimal('100000'):
                detected_bots = 3  # Low activity pools
            else:
                detected_bots = 1  # Minimal activity
            
            # Recommend protection based on threat level
            if threat_level >= 70:
                recommended_protection = 'private_mempool'
            elif threat_level >= 50:
                recommended_protection = 'flashbots'
            elif threat_level >= 30:
                recommended_protection = 'slippage_protection'
            else:
                recommended_protection = 'none_needed'
            
            result = {
                'threat_level': round(threat_level, 2),
                'sandwich_risk': round(sandwich_risk, 2),
                'frontrun_probability': round(frontrun_probability, 2),
                'detected_bots': detected_bots,
                'recommended_protection': recommended_protection,
                'data_quality': 'HEURISTIC',
                'trade_impact_percent': round(trade_impact, 2)
            }
            
            self.logger.debug(
                f"[MEV] Analysis complete: threat={threat_level:.1f}, "
                f"sandwich={sandwich_risk:.1f}, bots={detected_bots}"
            )
            return result
            
        except Exception as e:
            self.logger.error(f"Error in MEV analysis: {e}", exc_info=True)
            # Return moderate fallback
            return {
                'threat_level': 30.0,
                'sandwich_risk': 30.0,
                'frontrun_probability': 30.0,
                'detected_bots': 3,
                'recommended_protection': 'slippage_protection',
                'data_quality': 'ERROR_FALLBACK',
                'trade_impact_percent': 0.5
            }


# =============================================================================
# MARKET STATE ANALYZER
# =============================================================================

class MarketStateAnalyzer(BaseAnalyzer):
    """
    Analyzes overall market conditions and timing.
    
    Provides trading recommendations based on combined market factors.
    """
    
    async def analyze(self, token_address: str, **kwargs) -> Dict[str, Any]:
        """
        Analyze overall market state and timing.
        
        Args:
            token_address: Token address to analyze
            **kwargs: Additional parameters (volatility_index, trend_direction, volume_24h)
        
        Returns:
            Dict containing:
            - market_conditions: Overall market assessment
            - timing_score: Trade timing score (0-100)
            - recommended_action: Suggested action ('buy', 'sell', 'hold', 'wait')
            - confidence_level: Confidence in recommendation (0-100)
        """
        try:
            volatility_index = kwargs.get('volatility_index', 30.0)
            trend_direction = kwargs.get('trend_direction', 'neutral')
            volume_24h = Decimal(str(kwargs.get('volume_24h', 50000)))
            
            # Assess market conditions
            if volatility_index < 20:
                market_conditions = 'stable'
                volatility_score = 80.0
            elif volatility_index < 50:
                market_conditions = 'moderate'
                volatility_score = 60.0
            elif volatility_index < 80:
                market_conditions = 'volatile'
                volatility_score = 30.0
            else:
                market_conditions = 'highly_volatile'
                volatility_score = 10.0
            
            # Assess trend strength
            if trend_direction == 'bullish':
                trend_score = 75.0
            elif trend_direction == 'bearish':
                trend_score = 25.0
            else:
                trend_score = 50.0
            
            # Assess volume
            if volume_24h >= Decimal('500000'):
                volume_score = 80.0
            elif volume_24h >= Decimal('100000'):
                volume_score = 60.0
            elif volume_24h >= Decimal('50000'):
                volume_score = 40.0
            else:
                volume_score = 20.0
            
            # Calculate overall timing score
            timing_score = (
                volatility_score * 0.4 +
                trend_score * 0.3 +
                volume_score * 0.3
            )
            
            # Determine recommended action
            if timing_score >= 70:
                recommended_action = 'buy' if trend_direction == 'bullish' else 'sell'
                confidence_level = 80.0
            elif timing_score >= 50:
                recommended_action = 'hold'
                confidence_level = 60.0
            else:
                recommended_action = 'wait'
                confidence_level = 40.0
            
            result = {
                'market_conditions': market_conditions,
                'timing_score': round(timing_score, 2),
                'recommended_action': recommended_action,
                'confidence_level': round(confidence_level, 2),
                'volatility_assessment': volatility_score,
                'trend_assessment': trend_score,
                'volume_assessment': volume_score
            }
            
            self.logger.debug(
                f"[MARKET] Analysis complete: {market_conditions}, "
                f"timing={timing_score:.1f}, action={recommended_action}"
            )
            return result
            
        except Exception as e:
            self.logger.error(f"Error in market state analysis: {e}", exc_info=True)
            # Return neutral fallback
            return {
                'market_conditions': 'unknown',
                'timing_score': 50.0,
                'recommended_action': 'hold',
                'confidence_level': 30.0,
                'volatility_assessment': 50.0,
                'trend_assessment': 50.0,
                'volume_assessment': 50.0
            }


# =============================================================================
# COMPOSITE ANALYZER
# =============================================================================

class CompositeMarketAnalyzer:
    """
    Combines all analyzers for comprehensive market intelligence using REAL DATA.
    
    Orchestrates gas, liquidity, volatility, MEV, and market state analysis.
    """
    
    def __init__(self):
        """Initialize all sub-analyzers."""
        self.logger = logging.getLogger(f'{__name__}.CompositeMarketAnalyzer')
        
        # Initialize REAL DATA analyzers
        self.gas_analyzer = RealGasAnalyzer()
        self.liquidity_analyzer = RealLiquidityAnalyzer()
        self.volatility_analyzer = RealVolatilityAnalyzer()
        self.mev_detector = SmartMEVDetector()
        self.market_state = MarketStateAnalyzer()
        
        self.logger.info(
            "[ANALYZERS] ✅ Real data analyzers loaded successfully "
            "(Gas: blockchain, Liquidity: Uniswap V3, Volatility: price history, "
            "MEV: smart heuristics)"
        )
    
    async def analyze_comprehensive(
        self,
        token_address: str,
        trade_size_usd: Decimal,
        liquidity_usd: Optional[Decimal] = None,
        volume_24h: Optional[Decimal] = None,
        chain_id: int = 84532,
        price_history: Optional[List[Decimal]] = None,
        current_price: Optional[Decimal] = None
    ) -> Dict[str, Any]:
        """
        Perform comprehensive market analysis using REAL DATA.
        
        Args:
            token_address: Token to analyze
            trade_size_usd: Intended trade size in USD
            liquidity_usd: Pool liquidity (optional, will query if not provided)
            volume_24h: 24-hour volume (optional)
            chain_id: Blockchain network ID
            price_history: Historical prices for volatility calculation
            current_price: Current token price
            
        Returns:
            Complete market analysis from all REAL DATA analyzers
        """
        try:
            self.logger.info(
                f"[COMPOSITE] Running REAL DATA analysis for {token_address[:10]}... "
                f"on chain {chain_id}"
            )
            
            # Run gas analysis first (provides network context)
            gas_analysis = await self.gas_analyzer.analyze(
                token_address,
                chain_id=chain_id
            )
            
            # Run liquidity analysis (may query blockchain if liquidity_usd not provided)
            liquidity_analysis = await self.liquidity_analyzer.analyze(
                token_address,
                chain_id=chain_id,
                trade_size_usd=trade_size_usd
            )
            
            # Use queried liquidity if we didn't have it
            if liquidity_usd is None:
                liquidity_usd = Decimal(str(liquidity_analysis['pool_liquidity_usd']))
            
            # Run volatility analysis with price history
            volatility_analysis = await self.volatility_analyzer.analyze(
                token_address,
                price_history=price_history or [],
                current_price=current_price or Decimal('0')
            )
            
            # Run MEV analysis with real market data
            mev_analysis = await self.mev_detector.analyze(
                token_address,
                liquidity_usd=liquidity_usd,
                volume_24h=volume_24h or Decimal('50000'),
                trade_size_usd=trade_size_usd
            )
            
            # Run market state analysis
            market_analysis = await self.market_state.analyze(
                token_address,
                volatility_index=volatility_analysis['volatility_index'],
                trend_direction=volatility_analysis['trend_direction'],
                volume_24h=volume_24h or Decimal('50000')
            )
            
            # Combine results
            result = {
                'token_address': token_address,
                'chain_id': chain_id,
                'timestamp': datetime.now().isoformat(),
                'gas_analysis': gas_analysis,
                'liquidity': liquidity_analysis,
                'volatility': volatility_analysis,
                'mev_analysis': mev_analysis,
                'market_state': market_analysis,
                'composite_scores': self._calculate_composite_scores(
                    gas_analysis, 
                    liquidity_analysis, 
                    volatility_analysis,
                    mev_analysis, 
                    market_analysis
                ),
                'data_quality': self._assess_overall_quality(
                    gas_analysis,
                    liquidity_analysis,
                    volatility_analysis,
                    mev_analysis
                )
            }
            
            quality = result['data_quality']
            self.logger.info(
                f"[COMPOSITE] ✅ REAL DATA analysis complete for {token_address[:10]}... "
                f"Quality: {quality}"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error in comprehensive analysis: {e}", exc_info=True)
            raise
    
    def _calculate_composite_scores(
        self, 
        gas: Dict[str, Any], 
        liquidity: Dict[str, Any], 
        volatility: Dict[str, Any],
        mev: Dict[str, Any], 
        market: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calculate composite risk/opportunity scores from all analyses.
        
        Args:
            gas: Gas analysis results
            liquidity: Liquidity analysis results
            volatility: Volatility analysis results
            mev: MEV analysis results
            market: Market state analysis results
            
        Returns:
            Dictionary with composite scores
        """
        # Calculate overall risk (lower is better)
        risk_score = (
            gas['network_congestion'] * 0.15 +
            mev['threat_level'] * 0.30 +
            volatility['volatility_index'] * 0.25 +
            (100 - liquidity['liquidity_depth_score']) * 0.30
        )
        
        # Calculate overall opportunity (higher is better)
        opportunity_score = (
            liquidity['liquidity_depth_score'] * 0.40 +
            (100 - volatility['volatility_index']) * 0.20 +
            (100 - mev['threat_level']) * 0.20 +
            (100 - gas['network_congestion']) * 0.20
        )
        
        # Calculate overall confidence
        confidence_score = (opportunity_score - risk_score + 100) / 2
        
        return {
            'overall_risk': round(risk_score, 2),
            'overall_opportunity': round(opportunity_score, 2),
            'overall_confidence': round(confidence_score, 2),
            'favorable_conditions': opportunity_score > 60 and risk_score < 40
        }
    
    def _assess_overall_quality(
        self,
        gas_analysis: Dict[str, Any],
        liquidity_analysis: Dict[str, Any],
        volatility_analysis: Dict[str, Any],
        mev_analysis: Dict[str, Any]
    ) -> str:
        """
        Assess overall data quality across all analyzers.
        
        Args:
            gas_analysis: Gas analysis results
            liquidity_analysis: Liquidity analysis results
            volatility_analysis: Volatility analysis results
            mev_analysis: MEV analysis results
        
        Returns:
            Overall quality rating: EXCELLENT, GOOD, FAIR, POOR
        """
        qualities = [
            gas_analysis.get('data_quality', 'UNKNOWN'),
            liquidity_analysis.get('data_quality', 'UNKNOWN'),
            volatility_analysis.get('data_quality', 'UNKNOWN'),
            mev_analysis.get('data_quality', 'UNKNOWN')
        ]
        
        # Count excellent/good sources
        excellent_count = qualities.count('EXCELLENT')
        good_count = excellent_count + qualities.count('GOOD')
        
        if excellent_count >= 3:
            return 'EXCELLENT'
        elif good_count >= 3:
            return 'GOOD'
        elif good_count >= 2:
            return 'FAIR'
        else:
            return 'POOR'


# =============================================================================
# MODULE INITIALIZATION
# =============================================================================

def _log_initialization() -> None:
    """Log analyzer initialization status."""
    logger.info("=" * 80)
    logger.info("[ANALYZERS] Modular Market Analyzers - REAL DATA VERSION")
    logger.info("=" * 80)
    logger.info(f"[ANALYZERS] Web3 Available: {WEB3_AVAILABLE}")
    if WEB3_AVAILABLE:
        logger.info("[ANALYZERS] ✅ Using REAL blockchain data")
        logger.info("[ANALYZERS]    - Gas: Blockchain RPC queries")
        logger.info("[ANALYZERS]    - Liquidity: Uniswap V3 pool queries")
        logger.info("[ANALYZERS]    - Volatility: Price history calculations")
        logger.info("[ANALYZERS]    - MEV: Smart heuristics (liquidity-based)")
    else:
        logger.warning("[ANALYZERS] ⚠️ Web3 unavailable - using fallback estimates")
    logger.info("=" * 80)


# Run initialization logging
_log_initialization()