/**
 * Paper Trading Dashboard JavaScript
 * Location: dexproject/static/js/paper_trading_dashboard.js
 * Description: Main JavaScript functionality for the paper trading dashboard
 */

// ========================================
// Global Configuration
// ========================================
window.paperTradingDashboard = {
    config: {
        apiBaseUrl: '/paper-trading/api/',
        updateInterval: 5000,      // 5 seconds for AI thoughts
        tradesUpdateInterval: 3000, // 3 seconds for trades/positions
        metricsUpdateInterval: 10000, // 10 seconds for metrics
        maxThoughts: 3,            // Limit displayed thoughts
        autoScroll: false          // Auto-scroll disabled by default
    },
    state: {
        lastThoughtUpdate: new Date().toISOString(),
        lastTradeUpdate: null,
        lastPositionUpdate: new Date().toISOString(),
        thoughtCount: 0,
        updateIntervals: []
    }
};

// ========================================
// AI Thoughts Management
// ========================================

/**
 * Fetch and update AI thoughts from the API
 */
function updateAIThoughts() {
    const { lastThoughtUpdate } = window.paperTradingDashboard.state;

    fetch(`/paper-trading/api/ai-thoughts/?since=${lastThoughtUpdate}&limit=5`)
        .then(response => response.json())
        .then(data => {
            if (data.thoughts && data.thoughts.length > 0) {
                updateThoughtsDisplay(data.thoughts);
                window.paperTradingDashboard.state.lastThoughtUpdate = new Date().toISOString();
                updateAIStatusIndicator('Live', 'success');
            }
        })
        .catch(error => {
            console.error('Error fetching AI thoughts:', error);
            updateAIStatusIndicator('Error', 'danger');
        });
}

/**
 * Update the AI status indicator badge
 * @param {string} status - Status text to display
 * @param {string} type - Badge type (success, danger, warning)
 */
function updateAIStatusIndicator(status, type) {
    const statusElement = document.getElementById('ai-status');
    if (statusElement) {
        statusElement.textContent = status;
        statusElement.className = `badge bg-${type}`;
    }
}

/**
 * Update the thoughts display with new thoughts
 * @param {Array} newThoughts - Array of thought objects
 */
function updateThoughtsDisplay(newThoughts) {
    const container = document.getElementById('thought-log-container');
    if (!container) return;

    const { maxThoughts, autoScroll } = window.paperTradingDashboard.config;

    // Remove placeholder if exists
    const placeholder = container.querySelector('.text-center');
    if (placeholder && newThoughts.length > 0) {
        placeholder.remove();
    }

    // Add new thoughts
    newThoughts.reverse().forEach(thought => {
        if (!document.querySelector(`[data-thought-id="${thought.id}"]`)) {
            const thoughtElement = createThoughtElement(thought);
            thoughtElement.classList.add('fade-in');
            container.insertBefore(thoughtElement, container.firstChild);
            window.paperTradingDashboard.state.thoughtCount++;
        }
    });

    // Remove excess thoughts
    removeExcessThoughts(container, maxThoughts);
    updateThoughtCounter();

    if (autoScroll) {
        scrollToNewest();
    }
}

/**
 * Create a thought element DOM node
 * @param {Object} thought - Thought data object
 * @returns {HTMLElement} - Created thought element
 */
