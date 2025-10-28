/**
 * Form Constants
 * 
 * Centralized UI element IDs, CSS classes, localStorage keys, and event names.
 * Used across the application for consistent DOM manipulation and event handling.
 * 
 * File: static/js/form-constants.js
 */

'use strict';

// ============================================================================
// ELEMENT IDS
// ============================================================================

const ELEMENT_IDS = {
    // Wallet connection elements
    WALLET_CONNECT_BTN: 'wallet-connect-btn',
    WALLET_DISCONNECT_BTN: 'wallet-disconnect-btn',
    WALLET_ADDRESS_DISPLAY: 'wallet-address',
    WALLET_CHAIN_DISPLAY: 'wallet-chain',
    WALLET_INFO_CONTAINER: 'wallet-info',
    WALLET_STATUS_MESSAGE: 'wallet-status',
    WALLET_NAV_INDICATOR: 'wallet-nav-indicator',
    WALLET_BALANCE: 'wallet-balance',

    // Trading form elements
    TRADING_FORM: 'tradingForm',
    TRADE_AMOUNT: 'trade-amount',
    TRADE_TOKEN: 'trade-token',
    TRADE_SLIPPAGE: 'trade-slippage',
    TRADE_GAS_PRICE: 'trade-gas-price',

    // Configuration elements
    CONFIG_FORM: 'configForm',
    CONFIG_NAME: 'config_name',
    TRADING_MODE_SELECT: 'trading-mode-select',
    RISK_INDICATOR: 'risk-indicator',

    // Paper trading elements
    PT_METRICS_CONTAINER: 'metrics-container',
    PT_POSITIONS_TABLE: 'positions-table',
    PT_TRADES_TABLE: 'trades-table',
    PT_BALANCE_DISPLAY: 'balance-display',

    // Dashboard elements
    DASHBOARD_CONTAINER: 'dashboard-container',
    PORTFOLIO_SUMMARY: 'portfolio-summary',
    ANALYTICS_CHART: 'analytics-chart',

    // Status and notification elements
    TOAST_CONTAINER: 'toast-container',
    LOADING_SPINNER: 'loading-spinner',
    ERROR_MESSAGE: 'error-message',
    SUCCESS_MESSAGE: 'success-message'
};

// ============================================================================
// CSS CLASSES
// ============================================================================

const CSS_CLASSES = {
    // Visibility
    HIDDEN: 'd-none',
    VISIBLE: 'd-block',
    INVISIBLE: 'invisible',

    // Status indicators
    STATUS_SUCCESS: 'status-success',
    STATUS_ERROR: 'status-error',
    STATUS_WARNING: 'status-warning',
    STATUS_INFO: 'status-info',
    STATUS_OPERATIONAL: 'bg-success',
    STATUS_DEGRADED: 'bg-warning',
    STATUS_DOWN: 'bg-danger',

    // State classes
    ACTIVE: 'active',
    DISABLED: 'disabled',
    LOADING: 'loading',
    CONNECTED: 'connected',
    DISCONNECTED: 'disconnected',

    // Alert classes
    ALERT_SUCCESS: 'alert-success',
    ALERT_ERROR: 'alert-danger',
    ALERT_WARNING: 'alert-warning',
    ALERT_INFO: 'alert-info',

    // Button states
    BTN_PRIMARY: 'btn-primary',
    BTN_SUCCESS: 'btn-success',
    BTN_DANGER: 'btn-danger',
    BTN_WARNING: 'btn-warning',
    BTN_LOADING: 'btn-loading',

    // Form validation
    IS_VALID: 'is-valid',
    IS_INVALID: 'is-invalid',
    WAS_VALIDATED: 'was-validated',

    // Animations
    FADE_IN: 'fade-in',
    FADE_OUT: 'fade-out',
    SLIDE_IN: 'slide-in',
    SLIDE_OUT: 'slide-out',
    PULSE: 'pulse'
};

// ============================================================================
// DATA ACTIONS (for event delegation)
// ============================================================================

