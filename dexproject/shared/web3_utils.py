"""
Shared Web3 Utilities - Centralized Web3 Import and Availability Check

This module provides centralized Web3 import handling to avoid duplicate
warning messages throughout the project. All other modules should import
Web3 utilities from here instead of directly importing web3.

Enhanced with POA middleware support for Base network compatibility.

File: dexproject/shared/web3_utils.py
"""

import logging
from typing import Optional, Any, Dict, Union, Tuple, List, Callable
from functools import lru_cache
from decimal import Decimal

logger = logging.getLogger(__name__)

# Global Web3 availability check - cached to avoid repeated checks
_WEB3_AVAILABILITY_CHECKED = False
_WEB3_AVAILABLE = False
_WEB3_IMPORT_ERROR = None

# Web3 components - will be None if not available
Web3: Optional[Any] = None
geth_poa_middleware: Optional[Any] = None
encode_defunct: Optional[Callable] = None
is_address: Optional[Callable[[Any], bool]] = None
to_checksum_address: Optional[Callable[[Union[str, bytes]], str]] = None
Account: Optional[Any] = None

# POA middleware availability tracking
_POA_MIDDLEWARE_AVAILABLE = False
_POA_MIDDLEWARE_IMPORT_PATHS_TRIED: List[str] = []


@lru_cache(maxsize=1)
def check_web3_availability() -> Tuple[bool, Optional[str]]:
    """
    Check Web3 package availability with caching.
    Enhanced with comprehensive POA middleware detection.
    
    Returns:
        Tuple[bool, Optional[str]]: (is_available, error_message)
    """
    global _WEB3_AVAILABILITY_CHECKED, _WEB3_AVAILABLE, _WEB3_IMPORT_ERROR
    global Web3, geth_poa_middleware, encode_defunct, is_address, to_checksum_address, Account
    global _POA_MIDDLEWARE_AVAILABLE, _POA_MIDDLEWARE_IMPORT_PATHS_TRIED
    
    if _WEB3_AVAILABILITY_CHECKED:
        return _WEB3_AVAILABLE, _WEB3_IMPORT_ERROR
    
    try:
        # Import all Web3 components
        from web3 import Web3 as _Web3
        
        # Try multiple import paths for POA middleware (Web3.py v6/v7 compatibility)
        _geth_poa_middleware = None
        poa_import_paths = [
            # Web3.py v7+ path
            ('web3.middleware.geth_poa', 'geth_poa_middleware'),
            # Web3.py v6 path
            ('web3.middleware', 'geth_poa_middleware'),
            # Alternative v7 path
            ('web3.middleware.geth_poa', 'async_geth_poa_middleware'),
            # Fallback for older versions
            ('web3.middleware.geth_poa_middleware', 'geth_poa_middleware'),
        ]
        
        for module_path, attr_name in poa_import_paths:
            _POA_MIDDLEWARE_IMPORT_PATHS_TRIED.append(f"{module_path}.{attr_name}")
            try:
                import importlib
                module = importlib.import_module(module_path)
                _geth_poa_middleware = getattr(module, attr_name, None)
                if _geth_poa_middleware is not None:
                    _POA_MIDDLEWARE_AVAILABLE = True
                    logger.debug(f"POA middleware loaded from: {module_path}.{attr_name}")
                    break
            except (ImportError, AttributeError) as e:
                logger.debug(f"POA middleware not found at {module_path}.{attr_name}: {e}")
                continue
        
        # Import other Web3 utilities - using proper export paths
        from eth_account.messages import encode_defunct as _encode_defunct
        from eth_utils.address import is_address as _is_address
        from eth_utils.address import to_checksum_address as _to_checksum_address
        from eth_account import Account as _Account
        
        # Assign to global variables
        Web3 = _Web3
        geth_poa_middleware = _geth_poa_middleware
        encode_defunct = _encode_defunct
        is_address = _is_address
        to_checksum_address = _to_checksum_address
        Account = _Account
        
        # Test basic functionality
        test_address = '0x742d35Cc6486C3D5C2d2AD6589e78aa27D4cc8bF'
        _is_address(test_address)
        _to_checksum_address(test_address)
        
        _WEB3_AVAILABLE = True
        _WEB3_IMPORT_ERROR = None
        
        # Log success with version info
        try:
            import web3
            version = getattr(web3, '__version__', 'Unknown')
            logger.info(f"Web3 packages successfully imported and validated (v{version})")
        except Exception:
            logger.info("Web3 packages successfully imported and validated")
        
        # Log POA middleware status
        if not _POA_MIDDLEWARE_AVAILABLE:
            logger.warning(
                "POA middleware not available - Base network support may be limited. "
                "Install with: pip install 'web3[tester]' or check Web3.py documentation."
            )
            logger.debug(f"Tried import paths: {_POA_MIDDLEWARE_IMPORT_PATHS_TRIED}")
        else:
            logger.info("POA middleware available - Base network ready")
        
    except ImportError as e:
        _WEB3_AVAILABLE = False
        _WEB3_IMPORT_ERROR = str(e)
        
        logger.warning(
            "Web3 packages not available - some features will be limited. "
            "Install with: pip install web3 eth-account"
        )
        
    except Exception as e:
        _WEB3_AVAILABLE = False
        _WEB3_IMPORT_ERROR = f"Web3 validation failed: {str(e)}"
        
        logger.warning(f"Web3 packages installed but validation failed: {e}")
    
    _WEB3_AVAILABILITY_CHECKED = True
    return _WEB3_AVAILABLE, _WEB3_IMPORT_ERROR


