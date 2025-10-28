/**
 * Wallet Connection Module
 * 
 * Complete frontend implementation for SIWE (Sign-In with Ethereum) wallet connection.
 * Integrates with MetaMask, WalletConnect, and other Web3 providers.
 * 
 * REFACTORED VERSION - Uses centralized constants and utilities
 * 
 * Dependencies:
 * - common-utils.js (must be loaded before this file)
 *   - Uses: getCSRFToken(), showToast()
 * 
 * Updates include:
 * - Centralized constants for API endpoints, element IDs, localStorage keys
 * - Removed duplicate utility functions (getCSRFToken, getCookie)
 * - Uses shared showToast() for all notifications
 * - Session persistence using localStorage
 * - Automatic reconnection on page load
 * - Retry logic for database lock errors
 * - Better error handling for signature issues
 * - Maintains connection across page navigation
 * 
 * File: dexproject/static/js/wallet-connection.js
 */

'use strict';

// ============================================================================
// WALLET CONSTANTS
// ============================================================================

const WALLET_CONSTANTS = {
    // API Endpoints
    API: {
        WALLET_INFO: '/api/wallet/info/',
        SIWE_CHALLENGE: '/api/wallet/siwe/challenge/',
        SIWE_VERIFY: '/api/wallet/siwe/verify/',
        DISCONNECT: '/api/wallet/disconnect/'
    },

    // Element IDs
    ELEMENTS: {
        STATUS_MESSAGE: 'wallet-status-message',
        NAV_INDICATOR: 'wallet-nav-indicator',
        CONNECT_BTN: 'wallet-connect-btn',
        DISCONNECT_BTN: 'wallet-disconnect-btn',
        ADDRESS_DISPLAY: 'wallet-address-display',
        CHAIN_DISPLAY: 'wallet-chain-display',
        WALLET_MODAL: 'walletModal'
    },

    // Data Attributes for Buttons
    ACTIONS: {
        CONNECT: 'connect-wallet',
        DISCONNECT: 'disconnect-wallet'
    },

    // localStorage Keys
    STORAGE: {
        SESSION: 'walletSession',
        SESSION_MAX_AGE_MS: 24 * 60 * 60 * 1000 // 24 hours
    },

    // Custom Events
    EVENTS: {
        CONNECTED: 'wallet:connected',
        DISCONNECTED: 'wallet:disconnected',
        CHAIN_CHANGED: 'wallet:chainChanged',
        ACCOUNT_CHANGED: 'wallet:accountChanged'
    },

    // Supported Blockchain Networks
    CHAINS: {
        84532: {
            name: 'Base Sepolia',
            rpcUrl: 'https://sepolia.base.org',
            blockExplorer: 'https://sepolia.basescan.org',
            currency: 'ETH'
        },
        11155111: {
            name: 'Ethereum Sepolia',
            rpcUrl: 'https://sepolia.infura.io/v3/YOUR_INFURA_KEY',
            blockExplorer: 'https://sepolia.etherscan.io',
            currency: 'ETH'
        },
        1: {
            name: 'Ethereum Mainnet',
            rpcUrl: 'https://mainnet.infura.io/v3/YOUR_INFURA_KEY',
            blockExplorer: 'https://etherscan.io',
            currency: 'ETH'
        },
        8453: {
            name: 'Base Mainnet',
            rpcUrl: 'https://mainnet.base.org',
            blockExplorer: 'https://basescan.org',
            currency: 'ETH'
        }
    },

    // Default Configuration
    DEFAULT_CHAIN_ID: 84532, // Base Sepolia for development

    // Retry Configuration
    MAX_RETRIES: 3,
    RETRY_DELAY_MS: 1000,

    // Status CSS Classes
    STATUS_CLASSES: {
        OPERATIONAL: 'status-indicator status-operational',
        ERROR: 'status-indicator status-error'
    }
};

// ============================================================================
// WALLET CONNECTION MANAGER CLASS
// ============================================================================

class WalletConnectionManager {
    constructor() {
        // Connection state
        this.isConnected = false;
        this.walletAddress = null;
        this.walletType = null;
        this.chainId = null;
        this.provider = null;
        this.signer = null;
        this.sessionId = null;
        this.walletId = null;

        // Retry configuration
        this.maxRetries = WALLET_CONSTANTS.MAX_RETRIES;
        this.retryDelay = WALLET_CONSTANTS.RETRY_DELAY_MS;

        // Supported chains
        this.supportedChains = WALLET_CONSTANTS.CHAINS;

        // Default to Base Sepolia for development
        this.targetChainId = WALLET_CONSTANTS.DEFAULT_CHAIN_ID;

        this.init();
    }

