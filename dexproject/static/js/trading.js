// /**
//  * Trading Frontend Integration - Phase 3 & 6B Complete Implementation
//  * 
//  * Enhanced with interactive trading charts for Phase 3 completion
//  * Maintains Phase 6B Transaction Manager integration
//  * 
//  * Features:
//  * - PHASE 3: Interactive trading charts (candlestick, depth, volume)
//  * - PHASE 3: Real-time chart updates via WebSocket
//  * - PHASE 3: Position performance visualization
//  * - PHASE 6B: Transaction Manager integration
//  * - Real-time WebSocket transaction status updates
//  * - Gas optimization savings display
//  * - Transaction lifecycle progress tracking
//  * 
//  * File: dexproject/dashboard/static/js/trading.js
//  */

// class TradingManager {
//     constructor() {
//         this.baseUrl = '/api/trading';
//         this.csrfToken = this.getCsrfToken();
//         this.eventSource = null;
//         this.websocket = null;
//         this.chartsWebsocket = null; // Phase 3: Separate WebSocket for charts

//         // Data storage
//         this.positions = new Map();
//         this.trades = new Map();
//         this.activeTransactions = new Map();
//         this.notifications = [];

//         // Phase 3: Chart data storage
//         this.priceHistory = [];
//         this.volumeHistory = [];
//         this.orderBookData = { bids: [], asks: [] };
//         this.candlestickData = [];

//         // Phase 3: Chart instances
//         this.charts = {
//             price: null,
//             candlestick: null,
//             volume: null,
//             depth: null,
//             portfolio: null,
//             positions: null
//         };

//         // WebSocket reconnection management
//         this.reconnectAttempts = 0;
//         this.maxReconnectAttempts = 5;
//         this.reconnectDelay = 1000;

//         // Feature flags
//         this.useTransactionManagerV2 = true;
//         this.enableInteractiveCharts = true; // Phase 3 feature flag

//         // Initialize trading functionality
//         this.init();

//         console.log('🚀 TradingManager initialized with Phase 3 Interactive Charts & Phase 6B Transaction Manager');
//     }

//     /**
//      * Initialize trading functionality and event listeners
//      */
//     init() {
//         this.bindEventListeners();
//         this.startRealTimeUpdates();
//         this.initializeWebSocket();

//         // Phase 3: Initialize trading charts
//         if (this.enableInteractiveCharts) {
//             this.initializeTradingCharts();
//             this.initializeChartsWebSocket();
//         }

//         this.loadInitialData();
//         this.setupEventHandlers();
//     }

//     // =============================================================================
//     // PHASE 3: INTERACTIVE TRADING CHARTS
//     // =============================================================================

//     /**
//      * Initialize all trading charts
//      */
//     initializeTradingCharts() {
//         console.log('📊 Initializing interactive trading charts...');

//         // Initialize individual chart types
//         this.initializeCandlestickChart();
//         this.initializeDepthChart();
//         this.initializeVolumeChart();
//         this.initializePortfolioChart();
//         this.initializePositionsChart();

//         // Enable chart interactions
//         this.enableChartInteractions();

//         console.log('✅ Trading charts initialized');
//     }

//     /**
//      * Initialize candlestick chart for price action
//      */
//     initializeCandlestickChart() {
//         const ctx = document.getElementById('candlestick-chart');
//         if (!ctx) {
//             console.warn('Candlestick chart canvas not found');
//             return;
//         }

//         // Prepare candlestick data format
//         const candlestickDataset = {
//             label: 'Price',
//             data: this.candlestickData,
//             borderColor: 'rgba(59, 130, 246, 1)',
//             backgroundColor: 'rgba(59, 130, 246, 0.1)',
//             borderWidth: 1,
//             barPercentage: 0.5,
//             categoryPercentage: 0.8
//         };

//         this.charts.candlestick = new Chart(ctx.getContext('2d'), {
//             type: 'candlestick',
//             data: {
//                 datasets: [candlestickDataset]
//             },
//             options: {
//                 responsive: true,
//                 maintainAspectRatio: false,
//                 interaction: {
//                     intersect: false,
//                     mode: 'index'
//                 },
//                 plugins: {
//                     legend: {
//                         display: false
//                     },
//                     tooltip: {
//                         backgroundColor: 'rgba(17, 24, 39, 0.95)',
//                         titleColor: '#fff',
//                         bodyColor: '#fff',
//                         borderColor: 'rgba(255, 255, 255, 0.1)',
//                         borderWidth: 1,
//                         displayColors: false,
//                         callbacks: {
//                             label: function (context) {
//                                 const point = context.raw;
//                                 if (!point) return '';

//                                 return [
//                                     `Open: $${point.o.toFixed(6)}`,
//                                     `High: $${point.h.toFixed(6)}`,
//                                     `Low: $${point.l.toFixed(6)}`,
//                                     `Close: $${point.c.toFixed(6)}`,
//                                     `Volume: $${formatLargeNumber(point.v || 0)}`
//                                 ];
//                             }
//                         }
//                     },
//                     zoom: {
//                         zoom: {
//                             wheel: {
//                                 enabled: true,
//                             },
//                             pinch: {
//                                 enabled: true
//                             },
//                             mode: 'x',
//                         },
//                         pan: {
//                             enabled: true,
//                             mode: 'x',
//                         }
//                     }
//                 },
//                 scales: {
//                     x: {
//                         type: 'time',
//                         time: {
//                             unit: 'minute',
//                             displayFormats: {
//                                 minute: 'HH:mm',
//                                 hour: 'HH:mm'
//                             }
//                         },
//                         grid: {
//                             color: 'rgba(255, 255, 255, 0.1)'
//                         },
//                         ticks: {
//                             color: 'rgba(255, 255, 255, 0.7)',
//                             maxRotation: 0
//                         }
//                     },
//                     y: {
//                         type: 'linear',
//                         grid: {
//                             color: 'rgba(255, 255, 255, 0.1)'
//                         },
//                         ticks: {
//                             color: 'rgba(255, 255, 255, 0.7)',
//                             callback: function (value) {
//                                 return '$' + value.toFixed(4);
//                             }
//                         }
//                     }
//                 }
//             }
//         });
//     }

//     /**
//      * Initialize market depth chart
//      */
//     initializeDepthChart() {
//         const ctx = document.getElementById('depth-chart');
//         if (!ctx) {
//             console.warn('Depth chart canvas not found');
//             return;
//         }

//         this.charts.depth = new Chart(ctx.getContext('2d'), {
//             type: 'line',
//             data: {
//                 labels: [],
//                 datasets: [
//                     {
//                         label: 'Bids',
//                         data: [],
//                         borderColor: 'rgba(34, 197, 94, 1)',
//                         backgroundColor: 'rgba(34, 197, 94, 0.2)',
//                         fill: true,
//                         stepped: 'middle',
//                         tension: 0
//                     },
//                     {
//                         label: 'Asks',
//                         data: [],
//                         borderColor: 'rgba(239, 68, 68, 1)',
//                         backgroundColor: 'rgba(239, 68, 68, 0.2)',
//                         fill: true,
//                         stepped: 'middle',
//                         tension: 0
//                     }
//                 ]
//             },
//             options: {
//                 responsive: true,
//                 maintainAspectRatio: false,
//                 interaction: {
//                     intersect: false,
//                     mode: 'index'
//                 },
//                 plugins: {
//                     legend: {
//                         display: true,
//                         labels: {
//                             color: 'rgba(255, 255, 255, 0.9)',
//                             usePointStyle: true
//                         }
//                     },
//                     tooltip: {
//                         callbacks: {
//                             label: function (context) {
//                                 return `${context.dataset.label}: $${formatLargeNumber(context.parsed.y)} @ $${context.parsed.x.toFixed(6)}`;
//                             }
//                         }
//                     }
//                 },
//                 scales: {
//                     x: {
//                         type: 'linear',
//                         title: {
//                             display: true,
//                             text: 'Price ($)',
//                             color: 'rgba(255, 255, 255, 0.7)'
//                         },
//                         grid: {
//                             color: 'rgba(255, 255, 255, 0.1)'
//                         },
//                         ticks: {
//                             color: 'rgba(255, 255, 255, 0.7)',
//                             callback: function (value) {
//                                 return '$' + value.toFixed(4);
//                             }
//                         }
//                     },
//                     y: {
//                         title: {
//                             display: true,
//                             text: 'Volume',
//                             color: 'rgba(255, 255, 255, 0.7)'
//                         },
//                         grid: {
//                             color: 'rgba(255, 255, 255, 0.1)'
//                         },
//                         ticks: {
//                             color: 'rgba(255, 255, 255, 0.7)',
//                             callback: function (value) {
//                                 return '$' + formatLargeNumber(value);
//                             }
//                         }
//                     }
//                 }
//             }
//         });
//     }

//     /**
//      * Initialize trading volume chart
//      */
//     initializeVolumeChart() {
//         const ctx = document.getElementById('trading-volume-chart');
//         if (!ctx) {
//             console.warn('Volume chart canvas not found');
//             return;
//         }

