/**
 * Paper Trading Sessions Analysis JavaScript
 * 
 * Handles session comparison charts, session listing, and CSV export functionality.
 * Provides visual comparison of trading sessions with interactive charts.
 * 
 * Dependencies:
 * - common-utils.js (must be loaded before this file)
 *   - Uses: showToast(), getCSRFToken()
 * - Chart.js 4.x (loaded in base.html)
 * 
 * File: dexproject/static/js/paper_trading_sessions.js
 */

'use strict';

// ============================================================================
// CONFIGURATION
// ============================================================================

const SESSIONS_CONFIG = {
    API_BASE_URL: '/paper-trading/api/sessions',
    EXPORT_URL_TEMPLATE: '/paper-trading/api/sessions/{session_id}/export/',
    DELETE_URL_TEMPLATE: '/paper-trading/api/sessions/{session_id}/delete/',
    MAX_SESSIONS_DISPLAY: 20,
    CHART_COLORS: [
        '#00D4AA',  // Primary teal
        '#FF3B30',  // Danger red
        '#007AFF',  // Blue
        '#FF9500',  // Orange
        '#5856D6',  // Purple
        '#34C759',  // Green
        '#FF2D55',  // Pink
        '#5AC8FA',  // Light blue
        '#FFCC00',  // Yellow
        '#8E8E93'   // Gray
    ]
};

// ============================================================================
// STATE MANAGEMENT
// ============================================================================

const sessionsState = {
    allSessions: [],
    selectedSessions: [],
    chart: null,
    currentChartType: 'balance'
};

// ============================================================================
// INITIALIZATION
// ============================================================================

/**
 * Initialize sessions page on DOM ready
 */
document.addEventListener('DOMContentLoaded', function () {
    console.log('Initializing sessions analysis page...');

    // Load sessions from API
    loadSessions();

    // Setup chart type switcher
    setupChartTypeSwitcher();

    console.log('Sessions analysis page initialized');
});

// ============================================================================
// API FUNCTIONS
// ============================================================================

/**
 * Load sessions from API
 */
async function loadSessions() {
    console.log('Loading sessions from API...');

    try {
        const response = await fetch(`${SESSIONS_CONFIG.API_BASE_URL}/history/`);
        const data = await response.json();

        if (data.success && data.sessions) {
            sessionsState.allSessions = data.sessions;
            console.log(`Loaded ${sessionsState.allSessions.length} sessions`);

            // Debug: Log first session structure
            if (sessionsState.allSessions.length > 0) {
                console.log('First session data:', sessionsState.allSessions[0]);
            }

            // Update total count badge
            document.getElementById('totalSessions').textContent = sessionsState.allSessions.length;

            // Render sessions
            renderSessions();

            // Auto-select first 3 sessions for comparison
            if (sessionsState.allSessions.length > 0) {
                const autoSelect = sessionsState.allSessions.slice(0, Math.min(3, sessionsState.allSessions.length));
                autoSelect.forEach(session => {
                    toggleSessionSelection(session.session_id, true);
                });
            }
        } else {
            console.warn('No sessions data received');
            showEmptyState();
        }

    } catch (error) {
        console.error('Error loading sessions:', error);
        showToast('Failed to load sessions', 'danger');
        showEmptyState();
    } finally {
        hideLoadingState();
    }
}

/**
 * Export session to CSV
 * 
 * @param {string} sessionId - Session ID to export
 * @param {string} sessionName - Session name for user feedback
 */
async function exportSessionCSV(sessionId, sessionName) {
    console.log(`Exporting session ${sessionId} to CSV...`);

    try {
        // Show loading toast
        showToast(`Exporting ${sessionName}...`, 'info', 2000);

        // Create download URL
        const exportUrl = SESSIONS_CONFIG.EXPORT_URL_TEMPLATE.replace('{session_id}', sessionId);

        // Trigger download
        window.location.href = exportUrl;

        // Show success toast after brief delay
        setTimeout(() => {
            showToast(`${sessionName} exported successfully!`, 'success');
        }, 500);

    } catch (error) {
        console.error('Error exporting session:', error);
        showToast(`Failed to export ${sessionName}`, 'danger');
    }
}

/**
 * Delete a session after confirmation
 * 
 * @param {string} sessionId - Session ID to delete
 * @param {string} sessionName - Session name for confirmation dialog
 */
