/**
 * Trading Core Module - Main Coordinator
 * 
 * Integrates all trading modules into a unified TradingManager class.
 * Coordinates between data management, WebSocket connections, charts, UI,
 * orders, and transactions (Phase 6B).
 * 
 * This is the main entry point for the trading system.
 * 
 * File: dexproject/dashboard/static/js/trading-core.js
 */

import { getCsrfToken } from './trading-utils.js';
import { TradingDataManager } from './trading-data.js';
import { TradingWebSocketManager } from './trading-websocket.js';
import { TradingChartsManager } from './trading-charts.js';
import { TradingUIManager } from './trading-ui.js';
import { TradingOrdersManager } from './trading-orders.js';
import { TradingTransactionsManager } from './trading-transactions.js';

export class TradingManager {
    /**
     * Initialize the Trading Manager
     * 
     * Coordinates all trading subsystems and provides a unified interface.
     */
    constructor() {
        // Configuration
        this.baseUrl = '/api/trading';
        this.csrfToken = getCsrfToken();

        // Feature flags
        this.useTransactionManagerV2 = true;
        this.enableInteractiveCharts = true;

        // Initialize UI Manager first (for notifications)
        this.uiManager = new TradingUIManager(this.showNotification.bind(this));

        // Initialize Data Manager
        this.dataManager = new TradingDataManager(
            this.baseUrl,
            this.csrfToken
        );

        // Initialize WebSocket Manager
        this.websocketManager = new TradingWebSocketManager(
            this.handleWebSocketMessage.bind(this),
            this.handleWebSocketError.bind(this),
            this.handleWebSocketStatusChange.bind(this)
        );

        // Initialize Charts Manager
        this.chartsManager = new TradingChartsManager(
            this.csrfToken,
            this.showNotification.bind(this)
        );

        // Initialize Orders Manager
        this.ordersManager = new TradingOrdersManager(
            this.baseUrl,
            this.makeRequest.bind(this),
            this.showNotification.bind(this),
            this.handleTradeUpdate.bind(this)
        );

        // Initialize Transactions Manager (Phase 6B)
        this.transactionsManager = new TradingTransactionsManager(
            this.csrfToken,
            this.showNotification.bind(this),
            this.uiManager.getStatusBadgeClass.bind(this.uiManager)
        );

        // Real-time update handling
        this.eventSource = null;

        console.log('🚀 TradingManager initialized with Phase 3 Interactive Charts & Phase 6B Transaction Manager');

        // Initialize the system
        this.init();
    }

    // =============================================================================
    // INITIALIZATION
    // =============================================================================

    /**
     * Initialize trading functionality and event listeners
     */
    init() {
        this.bindEventListeners();
        this.startRealTimeUpdates();
        this.websocketManager.initializeTradingSocket();

        // Initialize charts if enabled
        if (this.enableInteractiveCharts) {
            this.chartsManager.initializeAllCharts();
            this.websocketManager.initializeChartsSocket();
        }

        this.loadInitialData();
        this.setupEventHandlers();
    }

    /**
     * Load initial trading data
     */
    async loadInitialData() {
        try {
            const data = await this.dataManager.loadAllData();

            // Update UI with loaded data
            this.uiManager.updatePositionsDisplay(data.positions);
            this.uiManager.updateTradeHistoryDisplay(data.trades);
            this.uiManager.updatePortfolioDisplay(data.portfolio);

            // Update charts with loaded data
            if (this.enableInteractiveCharts && data.positions) {
                this.chartsManager.updatePositionsChart(data.positions);
            }

        } catch (error) {
            console.error('Error loading initial trading data:', error);
            this.showNotification('Failed to load trading data', 'error');
        }
    }

    // =============================================================================
    // EVENT LISTENERS
    // =============================================================================

