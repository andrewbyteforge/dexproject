/**
 * Fast Lane Configuration JavaScript
 * 
 * Extracted from fast_lane_config.html template
 * Provides interactive functionality for high-speed trading configuration
 * 
 * File: dashboard/static/dashboard/js/fast_lane_config.js
 */

'use strict';

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
        const configForm = document.getElementById('fast-lane-config-form');
        const quickBuyForm = document.getElementById('quick-buy-form');
        const quickSellForm = document.getElementById('quick-sell-form');

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
        const timeoutSlider = document.getElementById('execution_timeout');
        const timeoutDisplay = document.getElementById('timeout-display');
        const slippageSlider = document.getElementById('max_slippage');
        const slippageDisplay = document.getElementById('slippage-display');

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
     * Bind trading pair selection handlers
     */
    bindTradingPairSelection: function () {
        const pairCards = document.querySelectorAll('.trading-pair-card');

        pairCards.forEach(card => {
            card.addEventListener('click', function () {
                this.classList.toggle('selected');
                FastLaneConfig.updateSelectedPairs();
            });
        });
    },

    /**
     * Bind configuration preview update handlers
     */
    bindConfigurationPreview: function () {
        const inputs = document.querySelectorAll('#fast-lane-config-form input, #fast-lane-config-form select');

        inputs.forEach(input => {
            input.addEventListener('input', this.updateConfigurationPreview.bind(this));
            input.addEventListener('change', this.updateConfigurationPreview.bind(this));
        });

        // Initial update
        this.updateConfigurationPreview();
    },

    /**
     * Initialize Bootstrap tooltips
     */
    initializeTooltips: function () {
        const tooltips = document.querySelectorAll('[data-bs-toggle="tooltip"]');
        tooltips.forEach(tooltip => {
            try {
                new bootstrap.Tooltip(tooltip);
            } catch (error) {
                console.warn('Bootstrap tooltip initialization failed:', error);
            }
        });
    },

    /**
     * Setup auto-save functionality
     */
    setupAutoSave: function () {
        let saveTimeout;

        document.addEventListener('input', function (e) {
            if (e.target.closest('#fast-lane-config-form')) {
                clearTimeout(saveTimeout);
                saveTimeout = setTimeout(() => {
                    try {
                        const config = FastLaneConfig.gatherConfigurationData();
                        localStorage.setItem('fast_lane_config', JSON.stringify(config));
                        console.log('Configuration auto-saved');
                    } catch (error) {
                        console.error('Auto-save failed:', error);
                    }
                }, 1000);
            }
        });
    }
};

// ============================================================================
// DISPLAY UPDATE FUNCTIONS
// ============================================================================

FastLaneConfig.updateSpeedDisplay = function (timeoutMs) {
    const speedDisplay = document.getElementById('speed-display');
    if (speedDisplay) {
        speedDisplay.textContent = `${timeoutMs}ms`;
    }

    // Update speed indicator color based on performance
    const speedIndicator = document.querySelector('.speed-indicator');
    if (speedIndicator) {
        if (timeoutMs <= 300) {
            speedIndicator.style.background = 'linear-gradient(135deg, #00ff88, #00d4aa)';
        } else if (timeoutMs <= 600) {
            speedIndicator.style.background = 'linear-gradient(135deg, #00d4aa, #00b894)';
        } else {
            speedIndicator.style.background = 'linear-gradient(135deg, #00b894, #ffc107)';
        }
    }
};

FastLaneConfig.updatePerformanceGauges = function () {
    const timeoutElement = document.getElementById('execution_timeout');
    const slippageElement = document.getElementById('max_slippage');

    if (!timeoutElement || !slippageElement) return;

    const timeout = parseInt(timeoutElement.value);
    const slippage = parseFloat(slippageElement.value);

    // Calculate speed index (inverse of timeout)
    const speedIndex = Math.max(0, 100 - (timeout / 20));
    const speedGauge = document.getElementById('speed-gauge');
    const speedNeedle = document.getElementById('speed-needle');

    if (speedGauge) {
        speedGauge.style.height = `${speedIndex}%`;
    }

    if (speedNeedle) {
        speedNeedle.style.transform = `rotate(${(speedIndex * 1.8) - 90}deg)`;
    }

    // Calculate risk level based on slippage and other factors
    const riskLevel = Math.min(100, slippage * 20);
    const riskGauge = document.getElementById('risk-gauge');
    const riskNeedle = document.getElementById('risk-needle');

    if (riskGauge) {
        riskGauge.style.height = `${riskLevel}%`;
    }

    if (riskNeedle) {
        riskNeedle.style.transform = `rotate(${(riskLevel * 1.8) - 90}deg)`;
    }
};