    /**
     * Initialize wallet connection manager
     */
    async init() {
        console.log('🔗 Initializing Wallet Connection Manager...');

        // Check localStorage for saved session first
        await this.checkLocalStorageSession();

        // Check if already connected from backend session
        await this.checkExistingConnection();

        // Setup event listeners
        this.setupEventListeners();

        // Setup wallet provider listeners
        this.setupWalletListeners();

        // Monitor page visibility for reconnection
        this.setupVisibilityListener();

        console.log('✅ Wallet Connection Manager initialized');
    }

    // ========================================================================
    // SESSION MANAGEMENT
    // ========================================================================

    /**
     * Check localStorage for saved wallet session
     */
    async checkLocalStorageSession() {
        try {
            const savedSession = localStorage.getItem(WALLET_CONSTANTS.STORAGE.SESSION);
            if (savedSession) {
                const session = JSON.parse(savedSession);

                // Check if session is less than 24 hours old
                const sessionAge = Date.now() - session.timestamp;
                if (sessionAge < WALLET_CONSTANTS.STORAGE.SESSION_MAX_AGE_MS) {
                    console.log('📦 Found saved wallet session in localStorage');

                    // Try to reconnect with saved session
                    await this.reconnectWithSavedSession(session);
                } else {
                    // Session expired, clear it
                    console.log('⏰ Saved session expired, clearing...');
                    localStorage.removeItem(WALLET_CONSTANTS.STORAGE.SESSION);
                }
            }
        } catch (error) {
            console.error('Error checking localStorage session:', error);
            localStorage.removeItem(WALLET_CONSTANTS.STORAGE.SESSION);
        }
    }

    /**
     * Reconnect with saved session from localStorage
     */
    async reconnectWithSavedSession(session) {
        try {
            if (window.ethereum) {
                // Check if the wallet is still connected
                const accounts = await window.ethereum.request({
                    method: 'eth_accounts'
                });

                if (accounts.length > 0 &&
                    accounts[0].toLowerCase() === session.walletAddress.toLowerCase()) {

                    // Wallet is still connected, restore session
                    this.provider = window.ethereum;
                    this.walletAddress = session.walletAddress;
                    this.chainId = session.chainId;
                    this.walletType = session.walletType;
                    this.sessionId = session.sessionId;
                    this.walletId = session.walletId;
                    this.isConnected = true;

                    console.log('🔄 Reconnected with saved session from localStorage');
                    this.updateConnectionUI();

                    // Verify with backend
                    await this.verifyBackendSession();
                } else {
                    // Wallet changed or disconnected, clear saved session
                    localStorage.removeItem(WALLET_CONSTANTS.STORAGE.SESSION);
                }
            }
        } catch (error) {
            console.error('Failed to reconnect with saved session:', error);
            localStorage.removeItem(WALLET_CONSTANTS.STORAGE.SESSION);
        }
    }

    /**
     * Verify session with backend
     */
    async verifyBackendSession() {
        try {
            const response = await fetch(WALLET_CONSTANTS.API.WALLET_INFO, {
                headers: {
                    'X-CSRFToken': getCSRFToken()
                }
            });

            if (!response.ok) {
                // Backend session invalid, re-authenticate
                console.log('⚠️ Backend session invalid, re-authenticating...');
                await this.authenticateWithSIWE();
            }
        } catch (error) {
            console.error('Failed to verify backend session:', error);
        }
    }

    /**
     * Save current session to localStorage
     */
    saveSessionToLocalStorage() {
        try {
            const session = {
                walletAddress: this.walletAddress,
                chainId: this.chainId,
                walletType: this.walletType,
                sessionId: this.sessionId,
                walletId: this.walletId,
                timestamp: Date.now()
            };

            localStorage.setItem(WALLET_CONSTANTS.STORAGE.SESSION, JSON.stringify(session));
            console.log('💾 Session saved to localStorage');
        } catch (error) {
            console.error('Failed to save session to localStorage:', error);
        }
    }

    /**
     * Check for existing wallet connection from backend
     */
    async checkExistingConnection() {
        try {
            // Check if wallet is connected in backend session
            const sessionData = await this.checkSessionStatus();
            if (sessionData && sessionData.connected) {
                await this.restoreWalletConnection(sessionData);
            }
        } catch (error) {
            console.log('No existing backend connection found');
        }
    }

