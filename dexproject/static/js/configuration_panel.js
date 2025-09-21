/**
 * Configuration Panel JavaScript
 * 
 * Handles form validation, real-time preview, risk indicators,
 * and advanced configuration options for Fast Lane and Smart Lane modes
 * 
 * File: dexproject/static/js/configuration_panel.js
 */

// ============================================================================
// GLOBAL VARIABLES AND STATE
// ============================================================================

let configPanelInitialized = false;
let riskIndicatorTimeout = null;
let validationRules = {};
let currentMode = null;

// ============================================================================
// PAGE INITIALIZATION
// ============================================================================

/**
 * Initialize configuration panel when DOM is ready
 */
document.addEventListener('DOMContentLoaded', function () {
    if (configPanelInitialized) return;

    console.log('🔧 Configuration panel initializing...');

    // Detect current mode from page content
    detectConfigurationMode();

    // Initialize Bootstrap tooltips if available
    initializeTooltips();

    // Set up risk level indicator highlighting
    setupRiskLevelIndicators();

    // Set up trailing stop toggle functionality
    setupTrailingStopToggle();

    // Set up form validation
    setupFormValidation();

    // Set up real-time configuration preview
    setupConfigurationPreview();

    // Set up Smart Lane specific features
    if (currentMode === 'smart_lane') {
        setupSmartLaneFeatures();
    }

    // Set up Fast Lane specific features
    if (currentMode === 'fast_lane') {
        setupFastLaneFeatures();
    }

    configPanelInitialized = true;
    console.log('✅ Configuration panel initialized successfully');
});

/**
 * Detect whether we're in Fast Lane or Smart Lane mode
 */
function detectConfigurationMode() {
    const modeHeader = document.querySelector('.mode-header');
    if (modeHeader) {
        if (modeHeader.classList.contains('fast-lane')) {
            currentMode = 'fast_lane';
        } else if (modeHeader.classList.contains('smart-lane')) {
            currentMode = 'smart_lane';
        }
    }

    // Fallback detection from URL or page title
    if (!currentMode) {
        const url = window.location.pathname;
        const title = document.title.toLowerCase();

        if (url.includes('fast') || title.includes('fast')) {
            currentMode = 'fast_lane';
        } else if (url.includes('smart') || title.includes('smart')) {
            currentMode = 'smart_lane';
        }
    }

    console.log(`🎯 Detected mode: ${currentMode || 'unknown'}`);
}

// ============================================================================
// TOOLTIP INITIALIZATION
// ============================================================================

/**
 * Initialize Bootstrap tooltips if available
 */
function initializeTooltips() {
    if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip) {
        const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
        const tooltipList = Array.from(tooltipTriggerList).map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });

        console.log(`💡 Initialized ${tooltipList.length} tooltips`);
    }
}

// ============================================================================
// RISK LEVEL INDICATORS
// ============================================================================

/**
 * Set up risk level indicator highlighting and interaction
 */
function setupRiskLevelIndicators() {
    const riskSelect = document.getElementById('risk_level');
    const riskIndicators = document.querySelectorAll('.risk-indicator');

    if (!riskSelect || riskIndicators.length === 0) return;

    /**
     * Update risk indicator visual state
     */
    function updateRiskIndicators() {
        const selectedRisk = riskSelect.value.toLowerCase();

        // Clear previous timeout
        if (riskIndicatorTimeout) {
            clearTimeout(riskIndicatorTimeout);
        }

        // Reset all indicators
        riskIndicators.forEach(indicator => {
            indicator.style.opacity = '0.5';
            indicator.style.transform = 'scale(0.95)';
            indicator.classList.remove('pulse');
        });

        // Highlight active indicator
        const activeIndicator = document.querySelector(`.risk-${selectedRisk}`);
        if (activeIndicator) {
            activeIndicator.style.opacity = '1';
            activeIndicator.style.transform = 'scale(1.05)';
            activeIndicator.classList.add('pulse');

            // Remove pulse animation after 2 seconds
            riskIndicatorTimeout = setTimeout(() => {
                activeIndicator.classList.remove('pulse');
            }, 2000);
        }

        // Update form validation based on risk level
        updateValidationRules(selectedRisk);
    }

    // Set up event listeners
    riskSelect.addEventListener('change', updateRiskIndicators);

    // Make indicators clickable
    riskIndicators.forEach(indicator => {
        indicator.addEventListener('click', function () {
            const riskLevel = this.classList.contains('risk-low') ? 'LOW' :
                this.classList.contains('risk-medium') ? 'MEDIUM' :
                    this.classList.contains('risk-high') ? 'HIGH' : '';

            if (riskLevel) {
                riskSelect.value = riskLevel;
                updateRiskIndicators();
                riskSelect.dispatchEvent(new Event('change'));
            }
        });
    });

    // Initialize on page load
    updateRiskIndicators();
}

