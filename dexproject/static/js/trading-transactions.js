/**
 * Trading Transactions Management Module - Phase 6B
 * 
 * Handles Transaction Manager V2 integration with features:
 * - Real-time transaction status updates via WebSocket
 * - Gas optimization tracking and savings display
 * - Transaction lifecycle progress tracking
 * - Transaction UI creation and updates
 * 
 * File: dexproject/dashboard/static/js/trading-transactions.js
 */

export class TradingTransactionsManager {
    /**
     * Initialize the transactions manager
     * 
     * @param {string} csrfToken - CSRF token for API requests
     * @param {Function} showNotification - Notification display function
     * @param {Function} getStatusBadgeClass - Status badge class helper
     */
    constructor(csrfToken, showNotification, getStatusBadgeClass) {
        this.csrfToken = csrfToken;
        this.showNotification = showNotification;
        this.getStatusBadgeClass = getStatusBadgeClass;

        // Active transactions tracking
        this.activeTransactions = new Map();

        console.log('🔄 TradingTransactionsManager initialized (Phase 6B)');
    }

    // =============================================================================
    // TRANSACTION MANAGER V2 EXECUTION
    // =============================================================================

    /**
     * Execute buy order with Transaction Manager V2 integration
     * 
     * @param {FormData} formData - Order form data
     * @returns {Promise<Object>} Transaction execution result
     */
    async executeBuyOrderV2(formData) {
        try {
            console.log('🚀 Executing buy order with Transaction Manager V2...');

            const response = await fetch('/api/trading/buy/v2/', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': this.csrfToken
                }
            });

            const result = await response.json();

