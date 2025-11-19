/**
 * Trading WebSocket Management Module
 * 
 * Handles WebSocket connections for real-time trading updates, including
 * transaction status, market data, and chart updates. Manages connection
 * lifecycle, reconnection logic, and message routing.
 * 
 * File: dexproject/dashboard/static/js/trading-websocket.js
 */

import { safeJsonParse } from './trading-utils.js';

export class TradingWebSocketManager {
    /**
     * Initialize the WebSocket manager
     * 
     * @param {Function} onMessage - Callback for processing messages
     * @param {Function} onError - Callback for handling errors
     * @param {Function} onStatusChange - Callback for connection status changes
     */
    constructor(onMessage, onError, onStatusChange) {
        this.onMessage = onMessage;
        this.onError = onError;
        this.onStatusChange = onStatusChange;

        // WebSocket instances
        this.tradingSocket = null;
        this.chartsSocket = null;

        // Connection configuration
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000; // Start with 1 second
        this.maxReconnectDelay = 30000; // Max 30 seconds

        // Connection state
        this.isConnecting = false;
        this.isConnected = false;
        this.shouldReconnect = true;

        // Message queue for when disconnected
        this.messageQueue = [];
        this.maxQueueSize = 100;

        // Heartbeat configuration
        this.heartbeatInterval = null;
        this.heartbeatTimeout = 30000; // 30 seconds
        this.lastHeartbeat = null;

        console.log('🔌 TradingWebSocketManager initialized');
    }

    // =============================================================================
    // CONNECTION MANAGEMENT
    // =============================================================================

    /**
     * Initialize WebSocket connection for trading updates
     * 
     * @param {string} url - WebSocket URL (optional, defaults to auto-detect)
     */
    initializeTradingSocket(url = null) {
        if (this.isConnecting || this.tradingSocket) {
            console.warn('Trading WebSocket already connecting or connected');
            return;
        }

        this.isConnecting = true;

        // Auto-detect WebSocket URL if not provided
        const wsUrl = url || this.getWebSocketUrl('/ws/trading/');

        console.log(`🔌 Connecting to trading WebSocket: ${wsUrl}`);

        try {
            this.tradingSocket = new WebSocket(wsUrl);
            this.setupTradingSocketHandlers();

        } catch (error) {
            console.error('❌ Error creating trading WebSocket:', error);
            this.isConnecting = false;
            this.handleReconnect('trading');
        }
    }

    /**
     * Initialize WebSocket connection for chart updates
     * 
     * @param {string} url - WebSocket URL (optional, defaults to auto-detect)
     */
    initializeChartsSocket(url = null) {
        if (this.chartsSocket) {
            console.warn('Charts WebSocket already connected');
            return;
        }

        // Auto-detect WebSocket URL if not provided
        const wsUrl = url || this.getWebSocketUrl('/ws/charts/');

        console.log(`📊 Connecting to charts WebSocket: ${wsUrl}`);

        try {
            this.chartsSocket = new WebSocket(wsUrl);
            this.setupChartsSocketHandlers();

        } catch (error) {
            console.error('❌ Error creating charts WebSocket:', error);
        }
    }

    /**
     * Auto-detect WebSocket URL based on current protocol
     * 
     * @param {string} path - WebSocket path
     * @returns {string} Full WebSocket URL
     */
    getWebSocketUrl(path) {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;
        return `${protocol}//${host}${path}`;
    }

    /**
     * Setup event handlers for trading WebSocket
     */
    setupTradingSocketHandlers() {
        if (!this.tradingSocket) return;

        // Connection opened
        this.tradingSocket.onopen = () => {
            console.log('✅ Trading WebSocket connected');
            this.isConnecting = false;
            this.isConnected = true;
            this.reconnectAttempts = 0;
            this.reconnectDelay = 1000;

            // Notify status change
            if (this.onStatusChange) {
                this.onStatusChange('connected', 'trading');
            }

            // Start heartbeat
            this.startHeartbeat('trading');

            // Process queued messages
            this.processMessageQueue();
        };

        // Message received
        this.tradingSocket.onmessage = (event) => {
            this.handleMessage(event, 'trading');
        };

        // Connection closed
        this.tradingSocket.onclose = (event) => {
            console.log(`🔌 Trading WebSocket closed: ${event.code} ${event.reason}`);
            this.isConnected = false;
            this.stopHeartbeat('trading');

            // Notify status change
            if (this.onStatusChange) {
                this.onStatusChange('disconnected', 'trading');
            }

            // Attempt reconnection
            if (this.shouldReconnect) {
                this.handleReconnect('trading');
            }
        };

        // Error occurred
        this.tradingSocket.onerror = (error) => {
            console.error('❌ Trading WebSocket error:', error);

            if (this.onError) {
                this.onError(error, 'trading');
            }
        };
    }

