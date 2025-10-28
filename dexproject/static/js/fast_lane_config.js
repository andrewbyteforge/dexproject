/**
 * Fast Lane Configuration JavaScript
 * 
 * Provides interactive functionality for high-speed trading configuration.
 * Handles form submission, quick trades, and real-time configuration preview.
 * 
 * Dependencies:
 * - common-utils.js (must be loaded before this file)
 *   - Uses: getCSRFToken(), showToast()
 * - api-constants.js (must be loaded before this file)
 *   - Uses: API_ENDPOINTS.TRADING
 * - form-constants.js (optional, for type safety)
 *   - Uses: ELEMENT_IDS
 * 
 * File: dashboard/static/dashboard/js/fast_lane_config.js
 */

'use strict';

// ============================================================================
// CONSTANTS
// ============================================================================

const FAST_LANE_CONFIG_CONSTANTS = {
    // Element IDs
    ELEMENTS: {
        CONFIG_FORM: 'fast-lane-config-form',
        QUICK_BUY_FORM: 'quick-buy-form',
        QUICK_SELL_FORM: 'quick-sell-form',

        // Sliders
        EXECUTION_TIMEOUT: 'execution_timeout',
        TIMEOUT_DISPLAY: 'timeout-display',
        MAX_SLIPPAGE: 'max_slippage',
        SLIPPAGE_DISPLAY: 'slippage-display',

        // Gauges
        SPEED_DISPLAY: 'speed-display',
        SPEED_GAUGE: 'speed-gauge',
        SPEED_NEEDLE: 'speed-needle',
        RISK_GAUGE: 'risk-gauge',
        RISK_NEEDLE: 'risk-needle',

        // Preview elements
        PREVIEW_POSITION_SIZE: 'preview-position-size',
        PREVIEW_SLIPPAGE: 'preview-slippage',
        PREVIEW_GAS: 'preview-gas',
        PREVIEW_MEV: 'preview-mev',

        // Configuration fields
        DEFAULT_POSITION_SIZE: 'default_position_size',
        MAX_POSITION_SIZE: 'max_position_size',
        GAS_PRICE_MULTIPLIER: 'gas_price_multiplier',
        MAX_GAS_PRICE: 'max_gas_price',
        PRIORITY_FEE: 'priority_fee',
        ENABLE_MEV_PROTECTION: 'enable_mev_protection',
        USE_PRIVATE_MEMPOOL: 'use_private_mempool',
        ENABLE_SANDWICH_PROTECTION: 'enable_sandwich_protection',
        STOP_LOSS_PERCENT: 'stop_loss_percent',
        TAKE_PROFIT_PERCENT: 'take_profit_percent',

        // Controls
        TRADING_CONTROLS: 'trading-controls',
        START_FAST_SESSION: 'start-fast-session',
        STOP_FAST_SESSION: 'stop-fast-session'
    },

    // Selectors
    SELECTORS: {
        TRADING_PAIR_CARD: '.trading-pair-card',
        TRADING_PAIR_SELECTED: '.trading-pair-card.selected',
        SPEED_INDICATOR: '.speed-indicator',
        CONFIG_FORM_INPUTS: '#fast-lane-config-form input, #fast-lane-config-form select',
        TOOLTIP: '[data-bs-toggle="tooltip"]'
    },

    // Speed thresholds (in milliseconds)
    SPEED_THRESHOLDS: {
        ULTRA_FAST: 300,
        FAST: 500,
        STANDARD: 1000
    },

    // Default values
    DEFAULTS: {
        EXECUTION_TIMEOUT: 500,
        MAX_SLIPPAGE: 1.0,
        DEFAULT_POSITION_SIZE: 0.1,
        MAX_POSITION_SIZE: 1.0,
        GAS_PRICE_MULTIPLIER: 1.2,
        MAX_GAS_PRICE: 100,
        PRIORITY_FEE: 2.0
    },

    // Storage key
    STORAGE_KEY: 'fast_lane_config',

    // Auto-save delay (milliseconds)
    AUTO_SAVE_DELAY: 2000
};

// ============================================================================
// FAST LANE CONFIGURATION MODULE
// ============================================================================

