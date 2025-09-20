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

# Use centralized Web3 utilities to avoid duplicate warnings
from shared.web3_utils import (
    is_web3_available, 
    get_web3_components, 
    create_web3_instance,
    validate_ethereum_address,
    to_checksum_ethereum_address,
    require_web3
)

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
        
        # Get Web3 components
        self.web3_components = get_web3_components()
        self.web3_available = is_web3_available()
        
        if self.web3_available:
            logger.debug("SIWE service initialized with Web3 support")
        else:
            logger.debug("SIWE service initialized in fallback mode (Web3 not available)")
        
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
            Dictionary containing message, nonce, timestamps, etc.
        """
        try:
            # Validate wallet address
            if not validate_ethereum_address(wallet_address):
                raise ValidationError(f"Invalid wallet address: {wallet_address}")
            
            # Convert to checksum format if Web3 available
            checksum_address = to_checksum_ethereum_address(wallet_address)
            if checksum_address:
                wallet_address = checksum_address
            
            # Generate components
            nonce = nonce or self.generate_nonce()
            statement = statement or self.statement
            issued_at = timezone.now()
            expiration_time = issued_at + timedelta(hours=expiration_hours)
            
            # Build SIWE message according to EIP-4361
            message_parts = [
                f"{self.domain} wants you to sign in with your Ethereum account:",
                wallet_address,
                "",
                statement,
                "",
                f"URI: https://{self.domain}",
                f"Version: {self.version}",
                f"Chain ID: {chain_id}",
                f"Nonce: {nonce}",
                f"Issued At: {issued_at.isoformat()}",
                f"Expiration Time: {expiration_time.isoformat()}"
            ]
            
            message = "\n".join(message_parts)
            
            logger.debug(f"Created SIWE message for {wallet_address} on chain {chain_id}")
            
            return {
                'message': message,
                'nonce': nonce,
                'issued_at': issued_at,
                'expiration_time': expiration_time,
                'domain': self.domain,
                'statement': statement,
                'wallet_address': wallet_address,
                'chain_id': chain_id
            }
            
        except Exception as e:
            logger.error(f"Failed to create SIWE message: {e}")
            raise ValidationError(f"SIWE message creation failed: {str(e)}")
    
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
        if not self.web3_available:
            logger.warning("Web3 not available - signature verification disabled for development")
            # In development without Web3, allow any signature that looks reasonable
            return (
                isinstance(signature, str) and 
                signature.startswith('0x') and 
                len(signature) >= 130  # Basic signature format check
            )
        
        try:
            # Get Web3 components
            components = self.web3_components
            encode_defunct = components['encode_defunct']
            
            # Create Web3 instance
            w3 = create_web3_instance()
            if not w3:
                logger.error("Failed to create Web3 instance for signature verification")
                return False
            
            # Create message hash
            message_hash = encode_defunct(text=message)
            
            # Recover address from signature
            recovered_address = w3.eth.account.recover_message(message_hash, signature=signature)
            
            # Verify the recovered address matches the expected address
            is_valid = recovered_address.lower() == wallet_address.lower()
            
            if is_valid:
                logger.debug(f"SIWE signature verified successfully for {wallet_address}")
            else:
                logger.warning(f"SIWE signature verification failed - expected {wallet_address}, got {recovered_address}")
            
            return is_valid
            
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
            checksum_address = to_checksum_ethereum_address(wallet_address)
            if checksum_address:
                wallet_address = checksum_address
            
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


class WalletService:
    """
    Service for wallet management and Web3 interactions.
    
    Handles wallet connections, balance tracking, and transaction monitoring
    without storing private keys server-side.
    """
    
    def __init__(self):
        """Initialize wallet service with Web3 providers."""
        self.web3_available = is_web3_available()
        self.siwe_service = SIWEService()
        self.providers = self._initialize_providers()
        
        if self.web3_available:
            logger.debug("Wallet service initialized with Web3 support")
        else:
            logger.debug("Wallet service initialized in fallback mode")
        
    def _initialize_providers(self) -> Dict[int, Any]:
        """Initialize Web3 providers for supported chains."""
        providers = {}
        
        if not self.web3_available:
            logger.debug("Web3 not available - provider initialization skipped")
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
        
        # Get Web3 components
        components = get_web3_components()
        Web3 = components['Web3']
        geth_poa_middleware = components['geth_poa_middleware']
        
        if not Web3:
            return providers
        
        for chain_id, config in chain_configs.items():
            try:
                w3 = create_web3_instance(config['rpc_url'])
                if not w3:
                    continue
                
                # Add POA middleware for Base networks
                if config['is_poa'] and geth_poa_middleware:
                    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
                
                # Test connection
                if w3.is_connected():
                    providers[chain_id] = w3
                    logger.debug(f"Connected to {config['name']} (Chain ID: {chain_id})")
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
            # Create SIWE session (includes signature verification)
            siwe_session = await self.siwe_service.create_siwe_session(
                wallet_address=wallet_address,
                chain_id=chain_id,
                signature=signature,
                message=message,
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            if not siwe_session:
                logger.warning(f"SIWE session creation failed for {wallet_address}")
                return None, None, None
            
            # Get or create user
            user = await self._get_or_create_user_for_wallet(wallet_address)
            if not user:
                logger.error(f"Failed to create user for wallet {wallet_address}")
                return None, None, None
            
            # Link user to SIWE session
            siwe_session.user = user
            await sync_to_async(siwe_session.save)(update_fields=['user'])
            
            # Get or create wallet record
            wallet = await self._get_or_create_wallet_record(
                user=user,
                wallet_address=wallet_address,
                wallet_type=wallet_type,
                chain_id=chain_id
            )
            
            if not wallet:
                logger.error(f"Failed to create wallet record for {wallet_address}")
                return None, None, None
            
            logger.info(f"Wallet authentication successful for {wallet_address}")
            return user, wallet, siwe_session
            
        except Exception as e:
            logger.error(f"Wallet authentication failed: {e}")
            return None, None, None
    
    async def _get_or_create_user_for_wallet(self, wallet_address: str) -> Optional[User]:
        """Get or create a Django user for a wallet address."""
        try:
            # Create a username based on wallet address
            username = f"wallet_{wallet_address[-8:].lower()}"
            
            # Try to get existing user
            try:
                user = await sync_to_async(User.objects.get)(username=username)
                return user
            except User.DoesNotExist:
                pass
            
            # Create new user
            user = await sync_to_async(User.objects.create)(
                username=username,
                email=f"{username}@wallet.local",
                first_name=f"Wallet {wallet_address[:6]}",
                is_active=True
            )
            
            logger.info(f"Created new user {username} for wallet {wallet_address}")
            return user
            
        except Exception as e:
            logger.error(f"Failed to get/create user for wallet {wallet_address}: {e}")
            return None
    
    async def _get_or_create_wallet_record(
        self,
        user: User,
        wallet_address: str,
        wallet_type: str,
        chain_id: int
    ) -> Optional[Wallet]:
        """Get or create a wallet record in the database."""
        try:
            # Convert to checksum address
            checksum_address = to_checksum_ethereum_address(wallet_address)
            if checksum_address:
                wallet_address = checksum_address
            
            # Try to get existing wallet
            try:
                wallet = await sync_to_async(Wallet.objects.get)(address=wallet_address)
                
                # Update connection status
                wallet.status = Wallet.WalletStatus.CONNECTED
                wallet.last_connected_at = timezone.now()
                wallet.user = user  # Ensure user is linked
                await sync_to_async(wallet.save)(
                    update_fields=['status', 'last_connected_at', 'user']
                )
                
                return wallet
                
            except Wallet.DoesNotExist:
                pass
            
            # Create new wallet record
            wallet = await sync_to_async(Wallet.objects.create)(
                user=user,
                address=wallet_address,
                wallet_type=wallet_type,
                name=f"Wallet {wallet_address[:10]}",
                primary_chain_id=chain_id,
                status=Wallet.WalletStatus.CONNECTED,
                last_connected_at=timezone.now(),
                is_trading_enabled=True,
                supported_chains=[chain_id, 84532, 1, 8453]  # Default supported chains
            )
            
            logger.info(f"Created new wallet record for {wallet_address}")
            return wallet
            
        except Exception as e:
            logger.error(f"Failed to get/create wallet record: {e}")
            return None
    
    async def get_wallet_summary(self, wallet: Wallet) -> Dict[str, Any]:
        """Get wallet summary information."""
        try:
            return {
                'wallet_id': str(wallet.wallet_id),
                'address': wallet.address,
                'name': wallet.get_display_name(),
                'wallet_type': wallet.wallet_type,
                'is_connected': wallet.status == Wallet.WalletStatus.CONNECTED,
                'primary_chain_id': wallet.primary_chain_id,
                'supported_chains': wallet.supported_chains,
                'trading_enabled': wallet.is_trading_enabled,
                'last_connected_at': wallet.last_connected_at.isoformat() if wallet.last_connected_at else None,
                'daily_limit_usd': str(wallet.daily_limit_usd) if wallet.daily_limit_usd else None,
                'per_transaction_limit_usd': str(wallet.per_transaction_limit_usd) if wallet.per_transaction_limit_usd else None
            }
        except Exception as e:
            logger.error(f"Failed to get wallet summary: {e}")
            return {}
    
    async def get_wallet_balances(self, wallet: Wallet, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Get wallet balances for all supported chains."""
        try:
            if force_refresh and self.web3_available:
                # TODO: Implement blockchain balance refresh
                logger.debug("Balance refresh requested but not yet implemented")
            
            # Get balances from database
            balances = await sync_to_async(list)(wallet.balances.all())
            
            balance_data = []
            for balance in balances:
                balance_data.append({
                    'token_symbol': balance.token_symbol,
                    'token_name': balance.token_name,
                    'balance_formatted': str(balance.balance_formatted),
                    'usd_value': str(balance.usd_value) if balance.usd_value else None,
                    'chain_id': balance.chain_id,
                    'last_updated': balance.last_updated.isoformat(),
                    'is_stale': balance.is_stale
                })
            
            return balance_data
            
        except Exception as e:
            logger.error(f"Failed to get wallet balances: {e}")
            return []


# Initialize services
siwe_service = SIWEService()
wallet_service = WalletService()

# Log initialization status
if is_web3_available():
    logger.info("Wallet services initialized with full Web3 support")
else:
    logger.info("Wallet services initialized in fallback mode (limited functionality)")