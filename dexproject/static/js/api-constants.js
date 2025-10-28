/**
 * API Constants and URL Patterns
 * 
 * Centralized API endpoints and URL patterns for the entire DEX Trading Bot project.
 * This file prevents hardcoding URLs throughout the codebase and ensures consistency.
 * 
 * Usage:
 *   import { API_ENDPOINTS } from './api-constants.js';
 *   fetch(API_ENDPOINTS.PAPER_TRADING.BOT_START, { ... });
 * 
 * File: dexproject/static/js/api-constants.js
 */

'use strict';

// ============================================================================
// DASHBOARD API ENDPOINTS
// ============================================================================

const DASHBOARD_API = {
    // Trading endpoints
    SET_TRADING_MODE: '/dashboard/api/set-trading-mode/',
    MANUAL_TRADE: '/dashboard/api/trading/manual/',
    SMART_LANE_TRADE: '/dashboard/api/trading/smart-lane/',

    // Smart Lane endpoints
    SMART_LANE_ANALYZE: '/dashboard/api/smart-lane/analyze/',
    SMART_LANE_TEST_CONFIG: '/dashboard/api/smart-lane/test-config/',

    // Analytics endpoints
    ANALYTICS_REFRESH: '/dashboard/api/analytics/refresh/',
    CHART_DATA: '/dashboard/api/chart-data/',

    // Metrics streaming
    METRICS_STREAM: '/dashboard/metrics/stream/',
    SSE_METRICS: '/dashboard/sse/metrics/',

    // Configuration endpoints
    SAVE_CONFIGURATION: '/dashboard/api/save-configuration/',
    LOAD_CONFIGURATION: '/dashboard/api/load-configuration/',
    CONFIGURATIONS_LIST: '/dashboard/api/configurations/',
};

// ============================================================================
// DASHBOARD PAGE URLS
// ============================================================================

const DASHBOARD_PAGES = {
    HOME: '/dashboard/',
    CONFIG_PANEL: (mode) => `/dashboard/config/${mode}/`,
    SMART_LANE_CONFIG: '/dashboard/config/smart_lane/',
    FAST_LANE_CONFIG: '/dashboard/config/fast_lane/',
    SMART_LANE_DEMO: '/dashboard/smart-lane/demo/',
    SETTINGS: '/dashboard/settings/',
    MODE_SELECTION: '/dashboard/mode-selection/',
};

// ============================================================================
// PAPER TRADING API ENDPOINTS
// ============================================================================

const PAPER_TRADING_API = {
    // Bot control
    BOT_START: '/paper-trading/api/bot/start/',
    BOT_STOP: '/paper-trading/api/bot/stop/',
    BOT_STATUS: '/paper-trading/api/bot/status/',

    // Data endpoints
    ANALYTICS_DATA: '/paper-trading/api/analytics/data/',
    ANALYTICS_EXPORT: '/paper-trading/api/analytics/export/',
    PORTFOLIO_DATA: '/paper-trading/api/portfolio/',
    TRADES_DATA: '/paper-trading/api/trades/',
    TRADES_RECENT: '/paper-trading/api/trades/recent/',
    POSITIONS_OPEN: '/paper-trading/api/positions/open/',

    // Metrics endpoints
    METRICS: '/paper-trading/api/metrics/',
    PERFORMANCE: '/paper-trading/api/performance/',

    // Configuration endpoints
    CONFIGURATION_GET: '/paper-trading/api/configuration/',
    CONFIGURATION_UPDATE: '/paper-trading/api/config/',

    // AI thoughts endpoint
    AI_THOUGHTS: '/paper-trading/api/ai-thoughts/',

    // Token price data
    TOKEN_PRICE: (symbol) => `/paper-trading/api/prices/${symbol}/`,
};

// ============================================================================
// PAPER TRADING PAGE URLS
// ============================================================================

