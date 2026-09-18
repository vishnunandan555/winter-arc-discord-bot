/**
 * Winter Arc Web Dashboard - Interactive Logic & Live Data Engine
 */

let appData = null;

// Fallback demo data in case of local file:// execution without a web server
const fallbackData = {
  meta: {
    generated_at: new Date().toISOString(),
    date_display: "Live Winter Arc Session",
    total_warriors: 4,
    total_collective_points: 140,
    daily_point_cap: 500,
    apex_threshold: 12000
  },
  disciplines: [
    { name: "Push-ups", description: "Chest, shoulders, and triceps", target: 100, unit: "reps", max_points: 100 },
    { name: "Pull-ups", description: "Lats, upper back, and biceps", target: 100, unit: "reps", max_points: 100 },
    { name: "Squats", description: "Quads, glutes, and legs", target: 100, unit: "reps", max_points: 100 },
    { name: "Sit-ups", description: "Core strength and hip flexors", target: 100, unit: "reps", max_points: 100 },
    { name: "Running", description: "Cardiovascular endurance", target: 10, unit: "km", max_points: 100 }
  ],
  ranks: [
    { level: 1, title: "Lone Stray", badge: "🐾", min_pts: 0, max_pts: 499 },
    { level: 2, title: "Stray", badge: "🐺", min_pts: 500, max_pts: 1199 },
    { level: 3, title: "Scout", badge: "🧭", min_pts: 1200, max_pts: 1999 },
    { level: 4, title: "Prowler", badge: "🐾", min_pts: 2000, max_pts: 2999 },
    { level: 5, title: "Tracker", badge: "🏹", min_pts: 3000, max_pts: 4199 },
    { level: 6, title: "Hunter", badge: "🗡️", min_pts: 4200, max_pts: 5499 },
    { level: 7, title: "Savage", badge: "⚔️", min_pts: 5500, max_pts: 6999 },
    { level: 8, title: "Vanguard", badge: "🛡️", min_pts: 7000, max_pts: 8499 },
    { level: 9, title: "Frostborn", badge: "❄️", min_pts: 8500, max_pts: 9799 },
    { level: 10, title: "Predator", badge: "⚡", min_pts: 9800, max_pts: 10799 },
    { level: 11, title: "Alpha", badge: "🔥", min_pts: 10800, max_pts: 11999 },
    { level: 12, title: "Apex", badge: "👑", min_pts: 12000, max_pts: null }
  ],
  overall_standings: [
    { rank: 1, username: "Arjun", total_points: 1000, streak: 2, perfect_days: 2, level: 2, title: "Stray", badge: "🐺", tier_pct: 71, pts_to_next: 200, arc_pct: 8.3 },
    { rank: 2, username: "Vishnu", total_points: 70, streak: 0, perfect_days: 0, level: 1, title: "Lone Stray", badge: "🐾", tier_pct: 14, pts_to_next: 430, arc_pct: 0.6 },
    { rank: 3, username: "Sarah", total_points: 0, streak: 0, perfect_days: 0, level: 1, title: "Lone Stray", badge: "🐾", tier_pct: 0, pts_to_next: 500, arc_pct: 0.0 },
    { rank: 4, username: "Dev", total_points: 0, streak: 0, perfect_days: 0, level: 1, title: "Lone Stray", badge: "🐾", tier_pct: 0, pts_to_next: 500, arc_pct: 0.0 }
  ],
  daily_standings: [
    { rank: 1, username: "Vishnu", points: 70, max_points: 500, completion_rate: 14.0, perfect_day: false },
    { rank: 2, username: "Arjun", points: 0, max_points: 500, completion_rate: 0.0, perfect_day: false }
  ]
};

// Application Initialization
document.addEventListener("DOMContentLoaded", () => {
  fetchData();
  initCountdown();
  setInterval(updateCountdown, 1000);
});

