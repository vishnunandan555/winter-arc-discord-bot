/**
 * Winter Arc Showcase & Self-Hosting Manual
 * Interactive UI Scripts:
 * - Live Countdown & Seasonal Phase Switcher
 * - Interactive Discord Client Embed Simulator
 * - Filterable & Searchable Slash Command Directory
 * - Multi-Platform Self-Hosting Tabs Controller
 * - Universal Copy-to-Clipboard with Toast Notifications
 * - Mobile Navigation Drawer
 */

document.addEventListener('DOMContentLoaded', () => {
  initMobileNav();
  initCountdownTimer();
  initDiscordSimulator();
  initCommandDirectory();
  initHostingPlatformTabs();
  initCopyEngine();
});

/**
 * Mobile Navigation Drawer Toggle & Backdrop Overlay
 */
function initMobileNav() {
  const toggleBtn = document.getElementById('mobileToggle');
  const navLinks = document.getElementById('navLinks');
  const navBackdrop = document.getElementById('navBackdrop');

  if (!toggleBtn || !navLinks) return;

  function openMenu() {
    navLinks.classList.add('active');
    toggleBtn.classList.add('active');
    if (navBackdrop) navBackdrop.classList.add('active');
    document.body.classList.add('menu-open');
  }

  function closeMenu() {
    navLinks.classList.remove('active');
    toggleBtn.classList.remove('active');
    if (navBackdrop) navBackdrop.classList.remove('active');
    document.body.classList.remove('menu-open');
  }

  toggleBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (navLinks.classList.contains('active')) {
      closeMenu();
    } else {
      openMenu();
    }
  });

  if (navBackdrop) {
    navBackdrop.addEventListener('click', closeMenu);
  }

  // Auto-close menu when clicking a link
  navLinks.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', closeMenu);
  });

  // Close on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && navLinks.classList.contains('active')) {
      closeMenu();
    }
  });
}

/**
 * Live Countdown Timer & Interactive Seasonal Phase Switcher
 */
function initCountdownTimer() {
  const timerDays = document.getElementById('timerDays');
  const timerHours = document.getElementById('timerHours');
  const timerMinutes = document.getElementById('timerMinutes');
  const timerSeconds = document.getElementById('timerSeconds');
  const titleEl = document.getElementById('countdownTargetTitle');
  const badgeEl = document.getElementById('countdownStatusBadge');
  const subtextEl = document.getElementById('countdownSubtext');
  const phaseBtns = document.querySelectorAll('.phase-btn');

  if (!timerDays || !timerHours || !timerMinutes || !timerSeconds) return;

  // Base year setup
  const now = new Date();
  const currentYear = now.getFullYear();

  // Default target: October 1st
  let targetDate = new Date(`${currentYear}-10-01T00:00:00`);

  function updateClock() {
    const currentTime = new Date().getTime();
    const diff = targetDate.getTime() - currentTime;

    if (diff <= 0) {
      timerDays.textContent = '00';
      timerHours.textContent = '00';
      timerMinutes.textContent = '00';
      timerSeconds.textContent = '00';
      return;
    }

    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    const seconds = Math.floor((diff % (1000 * 60)) / 1000);

    timerDays.textContent = String(days).padStart(2, '0');
    timerHours.textContent = String(hours).padStart(2, '0');
    timerMinutes.textContent = String(minutes).padStart(2, '0');
    timerSeconds.textContent = String(seconds).padStart(2, '0');
  }

  // Update clock every second
  updateClock();
  setInterval(updateClock, 1000);

  // Phase switcher buttons
  phaseBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      phaseBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      const targetIso = btn.getAttribute('data-target');
      const title = btn.getAttribute('data-title');
      const badge = btn.getAttribute('data-badge');
      const sub = btn.getAttribute('data-sub');

      if (targetIso) {
        targetDate = new Date(targetIso);
      }
      if (title && titleEl) {
        titleEl.textContent = title;
      }
      if (badge && badgeEl) {
        badgeEl.textContent = badge;
      }
      if (sub && subtextEl) {
        subtextEl.textContent = sub;
      }

      updateClock();
    });
  });
}

