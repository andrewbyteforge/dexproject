/**
 * Paper Trading Orders - Client-Side JavaScript
 * 
 * Handles:
 * - Order form interactions and validation
 * - Real-time price updates
 * - WebSocket order status updates
 * - Order cancellation
 * - Dynamic field display based on order type
 * - Order details modal
 * - CSV export functionality
 * 
 * File: static/js/orders.js
 */

// =============================================================================
// GLOBAL VARIABLES
// =============================================================================

let orderWebSocket = null;
let orderFormState = {
    orderType: 'LIMIT_BUY',
    tokenAddress: '',
    currentPrice: null,
};

// =============================================================================
// ORDER FORM INITIALIZATION
// =============================================================================

/**
 * Initialize the order placement form
 */
function initializeOrderForm() {
    console.log('Initializing order form...');

    // Order type radio buttons
    const orderTypeRadios = document.querySelectorAll('input[name="order_type"]');
    orderTypeRadios.forEach(radio => {
        radio.addEventListener('change', handleOrderTypeChange);
    });

    // Token address input
    const tokenAddressInput = document.getElementById('token_address');
    if (tokenAddressInput) {
        tokenAddressInput.addEventListener('blur', validateTokenAddress);
    }

    // Amount USD input
    const amountInput = document.getElementById('amount_usd');
    if (amountInput) {
        amountInput.addEventListener('input', updateOrderSummary);
    }

    // Price inputs
    const limitPriceInput = document.getElementById('limit_price');
    if (limitPriceInput) {
        limitPriceInput.addEventListener('input', updateOrderSummary);
    }

    // Refresh price button
    const refreshPriceBtn = document.getElementById('refresh_price');
    if (refreshPriceBtn) {
        refreshPriceBtn.addEventListener('click', refreshCurrentPrice);
    }

    // Form submission
    const orderForm = document.getElementById('orderForm');
    if (orderForm) {
        orderForm.addEventListener('submit', handleOrderFormSubmit);
    }

    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Set initial order type
    handleOrderTypeChange();

    console.log('Order form initialized');
}

/**
 * Handle order type selection change
 */
function handleOrderTypeChange() {
    const selectedType = document.querySelector('input[name="order_type"]:checked');
    if (!selectedType) return;

    const orderType = selectedType.value;
    orderFormState.orderType = orderType;

    console.log('Order type changed to:', orderType);

    // Update visual selection
    document.querySelectorAll('.order-type-card').forEach(card => {
        card.classList.remove('selected');
    });
    selectedType.closest('.order-type-card').classList.add('selected');

    // Show/hide price fields based on order type
    const triggerPriceField = document.getElementById('field_trigger_price');
    const limitPriceField = document.getElementById('field_limit_price');
    const trailingStopFields = document.getElementById('trailing_stop_fields');

    // Reset visibility
    if (triggerPriceField) triggerPriceField.style.display = 'none';
    if (limitPriceField) limitPriceField.style.display = 'none';
    if (trailingStopFields) trailingStopFields.style.display = 'none';

    // Show relevant fields
    if (orderType === 'STOP_LIMIT_BUY' || orderType === 'STOP_LIMIT_SELL') {
        if (triggerPriceField) triggerPriceField.style.display = 'block';
        if (limitPriceField) limitPriceField.style.display = 'block';
    } else if (orderType === 'TRAILING_STOP') {
        if (trailingStopFields) trailingStopFields.style.display = 'block';
    } else {
        // LIMIT_BUY or LIMIT_SELL
        if (limitPriceField) limitPriceField.style.display = 'block';
    }

    // Update summary
    updateOrderSummary();
}

/**
 * Validate token address format
 */
function validateTokenAddress() {
    const tokenAddressInput = document.getElementById('token_address');
    if (!tokenAddressInput) return;

    const address = tokenAddressInput.value.trim();

    if (address && (!address.startsWith('0x') || address.length !== 42)) {
        tokenAddressInput.classList.add('is-invalid');
        showToast('Invalid token address format', 'error');
        return false;
    } else {
        tokenAddressInput.classList.remove('is-invalid');
        tokenAddressInput.classList.add('is-valid');
        orderFormState.tokenAddress = address;
        return true;
    }
}

