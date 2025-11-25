/**
 * Paper Trading Trade History Page JavaScript
 * 
 * Handles filtering, exporting, displaying trade history, and real-time WebSocket updates.
 * Provides CSV export functionality and print formatting.
 * 
 * Dependencies:
 * - common-utils.js (must be loaded before this file)
 *   - Uses: showToast()
 * 
 * File: dexproject/static/js/paper_trading_trade_history.js
 */

'use strict';

// ============================================================================
// CONSTANTS
// ============================================================================

const TRADE_HISTORY_CONFIG = {
    BASE_URL: '/paper-trading/trades/',
    CSV_FILENAME_PREFIX: 'paper_trades_',
    CSV_HEADERS: [
        'Date',
        'Time',
        'Type',
        'Token In',
        'Token Out',
        'Amount In',
        'Amount In USD',
        'Amount Out',
        'Gas Cost USD',
        'Slippage %',
        'Status',
        'Execution Time (ms)'
    ],
    SELECTORS: {
        TRADE_ROW: '.trade-row',
        TRADE_TABLE_BODY: '#trade-table-body',
        FILTER_FORM: 'filter-form',
        NO_TRADES_MESSAGE: '.empty-state',
        TABLE_CONTAINER: '.table-responsive',
        TOTAL_TRADES: '#total-trades-count',
        WS_STATUS: '#ws-status'
    },
    // WebSocket configuration
    WS: {
        RECONNECT_DELAY: 1000,
        MAX_RECONNECT_DELAY: 30000,
        MAX_RECONNECT_ATTEMPTS: 10
    }
};

// ============================================================================
// GLOBAL STATE
// ============================================================================

window.tradeHistoryState = {
    websocket: null,
    wsConnected: false,
    reconnectAttempts: 0,
    reconnectDelay: TRADE_HISTORY_CONFIG.WS.RECONNECT_DELAY
};

// ============================================================================
// WEBSOCKET MANAGEMENT
// ============================================================================

/**
 * Initialize WebSocket connection for real-time trade updates
 * Connects to the same endpoint as the dashboard
 * 
 * @returns {void}
 */