def is_web3_available() -> bool:
    """
    Check if Web3 is available.
    
    Returns:
        bool: True if Web3 packages are available and working
    """
    available, _ = check_web3_availability()
    return available


def is_poa_middleware_available() -> bool:
    """
    Check if POA middleware is available for Base network support.
    
    Returns:
        bool: True if POA middleware is available
    """
    check_web3_availability()  # Ensure availability check has run
    return _POA_MIDDLEWARE_AVAILABLE


def get_web3_error() -> Optional[str]:
    """
    Get Web3 import error message if any.
    
    Returns:
        Optional[str]: Error message if Web3 is not available, None otherwise
    """
    _, error = check_web3_availability()
    return error


def require_web3() -> None:
    """
    Ensure Web3 is available, raise exception if not.
    
    Raises:
        ImportError: If Web3 packages are not available
    """
    if not is_web3_available():
        error = get_web3_error()
        raise ImportError(f"Web3 packages required but not available: {error}")


def require_poa_middleware() -> None:
    """
    Ensure POA middleware is available, raise exception if not.
    
    Raises:
        ImportError: If POA middleware is not available
    """
    if not is_poa_middleware_available():
        raise ImportError(
            "POA middleware required but not available. "
            "Install with: pip install 'web3[tester]'"
        )


def get_web3_components() -> Dict[str, Any]:
    """
    Get all Web3 components in a dictionary.
    
    Returns:
        Dict[str, Any]: Dictionary of Web3 components, values will be None if not available
    """
    check_web3_availability()  # Ensure components are loaded
    
    return {
        'Web3': Web3,
        'geth_poa_middleware': geth_poa_middleware,
        'encode_defunct': encode_defunct,
        'is_address': is_address,
        'to_checksum_address': to_checksum_address,
        'Account': Account,
        'available': _WEB3_AVAILABLE,
        'poa_available': _POA_MIDDLEWARE_AVAILABLE
    }