    /**
     * Check session status with backend
     */
    async checkSessionStatus() {
        try {
            const response = await fetch(WALLET_CONSTANTS.API.WALLET_INFO, {
                headers: {
                    'X-CSRFToken': getCSRFToken()
                }
            });

            if (response.ok) {
                return await response.json();
            }
        } catch (error) {
            console.log('No active session found');
        }

        return null;
    }

    /**
     * Restore wallet connection from session
     */
    async restoreWalletConnection(sessionData) {
        console.log('🔄 Restoring wallet connection from backend...');

        this.isConnected = true;
        this.walletAddress = sessionData.wallet.address;
        this.walletType = sessionData.wallet.wallet_type;
        this.chainId = sessionData.wallet.primary_chain_id;
        this.walletId = sessionData.wallet.wallet_id;

        // Try to reconnect to provider
        const provider = await this.detectProvider();
        if (provider) {
            this.provider = provider;

            // Verify the account matches
            try {
                const accounts = await provider.request({
                    method: 'eth_accounts'
                });

                if (accounts.length === 0 ||
                    accounts[0].toLowerCase() !== this.walletAddress.toLowerCase()) {
                    // Account mismatch, need to reconnect
                    console.log('⚠️ Account mismatch, clearing session');
                    this.handleDisconnection();
                    return;
                }
            } catch (error) {
                console.error('Error verifying account:', error);
            }
        }

        // Save to localStorage for persistence
        this.saveSessionToLocalStorage();

        this.updateConnectionUI();

        console.log('✅ Wallet connection restored');
    }

    // ========================================================================
    // EVENT LISTENERS
    // ========================================================================

    /**
     * Setup event listeners for UI interactions
     */
    setupEventListeners() {
        // Connect wallet button
        document.addEventListener('click', (e) => {
            if (e.target.matches(`[data-action="${WALLET_CONSTANTS.ACTIONS.CONNECT}"]`)) {
                e.preventDefault();
                this.connectWallet();
            }

            if (e.target.matches(`[data-action="${WALLET_CONSTANTS.ACTIONS.DISCONNECT}"]`)) {
                e.preventDefault();
                this.disconnectWallet();
            }
        });
    }

    /**
     * Setup wallet provider event listeners
     */
    setupWalletListeners() {
        if (!window.ethereum) return;

        // Account changed
        window.ethereum.on('accountsChanged', (accounts) => {
            console.log('👤 Account changed:', accounts);

            if (accounts.length === 0) {
                // User disconnected wallet
                this.handleDisconnection();
            } else if (accounts[0].toLowerCase() !== this.walletAddress?.toLowerCase()) {
                // User switched accounts
                this.handleAccountChange(accounts[0]);
            }
        });

        // Chain changed
        window.ethereum.on('chainChanged', (chainId) => {
            console.log('⛓️ Chain changed:', chainId);
            this.handleChainChange(parseInt(chainId, 16));
        });

        // Disconnect
        window.ethereum.on('disconnect', () => {
            console.log('🔌 Wallet disconnected');
            this.handleDisconnection();
        });
    }

