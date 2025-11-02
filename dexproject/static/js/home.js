/**
 * Dashboard Home Page JavaScript
 * 
 * Enhanced with interactive trading charts for Phase 3
 * Handles real-time updates, chart management, WebSocket/SSE connections,
 * and interactive dashboard functionality
 * 
 * File: dexproject/static/js/home.js
 */

// ============================================================================
// GLOBAL VARIABLES AND STATE
// ============================================================================

let performanceChart = null;
let priceChart = null;
let volumeChart = null;
let liquidityChart = null;
let sseConnection = null;
let wsConnection = null;
let thoughtLogData = [];
let recentAnalysesData = [];
let priceHistory = [];
let volumeHistory = [];

// Chart update intervals
let chartUpdateInterval = null;
const CHART_UPDATE_INTERVAL = 5000; // 5 seconds

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

// Price chart data structure (candlestick)
const priceChartData = {
    labels: [],
    datasets: [{
        label: 'Token Price',
        data: [],
        borderColor: '#8b5cf6',
        backgroundColor: 'rgba(139, 92, 246, 0.1)',
        borderWidth: 2,
        tension: 0.1,
        pointRadius: 0,
        pointHoverRadius: 6,
        pointBackgroundColor: '#8b5cf6',
        pointBorderColor: '#fff',
        pointBorderWidth: 2
    }]
};

// Volume chart data structure
const volumeChartData = {
    labels: [],
    datasets: [{
        label: 'Trading Volume',
        data: [],
        backgroundColor: 'rgba(34, 197, 94, 0.5)',
        borderColor: '#22c55e',
        borderWidth: 1
    }]
};

// ============================================================================
// ENHANCED CHART INITIALIZATION
// ============================================================================

/**
 * Initialize all dashboard charts
 */
function initializeAllCharts() {
    console.log('📊 Initializing interactive charts...');

    initPerformanceChart();
    initPriceChart();
    initVolumeChart();
    initLiquidityChart();

    // Enable chart interactions
    enableChartInteractions();

    console.log('✅ All charts initialized');
}

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
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: {
                    labels: {
                        color: 'rgba(255, 255, 255, 0.9)',
                        usePointStyle: true,
                        padding: 15
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(17, 24, 39, 0.9)',
                    titleColor: '#fff',
                    bodyColor: '#fff',
                    borderColor: 'rgba(255, 255, 255, 0.1)',
                    borderWidth: 1,
                    padding: 12,
                    displayColors: true,
                    callbacks: {
                        label: function (context) {
                            return context.dataset.label + ': ' + context.parsed.y.toFixed(2) + 'ms';
                        }
                    }
                },
                zoom: {
                    zoom: {
                        wheel: {
                            enabled: true,
                        },
                        pinch: {
                            enabled: true
                        },
                        mode: 'x',
                    },
                    pan: {
                        enabled: true,
                        mode: 'x',
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.7)',
                        callback: function (value) {
                            return value + 'ms';
                        }
                    }
                },
                x: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.7)',
                        maxTicksLimit: 10,
                        maxRotation: 0
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
 * Initialize price chart with candlestick support
 */
function initPriceChart() {
    const ctx = document.getElementById('priceChart');
    if (!ctx) {
        // Create price chart container if it doesn't exist
        const chartContainer = document.querySelector('.chart-container');
        if (chartContainer) {
            const canvas = document.createElement('canvas');
            canvas.id = 'priceChart';
            canvas.height = 300;
            chartContainer.appendChild(canvas);
        } else {
            console.warn('Price chart canvas not found');
            return;
        }
    }

    const priceCtx = document.getElementById('priceChart');
    if (!priceCtx) return;

    priceChart = new Chart(priceCtx.getContext('2d'), {
        type: 'line',
        data: priceChartData,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: {
                    display: true,
                    labels: {
                        color: 'rgba(255, 255, 255, 0.9)'
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(17, 24, 39, 0.9)',
                    callbacks: {
                        label: function (context) {
                            const price = context.parsed.y;
                            return `Price: $${price.toFixed(6)}`;
                        },
                        afterLabel: function (context) {
                            const index = context.dataIndex;
                            if (index > 0) {
                                const prevPrice = context.dataset.data[index - 1];
                                const change = ((context.parsed.y - prevPrice) / prevPrice * 100).toFixed(2);
                                return `Change: ${change > 0 ? '+' : ''}${change}%`;
                            }
                            return '';
                        }
                    }
                }
            },
            scales: {
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.7)',
                        callback: function (value) {
                            return '$' + value.toFixed(4);
                        }
                    }
                },
                x: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.7)',
                        maxTicksLimit: 8
                    }
                }
            }
        }
    });
}

