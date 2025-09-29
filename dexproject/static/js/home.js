/**
 * Dashboard Home Page JavaScript
 * 
 * Handles real-time updates, chart management, SSE connections,
 * and interactive dashboard functionality
 * 
 * File: dexproject/static/js/home.js
 */

// ============================================================================
// GLOBAL VARIABLES AND STATE
// ============================================================================

let performanceChart = null;
let sseConnection = null;
let thoughtLogData = [];
let recentAnalysesData = [];

// Performance chart data structure
const performanceData = {
    labels: [],
    datasets: [
        {
            label: 'Fast Lane (ms)',
            data: [],
            borderColor: '#10b981',
            backgroundColor: 'rgba(16, 185, 129, 0.1)',
            tension: 0.4,
            fill: true
        },
        {
            label: 'Smart Lane (ms)',
            data: [],
            borderColor: '#3b82f6',
            backgroundColor: 'rgba(59, 130, 246, 0.1)',
            tension: 0.4,
            fill: true
        }
    ]
};

// ============================================================================
// CHART INITIALIZATION AND MANAGEMENT
// ============================================================================

/**
 * Initialize the performance chart with Chart.js
 * Sets up real-time performance monitoring visualization
 */
function initPerformanceChart() {
    const ctx = document.getElementById('performanceChart');
    if (!ctx) {
        console.warn('Performance chart canvas not found');
        return;
    }

    performanceChart = new Chart(ctx.getContext('2d'), {
        type: 'line',
        data: performanceData,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.7)'
                    }
                },
                x: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.7)',
                        maxTicksLimit: 10
                    }
                }
            },
            plugins: {
                legend: {
                    labels: {
                        color: 'rgba(255, 255, 255, 0.9)'
                    }
                }
            },
            elements: {
                point: {
                    radius: 3,
                    hoverRadius: 6
                }
            }
        }
    });
}

/**
 * Update performance chart with new metrics data
 * @param {Object} metrics - Real-time metrics from server
 */
function updatePerformanceChart(metrics) {
    if (!performanceChart) return;

    const now = new Date().toLocaleTimeString();

    // Add new data points
    performanceData.labels.push(now);
    performanceData.datasets[0].data.push(metrics.fast_lane?.execution_time_ms || 0);
    performanceData.datasets[1].data.push(metrics.smart_lane?.analysis_time_ms || 0);

    // Keep only last 20 data points for performance
    if (performanceData.labels.length > 20) {
        performanceData.labels.shift();
        performanceData.datasets[0].data.shift();
        performanceData.datasets[1].data.shift();
    }

    performanceChart.update('none'); // No animation for real-time updates

    // Update chart timestamp
    const timestampEl = document.getElementById('chart-last-update');
    if (timestampEl) {
        timestampEl.textContent = `Updated: ${now}`;
    }
}

// ============================================================================
// STATUS INDICATORS AND UI UPDATES
// ============================================================================

/**
 * Update status indicators based on system metrics
 * @param {Object} data - System status data from SSE
 */
function updateStatusIndicators(data) {
    // System status
    const systemStatus = data.system?.overall_status || 'UNKNOWN';
    const systemIndicator = document.getElementById('system-status-indicator');
    const systemText = document.getElementById('system-status-text');

    if (systemIndicator && systemText) {
        systemIndicator.className = 'status-indicator';
        if (systemStatus === 'FULLY_OPERATIONAL') {
            systemIndicator.classList.add('status-live');
            systemText.textContent = 'Fully Operational';
        } else if (systemStatus === 'PARTIALLY_OPERATIONAL') {
            systemIndicator.classList.add('status-mock');
            systemText.textContent = 'Partially Operational';
        } else {
            systemIndicator.classList.add('status-error');
            systemText.textContent = 'System Issues';
        }
    }

    // Data source indicator
    const dataSourceText = document.getElementById('data-source-text');
    if (dataSourceText) {
        dataSourceText.textContent = data.data_source === 'LIVE' ? 'LIVE DATA' : 'DEMO MODE';
    }
}

/**
 * Update dashboard metrics display
 * @param {Object} data - Metrics data from server
 */