//         this.charts.volume = new Chart(ctx.getContext('2d'), {
//             type: 'bar',
//             data: {
//                 labels: [],
//                 datasets: [
//                     {
//                         label: 'Buy Volume',
//                         data: [],
//                         backgroundColor: 'rgba(34, 197, 94, 0.6)',
//                         borderColor: 'rgba(34, 197, 94, 1)',
//                         borderWidth: 1
//                     },
//                     {
//                         label: 'Sell Volume',
//                         data: [],
//                         backgroundColor: 'rgba(239, 68, 68, 0.6)',
//                         borderColor: 'rgba(239, 68, 68, 1)',
//                         borderWidth: 1
//                     }
//                 ]
//             },
//             options: {
//                 responsive: true,
//                 maintainAspectRatio: false,
//                 scales: {
//                     x: {
//                         stacked: true,
//                         grid: {
//                             color: 'rgba(255, 255, 255, 0.1)'
//                         },
//                         ticks: {
//                             color: 'rgba(255, 255, 255, 0.7)',
//                             maxTicksLimit: 10
//                         }
//                     },
//                     y: {
//                         stacked: true,
//                         beginAtZero: true,
//                         grid: {
//                             color: 'rgba(255, 255, 255, 0.1)'
//                         },
//                         ticks: {
//                             color: 'rgba(255, 255, 255, 0.7)',
//                             callback: function (value) {
//                                 return '$' + formatLargeNumber(value);
//                             }
//                         }
//                     }
//                 },
//                 plugins: {
//                     legend: {
//                         display: true,
//                         labels: {
//                             color: 'rgba(255, 255, 255, 0.9)'
//                         }
//                     },
//                     tooltip: {
//                         callbacks: {
//                             label: function (context) {
//                                 return `${context.dataset.label}: $${formatLargeNumber(context.parsed.y)}`;
//                             }
//                         }
//                     }
//                 }
//             }
//         });
//     }

//     /**
//      * Initialize portfolio performance chart
//      */
//     initializePortfolioChart() {
//         const ctx = document.getElementById('portfolio-performance-chart');
//         if (!ctx) {
//             console.warn('Portfolio chart canvas not found');
//             return;
//         }

//         this.charts.portfolio = new Chart(ctx.getContext('2d'), {
//             type: 'line',
//             data: {
//                 labels: [],
//                 datasets: [
//                     {
//                         label: 'Portfolio Value',
//                         data: [],
//                         borderColor: 'rgba(139, 92, 246, 1)',
//                         backgroundColor: 'rgba(139, 92, 246, 0.1)',
//                         fill: true,
//                         tension: 0.4,
//                         yAxisID: 'y'
//                     },
//                     {
//                         label: 'P&L %',
//                         data: [],
//                         borderColor: 'rgba(251, 191, 36, 1)',
//                         backgroundColor: 'rgba(251, 191, 36, 0.1)',
//                         fill: false,
//                         tension: 0.4,
//                         yAxisID: 'y1'
//                     }
//                 ]
//             },
//             options: {
//                 responsive: true,
//                 maintainAspectRatio: false,
//                 interaction: {
//                     mode: 'index',
//                     intersect: false,
//                 },
//                 plugins: {
//                     legend: {
//                         display: true,
//                         labels: {
//                             color: 'rgba(255, 255, 255, 0.9)'
//                         }
//                     },
//                     tooltip: {
//                         callbacks: {
//                             label: function (context) {
//                                 if (context.datasetIndex === 0) {
//                                     return `Value: $${context.parsed.y.toFixed(2)}`;
//                                 } else {
//                                     return `P&L: ${context.parsed.y.toFixed(2)}%`;
//                                 }
//                             }
//                         }
//                     }
//                 },
//                 scales: {
//                     x: {
//                         grid: {
//                             color: 'rgba(255, 255, 255, 0.1)'
//                         },
//                         ticks: {
//                             color: 'rgba(255, 255, 255, 0.7)'
//                         }
//                     },
//                     y: {
//                         type: 'linear',
//                         display: true,
//                         position: 'left',
//                         grid: {
//                             color: 'rgba(255, 255, 255, 0.1)'
//                         },
//                         ticks: {
//                             color: 'rgba(255, 255, 255, 0.7)',
//                             callback: function (value) {
//                                 return '$' + value.toFixed(0);
//                             }
//                         }
//                     },
//                     y1: {
//                         type: 'linear',
//                         display: true,
//                         position: 'right',
//                         grid: {
//                             drawOnChartArea: false,
//                         },
//                         ticks: {
//                             color: 'rgba(255, 255, 255, 0.7)',
//                             callback: function (value) {
//                                 return value.toFixed(1) + '%';
//                             }
//                         }
//                     }
//                 }
//             }
//         });
//     }

//     /**
//      * Initialize positions performance chart
//      */
//     initializePositionsChart() {
//         const ctx = document.getElementById('positions-performance-chart');
//         if (!ctx) {
//             console.warn('Positions chart canvas not found');
//             return;
//         }

//         this.charts.positions = new Chart(ctx.getContext('2d'), {
//             type: 'bar',
//             data: {
//                 labels: [],
//                 datasets: [{
//                     label: 'Position P&L',
//                     data: [],
//                     backgroundColor: [],
//                     borderColor: [],
//                     borderWidth: 1
//                 }]
//             },
//             options: {
//                 responsive: true,
//                 maintainAspectRatio: false,
//                 indexAxis: 'y',
//                 plugins: {
//                     legend: {
//                         display: false
//                     },
//                     tooltip: {
//                         callbacks: {
//                             label: function (context) {
//                                 const value = context.parsed.x;
//                                 return `P&L: ${value >= 0 ? '+' : ''}$${value.toFixed(2)}`;
//                             }
//                         }
//                     }
//                 },
//                 scales: {
//                     x: {
//                         grid: {
//                             color: 'rgba(255, 255, 255, 0.1)'
//                         },
//                         ticks: {
//                             color: 'rgba(255, 255, 255, 0.7)',
//                             callback: function (value) {
//                                 return '$' + value.toFixed(0);
//                             }
//                         }
//                     },
//                     y: {
//                         grid: {
//                             color: 'rgba(255, 255, 255, 0.1)'
//                         },
//                         ticks: {
//                             color: 'rgba(255, 255, 255, 0.7)'
//                         }
//                     }
//                 }
//             }
//         });
//     }

//     /**
//      * Enable interactive features for trading charts
//      */
//     enableChartInteractions() {
//         // Add time range selector for all charts
//         this.addTimeRangeSelector();

//         // Add chart export buttons
//         this.addChartExportButtons();

//         // Add fullscreen toggle
//         this.addFullscreenToggle();

//         // Add drawing tools for technical analysis
//         this.addDrawingTools();
//     }

//     /**
//      * Add time range selector for charts
//      */
//     addTimeRangeSelector() {
//         const selector = document.getElementById('chart-timeframe-selector');
//         if (!selector) return;

//         selector.addEventListener('change', (e) => {
//             const timeframe = e.target.value;
//             this.updateChartsTimeframe(timeframe);
//         });
//     }

//     /**
//      * Update charts based on selected timeframe
//      */
//     updateChartsTimeframe(timeframe) {
//         console.log(`📊 Updating charts to ${timeframe} timeframe`);

//         // Map timeframe to data parameters
//         const timeframeConfig = {
//             '1m': { interval: 60, points: 60 },
//             '5m': { interval: 300, points: 60 },
//             '15m': { interval: 900, points: 48 },
//             '1h': { interval: 3600, points: 24 },
//             '4h': { interval: 14400, points: 28 },
//             '1d': { interval: 86400, points: 30 }
//         };

//         const config = timeframeConfig[timeframe] || timeframeConfig['5m'];

//         // Request new data for the timeframe
//         this.fetchChartData(config);

//         // Update chart options
//         if (this.charts.candlestick) {
//             this.charts.candlestick.options.scales.x.time.unit =
//                 timeframe === '1m' ? 'minute' :
//                     timeframe === '1d' ? 'day' : 'hour';
//             this.charts.candlestick.update();
//         }

//         this.showNotification(`Charts updated to ${timeframe} timeframe`, 'info');
//     }

//     /**
//      * Add chart export functionality
//      */
//     addChartExportButtons() {
//         Object.entries(this.charts).forEach(([name, chart]) => {
//             if (!chart) return;

//             const exportBtn = document.getElementById(`export-${name}-chart`);
//             if (exportBtn) {
//                 exportBtn.addEventListener('click', () => {
//                     this.exportChart(chart, name);
//                 });
//             }
//         });
//     }

//     /**
//      * Export chart as image
//      */
//     exportChart(chart, name) {
//         const url = chart.toBase64Image();
//         const a = document.createElement('a');
//         a.href = url;
//         a.download = `${name}_chart_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.png`;
//         document.body.appendChild(a);
//         a.click();
//         document.body.removeChild(a);

//         this.showNotification(`${name} chart exported`, 'success');
//     }

//     /**
//      * Add fullscreen toggle for charts
//      */
//     addFullscreenToggle() {
//         const fullscreenBtns = document.querySelectorAll('.chart-fullscreen-btn');