def inject_poa_middleware(w3_instance: Any, layer: int = 0) -> bool:
    """
    Inject POA middleware into a Web3 instance for Base network compatibility.
    
    Args:
        w3_instance: Web3 instance to inject middleware into
        layer: Middleware layer position (default: 0 for highest priority)
        
    Returns:
        bool: True if middleware was successfully injected, False otherwise
        
    Example:
        >>> w3 = create_web3_instance("https://mainnet.base.org")
        >>> inject_poa_middleware(w3)
    """
    if not is_poa_middleware_available():
        logger.warning("Cannot inject POA middleware - not available")
        return False
    
    if not w3_instance:
        logger.error("Cannot inject POA middleware - Web3 instance is None")
        return False
    
    # Type guard: ensure geth_poa_middleware is not None
    if geth_poa_middleware is None:
        logger.error("POA middleware is None despite availability check")
        return False
    
    try:
        # Check if middleware is already injected
        middleware_names = [m[0] for m in w3_instance.middleware_onion]
        if 'geth_poa' in middleware_names:
            logger.debug("POA middleware already injected")
            return True
        
        # Inject POA middleware
        w3_instance.middleware_onion.inject(geth_poa_middleware, layer=layer)
        logger.info(f"POA middleware injected at layer {layer}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to inject POA middleware: {e}")
        return False


def create_web3_instance(
    rpc_url: Optional[str] = None,
    inject_poa: bool = False,
    timeout: int = 30
) -> Optional[Any]:
    """
    Create a Web3 instance if available.
    
    Args:
        rpc_url: Optional RPC URL for the provider
        inject_poa: Whether to inject POA middleware (for Base network)
        timeout: Request timeout in seconds (default: 30)
        
    Returns:
        Web3 instance if available, None otherwise
        
    Example:
        >>> # Create instance for Base network
        >>> w3 = create_web3_instance("https://mainnet.base.org", inject_poa=True)
    """
    if not is_web3_available():
        return None
    
    # Type guard: ensure Web3 is not None
    if Web3 is None:
        return None
    
    try:
        if rpc_url:
            from web3.providers import HTTPProvider
            
            # Configure provider with timeout
            provider = HTTPProvider(
                rpc_url,
                request_kwargs={'timeout': timeout}
            )
            w3 = Web3(provider)
        else:
            w3 = Web3()
        
        # Inject POA middleware if requested
        if inject_poa:
            inject_poa_middleware(w3)
        
        return w3
        
    except Exception as e:
        logger.error(f"Failed to create Web3 instance: {e}")
        return None


def create_base_network_instance(rpc_url: str, timeout: int = 30) -> Optional[Any]:
    """
    Create a Web3 instance specifically configured for Base network.
    Automatically injects POA middleware.
    
    Args:
        rpc_url: Base network RPC URL
        timeout: Request timeout in seconds (default: 30)
        
    Returns:
        Web3 instance configured for Base, None if creation failed
        
    Example:
        >>> w3 = create_base_network_instance("https://mainnet.base.org")
    """
    if not is_poa_middleware_available():
        logger.warning(
            "Creating Base network instance without POA middleware. "
            "Some operations may fail. Install with: pip install 'web3[tester]'"
        )
    
    w3 = create_web3_instance(rpc_url, inject_poa=True, timeout=timeout)
    
    if w3:
        logger.info(f"Base network Web3 instance created: {rpc_url}")
    
    return w3


def validate_ethereum_address(address: str) -> bool:
    """
    Validate an Ethereum address using Web3 utilities.
    
    Args:
        address: Address string to validate
        
    Returns:
        bool: True if address is valid, False otherwise
    """
    if not is_web3_available() or is_address is None:
        # Fallback validation without Web3
        return (
            isinstance(address, str) and 
            address.startswith('0x') and 
            len(address) == 42 and
            all(c in '0123456789abcdefABCDEF' for c in address[2:])
        )
    
    try:
        return is_address(address)
    except Exception:
        return False


def to_checksum_ethereum_address(address: str) -> Optional[str]:
    """
    Convert address to checksum format using Web3 utilities.
    
    Args:
        address: Address string to convert
        
    Returns:
        Checksum address if valid, None otherwise
    """
    if not is_web3_available() or is_address is None or to_checksum_address is None:
        # Return original address if Web3 not available
        return address if validate_ethereum_address(address) else None
    
    try:
        if is_address(address):
            return to_checksum_address(address)
        return None
    except Exception:
        return None


