/**
 * Paper Trading Configuration Page JavaScript - ENHANCED WITH LOGGING
 * 
 * Handles configuration form interactions, bot controls, and risk calculations.
 * ALL configuration changes are logged to the console for debugging and monitoring.
 * 
 * FIXED: Removed duplicate API_ENDPOINTS declaration - uses the one from api-constants.js
 * 
 * Dependencies:
 * - common-utils.js (must be loaded before this file)
 *   - Uses: getCSRFToken(), showToast()
 * - api-constants.js (must be loaded before this file)
 *   - Uses: API_ENDPOINTS (shared constant)
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

// Use API_ENDPOINTS from api-constants.js (already loaded)
// DO NOT redeclare it here!

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

// Friendly field names for logging
const FRIENDLY_FIELD_NAMES = {
    'name': 'Configuration Name',
    'config_name': 'Configuration Name',
    'trading_mode': 'Trading Mode',
    'trading_mode_visual': 'Trading Mode (Visual)',
    'use_fast_lane': 'Fast Lane',
    'use_smart_lane': 'Smart Lane',
    'max_position_size_percent': 'Max Position Size',
    'max_daily_trades': 'Max Daily Trades',
    'confidence_threshold': 'Confidence Threshold',
    'stop_loss_percent': 'Stop Loss',
    'take_profit_percent': 'Take Profit'
};

// ============================================================================
// LOGGING UTILITIES
// ============================================================================

/**
 * Log configuration changes to console with detailed formatting
 * @param {HTMLElement} element - The changed form element
 * @param {boolean} isRealtime - Whether this is a real-time update (input event)
 */
function logConfigurationChange(element, isRealtime = false) {
    const fieldName = element.name || element.id || 'unknown';
    let value = element.value;

    // Special handling for checkboxes
    if (element.type === 'checkbox') {
        value = element.checked ? '✓ ENABLED' : '✗ DISABLED';
    }

    // Special handling for radio buttons
    if (element.type === 'radio') {
        if (!element.checked) {
            return; // Only log the selected radio button
        }
        value = `${value} (selected)`;
    }

    // Format the log message
    const prefix = isRealtime ? '⚡' : '✏️';
    const suffix = isRealtime ? ' [real-time]' : ' [committed]';
    const timestamp = new Date().toLocaleTimeString();

    // Get friendly field name
    const displayName = FRIENDLY_FIELD_NAMES[fieldName] || fieldName.replace(/_/g, ' ').toUpperCase();

    // Add unit suffix for numeric fields
    let unit = '';
    if (fieldName.includes('percent') || fieldName.includes('threshold') || fieldName.includes('size')) {
        if (element.type === 'number' || element.type === 'range') {
            unit = '%';
        }
    }

    console.log(`${prefix} [${timestamp}] ${displayName}: ${value}${unit}${suffix}`);
}

/**
 * Log complete configuration snapshot
 * Shows all current configuration values at once
 */
function logConfigurationSnapshot() {
    console.log('\n' + '═'.repeat(70));
    console.log('📸 CONFIGURATION SNAPSHOT');
    console.log('═'.repeat(70));

    // Get all form values
    const nameField = document.querySelector(`[name="${CONFIG_FIELDS.NAME}"]`);
    const modeSelect = document.getElementById(CONFIG_FIELDS.TRADING_MODE_SELECT);
    const fastLaneField = document.querySelector(`[name="${CONFIG_FIELDS.USE_FAST_LANE}"]`);
    const smartLaneField = document.querySelector(`[name="${CONFIG_FIELDS.USE_SMART_LANE}"]`);
    const positionSizeField = document.querySelector(`[name="${CONFIG_FIELDS.MAX_POSITION_SIZE}"]`);
    const maxTradesField = document.querySelector(`[name="${CONFIG_FIELDS.MAX_DAILY_TRADES}"]`);
    const confidenceField = document.querySelector(`[name="${CONFIG_FIELDS.CONFIDENCE_THRESHOLD}"]`);
    const stopLossField = document.querySelector(`[name="${CONFIG_FIELDS.STOP_LOSS}"]`);
    const takeProfitField = document.querySelector(`[name="${CONFIG_FIELDS.TAKE_PROFIT}"]`);

    console.log(`📝 Name: ${nameField?.value || 'N/A'}`);
    console.log(`🎯 Trading Mode: ${modeSelect?.value || 'N/A'}`);
    console.log(`⚡ Fast Lane: ${fastLaneField?.checked ? '✓ ENABLED' : '✗ DISABLED'}`);
    console.log(`🧠 Smart Lane: ${smartLaneField?.checked ? '✓ ENABLED' : '✗ DISABLED'}`);
    console.log(`💰 Max Position Size: ${positionSizeField?.value || 'N/A'}%`);
    console.log(`📊 Max Daily Trades: ${maxTradesField?.value || 'N/A'}`);
    console.log(`🎲 Confidence Threshold: ${confidenceField?.value || 'N/A'}%`);
    console.log(`🛡️ Stop Loss: ${stopLossField?.value || 'N/A'}%`);
    console.log(`🎯 Take Profit: ${takeProfitField?.value || 'N/A'}%`);
    console.log('═'.repeat(70) + '\n');
}