/**
 * Initialize volume chart
 */
function initVolumeChart() {
    const ctx = document.getElementById('volumeChart');
    if (!ctx) {
        console.warn('Volume chart canvas not found');
        return;
    }

    volumeChart = new Chart(ctx.getContext('2d'), {
        type: 'bar',
        data: volumeChartData,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    labels: {
                        color: 'rgba(255, 255, 255, 0.9)'
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            const volume = context.parsed.y;
                            return `Volume: $${formatLargeNumber(volume)}`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.7)',
                        callback: function (value) {
                            return '$' + formatLargeNumber(value);
                        }
                    }
                },
                x: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.7)',
                        maxTicksLimit: 8
                    }
                }
            }
        }
    });
}

/**
 * Initialize liquidity depth chart
 */
function initLiquidityChart() {
    const ctx = document.getElementById('liquidityChart');
    if (!ctx) {
        console.warn('Liquidity chart canvas not found');
        return;
    }

    liquidityChart = new Chart(ctx.getContext('2d'), {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Buy Orders',
                    data: [],
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.2)',
                    fill: '+1',
                    stepped: true
                },
                {
                    label: 'Sell Orders',
                    data: [],
                    borderColor: '#ef4444',
                    backgroundColor: 'rgba(239, 68, 68, 0.2)',
                    fill: '-1',
                    stepped: true
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                legend: {
                    display: true,
                    labels: {
                        color: 'rgba(255, 255, 255, 0.9)'
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            return `${context.dataset.label}: $${formatLargeNumber(context.parsed.y)}`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.7)',
                        callback: function (value) {
                            return '$' + formatLargeNumber(value);
                        }
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Price',
                        color: 'rgba(255, 255, 255, 0.7)'
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.7)'
                    }
                }
            }
        }
    });
}

// ============================================================================
// CHART INTERACTION FEATURES
// ============================================================================

/**
 * Enable interactive features for all charts
 */
function enableChartInteractions() {
    // Add reset zoom buttons
    addResetZoomButtons();

    // Add export functionality
    addChartExportButtons();

    // Add time range selector
    addTimeRangeSelector();

    // Enable crosshair cursor
    enableCrosshairCursor();
}

/**
 * Add reset zoom buttons to charts
 */
function addResetZoomButtons() {
    const charts = [
        { chart: performanceChart, id: 'performanceChart' },
        { chart: priceChart, id: 'priceChart' },
        { chart: volumeChart, id: 'volumeChart' }
    ];

    charts.forEach(({ chart, id }) => {
        if (!chart) return;

        const canvas = document.getElementById(id);
        if (!canvas) return;

        const container = canvas.parentElement;
        const resetBtn = document.createElement('button');
        resetBtn.className = 'btn btn-sm btn-outline-light chart-reset-btn';
        resetBtn.innerHTML = '<i class="bi bi-zoom-out"></i> Reset';
        resetBtn.style.position = 'absolute';
        resetBtn.style.top = '10px';
        resetBtn.style.right = '10px';
        resetBtn.style.zIndex = '10';
        resetBtn.style.display = 'none';

        resetBtn.onclick = () => {
            if (chart.resetZoom) {
                chart.resetZoom();
                resetBtn.style.display = 'none';
            }
        };

        container.appendChild(resetBtn);

        // Show button when zoomed
        canvas.addEventListener('wheel', () => {
            setTimeout(() => {
                if (chart.isZoomedOrPanned && chart.isZoomedOrPanned()) {
                    resetBtn.style.display = 'block';
                }
            }, 100);
        });
    });
}

