// OpenClaw Mission Control — Dashboard

let ws = null;
let reconnectTimer = null;
let pingInterval = null;
let lastState = null;

// Gateway control state
let _gwState = 'unknown';
let _gwBusy = false;
let _gwPollTimer = null;

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

// ── Gateway Control ─────────────────────────────────────────────────────────

async function refreshGatewayStatus() {
  try {
    const res = await fetch('/api/gateway/status');
    const data = await res.json();
    _gwState = data.state || 'unknown';

    const dot = document.getElementById('gwDot');
    const label = document.getElementById('gwLabel');
    const checked = document.getElementById('gwChecked');
    const btnStart = document.getElementById('gwBtnStart');
    const btnStop = document.getElementById('gwBtnStop');
    const btnRestart = document.getElementById('gwBtnRestart');

    // Update dot class
    dot.className = 'gw-dot gw-' + _gwState;

    // Update label
    const stateLabels = {
      running: 'Gateway · Running',
      stopped: 'Gateway · Stopped',
      error: 'Gateway · Error',
      unreachable: 'Gateway · Unreachable',
      unknown: 'Gateway · Unknown'
    };
    label.textContent = stateLabels[_gwState] || 'Gateway · ' + _gwState;

    // Update last-checked time
    const now = new Date();
    const timeStr = now.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
    checked.textContent = `(checked ${timeStr})`;

    // Update button states
    btnStart.disabled = _gwState === 'running' || _gwBusy;
    btnStop.disabled = _gwState === 'stopped' || _gwBusy;
    btnRestart.disabled = _gwBusy;
  } catch (e) {
    _gwState = 'unreachable';
    document.getElementById('gwDot').className = 'gw-dot gw-unreachable';
    document.getElementById('gwLabel').textContent = 'Gateway · Unreachable';
  }
}

async function gatewayAction(action) {
  if (_gwBusy) return;

  // Confirm for destructive actions
  if ((action === 'stop' || action === 'restart') && !confirm(`Are you sure you want to ${action} the gateway?`)) {
    return;
  }

  _gwBusy = true;
  const dot = document.getElementById('gwDot');
  const label = document.getElementById('gwLabel');
  const btnStart = document.getElementById('gwBtnStart');
  const btnStop = document.getElementById('gwBtnStop');
  const btnRestart = document.getElementById('gwBtnRestart');

  // Disable all buttons
  btnStart.disabled = true;
  btnStop.disabled = true;
  btnRestart.disabled = true;

  // Show busy state
  dot.className = 'gw-dot gw-busy';
  const actionLabels = { start: 'Starting...', stop: 'Stopping...', restart: 'Restarting...' };
  label.textContent = actionLabels[action] || 'Busy...';

  try {
    const method = action === 'start' ? 'POST' : 'POST';
    const endpoint = `/api/gateway/${action}`;
    const res = await fetch(endpoint, { method });
    const data = await res.json();

    if (!data.ok) {
      alert(`Failed to ${action} gateway:\n${data.stderr || data.message || 'Unknown error'}`);
    }

    // Refresh status after a short delay
    await new Promise(resolve => setTimeout(resolve, 1500));
    await refreshGatewayStatus();
  } catch (e) {
    alert(`Error: ${e.message}`);
    await refreshGatewayStatus();
  } finally {
    _gwBusy = false;
  }
}

function showGatewayBanner(message) {
  const banner = document.getElementById('gatewayBanner');
  const text = document.getElementById('gatewayBannerText');
  text.textContent = message;
  banner.style.display = 'flex';
}

function dismissGatewayBanner() {
  document.getElementById('gatewayBanner').style.display = 'none';
}

function startGatewayPolling() {
  refreshGatewayStatus();
  _gwPollTimer = setInterval(refreshGatewayStatus, 5000);
}

