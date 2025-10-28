/**
 * Form Field Constants
 * 
 * Centralized form field names, element IDs, and CSS selectors for the entire project.
 * This prevents typos and makes refactoring easier by providing a single source of truth.
 * 
 * Usage:
 *   const field = document.querySelector(`[name="${FORM_FIELDS.TRADING.MAX_POSITION_SIZE}"]`);
 *   const element = document.getElementById(ELEMENT_IDS.CONFIG_FORM);
 * 
 * File: dexproject/static/js/form-constants.js
 */

'use strict';

// ============================================================================
// TRADING CONFIGURATION FORM FIELDS
// ============================================================================

const TRADING_FIELDS = {
    // Mode selection
    TRADING_MODE_VISUAL: 'trading_mode_visual',
    TRADING_MODE_SELECT: 'trading-mode-select',

    // Strategy name
    NAME: 'name',
    DESCRIPTION: 'description',

    // Lane selection
    USE_FAST_LANE: 'use_fast_lane',
    USE_SMART_LANE: 'use_smart_lane',

    // Position sizing
    MAX_POSITION_SIZE: 'max_position_size_percent',
    MAX_POSITION_SIZE_USD: 'max_position_size_usd',
    MIN_POSITION_SIZE: 'min_position_size_percent',

    // Trade limits
    MAX_DAILY_TRADES: 'max_daily_trades',
    MAX_CONCURRENT_POSITIONS: 'max_concurrent_positions',

    // Risk management
    CONFIDENCE_THRESHOLD: 'confidence_threshold',
    STOP_LOSS: 'stop_loss_percent',
    TAKE_PROFIT: 'take_profit_percent',
    TRAILING_STOP: 'trailing_stop_percent',
    MAX_SLIPPAGE: 'max_slippage_percent',

    // Timing
    MIN_HOLD_TIME: 'min_hold_time_seconds',
    MAX_HOLD_TIME: 'max_hold_time_seconds',

    // Advanced settings
    USE_MEV_PROTECTION: 'use_mev_protection',
    USE_FLASHBOTS: 'use_flashbots',
    AUTO_REBALANCE: 'auto_rebalance',

    // Metadata
    SAVE_AS_NEW: 'save_as_new',
    IS_ACTIVE: 'is_active'
};

// ============================================================================
// SMART LANE CONFIGURATION FIELDS
// ============================================================================

const SMART_LANE_FIELDS = {
    // Analyzer toggles
    ENABLE_TECHNICAL: 'enable_technical',
    ENABLE_SENTIMENT: 'enable_sentiment',
    ENABLE_LIQUIDITY: 'enable_liquidity',
    ENABLE_VOLUME: 'enable_volume',
    ENABLE_HOLDER: 'enable_holder',
    ENABLE_SOCIAL: 'enable_social',

    // Technical indicators
    TECHNICAL_INDICATORS: 'technical_indicators',
    TECHNICAL_TIMEFRAMES: 'technical_timeframes',

    // Weights
    TECHNICAL_WEIGHT: 'technical_weight',
    SENTIMENT_WEIGHT: 'sentiment_weight',
    LIQUIDITY_WEIGHT: 'liquidity_weight',
    VOLUME_WEIGHT: 'volume_weight',

    // Thresholds
    MIN_LIQUIDITY: 'min_liquidity_usd',
    MIN_VOLUME_24H: 'min_volume_24h',
    MIN_HOLDERS: 'min_holders_count',

    // Analysis settings
    ANALYSIS_DEPTH: 'analysis_depth',
    USE_HISTORICAL_DATA: 'use_historical_data',
    LOOKBACK_PERIOD: 'lookback_period_hours'
};

// ============================================================================
// FILTER FORM FIELDS
// ============================================================================

const FILTER_FIELDS = {
    // Trade history filters
    STATUS: 'status',
    TRADE_TYPE: 'trade_type',
    DATE_FROM: 'date_from',
    DATE_TO: 'date_to',
    TOKEN_SYMBOL: 'token_symbol',
    MIN_AMOUNT: 'min_amount',
    MAX_AMOUNT: 'max_amount',

    // Analytics filters
    TIME_PERIOD: 'time_period',
    METRIC_TYPE: 'metric_type',

    // Portfolio filters
    POSITION_STATUS: 'position_status',
    SORT_BY: 'sort_by',
    SORT_ORDER: 'sort_order'
};