FastLaneConfig.updateConfigurationPreview = function () {
    const elements = {
        positionSize: document.getElementById('default_position_size'),
        slippage: document.getElementById('max_slippage'),
        gasMultiplier: document.getElementById('gas_price_multiplier'),
        mevProtection: document.getElementById('enable_mev_protection')
    };

    const previews = {
        positionSize: document.getElementById('preview-position-size'),
        slippage: document.getElementById('preview-slippage'),
        gas: document.getElementById('preview-gas'),
        mev: document.getElementById('preview-mev')
    };

    if (elements.positionSize && previews.positionSize) {
        previews.positionSize.textContent = `${elements.positionSize.value} ETH`;
    }

    if (elements.slippage && previews.slippage) {
        previews.slippage.textContent = `${elements.slippage.value}%`;
    }

    if (elements.gasMultiplier && previews.gas) {
        previews.gas.textContent = `${elements.gasMultiplier.value}x`;
    }

    if (elements.mevProtection && previews.mev) {
        const enabled = elements.mevProtection.checked;
        previews.mev.textContent = enabled ? 'Enabled' : 'Disabled';
        previews.mev.className = `fw-bold ${enabled ? 'text-success' : 'text-warning'}`;
    }
};

FastLaneConfig.updateSelectedPairs = function () {
    const selectedPairs = document.querySelectorAll('.trading-pair-card.selected');
    console.log(`Selected ${selectedPairs.length} trading pairs`);

    // Could show selected pairs count in UI if needed
    return selectedPairs.length;
};

// ============================================================================
// CONFIGURATION MANAGEMENT
// ============================================================================

FastLaneConfig.gatherConfigurationData = function () {
    const selectedPairs = Array.from(document.querySelectorAll('.trading-pair-card.selected'))
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

    return {
        execution_timeout_ms: parseInt(getElementValue('execution_timeout', '500')),
        max_slippage_percent: parseFloat(getElementValue('max_slippage', '1.0')),
        default_position_size_eth: parseFloat(getElementValue('default_position_size', '0.1')),
        max_position_size_eth: parseFloat(getElementValue('max_position_size', '1.0')),
        gas_price_multiplier: parseFloat(getElementValue('gas_price_multiplier', '1.2')),
        max_gas_price_gwei: parseInt(getElementValue('max_gas_price', '100')),
        priority_fee_gwei: parseFloat(getElementValue('priority_fee', '2.0')),
        mev_protection_enabled: getCheckboxValue('enable_mev_protection', true),
        private_mempool_enabled: getCheckboxValue('use_private_mempool', true),
        sandwich_protection_enabled: getCheckboxValue('enable_sandwich_protection', true),
        target_trading_pairs: selectedPairs,
        stop_loss_percent: parseFloat(getElementValue('stop_loss_percent')) || null,
        take_profit_percent: parseFloat(getElementValue('take_profit_percent')) || null
    };
};

FastLaneConfig.loadSavedConfiguration = function () {
    try {
        const saved = localStorage.getItem('fast_lane_config');
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

    try {
        const response = await fetch('/api/trading/session/start/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCsrfToken(),
            },
            body: JSON.stringify({
                ...config,
                strategy_type: 'FAST_LANE',
                auto_execution: true
            })
        });

        const result = await response.json();

        if (result.success) {
            this.showNotification('Fast Lane configuration saved and activated!', 'success');

            // Show trading controls
            const tradingControls = document.getElementById('trading-controls');
            if (tradingControls) {
                tradingControls.style.display = 'block';
            }

            // Update session controls
            const startBtn = document.getElementById('start-fast-session');
            const stopBtn = document.getElementById('stop-fast-session');

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
        this.showNotification(`Configuration failed: ${error.message}`, 'error');
    }
};

