/**
 * Trading Orders Management Module
 * 
 * Handles order execution (buy/sell), position management, and order validation.
 * Provides both legacy and Transaction Manager V2 execution paths.
 * 
 * File: dexproject/dashboard/static/js/trading-orders.js
 */

export class TradingOrdersManager {
    /**
     * Initialize the orders manager
     * 
     * @param {string} baseUrl - Base URL for API requests
     * @param {Function} makeRequest - API request function
     * @param {Function} showNotification - Notification display function
     * @param {Function} onTradeUpdate - Callback for trade updates
     */
    constructor(baseUrl, makeRequest, showNotification, onTradeUpdate) {
        this.baseUrl = baseUrl;
        this.makeRequest = makeRequest;
        this.showNotification = showNotification;
        this.onTradeUpdate = onTradeUpdate;

        // Configuration
        this.defaultSlippage = 0.005; // 0.5%
        this.defaultChainId = 8453; // Base mainnet

        console.log('💼 TradingOrdersManager initialized');
    }

    // =============================================================================
    // BUY ORDERS
    // =============================================================================

    /**
     * Execute a buy order (legacy method)
     * 
     * @param {FormData} formData - Form data with order parameters
     * @returns {Promise<Object>} Order execution result
     */
    async executeBuyOrder(formData) {
        const buyData = {
            token_address: formData.get('token_address'),
            amount_eth: formData.get('amount_eth'),
            slippage_tolerance: parseFloat(formData.get('slippage_tolerance') || this.defaultSlippage),
            gas_price_gwei: formData.get('gas_price_gwei') ?
                parseFloat(formData.get('gas_price_gwei')) : null,
            strategy_id: formData.get('strategy_id') || null,
            chain_id: parseInt(formData.get('chain_id') || this.defaultChainId)
        };

        // Validate order data
        const validation = this.validateBuyOrder(buyData);
        if (!validation.valid) {
            this.showNotification(validation.error, 'error');
            throw new Error(validation.error);
        }

        try {
            this.showNotification('Executing buy order...', 'info');

            const response = await this.makeRequest('POST', '/buy/', buyData);

            if (response.success) {
                this.showNotification(
                    `Buy order submitted successfully! Trade ID: ${response.trade_id}`,
                    'success'
                );

                // Notify about pending trade
                if (this.onTradeUpdate) {
                    this.onTradeUpdate({
                        trade_id: response.trade_id,
                        trade_type: 'BUY',
                        status: 'PENDING',
                        token_address: buyData.token_address,
                        amount_eth: buyData.amount_eth,
                        created_at: new Date().toISOString()
                    });
                }

                return {
                    success: true,
                    trade_id: response.trade_id,
                    task_id: response.task_id
                };

            } else {
                throw new Error(response.error || 'Buy order failed');
            }

        } catch (error) {
            console.error('❌ Buy order error:', error);
            this.showNotification(
                `Buy order failed: ${error.message}`,
                'error'
            );
            throw error;
        }
    }

    /**
     * Validate buy order parameters
     * 
     * @param {Object} orderData - Order data to validate
     * @returns {Object} Validation result with valid flag and error message
     */
    validateBuyOrder(orderData) {
        if (!orderData.token_address || !/^0x[a-fA-F0-9]{40}$/.test(orderData.token_address)) {
            return { valid: false, error: 'Invalid token address' };
        }

        const amount = parseFloat(orderData.amount_eth);
        if (isNaN(amount) || amount <= 0) {
            return { valid: false, error: 'Invalid ETH amount' };
        }

        if (amount > 10) {
            return { valid: false, error: 'ETH amount exceeds maximum (10 ETH)' };
        }

        const slippage = parseFloat(orderData.slippage_tolerance);
        if (isNaN(slippage) || slippage < 0 || slippage > 0.5) {
            return { valid: false, error: 'Slippage must be between 0% and 50%' };
        }

        return { valid: true };
    }

    // =============================================================================
    // SELL ORDERS
    // =============================================================================