function initializeWebSocket() {
    const state = window.tradeHistoryState;

    // Determine WebSocket URL based on current protocol
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/paper-trading/`;

    console.log('[TradeHistory] Connecting to WebSocket:', wsUrl);

    try {
        state.websocket = new WebSocket(wsUrl);

        state.websocket.onopen = handleWebSocketOpen;
        state.websocket.onmessage = handleWebSocketMessage;
        state.websocket.onclose = handleWebSocketClose;
        state.websocket.onerror = handleWebSocketError;

    } catch (error) {
        console.error('[TradeHistory] Failed to create WebSocket connection:', error);
    }
}

/**
 * Handle WebSocket connection open event
 * 
 * @param {Event} event - WebSocket open event
 * @returns {void}
 */
function handleWebSocketOpen(event) {
    const state = window.tradeHistoryState;

    console.log('[TradeHistory] WebSocket connected successfully');
    state.wsConnected = true;
    state.reconnectAttempts = 0;
    state.reconnectDelay = TRADE_HISTORY_CONFIG.WS.RECONNECT_DELAY;

    // Update status indicator if exists
    updateWsStatusIndicator('Connected', 'success');

    // Show toast notification
    if (typeof showToast === 'function') {
        showToast('Real-time updates connected', 'success');
    }
}

/**
 * Handle incoming WebSocket messages
 * Routes messages to appropriate handlers
 * 
 * @param {MessageEvent} event - WebSocket message event
 * @returns {void}
 */
function handleWebSocketMessage(event) {
    try {
        const message = JSON.parse(event.data);
        console.log('[TradeHistory] WebSocket message received:', message.type, message);

        switch (message.type) {
            // Connection messages
            case 'connection_confirmed':
                console.log('[TradeHistory] Connection confirmed by server');
                break;

            // Trade messages - these are the ones we care about
            case 'trade_executed':
            case 'trade.executed':
                console.log('[TradeHistory] New trade executed:', message.data);
                handleNewTrade(message.data);
                break;

            // Ping/Pong for keepalive
            case 'ping':
                sendPong();
                break;

            case 'pong':
                // Heartbeat acknowledged
                break;

            default:
                // Ignore other message types on this page
                console.log('[TradeHistory] Ignoring message type:', message.type);
        }

    } catch (error) {
        console.error('[TradeHistory] Error parsing WebSocket message:', error);
    }
}

/**
 * Handle WebSocket connection close event
 * Implements exponential backoff reconnection
 * 
 * @param {CloseEvent} event - WebSocket close event
 * @returns {void}
 */
function handleWebSocketClose(event) {
    const state = window.tradeHistoryState;

    console.log('[TradeHistory] WebSocket disconnected:', event.code, event.reason);
    state.wsConnected = false;
    state.websocket = null;

    updateWsStatusIndicator('Reconnecting...', 'warning');

    // Attempt to reconnect with exponential backoff
    if (state.reconnectAttempts < TRADE_HISTORY_CONFIG.WS.MAX_RECONNECT_ATTEMPTS) {
        state.reconnectAttempts++;

        console.log(`[TradeHistory] Reconnecting (${state.reconnectAttempts}/${TRADE_HISTORY_CONFIG.WS.MAX_RECONNECT_ATTEMPTS})...`);

        setTimeout(() => {
            initializeWebSocket();
        }, state.reconnectDelay);

        // Exponential backoff
        state.reconnectDelay = Math.min(
            state.reconnectDelay * 2,
            TRADE_HISTORY_CONFIG.WS.MAX_RECONNECT_DELAY
        );
    } else {
        console.error('[TradeHistory] Max reconnection attempts reached');
        updateWsStatusIndicator('Disconnected', 'danger');

        if (typeof showToast === 'function') {
            showToast('Real-time updates disconnected. Refresh page to reconnect.', 'warning');
        }
    }
}

/**
 * Handle WebSocket errors
 * 
 * @param {Event} error - WebSocket error event
 * @returns {void}
 */
function handleWebSocketError(error) {
    console.error('[TradeHistory] WebSocket error:', error);
    updateWsStatusIndicator('Error', 'danger');
}

/**
 * Send pong response to server ping
 * 
 * @returns {void}
 */
function sendPong() {
    const state = window.tradeHistoryState;

    if (state.websocket && state.websocket.readyState === WebSocket.OPEN) {
        state.websocket.send(JSON.stringify({ type: 'pong' }));
    }
}

/**
 * Update WebSocket status indicator in the UI
 * 
 * @param {string} status - Status text to display
 * @param {string} type - Bootstrap color class (success, warning, danger)
 * @returns {void}
 */
function updateWsStatusIndicator(status, type) {
    const indicator = document.getElementById('ws-status');
    if (indicator) {
        indicator.textContent = status;
        indicator.className = `badge bg-${type}`;
    }
}

// ============================================================================
// TRADE UPDATE HANDLERS
// ============================================================================

/**
 * Handle new trade from WebSocket
 * Adds the trade to the table or refreshes the page
 * 
 * @param {Object} tradeData - Trade data from WebSocket message
 * @returns {void}
 */
function handleNewTrade(tradeData) {
    if (!tradeData) return;

    console.log('[TradeHistory] Processing new trade:', tradeData);

    // Check if we have a table body to add to
    const tableBody = document.getElementById('trade-table-body');

    if (tableBody) {
        // Add new trade row to the top of the table
        addTradeToTable(tradeData, tableBody);

        // Update total count if element exists
        updateTradeCount(1);

        // Show notification
        const side = tradeData.trade_type || tradeData.side || 'TRADE';
        const symbol = tradeData.token_out_symbol || tradeData.symbol || 'Token';
        const amount = tradeData.amount_in_usd || tradeData.amount || 0;

        if (typeof showToast === 'function') {
            showToast(`New trade: ${side} ${symbol} - $${parseFloat(amount).toFixed(2)}`, 'info');
        }
    } else {
        // No table body found - might be showing "no trades" message
        // Refresh the page to show the new trade
        console.log('[TradeHistory] No table body found, refreshing page...');
        window.location.reload();
    }
}

/**
 * Add a trade row to the trade table
 * 
 * @param {Object} trade - Trade data object
 * @param {HTMLElement} tableBody - Table body element to add row to
 * @returns {void}
 */
function addTradeToTable(trade, tableBody) {
    // Hide empty state if showing
    const emptyState = document.querySelector(TRADE_HISTORY_CONFIG.SELECTORS.NO_TRADES_MESSAGE);
    if (emptyState) {
        emptyState.style.display = 'none';
    }

    // Show table container if hidden
    const tableContainer = document.querySelector(TRADE_HISTORY_CONFIG.SELECTORS.TABLE_CONTAINER);
    if (tableContainer) {
        tableContainer.style.display = 'block';
    }

    // Format timestamp
    const timestamp = new Date(trade.created_at || trade.timestamp || new Date());
    const dateStr = timestamp.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric'
    });
    const timeStr = timestamp.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });

    // Determine trade type styling
    const tradeType = (trade.trade_type || trade.side || 'SWAP').toUpperCase();
    let tradeTypeClass = 'trade-type-swap';
    if (tradeType === 'BUY') {
        tradeTypeClass = 'trade-type-buy';
    } else if (tradeType === 'SELL') {
        tradeTypeClass = 'trade-type-sell';
    }

    // Determine status styling
    const status = (trade.status || 'COMPLETED').toUpperCase();
    let statusBadge = '<span class="badge bg-success"><i class="bi bi-check-circle me-1"></i>Completed</span>';
    if (status === 'PENDING') {
        statusBadge = '<span class="badge bg-warning"><i class="bi bi-clock me-1"></i>Pending</span>';
    } else if (status === 'FAILED') {
        statusBadge = '<span class="badge bg-danger"><i class="bi bi-x-circle me-1"></i>Failed</span>';
    }

    // Create table row
    const row = document.createElement('tr');
    row.className = 'trade-row new-trade-highlight';
    row.innerHTML = `
        <td>
            <div>${dateStr}</div>
            <small class="text-muted">${timeStr}</small>
        </td>
        <td>
            <span class="${tradeTypeClass}">${tradeType}</span>
        </td>
        <td>
            <div class="token-pair">
                <span>${trade.token_in_symbol || 'ETH'}</span>
                <span class="token-arrow">&#8594;</span>
                <span>${trade.token_out_symbol || 'TOKEN'}</span>
            </div>
        </td>
        <td>
            <div>${parseFloat(trade.amount_in || 0).toFixed(4)} ${trade.token_in_symbol || 'ETH'}</div>
            <div class="text-muted" style="font-size: 0.85rem;">
                $${parseFloat(trade.amount_in_usd || 0).toFixed(2)}
            </div>
        </td>
        <td>
            ${trade.amount_out ?
            `<div>${parseFloat(trade.amount_out).toFixed(4)} ${trade.token_out_symbol || 'TOKEN'}</div>` :
            '<span class="text-muted">-</span>'}
        </td>
        <td>
            <div class="gas-cost">
                <i class="bi bi-fuel-pump"></i>
                $${parseFloat(trade.gas_cost_usd || 0).toFixed(2)}
            </div>
        </td>
        <td>
            ${trade.slippage_percent ?
            `<span class="${parseFloat(trade.slippage_percent) > 1 ? 'text-warning' : ''}">${parseFloat(trade.slippage_percent).toFixed(2)}%</span>` :
            '<span class="text-muted">-</span>'}
        </td>
        <td>${statusBadge}</td>
        <td>
            ${trade.execution_time_ms ?
            `<div class="execution-time"><i class="bi bi-stopwatch"></i>${trade.execution_time_ms}ms</div>` :
            '<span class="text-muted">-</span>'}
        </td>
    `;

    // Insert at the top of the table
    tableBody.insertBefore(row, tableBody.firstChild);

    // Remove highlight after animation
    setTimeout(() => {
        row.classList.remove('new-trade-highlight');
    }, 3000);

    console.log('[TradeHistory] Added new trade row to table');
}

/**
 * Update the trade count display
 * 
 * @param {number} increment - Number to add to current count
 * @returns {void}
 */
function updateTradeCount(increment) {
    const countElement = document.getElementById('total-trades-count');
    if (countElement) {
        const currentCount = parseInt(countElement.textContent, 10) || 0;
        countElement.textContent = currentCount + increment;
    }
}

// ============================================================================
// FILTER MANAGEMENT
// ============================================================================

/**
 * Clear all filters and reload page
 * Removes all query parameters and returns to unfiltered view
 * 
 * @returns {void}
 */
function clearFilters() {
    console.log('[TradeHistory] Clearing all filters...');
    window.location.href = TRADE_HISTORY_CONFIG.BASE_URL;
}

// ============================================================================
// CSV EXPORT
// ============================================================================

/**
 * Export trades to CSV file
 * Extracts data from visible trade rows and creates downloadable CSV
 * 
 * @returns {void}
 */
function exportToCSV() {
    console.log('[TradeHistory] Starting CSV export...');

    try {
        const rows = [];

        // Add headers
        rows.push(TRADE_HISTORY_CONFIG.CSV_HEADERS);

        // Extract data from table rows
        const tradeRows = document.querySelectorAll(TRADE_HISTORY_CONFIG.SELECTORS.TRADE_ROW);

        if (tradeRows.length === 0) {
            console.warn('[TradeHistory] No trade rows found to export');
            if (typeof showToast === 'function') {
                showToast('No trades to export', 'warning');
            }
            return;
        }

        console.log(`[TradeHistory] Exporting ${tradeRows.length} trade rows...`);

        // Process each trade row
        tradeRows.forEach((row, rowIndex) => {
            const cells = row.querySelectorAll('td');
            const rowData = [];

            // Extract text from each cell, cleaning up the data
            cells.forEach((cell, cellIndex) => {
                let text = cell.textContent.trim().replace(/\s+/g, ' ');

                // Special handling for certain columns
                if (cellIndex === 0) {
                    // Date/Time column - normalize whitespace
                    text = text.replace(/\s+/g, ' ');
                } else if (cellIndex === 2) {
                    // Token pair column - replace arrow character
                    text = text.replace(/\u2192/g, ' -> ');
                    text = text.replace(/&#8594;/g, ' -> ');
                }

                rowData.push(text);
            });

            if (rowData.length > 0) {
                rows.push(rowData);
            }
        });

        console.log(`[TradeHistory] Processed ${rows.length - 1} data rows (excluding header)`);

        // Create CSV content with proper escaping
        const csvContent = rows.map(row =>
            row.map(field => escapeCsvField(field)).join(',')
        ).join('\n');

        // Generate filename with current date
        const filename = `${TRADE_HISTORY_CONFIG.CSV_FILENAME_PREFIX}${getCurrentDateString()}.csv`;

        // Trigger download
        downloadCsvFile(csvContent, filename);

        console.log(`[TradeHistory] CSV export completed: ${filename}`);

        if (typeof showToast === 'function') {
            showToast('Trade history exported to CSV', 'success');
        }

    } catch (error) {
        console.error('[TradeHistory] Error exporting CSV:', error);
        if (typeof showToast === 'function') {
            showToast('Failed to export CSV', 'danger');
        }
    }
}

/**
 * Escape CSV field to handle commas and quotes
 * 
 * @param {string|number} field - Field value to escape
 * @returns {string} Escaped field value
 */
function escapeCsvField(field) {
    // Convert to string
    const fieldStr = String(field);

    // If field contains comma, quote, or newline, wrap in quotes and escape internal quotes
    if (fieldStr.includes(',') || fieldStr.includes('"') || fieldStr.includes('\n')) {
        return `"${fieldStr.replace(/"/g, '""')}"`;
    }

    return fieldStr;
}