    /**
     * Setup page visibility listener for reconnection
     */
    setupVisibilityListener() {
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden && this.isConnected) {
                // Page became visible and we think we're connected
                // Verify the connection is still valid
                this.verifyConnection();
            }
        });

        // Also check on focus
        window.addEventListener('focus', () => {
            if (this.isConnected) {
                this.verifyConnection();
            }
        });
    }

    /**
     * Verify current connection is still valid
     */
    async verifyConnection() {
        if (!this.provider || !window.ethereum) return;

        try {
            const accounts = await window.ethereum.request({
                method: 'eth_accounts'
            });

            if (accounts.length === 0 ||
                accounts[0].toLowerCase() !== this.walletAddress?.toLowerCase()) {
                // Connection lost or account changed
                console.log('⚠️ Connection lost or account changed');
                this.handleDisconnection();
            }
        } catch (error) {
            console.error('Error verifying connection:', error);
        }
    }

    // ========================================================================
    // WALLET CONNECTION
    // ========================================================================

    /**
     * Connect wallet
     */
    async connectWallet() {
        try {
            showToast('Connecting wallet...', 'info');

            // Detect provider
            const provider = await this.detectProvider();
            if (!provider) {
                showToast('No Web3 wallet detected. Please install MetaMask or another Web3 wallet.', 'error');
                return;
            }

            this.provider = provider;

            // Request accounts
            const accounts = await provider.request({
                method: 'eth_requestAccounts'
            });

            if (accounts.length === 0) {
                showToast('No accounts found. Please unlock your wallet.', 'error');
                return;
            }

            this.walletAddress = accounts[0];

            // Get chain ID
            const chainId = await provider.request({
                method: 'eth_chainId'
            });
            this.chainId = parseInt(chainId, 16);

            // Detect wallet type
            this.walletType = this.detectWalletType(provider);

            console.log('✅ Wallet connected:', {
                address: this.walletAddress,
                chainId: this.chainId,
                walletType: this.walletType
            });

            // Check if we're on the correct chain
            if (this.chainId !== this.targetChainId) {
                await this.switchToTargetChain();
            }

            // Authenticate with SIWE
            await this.authenticateWithSIWE();

        } catch (error) {
            console.error('Failed to connect wallet:', error);

            if (error.code === 4001) {
                showToast('Connection request rejected', 'warning');
            } else {
                showToast(`Failed to connect wallet: ${error.message}`, 'error');
            }
        }
    }

    /**
     * Detect Web3 provider
     */
    async detectProvider() {
        if (window.ethereum) {
            return window.ethereum;
        }

        // Check for other providers
        if (window.web3) {
            return window.web3.currentProvider;
        }

        return null;
    }

    /**
     * Detect wallet type
     */
    detectWalletType(provider) {
        if (provider.isMetaMask) {
            return 'metamask';
        }

        if (provider.isCoinbaseWallet) {
            return 'coinbase';
        }

        if (provider.isWalletConnect) {
            return 'walletconnect';
        }

        return 'unknown';
    }

    /**
     * Switch to target chain
     */
    async switchToTargetChain() {
        try {
            showToast('Switching to correct network...', 'info');

            const chainIdHex = '0x' + this.targetChainId.toString(16);

            await this.provider.request({
                method: 'wallet_switchEthereumChain',
                params: [{ chainId: chainIdHex }]
            });

            this.chainId = this.targetChainId;
            showToast('Network switched successfully', 'success');

        } catch (error) {
            // Chain not added, try to add it
            if (error.code === 4902) {
                await this.addChainToWallet();
            } else {
                console.error('Failed to switch chain:', error);
                showToast('Failed to switch network. Please switch manually in your wallet.', 'error');
                throw error;
            }
        }
    }

    /**
     * Add chain to wallet
     */
    async addChainToWallet() {
        try {
            const chainConfig = this.supportedChains[this.targetChainId];
            if (!chainConfig) {
                throw new Error('Unsupported chain');
            }

            const chainIdHex = '0x' + this.targetChainId.toString(16);

            await this.provider.request({
                method: 'wallet_addEthereumChain',
                params: [{
                    chainId: chainIdHex,
                    chainName: chainConfig.name,
                    rpcUrls: [chainConfig.rpcUrl],
                    blockExplorerUrls: [chainConfig.blockExplorer],
                    nativeCurrency: {
                        name: chainConfig.currency,
                        symbol: chainConfig.currency,
                        decimals: 18
                    }
                }]
            });

            this.chainId = this.targetChainId;
            showToast('Network added and switched successfully', 'success');

        } catch (error) {
            console.error('Failed to add chain:', error);
            showToast('Failed to add network. Please add manually in your wallet.', 'error');
            throw error;
        }
    }

    // ========================================================================
    // SIWE AUTHENTICATION
    // ========================================================================

    /**
     * Authenticate with Sign-In with Ethereum (SIWE)
     */
    async authenticateWithSIWE() {
        try {
            showToast('Requesting signature...', 'info');

            // Get challenge from backend with retry logic
            const challenge = await this.getChallenge();

            // Sign the challenge
            const signature = await this.signChallenge(challenge);

            // Verify signature with backend with retry logic
            const result = await this.verifySignature(signature, challenge);

            if (result.success) {
                this.isConnected = true;
                this.sessionId = result.session_id;
                this.walletId = result.wallet_id;

                // Save to localStorage
                this.saveSessionToLocalStorage();

                this.updateConnectionUI();
                this.dispatchConnectionEvent(WALLET_CONSTANTS.EVENTS.CONNECTED, {
                    address: this.walletAddress,
                    chainId: this.chainId,
                    walletType: this.walletType
                });

                showToast('Wallet connected successfully!', 'success');
            } else {
                throw new Error(result.error || 'Authentication failed');
            }

        } catch (error) {
            console.error('SIWE authentication failed:', error);

            if (error.code === 4001) {
                showToast('Signature request rejected', 'warning');
            } else {
                showToast(`Authentication failed: ${error.message}`, 'error');
            }

            // Clear partial connection state
            this.isConnected = false;
            this.walletAddress = null;
            this.chainId = null;
        }
    }

    /**
     * Get SIWE challenge from backend with retry logic
     */
    async getChallenge(retryCount = 0) {
        try {
            const response = await fetch(WALLET_CONSTANTS.API.SIWE_CHALLENGE, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                },
                body: JSON.stringify({
                    address: this.walletAddress,
                    chain_id: this.chainId
                })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to get challenge');
            }

            return await response.json();

        } catch (error) {
            // Retry logic for database locks
            if (error.message.includes('database') && retryCount < this.maxRetries) {
                console.log(`⏳ Database busy, retrying... (${retryCount + 1}/${this.maxRetries})`);
                await this.sleep(this.retryDelay * (retryCount + 1));
                return this.getChallenge(retryCount + 1);
            }

            throw error;
        }
    }

    /**
     * Sign SIWE challenge
     */
    async signChallenge(challenge) {
        try {
            const signature = await this.provider.request({
                method: 'personal_sign',
                params: [challenge.message, this.walletAddress]
            });

            return signature;

        } catch (error) {
            console.error('Failed to sign challenge:', error);
            throw error;
        }
    }

    /**
     * Verify signature with backend with retry logic
     */
    async verifySignature(signature, challenge, retryCount = 0) {
        try {
            const response = await fetch(WALLET_CONSTANTS.API.SIWE_VERIFY, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                },
                body: JSON.stringify({
                    message: challenge.message,
                    signature: signature,
                    address: this.walletAddress,
                    chain_id: this.chainId,
                    wallet_type: this.walletType
                })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Verification failed');
            }

            return await response.json();

        } catch (error) {
            // Retry logic for database locks
            if (error.message.includes('database') && retryCount < this.maxRetries) {
                console.log(`⏳ Database busy, retrying... (${retryCount + 1}/${this.maxRetries})`);
                await this.sleep(this.retryDelay * (retryCount + 1));
                return this.verifySignature(signature, challenge, retryCount + 1);
            }

            throw error;
        }
    }

    // ========================================================================
    // WALLET DISCONNECTION
    // ========================================================================

    /**
     * Disconnect wallet
     */
    async disconnectWallet() {
        try {
            showToast('Disconnecting wallet...', 'info');

            // Call backend to clear session
            const response = await fetch(WALLET_CONSTANTS.API.DISCONNECT, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                }
            });

            if (!response.ok) {
                console.error('Failed to disconnect from backend');
            }

            // Clear local state
            this.handleDisconnection();

            showToast('Wallet disconnected', 'success');

        } catch (error) {
            console.error('Failed to disconnect wallet:', error);
            showToast('Error disconnecting wallet', 'error');

            // Clear local state anyway
            this.handleDisconnection();
        }
    }

    /**
     * Handle wallet disconnection
     */
    handleDisconnection() {
        this.isConnected = false;
        this.walletAddress = null;
        this.walletType = null;
        this.chainId = null;
        this.provider = null;
        this.sessionId = null;
        this.walletId = null;

        // Clear localStorage
        localStorage.removeItem(WALLET_CONSTANTS.STORAGE.SESSION);

        this.updateConnectionUI();

        this.dispatchConnectionEvent(WALLET_CONSTANTS.EVENTS.DISCONNECTED);

        console.log('🔌 Wallet disconnected and session cleared');
    }

    /**
     * Handle account change
     */
    async handleAccountChange(newAccount) {
        console.log('👤 Account changed to:', newAccount);

        // Disconnect old account
        await this.disconnectWallet();

        // Show notification
        showToast('Wallet account changed. Please reconnect.', 'warning');

        this.dispatchConnectionEvent(WALLET_CONSTANTS.EVENTS.ACCOUNT_CHANGED, {
            newAccount: newAccount
        });
    }

    /**
     * Handle chain change
     */
    handleChainChange(newChainId) {
        this.chainId = newChainId;

        this.updateConnectionUI();

        this.dispatchConnectionEvent(WALLET_CONSTANTS.EVENTS.CHAIN_CHANGED, {
            chainId: newChainId
        });

        // Check if we're on the correct chain
        if (newChainId !== this.targetChainId) {
            showToast(`Please switch to ${this.supportedChains[this.targetChainId]?.name || 'the correct network'}`, 'warning');
        }
    }

    // ========================================================================
    // UI UPDATES
    // ========================================================================

    /**
     * Update connection UI
     */
    updateConnectionUI() {
        // Update connect button
        const connectBtn = document.getElementById(WALLET_CONSTANTS.ELEMENTS.CONNECT_BTN);
        if (connectBtn) {
            connectBtn.style.display = this.isConnected ? 'none' : 'block';
        }

        // Update disconnect button
        const disconnectBtn = document.getElementById(WALLET_CONSTANTS.ELEMENTS.DISCONNECT_BTN);
        if (disconnectBtn) {
            disconnectBtn.style.display = this.isConnected ? 'block' : 'none';
        }

        // Update address display
        const addressDisplay = document.getElementById(WALLET_CONSTANTS.ELEMENTS.ADDRESS_DISPLAY);
        if (addressDisplay) {
            addressDisplay.textContent = this.isConnected ?
                this.formatAddress(this.walletAddress) : '';
        }

        // Update chain display
        const chainDisplay = document.getElementById(WALLET_CONSTANTS.ELEMENTS.CHAIN_DISPLAY);
        if (chainDisplay) {
            if (this.isConnected && this.chainId) {
                const chainInfo = this.supportedChains[this.chainId];
                chainDisplay.textContent = chainInfo ? chainInfo.name : `Chain ${this.chainId}`;
            } else {
                chainDisplay.textContent = '';
            }
        }

        // Update connection indicator in navigation
        const navIndicator = document.getElementById(WALLET_CONSTANTS.ELEMENTS.NAV_INDICATOR);
        if (navIndicator) {
            navIndicator.className = this.isConnected ?
                WALLET_CONSTANTS.STATUS_CLASSES.OPERATIONAL :
                WALLET_CONSTANTS.STATUS_CLASSES.ERROR;
        }
    }

    /**
     * Format wallet address for display
     */
    formatAddress(address) {
        if (!address) return '';
        return `${address.slice(0, 6)}...${address.slice(-4)}`;
    }

    // ========================================================================
    // EVENT DISPATCHING
    // ========================================================================

    /**
     * Dispatch custom wallet events
     */
    dispatchConnectionEvent(eventName, data = {}) {
        const event = new CustomEvent(eventName, {
            detail: {
                ...data,
                timestamp: Date.now()
            }
        });
        document.dispatchEvent(event);
    }

    // ========================================================================
    // UTILITY METHODS
    // ========================================================================

    /**
     * Sleep utility for retry logic
     */
    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    /**
     * Get wallet balance (utility method for future use)
     */
    async getWalletBalance() {
        if (!this.isConnected || !this.provider) {
            throw new Error('Wallet not connected');
        }

        try {
            const balance = await this.provider.request({
                method: 'eth_getBalance',
                params: [this.walletAddress, 'latest']
            });

            // Convert from wei to ether
            const balanceInEth = parseInt(balance, 16) / Math.pow(10, 18);
            return balanceInEth;

        } catch (error) {
            console.error('Failed to get wallet balance:', error);
            throw error;
        }
    }
}