/**
 * Add export buttons to charts
 */
function addChartExportButtons() {
    const charts = [
        { chart: performanceChart, id: 'performanceChart', name: 'performance' },
        { chart: priceChart, id: 'priceChart', name: 'price' },
        { chart: volumeChart, id: 'volumeChart', name: 'volume' }
    ];

    charts.forEach(({ chart, id, name }) => {
        if (!chart) return;

        const canvas = document.getElementById(id);
        if (!canvas) return;

        const container = canvas.parentElement;
        const exportBtn = document.createElement('button');
        exportBtn.className = 'btn btn-sm btn-outline-light chart-export-btn';
        exportBtn.innerHTML = '<i class="bi bi-download"></i>';
        exportBtn.style.position = 'absolute';
        exportBtn.style.top = '10px';
        exportBtn.style.right = '60px';
        exportBtn.style.zIndex = '10';
        exportBtn.title = 'Export chart';

        exportBtn.onclick = () => {
            exportChart(chart, name);
        };

        container.appendChild(exportBtn);
    });
}

/**
 * Export chart as image
 */
function exportChart(chart, name) {
    if (!chart) return;

    const url = chart.toBase64Image();
    const a = document.createElement('a');
    a.href = url;
    a.download = `${name}_chart_${new Date().toISOString().slice(0, 10)}.png`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    showToast(`${name} chart exported successfully`, 'success');
}

/**
 * Add time range selector for charts
 */
function addTimeRangeSelector() {
    const selector = document.getElementById('chart-time-range');
    if (!selector) {
        console.warn('Time range selector not found');
        return;
    }

    selector.addEventListener('change', (e) => {
        const range = e.target.value;
        updateChartsTimeRange(range);
    });
}

/**
 * Update charts based on selected time range
 */
function updateChartsTimeRange(range) {
    console.log(`📊 Updating charts to ${range} time range`);

    // Map range to data points
    const dataPoints = {
        '1h': 12,   // 5-minute intervals
        '4h': 16,   // 15-minute intervals  
        '1d': 24,   // 1-hour intervals
        '1w': 28,   // 6-hour intervals
        '1m': 30    // 1-day intervals
    };

    const maxPoints = dataPoints[range] || 20;

    // Update all charts with new time range
    [performanceChart, priceChart, volumeChart].forEach(chart => {
        if (chart) {
            chart.options.scales.x.ticks.maxTicksLimit = Math.min(maxPoints, 10);
            chart.update();
        }
    });

    showToast(`Charts updated to ${range} view`, 'info');
}

/**
 * Enable crosshair cursor for better chart interaction
 */
function enableCrosshairCursor() {
    const chartCanvases = ['performanceChart', 'priceChart', 'volumeChart'];

    chartCanvases.forEach(id => {
        const canvas = document.getElementById(id);
        if (canvas) {
            canvas.style.cursor = 'crosshair';
        }
    });
}

// ============================================================================
// ENHANCED CHART UPDATE FUNCTIONS
// ============================================================================

/**
 * Update performance chart with new metrics data
 * @param {Object} metrics - Real-time metrics from server
 */
function updatePerformanceChart(metrics) {
    if (!performanceChart) return;

    const now = new Date().toLocaleTimeString();

    // Add new data points with animation
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
    updateChartTimestamp('chart-last-update', now);
}

/**
 * Update price chart with new price data
 * @param {Object} priceData - Price data from server
 */
function updatePriceChart(priceData) {
    if (!priceChart) return;

    const now = new Date().toLocaleTimeString();

    priceChartData.labels.push(now);
    priceChartData.datasets[0].data.push(priceData.price || 0);

    // Maintain sliding window
    if (priceChartData.labels.length > 30) {
        priceChartData.labels.shift();
        priceChartData.datasets[0].data.shift();
    }

    priceChart.update();
    updateChartTimestamp('price-chart-update', now);
}

/**
 * Update volume chart with new volume data
 * @param {Object} volumeData - Volume data from server
 */