const FastLaneConfig = {

    /**
     * Initialize the Fast Lane configuration page
     */
    init: function () {
        console.log('Initializing Fast Lane Configuration...');

        // Mark page for trading functionality
        document.body.dataset.page = 'fast-lane';

        // Initialize all components
        this.initializeFastLaneConfig();

        console.log('Fast Lane Configuration initialized');
    },

    /**
     * Main initialization function
     */
    initializeFastLaneConfig: function () {
        // Bind form events
        this.bindFormEvents();

        // Bind range input updates
        this.bindRangeInputs();

        // Bind trading pair selection
        this.bindTradingPairSelection();

        // Load saved configuration
        this.loadSavedConfiguration();

        // Update preview in real-time
        this.bindConfigurationPreview();

        // Initialize tooltips
        this.initializeTooltips();

        // Setup auto-save
        this.setupAutoSave();
    },

    /**
     * Bind form event handlers
     */
    bindFormEvents: function () {
        const configForm = document.getElementById(FAST_LANE_CONFIG_CONSTANTS.ELEMENTS.CONFIG_FORM);
        const quickBuyForm = document.getElementById(FAST_LANE_CONFIG_CONSTANTS.ELEMENTS.QUICK_BUY_FORM);
        const quickSellForm = document.getElementById(FAST_LANE_CONFIG_CONSTANTS.ELEMENTS.QUICK_SELL_FORM);

        if (configForm) {
            configForm.addEventListener('submit', this.saveConfiguration.bind(this));
        }

        if (quickBuyForm) {
            quickBuyForm.addEventListener('submit', this.executeQuickBuy.bind(this));
        }

        if (quickSellForm) {
            quickSellForm.addEventListener('submit', this.executeQuickSell.bind(this));
        }
    },

    /**
     * Bind range input event handlers
     */
    bindRangeInputs: function () {
        const timeoutSlider = document.getElementById(FAST_LANE_CONFIG_CONSTANTS.ELEMENTS.EXECUTION_TIMEOUT);
        const timeoutDisplay = document.getElementById(FAST_LANE_CONFIG_CONSTANTS.ELEMENTS.TIMEOUT_DISPLAY);
        const slippageSlider = document.getElementById(FAST_LANE_CONFIG_CONSTANTS.ELEMENTS.MAX_SLIPPAGE);
        const slippageDisplay = document.getElementById(FAST_LANE_CONFIG_CONSTANTS.ELEMENTS.SLIPPAGE_DISPLAY);

        if (timeoutSlider && timeoutDisplay) {
            timeoutSlider.addEventListener('input', function () {
                timeoutDisplay.textContent = `${this.value}ms`;
                FastLaneConfig.updateSpeedDisplay(this.value);
                FastLaneConfig.updatePerformanceGauges();
            });
        }

        if (slippageSlider && slippageDisplay) {
            slippageSlider.addEventListener('input', function () {
                slippageDisplay.textContent = `${this.value}%`;
                FastLaneConfig.updatePerformanceGauges();
            });
        }
    },

    /**
     * Bind trading pair selection events
     */
    bindTradingPairSelection: function () {
        const pairCards = document.querySelectorAll(FAST_LANE_CONFIG_CONSTANTS.SELECTORS.TRADING_PAIR_CARD);

        pairCards.forEach(card => {
            card.addEventListener('click', function () {
                this.classList.toggle('selected');
                FastLaneConfig.updateSelectedPairs();
                FastLaneConfig.updateConfigurationPreview();
            });
        });
    },

    /**
     * Bind configuration preview updates
     */
    bindConfigurationPreview: function () {
        const inputs = document.querySelectorAll(FAST_LANE_CONFIG_CONSTANTS.SELECTORS.CONFIG_FORM_INPUTS);

        inputs.forEach(input => {
            input.addEventListener('input', () => {
                this.updateConfigurationPreview();
                this.updatePerformanceGauges();
            });

            input.addEventListener('change', () => {
                this.updateConfigurationPreview();
                this.updatePerformanceGauges();
            });
        });
    },

    /**
     * Initialize Bootstrap tooltips
     */
    initializeTooltips: function () {
        const tooltips = document.querySelectorAll(FAST_LANE_CONFIG_CONSTANTS.SELECTORS.TOOLTIP);

        if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip) {
            tooltips.forEach(element => {
                new bootstrap.Tooltip(element);
            });
        }
    },

    /**
     * Setup auto-save functionality
     */
    setupAutoSave: function () {
        let autoSaveTimeout;

        const inputs = document.querySelectorAll(FAST_LANE_CONFIG_CONSTANTS.SELECTORS.CONFIG_FORM_INPUTS);

        inputs.forEach(input => {
            input.addEventListener('change', () => {
                clearTimeout(autoSaveTimeout);
                autoSaveTimeout = setTimeout(() => {
                    this.autoSaveConfiguration();
                }, FAST_LANE_CONFIG_CONSTANTS.AUTO_SAVE_DELAY);
            });
        });
    },

    /**
     * Auto-save configuration to localStorage
     */
    autoSaveConfiguration: function () {
        try {
            const config = this.gatherConfigurationData();
            localStorage.setItem(FAST_LANE_CONFIG_CONSTANTS.STORAGE_KEY, JSON.stringify(config));
            console.log('Configuration auto-saved');
        } catch (error) {
            console.error('Auto-save error:', error);
        }
    }
};

