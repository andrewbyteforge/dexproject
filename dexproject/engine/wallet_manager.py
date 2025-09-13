"""
Enhanced Wallet Manager for DEX Auto-Trading Bot

Handles secure private key management, transaction signing, and wallet operations
with support for multiple wallet types including development, hardware, and keystore.

File: dexproject/engine/wallet_manager.py
"""

import logging
import os
import json
from typing import Dict, Any, Optional, Union, List
from decimal import Decimal
from dataclasses import dataclass
from enum import Enum
import asyncio
from pathlib import Path

from web3 import Web3
from web3.types import TxParams, HexBytes
from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_typing import ChecksumAddress, HexStr
from eth_utils import to_checksum_address, is_address
from cryptography.fernet import Fernet
import keyring

from .config import config, ChainConfig
from .web3_client import Web3Client

logger = logging.getLogger(__name__)


class WalletType(Enum):
    """Types of wallet management."""
    DEVELOPMENT = "development"  # For testing with test private keys
    KEYSTORE = "keystore"       # Encrypted JSON keystore files
    HARDWARE = "hardware"       # Hardware wallet integration
    ENVIRONMENT = "environment" # Private key from environment variable
    KEYRING = "keyring"         # OS keyring storage


@dataclass
class WalletConfig:
    """Configuration for wallet access."""
    wallet_type: WalletType
    address: ChecksumAddress
    name: str
    config: Dict[str, Any]
    is_trading_enabled: bool = True
    daily_limit_usd: Optional[Decimal] = None
    per_transaction_limit_usd: Optional[Decimal] = None


@dataclass
class SignedTransaction:
    """Represents a signed transaction ready for broadcast."""
    signed_transaction: HexBytes
    transaction_hash: HexStr
    raw_transaction: TxParams
    gas_estimate: int
    gas_price_gwei: Decimal
    estimated_cost_eth: Decimal


