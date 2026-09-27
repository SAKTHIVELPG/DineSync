const ReservationController = {
  table: null,
  availability: null,
  availabilityRequest: 0,

  open(table) {
    this.table = table;
    this.availability = null;
    document.getElementById('reservation-table-label').textContent = `${table.name} · ${table.section}`;
    document.getElementById('reservation-capacity-label').textContent = `Up to ${table.capacity} guests`;
    const party = document.getElementById('reservation-party-size');
    party.innerHTML = Array.from({ length: table.capacity }, (_, i) => `<option value="${i + 1}">${i + 1} ${i === 0 ? 'guest' : 'guests'}</option>`).join('');
    this.setDefaultSchedule();
    document.getElementById('reservation-duration').value = '2';
    document.getElementById('reservation-form').classList.remove('hidden');
    document.getElementById('reservation-confirmation').classList.add('hidden');
    document.getElementById('reservation-modal').classList.remove('hidden');
    document.getElementById('reservation-name').focus();
    this.refreshAvailability();
  },

  close() {
    document.getElementById('reservation-modal')?.classList.add('hidden');
    this.table = null;
    this.availability = null;
  },

  setDefaultSchedule() {
    const now = new Date();
    const date = document.getElementById('reservation-date');
    const time = document.getElementById('reservation-time');
    // Use the restaurant guest's local calendar date, not UTC (which can be
    // yesterday after midnight in India, Australia, and other time zones).
    date.value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    date.min = date.value;
    const rounded = new Date(now.getTime() + 30 * 60 * 1000);
    rounded.setMinutes(Math.ceil(rounded.getMinutes() / 30) * 30, 0, 0);
    time.value = `${String(rounded.getHours()).padStart(2, '0')}:${String(rounded.getMinutes()).padStart(2, '0')}`;
  },

  toggleContactMethod() {
    const method = document.querySelector('input[name="notification_method"]:checked')?.value || 'email';
    document.getElementById('reservation-email-field')?.classList.toggle('hidden', method !== 'email');
    document.getElementById('reservation-phone-field')?.classList.toggle('hidden', method !== 'sms');
    document.getElementById('reservation-email')?.toggleAttribute('required', method === 'email');
    document.getElementById('reservation-phone')?.toggleAttribute('required', method === 'sms');
  },

  async refreshAvailability() {
    if (!this.table) return;
    const date = document.getElementById('reservation-date').value;
    const time = document.getElementById('reservation-time').value;
    const duration = Number(document.getElementById('reservation-duration').value || 2);
    if (!date || !time) return;
    const requestId = ++this.availabilityRequest;
    const card = document.getElementById('reservation-availability');
    const submit = document.querySelector('#reservation-form button[type="submit"]');
    card.className = 'availability-card is-loading';
    card.innerHTML = '<span class="availability-dot"></span><span>Checking this table’s schedule…</span>';
    try {
      const response = await fetch(`/api/v1/reservations/availability/check?table_id=${this.table.id}&reservation_date=${encodeURIComponent(date)}&reservation_time=${encodeURIComponent(time)}&duration_hours=${duration}`);
      const result = await response.json();
      if (requestId !== this.availabilityRequest) return;
      if (!response.ok) throw new Error(result.detail || 'Availability check failed');
      this.availability = result;
      const booked = `${result.booking_count} ${result.booking_count === 1 ? 'booking' : 'bookings'} · ${result.booked_guests} ${result.booked_guests === 1 ? 'guest' : 'guests'} already booked that day`;
      card.className = `availability-card ${result.available ? 'is-available' : 'is-busy'}`;
      card.innerHTML = `<span class="availability-dot"></span><div><strong>${result.available ? 'Available for your selected time' : 'Not available for that time'}</strong><small>${result.available ? `Your table would be held until ${result.requested_end_display}.` : `Next available: ${result.next_available_display}.`}</small><small>${booked}</small></div>`;
      submit.disabled = !result.available;
      submit.classList.toggle('opacity-50', !result.available);
      submit.title = result.available ? '' : 'Choose a different time';
    } catch (error) {
      this.availability = null;
      submit.disabled = false;
      card.className = 'availability-card is-error';
      card.innerHTML = '<span class="availability-dot"></span><span>Availability could not be checked. Please try again.</span>';
    }
  },

  async submit(event) {
    event.preventDefault();
    if (!this.table) return;
    const submit = event.currentTarget.querySelector('button[type="submit"]');
    const errorBox = document.getElementById('reservation-form-error');
    if (errorBox) errorBox.textContent = '';
    await this.refreshAvailability();
    if (!this.availability) {
      if (errorBox) errorBox.textContent = 'We could not verify this time. Check your connection and try again.';
      return;
    }
    if (!this.availability.available) {
      App.showToast(this.availability?.next_available_display ? `Next available: ${this.availability.next_available_display}` : 'Choose an available time.', 'error');
      return;
    }
    const form = event.currentTarget;
    submit.disabled = true;
    submit.textContent = 'Confirming…';
    const method = document.querySelector('input[name="notification_method"]:checked')?.value || 'email';
    const payload = {
      table_id: this.table.id,
      customer_name: document.getElementById('reservation-name').value.trim(),
      email: document.getElementById('reservation-email').value.trim() || null,
      phone: document.getElementById('reservation-phone').value.trim() || null,
      notification_method: method,
      party_size: Number(document.getElementById('reservation-party-size').value),
      reservation_date: document.getElementById('reservation-date').value,
      reservation_time: document.getElementById('reservation-time').value,
      duration_hours: Number(document.getElementById('reservation-duration').value),
    };

    try {
      const response = await fetch('/api/v1/reservations', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
      });
      const result = await response.json();
      if (!response.ok) {
        const detail = typeof result.detail === 'object' ? `${result.detail.message} Next available: ${result.detail.next_available_display || 'later'}.` : result.detail;
        if (errorBox) errorBox.textContent = detail || 'We could not complete the reservation.';
        App.showToast(detail || 'We could not complete the reservation.', 'error');
        return;
      }
      document.getElementById('reservation-form').classList.add('hidden');
      document.getElementById('reservation-confirmation').classList.remove('hidden');
      document.getElementById('reservation-booking-id').textContent = result.booking_id;
      document.getElementById('reservation-confirmed-table').textContent = `Table ${result.table.table_number} · ${result.reservation.party_size} ${result.reservation.party_size === 1 ? 'guest' : 'guests'}`;
      document.getElementById('reservation-confirmed-date').textContent = `${result.reservation.date} at ${result.reservation.time}`;
      document.getElementById('reservation-confirmed-window').textContent = `${result.reservation.duration_hours} hour${result.reservation.duration_hours === 1 ? '' : 's'} · free at ${result.reservation.end_display}`;
      document.getElementById('reservation-confirmed-channel').textContent = `${method === 'email' ? 'Email' : 'SMS'} confirmation queued`;
      document.getElementById('reservation-confirmed-booked').textContent = `${result.availability.booking_count} bookings · ${result.availability.booked_guests} guests booked that day`;
      App.showToast('Your table has been reserved.', 'success');
      this.table = result.table;
      TablesController.fetchTables();
    } catch (error) {
      if (errorBox) errorBox.textContent = 'Network error. Please check your connection and try again.';
      App.showToast('Network error. Your table was not reserved.', 'error');
    } finally {
      submit.disabled = false;
      submit.textContent = 'Confirm reservation';
    }
  },
};

document.addEventListener('DOMContentLoaded', () => {
  // The modal is declared near the legacy admin markup for source organization,
  // but must live under body so hidden staff views cannot collapse its layout.
  const modal = document.getElementById('reservation-modal');
  if (modal && modal.parentElement !== document.body) document.body.appendChild(modal);
  document.getElementById('reservation-date')?.addEventListener('change', () => ReservationController.refreshAvailability());
  document.getElementById('reservation-time')?.addEventListener('change', () => ReservationController.refreshAvailability());
  document.getElementById('reservation-duration')?.addEventListener('change', () => ReservationController.refreshAvailability());
  ReservationController.toggleContactMethod();
});
