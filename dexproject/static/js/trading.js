/**
 * Trading Frontend Integration - Phase 5.1C Complete Implementation
 * 
 * Provides complete frontend integration for trading functionality,
 * connecting dashboard UI to trading API endpoints with real-time updates.
 * 
 * Features:
 * - Trade execution (buy/sell orders)
 * - Real-time position tracking
 * - Portfolio management
 * - Trading session management
 * - Live status updates and notifications
 * - Integration with existing dashboard components
 * 
 * File: dashboard/static/js/trading.js
 */

class TradingManager {
    constructor() {
        this.baseUrl = '/api/trading';
        this.csrfToken = this.getCsrfToken();
        this.eventSource = null;
        this.positions = new Map();
        this.trades = new Map();
        this.notifications = [];

        // Initialize trading functionality
        this.init();

        console.log('🚀 TradingManager initialized');
    }

    /**
     * Initialize trading functionality and event listeners
     */
    init() {
        this.bindEventListeners();
        this.startRealTimeUpdates();
        this.loadInitialData();
    }

    /**
     * Get CSRF token from meta tag or cookie
     */
    getCsrfToken() {
        const token = document.querySelector('meta[name="csrf-token"]');
        return token ? token.getAttribute('content') : '';
    }

    /**
     * Bind event listeners for trading UI elements
     */
    bindEventListeners() {
        // Trading action buttons
        document.addEventListener('click', (e) => {
            if (e.target.matches('[data-action="buy"]')) {
                e.preventDefault();
                const tokenAddress = e.target.dataset.tokenAddress;
                const amount = e.target.dataset.amount || '0.1';
                this.showBuyOrderModal(tokenAddress, amount);
            }

            if (e.target.matches('[data-action="sell"]')) {
                e.preventDefault();
                const tokenAddress = e.target.dataset.tokenAddress;
                const amount = e.target.dataset.amount || '100';
                this.showSellOrderModal(tokenAddress, amount);
            }

            if (e.target.matches('[data-action="close-position"]')) {
                e.preventDefault();
                const positionId = e.target.dataset.positionId;
                this.showClosePositionModal(positionId);
            }

            if (e.target.matches('[data-action="start-session"]')) {
                e.preventDefault();
                this.startTradingSession();
            }

            if (e.target.matches('[data-action="stop-session"]')) {
                e.preventDefault();
                this.stopTradingSession();
            }
        });

        // Form submissions
        document.addEventListener('submit', (e) => {
            if (e.target.matches('#buy-order-form')) {
                e.preventDefault();
                this.executeBuyOrder(new FormData(e.target));
            }

            if (e.target.matches('#sell-order-form')) {
                e.preventDefault();
                this.executeSellOrder(new FormData(e.target));
            }

            if (e.target.matches('#close-position-form')) {
                e.preventDefault();
                this.closePosition(new FormData(e.target));
            }
        });

        // Smart Lane analysis result handlers
        document.addEventListener('analysis:complete', (e) => {
            this.handleAnalysisResult(e.detail);
        });

        // Fast Lane configuration handlers
        document.addEventListener('fast-lane:configured', (e) => {
            this.handleFastLaneConfiguration(e.detail);
        });
    }

