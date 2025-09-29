// File: dexproject/paper_trading/static/js/paper_trading_analytics.js

/**
 * Paper Trading Analytics JavaScript
 * 
 * Handles chart initialization and real-time updates for the analytics dashboard.
 * Uses Chart.js for rendering interactive charts.
 */

// Chart configuration defaults
Chart.defaults.color = '#9ca3af';
Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.1)';

/**
 * Initialize P&L trend chart
 * @param {Array} dailyPnlData - Array of daily P&L data points
 */
function initializePnLChart(dailyPnlData) {
    const ctx = document.getElementById('pnlChart');
    if (!ctx) return;

    const labels = dailyPnlData.map(d => d.date);
    const dailyPnl = dailyPnlData.map(d => d.pnl);
    const cumulativePnl = dailyPnlData.map(d => d.cumulative);

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Daily P&L',
                    data: dailyPnl,
                    borderColor: '#0095ff',
                    backgroundColor: 'rgba(0, 149, 255, 0.1)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: true,
                    yAxisID: 'y'
                },
                {
                    label: 'Cumulative P&L',
                    data: cumulativePnl,
                    borderColor: '#00d68f',
                    backgroundColor: 'rgba(0, 214, 143, 0.1)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: false,
                    yAxisID: 'y1'
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
                    position: 'top',
                    labels: {
                        padding: 15,
                        usePointStyle: true
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    padding: 12,
                    titleColor: '#fff',
                    bodyColor: '#9ca3af',
                    borderColor: 'rgba(255, 255, 255, 0.1)',
                    borderWidth: 1,
                    displayColors: true,
                    callbacks: {
                        label: function (context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            if (context.parsed.y !== null) {
                                label += '$' + context.parsed.y.toFixed(2);
                            }
                            return label;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        maxRotation: 45,
                        minRotation: 45,
                        autoSkip: true,
                        maxTicksLimit: 10
                    }
                },
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    title: {
                        display: true,
                        text: 'Daily P&L ($)'
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.05)'
                    }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    title: {
                        display: true,
                        text: 'Cumulative P&L ($)'
                    },
                    grid: {
                        drawOnChartArea: false
                    }
                }
            }
        }
    });
}

/**
 * Initialize hourly trading activity chart
 * @param {Object} hourlyDistribution - Object with hourly trading data
 */
function initializeHourlyChart(hourlyDistribution) {
    const ctx = document.getElementById('hourlyChart');
    if (!ctx) return;

    const hours = Object.keys(hourlyDistribution).map(h => `${h}:00`);
    const counts = Object.values(hourlyDistribution).map(d => d.count);
    const avgPnl = Object.values(hourlyDistribution).map(d => d.avg_pnl);

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: hours,
            datasets: [
                {
                    label: 'Trade Count',
                    data: counts,
                    backgroundColor: 'rgba(0, 149, 255, 0.5)',
                    borderColor: '#0095ff',
                    borderWidth: 1,
                    yAxisID: 'y'
                },
                {
                    label: 'Avg P&L',
                    data: avgPnl,
                    type: 'line',
                    borderColor: '#00d68f',
                    backgroundColor: 'rgba(0, 214, 143, 0.1)',
                    borderWidth: 2,
                    tension: 0.4,
                    yAxisID: 'y1'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        padding: 10,
                        usePointStyle: true,
                        font: {
                            size: 11
                        }
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    callbacks: {
                        label: function (context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            if (context.datasetIndex === 0) {
                                label += context.parsed.y + ' trades';
                            } else {
                                label += '$' + context.parsed.y.toFixed(2);
                            }
                            return label;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        font: {
                            size: 10
                        },
                        autoSkip: true,
                        maxTicksLimit: 12
                    }
                },
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    title: {
                        display: false
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.05)'
                    }
                },
                y1: {
                    type: 'linear',
                    display: false,
                    position: 'right',
                    grid: {
                        drawOnChartArea: false
                    }
                }
            }
        }
    });
}

/**
 * Initialize token distribution pie chart
 * @param {Array} tokenStats - Array of token statistics
 */