async function deleteSession(sessionId, sessionName) {
    console.log(`Delete requested for session ${sessionId}`);

    // Show confirmation dialog
    const confirmed = confirm(
        `Are you sure you want to delete "${sessionName}"?\n\n` +
        `This will permanently remove:\n` +
        `• All trades from this session\n` +
        `• All positions from this session\n` +
        `• Session performance data\n\n` +
        `This action cannot be undone!`
    );

    if (!confirmed) {
        console.log('Delete cancelled by user');
        return;
    }

    try {
        // Show loading toast
        showToast(`Deleting ${sessionName}...`, 'info', 2000);

        // Create delete URL
        const deleteUrl = SESSIONS_CONFIG.DELETE_URL_TEMPLATE.replace('{session_id}', sessionId);

        // Call delete API
        const response = await fetch(deleteUrl, {
            method: 'POST',  // Using POST since some browsers don't support DELETE with fetch
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            }
        });

        const data = await response.json();

        if (data.success) {
            showToast(`${sessionName} deleted successfully!`, 'success');

            // Remove from state
            sessionsState.allSessions = sessionsState.allSessions.filter(
                s => s.session_id !== sessionId
            );
            sessionsState.selectedSessions = sessionsState.selectedSessions.filter(
                id => id !== sessionId
            );

            // Re-render sessions
            renderSessions();

            // Update chart
            updateChart();

            // Update total count
            document.getElementById('totalSessions').textContent = sessionsState.allSessions.length;

        } else {
            showToast(`Failed to delete ${sessionName}: ${data.error}`, 'danger');
        }

    } catch (error) {
        console.error('Error deleting session:', error);
        showToast(`Failed to delete ${sessionName}`, 'danger');
    }
}

// ============================================================================
// RENDERING FUNCTIONS
// ============================================================================

/**
 * Render sessions grid
 */
function renderSessions() {
    const grid = document.getElementById('sessionsGrid');

    if (!grid) {
        console.error('Sessions grid element not found');
        return;
    }

    // Clear existing content
    grid.innerHTML = '';

    if (sessionsState.allSessions.length === 0) {
        showEmptyState();
        return;
    }

    // Show grid
    grid.style.display = 'flex';
    document.getElementById('emptyState').style.display = 'none';

    // Render each session card
    sessionsState.allSessions.forEach((session, index) => {
        const card = createSessionCard(session, index);
        grid.appendChild(card);
    });
}

/**
 * Create session card element
 * 
 * @param {Object} session - Session data
 * @param {number} index - Session index for color
 * @returns {HTMLElement} Session card element
 */