function updateVolumeChart(volumeData) {
    if (!volumeChart) return;

    const now = new Date().toLocaleTimeString();

    volumeChartData.labels.push(now);
    volumeChartData.datasets[0].data.push(volumeData.volume || 0);

    // Maintain sliding window
    if (volumeChartData.labels.length > 20) {
        volumeChartData.labels.shift();
        volumeChartData.datasets[0].data.shift();
    }

    volumeChart.update();
    updateChartTimestamp('volume-chart-update', now);
}

/**
 * Update chart timestamp display
 */
function updateChartTimestamp(elementId, timestamp) {
    const element = document.getElementById(elementId);
    if (element) {
        element.textContent = `Updated: ${timestamp}`;
        element.classList.add('pulse-animation');
        setTimeout(() => element.classList.remove('pulse-animation'), 1000);
    }
}

// ============================================================================
// WEBSOCKET CONNECTION FOR REAL-TIME CHARTS
// ============================================================================

/**
 * Initialize WebSocket connection for real-time chart updates
 */
function initializeWebSocketForCharts() {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/dashboard/metrics/`;

    try {
        wsConnection = new WebSocket(wsUrl);

        wsConnection.onopen = () => {
            console.log('📊 Chart WebSocket connected');
            showToast('Real-time chart updates connected', 'success', 2000);
        };

        wsConnection.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleChartWebSocketMessage(data);
            } catch (error) {
                console.error('Error parsing chart WebSocket message:', error);
            }
        };

        wsConnection.onerror = (error) => {
            console.error('Chart WebSocket error:', error);
        };

        wsConnection.onclose = () => {
            console.log('Chart WebSocket disconnected');
            // Attempt reconnection after 5 seconds
            setTimeout(() => initializeWebSocketForCharts(), 5000);
        };

    } catch (error) {
        console.error('Failed to initialize chart WebSocket:', error);
        // Fall back to polling
        startChartPolling();
    }
}

/**
 * Handle WebSocket messages for chart updates
 */
function handleChartWebSocketMessage(data) {
    switch (data.type) {
        case 'price_update':
            updatePriceChart(data.data);
            break;
        case 'volume_update':
            updateVolumeChart(data.data);
            break;
        case 'performance_update':
            updatePerformanceChart(data.data);
            break;
        case 'liquidity_update':
            updateLiquidityChart(data.data);
            break;
        default:
            console.warn('Unknown chart message type:', data.type);
    }
}

/**
 * Start polling for chart updates (fallback)
 */
function startChartPolling() {
    if (chartUpdateInterval) return;

    console.log('📊 Starting chart polling (fallback mode)');

    chartUpdateInterval = setInterval(async () => {
        try {
            const response = await fetch('/dashboard/api/chart-data/', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'same-origin'
            });

            if (response.ok) {
                const data = await response.json();
                updateAllCharts(data);
            }
        } catch (error) {
            console.error('Chart polling error:', error);
        }
    }, CHART_UPDATE_INTERVAL);
}

/**
 * Update all charts with polled data
 */
function updateAllCharts(data) {
    if (data.performance) updatePerformanceChart(data.performance);
    if (data.price) updatePriceChart(data.price);
    if (data.volume) updateVolumeChart(data.volume);
    if (data.liquidity) updateLiquidityChart(data.liquidity);
}

// ============================================================================
// MISSING FUNCTIONS - IMPLEMENTED
// ============================================================================

/**
 * Update liquidity chart with new data
 */
function updateLiquidityChart(liquidityData) {
    if (!liquidityChart) return;

    if (liquidityData.buy_orders && liquidityData.sell_orders) {
        liquidityChart.data.labels = liquidityData.price_levels || [];
        liquidityChart.data.datasets[0].data = liquidityData.buy_orders;
        liquidityChart.data.datasets[1].data = liquidityData.sell_orders;
        liquidityChart.update();
    }
}

/**
 * Show toast notification
 */
function showToast(message, type = 'info', duration = 3000) {
    // Create toast container if it doesn't exist
    let toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'toast-container';
        toastContainer.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 9999;
        `;
        document.body.appendChild(toastContainer);
    }

    // Create toast element
    const toast = document.createElement('div');
    toast.className = `alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show`;
    toast.style.cssText = `
        min-width: 250px;
        margin-bottom: 10px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    `;
    toast.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;

    toastContainer.appendChild(toast);

    // Auto-remove after duration
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 150);
    }, duration);
}

