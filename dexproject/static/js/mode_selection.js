/**
 * Mode Selection JavaScript
 * 
 * Extracted from mode_selection.html template
 * Provides interactive functionality for trading mode selection
 * 
 * File: dashboard/static/dashboard/js/mode_selection.js
 */

'use strict';

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
        const modeCards = document.querySelectorAll('.mode-card');

        modeCards.forEach(card => {
            const disabledOverlay = card.querySelector('.disabled-overlay');
            if (disabledOverlay) return; // Skip disabled cards

            card.addEventListener('click', function (e) {
                // Don't trigger if clicking a button
                if (e.target.tagName === 'BUTTON') return;

                if (this.classList.contains('fast-lane-card')) {
                    ModeSelection.selectMode('FAST_LANE');
                } else if (this.classList.contains('smart-lane-card')) {
                    ModeSelection.selectMode('SMART_LANE');
                }
            });
        });
    },

    /**
     * Setup button click handlers
     */
    setupButtonHandlers: function () {
        // Mode selection buttons in cards
        const modeButtons = document.querySelectorAll('.mode-card button');
        modeButtons.forEach(button => {
            button.addEventListener('click', function (e) {
                e.stopPropagation(); // Prevent card click

                const card = this.closest('.mode-card');
                if (card.classList.contains('fast-lane-card')) {
                    ModeSelection.selectMode('FAST_LANE');
                } else if (card.classList.contains('smart-lane-card')) {
                    ModeSelection.selectMode('SMART_LANE');
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
        // Modal buttons for mode selection
        const modalFastButton = document.querySelector('#hybridModal [onclick*="FAST_LANE"]');
        if (modalFastButton) {
            modalFastButton.removeAttribute('onclick');
            modalFastButton.addEventListener('click', () => {
                ModeSelection.selectMode('FAST_LANE');
                bootstrap.Modal.getInstance(document.getElementById('hybridModal'))?.hide();
            });
        }

        const modalSmartButton = document.querySelector('#hybridModal [onclick*="SMART_LANE"]');
        if (modalSmartButton) {
            modalSmartButton.removeAttribute('onclick');
            modalSmartButton.addEventListener('click', () => {
                ModeSelection.selectMode('SMART_LANE');
                bootstrap.Modal.getInstance(document.getElementById('hybridModal'))?.hide();
            });
        }
    },

    /**
     * Setup card hover interactions
     */
    setupCardInteractions: function () {
        const modeCards = document.querySelectorAll('.mode-card');

        modeCards.forEach(card => {
            const disabledOverlay = card.querySelector('.disabled-overlay');
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
        // Animate metrics on page load
        setTimeout(() => {
            const metrics = document.querySelectorAll('.metric-value');
            metrics.forEach((metric, index) => {
                metric.style.opacity = '0';
                metric.style.transform = 'translateY(20px)';
                metric.style.transition = 'all 0.6s ease';

                setTimeout(() => {
                    metric.style.opacity = '1';
                    metric.style.transform = 'translateY(0)';
                }, index * 100 + Math.random() * 300);
            });
        }, 200);

        // Animate cards
        const cards = document.querySelectorAll('.mode-card');
        cards.forEach((card, index) => {
            card.style.opacity = '0';
            card.style.transform = 'translateY(30px)';
            card.style.transition = 'all 0.8s ease';

            setTimeout(() => {
                card.style.opacity = '1';
                card.style.transform = 'translateY(0)';
            }, index * 200 + 100);
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
            if (mode === 'SMART_LANE') {
                const configUrl = this.buildConfigUrl('smart_lane');
                window.location.href = configUrl;
            } else {
                const configUrl = this.buildConfigUrl('fast_lane');
                window.location.href = configUrl;
            }
        })
        .catch((error) => {
            console.error('Failed to set trading mode:', error);
            this.setLoadingState(false);
            this.showError('Failed to set trading mode. Please try again.');
        });
};

/**
 * Show demo for specified mode
 * @param {string} mode - Mode to show demo for
 */
ModeSelection.showDemo = function (mode) {
    if (mode === 'smart_lane') {
        // Try to get the smart lane demo URL, fallback to configuration
        try {
            const demoUrl = this.getUrlPattern('dashboard:smart_lane_demo');
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
    const modalElement = document.getElementById('hybridModal');
    if (modalElement) {
        const modal = new bootstrap.Modal(modalElement);
        modal.show();
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
    const apiUrl = this.getUrlPattern('dashboard:api_set_trading_mode');

    return fetch(apiUrl, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': this.getCsrfToken()
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
            return data;
        });
};

/**
 * Get CSRF token from cookies
 * @returns {string|null} CSRF token or null if not found
 */
ModeSelection.getCsrfToken = function () {
    const name = 'csrftoken';
    let cookieValue = null;

    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }

    return cookieValue;
};

/**
 * Build configuration URL for specified mode
 * @param {string} mode - Mode for configuration URL
 * @returns {string} Configuration URL
 */
ModeSelection.buildConfigUrl = function (mode) {
    try {
        // Try to get the URL pattern from Django
        return this.getUrlPattern('dashboard:configuration_panel', { mode: mode });
    } catch (error) {
        // Fallback URL construction
        console.warn('URL pattern not available, using fallback');
        return `/dashboard/config/${mode}/`;
    }
};

/**
 * Get URL pattern (placeholder for Django URL resolution)
 * @param {string} pattern - URL pattern name
 * @param {Object} params - URL parameters
 * @returns {string} Resolved URL
 */
ModeSelection.getUrlPattern = function (pattern, params = {}) {
    // This would typically be replaced with actual Django URL resolution
    // For now, we'll use hardcoded fallbacks
    const urlPatterns = {
        'dashboard:api_set_trading_mode': '/dashboard/api/set-trading-mode/',
        'dashboard:configuration_panel': `/dashboard/config/${params.mode || 'smart_lane'}/`,
        'dashboard:smart_lane_demo': '/dashboard/smart-lane/demo/',
        'dashboard:home': '/dashboard/'
    };

    const url = urlPatterns[pattern];
    if (!url) {
        throw new Error(`URL pattern '${pattern}' not found`);
    }

    return url;
};

/**
 * Set loading state for buttons
 * @param {boolean} loading - Whether to show loading state
 */
ModeSelection.setLoadingState = function (loading) {
    const cards = document.querySelectorAll('.mode-card');

    cards.forEach(card => {
        const button = card.querySelector('button');
        if (button && !button.disabled) {
            if (loading) {
                button.innerHTML = '<i class="bi bi-hourglass-split me-2"></i>Setting up...';
                button.disabled = true;
                button.classList.add('btn-loading');
            } else {
                // Restore original button text
                button.classList.remove('btn-loading');
                button.disabled = false;

                if (card.classList.contains('fast-lane-card')) {
                    button.innerHTML = '<i class="bi bi-lightning-charge me-2"></i>Choose Fast Lane';
                } else if (card.classList.contains('smart-lane-card')) {
                    button.innerHTML = '<i class="bi bi-cpu me-2"></i>Choose Smart Lane';
                }
            }
        }
    });
};

/**
 * Show error message to user
 * @param {string} message - Error message to display
 */
ModeSelection.showError = function (message) {
    // Try to use a toast notification if available
    if (window.showNotification) {
        window.showNotification(message, 'error');
    } else if (window.tradingManager && window.tradingManager.showNotification) {
        window.tradingManager.showNotification(message, 'error');
    } else {
        // Fallback to alert
        alert(message);
    }
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