// OpenClaw Mission Control — Dashboard

let ws = null;
let reconnectTimer = null;
let pingInterval = null;
let lastState = null;

// ── WebSocket connection ───────────────────────────────────────────────────

function connect() {
  const wsUrl = `ws://${location.host}/ws`;
  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    setConnStatus(true);
    clearTimeout(reconnectTimer);
    // Send periodic pings to keep connection alive — clear any prior interval first
    clearInterval(pingInterval);
    pingInterval = setInterval(() => { if (ws.readyState === 1) ws.send('ping'); }, 20000);
  };

  ws.onmessage = (evt) => {
    try {
      const state = JSON.parse(evt.data);
      lastState = state;
      render(state);
    } catch (e) { /* ignore parse errors */ }
  };

  ws.onclose = () => {
    setConnStatus(false);
    clearInterval(pingInterval);
    reconnectTimer = setTimeout(connect, 3000);
  };

  ws.onerror = () => {
    setConnStatus(false);
  };
}

function setConnStatus(live) {
  document.getElementById('connDot').className = 'conn-dot ' + (live ? 'conn-live' : 'conn-off');
  document.getElementById('connLabel').textContent = live ? 'Live' : 'Reconnecting...';
}

// ── Render ─────────────────────────────────────────────────────────────────

function render(state) {
  const hasWorkspace = state && (state.active_project || Object.keys(state.agents || {}).length > 0);

  document.getElementById('noWorkspace').style.display = hasWorkspace ? 'none' : 'block';
  document.getElementById('dashboardContent').style.display = hasWorkspace ? 'block' : 'none';

  if (!hasWorkspace) return;

  renderAlerts(state.alerts || []);
  renderAgents(state.agents || {});
  renderProject(state.project || {}, state.active_project);
  renderTickets(state.tickets || {});
  renderActivity(state.activity || []);
  renderOvernight(state.overnight || {});
}

// ── Alerts ─────────────────────────────────────────────────────────────────

function renderAlerts(alerts) {
  const panel = document.getElementById('alertsPanel');
  const active = alerts.filter(a => !a.dismissed);
  if (!active.length) { panel.innerHTML = ''; return; }

  panel.innerHTML = active.slice(0, 5).map(a => `
    <div class="alert-strip alert-${a.level || 'info'}">
      <span>${levelIcon(a.level)}</span>
      <span><strong>${timeAgo(a.time)}</strong> — ${escHtml(a.message)}</span>
      <button class="alert-dismiss" onclick="dismissAlert('${a.id}')" title="Dismiss">×</button>
    </div>
  `).join('');
}

function levelIcon(level) {
  return { security: '🔴', warning: '⚠️', info: 'ℹ️' }[level] || 'ℹ️';
}

async function dismissAlert(id) {
  await fetch(`/api/alerts/dismiss/${id}`);
  if (lastState) {
    const a = (lastState.alerts || []).find(x => x.id === id);
    if (a) { a.dismissed = true; render(lastState); }
  }
}

// ── Agents ─────────────────────────────────────────────────────────────────

let _agentsData = {};

function renderAgents(agents) {
  _agentsData = agents;
  const grid = document.getElementById('agentGrid');
  const entries = Object.values(agents);

  if (!entries.length) {
    grid.innerHTML = '<p style="color:var(--text-muted);font-size:13px">No agents configured. Install a workspace to get started.</p>';
    return;
  }

  grid.innerHTML = entries.map(a => `
    <div class="agent-card">
      <button class="agent-cog" onclick="showAgentDetails('${escHtml(a.role || '')}')" title="Agent details">⚙</button>
      <div class="agent-card-role">${escHtml(a.role || '')}</div>
      <div class="agent-card-char">${escHtml(a.character || '—')}</div>
      <div class="agent-card-status">
        <span class="dot dot-${a.status || 'unknown'}"></span>
        <span>${statusLabel(a.status)}</span>
      </div>
      ${a.last_active ? `<div class="agent-card-time">${timeAgo(a.last_active)}</div>` : ''}
    </div>
  `).join('');
}

function statusLabel(s) {
  return { active: 'Active', idle: 'Idle', stalled: 'Stalled', unknown: 'Unknown' }[s] || 'Unknown';
}

function showAgentDetails(role) {
  const a = _agentsData[role];
  if (!a) return;
  document.getElementById('agentModalTitle').textContent = a.character || role;
  document.getElementById('agentModalRole').textContent = role.toUpperCase();

  const regBadge = a.openclaw_registered
    ? '<span class="badge-ok">✔ Registered</span>'
    : '<span class="badge-warn">✘ Not registered</span>';

  const rows = [
    ['Status',              statusLabel(a.status)],
    ['Last Active',         a.last_active ? timeAgo(a.last_active) : '—'],
    ['Model',               a.model || '—'],
    ['Workspace',           a.workspace_path || '—'],
    ['Launcher (Mac/Linux)', a.launcher_sh  || '—'],
    ['Launcher (Windows)',   a.launcher_bat || '—'],
    ['OpenClaw Agent Dir',   a.openclaw_dir || '—'],
    ['OpenClaw Registration', regBadge],
  ];

  document.getElementById('agentModalBody').innerHTML = rows.map(([label, value]) => `
    <div class="agent-modal-row">
      <div class="agent-modal-label">${escHtml(label)}</div>
      <div class="agent-modal-value">${value}</div>
    </div>
  `).join('');

  document.getElementById('agentModalOverlay').classList.add('open');
}