/**
 * Update validation rules based on risk level
 * @param {string} riskLevel - Selected risk level (low, medium, high)
 */
function updateValidationRules(riskLevel) {
    const positionSizeInput = document.getElementById('position_size');
    const slippageInput = document.getElementById('slippage_tolerance');

    if (!positionSizeInput || !slippageInput) return;

    // Adjust limits based on risk level
    switch (riskLevel) {
        case 'low':
            positionSizeInput.max = '1000';
            slippageInput.max = '2.0';
            break;
        case 'medium':
            positionSizeInput.max = '5000';
            slippageInput.max = '3.0';
            break;
        case 'high':
            positionSizeInput.max = '10000';
            slippageInput.max = '5.0';
            break;
    }

    // Visual feedback for risk level
    const helpTexts = document.querySelectorAll('.help-text');
    helpTexts.forEach(text => {
        if (text.textContent.includes('position') || text.textContent.includes('slippage')) {
            text.style.color = riskLevel === 'high' ? '#ff6b6b' :
                riskLevel === 'medium' ? '#ffc107' : '#28a745';
        }
    });
}

// ============================================================================
// TRAILING STOP FUNCTIONALITY
// ============================================================================

/**
 * Set up trailing stop toggle functionality
 */
function setupTrailingStopToggle() {
    const trailingStopCheckbox = document.getElementById('enable_trailing_stop');
    const trailingStopDistance = document.getElementById('trailing-stop-distance');

    if (!trailingStopCheckbox || !trailingStopDistance) return;

    function toggleTrailingStopDistance() {
        if (trailingStopCheckbox.checked) {
            trailingStopDistance.style.display = 'block';
            trailingStopDistance.classList.add('slide-down');

            // Make the field required when visible
            const distanceInput = document.getElementById('trailing_stop_distance');
            if (distanceInput) {
                distanceInput.required = true;
            }
        } else {
            trailingStopDistance.style.display = 'none';
            trailingStopDistance.classList.remove('slide-down');

            // Remove required attribute when hidden
            const distanceInput = document.getElementById('trailing_stop_distance');
            if (distanceInput) {
                distanceInput.required = false;
            }
        }
    }

    trailingStopCheckbox.addEventListener('change', toggleTrailingStopDistance);

    // Initialize state
    toggleTrailingStopDistance();
}

// ============================================================================
// FORM VALIDATION
// ============================================================================

/**
 * Set up comprehensive form validation
 */