const PAPER_TRADING_PAGES = {
    DASHBOARD: '/paper-trading/',
    TRADES: '/paper-trading/trades/',
    PORTFOLIO: '/paper-trading/portfolio/',
    CONFIGURATION: '/paper-trading/configuration/',
    ANALYTICS: '/paper-trading/analytics/',
};

// ============================================================================
// TRADING API ENDPOINTS
// ============================================================================

const TRADING_API = {
    // Trading operations
    BASE_URL: '/api/trading',
    BUY_V2: '/api/trading/buy/v2/',
    SESSION_START: '/api/trading/session/start/',
    SESSION_STOP: '/api/trading/session/stop/',
    SESSION_STATUS: '/api/trading/session/status/',

    // Trade execution
    EXECUTE_TRADE: '/api/trading/execute/',
    CANCEL_TRADE: '/api/trading/cancel/',
    TRADE_STATUS: (tradeId) => `/api/trading/status/${tradeId}/`,
};

// ============================================================================
// WALLET API ENDPOINTS
// ============================================================================

const WALLET_API = {
    // Wallet info
    INFO: '/api/wallet/info/',
    BALANCE: '/api/wallet/balance/',

    // Authentication
    AUTH_SIWE_GENERATE: '/api/wallet/auth/siwe/generate/',
    AUTH_SIWE_AUTHENTICATE: '/api/wallet/auth/siwe/authenticate/',
    AUTH_LOGOUT: '/api/wallet/auth/logout/',

    // Wallet operations
    CONNECT: '/api/wallet/connect/',
    DISCONNECT: '/api/wallet/disconnect/',
};

// ============================================================================
// WEBSOCKET ENDPOINTS
// ============================================================================

const WEBSOCKET_ENDPOINTS = {
    PAPER_TRADING: 'ws://localhost:8000/ws/paper-trading/',
    PAPER_TRADING_SECURE: 'wss://localhost:8000/ws/paper-trading/',

    /**
     * Get appropriate WebSocket URL based on page protocol
     * @returns {string} WebSocket URL
     */
    getPaperTradingUrl: function () {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;
        return `${protocol}//${host}/ws/paper-trading/`;
    }
};

// ============================================================================
// DJANGO URL PATTERNS (Named Routes)
// ============================================================================

const DJANGO_URL_PATTERNS = {
    // Dashboard patterns
    'dashboard:home': '/dashboard/',
    'dashboard:api_set_trading_mode': '/dashboard/api/set-trading-mode/',
    'dashboard:configuration_panel': (mode) => `/dashboard/config/${mode}/`,
    'dashboard:smart_lane_demo': '/dashboard/smart-lane/demo/',
    'dashboard:mode_selection': '/dashboard/mode-selection/',
    'dashboard:settings': '/dashboard/settings/',

    // Paper Trading patterns
    'paper_trading:dashboard': '/paper-trading/',
    'paper_trading:trades': '/paper-trading/trades/',
    'paper_trading:portfolio': '/paper-trading/portfolio/',
    'paper_trading:configuration': '/paper-trading/configuration/',
    'paper_trading:analytics': '/paper-trading/analytics/',
};

// ============================================================================
// API RESPONSE CONSTANTS
// ============================================================================

const API_RESPONSE = {
    STATUS: {
        SUCCESS: 'success',
        ERROR: 'error',
        PENDING: 'pending',
        COMPLETED: 'completed',
        FAILED: 'failed'
    },

    HTTP_STATUS: {
        OK: 200,
        CREATED: 201,
        BAD_REQUEST: 400,
        UNAUTHORIZED: 401,
        FORBIDDEN: 403,
        NOT_FOUND: 404,
        SERVER_ERROR: 500
    }
};

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * API Utilities namespace
 */