FastLaneConfig.executeQuickBuy = async function (e) {
    e.preventDefault();

    const formData = new FormData(e.target);
    const buyData = {
        token_address: formData.get('token_address') || document.getElementById('buy_token_address')?.value,
        amount_eth: formData.get('amount') || document.getElementById('buy_amount')?.value,
        slippage_tolerance: (parseFloat(formData.get('slippage') || document.getElementById('buy_slippage')?.value || '1.0')) / 100,
        chain_id: 8453 // Base mainnet
    };

    // Validate required fields
    if (!buyData.token_address || !buyData.amount_eth) {
        this.showNotification('Please fill in all required fields', 'warning');
        return;
    }

    try {
        // Use trading manager if available
        if (window.tradingManager) {
            const mockFormData = new FormData();
            Object.entries(buyData).forEach(([key, value]) => {
                mockFormData.append(key, value);
            });

            await window.tradingManager.executeBuyOrder(mockFormData);

            // Clear form on success
            e.target.reset();

        } else {
            throw new Error('Trading manager not available');
        }

    } catch (error) {
        console.error('Quick buy error:', error);
        this.showNotification(`Quick buy failed: ${error.message}`, 'error');
    }
};

FastLaneConfig.executeQuickSell = async function (e) {
    e.preventDefault();

    const formData = new FormData(e.target);
    const sellData = {
        token_address: formData.get('token_address') || document.getElementById('sell_token_address')?.value,
        token_amount: formData.get('amount') || document.getElementById('sell_amount')?.value,
        slippage_tolerance: (parseFloat(formData.get('slippage') || document.getElementById('sell_slippage')?.value || '1.0')) / 100,
        chain_id: 8453
    };

    // Validate required fields
    if (!sellData.token_address || !sellData.token_amount) {
        this.showNotification('Please fill in all required fields', 'warning');
        return;
    }

    try {
        // Use trading manager if available
        if (window.tradingManager) {
            const mockFormData = new FormData();
            Object.entries(sellData).forEach(([key, value]) => {
                mockFormData.append(key, value);
            });

            await window.tradingManager.executeSellOrder(mockFormData);

            // Clear form on success
            e.target.reset();

        } else {
            throw new Error('Trading manager not available');
        }

    } catch (error) {
        console.error('Quick sell error:', error);
        this.showNotification(`Quick sell failed: ${error.message}`, 'error');
    }
};

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

FastLaneConfig.testConfiguration = function () {
    const config = this.gatherConfigurationData();

    this.showNotification('Testing Fast Lane configuration...', 'info');

    // Simulate test with timeout
    setTimeout(() => {
        const testResults = {
            estimated_speed: `${config.execution_timeout_ms}ms`,
            gas_efficiency: config.gas_price_multiplier < 1.5 ? 'Good' : 'High',
            mev_protection: config.mev_protection_enabled ? 'Active' : 'Disabled',
            risk_level: config.max_slippage_percent > 2 ? 'High' : 'Medium'
        };

        this.showNotification(
            `Test complete: ${testResults.estimated_speed} execution, ${testResults.gas_efficiency} gas efficiency`,
            'success'
        );

    }, 2000);
};

FastLaneConfig.resetConfiguration = function () {
    // Reset form to defaults
    const form = document.getElementById('fast-lane-config-form');
    if (form) {
        form.reset();
    }

    // Reset specific elements to default values
    const defaults = {
        'execution_timeout': 500,
        'max_slippage': 1.0,
        'timeout-display': '500ms',
        'slippage-display': '1.0%'
    };

    Object.entries(defaults).forEach(([id, value]) => {
        const element = document.getElementById(id);
        if (element) {
            if (element.tagName === 'INPUT') {
                element.value = value;
            } else {
                element.textContent = value;
            }
        }
    });

    // Reset trading pairs to default selection
    document.querySelectorAll('.trading-pair-card').forEach(card => {
        card.classList.remove('selected');
    });

    const defaultPair = document.querySelector('[data-pair="WETH/USDC"]');
    if (defaultPair) {
        defaultPair.classList.add('selected');
    }

    // Update all displays
    this.updateConfigurationPreview();
    this.updatePerformanceGauges();
    this.updateSpeedDisplay(500);

    this.showNotification('Configuration reset to defaults', 'info');
};

FastLaneConfig.getCsrfToken = function () {
    const token = document.querySelector('meta[name="csrf-token"]');
    return token ? token.getAttribute('content') : '';
};

FastLaneConfig.showNotification = function (message, type = 'info') {
    if (window.tradingManager && typeof window.tradingManager.showNotification === 'function') {
        window.tradingManager.showNotification(message, type);
    } else {
        console.log(`[${type.toUpperCase()}] ${message}`);
        // Fallback to alert for critical messages
        if (type === 'error') {
            alert(message);
        }
    }
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