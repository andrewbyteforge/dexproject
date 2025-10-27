"""
Modular Market Analyzers for Paper Trading Intelligence

Separate analyzer modules for different aspects of market analysis,
making the system easier to maintain and extend.

File: dexproject/paper_trading/intelligence/analyzers/__init__.py
"""

import logging
import math
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union, cast

# Import defaults for data quality requirements
from paper_trading.defaults import IntelligenceDefaults

# Import Web3 infrastructure for real data (optional)
if TYPE_CHECKING:
    # Only import for type checking, not at runtime
    from engine.web3_client import Web3Client as Web3ClientType
else:
    Web3ClientType = Any  # Runtime placeholder

try:
    import engine.config as engine_config_module
    from engine.config import get_config
    from engine.web3_client import Web3Client
    ENGINE_CONFIG_MODULE_AVAILABLE = True
except ImportError:
    engine_config_module = None  # type: ignore
    get_config = None  # type: ignore
    Web3Client = None  # type: ignore
    ENGINE_CONFIG_MODULE_AVAILABLE = False

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
        self._web3_client: Optional[Any] = None
        self._web3_initialized = False

    async def _ensure_web3_client(self, chain_id: int = 84532) -> Optional[Any]:
        """
        Ensure Web3 client is initialized with lazy config initialization.

        This method now properly handles the engine config initialization timing issue
        by checking and initializing the config on-demand rather than at import time.

        Args:
            chain_id: Chain ID for Web3 connection

        Returns:
            Web3Client instance or None if unavailable
        """
        # Check if engine config module is available
        if not ENGINE_CONFIG_MODULE_AVAILABLE:
            self.logger.warning("Web3 infrastructure not available - engine.config module not found")
            return None

        # Return cached client if already initialized
        if self._web3_initialized and self._web3_client:
            return self._web3_client

        try:
            # Lazy initialization: Check config availability on-demand
            if engine_config_module is None:
                self.logger.error("Engine config module is None")
                return None

            # Get the config from the module
            engine_config = getattr(engine_config_module, 'config', None)

            # If config is None, try to initialize it
            if engine_config is None:
                self.logger.info("[WEB3] Engine config not initialized, initializing now...")
                if get_config is not None:
                    # Import async_to_sync for calling async get_config
                    from asgiref.sync import async_to_sync
                    async_to_sync(get_config)()
                    # Get config again after initialization
                    engine_config = getattr(engine_config_module, 'config', None)

                # If still None after initialization attempt, give up
                if engine_config is None:
                    self.logger.error("Failed to initialize engine config")
                    return None

            # Get chain config
            chain_config = engine_config.get_chain_config(chain_id)
            if not chain_config:
                self.logger.error(f"No config for chain {chain_id}")
                return None

            # Check if Web3Client is available (not None)
            if Web3Client is None:
                self.logger.error("Web3Client class is not available")
                return None

            # Initialize Web3 client
            self._web3_client = Web3Client(chain_config)
            await self._web3_client.connect()

            if not self._web3_client.is_connected:
                self.logger.error(f"Failed to connect to chain {chain_id}")
                return None

            self._web3_initialized = True
            self.logger.info(f"[WEB3] Connected to chain {chain_id}")
            return self._web3_client

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

    Queries the blockchain for:
    - Current gas prices from pending blocks
    - Base fee and priority fee
    - Network congestion levels
    - Gas cost categorization

    This provides accurate gas assessment for optimal trade timing.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize gas analyzer with optional configuration.

        Args:
            config: Optional configuration with gas thresholds
        """
        super().__init__(config)

        # Gas price thresholds (in gwei) - can be overridden per chain
        self.gas_thresholds = {
            'low': Decimal('0.5'),      # < 0.5 gwei = Low gas
            'medium': Decimal('2.0'),   # 0.5-2 gwei = Medium gas
            'high': Decimal('5.0'),     # 2-5 gwei = High gas
            'extreme': Decimal('10.0')  # > 5 gwei = Extreme gas
        }

        # Override with config if provided
        if config and 'gas_thresholds' in config:
            self.gas_thresholds.update(config['gas_thresholds'])

    async def analyze(
        self,
        token_address: str,
        chain_id: int = 84532,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Analyze current gas conditions on the blockchain.

        Args:
            token_address: Token address (for context, not used in gas analysis)
            chain_id: Blockchain network ID
            **kwargs: Additional parameters

        Returns:
            Dictionary containing gas analysis:
            - gas_price_gwei: Current gas price in gwei
            - base_fee_gwei: Base fee (EIP-1559)
            - priority_fee_gwei: Priority fee (EIP-1559)
            - network_congestion: Congestion level (0-100)
            - cost_category: 'low', 'medium', 'high', or 'extreme'
            - data_quality: Data quality indicator
        """
        try:
            # Try to get real blockchain data
            web3_client = await self._ensure_web3_client(chain_id)

            if web3_client:
                # Get latest block for gas price
                latest_block = web3_client.web3.eth.get_block('latest')  # Remove await

                # Extract gas prices (EIP-1559 format)
                base_fee = Decimal(str(latest_block.get('baseFeePerGas', 0))) / Decimal('1e9')  # Wei to Gwei
                gas_price = web3_client.web3.eth.gas_price  # Remove await
                gas_price_gwei = Decimal(str(gas_price)) / Decimal('1e9')

                # Calculate priority fee (for EIP-1559 chains)
                priority_fee_gwei = max(Decimal('0'), gas_price_gwei - base_fee)

                # Calculate network congestion based on gas price
                congestion = self._calculate_congestion(gas_price_gwei)

                # Categorize gas cost
                category = self._categorize_gas_cost(gas_price_gwei)

                self.logger.info(
                    f"[GAS] ✅ Real data: {gas_price_gwei:.2f} gwei "
                    f"({category}), Congestion: {congestion:.0f}%"
                )

                return {
                    'gas_price_gwei': float(gas_price_gwei),
                    'base_fee_gwei': float(base_fee),
                    'priority_fee_gwei': float(priority_fee_gwei),
                    'network_congestion': congestion,
                    'cost_category': category,
                    'data_quality': 'EXCELLENT',
                    'data_source': 'blockchain_rpc'
                }

            else:
                # Web3 not available - cannot provide real data
                self.logger.error(
                    "[GAS] Web3 unavailable and REQUIRE_REAL_GAS_DATA=True - "
                    "Cannot analyze without real data"
                )
                if IntelligenceDefaults.SKIP_TRADE_ON_MISSING_DATA:
                    return {
                        'gas_price_gwei': None,
                        'base_fee_gwei': None,
                        'priority_fee_gwei': None,
                        'network_congestion': None,
                        'cost_category': 'unknown',
                        'data_quality': 'NO_DATA',
                        'data_source': 'none',
                        'error': 'Real gas data unavailable - Web3 not connected'
                    }

                self.logger.warning("[GAS] Web3 unavailable - cannot get real data")
                return {
                    'gas_price_gwei': 0.0,
                    'base_fee_gwei': 0.0,
                    'priority_fee_gwei': 0.0,
                    'network_congestion': 0.0,
                    'cost_category': 'unknown',
                    'data_quality': 'NO_DATA',
                    'data_source': 'none'
                }

        except Exception as e:
            self.logger.error(f"Error analyzing gas: {e}", exc_info=True)
            return {
                'gas_price_gwei': None,
                'base_fee_gwei': None,
                'priority_fee_gwei': None,
                'network_congestion': None,
                'cost_category': 'unknown',
                'data_quality': 'ERROR',
                'data_source': 'error',
                'error': f'Gas analysis failed: {str(e)}'
            }

    def _calculate_congestion(self, gas_price_gwei: Decimal) -> float:
        """
        Calculate network congestion level from gas price.

        Args:
            gas_price_gwei: Current gas price in gwei

        Returns:
            Congestion level from 0 (empty) to 100 (completely congested)
        """
        # Map gas price to congestion level using thresholds
        if gas_price_gwei <= self.gas_thresholds['low']:
            # 0-20% congestion for low gas prices
            ratio = float(gas_price_gwei / self.gas_thresholds['low'])
            return min(20.0, ratio * 20.0)

        elif gas_price_gwei <= self.gas_thresholds['medium']:
            # 20-50% congestion for medium gas prices
            ratio = float(
                (gas_price_gwei - self.gas_thresholds['low']) /
                (self.gas_thresholds['medium'] - self.gas_thresholds['low'])
            )
            return 20.0 + (ratio * 30.0)

        elif gas_price_gwei <= self.gas_thresholds['high']:
            # 50-80% congestion for high gas prices
            ratio = float(
                (gas_price_gwei - self.gas_thresholds['medium']) /
                (self.gas_thresholds['high'] - self.gas_thresholds['medium'])
            )
            return 50.0 + (ratio * 30.0)

        else:
            # 80-100% congestion for extreme gas prices
            ratio = min(1.0, float(
                (gas_price_gwei - self.gas_thresholds['high']) /
                (self.gas_thresholds['extreme'] - self.gas_thresholds['high'])
            ))
            return 80.0 + (ratio * 20.0)

    def _categorize_gas_cost(self, gas_price_gwei: Decimal) -> str:
        """
        Categorize gas cost level.

        Args:
            gas_price_gwei: Current gas price in gwei

        Returns:
            Category: 'low', 'medium', 'high', or 'extreme'
        """
        if gas_price_gwei <= self.gas_thresholds['low']:
            return 'low'
        elif gas_price_gwei <= self.gas_thresholds['medium']:
            return 'medium'
        elif gas_price_gwei <= self.gas_thresholds['high']:
            return 'high'
        else:
            return 'extreme'