            if (result.success) {
                const transactionId = result.transaction_id;
                const tradeId = result.trade_id;

                console.log(`✅ Transaction Manager buy order submitted: ${transactionId}`);

                // Add to active transactions for tracking
                this.activeTransactions.set(transactionId, {
                    transaction_id: transactionId,
                    trade_id: tradeId,
                    status: result.status,
                    timestamp: new Date(),
                    type: 'buy',
                    data: result
                });

                // Create UI elements for real-time transaction tracking
                this.createTransactionTrackingUI(transactionId, result);

                // Show success notification with gas savings
                let message = 'Buy order submitted with gas optimization!';
                if (result.optimization_details && result.optimization_details.gas_savings_achieved) {
                    message += ` Expected savings: ${parseFloat(result.optimization_details.gas_savings_achieved).toFixed(2)}%`;
                }

                this.showNotification(message, 'success');

                return result;

            } else {
                console.error('❌ Transaction Manager buy order failed:', result.error);
                this.showNotification(`Buy order failed: ${result.error}`, 'error');
                return result;
            }

        } catch (error) {
            console.error('❌ Transaction Manager buy order execution error:', error);
            this.showNotification('Buy order execution failed', 'error');
            return { success: false, error: error.message };
        }
    }

    /**
     * Cancel a transaction (if possible)
     * 
     * @param {string} transactionId - Transaction ID to cancel
     * @returns {Promise<Object>} Cancellation result
     */
    async cancelTransaction(transactionId) {
        try {
            const response = await fetch(`/api/trading/cancel/${transactionId}/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': this.csrfToken,
                    'Content-Type': 'application/json'
                }
            });

            const result = await response.json();

            if (result.success) {
                this.showNotification('Transaction cancelled successfully', 'success');
            } else {
                this.showNotification(`Cannot cancel: ${result.error}`, 'warning');
            }

            return result;

        } catch (error) {
            console.error('❌ Cancel transaction error:', error);
            this.showNotification('Failed to cancel transaction', 'error');
            return { success: false, error: error.message };
        }
    }

    // =============================================================================
    // REAL-TIME UPDATES
    // =============================================================================

    /**
     * Handle real-time transaction status updates from WebSocket
     * 
     * @param {Object} data - Transaction update data
     */
    handleTransactionUpdate(data) {
        const transactionId = data.transaction_id;
        const status = data.status;
        const gasUsed = data.gas_used;
        const gasSavingsPercent = data.gas_savings_percent;
        const errorMessage = data.error_message;
        const transactionHash = data.transaction_hash;
        const executionTime = data.execution_time_ms;

        console.log(`📊 Transaction Manager Update: ${transactionId} → ${status}`);

        // Update active transactions map
        this.activeTransactions.set(transactionId, {
            ...data,
            lastUpdate: new Date()
        });

        // Update UI based on status
        this.updateTransactionUI(transactionId, {
            status,
            gasUsed,
            gasSavingsPercent,
            errorMessage,
            transactionHash,
            executionTime
        });

        // Show status-specific notifications
        this.showTransactionNotification(transactionId, status, {
            gasSavingsPercent,
            errorMessage,
            executionTime
        });

        // Clean up completed transactions
        if (['completed', 'failed', 'cancelled'].includes(status.toLowerCase())) {
            setTimeout(() => {
                this.activeTransactions.delete(transactionId);
                // Remove UI element after delay
                const element = document.getElementById(`transaction-${transactionId}`);
                if (element) {
                    element.style.transition = 'opacity 1s';
                    element.style.opacity = '0';
                    setTimeout(() => element.remove(), 1000);
                }
            }, 120000); // Keep for 2 minutes after completion
        }
    }

    // =============================================================================
    // UI UPDATES
    // =============================================================================

    /**
     * Update transaction UI elements with real-time data
     * 
     * @param {string} transactionId - Transaction ID
     * @param {Object} details - Transaction details to update
     */
    updateTransactionUI(transactionId, details) {
        // Update transaction status badge
        const statusElement = document.getElementById(`tx-status-${transactionId}`);
        if (statusElement) {
            statusElement.textContent = details.status.toUpperCase();
            statusElement.className = `badge ${this.getStatusBadgeClass(details.status)}`;
        }

        // Update transaction hash link
        if (details.transactionHash && details.transactionHash !== '0x') {
            const hashElement = document.getElementById(`tx-hash-${transactionId}`);
            const placeholder = document.getElementById(`tx-hash-placeholder-${transactionId}`);

            if (hashElement) {
                hashElement.href = this.getExplorerUrl(details.transactionHash);
                hashElement.textContent = this.formatHash(details.transactionHash);
                hashElement.style.display = 'inline';
            }
            if (placeholder) {
                placeholder.style.display = 'none';
            }
        }

        // Update gas savings display (Phase 6B feature)
        if (details.gasSavingsPercent) {
            const gasSavingsElement = document.getElementById(`tx-gas-savings-${transactionId}`);
            if (gasSavingsElement) {
                const savings = parseFloat(details.gasSavingsPercent).toFixed(2);
                gasSavingsElement.textContent = `${savings}% saved`;
                gasSavingsElement.className = 'text-success fw-bold';
            }
        }

        // Update gas used
        if (details.gasUsed) {
            const gasUsedElement = document.getElementById(`tx-gas-used-${transactionId}`);
            if (gasUsedElement) {
                gasUsedElement.textContent = details.gasUsed.toLocaleString();
            }
        }

        // Update execution time
        if (details.executionTime) {
            const executionTimeElement = document.getElementById(`tx-execution-time-${transactionId}`);
            if (executionTimeElement) {
                const seconds = (details.executionTime / 1000).toFixed(2);
                executionTimeElement.textContent = `${seconds}s`;
            }
        }

        // Update error message if present
        if (details.errorMessage) {
            const errorElement = document.getElementById(`tx-error-${transactionId}`);
            if (errorElement) {
                errorElement.textContent = details.errorMessage;
                errorElement.style.display = 'block';
            }
        }

        // Update progress bar
        this.updateTransactionProgress(transactionId, details.status);
    }

    /**
     * Update transaction progress indicator
     * 
     * @param {string} transactionId - Transaction ID
     * @param {string} status - Current status
     */
    updateTransactionProgress(transactionId, status) {
        const progressElement = document.getElementById(`tx-progress-${transactionId}`);
        if (!progressElement) return;

        const progressSteps = {
            'preparing': 10,
            'gas_optimizing': 25,
            'ready_to_submit': 40,
            'submitted': 60,
            'pending': 75,
            'confirming': 90,
            'confirmed': 95,
            'completed': 100,
            'failed': 100,
            'cancelled': 100
        };

        const progress = progressSteps[status.toLowerCase()] || 0;
        const progressBar = progressElement.querySelector('.progress-bar');

        if (progressBar) {
            progressBar.style.width = `${progress}%`;
            progressBar.setAttribute('aria-valuenow', progress);

            // Update progress bar color based on status
            const statusClass = this.getProgressBarClass(status);
            progressBar.className = `progress-bar ${statusClass}`;

            // Add animation for active states
            if (['preparing', 'gas_optimizing', 'submitted', 'pending', 'confirming'].includes(status.toLowerCase())) {
                progressBar.classList.add('progress-bar-striped', 'progress-bar-animated');
            } else {
                progressBar.classList.remove('progress-bar-striped', 'progress-bar-animated');
            }
        }
    }

    /**
     * Create UI elements for transaction tracking (Phase 6B)
     * 
     * @param {string} transactionId - Transaction ID
     * @param {Object} transactionData - Transaction data
     */
    createTransactionTrackingUI(transactionId, transactionData) {
        const container = document.getElementById('active-transactions-container') ||
            document.getElementById('positions-container');
        if (!container) return;

        const transactionElement = document.createElement('div');
        transactionElement.id = `transaction-${transactionId}`;
        transactionElement.className = 'transaction-tracker mb-3 p-3 border rounded bg-light';
        transactionElement.innerHTML = `
            <div class="d-flex justify-content-between align-items-start mb-2">
                <div>
                    <h6 class="mb-1">
                        <i class="bi bi-cpu me-2"></i>Transaction Manager
                        <span class="text-muted">${transactionId.slice(-8)}...</span>
                        <span id="tx-status-${transactionId}" class="badge ${this.getStatusBadgeClass('submitted')}">
                            SUBMITTED
                        </span>
                    </h6>
                    <small class="text-muted">
                        ${transactionData.trade_details?.amount_eth || '0'} ETH → Token
                        ${transactionData.trade_details?.is_paper_trade ? '(Paper Trading)' : ''}
                    </small>
                </div>
                <div class="text-end">
                    <div id="tx-gas-savings-${transactionId}" class="text-success fw-bold">
                        ${transactionData.optimization_details?.gas_savings_achieved ?
                `${parseFloat(transactionData.optimization_details.gas_savings_achieved).toFixed(2)}% saved` :
                'Optimizing gas...'}
                    </div>
                    <small class="text-muted">Strategy: ${transactionData.trade_details?.gas_strategy || 'balanced'}</small>
                </div>
            </div>
            
            <div class="progress mb-2" style="height: 8px;" id="tx-progress-${transactionId}">
                <div class="progress-bar progress-bar-striped progress-bar-animated bg-info" 
                     style="width: 60%" aria-valuenow="60" aria-valuemin="0" aria-valuemax="100">
                </div>
            </div>
            
            <div class="row text-center">
                <div class="col-3">
                    <small class="text-muted">Gas Used</small><br>
                    <span id="tx-gas-used-${transactionId}" class="fw-bold">-</span>
                </div>
                <div class="col-3">
                    <small class="text-muted">Execution Time</small><br>
                    <span id="tx-execution-time-${transactionId}" class="fw-bold">-</span>
                </div>
                <div class="col-6">
                    <small class="text-muted">Transaction Hash</small><br>
                    <a id="tx-hash-${transactionId}" href="#" target="_blank" style="display: none;" class="text-decoration-none">
                        <i class="bi bi-box-arrow-up-right me-1"></i>View on Explorer
                    </a>
                    <span id="tx-hash-placeholder-${transactionId}" class="text-muted">Pending...</span>
                </div>
            </div>
            
            <div id="tx-error-${transactionId}" class="alert alert-danger mt-2 mb-0" style="display: none;"></div>
            
            <div class="mt-2 text-end">
                <button class="btn btn-sm btn-outline-danger" data-action="cancel-transaction" data-transaction-id="${transactionId}">
                    <i class="bi bi-x-circle me-1"></i>Cancel
                </button>
            </div>
        `;

        // Insert at the top of container
        container.insertBefore(transactionElement, container.firstChild);
    }

    // =============================================================================
    // NOTIFICATIONS
    // =============================================================================

    /**
     * Show transaction-specific notifications
     * 
     * @param {string} transactionId - Transaction ID
     * @param {string} status - Transaction status
     * @param {Object} details - Additional details
     */
    showTransactionNotification(transactionId, status, details) {
        let message = '';
        let type = 'info';

        switch (status.toLowerCase()) {
            case 'gas_optimizing':
                message = 'Optimizing gas prices for maximum savings...';
                type = 'info';
                break;
            case 'submitted':
                message = 'Transaction submitted to blockchain';
                type = 'info';
                break;
            case 'confirmed':
                message = `Transaction confirmed!`;
                if (details.gasSavingsPercent) {
                    message += ` Gas savings: ${parseFloat(details.gasSavingsPercent).toFixed(2)}%`;
                }
                type = 'success';
                break;
            case 'completed':
                message = 'Transaction completed successfully!';
                if (details.executionTime) {
                    const seconds = (details.executionTime / 1000).toFixed(2);
                    message += ` Execution time: ${seconds}s`;
                }
                type = 'success';
                break;
            case 'failed':
                message = `Transaction failed: ${details.errorMessage || 'Unknown error'}`;
                type = 'error';
                break;
            case 'cancelled':
                message = 'Transaction cancelled';
                type = 'warning';
                break;
        }

        if (message) {
            this.showNotification(message, type, 4000); // Show for 4 seconds
        }
    }

    // =============================================================================
    // HELPER METHODS
    // =============================================================================

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
     * Get active transaction count
     * 
     * @returns {number} Number of active transactions
     */
    getActiveTransactionCount() {
        return this.activeTransactions.size;
    }

    /**
     * Get all active transactions
     * 
     * @returns {Array} Array of active transaction objects
     */
    getActiveTransactions() {
        return Array.from(this.activeTransactions.values());
    }

    /**
     * Clear completed transactions from UI
     */
    clearCompletedTransactions() {
        this.activeTransactions.forEach((transaction, transactionId) => {
            if (['completed', 'failed', 'cancelled'].includes(transaction.status?.toLowerCase())) {
                const element = document.getElementById(`transaction-${transactionId}`);
                if (element) {
                    element.remove();
                }
                this.activeTransactions.delete(transactionId);
            }
        });
    }

    /**
     * Cleanup and destroy
     */
    destroy() {
        this.activeTransactions.clear();
        console.log('🧹 TradingTransactionsManager cleanup completed');
    }
}