class WalletManager:
    """
    Secure wallet management for trading operations.
    
    Features:
    - Multiple wallet type support (dev, keystore, hardware)
    - Secure private key handling with encryption
    - Transaction signing and gas optimization
    - Spending limits and security checks
    - Integration with Django wallet models
    """
    
    def __init__(self, chain_config: ChainConfig):
        """
        Initialize wallet manager for specific chain.
        
        Args:
            chain_config: Chain configuration for wallet operations
        """
        self.chain_config = chain_config
        self.logger = logging.getLogger(f'engine.wallet.{chain_config.name.lower()}')
        
        # Wallet storage
        self.wallets: Dict[str, WalletConfig] = {}
        self.accounts: Dict[str, LocalAccount] = {}
        self.web3_client: Optional[Web3Client] = None
        
        # Security settings
        self.encryption_key: Optional[bytes] = None
        self.is_locked = True
        
        # Spending tracking
        self.daily_spending: Dict[str, Decimal] = {}
        self.transaction_spending: Dict[str, List[Decimal]] = {}
        
        self.logger.info(f"Initialized WalletManager for {chain_config.name}")

    async def initialize(self, web3_client: Web3Client) -> bool:
        """
        Initialize wallet manager with Web3 client.
        
        Args:
            web3_client: Connected Web3 client instance
            
        Returns:
            bool: True if initialization successful
        """
        try:
            self.web3_client = web3_client
            
            # Load encryption key for secure storage
            await self._initialize_encryption()
            
            # Load configured wallets
            await self._load_wallets()
            
            self.logger.info(f"WalletManager initialized with {len(self.wallets)} wallets")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize wallet manager: {e}")
            return False

    async def _initialize_encryption(self) -> None:
        """Initialize encryption for secure key storage."""
        try:
            # Try to load existing encryption key
            key_file = Path("wallets/.encryption_key")
            
            if key_file.exists():
                self.encryption_key = key_file.read_bytes()
                self.logger.debug("Loaded existing encryption key")
            else:
                # Generate new encryption key for development
                if config.trading_mode == 'PAPER':
                    self.encryption_key = Fernet.generate_key()
                    
                    # Create wallets directory
                    key_file.parent.mkdir(exist_ok=True)
                    key_file.write_bytes(self.encryption_key)
                    
                    self.logger.info("Generated new encryption key for development")
                else:
                    self.logger.warning("No encryption key found for production mode")
                    
        except Exception as e:
            self.logger.error(f"Failed to initialize encryption: {e}")

    async def _load_wallets(self) -> None:
        """Load wallet configurations from various sources."""
        try:
            # Load development wallets for testing
            if config.trading_mode == 'PAPER':
                await self._load_development_wallets()
            
            # Load environment variable wallets
            await self._load_environment_wallets()
            
            # Load keystore wallets
            await self._load_keystore_wallets()
            
            self.logger.info(f"Loaded {len(self.wallets)} wallet configurations")
            
        except Exception as e:
            self.logger.error(f"Failed to load wallets: {e}")

    async def _load_development_wallets(self) -> None:
        """Load development wallets for testing (PAPER mode only)."""
        if config.trading_mode != 'PAPER':
            return
            
        try:
            # Create a test wallet with a well-known private key for development
            test_private_key = "0x" + "1" * 64  # Test private key - NEVER use in production
            account = Account.from_key(test_private_key)
            
            wallet_config = WalletConfig(
                wallet_type=WalletType.DEVELOPMENT,
                address=to_checksum_address(account.address),
                name="Development Test Wallet",
                config={
                    "is_test_wallet": True,
                    "created_by": "development_setup"
                },
                daily_limit_usd=Decimal('1000'),
                per_transaction_limit_usd=Decimal('100')
            )
            
            self.wallets[account.address] = wallet_config
            self.accounts[account.address] = account
            
            self.logger.info(f"✅ Loaded development wallet: {account.address}")
            
        except Exception as e:
            self.logger.error(f"Failed to load development wallets: {e}")

    async def _load_environment_wallets(self) -> None:
        """Load wallets from environment variables."""
        try:
            # Check for private key in environment
            private_key = os.getenv('WALLET_PRIVATE_KEY')
            if private_key:
                if not private_key.startswith('0x'):
                    private_key = '0x' + private_key
                
                account = Account.from_key(private_key)
                
                wallet_config = WalletConfig(
                    wallet_type=WalletType.ENVIRONMENT,
                    address=to_checksum_address(account.address),
                    name="Environment Wallet",
                    config={
                        "source": "environment_variable"
                    },
                    daily_limit_usd=Decimal(os.getenv('WALLET_DAILY_LIMIT', '5000')),
                    per_transaction_limit_usd=Decimal(os.getenv('WALLET_TX_LIMIT', '500'))
                )
                
                self.wallets[account.address] = wallet_config
                self.accounts[account.address] = account
                
                self.logger.info(f"✅ Loaded environment wallet: {account.address}")
                
        except Exception as e:
            self.logger.error(f"Failed to load environment wallet: {e}")

    async def _load_keystore_wallets(self) -> None:
        """Load wallets from encrypted keystore files."""
        try:
            keystore_dir = Path("wallets/keystores")
            if not keystore_dir.exists():
                return
            
            for keystore_file in keystore_dir.glob("*.json"):
                try:
                    with open(keystore_file, 'r') as f:
                        keystore_data = json.load(f)
                    
                    # Note: In production, you'd prompt for password
                    # For development, we'll skip password-protected keystores
                    address = keystore_data.get('address')
                    if address:
                        wallet_config = WalletConfig(
                            wallet_type=WalletType.KEYSTORE,
                            address=to_checksum_address(f"0x{address}"),
                            name=f"Keystore {keystore_file.stem}",
                            config={
                                "keystore_file": str(keystore_file),
                                "requires_password": True
                            },
                            is_trading_enabled=False  # Disabled until password provided
                        )
                        
                        self.wallets[wallet_config.address] = wallet_config
                        
                        self.logger.info(f"📁 Found keystore wallet: {wallet_config.address}")
                        
                except Exception as e:
                    self.logger.warning(f"Failed to load keystore {keystore_file}: {e}")
                    
        except Exception as e:
            self.logger.error(f"Failed to load keystore wallets: {e}")

    def get_available_wallets(self) -> List[WalletConfig]:
        """Get list of available wallets."""
        return list(self.wallets.values())

    def get_trading_enabled_wallets(self) -> List[WalletConfig]:
        """Get wallets that are enabled for trading."""
        return [w for w in self.wallets.values() if w.is_trading_enabled]

    async def get_wallet_balance(self, address: str) -> Dict[str, Any]:
        """
        Get current wallet balance from blockchain.
        
        Args:
            address: Wallet address to check
            
        Returns:
            Dict with balance information
        """
        try:
            if not self.web3_client or not self.web3_client.is_connected:
                raise ValueError("Web3 client not connected")
            
            checksum_address = to_checksum_address(address)
            web3 = self.web3_client.web3
            
            # Get ETH balance
            eth_balance_wei = web3.eth.get_balance(checksum_address)
            eth_balance = Decimal(eth_balance_wei) / Decimal('1e18')
            
            # Get nonce for pending transactions
            nonce = web3.eth.get_transaction_count(checksum_address, 'pending')
            
            return {
                'address': checksum_address,
                'eth_balance': str(eth_balance),
                'eth_balance_wei': eth_balance_wei,
                'nonce': nonce,
                'chain_id': self.chain_config.chain_id,
                'status': 'success'
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get balance for {address}: {e}")
            return {
                'address': address,
                'error': str(e),
                'status': 'failed'
            }

    async def estimate_gas_price(self) -> Dict[str, Decimal]:
        """
        Estimate current gas prices with different priority levels.
        
        Returns:
            Dict with gas price estimates in Gwei
        """
        try:
            if not self.web3_client or not self.web3_client.is_connected:
                raise ValueError("Web3 client not connected")
            
            web3 = self.web3_client.web3
            
            # Get base gas price
            base_gas_price = web3.eth.gas_price
            base_gwei = Decimal(base_gas_price) / Decimal('1e9')
            
            # Calculate different priority levels
            return {
                'slow': base_gwei * Decimal('0.9'),      # 10% below base
                'standard': base_gwei,                    # Base gas price
                'fast': base_gwei * Decimal('1.2'),      # 20% above base
                'urgent': base_gwei * Decimal('1.5'),    # 50% above base
                'base_wei': base_gas_price
            }
            
        except Exception as e:
            self.logger.error(f"Failed to estimate gas price: {e}")
            return {
                'slow': Decimal('20'),
                'standard': Decimal('25'),
                'fast': Decimal('30'),
                'urgent': Decimal('40'),
                'error': str(e)
            }

    async def prepare_transaction(
        self,
        from_address: str,
        to_address: str,
        value: int = 0,
        data: bytes = b'',
        gas_price_gwei: Optional[Decimal] = None,
        gas_limit: Optional[int] = None
    ) -> TxParams:
        """
        Prepare transaction parameters for signing.
        
        Args:
            from_address: Sender address
            to_address: Recipient address  
            value: Value to send in wei
            data: Transaction data (for contract calls)
            gas_price_gwei: Gas price in Gwei (auto if None)
            gas_limit: Gas limit (auto estimate if None)
            
        Returns:
            Prepared transaction parameters
        """
        try:
            if not self.web3_client or not self.web3_client.is_connected:
                raise ValueError("Web3 client not connected")
            
            web3 = self.web3_client.web3
            from_address = to_checksum_address(from_address)
            to_address = to_checksum_address(to_address)
            
            # Get nonce
            nonce = web3.eth.get_transaction_count(from_address, 'pending')
            
            # Estimate gas price if not provided
            if gas_price_gwei is None:
                gas_prices = await self.estimate_gas_price()
                gas_price_gwei = gas_prices['standard']
            
            gas_price_wei = int(gas_price_gwei * Decimal('1e9'))
            
            # Build transaction
            tx_params = TxParams({
                'from': from_address,
                'to': to_address,
                'value': value,
                'nonce': nonce,
                'gasPrice': gas_price_wei,
                'chainId': self.chain_config.chain_id
            })
            
            # Add data if provided
            if data:
                tx_params['data'] = data
            
            # Estimate gas limit if not provided
            if gas_limit is None:
                try:
                    estimated_gas = web3.eth.estimate_gas(tx_params)
                    # Add 20% buffer to estimated gas
                    gas_limit = int(estimated_gas * 1.2)
                except Exception as e:
                    self.logger.warning(f"Gas estimation failed: {e}, using default")
                    gas_limit = 100000  # Default gas limit
            
            tx_params['gas'] = gas_limit
            
            return tx_params
            
        except Exception as e:
            self.logger.error(f"Failed to prepare transaction: {e}")
            raise

    async def sign_transaction(
        self,
        transaction: TxParams,
        from_address: str
    ) -> SignedTransaction:
        """
        Sign transaction with wallet's private key.
        
        Args:
            transaction: Transaction parameters to sign
            from_address: Address of wallet to sign with
            
        Returns:
            Signed transaction ready for broadcast
        """
        try:
            from_address = to_checksum_address(from_address)
            
            # Check if wallet exists and is enabled
            if from_address not in self.wallets:
                raise ValueError(f"Wallet {from_address} not configured")
            
            wallet_config = self.wallets[from_address]
            if not wallet_config.is_trading_enabled:
                raise ValueError(f"Trading disabled for wallet {from_address}")
            
            # Get account for signing
            if from_address not in self.accounts:
                raise ValueError(f"Account {from_address} not available for signing")
            
            account = self.accounts[from_address]
            
            # Check spending limits
            await self._check_spending_limits(wallet_config, transaction)
            
            # Sign transaction
            signed_txn = account.sign_transaction(transaction)
            
            # Calculate costs
            gas_price_gwei = Decimal(transaction['gasPrice']) / Decimal('1e9')
            estimated_cost_wei = transaction['gas'] * transaction['gasPrice']
            estimated_cost_eth = Decimal(estimated_cost_wei) / Decimal('1e18')
            
            result = SignedTransaction(
                signed_transaction=signed_txn.rawTransaction,
                transaction_hash=signed_txn.hash.hex(),
                raw_transaction=transaction,
                gas_estimate=transaction['gas'],
                gas_price_gwei=gas_price_gwei,
                estimated_cost_eth=estimated_cost_eth
            )
            
            self.logger.info(
                f"✅ Transaction signed by {from_address}: {signed_txn.hash.hex()[:10]}... "
                f"(Gas: {gas_price_gwei:.1f} gwei, Cost: {estimated_cost_eth:.6f} ETH)"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to sign transaction: {e}")
            raise

    async def _check_spending_limits(
        self,
        wallet_config: WalletConfig,
        transaction: TxParams
    ) -> None:
        """Check transaction against wallet spending limits."""
        try:
            # Calculate transaction value in ETH
            tx_value_wei = transaction.get('value', 0)
            gas_cost_wei = transaction['gas'] * transaction['gasPrice']
            total_cost_wei = tx_value_wei + gas_cost_wei
            total_cost_eth = Decimal(total_cost_wei) / Decimal('1e18')
            
            # Note: In production, you'd convert to USD using price feeds
            # For now, we'll use ETH limits
            
            # Check per-transaction limit
            if wallet_config.per_transaction_limit_usd:
                # Assume 1 ETH = $2000 for limit checking (should use real price feed)
                estimated_usd = total_cost_eth * Decimal('2000')
                if estimated_usd > wallet_config.per_transaction_limit_usd:
                    raise ValueError(
                        f"Transaction exceeds per-transaction limit: "
                        f"${estimated_usd:.2f} > ${wallet_config.per_transaction_limit_usd:.2f}"
                    )
            
            # Daily limits would require tracking in database
            # This is a simplified check
            
        except Exception as e:
            self.logger.error(f"Spending limit check failed: {e}")
            raise

    async def broadcast_transaction(self, signed_transaction: SignedTransaction) -> str:
        """
        Broadcast signed transaction to blockchain.
        
        Args:
            signed_transaction: Signed transaction to broadcast
            
        Returns:
            Transaction hash
        """
        try:
            if not self.web3_client or not self.web3_client.is_connected:
                raise ValueError("Web3 client not connected")
            
            web3 = self.web3_client.web3
            
            # Broadcast transaction
            tx_hash = web3.eth.send_raw_transaction(signed_transaction.signed_transaction)
            
            self.logger.info(f"📡 Transaction broadcasted: {tx_hash.hex()}")
            return tx_hash.hex()
            
        except Exception as e:
            self.logger.error(f"Failed to broadcast transaction: {e}")
            raise

    async def wait_for_transaction_receipt(
        self,
        tx_hash: str,
        timeout_seconds: int = 180
    ) -> Dict[str, Any]:
        """
        Wait for transaction confirmation and return receipt.
        
        Args:
            tx_hash: Transaction hash to wait for
            timeout_seconds: Maximum time to wait
            
        Returns:
            Transaction receipt data
        """
        try:
            if not self.web3_client or not self.web3_client.is_connected:
                raise ValueError("Web3 client not connected")
            
            web3 = self.web3_client.web3
            
            self.logger.info(f"⏳ Waiting for confirmation: {tx_hash}")
            
            # Wait for receipt
            receipt = web3.eth.wait_for_transaction_receipt(
                tx_hash, 
                timeout=timeout_seconds
            )
            
            success = receipt.status == 1
            
            result = {
                'transaction_hash': tx_hash,
                'block_number': receipt.blockNumber,
                'block_hash': receipt.blockHash.hex(),
                'gas_used': receipt.gasUsed,
                'status': 'success' if success else 'failed',
                'confirmation_time': 'immediate',  # Could calculate actual time
                'receipt': dict(receipt)
            }
            
            if success:
                self.logger.info(f"✅ Transaction confirmed: {tx_hash} (Block: {receipt.blockNumber})")
            else:
                self.logger.error(f"❌ Transaction failed: {tx_hash}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Failed waiting for transaction {tx_hash}: {e}")
            return {
                'transaction_hash': tx_hash,
                'error': str(e),
                'status': 'timeout_or_error'
            }

    def unlock_wallet(self, password: Optional[str] = None) -> bool:
        """
        Unlock wallet manager for transaction signing.
        
        Args:
            password: Password for encrypted wallets (if required)
            
        Returns:
            bool: True if unlock successful
        """
        try:
            # In development mode, auto-unlock
            if config.trading_mode == 'PAPER':
                self.is_locked = False
                self.logger.info("🔓 Wallet manager unlocked (development mode)")
                return True
            
            # In production, would implement proper password checking
            # For now, simple unlock for environment wallets
            if any(w.wallet_type == WalletType.ENVIRONMENT for w in self.wallets.values()):
                self.is_locked = False
                self.logger.info("🔓 Wallet manager unlocked (environment mode)")
                return True
            
            self.logger.warning("🔒 Wallet unlock not implemented for production")
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to unlock wallet: {e}")
            return False

    def lock_wallet(self) -> None:
        """Lock wallet manager and clear sensitive data."""
        self.is_locked = True
        # In production, would clear private keys from memory
        self.logger.info("🔒 Wallet manager locked")

    def get_status(self) -> Dict[str, Any]:
        """Get wallet manager status summary."""
        return {
            'is_locked': self.is_locked,
            'total_wallets': len(self.wallets),
            'trading_enabled_wallets': len(self.get_trading_enabled_wallets()),
            'wallet_types': [w.wallet_type.value for w in self.wallets.values()],
            'chain': self.chain_config.name,
            'chain_id': self.chain_config.chain_id,
            'web3_connected': self.web3_client.is_connected if self.web3_client else False
        }