function createSessionCard(session, index) {
    const col = document.createElement('div');
    col.className = 'col-md-6 col-lg-4';

    // Safe field access with defaults
    const pnlUsd = session.pnl_usd || 0;
    const pnlPercent = session.pnl_percent || 0;
    const totalTrades = session.total_trades || 0;
    const winRate = session.win_rate || 0;
    const startingBalance = session.starting_balance || 0;
    const endingBalance = session.ending_balance || 0;
    const sessionName = session.session_name || session.name || 'Unnamed Session';
    const status = session.status || 'UNKNOWN';

    // Determine profit class
    const profitClass = pnlUsd >= 0 ? 'profit-positive' : 'profit-negative';
    const profitIcon = pnlUsd >= 0 ? 'bi-arrow-up-right' : 'bi-arrow-down-right';

    // Format dates
    const startDate = session.started_at ? new Date(session.started_at).toLocaleDateString() : 'N/A';
    const endDate = session.stopped_at ? new Date(session.stopped_at).toLocaleDateString() : 'Running';

    // Calculate duration
    let duration = 'N/A';
    if (session.started_at && session.stopped_at) {
        const start = new Date(session.started_at);
        const end = new Date(session.stopped_at);
        const hours = Math.floor((end - start) / (1000 * 60 * 60));
        const minutes = Math.floor(((end - start) % (1000 * 60 * 60)) / (1000 * 60));
        duration = `${hours}h ${minutes}m`;
    }

    col.innerHTML = `
        <div class="session-card" data-session-id="${session.session_id}">
            <div class="d-flex justify-content-between align-items-start mb-3">
                <div class="form-check">
                    <input 
                        class="form-check-input session-checkbox" 
                        type="checkbox" 
                        id="session_${session.session_id}"
                        onchange="toggleSessionSelection('${session.session_id}')"
                    >
                    <label class="form-check-label fw-bold" for="session_${session.session_id}">
                        ${sessionName}
                    </label>
                </div>
                <span class="badge bg-secondary">${status}</span>
            </div>
            
            <!-- P&L Display -->
            <div class="mb-3">
                <div class="h4 mb-0 ${profitClass}">
                    <i class="bi ${profitIcon} me-1"></i>
                    $${Math.abs(pnlUsd).toFixed(2)}
                    <small class="fs-6">(${pnlPercent >= 0 ? '+' : ''}${pnlPercent.toFixed(2)}%)</small>
                </div>
            </div>
            
            <!-- Session Stats -->
            <div class="row g-2 mb-3">
                <div class="col-6">
                    <div class="stat-badge">
                        <i class="bi bi-calendar3 text-primary"></i>
                        <div>
                            <small class="text-muted d-block">Started</small>
                            <small>${startDate}</small>
                        </div>
                    </div>
                </div>
                <div class="col-6">
                    <div class="stat-badge">
                        <i class="bi bi-clock text-primary"></i>
                        <div>
                            <small class="text-muted d-block">Duration</small>
                            <small>${duration}</small>
                        </div>
                    </div>
                </div>
                <div class="col-6">
                    <div class="stat-badge">
                        <i class="bi bi-graph-up text-success"></i>
                        <div>
                            <small class="text-muted d-block">Trades</small>
                            <small>${totalTrades}</small>
                        </div>
                    </div>
                </div>
                <div class="col-6">
                    <div class="stat-badge">
                        <i class="bi bi-trophy text-warning"></i>
                        <div>
                            <small class="text-muted d-block">Win Rate</small>
                            <small>${winRate.toFixed(1)}%</small>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Balance Info -->
            <div class="mb-3 small text-muted">
                <div class="d-flex justify-content-between">
                    <span>Starting:</span>
                    <span class="fw-bold">$${startingBalance.toFixed(2)}</span>
                </div>
                <div class="d-flex justify-content-between">
                    <span>Ending:</span>
                    <span class="fw-bold">$${endingBalance.toFixed(2)}</span>
                </div>
            </div>
            
            <!-- Export Button -->
            <button 
                class="btn btn-outline-primary btn-sm w-100 mb-2" 
                onclick="exportSessionCSV('${session.session_id}', '${sessionName.replace(/'/g, "\\'")}')"
            >
                <i class="bi bi-download me-1"></i>
                Export to CSV
            </button>
            
            <!-- Delete Button (only for completed/stopped sessions) -->
            ${status !== 'RUNNING' && status !== 'PAUSED' ? `
            <button 
                class="btn btn-outline-danger btn-sm w-100" 
                onclick="deleteSession('${session.session_id}', '${sessionName.replace(/'/g, "\\'")}')"
            >
                <i class="bi bi-trash me-1"></i>
                Delete Session
            </button>
            ` : `
            <button 
                class="btn btn-outline-secondary btn-sm w-100" 
                disabled
                title="Cannot delete active sessions"
            >
                <i class="bi bi-trash me-1"></i>
                Delete Session
            </button>
            `}
        </div>
    `;

    return col;
}

// ============================================================================
// SESSION SELECTION
// ============================================================================

/**
 * Toggle session selection for chart comparison
 * 
 * @param {string} sessionId - Session ID to toggle
 * @param {boolean} forceState - Optional: force checked state
 */
function toggleSessionSelection(sessionId, forceState = null) {
    const checkbox = document.getElementById(`session_${sessionId}`);
    const card = document.querySelector(`[data-session-id="${sessionId}"]`);

    if (!checkbox || !card) return;

    // Apply force state if provided
    if (forceState !== null) {
        checkbox.checked = forceState;
    }

    const isChecked = checkbox.checked;

    // Update card appearance
    if (isChecked) {
        card.classList.add('active');

        // Add to selected sessions if not already there
        if (!sessionsState.selectedSessions.includes(sessionId)) {
            sessionsState.selectedSessions.push(sessionId);
        }
    } else {
        card.classList.remove('active');

        // Remove from selected sessions
        const index = sessionsState.selectedSessions.indexOf(sessionId);
        if (index > -1) {
            sessionsState.selectedSessions.splice(index, 1);
        }
    }

    // Update chart
    updateChart();
}