    /**
     * Setup event handlers for charts WebSocket
     */
    setupChartsSocketHandlers() {
        if (!this.chartsSocket) return;

        this.chartsSocket.onopen = () => {
            console.log('✅ Charts WebSocket connected');

            if (this.onStatusChange) {
                this.onStatusChange('connected', 'charts');
            }
        };

        this.chartsSocket.onmessage = (event) => {
            this.handleMessage(event, 'charts');
        };

        this.chartsSocket.onclose = (event) => {
            console.log(`📊 Charts WebSocket closed: ${event.code} ${event.reason}`);

            if (this.onStatusChange) {
                this.onStatusChange('disconnected', 'charts');
            }
        };

        this.chartsSocket.onerror = (error) => {
            console.error('❌ Charts WebSocket error:', error);

            if (this.onError) {
                this.onError(error, 'charts');
            }
        };
    }

    /**
     * Handle incoming WebSocket message
     * 
     * @param {MessageEvent} event - WebSocket message event
     * @param {string} source - Source socket ('trading' or 'charts')
     */
    handleMessage(event, source) {
        try {
            const data = safeJsonParse(event.data);

            if (!data) {
                console.warn('Received invalid JSON from WebSocket');
                return;
            }

            // Update last heartbeat time
            this.lastHeartbeat = Date.now();

            // Handle heartbeat/ping messages
            if (data.type === 'ping') {
                this.sendMessage({ type: 'pong' }, source);
                return;
            }

            if (data.type === 'pong') {
                // Heartbeat acknowledged
                return;
            }

            console.log(`📨 WebSocket message from ${source}:`, data);

            // Route message to handler
            if (this.onMessage) {
                this.onMessage(data, source);
            }

        } catch (error) {
            console.error('Error handling WebSocket message:', error);
        }
    }

    // =============================================================================
    // MESSAGE SENDING
    // =============================================================================

    /**
     * Send message through WebSocket
     * 
     * @param {Object} data - Message data to send
     * @param {string} socket - Target socket ('trading' or 'charts')
     * @returns {boolean} True if sent successfully
     */
    sendMessage(data, socket = 'trading') {
        const targetSocket = socket === 'trading' ? this.tradingSocket : this.chartsSocket;

        if (!targetSocket || targetSocket.readyState !== WebSocket.OPEN) {
            console.warn(`Cannot send message, ${socket} WebSocket not connected`);

            // Queue message for later if it's the trading socket
            if (socket === 'trading' && this.messageQueue.length < this.maxQueueSize) {
                this.messageQueue.push(data);
                console.log(`📦 Message queued (${this.messageQueue.length} in queue)`);
            }

            return false;
        }

        try {
            const message = JSON.stringify(data);
            targetSocket.send(message);
            console.log(`📤 Sent ${socket} WebSocket message:`, data);
            return true;

        } catch (error) {
            console.error(`Error sending ${socket} WebSocket message:`, error);
            return false;
        }
    }

    /**
     * Process queued messages
     */
    processMessageQueue() {
        if (this.messageQueue.length === 0) return;

        console.log(`📦 Processing ${this.messageQueue.length} queued messages`);

        while (this.messageQueue.length > 0) {
            const message = this.messageQueue.shift();
            this.sendMessage(message, 'trading');
        }
    }

    // =============================================================================
    // HEARTBEAT / KEEP-ALIVE
    // =============================================================================

