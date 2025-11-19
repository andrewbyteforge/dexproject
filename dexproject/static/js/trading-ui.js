/**
 * Trading UI Management Module
 * 
 * Handles all UI interactions, notifications, modals, event listeners,
 * and display updates for the trading system. Manages user interface
 * state, form handling, and visual feedback.
 * 
 * File: dexproject/dashboard/static/js/trading-ui.js
 */

import { formatTimestamp, formatCurrency, formatPercentage } from './trading-utils.js';

export class TradingUIManager {
    /**
     * Initialize the UI manager
     * 
     * @param {Function} showNotification - External notification function
     */
    constructor(showNotification) {
        this.showNotification = showNotification || this.defaultShowNotification.bind(this);
        this.notifications = [];

        console.log('🎨 TradingUIManager initialized');
    }

    // =============================================================================
    // NOTIFICATION SYSTEM
    // =============================================================================

    /**
     * Default notification display implementation
     * 
     * @param {string} message - Notification message
     * @param {string} type - Notification type (success, error, warning, info)
     * @param {number} duration - Display duration in milliseconds
     */
    defaultShowNotification(message, type = 'info', duration = 5000) {
        const notification = {
            id: Date.now(),
            message,
            type,
            timestamp: new Date()
        };

        this.notifications.push(notification);
        this.displayNotification(notification);

        // Remove notification after duration
        setTimeout(() => {
            this.removeNotification(notification.id);
        }, duration);
    }