/**
 * Get current date as string (YYYY-MM-DD format)
 * 
 * @returns {string} Current date string
 */
function getCurrentDateString() {
    const date = new Date();
    return date.toISOString().split('T')[0];
}

/**
 * Download CSV file to user's computer
 * 
 * @param {string} content - CSV content
 * @param {string} filename - Desired filename
 * @returns {void}
 */
function downloadCsvFile(content, filename) {
    // Create blob with UTF-8 encoding
    const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' });
    const url = window.URL.createObjectURL(blob);

    // Create temporary download link
    const downloadLink = document.createElement('a');
    downloadLink.href = url;
    downloadLink.download = filename;
    downloadLink.style.display = 'none';

    // Trigger download
    document.body.appendChild(downloadLink);
    downloadLink.click();

    // Cleanup
    document.body.removeChild(downloadLink);
    window.URL.revokeObjectURL(url);
}

// ============================================================================
// PRINT FUNCTIONALITY
// ============================================================================

/**
 * Print trade report
 * Opens browser print dialog with current page
 * 
 * @returns {void}
 */
function printReport() {
    console.log('[TradeHistory] Opening print dialog...');
    window.print();
}

// ============================================================================
// FILTER AUTO-SUBMIT (Optional Feature)
// ============================================================================

/**
 * Enable auto-submit on filter changes
 * Uncomment the function call in initialization to activate
 * 
 * @returns {void}
 */