function setupFormValidation() {
    const form = document.getElementById('configForm');
    if (!form) return;

    // Define validation rules
    validationRules = {
        config_name: {
            required: true,
            minLength: 3,
            maxLength: 50,
            pattern: /^[a-zA-Z0-9\s\-_]+$/
        },
        position_size: {
            required: true,
            min: 10,
            max: 10000
        },
        slippage_tolerance: {
            required: true,
            min: 0.1,
            max: 5.0
        }
    };

    // Add Smart Lane specific validation rules
    if (currentMode === 'smart_lane') {
        validationRules.analysis_depth = { required: true };
        validationRules.ai_thought_log = { required: true };
        validationRules.risk_tolerance = { required: true };
        validationRules.position_sizing_method = { required: true };
        validationRules.min_confidence_threshold = { required: true, min: 50, max: 95 };
        validationRules.stop_loss_percentage = { required: true, min: 1, max: 50 };
        validationRules.take_profit_percentage = { required: true, min: 5, max: 500 };
    }

    // Real-time validation
    form.addEventListener('input', function (e) {
        validateField(e.target);
    });

    // Form submission validation
    form.addEventListener('submit', function (e) {
        if (!validateForm()) {
            e.preventDefault();
            return false;
        }
    });

    console.log('📝 Form validation initialized');
}

/**
 * Validate individual form field
 * @param {HTMLElement} field - Form field to validate
 */
function validateField(field) {
    if (!field || !field.name) return true;

    const rule = validationRules[field.name];
    if (!rule) return true;

    const value = field.value.trim();
    const errors = [];

    // Required validation
    if (rule.required && !value) {
        errors.push('This field is required');
    }

    // Length validation
    if (value && rule.minLength && value.length < rule.minLength) {
        errors.push(`Minimum length is ${rule.minLength} characters`);
    }

    if (value && rule.maxLength && value.length > rule.maxLength) {
        errors.push(`Maximum length is ${rule.maxLength} characters`);
    }

    // Numeric validation
    if (value && rule.min !== undefined) {
        const numValue = parseFloat(value);
        if (isNaN(numValue) || numValue < rule.min) {
            errors.push(`Minimum value is ${rule.min}`);
        }
    }

    if (value && rule.max !== undefined) {
        const numValue = parseFloat(value);
        if (isNaN(numValue) || numValue > rule.max) {
            errors.push(`Maximum value is ${rule.max}`);
        }
    }

    // Pattern validation
    if (value && rule.pattern && !rule.pattern.test(value)) {
        errors.push('Invalid format');
    }

    // Update field styling
    updateFieldValidation(field, errors);

    return errors.length === 0;
}

/**
 * Update field validation styling and messages
 * @param {HTMLElement} field - Form field
 * @param {Array} errors - Array of error messages
 */
function updateFieldValidation(field, errors) {
    // Remove existing validation classes
    field.classList.remove('is-valid', 'is-invalid');

    // Remove existing error messages
    const existingError = field.parentNode.querySelector('.invalid-feedback');
    if (existingError) {
        existingError.remove();
    }

    if (errors.length > 0) {
        field.classList.add('is-invalid');

        // Add error message
        const errorDiv = document.createElement('div');
        errorDiv.className = 'invalid-feedback';
        errorDiv.textContent = errors[0]; // Show first error
        field.parentNode.appendChild(errorDiv);
    } else if (field.value.trim()) {
        field.classList.add('is-valid');
    }
}

/**
 * Validate entire form
 * @returns {boolean} True if form is valid
 */
function validateForm() {
    const form = document.getElementById('configForm');
    if (!form) return false;

    let isValid = true;
    const errors = [];

    // Validate basic fields
    Object.keys(validationRules).forEach(fieldName => {
        const field = form.querySelector(`[name="${fieldName}"]`);
        if (field && !validateField(field)) {
            isValid = false;
        }
    });

    // Configuration name validation
    const configName = document.getElementById('config_name');
    if (configName && !configName.value.trim()) {
        errors.push('Please enter a configuration name.');
        configName.focus();
        isValid = false;
    }

    // Smart Lane specific validation
    if (currentMode === 'smart_lane') {
        isValid = validateSmartLaneForm() && isValid;
    }

    // Show first error if any
    if (errors.length > 0) {
        showToast(errors[0], 'error');
    }

    return isValid;
}

/**
 * Validate Smart Lane specific form requirements
 * @returns {boolean} True if Smart Lane form is valid
 */