function createThoughtElement(thought) {
    const div = document.createElement('div');
    div.className = 'thought-log-step';
    div.setAttribute('data-thought-id', thought.id);

    const time = new Date(thought.timestamp).toLocaleTimeString();
    const laneClass = thought.lane_used === 'FAST' ? 'fast-lane-badge' : 'smart-lane-badge';
    const confidence = Math.round(thought.confidence_percent || 0);

    const reasoning = thought.primary_reasoning || 'Analyzing market conditions...';
    const truncatedReasoning = reasoning.length > 150 ?
        reasoning.substring(0, 150) + '...' : reasoning;

    div.innerHTML = `
        <div class="d-flex justify-content-between align-items-start mb-2">
            <div>
                <strong>${thought.decision_type}</strong>
                <span class="text-muted ms-2">${thought.token_symbol}</span>
                <span class="lane-badge ${laneClass} ms-2">${thought.lane_used}</span>
            </div>
            <small class="text-muted">${time}</small>
        </div>
        <div class="d-flex align-items-center mb-2">
            <small class="me-2">Confidence:</small>
            <div class="confidence-bar flex-grow-1">
                <div class="confidence-fill" style="width: ${confidence}%"></div>
            </div>
            <small class="ms-2 fw-bold">${confidence}%</small>
        </div>
        <div class="thought-summary">
            ${truncatedReasoning}
        </div>
    `;

    return div;
}

/**
 * Remove excess thoughts beyond the max limit
 * @param {HTMLElement} container - Thoughts container element
 * @param {number} maxThoughts - Maximum number of thoughts to display
 */
function removeExcessThoughts(container, maxThoughts) {
    const thoughtItems = container.querySelectorAll('.thought-log-step:not(.text-center)');
    if (thoughtItems.length > maxThoughts) {
        for (let i = maxThoughts; i < thoughtItems.length; i++) {
            const item = thoughtItems[i];
            item.classList.add('fade-out');
            setTimeout(() => {
                if (item.parentNode) {
                    item.remove();
                }
            }, 300);
        }
    }
}

/**
 * Update the thought counter display
 */
function updateThoughtCounter() {
    const container = document.getElementById('thought-log-container');
    const thoughts = container.querySelectorAll('.thought-log-step:not(.text-center)');
    const countBadge = document.getElementById('thought-count');
    const counterText = document.getElementById('thought-counter-text');
    const { maxThoughts } = window.paperTradingDashboard.config;

    if (countBadge) {
        countBadge.textContent = thoughts.length;
    }

    if (counterText) {
        counterText.textContent = `Showing ${thoughts.length} latest thoughts (max ${maxThoughts})`;
    }
}

// ========================================
// Trading Data Management
// ========================================

/**
 * Update recent trades display
 * @param {boolean} isInitial - Whether this is the initial load
 */
function updateRecentTrades(isInitial = false) {
    const { lastTradeUpdate } = window.paperTradingDashboard.state;

    let url = '/paper-trading/api/trades/recent/?limit=10';
    if (lastTradeUpdate && !isInitial) {
        url += `&since=${lastTradeUpdate}`;
    }

    fetch(url)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                if (isInitial || !lastTradeUpdate) {
                    replaceAllTrades(data.trades);
                } else if (data.trades && data.trades.length > 0) {
                    updateTradesTable(data.trades);
                    flashUpdateIndicator('trades-update-indicator');
                }

                window.paperTradingDashboard.state.lastTradeUpdate = new Date().toISOString();
            }
        })
        .catch(error => {
            console.error('Error fetching recent trades:', error);
        });
}

/**
 * Replace all trades in the table
 * @param {Array} trades - Array of trade objects
 */
function replaceAllTrades(trades) {
    const tableBody = document.getElementById('recent-trades-tbody');
    if (!tableBody) return;

    tableBody.innerHTML = '';

    if (trades.length === 0) {
        tableBody.innerHTML = getNoTradesMessage();
        return;
    }

    trades.forEach(trade => {
        const row = createTradeRow(trade);
        tableBody.appendChild(row);
    });
}

/**
 * Get the no trades message HTML
 * @returns {string} HTML string for no trades message
 */
function getNoTradesMessage() {
    return `
        <tr class="no-trades-message">
            <td colspan="5" class="text-center text-muted py-4">
                <i class="bi bi-graph-up fs-3 mb-2 d-block"></i>
                <p class="mb-0">No trades yet. Start the bot to begin paper trading!</p>
            </td>
        </tr>
    `;
}

