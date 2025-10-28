/**
 * Common Utilities for DEX Trading Bot
 * 
 * Shared utility functions used across all JavaScript files in the project.
 * This file should be included in base templates before any other JavaScript files.
 * 
 * File: dexproject/static/js/common-utils.js
 */

'use strict';

// ============================================================================
// CSRF TOKEN UTILITIES
// ============================================================================

/**
 * Get CSRF token from cookies
 * Required for all Django POST requests
 * 
 * @returns {string|null} CSRF token value or null if not found
 */
function getCSRFToken() {
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
}

// ============================================================================
// TOAST NOTIFICATION UTILITIES
// ============================================================================

/**
 * Show toast notification message
 * Automatically creates and removes toast notifications
 * 
 * @param {string} message - Message to display
 * @param {string} type - Toast type: 'success', 'error', 'warning', 'info', 'danger'
 * @param {number} duration - Duration in milliseconds (default: 5000)
 */
function showToast(message, type = 'info', duration = 5000) {
    // Normalize type names (danger -> error, etc.)
    const typeMap = {
        'danger': 'danger',
        'error': 'danger',
        'success': 'success',
        'warning': 'warning',
        'info': 'info'
    };

    const normalizedType = typeMap[type] || 'info';

    // Try to find existing toast container
    let toastContainer = document.getElementById('toast-container');

    // Create toast container if it doesn't exist
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'toast-container';
        toastContainer.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 9999;
            max-width: 350px;
        `;
        document.body.appendChild(toastContainer);
    }

    // Create toast element
    const toast = document.createElement('div');
    toast.className = `toast bg-${normalizedType} text-white mb-2`;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');

    // Get icon based on type
    const icons = {
        'success': 'bi-check-circle',
        'danger': 'bi-exclamation-triangle',
        'warning': 'bi-exclamation-circle',
        'info': 'bi-info-circle'
    };
    const icon = icons[normalizedType] || 'bi-info-circle';

    toast.innerHTML = `
        <div class="toast-body d-flex align-items-center">
            <i class="bi ${icon} me-2"></i>
            <span>${escapeHtml(message)}</span>
            <button type="button" class="btn-close btn-close-white ms-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;

    // Apply custom styles for better visibility
    toast.style.cssText = `
        min-width: 300px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        border-radius: 8px;
        animation: slideInRight 0.3s ease-out;
    `;

    toastContainer.appendChild(toast);

    // Initialize Bootstrap toast if available
    if (typeof bootstrap !== 'undefined' && bootstrap.Toast) {
        const bsToast = new bootstrap.Toast(toast, {
            autohide: true,
            delay: duration
        });
        bsToast.show();

        // Remove from DOM after hidden
        toast.addEventListener('hidden.bs.toast', () => {
            toast.remove();
        });
    } else {
        // Fallback: Auto-remove without Bootstrap
        setTimeout(() => {
            toast.style.animation = 'slideOutRight 0.3s ease-out';
            setTimeout(() => {
                toast.remove();
            }, 300);
        }, duration);
    }
}

/**
 * Show notification (alias for showToast for backwards compatibility)
 * 
 * @param {string} message - Message to display
 * @param {string} type - Notification type
 */
function showNotification(message, type = 'info') {
    showToast(message, type);
}

// ============================================================================
// FORMATTING UTILITIES
// ============================================================================

/**
 * Format number as currency (USD)
 * 
 * @param {number|string} value - Value to format
 * @param {number} decimals - Number of decimal places (default: 2)
 * @returns {string} Formatted currency string
 */
function formatCurrency(value, decimals = 2) {
    const num = parseFloat(value);

    if (isNaN(num)) {
        return '$0.00';
    }

    return '$' + num.toLocaleString('en-US', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    });
}

/**
 * Format number as percentage
 * 
 * @param {number|string} value - Value to format (e.g., 0.5 for 50%)
 * @param {number} decimals - Number of decimal places (default: 2)
 * @returns {string} Formatted percentage string
 */