//         fullscreenBtns.forEach(btn => {
//             btn.addEventListener('click', (e) => {
//                 const chartContainer = e.target.closest('.chart-container');
//                 if (chartContainer) {
//                     if (chartContainer.requestFullscreen) {
//                         chartContainer.requestFullscreen();
//                     }
//                 }
//             });
//         });
//     }

//     /**
//      * Add drawing tools for technical analysis
//      */
//     addDrawingTools() {
//         // Placeholder for drawing tools implementation
//         // This would integrate with a library like Chart.js annotations plugin
//         console.log('📐 Drawing tools ready for technical analysis');
//     }

//     /**
//      * Initialize WebSocket for real-time chart updates
//      */
//     initializeChartsWebSocket() {
//         const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
//         const wsUrl = `${wsProtocol}//${window.location.host}/ws/trading/charts/`;

//         try {
//             this.chartsWebsocket = new WebSocket(wsUrl);

//             this.chartsWebsocket.onopen = () => {
//                 console.log('📊 Charts WebSocket connected');
//                 this.subscribeToChartUpdates();
//             };

//             this.chartsWebsocket.onmessage = (event) => {
//                 try {
//                     const data = JSON.parse(event.data);
//                     this.handleChartUpdate(data);
//                 } catch (error) {
//                     console.error('Error parsing chart WebSocket message:', error);
//                 }
//             };

//             this.chartsWebsocket.onerror = (error) => {
//                 console.error('Charts WebSocket error:', error);
//             };

//             this.chartsWebsocket.onclose = () => {
//                 console.log('Charts WebSocket disconnected');
//                 // Reconnect after delay
//                 setTimeout(() => this.initializeChartsWebSocket(), 5000);
//             };

//         } catch (error) {
//             console.error('Failed to initialize charts WebSocket:', error);
//         }
//     }

//     /**
//      * Subscribe to real-time chart updates
//      */
//     subscribeToChartUpdates() {
//         if (this.chartsWebsocket && this.chartsWebsocket.readyState === WebSocket.OPEN) {
//             this.chartsWebsocket.send(JSON.stringify({
//                 type: 'subscribe',
//                 channels: ['price', 'volume', 'depth', 'trades']
//             }));
//         }
//     }

//     /**
//      * Handle real-time chart updates
//      */
//     handleChartUpdate(data) {
//         switch (data.type) {
//             case 'price_update':
//                 this.updatePriceChart(data.data);
//                 this.updateCandlestick(data.data);
//                 break;
//             case 'volume_update':
//                 this.updateVolumeChart(data.data);
//                 break;
//             case 'depth_update':
//                 this.updateDepthChart(data.data);
//                 break;
//             case 'trade_update':
//                 this.addTradeToChart(data.data);
//                 break;
//             case 'portfolio_update':
//                 this.updatePortfolioChart(data.data);
//                 break;
//             case 'position_update':
//                 this.updatePositionsChart(data.data);
//                 break;
//         }
//     }

//     /**
//      * Update candlestick chart with new data
//      */
//     updateCandlestick(data) {
//         if (!this.charts.candlestick) return;

//         const newCandle = {
//             x: new Date(data.timestamp),
//             o: data.open,
//             h: data.high,
//             l: data.low,
//             c: data.close,
//             v: data.volume
//         };

//         // Add or update the latest candle
//         const dataset = this.charts.candlestick.data.datasets[0];
//         const lastIndex = dataset.data.length - 1;

//         if (lastIndex >= 0 &&
//             dataset.data[lastIndex].x.getTime() === newCandle.x.getTime()) {
//             // Update existing candle
//             dataset.data[lastIndex] = newCandle;
//         } else {
//             // Add new candle
//             dataset.data.push(newCandle);

//             // Limit to last 100 candles
//             if (dataset.data.length > 100) {
//                 dataset.data.shift();
//             }
//         }

//         this.charts.candlestick.update('none');
//     }

//     /**
//      * Update depth chart with order book data
//      */
//     updateDepthChart(data) {
//         if (!this.charts.depth) return;

//         // Process bid and ask data
//         const bids = data.bids || [];
//         const asks = data.asks || [];

//         // Calculate cumulative volumes
//         let bidVolume = 0;
//         const bidData = bids.map(bid => {
//             bidVolume += bid.volume;
//             return { x: bid.price, y: bidVolume };
//         });

//         let askVolume = 0;
//         const askData = asks.map(ask => {
//             askVolume += ask.volume;
//             return { x: ask.price, y: askVolume };
//         });

//         // Update chart data
//         this.charts.depth.data.datasets[0].data = bidData;
//         this.charts.depth.data.datasets[1].data = askData;

//         this.charts.depth.update('none');
//     }

//     /**
//      * Update volume chart with trading volume data
//      */
//     updateVolumeChart(data) {
//         if (!this.charts.volume) return;

//         const labels = this.charts.volume.data.labels;
//         const buyVolume = this.charts.volume.data.datasets[0].data;
//         const sellVolume = this.charts.volume.data.datasets[1].data;

//         // Add new data point
//         labels.push(new Date(data.timestamp).toLocaleTimeString());
//         buyVolume.push(data.buyVolume || 0);
//         sellVolume.push(data.sellVolume || 0);

//         // Keep last 20 data points
//         if (labels.length > 20) {
//             labels.shift();
//             buyVolume.shift();
//             sellVolume.shift();
//         }

//         this.charts.volume.update('none');
//     }

//     /**
//      * Update portfolio performance chart
//      */
//     updatePortfolioChart(data) {
//         if (!this.charts.portfolio) return;

//         const labels = this.charts.portfolio.data.labels;
//         const values = this.charts.portfolio.data.datasets[0].data;
//         const pnlPercent = this.charts.portfolio.data.datasets[1].data;

//         // Add new data point
//         labels.push(new Date().toLocaleTimeString());
//         values.push(data.totalValue || 0);
//         pnlPercent.push(data.pnlPercent || 0);

//         // Keep last 50 data points
//         if (labels.length > 50) {
//             labels.shift();
//             values.shift();
//             pnlPercent.shift();
//         }

//         this.charts.portfolio.update('none');
//     }

//     /**
//      * Update positions performance chart
//      */
//     updatePositionsChart(positionsData) {
//         if (!this.charts.positions) return;

//         const positions = Array.isArray(positionsData) ? positionsData : [];

//         // Clear and rebuild chart data
//         const labels = [];
//         const data = [];
//         const backgroundColors = [];
//         const borderColors = [];

//         positions.forEach(position => {
//             labels.push(position.symbol || position.token_symbol);
//             const pnl = parseFloat(position.unrealized_pnl_usd || 0);
//             data.push(pnl);

//             // Color based on profit/loss
//             if (pnl >= 0) {
//                 backgroundColors.push('rgba(34, 197, 94, 0.6)');
//                 borderColors.push('rgba(34, 197, 94, 1)');
//             } else {
//                 backgroundColors.push('rgba(239, 68, 68, 0.6)');
//                 borderColors.push('rgba(239, 68, 68, 1)');
//             }
//         });

//         this.charts.positions.data.labels = labels;
//         this.charts.positions.data.datasets[0].data = data;
//         this.charts.positions.data.datasets[0].backgroundColor = backgroundColors;
//         this.charts.positions.data.datasets[0].borderColor = borderColors;

//         this.charts.positions.update('none');
//     }

//     /**
//      * Fetch chart data from server
//      */
//     async fetchChartData(config) {
//         try {
//             const response = await fetch(`/api/trading/charts/data/`, {
//                 method: 'POST',
//                 headers: {
//                     'Content-Type': 'application/json',
//                     'X-CSRFToken': this.csrfToken
//                 },
//                 body: JSON.stringify({
//                     interval: config.interval,
//                     points: config.points
//                 })
//             });

//             if (response.ok) {
//                 const data = await response.json();
//                 this.updateAllChartsWithData(data);
//             }
//         } catch (error) {
//             console.error('Error fetching chart data:', error);
//         }
//     }

//     /**
//      * Update all charts with fetched data
//      */
//     updateAllChartsWithData(data) {
//         if (data.candlestick) {
//             this.charts.candlestick.data.datasets[0].data = data.candlestick;
//             this.charts.candlestick.update();
//         }

//         if (data.volume) {
//             this.updateVolumeChart(data.volume);
//         }

//         if (data.depth) {
//             this.updateDepthChart(data.depth);
//         }

//         if (data.portfolio) {
//             this.updatePortfolioChart(data.portfolio);
//         }
//     }

//     // =============================================================================
//     // UTILITY FUNCTIONS
//     // =============================================================================

//     /**
//      * Format large numbers for display
//      */
//     formatLargeNumber(num) {
//         if (num >= 1e9) return (num / 1e9).toFixed(2) + 'B';
//         if (num >= 1e6) return (num / 1e6).toFixed(2) + 'M';
//         if (num >= 1e3) return (num / 1e3).toFixed(2) + 'K';
//         return num.toFixed(2);
//     }

//     // =============================================================================
//     // DATA LOADING AND UI UPDATE METHODS
//     // =============================================================================

//     /**
//      * Load current positions
//      */
//     async loadPositions() {
//         try {
//             const response = await this.makeRequest('GET', '/positions/');

