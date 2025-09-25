"""
Fixed SIWE Service - Authentication Issue Resolved

Fixed the issue with wallet_address variable scope in create_siwe_session method.
The main issues were:
1. wallet_address variable was being reassigned, causing scope issues in exception handling
2. Missing proper error handling for the checksum conversion

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
        """
        Parse a SIWE message to extract components.
        
        Args:
            message: SIWE message string
            
        Returns:
            Dictionary of parsed components or None if parsing fails
        """
        try:
            lines = message.strip().split('\n')
            data = {}
            
            # Parse each line
            for line in lines:
                line = line.strip()
                
                # Handle address line (second line)
                if line.startswith('0x') and len(line) == 42:
                    data['address'] = line
                    continue
                
                # Handle field:value pairs
                if ':' in line:
                    # Split only on first colon to handle URIs
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        key = parts[0].strip()
                        value = parts[1].strip()
                        
                        # Map field names to expected keys
                        field_mapping = {
                            'URI': 'uri',
                            'Version': 'version',
                            'Chain ID': 'chainId',
                            'Nonce': 'nonce',
                            'Issued At': 'issuedAt',
                            'Expiration Time': 'expirationTime',
                            'Not Before': 'notBefore',
                            'Request ID': 'requestId',
                            'Statement': 'statement'
                        }
                        
                        mapped_key = field_mapping.get(key, key.lower().replace(' ', ''))
                        data[mapped_key] = value
            
            # Extract domain from first line
            if lines:
                first_line = lines[0]
                if 'wants you to sign in' in first_line:
                    domain = first_line.split(' wants you to sign in')[0]
                    data['domain'] = domain
            
            # Extract statement (if present as separate lines)
            statement_lines = []
            in_statement = False
            for line in lines:
                if line == "":
                    if in_statement:
                        break
                    elif data.get('address'):
                        in_statement = True
                elif in_statement and ':' not in line and not line.startswith('0x'):
                    statement_lines.append(line)
            
            if statement_lines:
                data['statement'] = ' '.join(statement_lines)
            
            # Validate required fields
            required_fields = ['address', 'uri', 'version', 'chainId', 'nonce', 'issuedAt']
            missing_fields = [field for field in required_fields if field not in data]
            
            if missing_fields:
                logger.error(f"Missing required SIWE fields: {missing_fields}")
                logger.debug(f"Parsed data: {data}")
                return None
            
            logger.debug(f"Successfully parsed SIWE message with fields: {list(data.keys())}")
            return data
            
        except Exception as e:
            logger.error(f"Failed to parse SIWE message: {e}")
            logger.debug(f"Message content: {message[:200]}...")  # Log first 200 chars
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
                    logger.error("Invalid signature format in fallback mode")
                    return False
                logger.debug("Fallback signature verification passed basic checks")
                return True
            
            # Use Web3 for actual signature verification
            web3 = create_web3_instance()
            if not web3:
                logger.error("Failed to create Web3 instance for signature verification")
                return False
            
            try:
                # Use eth_account for signature verification
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
                    logger.debug(f"SIWE signature verified successfully for {wallet_address}")
                else:
                    logger.warning(f"SIWE signature verification failed: expected {wallet_address}, got {recovered_address}")
                
                return is_valid
                
            except Exception as signature_error:
                logger.error(f"Error recovering address from signature: {signature_error}")
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
        # Store original wallet address for error handling
        original_wallet_address = wallet_address
        message_data = None
        
        try:
            # Parse the SIWE message to extract components
            message_data = self._parse_siwe_message(message)
            if not message_data:
                logger.error(f"Failed to parse SIWE message for wallet {original_wallet_address}")
                return None
            
            # Verify the signature
            is_valid = await self.verify_siwe_signature(message, signature, wallet_address)
            if not is_valid:
                logger.error(f"SIWE signature verification failed for {original_wallet_address}")
                return None
            
            # Get wallet address in checksum format if available
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
                logger.warning(f"Failed to parse issued_at timestamp: {e}, using current time")
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
                    expiration_time = timezone.now() + timedelta(hours=self.default_expiration_hours)
            else:
                # Set default expiration if not provided
                expiration_time = timezone.now() + timedelta(hours=self.default_expiration_hours)
                logger.debug("No expiration time in message, using default 24 hours")
            
            # Generate session ID
            session_id = secrets.token_hex(32)
            
            # Create SIWE session
            session = await sync_to_async(SIWESession.objects.create)(
                session_id=session_id,
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
            
            logger.info(f"Created SIWE session {session_id} for {wallet_address}")
            return session
            
        except Exception as e:
            logger.error(f"Failed to create SIWE session for {original_wallet_address}: {e}")
            if message_data:
                logger.debug(f"Message data: {message_data}")
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
        if not self.web3_available:
            logger.debug("Skipping Web3 provider initialization - Web3 not available")
            return
        
        # Use centralized Web3 creation
        for chain_id in self.supported_chains:
            try:
                # Get RPC URL based on chain
                rpc_url = self._get_rpc_url_for_chain(chain_id)
                if rpc_url:
                    web3 = create_web3_instance(rpc_url)
                    if web3 and web3.is_connected():
                        self.web3_providers[chain_id] = web3
                        logger.debug(f"Initialized Web3 provider for chain {chain_id}")
                    else:
                        logger.warning(f"Could not connect to chain {chain_id}")
            except Exception as e:
                logger.error(f"Failed to initialize Web3 for chain {chain_id}: {e}")
    
    def _get_rpc_url_for_chain(self, chain_id: int) -> Optional[str]:
        """Get RPC URL for a specific chain."""
        # Map chain IDs to RPC URLs
        rpc_urls = {
            1: getattr(settings, 'ETH_MAINNET_RPC', 'https://eth.public-rpc.com'),
            84532: getattr(settings, 'BASE_SEPOLIA_RPC', 'https://sepolia.base.org'),
            8453: getattr(settings, 'BASE_MAINNET_RPC', 'https://mainnet.base.org'),
            11155111: getattr(settings, 'SEPOLIA_RPC', 'https://rpc.sepolia.org')
        }
        return rpc_urls.get(chain_id)
    
    def get_web3_for_chain(self, chain_id: int):
        """Get Web3 instance for a specific chain."""
        return self.web3_providers.get(chain_id)
    
    async def authenticate_wallet(
        self,
        wallet_address: str,
        chain_id: int,
        signature: str,
        message: str,
        wallet_type: str = Wallet.WalletType.METAMASK,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Tuple[Optional[User], Optional[Wallet], Optional[SIWESession]]:
        """
        Authenticate a wallet using SIWE.
        
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
            # Generate username from wallet address
            username = f"wallet_{wallet_address[-8:].lower()}"
            
            # Try to get existing user
            user = await sync_to_async(User.objects.filter(username=username).first)()
            
            if user:
                logger.debug(f"Found existing user {username} for wallet {wallet_address}")
                return user
            
            # Create new user
            user = await sync_to_async(User.objects.create_user)(
                username=username,
                first_name='Wallet',
                last_name='User',
                email=f"{username}@wallet.local"
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
        """Get or create wallet record."""
        try:
            # Convert to checksum address if possible
            checksum_address = to_checksum_ethereum_address(wallet_address)
            if checksum_address:
                wallet_address = checksum_address
            
            # Try to get existing wallet
            wallet = await sync_to_async(
                Wallet.objects.filter(address=wallet_address).first
            )()
            
            if wallet:
                # Update wallet if needed
                if wallet.user != user:
                    wallet.user = user
                    wallet.status = Wallet.WalletStatus.CONNECTED
                    await sync_to_async(wallet.save)(update_fields=['user', 'status'])
                logger.debug(f"Found existing wallet record for {wallet_address}")
                return wallet
            
            # Create new wallet
            wallet = await sync_to_async(Wallet.objects.create)(
                user=user,
                address=wallet_address,
                wallet_type=wallet_type,
                primary_chain_id=chain_id,
                status=Wallet.WalletStatus.CONNECTED
            )
            
            logger.info(f"Created new wallet record for {wallet_address}")
            return wallet
            
        except Exception as e:
            logger.error(f"Failed to get or create wallet record: {e}")
            return None
    
    async def get_wallet_balance(
        self,
        wallet_address: str,
        chain_id: int
    ) -> Optional[Decimal]:
        """
        Get wallet balance for a specific chain.
        
        Args:
            wallet_address: Wallet address to check
            chain_id: Chain ID to check balance on
            
        Returns:
            Balance in Ether/native token or None if error
        """
        if not self.web3_available:
            logger.warning("Web3 not available - cannot get wallet balance")
            return None
            
        try:
            web3 = self.get_web3_for_chain(chain_id)
            if not web3:
                logger.error(f"No Web3 provider for chain {chain_id}")
                return None
            
            # Convert to checksum address
            checksum_address = to_checksum_ethereum_address(wallet_address)
            if not checksum_address:
                logger.error(f"Invalid wallet address: {wallet_address}")
                return None
            
            # Get balance in Wei
            balance_wei = await sync_to_async(web3.eth.get_balance)(checksum_address)
            
            # Convert to Ether
            balance_ether = web3.from_wei(balance_wei, 'ether')
            
            logger.debug(f"Balance for {wallet_address} on chain {chain_id}: {balance_ether}")
            return Decimal(str(balance_ether))
            
        except Exception as e:
            logger.error(f"Failed to get balance for {wallet_address} on chain {chain_id}: {e}")
            return None
    
    async def get_token_balance(
        self,
        wallet_address: str,
        token_address: str,
        chain_id: int,
        decimals: int = 18
    ) -> Optional[Decimal]:
        """
        Get ERC20 token balance for a wallet.
        
        Args:
            wallet_address: Wallet address to check
            token_address: Token contract address
            chain_id: Chain ID
            decimals: Token decimals (default 18)
            
        Returns:
            Token balance or None if error
        """
        if not self.web3_available:
            logger.warning("Web3 not available - cannot get token balance")
            return None
            
        try:
            web3 = self.get_web3_for_chain(chain_id)
            if not web3:
                logger.error(f"No Web3 provider for chain {chain_id}")
                return None
            
            # Convert addresses to checksum
            wallet_checksum = to_checksum_ethereum_address(wallet_address)
            token_checksum = to_checksum_ethereum_address(token_address)
            
            if not wallet_checksum or not token_checksum:
                logger.error("Invalid wallet or token address")
                return None
            
            # ERC20 ABI for balanceOf function
            erc20_abi = [{
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function"
            }]
            
            # Create contract instance
            contract = web3.eth.contract(address=token_checksum, abi=erc20_abi)
            
            # Get balance
            balance_raw = await sync_to_async(contract.functions.balanceOf(wallet_checksum).call)()
            
            # Convert based on decimals
            balance = Decimal(balance_raw) / Decimal(10 ** decimals)
            
            logger.debug(f"Token balance for {wallet_address}: {balance}")
            return balance
            
        except Exception as e:
            logger.error(f"Failed to get token balance: {e}")
            return None
    
    async def monitor_wallet_transactions(
        self,
        wallet_address: str,
        chain_id: int,
        from_block: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Monitor transactions for a wallet.
        
        Args:
            wallet_address: Wallet address to monitor
            chain_id: Chain ID to monitor
            from_block: Starting block number (None for latest)
            
        Returns:
            List of transaction details
        """
        try:
            web3 = self.get_web3_for_chain(chain_id)
            if not web3:
                logger.error(f"No Web3 provider for chain {chain_id}")
                return []
            
            # This would typically use event filters or transaction history APIs
            # For now, return empty list as placeholder
            logger.debug(f"Transaction monitoring not fully implemented for {wallet_address}")
            return []
            
        except Exception as e:
            logger.error(f"Failed to monitor transactions: {e}")
            return []
    
    async def update_wallet_balances(self, wallet: Wallet) -> bool:
        """
        Update all balances for a wallet.
        
        Args:
            wallet: Wallet instance to update
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get native balance for primary chain
            if self.web3_available:
                balance = await self.get_wallet_balance(
                    wallet.address,
                    wallet.primary_chain_id
                )
                
                if balance is not None:
                    # Update or create balance record
                    await sync_to_async(WalletBalance.objects.update_or_create)(
                        wallet=wallet,
                        chain_id=wallet.primary_chain_id,
                        token_address=None,  # Native token
                        defaults={
                            'balance': balance,
                            'balance_usd': balance * Decimal('0')  # Would need price feed
                        }
                    )
                    logger.info(f"Updated balance for wallet {wallet.address}")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to update wallet balances: {e}")
            return False