    /**
     * Start heartbeat to keep connection alive
     * 
     * @param {string} socket - Socket to monitor ('trading' or 'charts')
     */
    startHeartbeat(socket = 'trading') {
        this.stopHeartbeat(socket); // Clear any existing interval

        this.lastHeartbeat = Date.now();

        this.heartbeatInterval = setInterval(() => {
            // Check if we've received a message recently
            const timeSinceLastHeartbeat = Date.now() - this.lastHeartbeat;

            if (timeSinceLastHeartbeat > this.heartbeatTimeout) {
                console.warn(`⚠️ No heartbeat for ${timeSinceLastHeartbeat}ms, reconnecting...`);
                this.handleReconnect(socket);
                return;
            }

            // Send ping
            this.sendMessage({ type: 'ping' }, socket);

        }, this.heartbeatTimeout / 2); // Send ping at half the timeout interval
    }

    /**
     * Stop heartbeat interval
     * 
     * @param {string} socket - Socket identifier
     */
    stopHeartbeat(socket) {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }
    }

    // =============================================================================
    // RECONNECTION LOGIC
    // =============================================================================

    /**
     * Handle WebSocket reconnection
     * 
     * @param {string} socket - Socket to reconnect ('trading' or 'charts')
     */
    handleReconnect(socket) {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error(`❌ Max reconnection attempts (${this.maxReconnectAttempts}) reached`);

            if (this.onStatusChange) {
                this.onStatusChange('failed', socket);
            }

            return;
        }

        this.reconnectAttempts++;

        // Calculate exponential backoff delay
        const delay = Math.min(
            this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
            this.maxReconnectDelay
        );

        console.log(`🔄 Reconnecting ${socket} WebSocket in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

        if (this.onStatusChange) {
            this.onStatusChange('reconnecting', socket);
        }

        setTimeout(() => {
            if (socket === 'trading') {
                this.close('trading');
                this.initializeTradingSocket();
            } else if (socket === 'charts') {
                this.close('charts');
                this.initializeChartsSocket();
            }
        }, delay);
    }

    /**
     * Reset reconnection attempts
     */
    resetReconnectionState() {
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
    }

    // =============================================================================
    // CONNECTION CONTROL
    // =============================================================================

    /**
     * Close WebSocket connection
     * 
     * @param {string} socket - Socket to close ('trading', 'charts', or 'all')
     */
    close(socket = 'all') {
        this.shouldReconnect = false;

        if (socket === 'trading' || socket === 'all') {
            if (this.tradingSocket) {
                console.log('🔌 Closing trading WebSocket');
                this.stopHeartbeat('trading');
                this.tradingSocket.close();
                this.tradingSocket = null;
                this.isConnected = false;
            }
        }

        if (socket === 'charts' || socket === 'all') {
            if (this.chartsSocket) {
                console.log('📊 Closing charts WebSocket');
                this.chartsSocket.close();
                this.chartsSocket = null;
            }
        }
    }

    /**
     * Reconnect WebSocket
     * 
     * @param {string} socket - Socket to reconnect ('trading', 'charts', or 'all')
     */
    reconnect(socket = 'all') {
        this.shouldReconnect = true;
        this.resetReconnectionState();

        this.close(socket);

        setTimeout(() => {
            if (socket === 'trading' || socket === 'all') {
                this.initializeTradingSocket();
            }
            if (socket === 'charts' || socket === 'all') {
                this.initializeChartsSocket();
            }
        }, 1000);
    }

    /**
     * Get connection status
     * 
     * @returns {Object} Connection status for all sockets
     */
    getStatus() {
        return {
            trading: {
                connected: this.tradingSocket?.readyState === WebSocket.OPEN,
                readyState: this.tradingSocket?.readyState || -1,
                reconnectAttempts: this.reconnectAttempts
            },
            charts: {
                connected: this.chartsSocket?.readyState === WebSocket.OPEN,
                readyState: this.chartsSocket?.readyState || -1
            },
            queueSize: this.messageQueue.length
        };
    }

    /**
     * Cleanup and destroy
     */
    destroy() {
        this.shouldReconnect = false;
        this.stopHeartbeat('trading');
        this.close('all');
        this.messageQueue = [];

        console.log('🧹 TradingWebSocketManager cleanup completed');
    }
}