/**
 * Log risk assessment details
 * @param {number} riskScore - Calculated risk score (0-100)
 * @param {string} riskLevel - Risk level (Low/Medium/High)
 */
function logRiskAssessment(riskScore, riskLevel) {
    const timestamp = new Date().toLocaleTimeString();
    console.log(`📈 [${timestamp}] RISK ASSESSMENT ─────────────────────────`);
    console.log(`   Risk Score: ${riskScore.toFixed(1)}/100`);
    console.log(`   Risk Level: ${riskLevel}`);

    // Color-coded indicator
    const indicator = riskLevel === 'Low' ? '🟢' : riskLevel === 'Medium' ? '🟡' : '🔴';
    console.log(`   Status: ${indicator} ${riskLevel} Risk`);
    console.log(`─────────────────────────────────────────────────────────`);
}

// ============================================================================
// MODE SYNCHRONIZATION
// ============================================================================

/**
 * Sync visual mode selector (radio buttons) with dropdown
 * Ensures both UI elements stay in sync when user changes trading mode
 */
function initializeModeSync() {
    console.log('🔄 Initializing mode synchronization...');

    // Sync radio buttons to dropdown
    document.querySelectorAll(`input[name="${CONFIG_FIELDS.TRADING_MODE_VISUAL}"]`).forEach(radio => {
        radio.addEventListener('change', function () {
            const selectElement = document.getElementById(CONFIG_FIELDS.TRADING_MODE_SELECT);
            if (selectElement) {
                selectElement.value = this.value;
                console.log(`🔄 [MODE SYNC] Radio → Dropdown: ${this.value}`);
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
            console.log(`🔄 [MODE SYNC] Dropdown → Radio: ${this.value}`);
            updateRiskIndicator();
        });
    }

    console.log('✅ Mode synchronization initialized');
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
        const oldValue = element.value;
        element.value = value;

        // 🔍 LOGGING: Log slider change with field name and value
        const fieldName = element.name || inputId;
        const displayName = FRIENDLY_FIELD_NAMES[fieldName] || fieldName.replace(/_/g, ' ').toUpperCase();
        const timestamp = new Date().toLocaleTimeString();

        // Determine unit
        let unit = '';
        if (fieldName.includes('percent') || fieldName.includes('threshold') || fieldName.includes('size')) {
            unit = '%';
        }

        console.log(`🎚️ [${timestamp}] SLIDER: ${displayName} = ${value}${unit} (was ${oldValue}${unit})`);

        updateRiskIndicator();
    } else {
        console.warn(`⚠️ Range input element with ID '${inputId}' not found`);
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
        console.warn('⚠️ Risk indicator: Some form elements not found');
        return;
    }

    // Get values
    const mode = modeElement.value;
    const positionSize = parseFloat(positionSizeElement.value) || 0;
    const stopLoss = parseFloat(stopLossElement.value) || 0;
    const confidence = parseFloat(confidenceElement.value) || 0;

    // Calculate risk score (0-100)
    let riskScore = 0;

    // Mode contribution (0-30 points)
    if (mode === 'CONSERVATIVE') riskScore += 0;
    else if (mode === 'MODERATE') riskScore += 15;
    else if (mode === 'AGGRESSIVE') riskScore += 30;

    // Position size contribution (0-30 points)
    riskScore += Math.min(30, positionSize);

    // Stop loss contribution (0-20 points, inverse - higher stop loss = lower risk)
    riskScore += Math.max(0, 20 - (stopLoss * 2));

    // Confidence contribution (0-20 points, inverse - higher confidence = lower risk)
    riskScore += Math.max(0, 20 - (confidence / 5));

    // Determine risk level
    let riskLevel = '';
    if (riskScore < RISK_THRESHOLDS.LOW) {
        riskLevel = 'Low';
    } else if (riskScore < RISK_THRESHOLDS.MEDIUM) {
        riskLevel = 'Medium';
    } else {
        riskLevel = 'High';
    }

    // Update UI elements
    const icon = document.querySelector('.risk-icon');
    const levelText = document.getElementById('risk-level-text');  // Changed to getElementById
    const description = document.getElementById('risk-description');  // Changed to getElementById

    if (!icon || !levelText || !description) {
        console.warn('⚠️ Risk indicator UI elements not found');
        return;
    }

    // Clear existing classes
    icon.classList.remove('bi-shield-check', 'bi-shield-exclamation', 'bi-shield-x', 'risk-low', 'risk-medium', 'risk-high');
    levelText.classList.remove('text-success', 'text-warning', 'text-danger');

    // Apply new classes based on risk level
    if (riskLevel === 'Low') {
        icon.classList.add('bi-shield-check', 'risk-low');
        levelText.textContent = 'Low';
        levelText.className = 'text-success';
        description.textContent = 'Conservative settings with good risk management';
    } else if (riskLevel === 'Medium') {
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

    // 🔍 LOGGING: Log risk assessment
    logRiskAssessment(riskScore, riskLevel);
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
        console.error('❌ Configuration form not found');
        return;
    }

    console.log('💾 Saving configuration as new...');

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

    console.log(`💾 Saving configuration as: "${nameField?.value}"`);
    logConfigurationSnapshot();
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
        console.log('❌ Bot start cancelled by user');
        return;
    }

    console.log('🚀 Starting paper trading bot...');
    logConfigurationSnapshot();

    try {
        // Get API endpoint from api-constants.js
        const botStartUrl = API_ENDPOINTS?.paperTrading?.BOT_START || '/paper-trading/api/bot/start/';

        const response = await fetch(botStartUrl, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCSRFToken(), // From common-utils.js
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (response.ok) {
            console.log('✅ Bot started successfully');
            showToast('Bot started successfully!', 'success'); // From common-utils.js

            // Reload page after short delay to show updated status
            setTimeout(() => location.reload(), 1500);
        } else {
            console.error('❌ Failed to start bot:', data.error);
            showToast(data.error || 'Failed to start bot', 'danger'); // From common-utils.js
        }
    } catch (error) {
        console.error('❌ Error starting bot:', error);
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
        console.log('❌ Bot stop cancelled by user');
        return;
    }

    console.log('🛑 Stopping paper trading bot...');

    try {
        // Get API endpoint from api-constants.js
        const botStopUrl = API_ENDPOINTS?.paperTrading?.BOT_STOP || '/paper-trading/api/bot/stop/';

        const response = await fetch(botStopUrl, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCSRFToken(), // From common-utils.js
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (response.ok) {
            console.log('✅ Bot stopped successfully');
            showToast('Bot stopped successfully', 'success'); // From common-utils.js

            // Reload page after short delay to show updated status
            setTimeout(() => location.reload(), 1500);
        } else {
            console.error('❌ Failed to stop bot:', data.error);
            showToast(data.error || 'Failed to stop bot', 'danger'); // From common-utils.js
        }
    } catch (error) {
        console.error('❌ Error stopping bot:', error);
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
        console.log('❌ Form reset cancelled by user');
        return;
    }

    console.log('🔄 Resetting form to default values...');

    // Reset all fields to defaults
    const nameField = document.querySelector(`[name="${CONFIG_FIELDS.NAME}"]`);
    if (nameField) {
        nameField.value = DEFAULT_VALUES.NAME;
        console.log(`   Reset: Configuration Name = "${DEFAULT_VALUES.NAME}"`);
    }

    const modeSelect = document.getElementById(CONFIG_FIELDS.TRADING_MODE_SELECT);
    if (modeSelect) {
        modeSelect.value = DEFAULT_VALUES.TRADING_MODE;
        console.log(`   Reset: Trading Mode = ${DEFAULT_VALUES.TRADING_MODE}`);
    }

    const modeRadio = document.querySelector(`[name="${CONFIG_FIELDS.TRADING_MODE_VISUAL}"][value="${DEFAULT_VALUES.TRADING_MODE}"]`);
    if (modeRadio) {
        modeRadio.checked = true;
    }

    const fastLaneField = document.querySelector(`[name="${CONFIG_FIELDS.USE_FAST_LANE}"]`);
    if (fastLaneField) {
        fastLaneField.checked = DEFAULT_VALUES.USE_FAST_LANE;
        console.log(`   Reset: Fast Lane = ${DEFAULT_VALUES.USE_FAST_LANE ? 'ENABLED' : 'DISABLED'}`);
    }

    const smartLaneField = document.querySelector(`[name="${CONFIG_FIELDS.USE_SMART_LANE}"]`);
    if (smartLaneField) {
        smartLaneField.checked = DEFAULT_VALUES.USE_SMART_LANE;
        console.log(`   Reset: Smart Lane = ${DEFAULT_VALUES.USE_SMART_LANE ? 'ENABLED' : 'DISABLED'}`);
    }

    const positionSizeField = document.querySelector(`[name="${CONFIG_FIELDS.MAX_POSITION_SIZE}"]`);
    if (positionSizeField) {
        positionSizeField.value = DEFAULT_VALUES.MAX_POSITION_SIZE;
        console.log(`   Reset: Max Position Size = ${DEFAULT_VALUES.MAX_POSITION_SIZE}%`);
    }

    const maxTradesField = document.querySelector(`[name="${CONFIG_FIELDS.MAX_DAILY_TRADES}"]`);
    if (maxTradesField) {
        maxTradesField.value = DEFAULT_VALUES.MAX_DAILY_TRADES;
        console.log(`   Reset: Max Daily Trades = ${DEFAULT_VALUES.MAX_DAILY_TRADES}`);
    }

    const confidenceField = document.querySelector(`[name="${CONFIG_FIELDS.CONFIDENCE_THRESHOLD}"]`);
    if (confidenceField) {
        confidenceField.value = DEFAULT_VALUES.CONFIDENCE_THRESHOLD;
        console.log(`   Reset: Confidence Threshold = ${DEFAULT_VALUES.CONFIDENCE_THRESHOLD}%`);
    }

    const stopLossField = document.querySelector(`[name="${CONFIG_FIELDS.STOP_LOSS}"]`);
    if (stopLossField) {
        stopLossField.value = DEFAULT_VALUES.STOP_LOSS;
        console.log(`   Reset: Stop Loss = ${DEFAULT_VALUES.STOP_LOSS}%`);
    }

    const takeProfitField = document.querySelector(`[name="${CONFIG_FIELDS.TAKE_PROFIT}"]`);
    if (takeProfitField) {
        takeProfitField.value = DEFAULT_VALUES.TAKE_PROFIT;
        console.log(`   Reset: Take Profit = ${DEFAULT_VALUES.TAKE_PROFIT}%`);
    }

    // Update risk indicator with new values
    updateRiskIndicator();

    console.log('✅ Form reset completed');
    logConfigurationSnapshot();

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
    console.log('\n' + '═'.repeat(70));
    console.log('🚀 PAPER TRADING CONFIGURATION PAGE - INITIALIZING');
    console.log('═'.repeat(70));
    console.log('📅 Date:', new Date().toLocaleString());
    console.log('🔍 Logging: ENABLED (All configuration changes will be logged)');
    console.log('═'.repeat(70) + '\n');

    // Initialize mode synchronization
    initializeModeSync();

    // Initial risk indicator calculation
    console.log('📊 Calculating initial risk assessment...');
    updateRiskIndicator();

    // Log initial configuration state
    logConfigurationSnapshot();

    // Add event listeners for ALL form elements with logging
    console.log('🎯 Setting up event listeners for configuration changes...');

    let listenerCount = 0;
    document.querySelectorAll('input, select').forEach(element => {
        const fieldName = element.name || element.id || 'unknown';
        const displayName = FRIENDLY_FIELD_NAMES[fieldName] || fieldName;

        // Log on change (when user finishes adjusting)
        element.addEventListener('change', function () {
            logConfigurationChange(this, false);
            updateRiskIndicator();
        });

        // Log on input (real-time as user types/slides)
        element.addEventListener('input', function () {
            logConfigurationChange(this, true);
            // Only update risk indicator, don't log it again to avoid spam
        });

        listenerCount++;
    });

    console.log(`✅ Event listeners attached to ${listenerCount} form elements`);
    console.log('✅ Paper trading configuration page initialized successfully');
    console.log('🎯 Ready to track configuration changes!\n');
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

// Export logging functions for debugging
window.logConfigurationSnapshot = logConfigurationSnapshot;

// Log that the script has loaded
console.log('📦 paper_trading_configuration.js loaded successfully');