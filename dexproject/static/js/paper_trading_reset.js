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
    let confirmResetBtn;
    let resetLoadingOverlay;

    // ==========================================================================
    // Initialization
    // ==========================================================================

    document.addEventListener('DOMContentLoaded', function () {
        initializeElements();
        attachEventListeners();
        initializeTooltips();
    });

    function initializeElements() {
        resetModal = document.getElementById('resetAccountModal');
        resetAmountInput = document.getElementById('resetAmount');
        confirmCheckbox = document.getElementById('confirmReset');
        confirmResetBtn = document.getElementById('confirmResetBtn');
        resetLoadingOverlay = document.getElementById('resetLoadingOverlay');
    }

    function attachEventListeners() {
        // Quick amount buttons
        document.querySelectorAll('.quick-amount').forEach(btn => {
            btn.addEventListener('click', function () {
                const amount = this.dataset.amount;
                resetAmountInput.value = amount;

                // Visual feedback
                document.querySelectorAll('.quick-amount').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
            });
        });

        // Confirm checkbox - enable/disable reset button
        if (confirmCheckbox) {
            confirmCheckbox.addEventListener('change', function () {
                confirmResetBtn.disabled = !this.checked;
            });
        }

        // Reset button click
        if (confirmResetBtn) {
            confirmResetBtn.addEventListener('click', handleReset);
        }

        // Reset modal hidden - clear form
        if (resetModal) {
            resetModal.addEventListener('hidden.bs.modal', function () {
                resetAmountInput.value = '10000';
                confirmCheckbox.checked = false;
                confirmResetBtn.disabled = true;
                document.querySelectorAll('.quick-amount').forEach(b => b.classList.remove('active'));
            });
        }
    }

    function initializeTooltips() {
        const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
        [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl));
    }

    // ==========================================================================
    // Reset Account Handler
    // ==========================================================================

    async function handleReset() {
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
            // Show loading overlay
            showLoading(true);

            // Close modal
            const modalInstance = bootstrap.Modal.getInstance(resetModal);
            if (modalInstance) {
                modalInstance.hide();
            }

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

            // Hide loading overlay
            showLoading(false);

            if (data.success) {
                // Show success message with details
                const message = `
                    Account reset successfully!
                    <br><br>
                    <strong>Details:</strong><br>
                    • New Balance: $${data.data.new_balance.toLocaleString()}<br>
                    • Positions Closed: ${data.data.positions_closed}<br>
                    • Realized P&L: ${formatPnL(data.data.realized_pnl)}<br>
                    • New Session: ${data.data.new_session_name}
                `;

                showToast(message, 'success', 8000);

                // Reload page after short delay
                setTimeout(() => {
                    window.location.reload();
                }, 2000);

            } else {
                showToast(`Error: ${data.error}`, 'danger', 8000);
            }

        } catch (error) {
            console.error('Reset error:', error);
            showLoading(false);
            showToast(`Failed to reset account: ${error.message}`, 'danger', 8000);
        }
    }

    // ==========================================================================
    // Utility Functions
    // ==========================================================================

    function showLoading(show) {
        if (resetLoadingOverlay) {
            resetLoadingOverlay.style.display = show ? 'flex' : 'none';
        }
    }

    function getCSRFToken() {
        const tokenElement = document.querySelector('[name=csrfmiddlewaretoken]');
        if (tokenElement) {
            return tokenElement.value;
        }

        // Fallback to meta tag
        const metaToken = document.querySelector('meta[name="csrf-token"]');
        return metaToken ? metaToken.getAttribute('content') : '';
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