function initializeTokenChart(tokenStats) {
    const ctx = document.getElementById('tokenChart');
    if (!ctx || !tokenStats || tokenStats.length === 0) return;

    // Take top 8 tokens for better visibility
    const topTokens = tokenStats.slice(0, 8);
    const labels = topTokens.map(t => t.symbol);
    const volumes = topTokens.map(t => t.volume);

    // Generate colors
    const colors = [
        '#00d68f',
        '#0095ff',
        '#ff3d71',
        '#ffaa00',
        '#bb6bd9',
        '#00bfa5',
        '#ff6b6b',
        '#4ecdc4'
    ];

    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: volumes,
                backgroundColor: colors.map(c => c + '80'), // Add transparency
                borderColor: colors,
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'right',
                    labels: {
                        padding: 15,
                        generateLabels: function (chart) {
                            const data = chart.data;
                            if (data.labels.length && data.datasets.length) {
                                return data.labels.map((label, i) => {
                                    const dataset = data.datasets[0];
                                    const value = dataset.data[i];
                                    const total = dataset.data.reduce((a, b) => a + b, 0);
                                    const percentage = ((value / total) * 100).toFixed(1);

                                    return {
                                        text: `${label} (${percentage}%)`,
                                        fillStyle: dataset.backgroundColor[i],
                                        strokeStyle: dataset.borderColor[i],
                                        lineWidth: dataset.borderWidth,
                                        hidden: false,
                                        index: i
                                    };
                                });
                            }
                            return [];
                        }
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    callbacks: {
                        label: function (context) {
                            const label = context.label || '';
                            const value = context.parsed;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = ((value / total) * 100).toFixed(1);
                            return `${label}: $${value.toFixed(2)} (${percentage}%)`;
                        }
                    }
                }
            },
            cutout: '60%'
        }
    });
}

/**
 * Refresh analytics data
 * Fetches latest data from the server and updates all charts
 */
async function refreshAnalytics() {
    try {
        const response = await fetch('/paper-trading/api/analytics/data/');
        if (!response.ok) throw new Error('Failed to fetch analytics data');

        const data = await response.json();

        // Update metric cards
        updateMetricCards(data.metrics);

        // Update charts
        if (data.daily_pnl) {
            updatePnLChart(data.daily_pnl);
        }

        console.log('Analytics refreshed successfully');
    } catch (error) {
        console.error('Error refreshing analytics:', error);
    }
}

/**
 * Update metric cards with new data
 * @param {Object} metrics - Updated metrics data
 */
function updateMetricCards(metrics) {
    // Update win rate
    const winRateEl = document.querySelector('[data-metric="win-rate"]');
    if (winRateEl) {
        winRateEl.textContent = `${metrics.win_rate.toFixed(1)}%`;
        winRateEl.className = metrics.win_rate >= 50 ? 'text-success' : 'text-danger';
    }

    // Update profit factor
    const profitFactorEl = document.querySelector('[data-metric="profit-factor"]');
    if (profitFactorEl) {
        profitFactorEl.textContent = metrics.profit_factor.toFixed(2);
        profitFactorEl.className = metrics.profit_factor >= 1 ? 'text-success' : 'text-danger';
    }

    // Add update animation
    document.querySelectorAll('.metric-card').forEach(card => {
        card.style.animation = 'pulse 0.5s ease-out';
        setTimeout(() => {
            card.style.animation = '';
        }, 500);
    });
}

/**
 * Export analytics data to CSV
 */
function exportAnalytics() {
    window.location.href = '/paper-trading/api/analytics/export/';
}

/**
 * Initialize page
 */
document.addEventListener('DOMContentLoaded', function () {
    // Set up auto-refresh every 30 seconds
    if (typeof has_data !== 'undefined' && has_data) {
        setInterval(refreshAnalytics, 30000);
    }

    // Add export button handler
    const exportBtn = document.getElementById('export-analytics');
    if (exportBtn) {
        exportBtn.addEventListener('click', exportAnalytics);
    }

    console.log('Analytics page initialized');
});

// CSS animation for pulse effect
const style = document.createElement('style');
style.textContent = `
    @keyframes pulse {
        0% { transform: scale(1); }
        50% { transform: scale(1.02); }
        100% { transform: scale(1); }
    }
`;
document.head.appendChild(style);