// ============================================================================
// CHART FUNCTIONS
// ============================================================================

/**
 * Setup chart type switcher radio buttons
 */
function setupChartTypeSwitcher() {
    const radioButtons = document.querySelectorAll('input[name="chartType"]');

    radioButtons.forEach(radio => {
        radio.addEventListener('change', function () {
            if (this.checked) {
                sessionsState.currentChartType = this.value;
                updateChart();
            }
        });
    });
}

/**
 * Update comparison chart based on selected sessions
 */
function updateChart() {
    const canvas = document.getElementById('sessionsChart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');

    // Destroy existing chart
    if (sessionsState.chart) {
        sessionsState.chart.destroy();
    }

    // Get selected session data
    const selectedData = sessionsState.allSessions.filter(
        session => sessionsState.selectedSessions.includes(session.session_id)
    );

    if (selectedData.length === 0) {
        // Show empty chart message
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.font = '16px Arial';
        ctx.fillStyle = '#94a3b8';
        ctx.textAlign = 'center';
        ctx.fillText('Select sessions to compare', canvas.width / 2, canvas.height / 2);
        return;
    }

    // Prepare datasets based on chart type
    const datasets = selectedData.map((session, index) => {
        let dataValue;

        switch (sessionsState.currentChartType) {
            case 'balance':
                dataValue = session.ending_balance || 0;
                break;
            case 'pnl':
                dataValue = session.pnl_usd || 0;
                break;
            case 'winrate':
                dataValue = session.win_rate || 0;
                break;
            default:
                dataValue = session.ending_balance || 0;
        }

        const sessionName = session.session_name || session.name || `Session ${session.session_id.substring(0, 8)}`;

        return {
            label: sessionName,
            data: [dataValue],
            backgroundColor: SESSIONS_CONFIG.CHART_COLORS[index % SESSIONS_CONFIG.CHART_COLORS.length],
            borderColor: SESSIONS_CONFIG.CHART_COLORS[index % SESSIONS_CONFIG.CHART_COLORS.length],
            borderWidth: 2
        };
    });

    // Chart labels
    let yAxisLabel;
    switch (sessionsState.currentChartType) {
        case 'balance':
            yAxisLabel = 'Balance (USD)';
            break;
        case 'pnl':
            yAxisLabel = 'Profit/Loss (USD)';
            break;
        case 'winrate':
            yAxisLabel = 'Win Rate (%)';
            break;
        default:
            yAxisLabel = 'Value';
    }

    // Create new chart
    sessionsState.chart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Comparison'],
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        color: '#fff',
                        font: {
                            size: 12
                        }
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    titleColor: '#fff',
                    bodyColor: '#fff',
                    borderColor: 'rgba(255, 255, 255, 0.1)',
                    borderWidth: 1,
                    callbacks: {
                        label: function (context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }

                            if (sessionsState.currentChartType === 'winrate') {
                                label += context.parsed.y.toFixed(2) + '%';
                            } else {
                                label += '$' + context.parsed.y.toFixed(2);
                            }
                            return label;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        color: '#fff',
                        callback: function (value) {
                            if (sessionsState.currentChartType === 'winrate') {
                                return value.toFixed(0) + '%';
                            }
                            return '$' + value.toFixed(0);
                        }
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    title: {
                        display: true,
                        text: yAxisLabel,
                        color: '#fff'
                    }
                },
                x: {
                    ticks: {
                        color: '#fff'
                    },
                    grid: {
                        display: false
                    }
                }
            }
        }
    });
}

// ============================================================================
// UI STATE FUNCTIONS
// ============================================================================

/**
 * Hide loading state
 */
function hideLoadingState() {
    const loadingState = document.getElementById('loadingState');
    if (loadingState) {
        loadingState.style.display = 'none';
    }
}

/**
 * Show empty state
 */
function showEmptyState() {
    const emptyState = document.getElementById('emptyState');
    const sessionsGrid = document.getElementById('sessionsGrid');

    if (emptyState) emptyState.style.display = 'block';
    if (sessionsGrid) sessionsGrid.style.display = 'none';
}

// ============================================================================
// GLOBAL EXPORTS
// ============================================================================

// Export functions for template usage
window.toggleSessionSelection = toggleSessionSelection;
window.exportSessionCSV = exportSessionCSV;
window.deleteSession = deleteSession;