/**
 * Update trades table with new trades
 * @param {Array} newTrades - Array of new trade objects
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
        if (!document.querySelector(`[data-trade-id="${trade.trade_id}"]`)) {
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
 * @param {Object} trade - Trade data object
 * @returns {HTMLElement} Created table row element
 */
function createTradeRow(trade) {
    const tr = document.createElement('tr');
    tr.setAttribute('data-trade-id', trade.trade_id);
    tr.className = 'trade-row';

    const time = new Date(trade.created_at).toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit'
    });

    const typeClass = trade.trade_type === 'BUY' ? 'bg-success' : 'bg-danger';
    const statusClass = trade.status === 'COMPLETED' ? 'bg-success' :
        trade.status === 'FAILED' ? 'bg-danger' : 'bg-warning';

    tr.innerHTML = `
        <td><small>${time}</small></td>
        <td>
            <span class="badge ${typeClass}">
                ${trade.trade_type}
            </span>
        </td>
        <td><small>${trade.token_out_symbol || trade.token_symbol || 'N/A'}</small></td>
        <td><small>$${parseFloat(trade.amount_in_usd || 0).toFixed(2)}</small></td>
        <td>
            <span class="badge ${statusClass}">
                ${trade.status || 'PENDING'}
            </span>
        </td>
    `;

    return tr;
}

/**
 * Update open positions display
 */
function updateOpenPositions() {
    fetch('/paper-trading/api/positions/open/')
        .then(response => response.json())
        .then(data => {
            if (data.success && data.positions) {
                updatePositionsTable(data.positions);
                window.paperTradingDashboard.state.lastPositionUpdate = new Date().toISOString();
                flashUpdateIndicator('positions-update-indicator');
            }
        })
        .catch(error => {
            console.error('Error fetching open positions:', error);
        });
}

/**
 * Update positions table with new data
 * @param {Array} positions - Array of position objects
 */
function updatePositionsTable(positions) {
    const tableBody = document.getElementById('open-positions-tbody');
    if (!tableBody) return;

    tableBody.innerHTML = '';

    if (positions.length === 0) {
        tableBody.innerHTML = getNoPositionsMessage();
        return;
    }

    positions.forEach(position => {
        const tr = createPositionRow(position);
        tableBody.appendChild(tr);
    });
}

/**
 * Get the no positions message HTML
 * @returns {string} HTML string for no positions message
 */
function getNoPositionsMessage() {
    return `
        <tr>
            <td colspan="4" class="text-center text-muted py-4">
                <i class="bi bi-briefcase fs-3 mb-2 d-block"></i>
                <p class="mb-0">No open positions</p>
            </td>
        </tr>
    `;
}

/**
 * Create a position table row
 * @param {Object} position - Position data object
 * @returns {HTMLElement} Created table row element
 */
function createPositionRow(position) {
    const tr = document.createElement('tr');
    tr.setAttribute('data-position-id', position.position_id);

    const pnlClass = position.unrealized_pnl_usd >= 0 ? 'text-success' : 'text-danger';
    const pnlPrefix = position.unrealized_pnl_usd >= 0 ? '+' : '';

    tr.innerHTML = `
        <td><small>${position.token_symbol}</small></td>
        <td><small>${parseFloat(position.quantity).toFixed(6)}</small></td>
        <td><small>$${parseFloat(position.current_value_usd).toFixed(2)}</small></td>
        <td>
            <small class="${pnlClass}">
                ${pnlPrefix}$${parseFloat(position.unrealized_pnl_usd).toFixed(2)}
                <br>(${parseFloat(position.unrealized_pnl_percent).toFixed(1)}%)
            </small>
        </td>
    `;

    return tr;
}

// ========================================
// Dashboard Metrics
// ========================================

/**
 * Update dashboard metrics display
 */