/**
 * Update order summary display
 */
function updateOrderSummary() {
    const amountUSD = document.getElementById('amount_usd')?.value || 0;
    const limitPrice = document.getElementById('limit_price')?.value || 0;

    // Update summary type
    const summaryType = document.getElementById('summary_type');
    if (summaryType) {
        const orderTypeLabels = {
            'LIMIT_BUY': 'Limit Buy',
            'LIMIT_SELL': 'Limit Sell',
            'STOP_LIMIT_BUY': 'Stop Limit Buy',
            'STOP_LIMIT_SELL': 'Stop Limit Sell',
            'TRAILING_STOP': 'Trailing Stop'
        };
        summaryType.textContent = orderTypeLabels[orderFormState.orderType] || 'Unknown';
    }

    // Update summary amount
    const summaryAmount = document.getElementById('summary_amount');
    if (summaryAmount) {
        summaryAmount.textContent = formatCurrency(parseFloat(amountUSD));
    }

    // Calculate estimated tokens
    const summaryTokens = document.getElementById('summary_tokens');
    if (summaryTokens && limitPrice && parseFloat(limitPrice) > 0) {
        const estimatedTokens = parseFloat(amountUSD) / parseFloat(limitPrice);
        summaryTokens.textContent = estimatedTokens.toFixed(4);
    } else if (summaryTokens) {
        summaryTokens.textContent = '--';
    }
}

/**
 * Refresh current token price
 */
async function refreshCurrentPrice() {
    const tokenAddress = document.getElementById('token_address')?.value;
    const tokenSymbol = document.getElementById('token_symbol')?.value;

    if (!tokenAddress && !tokenSymbol) {
        showToast('Enter token address or symbol first', 'warning');
        return;
    }

    const refreshBtn = document.getElementById('refresh_price');
    if (refreshBtn) {
        refreshBtn.disabled = true;
        refreshBtn.innerHTML = '<i class="bi bi-arrow-clockwise spinner-border spinner-border-sm"></i>';
    }

    try {
        // Call price API (implementation depends on your API structure)
        const symbol = tokenSymbol || 'UNKNOWN';
        const response = await fetch(`/paper-trading/api/prices/${symbol}/`);
        const data = await response.json();

        if (data.success && data.price) {
            orderFormState.currentPrice = data.price;
            const priceDisplay = document.getElementById('current_price');
            if (priceDisplay) {
                priceDisplay.textContent = formatCurrency(data.price);
            }
            showToast('Price updated successfully', 'success');
        } else {
            showToast('Could not fetch price', 'error');
        }
    } catch (error) {
        console.error('Error fetching price:', error);
        showToast('Failed to fetch price', 'error');
    } finally {
        if (refreshBtn) {
            refreshBtn.disabled = false;
            refreshBtn.innerHTML = '<i class="bi bi-arrow-clockwise"></i>';
        }
    }
}

/**
 * Handle order form submission
 */
async function handleOrderFormSubmit(event) {
    event.preventDefault();

    console.log('Submitting order form...');

    const submitBtn = document.getElementById('submit_order');
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Placing Order...';
    }

    // Validate form
    if (!validateTokenAddress()) {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<i class="bi bi-check-circle me-2"></i>Place Order';
        }
        return;
    }

    // Submit form (let Django handle it)
    event.target.submit();
}

// =============================================================================
// ACTIVE ORDERS PAGE
// =============================================================================

/**
 * Initialize active orders page
 */
function initializeActiveOrdersPage() {
    console.log('Initializing active orders page...');

    // Cancel order buttons
    const cancelButtons = document.querySelectorAll('.cancel-order-btn');
    cancelButtons.forEach(btn => {
        btn.addEventListener('click', handleCancelOrderClick);
    });

    // View order buttons
    const viewButtons = document.querySelectorAll('.view-order-btn');
    viewButtons.forEach(btn => {
        btn.addEventListener('click', handleViewOrderClick);
    });

    // Cancel all button
    const cancelAllBtn = document.getElementById('cancel_all_btn');
    if (cancelAllBtn) {
        cancelAllBtn.addEventListener('click', handleCancelAllOrders);
    }

    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    console.log('Active orders page initialized');
}