function formatPercent(value, decimals = 2) {
    const num = parseFloat(value);

    if (isNaN(num)) {
        return '0.00%';
    }

    return num.toFixed(decimals) + '%';
}

/**
 * Format large numbers with K, M, B suffixes
 * 
 * @param {number|string} value - Value to format
 * @param {number} decimals - Number of decimal places (default: 1)
 * @returns {string} Formatted number string
 */
function formatNumber(value, decimals = 1) {
    const num = parseFloat(value);

    if (isNaN(num)) {
        return '0';
    }

    if (num >= 1000000000) {
        return (num / 1000000000).toFixed(decimals) + 'B';
    }
    if (num >= 1000000) {
        return (num / 1000000).toFixed(decimals) + 'M';
    }
    if (num >= 1000) {
        return (num / 1000).toFixed(decimals) + 'K';
    }

    return num.toFixed(decimals);
}

// ============================================================================
// HTML/STRING UTILITIES
// ============================================================================

/**
 * Escape HTML to prevent XSS attacks
 * 
 * @param {string} text - Text to escape
 * @returns {string} HTML-safe text
 */
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };

    return String(text).replace(/[&<>"']/g, (m) => map[m]);
}

/**
 * Truncate string to specified length
 * 
 * @param {string} str - String to truncate
 * @param {number} maxLength - Maximum length
 * @returns {string} Truncated string with ellipsis
 */
function truncateString(str, maxLength = 50) {
    if (str.length <= maxLength) {
        return str;
    }
    return str.substring(0, maxLength - 3) + '...';
}

// ============================================================================
// DATE/TIME UTILITIES
// ============================================================================

/**
 * Update all elements with relative time displays
 * Updates elements with data-timestamp attribute
 */
function updateRelativeTimes() {
    const elements = document.querySelectorAll('[data-timestamp]');

    elements.forEach(element => {
        const timestamp = element.getAttribute('data-timestamp');
        if (timestamp) {
            element.textContent = getRelativeTime(timestamp);
        }
    });
}

/**
 * Get relative time string (e.g., "2 hours ago")
 * 
 * @param {string|Date} timestamp - Timestamp to convert
 * @returns {string} Relative time string
 */
function getRelativeTime(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const seconds = Math.floor((now - date) / 1000);

    if (seconds < 60) {
        return 'just now';
    }

    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) {
        return `${minutes} minute${minutes !== 1 ? 's' : ''} ago`;
    }

    const hours = Math.floor(minutes / 60);
    if (hours < 24) {
        return `${hours} hour${hours !== 1 ? 's' : ''} ago`;
    }

    const days = Math.floor(hours / 24);
    if (days < 30) {
        return `${days} day${days !== 1 ? 's' : ''} ago`;
    }

    const months = Math.floor(days / 30);
    if (months < 12) {
        return `${months} month${months !== 1 ? 's' : ''} ago`;
    }

    const years = Math.floor(months / 12);
    return `${years} year${years !== 1 ? 's' : ''} ago`;
}

/**
 * Format date as readable string
 * 
 * @param {string|Date} date - Date to format
 * @returns {string} Formatted date string
 */
function formatDate(date) {
    const d = new Date(date);
    return d.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
}

/**
 * Format time as readable string
 * 
 * @param {string|Date} date - Date to format
 * @returns {string} Formatted time string
 */