function updateDashboardMetrics() {
    fetch('/paper-trading/api/metrics/')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                updateMetricElements(data);
            }
        })
        .catch(error => {
            console.error('Error fetching metrics:', error);
        });
}

/**
 * Update individual metric elements
 * @param {Object} data - Metrics data object
 */
function updateMetricElements(data) {
    // Portfolio value
    updateElementText('portfolio-value',
        data.current_balance ? `$${parseFloat(data.current_balance).toFixed(2)}` : null);

    // Total P&L
    if (data.total_pnl !== undefined) {
        const pnlElement = document.getElementById('total-pnl');
        if (pnlElement) {
            const pnlValue = parseFloat(data.total_pnl);
            const prefix = pnlValue >= 0 ? '+' : '';
            const colorClass = pnlValue >= 0 ? 'text-success' : 'text-danger';
            pnlElement.innerHTML = `<span class="${colorClass}">${prefix}$${pnlValue.toFixed(2)}</span>`;
        }
    }

    // Win rate
    updateElementText('win-rate',
        data.win_rate !== undefined ? `${parseFloat(data.win_rate).toFixed(1)}%` : null);

    // 24h trades
    updateElementText('trades-24h', data.trades_24h);

    // Total trades
    updateElementText('total-trades', data.total_trades);

    // 24h volume
    updateElementText('volume-24h',
        data.volume_24h ? `$${parseFloat(data.volume_24h).toFixed(2)}` : null);

    // Successful trades
    updateElementText('successful-trades', data.successful_trades);

    // Return percent
    if (data.return_percent !== undefined) {
        const returnElement = document.getElementById('return-percent');
        if (returnElement) {
            const returnValue = parseFloat(data.return_percent);
            const prefix = returnValue >= 0 ? '+' : '';
            const colorClass = returnValue >= 0 ? 'text-success' : 'text-danger';
            returnElement.className = colorClass;
            returnElement.textContent = `${prefix}${returnValue.toFixed(2)}%`;
        }
    }
}

// ========================================
// Bot Control Functions
// ========================================

/**
 * Start the trading bot
 */
function startBot() {
    fetch('/paper-trading/api/bot/start/', {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken'),
            'Content-Type': 'application/json'
        }
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showToast('Bot started successfully', 'success');
                setTimeout(() => location.reload(), 1000);
            } else {
                showToast('Failed to start bot: ' + (data.error || 'Unknown error'), 'danger');
            }
        })
        .catch(error => {
            console.error('Error starting bot:', error);
            showToast('Error starting bot', 'danger');
        });
}

/**
 * Stop the trading bot
 */
function stopBot() {
    fetch('/paper-trading/api/bot/stop/', {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken'),
            'Content-Type': 'application/json'
        }
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showToast('Bot stopped successfully', 'success');
                setTimeout(() => location.reload(), 1000);
            } else {
                showToast('Failed to stop bot: ' + (data.error || 'Unknown error'), 'danger');
            }
        })
        .catch(error => {
            console.error('Error stopping bot:', error);
            showToast('Error stopping bot', 'danger');
        });
}

// ========================================
// UI Helper Functions
// ========================================

/**
 * Scroll to the newest thoughts
 */
function scrollToNewest() {
    const container = document.getElementById('thought-log-container');
    if (container) {
        container.scrollTop = 0;
    }
}

/**
 * Toggle auto-scroll functionality
 */
function toggleAutoScroll() {
    const config = window.paperTradingDashboard.config;
    config.autoScroll = !config.autoScroll;

    const icon = document.getElementById('auto-scroll-icon');
    if (icon) {
        if (config.autoScroll) {
            icon.classList.add('text-success');
            showToast('Auto-scroll enabled', 'info');
        } else {
            icon.classList.remove('text-success');
            showToast('Auto-scroll disabled', 'info');
        }
    }
}

/**
 * Clear all thoughts from display
 */
