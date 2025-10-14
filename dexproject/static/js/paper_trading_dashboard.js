// ========================================
// WebSocket Debug Interceptor - MUST BE FIRST
// ========================================
(function () {
    console.log('🔍 Installing WebSocket interceptor...');

    // Store original WebSocket
    const OriginalWebSocket = window.WebSocket;

    // Track all WebSocket connections
    window.__wsConnections = [];

    // Override WebSocket constructor
    window.WebSocket = function (url, protocols) {
        console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
        console.log('🚨 NEW WEBSOCKET CONNECTION:');
        console.log('📍 URL:', url);
        console.log('🕐 Time:', new Date().toISOString());

        // Get stack trace
        const stack = new Error().stack;
        console.log('📞 Stack trace:', stack);

        // Check for the problematic connection
        if (url.includes('dashboard/charts')) {
            console.error('❌❌❌ FOUND THE PHANTOM CHARTS WEBSOCKET! ❌❌❌');
            console.error('This is trying to connect to:', url);
            console.error('Stack trace will show where it\'s coming from!');

            // Create a fake WebSocket that does nothing
            return {
                send: () => { },
                close: () => { },
                addEventListener: () => { },
                removeEventListener: () => { },
                readyState: 3,
                url: url,
                CONNECTING: 0,
                OPEN: 1,
                CLOSING: 2,
                CLOSED: 3
            };
        }

        // Create real WebSocket for valid connections
        const ws = new OriginalWebSocket(url, protocols);
        window.__wsConnections.push({ url, ws, createdAt: new Date() });

        console.log('✅ WebSocket created successfully');
        console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');

        return ws;
    };

    // Copy WebSocket properties
    Object.setPrototypeOf(window.WebSocket, OriginalWebSocket);
    window.WebSocket.prototype = OriginalWebSocket.prototype;

    console.log('✅ Interceptor installed! Now waiting for WebSocket connections...');
})();

/**
 * Paper Trading Dashboard JavaScript
 * Location: dexproject/static/js/paper_trading_dashboard.js
 * Description: Main JavaScript functionality for the paper trading dashboard
 * 
 * FIXED: Updated WebSocket message handlers to match backend message types
 */

// ========================================
// Global Configuration
// ========================================
window.paperTradingDashboard = {
    config: {
        apiBaseUrl: '/paper-trading/api/',
        wsUrl: null,  // Will be set dynamically
        updateInterval: 5000,      // 5 seconds for AI thoughts (fallback)
        tradesUpdateInterval: 3000, // 3 seconds for trades/positions
        metricsUpdateInterval: 10000, // 10 seconds for metrics
        maxThoughts: 3,            // Limit displayed thoughts
        autoScroll: false,         // Auto-scroll disabled by default
        useWebSocket: true,        // Enable WebSocket for real-time updates
        reconnectDelay: 1000,      // Initial WebSocket reconnect delay
        maxReconnectDelay: 30000, // Maximum reconnect delay
        reconnectAttempts: 0,      // Track reconnection attempts
        maxReconnectAttempts: 10   // Maximum reconnection attempts
    },
    state: {
        lastThoughtUpdate: new Date().toISOString(),
        lastTradeUpdate: null,
        lastPositionUpdate: new Date().toISOString(),
        thoughtCount: 0,
        updateIntervals: [],
        websocket: null,
        wsConnected: false
    }
};

// ========================================
// WebSocket Management
// ========================================

/**
 * Initialize WebSocket connection for real-time updates
 */