//             if (response.success) {
//                 this.positions.clear();
//                 response.positions.forEach(position => {
//                     this.positions.set(position.position_id, position);
//                 });

//                 this.updatePositionsDisplay(response.positions);
//                 this.updatePortfolioSummary(response.summary);

//                 // Phase 3: Update positions chart
//                 if (this.enableInteractiveCharts) {
//                     this.updatePositionsChart(response.positions);
//                 }
//             }

//         } catch (error) {
//             console.error('Error loading positions:', error);
//         }
//     }

//     /**
//      * Load trade history
//      */
//     async loadTradeHistory(limit = 50) {
//         try {
//             const response = await this.makeRequest('GET', `/history/?limit=${limit}`);

//             if (response.success) {
//                 this.trades.clear();
//                 response.trades.forEach(trade => {
//                     this.trades.set(trade.trade_id, trade);
//                 });

//                 this.updateTradeHistoryDisplay(response.trades);
//             }

//         } catch (error) {
//             console.error('Error loading trade history:', error);
//         }
//     }

//     /**
//      * Load portfolio summary
//      */
//     async loadPortfolioSummary() {
//         try {
//             const response = await this.makeRequest('GET', '/portfolio/');

//             if (response.success) {
//                 this.updatePortfolioDisplay(response.portfolio);

//                 // Phase 3: Update portfolio chart
//                 if (this.enableInteractiveCharts && this.charts.portfolio) {
//                     this.updatePortfolioChart(response.portfolio);
//                 }
//             }

//         } catch (error) {
//             console.error('Error loading portfolio summary:', error);
//         }
//     }

//     /**
//      * Start a trading session
//      */
//     async startTradingSession(config = {}) {
//         const sessionData = {
//             strategy_id: config.strategy_id || null,
//             max_position_size_usd: config.max_position_size_usd || 1000.0,
//             risk_tolerance: config.risk_tolerance || 'MEDIUM',
//             auto_execution: config.auto_execution || false
//         };

//         try {
//             this.showNotification('Starting trading session...', 'info');

//             const response = await this.makeRequest('POST', '/session/start/', sessionData);

//             if (response.success) {
//                 this.showNotification('Trading session started successfully!', 'success');
//                 this.updateSessionStatus(response.session);

//                 // Enable session-dependent UI elements
//                 this.toggleSessionUI(true);

//             } else {
//                 throw new Error(response.error || 'Failed to start trading session');
//             }

//         } catch (error) {
//             console.error('Trading session start error:', error);
//             this.showNotification(
//                 `Failed to start trading session: ${error.message}`,
//                 'error'
//             );
//         }
//     }

//     /**
//      * Stop the active trading session
//      */
//     async stopTradingSession() {
//         try {
//             this.showNotification('Stopping trading session...', 'info');

//             const response = await this.makeRequest('POST', '/session/stop/');

//             if (response.success) {
//                 this.showNotification('Trading session stopped successfully!', 'success');
//                 this.updateSessionStatus(null);

//                 // Disable session-dependent UI elements
//                 this.toggleSessionUI(false);

//             } else {
//                 throw new Error(response.error || 'Failed to stop trading session');
//             }

//         } catch (error) {
//             console.error('Trading session stop error:', error);
//             this.showNotification(
//                 `Failed to stop trading session: ${error.message}`,
//                 'error'
//             );
//         }
//     }

//     /**
//      * Update positions display in dashboard
//      */
//     updatePositionsDisplay(positions) {
//         const container = document.getElementById('positions-container');
//         if (!container) return;

//         if (positions.length === 0) {
//             container.innerHTML = `
//                 <div class="text-center py-4 text-muted">
//                     <i class="bi bi-inbox display-4 d-block mb-3"></i>
//                     <p>No open positions</p>
//                     <small>Execute your first trade to see positions here</small>
//                 </div>
//             `;
//             return;
//         }

//         const positionsHtml = positions.map(position => `
//             <div class="card mb-3" data-position-id="${position.position_id}">
//                 <div class="card-body">
//                     <div class="row align-items-center">
//                         <div class="col-md-3">
//                             <h6 class="mb-1">${position.token_symbol}</h6>
//                             <small class="text-muted">${position.token_name}</small>
//                         </div>
//                         <div class="col-md-2">
//                             <div class="text-end">
//                                 <div class="fw-bold">${position.current_amount}</div>
//                                 <small class="text-muted">Tokens</small>
//                             </div>
//                         </div>
//                         <div class="col-md-2">
//                             <div class="text-end">
//                                 <div class="fw-bold">${parseFloat(position.current_value_usd).toFixed(2)}</div>
//                                 <small class="text-muted">Current Value</small>
//                             </div>
//                         </div>
//                         <div class="col-md-2">
//                             <div class="text-end">
//                                 <div class="fw-bold ${parseFloat(position.unrealized_pnl_usd) >= 0 ? 'text-success' : 'text-danger'}">
//                                     ${parseFloat(position.unrealized_pnl_usd) >= 0 ? '+' : ''}${parseFloat(position.unrealized_pnl_usd).toFixed(2)}
//                                 </div>
//                                 <small class="text-muted">${position.unrealized_pnl_percent}%</small>
//                             </div>
//                         </div>
//                         <div class="col-md-1">
//                             <span class="badge ${this.getStatusBadgeClass(position.status)}">${position.status}</span>
//                         </div>
//                         <div class="col-md-2">
//                             <div class="btn-group btn-group-sm">
//                                 <button class="btn btn-outline-primary" 
//                                         data-action="close-position" 
//                                         data-position-id="${position.position_id}">
//                                     <i class="bi bi-x-circle me-1"></i>Close
//                                 </button>
//                             </div>
//                         </div>
//                     </div>
//                 </div>
//             </div>
//         `).join('');

//         container.innerHTML = positionsHtml;
//     }

//     /**
//      * Update trade history display
//      */
//     updateTradeHistoryDisplay(trades) {
//         const container = document.getElementById('trade-history-container');
//         if (!container) return;

//         if (trades.length === 0) {
//             container.innerHTML = `
//                 <div class="text-center py-4 text-muted">
//                     <i class="bi bi-clock-history display-4 d-block mb-3"></i>
//                     <p>No trade history</p>
//                     <small>Your completed trades will appear here</small>
//                 </div>
//             `;
//             return;
//         }

//         const tradesHtml = trades.map(trade => `
//             <div class="card mb-2" data-trade-id="${trade.trade_id}">
//                 <div class="card-body py-2">
//                     <div class="row align-items-center">
//                         <div class="col-md-2">
//                             <span class="badge ${this.getTradeBadgeClass(trade.trade_type)}">${trade.trade_type}</span>
//                         </div>
//                         <div class="col-md-2">
//                             <div class="fw-bold">${trade.token_symbol || 'Token'}</div>
//                         </div>
//                         <div class="col-md-2">
//                             <div class="text-end">
//                                 ${trade.amount_in ? `${trade.amount_in} ETH` : `${trade.amount_out} tokens`}
//                             </div>
//                         </div>
//                         <div class="col-md-2">
//                             <div class="text-end">
//                                 ${trade.execution_price ? `${parseFloat(trade.execution_price).toFixed(4)}` : '-'}
//                             </div>
//                         </div>
//                         <div class="col-md-2">
//                             <span class="badge ${this.getStatusBadgeClass(trade.status)}">${trade.status}</span>
//                         </div>
//                         <div class="col-md-2">
//                             <small class="text-muted">${new Date(trade.created_at).toLocaleString()}</small>
//                         </div>
//                     </div>
//                 </div>
//             </div>
//         `).join('');

//         container.innerHTML = tradesHtml;
//     }

//     /**
//      * Update portfolio summary display
//      */
//     updatePortfolioDisplay(portfolio) {
//         // Update total portfolio value
//         const totalValueEl = document.getElementById('total-portfolio-value');
//         if (totalValueEl) {
//             totalValueEl.textContent = `${parseFloat(portfolio.total_value_usd || 0).toFixed(2)}`;
//         }

//         // Update total P&L
//         const totalPnlEl = document.getElementById('total-pnl');
//         if (totalPnlEl) {
//             const pnl = parseFloat(portfolio.total_pnl_usd || 0);
//             totalPnlEl.textContent = `${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}`;
//             totalPnlEl.className = `metric-value ${pnl >= 0 ? 'text-success' : 'text-danger'}`;
//         }

//         // Update positions count
//         const positionsCountEl = document.getElementById('positions-count');
//         if (positionsCountEl) {
//             positionsCountEl.textContent = portfolio.positions?.open_count || 0;
//         }

//         // Update trades count
//         const tradesCountEl = document.getElementById('trades-count');
//         if (tradesCountEl) {
//             tradesCountEl.textContent = portfolio.trades?.total_count || 0;
//         }

//         // Phase 6B: Update gas savings stats
//         const gasSavingsEl = document.getElementById('gas-savings-total');
//         if (gasSavingsEl) {
//             gasSavingsEl.textContent = `${(portfolio.gas_savings_percent || 0).toFixed(1)}%`;
//         }
//     }

