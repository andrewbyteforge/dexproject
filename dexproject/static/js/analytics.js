/**
 * Analytics Page JavaScript
 * 
 * Handles trading analytics, portfolio visualization, manual trading,
 * and real-time data updates for the analytics dashboard
 * 
 * File: dexproject/static/js/analytics.js
 */

// ============================================================================
// GLOBAL VARIABLES AND STATE
// ============================================================================

let currentTradeAction = 'buy';
let analyticsEventSource = null;
let pnlChart = null;
let refreshTimer = null;

// ============================================================================
// PAGE INITIALIZATION
// ============================================================================

/**
 * Initialize analytics page when DOM is ready
 */
document.addEventListener('DOMContentLoaded', function () {
    console.log('📊 Analytics page loaded');

    // Initialize P&L chart if data is available
    if (window.analyticsConfig?.hasChartData) {
        initializePnLChart();
    }

    // Set up modal event handlers
    setupModalHandlers();

    // Start real-time updates if available
    if (window.analyticsConfig?.analyticsReady) {
        setTimeout(startRealTimeUpdates, 1000);
    }

    // Auto-refresh data every 30 seconds
    startAutoRefresh();

    console.log('✅ Analytics page initialized');
});

// ============================================================================
// CHART INITIALIZATION AND MANAGEMENT
// ============================================================================

/**
 * Initialize P&L Chart with historical data
 */