    /**
     * Execute a sell order
     * 
     * @param {FormData} formData - Form data with order parameters
     * @returns {Promise<Object>} Order execution result
     */
    async executeSellOrder(formData) {
        const sellData = {
            token_address: formData.get('token_address'),
            token_amount: formData.get('token_amount'),
            slippage_tolerance: parseFloat(formData.get('slippage_tolerance') || this.defaultSlippage),
            gas_price_gwei: formData.get('gas_price_gwei') ?
                parseFloat(formData.get('gas_price_gwei')) : null,
            chain_id: parseInt(formData.get('chain_id') || this.defaultChainId)
        };

        // Validate order data
        const validation = this.validateSellOrder(sellData);
        if (!validation.valid) {
            this.showNotification(validation.error, 'error');
            throw new Error(validation.error);
        }

        try {
            this.showNotification('Executing sell order...', 'info');

            const response = await this.makeRequest('POST', '/sell/', sellData);

            if (response.success) {
                this.showNotification(
                    `Sell order submitted successfully! Trade ID: ${response.trade_id}`,
                    'success'
                );

                // Notify about pending trade
                if (this.onTradeUpdate) {
                    this.onTradeUpdate({
                        trade_id: response.trade_id,
                        trade_type: 'SELL',
                        status: 'PENDING',
                        token_address: sellData.token_address,
                        token_amount: sellData.token_amount,
                        created_at: new Date().toISOString()
                    });
                }

                return {
                    success: true,
                    trade_id: response.trade_id,
                    task_id: response.task_id
                };

            } else {
                throw new Error(response.error || 'Sell order failed');
            }

        } catch (error) {
            console.error('❌ Sell order error:', error);
            this.showNotification(
                `Sell order failed: ${error.message}`,
                'error'
            );
            throw error;
        }
    }

    /**
     * Validate sell order parameters
     * 
     * @param {Object} orderData - Order data to validate
     * @returns {Object} Validation result with valid flag and error message
     */
    validateSellOrder(orderData) {
        if (!orderData.token_address || !/^0x[a-fA-F0-9]{40}$/.test(orderData.token_address)) {
            return { valid: false, error: 'Invalid token address' };
        }

        const amount = parseFloat(orderData.token_amount);
        if (isNaN(amount) || amount <= 0) {
            return { valid: false, error: 'Invalid token amount' };
        }

        const slippage = parseFloat(orderData.slippage_tolerance);
        if (isNaN(slippage) || slippage < 0 || slippage > 0.5) {
            return { valid: false, error: 'Slippage must be between 0% and 50%' };
        }

        return { valid: true };
    }

    // =============================================================================
    // POSITION MANAGEMENT
    // =============================================================================

    /**
     * Close a position
     * 
     * @param {string} positionId - Position ID
     * @param {number} percentage - Percentage to close (1-100)
     * @returns {Promise<Object>} Close position result
     */
    async closePosition(positionId, percentage = 100) {
        // Validate parameters
        if (!positionId) {
            this.showNotification('Invalid position ID', 'error');
            throw new Error('Invalid position ID');
        }

        const pct = parseFloat(percentage);
        if (isNaN(pct) || pct <= 0 || pct > 100) {
            this.showNotification('Percentage must be between 1 and 100', 'error');
            throw new Error('Invalid percentage');
        }

        try {
            this.showNotification('Closing position...', 'info');

            const response = await this.makeRequest('POST', '/positions/close/', {
                position_id: positionId,
                percentage: pct
            });

            if (response.success) {
                this.showNotification(
                    `Position close order submitted! Trade ID: ${response.trade_id}`,
                    'success'
                );

                return {
                    success: true,
                    trade_id: response.trade_id
                };

            } else {
                throw new Error(response.error || 'Failed to close position');
            }

        } catch (error) {
            console.error('❌ Close position error:', error);
            this.showNotification(
                `Failed to close position: ${error.message}`,
                'error'
            );
            throw error;
        }
    }

    /**
     * Close multiple positions
     * 
     * @param {Array<string>} positionIds - Array of position IDs
     * @param {number} percentage - Percentage to close (1-100)
     * @returns {Promise<Array>} Array of close results
     */
    async closeMultiplePositions(positionIds, percentage = 100) {
        const results = [];

        for (const positionId of positionIds) {
            try {
                const result = await this.closePosition(positionId, percentage);
                results.push({ positionId, success: true, result });
            } catch (error) {
                results.push({ positionId, success: false, error: error.message });
            }
        }

        return results;
    }

    // =============================================================================
    // TRADING SESSION MANAGEMENT
    // =============================================================================

