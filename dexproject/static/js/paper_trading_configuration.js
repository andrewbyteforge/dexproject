/**
 * Paper Trading Configuration Page JavaScript
 * Handles configuration form interactions, bot controls, and risk calculations
 */

/**
 * Sync visual mode selector with dropdown
 */
document.querySelectorAll('input[name="trading_mode_visual"]').forEach(radio => {
    radio.addEventListener('change', function () {
        document.getElementById('trading-mode-select').value = this.value;
        updateRiskIndicator();
    });
});

document.getElementById('trading-mode-select').addEventListener('change', function () {
    const radios = document.querySelectorAll('input[name="trading_mode_visual"]');
    radios.forEach(radio => {
        if (radio.value === this.value) {
            radio.checked = true;
        }
    });
    updateRiskIndicator();
});

/**
 * Update range input display value
 */
function updateRangeValue(inputId, value) {
    document.getElementById(inputId).value = value;
    updateRiskIndicator();
}

/**
 * Calculate and update risk indicator
 */
function updateRiskIndicator() {
    const mode = document.getElementById('trading-mode-select').value;
    const positionSize = parseFloat(document.querySelector('[name="max_position_size_percent"]').value);
    const stopLoss = parseFloat(document.querySelector('[name="stop_loss_percent"]').value);
    const confidence = parseFloat(document.querySelector('[name="confidence_threshold"]').value);

    let riskScore = 0;

    // Calculate risk based on parameters
    if (mode === 'AGGRESSIVE') riskScore += 30;
    else if (mode === 'MODERATE') riskScore += 15;

    if (positionSize > 30) riskScore += 20;
    else if (positionSize > 15) riskScore += 10;

    if (stopLoss > 10) riskScore += 20;
    else if (stopLoss > 5) riskScore += 10;

    if (confidence < 50) riskScore += 20;
    else if (confidence < 70) riskScore += 10;

    const indicator = document.getElementById('risk-indicator');
    const icon = indicator.querySelector('.risk-icon');
    const levelText = document.getElementById('risk-level-text');
    const description = document.getElementById('risk-description');

    // Update display based on risk score
    icon.className = 'bi risk-icon';

    if (riskScore < 30) {
        icon.classList.add('bi-shield-check', 'risk-low');
        levelText.textContent = 'Low';
        levelText.className = 'text-success';
        description.textContent = 'Conservative settings with good risk management';
    } else if (riskScore < 60) {
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
}

/**
 * Save configuration as new
 */
function saveAsNew() {
    // Add a hidden field to indicate saving as new
    const form = document.getElementById('config-form');
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = 'save_as_new';
    input.value = 'true';
    form.appendChild(input);

    // Update the name field to avoid duplicates
    const nameField = document.querySelector('[name="name"]');
    if (nameField.value && !nameField.value.endsWith(' (Copy)')) {
        nameField.value = nameField.value + ' (Copy)';
    }

    form.submit();
}

/**
 * Start paper trading bot
 */
async function startBot() {
    if (!confirm('Start the paper trading bot with current configuration?')) {
        return;
    }

    try {
        const response = await fetch('/paper-trading/api/bot/start/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCSRFToken(),
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (response.ok) {
            showToast('Bot started successfully!', 'success');
            setTimeout(() => location.reload(), 1500);
        } else {
            showToast(data.error || 'Failed to start bot', 'danger');
        }
    } catch (error) {
        console.error('Error starting bot:', error);
        showToast('Error starting bot', 'danger');
    }
}

/**
 * Stop paper trading bot
 */
async function stopBot() {
    if (!confirm('Stop the paper trading bot?')) {
        return;
    }

    try {
        const response = await fetch('/paper-trading/api/bot/stop/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCSRFToken(),
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (response.ok) {
            showToast('Bot stopped successfully', 'success');
            setTimeout(() => location.reload(), 1500);
        } else {
            showToast(data.error || 'Failed to stop bot', 'danger');
        }
    } catch (error) {
        console.error('Error stopping bot:', error);
        showToast('Error stopping bot', 'danger');
    }
}

/**
 * Reset form to default values
 */
function resetForm() {
    if (!confirm('Reset all settings to default values?')) {
        return;
    }

    document.querySelector('[name="name"]').value = 'My Strategy';
    document.getElementById('trading-mode-select').value = 'MODERATE';
    document.querySelector('[name="trading_mode_visual"][value="MODERATE"]').checked = true;
    document.querySelector('[name="use_fast_lane"]').checked = true;
    document.querySelector('[name="use_smart_lane"]').checked = false;
    document.querySelector('[name="max_position_size_percent"]').value = 25;
    document.querySelector('[name="max_daily_trades"]').value = 20;
    document.querySelector('[name="confidence_threshold"]').value = 60;
    document.querySelector('[name="stop_loss_percent"]').value = 5;
    document.querySelector('[name="take_profit_percent"]').value = 10;

    updateRiskIndicator();
    showToast('Form reset to default values', 'info');
}

// Initialize risk indicator on page load
document.addEventListener('DOMContentLoaded', function () {
    updateRiskIndicator();

    // Update risk indicator when any parameter changes
    document.querySelectorAll('input, select').forEach(element => {
        element.addEventListener('change', updateRiskIndicator);
        element.addEventListener('input', updateRiskIndicator);
    });
});