// ============================================================================
// DISPLAY UPDATE FUNCTIONS
// ============================================================================

FastLaneConfig.updateSpeedDisplay = function (timeoutMs) {
    const speedDisplay = document.getElementById(FAST_LANE_CONFIG_CONSTANTS.ELEMENTS.SPEED_DISPLAY);
    if (!speedDisplay) return;

    const thresholds = FAST_LANE_CONFIG_CONSTANTS.SPEED_THRESHOLDS;
    let speedText, speedClass;

    const speedIndicator = document.querySelector(FAST_LANE_CONFIG_CONSTANTS.SELECTORS.SPEED_INDICATOR);

    if (timeoutMs <= thresholds.ULTRA_FAST) {
        speedText = 'Ultra Fast';
        speedClass = 'speed-ultra-fast';
    } else if (timeoutMs <= thresholds.FAST) {
        speedText = 'Fast';
        speedClass = 'speed-fast';
    } else {
        speedText = 'Standard';
        speedClass = 'speed-standard';
    }

    speedDisplay.textContent = speedText;
    if (speedIndicator) {
        speedIndicator.className = `speed-indicator ${speedClass}`;
    }
};

FastLaneConfig.updatePerformanceGauges = function () {
    const timeoutElement = document.getElementById(FAST_LANE_CONFIG_CONSTANTS.ELEMENTS.EXECUTION_TIMEOUT);
    const slippageElement = document.getElementById(FAST_LANE_CONFIG_CONSTANTS.ELEMENTS.MAX_SLIPPAGE);

    if (!timeoutElement || !slippageElement) return;

    const timeout = parseInt(timeoutElement.value);
    const slippage = parseFloat(slippageElement.value);

    // Update speed gauge (lower timeout = higher speed)
    const speedGauge = document.getElementById(FAST_LANE_CONFIG_CONSTANTS.ELEMENTS.SPEED_GAUGE);
    const speedNeedle = document.getElementById(FAST_LANE_CONFIG_CONSTANTS.ELEMENTS.SPEED_NEEDLE);

    if (speedGauge && speedNeedle) {
        const speedPercentage = Math.max(0, Math.min(100, (2000 - timeout) / 20));
        speedNeedle.style.transform = `rotate(${speedPercentage * 1.8}deg)`;
    }

    // Update risk gauge (higher slippage = higher risk)
    const riskGauge = document.getElementById(FAST_LANE_CONFIG_CONSTANTS.ELEMENTS.RISK_GAUGE);
    const riskNeedle = document.getElementById(FAST_LANE_CONFIG_CONSTANTS.ELEMENTS.RISK_NEEDLE);

    if (riskGauge && riskNeedle) {
        const riskPercentage = Math.min(100, slippage * 20);
        riskNeedle.style.transform = `rotate(${riskPercentage * 1.8}deg)`;
    }
};

