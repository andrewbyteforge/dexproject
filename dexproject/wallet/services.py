"""
Fixed SIWE Service - Parsing and Session Creation Fix

Fixed the issue with parsing SIWE messages and creating sessions.
The main issues were:
1. Missing expirationTime in parsed message data
2. Improved error handling and logging

File: dexproject/wallet/services.py (Fixed version)
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
        """
        Parse a SIWE message to extract components.
        
        Args:
            message: SIWE message string
            
        Returns:
            Dictionary with parsed components or None if parsing fails
        """
        try:
            lines = message.strip().split('\n')
            if len(lines) < 8:
                logger.error(f"SIWE message has insufficient lines: {len(lines)}")
                return None
            
            # Initialize data dictionary
            data = {}
            
            # Extract address from second line
            if len(lines) > 1:
                data['address'] = lines[1].strip()
            
            # Extract statement (line before URI, after empty line)
            statement_line = None
            for i, line in enumerate(lines):
                if line.strip() == "" and i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line and not next_line.startswith('URI:'):
                        statement_line = next_line
                        break
            
            if statement_line:
                data['statement'] = statement_line
            
            # Extract key-value pairs
            for line in lines:
                line = line.strip()
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    if key == 'URI':
                        data['uri'] = value
                    elif key == 'Version':
                        data['version'] = value
                    elif key == 'Chain ID':
                        try:
                            data['chainId'] = int(value)
                        except ValueError:
                            logger.error(f"Invalid Chain ID: {value}")
                            return None
                    elif key == 'Nonce':
                        data['nonce'] = value
                    elif key == 'Issued At':
                        data['issuedAt'] = value
                    elif key == 'Expiration Time':
                        data['expirationTime'] = value
                    elif key == 'Not Before':
                        data['notBefore'] = value
                    elif key == 'Request ID':
                        data['requestId'] = value
            
            # Extract domain from first line
            if len(lines) > 0:
                first_line = lines[0]
                if 'wants you to sign in' in first_line:
                    domain = first_line.split(' wants you to sign in')[0]
                    data['domain'] = domain
            
            # Validate required fields
            required_fields = ['address', 'uri', 'version', 'chainId', 'nonce', 'issuedAt']
            missing_fields = [field for field in required_fields if field not in data]
            
            if missing_fields:
                logger.error(f"Missing required SIWE fields: {missing_fields}")
                logger.debug(f"Parsed data: {data}")
                logger.debug(f"Original message: {message}")
                return None
            
            logger.debug(f"Successfully parsed SIWE message with fields: {list(data.keys())}")
            return data
            
        except Exception as e:
            logger.error(f"Failed to parse SIWE message: {e}")
            logger.debug(f"Message content: {message}")
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
            message: SIWE message that was signed
            signature: Signature to verify
            wallet_address: Expected wallet address
            
        Returns:
            True if signature is valid, False otherwise
        """
        try:
            if not self.web3_available:
                logger.warning("Web3 not available - using fallback signature verification")
                # In fallback mode, do basic validation but don't verify signature
                if not signature or not signature.startswith('0x') or len(signature) != 132:
                    return False
                logger.debug("Fallback signature verification passed basic checks")
                return True
            
            # Use Web3 for actual signature verification
            web3 = create_web3_instance()
            if not web3:
                logger.error("Failed to create Web3 instance for signature verification")
                return False
            
            try:
                # Encode the message properly for signature verification
                # SIWE uses personal sign which prefixes the message
                encoded_message = f"\x19Ethereum Signed Message:\n{len(message)}{message}"
                message_hash = web3.keccak(text=encoded_message)
                
                # Recover address from signature using the correct Web3 method
                recovered_address = web3.eth.account.recover_message(
                    message_hash,
                    signature=signature
                )
                
                # Compare addresses (case-insensitive)
                is_valid = recovered_address.lower() == wallet_address.lower()
                
                if is_valid:
                    logger.debug(f"SIWE signature verified successfully for {wallet_address}")
                else:
                    logger.warning(f"SIWE signature verification failed: expected {wallet_address}, got {recovered_address}")
                
                return is_valid
                
            except Exception as signature_error:
                logger.error(f"Error recovering address from signature: {signature_error}")
                
                # Try alternative method with encode_defunct
                try:
                    from eth_account.messages import encode_defunct
                    
                    # Create message hash using encode_defunct
                    message_encoded = encode_defunct(text=message)
                    recovered_address = web3.eth.account.recover_message(
                        message_encoded,
                        signature=signature
                    )
                    
                    # Compare addresses (case-insensitive)
                    is_valid = recovered_address.lower() == wallet_address.lower()
                    
                    if is_valid:
                        logger.debug(f"SIWE signature verified successfully using encode_defunct for {wallet_address}")
                    else:
                        logger.warning(f"SIWE signature verification failed using encode_defunct: expected {wallet_address}, got {recovered_address}")
                    
                    return is_valid
                    
                except Exception as alt_error:
                    logger.error(f"Alternative signature verification also failed: {alt_error}")
                    return False
            
        except Exception as e:
            logger.error(f"Error verifying SIWE signature: {e}")
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
        Create a SIWE session after verifying the signature.
        
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
            
            # Parse timestamps with better error handling
            try:
                issued_at_str = message_data['issuedAt']
                if issued_at_str.endswith('Z'):
                    issued_at_str = issued_at_str[:-1] + '+00:00'
                issued_at = datetime.fromisoformat(issued_at_str)
            except Exception as e:
                logger.error(f"Failed to parse issued_at timestamp: {e}")
                issued_at = timezone.now()
            
            # Handle expiration time - make it optional
            expiration_time = None
            if 'expirationTime' in message_data:
                try:
                    expiration_str = message_data['expirationTime']
                    if expiration_str.endswith('Z'):
                        expiration_str = expiration_str[:-1] + '+00:00'
                    expiration_time = datetime.fromisoformat(expiration_str)
                except Exception as e:
                    logger.warning(f"Failed to parse expiration_time timestamp: {e}")
                    # Set default expiration if parsing fails
                    expiration_time = timezone.now() + timedelta(hours=24)
            else:
                # Set default expiration if not provided
                expiration_time = timezone.now() + timedelta(hours=24)
                logger.info("No expiration time in message, using default 24 hours")
            
            # Create SIWE session
            session = await sync_to_async(SIWESession.objects.create)(
                wallet_address=wallet_address,
                domain=message_data.get('domain', self.domain),
                statement=message_data.get('statement', ''),
                uri=message_data.get('uri', f'https://{self.domain}'),
                version=message_data.get('version', '1'),
                chain_id=chain_id,
                nonce=message_data['nonce'],
                issued_at=issued_at,
                expiration_time=expiration_time,
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
            logger.debug(f"Message data: {message_data if 'message_data' in locals() else 'None'}")
            return None


class WalletService:
    """
    Service for wallet management and Web3 interactions.
    
    Handles wallet connections, balance tracking, and transaction monitoring
    without storing private keys server-side.
    """
    
    def __init__(self):
        """Initialize wallet service with Web3 providers."""
        self.siwe_service = SIWEService()
        
        # Initialize Web3 providers for supported chains
        self.web3_providers = {}
        self.supported_chains = {
            1: "Ethereum Mainnet",
            84532: "Base Sepolia", 
            8453: "Base Mainnet",
            11155111: "Sepolia Testnet"
        }
        
        # Get Web3 components
        self.web3_components = get_web3_components()
        self.web3_available = is_web3_available()
        
        if self.web3_available:
            self._initialize_web3_providers()
            logger.debug("Wallet service initialized with Web3 support")
        else:
            logger.debug("Wallet service initialized in fallback mode")
        
    def _initialize_web3_providers(self):
        """Initialize Web3 providers for supported chains."""
        try:
            # Initialize providers for each supported chain
            for chain_id, name in self.supported_chains.items():
                try:
                    web3_instance = create_web3_instance(chain_id)
                    if web3_instance:
                        self.web3_providers[chain_id] = web3_instance
                        logger.debug(f"Initialized Web3 provider for {name} (Chain {chain_id})")
                except Exception as e:
                    logger.warning(f"Failed to initialize Web3 provider for {name}: {e}")
                    
        except Exception as e:
            logger.error(f"Error initializing Web3 providers: {e}")
    
    async def authenticate_wallet(
        self,
        wallet_address: str,
        chain_id: int,
        signature: str,
        message: str,
        wallet_type: str = 'UNKNOWN',
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Tuple[Optional[User], Optional[Wallet], Optional[SIWESession]]:
        """
        Authenticate a wallet using SIWE signature.
        
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
            username = f"wallet_{wallet_address.lower()[-8:]}"  # Use last 8 chars for username
            
            # Try to get existing user
            try:
                user = await sync_to_async(User.objects.get)(username=username)
                logger.debug(f"Found existing user {username} for wallet {wallet_address}")
                return user
            except User.DoesNotExist:
                pass
            
            # Create new user
            user = await sync_to_async(User.objects.create_user)(
                username=username,
                email=f"{username}@wallet.local",  # Dummy email
                first_name="Wallet",
                last_name=wallet_address[:10] + "..."
            )
            
            logger.info(f"Created new user {username} for wallet {wallet_address}")
            return user
            
        except Exception as e:
            logger.error(f"Failed to get or create user for wallet {wallet_address}: {e}")
            return None
    
    async def _get_or_create_wallet_record(
        self,
        user: User,
        wallet_address: str,
        wallet_type: str,
        chain_id: int
    ) -> Optional[Wallet]:
        """Get or create a wallet record."""
        try:
            # Try to get existing wallet
            try:
                wallet = await sync_to_async(Wallet.objects.get)(
                    address=wallet_address.lower(),
                    user=user
                )
                
                # Update connection info
                wallet.last_connected_at = timezone.now()
                wallet.status = Wallet.WalletStatus.CONNECTED
                if wallet.primary_chain_id != chain_id:
                    wallet.primary_chain_id = chain_id
                
                await sync_to_async(wallet.save)()
                logger.debug(f"Updated existing wallet record for {wallet_address}")
                return wallet
                
            except Wallet.DoesNotExist:
                pass
            
            # Create new wallet
            wallet = await sync_to_async(Wallet.objects.create)(
                user=user,
                address=wallet_address.lower(),
                wallet_type=wallet_type,
                primary_chain_id=chain_id,
                status=Wallet.WalletStatus.CONNECTED,
                last_connected_at=timezone.now()
            )
            
            logger.info(f"Created new wallet record for {wallet_address}")
            return wallet
            
        except Exception as e:
            logger.error(f"Failed to get or create wallet record for {wallet_address}: {e}")
            return None


# Initialize service instances
wallet_service = WalletService()

# Export services
__all__ = [
    'SIWEService',
    'WalletService', 
    'wallet_service'
]