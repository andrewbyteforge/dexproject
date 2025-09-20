"""
Wallet Services - Web3 Integration and SIWE Authentication

This module provides services for wallet connection, SIWE authentication,
balance tracking, and Web3 interactions. Implements secure client-side
key management with server-side verification.

Phase 5.1B Implementation:
- SIWE (EIP-4361) message generation and verification
- Web3 provider management for Base Sepolia and Ethereum
- Real-time balance tracking
- Wallet connection management
- Security and audit logging

File: dexproject/wallet/services.py
"""

import json
import secrets
import hashlib
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple
import asyncio
import logging
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from asgiref.sync import sync_to_async
import logging
logger = logging.getLogger(__name__)
# Web3 imports with fallback
# Web3 imports with enhanced fallback and modern import paths
# FIXED: Updated for web3.py v6+ import structure that handles geth_poa_middleware correctly
WEB3_AVAILABLE = False
WEB3_IMPORT_ERROR = None

try:
    from web3 import Web3
    from eth_account.messages import encode_defunct
    from eth_utils import is_address, to_checksum_address
    from eth_account import Account
    
    # Handle geth_poa_middleware import which changed in web3.py v6+
    geth_poa_middleware = None
    try:
        # Try old import path (web3.py v5 and earlier)
        from web3.middleware import geth_poa_middleware
    except ImportError:
        # New versions don't need POA middleware for most networks
        # Base networks work fine without it in web3.py v6+
        pass
    
    WEB3_AVAILABLE = True
    logger.info("✅ Web3 packages imported successfully")
    
except ImportError as e:
    WEB3_IMPORT_ERROR = str(e)
    Web3 = None
    geth_poa_middleware = None
    encode_defunct = None
    is_address = None
    to_checksum_address = None
    Account = None
    logger.warning(f"⚠️ Web3 packages not available: {e}")
    logger.warning("Install with: pip install web3 eth-account eth-utils")
except Exception as e:
    WEB3_IMPORT_ERROR = str(e)
    Web3 = None
    geth_poa_middleware = None
    encode_defunct = None
    is_address = None
    to_checksum_address = None
    Account = None
    logger.error(f"❌ Unexpected error importing Web3: {e}")


def setup_poa_middleware(w3):
    """Setup POA middleware for Base networks with compatibility for different web3.py versions."""
    if WEB3_AVAILABLE and geth_poa_middleware:
        # Only inject if geth_poa_middleware is available (older web3.py versions)
        try:
            w3.middleware_onion.inject(geth_poa_middleware, layer=0)
            logger.debug("✅ POA middleware injected")
        except Exception as e:
            logger.debug(f"POA middleware injection failed (probably not needed): {e}")
    elif WEB3_AVAILABLE:
        # Newer web3.py versions handle POA networks automatically
        logger.debug("✅ Using web3.py v6+ - POA middleware not required")
    return w3

from .models import SIWESession, Wallet, WalletBalance, WalletTransaction, WalletActivity

logger = logging.getLogger(__name__)


