/**
 * Trading Data Management Module
 * 
 * Handles all data loading, caching, API requests, and data transformations
 * for the trading system. Manages positions, trades, portfolio data, and
 * market information.
 * 
 * File: dexproject/dashboard/static/js/trading-data.js
 */

import { safeJsonParse } from './trading-utils.js';

export class TradingDataManager {
    /**
     * Initialize the data manager
     * 
     * @param {string} baseUrl - Base URL for API requests
     * @param {string} csrfToken - CSRF token for POST requests
     */
    constructor(baseUrl, csrfToken) {
        this.baseUrl = baseUrl;
        this.csrfToken = csrfToken;

        // Data storage
        this.positions = new Map();
        this.trades = new Map();
        this.portfolioData = null;
        this.marketData = new Map();

        // Caching configuration
        this.cacheTimeout = 5000; // 5 seconds default cache
        this.lastFetch = new Map();

        console.log('📊 TradingDataManager initialized');
    }

    // =============================================================================
    // API REQUEST METHODS
    // =============================================================================

    /**
     * Make an API request with error handling
     * 
     * @param {string} method - HTTP method (GET, POST, etc.)
     * @param {string} endpoint - API endpoint path
     * @param {Object|null} data - Request payload for POST/PUT
     * @returns {Promise<Object>} Response data
     */
    async makeRequest(method, endpoint, data = null) {
        const url = `${this.baseUrl}${endpoint}`;

        const options = {
            method: method,
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'same-origin'
        };

        // Add CSRF token for non-GET requests
        if (method !== 'GET') {
            options.headers['X-CSRFToken'] = this.csrfToken;
        }

        // Add body for POST/PUT/PATCH requests
        if (data && method !== 'GET') {
            options.body = JSON.stringify(data);
        }

        try {
            console.log(`🌐 API Request: ${method} ${url}`);

            const response = await fetch(url, options);

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
            }

            const responseData = await response.json();
            console.log(`✅ API Response: ${method} ${url}`, responseData);

            return responseData;

        } catch (error) {
            console.error(`❌ API Error: ${method} ${url}`, error);
            throw error;
        }
    }

    /**
     * Check if cached data is still valid
     * 
     * @param {string} key - Cache key
     * @returns {boolean} True if cache is valid
     */
    isCacheValid(key) {
        const lastFetch = this.lastFetch.get(key);
        if (!lastFetch) return false;

        return (Date.now() - lastFetch) < this.cacheTimeout;
    }

    /**
     * Update cache timestamp
     * 
     * @param {string} key - Cache key
     */
    updateCacheTimestamp(key) {
        this.lastFetch.set(key, Date.now());
    }

    // =============================================================================
    // POSITION DATA METHODS
    // =============================================================================

    /**
     * Load all open positions
     * 
     * @param {boolean} forceRefresh - Force refresh bypassing cache
     * @returns {Promise<Array>} Array of position objects
     */
    async loadPositions(forceRefresh = false) {
        const cacheKey = 'positions';

        // Return cached data if valid
        if (!forceRefresh && this.isCacheValid(cacheKey) && this.positions.size > 0) {
            console.log('📦 Using cached positions data');
            return Array.from(this.positions.values());
        }

        try {
            const response = await this.makeRequest('GET', '/positions/');

            if (response.positions) {
                // Clear and update positions map
                this.positions.clear();
                response.positions.forEach(position => {
                    this.positions.set(position.id, position);
                });

                this.updateCacheTimestamp(cacheKey);
                console.log(`✅ Loaded ${this.positions.size} positions`);

                return response.positions;
            }

            return [];

        } catch (error) {
            console.error('Error loading positions:', error);
            throw error;
        }
    }

    /**
     * Get a specific position by ID
     * 
     * @param {string|number} positionId - Position ID
     * @returns {Object|null} Position object or null
     */
    getPosition(positionId) {
        return this.positions.get(positionId) || null;
    }

    /**
     * Update a position in local storage
     * 
     * @param {Object} position - Updated position data
     */
    updatePosition(position) {
        if (position && position.id) {
            this.positions.set(position.id, position);
            console.log(`✅ Updated position ${position.id}`);
        }
    }

    /**
     * Remove a position from local storage
     * 
     * @param {string|number} positionId - Position ID
     */
    removePosition(positionId) {
        const removed = this.positions.delete(positionId);
        if (removed) {
            console.log(`✅ Removed position ${positionId}`);
        }
    }

    // =============================================================================
    // TRADE HISTORY METHODS
    // =============================================================================

    /**
     * Load trade history
     * 
     * @param {number} limit - Maximum number of trades to load
     * @param {boolean} forceRefresh - Force refresh bypassing cache
     * @returns {Promise<Array>} Array of trade objects
     */
    async loadTradeHistory(limit = 50, forceRefresh = false) {
        const cacheKey = `trades_${limit}`;

        // Return cached data if valid
        if (!forceRefresh && this.isCacheValid(cacheKey) && this.trades.size > 0) {
            console.log('📦 Using cached trade history');
            return Array.from(this.trades.values());
        }

        try {
            const response = await this.makeRequest('GET', `/trades/?limit=${limit}`);

            if (response.trades) {
                // Clear and update trades map
                this.trades.clear();
                response.trades.forEach(trade => {
                    this.trades.set(trade.id, trade);
                });

                this.updateCacheTimestamp(cacheKey);
                console.log(`✅ Loaded ${this.trades.size} trades`);

                return response.trades;
            }

            return [];

        } catch (error) {
            console.error('Error loading trade history:', error);
            throw error;
        }
    }

    /**
     * Get a specific trade by ID
     * 
     * @param {string|number} tradeId - Trade ID
     * @returns {Object|null} Trade object or null
     */
    getTrade(tradeId) {
        return this.trades.get(tradeId) || null;
    }

    /**
     * Add a new trade to local storage
     * 
     * @param {Object} trade - Trade data
     */
    addTrade(trade) {
        if (trade && trade.id) {
            this.trades.set(trade.id, trade);
            console.log(`✅ Added trade ${trade.id}`);
        }
    }

    /**
     * Update a trade in local storage
     * 
     * @param {Object} trade - Updated trade data
     */
    updateTrade(trade) {
        if (trade && trade.id) {
            this.trades.set(trade.id, trade);
            console.log(`✅ Updated trade ${trade.id}`);
        }
    }

    // =============================================================================
    // PORTFOLIO DATA METHODS
    // =============================================================================

    /**
     * Load portfolio summary
     * 
     * @param {boolean} forceRefresh - Force refresh bypassing cache
     * @returns {Promise<Object>} Portfolio summary data
     */
    async loadPortfolioSummary(forceRefresh = false) {
        const cacheKey = 'portfolio';

        // Return cached data if valid
        if (!forceRefresh && this.isCacheValid(cacheKey) && this.portfolioData) {
            console.log('📦 Using cached portfolio data');
            return this.portfolioData;
        }

        try {
            const response = await this.makeRequest('GET', '/portfolio/summary/');

            if (response) {
                this.portfolioData = response;
                this.updateCacheTimestamp(cacheKey);
                console.log('✅ Loaded portfolio summary', response);

                return response;
            }

            return null;

        } catch (error) {
            console.error('Error loading portfolio summary:', error);
            throw error;
        }
    }

    /**
     * Get current portfolio data
     * 
     * @returns {Object|null} Portfolio data or null
     */
    getPortfolioData() {
        return this.portfolioData;
    }

    // =============================================================================
    // MARKET DATA METHODS
    // =============================================================================

    /**
     * Load market data for a token
     * 
     * @param {string} tokenAddress - Token contract address
     * @param {number} chainId - Blockchain chain ID
     * @returns {Promise<Object>} Market data for the token
     */
    async loadMarketData(tokenAddress, chainId = 8453) {
        const cacheKey = `market_${tokenAddress}_${chainId}`;

        // Return cached data if valid
        if (this.isCacheValid(cacheKey)) {
            const cached = this.marketData.get(cacheKey);
            if (cached) {
                console.log(`📦 Using cached market data for ${tokenAddress}`);
                return cached;
            }
        }

        try {
            const response = await this.makeRequest(
                'GET',
                `/market/data/?token=${tokenAddress}&chain_id=${chainId}`
            );

            if (response) {
                this.marketData.set(cacheKey, response);
                this.updateCacheTimestamp(cacheKey);
                console.log(`✅ Loaded market data for ${tokenAddress}`);

                return response;
            }

            return null;

        } catch (error) {
            console.error(`Error loading market data for ${tokenAddress}:`, error);
            throw error;
        }
    }

    /**
     * Get cached market data
     * 
     * @param {string} tokenAddress - Token contract address
     * @param {number} chainId - Blockchain chain ID
     * @returns {Object|null} Cached market data or null
     */
    getMarketData(tokenAddress, chainId = 8453) {
        const cacheKey = `market_${tokenAddress}_${chainId}`;
        return this.marketData.get(cacheKey) || null;
    }

    // =============================================================================
    // BATCH LOADING METHODS
    // =============================================================================

    /**
     * Load all initial data in parallel
     * 
     * @returns {Promise<Object>} Object containing all loaded data
     */
    async loadAllData() {
        console.log('🔄 Loading all trading data...');

        try {
            const [positions, trades, portfolio] = await Promise.all([
                this.loadPositions(true),
                this.loadTradeHistory(50, true),
                this.loadPortfolioSummary(true)
            ]);

            console.log('✅ All trading data loaded successfully');

            return {
                positions,
                trades,
                portfolio
            };

        } catch (error) {
            console.error('Error loading all trading data:', error);
            throw error;
        }
    }

    /**
     * Refresh all data
     * Forces refresh of all cached data
     * 
     * @returns {Promise<Object>} Object containing refreshed data
     */
    async refreshAllData() {
        console.log('🔄 Refreshing all trading data...');

        // Clear cache timestamps
        this.lastFetch.clear();

        return await this.loadAllData();
    }

    // =============================================================================
    // DATA TRANSFORMATION METHODS
    // =============================================================================

    /**
     * Transform position data for chart display
     * 
     * @returns {Array} Array of position data formatted for charts
     */
    getPositionsForChart() {
        const positions = Array.from(this.positions.values());

        return positions.map(pos => ({
            label: pos.token_symbol || 'Unknown',
            value: pos.current_value_usd || 0,
            pnl: pos.unrealized_pnl || 0,
            pnl_percent: pos.pnl_percentage || 0
        }));
    }

    /**
     * Get performance statistics
     * 
     * @returns {Object} Performance statistics
     */
    getPerformanceStats() {
        const positions = Array.from(this.positions.values());
        const trades = Array.from(this.trades.values());

        const totalPnL = positions.reduce((sum, pos) => sum + (pos.unrealized_pnl || 0), 0);
        const realizedPnL = trades
            .filter(t => t.status === 'COMPLETED')
            .reduce((sum, t) => sum + (t.realized_pnl || 0), 0);

        const winningTrades = trades.filter(t => t.realized_pnl > 0).length;
        const losingTrades = trades.filter(t => t.realized_pnl < 0).length;
        const winRate = trades.length > 0 ? (winningTrades / trades.length) * 100 : 0;

        return {
            totalPnL,
            realizedPnL,
            unrealizedPnL: totalPnL - realizedPnL,
            winningTrades,
            losingTrades,
            totalTrades: trades.length,
            winRate
        };
    }

    /**
     * Clear all cached data
     */
    clearCache() {
        this.lastFetch.clear();
        console.log('🧹 Cache cleared');
    }

    /**
     * Get cache statistics
     * 
     * @returns {Object} Cache statistics
     */
    getCacheStats() {
        return {
            cachedItems: this.lastFetch.size,
            positions: this.positions.size,
            trades: this.trades.size,
            marketData: this.marketData.size,
            hasPortfolio: !!this.portfolioData
        };
    }
}