async function restartMissionControl() {
  if (!confirm('Restart Mission Control server? The page will reload automatically when it comes back up.')) return;
  const btn = document.getElementById('mcBtnRestart');
  btn.disabled = true;
  btn.textContent = '↺ Restarting…';
  try {
    await fetch('/api/server/restart', { method: 'POST' });
  } catch (_) {
    // Expected — server drops the connection during restart
  }
  // Poll until server responds again, then reload
  const poll = setInterval(async () => {
    try {
      const r = await fetch('/api/version');
      if (r.ok) {
        clearInterval(poll);
        location.reload();
      }
    } catch (_) { /* still restarting */ }
  }, 1000);
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
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;">
        <button class="agent-cog" onclick="showAgentDetails('${escHtml(a.role || '')}')" title="Agent details">⚙</button>
      </div>
      <div class="agent-card-role">${escHtml(a.role || '')}</div>
      <div class="agent-card-char">${escHtml(a.character || '—')}</div>
      <div class="agent-card-status">
        <span class="dot dot-${a.status || 'unknown'}"></span>
        <span>${statusLabel(a.status)}</span>
      </div>
      ${a.last_active ? `<div class="agent-card-time">${timeAgo(a.last_active)}</div>` : ''}
      <div class="agent-card-actions">
        <button class="agent-action-btn" onclick="chatWithAgent('${escHtml(a.role || '')}')" title="Open chat">💬</button>
        <button class="agent-action-btn" onclick="verifyAgent('${escHtml(a.role || '')}')" title="Verify responsive">✓</button>
        <button class="agent-action-btn" onclick="setAsMain('${escHtml(a.role || '')}')" title="Set as primary chat agent">★</button>
      </div>
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
  const details = tickets._details || {};
  const stale = tickets._stale || 0;
  board.innerHTML = TICKET_STATES.map(s => {
    const count = tickets[s] || 0;
    const cls = count > 0 ? 'has-items' : '';
    const items = details[s] || [];
    const clickable = count > 0 ? ' style="cursor:pointer" onclick="toggleKanbanDetail(this)"' : '';
    let itemsHtml = '';
    if (items.length > 0) {
      itemsHtml = `<div class="kanban-detail" style="display:none;margin-top:6px;font-size:12px;">` +
        items.map(t => {
          const staleTag = t.stale ? ' <span style="color:#f5a623;" title="Stale">⚠</span>' : '';
          return `<div style="padding:2px 0;border-top:1px solid var(--border);color:var(--text-muted);" title="${escHtml(t.file)}">${escHtml(t.title)}${staleTag}</div>`;
        }).join('') + '</div>';
    }
    return `
      <div class="kanban-col"${clickable}>
        <div class="kanban-col-title">
          <span>${s}</span>
          <span class="kanban-count ${cls}">${count}</span>
        </div>
        ${itemsHtml}
      </div>`;
  }).join('') + (stale > 0 ? `<div style="grid-column:1/-1;padding:6px 10px;background:#f5a62320;border:1px solid #f5a623;border-radius:6px;font-size:12px;color:#f5a623;margin-top:6px;">⚠ ${stale} ticket${stale > 1 ? 's' : ''} stale (in-progress or blocked &gt; 4 hours)</div>` : '');
}

