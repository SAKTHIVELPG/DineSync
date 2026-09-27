/**
 * DINESYNC Live Dashboard Controller
 */
const DashboardController = {
  recentActivity: [
    { text: "Table 2 occupied (ESP32 sensor trigger)", time: "Just now", type: "occupied" },
    { text: "Table 5 vacated and marked available", time: "4m ago", type: "available" },
    { text: "Party of 4 seated at Table 4", time: "8m ago", type: "seated" },
    { text: "IoT Node ESP32-NODE-09 heartbeat acknowledged", time: "12m ago", type: "sensor" },
  ],

  async init() {
    await this.fetchAndRenderStats();
    await this.fetchAndRenderMiniFloor();
    this.renderActivityStream();
    this.setupListeners();
  },

  setupListeners() {
    window.addEventListener('dinesync:table_update', (e) => {
      const table = e.detail.data;
      this.fetchAndRenderStats();
      this.fetchAndRenderMiniFloor();
      
      const actionText = table.status === 'OCCUPIED' 
        ? `Table ${table.table_number} occupied (${table.section})`
        : `Table ${table.table_number} status updated to ${table.status}`;
      
      this.addActivityEvent(actionText, table.status.toLowerCase());
    });

    window.addEventListener('dinesync:stats_refresh', () => {
      this.fetchAndRenderStats();
    });

    window.addEventListener('dinesync:sensor_telemetry', (e) => {
      const tel = e.detail.data;
      const act = tel.occupied ? `Sensor ${tel.sensor_id} detected customer seated` : `Sensor ${tel.sensor_id} detected vacant table`;
      this.addActivityEvent(act, 'sensor');
    });
  },

  async fetchAndRenderStats() {
    try {
      const res = await fetch('/api/v1/tables/summary/stats');
      if (!res.ok) return;
      const stats = await res.json();

      // Update Top KPIs
      const elTotal = document.getElementById('stat-total-tables');
      const elAvail = document.getElementById('stat-available-tables');
      const elOccup = document.getElementById('stat-occupied-tables');
      const elRate = document.getElementById('stat-occupancy-rate');
      const elRushTag = document.getElementById('stat-rush-tag');
      const elSeats = document.getElementById('stat-seated-capacity');

      if (elTotal) elTotal.innerText = stats.total_tables;
      if (elAvail) elAvail.innerText = stats.available_tables;
      if (elOccup) elOccup.innerText = stats.occupied_tables;
      if (elSeats) elSeats.innerText = `${stats.occupied_seats} / ${stats.total_seats}`;

      const homeAvail = document.getElementById('home-stat-avail');
      if (homeAvail) homeAvail.innerText = `${stats.available_tables} Open`;

      // Fetch live queue length and dynamic walk-in prediction for home screen
      try {
        const qRes = await fetch('/api/v1/queue');
        if (qRes.ok) {
          const qList = await qRes.json();
          const waitingCount = qList.filter(q => q.status === 'WAITING').length;
          const homeQueue = document.getElementById('home-stat-queue');
          if (homeQueue) homeQueue.innerText = `${waitingCount} ${waitingCount === 1 ? 'Party' : 'Parties'}`;
        }
        const predRes = await fetch('/api/v1/predictions/wait-time', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ party_size: 2, preferred_section: 'Any' })
        });
        if (predRes.ok) {
          const pred = await predRes.json();
          const homeWait = document.getElementById('home-stat-wait');
          if (homeWait) homeWait.innerText = pred.predicted_wait_minutes === 0 ? 'Immediate' : `~${pred.predicted_wait_minutes} mins`;
        }
        const sRes = await fetch('/api/v1/sensors');
        if (sRes.ok) {
          const sList = await sRes.json();
          const onlineCount = sList.filter(s => s.is_online).length;
          const homeSensors = document.getElementById('home-stat-sensors');
          if (homeSensors) homeSensors.innerText = `${onlineCount} Online`;
        }
      } catch (err) {
        // quiet fallback
      }

      const rate = stats.table_occupancy_rate || 0;
      if (elRate) elRate.innerText = `${rate}%`;

      // Update Radial Gauge
      const circle = document.getElementById('radial-gauge-circle');
      if (circle) {
        // Circumference is 2 * PI * 45 = 282.74
        const maxOffset = 283;
        const offset = maxOffset - (maxOffset * (rate / 100));
        circle.style.strokeDashoffset = offset;

        // Color threshold
        if (rate >= 80) {
          circle.style.stroke = '#F43F5E'; // Rose / Peak
        } else if (rate >= 50) {
          circle.style.stroke = '#F59E0B'; // Amber / Moderate
        } else {
          circle.style.stroke = '#10B981'; // Emerald / Light
        }
      }

      if (elRushTag) {
        elRushTag.innerText = stats.rush_status;
        if (rate >= 80) {
          elRushTag.className = "px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-500/20 text-rose-400 border border-rose-500/30";
        } else if (rate >= 50) {
          elRushTag.className = "px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/20 text-amber-400 border border-amber-500/30";
        } else {
          elRushTag.className = "px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30";
        }
      }
    } catch (e) {
      console.error('Error loading dashboard stats:', e);
    }
  },

  async fetchAndRenderMiniFloor() {
    try {
      const res = await fetch('/api/v1/tables');
      if (!res.ok) return;
      const tables = await res.json();

      const container = document.getElementById('mini-floor-grid');
      if (!container) return;

      container.innerHTML = tables.map(t => {
        let statusBg = 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400';
        let statusDot = 'bg-emerald-400';
        let statusText = 'Available';

        if (t.status === 'OCCUPIED') {
          statusBg = 'bg-rose-500/10 border-rose-500/30 text-rose-400';
          statusDot = 'bg-rose-400';
          statusText = `${t.elapsed_minutes || 1}m`;
        } else if (t.status === 'RESERVED') {
          statusBg = 'bg-amber-500/10 border-amber-500/30 text-amber-400';
          statusDot = 'bg-amber-400';
          statusText = 'Reserved';
        } else if (t.status === 'CLEANING') {
          statusBg = 'bg-purple-500/10 border-purple-500/30 text-purple-400';
          statusDot = 'bg-purple-400';
          statusText = 'Cleaning';
        }

        return `
          <div onclick="App.navigateTo('tables'); TablesController.openTableDrawer(${t.id});" 
               class="p-3 rounded-xl border ${statusBg} flex flex-col justify-between cursor-pointer hover:border-white/40 transition">
            <div class="flex items-center justify-between">
              <span class="font-bold text-sm text-white">T${t.table_number}</span>
              <span class="w-2 h-2 rounded-full ${statusDot}"></span>
            </div>
            <div class="mt-2 flex items-center justify-between text-xs opacity-80">
              <span>${t.capacity} seats</span>
              <span class="font-medium">${statusText}</span>
            </div>
          </div>
        `;
      }).join('');

    } catch (e) {
      console.error('Error rendering mini floor:', e);
    }
  },

  addActivityEvent(text, type) {
    this.recentActivity.unshift({
      text,
      time: "Just now",
      type: type || "sensor"
    });
    if (this.recentActivity.length > 8) this.recentActivity.pop();
    this.renderActivityStream();
  },

  renderActivityStream() {
    const container = document.getElementById('activity-stream-list');
    if (!container) return;

    container.innerHTML = this.recentActivity.map(act => {
      let iconColor = 'text-cyan-400 bg-cyan-400/10';
      let icon = `<i data-lucide="radio" class="w-4 h-4"></i>`;

      if (act.type === 'occupied') {
        iconColor = 'text-rose-400 bg-rose-400/10';
        icon = `<i data-lucide="user-check" class="w-4 h-4"></i>`;
      } else if (act.type === 'available') {
        iconColor = 'text-emerald-400 bg-emerald-400/10';
        icon = `<i data-lucide="check-circle" class="w-4 h-4"></i>`;
      } else if (act.type === 'seated') {
        iconColor = 'text-purple-400 bg-purple-400/10';
        icon = `<i data-lucide="utensils" class="w-4 h-4"></i>`;
      }

      return `
        <div class="flex items-start gap-3 p-2.5 rounded-lg hover:bg-slate-800/40 transition text-sm">
          <div class="p-2 rounded-lg ${iconColor} shrink-0">
            ${icon}
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-slate-200 text-xs font-medium truncate">${act.text}</p>
            <span class="text-[10px] text-slate-500">${act.time}</span>
          </div>
        </div>
      `;
    }).join('');

    if (window.lucide) lucide.createIcons();
  }
};