function enableFilterAutoSubmit() {
    const filterForm = document.getElementById(TRADE_HISTORY_CONFIG.SELECTORS.FILTER_FORM);

    if (!filterForm) {
        console.warn('[TradeHistory] Filter form not found');
        return;
    }

    console.log('[TradeHistory] Enabling auto-submit for filter form');

    const filterSelects = filterForm.querySelectorAll('select');
    const filterInputs = filterForm.querySelectorAll('input[type="date"]');

    // Auto-submit when select changes
    filterSelects.forEach(select => {
        select.addEventListener('change', () => {
            console.log('[TradeHistory] Filter changed, submitting form...');
            filterForm.submit();
        });
    });

    // Auto-submit when date changes
    filterInputs.forEach(input => {
        input.addEventListener('change', () => {
            console.log('[TradeHistory] Date filter changed, submitting form...');
            filterForm.submit();
        });
    });
}

// ============================================================================
// INITIALIZATION
// ============================================================================

/**
 * Initialize trade history page
 * Sets up WebSocket connection and event listeners
 * 
 * @returns {void}
 */
function initializeTradeHistory() {
    console.log('[TradeHistory] Initializing trade history page...');

    // Check if we have any trades displayed
    const tradeRows = document.querySelectorAll(TRADE_HISTORY_CONFIG.SELECTORS.TRADE_ROW);
    console.log(`[TradeHistory] Found ${tradeRows.length} trade rows`);

    // Initialize WebSocket for real-time updates
    initializeWebSocket();

    // Optional: Enable auto-submit on filter changes
    // Uncomment the line below if you want instant filtering
    // enableFilterAutoSubmit();

    // Add CSS for new trade highlight animation
    addHighlightStyles();

    console.log('[TradeHistory] Trade history page initialized successfully');
}