function closeAgentModal(e) {
  if (e && e.target !== document.getElementById('agentModalOverlay')) return;
  document.getElementById('agentModalOverlay').classList.remove('open');
}

// ── Project ────────────────────────────────────────────────────────────────

function renderProject(project, activeProject) {
  const banner = document.getElementById('projectBanner');
  const name = project.name || activeProject?.name || 'No project';
  const cur = project.milestone_current;
  const total = project.milestone_total;
  const pct = (cur && total) ? Math.round((cur / total) * 100) : 0;
  const updated = project.last_updated ? timeAgo(project.last_updated) : 'Never';

  banner.innerHTML = `
    <div>
      <div class="project-name">${escHtml(name)}</div>
      <div class="project-milestone">
        ${cur ? `Milestone ${cur}${total ? ' of ' + total : ''}` : 'No active milestone'}
        &nbsp;&bull;&nbsp; Updated ${updated}
      </div>
    </div>
    <div class="project-progress">
      <div class="progress-bar" style="height:10px">
        <div class="progress-fill" style="width:${pct}%"></div>
      </div>
      <div style="font-size:11px;color:var(--text-muted);margin-top:3px;text-align:right">${pct}%</div>
    </div>
  `;
}

// ── Tickets ────────────────────────────────────────────────────────────────

const TICKET_STATES = ['proposed','ready','in-progress','blocked','qa-failed','fixed','passed','released'];

function renderTickets(tickets) {
  const board = document.getElementById('kanbanBoard');
  board.innerHTML = TICKET_STATES.map(s => {
    const count = tickets[s] || 0;
    const cls = count > 0 ? 'has-items' : '';
    const colClass = s === 'blocked' || s === 'qa-failed' ? 'badge-red' : '';
    return `
      <div class="kanban-col">
        <div class="kanban-col-title">
          <span>${s}</span>
          <span class="kanban-count ${cls}">${count}</span>
        </div>
      </div>`;
  }).join('');
}

// ── Activity ───────────────────────────────────────────────────────────────

function renderActivity(activity) {
  const feed = document.getElementById('activityFeed');
  if (!activity.length) {
    feed.innerHTML = '<p style="color:var(--text-muted);font-size:13px">No recent activity.</p>';
    return;
  }
  feed.innerHTML = activity.slice(0, 20).map(a => `
    <div class="activity-item">
      <span class="activity-time">${timeAgo(a.time)}</span>
      <span class="activity-msg">${escHtml(a.message)}</span>
    </div>
  `).join('');
}

// ── Overnight ──────────────────────────────────────────────────────────────

function renderOvernight(overnight) {
  const panel = document.getElementById('overnightPanel');
  const on = overnight.enabled;
  const tonightCount = overnight.milestones_tonight || 0;
  const hasReport = overnight.report_available;

  panel.innerHTML = `
    <div class="overnight-indicator ${on ? 'overnight-on' : 'overnight-off'}">
      ${on ? '🌙 Night mode: ON' : '☀️ Night mode: OFF'}
    </div>
    ${on ? `<div>Milestones tonight: <strong>${tonightCount}</strong></div>` : ''}
    ${hasReport ? `<button class="btn btn-ghost" style="padding:4px 12px;font-size:12px" onclick="loadReport()">Read Morning Report</button>` : ''}
  `;
}

// ── Morning Report Modal ───────────────────────────────────────────────────

async function loadReport() {
  document.getElementById('morning-report-modal').style.display = 'block';
  document.getElementById('reportContent').textContent = 'Loading...';
  try {
    const res = await fetch('/api/morning-report');
    const data = await res.json();
    document.getElementById('reportContent').textContent = data.content || 'No report available.';
  } catch (e) {
    document.getElementById('reportContent').textContent = 'Could not load report.';
  }
}

function closeReport() {
  document.getElementById('morning-report-modal').style.display = 'none';
}

// ── Utilities ──────────────────────────────────────────────────────────────

function timeAgo(iso) {
  if (!iso) return '';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Version badge ──────────────────────────────────────────────────────────

fetch('/api/version')
  .then(r => r.json())
  .then(d => {
    const el = document.getElementById('versionBadge');
    if (el && d.version) el.textContent = `v${d.version}`;
  })
  .catch(() => {});

// ── Boot ───────────────────────────────────────────────────────────────────

// Initial state fetch (in case WebSocket is slow to connect)
fetch('/api/state')
  .then(r => r.json())
  .then(state => { if (!lastState) render(state); })
  .catch(() => {});

connect();