/**
 * Update data source display indicator
 */
function updateDataSourceDisplay(status, type = 'info') {
    const indicator = document.getElementById('data-source-indicator');
    if (!indicator) return;

    const colors = {
        success: '#10b981',
        error: '#ef4444',
        warning: '#f59e0b',
        info: '#3b82f6'
    };

    indicator.textContent = status;
    indicator.style.color = colors[type] || colors.info;

    // Add pulse animation for live data
    if (type === 'success') {
        indicator.classList.add('pulse-animation');
        setTimeout(() => indicator.classList.remove('pulse-animation'), 1000);
    }
}

/**
 * Update wallet dashboard state
 */
function updateWalletDashboardState(state) {
    const walletStatus = document.getElementById('wallet-status');
    const walletAddress = document.getElementById('wallet-address');
    const walletBalance = document.getElementById('wallet-balance');

    if (state === 'wallet-connected' && window.walletManager) {
        if (walletStatus) {
            walletStatus.innerHTML = '<i class="bi bi-check-circle-fill text-success"></i> Connected';
        }
        if (walletAddress && window.walletManager.address) {
            const shortAddress = window.walletManager.address.slice(0, 6) + '...' + window.walletManager.address.slice(-4);
            walletAddress.textContent = shortAddress;
        }
        if (walletBalance && window.walletManager.balance) {
            walletBalance.textContent = `${parseFloat(window.walletManager.balance).toFixed(4)} ETH`;
        }
    } else {
        if (walletStatus) {
            walletStatus.innerHTML = '<i class="bi bi-x-circle-fill text-danger"></i> Not Connected';
        }
        if (walletAddress) walletAddress.textContent = 'N/A';
        if (walletBalance) walletBalance.textContent = 'N/A';
    }
}

/**
 * Update metrics display on dashboard
 */
function updateMetricsDisplay(metrics) {
    // Update fast lane metrics
    if (metrics.fast_lane) {
        updateElement('fast-lane-speed', `${metrics.fast_lane.execution_time_ms.toFixed(2)}ms`);
        updateElement('fast-lane-success', `${metrics.fast_lane.success_rate.toFixed(1)}%`);
        updateElement('fast-lane-trades', metrics.fast_lane.total_trades);
    }

    // Update smart lane metrics
    if (metrics.smart_lane) {
        updateElement('smart-lane-speed', `${metrics.smart_lane.analysis_time_ms.toFixed(2)}ms`);
        updateElement('smart-lane-accuracy', `${metrics.smart_lane.accuracy_rate.toFixed(1)}%`);
        updateElement('smart-lane-analysis', metrics.smart_lane.total_analyses);
    }

    // Update overall metrics
    if (metrics.overall) {
        updateElement('total-profit', `$${metrics.overall.total_profit.toFixed(2)}`);
        updateElement('win-rate', `${metrics.overall.win_rate.toFixed(1)}%`);
        updateElement('active-trades', metrics.overall.active_trades);
    }
}

/**
 * Update status indicators
 */
function updateStatusIndicators(status) {
    // Update fast lane status
    const fastLaneIndicator = document.getElementById('fast-lane-status');
    if (fastLaneIndicator) {
        const isActive = status.fast_lane?.active;
        fastLaneIndicator.innerHTML = isActive
            ? '<span class="badge bg-success">Active</span>'
            : '<span class="badge bg-secondary">Inactive</span>';
    }

    // Update smart lane status
    const smartLaneIndicator = document.getElementById('smart-lane-status');
    if (smartLaneIndicator) {
        const isActive = status.smart_lane?.active;
        smartLaneIndicator.innerHTML = isActive
            ? '<span class="badge bg-success">Active</span>'
            : '<span class="badge bg-secondary">Inactive</span>';
    }

    // Update system status
    const systemStatus = document.getElementById('system-status');
    if (systemStatus) {
        const statusClass = status.system === 'healthy' ? 'success' : 'warning';
        systemStatus.innerHTML = `<span class="badge bg-${statusClass}">${status.system || 'Unknown'}</span>`;
    }
}

