/**
 * DINESYNC Analytics & Historical Reporting Controller
 */
const AnalyticsController = {
  charts: {},

  async init() {
    await this.fetchAndRenderAnalytics();
  },

  async fetchAndRenderAnalytics() {
    try {
      const res = await fetch('/api/v1/analytics/summary');
      if (!res.ok) return;
      const data = await res.json();

      // Render Metrics
      document.getElementById('an-total-seated').innerText = data.total_seated_today;
      document.getElementById('an-avg-duration').innerText = `${data.avg_dining_duration_mins}m`;
      document.getElementById('an-avg-wait').innerText = `${data.avg_queue_wait_mins}m`;
      document.getElementById('an-peak-occupancy').innerText = `${data.peak_occupancy_today}%`;

      this.renderOccupancyHistoryChart(data.hourly_occupancy_history);
      this.renderWaitTimeAccuracyChart(data.wait_time_vs_predicted);
      this.renderSectionPopularityChart(data.section_popularity);
      this.renderPartySizeChart(data.party_size_breakdown);

    } catch (e) {
      console.error('Error loading analytics:', e);
    }
  },

  renderOccupancyHistoryChart(historyData) {
    const ctx = document.getElementById('an-occupancy-chart');
    if (!ctx || !historyData) return;

    if (this.charts.occ) this.charts.occ.destroy();

    const labels = historyData.map(h => h.hour_label);
    const occRates = historyData.map(h => h.occupancy_rate);
    const queueDepths = historyData.map(h => h.queue_depth);

    this.charts.occ = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Occupancy Rate (%)',
            data: occRates,
            borderColor: '#10B981',
            backgroundColor: 'rgba(16, 185, 129, 0.15)',
            fill: true,
            tension: 0.3,
            yAxisID: 'y'
          },
          {
            label: 'Queue Length (Parties)',
            data: queueDepths,
            borderColor: '#F59E0B',
            borderDash: [5, 5],
            tension: 0.3,
            pointRadius: 3,
            yAxisID: 'y1'
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: '#CBD5E1' } }
        },
        scales: {
          x: { grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#94A3B8' } },
          y: {
            min: 0,
            max: 100,
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: { color: '#94A3B8', callback: (v) => `${v}%` }
          },
          y1: {
            position: 'right',
            grid: { display: false },
            ticks: { color: '#F59E0B' }
          }
        }
      }
    });
  },

  renderWaitTimeAccuracyChart(waitData) {
    const ctx = document.getElementById('an-wait-accuracy-chart');
    if (!ctx || !waitData) return;

    if (this.charts.wait) this.charts.wait.destroy();

    const labels = waitData.map(w => w.session_id);
    const actuals = waitData.map(w => w.actual_wait_minutes);
    const predicted = waitData.map(w => w.predicted_wait_minutes);

    this.charts.wait = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Actual Wait (mins)',
            data: actuals,
            backgroundColor: 'rgba(59, 130, 246, 0.8)',
            borderRadius: 6
          },
          {
            label: 'AI Predicted Wait (mins)',
            data: predicted,
            backgroundColor: 'rgba(6, 182, 212, 0.5)',
            borderRadius: 6
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: '#CBD5E1' } }
        },
        scales: {
          x: { grid: { display: false }, ticks: { color: '#94A3B8', font: { size: 10 } } },
          y: { grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#94A3B8' } }
        }
      }
    });
  },

  renderSectionPopularityChart(secData) {
    const ctx = document.getElementById('an-section-chart');
    if (!ctx || !secData) return;

    if (this.charts.sec) this.charts.sec.destroy();

    const labels = Object.keys(secData);
    const values = Object.values(secData);

    this.charts.sec = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: labels,
        datasets: [{
          data: values,
          backgroundColor: ['#3B82F6', '#10B981', '#06B6D4', '#F59E0B', '#8B5CF6'],
          borderWidth: 0
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom', labels: { color: '#CBD5E1', boxWidth: 12 } }
        },
        cutout: '68%'
      }
    });
  },

  renderPartySizeChart(partyData) {
    const ctx = document.getElementById('an-party-chart');
    if (!ctx || !partyData) return;

    if (this.charts.party) this.charts.party.destroy();

    const labels = Object.keys(partyData);
    const values = Object.values(partyData);

    this.charts.party = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{
          label: 'Dining Parties',
          data: values,
          backgroundColor: '#8B5CF6',
          borderRadius: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false }, ticks: { color: '#94A3B8' } },
          y: { grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#94A3B8' } }
        }
      }
    });
  },

  exportCSV() {
    window.location.href = '/api/v1/analytics/export';
  }
};
