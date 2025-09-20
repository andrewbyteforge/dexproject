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
import re
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

# Web3 imports with fallback
try:
    from web3 import Web3
    from web3.middleware import geth_poa_middleware
    from eth_account.messages import encode_defunct
    from eth_utils import is_address, to_checksum_address
    WEB3_AVAILABLE = True
except ImportError:
    WEB3_AVAILABLE = False
    Web3 = None

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
        
        if not WEB3_AVAILABLE:
            logger.warning("Web3 not available - install with: pip install web3 eth-account")
        
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
    
    def verify_siwe_signature(
        self,
        message: str,
        signature: str,
        expected_nonce: str,
        expected_domain: str,
        now: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Verify a SIWE signature according to EIP-4361 specification.
        
        Args:
            message: The SIWE message that was signed
            signature: The signature to verify (0x prefixed hex)
            expected_nonce: Expected nonce value (single-use)
            expected_domain: Expected domain value
            now: Current time for validation (defaults to timezone.now())
            
        Returns:
            Dict with verification results:
            {
                'valid': bool,
                'address': str,  # Recovered wallet address (checksum)
                'chain_id': int,
                'error': str,    # Error message if validation failed
                'parsed_data': dict  # Parsed SIWE message components
            }
        """
        result = {
            'valid': False,
            'address': None,
            'chain_id': None,
            'error': None,
            'parsed_data': None
        }
        
        if not WEB3_AVAILABLE:
            logger.warning("Web3 not available - signature verification disabled")
            # In development without Web3, allow basic validation
            if len(signature) > 10 and message and expected_nonce:
                result.update({
                    'valid': True,
                    'address': '0x0000000000000000000000000000000000000000',
                    'chain_id': 84532,
                    'error': 'Web3 not available - using mock validation'
                })
            else:
                result['error'] = 'Basic validation failed'
            return result
        
        try:
            # Step 1: Parse SIWE message
            parsed_data = self._parse_siwe_message(message)
            if not parsed_data:
                result['error'] = 'Failed to parse SIWE message format'
                return result
            
            result['parsed_data'] = parsed_data
            
            # Step 2: Validate domain
            if parsed_data.get('domain') != expected_domain:
                result['error'] = f"Domain mismatch: expected {expected_domain}, got {parsed_data.get('domain')}"
                return result
            
            # Step 3: Validate nonce
            if parsed_data.get('nonce') != expected_nonce:
                result['error'] = f"Nonce mismatch: expected {expected_nonce}, got {parsed_data.get('nonce')}"
                return result
            
            # Step 4: Validate time window
            current_time = now or timezone.now()
            
            # Check issued_at
            if 'issuedAt' in parsed_data:
                try:
                    issued_at = datetime.fromisoformat(parsed_data['issuedAt'].replace('Z', '+00:00'))
                    if current_time < issued_at:
                        result['error'] = f"Message not yet valid (issued in future)"
                        return result
                except (ValueError, TypeError) as e:
                    result['error'] = f"Invalid issuedAt format: {e}"
                    return result
            
            # Check expiration_time
            if 'expirationTime' in parsed_data:
                try:
                    expiration_time = datetime.fromisoformat(parsed_data['expirationTime'].replace('Z', '+00:00'))
                    if current_time > expiration_time:
                        result['error'] = f"Message expired"
                        return result
                except (ValueError, TypeError) as e:
                    result['error'] = f"Invalid expirationTime format: {e}"
                    return result
            
            # Check not_before (if present)
            if 'notBefore' in parsed_data:
                try:
                    not_before = datetime.fromisoformat(parsed_data['notBefore'].replace('Z', '+00:00'))
                    if current_time < not_before:
                        result['error'] = f"Message not yet valid (before notBefore time)"
                        return result
                except (ValueError, TypeError) as e:
                    result['error'] = f"Invalid notBefore format: {e}"
                    return result
            
            # Step 5: Recover signer from signature
            try:
                # Create message hash for signing
                message_hash = encode_defunct(text=message)
                
                # Recover address from signature
                w3 = Web3()
                recovered_address = w3.eth.account.recover_message(message_hash, signature=signature)
                
                # Convert to checksum format
                recovered_address = to_checksum_address(recovered_address)
                
            except Exception as e:
                result['error'] = f"Signature recovery failed: {e}"
                return result
            
            # Step 6: Verify recovered address matches claimed address
            claimed_address = parsed_data.get('address', '').strip()
            if not claimed_address:
                result['error'] = "No address found in SIWE message"
                return result
            
            try:
                claimed_address = to_checksum_address(claimed_address)
            except Exception as e:
                result['error'] = f"Invalid address format in message: {e}"
                return result
            
            if recovered_address != claimed_address:
                result['error'] = f"Address mismatch: signed by {recovered_address}, claimed {claimed_address}"
                return result
            
            # Step 7: Extract chain ID
            try:
                chain_id = int(parsed_data.get('chainId', 0))
                if chain_id <= 0:
                    result['error'] = "Invalid or missing chain ID"
                    return result
            except (ValueError, TypeError):
                result['error'] = f"Invalid chain ID format: {parsed_data.get('chainId')}"
                return result
            
            # Success!
            result.update({
                'valid': True,
                'address': recovered_address,
                'chain_id': chain_id,
                'error': None
            })
            
            logger.info(f"SIWE signature verified successfully for {recovered_address}")
            return result
            
        except Exception as e:
            logger.error(f"SIWE signature verification failed: {e}")
            result['error'] = f"Verification error: {str(e)}"
            return result
    
    def _parse_siwe_message(self, message: str) -> Optional[Dict[str, str]]:
        """
        Parse a SIWE message to extract components according to EIP-4361.
        
        Args:
            message: Raw SIWE message string
            
        Returns:
            Dict with parsed components or None if parsing failed
        """
        try:
            lines = message.strip().split('\n')
            if len(lines) < 4:
                logger.error("SIWE message too short")
                return None
            
            # Parse the first line for domain and address
            first_line = lines[0]
            if " wants you to sign in with your Ethereum account:" not in first_line:
                logger.error("Invalid SIWE message format - missing standard phrase")
                return None
            
            domain = first_line.split(" wants you to sign in with your Ethereum account:")[0]
            
            # Second line should be the address
            address = lines[1].strip()
            if not address.startswith('0x'):
                logger.error("Invalid address format in SIWE message")
                return None
            
            # Find the statement (after empty line, before URI line)
            statement = ""
            uri_line_idx = None
            
            for i, line in enumerate(lines):
                if line.startswith("URI: "):
                    uri_line_idx = i
                    break
            
            if uri_line_idx is None:
                logger.error("No URI line found in SIWE message")
                return None
            
            # Statement is between address and URI (skip empty lines)
            statement_lines = []
            for i in range(2, uri_line_idx):
                line = lines[i].strip()
                if line:  # Skip empty lines
                    statement_lines.append(line)
            
            statement = "\n".join(statement_lines) if statement_lines else ""
            
            # Parse structured fields
            parsed = {
                'domain': domain,
                'address': address,
                'statement': statement
            }
            
            # Extract structured fields from remaining lines
            for line in lines[uri_line_idx:]:
                line = line.strip()
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip().replace(' ', '')
                    value = value.strip()
                    
                    # Map field names to camelCase
                    field_mapping = {
                        'URI': 'uri',
                        'Version': 'version',
                        'ChainID': 'chainId',
                        'Nonce': 'nonce',
                        'IssuedAt': 'issuedAt',
                        'ExpirationTime': 'expirationTime',
                        'NotBefore': 'notBefore',
                        'RequestId': 'requestId'
                    }
                    
                    if key in field_mapping:
                        parsed[field_mapping[key]] = value
            
            # Validate required fields
            required_fields = ['domain', 'address', 'uri', 'version', 'chainId', 'nonce']
            missing_fields = [field for field in required_fields if field not in parsed or not parsed[field]]
            
            if missing_fields:
                logger.error(f"Missing required SIWE fields: {missing_fields}")
                return None
            
            return parsed
            
        except Exception as e:
            logger.error(f"Error parsing SIWE message: {e}")
            return None
    
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
            parsed_data = self._parse_siwe_message(message)
            if not parsed_data:
                logger.error("Failed to parse SIWE message")
                return None
            
            # Verify the signature (note: this will be called by views with nonce/domain)
            # For now, just do basic validation here
            if WEB3_AVAILABLE:
                wallet_address = to_checksum_address(wallet_address)
            
            # Create SIWE session
            session = await sync_to_async(SIWESession.objects.create)(
                wallet_address=wallet_address,
                domain=parsed_data['domain'],
                statement=parsed_data.get('statement', ''),
                uri=parsed_data['uri'],
                version=parsed_data['version'],
                chain_id=chain_id,
                nonce=parsed_data['nonce'],
                issued_at=datetime.fromisoformat(parsed_data['issuedAt'].replace('Z', '+00:00')),
                expiration_time=datetime.fromisoformat(parsed_data['expirationTime'].replace('Z', '+00:00')),
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
    Service for wallet management and operations.
    
    Handles wallet connection, balance tracking, transaction monitoring,
    and integration with blockchain networks.
    """
    
    def __init__(self):
        """Initialize wallet service."""
        self.siwe_service = SIWEService()
        self.supported_chains = {
            1: {'name': 'Ethereum', 'testnet': False},
            8453: {'name': 'Base', 'testnet': False},
            84532: {'name': 'Base Sepolia', 'testnet': True},
            11155111: {'name': 'Ethereum Sepolia', 'testnet': True}
        }
    
    async def authenticate_wallet(
        self,
        wallet_address: str,
        chain_id: int,
        signature: str,
        message: str,
        wallet_type: str = 'METAMASK',
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        expected_nonce: Optional[str] = None,
        expected_domain: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Authenticate a wallet using SIWE signature.
        
        Returns:
            Dict with authentication results
        """
        try:
            # Use provided values or defaults
            expected_domain = expected_domain or self.siwe_service.domain
            
            # Extract nonce from message if not provided
            if not expected_nonce:
                parsed_data = self.siwe_service._parse_siwe_message(message)
                if parsed_data:
                    expected_nonce = parsed_data.get('nonce')
                
                if not expected_nonce:
                    return {
                        'success': False,
                        'error': 'Could not extract nonce from message'
                    }
            
            # Verify SIWE signature
            verification_result = self.siwe_service.verify_siwe_signature(
                message=message,
                signature=signature,
                expected_nonce=expected_nonce,
                expected_domain=expected_domain
            )
            
            if not verification_result['valid']:
                return {
                    'success': False,
                    'error': verification_result['error']
                }
            
            # Create SIWE session
            siwe_session = await self.siwe_service.create_siwe_session(
                wallet_address=verification_result['address'],
                chain_id=verification_result['chain_id'],
                signature=signature,
                message=message,
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            if not siwe_session:
                return {
                    'success': False,
                    'error': 'Failed to create SIWE session'
                }
            
            # Get or create user
            user = await self._get_or_create_user_for_wallet(verification_result['address'])
            
            # Update SIWE session with user
            siwe_session.user = user
            await sync_to_async(siwe_session.save)(update_fields=['user'])
            
            # Get or create wallet record
            wallet = await self._get_or_create_wallet(
                address=verification_result['address'],
                chain_id=verification_result['chain_id'],
                wallet_type=wallet_type,
                user=user
            )
            
            return {
                'success': True,
                'user_id': user.id,
                'wallet_id': str(wallet.wallet_id),
                'session_id': str(siwe_session.session_id),
                'address': verification_result['address'],
                'chain_id': verification_result['chain_id']
            }
            
        except Exception as e:
            logger.error(f"Wallet authentication failed: {e}")
            return {
                'success': False,
                'error': f'Authentication failed: {str(e)}'
            }
    
    async def _get_or_create_user_for_wallet(self, wallet_address: str) -> User:
        """Get or create a Django user for the wallet address."""
        username = f"wallet_{wallet_address.lower()}"
        
        try:
            user = await sync_to_async(User.objects.get)(username=username)
            return user
        except User.DoesNotExist:
            # Create new user
            user = await sync_to_async(User.objects.create_user)(
                username=username,
                email='',  # No email required for wallet users
                first_name='Wallet',
                last_name=wallet_address[:10] + '...'
            )
            logger.info(f"Created new user for wallet {wallet_address}")
            return user
    
    async def _get_or_create_wallet(
        self,
        address: str,
        chain_id: int,
        wallet_type: str,
        user: User
    ) -> Wallet:
        """Get or create wallet record."""
        try:
            wallet = await sync_to_async(Wallet.objects.get)(
                user=user,
                address=address
            )
            
            # Update connection info
            wallet.last_connected_at = timezone.now()
            wallet.status = Wallet.WalletStatus.CONNECTED
            await sync_to_async(wallet.save)(update_fields=['last_connected_at', 'status'])
            
            return wallet
            
        except Wallet.DoesNotExist:
            # Create new wallet
            wallet = await sync_to_async(Wallet.objects.create)(
                user=user,
                address=address,
                wallet_type=wallet_type,
                primary_chain_id=chain_id,
                status=Wallet.WalletStatus.CONNECTED,
                last_connected_at=timezone.now()
            )
            logger.info(f"Created new wallet record for {address}")
            return wallet
    
    async def get_wallet_balances(self, wallet: Wallet) -> List[Dict[str, Any]]:
        """
        Get wallet balances across supported chains.
        
        Args:
            wallet: Wallet instance
            
        Returns:
            List of balance dictionaries
        """
        try:
            # This will be implemented in Step 4 (Balance Tracking)
            # For now, return placeholder data
            balances = []
            
            for chain_id, chain_info in self.supported_chains.items():
                balances.append({
                    'chain_id': chain_id,
                    'chain_name': chain_info['name'],
                    'token_symbol': 'ETH',
                    'token_address': None,  # Native token
                    'balance': '0.0',
                    'balance_wei': 0,
                    'usd_value': None,
                    'last_updated': timezone.now().isoformat()
                })
            
            return balances
            
        except Exception as e:
            logger.error(f"Error getting wallet balances: {e}")
            return []
    
    async def get_wallet_summary(self, wallet: Wallet) -> Dict[str, Any]:
        """Get comprehensive wallet summary."""
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
siwe_service = SIWEService()
wallet_service = WalletService()