function validateSmartLaneForm() {
    let isValid = true;

    // Validate technical indicators (at least 2 selected)
    const technicalIndicators = document.querySelectorAll('input[name="technical_indicators"]:checked');
    if (technicalIndicators.length < 2) {
        showToast('Please select at least 2 technical indicators for comprehensive analysis.', 'error');
        isValid = false;
    }

    // Validate timeframes (at least 2 selected)
    const timeframes = document.querySelectorAll('input[name="technical_timeframes"]:checked');
    if (timeframes.length < 2) {
        showToast('Please select at least 2 timeframes for technical analysis.', 'error');
        isValid = false;
    }

    // Validate stop loss vs take profit
    const stopLoss = parseFloat(document.getElementById('stop_loss_percentage')?.value || 0);
    const takeProfit = parseFloat(document.getElementById('take_profit_percentage')?.value || 0);

    if (takeProfit <= stopLoss) {
        showToast('Take profit percentage should be higher than stop loss percentage.', 'error');
        isValid = false;
    }

    // Validate confidence threshold
    const confidence = parseFloat(document.getElementById('min_confidence_threshold')?.value || 0);
    if (confidence < 50 || confidence > 95) {
        showToast('Confidence threshold should be between 50% and 95%.', 'error');
        isValid = false;
    }

    return isValid;
}

// ============================================================================
// CONFIGURATION PREVIEW
// ============================================================================

/**
 * Set up real-time configuration preview
 */
function setupConfigurationPreview() {
    const previewElements = [
        'analysis_depth', 'ai_thought_log', 'risk_tolerance',
        'position_sizing_method', 'min_confidence_threshold'
    ];

    previewElements.forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.addEventListener('change', updateConfigurationPreview);
        }
    });

    // Initialize preview
    updateConfigurationPreview();
}

/**
 * Update configuration preview and estimated analysis time
 */
function updateConfigurationPreview() {
    const analysisDepth = document.getElementById('analysis_depth')?.value;
    const estimatedTime = calculateEstimatedAnalysisTime(analysisDepth);

    const timeDisplay = document.getElementById('estimated-analysis-time');
    if (timeDisplay) {
        timeDisplay.textContent = `Estimated analysis time: ${estimatedTime}`;
        timeDisplay.style.color = getTimeDisplayColor(estimatedTime);
    }

    // Update other preview elements
    updateRiskPreview();
    updatePerformancePreview();
}

/**
 * Calculate estimated analysis time based on configuration
 * @param {string} depth - Analysis depth setting
 * @returns {string} Estimated time range
 */
function calculateEstimatedAnalysisTime(depth) {
    switch (depth) {
        case 'BASIC': return '1-2 seconds';
        case 'COMPREHENSIVE': return '3-5 seconds';
        case 'DEEP_DIVE': return '8-12 seconds';
        default: return '3-5 seconds';
    }
}

/**
 * Get color for time display based on estimated time
 * @param {string} timeString - Time string
 * @returns {string} CSS color value
 */
function getTimeDisplayColor(timeString) {
    if (timeString.includes('1-2')) return '#28a745'; // Fast - green
    if (timeString.includes('3-5')) return '#ffc107'; // Medium - yellow
    if (timeString.includes('8-12')) return '#dc3545'; // Slow - red
    return '#adb5bd'; // Default - gray
}

/**
 * Update risk preview display
 */
function updateRiskPreview() {
    const riskTolerance = document.getElementById('risk_tolerance')?.value;
    const confidenceThreshold = document.getElementById('min_confidence_threshold')?.value;

    // Update visual indicators based on settings
    const riskElements = document.querySelectorAll('.risk-indicator');
    riskElements.forEach(element => {
        element.style.opacity = '0.6';
    });

    if (riskTolerance) {
        const activeRisk = document.querySelector(`.risk-${riskTolerance.toLowerCase()}`);
        if (activeRisk) {
            activeRisk.style.opacity = '1';
        }
    }
}

/**
 * Update performance preview
 */