function clearThoughts() {
    if (!confirm('Clear all AI thoughts from display?')) return;

    const container = document.getElementById('thought-log-container');
    if (!container) return;

    const thoughts = container.querySelectorAll('.thought-log-step:not(.text-center)');
    thoughts.forEach((thought, index) => {
        setTimeout(() => {
            thought.classList.add('fade-out');
            setTimeout(() => thought.remove(), 300);
        }, index * 50);
    });

    setTimeout(() => {
        window.paperTradingDashboard.state.thoughtCount = 0;
        updateThoughtCounter();
    }, thoughts.length * 50 + 300);
}

/**
 * Flash an update indicator
 * @param {string} indicatorId - ID of the indicator element
 */
function flashUpdateIndicator(indicatorId) {
    const indicator = document.getElementById(indicatorId);
    if (indicator) {
        indicator.classList.add('flash-update');
        setTimeout(() => {
            indicator.classList.remove('flash-update');
        }, 1000);
    }
}

/**
 * Limit table rows to a maximum number
 * @param {HTMLElement} tableBody - Table body element
 * @param {number} maxRows - Maximum number of rows
 */
function limitTableRows(tableBody, maxRows) {
    const allRows = tableBody.querySelectorAll('tr:not(.no-trades-message)');
    if (allRows.length > maxRows) {
        for (let i = maxRows; i < allRows.length; i++) {
            allRows[i].remove();
        }
    }
}

/**
 * Update element text content
 * @param {string} elementId - Element ID
 * @param {*} value - Value to set (or null to skip)
 */
function updateElementText(elementId, value) {
    if (value !== null && value !== undefined) {
        const element = document.getElementById(elementId);
        if (element) {
            element.textContent = value;
        }
    }
}

// ========================================
// Utility Functions
// ========================================

/**
 * Show a toast notification
 * @param {string} message - Toast message
 * @param {string} type - Toast type (success, danger, warning, info)
 */
function showToast(message, type) {
    let toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'toast-container';
        document.body.appendChild(toastContainer);
    }

    const toast = document.createElement('div');
    toast.className = `alert alert-${type} alert-dismissible fade show`;
    toast.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;

    toastContainer.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 5000);
}

/**
 * Get CSRF token from cookies
 * @param {string} name - Cookie name
 * @returns {string|null} Cookie value or null
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

// ========================================
// Initialization
// ========================================

/**
 * Initialize the dashboard
 */
function initializeDashboard() {
    const { config, state } = window.paperTradingDashboard;

    // Initialize thought counter
    updateThoughtCounter();

    // Set up periodic updates for AI thoughts
    const thoughtInterval = setInterval(updateAIThoughts, config.updateInterval);
    state.updateIntervals.push(thoughtInterval);

    // Set up periodic updates for trades & positions
    const tradesInterval = setInterval(() => {
        updateRecentTrades(false);
        updateOpenPositions();
    }, config.tradesUpdateInterval);
    state.updateIntervals.push(tradesInterval);

    // Set up periodic updates for metrics
    const metricsInterval = setInterval(updateDashboardMetrics, config.metricsUpdateInterval);
    state.updateIntervals.push(metricsInterval);

    // Initial data loads with slight delay
    setTimeout(() => {
        updateAIThoughts();
        updateRecentTrades(true);
        updateOpenPositions();
        updateDashboardMetrics();
    }, 1000);
}

/**
 * Clean up intervals on page unload
 */
function cleanupDashboard() {
    const { state } = window.paperTradingDashboard;
    state.updateIntervals.forEach(interval => clearInterval(interval));
    state.updateIntervals = [];
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', initializeDashboard);

// Cleanup on page unload
window.addEventListener('beforeunload', cleanupDashboard);

// Export functions to global scope for HTML onclick handlers
window.startBot = startBot;
window.stopBot = stopBot;
window.scrollToNewest = scrollToNewest;
window.toggleAutoScroll = toggleAutoScroll;
window.clearThoughts = clearThoughts;