//     /**
//      * Update session status display
//      */
//     updateSessionStatus(session) {
//         const statusEl = document.getElementById('session-status');
//         if (statusEl) {
//             statusEl.textContent = session ? 'Active' : 'Inactive';
//             statusEl.className = `badge ${session ? 'bg-success' : 'bg-secondary'}`;
//         }
//     }

//     /**
//      * Toggle session-dependent UI elements
//      */
//     toggleSessionUI(enabled) {
//         const sessionButtons = document.querySelectorAll('[data-requires-session]');
//         sessionButtons.forEach(button => {
//             button.disabled = !enabled;
//         });

//         const startButton = document.querySelector('[data-action="start-session"]');
//         const stopButton = document.querySelector('[data-action="stop-session"]');

//         if (startButton) startButton.style.display = enabled ? 'none' : 'inline-block';
//         if (stopButton) stopButton.style.display = enabled ? 'inline-block' : 'none';
//     }

//     /**
//      * Cancel transaction (if possible)
//      */
//     async cancelTransaction(transactionId) {
//         try {
//             const response = await fetch(`/api/trading/cancel/${transactionId}/`, {
//                 method: 'POST',
//                 headers: {
//                     'X-CSRFToken': this.getCsrfToken(),
//                     'Content-Type': 'application/json'
//                 }
//             });

//             const result = await response.json();

//             if (result.success) {
//                 this.showNotification('Transaction cancelled successfully', 'success');
//             } else {
//                 this.showNotification(`Cannot cancel: ${result.error}`, 'warning');
//             }

//             return result;

//         } catch (error) {
//             console.error('❌ Cancel transaction error:', error);
//             this.showNotification('Failed to cancel transaction', 'error');
//             return { success: false, error: error.message };
//         }
//     }

//     /**
//      * Helper methods for Transaction Manager UI
//      */
//     getProgressBarClass(status) {
//         if (['completed', 'confirmed'].includes(status.toLowerCase())) {
//             return 'bg-success';
//         } else if (status.toLowerCase() === 'failed') {
//             return 'bg-danger';
//         } else if (status.toLowerCase() === 'cancelled') {
//             return 'bg-secondary';
//         }
//         return 'bg-info';
//     }

//     formatHash(hash) {
//         if (!hash || hash === '0x') return '';
//         return `${hash.slice(0, 6)}...${hash.slice(-4)}`;
//     }

//     getExplorerUrl(hash) {
//         // Default to Base explorer, could make this chain-specific
//         return `https://basescan.org/tx/${hash}`;
//     }

//     getActiveTransactionCount() {
//         return this.activeTransactions.size;
//     }

//     // =============================================================================
//     // UTILITY AND HELPER METHODS
//     // =============================================================================

//     /**
//      * Make HTTP request to trading API
//      */
//     async makeRequest(method, endpoint, data = null) {
//         const url = `${this.baseUrl}${endpoint}`;
//         const options = {
//             method,
//             headers: {
//                 'Content-Type': 'application/json',
//                 'X-CSRFToken': this.csrfToken,
//             },
//         };

//         if (data) {
//             options.body = JSON.stringify(data);
//         }

//         const response = await fetch(url, options);

//         if (!response.ok) {
//             throw new Error(`HTTP ${response.status}: ${response.statusText}`);
//         }

//         return await response.json();
//     }

//     /**
//      * Show notification to user
//      */
//     showNotification(message, type = 'info', duration = 5000) {
//         const notification = {
//             id: Date.now(),
//             message,
//             type,
//             timestamp: new Date()
//         };

//         this.notifications.push(notification);
//         this.displayNotification(notification);

//         // Remove notification after duration
//         setTimeout(() => {
//             this.removeNotification(notification.id);
//         }, duration);
//     }

//     /**
//      * Display notification in UI
//      */
//     displayNotification(notification) {
//         const container = document.getElementById('notifications-container') || this.createNotificationsContainer();

//         const alertClass = {
//             'success': 'alert-success',
//             'error': 'alert-danger',
//             'warning': 'alert-warning',
//             'info': 'alert-info'
//         }[notification.type] || 'alert-info';

//         const notificationHtml = `
//             <div class="alert ${alertClass} alert-dismissible fade show" id="notification-${notification.id}">
//                 <i class="bi bi-${this.getNotificationIcon(notification.type)} me-2"></i>
//                 ${notification.message}
//                 <button type="button" class="btn-close" onclick="window.tradingManager.removeNotification(${notification.id})"></button>
//             </div>
//         `;

//         container.insertAdjacentHTML('beforeend', notificationHtml);
//     }

//     /**
//      * Remove notification from UI
//      */
//     removeNotification(notificationId) {
//         const element = document.getElementById(`notification-${notificationId}`);
//         if (element) {
//             element.remove();
//         }

//         this.notifications = this.notifications.filter(n => n.id !== notificationId);
//     }

//     /**
//      * Create notifications container if it doesn't exist
//      */
//     createNotificationsContainer() {
//         const container = document.createElement('div');
//         container.id = 'notifications-container';
//         container.className = 'position-fixed top-0 end-0 p-3';
//         container.style.zIndex = '9999';
//         document.body.appendChild(container);
//         return container;
//     }

//     /**
//      * Get notification icon based on type
//      */
//     getNotificationIcon(type) {
//         const icons = {
//             'success': 'check-circle',
//             'error': 'exclamation-triangle',
//             'warning': 'exclamation-triangle',
//             'info': 'info-circle'
//         };
//         return icons[type] || 'info-circle';
//     }

//     /**
//      * Get badge class for status
//      */
//     getStatusBadgeClass(status) {
//         const classes = {
//             'OPEN': 'bg-success',
//             'CLOSED': 'bg-secondary',
//             'PENDING': 'bg-warning',
//             'COMPLETED': 'bg-success',
//             'FAILED': 'bg-danger',
//             'CANCELLED': 'bg-secondary',
//             'CLOSING': 'bg-warning',
//             // Phase 6B Transaction Manager statuses
//             'preparing': 'bg-info',
//             'gas_optimizing': 'bg-warning',
//             'ready_to_submit': 'bg-primary',
//             'submitted': 'bg-info',
//             'pending': 'bg-warning',
//             'confirming': 'bg-warning',
//             'confirmed': 'bg-success',
//             'completed': 'bg-success',
//             'failed': 'bg-danger',
//             'cancelled': 'bg-secondary'
//         };
//         return classes[status] || 'bg-secondary';
//     }

//     /**
//      * Get badge class for trade type
//      */
//     getTradeBadgeClass(tradeType) {
//         return tradeType === 'BUY' ? 'bg-success' : 'bg-danger';
//     }

//     /**
//      * Handle real-time updates from server (legacy SSE)
//      */
//     handleRealTimeUpdate(data) {
//         if (data.type === 'trade_update') {
//             this.handleTradeUpdate(data.trade);
//         } else if (data.type === 'position_update') {
//             this.handlePositionUpdate(data.position);
//         } else if (data.type === 'portfolio_update') {
//             this.updatePortfolioDisplay(data.portfolio);
//         }
//     }

//     /**
//      * Handle trade updates
//      */
//     handleTradeUpdate(trade) {
//         // Update trades map
//         this.trades.set(trade.trade_id, trade);

//         // Update UI
//         this.updateTradeHistoryDisplay(Array.from(this.trades.values()));

//         // Show notification for important updates
//         if (trade.status === 'COMPLETED') {
//             this.showNotification(`Trade ${trade.trade_id} completed successfully!`, 'success');
//         } else if (trade.status === 'FAILED') {
//             this.showNotification(`Trade ${trade.trade_id} failed: ${trade.error_message}`, 'error');
//         }
//     }

//     /**
//      * Handle position updates
//      */
//     handlePositionUpdate(position) {
//         // Update positions map
//         this.positions.set(position.position_id, position);

//         // Update UI
//         this.updatePositionsDisplay(Array.from(this.positions.values()));

//         // Phase 3: Update positions chart
//         if (this.enableInteractiveCharts) {
//             this.updatePositionsChart(Array.from(this.positions.values()));
//         }
//     }

//     /**
//      * Monitor trade status via polling (legacy)
//      */
//     async monitorTradeStatus(tradeId, taskId) {
//         const maxAttempts = 30; // Monitor for 5 minutes (10s intervals)
//         let attempts = 0;

//         const checkStatus = async () => {
//             try {
//                 attempts++;

//                 const response = await this.makeRequest('GET', `/history/?trade_id=${tradeId}`);

//                 if (response.success && response.trades.length > 0) {
//                     const trade = response.trades[0];

//                     if (trade.status === 'COMPLETED' || trade.status === 'FAILED') {
//                         this.handleTradeUpdate(trade);
//                         return; // Stop monitoring
//                     }
//                 }

//                 if (attempts < maxAttempts) {
//                     setTimeout(checkStatus, 10000); // Check again in 10 seconds
//                 }

//             } catch (error) {
//                 console.error('Error monitoring trade status:', error);
//             }
//         };

//         // Start monitoring after 5 seconds
//         setTimeout(checkStatus, 5000);
//     }

//     /**
//      * Add pending trade to UI immediately
//      */
//     addPendingTrade(trade) {
//         // Add to trades map
//         this.trades.set(trade.trade_id, trade);