/**
 * Handle cancel order button click
 */
function handleCancelOrderClick(event) {
    const orderId = event.currentTarget.dataset.orderId;
    console.log('Cancel order clicked:', orderId);

    // Show confirmation modal
    const confirmModal = new bootstrap.Modal(document.getElementById('cancelConfirmModal'));
    confirmModal.show();

    // Set up confirmation button
    const confirmBtn = document.getElementById('confirm_cancel_btn');
    confirmBtn.onclick = () => cancelOrder(orderId, confirmModal);
}

/**
 * Cancel an order
 */
async function cancelOrder(orderId, modal) {
    console.log('Cancelling order:', orderId);

    try {
        const response = await fetch('/paper-trading/api/orders/cancel/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({
                order_id: orderId,
                reason: 'User requested cancellation'
            })
        });

        const data = await response.json();

        if (data.success) {
            showToast('Order cancelled successfully', 'success');
            modal.hide();

            // Remove order row from table
            const orderRow = document.querySelector(`tr[data-order-id="${orderId}"]`);
            if (orderRow) {
                orderRow.remove();
            }

            // Update counts
            updateOrderCounts();
        } else {
            showToast(data.error || 'Failed to cancel order', 'error');
        }
    } catch (error) {
        console.error('Error cancelling order:', error);
        showToast('Failed to cancel order', 'error');
    }
}

/**
 * Handle view order button click
 */
async function handleViewOrderClick(event) {
    const orderId = event.currentTarget.dataset.orderId;
    console.log('View order clicked:', orderId);

    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('orderDetailsModal'));
    modal.show();

    // Fetch order details
    try {
        const response = await fetch(`/paper-trading/api/orders/${orderId}/`);
        const data = await response.json();

        if (data.success) {
            displayOrderDetails(data.order);
        } else {
            document.getElementById('order_details_body').innerHTML =
                '<div class="alert alert-danger">Failed to load order details</div>';
        }
    } catch (error) {
        console.error('Error fetching order details:', error);
        document.getElementById('order_details_body').innerHTML =
            '<div class="alert alert-danger">Error loading order details</div>';
    }
}

/**
 * Display order details in modal
 */
function displayOrderDetails(order) {
    const detailsBody = document.getElementById('order_details_body');
    if (!detailsBody) return;

    const html = `
        <div class="row g-3">
            <div class="col-md-6">
                <strong>Order ID:</strong><br>
                <span class="font-monospace small">${order.order_id}</span>
            </div>
            <div class="col-md-6">
                <strong>Status:</strong><br>
                <span class="badge bg-${getStatusColor(order.status)}">${order.status}</span>
            </div>
            <div class="col-md-6">
                <strong>Order Type:</strong><br>
                ${order.order_type}
            </div>
            <div class="col-md-6">
                <strong>Token:</strong><br>
                ${order.token_symbol} (${order.token_address.slice(0, 10)}...)
            </div>
            <div class="col-md-6">
                <strong>Amount (USD):</strong><br>
                ${formatCurrency(order.amount_usd)}
            </div>
            ${order.limit_price ? `<div class="col-md-6">
                <strong>Limit Price:</strong><br>
                ${formatCurrency(order.limit_price)}
            </div>` : ''}
            ${order.trigger_price ? `<div class="col-md-6">
                <strong>Trigger Price:</strong><br>
                ${formatCurrency(order.trigger_price)}
            </div>` : ''}
            ${order.trail_percent ? `<div class="col-md-6">
                <strong>Trail Percent:</strong><br>
                ${order.trail_percent}%
            </div>` : ''}
            <div class="col-md-6">
                <strong>Created:</strong><br>
                ${new Date(order.created_at).toLocaleString()}
            </div>
            ${order.expires_at ? `<div class="col-md-6">
                <strong>Expires:</strong><br>
                ${new Date(order.expires_at).toLocaleString()}
            </div>` : ''}
            ${order.notes ? `<div class="col-12">
                <strong>Notes:</strong><br>
                ${order.notes}
            </div>` : ''}
        </div>
    `;

    detailsBody.innerHTML = html;
}