function toggleKanbanDetail(col) {
  const detail = col.querySelector('.kanban-detail');
  if (detail) {
    detail.style.display = detail.style.display === 'none' ? 'block' : 'none';
  }
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

// ── Session Log ───────────────────────────────────────────────────────────

async function loadSessionLog() {
  const body = document.getElementById('sessionLogBody');
  body.innerHTML = '<p style="color:var(--text-muted);font-size:13px">Loading...</p>';
  try {
    const res = await fetch('/api/session-log');
    const data = await res.json();
    if (!data.rows || data.rows.length === 0) {
      body.innerHTML = '<p style="color:var(--text-muted);font-size:13px">No session log entries yet.</p>';
      return;
    }
    // Show most recent entries first (reversed), limit to 10
    const rows = data.rows.slice().reverse().slice(0, 10);
    let html = '<table style="width:100%;border-collapse:collapse;font-size:13px;">';
    html += '<tr style="border-bottom:1px solid var(--border);text-align:left;">';
    html += '<th style="padding:4px 8px;width:90px;">Date</th>';
    html += '<th style="padding:4px 8px;width:100px;">Agent</th>';
    html += '<th style="padding:4px 8px;">Items Completed</th></tr>';
    for (const r of rows) {
      html += '<tr style="border-bottom:1px solid var(--border);">';
      html += `<td style="padding:4px 8px;white-space:nowrap;color:var(--text-muted);">${escHtml(r.date)}</td>`;
      html += `<td style="padding:4px 8px;white-space:nowrap;">${escHtml(r.agent)}</td>`;
      html += `<td style="padding:4px 8px;">${escHtml(r.items)}</td>`;
      html += '</tr>';
    }
    html += '</table>';
    if (data.rows.length > 10) {
      html += `<p style="color:var(--text-muted);font-size:12px;margin-top:6px;">${data.rows.length - 10} older entries not shown</p>`;
    }
    body.innerHTML = html;
  } catch (e) {
    body.innerHTML = '<p style="color:var(--text-muted);font-size:13px">Could not load session log.</p>';
  }
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

// ── OpenClaw Sync ──────────────────────────────────────────────────────────

async function checkOpenclawSync() {
  const card = document.getElementById('openclawSyncCard');
  const body = document.getElementById('openclawSyncBody');
  if (!card || !body) return;
  try {
    const res = await fetch('/api/openclaw-workspace');
    const data = await res.json();
    card.style.display = 'block';
    if (data.match) {
      body.innerHTML = `<span class="badge-ok">✔ OpenClaw workspace matches Mission Control workspace</span>
        <span style="margin-left:12px;font-family:monospace;font-size:12px;">${escHtml(data.mc_workspace || '')}</span>`;
    } else {
      const ocPath = data.openclaw_workspace || '(not configured)';
      const mcPath = data.mc_workspace || '(unknown)';
      body.innerHTML = `
        <span class="badge-warn">⚠ Workspace path mismatch — agents may not appear in OpenClaw</span>
        <div style="margin-top:10px;display:flex;flex-direction:column;gap:5px;font-size:12px;">
          <div><span style="color:var(--text-muted);width:160px;display:inline-block;">OpenClaw workspace:</span><code>${escHtml(ocPath)}</code></div>
          <div><span style="color:var(--text-muted);width:160px;display:inline-block;">Mission Control:</span><code>${escHtml(mcPath)}</code></div>
        </div>
        <div style="margin-top:10px;font-size:12px;color:var(--text-muted);">
          Click "Re-register Agents" to write the correct workspace path to OpenClaw's config and re-register all agents.
        </div>`;
    }
  } catch (e) {
    // Non-critical — hide the card
  }
}

async function reregisterAgents() {
  const body = document.getElementById('openclawSyncBody');
  const btn = document.querySelector('#openclawSyncCard button');
  if (btn) { btn.disabled = true; btn.textContent = 'Registering…'; }

  try {
    // Get workspace path from current state
    const stateRes = await fetch('/api/state');
    const state = await stateRes.json();
    const workspace = state?.workspace || '';
    if (!workspace) {
      if (body) body.innerHTML = '<span class="badge-warn">⚠ No workspace path found in current state.</span>';
      return;
    }
    const res = await fetch('/api/reregister-agents', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: workspace }),
    });
    const data = await res.json();
    if (data.ok) {
      if (body) body.innerHTML = `<span class="badge-ok">✔ Re-registered ${data.registered} agents. OpenClaw workspace path updated.</span>`;
      setTimeout(checkOpenclawSync, 2000);
    } else {
      if (body) body.innerHTML = `<span class="badge-warn">⚠ Re-registration failed: ${escHtml(data.error || 'unknown error')}</span>`;
    }
  } catch (e) {
    if (body) body.innerHTML = '<span class="badge-warn">⚠ Could not reach server.</span>';
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Re-register Agents'; }
  }
}

// ── Agent Cleanup ──────────────────────────────────────────────────────────

