/**
 * DINESYNC Admin Console Controller (Sensors, Table Mgmt, Queue Host Stand, Auth)
 */
const AdminController = {
  isAuthenticated: false,
  adminToken: null,
  sensorsList: [],
  queueList: [],

  async init() {
    this.checkSession();
    if (this.isAuthenticated) {
      await this.refreshAll();
    }
    this.setupListeners();
  },

  checkSession() {
    const token = localStorage.getItem('dinesync_admin_token');
    if (token) {
      this.isAuthenticated = true;
      this.adminToken = token;
      this.renderAuthState();
    }
  },

  setupListeners() {
    window.addEventListener('dinesync:table_update', () => {
      if (this.isAuthenticated) {
        this.fetchSensors();
        this.fetchQueue();
      }
    });

    window.addEventListener('dinesync:sensor_telemetry', () => {
      if (this.isAuthenticated) {
        this.fetchSensors();
      }
    });

    window.addEventListener('dinesync:queue_update', () => {
      if (this.isAuthenticated) {
        this.fetchQueue();
      }
    });
  },

  async login(pin) {
    try {
      const res = await fetch('/api/v1/admin/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pin })
      });

      if (!res.ok) {
        App.showToast('Invalid Admin PIN. (Default demo PIN is 1234)', 'error');
        return false;
      }

      const data = await res.json();
      this.isAuthenticated = true;
      this.adminToken = data.token;
      localStorage.setItem('dinesync_admin_token', data.token);

      App.setRole('admin');
      App.showToast('Staff Manager access granted!', 'success');
      this.renderAuthState();
      await this.refreshAll();
      App.navigateTo('admin');
      return true;
    } catch (e) {
      App.showToast('Admin login error', 'error');
      return false;
    }
  },

  logout() {
    this.isAuthenticated = false;
    this.adminToken = null;
    localStorage.removeItem('dinesync_admin_token');
    this.renderAuthState();
    App.setRole('customer');
    App.navigateTo('home');
    App.showToast('Staff logged out. Returned to Customer Portal.', 'info');
  },

  renderAuthState() {
    const authLocked = document.getElementById('admin-auth-locked');
    const authUnlocked = document.getElementById('admin-auth-unlocked');

    if (this.isAuthenticated) {
      authLocked?.classList.add('hidden');
      authUnlocked?.classList.remove('hidden');
    } else {
      authLocked?.classList.add('hidden'); // login view handles login
      authUnlocked?.classList.add('hidden');
    }
  },

  async refreshAll() {
    await this.fetchSensors();
    await this.fetchQueue();
    await this.populateTableSelects();
  },

  async fetchSensors() {
    try {
      const res = await fetch('/api/v1/sensors');
      if (!res.ok) return;
      this.sensorsList = await res.json();
      this.renderSensorsTable();
    } catch (e) {
      console.error('Error fetching sensors:', e);
    }
  },

  renderSensorsTable() {
    const container = document.getElementById('admin-sensors-table-body');
    if (!container) return;

    container.innerHTML = this.sensorsList.map(s => {
      let stateBadge = 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30';
      if (s.state === 'OCCUPIED') stateBadge = 'bg-rose-500/20 text-rose-400 border-rose-500/30';
      if (s.state === 'WARNING') stateBadge = 'bg-amber-500/20 text-amber-400 border-amber-500/30';
      if (s.state === 'OFFLINE') stateBadge = 'bg-slate-700 text-slate-400 border-white/10';

      const batteryColor = s.battery_level < 20 ? 'text-rose-400' : (s.battery_level < 50 ? 'text-amber-400' : 'text-emerald-400');

      return `
        <tr class="border-b border-white/5 hover:bg-slate-800/30 transition text-xs">
          <td class="py-3 px-4 font-mono font-bold text-cyan-400">${s.sensor_id}</td>
          <td class="py-3 px-4 text-white font-medium">${s.table_name || 'Unassigned'}</td>
          <td class="py-3 px-4">
            <span class="px-2 py-0.5 rounded-full text-[10px] font-bold border ${stateBadge}">
              ${s.state}
            </span>
          </td>
          <td class="py-3 px-4 ${batteryColor} font-bold">${s.battery_level}%</td>
          <td class="py-3 px-4 font-mono text-slate-400">${s.signal_rssi} dBm</td>
          <td class="py-3 px-4 text-slate-300 font-bold">${s.distance_cm} cm</td>
          <td class="py-3 px-4 text-slate-500">${new Date(s.last_ping).toLocaleTimeString()}</td>
          <td class="py-3 px-4">
            <div class="flex items-center gap-1.5">
              <button onclick="AdminController.triggerSimulate('${s.table_id || 1}', 'OCCUPY')" 
                      class="px-2 py-1 bg-rose-500/20 hover:bg-rose-500/30 text-rose-400 rounded text-[10px] font-medium border border-rose-500/30 transition">
                Sit
              </button>
              <button onclick="AdminController.triggerSimulate('${s.table_id || 1}', 'VACATE')" 
                      class="px-2 py-1 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 rounded text-[10px] font-medium border border-emerald-500/30 transition">
                Vacate
              </button>
            </div>
          </td>
        </tr>
      `;
    }).join('');
  },

  async fetchQueue() {
    try {
      const res = await fetch('/api/v1/queue');
      if (!res.ok) return;
      this.queueList = await res.json();
      this.renderHostStandQueue();
    } catch (e) {
      console.error('Error fetching host queue:', e);
    }
  },

  renderHostStandQueue() {
    const container = document.getElementById('admin-queue-table-body');
    if (!container) return;

    if (this.queueList.length === 0) {
      container.innerHTML = `
        <tr><td colspan="7" class="text-center py-6 text-slate-500 text-xs">Waitlist is currently empty.</td></tr>
      `;
      return;
    }

    container.innerHTML = this.queueList.map(q => {
      const isCalled = q.status === 'CALLED';

      return `
        <tr class="border-b border-white/5 hover:bg-slate-800/30 transition text-xs">
          <td class="py-3 px-4 font-mono font-bold text-white">${q.ticket_code}</td>
          <td class="py-3 px-4 font-medium text-slate-200">
            <div>${q.customer_name}</div>
            <div class="text-[10px] text-slate-500 font-mono">${q.phone}</div>
          </td>
          <td class="py-3 px-4 text-cyan-400 font-bold">${q.party_size} Guests</td>
          <td class="py-3 px-4 text-slate-400">${q.preferred_section}</td>
          <td class="py-3 px-4">
            <span class="px-2 py-0.5 rounded-full text-[10px] font-bold ${isCalled ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 animate-pulse' : 'bg-slate-800 text-slate-300'}">
              ${q.status}
            </span>
          </td>
          <td class="py-3 px-4 text-slate-400 font-bold">~${q.estimated_wait_minutes}m</td>
          <td class="py-3 px-4">
            <div class="flex items-center gap-1.5">
              ${!isCalled ? `
                <button onclick="AdminController.executeQueueAction(${q.id}, 'call')" 
                        class="px-2.5 py-1 bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-400 rounded text-xs font-semibold border border-cyan-500/30 transition">
                  🔔 Call
                </button>
              ` : `
                <button onclick="AdminController.executeQueueAction(${q.id}, 'seat')" 
                        class="px-2.5 py-1 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 rounded text-xs font-semibold border border-emerald-500/40 transition">
                  🪑 Seat Party
                </button>
              `}
              <button onclick="AdminController.executeQueueAction(${q.id}, 'no_show')" 
                      class="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-400 rounded text-xs transition" title="No Show">
                ✕
              </button>
            </div>
          </td>
        </tr>
      `;
    }).join('');
  },

  async executeQueueAction(queueId, action, tableId = null) {
    try {
      const res = await fetch(`/api/v1/queue/${queueId}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, table_id: tableId })
      });

      if (!res.ok) {
        const err = await res.json();
        App.showToast(err.detail || 'Action failed', 'error');
        return;
      }

      App.showToast(`Party marked as ${action.toUpperCase()}`, 'success');
      await this.fetchQueue();
    } catch (e) {
      App.showToast('Failed to execute queue action', 'error');
    }
  },

  async triggerSimulate(tableNumber, eventType) {
    try {
      const res = await fetch(`/api/v1/sensors/simulate?table_number=${tableNumber}&event_type=${eventType}`, {
        method: 'POST'
      });
      if (res.ok) {
        App.showToast(`Simulated: ${eventType} on Table ${tableNumber}`, 'success');
      }
    } catch (e) {
      App.showToast('Simulation error', 'error');
    }
  },

  async populateTableSelects() {
    try {
      const res = await fetch('/api/v1/tables');
      if (!res.ok) return;
      const tables = await res.json();

      const simSelect = document.getElementById('sim-target-table-select');
      if (simSelect) {
        simSelect.innerHTML = tables.map(t => `<option value="${t.table_number}">Table ${t.table_number} (${t.name} - ${t.capacity}p)</option>`).join('');
      }
    } catch (e) {
      // ignore
    }
  },

  async triggerSelectedSim(eventType) {
    const tableNum = document.getElementById('sim-target-table-select')?.value || 1;
    await this.triggerSimulate(tableNum, eventType);
  },

  async resetDemoDatabase() {
    if (!confirm('Re-seed DINESYNC database back to initial fresh state?')) return;
    try {
      const res = await fetch('/api/v1/admin/reset-demo', { method: 'POST' });
      if (res.ok) {
        App.showToast('Demo database successfully re-seeded!', 'success');
        await this.refreshAll();
        if (DashboardController) await DashboardController.init();
        if (TablesController) await TablesController.init();
      }
    } catch (e) {
      App.showToast('Failed to reset demo database', 'error');
    }
  },

  async retrainAI() {
    try {
      App.showToast('Initiating AI regression model training on historical logs...', 'info');
      const res = await fetch('/api/v1/admin/train-ai', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        App.showToast(`AI Models Retrained! Samples: ${data.training_samples}, R² Score: ${data.r2_score ?? 'N/A'}`, 'success');
        if (AIPredictionController) await AIPredictionController.init();
      } else {
        App.showToast('AI retraining failed', 'error');
      }
    } catch (e) {
      App.showToast('Network error during AI training', 'error');
    }
  },

  async deleteTable(tableId) {
    if (!confirm(`Are you sure you want to remove Table #${tableId} from the floor?`)) return;
    try {
      const res = await fetch(`/api/v1/admin/tables/${tableId}`, { method: 'DELETE' });
      if (res.ok) {
        App.showToast(`Table ${tableId} removed`, 'success');
        await this.refreshAll();
        if (TablesController) await TablesController.fetchTables();
      }
    } catch (e) {
      App.showToast('Failed to delete table', 'error');
    }
  },

  async createTable(event) {
    event.preventDefault();
    const tableNum = parseInt(document.getElementById('admin-new-table-num')?.value, 10);
    const name = document.getElementById('admin-new-table-name')?.value || `Table ${tableNum}`;
    const capacity = parseInt(document.getElementById('admin-new-table-capacity')?.value, 10);
    const section = document.getElementById('admin-new-table-section')?.value;
    const shape = document.getElementById('admin-new-table-shape')?.value || 'rect';
    const sensorId = document.getElementById('admin-new-table-sensor')?.value.trim() || `ESP32-NODE-${tableNum < 10 ? '0' : ''}${tableNum}`;

    if (!tableNum || !capacity || !section) {
      App.showToast('Please fill all required table fields', 'warning');
      return;
    }

    try {
      const res = await fetch('/api/v1/admin/tables', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          table_number: tableNum,
          name: name,
          capacity: capacity,
          section: section,
          shape: shape,
          sensor_id: sensorId,
          pos_x: 230,
          pos_y: 200
        })
      });

      if (res.ok) {
        App.showToast(`Table ${tableNum} successfully created and linked to ${sensorId}!`, 'success');
        document.getElementById('admin-add-table-modal')?.classList.add('hidden');
        document.getElementById('admin-add-table-form')?.reset();
        await this.refreshAll();
        if (TablesController) await TablesController.fetchTables();
      } else {
        const err = await res.json();
        App.showToast(err.detail || 'Failed to create table', 'error');
      }
    } catch (e) {
      App.showToast('Network error while creating table', 'error');
    }
  },

  copyFirmwareCode() {
    const code = document.getElementById('firmware-code-block')?.innerText;
    if (code) {
      navigator.clipboard.writeText(code);
      App.showToast('ESP32 Arduino C++ firmware code copied to clipboard!', 'success');
    }
  }
};