const DATA_ACTIONS = {
    CONNECT_WALLET: '[data-action="connect-wallet"]',
    DISCONNECT_WALLET: '[data-action="disconnect-wallet"]',
    SWITCH_CHAIN: '[data-action="switch-chain"]',
    REFRESH_BALANCE: '[data-action="refresh-balance"]',
    EXECUTE_TRADE: '[data-action="execute-trade"]',
    START_BOT: '[data-action="start-bot"]',
    STOP_BOT: '[data-action="stop-bot"]',
    SAVE_CONFIG: '[data-action="save-config"]',
    DELETE_CONFIG: '[data-action="delete-config"]',
    EXPORT_DATA: '[data-action="export-data"]',
    PRINT_REPORT: '[data-action="print-report"]'
};

// ============================================================================
// SELECTORS
// ============================================================================

const SELECTORS = {
    // Forms
    ALL_FORMS: 'form',
    REQUIRED_FIELDS: '[required]',
    INPUT_FIELDS: 'input, select, textarea',

    // Tables
    DATA_TABLES: '.data-table',
    TABLE_ROWS: 'tr',
    TABLE_CELLS: 'td',

    // Cards
    CARDS: '.card',
    CARD_HEADERS: '.card-header',
    CARD_BODIES: '.card-body',

    // Modals
    MODALS: '.modal',
    MODAL_TRIGGERS: '[data-bs-toggle="modal"]',

    // Navigation
    NAV_LINKS: '.nav-link',
    NAV_ITEMS: '.nav-item',

    // Buttons
    BUTTONS: 'button',
    SUBMIT_BUTTONS: 'button[type="submit"]',

    // Status indicators
    STATUS_BADGES: '.status-badge',
    STATUS_INDICATORS: '.status-indicator'
};

// ============================================================================
// LOCAL STORAGE KEYS
// ============================================================================

const LOCAL_STORAGE_KEYS = {
    WALLET_SESSION: 'walletSession',
    USER_PREFERENCES: 'userPreferences',
    TRADING_CONFIG: 'tradingConfig',
    FAST_LANE_CONFIG: 'fastLaneConfig',
    SMART_LANE_CONFIG: 'smartLaneConfig',
    CHART_SETTINGS: 'chartSettings',
    DASHBOARD_LAYOUT: 'dashboardLayout',
    THEME_MODE: 'themeMode',
    LAST_SELECTED_CHAIN: 'lastSelectedChain',
    SESSION_DATA: 'sessionData'
};

// ============================================================================
// CUSTOM EVENTS
// ============================================================================

const CUSTOM_EVENTS = {
    // Wallet events
    WALLET_CONNECTED: 'wallet:connected',
    WALLET_DISCONNECTED: 'wallet:disconnected',
    WALLET_CHAIN_CHANGED: 'wallet:chainChanged',
    WALLET_ACCOUNT_CHANGED: 'wallet:accountChanged',
    WALLET_BALANCE_UPDATED: 'wallet:balanceUpdated',

    // Trading events
    TRADE_EXECUTED: 'trade:executed',
    TRADE_FAILED: 'trade:failed',
    TRADE_PENDING: 'trade:pending',
    TRADE_CONFIRMED: 'trade:confirmed',

    // Bot events
    BOT_STARTED: 'bot:started',
    BOT_STOPPED: 'bot:stopped',
    BOT_ERROR: 'bot:error',
    BOT_STATUS_CHANGED: 'bot:statusChanged',

    // UI events
    TOAST_SHOW: 'toast:show',
    TOAST_HIDE: 'toast:hide',
    MODAL_OPENED: 'modal:opened',
    MODAL_CLOSED: 'modal:closed',
    FORM_VALIDATED: 'form:validated',
    FORM_SUBMITTED: 'form:submitted',

    // Data events
    DATA_LOADED: 'data:loaded',
    DATA_ERROR: 'data:error',
    DATA_UPDATED: 'data:updated',
    DATA_REFRESHED: 'data:refreshed'
};

// ============================================================================
// MESSAGE TYPES (for status messages)
// ============================================================================