async function loadAgentRegistry() {
  const card = document.getElementById('agentCleanupCard');
  const body = document.getElementById('agentCleanupBody');
  if (!card || !body) return;

  try {
    const res = await fetch('/api/agent-registry');
    if (!res.ok) {
      body.innerHTML = '<p style="color:var(--text-muted)">Unable to load agent registry.</p>';
      return;
    }
    const report = await res.json();

    // Only show card if there are orphaned/test agents
    const hasOrphaned = (report.orphaned || []).length > 0;
    const hasTest = (report.test || []).length > 0;
    const hasMissing = (report.missing || []).length > 0;

    if (!hasOrphaned && !hasTest && !hasMissing) {
      card.style.display = 'none';
      return;
    }

    card.style.display = 'block';
    let html = '';

    // Managed agents with chat status
    if ((report.managed || []).length > 0) {
      html += '<div style="margin-bottom:16px;"><h4 style="font-size:12px;font-weight:600;color:var(--text);margin-bottom:8px;text-transform:uppercase;">Managed Agents - Chat Status</h4>';
      for (const agent of report.managed) {
        const chatStatus = agent.chatAvailable ? '<span style="color:#4caf50;">✓ Chat available</span>' : '<span style="color:#f59e0b;">⚠ Not chat-routable</span>';
        const note = agent.chatNote ? `<div style="font-size:11px;color:var(--text-muted);margin-top:4px;">${escHtml(agent.chatNote)}</div>` : '';
        html += `<div style="padding:8px;background:var(--border);border-radius:4px;margin-bottom:6px;font-size:12px;">
          <div><strong>${escHtml(agent.displayName)}</strong> <span style="color:var(--text-muted);">(<code>${escHtml(agent.agentId)}</code>)</span></div>
          <div style="margin-top:4px;">${chatStatus}</div>
          ${note}
        </div>`;
      }
      html += '</div>';
    }

    // Orphaned agents
    if (hasOrphaned) {
      html += '<div style="margin-bottom:16px;"><h4 style="font-size:12px;font-weight:600;color:var(--text);margin-bottom:8px;text-transform:uppercase;">Orphaned Agents</h4>';
      for (const agent of report.orphaned) {
        html += `<div style="display:flex;justify-content:space-between;align-items:center;padding:8px;background:var(--border);border-radius:4px;margin-bottom:6px;font-size:12px;">
          <span><strong>${escHtml(agent.agentId)}</strong> <span style="color:var(--text-muted);">${agent.isEmpty ? '(empty)' : '(with sessions)'}</span></span>
          <div style="display:flex;gap:6px;">
            <button class="btn btn-sm" onclick="archiveAgent('${escHtml(agent.agentId)}')">Archive</button>
            <button class="btn btn-sm" onclick="purgeAgent('${escHtml(agent.agentId)}')">Remove</button>
          </div>
        </div>`;
      }
      html += '</div>';
    }

    // Test agents
    if (hasTest) {
      html += '<div style="margin-bottom:16px;"><h4 style="font-size:12px;font-weight:600;color:var(--text);margin-bottom:8px;text-transform:uppercase;">Test Agents</h4>';
      for (const agent of report.test) {
        html += `<div style="display:flex;justify-content:space-between;align-items:center;padding:8px;background:var(--border);border-radius:4px;margin-bottom:6px;font-size:12px;">
          <span><strong>${escHtml(agent.agentId)}</strong> <span style="color:var(--text-muted);">(${agent.category})</span></span>
          <div style="display:flex;gap:6px;">
            <button class="btn btn-sm" onclick="archiveAgent('${escHtml(agent.agentId)}')">Archive</button>
            <button class="btn btn-sm" onclick="purgeAgent('${escHtml(agent.agentId)}')">Remove</button>
          </div>
        </div>`;
      }
      html += '</div>';
    }

    // Missing agents
    if (hasMissing) {
      html += '<div><h4 style="font-size:12px;font-weight:600;color:var(--text);margin-bottom:8px;text-transform:uppercase;">Missing Agents</h4>';
      for (const agent of report.missing) {
        html += `<div style="padding:8px;background:var(--border);border-radius:4px;margin-bottom:6px;font-size:12px;color:var(--text-muted);">
          <strong>${escHtml(agent.displayName)}</strong> (${escHtml(agent.agentId)}) — expected by workspace but not registered
        </div>`;
      }
      html += '</div>';
    }

    body.innerHTML = html;
  } catch (e) {
    body.innerHTML = '<p style="color:var(--red)">Error loading agent registry.</p>';
  }
}