const API_UTILS = {
    /**
     * Build URL with query parameters
     * 
     * @param {string} baseUrl - Base URL
     * @param {Object} params - Query parameters object
     * @returns {string} URL with query string
     */
    buildUrl: function (baseUrl, params = {}) {
        const url = new URL(baseUrl, window.location.origin);

        Object.keys(params).forEach(key => {
            if (params[key] !== null && params[key] !== undefined) {
                url.searchParams.append(key, params[key]);
            }
        });

        return url.toString();
    },

    /**
     * Check if URL is relative
     * 
     * @param {string} url - URL to check
     * @returns {boolean} True if relative URL
     */
    isRelativeUrl: function (url) {
        return !url.startsWith('http://') && !url.startsWith('https://');
    },

    /**
     * Get full URL from relative path
     * 
     * @param {string} path - Relative path
     * @returns {string} Full URL
     */
    getFullUrl: function (path) {
        if (!this.isRelativeUrl(path)) {
            return path;
        }
        return window.location.origin + path;
    },

    /**
     * Resolve Django URL pattern
     * 
     * @param {string} pattern - Django URL pattern name (e.g., 'dashboard:home')
     * @param {Object} params - URL parameters
     * @returns {string} Resolved URL
     */
    resolveUrl: function (pattern, params = {}) {
        const urlPattern = DJANGO_URL_PATTERNS[pattern];

        if (!urlPattern) {
            console.error(`URL pattern '${pattern}' not found`);
            return '/';
        }

        // If pattern is a function, call it with params
        if (typeof urlPattern === 'function') {
            return urlPattern(params.mode || params);
        }

        return urlPattern;
    }
};

// ============================================================================
// COMBINED API ENDPOINTS OBJECT
// ============================================================================

/**
 * Main API endpoints object
 * Provides organized access to all API endpoints
 */
const API_ENDPOINTS = {
    DASHBOARD: DASHBOARD_API,
    DASHBOARD_PAGES: DASHBOARD_PAGES,
    PAPER_TRADING: PAPER_TRADING_API,
    PAPER_TRADING_PAGES: PAPER_TRADING_PAGES,
    TRADING: TRADING_API,
    WALLET: WALLET_API,
    WEBSOCKET: WEBSOCKET_ENDPOINTS,
    PATTERNS: DJANGO_URL_PATTERNS,
    RESPONSE: API_RESPONSE,
    UTILS: API_UTILS
};

// ============================================================================
// GLOBAL EXPORTS
// ============================================================================

// Make available globally
window.API_ENDPOINTS = API_ENDPOINTS;
window.DASHBOARD_API = DASHBOARD_API;
window.DASHBOARD_PAGES = DASHBOARD_PAGES;
window.PAPER_TRADING_API = PAPER_TRADING_API;
window.PAPER_TRADING_PAGES = PAPER_TRADING_PAGES;
window.TRADING_API = TRADING_API;
window.WALLET_API = WALLET_API;
window.WEBSOCKET_ENDPOINTS = WEBSOCKET_ENDPOINTS;
window.API_UTILS = API_UTILS;

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        API_ENDPOINTS,
        DASHBOARD_API,
        DASHBOARD_PAGES,
        PAPER_TRADING_API,
        PAPER_TRADING_PAGES,
        TRADING_API,
        WALLET_API,
        WEBSOCKET_ENDPOINTS,
        DJANGO_URL_PATTERNS,
        API_RESPONSE,
        API_UTILS
    };
}

// ============================================================================
// INITIALIZATION
// ============================================================================

/**
 * Initialize API constants
 * Logs configuration for debugging
 */
function initializeApiConstants() {
    console.log('API Constants loaded successfully');
    console.log('Available endpoints:', {
        dashboard: Object.keys(DASHBOARD_API).length,
        paperTrading: Object.keys(PAPER_TRADING_API).length,
        trading: Object.keys(TRADING_API).length,
        wallet: Object.keys(WALLET_API).length
    });
}

// Auto-initialize
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeApiConstants);
} else {
    initializeApiConstants();
}

console.log('API Constants v1.0 loaded successfully');