    /**
     * Start real-time updates for positions and trades
     */
    startRealTimeUpdates() {
        // Close existing connection
        if (this.eventSource) {
            this.eventSource.close();
        }

        // Start server-sent events for real-time updates
        this.eventSource = new EventSource('/dashboard/metrics/stream/');

        this.eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleRealTimeUpdate(data);
            } catch (e) {
                console.error('Error parsing real-time update:', e);
            }
        };

        this.eventSource.onerror = (error) => {
            console.error('Real-time updates connection error:', error);
            // Attempt to reconnect after 5 seconds
            setTimeout(() => this.startRealTimeUpdates(), 5000);
        };
    }

    /**
     * Load initial trading data
     */
    async loadInitialData() {
        try {
            await Promise.all([
                this.loadPositions(),
                this.loadTradeHistory(),
                this.loadPortfolioSummary()
            ]);
        } catch (error) {
            console.error('Error loading initial trading data:', error);
        }
    }

    // =============================================================================
    // TRADE EXECUTION METHODS
    // =============================================================================

    /**
     * Execute a buy order
     */
    async executeBuyOrder(formData) {
        const buyData = {
            token_address: formData.get('token_address'),
            amount_eth: formData.get('amount_eth'),
            slippage_tolerance: parseFloat(formData.get('slippage_tolerance') || '0.005'),
            gas_price_gwei: formData.get('gas_price_gwei') ? parseFloat(formData.get('gas_price_gwei')) : null,
            strategy_id: formData.get('strategy_id') || null,
            chain_id: parseInt(formData.get('chain_id') || '8453')
        };

        try {
            this.showNotification('Executing buy order...', 'info');

            const response = await this.makeRequest('POST', '/buy/', buyData);

            if (response.success) {
                this.showNotification(
                    `Buy order submitted successfully! Trade ID: ${response.trade_id}`,
                    'success'
                );

                // Update UI with pending trade
                this.addPendingTrade({
                    trade_id: response.trade_id,
                    trade_type: 'BUY',
                    status: 'PENDING',
                    token_address: buyData.token_address,
                    amount_eth: buyData.amount_eth,
                    created_at: new Date().toISOString()
                });

                // Close modal
                this.closeModal('buy-order-modal');

                // Start monitoring trade status
                this.monitorTradeStatus(response.trade_id, response.task_id);

            } else {
                throw new Error(response.error || 'Buy order failed');
            }

        } catch (error) {
            console.error('Buy order error:', error);
            this.showNotification(
                `Buy order failed: ${error.message}`,
                'error'
            );
        }
    }

    /**
     * Execute a sell order
     */
    async executeSellOrder(formData) {
        const sellData = {
            token_address: formData.get('token_address'),
            token_amount: formData.get('token_amount'),
            slippage_tolerance: parseFloat(formData.get('slippage_tolerance') || '0.005'),
            gas_price_gwei: formData.get('gas_price_gwei') ? parseFloat(formData.get('gas_price_gwei')) : null,
            chain_id: parseInt(formData.get('chain_id') || '8453')
        };

        try {
            this.showNotification('Executing sell order...', 'info');

            const response = await this.makeRequest('POST', '/sell/', sellData);

            if (response.success) {
                this.showNotification(
                    `Sell order submitted successfully! Trade ID: ${response.trade_id}`,
                    'success'
                );

                // Update UI with pending trade
                this.addPendingTrade({
                    trade_id: response.trade_id,
                    trade_type: 'SELL',
                    status: 'PENDING',
                    token_address: sellData.token_address,
                    token_amount: sellData.token_amount,
                    created_at: new Date().toISOString()
                });

                // Close modal
                this.closeModal('sell-order-modal');

                // Start monitoring trade status
                this.monitorTradeStatus(response.trade_id, response.task_id);

            } else {
                throw new Error(response.error || 'Sell order failed');
            }

        } catch (error) {
            console.error('Sell order error:', error);
            this.showNotification(
                `Sell order failed: ${error.message}`,
                'error'
            );
        }
    }

    /**
     * Close a trading position
     */
    async closePosition(formData) {
        const closeData = {
            position_id: formData.get('position_id'),
            percentage: parseFloat(formData.get('percentage') || '100'),
            slippage_tolerance: parseFloat(formData.get('slippage_tolerance') || '0.005'),
            gas_price_gwei: formData.get('gas_price_gwei') ? parseFloat(formData.get('gas_price_gwei')) : null
        };

        try {
            this.showNotification('Closing position...', 'info');

            const response = await this.makeRequest('POST', '/positions/close/', closeData);

            if (response.success) {
                this.showNotification(
                    `Position closure submitted successfully! ${closeData.percentage}% of position will be closed.`,
                    'success'
                );

                // Update position status in UI
                this.updatePositionStatus(closeData.position_id, 'CLOSING');

                // Close modal
                this.closeModal('close-position-modal');

                // Start monitoring position closure
                this.monitorTradeStatus(response.task_id);

            } else {
                throw new Error(response.error || 'Position closure failed');
            }

        } catch (error) {
            console.error('Position closure error:', error);
            this.showNotification(
                `Position closure failed: ${error.message}`,
                'error'
            );
        }
    }

    // =============================================================================
    // DATA LOADING METHODS
    // =============================================================================

    /**
     * Load current positions
     */
    async loadPositions() {
        try {
            const response = await this.makeRequest('GET', '/positions/');

            if (response.success) {
                this.positions.clear();
                response.positions.forEach(position => {
                    this.positions.set(position.position_id, position);
                });

                this.updatePositionsDisplay(response.positions);
                this.updatePortfolioSummary(response.summary);
            }

        } catch (error) {
            console.error('Error loading positions:', error);
        }
    }

    /**
     * Load trade history
     */
    async loadTradeHistory(limit = 50) {
        try {
            const response = await this.makeRequest('GET', `/history/?limit=${limit}`);

            if (response.success) {
                this.trades.clear();
                response.trades.forEach(trade => {
                    this.trades.set(trade.trade_id, trade);
                });

                this.updateTradeHistoryDisplay(response.trades);
            }

        } catch (error) {
            console.error('Error loading trade history:', error);
        }
    }

    /**
     * Load portfolio summary
     */
    async loadPortfolioSummary() {
        try {
            const response = await this.makeRequest('GET', '/portfolio/');

            if (response.success) {
                this.updatePortfolioDisplay(response.portfolio);
            }

        } catch (error) {
            console.error('Error loading portfolio summary:', error);
        }
    }

    // =============================================================================
    // TRADING SESSION MANAGEMENT
    // =============================================================================

    /**
     * Start a trading session
     */
    async startTradingSession(config = {}) {
        const sessionData = {
            strategy_id: config.strategy_id || null,
            max_position_size_usd: config.max_position_size_usd || 1000.0,
            risk_tolerance: config.risk_tolerance || 'MEDIUM',
            auto_execution: config.auto_execution || false
        };

        try {
            this.showNotification('Starting trading session...', 'info');

            const response = await this.makeRequest('POST', '/session/start/', sessionData);

            if (response.success) {
                this.showNotification('Trading session started successfully!', 'success');
                this.updateSessionStatus(response.session);

                // Enable session-dependent UI elements
                this.toggleSessionUI(true);

            } else {
                throw new Error(response.error || 'Failed to start trading session');
            }

        } catch (error) {
            console.error('Trading session start error:', error);
            this.showNotification(
                `Failed to start trading session: ${error.message}`,
                'error'
            );
        }
    }

    /**
     * Stop the active trading session
     */
    async stopTradingSession() {
        try {
            this.showNotification('Stopping trading session...', 'info');

            const response = await this.makeRequest('POST', '/session/stop/');

            if (response.success) {
                this.showNotification('Trading session stopped successfully!', 'success');
                this.updateSessionStatus(null);

                // Disable session-dependent UI elements
                this.toggleSessionUI(false);

            } else {
                throw new Error(response.error || 'Failed to stop trading session');
            }

        } catch (error) {
            console.error('Trading session stop error:', error);
            this.showNotification(
                `Failed to stop trading session: ${error.message}`,
                'error'
            );
        }
    }

    // =============================================================================
    // UI UPDATE METHODS
    // =============================================================================

    /**
     * Update positions display in dashboard
     */
    updatePositionsDisplay(positions) {
        const container = document.getElementById('positions-container');
        if (!container) return;

        if (positions.length === 0) {
            container.innerHTML = `
                <div class="text-center py-4 text-muted">
                    <i class="bi bi-inbox display-4 d-block mb-3"></i>
                    <p>No open positions</p>
                </div>
            `;
            return;
        }

        const positionsHtml = positions.map(position => `
            <div class="card mb-3" data-position-id="${position.position_id}">
                <div class="card-body">
                    <div class="row align-items-center">
                        <div class="col-md-3">
                            <h6 class="mb-1">${position.token_symbol}</h6>
                            <small class="text-muted">${position.token_name}</small>
                        </div>
                        <div class="col-md-2">
                            <div class="text-end">
                                <div class="fw-bold">${position.current_amount}</div>
                                <small class="text-muted">Tokens</small>
                            </div>
                        </div>
                        <div class="col-md-2">
                            <div class="text-end">
                                <div class="fw-bold">$${parseFloat(position.current_value_usd).toFixed(2)}</div>
                                <small class="text-muted">Current Value</small>
                            </div>
                        </div>
                        <div class="col-md-2">
                            <div class="text-end">
                                <div class="fw-bold ${parseFloat(position.unrealized_pnl_usd) >= 0 ? 'text-success' : 'text-danger'}">
                                    ${parseFloat(position.unrealized_pnl_usd) >= 0 ? '+' : ''}$${parseFloat(position.unrealized_pnl_usd).toFixed(2)}
                                </div>
                                <small class="text-muted">${position.unrealized_pnl_percent}%</small>
                            </div>
                        </div>
                        <div class="col-md-1">
                            <span class="badge ${this.getStatusBadgeClass(position.status)}">${position.status}</span>
                        </div>
                        <div class="col-md-2">
                            <div class="btn-group btn-group-sm">
                                <button class="btn btn-outline-primary" 
                                        data-action="close-position" 
                                        data-position-id="${position.position_id}">
                                    <i class="bi bi-x-circle me-1"></i>Close
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `).join('');

        container.innerHTML = positionsHtml;
    }

    /**
     * Update trade history display
     */
    updateTradeHistoryDisplay(trades) {
        const container = document.getElementById('trade-history-container');
        if (!container) return;

        if (trades.length === 0) {
            container.innerHTML = `
                <div class="text-center py-4 text-muted">
                    <i class="bi bi-clock-history display-4 d-block mb-3"></i>
                    <p>No trade history</p>
                </div>
            `;
            return;
        }

        const tradesHtml = trades.map(trade => `
            <div class="card mb-2" data-trade-id="${trade.trade_id}">
                <div class="card-body py-2">
                    <div class="row align-items-center">
                        <div class="col-md-2">
                            <span class="badge ${this.getTradeBadgeClass(trade.trade_type)}">${trade.trade_type}</span>
                        </div>
                        <div class="col-md-2">
                            <div class="fw-bold">${trade.token_symbol}</div>
                        </div>
                        <div class="col-md-2">
                            <div class="text-end">
                                ${trade.amount_in ? `${trade.amount_in} ETH` : `${trade.amount_out} tokens`}
                            </div>
                        </div>
                        <div class="col-md-2">
                            <div class="text-end">
                                ${trade.execution_price ? `$${parseFloat(trade.execution_price).toFixed(4)}` : '-'}
                            </div>
                        </div>
                        <div class="col-md-2">
                            <span class="badge ${this.getStatusBadgeClass(trade.status)}">${trade.status}</span>
                        </div>
                        <div class="col-md-2">
                            <small class="text-muted">${new Date(trade.created_at).toLocaleString()}</small>
                        </div>
                    </div>
                </div>
            </div>
        `).join('');

        container.innerHTML = tradesHtml;
    }

    /**
     * Update portfolio summary display
     */
    updatePortfolioDisplay(portfolio) {
        // Update total portfolio value
        const totalValueEl = document.getElementById('total-portfolio-value');
        if (totalValueEl) {
            totalValueEl.textContent = `$${parseFloat(portfolio.total_value_usd || 0).toFixed(2)}`;
        }

        // Update total P&L
        const totalPnlEl = document.getElementById('total-pnl');
        if (totalPnlEl) {
            const pnl = parseFloat(portfolio.total_pnl_usd || 0);
            totalPnlEl.textContent = `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`;
            totalPnlEl.className = `fw-bold ${pnl >= 0 ? 'text-success' : 'text-danger'}`;
        }

        // Update positions count
        const positionsCountEl = document.getElementById('positions-count');
        if (positionsCountEl) {
            positionsCountEl.textContent = portfolio.positions.open_count || 0;
        }

        // Update trades count
        const tradesCountEl = document.getElementById('trades-count');
        if (tradesCountEl) {
            tradesCountEl.textContent = portfolio.trades.total_count || 0;
        }
    }

    /**
     * Update session status display
     */
    updateSessionStatus(session) {
        const statusEl = document.getElementById('session-status');
        if (!statusEl) return;

        if (session) {
            statusEl.innerHTML = `
                <div class="d-flex align-items-center">
                    <span class="status-indicator status-operational me-2"></span>
                    <span>Session Active</span>
                    <small class="text-muted ms-2">${session.strategy_name || 'Default'}</small>
                </div>
            `;
        } else {
            statusEl.innerHTML = `
                <div class="d-flex align-items-center">
                    <span class="status-indicator status-error me-2"></span>
                    <span>No Active Session</span>
                </div>
            `;
        }
    }

    /**
     * Toggle session-dependent UI elements
     */
    toggleSessionUI(enabled) {
        const sessionButtons = document.querySelectorAll('[data-requires-session]');
        sessionButtons.forEach(button => {
            button.disabled = !enabled;
        });

        const startButton = document.querySelector('[data-action="start-session"]');
        const stopButton = document.querySelector('[data-action="stop-session"]');

        if (startButton) startButton.style.display = enabled ? 'none' : 'inline-block';
        if (stopButton) stopButton.style.display = enabled ? 'inline-block' : 'none';
    }

    // =============================================================================
    // MODAL AND UI HELPER METHODS
    // =============================================================================

    /**
     * Show buy order modal
     */
    showBuyOrderModal(tokenAddress, defaultAmount = '0.1') {
        const modal = this.createModal('buy-order-modal', 'Execute Buy Order', `
            <form id="buy-order-form">
                <div class="mb-3">
                    <label for="token_address" class="form-label">Token Address</label>
                    <input type="text" class="form-control" name="token_address" value="${tokenAddress}" readonly>
                </div>
                <div class="mb-3">
                    <label for="amount_eth" class="form-label">Amount (ETH)</label>
                    <input type="number" class="form-control" name="amount_eth" value="${defaultAmount}" 
                           min="0.001" max="1000" step="0.001" required>
                </div>
                <div class="mb-3">
                    <label for="slippage_tolerance" class="form-label">Slippage Tolerance (%)</label>
                    <input type="number" class="form-control" name="slippage_tolerance" value="0.5" 
                           min="0.1" max="50" step="0.1" required>
                </div>
                <div class="mb-3">
                    <label for="gas_price_gwei" class="form-label">Gas Price (Gwei) - Optional</label>
                    <input type="number" class="form-control" name="gas_price_gwei" 
                           min="1" max="1000" step="0.1" placeholder="Auto">
                </div>
                <input type="hidden" name="chain_id" value="8453">
                <div class="d-flex justify-content-end gap-2">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                    <button type="submit" class="btn btn-success">Execute Buy Order</button>
                </div>
            </form>
        `);

        modal.show();
    }

    /**
     * Show sell order modal
     */
    showSellOrderModal(tokenAddress, defaultAmount = '100') {
        const modal = this.createModal('sell-order-modal', 'Execute Sell Order', `
            <form id="sell-order-form">
                <div class="mb-3">
                    <label for="token_address" class="form-label">Token Address</label>
                    <input type="text" class="form-control" name="token_address" value="${tokenAddress}" readonly>
                </div>
                <div class="mb-3">
                    <label for="token_amount" class="form-label">Token Amount</label>
                    <input type="number" class="form-control" name="token_amount" value="${defaultAmount}" 
                           min="0.000001" step="any" required>
                </div>
                <div class="mb-3">
                    <label for="slippage_tolerance" class="form-label">Slippage Tolerance (%)</label>
                    <input type="number" class="form-control" name="slippage_tolerance" value="0.5" 
                           min="0.1" max="50" step="0.1" required>
                </div>
                <div class="mb-3">
                    <label for="gas_price_gwei" class="form-label">Gas Price (Gwei) - Optional</label>
                    <input type="number" class="form-control" name="gas_price_gwei" 
                           min="1" max="1000" step="0.1" placeholder="Auto">
                </div>
                <input type="hidden" name="chain_id" value="8453">
                <div class="d-flex justify-content-end gap-2">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                    <button type="submit" class="btn btn-danger">Execute Sell Order</button>
                </div>
            </form>
        `);

        modal.show();
    }

    /**
     * Show close position modal
     */
    showClosePositionModal(positionId) {
        const position = this.positions.get(positionId);
        if (!position) {
            this.showNotification('Position not found', 'error');
            return;
        }

        const modal = this.createModal('close-position-modal', 'Close Position', `
            <form id="close-position-form">
                <div class="mb-3">
                    <h6>${position.token_symbol} Position</h6>
                    <small class="text-muted">Current Amount: ${position.current_amount} tokens</small>
                </div>
                <div class="mb-3">
                    <label for="percentage" class="form-label">Percentage to Close (%)</label>
                    <input type="number" class="form-control" name="percentage" value="100" 
                           min="0.01" max="100" step="0.01" required>
                </div>
                <div class="mb-3">
                    <label for="slippage_tolerance" class="form-label">Slippage Tolerance (%)</label>
                    <input type="number" class="form-control" name="slippage_tolerance" value="0.5" 
                           min="0.1" max="50" step="0.1" required>
                </div>
                <div class="mb-3">
                    <label for="gas_price_gwei" class="form-label">Gas Price (Gwei) - Optional</label>
                    <input type="number" class="form-control" name="gas_price_gwei" 
                           min="1" max="1000" step="0.1" placeholder="Auto">
                </div>
                <input type="hidden" name="position_id" value="${positionId}">
                <div class="d-flex justify-content-end gap-2">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                    <button type="submit" class="btn btn-warning">Close Position</button>
                </div>
            </form>
        `);

        modal.show();
    }

    /**
     * Create and show a modal
     */
    createModal(id, title, content) {
        // Remove existing modal with same ID
        const existing = document.getElementById(id);
        if (existing) {
            existing.remove();
        }

        const modalHtml = `
            <div class="modal fade" id="${id}" tabindex="-1">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">${title}</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            ${content}
                        </div>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', modalHtml);

        return new bootstrap.Modal(document.getElementById(id));
    }

    /**
     * Close modal by ID
     */
    closeModal(modalId) {
        const modal = bootstrap.Modal.getInstance(document.getElementById(modalId));
        if (modal) {
            modal.hide();
        }
    }

    // =============================================================================
    // UTILITY METHODS
    // =============================================================================

    /**
     * Make HTTP request to trading API
     */
    async makeRequest(method, endpoint, data = null) {
        const url = `${this.baseUrl}${endpoint}`;
        const options = {
            method,
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.csrfToken,
            },
        };

        if (data) {
            options.body = JSON.stringify(data);
        }

        const response = await fetch(url, options);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        return await response.json();
    }

    /**
     * Show notification to user
     */
    showNotification(message, type = 'info') {
        const notification = {
            id: Date.now(),
            message,
            type,
            timestamp: new Date()
        };

        this.notifications.push(notification);
        this.displayNotification(notification);

        // Remove notification after 5 seconds
        setTimeout(() => {
            this.removeNotification(notification.id);
        }, 5000);
    }

    /**
     * Display notification in UI
     */
    displayNotification(notification) {
        const container = document.getElementById('notifications-container') || this.createNotificationsContainer();

        const alertClass = {
            'success': 'alert-success',
            'error': 'alert-danger',
            'warning': 'alert-warning',
            'info': 'alert-info'
        }[notification.type] || 'alert-info';

        const notificationHtml = `
            <div class="alert ${alertClass} alert-dismissible fade show" id="notification-${notification.id}">
                <i class="bi bi-${this.getNotificationIcon(notification.type)} me-2"></i>
                ${notification.message}
                <button type="button" class="btn-close" onclick="window.tradingManager.removeNotification(${notification.id})"></button>
            </div>
        `;

        container.insertAdjacentHTML('beforeend', notificationHtml);
    }

    /**
     * Remove notification from UI
     */
    removeNotification(notificationId) {
        const element = document.getElementById(`notification-${notificationId}`);
        if (element) {
            element.remove();
        }

        this.notifications = this.notifications.filter(n => n.id !== notificationId);
    }

    /**
     * Create notifications container if it doesn't exist
     */
    createNotificationsContainer() {
        const container = document.createElement('div');
        container.id = 'notifications-container';
        container.className = 'position-fixed top-0 end-0 p-3';
        container.style.zIndex = '9999';
        document.body.appendChild(container);
        return container;
    }

    /**
     * Get notification icon based on type
     */
    getNotificationIcon(type) {
        const icons = {
            'success': 'check-circle',
            'error': 'exclamation-triangle',
            'warning': 'exclamation-triangle',
            'info': 'info-circle'
        };
        return icons[type] || 'info-circle';
    }

    /**
     * Get badge class for status
     */
    getStatusBadgeClass(status) {
        const classes = {
            'OPEN': 'bg-success',
            'CLOSED': 'bg-secondary',
            'PENDING': 'bg-warning',
            'COMPLETED': 'bg-success',
            'FAILED': 'bg-danger',
            'CANCELLED': 'bg-secondary',
            'CLOSING': 'bg-warning'
        };
        return classes[status] || 'bg-secondary';
    }

    /**
     * Get badge class for trade type
     */
    getTradeBadgeClass(tradeType) {
        return tradeType === 'BUY' ? 'bg-success' : 'bg-danger';
    }

    /**
     * Handle real-time updates from server
     */
    handleRealTimeUpdate(data) {
        if (data.type === 'trade_update') {
            this.handleTradeUpdate(data.trade);
        } else if (data.type === 'position_update') {
            this.handlePositionUpdate(data.position);
        } else if (data.type === 'portfolio_update') {
            this.updatePortfolioDisplay(data.portfolio);
        }
    }

    /**
     * Handle trade status updates
     */
    handleTradeUpdate(trade) {
        this.trades.set(trade.trade_id, trade);

        // Update UI if trade element exists
        const tradeElement = document.querySelector(`[data-trade-id="${trade.trade_id}"]`);
        if (tradeElement) {
            const statusBadge = tradeElement.querySelector('.badge');
            if (statusBadge) {
                statusBadge.className = `badge ${this.getStatusBadgeClass(trade.status)}`;
                statusBadge.textContent = trade.status;
            }
        }

        // Show notification for completed/failed trades
        if (trade.status === 'COMPLETED') {
            this.showNotification(
                `Trade completed successfully! ${trade.trade_type} ${trade.token_symbol}`,
                'success'
            );
        } else if (trade.status === 'FAILED') {
            this.showNotification(
                `Trade failed: ${trade.error_message || 'Unknown error'}`,
                'error'
            );
        }
    }

    /**
     * Handle position updates
     */
    handlePositionUpdate(position) {
        this.positions.set(position.position_id, position);

        // Update UI if position element exists
        const positionElement = document.querySelector(`[data-position-id="${position.position_id}"]`);
        if (positionElement) {
            // Update current value and P&L
            const valueEl = positionElement.querySelector('.current-value');
            const pnlEl = positionElement.querySelector('.unrealized-pnl');

            if (valueEl) {
                valueEl.textContent = `$${parseFloat(position.current_value_usd).toFixed(2)}`;
            }

            if (pnlEl) {
                const pnl = parseFloat(position.unrealized_pnl_usd);
                pnlEl.textContent = `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`;
                pnlEl.className = `fw-bold ${pnl >= 0 ? 'text-success' : 'text-danger'}`;
            }
        }
    }

    /**
     * Monitor trade status via polling
     */
    async monitorTradeStatus(tradeId, taskId) {
        const maxAttempts = 30; // Monitor for 5 minutes (10s intervals)
        let attempts = 0;

        const checkStatus = async () => {
            try {
                attempts++;

                const response = await this.makeRequest('GET', `/history/?trade_id=${tradeId}`);

                if (response.success && response.trades.length > 0) {
                    const trade = response.trades[0];

                    if (trade.status === 'COMPLETED' || trade.status === 'FAILED') {
                        this.handleTradeUpdate(trade);
                        return; // Stop monitoring
                    }
                }

                if (attempts < maxAttempts) {
                    setTimeout(checkStatus, 10000); // Check again in 10 seconds
                }

            } catch (error) {
                console.error('Error monitoring trade status:', error);
            }
        };

        // Start monitoring after 5 seconds
        setTimeout(checkStatus, 5000);
    }

    /**
     * Handle Smart Lane analysis results
     */
    handleAnalysisResult(analysisResult) {
        // Add execute trade buttons to analysis results
        if (analysisResult.recommendation && analysisResult.recommendation !== 'HOLD') {
            this.addTradeButtonsToAnalysis(analysisResult);
        }
    }

    /**
     * Add trade execution buttons to analysis results
     */
    addTradeButtonsToAnalysis(analysisResult) {
        const analysisContainer = document.getElementById('smart-lane-analysis-result');
        if (!analysisContainer) return;

        const recommendation = analysisResult.recommendation;
        const tokenAddress = analysisResult.token_address;

        let buttonsHtml = '';

        if (recommendation === 'BUY' || recommendation === 'STRONG_BUY') {
            buttonsHtml += `
                <button class="btn btn-success me-2" 
                        data-action="buy" 
                        data-token-address="${tokenAddress}"
                        data-amount="${analysisResult.suggested_amount || '0.1'}">
                    <i class="bi bi-cart-plus me-1"></i>Execute Buy Order
                </button>
            `;
        }

        if (recommendation === 'SELL' || recommendation === 'STRONG_SELL') {
            buttonsHtml += `
                <button class="btn btn-danger me-2" 
                        data-action="sell" 
                        data-token-address="${tokenAddress}"
                        data-amount="${analysisResult.suggested_amount || '100'}">
                    <i class="bi bi-cart-dash me-1"></i>Execute Sell Order
                </button>
            `;
        }

        if (buttonsHtml) {
            const actionsDiv = analysisContainer.querySelector('.analysis-actions') ||
                this.createAnalysisActionsDiv(analysisContainer);

            actionsDiv.innerHTML = buttonsHtml;
        }
    }

    /**
     * Create analysis actions div if it doesn't exist
     */
    createAnalysisActionsDiv(container) {
        const actionsDiv = document.createElement('div');
        actionsDiv.className = 'analysis-actions mt-3 p-3 border-top';
        container.appendChild(actionsDiv);
        return actionsDiv;
    }

    /**
     * Handle Fast Lane configuration
     */
    handleFastLaneConfiguration(config) {
        // Enable Fast Lane trading capabilities
        this.fastLaneConfig = config;

        // Update UI to show Fast Lane is ready
        const statusEl = document.getElementById('fast-lane-status');
        if (statusEl) {
            statusEl.innerHTML = `
                <span class="status-indicator status-operational me-2"></span>
                <span>Fast Lane Ready</span>
            `;
        }
    }

    /**
     * Add pending trade to UI immediately
     */
    addPendingTrade(trade) {
        // Add to trades map
        this.trades.set(trade.trade_id, trade);

        // Update trade history display
        this.loadTradeHistory();

        // Show in quick stats
        const pendingTradesEl = document.getElementById('pending-trades-count');
        if (pendingTradesEl) {
            const currentCount = parseInt(pendingTradesEl.textContent) || 0;
            pendingTradesEl.textContent = currentCount + 1;
        }
    }

    /**
     * Update position status in UI
     */
    updatePositionStatus(positionId, status) {
        const positionElement = document.querySelector(`[data-position-id="${positionId}"]`);
        if (positionElement) {
            const statusBadge = positionElement.querySelector('.badge');
            if (statusBadge) {
                statusBadge.className = `badge ${this.getStatusBadgeClass(status)}`;
                statusBadge.textContent = status;
            }
        }
    }

    /**
     * Cleanup method
     */
    destroy() {
        if (this.eventSource) {
            this.eventSource.close();
        }

        // Remove event listeners
        document.removeEventListener('click', this.boundClickHandler);
        document.removeEventListener('submit', this.boundSubmitHandler);
    }
}

// Initialize trading manager when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    // Only initialize if we're on a page that needs trading functionality
    if (document.body.dataset.page === 'dashboard' ||
        document.body.dataset.page === 'trading' ||
        document.querySelector('[data-trading-enabled]')) {

        window.tradingManager = new TradingManager();
        console.log('✅ Trading functionality initialized');
    }
});

// Export for use in other scripts
window.TradingManager = TradingManager;