async function archiveAgent(agentId) {
  if (!confirm(`Archive agent ${agentId}? Its directory will be renamed with a timestamp, preserving session history.`)) return;
  try {
    const res = await fetch('/api/agents/cleanup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agentId, action: 'archive' }),
    });
    const data = await res.json();
    if (data.ok) {
      alert(`Agent ${agentId} archived.`);
      loadAgentRegistry();
    } else {
      alert(`Archive failed: ${data.error}`);
    }
  } catch (e) {
    alert(`Error: ${e.message}`);
  }
}

async function purgeAgent(agentId) {
  if (!confirm(`PERMANENTLY DELETE agent ${agentId} and all its files? This cannot be undone.`)) return;
  if (!confirm('Are you sure? This will remove all session history and state.')) return;
  try {
    const res = await fetch('/api/agents/cleanup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agentId, action: 'purge', confirm: true }),
    });
    const data = await res.json();
    if (data.ok) {
      alert(`Agent ${agentId} removed.`);
      loadAgentRegistry();
    } else {
      alert(`Removal failed: ${data.error}`);
    }
  } catch (e) {
    alert(`Error: ${e.message}`);
  }
}

// ── Agent Chat ─────────────────────────────────────────────────────────────

// Per-agent state: session IDs and message history
const _chatSessions = {};   // { agentId: sessionId | null }
const _chatHistory  = {};   // { agentId: [{role, text, model?}] }
let _chatAgent = null;      // currently open agent
let _chatBusy  = false;

function chatWithAgent(role) {
  _chatAgent = role;
  const a = _agentsData[role] || {};
  document.getElementById('chatModalTitle').textContent = `${a.character || role}`;
  _updateChatMeta();
  _renderChatHistory();
  document.getElementById('chatModalOverlay').classList.add('open');
  setTimeout(() => document.getElementById('chatInput').focus(), 100);
}

function closeChatModal(e) {
  if (e && e.target !== document.getElementById('chatModalOverlay')) return;
  document.getElementById('chatModalOverlay').classList.remove('open');
}

async function newChatSession() {
  if (!_chatAgent) return;
  // Notify server to clear session state
  try {
    await fetch(`/api/chat/session/${encodeURIComponent(_chatAgent)}`, { method: 'DELETE' });
  } catch (_) { /* best-effort */ }
  _chatSessions[_chatAgent] = null;
  _chatHistory[_chatAgent] = [];
  _renderChatHistory();
  _updateChatMeta();
  document.getElementById('chatInput').focus();
}

function _updateChatMeta() {
  const el = document.getElementById('chatModalMeta');
  if (!_chatAgent) { el.textContent = ''; return; }
  const sid = _chatSessions[_chatAgent];
  el.textContent = sid ? `Session: ${sid.substring(0, 8)}…` : 'New conversation';
}

function _renderChatHistory() {
  if (!_chatAgent) return;
  const msgs = _chatHistory[_chatAgent] || [];
  const container = document.getElementById('chatMessages');
  const empty = document.getElementById('chatEmpty');

  if (!msgs.length) {
    empty.style.display = '';
    container.querySelectorAll('.chat-msg,.chat-model-tag').forEach(el => el.remove());
    return;
  }

  empty.style.display = 'none';
  container.querySelectorAll('.chat-msg,.chat-model-tag').forEach(el => el.remove());

  for (const msg of msgs) {
    const div = document.createElement('div');
    div.className = `chat-msg chat-msg-${msg.role}`;
    div.textContent = msg.text;
    container.appendChild(div);
    if (msg.role === 'assistant' && msg.model) {
      const tag = document.createElement('div');
      tag.className = 'chat-model-tag';
      tag.textContent = msg.model;
      container.appendChild(tag);
    }
  }
  container.scrollTop = container.scrollHeight;
}

function chatInputKeydown(e) {
  // Send on Enter (not Shift+Enter)
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendChatMessage();
  }
}

function chatInputResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