/**
 * Update health indicators
 */
function updateHealthIndicators(health) {
    // Update RPC health
    updateHealthBadge('rpc-health', health.rpc_status, health.rpc_latency);

    // Update database health
    updateHealthBadge('db-health', health.db_status, health.db_latency);

    // Update Redis health
    updateHealthBadge('redis-health', health.redis_status, health.redis_latency);

    // Update overall system health
    const overallHealth = document.getElementById('overall-health');
    if (overallHealth) {
        const allHealthy = health.rpc_status === 'healthy' &&
            health.db_status === 'healthy' &&
            health.redis_status === 'healthy';

        overallHealth.innerHTML = allHealthy
            ? '<i class="bi bi-heart-fill text-success"></i> System Healthy'
            : '<i class="bi bi-exclamation-triangle-fill text-warning"></i> Degraded';
    }
}

/**
 * Helper to update health badge
 */
function updateHealthBadge(elementId, status, latency) {
    const element = document.getElementById(elementId);
    if (!element) return;

    const isHealthy = status === 'healthy';
    const badgeClass = isHealthy ? 'success' : 'danger';
    const icon = isHealthy ? 'check-circle-fill' : 'x-circle-fill';

    element.innerHTML = `
        <i class="bi bi-${icon} text-${badgeClass}"></i>
        ${status} ${latency ? `(${latency}ms)` : ''}
    `;
}

/**
 * Add thought log entry to dashboard
 */
function addThoughtLogEntry(thought) {
    const thoughtLogContainer = document.getElementById('thought-log-container');
    if (!thoughtLogContainer) return;

    // Add to data array
    thoughtLogData.unshift(thought);

    // Keep only last 20 entries
    if (thoughtLogData.length > 20) {
        thoughtLogData.pop();
    }

    // Create thought entry element
    const entry = document.createElement('div');
    entry.className = 'thought-log-entry mb-2 p-2 border-start border-3';
    entry.style.borderColor = getConfidenceColor(thought.confidence);

    entry.innerHTML = `
        <div class="d-flex justify-content-between align-items-start">
            <div class="flex-grow-1">
                <span class="badge ${getConfidenceBadgeClass(thought.confidence)} me-2">
                    ${thought.confidence}% confidence
                </span>
                <span class="badge bg-secondary">${thought.token_symbol}</span>
                <span class="text-muted small ms-2">${new Date(thought.timestamp).toLocaleTimeString()}</span>
            </div>
            <span class="badge ${getActionBadgeClass(thought.action)}">${thought.action}</span>
        </div>
        <p class="mb-0 mt-2 small">${thought.reasoning}</p>
    `;

    // Add to container (prepend)
    thoughtLogContainer.insertBefore(entry, thoughtLogContainer.firstChild);

    // Remove oldest if more than 10 visible
    while (thoughtLogContainer.children.length > 10) {
        thoughtLogContainer.removeChild(thoughtLogContainer.lastChild);
    }
}

/**
 * Get confidence badge class
 */
function getConfidenceBadgeClass(confidence) {
    if (confidence >= 80) return 'bg-success';
    if (confidence >= 60) return 'bg-info';
    if (confidence >= 40) return 'bg-warning';
    return 'bg-danger';
}

/**
 * Get confidence color
 */
function getConfidenceColor(confidence) {
    if (confidence >= 80) return '#10b981';
    if (confidence >= 60) return '#3b82f6';
    if (confidence >= 40) return '#f59e0b';
    return '#ef4444';
}

/**
 * Get action badge class
 */
function getActionBadgeClass(action) {
    switch (action?.toUpperCase()) {
        case 'BUY': return 'bg-success';
        case 'SELL': return 'bg-danger';
        case 'HOLD': return 'bg-info';
        case 'SKIP': return 'bg-secondary';
        default: return 'bg-secondary';
    }
}

/**
 * Toggle Fast Lane
 */
