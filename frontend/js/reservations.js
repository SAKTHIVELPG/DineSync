const ReservationController = {
  table: null,

  open(table) {
    this.table = table;
    document.getElementById('reservation-table-label').textContent = `${table.name} · ${table.section}`;
    document.getElementById('reservation-capacity-label').textContent = `Up to ${table.capacity} guests`;
    const party = document.getElementById('reservation-party-size');
    party.innerHTML = Array.from({ length: table.capacity }, (_, i) => `<option value="${i + 1}">${i + 1} ${i === 0 ? 'guest' : 'guests'}</option>`).join('');
    document.getElementById('reservation-form').classList.remove('hidden');
    document.getElementById('reservation-confirmation').classList.add('hidden');
    document.getElementById('reservation-modal').classList.remove('hidden');
    document.getElementById('reservation-name').focus();
  },

  close() {
    document.getElementById('reservation-modal')?.classList.add('hidden');
    this.table = null;
  },

  toggleContactMethod() {
    const method = document.querySelector('input[name="notification_method"]:checked')?.value || 'email';
    document.getElementById('reservation-email-field')?.classList.toggle('hidden', method !== 'email');
    document.getElementById('reservation-phone-field')?.classList.toggle('hidden', method !== 'sms');
    document.getElementById('reservation-email')?.toggleAttribute('required', method === 'email');
    document.getElementById('reservation-phone')?.toggleAttribute('required', method === 'sms');
  },

  async submit(event) {
    event.preventDefault();
    if (!this.table) return;
    const form = event.currentTarget;
    const submit = form.querySelector('button[type="submit"]');
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
    };

    try {
      const response = await fetch('/api/v1/reservations', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
      });
      const result = await response.json();
      if (!response.ok) {
        App.showToast(result.detail || 'We could not complete the reservation.', 'error');
        return;
      }
      document.getElementById('reservation-form').classList.add('hidden');
      document.getElementById('reservation-confirmation').classList.remove('hidden');
      document.getElementById('reservation-booking-id').textContent = result.booking_id;
      document.getElementById('reservation-confirmed-table').textContent = `Table ${result.table.table_number} · ${result.reservation.party_size} ${result.reservation.party_size === 1 ? 'guest' : 'guests'}`;
      document.getElementById('reservation-confirmed-date').textContent = `${result.reservation.date} at ${result.reservation.time}`;
      document.getElementById('reservation-confirmed-channel').textContent = `${method === 'email' ? 'Email' : 'SMS'} confirmation queued`;
      App.showToast('Your table has been reserved.', 'success');
      this.table = result.table;
      TablesController.fetchTables();
    } catch (error) {
      App.showToast('Network error. Your table was not reserved.', 'error');
    } finally {
      submit.disabled = false;
      submit.textContent = 'Confirm reservation';
    }
  },
};

document.addEventListener('DOMContentLoaded', () => {
  const date = document.getElementById('reservation-date');
  if (date) date.min = new Date().toISOString().slice(0, 10);
  ReservationController.toggleContactMethod();
});
