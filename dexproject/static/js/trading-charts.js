/**
 * Trading Charts Module - Phase 3 Interactive Charts
 * 
 * Handles initialization, updates, and interactions for all trading charts:
 * - Candlestick chart for price action
 * - Market depth chart for order book visualization
 * - Volume chart for buy/sell activity
 * - Portfolio performance chart
 * - Positions P&L chart
 * 
 * Features real-time WebSocket updates, chart export, timeframe selection,
 * zoom/pan interactions, and fullscreen mode.
 * 
 * File: dexproject/dashboard/static/js/trading-charts.js
 */

import { formatLargeNumber, safeJsonParse } from './trading-utils.js';

export class TradingChartsManager {
    /**
     * Initialize the charts manager
     * 
     * @param {string} csrfToken - CSRF token for API requests
     * @param {Function} showNotification - Notification display callback
     */
    constructor(csrfToken, showNotification) {
        this.csrfToken = csrfToken;
        this.showNotification = showNotification;

        // Chart instances
        this.charts = {
            candlestick: null,
            depth: null,
            volume: null,
            portfolio: null,
            positions: null
        };

        // Chart data storage
        this.candlestickData = [];
        this.volumeHistory = [];
        this.orderBookData = { bids: [], asks: [] };

        console.log('📊 TradingChartsManager initialized');
    }

    // =============================================================================
    // CHART INITIALIZATION
    // =============================================================================

    /**
     * Initialize all trading charts
     */
    initializeAllCharts() {
        console.log('📊 Initializing interactive trading charts...');

        this.initializeCandlestickChart();
        this.initializeDepthChart();
        this.initializeVolumeChart();
        this.initializePortfolioChart();
        this.initializePositionsChart();
        this.enableChartInteractions();

        console.log('✅ Trading charts initialized');
    }

    /**
     * Initialize candlestick chart for price action
     */
    initializeCandlestickChart() {
        const ctx = document.getElementById('candlestick-chart');
        if (!ctx) {
            console.warn('Candlestick chart canvas not found');
            return;
        }

        const candlestickDataset = {
            label: 'Price',
            data: this.candlestickData,
            borderColor: 'rgba(59, 130, 246, 1)',
            backgroundColor: 'rgba(59, 130, 246, 0.1)',
            borderWidth: 1,
            barPercentage: 0.5,
            categoryPercentage: 0.8
        };

        this.charts.candlestick = new Chart(ctx.getContext('2d'), {
            type: 'candlestick',
            data: {
                datasets: [candlestickDataset]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        backgroundColor: 'rgba(17, 24, 39, 0.95)',
                        titleColor: '#fff',
                        bodyColor: '#fff',
                        borderColor: 'rgba(255, 255, 255, 0.1)',
                        borderWidth: 1,
                        displayColors: false,
                        callbacks: {
                            label: function (context) {
                                const point = context.raw;
                                if (!point) return '';

                                return [
                                    `Open: $${point.o.toFixed(6)}`,
                                    `High: $${point.h.toFixed(6)}`,
                                    `Low: $${point.l.toFixed(6)}`,
                                    `Close: $${point.c.toFixed(6)}`,
                                    `Volume: $${formatLargeNumber(point.v || 0)}`
                                ];
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
                    x: {
                        type: 'time',
                        time: {
                            unit: 'minute',
                            displayFormats: {
                                minute: 'HH:mm',
                                hour: 'HH:mm'
                            }
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        },
                        ticks: {
                            color: 'rgba(255, 255, 255, 0.7)',
                            maxRotation: 0
                        }
                    },
                    y: {
                        type: 'linear',
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        },
                        ticks: {
                            color: 'rgba(255, 255, 255, 0.7)',
                            callback: function (value) {
                                return '$' + value.toFixed(4);
                            }
                        }
                    }
                }
            }
        });
    }