    /**
     * Bind event listeners for trading UI elements
     */
    bindEventListeners() {
        // Trading action buttons
        document.addEventListener('click', (e) => {
            // Buy action
            if (e.target.matches('[data-action="buy"]')) {
                e.preventDefault();
                const tokenAddress = e.target.dataset.tokenAddress;
                const amount = e.target.dataset.amount || '0.1';
                this.uiManager.showBuyOrderModal(tokenAddress, amount);
            }

            // Sell action
            if (e.target.matches('[data-action="sell"]')) {
                e.preventDefault();
                const tokenAddress = e.target.dataset.tokenAddress;
                const amount = e.target.dataset.amount || '100';
                this.uiManager.showSellOrderModal(tokenAddress, amount);
            }

            // Close position action
            if (e.target.matches('[data-action="close-position"]')) {
                e.preventDefault();
                const positionId = e.target.dataset.positionId;
                this.uiManager.showClosePositionModal(positionId);
            }

            // Start trading session
            if (e.target.matches('[data-action="start-session"]')) {
                e.preventDefault();
                this.startTradingSession();
            }

            // Stop trading session
            if (e.target.matches('[data-action="stop-session"]')) {
                e.preventDefault();
                this.stopTradingSession();
            }

            // Phase 6B: Cancel transaction button
            if (e.target.matches('[data-action="cancel-transaction"]')) {
                e.preventDefault();
                const transactionId = e.target.dataset.transactionId;
                this.transactionsManager.cancelTransaction(transactionId);
            }
        });

        // Form submissions
        document.addEventListener('submit', (e) => {
            if (e.target.matches('#buy-order-form')) {
                e.preventDefault();
                const formData = new FormData(e.target);

                // Use Transaction Manager V2 if enabled
                if (this.useTransactionManagerV2) {
                    this.transactionsManager.executeBuyOrderV2(formData);
                } else {
                    this.ordersManager.executeBuyOrder(formData);
                }

                this.uiManager.closeModal('buy-order-modal');
            }

            if (e.target.matches('#sell-order-form')) {
                e.preventDefault();
                const formData = new FormData(e.target);
                this.ordersManager.executeSellOrder(formData);
                this.uiManager.closeModal('sell-order-modal');
            }

            if (e.target.matches('#close-position-form')) {
                e.preventDefault();
                const formData = new FormData(e.target);
                const positionId = formData.get('position_id');
                const percentage = formData.get('percentage');
                this.ordersManager.closePosition(positionId, percentage);
            }
        });

        // Custom events
        document.addEventListener('buyOrderSubmit', (e) => {
            const formData = new FormData();
            formData.append('token_address', e.detail.token_address);
            formData.append('amount_eth', e.detail.amount_eth);

            if (this.useTransactionManagerV2) {
                this.transactionsManager.executeBuyOrderV2(formData);
            } else {
                this.ordersManager.executeBuyOrder(formData);
            }
        });

        document.addEventListener('sellOrderSubmit', (e) => {
            const formData = new FormData();
            formData.append('token_address', e.detail.token_address);
            formData.append('token_amount', e.detail.token_amount);
            this.ordersManager.executeSellOrder(formData);
        });

        document.addEventListener('closePositionSubmit', (e) => {
            this.ordersManager.closePosition(e.detail.position_id, e.detail.percentage);
        });
    }

