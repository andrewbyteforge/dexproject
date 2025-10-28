/**
 * Mode Selection JavaScript
 * 
 * Provides interactive functionality for trading mode selection.
 * Handles mode card interactions, animations, and API calls for mode selection.
 * 
 * Dependencies:
 * - common-utils.js (must be loaded before this file)
 *   - Uses: getCSRFToken(), showToast()
 * - api-constants.js (must be loaded before this file)
 *   - Uses: API_ENDPOINTS, API_UTILS
 * 
 * File: dashboard/static/dashboard/js/mode_selection.js
 */

'use strict';

// ============================================================================
// CONSTANTS
// ============================================================================

const MODE_SELECTION_CONFIG = {
    MODES: {
        FAST_LANE: 'FAST_LANE',
        SMART_LANE: 'SMART_LANE'
    },

    SELECTORS: {
        MODE_CARD: '.mode-card',
        FAST_LANE_CARD: '.fast-lane-card',
        SMART_LANE_CARD: '.smart-lane-card',
        DISABLED_OVERLAY: '.disabled-overlay',
        METRIC_VALUE: '.metric-value',
        MODE_CARD_BUTTON: '.mode-card button'
    },

    MODAL_IDS: {
        HYBRID: 'hybridModal'
    },

    BUTTON_TEXT: {
        LOADING: '<i class="bi bi-hourglass-split me-2"></i>Setting up...',
        FAST_LANE: '<i class="bi bi-lightning-charge me-2"></i>Choose Fast Lane',
        SMART_LANE: '<i class="bi bi-cpu me-2"></i>Choose Smart Lane'
    },

    ANIMATION_TIMING: {
        INITIAL_DELAY: 200,
        METRIC_DELAY_BASE: 100,
        METRIC_DELAY_RANDOM: 300,
        CARD_DELAY: 200,
        CARD_START_DELAY: 100
    }
};

// ============================================================================
// MODE SELECTION MODULE
// ============================================================================