    /**
     * Initialize market depth chart
     */
    initializeDepthChart() {
        const ctx = document.getElementById('depth-chart');
        if (!ctx) {
            console.warn('Depth chart canvas not found');
            return;
        }

        this.charts.depth = new Chart(ctx.getContext('2d'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Bids',
                        data: [],
                        borderColor: 'rgba(34, 197, 94, 1)',
                        backgroundColor: 'rgba(34, 197, 94, 0.2)',
                        fill: true,
                        stepped: 'middle',
                        tension: 0
                    },
                    {
                        label: 'Asks',
                        data: [],
                        borderColor: 'rgba(239, 68, 68, 1)',
                        backgroundColor: 'rgba(239, 68, 68, 0.2)',
                        fill: true,
                        stepped: 'middle',
                        tension: 0
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                plugins: {
                    legend: {
                        display: true,
                        labels: {
                            color: 'rgba(255, 255, 255, 0.9)',
                            usePointStyle: true
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function (context) {
                                return `${context.dataset.label}: $${formatLargeNumber(context.parsed.y)} @ $${context.parsed.x.toFixed(6)}`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        type: 'linear',
                        title: {
                            display: true,
                            text: 'Price ($)',
                            color: 'rgba(255, 255, 255, 0.7)'
                        },
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
                    y: {
                        title: {
                            display: true,
                            text: 'Volume',
                            color: 'rgba(255, 255, 255, 0.7)'
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        },
                        ticks: {
                            color: 'rgba(255, 255, 255, 0.7)',
                            callback: function (value) {
                                return '$' + formatLargeNumber(value);
                            }
                        }
                    }
                }
            }
        });
    }

    /**
     * Initialize trading volume chart
     */
    initializeVolumeChart() {
        const ctx = document.getElementById('trading-volume-chart');
        if (!ctx) {
            console.warn('Volume chart canvas not found');
            return;
        }

        this.charts.volume = new Chart(ctx.getContext('2d'), {
            type: 'bar',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Buy Volume',
                        data: [],
                        backgroundColor: 'rgba(34, 197, 94, 0.6)',
                        borderColor: 'rgba(34, 197, 94, 1)',
                        borderWidth: 1
                    },
                    {
                        label: 'Sell Volume',
                        data: [],
                        backgroundColor: 'rgba(239, 68, 68, 0.6)',
                        borderColor: 'rgba(239, 68, 68, 1)',
                        borderWidth: 1
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        stacked: true,
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        },
                        ticks: {
                            color: 'rgba(255, 255, 255, 0.7)',
                            maxTicksLimit: 10
                        }
                    },
                    y: {
                        stacked: true,
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
                    }
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
                }
            }
        });
    }

    /**
     * Initialize portfolio performance chart
     */
    initializePortfolioChart() {
        const ctx = document.getElementById('portfolio-performance-chart');
        if (!ctx) {
            console.warn('Portfolio chart canvas not found');
            return;
        }

        this.charts.portfolio = new Chart(ctx.getContext('2d'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Portfolio Value',
                        data: [],
                        borderColor: 'rgba(139, 92, 246, 1)',
                        backgroundColor: 'rgba(139, 92, 246, 0.1)',
                        fill: true,
                        tension: 0.4,
                        yAxisID: 'y'
                    },
                    {
                        label: 'P&L %',
                        data: [],
                        borderColor: 'rgba(251, 191, 36, 1)',
                        backgroundColor: 'rgba(251, 191, 36, 0.1)',
                        fill: false,
                        tension: 0.4,
                        yAxisID: 'y1'
                    }
                ]
            },
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
                        callbacks: {
                            label: function (context) {
                                if (context.datasetIndex === 0) {
                                    return `Value: $${context.parsed.y.toFixed(2)}`;
                                } else {
                                    return `P&L: ${context.parsed.y.toFixed(2)}%`;
                                }
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        },
                        ticks: {
                            color: 'rgba(255, 255, 255, 0.7)'
                        }
                    },
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
                                return '$' + value.toFixed(0);
                            }
                        }
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        grid: {
                            drawOnChartArea: false,
                        },
                        ticks: {
                            color: 'rgba(255, 255, 255, 0.7)',
                            callback: function (value) {
                                return value.toFixed(1) + '%';
                            }
                        }
                    }
                }
            }
        });
    }

    /**
     * Initialize positions performance chart
     */
    initializePositionsChart() {
        const ctx = document.getElementById('positions-performance-chart');
        if (!ctx) {
            console.warn('Positions chart canvas not found');
            return;
        }

        this.charts.positions = new Chart(ctx.getContext('2d'), {
            type: 'bar',
            data: {
                labels: [],
                datasets: [{
                    label: 'Position P&L',
                    data: [],
                    backgroundColor: [],
                    borderColor: [],
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y',
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        callbacks: {
                            label: function (context) {
                                const value = context.parsed.x;
                                return `P&L: ${value >= 0 ? '+' : ''}$${value.toFixed(2)}`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        },
                        ticks: {
                            color: 'rgba(255, 255, 255, 0.7)',
                            callback: function (value) {
                                return '$' + value.toFixed(0);
                            }
                        }
                    },
                    y: {
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

    // =============================================================================
    // CHART UPDATES
    // =============================================================================

    /**
     * Update candlestick chart with new data
     * 
     * @param {Object} data - Price data with OHLCV values
     */
    updateCandlestick(data) {
        if (!this.charts.candlestick) return;

        const newCandle = {
            x: new Date(data.timestamp),
            o: data.open,
            h: data.high,
            l: data.low,
            c: data.close,
            v: data.volume
        };

        const dataset = this.charts.candlestick.data.datasets[0];
        const lastIndex = dataset.data.length - 1;

        if (lastIndex >= 0 &&
            dataset.data[lastIndex].x.getTime() === newCandle.x.getTime()) {
            // Update existing candle
            dataset.data[lastIndex] = newCandle;
        } else {
            // Add new candle
            dataset.data.push(newCandle);

            // Limit to last 100 candles
            if (dataset.data.length > 100) {
                dataset.data.shift();
            }
        }

        this.charts.candlestick.update('none');
    }

    /**
     * Update depth chart with order book data
     * 
     * @param {Object} data - Order book data with bids and asks
     */
    updateDepthChart(data) {
        if (!this.charts.depth) return;

        const bids = data.bids || [];
        const asks = data.asks || [];

        // Calculate cumulative volumes
        let bidVolume = 0;
        const bidData = bids.map(bid => {
            bidVolume += bid.volume;
            return { x: bid.price, y: bidVolume };
        });

        let askVolume = 0;
        const askData = asks.map(ask => {
            askVolume += ask.volume;
            return { x: ask.price, y: askVolume };
        });

        // Update chart data
        this.charts.depth.data.datasets[0].data = bidData;
        this.charts.depth.data.datasets[1].data = askData;

        this.charts.depth.update('none');
    }

    /**
     * Update volume chart with trading volume data
     * 
     * @param {Object} data - Volume data with buy/sell volumes
     */
    updateVolumeChart(data) {
        if (!this.charts.volume) return;

        const labels = this.charts.volume.data.labels;
        const buyVolume = this.charts.volume.data.datasets[0].data;
        const sellVolume = this.charts.volume.data.datasets[1].data;

        // Add new data point
        labels.push(new Date(data.timestamp).toLocaleTimeString());
        buyVolume.push(data.buyVolume || 0);
        sellVolume.push(data.sellVolume || 0);

        // Keep last 20 data points
        if (labels.length > 20) {
            labels.shift();
            buyVolume.shift();
            sellVolume.shift();
        }

        this.charts.volume.update('none');
    }

    /**
     * Update portfolio performance chart
     * 
     * @param {Object} data - Portfolio data with value and P&L
     */
    updatePortfolioChart(data) {
        if (!this.charts.portfolio) return;

        const labels = this.charts.portfolio.data.labels;
        const values = this.charts.portfolio.data.datasets[0].data;
        const pnlPercent = this.charts.portfolio.data.datasets[1].data;

        // Add new data point
        labels.push(new Date().toLocaleTimeString());
        values.push(data.totalValue || 0);
        pnlPercent.push(data.pnlPercent || 0);

        // Keep last 50 data points
        if (labels.length > 50) {
            labels.shift();
            values.shift();
            pnlPercent.shift();
        }

        this.charts.portfolio.update('none');
    }

    /**
     * Update positions performance chart
     * 
     * @param {Array} positionsData - Array of position objects
     */
    updatePositionsChart(positionsData) {
        if (!this.charts.positions) return;

        const positions = Array.isArray(positionsData) ? positionsData : [];

        const labels = [];
        const data = [];
        const backgroundColors = [];
        const borderColors = [];

        positions.forEach(position => {
            labels.push(position.symbol || position.token_symbol);
            const pnl = parseFloat(position.unrealized_pnl_usd || 0);
            data.push(pnl);

            // Color based on profit/loss
            if (pnl >= 0) {
                backgroundColors.push('rgba(34, 197, 94, 0.6)');
                borderColors.push('rgba(34, 197, 94, 1)');
            } else {
                backgroundColors.push('rgba(239, 68, 68, 0.6)');
                borderColors.push('rgba(239, 68, 68, 1)');
            }
        });

        this.charts.positions.data.labels = labels;
        this.charts.positions.data.datasets[0].data = data;
        this.charts.positions.data.datasets[0].backgroundColor = backgroundColors;
        this.charts.positions.data.datasets[0].borderColor = borderColors;

        this.charts.positions.update('none');
    }

    /**
     * Update all charts with fetched data
     * 
     * @param {Object} data - Combined data for all charts
     */
    updateAllChartsWithData(data) {
        if (data.candlestick) {
            this.charts.candlestick.data.datasets[0].data = data.candlestick;
            this.charts.candlestick.update();
        }

        if (data.volume) {
            this.updateVolumeChart(data.volume);
        }

        if (data.depth) {
            this.updateDepthChart(data.depth);
        }

        if (data.portfolio) {
            this.updatePortfolioChart(data.portfolio);
        }
    }

    // =============================================================================
    // CHART INTERACTIONS
    // =============================================================================

    /**
     * Enable interactive features for trading charts
     */
    enableChartInteractions() {
        this.addTimeRangeSelector();
        this.addChartExportButtons();
        this.addFullscreenToggle();
        this.addDrawingTools();
    }

    /**
     * Add time range selector for charts
     */
    addTimeRangeSelector() {
        const selector = document.getElementById('chart-timeframe-selector');
        if (!selector) return;

        selector.addEventListener('change', (e) => {
            const timeframe = e.target.value;
            this.updateChartsTimeframe(timeframe);
        });
    }

    /**
     * Update charts based on selected timeframe
     * 
     * @param {string} timeframe - Selected timeframe (1m, 5m, 15m, 1h, 4h, 1d)
     */
    updateChartsTimeframe(timeframe) {
        console.log(`📊 Updating charts to ${timeframe} timeframe`);

        const timeframeConfig = {
            '1m': { interval: 60, points: 60 },
            '5m': { interval: 300, points: 60 },
            '15m': { interval: 900, points: 48 },
            '1h': { interval: 3600, points: 24 },
            '4h': { interval: 14400, points: 28 },
            '1d': { interval: 86400, points: 30 }
        };

        const config = timeframeConfig[timeframe] || timeframeConfig['5m'];

        // Request new data for the timeframe
        this.fetchChartData(config);

        // Update chart options
        if (this.charts.candlestick) {
            this.charts.candlestick.options.scales.x.time.unit =
                timeframe === '1m' ? 'minute' :
                    timeframe === '1d' ? 'day' : 'hour';
            this.charts.candlestick.update();
        }

        this.showNotification(`Charts updated to ${timeframe} timeframe`, 'info');
    }

    /**
     * Add chart export functionality
     */
    addChartExportButtons() {
        Object.entries(this.charts).forEach(([name, chart]) => {
            if (!chart) return;

            const exportBtn = document.getElementById(`export-${name}-chart`);
            if (exportBtn) {
                exportBtn.addEventListener('click', () => {
                    this.exportChart(chart, name);
                });
            }
        });
    }

    /**
     * Export chart as image
     * 
     * @param {Chart} chart - Chart.js instance
     * @param {string} name - Chart name for filename
     */
    exportChart(chart, name) {
        const url = chart.toBase64Image();
        const a = document.createElement('a');
        a.href = url;
        a.download = `${name}_chart_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.png`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);

        this.showNotification(`${name} chart exported`, 'success');
    }

    /**
     * Add fullscreen toggle for charts
     */
    addFullscreenToggle() {
        const fullscreenBtns = document.querySelectorAll('.chart-fullscreen-btn');

        fullscreenBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                const chartContainer = e.target.closest('.chart-container');
                if (chartContainer) {
                    if (chartContainer.requestFullscreen) {
                        chartContainer.requestFullscreen();
                    }
                }
            });
        });
    }

    /**
     * Add drawing tools for technical analysis
     */
    addDrawingTools() {
        // Placeholder for drawing tools implementation
        // Would integrate with Chart.js annotations plugin
        console.log('📐 Drawing tools ready for technical analysis');
    }

    // =============================================================================
    // DATA FETCHING
    // =============================================================================

    /**
     * Fetch chart data from server
     * 
     * @param {Object} config - Configuration with interval and points
     */
    async fetchChartData(config) {
        try {
            const response = await fetch(`/api/trading/charts/data/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                },
                body: JSON.stringify({
                    interval: config.interval,
                    points: config.points
                })
            });

            if (response.ok) {
                const data = await response.json();
                this.updateAllChartsWithData(data);
            }
        } catch (error) {
            console.error('Error fetching chart data:', error);
        }
    }

    // =============================================================================
    // CHART MANAGEMENT
    // =============================================================================

    /**
     * Get specific chart instance
     * 
     * @param {string} name - Chart name
     * @returns {Chart|null} Chart instance or null
     */
    getChart(name) {
        return this.charts[name] || null;
    }

    /**
     * Destroy all charts and cleanup
     */
    destroy() {
        Object.values(this.charts).forEach(chart => {
            if (chart) chart.destroy();
        });

        this.charts = {
            candlestick: null,
            depth: null,
            volume: null,
            portfolio: null,
            positions: null
        };

        console.log('🧹 TradingChartsManager cleanup completed');
    }
}