FastLaneConfig.updateConfigurationPreview = function () {
    const fields = {
        positionSize: document.getElementById(FAST_LANE_CONFIG_CONSTANTS.ELEMENTS.DEFAULT_POSITION_SIZE),
        slippage: document.getElementById(FAST_LANE_CONFIG_CONSTANTS.ELEMENTS.MAX_SLIPPAGE),
        gasMultiplier: document.getElementById(FAST_LANE_CONFIG_CONSTANTS.ELEMENTS.GAS_PRICE_MULTIPLIER),
        mevProtection: document.getElementById(FAST_LANE_CONFIG_CONSTANTS.ELEMENTS.ENABLE_MEV_PROTECTION)
    };

    const previews = {
        positionSize: document.getElementById(FAST_LANE_CONFIG_CONSTANTS.ELEMENTS.PREVIEW_POSITION_SIZE),
        slippage: document.getElementById(FAST_LANE_CONFIG_CONSTANTS.ELEMENTS.PREVIEW_SLIPPAGE),
        gas: document.getElementById(FAST_LANE_CONFIG_CONSTANTS.ELEMENTS.PREVIEW_GAS),
        mev: document.getElementById(FAST_LANE_CONFIG_CONSTANTS.ELEMENTS.PREVIEW_MEV)
    };

    if (fields.positionSize && previews.positionSize) {
        previews.positionSize.textContent = `${fields.positionSize.value} ETH`;
    }

    if (fields.slippage && previews.slippage) {
        previews.slippage.textContent = `${fields.slippage.value}%`;
        previews.slippage.className = `fw-bold ${parseFloat(fields.slippage.value) > 2 ? 'text-warning' : 'text-success'}`;
    }

    if (fields.gasMultiplier && previews.gas) {
        previews.gas.textContent = `${fields.gasMultiplier.value}x`;
    }

    if (fields.mevProtection && previews.mev) {
        const enabled = fields.mevProtection.checked;
        previews.mev.textContent = enabled ? 'Enabled' : 'Disabled';
        previews.mev.className = `fw-bold ${enabled ? 'text-success' : 'text-warning'}`;
    }
};

FastLaneConfig.updateSelectedPairs = function () {
    const selectedPairs = document.querySelectorAll(FAST_LANE_CONFIG_CONSTANTS.SELECTORS.TRADING_PAIR_SELECTED);
    console.log(`Selected ${selectedPairs.length} trading pairs`);

    // Could show selected pairs count in UI if needed
    return selectedPairs.length;
};

// ============================================================================
// CONFIGURATION MANAGEMENT
// ============================================================================

FastLaneConfig.gatherConfigurationData = function () {
    const selectedPairs = Array.from(document.querySelectorAll(FAST_LANE_CONFIG_CONSTANTS.SELECTORS.TRADING_PAIR_SELECTED))
        .map(card => card.dataset.pair)
        .filter(pair => pair); // Filter out undefined values

    const getElementValue = (id, defaultValue = null) => {
        const element = document.getElementById(id);
        return element ? element.value : defaultValue;
    };

    const getCheckboxValue = (id, defaultValue = false) => {
        const element = document.getElementById(id);
        return element ? element.checked : defaultValue;
    };

    const elements = FAST_LANE_CONFIG_CONSTANTS.ELEMENTS;

    return {
        execution_timeout_ms: parseInt(getElementValue(elements.EXECUTION_TIMEOUT, FAST_LANE_CONFIG_CONSTANTS.DEFAULTS.EXECUTION_TIMEOUT)),
        max_slippage_percent: parseFloat(getElementValue(elements.MAX_SLIPPAGE, FAST_LANE_CONFIG_CONSTANTS.DEFAULTS.MAX_SLIPPAGE)),
        default_position_size_eth: parseFloat(getElementValue(elements.DEFAULT_POSITION_SIZE, FAST_LANE_CONFIG_CONSTANTS.DEFAULTS.DEFAULT_POSITION_SIZE)),
        max_position_size_eth: parseFloat(getElementValue(elements.MAX_POSITION_SIZE, FAST_LANE_CONFIG_CONSTANTS.DEFAULTS.MAX_POSITION_SIZE)),
        gas_price_multiplier: parseFloat(getElementValue(elements.GAS_PRICE_MULTIPLIER, FAST_LANE_CONFIG_CONSTANTS.DEFAULTS.GAS_PRICE_MULTIPLIER)),
        max_gas_price_gwei: parseInt(getElementValue(elements.MAX_GAS_PRICE, FAST_LANE_CONFIG_CONSTANTS.DEFAULTS.MAX_GAS_PRICE)),
        priority_fee_gwei: parseFloat(getElementValue(elements.PRIORITY_FEE, FAST_LANE_CONFIG_CONSTANTS.DEFAULTS.PRIORITY_FEE)),
        mev_protection_enabled: getCheckboxValue(elements.ENABLE_MEV_PROTECTION, true),
        private_mempool_enabled: getCheckboxValue(elements.USE_PRIVATE_MEMPOOL, true),
        sandwich_protection_enabled: getCheckboxValue(elements.ENABLE_SANDWICH_PROTECTION, true),
        target_trading_pairs: selectedPairs,
        stop_loss_percent: parseFloat(getElementValue(elements.STOP_LOSS_PERCENT)) || null,
        take_profit_percent: parseFloat(getElementValue(elements.TAKE_PROFIT_PERCENT)) || null
    };
};