function formatTime(date) {
    const d = new Date(date);
    return d.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

// ============================================================================
// LOADING STATE UTILITIES
// ============================================================================

/**
 * Set loading state on a button
 * 
 * @param {HTMLElement} button - Button element
 * @param {boolean} loading - Whether to show loading state
 * @param {string} loadingText - Text to display when loading (default: 'Loading...')
 */
function setButtonLoading(button, loading, loadingText = 'Loading...') {
    if (!button) return;

    if (loading) {
        // Store original content
        button.setAttribute('data-original-html', button.innerHTML);
        button.setAttribute('data-original-disabled', button.disabled);

        // Set loading state
        button.innerHTML = `<i class="bi bi-hourglass-split me-2"></i>${loadingText}`;
        button.disabled = true;
        button.classList.add('btn-loading');
    } else {
        // Restore original state
        const originalHtml = button.getAttribute('data-original-html');
        const originalDisabled = button.getAttribute('data-original-disabled') === 'true';

        if (originalHtml) {
            button.innerHTML = originalHtml;
        }
        button.disabled = originalDisabled;
        button.classList.remove('btn-loading');

        // Clean up data attributes
        button.removeAttribute('data-original-html');
        button.removeAttribute('data-original-disabled');
    }
}

// ============================================================================
// VALIDATION UTILITIES
// ============================================================================

/**
 * Validate email address format
 * 
 * @param {string} email - Email address to validate
 * @returns {boolean} True if valid email format
 */
function isValidEmail(email) {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
}

/**
 * Validate number is within range
 * 
 * @param {number} value - Value to validate
 * @param {number} min - Minimum value
 * @param {number} max - Maximum value
 * @returns {boolean} True if within range
 */
function isInRange(value, min, max) {
    const num = parseFloat(value);
    return !isNaN(num) && num >= min && num <= max;
}

// ============================================================================
// ANIMATION UTILITIES
// ============================================================================

/**
 * Add CSS animation keyframes dynamically
 */
function addAnimationStyles() {
    if (document.getElementById('common-utils-animations')) {
        return; // Already added
    }

    const style = document.createElement('style');
    style.id = 'common-utils-animations';
    style.textContent = `
        @keyframes slideInRight {
            from {
                transform: translateX(100%);
                opacity: 0;
            }
            to {
                transform: translateX(0);
                opacity: 1;
            }
        }
        
        @keyframes slideOutRight {
            from {
                transform: translateX(0);
                opacity: 1;
            }
            to {
                transform: translateX(100%);
                opacity: 0;
            }
        }
        
        @keyframes pulse {
            0%, 100% {
                opacity: 1;
            }
            50% {
                opacity: 0.5;
            }
        }
        
        .btn-loading {
            pointer-events: none;
            opacity: 0.7;
        }
    `;
    document.head.appendChild(style);
}

// ============================================================================
// INITIALIZATION
// ============================================================================

/**
 * Initialize common utilities
 * Called automatically when script loads
 */
function initCommonUtils() {
    // Add animation styles
    addAnimationStyles();

    // Update relative times every minute
    updateRelativeTimes();
    setInterval(updateRelativeTimes, 60000);

    console.log('Common utilities initialized');
}

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCommonUtils);
} else {
    initCommonUtils();
}

// ============================================================================
// GLOBAL EXPORTS
// ============================================================================

// Make functions globally available
window.getCSRFToken = getCSRFToken;
window.showToast = showToast;
window.showNotification = showNotification;
window.formatCurrency = formatCurrency;
window.formatPercent = formatPercent;
window.formatNumber = formatNumber;
window.escapeHtml = escapeHtml;
window.truncateString = truncateString;
window.updateRelativeTimes = updateRelativeTimes;
window.getRelativeTime = getRelativeTime;
window.formatDate = formatDate;
window.formatTime = formatTime;
window.setButtonLoading = setButtonLoading;
window.isValidEmail = isValidEmail;
window.isInRange = isInRange;

// Export for module systems (if needed)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        getCSRFToken,
        showToast,
        showNotification,
        formatCurrency,
        formatPercent,
        formatNumber,
        escapeHtml,
        truncateString,
        updateRelativeTimes,
        getRelativeTime,
        formatDate,
        formatTime,
        setButtonLoading,
        isValidEmail,
        isInRange
    };
}

console.log('Common Utils v1.0 loaded successfully');