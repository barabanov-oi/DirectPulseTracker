/**
 * Reports.js - Functionality for report generation and display
 */

// Initialize DataTables when document is ready
document.addEventListener('DOMContentLoaded', function() {
    // Initialize the DataTable for campaign data
    if (document.getElementById('campaignsTable')) {
        $('#campaignsTable').DataTable({
            responsive: true,
            dom: 'Bfrtip',
            buttons: [
                {
                    extend: 'copy',
                    className: 'btn btn-sm btn-outline-secondary'
                },
                {
                    extend: 'csv',
                    className: 'btn btn-sm btn-outline-secondary'
                },
                {
                    extend: 'excel',
                    className: 'btn btn-sm btn-outline-secondary'
                },
                {
                    extend: 'pdf',
                    className: 'btn btn-sm btn-outline-secondary'
                },
                {
                    extend: 'print',
                    className: 'btn btn-sm btn-outline-secondary'
                }
            ]
        });
    }

    // Initialize the DataTable for reports list
    if (document.getElementById('reportsTable')) {
        $('#reportsTable').DataTable({
            order: [[2, 'desc']], // Sort by date (created) column
            responsive: true
        });
    }

    // Format currency values
    formatCurrencyValues();
});

/**
 * Format all currency values with proper symbol and thousand separators
 */
function formatCurrencyValues() {
    document.querySelectorAll('.currency-value').forEach(function(element) {
        const value = parseFloat(element.textContent);
        if (!isNaN(value)) {
            element.textContent = formatCurrency(value, '₽');
        }
    });
}

/**
 * Format a number as currency with the specified symbol
 * @param {number} value - Number to format as currency
 * @param {string} symbol - Currency symbol to use (default: ₽)
 * @returns {string} Formatted currency string
 */
function formatCurrency(value, symbol = '₽') {
    return value.toLocaleString('ru-RU', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }) + ' ' + symbol;
}

/**
 * Export currently displayed report to CSV
 * @param {number} reportId - The ID of the report to export
 */
function exportReportToCSV(reportId) {
    window.location.href = `/reports/export/${reportId}`;
}

/**
 * Send a report to Telegram manually
 * @param {number} reportId - The ID of the report to send
 */
function sendReportToTelegram(reportId) {
    // Show loading indicator
    const sendButton = document.getElementById('sendToTelegramBtn');
    if (sendButton) {
        const originalText = sendButton.innerHTML;
        sendButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Sending...';
        sendButton.disabled = true;

        // Make Ajax request to send the report
        fetch(`/reports/send_to_telegram/${reportId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Show success message
                showAlert('Report sent to Telegram successfully!', 'success');
                
                // Update the button to show sent status
                sendButton.innerHTML = '<i class="fas fa-check"></i> Sent';
                sendButton.classList.remove('btn-primary');
                sendButton.classList.add('btn-success');
            } else {
                // Show error message
                showAlert('Failed to send report: ' + data.error, 'danger');
                sendButton.innerHTML = originalText;
                sendButton.disabled = false;
            }
        })
        .catch(error => {
            console.error('Error sending report to Telegram:', error);
            showAlert('An error occurred while sending the report', 'danger');
            sendButton.innerHTML = originalText;
            sendButton.disabled = false;
        });
    }
}

/**
 * Show an alert message on the page
 * @param {string} message - The message to display
 * @param {string} type - Alert type (success, danger, warning, info)
 */
function showAlert(message, type = 'info') {
    const alertsContainer = document.getElementById('alertsContainer');
    if (!alertsContainer) {
        // Create alerts container if it doesn't exist
        const container = document.createElement('div');
        container.id = 'alertsContainer';
        container.className = 'position-fixed top-0 end-0 p-3';
        container.style.zIndex = '5000';
        document.body.appendChild(container);
    }

    const id = 'alert-' + Date.now();
    const html = `
        <div id="${id}" class="toast align-items-center text-white bg-${type} border-0" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body">
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>
    `;

    const alertsContainer = document.getElementById('alertsContainer');
    alertsContainer.insertAdjacentHTML('beforeend', html);

    const toastElement = document.getElementById(id);
    const toast = new bootstrap.Toast(toastElement, { delay: 5000 });
    toast.show();

    // Remove the element after it's hidden
    toastElement.addEventListener('hidden.bs.toast', function() {
        toastElement.remove();
    });
}

/**
 * Generate a report on demand for the selected template
 * @param {number} templateId - The ID of the template to use
 */
function generateReportForTemplate(templateId) {
    // Redirect to generate report page with template pre-selected
    window.location.href = `/reports/generate?template_id=${templateId}`;
}