// ============================================================================
// QUICK TRADE FORM FIELDS
// ============================================================================

const QUICK_TRADE_FIELDS = {
    TOKEN_ADDRESS: 'token_address',
    TOKEN_SYMBOL: 'token_symbol',
    AMOUNT: 'amount',
    AMOUNT_USD: 'amount_usd',
    TRADE_TYPE: 'trade_type',
    SLIPPAGE: 'slippage',
    USE_MEV_PROTECTION: 'use_mev_protection'
};

// ============================================================================
// WALLET FIELDS
// ============================================================================

const WALLET_FIELDS = {
    WALLET_ADDRESS: 'wallet_address',
    CHAIN_ID: 'chain_id',
    SIGNATURE: 'signature',
    MESSAGE: 'message',
    NONCE: 'nonce'
};

// ============================================================================
// ELEMENT IDS
// ============================================================================

const ELEMENT_IDS = {
    // Forms
    CONFIG_FORM: 'config-form',
    FAST_LANE_CONFIG_FORM: 'fast-lane-config-form',
    SMART_LANE_CONFIG_FORM: 'smart-lane-config-form',
    FILTER_FORM: 'filter-form',
    QUICK_TRADE_FORM: 'quick-trade-form',
    QUICK_BUY_FORM: 'quick-buy-form',
    ANALYSIS_FORM: 'analysis-form',

    // Risk indicators
    RISK_INDICATOR: 'risk-indicator',
    RISK_LEVEL_TEXT: 'risk-level-text',
    RISK_DESCRIPTION: 'risk-description',
    COMPLEXITY_INDICATOR: 'complexity-indicator',

    // Confidence displays
    CONFIDENCE_FILL: 'confidence-fill',
    CONFIDENCE_PERCENTAGE: 'confidence-percentage',

    // Status displays
    BOT_STATUS_TEXT: 'bot-status-text',
    AI_STATUS: 'ai-status',
    LOADING_STATUS: 'loading-status',

    // Containers
    NOTIFICATIONS_CONTAINER: 'notifications-container',
    TOAST_CONTAINER: 'toast-container',
    POSITIONS_CONTAINER: 'positions-container',
    OPEN_POSITIONS_TBODY: 'open-positions-tbody',
    ACTIVE_TRANSACTIONS_CONTAINER: 'active-transactions-container',
    ANALYZER_RESULTS: 'analyzer-results',
    ANALYSIS_RESULTS: 'analysis-results',
    DETAILED_ANALYSIS: 'detailed-analysis',

    // Charts
    PORTFOLIO_VALUE_CHART: 'portfolio-value-chart',
    PORTFOLIO_PERFORMANCE_CHART: 'portfolio-performance-chart',
    POSITIONS_PERFORMANCE_CHART: 'positions-performance-chart',
    PNL_CHART: 'pnlChart',
    HOURLY_CHART: 'hourlyChart',
    TOKEN_CHART: 'tokenChart',
    DISTRIBUTION_CHART: 'distributionChart',
    CANDLESTICK_CHART: 'candlestick-chart',
    DEPTH_CHART: 'depth-chart',

    // Buttons
    ANALYZE_BTN: 'analyze-btn',
    MANUAL_TRADE_BTN: 'manual-trade-btn',
    EXECUTE_BUY_BTN: 'execute-buy-btn',
    EXECUTE_SELL_BTN: 'execute-sell-btn',
    FAST_LANE_TOGGLE_BTN: 'fast-lane-toggle-btn',
    EXPORT_ANALYTICS: 'export-analytics',

    // Displays
    PORTFOLIO_VALUE: 'portfolio-value',
    POSITIONS_COUNT: 'positions-count',
    PENDING_TRADES_COUNT: 'pending-trades-count',
    GAS_PRICE_DISPLAY: 'gas-price-display',
    GAS_SAVINGS_TOTAL: 'gas-savings-total',
    EXECUTION_TIME_DISPLAY: 'execution-time-display',
    ESTIMATED_ANALYSIS_TIME: 'estimated-analysis-time',

    // Preview displays
    PREVIEW_GAS: 'preview-gas',
    PREVIEW_SLIPPAGE: 'preview-slippage',
    PREVIEW_MEV: 'preview-mev',
    PREVIEW_POSITION_SIZE: 'preview-position-size',
    EXPECTED_SLIPPAGE: 'expected-slippage',

    // Warnings and alerts
    MEV_WARNING: 'mev-warning',
    LOADING_OVERLAY: 'loading-overlay',
    INITIAL_STATE: 'initial-state',

    // Selectors
    CHART_TIMEFRAME_SELECTOR: 'chart-timeframe-selector',
    CHART_TIME_RANGE: 'chart-time-range',

    // Modals
    DELETE_MODAL: 'deleteModal',
    HYBRID_MODAL: 'hybridModal',
    QUICK_TRADE_MODAL: 'quick-trade-modal',

    // Icons
    AUTO_SCROLL_ICON: 'auto-scroll-icon'
};

