// Chart instances
let viewsChart = null;
let favouritesChart = null;
let watchersChart = null;

// State
let allDeviations = [];
let currentPeriod = 7;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initializePeriodButtons();
    loadDeviations();
    updateCharts();
});

// Initialize period button handlers
function initializePeriodButtons() {
    const periodButtons = document.querySelectorAll('.period-btn');
    periodButtons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            // Remove active class from all buttons
            periodButtons.forEach(b => b.classList.remove('active'));
            // Add active class to clicked button
            e.target.classList.add('active');
            // Update current period
            currentPeriod = parseInt(e.target.dataset.period);
            // Refresh charts
            updateCharts();
        });
    });
}

// Load deviations list for filtering
async function loadDeviations() {
    try {
        const response = await fetch('/api/charts/deviations');
        const result = await response.json();

        if (!result.success) {
            console.error('Failed to load deviations:', result.error);
            return;
        }

        allDeviations = result.data;
        renderDeviationList();
    } catch (error) {
        console.error('Error loading deviations:', error);
    }
}

// Render deviation checkboxes
function renderDeviationList() {
    const container = document.getElementById('deviation-list');

    if (allDeviations.length === 0) {
        container.innerHTML = '<div class="text-center text-muted py-2"><small>No deviations found</small></div>';
        return;
    }

    container.innerHTML = allDeviations.map(dev => `
        <div class="form-check deviation-checkbox">
            <input class="form-check-input deviation-check" type="checkbox"
                   value="${dev.deviationid}" id="dev-${dev.deviationid}">
            <label class="form-check-label small" for="dev-${dev.deviationid}">
                ${dev.title}
            </label>
        </div>
    `).join('');

    // Add change listeners to checkboxes
    document.querySelectorAll('.deviation-check').forEach(checkbox => {
        checkbox.addEventListener('change', updateCharts);
    });
}

// Get selected deviation IDs
function getSelectedDeviationIds() {
    const checkboxes = document.querySelectorAll('.deviation-check:checked');
    return Array.from(checkboxes).map(cb => cb.value);
}

// Select all deviations
function selectAllDeviations() {
    document.querySelectorAll('.deviation-check').forEach(cb => cb.checked = true);
    updateCharts();
}

// Deselect all deviations
function deselectAllDeviations() {
    document.querySelectorAll('.deviation-check').forEach(cb => cb.checked = false);
    updateCharts();
}

// Update all charts
async function updateCharts() {
    const selectedIds = getSelectedDeviationIds();
    const username = document.getElementById('username-input').value.trim();

    await Promise.all([
        updateDeviationCharts(selectedIds),
        updateWatchersChart(username)
    ]);
}

// Update deviation stats charts (views & favourites)
async function updateDeviationCharts(deviationIds) {
    try {
        const params = new URLSearchParams({
            period: currentPeriod.toString()
        });

        if (deviationIds.length > 0) {
            params.append('deviation_ids', deviationIds.join(','));
        }

        const response = await fetch(`/api/charts/aggregated?${params}`);
        const result = await response.json();

        if (!result.success) {
            console.error('Failed to load aggregated data:', result.error);
            return;
        }

        const data = result.data;

        // Update views chart
        updateChart('viewsChart', data.labels, [
            {
                label: 'Views',
                data: data.datasets.views,
                borderColor: 'rgb(75, 192, 192)',
                backgroundColor: 'rgba(75, 192, 192, 0.1)',
                tension: 0.4
            }
        ], 'views');

        // Update favourites chart
        updateChart('favouritesChart', data.labels, [
            {
                label: 'Favourites',
                data: data.datasets.favourites,
                borderColor: 'rgb(255, 99, 132)',
                backgroundColor: 'rgba(255, 99, 132, 0.1)',
                tension: 0.4
            }
        ], 'favourites');

    } catch (error) {
        console.error('Error updating deviation charts:', error);
    }
}

// Update watchers chart
async function updateWatchersChart(username) {
    if (!username) {
        console.warn('No username provided for watchers chart');
        return;
    }

    try {
        const params = new URLSearchParams({
            username: username,
            period: currentPeriod.toString()
        });

        const response = await fetch(`/api/charts/user-watchers?${params}`);
        const result = await response.json();

        if (!result.success) {
            console.error('Failed to load watchers data:', result.error);
            return;
        }

        const data = result.data;

        // Update watchers chart
        updateChart('watchersChart', data.labels, [
            {
                label: 'Watchers',
                data: data.datasets.watchers,
                borderColor: 'rgb(54, 162, 235)',
                backgroundColor: 'rgba(54, 162, 235, 0.1)',
                tension: 0.4
            },
            {
                label: 'Friends',
                data: data.datasets.friends,
                borderColor: 'rgb(153, 102, 255)',
                backgroundColor: 'rgba(153, 102, 255, 0.1)',
                tension: 0.4
            }
        ], 'watchers');

    } catch (error) {
        console.error('Error updating watchers chart:', error);
    }
}

// Generic chart update function
function updateChart(canvasId, labels, datasets, chartType) {
    const ctx = document.getElementById(canvasId).getContext('2d');

    // Destroy existing chart if it exists
    if (chartType === 'views' && viewsChart) {
        viewsChart.destroy();
    } else if (chartType === 'favourites' && favouritesChart) {
        favouritesChart.destroy();
    } else if (chartType === 'watchers' && watchersChart) {
        watchersChart.destroy();
    }

    // Create new chart
    const chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                },
                tooltip: {
                    mode: 'index',
                    intersect: false
                }
            },
            scales: {
                x: {
                    display: true,
                    title: {
                        display: true,
                        text: 'Date'
                    }
                },
                y: {
                    display: true,
                    title: {
                        display: true,
                        text: 'Count'
                    },
                    beginAtZero: true
                }
            },
            interaction: {
                mode: 'nearest',
                axis: 'x',
                intersect: false
            }
        }
    });

    // Store chart instance
    if (chartType === 'views') {
        viewsChart = chart;
    } else if (chartType === 'favourites') {
        favouritesChart = chart;
    } else if (chartType === 'watchers') {
        watchersChart = chart;
    }
}
