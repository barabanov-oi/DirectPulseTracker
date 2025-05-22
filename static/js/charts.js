/**
 * Charts.js - Functions for creating charts for DirectPulse
 */

/**
 * Creates a cost and clicks chart from summary data
 * @param {string} canvasId - Canvas element ID
 * @param {Object} totals - Report totals data
 */
function createCostClicksChart(canvasId, totals) {
    if (!totals || !document.getElementById(canvasId)) {
        return;
    }
    
    const ctx = document.getElementById(canvasId).getContext('2d');
    
    const chart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Performance'],
            datasets: [
                {
                    label: 'Cost (₽)',
                    data: [totals.Cost],
                    backgroundColor: 'rgba(220, 53, 69, 0.6)',
                    borderColor: 'rgba(220, 53, 69, 1)',
                    borderWidth: 1,
                    yAxisID: 'y'
                },
                {
                    label: 'Clicks',
                    data: [totals.Clicks],
                    backgroundColor: 'rgba(13, 110, 253, 0.6)',
                    borderColor: 'rgba(13, 110, 253, 1)',
                    borderWidth: 1,
                    yAxisID: 'y1'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    type: 'linear',
                    position: 'left',
                    title: {
                        display: true,
                        text: 'Cost (₽)'
                    },
                    ticks: {
                        callback: function(value) {
                            return value.toLocaleString() + ' ₽';
                        }
                    }
                },
                y1: {
                    type: 'linear',
                    position: 'right',
                    title: {
                        display: true,
                        text: 'Clicks'
                    },
                    grid: {
                        drawOnChartArea: false
                    }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            
                            if (context.dataset.yAxisID === 'y') {
                                label += context.parsed.y.toLocaleString() + ' ₽';
                            } else {
                                label += context.parsed.y.toLocaleString();
                            }
                            
                            return label;
                        }
                    }
                }
            }
        }
    });
    
    return chart;
}

/**
 * Creates a chart showing top campaigns by a specific metric
 * @param {string} canvasId - Canvas element ID
 * @param {Array} campaigns - Array of campaign data
 * @param {string} metric - Metric to display (e.g., 'Cost', 'Clicks')
 * @param {string} unit - Unit to display (e.g., '₽', '')
 */
function createTopCampaignsChart(canvasId, campaigns, metric = 'Cost', unit = '') {
    if (!campaigns || !campaigns.length || !document.getElementById(canvasId)) {
        return;
    }
    
    const ctx = document.getElementById(canvasId).getContext('2d');
    
    // Sort campaigns by the specified metric
    const sortedCampaigns = [...campaigns].sort((a, b) => b[metric] - a[metric]);
    
    // Take top 5 or fewer if less are available
    const topCampaigns = sortedCampaigns.slice(0, Math.min(5, sortedCampaigns.length));
    
    // Prepare labels and data
    const labels = topCampaigns.map(campaign => truncateString(campaign.Name, 15));
    const data = topCampaigns.map(campaign => campaign[metric]);
    
    // Choose color based on metric
    let backgroundColor, borderColor;
    switch (metric) {
        case 'Cost':
            backgroundColor = 'rgba(220, 53, 69, 0.6)';
            borderColor = 'rgba(220, 53, 69, 1)';
            break;
        case 'Clicks':
            backgroundColor = 'rgba(13, 110, 253, 0.6)';
            borderColor = 'rgba(13, 110, 253, 1)';
            break;
        case 'Conversions':
            backgroundColor = 'rgba(25, 135, 84, 0.6)';
            borderColor = 'rgba(25, 135, 84, 1)';
            break;
        default:
            backgroundColor = 'rgba(111, 66, 193, 0.6)';
            borderColor = 'rgba(111, 66, 193, 1)';
    }
    
    // Create chart
    const chart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: metric,
                data: data,
                backgroundColor: backgroundColor,
                borderColor: borderColor,
                borderWidth: 1
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: metric + (unit ? ' (' + unit + ')' : '')
                    },
                    ticks: {
                        callback: function(value) {
                            if (unit === '₽') {
                                return value.toLocaleString() + ' ₽';
                            } else if (unit === '%') {
                                return value + '%';
                            } else {
                                return value.toLocaleString();
                            }
                        }
                    }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            
                            if (unit === '₽') {
                                label += context.parsed.x.toLocaleString() + ' ₽';
                            } else if (unit === '%') {
                                label += context.parsed.x + '%';
                            } else {
                                label += context.parsed.x.toLocaleString();
                            }
                            
                            return label;
                        },
                        title: function(context) {
                            // Return full campaign name in tooltip
                            const index = context[0].dataIndex;
                            return topCampaigns[index].Name;
                        }
                    }
                }
            }
        }
    });
    
    return chart;
}