const ModeSelection = {

    /**
     * Initialize the mode selection page
     */
    init: function () {
        console.log('Initializing Mode Selection...');

        this.bindEventHandlers();
        this.initializeAnimations();
        this.setupCardInteractions();

        console.log('Mode Selection initialized');
    },

    /**
     * Bind event handlers for interactive elements
     */
    bindEventHandlers: function () {
        // Mode card click handlers
        this.setupModeCardClicks();

        // Button click handlers
        this.setupButtonHandlers();

        // Modal handlers
        this.setupModalHandlers();
    },

    /**
     * Setup mode card click interactions
     */
    setupModeCardClicks: function () {
        const modeCards = document.querySelectorAll(MODE_SELECTION_CONFIG.SELECTORS.MODE_CARD);

        modeCards.forEach(card => {
            const disabledOverlay = card.querySelector(MODE_SELECTION_CONFIG.SELECTORS.DISABLED_OVERLAY);
            if (disabledOverlay) return; // Skip disabled cards

            card.addEventListener('click', function (e) {
                // Don't trigger if clicking a button
                if (e.target.tagName === 'BUTTON') return;

                if (this.classList.contains('fast-lane-card')) {
                    ModeSelection.selectMode(MODE_SELECTION_CONFIG.MODES.FAST_LANE);
                } else if (this.classList.contains('smart-lane-card')) {
                    ModeSelection.selectMode(MODE_SELECTION_CONFIG.MODES.SMART_LANE);
                }
            });
        });
    },

    /**
     * Setup button click handlers
     */
    setupButtonHandlers: function () {
        // Mode selection buttons in cards
        const modeButtons = document.querySelectorAll(MODE_SELECTION_CONFIG.SELECTORS.MODE_CARD_BUTTON);
        modeButtons.forEach(button => {
            button.addEventListener('click', function (e) {
                e.stopPropagation(); // Prevent card click

                const card = this.closest(MODE_SELECTION_CONFIG.SELECTORS.MODE_CARD);
                if (card.classList.contains('fast-lane-card')) {
                    ModeSelection.selectMode(MODE_SELECTION_CONFIG.MODES.FAST_LANE);
                } else if (card.classList.contains('smart-lane-card')) {
                    ModeSelection.selectMode(MODE_SELECTION_CONFIG.MODES.SMART_LANE);
                }
            });
        });

        // Demo and info buttons
        const demoButtons = document.querySelectorAll('[onclick*="showDemo"]');
        demoButtons.forEach(button => {
            button.removeAttribute('onclick');
            button.addEventListener('click', () => ModeSelection.showDemo('smart_lane'));
        });

        const hybridButtons = document.querySelectorAll('[onclick*="showHybridInfo"]');
        hybridButtons.forEach(button => {
            button.removeAttribute('onclick');
            button.addEventListener('click', ModeSelection.showHybridInfo);
        });
    },

    /**
     * Setup modal event handlers
     */
    setupModalHandlers: function () {
        const modalId = MODE_SELECTION_CONFIG.MODAL_IDS.HYBRID;

        // Modal buttons for mode selection
        const modalFastButton = document.querySelector(`#${modalId} [onclick*="FAST_LANE"]`);
        if (modalFastButton) {
            modalFastButton.removeAttribute('onclick');
            modalFastButton.addEventListener('click', () => {
                ModeSelection.selectMode(MODE_SELECTION_CONFIG.MODES.FAST_LANE);
                const modalElement = document.getElementById(modalId);
                if (modalElement && bootstrap.Modal) {
                    bootstrap.Modal.getInstance(modalElement)?.hide();
                }
            });
        }

        const modalSmartButton = document.querySelector(`#${modalId} [onclick*="SMART_LANE"]`);
        if (modalSmartButton) {
            modalSmartButton.removeAttribute('onclick');
            modalSmartButton.addEventListener('click', () => {
                ModeSelection.selectMode(MODE_SELECTION_CONFIG.MODES.SMART_LANE);
                const modalElement = document.getElementById(modalId);
                if (modalElement && bootstrap.Modal) {
                    bootstrap.Modal.getInstance(modalElement)?.hide();
                }
            });
        }
    },

    /**
     * Setup card hover interactions
     */
    setupCardInteractions: function () {
        const modeCards = document.querySelectorAll(MODE_SELECTION_CONFIG.SELECTORS.MODE_CARD);

        modeCards.forEach(card => {
            const disabledOverlay = card.querySelector(MODE_SELECTION_CONFIG.SELECTORS.DISABLED_OVERLAY);
            if (disabledOverlay) return; // Skip disabled cards

            card.addEventListener('mouseenter', function () {
                this.style.transform = 'translateY(-5px)';
            });

            card.addEventListener('mouseleave', function () {
                this.style.transform = 'translateY(0)';
            });

            // Add keyboard navigation support
            card.setAttribute('tabindex', '0');
            card.setAttribute('role', 'button');

            card.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    this.click();
                }
            });
        });
    },

    /**
     * Initialize entrance animations
     */
    initializeAnimations: function () {
        const timing = MODE_SELECTION_CONFIG.ANIMATION_TIMING;

        // Animate metrics on page load
        setTimeout(() => {
            const metrics = document.querySelectorAll(MODE_SELECTION_CONFIG.SELECTORS.METRIC_VALUE);
            metrics.forEach((metric, index) => {
                metric.style.opacity = '0';
                metric.style.transform = 'translateY(20px)';
                metric.style.transition = 'all 0.6s ease';

                setTimeout(() => {
                    metric.style.opacity = '1';
                    metric.style.transform = 'translateY(0)';
                }, index * timing.METRIC_DELAY_BASE + Math.random() * timing.METRIC_DELAY_RANDOM);
            });
        }, timing.INITIAL_DELAY);

        // Animate cards
        const cards = document.querySelectorAll(MODE_SELECTION_CONFIG.SELECTORS.MODE_CARD);
        cards.forEach((card, index) => {
            card.style.opacity = '0';
            card.style.transform = 'translateY(30px)';
            card.style.transition = 'all 0.8s ease';

            setTimeout(() => {
                card.style.opacity = '1';
                card.style.transform = 'translateY(0)';
            }, index * timing.CARD_DELAY + timing.CARD_START_DELAY);
        });
    }
};

// ============================================================================
// MODE SELECTION FUNCTIONS
// ============================================================================

/**
 * Select and configure trading mode
 * @param {string} mode - Either 'FAST_LANE' or 'SMART_LANE'
 */
ModeSelection.selectMode = function (mode) {
    console.log('Selecting mode:', mode);

    // Show loading state on all buttons
    this.setLoadingState(true);

    // Set trading mode via API
    this.setTradingMode(mode)
        .then(() => {
            // Redirect to appropriate configuration page
            const modeParam = mode === MODE_SELECTION_CONFIG.MODES.SMART_LANE ? 'smart_lane' : 'fast_lane';
            const configUrl = this.buildConfigUrl(modeParam);

            console.log(`Redirecting to configuration: ${configUrl}`);
            window.location.href = configUrl;
        })
        .catch((error) => {
            console.error('Failed to set trading mode:', error);
            this.setLoadingState(false);

            // Use global showToast from common-utils.js
            showToast('Failed to set trading mode. Please try again.', 'danger');
        });
};

/**
 * Show demo for specified mode
 * @param {string} mode - Mode to show demo for
 */