//         // Update trade history display
//         this.loadTradeHistory();

//         // Show in quick stats
//         const pendingTradesEl = document.getElementById('pending-trades-count');
//         if (pendingTradesEl) {
//             const currentCount = parseInt(pendingTradesEl.textContent) || 0;
//             pendingTradesEl.textContent = currentCount + 1;
//         }
//     }

//     /**
//      * Set loading state for UI elements
//      */
//     setLoadingState(loading) {
//         const buttons = document.querySelectorAll('.trading-submit-btn');
//         buttons.forEach(btn => {
//             btn.disabled = loading;
//             btn.textContent = loading ? 'Processing...' : 'Submit Order';
//         });
//     }

//     /**
//      * Setup event handlers for Page Visibility API and cleanup
//      */
//     setupEventHandlers() {
//         // Handle page visibility changes to manage WebSocket connection
//         document.addEventListener('visibilitychange', () => {
//             if (document.hidden) {
//                 console.log('📱 Page hidden - maintaining WebSocket connection');
//             } else {
//                 console.log('📱 Page visible - ensuring WebSocket connection');
//                 if (!this.websocket || this.websocket.readyState !== WebSocket.OPEN) {
//                     this.initializeWebSocket();
//                 }
//                 if (this.enableInteractiveCharts &&
//                     (!this.chartsWebsocket || this.chartsWebsocket.readyState !== WebSocket.OPEN)) {
//                     this.initializeChartsWebSocket();
//                 }
//             }
//         });

//         // Handle beforeunload to close connections cleanly
//         window.addEventListener('beforeunload', () => {
//             this.destroy();
//         });
//     }

//     // Modal and form helper methods
//     showBuyOrderModal(tokenAddress, amount) {
//         // Enhanced modal with Transaction Manager V2 option
//         const useV2 = confirm(`Use Transaction Manager V2 with gas optimization?\n\nV2 Features:\n• Real-time transaction status\n• Gas optimization (avg 23% savings)\n• Transaction progress tracking\n\nClick OK for V2, Cancel for traditional`);

//         if (useV2) {
//             this.useTransactionManagerV2 = true;
//         }

//         // Simple implementation - you can enhance with Bootstrap modals
//         const tokenAddr = prompt('Token Address:', tokenAddress || '');
//         const ethAmount = prompt('ETH Amount:', amount || '0.1');

//         if (tokenAddr && ethAmount) {
//             const formData = new FormData();
//             formData.append('token_address', tokenAddr);
//             formData.append('amount_eth', ethAmount);
//             formData.append('slippage_tolerance', '0.005');
//             formData.append('chain_id', '8453');
//             formData.append('gas_strategy', 'balanced');
//             formData.append('is_paper_trade', 'false');

//             if (this.useTransactionManagerV2) {
//                 this.executeBuyOrderV2(formData);
//             } else {
//                 this.executeBuyOrder(formData);
//             }
//         }
//     }

//     showSellOrderModal(tokenAddress, amount) {
//         // Simple implementation - you can enhance with Bootstrap modals
//         const tokenAddr = prompt('Token Address:', tokenAddress || '');
//         const tokenAmount = prompt('Token Amount:', amount || '100');

//         if (tokenAddr && tokenAmount) {
//             const formData = new FormData();
//             formData.append('token_address', tokenAddr);
//             formData.append('token_amount', tokenAmount);
//             formData.append('slippage_tolerance', '0.005');
//             formData.append('chain_id', '8453');

//             this.executeSellOrder(formData);
//         }
//     }

//     showClosePositionModal(positionId) {
//         const percentage = prompt('Close what percentage of position? (1-100)', '100');

//         if (percentage && percentage > 0 && percentage <= 100) {
//             const formData = new FormData();
//             formData.append('position_id', positionId);
//             formData.append('percentage', percentage);

//             this.closePosition(formData);
//         }
//     }

//     async closePosition(formData) {
//         try {
//             this.showNotification('Closing position...', 'info');

//             const response = await this.makeRequest('POST', '/positions/close/', {
//                 position_id: formData.get('position_id'),
//                 percentage: parseFloat(formData.get('percentage') || '100')
//             });

//             if (response.success) {
//                 this.showNotification('Position close order submitted!', 'success');
//                 this.loadPositions(); // Refresh positions
//             } else {
//                 throw new Error(response.error || 'Failed to close position');
//             }

//         } catch (error) {
//             console.error('Close position error:', error);
//             this.showNotification(`Failed to close position: ${error.message}`, 'error');
//         }
//     }

//     closeModal(modalId) {
//         // Helper method for closing modals
//         const modal = document.getElementById(modalId);
//         if (modal) {
//             modal.style.display = 'none';
//         }
//     }

//     /**
//      * Get CSRF token from meta tag or cookie
//      */
//     getCsrfToken() {
//         const token = document.querySelector('meta[name="csrf-token"]') ||
//             document.querySelector('[name=csrfmiddlewaretoken]');
//         return token ? token.getAttribute('content') || token.value : '';
//     }

//     /**
//      * Initialize WebSocket connection for real-time transaction updates
//      */
//     initializeWebSocket() {
//         try {
//             const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
//             const wsUrl = `${wsProtocol}//${window.location.host}/ws/dashboard/metrics/`;

//             this.websocket = new WebSocket(wsUrl);

//             this.websocket.onopen = (event) => {
//                 console.log('🔗 Transaction Manager WebSocket connected');
//                 this.reconnectAttempts = 0;
//                 this.reconnectDelay = 1000;
//                 this.showNotification('Real-time transaction updates connected', 'success', 2000);
//             };

//             this.websocket.onmessage = (event) => {
//                 try {
//                     const data = JSON.parse(event.data);
//                     this.handleWebSocketMessage(data);
//                 } catch (error) {
//                     console.error('❌ Error parsing WebSocket message:', error);
//                 }
//             };

//             this.websocket.onclose = (event) => {
//                 console.log('🔌 Transaction Manager WebSocket disconnected');
//                 this.handleWebSocketClose();
//             };

//             this.websocket.onerror = (error) => {
//                 console.error('❌ WebSocket error:', error);
//             };

//         } catch (error) {
//             console.error('❌ Failed to initialize WebSocket:', error);
//             this.showNotification('Real-time transaction updates unavailable', 'warning');
//         }
//     }

//     /**
//      * Handle WebSocket disconnection with exponential backoff reconnection
//      */
//     handleWebSocketClose() {
//         if (this.reconnectAttempts < this.maxReconnectAttempts) {
//             this.reconnectAttempts++;

//             console.log(`🔄 Attempting to reconnect WebSocket (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);

//             setTimeout(() => {
//                 this.initializeWebSocket();
//             }, this.reconnectDelay);

//             // Exponential backoff
//             this.reconnectDelay = Math.min(this.reconnectDelay * 2, 30000);
//         } else {
//             console.error('❌ WebSocket reconnection failed after maximum attempts');
//             this.showNotification('Real-time updates disconnected', 'error');
//         }
//     }

//     /**
//      * Handle incoming WebSocket messages
//      */
//     handleWebSocketMessage(data) {
//         switch (data.type) {
//             case 'transaction_update':
//                 this.handleTransactionUpdate(data);
//                 break;
//             case 'status_update':
//                 if (data.data && data.data.type === 'transaction_update') {
//                     this.handleTransactionUpdate(data.data);
//                 }
//                 break;
//             case 'connection_confirmed':
//                 console.log('✅ WebSocket connection confirmed');
//                 break;
//             default:
//                 // Handle legacy real-time updates
//                 this.handleRealTimeUpdate(data);
//         }
//     }

//     /**
//      * Handle real-time transaction status updates from Transaction Manager
//      */
//     handleTransactionUpdate(data) {
//         const transactionId = data.transaction_id;
//         const status = data.status;
//         const gasUsed = data.gas_used;
//         const gasSavingsPercent = data.gas_savings_percent;
//         const errorMessage = data.error_message;
//         const transactionHash = data.transaction_hash;
//         const executionTime = data.execution_time_ms;

//         console.log(`📊 Transaction Manager Update: ${transactionId} → ${status}`);

//         // Update active transactions map
//         this.activeTransactions.set(transactionId, {
//             ...data,
//             lastUpdate: new Date()
//         });

//         // Update UI based on status
//         this.updateTransactionUI(transactionId, {
//             status,
//             gasUsed,
//             gasSavingsPercent,
//             errorMessage,
//             transactionHash,
//             executionTime
//         });

//         // Show status-specific notifications
//         this.showTransactionNotification(transactionId, status, {
//             gasSavingsPercent,
//             errorMessage,
//             executionTime
//         });

//         // Clean up completed transactions
//         if (['completed', 'failed', 'cancelled'].includes(status.toLowerCase())) {
//             setTimeout(() => {
//                 this.activeTransactions.delete(transactionId);
//                 // Remove UI element after delay
//                 const element = document.getElementById(`transaction-${transactionId}`);
//                 if (element) {
//                     element.remove();
//                 }
//             }, 120000); // Keep for 2 minutes after completion
//         }
//     }

