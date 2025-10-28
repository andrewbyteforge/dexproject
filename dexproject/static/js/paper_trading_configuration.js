/**
 * Paper Trading Configuration Page JavaScript
 * 
 * Handles configuration form interactions, bot controls, and risk calculations.
 * 
 * Dependencies:
 * - common-utils.js (must be loaded before this file)
 *   - Uses: getCSRFToken(), showToast()
 * 
 * File: dexproject/static/js/paper_trading_configuration.js
 */

'use strict';

// ============================================================================
// FORM FIELD CONSTANTS
// ============================================================================

const CONFIG_FIELDS = {
    TRADING_MODE_VISUAL: 'trading_mode_visual',
    TRADING_MODE_SELECT: 'trading-mode-select',
    NAME: 'name',
    USE_FAST_LANE: 'use_fast_lane',
    USE_SMART_LANE: 'use_smart_lane',
    MAX_POSITION_SIZE: 'max_position_size_percent',
    MAX_DAILY_TRADES: 'max_daily_trades',
    CONFIDENCE_THRESHOLD: 'confidence_threshold',
    STOP_LOSS: 'stop_loss_percent',
    TAKE_PROFIT: 'take_profit_percent',
    SAVE_AS_NEW: 'save_as_new'
};

const API_ENDPOINTS = {
    BOT_START: '/paper-trading/api/bot/start/',
    BOT_STOP: '/paper-trading/api/bot/stop/'
};

const RISK_THRESHOLDS = {
    LOW: 30,
    MEDIUM: 60
};

const DEFAULT_VALUES = {
    NAME: 'My Strategy',
    TRADING_MODE: 'MODERATE',
    USE_FAST_LANE: true,
    USE_SMART_LANE: false,
    MAX_POSITION_SIZE: 25,
    MAX_DAILY_TRADES: 20,
    CONFIDENCE_THRESHOLD: 60,
    STOP_LOSS: 5,
    TAKE_PROFIT: 10
};

// ============================================================================
// MODE SYNCHRONIZATION
// ============================================================================

/**
 * Sync visual mode selector (radio buttons) with dropdown
 * Ensures both UI elements stay in sync when user changes trading mode
 */
function initializeModeSync() {
    // Sync radio buttons to dropdown
    document.querySelectorAll(`input[name="${CONFIG_FIELDS.TRADING_MODE_VISUAL}"]`).forEach(radio => {
        radio.addEventListener('change', function () {
            const selectElement = document.getElementById(CONFIG_FIELDS.TRADING_MODE_SELECT);
            if (selectElement) {
                selectElement.value = this.value;
                updateRiskIndicator();
            }
        });
    });

    // Sync dropdown to radio buttons
    const selectElement = document.getElementById(CONFIG_FIELDS.TRADING_MODE_SELECT);
    if (selectElement) {
        selectElement.addEventListener('change', function () {
            const radios = document.querySelectorAll(`input[name="${CONFIG_FIELDS.TRADING_MODE_VISUAL}"]`);
            radios.forEach(radio => {
                if (radio.value === this.value) {
                    radio.checked = true;
                }
            });
            updateRiskIndicator();
        });
    }
}

// ============================================================================
// RANGE INPUT UTILITIES
// ============================================================================

/**
 * Update range input display value
 * Called when range sliders are moved
 * 
 * @param {string} inputId - ID of the input element to update
 * @param {number} value - New value for the input
 */
function updateRangeValue(inputId, value) {
    const element = document.getElementById(inputId);
    if (element) {
        element.value = value;
        updateRiskIndicator();
    } else {
        console.warn(`Range input element with ID '${inputId}' not found`);
    }
}

// ============================================================================
// RISK CALCULATION
// ============================================================================

/**
 * Calculate and update risk indicator
 * Analyzes trading parameters to determine risk level (Low/Medium/High)
 */