/**
 * Add CSS styles for new trade highlight animation
 * 
 * @returns {void}
 */
function addHighlightStyles() {
    const style = document.createElement('style');
    style.textContent = `
        .new-trade-highlight {
            animation: highlightFade 3s ease-out;
        }
        
        @keyframes highlightFade {
            0% {
                background-color: rgba(0, 123, 255, 0.3);
            }
            100% {
                background-color: transparent;
            }
        }
    `;
    document.head.appendChild(style);
}

/**
 * Cleanup WebSocket on page unload
 * 
 * @returns {void}
 */
function cleanup() {
    const state = window.tradeHistoryState;

    if (state.websocket) {
        console.log('[TradeHistory] Closing WebSocket connection...');
        state.websocket.close();
        state.websocket = null;
    }
}

// Auto-initialize when DOM is ready
document.addEventListener('DOMContentLoaded', initializeTradeHistory);

// Cleanup on page unload
window.addEventListener('beforeunload', cleanup);

// ============================================================================
// GLOBAL EXPORTS
// ============================================================================

// Export functions for template usage
window.clearFilters = clearFilters;
window.exportToCSV = exportToCSV;
window.printReport = printReport;

// Export configuration for testing/debugging
window.TRADE_HISTORY_CONFIG = TRADE_HISTORY_CONFIG;