FastLaneConfig.loadSavedConfiguration = function () {
    try {
        const saved = localStorage.getItem(FAST_LANE_CONFIG_CONSTANTS.STORAGE_KEY);
        if (saved) {
            const config = JSON.parse(saved);
            this.applyConfigurationToForm(config);
            console.log('Saved configuration loaded');
        }
    } catch (error) {
        console.error('Error loading saved configuration:', error);
    }
};

FastLaneConfig.applyConfigurationToForm = function (config) {
    // Apply saved configuration to form fields
    Object.entries(config).forEach(([key, value]) => {
        const element = document.getElementById(key);
        if (element) {
            if (element.type === 'checkbox') {
                element.checked = value;
            } else {
                element.value = value;
            }
        }
    });

    // Update displays
    this.updateConfigurationPreview();
    this.updatePerformanceGauges();

    // Update speed display if timeout is available
    if (config.execution_timeout_ms) {
        this.updateSpeedDisplay(config.execution_timeout_ms);
    }
};

// ============================================================================
// FORM SUBMISSION HANDLERS
// ============================================================================

FastLaneConfig.saveConfiguration = async function (e) {
    e.preventDefault();

    const config = this.gatherConfigurationData();

    console.log('Saving Fast Lane configuration:', config);

    try {
        // Use API endpoint from api-constants.js
        const response = await fetch(API_ENDPOINTS.TRADING.SESSION_START, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken(), // From common-utils.js
            },
            body: JSON.stringify({
                ...config,
                strategy_type: 'FAST_LANE',
                auto_execution: true
            })
        });

        const result = await response.json();

        if (result.success) {
            // Use global showToast from common-utils.js
            showToast('Fast Lane configuration saved and activated!', 'success');

            // Show trading controls
            const tradingControls = document.getElementById(FAST_LANE_CONFIG_CONSTANTS.ELEMENTS.TRADING_CONTROLS);
            if (tradingControls) {
                tradingControls.style.display = 'block';
            }

            // Update session controls
            const startBtn = document.getElementById(FAST_LANE_CONFIG_CONSTANTS.ELEMENTS.START_FAST_SESSION);
            const stopBtn = document.getElementById(FAST_LANE_CONFIG_CONSTANTS.ELEMENTS.STOP_FAST_SESSION);

            if (startBtn) startBtn.style.display = 'none';
            if (stopBtn) stopBtn.style.display = 'inline-block';

            // Trigger custom event
            document.dispatchEvent(new CustomEvent('fast-lane:configured', {
                detail: config
            }));

        } else {
            throw new Error(result.error || 'Configuration failed');
        }

    } catch (error) {
        console.error('Configuration error:', error);
        showToast(`Configuration failed: ${error.message}`, 'danger'); // From common-utils.js
    }
};

FastLaneConfig.executeQuickBuy = async function (e) {
    e.preventDefault();

    // Gather form data
    const formData = new FormData(e.target);
    const config = Object.fromEntries(formData.entries());

    // Validate required fields
    if (!config.token_address || !config.amount_eth) {
        showToast('Please fill in all required fields', 'warning'); // From common-utils.js
        return;
    }

    console.log('Executing quick buy:', config);

    try {
        const response = await fetch(API_ENDPOINTS.TRADING.BUY_V2, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken(), // From common-utils.js
            },
            body: JSON.stringify(config)
        });

        const result = await response.json();

        if (result.success) {
            showToast('Quick buy executed successfully!', 'success'); // From common-utils.js
            e.target.reset();
        } else {
            throw new Error(result.error || 'Quick buy failed');
        }

    } catch (error) {
        console.error('Quick buy error:', error);
        showToast(`Quick buy failed: ${error.message}`, 'danger'); // From common-utils.js
    }
};