function updateRiskIndicator() {
    // Get form values
    const modeElement = document.getElementById(CONFIG_FIELDS.TRADING_MODE_SELECT);
    const positionSizeElement = document.querySelector(`[name="${CONFIG_FIELDS.MAX_POSITION_SIZE}"]`);
    const stopLossElement = document.querySelector(`[name="${CONFIG_FIELDS.STOP_LOSS}"]`);
    const confidenceElement = document.querySelector(`[name="${CONFIG_FIELDS.CONFIDENCE_THRESHOLD}"]`);

    // Validate elements exist
    if (!modeElement || !positionSizeElement || !stopLossElement || !confidenceElement) {
        console.warn('Risk indicator: Required form elements not found');
        return;
    }

    const mode = modeElement.value;
    const positionSize = parseFloat(positionSizeElement.value);
    const stopLoss = parseFloat(stopLossElement.value);
    const confidence = parseFloat(confidenceElement.value);

    let riskScore = 0;

    // Calculate risk based on trading mode
    if (mode === 'AGGRESSIVE') {
        riskScore += 30;
    } else if (mode === 'MODERATE') {
        riskScore += 15;
    }
    // CONSERVATIVE adds 0

    // Calculate risk based on position size
    if (positionSize > 30) {
        riskScore += 20;
    } else if (positionSize > 15) {
        riskScore += 10;
    }

    // Calculate risk based on stop loss
    if (stopLoss > 10) {
        riskScore += 20;
    } else if (stopLoss > 5) {
        riskScore += 10;
    }

    // Calculate risk based on confidence threshold (lower = riskier)
    if (confidence < 50) {
        riskScore += 20;
    } else if (confidence < 70) {
        riskScore += 10;
    }

    // Update UI elements
    const indicator = document.getElementById('risk-indicator');
    const icon = indicator?.querySelector('.risk-icon');
    const levelText = document.getElementById('risk-level-text');
    const description = document.getElementById('risk-description');

    if (!indicator || !icon || !levelText || !description) {
        console.warn('Risk indicator: UI elements not found');
        return;
    }

    // Reset icon classes
    icon.className = 'bi risk-icon';

    // Apply risk level styling
    if (riskScore < RISK_THRESHOLDS.LOW) {
        icon.classList.add('bi-shield-check', 'risk-low');
        levelText.textContent = 'Low';
        levelText.className = 'text-success';
        description.textContent = 'Conservative settings with good risk management';
    } else if (riskScore < RISK_THRESHOLDS.MEDIUM) {
        icon.classList.add('bi-shield-exclamation', 'risk-medium');
        levelText.textContent = 'Medium';
        levelText.className = 'text-warning';
        description.textContent = 'Balanced approach with moderate risk exposure';
    } else {
        icon.classList.add('bi-shield-x', 'risk-high');
        levelText.textContent = 'High';
        levelText.className = 'text-danger';
        description.textContent = 'Aggressive settings - higher potential returns and losses';
    }

    console.log(`Risk assessment: Score=${riskScore}, Level=${levelText.textContent}`);
}

// ============================================================================
// CONFIGURATION MANAGEMENT
// ============================================================================

/**
 * Save configuration as new (duplicate current config)
 * Creates a copy of the current configuration with "(Copy)" suffix
 */
function saveAsNew() {
    const form = document.getElementById('config-form');
    if (!form) {
        console.error('Configuration form not found');
        return;
    }

    // Add hidden field to indicate saving as new
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = CONFIG_FIELDS.SAVE_AS_NEW;
    input.value = 'true';
    form.appendChild(input);

    // Update the name field to avoid duplicates
    const nameField = document.querySelector(`[name="${CONFIG_FIELDS.NAME}"]`);
    if (nameField && nameField.value && !nameField.value.endsWith(' (Copy)')) {
        nameField.value = nameField.value + ' (Copy)';
    }

    console.log('Saving configuration as new:', nameField?.value);
    form.submit();
}

// ============================================================================
// BOT CONTROL FUNCTIONS
// ============================================================================

/**
 * Start paper trading bot
 * Sends API request to start the bot with current configuration
 */