//     /**
//      * Update transaction UI elements with real-time data
//      */
//     updateTransactionUI(transactionId, details) {
//         // Update transaction status badge
//         const statusElement = document.getElementById(`tx-status-${transactionId}`);
//         if (statusElement) {
//             statusElement.textContent = details.status.toUpperCase();
//             statusElement.className = `badge ${this.getStatusBadgeClass(details.status)}`;
//         }

//         // Update transaction hash link
//         if (details.transactionHash && details.transactionHash !== '0x') {
//             const hashElement = document.getElementById(`tx-hash-${transactionId}`);
//             if (hashElement) {
//                 hashElement.href = this.getExplorerUrl(details.transactionHash);
//                 hashElement.textContent = this.formatHash(details.transactionHash);
//                 hashElement.style.display = 'inline';
//             }
//         }

//         // Update gas savings display (Phase 6B feature)
//         if (details.gasSavingsPercent) {
//             const gasSavingsElement = document.getElementById(`tx-gas-savings-${transactionId}`);
//             if (gasSavingsElement) {
//                 const savings = parseFloat(details.gasSavingsPercent).toFixed(2);
//                 gasSavingsElement.textContent = `${savings}% saved`;
//                 gasSavingsElement.className = 'text-success fw-bold';
//             }
//         }

//         // Update gas used
//         if (details.gasUsed) {
//             const gasUsedElement = document.getElementById(`tx-gas-used-${transactionId}`);
//             if (gasUsedElement) {
//                 gasUsedElement.textContent = details.gasUsed.toLocaleString();
//             }
//         }

//         // Update execution time
//         if (details.executionTime) {
//             const executionTimeElement = document.getElementById(`tx-execution-time-${transactionId}`);
//             if (executionTimeElement) {
//                 const seconds = (details.executionTime / 1000).toFixed(2);
//                 executionTimeElement.textContent = `${seconds}s`;
//             }
//         }

//         // Update error message if present
//         if (details.errorMessage) {
//             const errorElement = document.getElementById(`tx-error-${transactionId}`);
//             if (errorElement) {
//                 errorElement.textContent = details.errorMessage;
//                 errorElement.style.display = 'block';
//             }
//         }

//         // Update progress bar
//         this.updateTransactionProgress(transactionId, details.status);
//     }

//     /**
//      * Update transaction progress indicator
//      */
//     updateTransactionProgress(transactionId, status) {
//         const progressElement = document.getElementById(`tx-progress-${transactionId}`);
//         if (!progressElement) return;

//         const progressSteps = {
//             'preparing': 10,
//             'gas_optimizing': 25,
//             'ready_to_submit': 40,
//             'submitted': 60,
//             'pending': 75,
//             'confirming': 90,
//             'confirmed': 95,
//             'completed': 100,
//             'failed': 100,
//             'cancelled': 100
//         };

//         const progress = progressSteps[status.toLowerCase()] || 0;
//         const progressBar = progressElement.querySelector('.progress-bar');

//         if (progressBar) {
//             progressBar.style.width = `${progress}%`;
//             progressBar.setAttribute('aria-valuenow', progress);

//             // Update progress bar color based on status
//             const statusClass = this.getProgressBarClass(status);
//             progressBar.className = `progress-bar ${statusClass}`;

//             // Add animation for active states
//             if (['preparing', 'gas_optimizing', 'submitted', 'pending', 'confirming'].includes(status.toLowerCase())) {
//                 progressBar.classList.add('progress-bar-striped', 'progress-bar-animated');
//             } else {
//                 progressBar.classList.remove('progress-bar-striped', 'progress-bar-animated');
//             }
//         }
//     }

//     /**
//      * Show transaction-specific notifications
//      */
//     showTransactionNotification(transactionId, status, details) {
//         let message = '';
//         let type = 'info';

//         switch (status.toLowerCase()) {
//             case 'gas_optimizing':
//                 message = 'Optimizing gas prices for maximum savings...';
//                 type = 'info';
//                 break;
//             case 'submitted':
//                 message = 'Transaction submitted to blockchain';
//                 type = 'info';
//                 break;
//             case 'confirmed':
//                 message = `Transaction confirmed!`;
//                 if (details.gasSavingsPercent) {
//                     message += ` Gas savings: ${parseFloat(details.gasSavingsPercent).toFixed(2)}%`;
//                 }
//                 type = 'success';
//                 break;
//             case 'completed':
//                 message = 'Transaction completed successfully!';
//                 if (details.executionTime) {
//                     const seconds = (details.executionTime / 1000).toFixed(2);
//                     message += ` Execution time: ${seconds}s`;
//                 }
//                 type = 'success';
//                 break;
//             case 'failed':
//                 message = `Transaction failed: ${details.errorMessage || 'Unknown error'}`;
//                 type = 'error';
//                 break;
//             case 'cancelled':
//                 message = 'Transaction cancelled';
//                 type = 'warning';
//                 break;
//         }

//         if (message) {
//             this.showNotification(message, type, 4000); // Show for 4 seconds
//         }
//     }

//     /**
//      * Create UI elements for transaction tracking (Phase 6B)
//      */
//     createTransactionTrackingUI(transactionId, transactionData) {
//         const container = document.getElementById('active-transactions-container') ||
//             document.getElementById('positions-container');
//         if (!container) return;

//         const transactionElement = document.createElement('div');
//         transactionElement.id = `transaction-${transactionId}`;
//         transactionElement.className = 'transaction-tracker mb-3 p-3 border rounded bg-light';
//         transactionElement.innerHTML = `
//             <div class="d-flex justify-content-between align-items-start mb-2">
//                 <div>
//                     <h6 class="mb-1">
//                         <i class="bi bi-cpu me-2"></i>Transaction Manager
//                         <span class="text-muted">${transactionId.slice(-8)}...</span>
//                         <span id="tx-status-${transactionId}" class="badge ${this.getStatusBadgeClass('submitted')}">
//                             SUBMITTED
//                         </span>
//                     </h6>
//                     <small class="text-muted">
//                         ${transactionData.trade_details.amount_eth} ETH → Token
//                         ${transactionData.trade_details.is_paper_trade ? '(Paper Trading)' : ''}
//                     </small>
//                 </div>
//                 <div class="text-end">
//                     <div id="tx-gas-savings-${transactionId}" class="text-success fw-bold">
//                         ${transactionData.optimization_details?.gas_savings_achieved ?
//                 `${parseFloat(transactionData.optimization_details.gas_savings_achieved).toFixed(2)}% saved` :
//                 'Optimizing gas...'}
//                     </div>
//                     <small class="text-muted">Strategy: ${transactionData.trade_details.gas_strategy}</small>
//                 </div>
//             </div>
            
//             <div class="progress mb-2" style="height: 8px;" id="tx-progress-${transactionId}">
//                 <div class="progress-bar progress-bar-striped progress-bar-animated bg-info" 
//                      style="width: 60%" aria-valuenow="60" aria-valuemin="0" aria-valuemax="100">
//                 </div>
//             </div>
            
//             <div class="row text-center">
//                 <div class="col-3">
//                     <small class="text-muted">Gas Used</small><br>
//                     <span id="tx-gas-used-${transactionId}" class="fw-bold">-</span>
//                 </div>
//                 <div class="col-3">
//                     <small class="text-muted">Execution Time</small><br>
//                     <span id="tx-execution-time-${transactionId}" class="fw-bold">-</span>
//                 </div>
//                 <div class="col-6">
//                     <small class="text-muted">Transaction Hash</small><br>
//                     <a id="tx-hash-${transactionId}" href="#" target="_blank" style="display: none;" class="text-decoration-none">
//                         <i class="bi bi-box-arrow-up-right me-1"></i>View on Explorer
//                     </a>
//                     <span id="tx-hash-placeholder-${transactionId}" class="text-muted">Pending...</span>
//                 </div>
//             </div>
            
//             <div id="tx-error-${transactionId}" class="alert alert-danger mt-2" style="display: none;"></div>
//         `;

//         // Insert at the top of container
//         container.insertBefore(transactionElement, container.firstChild);

//         // Auto-remove completed transactions after delay
//         setTimeout(() => {
//             if (transactionElement.parentNode) {
//                 transactionElement.style.opacity = '0.5';
//                 setTimeout(() => transactionElement.remove(), 30000); // Fade and remove
//             }
//         }, 300000); // Start fade after 5 minutes
//     }

//     /**
//      * Execute buy order with Transaction Manager V2 integration
//      */
//     async executeBuyOrderV2(formData) {
//         try {
//             console.log('🚀 Executing buy order with Transaction Manager V2...');

//             // Show loading state
//             this.setLoadingState(true);

//             const response = await fetch('/api/trading/buy/v2/', {
//                 method: 'POST',
//                 body: formData,
//                 headers: {
//                     'X-CSRFToken': this.getCsrfToken()
//                 }
//             });

//             const result = await response.json();

//             if (result.success) {
//                 const transactionId = result.transaction_id;
//                 const tradeId = result.trade_id;

//                 console.log(`✅ Transaction Manager buy order submitted: ${transactionId}`);

//                 // Add to active transactions for tracking
//                 this.activeTransactions.set(transactionId, {
//                     transaction_id: transactionId,
//                     trade_id: tradeId,
//                     status: result.status,
//                     timestamp: new Date(),
//                     type: 'buy'
//                 });