function initializePnLChart() {
    const ctx = document.getElementById('pnlChart');
    if (!ctx) {
        console.warn('P&L chart canvas not found');
        return;
    }

    // Chart data will be provided by Django template
    const chartData = window.analyticsConfig?.chartData || [];

    pnlChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: chartData.map(d => d.date),
            datasets: [{
                label: 'P&L',
                data: chartData.map(d => d.pnl),
                borderColor: '#00d4aa',
                backgroundColor: 'rgba(0, 212, 170, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.4,
                pointBackgroundColor: '#00d4aa',
                pointBorderColor: '#ffffff',
                pointBorderWidth: 2,
                pointRadius: 4,
                pointHoverRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    titleColor: '#ffffff',
                    bodyColor: '#ffffff',
                    borderColor: '#00d4aa',
                    borderWidth: 1,
                    callbacks: {
                        label: function (context) {
                            return `P&L: $${context.parsed.y.toFixed(2)}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    display: false
                },
                y: {
                    display: true,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: '#999',
                        callback: function (value) {
                            return '$' + value.toFixed(0);
                        }
                    }
                }
            },
            interaction: {
                intersect: false,
                mode: 'index'
            }
        }
    });

    console.log('📈 P&L chart initialized');
}

/**
 * Update P&L chart with new data
 * @param {Array} newData - Array of {date, pnl} objects
 */
function updatePnLChart(newData) {
    if (!pnlChart || !newData) return;

    pnlChart.data.labels = newData.map(d => d.date);
    pnlChart.data.datasets[0].data = newData.map(d => d.pnl);
    pnlChart.update('none');

    console.log('📈 P&L chart updated with new data');
}

// ============================================================================
// DATA REFRESH FUNCTIONALITY
// ============================================================================

/**
 * Refresh analytics data from server
 */
async function refreshAnalytics() {
    console.log('🔄 Refreshing analytics data...');

    try {
        // Show loading indicator
        showToast('Refreshing analytics data...', 'info');

        // In a production environment, this would use AJAX to update specific sections
        // For now, we'll reload the page to get the latest data
        const currentUrl = new URL(window.location);
        currentUrl.searchParams.set('_t', Date.now()); // Add timestamp to prevent caching
        window.location.href = currentUrl.toString();

    } catch (error) {
        console.error('❌ Failed to refresh analytics:', error);
        showToast('Failed to refresh analytics data', 'error');
    }
}

/**
 * Start auto-refresh timer
 */
function startAutoRefresh() {
    // Clear existing timer
    if (refreshTimer) {
        clearInterval(refreshTimer);
    }

    // Auto-refresh every 30 seconds
    refreshTimer = setInterval(() => {
        if (!document.hidden) { // Only refresh when page is visible
            refreshAnalyticsData();
        }
    }, 30000);

    console.log('⏰ Auto-refresh timer started (30s interval)');
}

/**
 * Refresh analytics data via AJAX (for production use)
 */
async function refreshAnalyticsData() {
    try {
        const response = await fetch('/dashboard/api/analytics/refresh/', {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        if (response.ok) {
            const data = await response.json();
            updateAnalyticsDisplay(data);
        }
    } catch (error) {
        console.error('Analytics refresh error:', error);
        // Fail silently for background updates
    }
}

/**
 * Update analytics display with new data
 * @param {Object} data - Analytics data from server
 */
function updateAnalyticsDisplay(data) {
    // Update portfolio metrics
    if (data.portfolio_data) {
        updatePortfolioMetrics(data.portfolio_data);
    }

    // Update P&L chart
    if (data.chart_data?.pnl_timeline) {
        updatePnLChart(data.chart_data.pnl_timeline);
    }

    // Update performance metrics
    if (data.performance_analytics) {
        updatePerformanceMetrics(data.performance_analytics);
    }

    console.log('📊 Analytics display updated');
}

// ============================================================================
// TRADING MODAL FUNCTIONALITY
// ============================================================================

/**
 * Set up modal event handlers
 */
function setupModalHandlers() {
    const executeBtn = document.getElementById('executeTradeBtn');
    if (executeBtn) {
        executeBtn.addEventListener('click', handleTradeExecution);
    }

    // Form validation
    const tradeForm = document.getElementById('tradeForm');
    if (tradeForm) {
        tradeForm.addEventListener('input', validateTradeForm);
    }
}

/**
 * Show trading modal for buy/sell actions
 * @param {string} action - 'buy' or 'sell'
 */
function showTradeModal(action) {
    currentTradeAction = action;

    // Update modal title and button text
    const modalTitle = document.getElementById('tradeModalLabel');
    const executeBtn = document.getElementById('executeTradeBtn');
    const amountUnit = document.getElementById('amountUnit');

    if (modalTitle && executeBtn && amountUnit) {
        if (action === 'buy') {
            modalTitle.textContent = 'Manual Buy Order';
            executeBtn.textContent = 'Execute Buy';
            executeBtn.className = 'btn btn-trade';
            amountUnit.textContent = 'ETH';
        } else {
            modalTitle.textContent = 'Manual Sell Order';
            executeBtn.textContent = 'Execute Sell';
            executeBtn.className = 'btn btn-trade btn-sell';
            amountUnit.textContent = 'Tokens';
        }
    }

    // Reset form
    const tradeForm = document.getElementById('tradeForm');
    if (tradeForm) {
        tradeForm.reset();
    }

    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('tradeModal'));
    modal.show();

    console.log(`💹 ${action.toUpperCase()} modal opened`);
}

/**
 * Validate trade form inputs
 */
function validateTradeForm() {
    const tokenAddress = document.getElementById('tokenAddress')?.value;
    const pairAddress = document.getElementById('pairAddress')?.value;
    const amount = document.getElementById('tradeAmount')?.value;
    const executeBtn = document.getElementById('executeTradeBtn');

    if (!executeBtn) return;

    const isValid = tokenAddress &&
        pairAddress &&
        amount &&
        tokenAddress.startsWith('0x') &&
        pairAddress.startsWith('0x') &&
        parseFloat(amount) > 0;

    executeBtn.disabled = !isValid;
}

/**
 * Handle trade execution from modal
 */
async function handleTradeExecution() {
    const tokenAddress = document.getElementById('tokenAddress')?.value;
    const pairAddress = document.getElementById('pairAddress')?.value;
    const amount = document.getElementById('tradeAmount')?.value;
    const slippage = document.getElementById('slippageTolerance')?.value;
    const executeBtn = document.getElementById('executeTradeBtn');

    // Validate inputs
    if (!tokenAddress || !pairAddress || !amount) {
        showToast('Please fill in all required fields', 'error');
        return;
    }

    if (!tokenAddress.startsWith('0x') || !pairAddress.startsWith('0x')) {
        showToast('Please enter valid contract addresses', 'error');
        return;
    }

    if (parseFloat(amount) <= 0) {
        showToast('Please enter a valid amount', 'error');
        return;
    }

    // Show loading state
    if (executeBtn) {
        executeBtn.disabled = true;
        executeBtn.innerHTML = '<i class="bi bi-hourglass-split me-2"></i>Processing...';
    }

    try {
        // Call the manual trade API
        const response = await fetch('/dashboard/api/trading/manual/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                action: currentTradeAction,
                token_address: tokenAddress,
                pair_address: pairAddress,
                amount: parseFloat(amount),
                slippage_tolerance: parseFloat(slippage) / 100
            })
        });

        const result = await response.json();

        if (result.status === 'success') {
            showToast(`${currentTradeAction.toUpperCase()} order submitted successfully!`, 'success');

            // Close modal
            const modal = bootstrap.Modal.getInstance(document.getElementById('tradeModal'));
            if (modal) {
                modal.hide();
            }

            // Reset form
            const tradeForm = document.getElementById('tradeForm');
            if (tradeForm) {
                tradeForm.reset();
            }

            // Refresh data after a short delay
            setTimeout(refreshAnalytics, 2000);

        } else {
            showToast(`Failed to submit order: ${result.error || 'Unknown error'}`, 'error');
        }

    } catch (error) {
        console.error('❌ Trade execution error:', error);
        showToast('Failed to execute trade. Please try again.', 'error');
    } finally {
        // Restore button state
        if (executeBtn) {
            executeBtn.disabled = false;
            executeBtn.innerHTML = currentTradeAction === 'buy' ? 'Execute Buy' : 'Execute Sell';
        }
    }
}

// ============================================================================
// SMART LANE INTEGRATION
// ============================================================================

/**
 * Trigger Smart Lane analysis for a specific token
 */
async function triggerSmartAnalysis() {
    const tokenAddress = prompt('Enter token address for Smart Lane analysis:');
    const pairAddress = prompt('Enter pair address:');

    if (!tokenAddress || !pairAddress) {
        showToast('Token and pair addresses are required', 'warning');
        return;
    }

    if (!tokenAddress.startsWith('0x') || !pairAddress.startsWith('0x')) {
        showToast('Please enter valid contract addresses', 'error');
        return;
    }

    try {
        showToast('Triggering Smart Lane analysis...', 'info');

        const response = await fetch('/dashboard/api/trading/smart-lane/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                token_address: tokenAddress,
                pair_address: pairAddress
            })
        });

        const result = await response.json();

        if (result.status === 'success') {
            showToast('Smart Lane analysis initiated! Check back in a few minutes.', 'success');
        } else {
            showToast(`Failed to trigger analysis: ${result.error || 'Unknown error'}`, 'error');
        }

    } catch (error) {
        console.error('❌ Smart analysis error:', error);
        showToast('Failed to trigger Smart Lane analysis', 'error');
    }
}

// ============================================================================
// WALLET INTEGRATION
// ============================================================================

/**
 * Connect wallet function
 */
function connectWallet() {
    if (window.walletManager && typeof window.walletManager.showWalletModal === 'function') {
        window.walletManager.showWalletModal();
    } else if (window.walletManager && typeof window.walletManager.connectWallet === 'function') {
        window.walletManager.connectWallet();
    } else {
        showToast('Wallet connection not available. Please check your setup.', 'warning');
    }
}

// ============================================================================
// REAL-TIME UPDATES
// ============================================================================

/**
 * Start real-time updates using Server-Sent Events
 */
function startRealTimeUpdates() {
    if (typeof EventSource === 'undefined') {
        console.warn('EventSource not supported, real-time updates disabled');
        return;
    }

    const streamUrl = window.analyticsConfig?.metricsStreamUrl || '/dashboard/metrics/stream/';
    analyticsEventSource = new EventSource(streamUrl);

    analyticsEventSource.onopen = function () {
        console.log('📡 Real-time analytics updates connected');
    };

    analyticsEventSource.onmessage = function (event) {
        try {
            const data = JSON.parse(event.data);

            // Update portfolio summary if available
            if (data.portfolio_summary) {
                updatePortfolioSummary(data.portfolio_summary);
            }

            // Update trading activity
            if (data.recent_trades) {
                updateTradingActivity(data.recent_trades);
            }

        } catch (error) {
            console.error('❌ Error processing real-time update:', error);
        }
    };

    analyticsEventSource.onerror = function (error) {
        console.error('❌ EventSource failed:', error);
        analyticsEventSource.close();

        // Attempt to reconnect after 5 seconds
        setTimeout(() => {
            if (!document.hidden) {
                startRealTimeUpdates();
            }
        }, 5000);
    };

    // Close connection when page unloads
    window.addEventListener('beforeunload', function () {
        if (analyticsEventSource) {
            analyticsEventSource.close();
        }
    });
}

/**
 * Update portfolio summary with real-time data
 * @param {Object} summary - Portfolio summary data
 */
function updatePortfolioSummary(summary) {
    console.log('📊 Portfolio update received:', summary);

    // Update total portfolio value
    const portfolioValueEl = document.querySelector('.metric-large');
    if (portfolioValueEl && summary.total_value_usd) {
        portfolioValueEl.textContent = `$${parseFloat(summary.total_value_usd).toFixed(2)}`;
    }

    // Update P&L
    const pnlElements = document.querySelectorAll('.pnl-positive, .pnl-negative');
    if (pnlElements.length > 0 && summary.total_pnl_usd !== undefined) {
        pnlElements[0].textContent = `$${parseFloat(summary.total_pnl_usd).toFixed(2)}`;
        pnlElements[0].className = summary.total_pnl_usd >= 0 ? 'metric-large pnl-positive' : 'metric-large pnl-negative';
    }
}

/**
 * Update trading activity section
 * @param {Array} trades - Recent trades data
 */
function updateTradingActivity(trades) {
    console.log('💹 Trading activity update received');
    // Implementation would update the trading activity list
    // This is a placeholder for real-time trade updates
}

// ============================================================================
// UI UPDATE FUNCTIONS
// ============================================================================

/**
 * Update portfolio metrics display
 * @param {Object} portfolioData - Portfolio data from server
 */
function updatePortfolioMetrics(portfolioData) {
    // Update portfolio value cards with new data
    const valueElement = document.querySelector('[data-metric="portfolio-value"]');
    if (valueElement && portfolioData.total_value_usd) {
        valueElement.textContent = `$${parseFloat(portfolioData.total_value_usd).toFixed(2)}`;
    }

    // Update P&L
    const pnlElement = document.querySelector('[data-metric="total-pnl"]');
    if (pnlElement && portfolioData.total_pnl_usd !== undefined) {
        pnlElement.textContent = `$${parseFloat(portfolioData.total_pnl_usd).toFixed(2)}`;
        pnlElement.className = portfolioData.total_pnl_usd >= 0 ? 'metric-large pnl-positive' : 'metric-large pnl-negative';
    }

    // Update position count
    const positionElement = document.querySelector('[data-metric="position-count"]');
    if (positionElement && portfolioData.position_count !== undefined) {
        positionElement.textContent = portfolioData.position_count;
    }
}

/**
 * Update performance metrics display
 * @param {Object} performanceData - Performance analytics data
 */
function updatePerformanceMetrics(performanceData) {
    const metricsMap = {
        'total-trades': 'total_trades',
        'win-rate': 'win_rate_percent',
        'avg-trade-size': 'avg_trade_size_usd',
        'total-volume': 'total_volume_usd'
    };

    Object.entries(metricsMap).forEach(([elementId, dataKey]) => {
        const element = document.querySelector(`[data-metric="${elementId}"]`);
        if (element && performanceData[dataKey] !== undefined) {
            let value = performanceData[dataKey];

            // Format the value based on type
            if (elementId.includes('rate')) {
                value = `${parseFloat(value).toFixed(1)}%`;
            } else if (elementId.includes('size') || elementId.includes('volume')) {
                value = `$${parseFloat(value).toFixed(2)}`;
            }

            element.textContent = value;
        }
    });
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
    toast.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    toast.innerHTML = `
        <i class="bi bi-${getToastIcon(type)} me-2"></i>
        ${message}
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

// ============================================================================
// PAGE LIFECYCLE MANAGEMENT
// ============================================================================

// Handle page visibility changes
document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
        console.log('📱 Analytics page hidden - pausing updates');
        if (refreshTimer) {
            clearInterval(refreshTimer);
        }
        if (analyticsEventSource) {
            analyticsEventSource.close();
        }
    } else {
        console.log('📱 Analytics page visible - resuming updates');
        startAutoRefresh();
        if (window.analyticsConfig?.analyticsReady) {
            startRealTimeUpdates();
        }
    }
});

// Clean up on page unload
window.addEventListener('beforeunload', function () {
    console.log('🔄 Analytics page unloading - cleaning up resources');
    if (refreshTimer) {
        clearInterval(refreshTimer);
    }
    if (analyticsEventSource) {
        analyticsEventSource.close();
    }
});

// ============================================================================
// GLOBAL EXPORTS FOR TESTING/DEBUGGING
// ============================================================================

// Make functions available globally for testing/debugging
window.analyticsFunctions = {
    refreshAnalytics,
    showTradeModal,
    triggerSmartAnalysis,
    connectWallet,
    showToast,
    updatePortfolioSummary,
    getCsrfToken
};

console.log('📊 Analytics JavaScript module loaded');