# =============================================================================
# REAL LIQUIDITY ANALYZER
# =============================================================================

class RealLiquidityAnalyzer(BaseAnalyzer):
    """
    Analyzes token liquidity using REAL blockchain data from Uniswap V3.

    Queries actual Uniswap V3 pools to determine:
    - Pool liquidity (total value locked)
    - Trade size impact on price
    - Pool depth and sustainability
    - Slippage estimates

    This provides accurate liquidity assessment for informed trading decisions.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize liquidity analyzer.

        Args:
            config: Optional configuration with liquidity thresholds
        """
        super().__init__(config)

        # Liquidity thresholds (in USD)
        self.liquidity_thresholds = {
            'excellent': Decimal('1000000'),   # $1M+ = Excellent liquidity
            'good': Decimal('250000'),         # $250K+ = Good liquidity
            'fair': Decimal('50000'),          # $50K+ = Fair liquidity
            'poor': Decimal('10000')           # $10K+ = Poor but tradeable
        }

        # Override with config if provided
        if config and 'liquidity_thresholds' in config:
            self.liquidity_thresholds.update(config['liquidity_thresholds'])

    async def analyze(
        self,
        token_address: str,
        chain_id: int = 84532,
        trade_size_usd: Decimal = Decimal('1000'),
        **kwargs
    ) -> Dict[str, Any]:
        """
        Analyze token liquidity from Uniswap V3 pools.

        Args:
            token_address: Token contract address to analyze
            chain_id: Blockchain network ID
            trade_size_usd: Intended trade size in USD for impact calculation
            **kwargs: Additional parameters

        Returns:
            Dictionary containing liquidity analysis:
            - pool_liquidity_usd: Total pool liquidity in USD
            - pool_address: Uniswap V3 pool address
            - fee_tier: Pool fee tier (500, 3000, or 10000)
            - trade_impact_percent: Estimated price impact of trade
            - liquidity_depth_score: Score from 0-100
            - liquidity_category: 'excellent', 'good', 'fair', or 'poor'
            - data_quality: Data quality indicator
        """
        try:
            # Try to get real blockchain data
            web3_client = await self._ensure_web3_client(chain_id)

            if web3_client:
                # Get pool info from Uniswap V3
                pool_info = await self._get_uniswap_pool_info(
                    web3_client,
                    token_address,
                    chain_id
                )

                if pool_info:
                    liquidity_usd = pool_info['liquidity_usd']

                    # Calculate trade impact
                    trade_impact = self._calculate_trade_impact(
                        trade_size_usd,
                        liquidity_usd
                    )

                    # Calculate liquidity depth score
                    depth_score = self._calculate_depth_score(liquidity_usd)

                    # Categorize liquidity
                    category = self._categorize_liquidity(liquidity_usd)

                    self.logger.info(
                        f"[LIQUIDITY] ✅ Real pool data: ${liquidity_usd:,.0f} "
                        f"({category}) - Impact: {trade_impact:.2f}%"
                    )

                    return {
                        'pool_liquidity_usd': float(liquidity_usd),
                        'pool_address': pool_info['pool_address'],
                        'fee_tier': pool_info['fee_tier'],
                        'trade_impact_percent': trade_impact,
                        'liquidity_depth_score': depth_score,
                        'liquidity_category': category,
                        'data_quality': 'EXCELLENT',
                        'data_source': 'uniswap_v3_pool'
                    }
                else:
                    # Pool not found - no real data available
                    self.logger.warning(
                        f"[LIQUIDITY] No pool found for token {token_address[:10]}... on chain {chain_id}"
                    )

                    if IntelligenceDefaults.SKIP_TRADE_ON_MISSING_DATA:
                        return {
                            'pool_liquidity_usd': None,
                            'pool_address': None,
                            'fee_tier': None,
                            'trade_impact_percent': None,
                            'liquidity_depth_score': 0.0,
                            'liquidity_category': 'none',
                            'data_quality': 'NO_POOL_FOUND',
                            'data_source': 'none',
                            'error': 'No Uniswap V3 pool found for this token'
                        }

                    return {
                        'pool_liquidity_usd': 0.0,
                        'pool_address': None,
                        'fee_tier': None,
                        'trade_impact_percent': None,
                        'liquidity_depth_score': 0.0,
                        'liquidity_category': 'none',
                        'data_quality': 'NO_POOL_FOUND',
                        'data_source': 'none'
                    }

            else:
                # Web3 not available - cannot get real data
                if IntelligenceDefaults.SKIP_TRADE_ON_MISSING_DATA:
                    self.logger.error(
                        "[LIQUIDITY] Web3 unavailable and SKIP_TRADE_ON_MISSING_DATA=True - "
                        "Cannot analyze without real data"
                    )
                    return {
                        'pool_liquidity_usd': None,
                        'pool_address': None,
                        'fee_tier': None,
                        'trade_impact_percent': None,
                        'liquidity_depth_score': 0.0,
                        'liquidity_category': 'none',
                        'data_quality': 'NO_DATA',
                        'data_source': 'none',
                        'error': 'Real liquidity data unavailable - Web3 not connected'
                    }

                self.logger.warning("[LIQUIDITY] Web3 unavailable - cannot get real data")
                return {
                    'pool_liquidity_usd': 0.0,
                    'pool_address': None,
                    'fee_tier': None,
                    'trade_impact_percent': None,
                    'liquidity_depth_score': 0.0,
                    'liquidity_category': 'none',
                    'data_quality': 'NO_DATA',
                    'data_source': 'none'
                }

        except Exception as e:
            self.logger.error(f"[LIQUIDITY] Error analyzing liquidity: {e}", exc_info=True)
            # No fallback data - return error state
            return {
                'pool_liquidity_usd': None,
                'pool_address': None,
                'fee_tier': None,
                'trade_impact_percent': None,
                'liquidity_depth_score': 0.0,
                'liquidity_category': 'unknown',
                'data_quality': 'ERROR',
                'data_source': 'error',
                'error': f'Liquidity analysis failed: {str(e)}'
            }

    async def _get_uniswap_pool_info(
        self,
        web3_client: Any,
        token_address: str,
        chain_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get Uniswap V3 pool information from blockchain.

        Args:
            web3_client: Connected Web3 client
            token_address: Token contract address
            chain_id: Blockchain network ID

        Returns:
            Dictionary with pool info or None if not found
        """
        try:
            # Get factory address for this chain
            factory_address = UNISWAP_V3_FACTORY.get(chain_id)
            if not factory_address:
                self.logger.error(f"No Uniswap V3 factory address for chain {chain_id}")
                return None

            # Common base tokens to check pairs against
            base_tokens = {
                84532: [
                    '0x036CbD53842c5426634e7929541eC2318f3dCF7e',  # USDC on Base Sepolia
                    '0x4200000000000000000000000000000000000006',  # WETH on Base Sepolia
                ],
                8453: [
                    '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913',  # USDC on Base Mainnet
                    '0x4200000000000000000000000000000000000006',  # WETH on Base Mainnet
                ]
            }

            base_token_list = base_tokens.get(chain_id, [])

            # Try each fee tier with each base token
            for base_token in base_token_list:
                for fee_tier in FEE_TIERS:
                    try:
                        # Create factory contract
                        factory_contract = await web3_client.get_contract(
                            factory_address,
                            FACTORY_ABI
                        )

                        # Get pool address
                        pool_address = await factory_contract.functions.getPool(
                            token_address,
                            base_token,
                            fee_tier
                        ).call()

                        # Check if pool exists (non-zero address)
                        if pool_address and pool_address != '0x0000000000000000000000000000000000000000':
                            # Get pool contract
                            pool_contract = await web3_client.get_contract(
                                pool_address,
                                POOL_ABI
                            )

                            # Get liquidity
                            liquidity = await pool_contract.functions.liquidity().call()

                            # Get slot0 for price
                            slot0 = await pool_contract.functions.slot0().call()
                            sqrt_price_x96 = slot0[0]

                            # Calculate liquidity in USD (simplified)
                            # For a more accurate calculation, we'd need token prices
                            # Here we use a rough approximation
                            liquidity_usd = Decimal(str(liquidity)) / Decimal('1e6')

                            return {
                                'pool_address': pool_address,
                                'fee_tier': fee_tier,
                                'liquidity': liquidity,
                                'liquidity_usd': liquidity_usd,
                                'sqrt_price_x96': sqrt_price_x96
                            }

                    except Exception:
                        # Pool doesn't exist for this pair/fee tier, continue
                        continue

            # No pool found
            return None

        except Exception as e:
            self.logger.error(f"Error getting Uniswap pool info: {e}", exc_info=True)
            return None

    def _calculate_trade_impact(
        self,
        trade_size_usd: Decimal,
        pool_liquidity_usd: Decimal
    ) -> float:
        """
        Calculate estimated price impact of a trade.

        Args:
            trade_size_usd: Trade size in USD
            pool_liquidity_usd: Pool liquidity in USD

        Returns:
            Estimated price impact as percentage
        """
        if pool_liquidity_usd == 0:
            return 100.0  # Maximum impact

        # Simplified impact calculation: impact = (trade_size / liquidity) * 100
        # Real calculation would use pool math, but this is a reasonable approximation
        impact_ratio = float(trade_size_usd / pool_liquidity_usd)

        # Apply non-linear scaling for larger trades
        if impact_ratio < 0.01:  # < 1% of pool
            return impact_ratio * 100
        elif impact_ratio < 0.05:  # 1-5% of pool
            return impact_ratio * 120  # Slightly higher impact
        else:  # > 5% of pool
            return min(100.0, impact_ratio * 150)  # Much higher impact

    def _calculate_depth_score(self, liquidity_usd: Decimal) -> float:
        """
        Calculate liquidity depth score (0-100).

        Args:
            liquidity_usd: Pool liquidity in USD

        Returns:
            Score from 0 (no liquidity) to 100 (excellent liquidity)
        """
        if liquidity_usd >= self.liquidity_thresholds['excellent']:
            return 100.0
        elif liquidity_usd >= self.liquidity_thresholds['good']:
            # Score between 75-100
            ratio = float(
                (liquidity_usd - self.liquidity_thresholds['good']) /
                (self.liquidity_thresholds['excellent'] - self.liquidity_thresholds['good'])
            )
            return 75.0 + (ratio * 25.0)
        elif liquidity_usd >= self.liquidity_thresholds['fair']:
            # Score between 50-75
            ratio = float(
                (liquidity_usd - self.liquidity_thresholds['fair']) /
                (self.liquidity_thresholds['good'] - self.liquidity_thresholds['fair'])
            )
            return 50.0 + (ratio * 25.0)
        elif liquidity_usd >= self.liquidity_thresholds['poor']:
            # Score between 25-50
            ratio = float(
                (liquidity_usd - self.liquidity_thresholds['poor']) /
                (self.liquidity_thresholds['fair'] - self.liquidity_thresholds['poor'])
            )
            return 25.0 + (ratio * 25.0)
        else:
            # Score between 0-25
            ratio = min(1.0, float(liquidity_usd / self.liquidity_thresholds['poor']))
            return ratio * 25.0

    def _categorize_liquidity(self, liquidity_usd: Decimal) -> str:
        """
        Categorize liquidity level.

        Args:
            liquidity_usd: Pool liquidity in USD

        Returns:
            Category: 'excellent', 'good', 'fair', or 'poor'
        """
        if liquidity_usd >= self.liquidity_thresholds['excellent']:
            return 'excellent'
        elif liquidity_usd >= self.liquidity_thresholds['good']:
            return 'good'
        elif liquidity_usd >= self.liquidity_thresholds['fair']:
            return 'fair'
        else:
            return 'poor'


# =============================================================================
# REAL VOLATILITY ANALYZER
# =============================================================================

class RealVolatilityAnalyzer(BaseAnalyzer):
    """
    Analyzes price volatility using REAL historical price data.

    Calculates:
    - Historical volatility from price movements
    - Price trends and momentum
    - Volatility indices
    - Risk metrics

    This provides accurate volatility assessment for risk management.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize volatility analyzer.

        Args:
            config: Optional configuration with volatility parameters
        """
        super().__init__(config)

        # Volatility configuration
        self.lookback_periods = config.get('lookback_periods', [24, 48, 168]) if config else [24, 48, 168]
        self.volatility_thresholds = {
            'low': Decimal('5.0'),      # < 5% volatility
            'medium': Decimal('15.0'),  # 5-15% volatility
            'high': Decimal('30.0'),    # 15-30% volatility
            'extreme': Decimal('50.0')  # > 30% volatility
        }

    async def analyze(
        self,
        token_address: str,
        price_history: Optional[List[Dict[str, Any]]] = None,
        current_price: Decimal = Decimal('0'),
        **kwargs
    ) -> Dict[str, Any]:
        """
        Analyze token price volatility.

        Args:
            token_address: Token contract address
            price_history: List of historical price data points
                         Each point: {'timestamp': int, 'price': Decimal}
            current_price: Current token price
            **kwargs: Additional parameters

        Returns:
            Dictionary containing volatility analysis:
            - volatility_index: Overall volatility score (0-100)
            - volatility_percent: Historical volatility percentage
            - trend_direction: 'bullish', 'bearish', or 'neutral'
            - price_momentum: Momentum score (-100 to +100)
            - volatility_category: 'low', 'medium', 'high', or 'extreme'
            - data_quality: Data quality indicator
        """
        try:
            # Use empty list if price_history is None
            price_history = price_history or []

            if not price_history or len(price_history) < 2:
                # No price data - cannot calculate real volatility
                self.logger.warning(
                    "[VOLATILITY] No price history available - cannot calculate volatility"
                )

                if IntelligenceDefaults.SKIP_TRADE_ON_MISSING_DATA:
                    return {
                        'volatility_index': None,
                        'volatility_percent': None,
                        'trend_direction': 'unknown',
                        'price_momentum': None,
                        'volatility_category': 'unknown',
                        'data_points': 0,
                        'data_quality': 'NO_DATA',
                        'data_source': 'none',
                        'error': 'Insufficient price history for volatility calculation'
                    }

                # If real data not required, return minimal data
                return {
                    'volatility_index': 0.0,
                    'volatility_percent': 0.0,
                    'trend_direction': 'unknown',
                    'price_momentum': 0.0,
                    'volatility_category': 'unknown',
                    'data_points': 0,
                    'data_quality': 'INSUFFICIENT_DATA',
                    'data_source': 'none'
                }

            # Calculate historical volatility
            volatility_percent = self._calculate_historical_volatility(price_history)

            # Determine trend direction
            trend = self._determine_trend(price_history, current_price)

            # Calculate momentum
            momentum = self._calculate_momentum(price_history)

            # Calculate volatility index (0-100)
            volatility_index = self._calculate_volatility_index(volatility_percent)

            # Categorize volatility
            category = self._categorize_volatility(volatility_percent)

            self.logger.info(
                f"[VOLATILITY] ✅ Real data: {volatility_percent:.1f}% "
                f"({category}), Trend: {trend}"
            )

            return {
                'volatility_index': volatility_index,
                'volatility_percent': float(volatility_percent),
                'trend_direction': trend,
                'price_momentum': momentum,
                'volatility_category': category,
                'data_points': len(price_history),
                'data_quality': 'EXCELLENT',
                'data_source': 'historical_prices'
            }

        except Exception as e:
            self.logger.error(f"[VOLATILITY] Error analyzing volatility: {e}", exc_info=True)
            # No fallback - return error state
            return {
                'volatility_index': None,
                'volatility_percent': None,
                'trend_direction': 'unknown',
                'price_momentum': None,
                'volatility_category': 'unknown',
                'data_points': 0,
                'data_quality': 'ERROR',
                'data_source': 'error',
                'error': f'Volatility analysis failed: {str(e)}'
            }

    def _calculate_historical_volatility(
        self,
        price_history: Union[List[Decimal], List[Dict[str, Any]]]
    ) -> Decimal:
        """
        Calculate historical volatility from price data.
        
        Handles two formats:
        - List of Decimal prices directly
        - List of dicts with 'price' key
        
        Args:
            price_history: Either list of Decimal prices or list of dicts with 'price' key
            
        Returns:
            Volatility as percentage (annualized)
        """
        if not price_history or len(price_history) < 2:
            return Decimal('0')  # Return 0 if insufficient data
        
        # Extract prices - ensure we always get List[Decimal]
        prices: List[Decimal] = []
        
        if isinstance(price_history[0], dict):
            # Extract from dict format - cast to tell Pylance the type
            dict_history = cast(List[Dict[str, Any]], price_history)
            prices = [Decimal(str(point['price'])) for point in dict_history]
        elif isinstance(price_history[0], Decimal):
            # Already Decimals - cast to tell Pylance the type
            decimal_history = cast(List[Decimal], price_history)
            prices = list(decimal_history)
        else:
            # Fallback: try to convert whatever format we have
            prices = [Decimal(str(p)) for p in price_history]
        
        # Validate we have prices after extraction
        if not prices or len(prices) < 2:
            return Decimal('0')
        
        # Calculate returns (percentage changes)
        returns: List[Decimal] = []
        for i in range(1, len(prices)):
            if prices[i-1] > Decimal('0'):
                ret = (prices[i] - prices[i-1]) / prices[i-1]
                returns.append(ret)
        
        if not returns:
            return Decimal('0')
        
        # Calculate standard deviation of returns
        mean_return = sum(returns) / Decimal(len(returns))
        variance = sum((r - mean_return) ** 2 for r in returns) / Decimal(len(returns))
        
        # Use math.sqrt for proper Decimal type handling
        std_dev = Decimal(str(math.sqrt(float(variance))))
        
        # Annualize (assuming hourly data, convert to annual)
        # sqrt(8760 hours per year) ≈ 93.6
        annual_volatility = std_dev * Decimal('93.6') * Decimal('100')
        
        return annual_volatility

    def _determine_trend(
        self,
        price_history: List[Dict[str, Any]],
        current_price: Decimal
    ) -> str:
        """
        Determine price trend direction.

        Args:
            price_history: List of historical price points
            current_price: Current price

        Returns:
            Trend: 'bullish', 'bearish', or 'neutral'
        """
        if not price_history:
            return 'neutral'

        # Get average price from history
        avg_price = sum(Decimal(str(p['price'])) for p in price_history) / Decimal(len(price_history))

        if current_price == 0:
            # Use most recent price if current not provided
            current_price = Decimal(str(price_history[-1]['price']))

        # Compare current price to average
        if avg_price > 0:
            price_change_percent = ((current_price - avg_price) / avg_price) * Decimal('100')
        else:
            return 'neutral'

        if price_change_percent > Decimal('5'):
            return 'bullish'
        elif price_change_percent < Decimal('-5'):
            return 'bearish'
        else:
            return 'neutral'

    def _calculate_momentum(self, price_history: List[Dict[str, Any]]) -> float:
        """
        Calculate price momentum score.

        Args:
            price_history: List of historical price points

        Returns:
            Momentum score from -100 (strong bearish) to +100 (strong bullish)
        """
        if len(price_history) < 2:
            return 0.0

        # Get first and last prices
        first_price = Decimal(str(price_history[0]['price']))
        last_price = Decimal(str(price_history[-1]['price']))

        if first_price == 0:
            return 0.0

        # Calculate percentage change
        percent_change = ((last_price - first_price) / first_price) * Decimal('100')

        # Normalize to -100 to +100 range
        # Assume ±50% change = ±100 momentum
        momentum = float(min(Decimal('100.0'), max(Decimal('-100.0'), percent_change * Decimal('2'))))

        return momentum

    def _calculate_volatility_index(self, volatility_percent: Decimal) -> float:
        """
        Convert volatility percentage to index score (0-100).

        Args:
            volatility_percent: Volatility percentage

        Returns:
            Volatility index from 0 (stable) to 100 (extremely volatile)
        """
        # Map volatility to 0-100 scale
        # 0% volatility = 0 index
        # 50%+ volatility = 100 index
        index = float(min(Decimal('100'), (volatility_percent / Decimal('50')) * Decimal('100')))
        return index

    def _categorize_volatility(self, volatility_percent: Decimal) -> str:
        """
        Categorize volatility level.

        Args:
            volatility_percent: Volatility percentage

        Returns:
            Category: 'low', 'medium', 'high', or 'extreme'
        """
        if volatility_percent < self.volatility_thresholds['low']:
            return 'low'
        elif volatility_percent < self.volatility_thresholds['medium']:
            return 'medium'
        elif volatility_percent < self.volatility_thresholds['high']:
            return 'high'
        else:
            return 'extreme'


# =============================================================================
# MEV THREAT DETECTOR
# =============================================================================

class MEVThreatDetector(BaseAnalyzer):
    """
    Detects MEV (Maximal Extractable Value) threats using market heuristics.

    Analyzes:
    - Sandwich attack probability based on liquidity and trade size
    - Front-running risk based on gas prices and timing
    - Overall MEV threat level
    - Recommended protection strategies

    Uses smart heuristics when direct MEV detection is not available.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize MEV detector.

        Args:
            config: Optional configuration
        """
        super().__init__(config)

    async def analyze(
        self,
        token_address: str,
        liquidity_usd: Decimal = Decimal('100000'),
        volume_24h: Decimal = Decimal('50000'),
        trade_size_usd: Decimal = Decimal('1000'),
        **kwargs
    ) -> Dict[str, Any]:
        """
        Analyze MEV threat level for a potential trade.

        Args:
            token_address: Token address
            liquidity_usd: Pool liquidity in USD
            volume_24h: 24-hour trading volume
            trade_size_usd: Intended trade size in USD
            **kwargs: Additional parameters

        Returns:
            Dictionary containing MEV analysis:
            - threat_level: MEV threat score (0-100)
            - sandwich_risk: Risk of sandwich attacks (0-100)
            - frontrun_risk: Risk of front-running (0-100)
            - recommended_protection: Protection strategy
            - data_quality: Data quality indicator
        """
        try:
            # Calculate sandwich attack risk based on liquidity and trade size
            sandwich_risk = self._calculate_sandwich_risk(trade_size_usd, liquidity_usd)

            # Calculate front-running risk based on volume patterns
            frontrun_risk = self._calculate_frontrun_risk(volume_24h, liquidity_usd)

            # Overall threat level (weighted average)
            threat_level = (sandwich_risk * 0.6 + frontrun_risk * 0.4)

            # Recommend protection strategy
            protection = self._recommend_protection(threat_level)

            self.logger.info(
                f"[MEV] Threat analysis: Level {threat_level:.0f}% "
                f"(Sandwich: {sandwich_risk:.0f}%, Frontrun: {frontrun_risk:.0f}%)"
            )

            return {
                'threat_level': threat_level,
                'sandwich_risk': sandwich_risk,
                'frontrun_risk': frontrun_risk,
                'recommended_protection': protection,
                'data_quality': 'GOOD',
                'data_source': 'heuristic_analysis'
            }

        except Exception as e:
            self.logger.error(f"Error in MEV analysis: {e}", exc_info=True)
            return {
                'threat_level': None,
                'sandwich_risk': None,
                'frontrun_risk': None,
                'recommended_protection': 'unknown',
                'data_quality': 'ERROR',
                'data_source': 'error',
                'error': f'MEV analysis failed: {str(e)}'
            }

    def _calculate_sandwich_risk(
        self,
        trade_size_usd: Decimal,
        liquidity_usd: Decimal
    ) -> float:
        """
        Calculate sandwich attack risk.

        Args:
            trade_size_usd: Trade size in USD
            liquidity_usd: Pool liquidity in USD

        Returns:
            Risk score (0-100)
        """
        if liquidity_usd == 0:
            return 100.0  # Maximum risk

        # Trade size as percentage of liquidity
        impact_ratio = float(trade_size_usd / liquidity_usd)

        # Larger trades relative to liquidity = higher sandwich risk
        if impact_ratio < 0.01:  # < 1%
            return 10.0
        elif impact_ratio < 0.05:  # 1-5%
            return 30.0 + (impact_ratio * 1000)  # 30-80%
        else:  # > 5%
            return min(100.0, 80.0 + (impact_ratio * 400))  # 80-100%

    def _calculate_frontrun_risk(
        self,
        volume_24h: Decimal,
        liquidity_usd: Decimal
    ) -> float:
        """
        Calculate front-running risk.

        Args:
            volume_24h: 24-hour trading volume
            liquidity_usd: Pool liquidity in USD

        Returns:
            Risk score (0-100)
        """
        if liquidity_usd == 0:
            return 100.0

        # Volume to liquidity ratio indicates competition for trades
        volume_ratio = float(volume_24h / liquidity_usd)

        # Higher volume relative to liquidity = more MEV bot activity
        if volume_ratio < 0.5:  # Low activity
            return 20.0
        elif volume_ratio < 2.0:  # Moderate activity
            return 40.0
        elif volume_ratio < 5.0:  # High activity
            return 60.0
        else:  # Very high activity
            return 80.0

    def _recommend_protection(self, threat_level: float) -> str:
        """
        Recommend MEV protection strategy.

        Args:
            threat_level: Overall MEV threat level (0-100)

        Returns:
            Protection recommendation
        """
        if threat_level < 30:
            return 'standard'  # Normal transaction
        elif threat_level < 60:
            return 'private_rpc'  # Use private RPC to reduce mempool visibility
        else:
            return 'flashbots'  # Use Flashbots protect for high-risk trades


# =============================================================================
# MARKET STATE ANALYZER
# =============================================================================

class MarketStateAnalyzer(BaseAnalyzer):
    """
    Analyzes overall market state and conditions.

    Evaluates:
    - Market sentiment (bullish, bearish, neutral)
    - Trading conditions
    - Market stability
    - Optimal trading windows

    Provides holistic market assessment for decision making.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize market state analyzer.

        Args:
            config: Optional configuration
        """
        super().__init__(config)

    async def analyze(
        self,
        token_address: str,
        volatility_index: float = 30.0,
        trend_direction: str = 'neutral',
        volume_24h: Decimal = Decimal('50000'),
        **kwargs
    ) -> Dict[str, Any]:
        """
        Analyze current market state.

        Args:
            token_address: Token address
            volatility_index: Volatility index (0-100)
            trend_direction: Price trend ('bullish', 'bearish', 'neutral')
            volume_24h: 24-hour trading volume
            **kwargs: Additional parameters

        Returns:
            Dictionary containing market state analysis:
            - market_sentiment: Overall sentiment
            - trading_conditions: Quality of trading conditions
            - market_stability: Stability score (0-100)
            - optimal_for_trading: Boolean indicating if conditions are good
            - data_quality: Data quality indicator
        """
        try:
            # Determine market sentiment
            sentiment = self._determine_sentiment(trend_direction, volatility_index)

            # Assess trading conditions
            conditions = self._assess_trading_conditions(
                volatility_index,
                float(volume_24h)
            )

            # Calculate stability score
            stability = self._calculate_stability(volatility_index)

            # Determine if conditions are optimal for trading
            optimal = self._is_optimal_for_trading(
                sentiment,
                conditions,
                stability
            )

            self.logger.info(
                f"[MARKET] State: {sentiment} sentiment, "
                f"{conditions} conditions, {stability:.0f}% stable"
            )

            return {
                'market_sentiment': sentiment,
                'trading_conditions': conditions,
                'market_stability': stability,
                'optimal_for_trading': optimal,
                'data_quality': 'GOOD',
                'data_source': 'composite_analysis'
            }

        except Exception as e:
            self.logger.error(f"Error in market state analysis: {e}", exc_info=True)
            return {
                'market_sentiment': 'unknown',
                'trading_conditions': 'unknown',
                'market_stability': None,
                'optimal_for_trading': False,
                'data_quality': 'ERROR',
                'data_source': 'error',
                'error': f'Market state analysis failed: {str(e)}'
            }

    def _determine_sentiment(
        self,
        trend_direction: str,
        volatility_index: float
    ) -> str:
        """
        Determine overall market sentiment.

        Args:
            trend_direction: Price trend direction
            volatility_index: Volatility level

        Returns:
            Sentiment: 'bullish', 'bearish', 'neutral', or 'uncertain'
        """
        if volatility_index > 60:
            return 'uncertain'  # Too volatile to determine sentiment

        return trend_direction  # Use trend as primary sentiment indicator

    def _assess_trading_conditions(
        self,
        volatility_index: float,
        volume_24h: float
    ) -> str:
        """
        Assess overall trading conditions.

        Args:
            volatility_index: Volatility level
            volume_24h: 24-hour volume

        Returns:
            Conditions: 'excellent', 'good', 'fair', or 'poor'
        """
        # Good conditions = moderate volatility + healthy volume
        if volatility_index < 20 and volume_24h > 100000:
            return 'excellent'
        elif volatility_index < 40 and volume_24h > 50000:
            return 'good'
        elif volatility_index < 60:
            return 'fair'
        else:
            return 'poor'

    def _calculate_stability(self, volatility_index: float) -> float:
        """
        Calculate market stability score.

        Args:
            volatility_index: Volatility level (0-100)

        Returns:
            Stability score (0-100, higher is more stable)
        """
        # Stability is inverse of volatility
        return 100.0 - volatility_index

    def _is_optimal_for_trading(
        self,
        sentiment: str,
        conditions: str,
        stability: float
    ) -> bool:
        """
        Determine if conditions are optimal for trading.

        Args:
            sentiment: Market sentiment
            conditions: Trading conditions
            stability: Market stability score

        Returns:
            True if conditions are favorable for trading
        """
        # Optimal conditions: clear sentiment, good conditions, stable market
        return (
            sentiment in ['bullish', 'neutral'] and
            conditions in ['excellent', 'good'] and
            stability > 50
        )


# =============================================================================
# COMPOSITE MARKET ANALYZER
# =============================================================================

class CompositeMarketAnalyzer(BaseAnalyzer):
    """
    Composite analyzer that coordinates all market analysis components.

    Combines:
    - Gas analysis (network conditions)
    - Liquidity analysis (pool depth)
    - Volatility analysis (price movements)
    - MEV analysis (threat detection)
    - Market state analysis (overall conditions)

    Provides comprehensive market intelligence for informed trading decisions.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize composite analyzer with all sub-analyzers.

        Args:
            config: Optional configuration for sub-analyzers
        """
        super().__init__(config)

        # Initialize all sub-analyzers
        self.gas_analyzer = RealGasAnalyzer(config)
        self.liquidity_analyzer = RealLiquidityAnalyzer(config)
        self.volatility_analyzer = RealVolatilityAnalyzer(config)
        self.mev_detector = MEVThreatDetector(config)
        self.market_state = MarketStateAnalyzer(config)

    async def analyze_comprehensive(
        self,
        token_address: str,
        chain_id: int = 84532,
        trade_size_usd: Decimal = Decimal('1000'),
        price_history: Optional[List[Dict[str, Any]]] = None,
        current_price: Optional[Decimal] = None,
        liquidity_usd: Optional[Decimal] = None,
        volume_24h: Optional[Decimal] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Perform comprehensive market analysis.

        Args:
            token_address: Token to analyze
            chain_id: Blockchain network ID
            trade_size_usd: Intended trade size in USD
            price_history: Historical price data (optional)
            current_price: Current token price (optional)
            liquidity_usd: Pool liquidity in USD (optional, will query if not provided)
            volume_24h: 24-hour trading volume (optional)
            **kwargs: Additional parameters

        Returns:
            Dictionary with all analysis results and composite scores
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
            if liquidity_usd is None and liquidity_analysis['pool_liquidity_usd'] is not None:
                liquidity_usd = Decimal(str(liquidity_analysis['pool_liquidity_usd']))
            elif liquidity_usd is None:
                liquidity_usd = Decimal('0')

            # Run volatility analysis with price history
            volatility_analysis = await self.volatility_analyzer.analyze(
                token_address,
                price_history=price_history,
                current_price=current_price or Decimal('0')
            )

            # Run MEV analysis with real market data
            mev_analysis = await self.mev_detector.analyze(
                token_address,
                liquidity_usd=liquidity_usd,
                volume_24h=volume_24h or Decimal('50000'),
                trade_size_usd=trade_size_usd
            )

            # Get volatility values for market state (handle None values)
            volatility_index = volatility_analysis.get('volatility_index')
            if volatility_index is None:
                volatility_index = 0.0

            trend_direction = volatility_analysis.get('trend_direction', 'unknown')

            # Run market state analysis
            market_analysis = await self.market_state.analyze(
                token_address,
                volatility_index=volatility_index,
                trend_direction=trend_direction,
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

    async def analyze(
        self,
        token_address: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Backward-compatible analyze method that calls analyze_comprehensive.

        This method exists for compatibility with code that calls .analyze()
        instead of .analyze_comprehensive().

        Args:
            token_address: Token to analyze
            **kwargs: Additional parameters passed to analyze_comprehensive

        Returns:
            Complete market analysis from analyze_comprehensive
        """
        return await self.analyze_comprehensive(token_address, **kwargs)

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
        # Get values, handling None cases
        network_congestion = gas.get('network_congestion', 0) or 0
        threat_level = mev.get('threat_level', 0) or 0
        volatility_index = volatility.get('volatility_index', 0) or 0
        liquidity_depth_score = liquidity.get('liquidity_depth_score', 0) or 0

        # Calculate overall risk (lower is better)
        risk_score = (
            network_congestion * 0.15 +
            threat_level * 0.30 +
            volatility_index * 0.25 +
            (100 - liquidity_depth_score) * 0.30
        )

        # Calculate overall opportunity (higher is better)
        opportunity_score = (
            liquidity_depth_score * 0.40 +
            (100 - volatility_index) * 0.20 +
            (100 - threat_level) * 0.20 +
            (100 - network_congestion) * 0.20
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
            Overall quality rating: EXCELLENT, GOOD, FAIR, POOR, NO_DATA, ERROR
        """
        qualities = [
            gas_analysis.get('data_quality', 'UNKNOWN'),
            liquidity_analysis.get('data_quality', 'UNKNOWN'),
            volatility_analysis.get('data_quality', 'UNKNOWN'),
            mev_analysis.get('data_quality', 'UNKNOWN')
        ]

        # Check for error states first
        if 'ERROR' in qualities:
            return 'ERROR'

        # Check for missing data
        if 'NO_DATA' in qualities or 'NO_POOL_FOUND' in qualities:
            return 'NO_DATA'

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
    logger.info(f"[ANALYZERS] Engine Config Module Available: {ENGINE_CONFIG_MODULE_AVAILABLE}")
    if ENGINE_CONFIG_MODULE_AVAILABLE:
        logger.info("[ANALYZERS] ✅ Using REAL blockchain data (lazy initialization)")
        logger.info("[ANALYZERS]    - Gas: Blockchain RPC queries")
        logger.info("[ANALYZERS]    - Liquidity: Uniswap V3 pool queries")
        logger.info("[ANALYZERS]    - Volatility: Price history calculations")
        logger.info("[ANALYZERS]    - MEV: Smart heuristics (liquidity-based)")
        logger.info("[ANALYZERS]    - Config: Initialized on-demand when analyzers run")
    else:
        logger.warning("[ANALYZERS] ⚠️ Engine config module unavailable")
    logger.info("[ANALYZERS] SKIP_TRADE_ON_MISSING_DATA: %s", IntelligenceDefaults.SKIP_TRADE_ON_MISSING_DATA)
    logger.info("=" * 80)


# Run initialization logging
_log_initialization()