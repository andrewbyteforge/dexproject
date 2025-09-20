/**
 * Wallet Connection Module
 * 
 * Complete frontend implementation for SIWE (Sign-In with Ethereum) wallet connection.
 * Integrates with MetaMask, WalletConnect, and other Web3 providers.
 * 
 * Phase 5.1B Frontend Implementation
 * File: static/js/wallet-connection.js
 */

class WalletConnectionManager {
    constructor() {
        this.isConnected = false;
        this.walletAddress = null;
        this.walletType = null;
        this.chainId = null;
        this.provider = null;
        this.signer = null;

        // Supported chains
        this.supportedChains = {
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
        };

        // Default to Base Sepolia for development
        this.targetChainId = 84532;

        this.init();
    }

    /**
     * Initialize wallet connection manager
     */
    async init() {
        console.log('🔗 Initializing Wallet Connection Manager...');

        // Check if already connected from previous session
        await this.checkExistingConnection();

        // Setup event listeners
        this.setupEventListeners();

        // Setup wallet provider listeners
        this.setupWalletListeners();

        console.log('✅ Wallet Connection Manager initialized');
    }

    /**
     * Check for existing wallet connection
     */
    async checkExistingConnection() {
        try {
            // Check if wallet is connected in session
            const sessionData = await this.checkSessionStatus();
            if (sessionData && sessionData.connected) {
                await this.restoreWalletConnection(sessionData);
            }
        } catch (error) {
            console.log('No existing wallet connection found');
        }
    }

    /**
     * Setup event listeners for UI interactions
     */
    setupEventListeners() {
        // Connect wallet button
        document.addEventListener('click', (e) => {
            if (e.target.matches('[data-action="connect-wallet"]')) {
                e.preventDefault();
                this.connectWallet();
            }

            if (e.target.matches('[data-action="disconnect-wallet"]')) {
                e.preventDefault();
                this.disconnectWallet();
            }

            if (e.target.matches('[data-action="switch-chain"]')) {
                e.preventDefault();
                const chainId = parseInt(e.target.dataset.chainId);
                this.switchChain(chainId);
            }
        });
    }

    /**
     * Setup wallet provider event listeners
     */
    setupWalletListeners() {
        if (window.ethereum) {
            // Account changes
            window.ethereum.on('accountsChanged', (accounts) => {
                console.log('👤 Accounts changed:', accounts);
                if (accounts.length === 0) {
                    this.handleDisconnection();
                } else if (accounts[0] !== this.walletAddress) {
                    this.handleAccountChange(accounts[0]);
                }
            });

            // Chain changes
            window.ethereum.on('chainChanged', (chainId) => {
                console.log('⛓️ Chain changed:', chainId);
                this.handleChainChange(parseInt(chainId, 16));
            });

            // Disconnection
            window.ethereum.on('disconnect', () => {
                console.log('🔌 Wallet disconnected');
                this.handleDisconnection();
            });
        }
    }

    /**
     * Connect wallet using available provider
     */
    async connectWallet() {
        try {
            this.showLoading('Connecting wallet...');

            // Detect available providers
            const provider = await this.detectProvider();
            if (!provider) {
                throw new Error('No Web3 wallet detected. Please install MetaMask or another Web3 wallet.');
            }

            // Request account access
            const accounts = await provider.request({
                method: 'eth_requestAccounts'
            });

            if (!accounts || accounts.length === 0) {
                throw new Error('No accounts found. Please unlock your wallet.');
            }

            this.walletAddress = accounts[0];
            this.provider = provider;

            // Get chain ID
            const chainId = await provider.request({ method: 'eth_chainId' });
            this.chainId = parseInt(chainId, 16);

            // Detect wallet type
            this.walletType = this.detectWalletType(provider);

            console.log(`🎯 Connected to ${this.walletType}: ${this.walletAddress}`);
            console.log(`⛓️ Chain: ${this.chainId} (${this.supportedChains[this.chainId]?.name || 'Unknown'})`);

            // Check if we're on the correct chain
            if (this.chainId !== this.targetChainId) {
                const shouldSwitch = confirm(
                    `You're connected to ${this.supportedChains[this.chainId]?.name || 'Unknown Network'}. ` +
                    `Switch to ${this.supportedChains[this.targetChainId].name} for optimal experience?`
                );

                if (shouldSwitch) {
                    await this.switchChain(this.targetChainId);
                }
            }

            // Generate and sign SIWE message
            await this.authenticateWithSIWE();

        } catch (error) {
            console.error('❌ Wallet connection failed:', error);
            this.showError(error.message);
        } finally {
            this.hideLoading();
        }
    }