function initializeWebSocket() {
    const { config, state } = window.paperTradingDashboard;

    if (!config.useWebSocket) {
        console.log('WebSocket disabled, using polling instead');
        return;
    }

    // Determine WebSocket URL
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/paper-trading/`;
    config.wsUrl = wsUrl;

    console.log('Connecting to WebSocket:', wsUrl);

    try {
        state.websocket = new WebSocket(wsUrl);

        state.websocket.onopen = handleWebSocketOpen;
        state.websocket.onmessage = handleWebSocketMessage;
        state.websocket.onclose = handleWebSocketClose;
        state.websocket.onerror = handleWebSocketError;

    } catch (error) {
        console.error('Failed to create WebSocket connection:', error);
        fallbackToPolling();
    }
}

/**
 * Handle WebSocket connection open
 */
function handleWebSocketOpen(event) {
    const { config, state } = window.paperTradingDashboard;

    console.log('WebSocket connected successfully');
    state.wsConnected = true;
    config.reconnectAttempts = 0;
    config.reconnectDelay = 1000;

    // Update UI to show WebSocket connection
    updateAIStatusIndicator('Live (WS)', 'success');
    showToast('Real-time updates connected', 'success');

    // Remove the subscribe message - the backend doesn't support it
    // The backend automatically subscribes you to the right channels
}

/**
 * Handle incoming WebSocket messages - FIXED VERSION
 */
function handleWebSocketMessage(event) {
    try {
        const message = JSON.parse(event.data);
        console.log('WebSocket message received:', message.type, message);

        switch (message.type) {
            // Connection messages
            case 'connection_confirmed':
                console.log('WebSocket connection confirmed by server');
                handleConnectionConfirmed(message);
                break;

            case 'initial_snapshot':
                console.log('Initial data snapshot received');
                handleInitialSnapshot(message);
                break;

            // Trade messages - FIXED NAMES
            case 'trade_executed':  // Changed from 'trade_update'
            case 'trade.executed':  // Support both formats
                console.log('Trade executed:', message.data);
                handleTradeExecuted(message.data);
                break;

            // Position messages    
            case 'position_updated':
            case 'position.updated':
                console.log('Position updated:', message.data);
                handlePositionUpdated(message.data);
                break;

            case 'position_closed':
            case 'position.closed':
                console.log('Position closed:', message.data);
                handlePositionClosed(message.data);
                break;

            // AI Thought messages
            case 'thought_log_created':
            case 'thought.log.created':
                console.log('AI thought received:', message.data);
                handleThoughtLogCreated(message.data);
                break;

            // Bot status messages
            case 'bot_status_update':
            case 'bot.status.update':
                console.log('Bot status update:', message.data);
                handleBotStatusUpdate(message.data);
                break;

            // Portfolio/Performance messages
            case 'portfolio_update':
            case 'portfolio.update':
                console.log('Portfolio update:', message.data);
                handlePortfolioUpdate(message.data);
                break;

            case 'performance_update':
            case 'performance.update':
                console.log('Performance update:', message.data);
                handlePerformanceUpdate(message.data);
                break;

            // Error messages
            case 'error':
                console.error('Server error:', message.message || message.data);
                handleWebSocketErrorMessage(message);
                break;

            // Ping/Pong
            case 'pong':
                console.log('Pong received');
                break;

            default:
                console.log('Unknown message type:', message.type);
        }

    } catch (error) {
        console.error('Error parsing WebSocket message:', error);
    }
}

/**
 * Handle WebSocket connection close
 */
function handleWebSocketClose(event) {
    const { config, state } = window.paperTradingDashboard;

    console.log('WebSocket disconnected:', event.code, event.reason);
    state.wsConnected = false;
    state.websocket = null;

    updateAIStatusIndicator('Reconnecting...', 'warning');

    // Attempt to reconnect with exponential backoff
    if (config.reconnectAttempts < config.maxReconnectAttempts) {
        config.reconnectAttempts++;

        console.log(`Attempting to reconnect (${config.reconnectAttempts}/${config.maxReconnectAttempts})...`);

        setTimeout(() => {
            initializeWebSocket();
        }, config.reconnectDelay);

        // Exponential backoff
        config.reconnectDelay = Math.min(
            config.reconnectDelay * 2,
            config.maxReconnectDelay
        );
    } else {
        console.error('Max reconnection attempts reached, falling back to polling');
        fallbackToPolling();
    }
}

/**
 * Handle WebSocket errors
 */
function handleWebSocketError(error) {
    console.error('WebSocket error:', error);
    updateAIStatusIndicator('Connection Error', 'danger');
}

/**
 * Fallback to polling mode if WebSocket fails
 */
function fallbackToPolling() {
    const { config, state } = window.paperTradingDashboard;

    console.log('Falling back to polling mode');
    config.useWebSocket = false;
    state.wsConnected = false;

    updateAIStatusIndicator('Live (Polling)', 'info');
    showToast('Using polling mode for updates', 'info');

    // Ensure polling intervals are set up
    if (state.updateIntervals.length === 0) {
        setupPollingIntervals();
    }
}

// ========================================
// WebSocket Message Handlers
// ========================================

/**
 * Handle connection confirmation message
 */
function handleConnectionConfirmed(message) {
    console.log('Connection confirmed with account:', message.account_id);
}

/**
 * Handle initial data snapshot
 */
function handleInitialSnapshot(message) {
    if (message.account) {
        updatePortfolioValue(message.account.current_balance);
    }
    if (message.session) {
        updateBotStatus(message.session.status === 'active');
    }
}

/**
 * Handle WebSocket error messages
 */
function handleWebSocketErrorMessage(message) {
    const errorMsg = message.message || message.data || 'Unknown error';
    console.error('WebSocket error message:', errorMsg);
    // Optionally show toast to user
    // showToast(`Connection error: ${errorMsg}`, 'danger');
}

/**
 * Handle trade executed event
 */
function handleTradeExecuted(data) {
    if (!data) return;

    // Update trades table
    updateTradesTable([data]);

    // Show notification
    const side = data.trade_type || data.side || 'TRADE';
    const symbol = data.token_out_symbol || data.symbol || 'Token';
    const amount = data.amount_in_usd || data.amount || 0;

    showToast(`${side} ${symbol} - $${parseFloat(amount).toFixed(2)}`, 'info');

    // Refresh metrics
    fetchMetrics();
}

/**
 * Handle position updated event
 */
function handlePositionUpdated(data) {
    if (!data) return;

    // Update position in table
    updatePositionInTable(data);

    // Refresh positions
    fetchOpenPositions();
}

/**
 * Handle position closed event
 */
function handlePositionClosed(data) {
    if (!data) return;

    // Remove position from table
    removePositionFromTable(data.position_id || data.id);

    // Show notification
    const symbol = data.token_symbol || data.symbol || 'Position';
    const pnl = data.realized_pnl_usd || data.pnl || 0;
    const pnlClass = pnl >= 0 ? 'success' : 'danger';

    showToast(`Closed ${symbol} - P&L: $${parseFloat(pnl).toFixed(2)}`, pnlClass);

    // Refresh metrics
    fetchMetrics();
}

/**
 * Handle new thought log creation from WebSocket
 */
function handleThoughtLogCreated(data) {
    if (!data) return;

    const thoughtContainer = document.getElementById('thought-log-container');
    if (!thoughtContainer) return;

    // Remove "waiting" message if exists
    const waitingMessage = thoughtContainer.querySelector('.text-center.text-muted');
    if (waitingMessage) {
        waitingMessage.remove();
    }

    // Create thought element
    const thoughtElement = createThoughtElement(data);

    // Add to container (newest first)
    thoughtContainer.insertBefore(thoughtElement, thoughtContainer.firstChild);

    // Update counter
    const { config, state } = window.paperTradingDashboard;
    state.thoughtCount++;
    updateThoughtCounter();

    // Limit displayed thoughts
    const thoughts = thoughtContainer.querySelectorAll('.thought-log-step');
    if (thoughts.length > config.maxThoughts) {
        // Remove oldest thoughts
        for (let i = config.maxThoughts; i < thoughts.length; i++) {
            thoughts[i].remove();
        }
    }

    // Auto-scroll if enabled
    if (config.autoScroll) {
        thoughtContainer.scrollTop = 0;
    }

    // Add animation
    thoughtElement.classList.add('new-thought');
    setTimeout(() => {
        thoughtElement.classList.remove('new-thought');
    }, 2000);
}

/**
 * Handle bot status update
 */
function handleBotStatusUpdate(data) {
    if (!data) return;

    const isRunning = data.status === 'RUNNING' || data.status === 'active';
    updateBotStatus(isRunning);

    if (data.message) {
        showToast(data.message, isRunning ? 'success' : 'warning');
    }
}

/**
 * Handle portfolio update from WebSocket
 */
function handlePortfolioUpdate(data) {
    if (!data) return;

    // Update portfolio value
    if (data.total_value !== undefined) {
        updatePortfolioValue(data.total_value);
    }

    // Update P&L
    if (data.total_pnl !== undefined) {
        updateTotalPnL(data.total_pnl);
    }

    // Update return percentage
    if (data.return_percentage !== undefined) {
        updateReturnPercentage(data.return_percentage);
    }
}

/**
 * Handle performance metrics update
 */
function handlePerformanceUpdate(data) {
    if (!data) return;

    // Update win rate
    if (data.win_rate !== undefined) {
        document.getElementById('win-rate').textContent = `${data.win_rate.toFixed(1)}%`;
    }

    // Update 24h trades
    if (data.trades_24h !== undefined) {
        document.getElementById('trades-24h').textContent = data.trades_24h;
    }

    // Update volume
    if (data.volume_24h !== undefined) {
        document.getElementById('volume-24h').textContent = `$${data.volume_24h.toFixed(2)}`;
    }
}

/**
 * Create thought element from data
 */
function createThoughtElement(data) {
    const thoughtDiv = document.createElement('div');
    thoughtDiv.className = 'thought-log-step';
    thoughtDiv.setAttribute('data-thought-id', data.thought_id || data.id || '');

    const time = new Date(data.created_at || data.timestamp).toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });

    const thoughtType = data.decision_type || data.thought_type || 'ANALYSIS';
    const symbol = data.token_symbol || data.symbol || '';
    const content = data.thought_content || data.content || 'Processing...';

    thoughtDiv.innerHTML = `
        <div class="d-flex justify-content-between align-items-start mb-2">
            <div>
                <strong>${thoughtType}</strong>
                ${symbol ? `<span class="text-muted ms-2">${symbol}</span>` : ''}
            </div>
            <small class="text-muted">${time}</small>
        </div>
        <div class="thought-summary">
            ${content.substring(0, 150)}${content.length > 150 ? '...' : ''}
        </div>
    `;

    return thoughtDiv;
}

// ========================================
// UI Update Functions
// ========================================

/**
 * Update AI status indicator
 */
function updateAIStatusIndicator(status, type) {
    const indicator = document.getElementById('ai-status');
    if (!indicator) return;

    indicator.textContent = status;
    indicator.className = `badge bg-${type} me-3`;
}

/**
 * Update bot status in UI
 */
function updateBotStatus(isRunning) {
    const statusDot = document.querySelector('.status-dot');
    const statusText = document.getElementById('bot-status-text');

    if (statusDot) {
        statusDot.className = isRunning ? 'status-dot status-active' : 'status-dot status-inactive';
    }

    if (statusText) {
        statusText.textContent = isRunning ? 'RUNNING' : 'STOPPED';
    }
}

/**
 * Update portfolio value
 */
function updatePortfolioValue(value) {
    const element = document.getElementById('portfolio-value');
    if (element) {
        element.textContent = `$${parseFloat(value).toFixed(2)}`;
    }
}

/**
 * Update total P&L
 */
function updateTotalPnL(value) {
    const element = document.getElementById('total-pnl');
    if (element) {
        const isPositive = value >= 0;
        element.innerHTML = `
            <span class="${isPositive ? 'text-success' : 'text-danger'}">
                ${isPositive ? '+' : ''}$${Math.abs(value).toFixed(2)}
            </span>
        `;
    }
}


/**
 * Update return percentage
 */
function updateReturnPercentage(value) {
    const element = document.getElementById('return-percent');
    if (element) {
        const isPositive = value >= 0;
        element.className = isPositive ? 'text-success' : 'text-danger';
        element.textContent = `${isPositive ? '+' : ''}${value.toFixed(2)}%`;
    }
}

/**
 * Update thought counter
 */
function updateThoughtCounter() {
    const { state } = window.paperTradingDashboard;

    const countBadge = document.getElementById('thought-count');
    if (countBadge) {
        countBadge.textContent = state.thoughtCount;
    }

    const counterText = document.getElementById('thought-counter-text');
    if (counterText) {
        const thoughtContainer = document.getElementById('thought-log-container');
        const displayedCount = thoughtContainer ?
            thoughtContainer.querySelectorAll('.thought-log-step').length : 0;
        counterText.textContent = `Showing ${displayedCount} latest thoughts`;
    }
}

/**
 * Show toast notification
 */
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toast-container');
    if (!toastContainer) return;

    const toast = document.createElement('div');
    toast.className = `toast bg-${type} text-white`;
    toast.innerHTML = `
        <div class="toast-body">
            ${message}
        </div>
    `;

    toastContainer.appendChild(toast);

    // Auto-remove after 5 seconds
    setTimeout(() => {
        toast.remove();
    }, 5000);
}

// ========================================
// API Functions
// ========================================

/**
 * Fetch recent trades
 */
/**
 * Fetch recent trades with abort controller to prevent race conditions
 */
async function fetchRecentTrades() {
    const { config, state } = window.paperTradingDashboard;

    try {
        let url = `${config.apiBaseUrl}trades/recent/?limit=10`;
        if (state.lastTradeUpdate) {
            url += `&since=${state.lastTradeUpdate}`;
        }

        // Create abort controller if it doesn't exist
        if (!window.paperTradingDashboard.abortController) {
            window.paperTradingDashboard.abortController = new AbortController();
        }

        const response = await fetch(url, {
            signal: window.paperTradingDashboard.abortController.signal
        });

        if (response.ok) {
            const trades = await response.json();
            if (trades.length > 0) {
                updateTradesTable(trades);
                state.lastTradeUpdate = new Date().toISOString();
            }
        }
    } catch (error) {
        // Handle abort errors silently
        if (error.name === 'AbortError') {
            console.log('Fetch request for trades was aborted');
            return;
        }
        console.error('Error fetching trades:', error);
    }
}

/**
 * Fetch open positions
 */
async function fetchOpenPositions() {
    const { config } = window.paperTradingDashboard;

    try {
        const response = await fetch(`${config.apiBaseUrl}positions/open/`);
        if (response.ok) {
            const data = await response.json();

            // Handle both array and object responses
            let positions = [];
            if (Array.isArray(data)) {
                positions = data;
            } else if (data && typeof data === 'object') {
                // If it's an object with a positions property
                if (data.positions && Array.isArray(data.positions)) {
                    positions = data.positions;
                } else if (data.results && Array.isArray(data.results)) {
                    positions = data.results;
                } else if (data.data && Array.isArray(data.data)) {
                    positions = data.data;
                } else {
                    // If it's a single position object, wrap in array
                    if (data.position_id || data.id) {
                        positions = [data];
                    }
                }
            }

            updatePositionsTable(positions);
        }
    } catch (error) {
        console.error('Error fetching positions:', error);
    }
}

/**
 * Fetch performance metrics
 */
async function fetchMetrics() {
    const { config } = window.paperTradingDashboard;

    try {
        const response = await fetch(`${config.apiBaseUrl}metrics/`);
        if (response.ok) {
            const metrics = await response.json();
            updateMetrics(metrics);
        }
    } catch (error) {
        console.error('Error fetching metrics:', error);
    }
}

/**
 * Start the trading bot
 */
async function startBot() {
    const { config } = window.paperTradingDashboard;

    try {
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
        const response = await fetch(`${config.apiBaseUrl}bot/start/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            }
        });

        if (response.ok) {
            showToast('Bot started successfully', 'success');
            location.reload(); // Refresh to update status
        } else {
            const error = await response.json();
            showToast(`Failed to start bot: ${error.message || 'Unknown error'}`, 'danger');
        }
    } catch (error) {
        console.error('Error starting bot:', error);
        showToast('Failed to start bot', 'danger');
    }
}