/**
 * Get status badge color
 */
function getStatusColor(status) {
    const colors = {
        'PENDING': 'warning',
        'TRIGGERED': 'info',
        'PARTIALLY_FILLED': 'primary',
        'FILLED': 'success',
        'CANCELLED': 'warning',
        'EXPIRED': 'secondary',
        'FAILED': 'danger'
    };
    return colors[status] || 'secondary';
}

/**
 * Handle cancel all orders
 */
function handleCancelAllOrders() {
    if (!confirm('Are you sure you want to cancel ALL active orders? This action cannot be undone.')) {
        return;
    }

    // Get all order IDs
    const orderRows = document.querySelectorAll('.order-row');
    const orderIds = Array.from(orderRows).map(row => row.dataset.orderId);

    // Cancel each order
    orderIds.forEach(orderId => {
        cancelOrder(orderId, null);
    });
}

/**
 * Update order counts in summary cards
 */
function updateOrderCounts() {
    const activeCount = document.querySelectorAll('.order-row').length;
    const totalActiveEl = document.getElementById('total_active');
    if (totalActiveEl) {
        totalActiveEl.textContent = activeCount;
    }
}

// =============================================================================
// ORDER HISTORY PAGE
// =============================================================================

/**
 * Initialize order history page
 */
function initializeOrderHistoryPage() {
    console.log('Initializing order history page...');

    // View order buttons
    const viewButtons = document.querySelectorAll('.view-history-btn');
    viewButtons.forEach(btn => {
        btn.addEventListener('click', handleViewHistoryOrderClick);
    });

    // Export CSV button
    const exportBtn = document.getElementById('export_csv_btn');
    if (exportBtn) {
        exportBtn.addEventListener('click', exportOrderHistoryCSV);
    }

    console.log('Order history page initialized');
}

/**
 * Handle view order button in history
 */
async function handleViewHistoryOrderClick(event) {
    const orderId = event.currentTarget.dataset.orderId;
    console.log('View history order clicked:', orderId);

    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('orderHistoryModal'));
    modal.show();

    // Fetch and display order details (reuse same function)
    try {
        const response = await fetch(`/paper-trading/api/orders/${orderId}/`);
        const data = await response.json();

        if (data.success) {
            const detailsBody = document.getElementById('order_history_details');
            if (detailsBody) {
                detailsBody.innerHTML = generateHistoryDetailsHTML(data.order);
            }
        }
    } catch (error) {
        console.error('Error fetching order details:', error);
    }
}

/**
 * Generate HTML for history order details
 */
function generateHistoryDetailsHTML(order) {
    return `
        <div class="row g-3">
            <div class="col-12">
                <h6>Order Information</h6>
            </div>
            ${displayOrderDetails(order)}
            ${order.filled_amount_usd ? `
            <div class="col-12 mt-3">
                <h6>Fill Information</h6>
            </div>
            <div class="col-md-6">
                <strong>Filled Amount:</strong><br>
                ${formatCurrency(order.filled_amount_usd)}
            </div>
            <div class="col-md-6">
                <strong>Average Fill Price:</strong><br>
                ${formatCurrency(order.average_fill_price)}
            </div>
            ` : ''}
            ${order.error_message ? `
            <div class="col-12">
                <div class="alert alert-danger">
                    <strong>Error:</strong> ${order.error_message}
                </div>
            </div>
            ` : ''}
        </div>
    `;
}

/**
 * Export order history to CSV
 */