async function toggleFastLane() {
    const button = document.getElementById('fast-lane-toggle-btn');
    if (!button) return;

    const currentState = button.textContent.includes('Enable');
    const newState = currentState ? 'enable' : 'disable';

    try {
        button.disabled = true;
        button.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Processing...';

        const response = await fetch('/dashboard/api/fast-lane/toggle/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({ action: newState }),
            credentials: 'same-origin'
        });

        if (response.ok) {
            const data = await response.json();
            button.innerHTML = data.active ? 'Disable Fast Lane' : 'Enable Fast Lane';
            button.className = data.active ? 'btn btn-danger' : 'btn btn-success';
            showToast(`Fast Lane ${data.active ? 'enabled' : 'disabled'}`, 'success');
        } else {
            throw new Error('Failed to toggle Fast Lane');
        }
    } catch (error) {
        console.error('Error toggling Fast Lane:', error);
        showToast('Failed to toggle Fast Lane', 'error');
    } finally {
        button.disabled = false;
    }
}

/**
 * Toggle Smart Lane
 */
async function toggleSmartLane() {
    const button = document.getElementById('smart-lane-toggle-btn');
    if (!button) return;

    const currentState = button.textContent.includes('Enable');
    const newState = currentState ? 'enable' : 'disable';

    try {
        button.disabled = true;
        button.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Processing...';

        const response = await fetch('/dashboard/api/smart-lane/toggle/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({ action: newState }),
            credentials: 'same-origin'
        });

        if (response.ok) {
            const data = await response.json();
            button.innerHTML = data.active ? 'Disable Smart Lane' : 'Enable Smart Lane';
            button.className = data.active ? 'btn btn-danger' : 'btn btn-success';
            showToast(`Smart Lane ${data.active ? 'enabled' : 'disabled'}`, 'success');
        } else {
            throw new Error('Failed to toggle Smart Lane');
        }
    } catch (error) {
        console.error('Error toggling Smart Lane:', error);
        showToast('Failed to toggle Smart Lane', 'error');
    } finally {
        button.disabled = false;
    }
}

/**
 * Run quick analysis
 */
async function runQuickAnalysis() {
    showToast('Running quick market analysis...', 'info');

    try {
        const response = await fetch('/dashboard/api/quick-analysis/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            credentials: 'same-origin'
        });

        if (response.ok) {
            const data = await response.json();
            showAnalysisResults(data);
        } else {
            throw new Error('Analysis failed');
        }
    } catch (error) {
        console.error('Error running quick analysis:', error);
        showToast('Failed to run analysis', 'error');
    }
}

/**
 * Show analysis results in modal
 */
function showAnalysisResults(data) {
    const resultsHtml = `
        <div class="analysis-results">
            <h5>Market Analysis Results</h5>
            <div class="row">
                <div class="col-md-6">
                    <p><strong>Best Opportunity:</strong> ${data.best_token || 'None'}</p>
                    <p><strong>Confidence:</strong> ${data.confidence || 0}%</p>
                </div>
                <div class="col-md-6">
                    <p><strong>Market Sentiment:</strong> ${data.sentiment || 'Neutral'}</p>
                    <p><strong>Risk Level:</strong> ${data.risk_level || 'Unknown'}</p>
                </div>
            </div>
        </div>
    `;

    showToast('Analysis complete!', 'success');
    console.log('Analysis results:', data);
}

/**
 * Enable hybrid mode
 */
async function enableHybridMode() {
    showToast('Enabling hybrid mode...', 'info');

    try {
        const response = await fetch('/dashboard/api/hybrid-mode/enable/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            credentials: 'same-origin'
        });

        if (response.ok) {
            showToast('Hybrid mode enabled', 'success');
        } else {
            throw new Error('Failed to enable hybrid mode');
        }
    } catch (error) {
        console.error('Error enabling hybrid mode:', error);
        showToast('Failed to enable hybrid mode', 'error');
    }
}

/**
 * View analytics
 */
function viewAnalytics() {
    window.location.href = '/dashboard/analytics/';
}

/**
 * Export thought log
 */