    /**
     * Authenticate using SIWE (Sign-In with Ethereum)
     */
    async authenticateWithSIWE() {
        try {
            this.showLoading('Generating authentication message...');

            // Generate SIWE message from backend
            const response = await fetch('/api/wallet/auth/siwe/generate/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({
                    wallet_address: this.walletAddress,
                    chain_id: this.chainId
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Failed to generate SIWE message');
            }

            const { message } = await response.json();
            console.log('📝 SIWE message generated');

            this.showLoading('Please sign the message in your wallet...');

            // Sign message with wallet
            const signature = await this.provider.request({
                method: 'personal_sign',
                params: [message, this.walletAddress]
            });

            console.log('✏️ Message signed');

            this.showLoading('Authenticating...');

            // Authenticate with backend
            const authResponse = await fetch('/api/wallet/auth/siwe/authenticate/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({
                    wallet_address: this.walletAddress,
                    chain_id: this.chainId,
                    message: message,
                    signature: signature,
                    wallet_type: this.walletType
                })
            });

            if (!authResponse.ok) {
                const errorData = await authResponse.json();
                throw new Error(errorData.error || 'Authentication failed');
            }

            const authData = await authResponse.json();
            console.log('🎉 Authentication successful:', authData);

            // Update connection state
            this.isConnected = true;
            this.sessionId = authData.session_id;
            this.walletId = authData.wallet_id;

            // Update UI
            this.updateConnectionUI();
            this.showSuccess('Wallet connected successfully!');

            // Trigger custom event for other components
            this.dispatchConnectionEvent('wallet:connected', {
                address: this.walletAddress,
                chainId: this.chainId,
                walletType: this.walletType,
                walletId: this.walletId
            });

        } catch (error) {
            console.error('❌ SIWE authentication failed:', error);
            throw error;
        }
    }

    /**
     * Disconnect wallet
     */
    async disconnectWallet() {
        try {
            this.showLoading('Disconnecting wallet...');

            // Call logout endpoint
            if (this.isConnected) {
                await fetch('/api/wallet/auth/logout/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCSRFToken()
                    }
                });
            }

            // Reset state
            this.handleDisconnection();

            this.showSuccess('Wallet disconnected successfully!');

        } catch (error) {
            console.error('❌ Disconnect error:', error);
            this.showError('Failed to disconnect wallet');
        } finally {
            this.hideLoading();
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

        this.updateConnectionUI();

        // Trigger custom event
        this.dispatchConnectionEvent('wallet:disconnected');
    }

    /**
     * Handle account change
     */
    async handleAccountChange(newAddress) {
        console.log('👤 Account changed to:', newAddress);

        if (this.isConnected) {
            // Disconnect current session and reconnect with new account
            await this.disconnectWallet();

            // Small delay before reconnecting
            setTimeout(async () => {
                try {
                    await this.connectWallet();
                } catch (error) {
                    console.error('Failed to reconnect with new account:', error);
                }
            }, 1000);
        }
    }

    /**
     * Handle chain change
     */
    handleChainChange(newChainId) {
        console.log('⛓️ Chain changed to:', newChainId);

        this.chainId = newChainId;
        this.updateConnectionUI();

        // Check if new chain is supported
        if (!this.supportedChains[newChainId]) {
            this.showWarning(`Connected to unsupported network. Please switch to ${this.supportedChains[this.targetChainId].name}.`);
        }

        // Trigger custom event
        this.dispatchConnectionEvent('wallet:chainChanged', { chainId: newChainId });
    }

    /**
     * Switch to specific chain
     */
    async switchChain(chainId) {
        try {
            const chain = this.supportedChains[chainId];
            if (!chain) {
                throw new Error(`Chain ${chainId} not supported`);
            }

            this.showLoading(`Switching to ${chain.name}...`);

            const chainIdHex = '0x' + chainId.toString(16);

            try {
                // Try to switch to the chain
                await this.provider.request({
                    method: 'wallet_switchEthereumChain',
                    params: [{ chainId: chainIdHex }]
                });
            } catch (switchError) {
                // If chain is not added, add it first
                if (switchError.code === 4902) {
                    await this.provider.request({
                        method: 'wallet_addEthereumChain',
                        params: [{
                            chainId: chainIdHex,
                            chainName: chain.name,
                            rpcUrls: [chain.rpcUrl],
                            blockExplorerUrls: [chain.blockExplorer],
                            nativeCurrency: {
                                name: chain.currency,
                                symbol: chain.currency,
                                decimals: 18
                            }
                        }]
                    });
                } else {
                    throw switchError;
                }
            }

            this.showSuccess(`Switched to ${chain.name}`);

        } catch (error) {
            console.error('❌ Chain switch failed:', error);
            this.showError(`Failed to switch chain: ${error.message}`);
        } finally {
            this.hideLoading();
        }
    }

    /**
     * Detect available Web3 provider
     */
    async detectProvider() {
        // MetaMask or other injected provider
        if (window.ethereum) {
            return window.ethereum;
        }

        // WalletConnect (future implementation)
        // if (window.WalletConnect) {
        //     return this.initWalletConnect();
        // }

        return null;
    }

    /**
     * Detect wallet type from provider
     */
    detectWalletType(provider) {
        if (provider.isMetaMask) return 'METAMASK';
        if (provider.isCoinbaseWallet) return 'COINBASE_WALLET';
        if (provider.isRainbow) return 'RAINBOW';
        if (provider.isTrust) return 'TRUST_WALLET';

        return 'OTHER';
    }

    /**
     * Update UI to reflect connection state
     */
    updateConnectionUI() {
        const connectBtn = document.getElementById('wallet-connect-btn');
        const disconnectBtn = document.getElementById('wallet-disconnect-btn');
        const walletInfo = document.getElementById('wallet-info');
        const walletAddress = document.getElementById('wallet-address');
        const walletChain = document.getElementById('wallet-chain');
        const walletStatus = document.getElementById('wallet-status');

        if (this.isConnected) {
            // Show connected state
            if (connectBtn) connectBtn.style.display = 'none';
            if (disconnectBtn) disconnectBtn.style.display = 'block';
            if (walletInfo) walletInfo.style.display = 'block';

            // Update wallet details
            if (walletAddress) {
                walletAddress.textContent = this.formatAddress(this.walletAddress);
                walletAddress.title = this.walletAddress;
            }

            if (walletChain) {
                const chainName = this.supportedChains[this.chainId]?.name || 'Unknown';
                walletChain.textContent = chainName;
                walletChain.className = this.supportedChains[this.chainId] ? 'badge bg-success' : 'badge bg-warning';
            }

            if (walletStatus) {
                walletStatus.innerHTML = '<i class="bi bi-check-circle text-success me-1"></i>Connected';
            }

        } else {
            // Show disconnected state
            if (connectBtn) connectBtn.style.display = 'block';
            if (disconnectBtn) disconnectBtn.style.display = 'none';
            if (walletInfo) walletInfo.style.display = 'none';

            if (walletStatus) {
                walletStatus.innerHTML = '<i class="bi bi-x-circle text-danger me-1"></i>Not Connected';
            }
        }

        // Update connection indicator in navigation
        const navIndicator = document.getElementById('wallet-nav-indicator');
        if (navIndicator) {
            navIndicator.className = this.isConnected ?
                'status-indicator status-operational' :
                'status-indicator status-error';
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
            const response = await fetch('/api/wallet/info/', {
                headers: {
                    'X-CSRFToken': this.getCSRFToken()
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
        console.log('🔄 Restoring wallet connection...');

        this.isConnected = true;
        this.walletAddress = sessionData.wallet.address;
        this.walletType = sessionData.wallet.wallet_type;
        this.chainId = sessionData.wallet.primary_chain_id;
        this.walletId = sessionData.wallet.wallet_id;

        // Try to reconnect to provider
        const provider = await this.detectProvider();
        if (provider) {
            this.provider = provider;
        }

        this.updateConnectionUI();

        console.log('✅ Wallet connection restored');
    }

    /**
     * Get CSRF token for API requests
     */
    getCSRFToken() {
        const token = document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
            document.querySelector('meta[name=csrf-token]')?.content ||
            this.getCookie('csrftoken');
        return token;
    }

    /**
     * Get cookie value by name
     */
    getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
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
     * Show loading state
     */
    showLoading(message) {
        this.updateStatus('loading', message);
    }

    /**
     * Hide loading state
     */
    hideLoading() {
        this.updateStatus('', '');
    }

    /**
     * Show success message
     */
    showSuccess(message) {
        this.updateStatus('success', message);
        setTimeout(() => this.hideLoading(), 3000);
    }

    /**
     * Show error message
     */
    showError(message) {
        this.updateStatus('error', message);
        setTimeout(() => this.hideLoading(), 5000);
    }

    /**
     * Show warning message
     */
    showWarning(message) {
        this.updateStatus('warning', message);
        setTimeout(() => this.hideLoading(), 4000);
    }

    /**
     * Update status display
     */
    updateStatus(type, message) {
        const statusEl = document.getElementById('wallet-status-message');
        if (statusEl) {
            statusEl.textContent = message;
            statusEl.className = `wallet-status-message ${type}`;
            statusEl.style.display = message ? 'block' : 'none';
        }

        // Also show in console for debugging
        if (message) {
            const emoji = {
                loading: '⏳',
                success: '✅',
                error: '❌',
                warning: '⚠️'
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

// Initialize wallet connection manager when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 Initializing Wallet Connection System...');

    // Initialize global wallet manager
    window.walletManager = new WalletConnectionManager();

    // Listen for wallet events
    document.addEventListener('wallet:connected', (event) => {
        console.log('🎉 Wallet connected event:', event.detail);

        // Reload page data if needed
        if (typeof refreshDashboardData === 'function') {
            refreshDashboardData();
        }
    });

    document.addEventListener('wallet:disconnected', (event) => {
        console.log('👋 Wallet disconnected event:', event.detail);

        // Handle disconnection in UI
        if (typeof handleWalletDisconnection === 'function') {
            handleWalletDisconnection();
        }
    });

    document.addEventListener('wallet:chainChanged', (event) => {
        console.log('⛓️ Chain changed event:', event.detail);

        // Handle chain change in UI
        if (typeof handleChainChange === 'function') {
            handleChainChange(event.detail.chainId);
        }
    });

    console.log('✅ Wallet Connection System ready');
});

// Export for module use
if (typeof module !== 'undefined' && module.exports) {
    module.exports = WalletConnectionManager;
}