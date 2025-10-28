/**
 * Paper Trading Trade History Page JavaScript
 * 
 * Handles filtering, exporting, and displaying trade history.
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
        FILTER_FORM: 'filter-form'
    }
};

// ============================================================================
// FILTER MANAGEMENT
// ============================================================================

/**
 * Clear all filters and reload page
 * Removes all query parameters and returns to unfiltered view
 */
function clearFilters() {
    console.log('Clearing all filters...');
    window.location.href = TRADE_HISTORY_CONFIG.BASE_URL;
}

// ============================================================================
// CSV EXPORT
// ============================================================================

/**
 * Export trades to CSV file
 * Extracts data from visible trade rows and creates downloadable CSV
 */
function exportToCSV() {
    console.log('Starting CSV export...');

    try {
        const rows = [];

        // Add headers
        rows.push(TRADE_HISTORY_CONFIG.CSV_HEADERS);

        // Extract data from table rows
        const tradeRows = document.querySelectorAll(TRADE_HISTORY_CONFIG.SELECTORS.TRADE_ROW);

        if (tradeRows.length === 0) {
            console.warn('No trade rows found to export');
            showToast('No trades to export', 'warning'); // From common-utils.js
            return;
        }

        console.log(`Exporting ${tradeRows.length} trade rows...`);

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
                    text = text.replace(/→/g, ' -> ');
                    text = text.replace(/â†'/g, ' -> '); // Handle encoding issues
                }

                rowData.push(text);
            });

            if (rowData.length > 0) {
                rows.push(rowData);
            }
        });

        console.log(`Processed ${rows.length - 1} data rows (excluding header)`);

        // Create CSV content with proper escaping
        const csvContent = rows.map(row =>
            row.map(field => escapeCsvField(field)).join(',')
        ).join('\n');

        // Generate filename with current date
        const filename = `${TRADE_HISTORY_CONFIG.CSV_FILENAME_PREFIX}${getCurrentDateString()}.csv`;

        // Trigger download
        downloadCsvFile(csvContent, filename);

        console.log(`CSV export completed: ${filename}`);
        showToast('Trade history exported to CSV', 'success'); // From common-utils.js

    } catch (error) {
        console.error('Error exporting CSV:', error);
        showToast('Failed to export CSV', 'danger'); // From common-utils.js
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
 */
function printReport() {
    console.log('Opening print dialog...');
    window.print();
}

// ============================================================================
// FILTER AUTO-SUBMIT (Optional Feature)
// ============================================================================

/**
 * Enable auto-submit on filter changes
 * Uncomment the function call in initialization to activate
 */
function enableFilterAutoSubmit() {
    const filterForm = document.getElementById(TRADE_HISTORY_CONFIG.SELECTORS.FILTER_FORM);

    if (!filterForm) {
        console.warn('Filter form not found');
        return;
    }

    console.log('Enabling auto-submit for filter form');

    const filterSelects = filterForm.querySelectorAll('select');
    const filterInputs = filterForm.querySelectorAll('input[type="date"]');

    // Auto-submit when select changes
    filterSelects.forEach(select => {
        select.addEventListener('change', () => {
            console.log('Filter changed, submitting form...');
            filterForm.submit();
        });
    });

    // Auto-submit when date changes
    filterInputs.forEach(input => {
        input.addEventListener('change', () => {
            console.log('Date filter changed, submitting form...');
            filterForm.submit();
        });
    });
}

// ============================================================================
// INITIALIZATION
// ============================================================================

/**
 * Initialize trade history page
 * Sets up event listeners and optional features
 */
function initializeTradeHistory() {
    console.log('Initializing trade history page...');

    // Check if we have any trades displayed
    const tradeRows = document.querySelectorAll(TRADE_HISTORY_CONFIG.SELECTORS.TRADE_ROW);
    console.log(`Found ${tradeRows.length} trade rows`);

    // Optional: Enable auto-submit on filter changes
    // Uncomment the line below if you want instant filtering
    // enableFilterAutoSubmit();

    console.log('Trade history page initialized successfully');
}

// Auto-initialize when DOM is ready
document.addEventListener('DOMContentLoaded', initializeTradeHistory);

// ============================================================================
// GLOBAL EXPORTS
// ============================================================================

// Export functions for template usage
window.clearFilters = clearFilters;
window.exportToCSV = exportToCSV;
window.printReport = printReport;

// Export configuration for testing/debugging
window.TRADE_HISTORY_CONFIG = TRADE_HISTORY_CONFIG;