/**
 * Interactive Discord Client Embed Simulator
 */
function initDiscordSimulator() {
  const simTabs = document.querySelectorAll('.sim-tab-btn');
  const embedCards = document.querySelectorAll('.discord-embed-card');

  if (!simTabs.length || !embedCards.length) return;

  simTabs.forEach(btn => {
    btn.addEventListener('click', () => {
      simTabs.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      const simKey = btn.getAttribute('data-sim');
      const targetCard = document.getElementById(`sim-view-${simKey}`);

      embedCards.forEach(card => card.classList.remove('active'));
      if (targetCard) {
        targetCard.classList.add('active');
      }
    });
  });
}

/**
 * Filterable & Searchable Slash Command Directory
 */
function initCommandDirectory() {
  const searchInput = document.getElementById('commandSearchInput');
  const clearBtn = document.getElementById('clearSearchBtn');
  const filterBtns = document.querySelectorAll('.filter-btn');
  const cmdCards = document.querySelectorAll('.commands-grid .cmd-card');

  if (!searchInput || !cmdCards.length) return;

  let activeCategory = 'all';

  function filterCommands() {
    const query = searchInput.value.toLowerCase().trim();

    // Toggle clear button visibility
    if (clearBtn) {
      if (query.length > 0) {
        clearBtn.classList.add('visible');
      } else {
        clearBtn.classList.remove('visible');
      }
    }

    cmdCards.forEach(card => {
      const cardCategory = card.getAttribute('data-category');
      const cardText = card.textContent.toLowerCase();

      const matchesCategory = (activeCategory === 'all' || cardCategory === activeCategory);
      const matchesSearch = (query === '' || cardText.includes(query));

      if (matchesCategory && matchesSearch) {
        card.style.display = 'flex';
      } else {
        card.style.display = 'none';
      }
    });
  }

  // Category filter button listener
  filterBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      filterBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeCategory = btn.getAttribute('data-category');
      filterCommands();
    });
  });

  // Search input listener
  searchInput.addEventListener('input', filterCommands);

  // Clear button listener
  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      searchInput.value = '';
      clearBtn.classList.remove('visible');
      filterCommands();
      searchInput.focus();
    });
  }
}

/**
 * Multi-Platform Self-Hosting Tabs Controller
 */
function initHostingPlatformTabs() {
  const platTabs = document.querySelectorAll('.plat-tab-btn');
  const platPanels = document.querySelectorAll('.plat-content');

  if (!platTabs.length || !platPanels.length) return;

  platTabs.forEach(btn => {
    btn.addEventListener('click', () => {
      platTabs.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      const targetId = btn.getAttribute('data-target');
      platPanels.forEach(panel => {
        panel.classList.remove('active');
        if (panel.id === targetId) {
          panel.classList.add('active');
        }
      });
    });
  });
}

/**
 * Universal Copy-to-Clipboard with Toast Feedback
 */
function initCopyEngine() {
  const copyButtons = document.querySelectorAll('[data-copy]');

  copyButtons.forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      const textToCopy = btn.getAttribute('data-copy');
      if (!textToCopy) return;

      try {
        await navigator.clipboard.writeText(textToCopy);
        
        // Button state feedback
        const originalText = btn.textContent;
        btn.textContent = 'Copied!';
        btn.classList.add('copied');

        showToast('Copied to clipboard!');

        setTimeout(() => {
          btn.textContent = originalText;
          btn.classList.remove('copied');
        }, 2000);
      } catch (err) {
        // Fallback for older browsers
        const textarea = document.createElement('textarea');
        textarea.value = textToCopy;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);

        showToast('Copied to clipboard!');
      }
    });
  });
}

/**
 * Floating Toast Notification
 */
function showToast(message) {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.innerHTML = `
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="#00E5FF" stroke-width="2.5">
      <polyline points="20 6 9 17 4 12"></polyline>
    </svg>
    <span>${message}</span>
  `;

  container.appendChild(toast);

  // Auto-remove after animation finishes (2.5s)
  setTimeout(() => {
    if (toast.parentNode === container) {
      container.removeChild(toast);
    }
  }, 2600);
}