async function sendChatMessage() {
  if (_chatBusy || !_chatAgent) return;
  const input = document.getElementById('chatInput');
  const message = input.value.trim();
  if (!message) return;

  input.value = '';
  input.style.height = '38px';
  _chatBusy = true;
  document.getElementById('chatSendBtn').disabled = true;

  // Add user message to history
  if (!_chatHistory[_chatAgent]) _chatHistory[_chatAgent] = [];
  _chatHistory[_chatAgent].push({ role: 'user', text: message });
  _renderChatHistory();

  // Show typing indicator
  const container = document.getElementById('chatMessages');
  const typing = document.createElement('div');
  typing.className = 'chat-typing';
  typing.id = 'chatTyping';
  typing.textContent = '···';
  container.appendChild(typing);
  container.scrollTop = container.scrollHeight;

  try {
    const res = await fetch('/api/chat/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        agentId: _chatAgent,
        message,
        sessionId: _chatSessions[_chatAgent] || null,
      }),
    });

    // Remove typing indicator
    document.getElementById('chatTyping')?.remove();

    if (!res.ok && res.status !== 200) {
      const errText = await res.text().catch(() => '');
      let errMsg = `Server error ${res.status}`;
      try { errMsg = JSON.parse(errText).error || errMsg; } catch (_) {}
      _chatHistory[_chatAgent].push({ role: 'error', text: `Error: ${errMsg}` });
      _renderChatHistory();
      return;
    }

    const data = await res.json();
    if (data.ok) {
      _chatSessions[_chatAgent] = data.sessionId;
      _chatHistory[_chatAgent].push({ role: 'assistant', text: data.response, model: data.model });
      _updateChatMeta();
    } else {
      _chatHistory[_chatAgent].push({ role: 'error', text: `Error: ${data.error || 'Agent returned no response'}` });
    }
    _renderChatHistory();
  } catch (e) {
    document.getElementById('chatTyping')?.remove();
    _chatHistory[_chatAgent].push({ role: 'error', text: `Network error: ${e.message}` });
    _renderChatHistory();
  } finally {
    _chatBusy = false;
    document.getElementById('chatSendBtn').disabled = false;
    input.focus();
  }
}

async function verifyAgent(role) {
  try {
    const btn = event.target;
    const originalText = btn.textContent;
    btn.textContent = '⏳';
    btn.disabled = true;

    const res = await fetch(`/api/agents/verify/${role}`, { method: 'POST' });
    const data = await res.json();

    if (data.ok) {
      btn.title = `Response: ${data.response.substring(0, 60)}...`;
      btn.textContent = '✓';
      setTimeout(() => {
        btn.textContent = originalText;
        btn.disabled = false;
        btn.title = 'Verify responsive';
      }, 3000);
    } else {
      btn.title = `Error: ${data.error}`;
      btn.textContent = '✗';
      setTimeout(() => {
        btn.textContent = originalText;
        btn.disabled = false;
        btn.title = 'Verify responsive';
      }, 3000);
    }
  } catch (e) {
    alert(`Error: ${e.message}`);
    const btn = event.target;
    btn.textContent = '✓';
    btn.disabled = false;
  }
}

async function setAsMain(role) {
  try {
    const btn = event.target;
    const originalText = btn.textContent;
    btn.textContent = '⏳';
    btn.disabled = true;

    const res = await fetch(`/api/agents/set-main/${role}`, { method: 'PUT' });
    const data = await res.json();

    if (data.ok) {
      btn.textContent = '★';
      showGatewayBanner('⚠ Gateway restart recommended — persona change may require it.');
      // Reload agent registry to show updated state
      setTimeout(() => {
        loadAgentRegistry();
      }, 1000);
    } else {
      alert(`Failed to promote ${role}: ${data.error}`);
      btn.textContent = originalText;
      btn.disabled = false;
    }
  } catch (e) {
    alert(`Error: ${e.message}`);
    const btn = event.target;
    btn.textContent = '★';
    btn.disabled = false;
  }
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
checkOpenclawSync();
loadAgentRegistry();
loadSessionLog();
startGatewayPolling();