async function fetchData() {
  try {
    const res = await fetch("stats.json?t=" + Date.now());
    if (!res.ok) throw new Error("Could not fetch stats.json");
    appData = await res.json();
  } catch (err) {
    console.warn("Using local fallback data:", err);
    appData = fallbackData;
  }

  renderAll();
}

function renderAll() {
  if (!appData) return;

  renderHero(appData.meta);
  renderOverall(appData.overall_standings || []);
  renderDaily(appData.daily_standings || []);
  renderLadder(appData.ranks || []);
  renderDisciplines(appData.disciplines || []);
  renderWarriors(appData.overall_standings || []);

  const syncTag = document.getElementById("last-sync-time");
  if (syncTag && appData.meta.date_display) {
    syncTag.textContent = `📅 ${appData.meta.date_display}`;
  }
}

// Hero Rendering
function renderHero(meta) {
  if (!meta) return;
  const warriorsEl = document.getElementById("val-total-warriors");
  const pointsEl = document.getElementById("val-total-points");
  const capEl = document.getElementById("val-daily-cap");

  if (warriorsEl) warriorsEl.textContent = meta.total_warriors || "0";
  if (pointsEl) pointsEl.textContent = (meta.total_collective_points || 0).toLocaleString() + " PTS";
  if (capEl) capEl.textContent = (meta.daily_point_cap || 500) + " PTS";
}

// Overall Standings Table
function renderOverall(list) {
  const tbody = document.getElementById("tbody-overall");
  if (!tbody) return;

  if (!list.length) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:#94A3B8; padding:30px;">No enrolled participants yet. Run /enroll in Discord!</td></tr>`;
    return;
  }

  tbody.innerHTML = list.map((u, i) => {
    let rankBadge = `<span class="badge-rank">#${u.rank}</span>`;
    if (i === 0) rankBadge = `<span class="badge-rank rank-gold">👑 #1</span>`;
    else if (i === 1) rankBadge = `<span class="badge-rank rank-silver">⚔️ #2</span>`;
    else if (i === 2) rankBadge = `<span class="badge-rank rank-bronze">🛡️ #3</span>`;

    const streakPill = u.streak > 0 ? `<span class="pill pill-fire">🔥 ${u.streak}d</span>` : "";
    const cleanPill = u.perfect_days > 0 ? `<span class="pill pill-clean">⭐ ${u.perfect_days}</span>` : "";

    return `
      <tr>
        <td>${rankBadge}</td>
        <td><span class="warrior-name">${escapeHtml(u.username)}</span></td>
        <td>
          <span class="tag-level">${u.badge} Lvl ${u.level}: ${u.title}</span>
        </td>
        <td><span class="points-text">${(u.total_points || 0).toLocaleString()} pts</span></td>
        <td>
          <div class="mini-bar-wrap">
            <div class="mini-bar-fill" style="width: ${u.tier_pct || 0}%"></div>
          </div>
          <span style="font-size:0.8rem; color:#94A3B8;">${u.tier_pct || 0}%</span>
        </td>
        <td>
          <div class="stat-pills">
            ${streakPill}
            ${cleanPill}
            ${!streakPill && !cleanPill ? '<span style="color:#64748B; font-size:0.75rem;">Started</span>' : ''}
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

// Daily Standings Table
function renderDaily(list) {
  const tbody = document.getElementById("tbody-daily");
  if (!tbody) return;

  if (!list.length) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:#94A3B8; padding:30px;">No activity logged today yet. Be the first with /log!</td></tr>`;
    return;
  }

  tbody.innerHTML = list.map((u, i) => {
    let rankBadge = `<span class="badge-rank">#${u.rank}</span>`;
    if (i === 0) rankBadge = `<span class="badge-rank rank-gold">👑 #1</span>`;
    else if (i === 1) rankBadge = `<span class="badge-rank rank-silver">⚔️ #2</span>`;
    else if (i === 2) rankBadge = `<span class="badge-rank rank-bronze">🛡️ #3</span>`;

    const statusPill = u.perfect_day
      ? `<span class="pill pill-clean">⭐ 100% Clean</span>`
      : `<span style="font-size:0.8rem; color:#94A3B8;">${u.completion_rate}% done</span>`;

    return `
      <tr>
        <td>${rankBadge}</td>
        <td><span class="warrior-name">${escapeHtml(u.username)}</span></td>
        <td><span class="points-text">${u.points} / ${u.max_points} pts</span></td>
        <td>
          <div class="mini-bar-wrap" style="width: 160px;">
            <div class="mini-bar-fill" style="width: ${Math.min(100, u.completion_rate)}%"></div>
          </div>
        </td>
        <td>${statusPill}</td>
      </tr>
    `;
  }).join("");
}

