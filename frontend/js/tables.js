/**
 * DINESYNC Tables & Interactive Floor Plan Controller
 */
const TablesController = {
  allTables: [],
  selectedSection: 'All',
  selectedCapacity: 0,
  selectedStatus: 'All',
  activeView: 'plan', // 'plan' or 'grid'
  currentTableDetail: null,

  async init() {
    await this.fetchTables();
    this.setupListeners();
  },

  setupListeners() {
    window.addEventListener('dinesync:table_update', (e) => {
      const updatedTable = e.detail.data;
      const idx = this.allTables.findIndex(t => t.id === updatedTable.id);
      if (idx !== -1) {
        this.allTables[idx] = updatedTable;
      } else {
        this.allTables.push(updatedTable);
      }
      this.render();

      if (this.currentTableDetail && this.currentTableDetail.id === updatedTable.id) {
        this.openTableDrawer(updatedTable.id, false);
      }
    });

    window.addEventListener('dinesync:sensor_telemetry', (e) => {
      const tel = e.detail.data;
      const tbl = this.allTables.find(t => t.sensor_id === tel.sensor_id || t.id === tel.table_id);
      if (tbl) {
        tbl.sensor_distance_cm = tel.distance_cm;
        tbl.sensor_battery = tel.battery_level;
        tbl.sensor_rssi = tel.signal_rssi;
        if (this.currentTableDetail && this.currentTableDetail.id === tbl.id) {
          this.openTableDrawer(tbl.id, false);
        }
      }
    });
  },

  async fetchTables() {
    try {
      const res = await fetch('/api/v1/tables');
      if (!res.ok) return;
      this.allTables = await res.json();
      this.render();
    } catch (e) {
      console.error('Error loading tables:', e);
    }
  },

  setFilter(type, value) {
    if (type === 'section') this.selectedSection = value;
    if (type === 'capacity') this.selectedCapacity = parseInt(value, 10);
    if (type === 'status') this.selectedStatus = value;
    this.render();
  },

  setView(view) {
    this.activeView = view;
    const planView = document.getElementById('tables-plan-view');
    const gridView = document.getElementById('tables-grid-view');
    const btnPlan = document.getElementById('btn-view-plan');
    const btnGrid = document.getElementById('btn-view-grid');

    if (view === 'plan') {
      planView?.classList.remove('hidden');
      gridView?.classList.add('hidden');
      btnPlan?.classList.add('bg-cyan-500/20', 'text-cyan-400', 'border-cyan-500/30');
      btnGrid?.classList.remove('bg-cyan-500/20', 'text-cyan-400', 'border-cyan-500/30');
    } else {
      planView?.classList.add('hidden');
      gridView?.classList.remove('hidden');
      btnGrid?.classList.add('bg-cyan-500/20', 'text-cyan-400', 'border-cyan-500/30');
      btnPlan?.classList.remove('bg-cyan-500/20', 'text-cyan-400', 'border-cyan-500/30');
    }
  },

  getFilteredTables() {
    return this.allTables.filter(t => {
      const matchSec = (this.selectedSection === 'All' || t.section === this.selectedSection);
      const matchCap = (this.selectedCapacity === 0 || t.capacity >= this.selectedCapacity);
      const matchStat = (this.selectedStatus === 'All' || t.status === this.selectedStatus);
      return matchSec && matchCap && matchStat;
    });
  },

  render() {
    this.renderFloorPlan();
    this.renderGrid();
  },

  renderFloorPlan() {
    const container = document.getElementById('floorplan-canvas');
    if (!container) return;

    const filtered = this.getFilteredTables();
    container.innerHTML = filtered.map(t => {
      const isOccupied = t.status === 'OCCUPIED';
      const shapeClass = t.shape === 'circle' ? 'table-shape-circle w-20 h-20' : (t.shape === 'booth' ? 'table-shape-booth w-28 h-24' : 'table-shape-rect w-24 h-20');
      
      let statusClass = 'status-available glow-emerald';
      if (t.status === 'OCCUPIED') statusClass = 'status-occupied glow-rose';
      if (t.status === 'RESERVED') statusClass = 'status-reserved glow-amber';
      if (t.status === 'CLEANING') statusClass = 'status-cleaning glow-purple';

      return `
        <div onclick="TablesController.openTableDrawer(${t.id})" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' ') TablesController.openTableDrawer(${t.id})"
             style="left: ${t.pos_x}px; top: ${t.pos_y}px;"
             class="floor-table ${shapeClass} ${statusClass} shadow-lg p-2 flex flex-col justify-between">
          
          <div class="flex items-center justify-between w-full px-1">
            <span class="font-extrabold text-sm">T${t.table_number}</span>
            <span class="text-[10px] font-bold opacity-90">${t.capacity}P</span>
          </div>

          <div class="text-center my-auto">
            ${isOccupied ? `<span class="text-xs font-semibold animate-pulse">${t.elapsed_minutes || 1}m</span>` : `<span class="text-[10px] uppercase font-bold tracking-wider">${t.status}</span>`}
          </div>

          <div class="flex items-center justify-between w-full px-1 text-[9px] opacity-75">
            <span>${t.sensor_id ? '📡' : ''}</span>
            <span>${t.section.split(' ')[0]}</span>
          </div>
          ${t.reservation_count ? `<span class="text-[9px] font-bold text-amber-200">BOOKED ${t.reservation_count}</span>` : ''}
        </div>
      `;
    }).join('');
  },

  renderGrid() {
    const container = document.getElementById('tables-grid-view') || document.getElementById('tables-card-grid');
    if (!container) return;

    const filtered = this.getFilteredTables();
    container.innerHTML = filtered.map(t => {
      const isOccupied = t.status === 'OCCUPIED';
      let badgeColor = 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30';
      if (t.status === 'OCCUPIED') badgeColor = 'bg-rose-500/20 text-rose-400 border-rose-500/30';
      if (t.status === 'RESERVED') badgeColor = 'bg-amber-500/20 text-amber-400 border-amber-500/30';
      if (t.status === 'CLEANING') badgeColor = 'bg-purple-500/20 text-purple-400 border-purple-500/30';

      return `
        <div class="glass-card p-5 flex flex-col justify-between">
          <div class="flex items-start justify-between">
            <div>
              <span class="text-xs text-slate-400 uppercase tracking-wider font-semibold">${t.section}</span>
              <h3 class="text-xl font-bold text-white mt-0.5">${t.name}</h3>
            </div>
            <span class="px-2.5 py-1 rounded-full text-xs font-semibold border ${badgeColor}">
              ${t.status}
            </span>
          </div>

          <div class="grid grid-cols-2 gap-3 my-4 py-3 border-y border-white/5 text-xs text-slate-300">
            <div>
              <span class="text-slate-500 block">Capacity</span>
              <span class="font-bold text-white text-sm">${t.capacity} Guests</span>
            </div>
            <div>
              <span class="text-slate-500 block">Occupied Duration</span>
              <span class="font-bold text-white text-sm">${isOccupied ? `${t.elapsed_minutes || 1} mins` : '—'}</span>
            </div>
            <div>
              <span class="text-slate-500 block">IoT Node</span>
              <span class="font-mono text-cyan-400 text-xs">${t.sensor_id || 'Unassigned'}</span>
            </div>
            <div>
              <span class="text-slate-500 block">Sensor Distance</span>
              <span class="font-bold text-white">${t.sensor_distance_cm ? `${t.sensor_distance_cm} cm` : '—'}</span>
            </div>
            <div class="col-span-2 pt-2 border-t border-white/5">
              <span class="text-slate-500 block">Upcoming reservations</span>
              <span class="font-bold ${t.reservation_count ? 'text-amber-300' : 'text-emerald-300'} text-sm">${t.reservation_count ? `${t.reservation_count} booking${t.reservation_count === 1 ? '' : 's'} · ${t.booked_guests} guests` : 'No upcoming bookings'}</span>
            </div>
          </div>

          <button onclick="TablesController.openTableDrawer(${t.id})" 
                  class="w-full py-2 px-3 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-white/10 transition flex items-center justify-center gap-1.5">
            <i data-lucide="info" class="w-3.5 h-3.5 text-cyan-400"></i> View Table Telemetry
          </button>
        </div>
      `;
    }).join('');

    if (window.lucide) lucide.createIcons();
  },

  async openTableDrawer(tableId, showToast = false) {
    try {
      const res = await fetch(`/api/v1/tables/${tableId}`);
      if (!res.ok) return;
      const table = await res.json();
      this.currentTableDetail = table;

      const drawer = document.getElementById('table-detail-drawer');
      if (!drawer) return;

      // Populate Drawer Details
      document.getElementById('drawer-table-title').innerText = `${table.name} (${table.section})`;
      document.getElementById('drawer-table-capacity').innerText = `${table.capacity} Guests (${table.shape} layout)`;
      document.getElementById('drawer-table-status').innerText = table.status;
      document.getElementById('drawer-table-elapsed').innerText = table.status === 'OCCUPIED' ? `${table.elapsed_minutes || 1} minutes` : 'Table is vacant';
      const bookingSummary = document.getElementById('drawer-booking-summary');
      if (bookingSummary) {
        const next = table.next_reservation_at ? new Date(table.next_reservation_at).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '';
        bookingSummary.innerHTML = table.reservation_count
          ? `<span class="text-slate-400 block">Reservation schedule</span><strong class="text-amber-300">${table.reservation_count} booking${table.reservation_count === 1 ? '' : 's'} · ${table.booked_guests} guests booked</strong><small class="text-slate-500 block mt-1">Next: ${next || 'scheduled'}</small>`
          : '<span class="text-slate-400 block">Reservation schedule</span><strong class="text-emerald-300">No upcoming bookings</strong>';
      }
      
      // Sensor Telemetry
      document.getElementById('drawer-sensor-id').innerText = table.sensor_id || 'Not Linked';
      document.getElementById('drawer-sensor-battery').innerText = `${table.sensor_battery || 95}%`;
      document.getElementById('drawer-sensor-battery-bar').style.width = `${table.sensor_battery || 95}%`;
      document.getElementById('drawer-sensor-rssi').innerText = `${table.sensor_rssi || -55} dBm (Good)`;
      document.getElementById('drawer-sensor-dist').innerText = `${table.sensor_distance_cm || 120.0} cm`;
      document.getElementById('drawer-sensor-ping').innerText = table.last_sensor_ping ? new Date(table.last_sensor_ping).toLocaleTimeString() : 'Active';

      // Status Badge Style
      const statusBadge = document.getElementById('drawer-status-badge');
      if (statusBadge) {
        statusBadge.innerText = table.status;
        if (table.status === 'OCCUPIED') statusBadge.className = 'px-3 py-1 rounded-full text-xs font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30';
        else if (table.status === 'AVAILABLE') statusBadge.className = 'px-3 py-1 rounded-full text-xs font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30';
        else if (table.status === 'RESERVED') statusBadge.className = 'px-3 py-1 rounded-full text-xs font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30';
        else statusBadge.className = 'px-3 py-1 rounded-full text-xs font-bold bg-purple-500/20 text-purple-400 border border-purple-500/30';
      }

      const reserveButton = document.getElementById('drawer-reserve-button');
      if (reserveButton) {
        reserveButton.classList.remove('hidden');
        reserveButton.innerHTML = `<i data-lucide="calendar-check" class="w-4 h-4" aria-hidden="true"></i> ${table.status === 'AVAILABLE' ? 'Reserve this table' : 'Check next available time'}`;
      }

      drawer.classList.remove('translate-x-full');
      if (window.lucide) lucide.createIcons();

    } catch (e) {
      console.error('Error opening table drawer:', e);
    }
  },

  closeDrawer() {
    const drawer = document.getElementById('table-detail-drawer');
    if (drawer) drawer.classList.add('translate-x-full');
    this.currentTableDetail = null;
  },

  async updateCurrentTableStatus(newStatus) {
    if (!this.currentTableDetail) return;
    try {
      const res = await fetch(`/api/v1/tables/${this.currentTableDetail.id}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus })
      });
      if (res.ok) {
        App.showToast(`Table ${this.currentTableDetail.table_number} updated to ${newStatus}`, 'success');
        this.openTableDrawer(this.currentTableDetail.id);
      }
    } catch (e) {
      App.showToast('Failed to update table status', 'error');
    }
  },

  async simulateSensorOnCurrentTable(eventType) {
    if (!this.currentTableDetail) return;
    try {
      const res = await fetch(`/api/v1/sensors/simulate?table_number=${this.currentTableDetail.table_number}&event_type=${eventType}`, {
        method: 'POST'
      });
      if (res.ok) {
        App.showToast(`Hardware trigger sent: ${eventType} on T${this.currentTableDetail.table_number}`, 'success');
      }
    } catch (e) {
      App.showToast('Simulation trigger failed', 'error');
    }
  }
};
