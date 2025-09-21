/**
 * Configuration Summary JavaScript
 * 
 * Extracted from configuration_summary.html template
 * Provides interactive functionality for configuration management
 * 
 * File: dashboard/static/dashboard/js/configuration_summary.js
 */

'use strict';

// ============================================================================
// CONFIGURATION SUMMARY MODULE
// ============================================================================

const ConfigurationSummary = {

    /**
     * Initialize the configuration summary page
     * Sets up event listeners and auto-dismiss functionality
     */
    init: function () {
        this.setupAutoDismissAlerts();
        this.setupEventListeners();
        console.log('Configuration Summary initialized');
    },

    /**
     * Set up event listeners for interactive elements
     */
    setupEventListeners: function () {
        // Additional event listeners can be added here
        // Example: Refresh buttons, real-time updates, etc.
    },

    /**
     * Auto-dismiss alert messages after 5 seconds
     */
    setupAutoDismissAlerts: function () {
        document.querySelectorAll('.alert').forEach(alert => {
            setTimeout(() => {
                if (alert.parentNode) {
                    alert.remove();
                }
            }, 5000);
        });
    }
};

// ============================================================================
// CANVAS DRAWING FUNCTIONS
// ============================================================================

/**
 * Draw a circular progress indicator on a canvas element
 * 
 * @param {string} canvasId - The ID of the canvas element
 * @param {number} percentage - Progress percentage (0-100)
 * @param {string} color - Color for the progress arc ('success', 'warning', 'danger')
 */
function drawCircularProgress(canvasId, percentage, color) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) {
        console.warn(`Canvas with ID '${canvasId}' not found`);
        return;
    }

    const ctx = canvas.getContext('2d');
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    const radius = 40;

    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw background circle
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, 0, 2 * Math.PI);
    ctx.strokeStyle = '#2c3e50';
    ctx.lineWidth = 6;
    ctx.stroke();

    // Draw progress arc
    const startAngle = -Math.PI / 2; // Start from top
    const endAngle = startAngle + (percentage / 100) * 2 * Math.PI;

    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, startAngle, endAngle);

    // Set color based on type
    ctx.strokeStyle = color === 'success' ? '#28a745' :
        color === 'warning' ? '#ffc107' : '#dc3545';
    ctx.lineWidth = 8;
    ctx.lineCap = 'round';
    ctx.stroke();
}

// ============================================================================
// ACTION FUNCTIONS
// ============================================================================

/**
 * Show confirmation modal for configuration deletion
 */
function confirmDelete() {
    const deleteModal = document.getElementById('deleteModal');
    if (deleteModal) {
        const modal = new bootstrap.Modal(deleteModal);
        modal.show();
    } else {
        console.warn('Delete modal not found');
    }
}

/**
 * Duplicate configuration functionality
 * Currently shows a placeholder message - to be implemented
 */
function duplicateConfig() {
    // Get the button that triggered this function
    const btn = event.target.closest('button');
    if (!btn) return;

    // Show loading state
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="bi bi-hourglass-split me-2"></i>Duplicating...';
    btn.disabled = true;

    // Simulate duplication process (replace with actual implementation)
    setTimeout(() => {
        alert('Configuration duplication feature coming soon!');
        btn.innerHTML = originalText;
        btn.disabled = false;
    }, 1000);
}

// ============================================================================
// INITIALIZATION
// ============================================================================

/**
 * Initialize the page when DOM is ready
 */
document.addEventListener('DOMContentLoaded', function () {
    ConfigurationSummary.init();
});

/**
 * Export for testing purposes
 */
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        ConfigurationSummary,
        drawCircularProgress,
        confirmDelete,
        duplicateConfig
    };
}