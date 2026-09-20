/**
 * Winter Arc Showcase & Self-Hosting Manual
 * Interactive UI scripts: live countdown, phase switcher, tabs, copy-to-clipboard, mobile navigation
 * Zero Emojis Policy
 */

document.addEventListener('DOMContentLoaded', () => {
  initMobileNav();
  initCommandTabs();
  initPlatformTabs();
  initCopyButtons();
  initCountdownTimer();
});

/**
 * Mobile Navigation Menu Toggle
 */
function initMobileNav() {
  const toggleBtn = document.getElementById('mobileToggle');
  const navLinks = document.getElementById('navLinks');

  if (!toggleBtn || !navLinks) return;

  toggleBtn.addEventListener('click', () => {
    navLinks.classList.toggle('active');
  });

  // Close menu when clicking on a link
  navLinks.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', () => {
      navLinks.classList.remove('active');
    });
  });
}

/**
 * Live Winter Arc Seasonal Countdown & Interactive Phase Switcher
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

  // Compute current year
  const now = new Date();
  const currentYear = now.getFullYear();

  // Phase target timestamps
  let currentTargetDate = new Date(`${currentYear}-10-01T00:00:00`);

  function updateClock() {
    const currentTime = new Date().getTime();
    const targetTime = currentTargetDate.getTime();
    let diff = targetTime - currentTime;

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
        currentTargetDate = new Date(targetIso);
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

  // Initial call and periodic tick
  updateClock();
  setInterval(updateClock, 1000);
}

/**
 * Slash Command Reference Tabs
 */
function initCommandTabs() {
  const tabButtons = document.querySelectorAll('.cmd-tab-btn');
  const tabContents = document.querySelectorAll('.cmd-tab-content');

  tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetId = btn.getAttribute('data-tab');

      tabButtons.forEach(b => b.classList.remove('active'));
      tabContents.forEach(c => c.classList.remove('active'));

      btn.classList.add('active');
      const targetContent = document.getElementById(targetId);
      if (targetContent) {
        targetContent.classList.add('active');
      }
    });
  });
}

/**
 * Self-Hosting Platform Tabs (Wispbyte, Linux VPS, Cloud)
 */
function initPlatformTabs() {
  const tabButtons = document.querySelectorAll('.plat-tab-btn');
  const tabContents = document.querySelectorAll('.plat-content');

  tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetId = btn.getAttribute('data-target');

      tabButtons.forEach(b => b.classList.remove('active'));
      tabContents.forEach(c => c.classList.remove('active'));

      btn.classList.add('active');
      const targetContent = document.getElementById(targetId);
      if (targetContent) {
        targetContent.classList.add('active');
      }
    });
  });
}

/**
 * One-Click Copy to Clipboard with Feedback
 */
function initCopyButtons() {
  const copyButtons = document.querySelectorAll('.copy-btn');

  copyButtons.forEach(btn => {
    btn.addEventListener('click', async () => {
      const textToCopy = btn.getAttribute('data-copy');
      if (!textToCopy) return;

      try {
        await navigator.clipboard.writeText(textToCopy);
        const originalText = btn.textContent;
        btn.textContent = 'Copied';
        btn.style.background = '#00e5ff';
        btn.style.color = '#000000';

        setTimeout(() => {
          btn.textContent = originalText;
          btn.style.background = '';
          btn.style.color = '';
        }, 2000);
      } catch (err) {
        // Fallback for older browsers or restricted permissions
        const textArea = document.createElement('textarea');
        textArea.value = textToCopy;
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);

        btn.textContent = 'Copied';
        setTimeout(() => {
          btn.textContent = 'Copy';
        }, 2000);
      }
    });
  });
}