function exportThoughtLog() {
    if (thoughtLogData.length === 0) {
        showToast('No thought log data to export', 'warning');
        return;
    }

    const dataStr = JSON.stringify(thoughtLogData, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(dataBlob);

    const a = document.createElement('a');
    a.href = url;
    a.download = `thought-log-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    showToast('Thought log exported successfully', 'success');
}

/**
 * Start polling for updates (fallback)
 */
function startPollingUpdates() {
    console.log('📊 Starting polling for dashboard updates');

    setInterval(async () => {
        try {
            const response = await fetch('/dashboard/api/status/', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'same-origin'
            });

            if (response.ok) {
                const data = await response.json();
                if (data.metrics) updateMetricsDisplay(data.metrics);
                if (data.status) updateStatusIndicators(data.status);
                if (data.health) updateHealthIndicators(data.health);
            }
        } catch (error) {
            console.error('Polling error:', error);
        }
    }, 10000); // Poll every 10 seconds
}

/**
 * Helper to update element text content
 */
function updateElement(id, value) {
    const element = document.getElementById(id);
    if (element) {
        element.textContent = value;
    }
}

/**
 * Get CSRF token from cookie
 */
function getCookie(name) {
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
// ENHANCED SSE CONNECTION
// ============================================================================

/**
 * Initialize Server-Sent Events with proper error handling
 */
function initializeSSE() {
    // Check if SSE is supported
    if (!window.EventSource) {
        console.warn('SSE not supported, using polling instead');
        startPollingUpdates();
        return;
    }

    const sseUrl = '/dashboard/sse/metrics/';

    try {
        console.log('📡 Initializing SSE connection...');
        sseConnection = new EventSource(sseUrl);

        sseConnection.onopen = () => {
            console.log('✅ SSE connection established');
            updateDataSourceDisplay('LIVE DATA', 'success');
        };

        sseConnection.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleSSEUpdate(data);
            } catch (error) {
                console.error('Error parsing SSE data:', error);
            }
        };

        sseConnection.onerror = (error) => {
            console.error('SSE error:', error);
            updateDataSourceDisplay('CONNECTION ERROR', 'error');

            // Auto-reconnect with exponential backoff
            setTimeout(() => {
                if (sseConnection.readyState === EventSource.CLOSED) {
                    console.log('Attempting SSE reconnection...');
                    initializeSSE();
                }
            }, 5000);
        };

    } catch (error) {
        console.error('Failed to initialize SSE:', error);
        startPollingUpdates();
    }
}

/**
 * Handle SSE update messages
 */
function handleSSEUpdate(data) {
    // Update various dashboard components
    if (data.metrics) {
        updateMetricsDisplay(data.metrics);
        updatePerformanceChart(data.metrics);
    }

    if (data.status) {
        updateStatusIndicators(data.status);
    }

    if (data.health) {
        updateHealthIndicators(data.health);
    }

    if (data.thought) {
        addThoughtLogEntry(data.thought);
    }
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Format large numbers for display
 */
function formatLargeNumber(num) {
    if (num >= 1e9) return (num / 1e9).toFixed(2) + 'B';
    if (num >= 1e6) return (num / 1e6).toFixed(2) + 'M';
    if (num >= 1e3) return (num / 1e3).toFixed(2) + 'K';
    return num.toFixed(2);
}

// ============================================================================
// INITIALIZATION
// ============================================================================

/**
 * Initialize dashboard when DOM is ready
 */
document.addEventListener('DOMContentLoaded', function () {
    console.log('🚀 Initializing enhanced dashboard with interactive charts...');

    // Initialize all charts
    initializeAllCharts();

    // Initialize WebSocket for real-time chart updates
    initializeWebSocketForCharts();

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

    console.log('✅ Enhanced dashboard initialized with Phase 3 interactive charts');
});

// ============================================================================
// EXPORT FOR TESTING
// ============================================================================

window.dashboardFunctions = {
    toggleFastLane,
    toggleSmartLane,
    runQuickAnalysis,
    enableHybridMode,
    viewAnalytics,
    exportThoughtLog,
    exportChart,
    updateChartsTimeRange,
    showToast
};