function exportOrderHistoryCSV() {
    console.log('Exporting order history to CSV...');

    const rows = document.querySelectorAll('.order-history-row');
    if (rows.length === 0) {
        showToast('No orders to export', 'warning');
        return;
    }

    // CSV headers
    let csv = 'Order ID,Type,Token Symbol,Token Address,Amount USD,Limit Price,Trigger Price,Status,Created,Completed\n';

    // Add rows
    rows.forEach(row => {
        const cells = row.querySelectorAll('td');
        const rowData = [
            cells[0].textContent.trim(),
            cells[1].textContent.trim(),
            cells[2].querySelector('strong').textContent.trim(),
            cells[2].querySelector('.font-monospace').textContent.trim(),
            cells[3].textContent.trim().replace('$', ''),
            cells[4].textContent.trim(),
            cells[4].textContent.trim(),
            cells[6].textContent.trim(),
            cells[7].textContent.trim(),
            cells[8].textContent.trim()
        ];
        csv += rowData.map(field => `"${field}"`).join(',') + '\n';
    });

    // Download
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `order_history_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);

    showToast('Order history exported successfully', 'success');
}

// =============================================================================
// WEBSOCKET FOR REAL-TIME UPDATES
// =============================================================================

/**
 * Initialize WebSocket connection for order updates
 */
function initializeOrderWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/paper-trading/`;

    console.log('Connecting to WebSocket:', wsUrl);

    orderWebSocket = new WebSocket(wsUrl);

    orderWebSocket.onopen = () => {
        console.log('WebSocket connected');
        updateWSStatus('connected');
    };

    orderWebSocket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data);
    };

    orderWebSocket.onerror = (error) => {
        console.error('WebSocket error:', error);
        updateWSStatus('error');
    };

    orderWebSocket.onclose = () => {
        console.log('WebSocket disconnected');
        updateWSStatus('disconnected');

        // Attempt to reconnect after 5 seconds
        setTimeout(initializeOrderWebSocket, 5000);
    };
}

/**
 * Handle WebSocket messages
 */
function handleWebSocketMessage(data) {
    console.log('WebSocket message received:', data);

    if (data.type === 'order_update') {
        updateOrderRow(data.order);
    } else if (data.type === 'order_filled') {
        handleOrderFilled(data.order);
    } else if (data.type === 'order_cancelled') {
        handleOrderCancelled(data.order);
    }
}

/**
 * Update WebSocket status indicator
 */
function updateWSStatus(status) {
    const wsStatus = document.getElementById('ws_status');
    if (!wsStatus) return;

    const statusConfig = {
        'connecting': { class: 'bg-warning', text: 'Connecting...' },
        'connected': { class: 'bg-success', text: 'Live' },
        'disconnected': { class: 'bg-secondary', text: 'Disconnected' },
        'error': { class: 'bg-danger', text: 'Error' }
    };

    const config = statusConfig[status] || statusConfig['disconnected'];
    wsStatus.className = `badge ${config.class}`;
    wsStatus.innerHTML = `<i class="bi bi-circle-fill me-1"></i>${config.text}`;
}

/**
 * Update order row with new data
 */
function updateOrderRow(order) {
    const row = document.querySelector(`tr[data-order-id="${order.order_id}"]`);
    if (!row) return;

    // Update status badge
    const statusBadge = row.querySelector('.badge');
    if (statusBadge) {
        statusBadge.className = `badge bg-${getStatusColor(order.status)}`;
        statusBadge.textContent = order.status;
    }

    // Add visual feedback
    row.classList.add('table-success');
    setTimeout(() => row.classList.remove('table-success'), 2000);
}

/**
 * Handle order filled notification
 */
function handleOrderFilled(order) {
    showToast(`Order ${order.order_id.slice(0, 8)}... filled successfully!`, 'success');

    // Remove from active orders table
    const row = document.querySelector(`tr[data-order-id="${order.order_id}"]`);
    if (row) {
        row.remove();
        updateOrderCounts();
    }
}

/**
 * Handle order cancelled notification
 */
function handleOrderCancelled(order) {
    showToast(`Order ${order.order_id.slice(0, 8)}... cancelled`, 'info');

    // Remove from active orders table
    const row = document.querySelector(`tr[data-order-id="${order.order_id}"]`);
    if (row) {
        row.remove();
        updateOrderCounts();
    }
}