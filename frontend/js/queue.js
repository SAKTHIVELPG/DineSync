/**
 * DINESYNC Join Queue & Live Queue Tracker Controller
 */
const QueueController = {
  activeTicket: null,
  activeQueueList: [],

  async init() {
    this.restoreStoredTicket();
    await this.fetchPublicQueue();
    this.setupListeners();
    this.updatePreviewWaitTime();
  },

  setupListeners() {
    window.addEventListener('dinesync:queue_update', (e) => {
      this.fetchPublicQueue();
      const { data, event } = e.detail;

      // If update belongs to our active ticket
      if (this.activeTicket && data && data.ticket_code === this.activeTicket.ticket_code) {
        this.activeTicket = data;
        this.renderActiveTicket();

        if (event === 'CALLED' || data.status === 'CALLED') {
          App.playAlertChime();
          App.showToast(`🎉 YOUR TABLE IS READY! Ticket ${data.ticket_code}`, 'success');
        } else if (event === 'SEATED' || data.status === 'SEATED') {
          App.showToast(`Welcome! You are seated at Table ${data.assigned_table_number || ''}`, 'success');
        }
      } else if (this.activeTicket && this.activeTicket.status === 'WAITING') {
        // Refresh position countdown in real time
        this.fetchTicketStatus(this.activeTicket.ticket_code);
      }
    });
  },

  restoreStoredTicket() {
    const savedCode = localStorage.getItem('dinesync_active_ticket');
    if (savedCode) {
      this.fetchTicketStatus(savedCode);
    }
  },

  async fetchPublicQueue() {
    try {
      const res = await fetch('/api/v1/queue');
      if (!res.ok) return;
      this.activeQueueList = await res.json();
      this.renderPublicQueueList();
    } catch (e) {
      console.error('Error fetching queue:', e);
    }
  },

  async updatePreviewWaitTime() {
    const partySizeEl = document.getElementById('queue-party-size');
    const sectionEl = document.getElementById('queue-preferred-section');
    const previewEl = document.getElementById('queue-preview-wait-text');
    if (!partySizeEl || !previewEl) return;

    const partySize = parseInt(partySizeEl.value, 10) || 2;
    const section = sectionEl ? sectionEl.value : "Any";

    try {
      const res = await fetch('/api/v1/predictions/wait-time', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ party_size: partySize, preferred_section: section })
      });
      if (res.ok) {
        const pred = await res.json();
        previewEl.innerText = pred.predicted_wait_minutes === 0 
          ? '0 mins (Immediate Seating Available)' 
          : `~${pred.predicted_wait_minutes} mins (${pred.min_estimated_minutes}-${pred.max_estimated_minutes}m range)`;
      }
    } catch (e) {
      // ignore
    }
  },

  async handleJoinQueue(e) {
    e.preventDefault();
    const name = document.getElementById('queue-customer-name').value.trim();
    const phone = document.getElementById('queue-phone').value.trim();
    const email = document.getElementById('queue-email').value.trim();
    const partySize = parseInt(document.getElementById('queue-party-size').value, 10);
    const section = document.getElementById('queue-preferred-section').value;
    const notes = document.getElementById('queue-notes').value.trim();

    if (!name || !phone) {
      App.showToast('Please enter your name and phone number', 'warning');
      return;
    }

    try {
      const res = await fetch('/api/v1/queue/join', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          customer_name: name,
          phone: phone,
          email: email || null,
          party_size: partySize,
          preferred_section: section,
          special_notes: notes
        })
      });

      if (!res.ok) {
        const err = await res.json();
        App.showToast(err.detail || 'Failed to join waitlist', 'error');
        return;
      }

      const ticket = await res.json();
      this.activeTicket = ticket;
      localStorage.setItem('dinesync_active_ticket', ticket.ticket_code);
      
      App.showToast(`Joined waitlist! Ticket: ${ticket.ticket_code}`, 'success');
      this.renderActiveTicket();
      await this.fetchPublicQueue();

      // Reset form
      document.getElementById('queue-registration-form')?.reset();

    } catch (err) {
      App.showToast('Network error while joining queue', 'error');
    }
  },

  async handleLookupTicket(query) {
    const clean = (query || '').trim();
    if (!clean) {
      App.showToast('Please enter your phone number or ticket code', 'warning');
      return;
    }

    try {
      const isTicket = clean.toUpperCase().startsWith('Q-');
      const param = isTicket ? `ticket_code=${encodeURIComponent(clean.toUpperCase())}` : `phone=${encodeURIComponent(clean)}`;
      
      const res = await fetch(`/api/v1/queue/lookup?${param}`);
      if (!res.ok) {
        App.showToast('No active waitlist ticket found for this phone or ticket code', 'error');
        return;
      }

      const ticket = await res.json();
      this.activeTicket = ticket;
      localStorage.setItem('dinesync_active_ticket', ticket.ticket_code);
      
      App.showToast(`Found Ticket ${ticket.ticket_code} for ${ticket.customer_name}!`, 'success');
      this.renderActiveTicket();
      App.navigateTo('queue');

    } catch (e) {
      App.showToast('Error looking up queue ticket', 'error');
    }
  },

  async fetchTicketStatus(ticketCode) {
    try {
      const res = await fetch(`/api/v1/queue/ticket/${ticketCode}`);
      if (res.ok) {
        this.activeTicket = await res.json();
        this.renderActiveTicket();
      } else {
        localStorage.removeItem('dinesync_active_ticket');
        this.activeTicket = null;
        this.renderActiveTicket();
      }
    } catch (e) {
      console.error('Error fetching ticket status:', e);
    }
  },

  renderActiveTicket() {
    const card = document.getElementById('active-ticket-card');
    const emptyState = document.getElementById('no-ticket-placeholder');

    if (!this.activeTicket || this.activeTicket.status === 'CANCELLED') {
      card?.classList.add('hidden');
      emptyState?.classList.remove('hidden');
      return;
    }

    card?.classList.remove('hidden');
    emptyState?.classList.add('hidden');

    const t = this.activeTicket;
    document.getElementById('ticket-code-display').innerText = t.ticket_code;
    document.getElementById('ticket-guest-name').innerText = `${t.customer_name} (Party of ${t.party_size})`;
    document.getElementById('ticket-section-pref').innerText = `Section: ${t.preferred_section}`;
    document.getElementById('ticket-position-display').innerText = t.position > 0 ? `#${t.position}` : '—';
    document.getElementById('ticket-est-wait').innerText = `${t.estimated_wait_minutes} mins`;

    const statusBanner = document.getElementById('ticket-status-banner');
    const statusText = document.getElementById('ticket-status-text');

    if (t.status === 'CALLED') {
      statusBanner.className = 'p-4 rounded-xl bg-gradient-to-r from-emerald-500/30 to-cyan-500/30 border border-emerald-400 text-emerald-300 animate-pulse';
      statusText.innerHTML = `🔔 <strong>YOUR TABLE IS READY!</strong> Please proceed to the Host Stand.`;
    } else if (t.status === 'SEATED') {
      statusBanner.className = 'p-4 rounded-xl bg-purple-500/20 border border-purple-500/30 text-purple-300';
      statusText.innerHTML = `🍽️ <strong>Seated at Table ${t.assigned_table_number || ''}!</strong> Enjoy your meal.`;
    } else {
      statusBanner.className = 'p-4 rounded-xl bg-slate-800/80 border border-white/10 text-slate-300';
      statusText.innerHTML = `⏳ In Line: <strong>${t.position} parties ahead</strong>. We will notify you when your table is prepared.`;
    }

    if (window.lucide) lucide.createIcons();
  },

  async cancelActiveTicket() {
    if (!this.activeTicket) return;
    if (!confirm('Are you sure you want to leave the waitlist queue?')) return;

    try {
      const res = await fetch(`/api/v1/queue/${this.activeTicket.id}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'cancel' })
      });

      if (res.ok) {
        localStorage.removeItem('dinesync_active_ticket');
        this.activeTicket = null;
        this.renderActiveTicket();
        App.showToast('You have left the waitlist queue', 'info');
        await this.fetchPublicQueue();
      }
    } catch (e) {
      App.showToast('Failed to cancel ticket', 'error');
    }
  },

  renderPublicQueueList() {
    const container = document.getElementById('public-queue-list');
    if (!container) return;

    if (this.activeQueueList.length === 0) {
      container.innerHTML = `
        <div class="text-center py-8 text-slate-500 text-sm">
          No parties currently waiting. Walk-in seating available!
        </div>
      `;
      return;
    }

    container.innerHTML = this.activeQueueList.map(item => {
      const isCalled = item.status === 'CALLED';
      const badgeStyle = isCalled 
        ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40 animate-pulse'
        : 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30';

      return `
        <div class="p-3 rounded-xl bg-slate-800/40 border border-white/5 flex items-center justify-between">
          <div class="flex items-center gap-3">
            <span class="w-8 h-8 rounded-lg bg-slate-700/80 text-white font-mono font-bold text-xs flex items-center justify-center">
              ${item.position > 0 ? `#${item.position}` : '🔔'}
            </span>
            <div>
              <div class="flex items-center gap-2">
                <span class="font-bold text-sm text-slate-200">${item.ticket_code}</span>
                <span class="text-xs text-slate-400">(${item.party_size} Guests)</span>
              </div>
              <span class="text-[11px] text-slate-500">${item.preferred_section}</span>
            </div>
          </div>

          <div class="text-right">
            <span class="px-2.5 py-1 rounded-full text-[11px] font-semibold border ${badgeStyle}">
              ${isCalled ? 'TABLE READY' : `~${item.estimated_wait_minutes}m wait`}
            </span>
          </div>
        </div>
      `;
    }).join('');
  }
};
