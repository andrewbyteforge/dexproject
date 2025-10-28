/**
 * Wallet Connection Module - REFACTORED
 * 
 * Complete frontend implementation for SIWE (Sign-In with Ethereum) wallet connection.
 * Integrates with MetaMask, WalletConnect, and other Web3 providers.
 * 
 * Phase 5.1B Frontend Implementation - REFACTORED VERSION
 * 
 * Updates include:
 * - Session persistence using localStorage
 * - Automatic reconnection on page load
 * - Retry logic for database lock errors
 * - Better error handling for signature issues
 * - Maintains connection across page navigation
 * - Uses centralized constants for maintainability
 * 
 * DEPENDENCIES (must be loaded before this file):
 * - common-utils.js - Utility functions (getCSRFToken, showToast, etc.)
 * - api-constants.js - API endpoints and chain configurations
 * - form-constants.js - Element IDs, event names, localStorage keys
 * 
 * File: static/js/wallet-connection.js
 */

'use strict';


// ============================================================================
// CONSTANTS - Using window scope directly
// All constants are loaded from external files and attached to window.
// We reference them as window.CONSTANT for reliability and timing independence.
// ============================================================================

// Wallet provider constants (local to this file)
const WALLET_PROVIDERS = {
    METAMASK: 'MetaMask',
    COINBASE_WALLET: 'Coinbase Wallet',
    WALLETCONNECT: 'WalletConnect',
    INJECTED: 'Injected',
    UNKNOWN: 'Unknown'
};

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

        // Retry configuration for database locks
        this.maxRetries = 3;
        this.retryDelay = 1000; // Base delay in milliseconds

        // Use centralized chain configurations
        this.supportedChains = window.window.CHAIN_CONFIGS || {};

        // Default to Base Sepolia for development
        this.targetChainId = window.API_ENDPOINTS?.CHAIN_SETTINGS?.DEFAULT_CHAIN_ID || 84532;

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

    /**
     * Check localStorage for saved wallet session
     */
    async checkLocalStorageSession() {
        try {
            const savedSession = localStorage.getItem(window.LOCAL_STORAGE_KEYS.WALLET_SESSION);
            if (savedSession) {
                const session = JSON.parse(savedSession);

                // Check if session is less than 24 hours old
                const sessionAge = Date.now() - session.timestamp;
                if (sessionAge < 24 * 60 * 60 * 1000) {
                    console.log('📦 Found saved wallet session in localStorage');

                    // Try to reconnect with saved session
                    await this.reconnectWithSavedSession(session);
                } else {
                    // Session expired, clear it
                    console.log('⏰ Saved session expired, clearing...');
                    localStorage.removeItem(window.LOCAL_STORAGE_KEYS.WALLET_SESSION);
                }
            }
        } catch (error) {
            console.error('Error checking localStorage session:', error);
            localStorage.removeItem(window.LOCAL_STORAGE_KEYS.WALLET_SESSION);
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
                    localStorage.removeItem(window.LOCAL_STORAGE_KEYS.WALLET_SESSION);
                }
            }
        } catch (error) {
            console.error('Failed to reconnect with saved session:', error);
            localStorage.removeItem(window.LOCAL_STORAGE_KEYS.WALLET_SESSION);
        }
    }

    /**
     * Verify session with backend
     */
    async verifyBackendSession() {
        try {
            const response = await fetch(window.API_ENDPOINTS.WALLET.INFO, {
                headers: {
                    'X-CSRFToken': window.getCSRFToken()
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

    /**
     * Setup event listeners for UI interactions
     */
    setupEventListeners() {
        // Connect wallet button
        document.addEventListener('click', (e) => {
            if (e.target.matches(window.DATA_ACTIONS.CONNECT_WALLET)) {
                e.preventDefault();
                this.connectWallet();
            }

            if (e.target.matches(window.DATA_ACTIONS.DISCONNECT_WALLET)) {
                e.preventDefault();
                this.disconnectWallet();
            }

            if (e.target.matches(window.DATA_ACTIONS.SWITCH_CHAIN)) {
                e.preventDefault();
                const chainId = parseInt(e.target.dataset.chainId);
                if (chainId) {
                    this.switchChain(chainId);
                }
            }
        });
    }

    /**
     * Setup wallet provider event listeners
     */
    setupWalletListeners() {
        if (window.ethereum) {
            // Account changed
            window.ethereum.on('accountsChanged', (accounts) => {
                console.log('👤 Account changed:', accounts);
                if (accounts.length === 0) {
                    this.handleDisconnection();
                } else if (accounts[0].toLowerCase() !== this.walletAddress?.toLowerCase()) {
                    // Account switched, reconnect with new account
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
                console.log('🔌 Provider disconnected');
                this.handleDisconnection();
            });
        }
    }

    /**
     * Connect wallet
     */
    async connectWallet() {
        try {
            this.showStatus(window.MESSAGE_TYPES.LOADING, window.WALLET_STATUS_MESSAGES.CONNECTING);

            // Detect wallet provider
            const provider = await this.detectProvider();
            if (!provider) {
                this.showStatus(window.MESSAGE_TYPES.ERROR, window.WALLET_STATUS_MESSAGES.NO_WALLET);
                return;
            }

            this.provider = provider;

            // Request account access
            const accounts = await provider.request({
                method: 'eth_requestAccounts'
            });

            if (accounts.length === 0) {
                throw new Error('No accounts found');
            }

            this.walletAddress = accounts[0];

            // Get current chain
            const chainId = await provider.request({
                method: 'eth_chainId'
            });
            this.chainId = parseInt(chainId, 16);

            // Check if chain is supported
            if (!window.CHAIN_UTILS.isChainSupported(this.chainId)) {
                this.showStatus(window.MESSAGE_TYPES.WARNING, window.WALLET_STATUS_MESSAGES.UNSUPPORTED_CHAIN);
                await this.switchChain(this.targetChainId);
                return;
            }

            // Detect wallet type
            this.walletType = this.detectWalletType();

            // Authenticate with SIWE
            await this.authenticateWithSIWE();

        } catch (error) {
            console.error('Failed to connect wallet:', error);

            if (error.code === 4001) {
                this.showStatus(window.MESSAGE_TYPES.WARNING, window.WALLET_STATUS_MESSAGES.REJECTED);
            } else {
                this.showStatus(window.MESSAGE_TYPES.ERROR, `${window.WALLET_STATUS_MESSAGES.ERROR}: ${error.message}`);
            }
        }
    }

    /**
     * Authenticate using SIWE (Sign-In with Ethereum)
     */
    async authenticateWithSIWE() {
        let retryCount = 0;

        while (retryCount < this.maxRetries) {
            try {
                this.showStatus(window.MESSAGE_TYPES.LOADING, window.WALLET_STATUS_MESSAGES.SIGNING);

                // Get challenge from backend
                const challengeResponse = await fetch(window.API_ENDPOINTS.WALLET.SIWE_CHALLENGE, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': window.getCSRFToken()
                    },
                    body: JSON.stringify({
                        wallet_address: this.walletAddress,  // ← CORRECT KEY
                        chain_id: this.chainId
                    })
                });

                if (!challengeResponse.ok) {
                    const errorData = await challengeResponse.json();
                    throw new Error(errorData.error || 'Failed to get SIWE challenge');
                }

                const challengeData = await challengeResponse.json();
                const { message, nonce } = challengeData;


                // ADD THESE DEBUG LINES:
                console.log('🔍 SIWE Challenge received:', challengeData);
                console.log('📝 Message to sign:', message);
                console.log('🎲 Nonce:', nonce);

                console.log('🎲 Nonce:', nonce);

                // ADD THIS:
                console.log('🚀 Requesting signature from MetaMask...');

                // Declare signature variable outside the Promise.race
                let signature;

                const signaturePromise = this.provider.request({
                    method: 'personal_sign',
                    params: [message, this.walletAddress]
                });

                const timeoutPromise = new Promise((_, reject) => {
                    setTimeout(() => reject(new Error('Signature request timed out after 60 seconds')), 60000);
                });

                // Now assign to the outer signature variable
                signature = await Promise.race([signaturePromise, timeoutPromise]);
                console.log('✅ Signature received:', signature.substring(0, 20) + '...');

                this.showStatus(window.MESSAGE_TYPES.LOADING, 'Verifying signature...');

                // Verify signature with backend
                const verifyResponse = await fetch(window.API_ENDPOINTS.WALLET.SIWE_VERIFY, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': window.getCSRFToken()
                    },
                    body: JSON.stringify({
                        message: message,
                        signature: signature,
                        wallet_address: this.walletAddress,  // ← CORRECT
                        chain_id: this.chainId,
                        wallet_type: this.walletType
                    })
                });

                if (!verifyResponse.ok) {
                    const errorData = await verifyResponse.json();
                    throw new Error(errorData.error || 'Failed to verify signature');
                }

                const verifyData = await verifyResponse.json();

                // Store session data
                this.sessionId = verifyData.session_id;
                this.walletId = verifyData.wallet_id;
                this.isConnected = true;

                // Save to localStorage for persistence
                this.saveSessionToLocalStorage();

                // Update UI
                this.updateConnectionUI();

                // Dispatch connection event
                this.dispatchConnectionEvent(window.CUSTOM_EVENTS.WALLET_CONNECTED, {
                    address: this.walletAddress,
                    chainId: this.chainId,
                    walletType: this.walletType
                });

                this.showStatus(window.MESSAGE_TYPES.SUCCESS, window.WALLET_STATUS_MESSAGES.CONNECTED);

                console.log('✅ Wallet connected successfully');
                break;

            } catch (error) {
                console.error(`SIWE authentication attempt ${retryCount + 1} failed:`, error);

                // Check for database lock errors
                if (error.message && error.message.includes('database is locked')) {
                    retryCount++;
                    if (retryCount < this.maxRetries) {
                        const delay = this.retryDelay * Math.pow(2, retryCount - 1);
                        console.log(`⏳ Retrying in ${delay}ms...`);
                        await new Promise(resolve => setTimeout(resolve, delay));
                        continue;
                    }
                }

                // Max retries reached or non-recoverable error
                if (error.code === 4001) {
                    this.showStatus(window.MESSAGE_TYPES.WARNING, window.WALLET_STATUS_MESSAGES.REJECTED);
                } else {
                    this.showStatus(window.MESSAGE_TYPES.ERROR, `${window.WALLET_STATUS_MESSAGES.ERROR}: ${error.message}`);
                }
                break;
            }
        }
    }

    /**
     * Save session to localStorage
     */
    saveSessionToLocalStorage() {
        try {
            const sessionData = {
                walletAddress: this.walletAddress,
                chainId: this.chainId,
                walletType: this.walletType,
                sessionId: this.sessionId,
                walletId: this.walletId,
                timestamp: Date.now()
            };

            localStorage.setItem(window.LOCAL_STORAGE_KEYS.WALLET_SESSION, JSON.stringify(sessionData));
            localStorage.setItem(window.LOCAL_STORAGE_KEYS.LAST_CONNECTED_ADDRESS, this.walletAddress);
            localStorage.setItem(window.LOCAL_STORAGE_KEYS.PREFERRED_WALLET, this.walletType);

            console.log('💾 Session saved to localStorage');
        } catch (error) {
            console.error('Failed to save session to localStorage:', error);
        }
    }

    /**
     * Disconnect wallet
     */
    async disconnectWallet() {
        try {
            this.showStatus(window.MESSAGE_TYPES.LOADING, window.WALLET_STATUS_MESSAGES.DISCONNECTING);

            // Call backend disconnect endpoint
            await fetch(window.API_ENDPOINTS.WALLET.DISCONNECT, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': window.getCSRFToken()
                }
            });

            // Clear local state
            this.handleDisconnection();

            this.showStatus(window.MESSAGE_TYPES.SUCCESS, window.WALLET_STATUS_MESSAGES.DISCONNECTED);

        } catch (error) {
            console.error('Failed to disconnect wallet:', error);
            // Still clear local state even if backend call fails
            this.handleDisconnection();
            this.showStatus(window.MESSAGE_TYPES.ERROR, `${window.WALLET_STATUS_MESSAGES.ERROR}: ${error.message}`);
        }
    }

    /**
     * Handle wallet disconnection
     */
    handleDisconnection() {
        // Clear state
        this.isConnected = false;
        this.walletAddress = null;
        this.walletType = null;
        this.chainId = null;
        this.provider = null;
        this.sessionId = null;
        this.walletId = null;

        // Clear localStorage
        localStorage.removeItem(window.LOCAL_STORAGE_KEYS.WALLET_SESSION);

        // Update UI
        this.updateConnectionUI();

        // Dispatch disconnection event
        this.dispatchConnectionEvent(window.CUSTOM_EVENTS.WALLET_DISCONNECTED);

        console.log('👋 Wallet disconnected');
    }

    /**
     * Handle account change
     */
    async handleAccountChange(newAddress) {
        console.log('🔄 Handling account change:', newAddress);

        // Disconnect old session
        await this.disconnectWallet();

        // Connect with new account
        this.walletAddress = newAddress;
        await this.authenticateWithSIWE();

        // Dispatch account change event
        this.dispatchConnectionEvent(window.CUSTOM_EVENTS.WALLET_ACCOUNT_CHANGED, {
            address: newAddress
        });
    }

    /**
     * Handle chain change
     */
    handleChainChange(newChainId) {
        console.log('⛓️ Handling chain change:', newChainId);

        this.chainId = newChainId;

        // Update UI
        this.updateConnectionUI();

        // Check if chain is supported
        if (!window.CHAIN_UTILS.isChainSupported(newChainId)) {
            this.showStatus(window.MESSAGE_TYPES.WARNING, window.WALLET_STATUS_MESSAGES.UNSUPPORTED_CHAIN);
        }

        // Dispatch chain change event
        this.dispatchConnectionEvent(window.CUSTOM_EVENTS.WALLET_CHAIN_CHANGED, {
            chainId: newChainId
        });
    }

    /**
     * Switch to a different chain
     */
    async switchChain(chainId) {
        try {
            this.showStatus(window.MESSAGE_TYPES.LOADING, window.WALLET_STATUS_MESSAGES.SWITCHING_CHAIN);

            const chainConfig = window.CHAIN_UTILS.getChainConfig(chainId);
            if (!chainConfig) {
                throw new Error(`Chain ${chainId} not supported`);
            }

            const hexChainId = chainConfig.hexChainId;

            try {
                // Try to switch to the chain
                await this.provider.request({
                    method: 'wallet_switchEthereumChain',
                    params: [{ chainId: hexChainId }]
                });

            } catch (switchError) {
                // Chain not added to wallet, try to add it
                if (switchError.code === 4902) {
                    await this.provider.request({
                        method: 'wallet_addEthereumChain',
                        params: [{
                            chainId: hexChainId,
                            chainName: chainConfig.name,
                            nativeCurrency: {
                                name: chainConfig.currency,
                                symbol: chainConfig.currency,
                                decimals: 18
                            },
                            rpcUrls: [chainConfig.rpcUrl],
                            blockExplorerUrls: [chainConfig.blockExplorer]
                        }]
                    });
                } else {
                    throw switchError;
                }
            }

            this.chainId = chainId;
            this.showStatus(window.MESSAGE_TYPES.SUCCESS, window.WALLET_STATUS_MESSAGES.CHAIN_SWITCHED);

        } catch (error) {
            console.error('Failed to switch chain:', error);

            if (error.code === 4001) {
                this.showStatus(window.MESSAGE_TYPES.WARNING, window.WALLET_STATUS_MESSAGES.REJECTED);
            } else {
                this.showStatus(window.MESSAGE_TYPES.ERROR, `${window.WALLET_STATUS_MESSAGES.ERROR}: ${error.message}`);
            }
        }
    }

    /**
     * Detect wallet provider
     */
    async detectProvider() {
        // Check for MetaMask
        if (window.ethereum && window.ethereum.isMetaMask) {
            console.log('🦊 MetaMask detected');
            return window.ethereum;
        }

        // Check for generic injected provider
        if (window.ethereum) {
            console.log('🔌 Injected wallet detected');
            return window.ethereum;
        }

        // No wallet found
        console.log('❌ No wallet provider found');
        return null;
    }

    /**
     * Detect wallet type
     */
    detectWalletType() {
        if (window.ethereum) {
            if (window.ethereum.isMetaMask) {
                return WALLET_PROVIDERS.METAMASK;
            }
            if (window.ethereum.isCoinbaseWallet) {
                return WALLET_PROVIDERS.COINBASE_WALLET;
            }
            return WALLET_PROVIDERS.INJECTED;
        }
        return WALLET_PROVIDERS.UNKNOWN;
    }

    /**
     * Update connection UI
     */
    updateConnectionUI() {
        // Update wallet address display
        const addressDisplay = document.getElementById(window.ELEMENT_IDS.WALLET_ADDRESS_DISPLAY);
        if (addressDisplay) {
            addressDisplay.textContent = this.isConnected ?
                this.formatAddress(this.walletAddress) :
                'Not Connected';
        }

        // Update chain display
        const chainDisplay = document.getElementById(window.ELEMENT_IDS.WALLET_CHAIN_DISPLAY);
        if (chainDisplay && this.isConnected) {
            const chainConfig = window.CHAIN_UTILS.getChainConfig(this.chainId);
            chainDisplay.textContent = chainConfig ? chainConfig.name : `Chain ${this.chainId}`;
        }

        // Toggle connect/disconnect buttons
        const connectBtn = document.querySelector(window.DATA_ACTIONS.CONNECT_WALLET);
        const disconnectBtn = document.querySelector(window.DATA_ACTIONS.DISCONNECT_WALLET);

        if (connectBtn) {
            connectBtn.style.display = this.isConnected ? 'none' : 'block';
        }

        if (disconnectBtn) {
            disconnectBtn.style.display = this.isConnected ? 'block' : 'none';
        }

        // Update wallet info container
        const infoContainer = document.getElementById(window.ELEMENT_IDS.WALLET_INFO_CONTAINER);
        if (infoContainer) {
            if (this.isConnected) {
                infoContainer.classList.remove(window.CSS_CLASSES.HIDDEN);
                infoContainer.classList.add(window.CSS_CLASSES.VISIBLE);
            } else {
                infoContainer.classList.add(window.CSS_CLASSES.HIDDEN);
                infoContainer.classList.remove(window.CSS_CLASSES.VISIBLE);
            }
        }

        // Update connection indicator in navigation
        const navIndicator = document.getElementById(window.ELEMENT_IDS.WALLET_NAV_INDICATOR);
        if (navIndicator) {
            navIndicator.className = this.isConnected ?
                `status-indicator ${window.CSS_CLASSES.STATUS_OPERATIONAL}` :
                `status-indicator ${window.CSS_CLASSES.STATUS_ERROR}`;
        }
    }

    /**
     * Format wallet address for display
     */
    formatAddress(address) {
        if (!address) return '';
        return `${address.slice(0, 6)}...${address.slice(-4)}`;
    }

    /**
     * Check session status with backend
     */
    async checkSessionStatus() {
        try {
            const response = await fetch(window.API_ENDPOINTS.WALLET.INFO, {
                headers: {
                    'X-CSRFToken': window.getCSRFToken()
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

    /**
     * Update status display - uses centralized showToast from common-utils.js
     */
    showStatus(type, message) {
        const statusEl = document.getElementById(window.ELEMENT_IDS.WALLET_STATUS_MESSAGE);
        if (statusEl) {
            statusEl.textContent = message;
            statusEl.className = `wallet-status-message ${type}`;
            statusEl.style.display = message ? 'block' : 'none';
        }

        // Also show toast notification
        if (window.showToast && message) {
            window.showToast(message, type);
        }

        // Console log with emoji
        if (message) {
            const emoji = {
                loading: '⏳',
                success: '✅',
                error: '❌',
                warning: '⚠️',
                info: 'ℹ️'
            };
            console.log(`${emoji[type] || '📝'} ${message}`);
        }
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
    document.addEventListener(window.CUSTOM_EVENTS.WALLET_CONNECTED, (event) => {
        console.log('🎉 Wallet connected event:', event.detail);

        // Reload page data if needed
        if (typeof refreshDashboardData === 'function') {
            refreshDashboardData();
        }
    });

    document.addEventListener(window.CUSTOM_EVENTS.WALLET_DISCONNECTED, (event) => {
        console.log('👋 Wallet disconnected event:', event.detail);

        // Handle disconnection in UI
        if (typeof handleWalletDisconnection === 'function') {
            handleWalletDisconnection();
        }
    });

    document.addEventListener(window.CUSTOM_EVENTS.WALLET_CHAIN_CHANGED, (event) => {
        console.log('⛓️ Chain changed event:', event.detail);

        // Handle chain change in UI
        if (typeof handleChainChange === 'function') {
            handleChainChange(event.detail.chainId);
        }
    });

    console.log('✅ Wallet Connection System ready');
});

// ============================================================================
// EXPORT FOR MODULE USE
// ============================================================================

if (typeof module !== 'undefined' && module.exports) {
    module.exports = WalletConnectionManager;
}

console.log('✅ Wallet Connection Manager v2.0 loaded successfully (refactored with centralized constants)');