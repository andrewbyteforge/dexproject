/**
 * Paper Trading Trade History Page JavaScript
 * Handles filtering, exporting, and displaying trade history
 */

/**
 * Clear all filters and reload page
 */
function clearFilters() {
    window.location.href = '/paper-trading/trades/';
}

/**
 * Export trades to CSV
 */
function exportToCSV() {
    const rows = [];

    // Headers
    rows.push([
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
    ]);

    // Data rows
    document.querySelectorAll('.trade-row').forEach(row => {
        const cells = row.querySelectorAll('td');
        const rowData = [];

        // Extract text from each cell, cleaning up the data
        cells.forEach((cell, index) => {
            let text = cell.textContent.trim().replace(/\s+/g, ' ');

            // Special handling for certain columns
            if (index === 0) { // Date/Time column
                text = text.replace(/\s+/g, ' ');
            } else if (index === 2) { // Token pair column
                text = text.replace('→', ' -> ');
            }

            rowData.push(text);
        });

        rows.push(rowData);
    });

    // Create CSV content
    const csvContent = rows.map(row =>
        row.map(field =>
            // Escape fields that contain commas or quotes
            typeof field === 'string' && (field.includes(',') || field.includes('"'))
                ? `"${field.replace(/"/g, '""')}"`
                : field
        ).join(',')
    ).join('\n');

    // Download file
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `paper_trades_${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);

    showToast('Trade history exported to CSV', 'success');
}

/**
 * Print trade report
 */
function printReport() {
    window.print();
}

/**
 * Auto-submit form when filters change (optional convenience feature)
 */
document.addEventListener('DOMContentLoaded', function () {
    const filterForm = document.getElementById('filter-form');

    // Optional: Auto-submit on select change
    // Uncomment if you want instant filtering
    /*
    const filterSelects = filterForm.querySelectorAll('select');
    filterSelects.forEach(select => {
        select.addEventListener('change', () => {
            filterForm.submit();
        });
    });
    */
});