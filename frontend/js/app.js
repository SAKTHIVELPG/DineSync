/**
 * DINESYNC Main Application Controller & Router
 */
const App = {
  currentRoute: 'home',
  currentRole: 'customer', // 'customer' | 'admin'
  customerSession: null,

  initTheme() {
    const theme = document.documentElement.dataset.theme || localStorage.getItem('dinesync_theme') || 'dark';
    document.documentElement.dataset.theme = theme;
    this.updateThemeToggle(theme);
  },

  toggleTheme() {
    const next = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
    document.documentElement.dataset.theme = next;
    localStorage.setItem('dinesync_theme', next);
    this.updateThemeToggle(next);
    this.showToast(`${next === 'light' ? 'Light' : 'Dark'} theme enabled`, 'info');
  },

  updateThemeToggle(theme) {
    const button = document.getElementById('theme-toggle');
    if (!button) return;
    const isLight = theme === 'light';
    button.setAttribute('aria-pressed', String(isLight));
    button.setAttribute('aria-label', `Switch to ${isLight ? 'dark' : 'light'} theme`);
    button.innerHTML = `<i data-lucide="${isLight ? 'moon' : 'sun'}" class="w-4 h-4" aria-hidden="true"></i><span class="hidden lg:inline">${isLight ? 'Dark mode' : 'Light mode'}</span>`;
    if (window.lucide) lucide.createIcons();
  },

  async init() {
    console.log('Initializing DINESYNC Smart Restaurant System...');
    this.initTheme();
    
    // Connect WebSocket
    if (window.dinesyncWS) {
      window.dinesyncWS.connect();
    }

    // Check saved role / session
    const savedToken = localStorage.getItem('dinesync_admin_token');
    if (savedToken) {
      this.currentRole = 'admin';
    } else {
      try { this.customerSession = JSON.parse(localStorage.getItem('dinesync_customer_session') || 'null'); } catch (_) { this.customerSession = null; }
    }

    // Initialize module controllers
    await DashboardController.init();
    await TablesController.init();
    await QueueController.init();
    await AIPredictionController.init();
    await AnalyticsController.init();
    await AdminController.init();

    this.updateRoleUI();

    // Check URL hash for routing
    const hash = window.location.hash.replace('#', '') || (this.currentRole === 'admin' ? 'admin' : (this.customerSession ? 'home' : 'login'));
    if (this.currentRole === 'customer' && !this.customerSession) this.setLoginTab('customer');
    this.navigateTo(hash, false);

    window.addEventListener('hashchange', () => {
      const h = window.location.hash.replace('#', '') || (this.currentRole === 'admin' ? 'admin' : (this.customerSession ? 'home' : 'login'));
      this.navigateTo(h, false);
    });

    if (window.lucide) {
      lucide.createIcons();
    }
  },

  setRole(role) {
    this.currentRole = role;
    this.updateRoleUI();
  },

  updateRoleUI() {
    const isStaff = (this.currentRole === 'admin' && AdminController.isAuthenticated);
    
    const customerNav = document.getElementById('nav-set-customer');
    const adminNav = document.getElementById('nav-set-admin');
    const customerActions = document.getElementById('header-customer-actions');
    const adminActions = document.getElementById('header-admin-actions');
    const roleBadge = document.getElementById('header-role-badge');
    const mobileCustomer = document.getElementById('mobile-nav-customer');
    const mobileAdmin = document.getElementById('mobile-nav-admin');
    const header = document.getElementById('main-header');

    if (isStaff) {
      customerNav?.classList.add('hidden');
      customerNav?.classList.remove('md:flex');
      adminNav?.classList.remove('hidden');
      adminNav?.classList.add('md:flex');
      
      customerActions?.classList.add('hidden');
      adminActions?.classList.remove('hidden');
      adminActions?.classList.add('flex');

      mobileCustomer?.classList.add('hidden');
      mobileAdmin?.classList.remove('hidden');
      mobileAdmin?.classList.add('flex');

      if (roleBadge) {
        roleBadge.innerText = 'Manager Mode';
        roleBadge.className = 'px-1.5 py-0.5 rounded text-[10px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/40';
      }
      if (header) {
        header.classList.add('border-purple-500/30');
      }
    } else {
      adminNav?.classList.add('hidden');
      adminNav?.classList.remove('md:flex');
      customerNav?.classList.remove('hidden');
      customerNav?.classList.add('md:flex');

      adminActions?.classList.add('hidden');
      adminActions?.classList.remove('flex');
      customerActions?.classList.remove('hidden');
      customerActions?.classList.add('flex');
      document.getElementById('header-customer-logout')?.classList.toggle('hidden', !this.customerSession);

      mobileAdmin?.classList.add('hidden');
      mobileCustomer?.classList.remove('hidden');
      mobileCustomer?.classList.add('flex');

      if (roleBadge) {
        roleBadge.innerText = this.customerSession ? `Hi, ${this.customerSession.name.split(' ')[0]}` : 'Customer Portal';
        roleBadge.className = 'px-1.5 py-0.5 rounded text-[10px] font-bold bg-cyan-500/20 text-cyan-400 border border-cyan-500/30';
      }
      if (header) {
        header.classList.remove('border-purple-500/30');
      }
    }

    if (window.lucide) lucide.createIcons();
  },

  navigateToRoleHome() {
    if (this.currentRole === 'admin' && AdminController.isAuthenticated) {
      this.navigateTo('admin');
    } else {
      this.navigateTo('home');
    }
  },

  switchToCustomerView() {
    this.currentRole = 'customer';
    if (!this.customerSession) {
      this.setLoginTab('customer');
      this.navigateTo('login');
      return;
    }
    this.updateRoleUI();
    this.navigateTo('home');
    this.showToast('Switched to Guest Customer View', 'info');
  },

  setLoginTab(tab) {
    const staffTab = document.getElementById('login-tab-staff');
    const guestTab = document.getElementById('login-tab-guest');
    const btnStaff = document.getElementById('login-tab-btn-staff');
    const btnGuest = document.getElementById('login-tab-btn-guest');

    if (tab === 'staff') {
      staffTab?.classList.remove('hidden');
      guestTab?.classList.add('hidden');
      btnStaff?.classList.add('bg-purple-500/20', 'text-purple-300', 'border', 'border-purple-500/30');
      btnStaff?.classList.remove('text-slate-400');
      btnGuest?.classList.remove('bg-cyan-500/20', 'text-cyan-300', 'border', 'border-cyan-500/30');
      btnGuest?.classList.add('text-slate-400');
    } else {
      guestTab?.classList.remove('hidden');
      staffTab?.classList.add('hidden');
      btnGuest?.classList.add('bg-cyan-500/20', 'text-cyan-300', 'border', 'border-cyan-500/30');
      btnGuest?.classList.remove('text-slate-400');
      btnStaff?.classList.remove('bg-purple-500/20', 'text-purple-300', 'border', 'border-purple-500/30');
      btnStaff?.classList.add('text-slate-400');
    }
    if (window.lucide) lucide.createIcons();
  },

  customerLogin(form) {
    const name = form.querySelector('#customer-name-input').value.trim();
    const email = form.querySelector('#customer-email-input').value.trim().toLowerCase();
    const phone = form.querySelector('#customer-phone-input').value.trim();
    if (!name || !email || !phone) return;
    this.customerSession = { name, email, phone, signedInAt: new Date().toISOString() };
    localStorage.setItem('dinesync_customer_session', JSON.stringify(this.customerSession));
    this.currentRole = 'customer';
    this.updateRoleUI();
    this.navigateTo('home');
    this.showToast(`Welcome, ${name.split(' ')[0]}. Your customer dashboard is ready.`, 'success');
  },

  customerLogout() {
    localStorage.removeItem('dinesync_customer_session');
    this.customerSession = null;
    this.currentRole = 'customer';
    this.updateRoleUI();
    this.setLoginTab('customer');
    this.navigateTo('login');
    this.showToast('You have been signed out.', 'info');
  },

  navigateTo(route, updateHash = true) {
    const validRoutes = ['home', 'dashboard', 'tables', 'queue', 'predictions', 'analytics', 'admin', 'login'];
    if (!validRoutes.includes(route)) route = 'home';

    // Entry guard: every dashboard view requires either a staff session or a customer profile.
    if (route !== 'login' && this.currentRole !== 'admin' && !this.customerSession) {
      this.setLoginTab('customer');
      route = 'login';
    }

    // Route Guard for Admin Console
    if (route === 'admin' && !AdminController.isAuthenticated) {
      this.showToast('Please enter Staff Security PIN to access Admin Console', 'warning');
      this.setLoginTab('staff');
      route = 'login';
    }

    this.currentRoute = route;
    if (updateHash) {
      window.location.hash = route;
    }

    // Hide all view containers
    validRoutes.forEach(r => {
      const el = document.getElementById(`view-${r}`);
      if (el) el.classList.add('hidden');

      const navBtn = document.getElementById(`nav-link-${r}`);
      const navBtnMobile = document.getElementById(`nav-mobile-${r}`);
      if (navBtn) navBtn.classList.remove('bg-cyan-500/20', 'text-cyan-400', 'border-cyan-500/30', 'font-semibold', 'bg-purple-500/20', 'text-purple-300', 'border-purple-500/30');
      if (navBtnMobile) navBtnMobile.classList.remove('text-cyan-400', 'font-bold', 'text-purple-400');
    });

    // Show current route view
    const activeEl = document.getElementById(`view-${route}`);
    if (activeEl) activeEl.classList.remove('hidden');

    const activeNavBtn = document.getElementById(`nav-link-${route}`);
    const activeNavBtnMobile = document.getElementById(`nav-mobile-${route}`);
    if (activeNavBtn) {
      if (this.currentRole === 'admin') {
        activeNavBtn.classList.add('bg-purple-500/20', 'text-purple-300', 'border-purple-500/30', 'font-semibold');
      } else {
        activeNavBtn.classList.add('bg-cyan-500/20', 'text-cyan-400', 'border-cyan-500/30', 'font-semibold');
      }
    }
    if (activeNavBtnMobile) {
      activeNavBtnMobile.classList.add('text-cyan-400', 'font-bold');
    }

    // Trigger module-specific refreshes
    if (route === 'dashboard') DashboardController.fetchAndRenderStats();
    if (route === 'tables') TablesController.render();
    if (route === 'queue') QueueController.fetchPublicQueue();
    if (route === 'predictions') AIPredictionController.calculateWaitPrediction();
    if (route === 'analytics') AnalyticsController.fetchAndRenderAnalytics();
    if (route === 'admin') AdminController.refreshAll();

    // Scroll to top
    window.scrollTo({ top: 0, behavior: 'smooth' });

    if (window.lucide) {
      lucide.createIcons();
    }
  },

  showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    let borderClass = 'border-cyan-500/40 text-cyan-200 bg-slate-900/95';
    let icon = 'info';

    if (type === 'success') {
      borderClass = 'border-emerald-500/50 text-emerald-200 bg-slate-900/95';
      icon = 'check-circle';
    } else if (type === 'warning') {
      borderClass = 'border-amber-500/50 text-amber-200 bg-slate-900/95';
      icon = 'alert-triangle';
    } else if (type === 'error') {
      borderClass = 'border-rose-500/50 text-rose-200 bg-slate-900/95';
      icon = 'alert-octagon';
    }

    toast.className = `toast p-4 rounded-xl border ${borderClass} shadow-2xl backdrop-blur-md flex items-center gap-3 text-xs max-w-sm`;
    toast.innerHTML = `
      <i data-lucide="${icon}" class="w-4 h-4 shrink-0"></i>
      <span class="flex-1 font-medium">${message}</span>
      <button onclick="this.parentElement.remove()" class="text-slate-400 hover:text-white ml-2">✕</button>
    `;

    container.appendChild(toast);
    if (window.lucide) lucide.createIcons();

    setTimeout(() => {
      if (toast.parentElement) {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
      }
    }, 4500);
  },

  playAlertChime() {
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext) return;
      const ctx = new AudioContext();

      const osc1 = ctx.createOscillator();
      const osc2 = ctx.createOscillator();
      const gain = ctx.createGain();

      osc1.type = 'sine';
      osc2.type = 'triangle';

      osc1.frequency.setValueAtTime(587.33, ctx.currentTime); // D5
      osc1.frequency.setValueAtTime(880.00, ctx.currentTime + 0.15); // A5

      osc2.frequency.setValueAtTime(440.00, ctx.currentTime);
      osc2.frequency.setValueAtTime(659.25, ctx.currentTime + 0.15);

      gain.gain.setValueAtTime(0.3, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.8);

      osc1.connect(gain);
      osc2.connect(gain);
      gain.connect(ctx.destination);

      osc1.start();
      osc2.start();
      osc1.stop(ctx.currentTime + 0.85);
      osc2.stop(ctx.currentTime + 0.85);
    } catch (e) {
      console.log('Audio chime not supported');
    }
  }
};

document.addEventListener('DOMContentLoaded', () => {
  App.init();
});