const MESSAGE_TYPES = {
    SUCCESS: 'success',
    ERROR: 'error',
    WARNING: 'warning',
    INFO: 'info',
    LOADING: 'loading'
};

// ============================================================================
// WALLET STATUS MESSAGES
// ============================================================================

const WALLET_STATUS_MESSAGES = {
    CONNECTING: 'Connecting to wallet...',
    CONNECTED: 'Wallet connected successfully',
    DISCONNECTED: 'Wallet disconnected',
    NO_WALLET: 'No Web3 wallet detected. Please install MetaMask.',
    UNSUPPORTED_CHAIN: 'Unsupported network. Please switch to a supported chain.',
    REJECTED: 'Connection request rejected by user',
    ERROR: 'Wallet connection error',
    SIGNING: 'Please sign the message in your wallet...',
    AUTHENTICATING: 'Authenticating with blockchain...',
    SWITCHING_CHAIN: 'Switching network...'
};

// ============================================================================
// TRADING FIELD NAMES
// ============================================================================

const TRADING_FIELDS = {
    TOKEN_IN: 'token_in',
    TOKEN_OUT: 'token_out',
    AMOUNT_IN: 'amount_in',
    AMOUNT_OUT: 'amount_out',
    SLIPPAGE: 'slippage_tolerance',
    GAS_PRICE: 'gas_price_gwei',
    DEADLINE: 'deadline_minutes',
    RECIPIENT: 'recipient_address',
    USE_PERMIT: 'use_permit2',
    MEV_PROTECTION: 'mev_protection',
    SMART_ROUTING: 'smart_routing_enabled',
    AUTO_REVERT: 'auto_revert_on_loss'
};

// ============================================================================
// SMART LANE FIELDS
// ============================================================================

const SMART_LANE_FIELDS = {
    ANALYSIS_DEPTH: 'analysis_depth',
    CONFIDENCE_THRESHOLD: 'min_confidence_threshold',
    RISK_TOLERANCE: 'risk_tolerance',
    POSITION_SIZING: 'position_sizing_method',
    STOP_LOSS: 'stop_loss_percentage',
    TAKE_PROFIT: 'take_profit_percentage',
    TRAILING_STOP: 'trailing_stop_enabled',
    AI_THOUGHT_LOG: 'ai_thought_log_enabled',
    TECHNICAL_INDICATORS: 'technical_indicators',
    TECHNICAL_TIMEFRAMES: 'technical_timeframes'
};

// ============================================================================
// EXPORT FOR GLOBAL USE
// ============================================================================

// Make available globally
window.ELEMENT_IDS = ELEMENT_IDS;
window.CSS_CLASSES = CSS_CLASSES;
window.DATA_ACTIONS = DATA_ACTIONS;
window.SELECTORS = SELECTORS;
window.LOCAL_STORAGE_KEYS = LOCAL_STORAGE_KEYS;
window.CUSTOM_EVENTS = CUSTOM_EVENTS;
window.MESSAGE_TYPES = MESSAGE_TYPES;
window.WALLET_STATUS_MESSAGES = WALLET_STATUS_MESSAGES;
window.TRADING_FIELDS = TRADING_FIELDS;
window.SMART_LANE_FIELDS = SMART_LANE_FIELDS;

console.log('Form Constants v1.0 loaded successfully');
console.log('Available constants:', {
    elementIds: Object.keys(ELEMENT_IDS).length,
    cssClasses: Object.keys(CSS_CLASSES).length,
    localStorageKeys: Object.keys(LOCAL_STORAGE_KEYS).length,
    customEvents: Object.keys(CUSTOM_EVENTS).length,
    messageTypes: Object.keys(MESSAGE_TYPES).length,
    walletMessages: Object.keys(WALLET_STATUS_MESSAGES).length,
    tradingFields: Object.keys(TRADING_FIELDS).length,
    smartLaneFields: Object.keys(SMART_LANE_FIELDS).length,
    dataActions: Object.keys(DATA_ACTIONS).length,
    selectors: Object.keys(SELECTORS).length
});