// 12-Level Hierarchy Ladder
function renderLadder(ranks) {
  const grid = document.getElementById("ladder-grid");
  if (!grid) return;

  grid.innerHTML = ranks.map(r => {
    const isApex = (r.level === 12);
    const rangeText = r.max_pts !== null ? `${r.min_pts.toLocaleString()} – ${r.max_pts.toLocaleString()} pts` : "12,000+ Lifetime Points";
    const cardClass = isApex ? "ladder-card apex-card" : "ladder-card";

    return `
      <div class="${cardClass}">
        <div class="ladder-header">
          <span class="ladder-lvl-badge">LEVEL ${r.level}</span>
          <span class="ladder-icon">${r.badge}</span>
        </div>
        <div>
          <h3 class="ladder-title">${r.title}</h3>
          <p class="ladder-range">${rangeText}</p>
        </div>
      </div>
    `;
  }).join("");
}

// The 5 Disciplines Cards
function renderDisciplines(disciplines) {
  const grid = document.getElementById("disciplines-grid");
  if (!grid) return;

  const icons = {
    "push-ups": "💪",
    "pull-ups": "🧗",
    "squats": "🦵",
    "sit-ups": "🧘",
    "running": "🏃"
  };

  grid.innerHTML = disciplines.map(d => {
    const icon = icons[d.name.toLowerCase()] || "🎯";
    return `
      <div class="discipline-card">
        <div class="disc-top">
          <span class="disc-icon">${icon}</span>
          <div>
            <h3 class="disc-title">${escapeHtml(d.name)}</h3>
            <span class="disc-target">Daily Goal: ${d.target} ${escapeHtml(d.unit)}</span>
          </div>
        </div>
        <p class="disc-desc">${escapeHtml(d.description || "Core daily challenge discipline.")}</p>
        <div class="disc-footer">
          <span>Formula: 1 pt / rep</span>
          <span class="disc-max-pts">${d.max_points} PTS MAX</span>
        </div>
      </div>
    `;
  }).join("");
}

// Warrior Profile Cards & Search
function renderWarriors(list) {
  const grid = document.getElementById("warrior-cards-grid");
  if (!grid) return;

  if (!list.length) {
    grid.innerHTML = `<p style="color:#94A3B8; text-align:center; grid-column: 1/-1;">No participants found.</p>`;
    return;
  }

  grid.innerHTML = list.map(u => {
    return `
      <div class="warrior-inspect-card" data-username="${u.username.toLowerCase()}">
        <div class="wic-header">
          <h3 class="wic-name">${escapeHtml(u.username)}</h3>
          <span class="wic-rank">${u.badge} Lvl ${u.level}</span>
        </div>
        <div style="font-size:0.85rem; color:#00D2FF; font-weight:600; margin-bottom:8px;">
          ${u.title} • ${(u.total_points || 0).toLocaleString()} pts
        </div>
        <div class="mini-bar-wrap" style="width:100%; height:8px; margin: 4px 0 10px;">
          <div class="mini-bar-fill" style="width:${u.tier_pct || 0}%"></div>
        </div>
        <div class="wic-stats-row">
          <span>🔥 Streak: <strong>${u.streak || 0}d</strong></span>
          <span>⭐ Clean Days: <strong>${u.perfect_days || 0}</strong></span>
        </div>
        <div style="font-size:0.75rem; color:#64748B; margin-top:8px;">
          ${u.pts_to_next > 0 ? `${u.pts_to_next.toLocaleString()} pts to next level` : '👑 Max Rank (Apex)'}
        </div>
      </div>
    `;
  }).join("");
}