function updatePerformancePreview() {
    const enabledAnalyzers = document.querySelectorAll('input[name^="enable_"]:checked').length;
    const selectedIndicators = document.querySelectorAll('input[name="technical_indicators"]:checked').length;

    // Calculate complexity score
    const complexityScore = enabledAnalyzers + selectedIndicators;

    // Update complexity indicator if it exists
    const complexityIndicator = document.getElementById('complexity-indicator');
    if (complexityIndicator) {
        complexityIndicator.textContent = `Analysis complexity: ${complexityScore}/10`;
        complexityIndicator.className = `small ${complexityScore > 7 ? 'text-warning' : 'text-success'}`;
    }
}

// ============================================================================
// SMART LANE SPECIFIC FEATURES
// ============================================================================

/**
 * Set up Smart Lane specific features
 */
function setupSmartLaneFeatures() {
    console.log('🧠 Setting up Smart Lane features...');

    // Set up analyzer toggles
    setupAnalyzerToggles();

    // Set up technical analysis configuration
    setupTechnicalAnalysisConfig();

    // Set up exit strategy configuration
    setupExitStrategyConfig();

    // Set up performance optimization
    setupPerformanceConfig();
}

/**
 * Set up analyzer toggle functionality
 */
function setupAnalyzerToggles() {
    const analyzerToggles = document.querySelectorAll('input[name^="enable_"]');

    analyzerToggles.forEach(toggle => {
        toggle.addEventListener('change', function () {
            const analyzerName = this.name.replace('enable_', '');
            const relatedSection = document.getElementById(`${analyzerName}-settings`);

            if (relatedSection) {
                if (this.checked) {
                    relatedSection.style.display = 'block';
                    relatedSection.classList.add('fade-in');
                } else {
                    relatedSection.style.display = 'none';
                    relatedSection.classList.remove('fade-in');
                }
            }

            updateConfigurationPreview();
        });
    });
}

/**
 * Set up technical analysis configuration
 */
function setupTechnicalAnalysisConfig() {
    const technicalAnalysisToggle = document.getElementById('enable_technical_analysis');
    const technicalSettings = document.getElementById('technical-analysis-settings');

    if (technicalAnalysisToggle && technicalSettings) {
        function toggleTechnicalSettings() {
            if (technicalAnalysisToggle.checked) {
                technicalSettings.style.display = 'block';
                technicalSettings.classList.add('fade-in');
            } else {
                technicalSettings.style.display = 'none';
                technicalSettings.classList.remove('fade-in');
            }
        }

        technicalAnalysisToggle.addEventListener('change', toggleTechnicalSettings);
        toggleTechnicalSettings(); // Initialize
    }
}

/**
 * Set up exit strategy configuration
 */
function setupExitStrategyConfig() {
    const stopLossInput = document.getElementById('stop_loss_percentage');
    const takeProfitInput = document.getElementById('take_profit_percentage');

    if (stopLossInput && takeProfitInput) {
        function validateExitStrategy() {
            const stopLoss = parseFloat(stopLossInput.value);
            const takeProfit = parseFloat(takeProfitInput.value);

            if (stopLoss && takeProfit) {
                const ratio = takeProfit / stopLoss;
                const ratioDisplay = document.getElementById('risk-reward-ratio');

                if (ratioDisplay) {
                    ratioDisplay.textContent = `Risk/Reward Ratio: 1:${ratio.toFixed(2)}`;
                    ratioDisplay.className = `small ${ratio >= 2 ? 'text-success' : ratio >= 1.5 ? 'text-warning' : 'text-danger'}`;
                }
            }
        }

        stopLossInput.addEventListener('input', validateExitStrategy);
        takeProfitInput.addEventListener('input', validateExitStrategy);
    }
}

/**
 * Set up performance configuration
 */