/**
 * Creates a comparison chart for metrics over time
 * @param {string} canvasId - Canvas element ID
 * @param {Array} data - Time series data
 * @param {Array} metrics - Array of metrics to display
 */
function createTimeSeriesChart(canvasId, data, metrics) {
    if (!data || !data.length || !document.getElementById(canvasId)) {
        return;
    }
    
    const ctx = document.getElementById(canvasId).getContext('2d');
    
    // Prepare datasets
    const datasets = metrics.map((metric, index) => {
        // Generate a color based on index
        const hue = (index * 137) % 360;
        const color = `hsl(${hue}, 70%, 60%)`;
        
        return {
            label: metric.label,
            data: data.map(item => item[metric.key]),
            borderColor: color,
            backgroundColor: color + '20',
            borderWidth: 2,
            tension: 0.3,
            fill: metric.fill || false,
            yAxisID: metric.yAxisID || 'y'
        };
    });
    
    // Create chart
    const chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.map(item => item.date),
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    type: 'linear',
                    position: 'left',
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: metrics.find(m => m.yAxisID === 'y' || !m.yAxisID)?.title || ''
                    }
                },
                y1: {
                    type: 'linear',
                    position: 'right',
                    beginAtZero: true,
                    grid: {
                        drawOnChartArea: false
                    },
                    title: {
                        display: true,
                        text: metrics.find(m => m.yAxisID === 'y1')?.title || ''
                    },
                    display: metrics.some(m => m.yAxisID === 'y1')
                }
            },
            interaction: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                tooltip: {
                    enabled: true
                }
            }
        }
    });
    
    return chart;
}

/**
 * Creates a pie chart showing distribution of a metric
 * @param {string} canvasId - Canvas element ID
 * @param {Object} data - Data object with labels and values
 * @param {string} title - Chart title
 */
function createPieChart(canvasId, data, title = '') {
    if (!data || !data.labels || !data.values || !document.getElementById(canvasId)) {
        return;
    }
    
    const ctx = document.getElementById(canvasId).getContext('2d');
    
    // Generate colors based on number of segments
    const colors = data.labels.map((_, index) => {
        const hue = (index * 137) % 360;
        return `hsl(${hue}, 70%, 60%)`;
    });
    
    // Create chart
    const chart = new Chart(ctx, {
        type: 'pie',
        data: {
            labels: data.labels,
            datasets: [{
                data: data.values,
                backgroundColor: colors,
                borderColor: 'rgba(255, 255, 255, 0.5)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom'
                },
                title: {
                    display: !!title,
                    text: title
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            let label = context.label || '';
                            if (label) {
                                label += ': ';
                            }
                            
                            const value = context.parsed;
                            if (data.format === 'currency') {
                                label += value.toLocaleString() + ' ₽';
                            } else if (data.format === 'percentage') {
                                label += value.toFixed(1) + '%';
                            } else {
                                label += value.toLocaleString();
                            }
                            
                            return label;
                        }
                    }
                }
            }
        }
    });
    
    return chart;
}

/**
 * Truncate a string if it's longer than maxLength and add ellipsis
 * @param {string} str - String to truncate
 * @param {number} maxLength - Maximum length before truncation
 * @returns {string} Truncated string with ellipsis if needed
 */
function truncateString(str, maxLength) {
    if (!str || str.length <= maxLength) {
        return str;
    }
    
    return str.substring(0, maxLength - 3) + '...';
}
