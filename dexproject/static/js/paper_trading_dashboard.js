/**
 * Paper Trading Dashboard JavaScript - WebSocket-First with 30s Backup Polling
 * Location: dexproject/static/js/paper_trading_dashboard.js
 * 
 * UPDATES:
 * - Added account_updated handler for real-time balance updates
 * - Reduced polling: removed 3s trades/positions polling
 * - Kept 30s metrics backup polling only
 * - WebSocket is primary update method
 * - FIXED: Initialize thought counter on page load to count existing thoughts
 */

// ========================================
// Global Configuration
// ========================================
window.paperTradingDashboard = {
    config: {
        apiBaseUrl: '/paper-trading/api/',
        wsUrl: null,  // Will be set dynamically
        metricsUpdateInterval: 30000, // 30 seconds for metrics backup
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
}

/**
 * Handle incoming WebSocket messages
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

            // Trade messages
            case 'trade_executed':
            case 'trade.executed':
            case 'trade_update':        // ADD THIS LINE
            case 'trade.update':        // ADD THIS LINE
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

            // Account messages - NEW!
            case 'account_updated':
            case 'account.updated':
                console.log('Account updated:', message.data);
                handleAccountUpdated(message.data);
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
        // Fetch full metrics which includes portfolio value calculation
        fetchMetrics();
    }
    if (message.session) {
        updateBotStatus(message.session.status === 'RUNNING' || message.session.status === 'active');
    }
}

/**
 * Handle WebSocket error messages
 */
function handleWebSocketErrorMessage(message) {
    const errorMsg = message.message || message.data || 'Unknown error';
    console.error('WebSocket error message:', errorMsg);
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

    showToast(`${side.toUpperCase()} ${symbol} - $${parseFloat(amount).toFixed(2)}`, 'info');

    // Fetch positions to update
    fetchOpenPositions();
}

/**
 * Handle position updated event
 */
function handlePositionUpdated(data) {
    if (!data) return;

    // Update position in table
    updatePositionInTable(data);
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

    // Refresh positions
    fetchOpenPositions();
}

/**
 * Handle account updated event - NEW!
 */
/**
 * Handle account updated event
 */
function handleAccountUpdated(data) {
    if (!data) return;

    console.log('Processing account update:', data);

    // Update total trades
    if (data.total_trades !== undefined) {
        const totalTradesElement = document.getElementById('total-trades');
        if (totalTradesElement) {
            totalTradesElement.textContent = data.total_trades;
        }
    }

    // Update successful/winning trades (signal sends 'winning_trades')
    const winningTrades = data.successful_trades || data.winning_trades;
    if (winningTrades !== undefined) {
        const successfulTradesElement = document.getElementById('successful-trades');
        if (successfulTradesElement) {
            successfulTradesElement.textContent = winningTrades;
        }
    }

    // Calculate and update win rate from winning/total
    if (data.total_trades !== undefined && data.total_trades > 0) {
        const wins = data.winning_trades || data.successful_trades || 0;
        const winRate = (wins / data.total_trades) * 100;
        const winRateElement = document.getElementById('win-rate');
        if (winRateElement) {
            winRateElement.textContent = `${winRate.toFixed(1)}%`;
        }
    }

    // Update balance display
    if (data.account_balance !== undefined) {
        const cashElement = document.getElementById('cash-balance');
        if (cashElement) {
            cashElement.textContent = `${parseFloat(data.account_balance).toFixed(2)}`;
        }
    }
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
/**
 * Handle portfolio update from WebSocket
 */
/**
 * Handle portfolio update from WebSocket
 * Uses pre-calculated values from bot and updates all stat cards
 */
function handlePortfolioUpdate(data) {
    if (!data) return;

    console.log('Processing portfolio update:', data);

    // Use pre-calculated portfolio value from bot (includes cash + positions)
    if (data.portfolio_value !== undefined && !isNaN(data.portfolio_value)) {
        updatePortfolioValue(parseFloat(data.portfolio_value));
    } else {
        // Fallback: calculate manually
        let totalPortfolio = parseFloat(data.account_balance) || 0;
        if (data.positions_value !== undefined) {
            totalPortfolio += parseFloat(data.positions_value);
        }
        updatePortfolioValue(totalPortfolio);
    }

    // Update Total P&L - use pre-calculated value
    if (data.total_pnl !== undefined && !isNaN(data.total_pnl)) {
        updateTotalPnL(parseFloat(data.total_pnl));
    }

    // Update Return Percentage - use pre-calculated value
    if (data.return_percent !== undefined && !isNaN(data.return_percent)) {
        updateReturnPercentage(parseFloat(data.return_percent));
    }

    // Update Win Rate
    if (data.win_rate !== undefined) {
        const winRateElement = document.getElementById('win-rate');
        if (winRateElement) {
            winRateElement.textContent = `${parseFloat(data.win_rate).toFixed(1)}%`;
        }
    }

    // Update 24h Trades (using daily_trades from bot)
    if (data.daily_trades !== undefined) {
        const trades24hElement = document.getElementById('trades-24h');
        if (trades24hElement) {
            trades24hElement.textContent = data.daily_trades;
        }
    }

    // Update Cash Balance display
    // Update Cash Balance display (check both field names for compatibility)
    const cashValue = data.account_balance ?? data.cash_balance;
    if (cashValue !== undefined) {
        const cashElement = document.getElementById('cash-balance');
        if (cashElement) {
            cashElement.textContent = parseFloat(cashValue).toFixed(2);
        }
    }

    // Log for debugging
    console.log(`Portfolio Update: Portfolio=$${parseFloat(data.portfolio_value || 0).toFixed(2)}, ` +
        `P&L=$${parseFloat(data.total_pnl || 0).toFixed(2)}, ` +
        `Return=${parseFloat(data.return_percent || 0).toFixed(2)}%, ` +
        `WinRate=${parseFloat(data.win_rate || 0).toFixed(1)}%`);
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

    const thoughtType = data.action || data.decision_type || 'ANALYSIS';
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
async function fetchRecentTrades() {
    const { config, state } = window.paperTradingDashboard;

    try {
        let url = `${config.apiBaseUrl}trades/recent/?limit=10`;
        if (state.lastTradeUpdate) {
            url += `&since=${state.lastTradeUpdate}`;
        }

        const response = await fetch(url);

        if (response.ok) {
            const trades = await response.json();
            if (trades.length > 0) {
                updateTradesTable(trades);
                state.lastTradeUpdate = new Date().toISOString();
            }
        }
    } catch (error) {
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
                if (data.positions && Array.isArray(data.positions)) {
                    positions = data.positions;
                } else if (data.results && Array.isArray(data.results)) {
                    positions = data.results;
                } else if (data.data && Array.isArray(data.data)) {
                    positions = data.data;
                } else if (data.position_id || data.id) {
                    positions = [data];
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
            const data = await response.json();
            // Extract the metrics object from the response
            if (data.success && data.metrics) {
                updateMetrics(data.metrics);  // ✅ Pass only the metrics object
            } else {
                console.warn('Invalid metrics response:', data);
            }
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
            location.reload();
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
            location.reload();
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
    const statusClass = status === 'completed' ? 'bg-success' :
        status === 'failed' ? 'bg-danger' : 'bg-warning';

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
                ${status.toUpperCase()}
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

    // Update portfolio value - ONLY use portfolio_value (cash + positions)
    // Never fall back to current_balance as that's cash only!
    if (metrics.portfolio_value !== undefined && !isNaN(metrics.portfolio_value)) {
        updatePortfolioValue(metrics.portfolio_value);
    } else {
        console.warn('Portfolio value not provided in metrics, skipping update');
    }
    // Update cash balance
    if (metrics.cash_balance !== undefined && !isNaN(metrics.cash_balance)) {
        const cashElement = document.getElementById('cash-balance');
        if (cashElement) {
            cashElement.textContent = `${parseFloat(metrics.cash_balance).toFixed(2)}`;
        }
    }
    // Update P&L
    if (metrics.total_pnl !== undefined && !isNaN(metrics.total_pnl)) {
        updateTotalPnL(metrics.total_pnl);
    }

    // Update return percentage
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
// Polling Functions (Backup Only - 30s interval)
// ========================================

/**
 * Setup polling intervals for backup metrics refresh
 */
function setupPollingIntervals() {
    const { config, state } = window.paperTradingDashboard;

    // Clear existing intervals
    state.updateIntervals.forEach(interval => clearInterval(interval));
    state.updateIntervals = [];

    // Setup 30-second metrics backup polling only
    const metricsInterval = setInterval(() => {
        console.log('[Backup Polling] Fetching metrics (30s interval)');
        fetchMetrics();
        loadActiveStrategies(); // Also refresh active strategies
    }, config.metricsUpdateInterval);
    state.updateIntervals.push(metricsInterval);

    console.log('Backup polling enabled: 30s metrics & strategies refresh');
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
// Active Strategies Management (Phase 7B - Day 7)
// ========================================

/**
 * Load and display active strategies
 */
async function loadActiveStrategies() {
    try {
        const response = await fetch('/paper-trading/api/strategies/active/');
        const data = await response.json();

        if (data.success) {
            displayActiveStrategies(data.strategies, data.count);
        } else {
            console.error('Failed to load active strategies:', data.error);
        }
    } catch (error) {
        console.error('Error loading active strategies:', error);
    }
}

/**
 * Display active strategies in the widget
 */
function displayActiveStrategies(strategies, count) {
    const container = document.getElementById('active-strategies-container');
    const countBadge = document.getElementById('active-strategies-count');
    const noStrategiesMessage = document.getElementById('no-active-strategies');

    // Update count badge
    if (countBadge) {
        countBadge.textContent = count;
    }

    if (!strategies || strategies.length === 0) {
        // Show empty state
        if (noStrategiesMessage) {
            noStrategiesMessage.style.display = 'block';
        }
        // Hide any existing strategy cards
        const existingCards = container.querySelectorAll('.strategy-card');
        existingCards.forEach(card => card.remove());
        return;
    }

    // Hide empty state message
    if (noStrategiesMessage) {
        noStrategiesMessage.style.display = 'none';
    }

    // Build HTML for strategies
    let html = '';
    strategies.forEach(strategy => {
        const statusColor = strategy.status === 'RUNNING' ? 'success' : 'warning';
        const progressPercent = strategy.progress_percent || 0;
        const pnlClass = strategy.current_pnl >= 0 ? 'text-success' : 'text-danger';
        const pnlSign = strategy.current_pnl >= 0 ? '+' : '';

        html += `
            <div class="strategy-card mb-3" data-strategy-id="${strategy.strategy_id}">
                <div class="d-flex justify-content-between align-items-start mb-2">
                    <div>
                        <span class="badge badge-${strategy.strategy_type.toLowerCase()}">${strategy.strategy_type}</span>
                        <strong class="ms-2">${strategy.token_symbol}</strong>
                    </div>
                    <div class="btn-group btn-group-sm">
                        ${strategy.status === 'RUNNING' ? `
                            <button class="btn btn-sm btn-outline-warning" onclick="pauseStrategy('${strategy.strategy_id}')" title="Pause">
                                <i class="bi bi-pause-fill"></i>
                            </button>
                        ` : `
                            <button class="btn btn-sm btn-outline-success" onclick="resumeStrategy('${strategy.strategy_id}')" title="Resume">
                                <i class="bi bi-play-fill"></i>
                            </button>
                        `}
                        <button class="btn btn-sm btn-outline-danger" onclick="cancelStrategy('${strategy.strategy_id}')" title="Cancel">
                            <i class="bi bi-x-lg"></i>
                        </button>
                    </div>
                </div>
                <div class="progress mb-2" style="height: 6px;">
                    <div class="progress-bar bg-${statusColor}" role="progressbar" 
                         style="width: ${progressPercent}%" 
                         aria-valuenow="${progressPercent}" aria-valuemin="0" aria-valuemax="100">
                    </div>
                </div>
                <div class="d-flex justify-content-between align-items-center">
                    <small class="text-muted">
                        ${strategy.completed_orders}/${strategy.total_orders} orders
                    </small>
                    <div class="text-end">
                        <small class="${pnlClass} fw-bold">
                            ${pnlSign}$${strategy.current_pnl.toFixed(2)}
                        </small>
                        <small class="text-muted ms-2">
                            (${strategy.current_roi >= 0 ? '+' : ''}${strategy.current_roi.toFixed(1)}%)
                        </small>
                    </div>
                </div>
            </div>
        `;
    });

    // Update container (preserve no-strategies message but hide it)
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = html;

    // Remove old strategy cards
    const oldCards = container.querySelectorAll('.strategy-card');
    oldCards.forEach(card => card.remove());

    // Add new strategy cards before the no-strategies message
    const firstChild = container.firstChild;
    tempDiv.querySelectorAll('.strategy-card').forEach(card => {
        container.insertBefore(card, firstChild);
    });
}

/**
 * Pause a running strategy
 */
async function pauseStrategy(strategyId) {
    if (!confirm('Pause this strategy? It will stop executing new orders but can be resumed later.')) {
        return;
    }

    try {
        const response = await fetch(`/paper-trading/api/strategies/${strategyId}/pause/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCsrfToken(),
            }
        });

        const data = await response.json();

        if (data.success) {
            showToast('Strategy paused successfully', 'success');
            loadActiveStrategies(); // Refresh the list
        } else {
            showToast(`Failed to pause strategy: ${data.error}`, 'error');
        }
    } catch (error) {
        console.error('Error pausing strategy:', error);
        showToast('Error pausing strategy', 'error');
    }
}

/**
 * Resume a paused strategy
 */
async function resumeStrategy(strategyId) {
    try {
        const response = await fetch(`/paper-trading/api/strategies/${strategyId}/resume/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCsrfToken(),
            }
        });

        const data = await response.json();

        if (data.success) {
            showToast('Strategy resumed successfully', 'success');
            loadActiveStrategies(); // Refresh the list
        } else {
            showToast(`Failed to resume strategy: ${data.error}`, 'error');
        }
    } catch (error) {
        console.error('Error resuming strategy:', error);
        showToast('Error resuming strategy', 'error');
    }
}

/**
 * Cancel/terminate a strategy permanently
 */
async function cancelStrategy(strategyId) {
    if (!confirm('Cancel this strategy? This action cannot be undone. The strategy will be terminated permanently.')) {
        return;
    }

    try {
        const response = await fetch(`/paper-trading/api/strategies/${strategyId}/cancel/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCsrfToken(),
            }
        });

        const data = await response.json();

        if (data.success) {
            showToast('Strategy cancelled successfully', 'info');
            loadActiveStrategies(); // Refresh the list
        } else {
            showToast(`Failed to cancel strategy: ${data.error}`, 'error');
        }
    } catch (error) {
        console.error('Error cancelling strategy:', error);
        showToast('Error cancelling strategy', 'error');
    }
}

/**
 * Get CSRF token from page
 */
function getCsrfToken() {
    const tokenElement = document.querySelector('[name=csrfmiddlewaretoken]');
    return tokenElement ? tokenElement.value : '';
}
// ========================================
// Initialization
// ========================================

/**
 * Initialize the dashboard
 */
function initializeDashboard() {
    console.log('🚀 Initializing Paper Trading Dashboard (WebSocket-First Mode)');

    // Initialize WebSocket connection
    initializeWebSocket();

    // Initial data fetch
    fetchRecentTrades();
    fetchOpenPositions();
    fetchMetrics();
    loadActiveStrategies();

    // Initialize thought counter from existing server-rendered thoughts
    const thoughtContainer = document.getElementById('thought-log-container');
    if (thoughtContainer) {
        const existingThoughts = thoughtContainer.querySelectorAll('.thought-log-step');
        window.paperTradingDashboard.state.thoughtCount = existingThoughts.length;
        updateThoughtCounter(); // Update the counter display
        console.log(`📊 Initialized with ${existingThoughts.length} existing thoughts`);
    }

    // Setup 30-second backup polling for metrics
    setupPollingIntervals();

    // Setup ping interval to keep WebSocket alive
    setInterval(sendPing, 30000); // Ping every 30 seconds

    console.log('✅ Dashboard initialization complete');
    console.log('📡 WebSocket: Primary update method');
    console.log('🔄 Backup polling: 30s metrics refresh');
}

// Start when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeDashboard);
} else {
    initializeDashboard();
}