function setupPerformanceConfig() {
    const cacheStrategy = document.getElementById('cache_strategy');
    const cacheTtl = document.getElementById('cache_ttl');

    if (cacheStrategy && cacheTtl) {
        cacheStrategy.addEventListener('change', function () {
            switch (this.value) {
                case 'AGGRESSIVE':
                    cacheTtl.value = '600'; // 10 minutes
                    break;
                case 'BALANCED':
                    cacheTtl.value = '300'; // 5 minutes
                    break;
                case 'CONSERVATIVE':
                    cacheTtl.value = '60'; // 1 minute
                    break;
            }
        });
    }
}

// ============================================================================
// FAST LANE SPECIFIC FEATURES
// ============================================================================

/**
 * Set up Fast Lane specific features
 */
function setupFastLaneFeatures() {
    console.log('⚡ Setting up Fast Lane features...');

    // Set up gas price optimization
    setupGasPriceOptimization();

    // Set up execution time monitoring
    setupExecutionTimeMonitoring();

    // Set up MEV protection configuration
    setupMevProtectionConfig();
}

/**
 * Set up gas price optimization
 */
function setupGasPriceOptimization() {
    const gasPriceInput = document.getElementById('gas_price_gwei');
    const gasPriceDisplay = document.getElementById('gas-price-display');

    if (gasPriceInput) {
        gasPriceInput.addEventListener('input', function () {
            const gasPrice = parseFloat(this.value);
            const estimatedCost = gasPrice * 21000 / 1e9; // Basic ETH transfer

            if (gasPriceDisplay) {
                gasPriceDisplay.textContent = `~$${(estimatedCost * 2000).toFixed(2)} per transaction`; // Assuming $2000 ETH
                gasPriceDisplay.className = `small ${gasPrice > 50 ? 'text-danger' : gasPrice > 20 ? 'text-warning' : 'text-success'}`;
            }
        });
    }
}

/**
 * Set up execution time monitoring
 */
function setupExecutionTimeMonitoring() {
    const executionTimeInput = document.getElementById('max_execution_time_ms');

    if (executionTimeInput) {
        executionTimeInput.addEventListener('input', function () {
            const time = parseInt(this.value);
            const timeDisplay = document.getElementById('execution-time-display');

            if (timeDisplay) {
                timeDisplay.textContent = `${time}ms execution limit`;
                timeDisplay.className = `small ${time < 500 ? 'text-success' : time < 1000 ? 'text-warning' : 'text-danger'}`;
            }
        });
    }
}

/**
 * Set up MEV protection configuration
 */
function setupMevProtectionConfig() {
    const mevProtection = document.getElementById('enable_mev_protection');
    const autoApproval = document.getElementById('auto_approval');

    if (mevProtection && autoApproval) {
        function updateMevWarning() {
            const mevEnabled = mevProtection.checked;
            const autoEnabled = autoApproval.checked;

            const warningDiv = document.getElementById('mev-warning');
            if (warningDiv) {
                if (!mevEnabled && autoEnabled) {
                    warningDiv.style.display = 'block';
                    warningDiv.className = 'alert alert-warning mt-2';
                    warningDiv.textContent = 'Warning: Auto-approval without MEV protection increases front-running risk.';
                } else {
                    warningDiv.style.display = 'none';
                }
            }
        }

        mevProtection.addEventListener('change', updateMevWarning);
        autoApproval.addEventListener('change', updateMevWarning);
    }
}

// ============================================================================
// CONFIGURATION TESTING AND EXPORT
// ============================================================================

/**
 * Test Smart Lane configuration
 */
async function testSmartLaneConfiguration() {
    const testButton = document.getElementById('test-config-btn');
    if (!testButton) return;

    // Show loading state
    testButton.disabled = true;
    testButton.innerHTML = '<i class="bi bi-hourglass-split me-1"></i>Testing...';

    try {
        const formData = new FormData(document.getElementById('configForm'));
        const config = Object.fromEntries(formData);

        const response = await fetch('/dashboard/api/smart-lane/test-config/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({ config: config })
        });

        const result = await response.json();

        if (result.success) {
            showToast(`Configuration test successful!\nEstimated analysis time: ${result.analysis_time_ms}ms\nAll analyzers: ${result.analyzers_status}`, 'success');
        } else {
            showToast(`Configuration test failed: ${result.error}`, 'error');
        }

    } catch (error) {
        console.error('Configuration test error:', error);
        showToast(`Test failed: ${error.message}`, 'error');
    } finally {
        // Restore button state
        testButton.disabled = false;
        testButton.innerHTML = '<i class="bi bi-play me-1"></i>Test Configuration';
    }
}