class SIWEService:
    """
    Service for SIWE (Sign-In with Ethereum) authentication.
    
    Handles message generation, signature verification, and session management
    according to EIP-4361 specification.
    """
    
    def __init__(self):
        """Initialize SIWE service with configuration."""
        self.domain = self._get_domain()
        self.statement = "Sign in to DEX Auto-Trading Bot"
        self.version = "1"
        self.default_expiration_hours = 24
        
    def _get_domain(self) -> str:
        """Get the domain for SIWE messages."""
        # Extract domain from Django settings or use default
        allowed_hosts = getattr(settings, 'ALLOWED_HOSTS', [])
        if allowed_hosts and allowed_hosts[0] != '*':
            return allowed_hosts[0]
        return 'localhost:8000'
    
    def generate_nonce(self) -> str:
        """Generate a cryptographically secure nonce."""
        return secrets.token_hex(16)
    
    def create_siwe_message(
        self,
        wallet_address: str,
        chain_id: int,
        nonce: Optional[str] = None,
        statement: Optional[str] = None,
        expiration_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Create a SIWE message for signing.
        
        Args:
            wallet_address: Ethereum wallet address
            chain_id: Chain ID for the network
            nonce: Optional nonce (generated if not provided)
            statement: Optional custom statement
            expiration_hours: Hours until message expires
            
        Returns:
            Dict containing SIWE message components and formatted message
        """
        try:
            if WEB3_AVAILABLE and not Web3.is_address(wallet_address):
                raise ValidationError("Invalid wallet address")
            
            if WEB3_AVAILABLE:
                wallet_address = to_checksum_address(wallet_address)
            
            nonce = nonce or self.generate_nonce()
            statement = statement or self.statement
            
            # Calculate timestamps
            issued_at = timezone.now()
            expiration_time = issued_at + timedelta(hours=expiration_hours)
            
            # Build SIWE message components
            message_data = {
                'domain': self.domain,
                'address': wallet_address,
                'statement': statement,
                'uri': f"https://{self.domain}",
                'version': self.version,
                'chainId': chain_id,
                'nonce': nonce,
                'issuedAt': issued_at.isoformat(),
                'expirationTime': expiration_time.isoformat(),
            }
            
            # Format the SIWE message according to EIP-4361
            message = self._format_siwe_message(message_data)
            
            return {
                'message': message,
                'message_data': message_data,
                'nonce': nonce,
                'issued_at': issued_at,
                'expiration_time': expiration_time
            }
        except Exception as e:
            logger.error(f"Error creating SIWE message: {e}")
            raise
    
    def _format_siwe_message(self, data: Dict[str, Any]) -> str:
        """Format SIWE message according to EIP-4361 specification."""
        message_parts = [
            f"{data['domain']} wants you to sign in with your Ethereum account:",
            data['address'],
            "",
            data['statement'],
            "",
            f"URI: {data['uri']}",
            f"Version: {data['version']}",
            f"Chain ID: {data['chainId']}",
            f"Nonce: {data['nonce']}",
            f"Issued At: {data['issuedAt']}",
            f"Expiration Time: {data['expirationTime']}"
        ]
        
        return "\n".join(message_parts)
    
    async def verify_siwe_signature(
        self,
        message: str,
        signature: str,
        wallet_address: str
    ) -> bool:
        """
        Verify a SIWE signature.
        
        Args:
            message: The SIWE message that was signed
            signature: The signature to verify
            wallet_address: Expected wallet address
            
        Returns:
            True if signature is valid, False otherwise
        """
        if not WEB3_AVAILABLE:
            logger.warning("Web3 not available - signature verification disabled")
            # In development without Web3, allow any signature
            return len(signature) > 10  # Basic validation
        
        try:
            # Create message hash
            message_hash = encode_defunct(text=message)
            
            # Recover address from signature
            w3 = Web3()
            recovered_address = w3.eth.account.recover_message(message_hash, signature=signature)
            
            # Verify the recovered address matches the expected address
            return recovered_address.lower() == wallet_address.lower()
            
        except Exception as e:
            logger.error(f"SIWE signature verification failed: {e}")
            return False
    
    async def create_siwe_session(
        self,
        wallet_address: str,
        chain_id: int,
        signature: str,
        message: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Optional[SIWESession]:
        """
        Create and verify a SIWE session.
        
        Args:
            wallet_address: Ethereum wallet address
            chain_id: Chain ID for the network
            signature: SIWE signature
            message: SIWE message that was signed
            ip_address: Client IP address
            user_agent: Client user agent
            
        Returns:
            SIWESession instance if verification successful, None otherwise
        """
        try:
            # Parse the SIWE message to extract components
            message_data = self._parse_siwe_message(message)
            if not message_data:
                logger.error("Failed to parse SIWE message")
                return None
            
            # Verify the signature
            is_valid = await self.verify_siwe_signature(message, signature, wallet_address)
            if not is_valid:
                logger.error("SIWE signature verification failed")
                return None
            
            # Get wallet address in checksum format
            if WEB3_AVAILABLE:
                wallet_address = to_checksum_address(wallet_address)
            
            # Create SIWE session
            session = await sync_to_async(SIWESession.objects.create)(
                wallet_address=wallet_address,
                domain=message_data['domain'],
                statement=message_data.get('statement', ''),
                uri=message_data['uri'],
                version=message_data['version'],
                chain_id=chain_id,
                nonce=message_data['nonce'],
                issued_at=datetime.fromisoformat(message_data['issuedAt'].replace('Z', '+00:00')),
                expiration_time=datetime.fromisoformat(message_data['expirationTime'].replace('Z', '+00:00')),
                message=message,
                signature=signature,
                status=SIWESession.SessionStatus.VERIFIED,
                ip_address=ip_address,
                user_agent=user_agent,
                verified_at=timezone.now()
            )
            
            logger.info(f"Created SIWE session for {wallet_address}")
            return session
            
        except Exception as e:
            logger.error(f"Failed to create SIWE session: {e}")
            return None
    
    def _parse_siwe_message(self, message: str) -> Optional[Dict[str, str]]:
        """Parse a SIWE message to extract components."""
        try:
            lines = message.strip().split('\n')
            if len(lines) < 8:
                return None
            
            # Extract address from second line
            address = lines[1].strip()
            
            # Extract other components
            data = {'address': address}
            
            for line in lines[4:]:  # Skip first 4 lines
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    if key == 'URI':
                        data['uri'] = value
                    elif key == 'Version':
                        data['version'] = value
                    elif key == 'Chain ID':
                        data['chainId'] = int(value)
                    elif key == 'Nonce':
                        data['nonce'] = value
                    elif key == 'Issued At':
                        data['issuedAt'] = value
                    elif key == 'Expiration Time':
                        data['expirationTime'] = value
                elif line.strip() and not data.get('statement'):
                    # Statement is before the URI line
                    data['statement'] = line.strip()
            
            # Extract domain from first line
            first_line = lines[0]
            if 'wants you to sign in' in first_line:
                domain = first_line.split(' wants you to sign in')[0]
                data['domain'] = domain
            
            return data
            
        except Exception as e:
            logger.error(f"Failed to parse SIWE message: {e}")
            return None


class WalletService:
    """
    Service for wallet management and Web3 interactions.
    
    Handles wallet connections, balance tracking, and transaction monitoring
    without storing private keys server-side.
    """
    
    def __init__(self):
        """Initialize wallet service with Web3 providers."""
        self.providers = self._initialize_providers()
        self.siwe_service = SIWEService()
        
    def _initialize_providers(self) -> Dict[int, Any]:
        """Initialize Web3 providers for supported chains."""
        providers = {}
        
        if not WEB3_AVAILABLE:
            logger.warning("Web3 not available - wallet functionality limited")
            return providers
        
        # Configuration for supported chains
        chain_configs = {
            84532: {  # Base Sepolia
                'name': 'Base Sepolia',
                'rpc_url': 'https://sepolia.base.org',
                'is_poa': True
            },
            1: {  # Ethereum Mainnet
                'name': 'Ethereum Mainnet',
                'rpc_url': f"https://eth-mainnet.g.alchemy.com/v2/{getattr(settings, 'ALCHEMY_API_KEY', 'demo')}",
                'is_poa': False
            },
            8453: {  # Base Mainnet
                'name': 'Base Mainnet',
                'rpc_url': f"https://base-mainnet.g.alchemy.com/v2/{getattr(settings, 'ALCHEMY_API_KEY', 'demo')}",
                'is_poa': True
            }
        }
        
        for chain_id, config in chain_configs.items():
            try:
                w3 = Web3(Web3.HTTPProvider(config['rpc_url']))
                
                # Add POA middleware for Base networks
                # Add POA middleware for Base networks (with compatibility check)
                if config['is_poa']:
                    w3 = setup_poa_middleware(w3)
                
                # Test connection
                if w3.is_connected():
                    providers[chain_id] = w3
                    logger.info(f"Connected to {config['name']} (Chain ID: {chain_id})")
                else:
                    logger.warning(f"Failed to connect to {config['name']}")
                    
            except Exception as e:
                logger.error(f"Error initializing provider for {config['name']}: {e}")
        
        return providers
    
    async def authenticate_wallet(
        self,
        wallet_address: str,
        chain_id: int,
        signature: str,
        message: str,
        wallet_type: str = 'METAMASK',
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Tuple[Optional[User], Optional[Wallet], Optional[SIWESession]]:
        """
        Authenticate a wallet using SIWE and create/update user and wallet records.
        
        Args:
            wallet_address: Ethereum wallet address
            chain_id: Chain ID for the network
            signature: SIWE signature
            message: SIWE message that was signed
            wallet_type: Type of wallet (METAMASK, WALLET_CONNECT, etc.)
            ip_address: Client IP address
            user_agent: Client user agent
            
        Returns:
            Tuple of (User, Wallet, SIWESession) if successful, (None, None, None) otherwise
        """
        try:
            # Create SIWE session
            siwe_session = await self.siwe_service.create_siwe_session(
                wallet_address, chain_id, signature, message, ip_address, user_agent
            )
            
            if not siwe_session:
                return None, None, None
            
            # Get or create user based on wallet address
            user = await self._get_or_create_user_for_wallet(wallet_address)
            
            # Get or create wallet record
            wallet = await self._get_or_create_wallet(
                user, wallet_address, chain_id, wallet_type
            )
            
            # Associate SIWE session with user
            siwe_session.user = user
            await sync_to_async(siwe_session.save)(update_fields=['user'])
            
            # Update wallet connection status
            await sync_to_async(wallet.update_connection_status)()
            
            # Log wallet activity
            await self._log_wallet_activity(
                wallet, user, WalletActivity.ActivityType.SIWE_LOGIN,
                "SIWE authentication successful", ip_address, user_agent,
                siwe_session=siwe_session
            )
            
            logger.info(f"Wallet authentication successful for {wallet_address}")
            return user, wallet, siwe_session
            
        except Exception as e:
            logger.error(f"Wallet authentication failed: {e}")
            return None, None, None
    
    async def _get_or_create_user_for_wallet(self, wallet_address: str) -> User:
        """Get or create a Django user for a wallet address."""
        username = f"wallet_{wallet_address.lower()}"
        
        try:
            user = await sync_to_async(User.objects.get)(username=username)
        except User.DoesNotExist:
            # Create new user
            user = await sync_to_async(User.objects.create_user)(
                username=username,
                email=f"{wallet_address.lower()}@wallet.local",
                first_name="Wallet",
                last_name=f"{wallet_address[:6]}...{wallet_address[-4:]}"
            )
            logger.info(f"Created new user for wallet {wallet_address}")
        
        return user
    
    async def _get_or_create_wallet(
        self,
        user: User,
        wallet_address: str,
        chain_id: int,
        wallet_type: str
    ) -> Wallet:
        """Get or create a wallet record."""
        if WEB3_AVAILABLE:
            wallet_address = to_checksum_address(wallet_address)
        
        try:
            wallet = await sync_to_async(Wallet.objects.get)(
                user=user, address=wallet_address
            )
            # Update connection info
            wallet.primary_chain_id = chain_id
            wallet.wallet_type = wallet_type
            await sync_to_async(wallet.save)(
                update_fields=['primary_chain_id', 'wallet_type', 'updated_at']
            )
        except Wallet.DoesNotExist:
            # Create new wallet
            wallet = await sync_to_async(Wallet.objects.create)(
                user=user,
                name=f"Wallet {wallet_address[:10]}...",
                address=wallet_address,
                wallet_type=wallet_type,
                primary_chain_id=chain_id,
                supported_chains=[chain_id]
            )
            logger.info(f"Created new wallet record for {wallet_address}")
        
        return wallet
    
    async def get_wallet_balances(
        self,
        wallet: Wallet,
        chain_id: Optional[int] = None,
        force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get wallet balances, optionally refreshing from blockchain.
        
        Args:
            wallet: Wallet instance
            chain_id: Specific chain ID to fetch (None for all supported chains)
            force_refresh: Whether to fetch fresh data from blockchain
            
        Returns:
            List of balance dictionaries
        """
        try:
            chains_to_check = [chain_id] if chain_id else wallet.supported_chains
            
            for chain in chains_to_check:
                if force_refresh or await self._should_refresh_balances(wallet, chain):
                    await self._refresh_wallet_balances(wallet, chain)
            
            # Return current balances from database
            if chain_id:
                balances = await sync_to_async(list)(
                    wallet.balances.filter(chain_id=chain_id).order_by('-usd_value')
                )
            else:
                balances = await sync_to_async(list)(
                    wallet.balances.all().order_by('-usd_value')
                )
            
            # Convert to dict format
            balance_list = []
            for balance in balances:
                balance_list.append({
                    'token_symbol': balance.token_symbol,
                    'token_name': balance.token_name,
                    'balance_formatted': str(balance.balance_formatted),
                    'usd_value': str(balance.usd_value) if balance.usd_value else None,
                    'chain_id': balance.chain_id,
                    'last_updated': balance.last_updated.isoformat(),
                    'is_stale': balance.is_stale
                })
            
            return balance_list
            
        except Exception as e:
            logger.error(f"Error getting wallet balances: {e}")
            return []
    
    async def _should_refresh_balances(self, wallet: Wallet, chain_id: int) -> bool:
        """Check if wallet balances should be refreshed."""
        try:
            latest_balance = await sync_to_async(
                wallet.balances.filter(chain_id=chain_id).order_by('-last_updated').first
            )()
            
            if not latest_balance:
                return True
            
            # Refresh if data is older than 5 minutes
            age_threshold = timezone.now() - timedelta(minutes=5)
            return latest_balance.last_updated < age_threshold
            
        except Exception:
            return True
    
    async def _refresh_wallet_balances(self, wallet: Wallet, chain_id: int) -> None:
        """Refresh wallet balances from blockchain."""
        if not WEB3_AVAILABLE or chain_id not in self.providers:
            logger.warning(f"Cannot refresh balances - Web3 not available or no provider for chain {chain_id}")
            return
        
        w3 = self.providers[chain_id]
        
        try:
            # Get ETH balance
            eth_balance_wei = w3.eth.get_balance(wallet.address)
            await self._update_balance_record(
                wallet, chain_id, 'ETH', 'ETH', 'Ethereum', 18, str(eth_balance_wei)
            )
            
            logger.info(f"Refreshed balances for wallet {wallet.address} on chain {chain_id}")
            
        except Exception as e:
            logger.error(f"Error refreshing balances: {e}")
    
    async def _update_balance_record(
        self,
        wallet: Wallet,
        chain_id: int,
        token_address: str,
        token_symbol: str,
        token_name: str,
        token_decimals: int,
        balance_wei: str,
        usd_value: Optional[Decimal] = None
    ) -> None:
        """Update or create a balance record."""
        try:
            balance, created = await sync_to_async(WalletBalance.objects.update_or_create)(
                wallet=wallet,
                chain_id=chain_id,
                token_address=token_address,
                defaults={
                    'token_symbol': token_symbol,
                    'token_name': token_name,
                    'token_decimals': token_decimals,
                    'balance_wei': balance_wei,
                    'balance_formatted': Decimal(balance_wei) / (10 ** token_decimals),
                    'usd_value': usd_value,
                    'last_updated': timezone.now(),
                    'is_stale': False,
                    'update_error': ''
                }
            )
            
            if created:
                logger.debug(f"Created new balance record for {token_symbol}")
            else:
                logger.debug(f"Updated balance record for {token_symbol}")
                
        except Exception as e:
            logger.error(f"Error updating balance record: {e}")
    
    async def _log_wallet_activity(
        self,
        wallet: Optional[Wallet],
        user: Optional[User],
        activity_type: str,
        description: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        siwe_session: Optional[SIWESession] = None,
        transaction: Optional[WalletTransaction] = None,
        was_successful: bool = True,
        error_message: str = '',
        additional_data: Optional[Dict] = None
    ) -> None:
        """Log wallet activity for audit purposes."""
        try:
            await sync_to_async(WalletActivity.objects.create)(
                wallet=wallet,
                user=user,
                activity_type=activity_type,
                description=description,
                ip_address=ip_address,
                user_agent=user_agent,
                siwe_session=siwe_session,
                transaction=transaction,
                was_successful=was_successful,
                error_message=error_message,
                data=additional_data or {}
            )
        except Exception as e:
            logger.error(f"Error logging wallet activity: {e}")
    
    async def disconnect_wallet(
        self,
        wallet: Wallet,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> bool:
        """Disconnect a wallet and invalidate sessions."""
        try:
            # Mark wallet as disconnected
            await sync_to_async(wallet.disconnect)()
            
            # Revoke active SIWE sessions for this wallet
            active_sessions = wallet.user.siwe_sessions.filter(
                wallet_address=wallet.address,
                status=SIWESession.SessionStatus.VERIFIED
            )
            
            await sync_to_async(active_sessions.update)(
                status=SIWESession.SessionStatus.REVOKED
            )
            
            # Log disconnection activity
            await self._log_wallet_activity(
                wallet, wallet.user, WalletActivity.ActivityType.DISCONNECTION,
                "Wallet disconnected", ip_address, user_agent
            )
            
            logger.info(f"Wallet {wallet.address} disconnected successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error disconnecting wallet: {e}")
            return False
    
    async def get_wallet_summary(self, wallet: Wallet) -> Dict[str, Any]:
        """Get a summary of wallet information and balances."""
        try:
            # Get recent balances
            balances = await self.get_wallet_balances(wallet)
            
            # Calculate total USD value
            total_usd = sum(
                Decimal(balance['usd_value']) for balance in balances 
                if balance['usd_value'] is not None
            )
            
            # Get recent transactions
            recent_transactions = await sync_to_async(list)(
                wallet.transactions.filter(
                    status__in=['CONFIRMED', 'PENDING']
                ).order_by('-created_at')[:5]
            )
            
            # Get connection status
            is_connected = wallet.status == Wallet.WalletStatus.CONNECTED
            
            return {
                'wallet_id': str(wallet.wallet_id),
                'address': wallet.address,
                'name': wallet.get_display_name(),
                'wallet_type': wallet.wallet_type,
                'is_connected': is_connected,
                'primary_chain_id': wallet.primary_chain_id,
                'supported_chains': wallet.supported_chains,
                'total_usd_value': str(total_usd),
                'balances': balances,
                'recent_transactions': [
                    {
                        'transaction_hash': t.transaction_hash,
                        'transaction_type': t.transaction_type,
                        'status': t.status,
                        'created_at': t.created_at.isoformat()
                    }
                    for t in recent_transactions
                ],
                'last_connected_at': wallet.last_connected_at.isoformat() if wallet.last_connected_at else None,
                'trading_enabled': wallet.is_trading_enabled
            }
            
        except Exception as e:
            logger.error(f"Error getting wallet summary: {e}")
            return {}


# Initialize service instances
wallet_service = WalletService()
siwe_service = SIWEService()