//                 // Create UI elements for real-time transaction tracking
//                 this.createTransactionTrackingUI(transactionId, result);

//                 // Show success notification with gas savings
//                 let message = 'Buy order submitted with gas optimization!';
//                 if (result.optimization_details && result.optimization_details.gas_savings_achieved) {
//                     message += ` Expected savings: ${parseFloat(result.optimization_details.gas_savings_achieved).toFixed(2)}%`;
//                 }

//                 this.showNotification(message, 'success');

//                 return result;

//             } else {
//                 console.error('❌ Transaction Manager buy order failed:', result.error);
//                 this.showNotification(`Buy order failed: ${result.error}`, 'error');
//                 return result;
//             }

//         } catch (error) {
//             console.error('❌ Transaction Manager buy order execution error:', error);
//             this.showNotification('Buy order execution failed', 'error');
//             return { success: false, error: error.message };

//         } finally {
//             this.setLoadingState(false);
//         }
//     }

//     /**
//      * Bind event listeners for trading UI elements
//      */
//     bindEventListeners() {
//         // Trading action buttons
//         document.addEventListener('click', (e) => {
//             if (e.target.matches('[data-action="buy"]')) {
//                 e.preventDefault();
//                 const tokenAddress = e.target.dataset.tokenAddress;
//                 const amount = e.target.dataset.amount || '0.1';
//                 this.showBuyOrderModal(tokenAddress, amount);
//             }

//             if (e.target.matches('[data-action="sell"]')) {
//                 e.preventDefault();
//                 const tokenAddress = e.target.dataset.tokenAddress;
//                 const amount = e.target.dataset.amount || '100';
//                 this.showSellOrderModal(tokenAddress, amount);
//             }

//             if (e.target.matches('[data-action="close-position"]')) {
//                 e.preventDefault();
//                 const positionId = e.target.dataset.positionId;
//                 this.showClosePositionModal(positionId);
//             }

//             if (e.target.matches('[data-action="start-session"]')) {
//                 e.preventDefault();
//                 this.startTradingSession();
//             }

//             if (e.target.matches('[data-action="stop-session"]')) {
//                 e.preventDefault();
//                 this.stopTradingSession();
//             }

//             // Phase 6B: Cancel transaction button
//             if (e.target.matches('[data-action="cancel-transaction"]')) {
//                 e.preventDefault();
//                 const transactionId = e.target.dataset.transactionId;
//                 this.cancelTransaction(transactionId);
//             }
//         });

//         // Form submissions with enhanced Transaction Manager support
//         document.addEventListener('submit', (e) => {
//             if (e.target.matches('#buy-order-form')) {
//                 e.preventDefault();
//                 const formData = new FormData(e.target);

//                 // Use Transaction Manager V2 if enabled
//                 if (this.useTransactionManagerV2) {
//                     this.executeBuyOrderV2(formData);
//                 } else {
//                     this.executeBuyOrder(formData);
//                 }
//             }

//             if (e.target.matches('#sell-order-form')) {
//                 e.preventDefault();
//                 this.executeSellOrder(new FormData(e.target));
//             }

//             if (e.target.matches('#close-position-form')) {
//                 e.preventDefault();
//                 this.closePosition(new FormData(e.target));
//             }
//         });
//     }

//     /**
//      * Start real-time updates for positions and trades
//      */
//     startRealTimeUpdates() {
//         // Close existing connection
//         if (this.eventSource) {
//             this.eventSource.close();
//         }

//         // Start server-sent events for real-time updates
//         this.eventSource = new EventSource('/dashboard/metrics/stream/');

//         this.eventSource.onmessage = (event) => {
//             try {
//                 const data = JSON.parse(event.data);
//                 this.handleRealTimeUpdate(data);
//             } catch (e) {
//                 console.error('Error parsing real-time update:', e);
//             }
//         };

//         this.eventSource.onerror = (error) => {
//             console.error('Real-time updates connection error:', error);
//             // Attempt to reconnect after 5 seconds
//             setTimeout(() => this.startRealTimeUpdates(), 5000);
//         };
//     }

//     /**
//      * Load initial trading data
//      */
//     async loadInitialData() {
//         try {
//             await Promise.all([
//                 this.loadPositions(),
//                 this.loadTradeHistory(),
//                 this.loadPortfolioSummary()
//             ]);
//         } catch (error) {
//             console.error('Error loading initial trading data:', error);
//         }
//     }

//     /**
//      * Execute a buy order (original method)
//      */
//     async executeBuyOrder(formData) {
//         const buyData = {
//             token_address: formData.get('token_address'),
//             amount_eth: formData.get('amount_eth'),
//             slippage_tolerance: parseFloat(formData.get('slippage_tolerance') || '0.005'),
//             gas_price_gwei: formData.get('gas_price_gwei') ? parseFloat(formData.get('gas_price_gwei')) : null,
//             strategy_id: formData.get('strategy_id') || null,
//             chain_id: parseInt(formData.get('chain_id') || '8453')
//         };

//         try {
//             this.showNotification('Executing buy order...', 'info');

//             const response = await this.makeRequest('POST', '/buy/', buyData);

//             if (response.success) {
//                 this.showNotification(
//                     `Buy order submitted successfully! Trade ID: ${response.trade_id}`,
//                     'success'
//                 );

//                 // Update UI with pending trade
//                 this.addPendingTrade({
//                     trade_id: response.trade_id,
//                     trade_type: 'BUY',
//                     status: 'PENDING',
//                     token_address: buyData.token_address,
//                     amount_eth: buyData.amount_eth,
//                     created_at: new Date().toISOString()
//                 });

//                 // Close modal
//                 this.closeModal('buy-order-modal');

//                 // Start monitoring trade status
//                 this.monitorTradeStatus(response.trade_id, response.task_id);

//             } else {
//                 throw new Error(response.error || 'Buy order failed');
//             }

//         } catch (error) {
//             console.error('Buy order error:', error);
//             this.showNotification(
//                 `Buy order failed: ${error.message}`,
//                 'error'
//             );
//         }
//     }

//     /**
//      * Execute a sell order
//      */
//     async executeSellOrder(formData) {
//         const sellData = {
//             token_address: formData.get('token_address'),
//             token_amount: formData.get('token_amount'),
//             slippage_tolerance: parseFloat(formData.get('slippage_tolerance') || '0.005'),
//             gas_price_gwei: formData.get('gas_price_gwei') ? parseFloat(formData.get('gas_price_gwei')) : null,
//             chain_id: parseInt(formData.get('chain_id') || '8453')
//         };

//         try {
//             this.showNotification('Executing sell order...', 'info');

//             const response = await this.makeRequest('POST', '/sell/', sellData);

//             if (response.success) {
//                 this.showNotification(
//                     `Sell order submitted successfully! Trade ID: ${response.trade_id}`,
//                     'success'
//                 );

//                 // Update UI with pending trade
//                 this.addPendingTrade({
//                     trade_id: response.trade_id,
//                     trade_type: 'SELL',
//                     status: 'PENDING',
//                     token_address: sellData.token_address,
//                     token_amount: sellData.token_amount,
//                     created_at: new Date().toISOString()
//                 });

//                 // Close modal
//                 this.closeModal('sell-order-modal');

//                 // Start monitoring trade status
//                 this.monitorTradeStatus(response.trade_id, response.task_id);

//             } else {
//                 throw new Error(response.error || 'Sell order failed');
//             }

//         } catch (error) {
//             console.error('Sell order error:', error);
//             this.showNotification(
//                 `Sell order failed: ${error.message}`,
//                 'error'
//             );
//         }
//     }

//     /**
//      * Cleanup method
//      */
//     destroy() {
//         // Clean up WebSocket connections
//         if (this.eventSource) {
//             this.eventSource.close();
//         }
//         if (this.websocket) {
//             this.websocket.close();
//         }
//         if (this.chartsWebsocket) {
//             this.chartsWebsocket.close();
//         }

//         // Destroy charts to free memory
//         Object.values(this.charts).forEach(chart => {
//             if (chart) chart.destroy();
//         });

//         console.log('🧹 TradingManager cleanup completed');
//     }
// }

// // Utility function for formatting large numbers (global)
// function formatLargeNumber(num) {
//     if (num >= 1e9) return (num / 1e9).toFixed(2) + 'B';
//     if (num >= 1e6) return (num / 1e6).toFixed(2) + 'M';
//     if (num >= 1e3) return (num / 1e3).toFixed(2) + 'K';
//     return num.toFixed(2);
// }

// // Initialize trading manager when DOM is loaded
// document.addEventListener('DOMContentLoaded', () => {
//     // Only initialize if we're on a page that needs trading functionality
//     if (document.body.dataset.page === 'dashboard' ||
//         document.body.dataset.page === 'trading' ||
//         document.querySelector('[data-trading-enabled]')) {

//         window.tradingManager = new TradingManager();
//         console.log('✅ Trading functionality initialized with Phase 3 Interactive Charts & Phase 6B Transaction Manager');
//     }
// });

// // Export for use in other scripts
// window.TradingManager = TradingManager;