/**
 * Export configuration as JSON file
 */
function exportSmartLaneConfig() {
    const form = document.getElementById('configForm');
    if (!form) return;

    const formData = new FormData(form);
    const config = {};

    // Process form data
    for (let [key, value] of formData.entries()) {
        if (config[key]) {
            // Handle multiple values (like checkboxes)
            if (Array.isArray(config[key])) {
                config[key].push(value);
            } else {
                config[key] = [config[key], value];
            }
        } else {
            config[key] = value;
        }
    }

    // Add metadata
    config._metadata = {
        mode: currentMode,
        exported_at: new Date().toISOString(),
        version: '1.0'
    };

    // Create and download file
    const configJson = JSON.stringify(config, null, 2);
    const blob = new Blob([configJson], { type: 'application/json' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');

    a.href = url;
    a.download = `${currentMode || 'config'}_${new Date().toISOString().slice(0, 10)}.json`;

    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    window.URL.revokeObjectURL(url);

    showToast('Configuration exported successfully!', 'success');
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Get CSRF token for API requests
 * @returns {string} CSRF token
 */
function getCsrfToken() {
    const csrfInput = document.querySelector('[name=csrfmiddlewaretoken]');
    const csrfMeta = document.querySelector('meta[name=csrf-token]');

    return csrfInput?.value || csrfMeta?.getAttribute('content') || '';
}

/**
 * Show toast notification
 * @param {string} message - Message to display
 * @param {string} type - Toast type (success, info, warning, error)
 */
function showToast(message, type = 'info') {
    // Create toast element
    const toast = document.createElement('div');
    toast.className = `alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show position-fixed`;
    toast.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px; max-width: 500px;';
    toast.innerHTML = `
        <i class="bi bi-${getToastIcon(type)} me-2"></i>
        ${message.replace(/\n/g, '<br>')}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;

    // Add to page
    document.body.appendChild(toast);

    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (toast.parentNode) {
            toast.remove();
        }
    }, 5000);
}

/**
 * Get appropriate icon for toast type
 * @param {string} type - Toast type
 * @returns {string} Bootstrap icon class
 */
function getToastIcon(type) {
    const icons = {
        success: 'check-circle-fill',
        info: 'info-circle-fill',
        warning: 'exclamation-triangle-fill',
        error: 'x-circle-fill'
    };
    return icons[type] || icons.info;
}

/**
 * Debounce function for performance optimization
 * @param {Function} func - Function to debounce
 * @param {number} wait - Wait time in milliseconds
 * @returns {Function} Debounced function
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// ============================================================================
// GLOBAL EXPORTS FOR TESTING/DEBUGGING
// ============================================================================

// Make functions available globally for testing/debugging
window.configPanelFunctions = {
    testSmartLaneConfiguration,
    exportSmartLaneConfig,
    validateForm,
    updateConfigurationPreview,
    showToast,
    getCsrfToken
};

// ============================================================================
// ERROR HANDLING AND CLEANUP
// ============================================================================

/**
 * Handle page unload cleanup
 */
window.addEventListener('beforeunload', function () {
    // Clear any pending timeouts
    if (riskIndicatorTimeout) {
        clearTimeout(riskIndicatorTimeout);
    }

    console.log('🔄 Configuration panel cleaning up resources');
});

/**
 * Handle errors globally
 */
window.addEventListener('error', function (event) {
    console.error('Configuration panel error:', event.error);
    showToast('An unexpected error occurred. Please refresh the page.', 'error');
});

console.log('🔧 Configuration panel JavaScript module loaded');