    /**
     * Setup event handlers for page visibility and cleanup
     */
    setupEventHandlers() {
        // Handle page visibility changes
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                console.log('📱 Page hidden - maintaining connections');
            } else {
                console.log('📱 Page visible - ensuring connections');
                const status = this.websocketManager.getStatus();

                if (!status.trading.connected) {
                    this.websocketManager.initializeTradingSocket();
                }

                if (this.enableInteractiveCharts && !status.charts.connected) {
                    this.websocketManager.initializeChartsSocket();
                }
            }
        });

        // Handle beforeunload
        window.addEventListener('beforeunload', () => {
            this.destroy();
        });
    }

    // =============================================================================
    // WEBSOCKET MESSAGE HANDLING
    // =============================================================================

    /**
     * Handle WebSocket message routing
     * 
     * @param {Object} data - Message data
     * @param {string} source - Message source ('trading' or 'charts')
     */
    handleWebSocketMessage(data, source) {
        if (source === 'trading') {
            this.handleTradingMessage(data);
        } else if (source === 'charts') {
            this.handleChartsMessage(data);
        }
    }

    /**
     * Handle trading WebSocket messages
     * 
     * @param {Object} data - Message data
     */
    handleTradingMessage(data) {
        switch (data.type) {
            case 'transaction_update':
                // Phase 6B: Transaction Manager updates
                this.transactionsManager.handleTransactionUpdate(data);
                break;
            case 'trade_update':
                this.handleTradeUpdate(data.trade);
                break;
            case 'position_update':
                this.handlePositionUpdate(data.position);
                break;
            case 'portfolio_update':
                this.uiManager.updatePortfolioDisplay(data.portfolio);
                break;
            case 'connection_confirmed':
                console.log('✅ Trading WebSocket connection confirmed');
                break;
            default:
                console.log('📨 Unknown trading message type:', data.type);
        }
    }

    /**
     * Handle charts WebSocket messages
     * 
     * @param {Object} data - Message data
     */
    handleChartsMessage(data) {
        switch (data.type) {
            case 'price_update':
                this.chartsManager.updateCandlestick(data.data);
                break;
            case 'volume_update':
                this.chartsManager.updateVolumeChart(data.data);
                break;
            case 'depth_update':
                this.chartsManager.updateDepthChart(data.data);
                break;
            case 'portfolio_update':
                this.chartsManager.updatePortfolioChart(data.data);
                break;
            case 'position_update':
                this.chartsManager.updatePositionsChart(data.data);
                break;
        }
    }

    /**
     * Handle WebSocket errors
     * 
     * @param {Error} error - Error object
     * @param {string} source - Error source
     */
    handleWebSocketError(error, source) {
        console.error(`❌ WebSocket error (${source}):`, error);
    }

    /**
     * Handle WebSocket status changes
     * 
     * @param {string} status - Connection status
     * @param {string} source - Status source
     */
    handleWebSocketStatusChange(status, source) {
        console.log(`🔌 WebSocket status (${source}): ${status}`);

        if (status === 'failed') {
            this.showNotification(`${source} connection failed`, 'error');
        }
    }

    // =============================================================================
    // TRADE AND POSITION UPDATES
    // =============================================================================

    /**
     * Handle trade updates
     * 
     * @param {Object} trade - Trade object
     */
    handleTradeUpdate(trade) {
        this.dataManager.updateTrade(trade);

        const trades = Array.from(this.dataManager.trades.values());
        this.uiManager.updateTradeHistoryDisplay(trades);

        // Show notification for important updates
        if (trade.status === 'COMPLETED') {
            this.showNotification(`Trade ${trade.trade_id} completed successfully!`, 'success');
        } else if (trade.status === 'FAILED') {
            this.showNotification(`Trade ${trade.trade_id} failed: ${trade.error_message}`, 'error');
        }
    }

    /**
     * Handle position updates
     * 
     * @param {Object} position - Position object
     */
    handlePositionUpdate(position) {
        this.dataManager.updatePosition(position);

        const positions = Array.from(this.dataManager.positions.values());
        this.uiManager.updatePositionsDisplay(positions);

        // Update charts if enabled
        if (this.enableInteractiveCharts) {
            this.chartsManager.updatePositionsChart(positions);
        }
    }

    // =============================================================================
    // SERVER-SENT EVENTS (LEGACY FALLBACK)
    // =============================================================================

    /**
     * Start real-time updates via Server-Sent Events (fallback)
     */
    startRealTimeUpdates() {
        if (this.eventSource) {
            this.eventSource.close();
        }

        this.eventSource = new EventSource('/dashboard/metrics/stream/');

        this.eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleRealTimeUpdate(data);
            } catch (e) {
                console.error('Error parsing SSE data:', e);
            }
        };

        this.eventSource.onerror = (error) => {
            console.error('SSE connection error:', error);
            setTimeout(() => this.startRealTimeUpdates(), 5000);
        };
    }

    /**
     * Handle real-time updates from SSE
     * 
     * @param {Object} data - Update data
     */
    handleRealTimeUpdate(data) {
        if (data.type === 'trade_update') {
            this.handleTradeUpdate(data.trade);
        } else if (data.type === 'position_update') {
            this.handlePositionUpdate(data.position);
        } else if (data.type === 'portfolio_update') {
            this.uiManager.updatePortfolioDisplay(data.portfolio);
        }
    }

    // =============================================================================
    // TRADING ACTIONS
    // =============================================================================

    /**
     * Start a trading session
     * 
     * @param {Object} config - Session configuration
     */
    async startTradingSession(config = {}) {
        try {
            const result = await this.ordersManager.startTradingSession(config);

            if (result.success) {
                this.uiManager.updateSessionStatus(result.session);
                this.uiManager.toggleSessionUI(true);
            }

        } catch (error) {
            // Error already handled by ordersManager
        }
    }

    /**
     * Stop the active trading session
     */
    async stopTradingSession() {
        try {
            const result = await this.ordersManager.stopTradingSession();

            if (result.success) {
                this.uiManager.updateSessionStatus(null);
                this.uiManager.toggleSessionUI(false);
            }

        } catch (error) {
            // Error already handled by ordersManager
        }
    }

    // =============================================================================
    // UTILITY METHODS
    // =============================================================================

    /**
     * Make API request (delegates to dataManager)
     * 
     * @param {string} method - HTTP method
     * @param {string} endpoint - API endpoint
     * @param {Object} data - Request data
     * @returns {Promise<Object>} Response data
     */
    async makeRequest(method, endpoint, data = null) {
        return await this.dataManager.makeRequest(method, endpoint, data);
    }

    /**
     * Show notification (delegates to uiManager)
     * 
     * @param {string} message - Notification message
     * @param {string} type - Notification type
     * @param {number} duration - Display duration
     */
    showNotification(message, type = 'info', duration = 5000) {
        this.uiManager.showNotification(message, type, duration);
    }

    /**
     * Refresh all data
     */
    async refreshData() {
        try {
            const data = await this.dataManager.refreshAllData();

            this.uiManager.updatePositionsDisplay(data.positions);
            this.uiManager.updateTradeHistoryDisplay(data.trades);
            this.uiManager.updatePortfolioDisplay(data.portfolio);

            if (this.enableInteractiveCharts && data.positions) {
                this.chartsManager.updatePositionsChart(data.positions);
            }

            this.showNotification('Data refreshed successfully', 'success');

        } catch (error) {
            this.showNotification('Failed to refresh data', 'error');
        }
    }

    // =============================================================================
    // CLEANUP
    // =============================================================================

    /**
     * Cleanup and destroy
     */
    destroy() {
        // Close connections
        if (this.eventSource) {
            this.eventSource.close();
        }

        // Cleanup managers
        this.websocketManager.destroy();
        this.chartsManager.destroy();
        this.uiManager.destroy();
        this.ordersManager.destroy();
        this.transactionsManager.destroy();

        console.log('🧹 TradingManager cleanup completed');
    }
}

// Initialize trading manager when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    // Only initialize if we're on a page that needs trading functionality
    if (document.body.dataset.page === 'dashboard' ||
        document.body.dataset.page === 'trading' ||
        document.querySelector('[data-trading-enabled]')) {

        window.tradingManager = new TradingManager();
        console.log('✅ Trading functionality initialized with Phase 3 Interactive Charts & Phase 6B Transaction Manager');
    }
});

// Export for use in other scripts
window.TradingManager = TradingManager;