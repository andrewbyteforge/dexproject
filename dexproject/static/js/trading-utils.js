/**
 * Trading Utilities Module
 * 
 * Provides utility functions and helpers used across the trading system.
 * Includes formatting, validation, and common helper methods.
 * 
 * File: dexproject/dashboard/static/js/trading-utils.js
 */

/**
 * Format large numbers with appropriate suffixes (B, M, K)
 * 
 * @param {number} num - The number to format
 * @returns {string} Formatted number string with suffix
 * 
 * @example
 * formatLargeNumber(1500000) // Returns "1.50M"
 * formatLargeNumber(2300) // Returns "2.30K"
 */
export function formatLargeNumber(num) {
    if (num >= 1e9) return (num / 1e9).toFixed(2) + 'B';
    if (num >= 1e6) return (num / 1e6).toFixed(2) + 'M';
    if (num >= 1e3) return (num / 1e3).toFixed(2) + 'K';
    return num.toFixed(2);
}

/**
 * Format currency values with proper decimal places
 * 
 * @param {number} value - The value to format
 * @param {number} decimals - Number of decimal places (default: 2)
 * @returns {string} Formatted currency string
 */
export function formatCurrency(value, decimals = 2) {
    if (value === null || value === undefined) return '$0.00';
    return '$' + parseFloat(value).toFixed(decimals);
}

/**
 * Format percentage values
 * 
 * @param {number} value - The percentage value (0.05 = 5%)
 * @param {number} decimals - Number of decimal places (default: 2)
 * @returns {string} Formatted percentage string
 */
export function formatPercentage(value, decimals = 2) {
    if (value === null || value === undefined) return '0.00%';
    return (value * 100).toFixed(decimals) + '%';
}

/**
 * Get CSRF token from cookie
 * Required for Django POST requests
 * 
 * @returns {string|null} CSRF token or null if not found
 */
export function getCsrfToken() {
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

/**
 * Validate Ethereum address format
 * 
 * @param {string} address - The address to validate
 * @returns {boolean} True if valid Ethereum address
 */
export function isValidEthereumAddress(address) {
    if (!address) return false;
    return /^0x[a-fA-F0-9]{40}$/.test(address);
}

/**
 * Validate positive number input
 * 
 * @param {string|number} value - The value to validate
 * @returns {boolean} True if valid positive number
 */
export function isValidPositiveNumber(value) {
    const num = parseFloat(value);
    return !isNaN(num) && num > 0;
}

/**
 * Format timestamp to readable date/time
 * 
 * @param {string|Date} timestamp - ISO timestamp or Date object
 * @returns {string} Formatted date/time string
 */
export function formatTimestamp(timestamp) {
    if (!timestamp) return 'N/A';

    const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;

    if (isNaN(date.getTime())) return 'Invalid Date';

    return date.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: true
    });
}

/**
 * Calculate time difference in human-readable format
 * 
 * @param {string|Date} timestamp - ISO timestamp or Date object
 * @returns {string} Human-readable time difference (e.g., "2 minutes ago")
 */
export function getTimeAgo(timestamp) {
    if (!timestamp) return 'N/A';

    const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
    const now = new Date();
    const diffMs = now - date;

    if (diffMs < 0) return 'Just now';

    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHour = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHour / 24);

    if (diffSec < 60) return `${diffSec} second${diffSec !== 1 ? 's' : ''} ago`;
    if (diffMin < 60) return `${diffMin} minute${diffMin !== 1 ? 's' : ''} ago`;
    if (diffHour < 24) return `${diffHour} hour${diffHour !== 1 ? 's' : ''} ago`;
    return `${diffDay} day${diffDay !== 1 ? 's' : ''} ago`;
}

/**
 * Truncate Ethereum address for display
 * 
 * @param {string} address - Full Ethereum address
 * @param {number} startChars - Characters to show at start (default: 6)
 * @param {number} endChars - Characters to show at end (default: 4)
 * @returns {string} Truncated address (e.g., "0x1234...5678")
 */
export function truncateAddress(address, startChars = 6, endChars = 4) {
    if (!address || address.length < startChars + endChars) return address;
    return `${address.slice(0, startChars)}...${address.slice(-endChars)}`;
}

/**
 * Deep clone an object
 * 
 * @param {Object} obj - Object to clone
 * @returns {Object} Cloned object
 */
export function deepClone(obj) {
    if (obj === null || typeof obj !== 'object') return obj;
    return JSON.parse(JSON.stringify(obj));
}

/**
 * Debounce function execution
 * 
 * @param {Function} func - Function to debounce
 * @param {number} wait - Milliseconds to wait
 * @returns {Function} Debounced function
 */
export function debounce(func, wait) {
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

/**
 * Throttle function execution
 * 
 * @param {Function} func - Function to throttle
 * @param {number} limit - Milliseconds between executions
 * @returns {Function} Throttled function
 */
export function throttle(func, limit) {
    let inThrottle;
    return function executedFunction(...args) {
        if (!inThrottle) {
            func(...args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

/**
 * Safe JSON parse with fallback
 * 
 * @param {string} jsonString - JSON string to parse
 * @param {*} fallback - Fallback value if parse fails
 * @returns {*} Parsed object or fallback value
 */
export function safeJsonParse(jsonString, fallback = null) {
    try {
        return JSON.parse(jsonString);
    } catch (e) {
        console.error('JSON parse error:', e);
        return fallback;
    }
}

/**
 * Generate unique ID
 * 
 * @returns {string} Unique identifier
 */
export function generateUniqueId() {
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * Calculate percentage change between two values
 * 
 * @param {number} oldValue - Original value
 * @param {number} newValue - New value
 * @returns {number} Percentage change (0.05 = 5% increase)
 */
export function calculatePercentageChange(oldValue, newValue) {
    if (oldValue === 0) return 0;
    return (newValue - oldValue) / oldValue;
}

/**
 * Clamp a value between min and max
 * 
 * @param {number} value - Value to clamp
 * @param {number} min - Minimum value
 * @param {number} max - Maximum value
 * @returns {number} Clamped value
 */
export function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
}