async function startBot() {
    // Confirm action
    if (!confirm('Start the paper trading bot with current configuration?')) {
        return;
    }

    console.log('Starting paper trading bot...');

    try {
        const response = await fetch(API_ENDPOINTS.BOT_START, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCSRFToken(), // From common-utils.js
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (response.ok) {
            console.log('Bot started successfully');
            showToast('Bot started successfully!', 'success'); // From common-utils.js

            // Reload page after short delay to show updated status
            setTimeout(() => location.reload(), 1500);
        } else {
            console.error('Failed to start bot:', data.error);
            showToast(data.error || 'Failed to start bot', 'danger'); // From common-utils.js
        }
    } catch (error) {
        console.error('Error starting bot:', error);
        showToast('Error starting bot', 'danger'); // From common-utils.js
    }
}

/**
 * Stop paper trading bot
 * Sends API request to stop the currently running bot
 */
async function stopBot() {
    // Confirm action
    if (!confirm('Stop the paper trading bot?')) {
        return;
    }

    console.log('Stopping paper trading bot...');

    try {
        const response = await fetch(API_ENDPOINTS.BOT_STOP, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCSRFToken(), // From common-utils.js
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (response.ok) {
            console.log('Bot stopped successfully');
            showToast('Bot stopped successfully', 'success'); // From common-utils.js

            // Reload page after short delay to show updated status
            setTimeout(() => location.reload(), 1500);
        } else {
            console.error('Failed to stop bot:', data.error);
            showToast(data.error || 'Failed to stop bot', 'danger'); // From common-utils.js
        }
    } catch (error) {
        console.error('Error stopping bot:', error);
        showToast('Error stopping bot', 'danger'); // From common-utils.js
    }
}

// ============================================================================
// FORM RESET
// ============================================================================

/**
 * Reset form to default values
 * Restores all configuration fields to their default settings
 */
function resetForm() {
    // Confirm action
    if (!confirm('Reset all settings to default values?')) {
        return;
    }

    console.log('Resetting form to default values...');

    // Reset all fields to defaults
    const nameField = document.querySelector(`[name="${CONFIG_FIELDS.NAME}"]`);
    if (nameField) nameField.value = DEFAULT_VALUES.NAME;

    const modeSelect = document.getElementById(CONFIG_FIELDS.TRADING_MODE_SELECT);
    if (modeSelect) modeSelect.value = DEFAULT_VALUES.TRADING_MODE;

    const modeRadio = document.querySelector(`[name="${CONFIG_FIELDS.TRADING_MODE_VISUAL}"][value="${DEFAULT_VALUES.TRADING_MODE}"]`);
    if (modeRadio) modeRadio.checked = true;

    const fastLaneField = document.querySelector(`[name="${CONFIG_FIELDS.USE_FAST_LANE}"]`);
    if (fastLaneField) fastLaneField.checked = DEFAULT_VALUES.USE_FAST_LANE;

    const smartLaneField = document.querySelector(`[name="${CONFIG_FIELDS.USE_SMART_LANE}"]`);
    if (smartLaneField) smartLaneField.checked = DEFAULT_VALUES.USE_SMART_LANE;

    const positionSizeField = document.querySelector(`[name="${CONFIG_FIELDS.MAX_POSITION_SIZE}"]`);
    if (positionSizeField) positionSizeField.value = DEFAULT_VALUES.MAX_POSITION_SIZE;

    const maxTradesField = document.querySelector(`[name="${CONFIG_FIELDS.MAX_DAILY_TRADES}"]`);
    if (maxTradesField) maxTradesField.value = DEFAULT_VALUES.MAX_DAILY_TRADES;

    const confidenceField = document.querySelector(`[name="${CONFIG_FIELDS.CONFIDENCE_THRESHOLD}"]`);
    if (confidenceField) confidenceField.value = DEFAULT_VALUES.CONFIDENCE_THRESHOLD;

    const stopLossField = document.querySelector(`[name="${CONFIG_FIELDS.STOP_LOSS}"]`);
    if (stopLossField) stopLossField.value = DEFAULT_VALUES.STOP_LOSS;

    const takeProfitField = document.querySelector(`[name="${CONFIG_FIELDS.TAKE_PROFIT}"]`);
    if (takeProfitField) takeProfitField.value = DEFAULT_VALUES.TAKE_PROFIT;

    // Update risk indicator with new values
    updateRiskIndicator();

    // Show confirmation
    showToast('Form reset to default values', 'info'); // From common-utils.js
}

// ============================================================================
// INITIALIZATION
// ============================================================================

/**
 * Initialize configuration page
 * Sets up event listeners and performs initial risk assessment
 */
function initializeConfigPage() {
    console.log('Initializing paper trading configuration page...');

    // Initialize mode synchronization
    initializeModeSync();

    // Initial risk indicator calculation
    updateRiskIndicator();

    // Update risk indicator when any parameter changes
    document.querySelectorAll('input, select').forEach(element => {
        element.addEventListener('change', updateRiskIndicator);
        element.addEventListener('input', updateRiskIndicator);
    });

    console.log('Paper trading configuration page initialized successfully');
}

// Auto-initialize when DOM is ready
document.addEventListener('DOMContentLoaded', initializeConfigPage);

// ============================================================================
// GLOBAL EXPORTS
// ============================================================================

// Export functions for template usage
window.updateRangeValue = updateRangeValue;
window.startBot = startBot;
window.stopBot = stopBot;
window.saveAsNew = saveAsNew;
window.resetForm = resetForm;