/**
 * Paper Trading - Reset Account Functionality
 * 
 * Handles the Reset & Add Funds feature for creating isolated trading sessions.
 * 
 * File: static/js/paper_trading_reset.js
 */

(function () {
    'use strict';

    // ==========================================================================
    // DOM Elements
    // ==========================================================================

    let resetModal;
    let resetAmountInput;
    let confirmCheckbox;
    let executeResetBtn;

    // ==========================================================================
    // Initialization
    // ==========================================================================

    document.addEventListener('DOMContentLoaded', function () {
        initializeElements();
        attachEventListeners();
    });

    function initializeElements() {
        resetModal = document.getElementById('resetAccountModal');
        resetAmountInput = document.getElementById('resetAmount');
        confirmCheckbox = document.getElementById('confirmReset');
        executeResetBtn = document.getElementById('executeResetBtn');
    }

    function attachEventListeners() {
        // Confirm checkbox - enable/disable reset button
        if (confirmCheckbox) {
            confirmCheckbox.addEventListener('change', function () {
                if (executeResetBtn) {
                    executeResetBtn.disabled = !this.checked;
                }
            });
        }

        // Reset modal hidden - clear form
        if (resetModal) {
            resetModal.addEventListener('hidden.bs.modal', function () {
                if (resetAmountInput) resetAmountInput.value = '10000';
                if (confirmCheckbox) confirmCheckbox.checked = false;
                if (executeResetBtn) executeResetBtn.disabled = true;
            });
        }
    }

    // ==========================================================================
    // Global Function - Called from modal button onclick
    // ==========================================================================

    window.executeReset = async function () {
        const amount = parseFloat(resetAmountInput.value);

        // Validation
        if (isNaN(amount) || amount < 100 || amount > 1000000) {
            showToast('Please enter a valid amount between $100 and $1,000,000', 'danger');
            return;
        }

        if (!confirmCheckbox.checked) {
            showToast('Please confirm that you understand this action', 'warning');
            return;
        }

        // Show confirmation dialog
        if (!confirm(`Are you sure you want to reset your account with $${amount.toLocaleString()}?\n\nThis will close all positions and start a new session.`)) {
            return;
        }

        try {
            // Disable button and show loading state
            executeResetBtn.disabled = true;
            executeResetBtn.innerHTML = '<i class="bi bi-hourglass-split me-1"></i> Processing...';

            // Close modal
            const modalInstance = bootstrap.Modal.getInstance(resetModal);
            if (modalInstance) {
                modalInstance.hide();
            }

            // Show loading toast
            showToast('Resetting account and closing positions...', 'info', 3000);

            // Call API
            const response = await fetch('/paper-trading/api/account/reset/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                },
                body: JSON.stringify({ amount: amount })
            });

            const data = await response.json();

            if (data.success) {
                // Show success message with details
                const message = `
                    <strong>Account reset successfully!</strong><br><br>
                    <strong>Details:</strong><br>
                    • New Balance: $${data.data.new_balance.toLocaleString()}<br>
                    • Positions Closed: ${data.data.positions_closed}<br>
                    • Realized P&L: ${formatPnL(data.data.realized_pnl)}<br>
                    • New Session: ${data.data.new_session_name}
                `;

                showToast(message, 'success', 8000);

                // Reload page to refresh all values
                setTimeout(() => {
                    window.location.reload();
                }, 2000);

            } else {
                // Re-enable button on error
                executeResetBtn.disabled = false;
                executeResetBtn.innerHTML = '<i class="bi bi-arrow-clockwise me-1"></i> Reset & Add Funds';

                showToast(`Error: ${data.error}`, 'danger', 8000);
            }

        } catch (error) {
            console.error('Reset error:', error);

            // Re-enable button on error
            if (executeResetBtn) {
                executeResetBtn.disabled = false;
                executeResetBtn.innerHTML = '<i class="bi bi-arrow-clockwise me-1"></i> Reset & Add Funds';
            }

            showToast(`Failed to reset account: ${error.message}`, 'danger', 8000);
        }
    };

    // ==========================================================================
    // Utility Functions
    // ==========================================================================

    function getCSRFToken() {
        // Try to get from form input first
        const tokenElement = document.querySelector('[name=csrfmiddlewaretoken]');
        if (tokenElement) {
            return tokenElement.value;
        }

        // Fallback to meta tag
        const metaToken = document.querySelector('meta[name="csrf-token"]');
        if (metaToken) {
            return metaToken.getAttribute('content');
        }

        // Last resort - try to get from cookie
        const cookieValue = document.cookie
            .split('; ')
            .find(row => row.startsWith('csrftoken='));

        return cookieValue ? cookieValue.split('=')[1] : '';
    }

    function formatPnL(value) {
        const num = parseFloat(value);
        const formatted = num.toLocaleString('en-US', {
            style: 'currency',
            currency: 'USD',
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });

        if (num > 0) {
            return `<span style="color: #10b981;">+${formatted}</span>`;
        } else if (num < 0) {
            return `<span style="color: #ef4444;">${formatted}</span>`;
        } else {
            return formatted;
        }
    }

    function showToast(message, type = 'info', duration = 5000) {
        // Check if toast function exists from base.html
        if (typeof window.showToast === 'function') {
            window.showToast(message, type, duration);
            return;
        }

        // Fallback toast implementation
        const toast = document.createElement('div');
        toast.className = `alert alert-${type} position-fixed top-0 start-50 translate-middle-x mt-3`;
        toast.style.zIndex = '9999';
        toast.style.minWidth = '300px';
        toast.innerHTML = `
            <div class="d-flex align-items-center">
                <i class="bi bi-${type === 'success' ? 'check-circle' : type === 'danger' ? 'x-circle' : 'info-circle'} me-2"></i>
                <div>${message}</div>
            </div>
        `;

        document.body.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transition = 'opacity 0.5s';
            setTimeout(() => toast.remove(), 500);
        }, duration);
    }

})();