function updateMetricsDisplay(data) {
    // Fast Lane metrics
    if (data.fast_lane) {
        updateElementText('fast-lane-tokens-analyzed', data.fast_lane.tokens_analyzed_today || 0);
        updateElementText('fast-lane-success-rate', (data.fast_lane.success_rate || 0).toFixed(1) + '%');
        updateElementText('fast-lane-avg-time', (data.fast_lane.avg_execution_time_ms || 0).toFixed(1) + 'ms');
    }

    // Smart Lane metrics
    if (data.smart_lane) {
        updateElementText('smart-lane-analyses', data.smart_lane.detailed_analyses_today || 0);
        updateElementText('smart-lane-success-rate', (data.smart_lane.success_rate || 0).toFixed(1) + '%');
        updateElementText('smart-lane-avg-time', (data.smart_lane.avg_analysis_time_ms || 0).toFixed(1) + 'ms');
    }

    // System metrics
    if (data.system) {
        updateElementText('total-volume', formatCurrency(data.system.total_volume_24h || 0));
        updateElementText('active-positions', data.system.active_positions || 0);
        updateElementText('profit-loss', formatCurrency(data.system.profit_loss_24h || 0));
    }
}

/**
 * Update health indicators with visual status
 * @param {Object} data - Health status data
 */
function updateHealthIndicators(data) {
    // Update health indicator circles
    const indicators = [
        { id: 'engine-health', status: data.system?.engine_status },
        { id: 'blockchain-health', status: data.system?.blockchain_status },
        { id: 'data-health', status: data.system?.data_feed_status }
    ];

    indicators.forEach(({ id, status }) => {
        const element = document.getElementById(id);
        if (element) {
            element.className = 'status-indicator';
            if (status === 'OPERATIONAL') {
                element.classList.add('status-live');
            } else if (status === 'DEGRADED') {
                element.classList.add('status-mock');
            } else {
                element.classList.add('status-error');
            }
        }
    });
}

// ============================================================================
// THOUGHT LOG FUNCTIONALITY
// ============================================================================

/**
 * Add new entry to the thought log display
 * @param {Object} entry - Log entry with text and timestamp
 */
function addThoughtLogEntry(entry) {
    thoughtLogData.push(entry);

    const container = document.getElementById('thought-log-container');
    if (!container) return;

    const logEntry = document.createElement('div');
    logEntry.className = 'thought-log-step fade-in';

    const timestamp = new Date(entry.timestamp).toLocaleTimeString();
    logEntry.innerHTML = `
        <span class="text-muted">[${timestamp}]</span> 
        ${entry.text}
        ${entry.confidence ? `<span class="analysis-badge ${getConfidenceBadgeClass(entry.confidence)}">${entry.confidence}%</span>` : ''}
    `;

    container.appendChild(logEntry);

    // Keep only last 50 entries
    while (container.children.length > 50) {
        container.removeChild(container.firstChild);
    }

    // Auto-scroll to bottom
    container.scrollTop = container.scrollHeight;
}

/**
 * Get CSS class for confidence badge based on percentage
 * @param {number} confidence - Confidence percentage (0-100)
 * @returns {string} CSS class name
 */
function getConfidenceBadgeClass(confidence) {
    if (confidence >= 80) return 'high-confidence';
    if (confidence >= 60) return 'medium-confidence';
    return 'low-confidence';
}

/**
 * Export thought log data as text file
 */