// ============================================================================
// CSS SELECTORS
// ============================================================================

const CSS_SELECTORS = {
    // Rows
    TRADE_ROW: '.trade-row',
    POSITION_ROW: '.position-row',
    CONFIG_ROW: '.config-row',

    // Cards
    MODE_CARD: '.mode-card',
    FAST_LANE_CARD: '.fast-lane-card',
    SMART_LANE_CARD: '.smart-lane-card',
    METRIC_CARD: '.metric-card',
    POSITION_CARD: '.position-card',

    // Status indicators
    STATUS_BADGE: '.status-badge',
    RISK_ICON: '.risk-icon',
    BOT_STATUS_INDICATOR: '.bot-status-indicator',

    // Navigation
    PAPER_NAV_LINK: '.paper-nav-link',
    NAV_LINK: '.nav-link',

    // Alerts
    ALERT: '.alert',
    TOAST: '.toast',

    // Forms
    ANALYZER_TOGGLE: 'input[name^="enable_"]',
    TECHNICAL_INDICATORS: 'input[name="technical_indicators"]',
    TECHNICAL_TIMEFRAMES: 'input[name="technical_timeframes"]',

    // Buttons
    BTN_PRIMARY: '.btn-primary',
    BTN_SUCCESS: '.btn-success',
    BTN_DANGER: '.btn-danger',
    BTN_LOADING: '.btn-loading',

    // Misc
    DISABLED_OVERLAY: '.disabled-overlay',
    LOADING_SPINNER: '.spinner-border'
};

// ============================================================================
// TRADING MODE VALUES
// ============================================================================

const TRADING_MODES = {
    CONSERVATIVE: 'CONSERVATIVE',
    MODERATE: 'MODERATE',
    AGGRESSIVE: 'AGGRESSIVE'
};

// ============================================================================
// TRADE TYPES
// ============================================================================

const TRADE_TYPES = {
    BUY: 'BUY',
    SELL: 'SELL',
    SWAP: 'SWAP'
};

// ============================================================================
// TRADE STATUS VALUES
// ============================================================================

const TRADE_STATUS = {
    PENDING: 'PENDING',
    COMPLETED: 'COMPLETED',
    FAILED: 'FAILED',
    CANCELLED: 'CANCELLED'
};

// ============================================================================
// POSITION STATUS VALUES
// ============================================================================

const POSITION_STATUS = {
    OPEN: 'OPEN',
    CLOSED: 'CLOSED',
    PARTIAL: 'PARTIAL'
};

// ============================================================================
// COMBINED FORM FIELDS OBJECT
// ============================================================================

/**
 * Main form fields object
 * Provides organized access to all form field constants
 */
const FORM_FIELDS = {
    TRADING: TRADING_FIELDS,
    SMART_LANE: SMART_LANE_FIELDS,
    FILTERS: FILTER_FIELDS,
    QUICK_TRADE: QUICK_TRADE_FIELDS,
    WALLET: WALLET_FIELDS
};

/**
 * Combined constants object
 * Provides access to all form-related constants
 */
const FORM_CONSTANTS = {
    FIELDS: FORM_FIELDS,
    ELEMENTS: ELEMENT_IDS,
    SELECTORS: CSS_SELECTORS,
    MODES: TRADING_MODES,
    TRADE_TYPES: TRADE_TYPES,
    TRADE_STATUS: TRADE_STATUS,
    POSITION_STATUS: POSITION_STATUS
};

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