ModeSelection.showDemo = function (mode) {
    if (mode === 'smart_lane') {
        // Try to get the smart lane demo URL
        try {
            const demoUrl = API_ENDPOINTS.DASHBOARD_PAGES.SMART_LANE_DEMO;
            console.log('Navigating to Smart Lane demo:', demoUrl);
            window.location.href = demoUrl;
        } catch (error) {
            console.warn('Smart lane demo URL not available, redirecting to configuration');
            const configUrl = this.buildConfigUrl('smart_lane');
            window.location.href = configUrl;
        }
    }
};

/**
 * Show hybrid strategy information modal
 */
ModeSelection.showHybridInfo = function () {
    const modalElement = document.getElementById(MODE_SELECTION_CONFIG.MODAL_IDS.HYBRID);

    if (modalElement) {
        if (typeof bootstrap !== 'undefined' && bootstrap.Modal) {
            const modal = new bootstrap.Modal(modalElement);
            modal.show();
        } else {
            console.error('Bootstrap Modal not available');
        }
    } else {
        console.error('Hybrid modal not found');
    }
};

// ============================================================================
// API AND UTILITY FUNCTIONS
// ============================================================================

/**
 * Set trading mode via API call
 * @param {string} mode - Trading mode to set
 * @returns {Promise} API response promise
 */
ModeSelection.setTradingMode = function (mode) {
    // Use API endpoint from api-constants.js
    const apiUrl = API_ENDPOINTS.DASHBOARD.SET_TRADING_MODE;

    console.log(`Setting trading mode to ${mode} via ${apiUrl}`);

    return fetch(apiUrl, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken() // From common-utils.js
        },
        body: JSON.stringify({ mode: mode })
    })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: Failed to set trading mode`);
            }
            return response.json();
        })
        .then(data => {
            if (!data.success) {
                throw new Error(data.error || 'Unknown error occurred');
            }
            console.log('Trading mode set successfully:', data);
            return data;
        });
};

/**
 * Build configuration URL for specified mode
 * @param {string} mode - Mode for configuration URL ('smart_lane' or 'fast_lane')
 * @returns {string} Configuration URL
 */
ModeSelection.buildConfigUrl = function (mode) {
    try {
        // Use URL from api-constants.js
        if (mode === 'smart_lane') {
            return API_ENDPOINTS.DASHBOARD_PAGES.SMART_LANE_CONFIG;
        } else if (mode === 'fast_lane') {
            return API_ENDPOINTS.DASHBOARD_PAGES.FAST_LANE_CONFIG;
        } else {
            // Generic config panel with mode parameter
            return API_ENDPOINTS.DASHBOARD_PAGES.CONFIG_PANEL(mode);
        }
    } catch (error) {
        // Fallback URL construction
        console.warn('API_ENDPOINTS not available, using fallback URL construction');
        return `/dashboard/config/${mode}/`;
    }
};

/**
 * Set loading state for buttons
 * @param {boolean} loading - Whether to show loading state
 */
ModeSelection.setLoadingState = function (loading) {
    const cards = document.querySelectorAll(MODE_SELECTION_CONFIG.SELECTORS.MODE_CARD);

    cards.forEach(card => {
        const button = card.querySelector('button');
        if (button && !button.disabled) {
            if (loading) {
                button.innerHTML = MODE_SELECTION_CONFIG.BUTTON_TEXT.LOADING;
                button.disabled = true;
                button.classList.add('btn-loading');
            } else {
                // Restore original button text
                button.classList.remove('btn-loading');
                button.disabled = false;

                if (card.classList.contains('fast-lane-card')) {
                    button.innerHTML = MODE_SELECTION_CONFIG.BUTTON_TEXT.FAST_LANE;
                } else if (card.classList.contains('smart-lane-card')) {
                    button.innerHTML = MODE_SELECTION_CONFIG.BUTTON_TEXT.SMART_LANE;
                }
            }
        }
    });
};

// ============================================================================
// GLOBAL FUNCTION EXPORTS (for template compatibility)
// ============================================================================

// Export functions for backwards compatibility with template onclick handlers
window.selectMode = ModeSelection.selectMode.bind(ModeSelection);
window.showDemo = ModeSelection.showDemo.bind(ModeSelection);
window.showHybridInfo = ModeSelection.showHybridInfo.bind(ModeSelection);

// Export module for global access
window.modeSelection = ModeSelection;

// ============================================================================
// INITIALIZATION
// ============================================================================

/**
 * Initialize Mode Selection when DOM is ready
 */
document.addEventListener('DOMContentLoaded', function () {
    ModeSelection.init();
});

/**
 * Handle page visibility changes to refresh data if needed
 */
document.addEventListener('visibilitychange', function () {
    if (!document.hidden) {
        // Page became visible - could refresh metrics here
        console.log('Mode selection page became visible');
    }
});

/**
 * Handle browser back/forward navigation
 */
window.addEventListener('pageshow', function (event) {
    if (event.persisted) {
        // Page was loaded from cache - reset any loading states
        ModeSelection.setLoadingState(false);
    }
});