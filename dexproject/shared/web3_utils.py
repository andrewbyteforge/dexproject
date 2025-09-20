"""
Shared Web3 Utilities - Centralized Web3 Import and Availability Check

This module provides centralized Web3 import handling to avoid duplicate
warning messages throughout the project. All other modules should import
Web3 utilities from here instead of directly importing web3.

File: dexproject/shared/web3_utils.py
"""

import logging
from typing import Optional, Any, Dict, Union, Tuple
from functools import lru_cache

logger = logging.getLogger(__name__)

# Global Web3 availability check - cached to avoid repeated checks
_WEB3_AVAILABILITY_CHECKED = False
_WEB3_AVAILABLE = False
_WEB3_IMPORT_ERROR = None

# Web3 components - will be None if not available
Web3 = None
geth_poa_middleware = None
encode_defunct = None
is_address = None
to_checksum_address = None
Account = None


@lru_cache(maxsize=1)
def check_web3_availability() -> Tuple[bool, Optional[str]]:
    """
    Check Web3 package availability with caching.
    
    Returns:
        Tuple[bool, Optional[str]]: (is_available, error_message)
    """
    global _WEB3_AVAILABILITY_CHECKED, _WEB3_AVAILABLE, _WEB3_IMPORT_ERROR
    global Web3, geth_poa_middleware, encode_defunct, is_address, to_checksum_address, Account
    
    if _WEB3_AVAILABILITY_CHECKED:
        return _WEB3_AVAILABLE, _WEB3_IMPORT_ERROR
    
    try:
        # Import all Web3 components
        from web3 import Web3 as _Web3
        
        # Try new Web3 v7+ import path first, fallback to old path
        try:
            from web3.middleware.geth_poa import geth_poa_middleware as _geth_poa_middleware
        except ImportError:
            try:
                from web3.middleware import geth_poa_middleware as _geth_poa_middleware
            except ImportError:
                # Web3 installed but no POA middleware available
                _geth_poa_middleware = None
        
        from eth_account.messages import encode_defunct as _encode_defunct
        from eth_utils import is_address as _is_address, to_checksum_address as _to_checksum_address
        from eth_account import Account as _Account
        
        # Assign to global variables
        Web3 = _Web3
        geth_poa_middleware = _geth_poa_middleware
        encode_defunct = _encode_defunct
        is_address = _is_address
        to_checksum_address = _to_checksum_address
        Account = _Account
        
        # Test basic functionality
        w3 = Web3()
        test_address = '0x742d35Cc6486C3D5C2d2AD6589e78aa27D4cc8bF'
        is_address(test_address)
        to_checksum_address(test_address)
        
        _WEB3_AVAILABLE = True
        _WEB3_IMPORT_ERROR = None
        
        # Log success only once with version info
        try:
            # Try to get version from web3 module
            import web3
            version = getattr(web3, '__version__', 'Unknown')
            logger.info(f"Web3 packages successfully imported and validated (v{version})")
        except Exception:
            logger.info("Web3 packages successfully imported and validated")
        
        if not geth_poa_middleware:
            logger.warning("POA middleware not available - Base network support may be limited")
        
    except ImportError as e:
        _WEB3_AVAILABLE = False
        _WEB3_IMPORT_ERROR = str(e)
        
        # Log warning only once
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


def get_web3_error() -> Optional[str]:
    """
    Get Web3 import error message if any.
    
    Returns:
        Optional[str]: Error message if Web3 is not available, None otherwise
    """
    _, error = check_web3_availability()
    return error


def require_web3():
    """
    Ensure Web3 is available, raise exception if not.
    
    Raises:
        ImportError: If Web3 packages are not available
    """
    if not is_web3_available():
        error = get_web3_error()
        raise ImportError(f"Web3 packages required but not available: {error}")


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
        'available': _WEB3_AVAILABLE
    }


def create_web3_instance(rpc_url: Optional[str] = None) -> Optional[Any]:
    """
    Create a Web3 instance if available.
    
    Args:
        rpc_url: Optional RPC URL for the provider
        
    Returns:
        Web3 instance if available, None otherwise
    """
    if not is_web3_available():
        return None
    
    try:
        if rpc_url:
            from web3.providers import HTTPProvider
            provider = HTTPProvider(rpc_url)
            return Web3(provider)
        else:
            return Web3()
    except Exception as e:
        logger.error(f"Failed to create Web3 instance: {e}")
        return None


def validate_ethereum_address(address: str) -> bool:
    """
    Validate an Ethereum address using Web3 utilities.
    
    Args:
        address: Address string to validate
        
    Returns:
        bool: True if address is valid, False otherwise
    """
    if not is_web3_available():
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
    if not is_web3_available():
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
        # Try to get version from web3 module
        import web3
        return getattr(web3, '__version__', None)
    except Exception:
        return None


def test_web3_connection(rpc_url: str) -> bool:
    """
    Test a Web3 connection to an RPC endpoint.
    
    Args:
        rpc_url: RPC URL to test
        
    Returns:
        bool: True if connection successful, False otherwise
    """
    if not is_web3_available():
        return False
    
    try:
        w3 = create_web3_instance(rpc_url)
        if not w3:
            return False
        
        # Test basic connection
        return w3.is_connected()
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
    if not is_web3_available():
        # Fallback calculation
        try:
            wei_int = int(wei_amount)
            ether = wei_int / 10**18
            return f"{ether:.6f}"
        except (ValueError, TypeError):
            return "0.0"
    
    try:
        return Web3.from_wei(int(wei_amount), 'ether')
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
    if not is_web3_available():
        # Fallback calculation
        try:
            ether_float = float(ether_amount)
            wei = int(ether_float * 10**18)
            return wei
        except (ValueError, TypeError):
            return 0
    
    try:
        return Web3.to_wei(ether_amount, 'ether')
    except Exception:
        return 0


def get_web3_status() -> Dict[str, Any]:
    """
    Get comprehensive Web3 status information.
    
    Returns:
        Dictionary with Web3 status details
    """
    available, error = check_web3_availability()
    
    status = {
        'available': available,
        'error': error,
        'version': get_web3_version(),
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


# Initialize Web3 availability check on module import
check_web3_availability()