const FORM_UTILS = {
    /**
     * Get form field value safely
     * 
     * @param {string} fieldName - Field name
     * @returns {string|null} Field value or null
     */
    getFieldValue: function (fieldName) {
        const field = document.querySelector(`[name="${fieldName}"]`);
        return field ? field.value : null;
    },

    /**
     * Set form field value safely
     * 
     * @param {string} fieldName - Field name
     * @param {any} value - Value to set
     * @returns {boolean} True if successful
     */
    setFieldValue: function (fieldName, value) {
        const field = document.querySelector(`[name="${fieldName}"]`);
        if (field) {
            if (field.type === 'checkbox' || field.type === 'radio') {
                field.checked = !!value;
            } else {
                field.value = value;
            }
            return true;
        }
        return false;
    },

    /**
     * Get element by ID safely
     * 
     * @param {string} elementId - Element ID
     * @returns {HTMLElement|null} Element or null
     */
    getElement: function (elementId) {
        return document.getElementById(elementId);
    },

    /**
     * Check if field exists
     * 
     * @param {string} fieldName - Field name
     * @returns {boolean} True if field exists
     */
    fieldExists: function (fieldName) {
        return document.querySelector(`[name="${fieldName}"]`) !== null;
    },

    /**
     * Get all checked values for checkbox/radio group
     * 
     * @param {string} fieldName - Field name
     * @returns {Array<string>} Array of checked values
     */
    getCheckedValues: function (fieldName) {
        const fields = document.querySelectorAll(`[name="${fieldName}"]:checked`);
        return Array.from(fields).map(field => field.value);
    },

    /**
     * Validate required fields
     * 
     * @param {Array<string>} requiredFields - Array of required field names
     * @returns {Object} Validation result {valid: boolean, missing: Array<string>}
     */
    validateRequired: function (requiredFields) {
        const missing = [];

        for (const fieldName of requiredFields) {
            const value = this.getFieldValue(fieldName);
            if (!value || value.trim() === '') {
                missing.push(fieldName);
            }
        }

        return {
            valid: missing.length === 0,
            missing: missing
        };
    }
};

// ============================================================================
// GLOBAL EXPORTS
// ============================================================================

// Make available globally
window.FORM_FIELDS = FORM_FIELDS;
window.FORM_CONSTANTS = FORM_CONSTANTS;
window.FORM_UTILS = FORM_UTILS;
window.TRADING_FIELDS = TRADING_FIELDS;
window.SMART_LANE_FIELDS = SMART_LANE_FIELDS;
window.FILTER_FIELDS = FILTER_FIELDS;
window.QUICK_TRADE_FIELDS = QUICK_TRADE_FIELDS;
window.WALLET_FIELDS = WALLET_FIELDS;
window.ELEMENT_IDS = ELEMENT_IDS;
window.CSS_SELECTORS = CSS_SELECTORS;
window.TRADING_MODES = TRADING_MODES;
window.TRADE_TYPES = TRADE_TYPES;
window.TRADE_STATUS = TRADE_STATUS;
window.POSITION_STATUS = POSITION_STATUS;

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        FORM_FIELDS,
        FORM_CONSTANTS,
        FORM_UTILS,
        TRADING_FIELDS,
        SMART_LANE_FIELDS,
        FILTER_FIELDS,
        QUICK_TRADE_FIELDS,
        WALLET_FIELDS,
        ELEMENT_IDS,
        CSS_SELECTORS,
        TRADING_MODES,
        TRADE_TYPES,
        TRADE_STATUS,
        POSITION_STATUS
    };
}

// ============================================================================
// INITIALIZATION
// ============================================================================

/**
 * Initialize form constants
 * Logs configuration for debugging
 */
function initializeFormConstants() {
    console.log('Form Constants loaded successfully');
    console.log('Available constants:', {
        tradingFields: Object.keys(TRADING_FIELDS).length,
        smartLaneFields: Object.keys(SMART_LANE_FIELDS).length,
        elementIds: Object.keys(ELEMENT_IDS).length,
        selectors: Object.keys(CSS_SELECTORS).length
    });
}

// Auto-initialize
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeFormConstants);
} else {
    initializeFormConstants();
}

console.log('Form Constants v1.0 loaded successfully');