// ============================================================================
// INITIALIZATION
// ============================================================================

// Initialize wallet connection manager when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 Initializing Wallet Connection System...');

    // Initialize global wallet manager
    window.walletManager = new WalletConnectionManager();

    // Listen for wallet events
    document.addEventListener(WALLET_CONSTANTS.EVENTS.CONNECTED, (event) => {
        console.log('🎉 Wallet connected event:', event.detail);

        // Reload page data if needed
        if (typeof refreshDashboardData === 'function') {
            refreshDashboardData();
        }
    });

    document.addEventListener(WALLET_CONSTANTS.EVENTS.DISCONNECTED, (event) => {
        console.log('👋 Wallet disconnected event:', event.detail);

        // Handle disconnection in UI
        if (typeof handleWalletDisconnection === 'function') {
            handleWalletDisconnection();
        }
    });

    document.addEventListener(WALLET_CONSTANTS.EVENTS.CHAIN_CHANGED, (event) => {
        console.log('⛓️ Chain changed event:', event.detail);

        // Handle chain change in UI
        if (typeof handleChainChange === 'function') {
            handleChainChange(event.detail.chainId);
        }
    });

    console.log('✅ Wallet Connection System ready');
});

// ============================================================================
// EXPORTS
// ============================================================================

// Export for module use
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        WalletConnectionManager,
        WALLET_CONSTANTS
    };
}

console.log('💼 Wallet Connection Module v2.0 (Refactored) loaded successfully');