/**
 * Stop the trading bot
 */
async function stopBot() {
    const { config } = window.paperTradingDashboard;

    try {
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
        const response = await fetch(`${config.apiBaseUrl}bot/stop/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            }
        });

        if (response.ok) {
            showToast('Bot stopped successfully', 'warning');
            location.reload(); // Refresh to update status
        } else {
            const error = await response.json();
            showToast(`Failed to stop bot: ${error.message || 'Unknown error'}`, 'danger');
        }
    } catch (error) {
        console.error('Error stopping bot:', error);
        showToast('Failed to stop bot', 'danger');
    }
}

// ========================================
// Table Update Functions
// ========================================

/**
 * Update trades table with new trades
 */
function updateTradesTable(newTrades) {
    const tableBody = document.getElementById('recent-trades-tbody');
    if (!tableBody) return;

    // Remove no trades message if exists
    const noTradesMessage = tableBody.querySelector('.no-trades-message');
    if (noTradesMessage) {
        noTradesMessage.remove();
    }

    // Add new trades
    newTrades.forEach(trade => {
        const existingRow = tableBody.querySelector(`[data-trade-id="${trade.trade_id || trade.id}"]`);
        if (!existingRow) {
            const row = createTradeRow(trade);
            row.classList.add('new-trade');
            tableBody.insertBefore(row, tableBody.firstChild);
        }
    });

    // Limit to 10 rows
    limitTableRows(tableBody, 10);

    // Remove new-trade class after animation
    setTimeout(() => {
        const newTradeRows = tableBody.querySelectorAll('.new-trade');
        newTradeRows.forEach(row => {
            row.classList.remove('new-trade');
        });
    }, 2000);
}

/**
 * Create a trade table row
 */
function createTradeRow(trade) {
    const tr = document.createElement('tr');
    tr.setAttribute('data-trade-id', trade.trade_id || trade.id);
    tr.className = 'trade-row';

    const time = new Date(trade.created_at || trade.executed_at).toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit'
    });

    const tradeType = trade.trade_type || trade.side || 'TRADE';
    const typeClass = tradeType.toUpperCase() === 'BUY' ? 'bg-success' : 'bg-danger';

    const status = trade.status || 'PENDING';
    const statusClass = status === 'COMPLETED' ? 'bg-success' :
        status === 'FAILED' ? 'bg-danger' : 'bg-warning';

    const symbol = trade.token_out_symbol || trade.token_symbol || trade.symbol || 'N/A';
    const amount = trade.amount_in_usd || trade.amount || 0;

    tr.innerHTML = `
        <td><small>${time}</small></td>
        <td>
            <span class="badge ${typeClass}">
                ${tradeType.toUpperCase()}
            </span>
        </td>
        <td><small>${symbol}</small></td>
        <td><small>$${parseFloat(amount).toFixed(2)}</small></td>
        <td>
            <span class="badge ${statusClass}">
                ${status}
            </span>
        </td>
    `;

    return tr;
}

/**
 * Update positions table
 */
function updatePositionsTable(positions) {
    const tableBody = document.getElementById('open-positions-tbody');
    if (!tableBody) return;

    // Clear existing rows
    tableBody.innerHTML = '';

    // Ensure positions is an array
    if (!Array.isArray(positions)) {
        console.warn('Positions is not an array:', positions);
        positions = [];
    }

    if (positions.length === 0) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="4" class="text-center text-muted py-4">
                    <i class="bi bi-briefcase fs-3 mb-2 d-block"></i>
                    <p class="mb-0">No open positions</p>
                </td>
            </tr>
        `;
        return;
    }

    // Add position rows
    positions.forEach(position => {
        const row = createPositionRow(position);
        tableBody.appendChild(row);
    });
}

/**
 * Create a position table row
 */
function createPositionRow(position) {
    const tr = document.createElement('tr');
    tr.setAttribute('data-position-id', position.position_id || position.id);

    const symbol = position.token_symbol || position.symbol || 'N/A';
    const quantity = position.quantity || 0;
    const value = position.current_value_usd || position.value || 0;
    const pnl = position.unrealized_pnl_usd || position.pnl || 0;
    const pnlClass = pnl >= 0 ? 'text-success' : 'text-danger';

    tr.innerHTML = `
        <td><small>${symbol}</small></td>
        <td><small>${parseFloat(quantity).toFixed(6)}</small></td>
        <td><small>$${parseFloat(value).toFixed(2)}</small></td>
        <td>
            <small class="${pnlClass}">
                ${pnl >= 0 ? '+' : ''}$${Math.abs(pnl).toFixed(2)}
            </small>
        </td>
    `;

    return tr;
}

/**
 * Update position in table
 */
function updatePositionInTable(positionData) {
    const tableBody = document.getElementById('open-positions-tbody');
    if (!tableBody) return;

    const positionId = positionData.position_id || positionData.id;
    const existingRow = tableBody.querySelector(`[data-position-id="${positionId}"]`);

    if (existingRow) {
        // Update existing row
        const newRow = createPositionRow(positionData);
        existingRow.replaceWith(newRow);
    } else {
        // Add new position
        const newRow = createPositionRow(positionData);
        tableBody.appendChild(newRow);

        // Remove "no positions" message if exists
        const noPositionsMsg = tableBody.querySelector('.text-center.text-muted');
        if (noPositionsMsg) {
            noPositionsMsg.closest('tr').remove();
        }
    }
}

/**
 * Remove position from table
 */
function removePositionFromTable(positionId) {
    const tableBody = document.getElementById('open-positions-tbody');
    if (!tableBody) return;

    const row = tableBody.querySelector(`[data-position-id="${positionId}"]`);
    if (row) {
        row.remove();

        // Add "no positions" message if table is empty
        if (tableBody.children.length === 0) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="4" class="text-center text-muted py-4">
                        <i class="bi bi-briefcase fs-3 mb-2 d-block"></i>
                        <p class="mb-0">No open positions</p>
                    </td>
                </tr>
            `;
        }
    }
}

/**
 * Update metrics display
 */
function updateMetrics(metrics) {
    console.log('Updating metrics:', metrics);

    // ✅ Update portfolio value (FIXED)
    if (metrics.portfolio_value !== undefined && !isNaN(metrics.portfolio_value)) {
        updatePortfolioValue(metrics.portfolio_value);
    } else if (metrics.current_balance !== undefined) {
        // Fallback: if portfolio_value missing, at least show balance
        console.warn('portfolio_value missing, showing current_balance');
        updatePortfolioValue(metrics.current_balance);
    }

    // ✅ Update P&L
    if (metrics.total_pnl !== undefined && !isNaN(metrics.total_pnl)) {
        updateTotalPnL(metrics.total_pnl);
    }

    // ✅ Update return percentage (FIXED)
    if (metrics.return_percent !== undefined && !isNaN(metrics.return_percent)) {
        updateReturnPercentage(metrics.return_percent);
    }

    // Update win rate
    if (metrics.win_rate !== undefined) {
        const winRateElement = document.getElementById('win-rate');
        if (winRateElement) {
            winRateElement.textContent = `${metrics.win_rate.toFixed(1)}%`;
        }
    }

    // Update 24h trades
    if (metrics.trades_24h !== undefined) {
        const trades24hElement = document.getElementById('trades-24h');
        if (trades24hElement) {
            trades24hElement.textContent = metrics.trades_24h;
        }
    }

    // Update volume
    if (metrics.volume_24h !== undefined) {
        const volume24hElement = document.getElementById('volume-24h');
        if (volume24hElement) {
            volume24hElement.textContent = `$${metrics.volume_24h.toFixed(2)}`;
        }
    }

    // Update total trades
    if (metrics.total_trades !== undefined) {
        const totalTradesElement = document.getElementById('total-trades');
        if (totalTradesElement) {
            totalTradesElement.textContent = metrics.total_trades;
        }
    }

    // Update successful trades
    if (metrics.successful_trades !== undefined) {
        const successfulTradesElement = document.getElementById('successful-trades');
        if (successfulTradesElement) {
            successfulTradesElement.textContent = metrics.successful_trades;
        }
    }
}

/**
 * Limit table rows to maximum count
 */
function limitTableRows(tableBody, maxRows) {
    const rows = tableBody.querySelectorAll('tr:not(.no-trades-message)');
    if (rows.length > maxRows) {
        for (let i = maxRows; i < rows.length; i++) {
            rows[i].remove();
        }
    }
}

// ========================================
// Polling Functions (Fallback)
// ========================================

/**
 * Setup polling intervals for data updates
 */
function setupPollingIntervals() {
    const { config, state } = window.paperTradingDashboard;

    // Clear existing intervals
    state.updateIntervals.forEach(interval => clearInterval(interval));
    state.updateIntervals = [];

    // Setup trades polling
    const tradesInterval = setInterval(() => {
        fetchRecentTrades();
        fetchOpenPositions();
    }, config.tradesUpdateInterval);
    state.updateIntervals.push(tradesInterval);

    // Setup metrics polling
    const metricsInterval = setInterval(() => {
        fetchMetrics();
    }, config.metricsUpdateInterval);
    state.updateIntervals.push(metricsInterval);

    console.log('Polling intervals set up');
}

// ========================================
// UI Control Functions
// ========================================

/**
 * Toggle auto-scroll for thought log
 */
function toggleAutoScroll() {
    const { config } = window.paperTradingDashboard;
    config.autoScroll = !config.autoScroll;

    const icon = document.getElementById('auto-scroll-icon');
    if (icon) {
        icon.className = config.autoScroll ?
            'bi bi-arrow-repeat text-success' :
            'bi bi-arrow-repeat';
    }

    showToast(config.autoScroll ? 'Auto-scroll enabled' : 'Auto-scroll disabled', 'info');
}

/**
 * Scroll to newest thought
 */
function scrollToNewest() {
    const container = document.getElementById('thought-log-container');
    if (container) {
        container.scrollTop = 0;
    }
}

/**
 * Clear all thoughts
 */
function clearThoughts() {
    const container = document.getElementById('thought-log-container');
    if (container) {
        container.innerHTML = `
            <div class="text-center text-muted py-5">
                <i class="bi bi-cpu fs-1 mb-3 d-block"></i>
                <p class="mb-0">Waiting for AI decisions...</p>
                <small>Start the bot to see live trading thoughts</small>
            </div>
        `;

        const { state } = window.paperTradingDashboard;
        state.thoughtCount = 0;
        updateThoughtCounter();
    }
}

/**
 * Send ping to keep connection alive
 */
function sendPing() {
    const { state } = window.paperTradingDashboard;

    if (state.websocket && state.websocket.readyState === WebSocket.OPEN) {
        state.websocket.send(JSON.stringify({
            type: 'ping',
            timestamp: new Date().toISOString()
        }));
    }
}

// ========================================
// Initialization
// ========================================

/**
 * Initialize the dashboard
 */
function initializeDashboard() {
    console.log('Initializing Paper Trading Dashboard');

    // Initialize WebSocket connection
    initializeWebSocket();

    // Setup initial data fetch
    fetchRecentTrades();
    fetchOpenPositions();
    fetchMetrics();

    // Setup polling as backup (or primary if WebSocket fails)
    if (!window.paperTradingDashboard.config.useWebSocket) {
        setupPollingIntervals();
    }

    // Setup ping interval to keep WebSocket alive
    setInterval(sendPing, 30000); // Ping every 30 seconds

    console.log('Dashboard initialization complete');
}

// Start when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeDashboard);
} else {
    initializeDashboard();
}