    /**
     * Start a trading session
     * 
     * @param {Object} config - Session configuration
     * @returns {Promise<Object>} Session start result
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

                return {
                    success: true,
                    session: response.session
                };

            } else {
                throw new Error(response.error || 'Failed to start trading session');
            }

        } catch (error) {
            console.error('❌ Trading session start error:', error);
            this.showNotification(
                `Failed to start trading session: ${error.message}`,
                'error'
            );
            throw error;
        }
    }

    /**
     * Stop the active trading session
     * 
     * @returns {Promise<Object>} Session stop result
     */
    async stopTradingSession() {
        try {
            this.showNotification('Stopping trading session...', 'info');

            const response = await this.makeRequest('POST', '/session/stop/');

            if (response.success) {
                this.showNotification('Trading session stopped successfully!', 'success');

                return {
                    success: true
                };

            } else {
                throw new Error(response.error || 'Failed to stop trading session');
            }

        } catch (error) {
            console.error('❌ Trading session stop error:', error);
            this.showNotification(
                `Failed to stop trading session: ${error.message}`,
                'error'
            );
            throw error;
        }
    }

    // =============================================================================
    // ORDER MONITORING
    // =============================================================================

    /**
     * Monitor trade status via polling
     * 
     * @param {string} tradeId - Trade ID to monitor
     * @param {string} taskId - Celery task ID
     * @param {number} maxAttempts - Maximum monitoring attempts
     * @returns {Promise<void>}
     */
    async monitorTradeStatus(tradeId, taskId, maxAttempts = 30) {
        let attempts = 0;

        const checkStatus = async () => {
            try {
                attempts++;

                const response = await this.makeRequest('GET', `/history/?trade_id=${tradeId}`);

                if (response.success && response.trades.length > 0) {
                    const trade = response.trades[0];

                    // Notify about trade update
                    if (this.onTradeUpdate) {
                        this.onTradeUpdate(trade);
                    }

                    if (trade.status === 'COMPLETED') {
                        console.log(`✅ Trade ${tradeId} completed successfully`);
                        return; // Stop monitoring
                    } else if (trade.status === 'FAILED') {
                        console.error(`❌ Trade ${tradeId} failed: ${trade.error_message}`);
                        return; // Stop monitoring
                    }
                }

                if (attempts < maxAttempts) {
                    setTimeout(checkStatus, 10000); // Check again in 10 seconds
                } else {
                    console.warn(`⏱️ Trade ${tradeId} monitoring timeout after ${attempts} attempts`);
                }

            } catch (error) {
                console.error('❌ Error monitoring trade status:', error);
            }
        };

        // Start monitoring after 5 seconds
        setTimeout(checkStatus, 5000);
    }

    // =============================================================================
    // UTILITY METHODS
    // =============================================================================

    /**
     * Calculate estimated output for a buy order
     * 
     * @param {number} ethAmount - ETH input amount
     * @param {number} tokenPrice - Token price in ETH
     * @param {number} slippage - Slippage tolerance
     * @returns {Object} Estimated output and minimum received
     */
    calculateBuyOutput(ethAmount, tokenPrice, slippage = 0.005) {
        if (!ethAmount || !tokenPrice) {
            return { estimated: 0, minimum: 0 };
        }

        const estimated = ethAmount / tokenPrice;
        const minimum = estimated * (1 - slippage);

        return {
            estimated: estimated,
            minimum: minimum
        };
    }

    /**
     * Calculate estimated output for a sell order
     * 
     * @param {number} tokenAmount - Token input amount
     * @param {number} tokenPrice - Token price in ETH
     * @param {number} slippage - Slippage tolerance
     * @returns {Object} Estimated output and minimum received
     */
    calculateSellOutput(tokenAmount, tokenPrice, slippage = 0.005) {
        if (!tokenAmount || !tokenPrice) {
            return { estimated: 0, minimum: 0 };
        }

        const estimated = tokenAmount * tokenPrice;
        const minimum = estimated * (1 - slippage);

        return {
            estimated: estimated,
            minimum: minimum
        };
    }

    /**
     * Estimate gas cost for an order
     * 
     * @param {string} orderType - Order type ('buy' or 'sell')
     * @param {number} gasPrice - Gas price in Gwei
     * @returns {Object} Gas cost estimates
     */
    estimateGasCost(orderType, gasPrice) {
        // Approximate gas limits
        const gasLimits = {
            'buy': 200000,
            'sell': 150000
        };

        const gasLimit = gasLimits[orderType] || 200000;
        const gasCostGwei = gasLimit * gasPrice;
        const gasCostEth = gasCostGwei / 1e9;

        return {
            gasLimit: gasLimit,
            gasPriceGwei: gasPrice,
            gasCostGwei: gasCostGwei,
            gasCostEth: gasCostEth
        };
    }

    /**
     * Cleanup and destroy
     */
    destroy() {
        console.log('🧹 TradingOrdersManager cleanup completed');
    }
}