    /**
     * Display notification in UI
     * 
     * @param {Object} notification - Notification object
     */
    displayNotification(notification) {
        const container = document.getElementById('notifications-container') ||
            this.createNotificationsContainer();

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
                <button type="button" class="btn-close" data-notification-id="${notification.id}"></button>
            </div>
        `;

        container.insertAdjacentHTML('beforeend', notificationHtml);

        // Bind close button
        const closeBtn = container.querySelector(`[data-notification-id="${notification.id}"]`);
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.removeNotification(notification.id));
        }
    }

    /**
     * Remove notification from UI
     * 
     * @param {number} notificationId - Notification ID
     */
    removeNotification(notificationId) {
        const element = document.getElementById(`notification-${notificationId}`);
        if (element) {
            element.classList.remove('show');
            setTimeout(() => element.remove(), 150);
        }

        this.notifications = this.notifications.filter(n => n.id !== notificationId);
    }

    /**
     * Create notifications container if it doesn't exist
     * 
     * @returns {HTMLElement} Notifications container element
     */
    createNotificationsContainer() {
        const container = document.createElement('div');
        container.id = 'notifications-container';
        container.className = 'position-fixed top-0 end-0 p-3';
        container.style.zIndex = '9999';
        container.style.maxWidth = '400px';
        document.body.appendChild(container);
        return container;
    }

    /**
     * Get notification icon based on type
     * 
     * @param {string} type - Notification type
     * @returns {string} Bootstrap icon class
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

    // =============================================================================
    // DISPLAY UPDATES
    // =============================================================================

    /**
     * Update positions display in dashboard
     * 
     * @param {Array} positions - Array of position objects
     */
    updatePositionsDisplay(positions) {
        const container = document.getElementById('positions-container');
        if (!container) return;

        if (positions.length === 0) {
            container.innerHTML = `
                <div class="text-center py-4 text-muted">
                    <i class="bi bi-inbox display-4 d-block mb-3"></i>
                    <p>No open positions</p>
                    <small>Execute your first trade to see positions here</small>
                </div>
            `;
            return;
        }

        const positionsHtml = positions.map(position => `
            <div class="card mb-3" data-position-id="${position.position_id}">
                <div class="card-body">
                    <div class="row align-items-center">
                        <div class="col-md-3">
                            <h6 class="mb-1">${position.token_symbol || 'Unknown'}</h6>
                            <small class="text-muted">${position.token_name || 'Token'}</small>
                        </div>
                        <div class="col-md-2">
                            <div class="text-end">
                                <div class="fw-bold">${parseFloat(position.current_amount || 0).toFixed(4)}</div>
                                <small class="text-muted">Tokens</small>
                            </div>
                        </div>
                        <div class="col-md-2">
                            <div class="text-end">
                                <div class="fw-bold">${formatCurrency(position.current_value_usd)}</div>
                                <small class="text-muted">Current Value</small>
                            </div>
                        </div>
                        <div class="col-md-2">
                            <div class="text-end">
                                <div class="fw-bold ${parseFloat(position.unrealized_pnl_usd || 0) >= 0 ? 'text-success' : 'text-danger'}">
                                    ${parseFloat(position.unrealized_pnl_usd || 0) >= 0 ? '+' : ''}${formatCurrency(position.unrealized_pnl_usd)}
                                </div>
                                <small class="text-muted">${formatPercentage(position.unrealized_pnl_percent / 100)}</small>
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
     * 
     * @param {Array} trades - Array of trade objects
     */
    updateTradeHistoryDisplay(trades) {
        const container = document.getElementById('trade-history-container');
        if (!container) return;

        if (trades.length === 0) {
            container.innerHTML = `
                <div class="text-center py-4 text-muted">
                    <i class="bi bi-clock-history display-4 d-block mb-3"></i>
                    <p>No trade history</p>
                    <small>Your completed trades will appear here</small>
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
                            <div class="fw-bold">${trade.token_symbol || 'Token'}</div>
                        </div>
                        <div class="col-md-2">
                            <div class="text-end">
                                ${trade.amount_in ? `${parseFloat(trade.amount_in).toFixed(4)} ETH` :
                `${parseFloat(trade.amount_out || 0).toFixed(4)} tokens`}
                            </div>
                        </div>
                        <div class="col-md-2">
                            <div class="text-end">
                                ${trade.execution_price ? formatCurrency(trade.execution_price, 6) : '-'}
                            </div>
                        </div>
                        <div class="col-md-2">
                            <span class="badge ${this.getStatusBadgeClass(trade.status)}">${trade.status}</span>
                        </div>
                        <div class="col-md-2">
                            <small class="text-muted">${formatTimestamp(trade.created_at)}</small>
                        </div>
                    </div>
                </div>
            </div>
        `).join('');

        container.innerHTML = tradesHtml;
    }

    /**
     * Update portfolio summary display
     * 
     * @param {Object} portfolio - Portfolio data object
     */
    updatePortfolioDisplay(portfolio) {
        // Update total portfolio value
        const totalValueEl = document.getElementById('total-portfolio-value');
        if (totalValueEl) {
            totalValueEl.textContent = formatCurrency(portfolio.total_value_usd);
        }

        // Update total P&L
        const totalPnlEl = document.getElementById('total-pnl');
        if (totalPnlEl) {
            const pnl = parseFloat(portfolio.total_pnl_usd || 0);
            totalPnlEl.textContent = `${pnl >= 0 ? '+' : ''}${formatCurrency(pnl)}`;
            totalPnlEl.className = `metric-value ${pnl >= 0 ? 'text-success' : 'text-danger'}`;
        }

        // Update positions count
        const positionsCountEl = document.getElementById('positions-count');
        if (positionsCountEl) {
            positionsCountEl.textContent = portfolio.positions?.open_count || 0;
        }

        // Update trades count
        const tradesCountEl = document.getElementById('trades-count');
        if (tradesCountEl) {
            tradesCountEl.textContent = portfolio.trades?.total_count || 0;
        }

        // Phase 6B: Update gas savings stats
        const gasSavingsEl = document.getElementById('gas-savings-total');
        if (gasSavingsEl) {
            gasSavingsEl.textContent = formatPercentage(portfolio.gas_savings_percent / 100);
        }
    }

    /**
     * Update session status display
     * 
     * @param {Object|null} session - Session object or null
     */
    updateSessionStatus(session) {
        const statusEl = document.getElementById('session-status');
        if (statusEl) {
            statusEl.textContent = session ? 'Active' : 'Inactive';
            statusEl.className = `badge ${session ? 'bg-success' : 'bg-secondary'}`;
        }
    }

    /**
     * Toggle session-dependent UI elements
     * 
     * @param {boolean} enabled - Whether session is enabled
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

    /**
     * Set loading state for UI elements
     * 
     * @param {boolean} loading - Whether loading is active
     */
    setLoadingState(loading) {
        const buttons = document.querySelectorAll('.trading-submit-btn');
        buttons.forEach(btn => {
            btn.disabled = loading;
            const originalText = btn.dataset.originalText || btn.textContent;
            btn.dataset.originalText = originalText;
            btn.textContent = loading ? 'Processing...' : originalText;
        });
    }

    /**
     * Add pending trade indicator to UI
     * 
     * @param {Object} trade - Trade object
     */
    addPendingTradeIndicator(trade) {
        const pendingTradesEl = document.getElementById('pending-trades-count');
        if (pendingTradesEl) {
            const currentCount = parseInt(pendingTradesEl.textContent) || 0;
            pendingTradesEl.textContent = currentCount + 1;
        }
    }

    /**
     * Remove pending trade indicator from UI
     */
    removePendingTradeIndicator() {
        const pendingTradesEl = document.getElementById('pending-trades-count');
        if (pendingTradesEl) {
            const currentCount = parseInt(pendingTradesEl.textContent) || 0;
            if (currentCount > 0) {
                pendingTradesEl.textContent = currentCount - 1;
            }
        }
    }

    // =============================================================================
    // MODAL MANAGEMENT
    // =============================================================================

    /**
     * Show modal by ID
     * 
     * @param {string} modalId - Modal element ID
     */
    showModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            // Bootstrap 5 modal
            const bsModal = new bootstrap.Modal(modal);
            bsModal.show();
        }
    }

    /**
     * Close modal by ID
     * 
     * @param {string} modalId - Modal element ID
     */
    closeModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            const bsModal = bootstrap.Modal.getInstance(modal);
            if (bsModal) {
                bsModal.hide();
            }
        }
    }

    /**
     * Show buy order modal
     * 
     * @param {string} tokenAddress - Token contract address
     * @param {string} amount - Default amount
     */
    showBuyOrderModal(tokenAddress = '', amount = '0.1') {
        const modal = document.getElementById('buy-order-modal');
        if (modal) {
            // Pre-fill form if modal has form elements
            const tokenInput = modal.querySelector('[name="token_address"]');
            const amountInput = modal.querySelector('[name="amount_eth"]');

            if (tokenInput) tokenInput.value = tokenAddress;
            if (amountInput) amountInput.value = amount;

            this.showModal('buy-order-modal');
        } else {
            // Fallback to simple prompt
            const tokenAddr = prompt('Token Address:', tokenAddress);
            const ethAmount = prompt('ETH Amount:', amount);

            if (tokenAddr && ethAmount) {
                // Trigger form submission event
                const event = new CustomEvent('buyOrderSubmit', {
                    detail: { token_address: tokenAddr, amount_eth: ethAmount }
                });
                document.dispatchEvent(event);
            }
        }
    }

    /**
     * Show sell order modal
     * 
     * @param {string} tokenAddress - Token contract address
     * @param {string} amount - Default amount
     */
    showSellOrderModal(tokenAddress = '', amount = '100') {
        const modal = document.getElementById('sell-order-modal');
        if (modal) {
            const tokenInput = modal.querySelector('[name="token_address"]');
            const amountInput = modal.querySelector('[name="token_amount"]');

            if (tokenInput) tokenInput.value = tokenAddress;
            if (amountInput) amountInput.value = amount;

            this.showModal('sell-order-modal');
        } else {
            // Fallback to simple prompt
            const tokenAddr = prompt('Token Address:', tokenAddress);
            const tokenAmount = prompt('Token Amount:', amount);

            if (tokenAddr && tokenAmount) {
                const event = new CustomEvent('sellOrderSubmit', {
                    detail: { token_address: tokenAddr, token_amount: tokenAmount }
                });
                document.dispatchEvent(event);
            }
        }
    }

    /**
     * Show close position modal
     * 
     * @param {string} positionId - Position ID
     */
    showClosePositionModal(positionId) {
        const percentage = prompt('Close what percentage of position? (1-100)', '100');

        if (percentage && percentage > 0 && percentage <= 100) {
            const event = new CustomEvent('closePositionSubmit', {
                detail: { position_id: positionId, percentage: percentage }
            });
            document.dispatchEvent(event);
        }
    }

    // =============================================================================
    // BADGE AND STYLING HELPERS
    // =============================================================================

    /**
     * Get badge class for status
     * 
     * @param {string} status - Status value
     * @returns {string} Bootstrap badge class
     */
    getStatusBadgeClass(status) {
        const classes = {
            'OPEN': 'bg-success',
            'CLOSED': 'bg-secondary',
            'PENDING': 'bg-warning',
            'COMPLETED': 'bg-success',
            'FAILED': 'bg-danger',
            'CANCELLED': 'bg-secondary',
            'CLOSING': 'bg-warning',
            // Phase 6B Transaction Manager statuses
            'preparing': 'bg-info',
            'gas_optimizing': 'bg-warning',
            'ready_to_submit': 'bg-primary',
            'submitted': 'bg-info',
            'pending': 'bg-warning',
            'confirming': 'bg-warning',
            'confirmed': 'bg-success',
            'completed': 'bg-success',
            'failed': 'bg-danger',
            'cancelled': 'bg-secondary'
        };
        return classes[status?.toUpperCase()] || 'bg-secondary';
    }

    /**
     * Get badge class for trade type
     * 
     * @param {string} tradeType - Trade type (BUY/SELL)
     * @returns {string} Bootstrap badge class
     */
    getTradeBadgeClass(tradeType) {
        return tradeType === 'BUY' ? 'bg-success' : 'bg-danger';
    }

    /**
     * Get progress bar class for transaction status
     * 
     * @param {string} status - Transaction status
     * @returns {string} Bootstrap progress bar class
     */
    getProgressBarClass(status) {
        if (['completed', 'confirmed'].includes(status?.toLowerCase())) {
            return 'bg-success';
        } else if (status?.toLowerCase() === 'failed') {
            return 'bg-danger';
        } else if (status?.toLowerCase() === 'cancelled') {
            return 'bg-secondary';
        }
        return 'bg-info';
    }

    // =============================================================================
    // UTILITY METHODS
    // =============================================================================

    /**
     * Format transaction hash for display
     * 
     * @param {string} hash - Transaction hash
     * @returns {string} Truncated hash
     */
    formatHash(hash) {
        if (!hash || hash === '0x') return '';
        return `${hash.slice(0, 6)}...${hash.slice(-4)}`;
    }

    /**
     * Get blockchain explorer URL for transaction
     * 
     * @param {string} hash - Transaction hash
     * @param {number} chainId - Blockchain chain ID
     * @returns {string} Explorer URL
     */
    getExplorerUrl(hash, chainId = 8453) {
        const explorers = {
            1: 'https://etherscan.io/tx/',
            8453: 'https://basescan.org/tx/',
            42161: 'https://arbiscan.io/tx/',
            84532: 'https://sepolia.basescan.org/tx/' // Base Sepolia testnet
        };

        const baseUrl = explorers[chainId] || explorers[8453];
        return `${baseUrl}${hash}`;
    }

    /**
     * Update element text content safely
     * 
     * @param {string} elementId - Element ID
     * @param {string} content - Text content
     */
    updateElementText(elementId, content) {
        const element = document.getElementById(elementId);
        if (element) {
            element.textContent = content;
        }
    }

    /**
     * Update element HTML content safely
     * 
     * @param {string} elementId - Element ID
     * @param {string} html - HTML content
     */
    updateElementHTML(elementId, html) {
        const element = document.getElementById(elementId);
        if (element) {
            element.innerHTML = html;
        }
    }

    /**
     * Show/hide element
     * 
     * @param {string} elementId - Element ID
     * @param {boolean} show - Whether to show element
     */
    toggleElement(elementId, show) {
        const element = document.getElementById(elementId);
        if (element) {
            element.style.display = show ? '' : 'none';
        }
    }

    /**
     * Enable/disable element
     * 
     * @param {string} elementId - Element ID
     * @param {boolean} enable - Whether to enable element
     */
    toggleElementEnabled(elementId, enable) {
        const element = document.getElementById(elementId);
        if (element) {
            element.disabled = !enable;
        }
    }

    /**
     * Clear all notifications
     */
    clearAllNotifications() {
        this.notifications.forEach(n => this.removeNotification(n.id));
        this.notifications = [];
    }

    /**
     * Cleanup and destroy
     */
    destroy() {
        this.clearAllNotifications();

        const container = document.getElementById('notifications-container');
        if (container) {
            container.remove();
        }

        console.log('🧹 TradingUIManager cleanup completed');
    }
}