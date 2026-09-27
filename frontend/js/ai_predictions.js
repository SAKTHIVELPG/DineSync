/**
 * DINESYNC AI Prediction Engine & Heatmap Controller
 */
const AIPredictionController = {
  forecastChart: null,
  peakData: null,

  async init() {
    await this.fetchPeakHoursAndHeatmap();
    await this.calculateWaitPrediction();
    this.setupListeners();
  },

  setupListeners() {
    const partyInput = document.getElementById('ai-sim-party-size');
    const secInput = document.getElementById('ai-sim-section');
    const hourInput = document.getElementById('ai-sim-hour');
    const dayInput = document.getElementById('ai-sim-day');

    [partyInput, secInput, hourInput, dayInput].forEach(el => {
      el?.addEventListener('change', () => this.calculateWaitPrediction());
      el?.addEventListener('input', () => this.calculateWaitPrediction());
    });
  },

  async calculateWaitPrediction() {
    const partySize = parseInt(document.getElementById('ai-sim-party-size')?.value || 4, 10);
    const section = document.getElementById('ai-sim-section')?.value || "Any";
    const hour = parseInt(document.getElementById('ai-sim-hour')?.value || new Date().getHours(), 10);
    const day = parseInt(document.getElementById('ai-sim-day')?.value || new Date().getDay(), 10);

    const hourDisplay = document.getElementById('ai-sim-hour-val');
    if (hourDisplay) {
      const d = new Date();
      d.setHours(hour, 0, 0);
      hourDisplay.innerText = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    try {
      const res = await fetch('/api/v1/predictions/wait-time', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          party_size: partySize,
          preferred_section: section,
          target_hour: hour,
          day_of_week: day
        })
      });

      if (!res.ok) return;
      const data = await res.json();

      // Render Result Card
      const elWait = document.getElementById('ai-pred-wait-mins');
      const elRange = document.getElementById('ai-pred-wait-range');
      const elConf = document.getElementById('ai-pred-confidence');
      const elRec = document.getElementById('ai-pred-recommendation');
      const elFactors = document.getElementById('ai-pred-factors-list');

      if (elWait) elWait.innerText = `${data.predicted_wait_minutes} min`;
      if (elRange) elRange.innerText = `Estimated Range: ${data.min_estimated_minutes} - ${data.max_estimated_minutes} mins`;
      if (elConf) elConf.innerText = `${Math.round(data.confidence_score * 100)}% AI Confidence`;
      if (elRec) elRec.innerText = data.recommendation;

      if (elFactors && data.factors) {
        elFactors.innerHTML = `
          <div class="flex justify-between py-1 border-b border-white/5">
            <span class="text-slate-400">Current Occupancy</span>
            <span class="font-semibold text-white">${data.factors.current_occupancy_pct || data.factors.occupancy_rate_pct || 0}%</span>
          </div>
          <div class="flex justify-between py-1 border-b border-white/5">
            <span class="text-slate-400">Parties in Queue</span>
            <span class="font-semibold text-white">${data.factors.active_queue_ahead || 0} parties</span>
          </div>
          <div class="flex justify-between py-1 border-b border-white/5">
            <span class="text-slate-400">Available Matching Tables</span>
            <span class="font-semibold text-emerald-400">${data.factors.matching_available_tables || 0} tables</span>
          </div>
          <div class="flex justify-between py-1">
            <span class="text-slate-400">Rush Classification</span>
            <span class="font-semibold text-cyan-400">${data.factors.rush_level}</span>
          </div>
        `;
      }

    } catch (e) {
      console.error('Error calculating AI prediction:', e);
    }
  },

  async fetchPeakHoursAndHeatmap() {
    try {
      const res = await fetch('/api/v1/predictions/peak-hours');
      if (!res.ok) return;
      this.peakData = await res.json();

      // Render Peak Header Stats
      const elCurrRate = document.getElementById('peak-current-rate');
      const elNextRush = document.getElementById('peak-next-rush');
      const elLunchWin = document.getElementById('peak-lunch-window');
      const elDinnerWin = document.getElementById('peak-dinner-window');

      if (elCurrRate) elCurrRate.innerText = `${this.peakData.current_occupancy_rate}% (${this.peakData.current_status})`;
      if (elNextRush) elNextRush.innerText = this.peakData.next_rush_hour || 'Normal flow';
      if (elLunchWin) elLunchWin.innerText = this.peakData.lunch_rush_window;
      if (elDinnerWin) elDinnerWin.innerText = this.peakData.dinner_rush_window;

      this.renderForecastChart(this.peakData.hourly_forecast);
      this.renderHeatmap(this.peakData.heatmap_matrix);

    } catch (e) {
      console.error('Error fetching peak hours:', e);
    }
  },

  renderForecastChart(forecastData) {
    const ctx = document.getElementById('ai-occupancy-forecast-chart');
    if (!ctx) return;

    const operationalHours = forecastData.filter(f => f.hour >= 11 && f.hour <= 23);
    const labels = operationalHours.map(f => f.hour_label);
    const rates = operationalHours.map(f => f.predicted_occupancy_percent);

    if (this.forecastChart) {
      this.forecastChart.destroy();
    }

    this.forecastChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [{
          label: 'Predicted Occupancy %',
          data: rates,
          borderColor: '#06B6D4',
          backgroundColor: 'rgba(6, 182, 212, 0.12)',
          fill: true,
          tension: 0.4,
          pointRadius: 4,
          pointHoverRadius: 7,
          pointBackgroundColor: '#06B6D4',
          pointBorderColor: '#fff',
          pointBorderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => ` Occupancy: ${ctx.parsed.y}%`
            }
          }
        },
        scales: {
          x: {
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: { color: '#94A3B8', font: { size: 11 } }
          },
          y: {
            min: 0,
            max: 100,
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: {
              color: '#94A3B8',
              callback: (val) => `${val}%`,
              font: { size: 11 }
            }
          }
        }
      }
    });
  },

  renderHeatmap(matrix) {
    const container = document.getElementById('ai-heatmap-grid');
    if (!container || !matrix) return;

    const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const hours = [11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23];

    let html = `
      <div class="grid grid-cols-[50px_repeat(13,_minmax(0,_1fr))] gap-1.5 text-center text-xs">
        <div class="font-bold text-slate-500 text-[10px] self-center">DAY</div>
        ${hours.map(h => {
          const lbl = h > 12 ? `${h-12}P` : (h === 12 ? '12P' : `${h}A`);
          return `<div class="font-bold text-slate-400 text-[10px] pb-1">${lbl}</div>`;
        }).join('')}
    `;

    days.forEach((dayName, dayIdx) => {
      html += `<div class="font-bold text-slate-400 text-xs py-2 self-center">${dayName}</div>`;
      hours.forEach(hour => {
        const val = matrix[dayIdx] ? matrix[dayIdx][hour] || 0 : 0;
        
        let bgStyle = 'background: rgba(16, 185, 129, 0.25); color: #A7F3D0;'; // Light green
        if (val >= 85) {
          bgStyle = 'background: rgba(244, 63, 94, 0.8); color: #FFF;'; // Heavy Red
        } else if (val >= 70) {
          bgStyle = 'background: rgba(245, 158, 11, 0.65); color: #FFF;'; // Amber Orange
        } else if (val >= 45) {
          bgStyle = 'background: rgba(59, 130, 246, 0.45); color: #BFDBFE;'; // Moderate Blue
        }

        html += `
          <div title="${dayName} at ${hour}:00 - ${val}% Occupancy" 
               style="${bgStyle}" 
               class="heatmap-cell py-2 rounded font-semibold cursor-pointer">
            ${Math.round(val)}%
          </div>
        `;
      });
    });

    html += `</div>`;
    container.innerHTML = html;
  }
};