// Search Filter
function filterWarriors(query) {
  const q = query.toLowerCase().trim();
  const cards = document.querySelectorAll(".warrior-inspect-card");
  cards.forEach(card => {
    const name = card.getAttribute("data-username") || "";
    card.style.display = name.includes(q) ? "block" : "none";
  });
}

// Tab Switching
function switchTab(tabId) {
  const buttons = document.querySelectorAll(".tab-btn");
  buttons.forEach(btn => btn.classList.remove("active"));

  const targetBtn = document.getElementById(`tab-btn-${tabId}`);
  if (targetBtn) targetBtn.classList.add("active");

  const panes = document.querySelectorAll(".tab-content");
  panes.forEach(pane => pane.classList.add("hidden"));

  const targetPane = document.getElementById(`tab-pane-${tabId}`);
  if (targetPane) targetPane.classList.remove("hidden");
}

// Standings Subtab Toggle
function toggleStandingsView(subtab) {
  const btnOverall = document.getElementById("subtab-overall");
  const btnDaily = document.getElementById("subtab-daily");
  const boardOverall = document.getElementById("board-overall");
  const boardDaily = document.getElementById("board-daily");

  if (subtab === "overall") {
    btnOverall.classList.add("active");
    btnDaily.classList.remove("active");
    boardOverall.classList.remove("hidden");
    boardDaily.classList.add("hidden");
  } else {
    btnDaily.classList.add("active");
    btnOverall.classList.remove("active");
    boardDaily.classList.remove("hidden");
    boardOverall.classList.add("hidden");
  }
}

// IST Countdown Timer (Next: 05:00, 16:30, or 00:00 IST)
function initCountdown() {
  updateCountdown();
}

function updateCountdown() {
  const clockEl = document.getElementById("countdown-clock");
  const labelEl = document.getElementById("countdown-label");
  if (!clockEl) return;

  // Convert current time to IST (UTC + 5:30)
  const now = new Date();
  const utc = now.getTime() + (now.getTimezoneOffset() * 60000);
  const istNow = new Date(utc + (3600000 * 5.5));

  const h = istNow.getHours();
  const m = istNow.getMinutes();
  const s = istNow.getSeconds();
  const currentSecs = (h * 3600) + (m * 60) + s;

  // Target checkpoints in seconds from midnight
  const tMorning = 5 * 3600;           // 05:00
  const tAfternoon = (16 * 3600) + (30 * 60); // 16:30
  const tMidnight = 24 * 3600;         // 00:00

  let targetSecs = 0;
  let targetName = "";

  if (currentSecs < tMorning) {
    targetSecs = tMorning;
    targetName = "Morning Kickoff (05:00 IST)";
  } else if (currentSecs < tAfternoon) {
    targetSecs = tAfternoon;
    targetName = "Afternoon Check-in (16:30 IST)";
  } else {
    targetSecs = tMidnight;
    targetName = "Midnight Finalization (00:00 IST)";
  }

  const diffSecs = targetSecs - currentSecs;
  const dh = Math.floor(diffSecs / 3600);
  const dm = Math.floor((diffSecs % 3600) / 60);
  const ds = diffSecs % 60;

  const timeStr = `${String(dh).padStart(2, '0')}:${String(dm).padStart(2, '0')}:${String(ds).padStart(2, '0')}`;
  clockEl.textContent = timeStr;
  if (labelEl) labelEl.textContent = targetName;
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