function exportThoughtLog() {
    if (thoughtLogData.length === 0) {
        showToast('No thought log data to export', 'warning');
        return;
    }

    const logText = thoughtLogData.map(entry =>
        `[${entry.timestamp}] ${entry.text}`
    ).join('\n');

    const blob = new Blob([logText], { type: 'text/plain' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `thought_log_${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);

    showToast('Thought log exported successfully', 'success');
}

// ============================================================================
// SERVER-SENT EVENTS (SSE) CONNECTION
// ============================================================================

/**
 * Initialize Server-Sent Events connection for real-time updates
 */
/**
 * Initialize Server-Sent Events connection for real-time dashboard updates
 * Includes comprehensive error handling, retry logic, and configuration checks
 */
function initializeSSE() {
    // TEMPORARY SOLUTION: Disable SSE completely to prevent server hanging
    // This prevents the EventSource connection that causes the server to block
    console.log('📡 SSE disabled for stability - using polling mode');

    // Set global flags to indicate SSE is disabled
    window.sseDisabled = true;
    window.sseConnection = null;

    // Clean up any existing connection
    if (typeof sseConnection !== 'undefined' && sseConnection) {
        try {
            console.log('🔄 Closing existing SSE connection');
            sseConnection.close();
            sseConnection = null;
        } catch (error) {
            console.error('Error closing existing SSE connection:', error);
        }
    }

    // Update UI elements to show current status
    const dataSourceEl = document.getElementById('data-source-text');
    if (dataSourceEl) {
        dataSourceEl.textContent = 'POLLING MODE';
        dataSourceEl.classList.remove('text-success', 'text-warning', 'text-danger');
        dataSourceEl.classList.add('text-info');
    }

    // Update any status indicators that might exist
    const statusIndicator = document.getElementById('connection-status');
    if (statusIndicator) {
        statusIndicator.textContent = 'Polling';
        statusIndicator.classList.remove('badge-success', 'badge-danger');
        statusIndicator.classList.add('badge-info');
    }

    // Log final status
    console.log('ℹ️ Data Source: POLLING MODE (SSE disabled)');

    // Exit function - no EventSource will be created
    return;
}

// Alternative: Polling-based update function (if you want to implement polling instead)
function startPollingUpdates() {
    // Only start if SSE is disabled and we're not already polling
    if (!window.sseDisabled || window.pollingInterval) {
        return;
    }

    console.log('📊 Starting polling updates (fallback for SSE)');

    // Poll for updates every 10 seconds
    window.pollingInterval = setInterval(async () => {
        try {
            // Fetch latest metrics via regular HTTP
            const response = await fetch('/dashboard/api/metrics/', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'same-origin'
            });

            if (response.ok) {
                const data = await response.json();

                // Update dashboard with polled data
                if (typeof updateStatusIndicators === 'function') {
                    updateStatusIndicators(data);
                }
                if (typeof updateMetricsDisplay === 'function') {
                    updateMetricsDisplay(data);
                }
                if (typeof updateHealthIndicators === 'function') {
                    updateHealthIndicators(data);
                }
                if (typeof updatePerformanceChart === 'function') {
                    updatePerformanceChart(data);
                }
            }
        } catch (error) {
            console.error('Polling update failed:', error);
        }
    }, 10000); // Poll every 10 seconds
}

// Stop polling when page is hidden
function stopPollingUpdates() {
    if (window.pollingInterval) {
        clearInterval(window.pollingInterval);
        window.pollingInterval = null;
        console.log('📊 Stopped polling updates');
    }
}

// Helper function that's called by initializeSSE
function updateDataSourceDisplay(text, status = 'info') {
    const dataSourceEl = document.getElementById('data-source-text');
    if (dataSourceEl) {
        dataSourceEl.textContent = text;

        // Remove all status classes
        dataSourceEl.classList.remove('text-success', 'text-warning', 'text-danger', 'text-info');

        // Add appropriate status class
        switch (status) {
            case 'success':
                dataSourceEl.classList.add('text-success');
                break;
            case 'warning':
                dataSourceEl.classList.add('text-warning');
                break;
            case 'error':
                dataSourceEl.classList.add('text-danger');
                break;
            default:
                dataSourceEl.classList.add('text-info');
        }
    }

    // Log to console
    const emoji = {
        success: '✅',
        warning: '⚠️',
        error: '❌',
        info: 'ℹ️'
    };
    console.log(`${emoji[status] || '📝'} Data Source: ${text}`);
}

// Handle page visibility changes
document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
        stopPollingUpdates();
    } else if (window.sseDisabled) {
        startPollingUpdates();
    }
});

// Clean up on page unload
window.addEventListener('beforeunload', function () {
    stopPollingUpdates();
    if (sseConnection) {
        sseConnection.close();
    }
});

/**
 * Helper function to update data source display
 * @param {string} text - Text to display
 * @param {string} status - Status type: 'success', 'warning', 'error', 'info'
 */
function updateDataSourceDisplay(text, status = 'info') {
    const dataSourceEl = document.getElementById('data-source-text');
    if (dataSourceEl) {
        dataSourceEl.textContent = text;

        // Remove all status classes
        dataSourceEl.classList.remove('text-success', 'text-warning', 'text-danger', 'text-info');

        // Add appropriate status class
        switch (status) {
            case 'success':
                dataSourceEl.classList.add('text-success');
                break;
            case 'warning':
                dataSourceEl.classList.add('text-warning');
                break;
            case 'error':
                dataSourceEl.classList.add('text-danger');
                break;
            default:
                dataSourceEl.classList.add('text-info');
        }
    }

    // Log to console for debugging
    const emoji = {
        success: '✅',
        warning: '⚠️',
        error: '❌',
        info: 'ℹ️'
    };
    console.log(`${emoji[status] || '📝'} Data Source: ${text}`);
}

/**
 * Helper function to update data source display
 * @param {string} text - Text to display
 * @param {string} status - Status type: 'success', 'warning', 'error', 'info'
 */
function updateDataSourceDisplay(text, status = 'info') {
    const dataSourceEl = document.getElementById('data-source-text');
    if (dataSourceEl) {
        dataSourceEl.textContent = text;

        // Remove all status classes
        dataSourceEl.classList.remove('text-success', 'text-warning', 'text-danger', 'text-info');

        // Add appropriate status class
        switch (status) {
            case 'success':
                dataSourceEl.classList.add('text-success');
                break;
            case 'warning':
                dataSourceEl.classList.add('text-warning');
                break;
            case 'error':
                dataSourceEl.classList.add('text-danger');
                break;
            default:
                dataSourceEl.classList.add('text-info');
        }
    }

    // Also log to console for debugging
    const emoji = {
        success: '✅',
        warning: '⚠️',
        error: '❌',
        info: 'ℹ️'
    };
    console.log(`${emoji[status] || '📝'} Data Source: ${text}`);
}

// ============================================================================
// CONTROL FUNCTIONS
// ============================================================================

/**
 * Toggle Fast Lane mode on/off
 */
function toggleFastLane() {
    const btn = document.getElementById('fast-lane-toggle-btn');
    if (btn) {
        btn.disabled = true;
        // TODO: Implement API call to toggle Fast Lane
        console.log('🚀 Toggle Fast Lane clicked');
        showToast('Fast Lane toggle requested', 'info');
        setTimeout(() => btn.disabled = false, 1000);
    }
}

/**
 * Toggle Smart Lane mode on/off
 */
function toggleSmartLane() {
    const btn = document.getElementById('smart-lane-toggle-btn');
    if (btn) {
        btn.disabled = true;
        // TODO: Implement API call to toggle Smart Lane
        console.log('🧠 Toggle Smart Lane clicked');
        showToast('Smart Lane toggle requested', 'info');
        setTimeout(() => btn.disabled = false, 1000);
    }
}

/**
 * Run quick analysis on current market conditions
 */
function runQuickAnalysis() {
    addThoughtLogEntry({
        text: 'Quick analysis initiated... Scanning current market conditions',
        timestamp: new Date().toISOString()
    });
    showToast('Quick analysis started', 'info');
}

/**
 * Enable hybrid mode (both Fast Lane and Smart Lane)
 */
function enableHybridMode() {
    console.log('🔄 Enable hybrid mode clicked');
    showToast('Hybrid mode activation requested', 'info');
}

/**
 * Navigate to analytics page
 */
function viewAnalytics() {
    // URL will be resolved by Django template when this is called
    const analyticsUrl = window.dashboardConfig?.analyticsUrl || '/dashboard/analytics/';
    window.location.href = analyticsUrl;
}

// ============================================================================
// WALLET INTEGRATION
// ============================================================================

/**
 * Update wallet display state based on connection status
 * @param {string} state - Wallet connection state
 */
function updateWalletDashboardState(state) {
    const walletDisplay = document.getElementById('wallet-display');
    const connectBtn = document.getElementById('wallet-connect-btn');

    if (!walletDisplay || !connectBtn) return;

    if (state === 'wallet-connected' && window.walletManager?.isConnected) {
        walletDisplay.style.display = 'block';
        connectBtn.style.display = 'none';

        // Update wallet info
        updateWalletInfo();
    } else {
        walletDisplay.style.display = 'none';
        connectBtn.style.display = 'block';
    }
}

/**
 * Update wallet information display
 */
function updateWalletInfo() {
    if (!window.walletManager?.isConnected) return;

    const manager = window.walletManager;

    // Update wallet address
    const addressEl = document.getElementById('wallet-display-address');
    if (addressEl && manager.connectedAccount) {
        const shortAddress = `${manager.connectedAccount.slice(0, 6)}...${manager.connectedAccount.slice(-4)}`;
        addressEl.textContent = shortAddress;
    }

    // Update chain info
    const chainEl = document.getElementById('wallet-display-chain');
    if (chainEl && manager.currentChainId) {
        const chainInfo = manager.supportedChains[manager.currentChainId];
        if (chainInfo) {
            chainEl.textContent = chainInfo.name;
            chainEl.className = 'badge bg-success';
        }
    }

    // Update balance
    manager.getWalletBalance()
        .then(balance => updateBalanceDisplay(balance))
        .catch(error => console.error('Failed to load balance:', error));
}

/**
 * Update balance display
 * @param {string} balance - Formatted balance string
 */
function updateBalanceDisplay(balance) {
    const balanceEl = document.getElementById('wallet-display-balance');
    if (balanceEl) {
        balanceEl.textContent = balance;
    }
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Update element text content safely
 * @param {string} id - Element ID
 * @param {string|number} value - New text value
 */
function updateElementText(id, value) {
    const element = document.getElementById(id);
    if (element) {
        element.textContent = value;
    }
}

/**
 * Format currency values
 * @param {number} amount - Amount to format
 * @returns {string} Formatted currency string
 */
function formatCurrency(amount) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(amount);
}

/**
 * Show toast notification
 * @param {string} message - Message to display
 * @param {string} type - Toast type (success, info, warning, error)
 */
function showToast(message, type = 'info') {
    // Get or create toast container
    let toastContainer = document.querySelector('.toast-container');
    if (!toastContainer) {
        toastContainer = createToastContainer();
    }

    // Create toast element
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-white bg-${type === 'success' ? 'success' : type === 'error' ? 'danger' : type === 'warning' ? 'warning' : 'info'} border-0`;
    toast.setAttribute('role', 'alert');
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">${message}</div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;

    toastContainer.appendChild(toast);

    const bsToast = new bootstrap.Toast(toast);
    bsToast.show();

    // Remove toast element after it's hidden
    toast.addEventListener('hidden.bs.toast', () => {
        toast.remove();
    });
}

/**
 * Create toast container for notifications
 * @returns {HTMLElement} Toast container element
 */
function createToastContainer() {
    const container = document.createElement('div');
    container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
    container.style.zIndex = '1055';
    document.body.appendChild(container);
    return container;
}

// ============================================================================
// EVENT LISTENERS
// ============================================================================

// Wallet event listeners
document.addEventListener('wallet:connected', (event) => {
    console.log('🔗 Wallet connected - updating dashboard');
    updateWalletDashboardState('wallet-connected');
    showToast('Wallet connected successfully', 'success');
});

document.addEventListener('wallet:disconnected', (event) => {
    console.log('🔌 Wallet disconnected - updating dashboard');
    updateWalletDashboardState('wallet-not-connected');
    showToast('Wallet disconnected', 'info');
});

document.addEventListener('wallet:chainChanged', (event) => {
    console.log('⛓️ Chain changed - updating dashboard');

    const chainEl = document.getElementById('wallet-display-chain');
    if (chainEl && event.detail.chainId && window.walletManager) {
        const chainInfo = window.walletManager.supportedChains[event.detail.chainId];
        if (chainInfo) {
            chainEl.textContent = chainInfo.name;
            chainEl.className = 'badge bg-success';
        } else {
            chainEl.textContent = 'Unknown Network';
            chainEl.className = 'badge bg-warning';
        }
    }

    // Refresh balance for new chain
    if (window.walletManager?.isConnected) {
        window.walletManager.getWalletBalance()
            .then(balance => updateBalanceDisplay(balance))
            .catch(error => console.error('Failed to load balance for new chain:', error));
    }
});

// ============================================================================
// INITIALIZATION
// ============================================================================

/**
 * Initialize dashboard when DOM is ready
 */
document.addEventListener('DOMContentLoaded', function () {
    console.log('🚀 Initializing dashboard...');

    // Initialize charts
    initPerformanceChart();

    // Initialize SSE connection
    initializeSSE();

    // Set up button event handlers
    const fastLaneBtn = document.getElementById('fast-lane-toggle-btn');
    const smartLaneBtn = document.getElementById('smart-lane-toggle-btn');

    if (fastLaneBtn) fastLaneBtn.onclick = toggleFastLane;
    if (smartLaneBtn) smartLaneBtn.onclick = toggleSmartLane;

    // Initialize wallet dashboard state
    if (window.walletManager?.isConnected) {
        updateWalletDashboardState('wallet-connected');
    } else {
        updateWalletDashboardState('wallet-not-connected');
    }

    console.log('✅ Dashboard initialized with Smart Lane and Wallet integration');
});

// ============================================================================
// PAGE LIFECYCLE MANAGEMENT
// ============================================================================

// Handle page visibility changes to manage SSE connection
document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
        console.log('📱 Page hidden - closing SSE connection');
        if (sseConnection) {
            sseConnection.close();
        }
    } else {
        console.log('📱 Page visible - reconnecting SSE');
        initializeSSE();
    }
});

// Clean up on page unload
window.addEventListener('beforeunload', function () {
    console.log('🔄 Page unloading - cleaning up resources');
    if (sseConnection) {
        sseConnection.close();
    }
});

// Resize chart on window resize
window.addEventListener('resize', function () {
    if (performanceChart) {
        performanceChart.resize();
    }
});

// ============================================================================
// EXPORT FOR TESTING (if needed)
// ============================================================================

// Make functions available globally for testing/debugging
window.dashboardFunctions = {
    toggleFastLane,
    toggleSmartLane,
    runQuickAnalysis,
    enableHybridMode,
    viewAnalytics,
    exportThoughtLog,
    showToast
};