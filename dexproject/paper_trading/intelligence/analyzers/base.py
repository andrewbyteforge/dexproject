"""
Base Analyzer Abstract Class

Provides the foundation for all market analyzers with:
- Abstract analyze() method that all analyzers must implement
- Shared Web3 client management and lazy initialization
- Common configuration and logging setup

File: dexproject/paper_trading/intelligence/analyzers/base.py
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, TYPE_CHECKING

# Import constants for engine availability check
from paper_trading.intelligence.dex_integrations.constants import (
    ENGINE_CONFIG_MODULE_AVAILABLE,
    engine_config_module,
    get_config,
    Web3Client
)

# Type hints for Web3Client
if TYPE_CHECKING:
    from engine.web3_client import Web3Client as Web3ClientType
else:
    Web3ClientType = Any  # Runtime placeholder


class BaseAnalyzer(ABC):
    """
    Base class for all market analyzers.
    
    Provides common functionality:
    - Configuration management
    - Logging setup
    - Web3 client initialization and caching
    - Abstract analyze() method that subclasses must implement
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize analyzer with optional configuration.

        Args:
            config: Optional configuration dictionary for customizing analyzer behavior
        """
        self.config = config or {}
        self.logger = logging.getLogger(f'{__name__}.{self.__class__.__name__}')
        self._web3_client: Optional[Any] = None
        self._web3_initialized = False

    async def _ensure_web3_client(self, chain_id: int = 8453) -> Optional[Any]:
        """
        Ensure Web3 client is initialized with lazy config initialization.

        This method handles the engine config initialization timing issue by checking
        and initializing the config on-demand rather than at import time. The client
        is cached after first successful initialization.

        Args:
            chain_id: Chain ID for Web3 connection (default: 8453 for Base Mainnet)

        Returns:
            Web3Client instance or None if unavailable/failed to connect
        """
        # Check if engine config module is available at all
        if not ENGINE_CONFIG_MODULE_AVAILABLE:
            self.logger.warning(
                "Web3 infrastructure not available - engine.config module not found"
            )
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
                    # Directly await get_config since we're already in an async method
                    await get_config()
                    # Get config again after initialization
                    engine_config = getattr(engine_config_module, 'config', None)
                
                # If still None after initialization attempt, give up
                if engine_config is None:
                    self.logger.error("Failed to initialize engine config")
                    return None

            # Get chain-specific configuration
            chain_config = engine_config.get_chain_config(chain_id)
            if not chain_config:
                self.logger.warning(
                    f"[WEB3] No configuration found for chain {chain_id}. "
                    f"Available chains: {list(engine_config.chains.keys())}"
                )
                return None

            # Check if Web3Client is available (not None)
            if Web3Client is None:
                self.logger.error("Web3Client class is not available")
                return None

            # Initialize Web3 client with chain config
            self._web3_client = Web3Client(chain_config)
            await self._web3_client.connect()

            # Verify connection was successful
            if not self._web3_client.is_connected:
                self.logger.error(f"Failed to connect to chain {chain_id}")
                return None

            # Mark as initialized and cache the client
            self._web3_initialized = True
            self.logger.info(f"[WEB3] Connected to chain {chain_id}")
            return self._web3_client

        except Exception as e:
            self.logger.error(f"Error initializing Web3 client: {e}", exc_info=True)
            return None

    @abstractmethod
    async def analyze(self, token_address: str, **kwargs) -> Dict[str, Any]:
        """
        Perform analysis on the given token.
        
        This is an abstract method that must be implemented by all subclasses.
        Each analyzer should provide its specific analysis logic here.

        Args:
            token_address: Token contract address to analyze
            **kwargs: Additional parameters specific to each analyzer

        Returns:
            Dictionary containing analysis results with at minimum:
            - data_quality: Quality indicator (EXCELLENT, GOOD, FAIR, POOR, NO_DATA, ERROR)
            - data_source: Source of the data used for analysis
        """
        pass