FastLaneConfig.executeQuickSell = async function (e) {
    e.preventDefault();

    // Gather form data
    const formData = new FormData(e.target);
    const config = Object.fromEntries(formData.entries());

    // Validate required fields
    if (!config.token_address || !config.amount_tokens) {
        showToast('Please fill in all required fields', 'warning'); // From common-utils.js
        return;
    }

    console.log('Executing quick sell:', config);

    try {
        const response = await fetch(API_ENDPOINTS.TRADING.BUY_V2, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken(), // From common-utils.js
            },
            body: JSON.stringify({
                ...config,
                trade_type: 'SELL'
            })
        });

        const result = await response.json();

        if (result.success) {
            showToast('Quick sell executed successfully!', 'success'); // From common-utils.js
            e.target.reset();
        } else {
            throw new Error(result.error || 'Quick sell failed');
        }

    } catch (error) {
        console.error('Quick sell error:', error);
        showToast(`Quick sell failed: ${error.message}`, 'danger'); // From common-utils.js
    }
};

FastLaneConfig.testConfiguration = async function () {
    const config = this.gatherConfigurationData();

    console.log('Testing Fast Lane configuration:', config);
    showToast('Testing Fast Lane configuration...', 'info'); // From common-utils.js

    try {
        // Simulate test - replace with actual API call when available
        await new Promise(resolve => setTimeout(resolve, 1000));

        // Show test results
        const testPassed = config.execution_timeout_ms <= 1000 && config.max_slippage_percent <= 5;

        if (testPassed) {
            showToast(
                `Configuration test passed! Estimated execution time: ${config.execution_timeout_ms}ms`,
                'success'
            );
        } else {
            showToast('Configuration test completed with warnings. Review your settings.', 'warning');
        }

    } catch (error) {
        console.error('Configuration test error:', error);
        showToast(`Test failed: ${error.message}`, 'danger'); // From common-utils.js
    }
};

FastLaneConfig.resetConfiguration = function () {
    if (!confirm('Reset all settings to default values?')) {
        return;
    }

    const defaults = FAST_LANE_CONFIG_CONSTANTS.DEFAULTS;
    const elements = FAST_LANE_CONFIG_CONSTANTS.ELEMENTS;

    // Reset form fields to defaults
    const setFieldValue = (id, value) => {
        const element = document.getElementById(id);
        if (element) {
            if (element.type === 'checkbox') {
                element.checked = value;
            } else {
                element.value = value;
            }
        }
    };

    setFieldValue(elements.EXECUTION_TIMEOUT, defaults.EXECUTION_TIMEOUT);
    setFieldValue(elements.MAX_SLIPPAGE, defaults.MAX_SLIPPAGE);
    setFieldValue(elements.DEFAULT_POSITION_SIZE, defaults.DEFAULT_POSITION_SIZE);
    setFieldValue(elements.MAX_POSITION_SIZE, defaults.MAX_POSITION_SIZE);
    setFieldValue(elements.GAS_PRICE_MULTIPLIER, defaults.GAS_PRICE_MULTIPLIER);
    setFieldValue(elements.MAX_GAS_PRICE, defaults.MAX_GAS_PRICE);
    setFieldValue(elements.PRIORITY_FEE, defaults.PRIORITY_FEE);
    setFieldValue(elements.ENABLE_MEV_PROTECTION, true);
    setFieldValue(elements.USE_PRIVATE_MEMPOOL, true);
    setFieldValue(elements.ENABLE_SANDWICH_PROTECTION, true);

    // Clear localStorage
    localStorage.removeItem(FAST_LANE_CONFIG_CONSTANTS.STORAGE_KEY);

    // Deselect all trading pairs
    const selectedPairs = document.querySelectorAll(FAST_LANE_CONFIG_CONSTANTS.SELECTORS.TRADING_PAIR_SELECTED);
    selectedPairs.forEach(card => card.classList.remove('selected'));

    // Update all displays
    this.updateConfigurationPreview();
    this.updatePerformanceGauges();
    this.updateSpeedDisplay(defaults.EXECUTION_TIMEOUT);

    showToast('Configuration reset to defaults', 'info'); // From common-utils.js
};

// ============================================================================
// GLOBAL FUNCTION EXPORTS
// ============================================================================

// Export functions for template compatibility
window.resetConfiguration = FastLaneConfig.resetConfiguration.bind(FastLaneConfig);
window.testConfiguration = FastLaneConfig.testConfiguration.bind(FastLaneConfig);

// Export module for global access
window.fastLaneConfig = FastLaneConfig;

// ============================================================================
// INITIALIZATION
// ============================================================================

/**
 * Initialize Fast Lane Configuration when DOM is ready
 */
document.addEventListener('DOMContentLoaded', function () {
    FastLaneConfig.init();
});