def get_web3_version() -> Optional[str]:
    """
    Get the installed Web3 version if available.
    
    Returns:
        Web3 version string if available, None otherwise
    """
    if not is_web3_available():
        return None
    
    try:
        import web3
        return getattr(web3, '__version__', None)
    except Exception:
        return None


def test_web3_connection(rpc_url: str, require_poa: bool = False) -> bool:
    """
    Test a Web3 connection to an RPC endpoint.
    
    Args:
        rpc_url: RPC URL to test
        require_poa: Whether to require POA middleware (for Base network)
        
    Returns:
        bool: True if connection successful, False otherwise
    """
    if not is_web3_available():
        return False
    
    try:
        w3 = create_web3_instance(rpc_url, inject_poa=require_poa)
        if not w3:
            return False
        
        # Test basic connection
        is_connected = w3.is_connected()
        
        if is_connected:
            logger.debug(f"Web3 connection test successful: {rpc_url}")
        else:
            logger.warning(f"Web3 connection test failed: {rpc_url}")
        
        return is_connected
        
    except Exception as e:
        logger.debug(f"Web3 connection test failed for {rpc_url}: {e}")
        return False


def format_wei_to_ether(wei_amount: Union[int, str]) -> str:
    """
    Convert Wei to Ether format.
    
    Args:
        wei_amount: Amount in Wei
        
    Returns:
        Formatted Ether amount as string
    """
    if not is_web3_available() or Web3 is None:
        # Fallback calculation
        try:
            wei_int = int(wei_amount)
            ether = wei_int / 10**18
            return f"{ether:.6f}"
        except (ValueError, TypeError):
            return "0.0"
    
    try:
        # Convert to string explicitly to satisfy type checker
        result = Web3.from_wei(int(wei_amount), 'ether')
        # Handle Decimal return type from Web3.from_wei
        if isinstance(result, Decimal):
            return str(result)
        return str(result)
    except Exception:
        return "0.0"


def format_ether_to_wei(ether_amount: Union[float, str]) -> int:
    """
    Convert Ether to Wei format.
    
    Args:
        ether_amount: Amount in Ether
        
    Returns:
        Amount in Wei as integer
    """
    if not is_web3_available() or Web3 is None:
        # Fallback calculation
        try:
            ether_float = float(ether_amount)
            wei = int(ether_float * 10**18)
            return wei
        except (ValueError, TypeError):
            return 0
    
    try:
        wei_result = Web3.to_wei(ether_amount, 'ether')
        return int(wei_result)
    except Exception:
        return 0


def get_web3_status() -> Dict[str, Any]:
    """
    Get comprehensive Web3 status information.
    
    Returns:
        Dictionary with Web3 status details including POA middleware status
    """
    available, error = check_web3_availability()
    
    status = {
        'available': available,
        'error': error,
        'version': get_web3_version(),
        'poa_middleware_available': _POA_MIDDLEWARE_AVAILABLE,
        'poa_import_paths_tried': _POA_MIDDLEWARE_IMPORT_PATHS_TRIED,
        'components': {
            'Web3': Web3 is not None,
            'geth_poa_middleware': geth_poa_middleware is not None,
            'encode_defunct': encode_defunct is not None,
            'is_address': is_address is not None,
            'to_checksum_address': to_checksum_address is not None,
            'Account': Account is not None
        }
    }
    
    return status


def get_recommended_base_rpc_urls() -> List[str]:
    """
    Get list of recommended Base network RPC URLs.
    
    Returns:
        List of RPC URLs for Base mainnet
    """
    return [
        "https://mainnet.base.org",
        "https://base.llamarpc.com",
        "https://base-mainnet.public.blastapi.io",
        "https://1rpc.io/base",
    ]


def get_recommended_base_testnet_rpc_urls() -> List[str]:
    """
    Get list of recommended Base testnet (Sepolia) RPC URLs.
    
    Returns:
        List of RPC URLs for Base Sepolia testnet
    """
    return [
        "https://sepolia.base.org",
        "https://base-sepolia.public.blastapi.io",
    ]


# Initialize Web3 availability check on module import
check_web3_availability()