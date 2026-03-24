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
      const data = JSON.parse(evt.data);
      if (data.type === 'team_chat') {
        // Real-time team chat update from file watcher
        if (data.messages && data.messages.length) {
          appendTeamChatMessages(data.messages);
        }
      } else {
        // Normal state broadcast
        lastState = data;
        render(data);
      }
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

function showGatewayBanner(message, action) {
  const banner = document.getElementById('gatewayBanner');
  const text = document.getElementById('gatewayBannerText');
  const btn = document.getElementById('gatewayBannerAction');
  text.textContent = message;
  if (action) {
    btn.textContent = action.label;
    btn.onclick = action.onclick;
    btn.style.display = '';
  } else {
    btn.style.display = 'none';
  }
  banner.style.display = 'flex';
}

function dismissGatewayBanner() {
  document.getElementById('gatewayBanner').style.display = 'none';
}

function startGatewayPolling() {
  refreshGatewayStatus();
  _gwPollTimer = setInterval(refreshGatewayStatus, 5000);
}

async function runDoctor() {
  const btn = document.getElementById('btnDoctor');
  const original = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '🩺 Running…';
  try {
    const res = await fetch('/api/doctor', { method: 'POST' });
    const data = await res.json();
    btn.disabled = false;
    btn.innerHTML = original;
    if (data.ok) {
      // Show results in a gateway banner
      const summary = data.output ? data.output.substring(0, 200) : 'Doctor completed.';
      showGatewayBanner('🩺 Doctor: ' + summary.replace(/\n/g, ' '));
      // Refresh gateway status after doctor runs
      setTimeout(refreshGatewayStatus, 1000);
    } else {
      showGatewayBanner('🩺 Doctor failed: ' + (data.error || 'Unknown error'));
    }
  } catch (e) {
    btn.disabled = false;
    btn.innerHTML = original;
    showGatewayBanner('🩺 Doctor: Could not connect to server.');
  }
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
  window._lastState = state;
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
  scheduleAssetRefresh();
}

// Throttled asset gallery refresh — re-fetches at most once per 30s on WS updates
let _assetRefreshTimer = null;
function scheduleAssetRefresh() {
  if (_assetRefreshTimer) return;
  _assetRefreshTimer = setTimeout(() => {
    _assetRefreshTimer = null;
    loadAssetGallery();
  }, 30000);
}

// ── Alerts ─────────────────────────────────────────────────────────────────

function renderAlerts(alerts) {
  const panel = document.getElementById('alertsPanel');
  const active = alerts.filter(a => !a.dismissed);
  if (!active.length) { panel.innerHTML = ''; return; }

  // Security alerts always show individually
  const security = active.filter(a => a.level === 'security');
  // Group non-security alerts into a collapsible summary
  const other = active.filter(a => a.level !== 'security');

  let html = security.map(a => `
    <div class="alert-strip alert-security">
      <span>${levelIcon(a.level)}</span>
      <span><strong>${timeAgo(a.time)}</strong> — ${escHtml(a.message)}</span>
      <button class="alert-dismiss" onclick="dismissAlert('${a.id}')" title="Dismiss">×</button>
    </div>
  `).join('');

  if (other.length === 1) {
    html += `
      <div class="alert-strip alert-${other[0].level || 'info'}">
        <span>${levelIcon(other[0].level)}</span>
        <span><strong>${timeAgo(other[0].time)}</strong> — ${escHtml(other[0].message)}</span>
        <button class="alert-dismiss" onclick="dismissAlert('${other[0].id}')" title="Dismiss">×</button>
      </div>`;
  } else if (other.length > 1) {
    const groupId = 'alertGroup';
    html += `
      <div class="alert-strip alert-warning" style="cursor:pointer" onclick="toggleAlertGroup()">
        <span>⚠️</span>
        <span><strong>${other.length} alerts</strong> — click to ${document.getElementById(groupId)?.style.display === 'block' ? 'hide' : 'expand'}</span>
        <button class="alert-dismiss" onclick="event.stopPropagation();dismissAllAlerts([${other.map(a => `'${a.id}'`).join(',')}])" title="Dismiss all">×</button>
      </div>
      <div id="${groupId}" style="display:none">
        ${other.slice(0, 10).map(a => `
          <div class="alert-strip alert-${a.level || 'info'}" style="margin-top:0;border-top:1px solid rgba(255,255,255,0.05)">
            <span>${levelIcon(a.level)}</span>
            <span><strong>${timeAgo(a.time)}</strong> — ${escHtml(a.message)}</span>
            <button class="alert-dismiss" onclick="event.stopPropagation();dismissAlert('${a.id}')" title="Dismiss">×</button>
          </div>
        `).join('')}
      </div>`;
  }

  panel.innerHTML = html;
}

function toggleAlertGroup() {
  const el = document.getElementById('alertGroup');
  if (el) el.style.display = el.style.display === 'block' ? 'none' : 'block';
}

async function dismissAllAlerts(ids) {
  for (const id of ids) await fetch(`/api/alerts/dismiss/${id}`);
  if (lastState) {
    for (const a of (lastState.alerts || [])) {
      if (ids.includes(a.id)) a.dismissed = true;
    }
    render(lastState);
  }
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
  // Update team chat agent selector with current agent data
  if (!Object.keys(_tcAgents).length && Object.keys(agents).length) {
    for (const [role, a] of Object.entries(agents)) {
      _tcAgents[role] = a.character || role;
    }
    _updateTcAgentSelect();
  }
  const grid = document.getElementById('agentGrid');
  const entries = Object.values(agents);

  if (!entries.length) {
    grid.innerHTML = '<p style="color:var(--text-muted);font-size:13px">No agents configured. Install a workspace to get started.</p>';
    return;
  }

  grid.innerHTML = entries.map(a => `
    <div class="agent-card">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;">
        <div style="flex:1;min-width:0;">
          <div class="agent-card-char">${escHtml(a.character || '—')}</div>
          <div class="agent-card-role">${escHtml(a.role_label || a.role || '')}</div>
        </div>
        <button class="agent-cog" onclick="showAgentDetails('${escHtml(a.role || '')}')" title="Agent details">⚙</button>
      </div>
      <div class="agent-card-status" style="margin-top:8px;">
        <span class="dot dot-${a.status || 'inactive'}"></span>
        <span>${statusLabel(a.status)}</span>
      </div>
      ${a.last_active ? `<div class="agent-card-time">${timeAgo(a.last_active)}</div>` : ''}
      <div class="agent-card-actions">
        <button class="agent-action-btn" onclick="chatWithAgent('${escHtml(a.role || '')}')" title="Open chat — send messages to this agent from Mission Control">💬</button>
        <button class="agent-action-btn" onclick="verifyAgent('${escHtml(a.role || '')}')" title="Verify — sends a test message to check if this agent is responding">✓</button>
        <button class="agent-action-btn" onclick="setAsMain('${escHtml(a.role || '')}')" title="Set as Main — makes this agent the default chat entrypoint in the OpenClaw app">★</button>
      </div>
      <div style="font-size:10px;color:var(--text-muted);margin-top:6px;font-family:monospace;opacity:0.6;">${escHtml(a.agentId || a.role || '')}</div>
    </div>
  `).join('') + `
    <div class="agent-card" style="display:flex;align-items:center;justify-content:center;cursor:pointer;opacity:0.5;transition:opacity 0.15s" onclick="showAddAgentModal()" onmouseover="this.style.opacity='0.8'" onmouseout="this.style.opacity='0.5'" title="Add a new agent">
      <div style="text-align:center">
        <div style="font-size:28px;line-height:1">+</div>
        <div style="font-size:11px;color:var(--text-muted);margin-top:4px">Add Agent</div>
      </div>
    </div>`;
}

function statusLabel(s) {
  return { active: 'Active', idle: 'Idle', stalled: 'Stalled', inactive: 'Inactive', offline: 'Inactive', unknown: 'Inactive' }[s] || 'Inactive';
}

let _availableModels = null; // cached after first fetch

async function _ensureModels() {
  if (_availableModels) return _availableModels;
  try {
    const res = await fetch('/api/configured-models');
    const configured = (await res.json()).models || [];
    // Only show models that are actually configured/authenticated in OpenClaw
    _availableModels = configured.map(m => {
      const id = m.id || m;
      return { id, label: m.label || id, provider: m.provider || '' };
    });
  } catch (_) {
    _availableModels = [];
  }
  return _availableModels;
}

async function showAgentDetails(role) {
  const a = _agentsData[role];
  if (!a) return;
  document.getElementById('agentModalTitle').textContent = a.character || role;
  document.getElementById('agentModalRole').textContent = role.toUpperCase();

  const regBadge = a.openclaw_registered
    ? '<span class="badge-ok">✔ Registered</span>'
    : '<span class="badge-warn">✘ Not registered</span>';

  // Build model selector
  const models = await _ensureModels();
  const currentModel = a.model || '—';
  let modelOptions = models.map(m =>
    `<option value="${escHtml(m.id)}" ${m.id === currentModel ? 'selected' : ''}>${escHtml(m.label || m.id)}</option>`
  ).join('');
  // If current model isn't in the list, add it
  if (!models.find(m => m.id === currentModel) && currentModel !== '—') {
    modelOptions = `<option value="${escHtml(currentModel)}" selected>${escHtml(currentModel)}</option>` + modelOptions;
  }
  const modelHtml = `
    <div style="display:flex;align-items:center;gap:8px;">
      <select id="agentModelSelect" style="flex:1;padding:4px 8px;font-size:12px;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:4px;">
        ${modelOptions}
      </select>
      <button class="btn btn-ghost" style="padding:3px 10px;font-size:11px;" onclick="changeAgentModel('${escHtml(role)}')">Save</button>
    </div>`;

  const rows = [
    ['Agent ID',            `<code>${escHtml(a.agentId || a.role || '')}</code>`],
    ['Display Name',        escHtml(a.character || '—')],
    ['Role',                escHtml(a.role_label || a.role || '')],
    ['Status',              statusLabel(a.status)],
    ['Last Active',         a.last_active ? timeAgo(a.last_active) : '—'],
    ['Model',               modelHtml],
    ['Created',             a.created_at || '—'],
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
  `).join('') + `
    <div style="border-top:1px solid var(--border);margin-top:10px;padding-top:10px;">
      <button class="btn btn-ghost" style="width:100%;padding:6px 0;font-size:12px;" onclick="showBulkModelChange()">Change model for ALL agents</button>
    </div>`;

  document.getElementById('agentModalOverlay').classList.add('open');
}

async function changeAgentModel(role) {
  const sel = document.getElementById('agentModelSelect');
  if (!sel) return;
  const newModel = sel.value;
  try {
    const res = await fetch('/api/agents/model', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role, model: newModel }),
    });
    const data = await res.json();
    if (data.ok) {
      showGatewayBanner(`Model updated for ${role}: ${newModel}`);
      // Update local cache so modal reflects change immediately
      if (_agentsData[role]) _agentsData[role].model = newModel;
    } else {
      alert('Failed: ' + (data.error || 'Unknown error'));
    }
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

async function showBulkModelChange() {
  const models = await _ensureModels();
  const currentFirst = Object.values(_agentsData)[0]?.model || '';
  let opts = models.map(m =>
    `<option value="${escHtml(m.id)}" ${m.id === currentFirst ? 'selected' : ''}>${escHtml(m.label || m.id)}</option>`
  ).join('');
  if (currentFirst && !models.find(m => m.id === currentFirst)) {
    opts = `<option value="${escHtml(currentFirst)}" selected>${escHtml(currentFirst)}</option>` + opts;
  }
  const modalBody = document.getElementById('agentModalBody');
  modalBody.innerHTML = `
    <div style="padding:10px 0;">
      <p style="font-size:13px;margin-bottom:10px;">Switch <strong>every agent</strong> to a single model. Use this to move the whole team to a local/free model.</p>
      <div style="display:flex;align-items:center;gap:8px;">
        <select id="bulkModelSelect" style="flex:1;padding:6px 8px;font-size:13px;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:4px;">
          ${opts}
        </select>
      </div>
      <div style="display:flex;gap:8px;margin-top:12px;">
        <button class="btn" style="flex:1;padding:6px 0;font-size:13px;" onclick="applyBulkModelChange()">Apply to All Agents</button>
        <button class="btn btn-ghost" style="padding:6px 12px;font-size:13px;" onclick="closeAgentModal()">Cancel</button>
      </div>
    </div>`;
  document.getElementById('agentModalTitle').textContent = 'Change All Models';
  document.getElementById('agentModalRole').textContent = '';
}

async function applyBulkModelChange() {
  const sel = document.getElementById('bulkModelSelect');
  if (!sel) return;
  const newModel = sel.value;
  const agentCount = Object.keys(_agentsData).length;
  if (!confirm(`Switch all ${agentCount} agents to "${newModel}"?`)) return;
  try {
    const res = await fetch('/api/agents/model/bulk', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: newModel }),
    });
    const data = await res.json();
    if (data.ok) {
      showGatewayBanner(`All agents switched to ${newModel}`);
      // Update local cache
      for (const role of Object.keys(_agentsData)) {
        _agentsData[role].model = newModel;
      }
      closeAgentModal();
    } else {
      alert('Failed: ' + (data.error || 'Unknown error'));
    }
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

function closeAgentModal(e) {
  if (e && e.target !== document.getElementById('agentModalOverlay')) return;
  document.getElementById('agentModalOverlay').classList.remove('open');
}

// ── Add Agent ──────────────────────────────────────────────────────────────

// Role ID → Label mapping (matches template_deployer.py ROLE_LABELS)
const ROLE_LABELS = {
  pm: 'Project Manager',
  architect: 'Architect',
  builder: 'Builder / Developer',
  qa: 'QA / Test Engineer',
  security: 'Security Engineer',
  devops: 'DevOps / Release',
  ux: 'UX / Documentation',
  research: 'Research Agent',
  graphics: 'Graphics Designer',
};

let _swapMode = false;  // true when replacing an existing agent's identity

function showAddAgentModal() {
  document.getElementById('addAgentRole').value = '';
  document.getElementById('addAgentName').value = '';
  document.getElementById('addAgentLabel').value = '';
  document.getElementById('addAgentError').style.display = 'none';
  document.getElementById('imageGenSetup').style.display = 'none';
  document.getElementById('customRoleRow').style.display = 'none';
  document.getElementById('addAgentCustomRole').value = '';
  _imageGenSetupShown = false;
  _swapMode = false;
  _updateSwapNotice('');
  document.getElementById('addAgentSubmitBtn').textContent = 'Add Agent';
  document.getElementById('addAgentOverlay').classList.add('open');
}

function _getExistingAgent(role) {
  if (!role || !lastState || !lastState.agents) return null;
  return lastState.agents[role] || null;
}

function _updateSwapNotice(role) {
  let notice = document.getElementById('addAgentSwapNotice');
  if (!notice) return;
  const btn = document.getElementById('addAgentSubmitBtn');
  const existing = _getExistingAgent(role);
  if (existing) {
    const char = existing.character || existing.displayName || role;
    notice.innerHTML = `<span style="color:var(--yellow);">⚠</span> A <strong>${ROLE_LABELS[role] || role}</strong> already exists: <strong>${escHtml(char)}</strong>. Submitting will swap their identity.`;
    notice.style.display = 'block';
    btn.textContent = 'Swap Identity';
    _swapMode = true;
  } else {
    notice.style.display = 'none';
    btn.textContent = 'Add Agent';
    _swapMode = false;
  }
}

function closeAddAgentModal(e) {
  if (e && e.target !== document.getElementById('addAgentOverlay')) return;
  document.getElementById('addAgentOverlay').classList.remove('open');
}

// ── Image Gen Setup for Graphics Agent ────────────────────────────────────

let _imageGenSpecsCache = null;
let _imageGenModelStatus = null;
let _imageGenSetupShown = false;

function onAddAgentRoleSelect(val) {
  const customRow = document.getElementById('customRoleRow');
  const labelInput = document.getElementById('addAgentLabel');

  if (val === '_custom') {
    customRow.style.display = 'block';
    labelInput.value = '';
    _onRoleResolved('');
    _updateSwapNotice('');
    return;
  }

  customRow.style.display = 'none';
  document.getElementById('addAgentCustomRole').value = '';

  // Auto-populate the label
  if (val && ROLE_LABELS[val]) {
    labelInput.value = ROLE_LABELS[val];
  } else {
    labelInput.value = '';
  }

  _onRoleResolved(val);
  _updateSwapNotice(val);
}

function onCustomRoleInput(val) {
  const role = val.trim().toLowerCase().replace(/[^a-z0-9-]/g, '');
  const labelInput = document.getElementById('addAgentLabel');
  // Auto-generate a label from the custom role ID: "data-eng" → "Data Eng"
  if (role) {
    labelInput.value = role.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  } else {
    labelInput.value = '';
  }
  _onRoleResolved(role);
}

function _onRoleResolved(role) {
  const panel = document.getElementById('imageGenSetup');
  if (role === 'graphics') {
    panel.style.display = 'block';
    if (!_imageGenSetupShown) {
      _imageGenSetupShown = true;
      loadImageGenSetup();
    }
  } else {
    panel.style.display = 'none';
  }
}

function _getSelectedRole() {
  const select = document.getElementById('addAgentRole').value;
  if (select === '_custom') {
    return document.getElementById('addAgentCustomRole').value.trim().toLowerCase().replace(/[^a-z0-9-]/g, '');
  }
  return select;
}

async function loadImageGenSetup() {
  const specsEl = document.getElementById('imageGenSpecs');
  const depsEl = document.getElementById('imageGenDeps');
  const modelsEl = document.getElementById('imageGenModels');

  try {
    // Fetch hardware specs, deps status, and installed models in parallel
    const [specsRes, depsRes, statusRes] = await Promise.all([
      fetch('/api/system/specs'),
      fetch('/api/image-models/deps'),
      fetch('/api/image-models/status'),
    ]);
    const specs = await specsRes.json();
    const depsData = await depsRes.json();
    const status = await statusRes.json();
    _imageGenSpecsCache = specs;
    _imageGenModelStatus = status.installed || [];

    // Show hardware summary
    const gpu = specs.gpu || 'Integrated';
    const metal = specs.metal ? ` | Metal: ${specs.metal}` : '';
    specsEl.innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px 16px;margin-bottom:4px;">
        <span>RAM: <strong>${specs.ram_gb || '?'} GB</strong></span>
        <span>Chip: <strong>${specs.chip || 'Unknown'}</strong></span>
        <span>GPU: <strong>${gpu}</strong>${metal}</span>
        <span>Disk Free: <strong>${specs.disk_free_gb || '?'} GB</strong></span>
      </div>
    `;

    // Show Python deps status
    const deps = depsData.deps || {};
    const coreDeps = ['torch', 'diffusers', 'transformers', 'accelerate'];
    const allInstalled = coreDeps.every(d => deps[d] && deps[d].installed);

    if (allInstalled) {
      const versions = coreDeps.map(d => `${d} ${deps[d].version}`).join(', ');
      depsEl.innerHTML = `
        <div style="font-size:12px;color:#4caf50;padding:6px 10px;border:1px solid #4caf5040;border-radius:4px;background:#4caf5010;">
          Ready for local image generation <span style="opacity:0.5;margin-left:4px;" title="${versions}">(hover for versions)</span>
        </div>`;
    } else {
      depsEl.innerHTML = `
        <div style="font-size:12px;padding:8px 10px;border:1px solid var(--border);border-radius:4px;display:flex;justify-content:space-between;align-items:center;"
             title="Local image generation needs PyTorch and Diffusers installed on this machine. This is a one-time setup — click Install to download them automatically.">
          <div>
            <div style="color:var(--yellow);font-weight:500;">Setup required for local image generation</div>
            <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">One-time install of AI image libraries (~2-4 GB download)</div>
            <div style="font-size:11px;color:var(--text-muted);">This lets the graphics agent generate images on this machine for free.</div>
          </div>
          <button class="btn" style="padding:4px 14px;font-size:12px;flex-shrink:0;" onclick="installImageDeps(this)">Install</button>
        </div>`;
    }

    // Show recommended models
    const models = specs.image_models || [];
    const installedIds = _imageGenModelStatus.map(m => m.id);

    if (models.length === 0) {
      modelsEl.innerHTML = '<div style="font-size:12px;color:var(--text-muted);">No compatible image models found for this hardware.</div>';
      return;
    }

    modelsEl.innerHTML = models.map(m => {
      const isInstalled = installedIds.includes(m.id);
      const isCloud = m.cloud;
      const recBadge = m.recommended ? '<span style="background:#4caf50;color:#fff;font-size:10px;padding:1px 6px;border-radius:8px;margin-left:6px;">Recommended</span>' : '';
      const makerLine = m.maker ? `by ${m.maker} &mdash; ` : '';
      const sizeLine = isCloud ? 'Cloud-based' : `${m.size_gb} GB download`;
      const whyLine = m.why ? `<div style="font-size:11px;color:var(--text-muted);margin-top:3px;font-style:italic;">${m.why}</div>` : '';
      const statusBadge = isInstalled
        ? '<span style="color:#4caf50;font-weight:600;font-size:11px;">Installed</span>'
        : isCloud
          ? '<span style="font-size:11px;color:var(--text-muted);">API key required</span>'
          : `<button class="btn" style="padding:2px 10px;font-size:11px;" onclick="installImageModel('${m.id}', this)">Install</button>`;

      return `
        <div style="padding:8px 10px;border:1px solid var(--border);border-radius:4px;background:var(--bg-card);">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;">
            <div style="flex:1;min-width:0;">
              <div style="font-size:13px;font-weight:500;">${m.name}${recBadge}</div>
              <div style="font-size:11px;color:var(--text-muted);">${makerLine}${m.description}</div>
              <div style="font-size:11px;color:var(--text-muted);">${sizeLine} | ${m.speed} | Quality: ${m.quality}</div>
            </div>
            <div style="flex-shrink:0;margin-left:10px;padding-top:2px;">${statusBadge}</div>
          </div>
          ${whyLine}
        </div>
      `;
    }).join('');

  } catch (e) {
    specsEl.innerHTML = `<div style="color:var(--red);font-size:12px;">Failed to detect hardware: ${e.message}</div>`;
  }
}

async function installImageDeps(btn) {
  const statusEl = document.getElementById('imageGenStatus');
  btn.disabled = true;
  btn.textContent = 'Installing...';
  statusEl.style.display = 'block';
  statusEl.style.color = 'var(--text-muted)';
  statusEl.textContent = 'Installing PyTorch + Diffusers... This may take several minutes.';

  try {
    const res = await fetch('/api/image-models/install-deps', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    if (res.status === 404) {
      btn.disabled = false;
      btn.textContent = 'Install';
      statusEl.innerHTML = 'Mission Control needs to be restarted to enable this feature. '
        + '<strong>Restart MC</strong>, then try again.';
      statusEl.style.color = 'var(--yellow)';
      return;
    }
    const data = await res.json();
    if (data.ok) {
      statusEl.textContent = 'Image libraries installed successfully.';
      statusEl.style.color = '#4caf50';
      _imageGenSetupShown = false;
      _imageGenSetupShown = true;
      loadImageGenSetup();
    } else {
      btn.disabled = false;
      btn.textContent = 'Retry';
      const errMsg = data.error || 'Install failed — check the terminal for details.';
      statusEl.innerHTML = `Install failed: ${errMsg.length > 200 ? errMsg.slice(0, 200) + '...' : errMsg}`
        + '<div style="margin-top:4px;font-size:10px;opacity:0.7;">Try running manually: pip install torch diffusers transformers accelerate</div>';
      statusEl.style.color = 'var(--red)';
    }
  } catch (e) {
    btn.disabled = false;
    btn.textContent = 'Retry';
    statusEl.innerHTML = `Could not reach Mission Control: ${e.message}`
      + '<div style="margin-top:4px;font-size:10px;opacity:0.7;">Make sure Mission Control is running and try again.</div>';
    statusEl.style.color = 'var(--red)';
  }
}

async function installImageModel(modelId, btn) {
  const statusEl = document.getElementById('imageGenStatus');
  btn.disabled = true;
  btn.textContent = 'Downloading...';
  statusEl.style.display = 'block';
  statusEl.textContent = `Downloading ${modelId}... This may take several minutes.`;

  try {
    const res = await fetch('/api/image-models/install', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_id: modelId }),
    });
    const data = await res.json();
    if (data.ok) {
      btn.textContent = 'Installed';
      btn.style.color = '#4caf50';
      btn.style.borderColor = '#4caf50';
      statusEl.textContent = data.already_installed
        ? `${modelId} was already installed.`
        : `${modelId} installed successfully at ${data.path}`;
      // Refresh the setup panel to reflect new state
      _imageGenSetupShown = false;
      _imageGenSetupShown = true;
      loadImageGenSetup();
    } else {
      btn.disabled = false;
      btn.textContent = 'Retry';
      btn.style.color = 'var(--red)';
      statusEl.textContent = `Install failed: ${data.error || 'Unknown error'}`;
      statusEl.style.color = 'var(--red)';
    }
  } catch (e) {
    btn.disabled = false;
    btn.textContent = 'Retry';
    statusEl.textContent = `Install error: ${e.message}`;
    statusEl.style.color = 'var(--red)';
  }
}

async function submitAddAgent() {
  const role = _getSelectedRole();
  const name = document.getElementById('addAgentName').value.trim();
  const label = document.getElementById('addAgentLabel').value.trim();
  const errEl = document.getElementById('addAgentError');

  if (!role) {
    errEl.textContent = 'Please select a role.';
    errEl.style.display = 'block';
    return;
  }
  if (!name) {
    errEl.textContent = 'Display Name is required.';
    errEl.style.display = 'block';
    return;
  }

  const endpoint = _swapMode ? '/api/agents/swap' : '/api/agents/add';

  try {
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role, name, label: label || name }),
    });
    if (!res.ok && res.headers.get('content-type')?.indexOf('application/json') === -1) {
      errEl.textContent = `Server error (${res.status})`;
      errEl.style.display = 'block';
      return;
    }
    const data = await res.json();
    if (data.ok) {
      closeAddAgentModal();
      if (_swapMode) {
        showGatewayBanner(data.message || `Swapped ${role} identity to ${name}`);
      }
      refreshGatewayStatus();
      setTimeout(() => location.reload(), 1000);
    } else {
      errEl.textContent = data.error || 'Failed.';
      errEl.style.display = 'block';
    }
  } catch (e) {
    errEl.textContent = `Error: ${e.message}`;
    errEl.style.display = 'block';
  }
}

// ── Theme Switcher ─────────────────────────────────────────────────────────

let _themesCache = null;

async function loadThemes() {
  if (_themesCache) return _themesCache;
  try {
    const res = await fetch('/api/themes');
    _themesCache = await res.json();
    return _themesCache;
  } catch { return []; }
}

async function showThemeSwitcher() {
  const overlay = document.getElementById('themeSwitcherOverlay');
  const select = document.getElementById('themeSwitcherSelect');
  const preview = document.getElementById('themeRosterPreview');
  const errEl = document.getElementById('themeSwitcherError');
  const applyBtn = document.getElementById('themeSwitcherApplyBtn');

  errEl.style.display = 'none';
  preview.style.display = 'none';
  applyBtn.disabled = true;
  select.innerHTML = '<option value="">Loading themes...</option>';
  overlay.style.display = 'flex';

  const themes = await loadThemes();
  select.innerHTML = '<option value="">Select a theme...</option>' +
    themes.map(t => `<option value="${t.id}">${escHtml(t.label)}</option>`).join('');
}

function closeThemeSwitcher(e) {
  if (e && e.target !== document.getElementById('themeSwitcherOverlay')) return;
  document.getElementById('themeSwitcherOverlay').style.display = 'none';
}

function previewThemeRoster(themeId) {
  const preview = document.getElementById('themeRosterPreview');
  const applyBtn = document.getElementById('themeSwitcherApplyBtn');

  if (!themeId || !_themesCache) {
    preview.style.display = 'none';
    applyBtn.disabled = true;
    return;
  }

  const theme = _themesCache.find(t => t.id === themeId);
  if (!theme || !theme.roles) {
    preview.style.display = 'none';
    applyBtn.disabled = true;
    return;
  }

  // Show roster preview: role → character mapping
  const rows = Object.entries(theme.roles).map(([role, char]) => {
    const label = ROLE_LABELS[role] || role;
    const current = _getExistingAgent(role);
    const currentChar = current ? (current.character || current.displayName || '—') : null;
    const changed = currentChar && currentChar !== char;
    return `<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;border-bottom:1px solid var(--border);font-size:12px;">
      <span style="color:var(--text-muted);min-width:120px;">${escHtml(label)}</span>
      <span style="font-weight:500;">${escHtml(char)}</span>
      ${currentChar ? `<span style="font-size:10px;color:${changed ? 'var(--yellow)' : 'var(--green)'};min-width:80px;text-align:right;">${changed ? '← ' + escHtml(currentChar) : '(same)'}</span>` : ''}
    </div>`;
  }).join('');

  preview.innerHTML = rows;
  preview.style.display = 'block';
  applyBtn.disabled = false;
}

async function applyTheme() {
  const select = document.getElementById('themeSwitcherSelect');
  const errEl = document.getElementById('themeSwitcherError');
  const applyBtn = document.getElementById('themeSwitcherApplyBtn');
  const themeId = select.value;

  if (!themeId) return;

  applyBtn.disabled = true;
  applyBtn.textContent = 'Applying...';

  try {
    const res = await fetch('/api/theme/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme: themeId }),
    });
    const data = await res.json();
    if (data.ok) {
      closeThemeSwitcher();
      showGatewayBanner(data.message || `Applied ${data.label} theme`, { label: 'Restart Gateway', onclick: () => gatewayAction('restart') });
      setTimeout(() => location.reload(), 1500);
    } else {
      errEl.textContent = data.error || 'Failed to apply theme.';
      errEl.style.display = 'block';
      applyBtn.disabled = false;
      applyBtn.textContent = 'Apply Theme';
    }
  } catch (e) {
    errEl.textContent = `Error: ${e.message}`;
    errEl.style.display = 'block';
    applyBtn.disabled = false;
    applyBtn.textContent = 'Apply Theme';
  }
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

// ── Project Switching ──────────────────────────────────────────────────

let _projectsList = [];

async function loadProjects() {
  const sel = document.getElementById('projectSelect');
  if (!sel) return;
  try {
    const res = await fetch('/api/projects');
    const data = await res.json();
    _projectsList = data.projects || [];
    sel.innerHTML = '';
    // Cloned projects first, then uncloned GH repos separated by a divider
    const cloned = _projectsList.filter(p => p.cloned);
    const uncloned = _projectsList.filter(p => !p.cloned);
    for (const p of cloned) {
      const opt = document.createElement('option');
      opt.value = p.name;
      const prefix = p.source === 'github' ? '[GH] ' : '';
      opt.textContent = prefix + p.name;
      if (p.name === data.active) opt.selected = true;
      sel.appendChild(opt);
    }
    if (uncloned.length > 0) {
      const divider = document.createElement('option');
      divider.disabled = true;
      divider.textContent = '── GitHub (not cloned) ──';
      sel.appendChild(divider);
      for (const p of uncloned) {
        const opt = document.createElement('option');
        opt.value = p.name;
        opt.textContent = '[GH] ' + p.name;
        opt.dataset.uncloned = 'true';
        opt.dataset.url = p.remote_url || '';
        sel.appendChild(opt);
      }
    }
  } catch (_) {}
}

/** Switch active-project.md and reload. No clone-check — project must already exist on disk. */
async function _activateProject(name) {
  try {
    const res = await fetch('/api/projects/switch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    const data = await res.json();
    if (data.ok) setTimeout(() => location.reload(), 300);
  } catch (_) {}
}

async function switchProject(name) {
  if (!name) return;
  // If this is an uncloned GH repo, clone it first then activate
  const proj = _projectsList.find(p => p.name === name);
  if (proj && !proj.cloned && proj.remote_url) {
    if (!confirm(`"${name}" hasn't been cloned yet. Clone it from GitHub now?`)) {
      loadProjects(); // reset dropdown
      return;
    }
    try {
      showGatewayBanner(`Cloning ${name}...`);
      const res = await fetch('/api/projects/clone', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo_url: proj.remote_url, name: name }),
      });
      const data = await res.json();
      if (!data.ok) {
        alert('Clone failed: ' + (data.error || 'Unknown error'));
        loadProjects();
        return;
      }
      showGatewayBanner(`Cloned ${name} successfully`);
      // Mark as cloned in memory so _activateProject won't re-trigger this branch
      proj.cloned = true;
    } catch (e) {
      alert('Clone error: ' + e.message);
      loadProjects();
      return;
    }
  }
  await _activateProject(name);
}

function showNewProjectModal() {
  const overlay = document.getElementById('newProjectOverlay');
  if (overlay) overlay.style.display = 'flex';
  switchProjectTab('local');
}

function closeNewProjectModal(e) {
  if (e && e.target !== e.currentTarget) return;
  const overlay = document.getElementById('newProjectOverlay');
  if (overlay) overlay.style.display = 'none';
}

function switchProjectTab(tab) {
  document.getElementById('projTabLocal').className = tab === 'local' ? 'tab-btn active' : 'tab-btn';
  document.getElementById('projTabGithub').className = tab === 'github' ? 'tab-btn active' : 'tab-btn';
  document.getElementById('projPanelLocal').style.display = tab === 'local' ? 'block' : 'none';
  document.getElementById('projPanelGithub').style.display = tab === 'github' ? 'block' : 'none';
  if (tab === 'github' && !_ghReposCache) loadGithubRepos();
}

async function createProject() {
  const name = document.getElementById('newProjectName').value.trim();
  if (!name) return;
  const btn = document.getElementById('createLocalBtn');
  btn.disabled = true; btn.textContent = 'Creating...';
  try {
    const res = await fetch('/api/projects/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    const data = await res.json();
    if (data.ok) {
      closeNewProjectModal();
      document.getElementById('newProjectName').value = '';
      await _activateProject(name); // project just created on disk — skip clone-check
    } else {
      alert(data.error || 'Failed to create project');
    }
  } catch (e) {
    alert(`Error: ${e.message}`);
  } finally {
    btn.disabled = false; btn.textContent = 'Create';
  }
}

// ── GitHub Clone ──────────────────────────────────────────────────────────

let _ghReposCache = null;
let _ghSelectedRepo = null;

async function loadGithubRepos() {
  const list = document.getElementById('ghRepoList');
  const err = document.getElementById('ghError');
  err.style.display = 'none';
  list.innerHTML = '<div style="color:var(--text-muted);padding:12px;">Loading repos...</div>';
  try {
    const res = await fetch('/api/github/repos');
    const data = await res.json();
    if (!data.ok) {
      err.textContent = data.error + (data.install_hint ? ` — ${data.install_hint}` : '');
      err.style.display = 'block';
      list.innerHTML = '';
      return;
    }
    _ghReposCache = data.repos || [];
    renderGhRepoList(_ghReposCache);
  } catch (e) {
    err.textContent = `Error: ${e.message}`;
    err.style.display = 'block';
    list.innerHTML = '';
  }
}

function filterGhRepos(query) {
  if (!_ghReposCache) return;
  const q = query.toLowerCase();
  const filtered = _ghReposCache.filter(r =>
    r.name.toLowerCase().includes(q) || (r.description || '').toLowerCase().includes(q)
  );
  renderGhRepoList(filtered);
}

function renderGhRepoList(repos) {
  const list = document.getElementById('ghRepoList');
  if (!repos.length) {
    list.innerHTML = '<div style="color:var(--text-muted);padding:12px;">No repos found.</div>';
    return;
  }
  list.innerHTML = repos.map(r => `
    <div style="padding:8px 10px;border-bottom:1px solid var(--border);cursor:pointer;display:flex;justify-content:space-between;align-items:center;"
         onclick="selectGhRepo('${escHtml(r.name)}', '${escHtml(r.url)}')">
      <div style="min-width:0;flex:1;">
        <div style="font-weight:600;font-size:13px;">${escHtml(r.name)}${r.isPrivate ? ' <span style="font-size:10px;color:var(--text-muted);">private</span>' : ''}</div>
        ${r.description ? `<div style="font-size:11px;color:var(--text-muted);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escHtml(r.description)}</div>` : ''}
      </div>
      <span style="font-size:11px;color:var(--accent);white-space:nowrap;margin-left:12px;">Select</span>
    </div>
  `).join('');
}

function selectGhRepo(name, url) {
  _ghSelectedRepo = { name, url };
  document.getElementById('ghSelectedName').textContent = name;
  document.getElementById('ghCloneName').value = '';
  document.getElementById('ghRepoSelected').style.display = 'block';
}

async function cloneGithubRepo() {
  if (!_ghSelectedRepo) return;
  const nameOverride = document.getElementById('ghCloneName').value.trim();
  const btn = document.getElementById('ghCloneBtn');
  btn.disabled = true; btn.textContent = 'Cloning...';
  try {
    const res = await fetch('/api/projects/clone', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        repo_url: _ghSelectedRepo.url,
        name: nameOverride || null,
      }),
    });
    const data = await res.json();
    if (data.ok) {
      closeNewProjectModal();
      _ghSelectedRepo = null;
      await _activateProject(data.name); // project is already on disk — skip clone-check
    } else {
      alert(data.error || 'Clone failed');
    }
  } catch (e) {
    alert(`Error: ${e.message}`);
  } finally {
    btn.disabled = false; btn.textContent = 'Clone & Create Project';
  }
}

// Legacy aliases for backward compatibility
function showNewProjectInput() { showNewProjectModal(); }
function hideNewProjectInput() { closeNewProjectModal(); }

// ── Asset Gallery ──────────────────────────────────────────────────────────

let _assetsCache = [];
let _assetFilter = 'all';
let _previewAssetPath = '';
let _galleryCollapsed = false;

function toggleAssetGallery() {
  _galleryCollapsed = !_galleryCollapsed;
  const body = document.getElementById('assetGalleryBody');
  const arrow = document.getElementById('assetGalleryArrow');
  const controls = document.getElementById('assetGalleryControls');
  body.style.display = _galleryCollapsed ? 'none' : 'block';
  controls.style.display = _galleryCollapsed ? 'none' : 'flex';
  arrow.classList.toggle('open', !_galleryCollapsed);
}

async function loadAssetGallery() {
  const card = document.getElementById('assetGalleryCard');
  const grid = document.getElementById('assetGalleryGrid');
  const empty = document.getElementById('assetGalleryEmpty');
  const filter = document.getElementById('assetCategoryFilter');

  try {
    const res = await fetch('/api/assets');
    const data = await res.json();
    _assetsCache = data.assets || [];

    if (!data.project) {
      card.style.display = 'none';
      return;
    }
    card.style.display = 'block';
    const activeAssets = _assetsCache.filter(a => !a.rejected);
    const countEl = document.getElementById('assetGalleryCount');
    countEl.textContent = activeAssets.length > 0 ? `(${activeAssets.length})` : '';

    if (_assetsCache.length === 0) {
      grid.style.display = 'none';
      empty.style.display = 'block';
      return;
    }
    grid.style.display = 'grid';
    empty.style.display = 'none';

    // Build category filter options (exclude "rejected" pseudo-category)
    const categories = [...new Set(activeAssets.map(a => a.category))].sort();
    filter.innerHTML = '<option value="all">All (' + activeAssets.length + ')</option>' +
      categories.map(c => {
        const count = activeAssets.filter(a => a.category === c).length;
        return `<option value="${c}">${c} (${count})</option>`;
      }).join('');
    filter.value = _assetFilter;

    renderAssetGrid();
  } catch (e) {
    card.style.display = 'block';
    grid.innerHTML = `<div style="grid-column:1/-1;color:var(--red);font-size:12px;">Failed to load assets: ${e.message}</div>`;
  }
}

function filterAssets(val) {
  _assetFilter = val;
  renderAssetGrid();
}

function _assetCard(a, isRejected) {
  const isSvg = a.ext === '.svg';
  const thumbUrl = `/api/assets/file/${encodeURIComponent(a.path).replace(/%2F/g, '/')}`;
  const sizeLabel = a.size_kb >= 1024 ? `${(a.size_kb/1024).toFixed(1)} MB` : `${a.size_kb} KB`;
  const timeLabel = timeAgo(a.modified);
  const dimStyle = isRejected ? 'opacity:0.5;' : '';
  return `
    <div class="asset-thumb" onclick="previewAsset('${escHtml(a.path)}', '${escHtml(a.name)}')"
         style="cursor:pointer;border:1px solid var(--border);border-radius:6px;overflow:hidden;background:var(--bg);transition:border-color 0.15s;${dimStyle}"
         onmouseover="this.style.borderColor='var(--accent)'" onmouseout="this.style.borderColor='var(--border)'">
      <div style="width:100%;aspect-ratio:1;display:flex;align-items:center;justify-content:center;background:#0d1117;overflow:hidden;">
        <img src="${thumbUrl}" loading="lazy" style="width:100%;height:100%;object-fit:${isSvg ? 'contain' : 'cover'};${isSvg ? 'padding:8px;box-sizing:border-box;' : ''}" alt="${escHtml(a.name)}">
      </div>
      <div style="padding:6px 8px;">
        <div style="font-size:11px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${escHtml(a.name)}">${escHtml(a.name)}</div>
        <div style="font-size:10px;color:var(--text-muted);">${sizeLabel} · ${timeLabel}</div>
      </div>
    </div>`;
}

let _rejectedExpanded = false;

function renderAssetGrid() {
  const grid = document.getElementById('assetGalleryGrid');
  const activeAssets = _assetsCache.filter(a => !a.rejected);
  const rejectedAssets = _assetsCache.filter(a => a.rejected);

  const filtered = _assetFilter === 'all'
    ? activeAssets
    : activeAssets.filter(a => a.category === _assetFilter);

  let html = '';

  if (filtered.length === 0 && rejectedAssets.length === 0) {
    grid.innerHTML = '<div style="grid-column:1/-1;color:var(--text-muted);font-size:12px;text-align:center;padding:12px;">No assets in this category.</div>';
    return;
  }

  // Group active assets by category when viewing All
  if (_assetFilter === 'all' && filtered.length > 0) {
    const cats = [...new Set(filtered.map(a => a.category))].sort();
    html += cats.map(cat => {
      const items = filtered.filter(a => a.category === cat);
      return `<div style="grid-column:1/-1;margin-top:8px;padding:4px 0;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;">
          <span style="font-size:12px;font-weight:600;text-transform:capitalize;color:var(--text);">${escHtml(cat)}</span>
          <span style="font-size:10px;color:var(--text-muted);">${items.length} file${items.length !== 1 ? 's' : ''}</span>
        </div>` + items.map(a => _assetCard(a)).join('');
    }).join('');
  } else if (filtered.length > 0) {
    html += filtered.map(a => _assetCard(a)).join('');
  } else {
    html += '<div style="grid-column:1/-1;color:var(--text-muted);font-size:12px;text-align:center;padding:12px;">No assets in this category.</div>';
  }

  // Rejected section — collapsed by default, shown at the bottom
  if (rejectedAssets.length > 0) {
    const rejLabel = _rejectedExpanded ? '▾' : '▸';
    const rejItemsHtml = _rejectedExpanded
      ? rejectedAssets.map(a => _assetCard(a, true)).join('')
      : '';
    html += `
      <div style="grid-column:1/-1;margin-top:16px;padding:6px 0;border-top:1px solid var(--border);display:flex;align-items:center;gap:8px;cursor:pointer;opacity:0.6;"
           onclick="toggleRejectedAssets()">
        <span style="font-size:11px;">${rejLabel}</span>
        <span style="font-size:11px;font-weight:600;color:var(--text-muted);">Rejected (${rejectedAssets.length})</span>
        <span style="font-size:10px;color:var(--text-muted);">click to ${_rejectedExpanded ? 'hide' : 'show'}</span>
      </div>
      ${rejItemsHtml}`;
  }

  grid.innerHTML = html;
}

function toggleRejectedAssets() {
  _rejectedExpanded = !_rejectedExpanded;
  renderAssetGrid();
}

function previewAsset(path, name) {
  const overlay = document.getElementById('assetPreviewOverlay');
  const img = document.getElementById('assetPreviewImg');
  const title = document.getElementById('assetPreviewTitle');
  const info = document.getElementById('assetPreviewInfo');

  _previewAssetPath = path;
  const asset = _assetsCache.find(a => a.path === path);
  title.textContent = name;
  img.src = `/api/assets/file/${encodeURIComponent(path)}`;

  if (asset) {
    const sizeLabel = asset.size_kb >= 1024 ? `${(asset.size_kb/1024).toFixed(1)} MB` : `${asset.size_kb} KB`;
    info.innerHTML = `
      <div style="display:flex;gap:16px;flex-wrap:wrap;">
        <span>Path: <strong>${escHtml(asset.path)}</strong></span>
        <span>Size: <strong>${sizeLabel}</strong></span>
        <span>Category: <strong>${escHtml(asset.category)}</strong></span>
        <span>Modified: <strong>${timeAgo(asset.modified)}</strong></span>
      </div>
    `;
  }
  overlay.classList.add('open');
}

function closeAssetPreview() {
  document.getElementById('assetPreviewOverlay').classList.remove('open');
  document.getElementById('assetPreviewImg').src = '';
  _previewAssetPath = '';
}

async function rejectAsset() {
  if (!_previewAssetPath) return;
  const reason = prompt('Why are you rejecting this asset? (The graphics agent can read this feedback)');
  if (reason === null) return; // cancelled
  try {
    const res = await fetch('/api/assets/reject', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: _previewAssetPath, reason }),
    });
    const data = await res.json();
    if (data.ok) {
      closeAssetPreview();
      loadAssetGallery();
    } else {
      alert('Reject failed: ' + (data.error || 'Unknown'));
    }
  } catch (e) {
    alert('Reject failed: ' + e.message);
  }
}

async function acceptAsset() {
  if (!_previewAssetPath) return;
  const reason = prompt('Optional: why do you like this asset? (The graphics agent can read this feedback)\n\nLeave blank and click OK to accept without a note.');
  if (reason === null) return; // cancelled
  try {
    const res = await fetch('/api/assets/accept', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: _previewAssetPath, reason: reason || '' }),
    });
    const data = await res.json();
    if (data.ok) {
      closeAssetPreview();
    } else {
      alert('Accept failed: ' + (data.error || 'Unknown'));
    }
  } catch (e) {
    alert('Accept failed: ' + e.message);
  }
}

async function commitAssets() {
  if (!confirm('Commit and push all assets to the GitHub repo?')) return;
  try {
    const res = await fetch('/api/assets/commit', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    const data = await res.json();
    if (data.ok) {
      const msg = data.committed
        ? `Committed ${data.committed} file(s).${data.pushed ? ' Pushed to GitHub.' : ' Push failed: ' + (data.push_error || 'unknown')}`
        : data.message;
      alert(msg);
    } else {
      alert('Error: ' + (data.error || 'Unknown'));
    }
  } catch (e) {
    alert('Commit failed: ' + e.message);
  }
}

async function pushProjectToGitHub() {
  const msg = prompt('Commit message (leave blank for auto-generated):');
  if (msg === null) return; // cancelled
  try {
    const res = await fetch('/api/projects/push', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg }),
    });
    const data = await res.json();
    if (data.ok) {
      const info = data.committed
        ? `Committed ${data.committed} file(s).${data.pushed ? ' Pushed to GitHub.' : ' Push failed: ' + (data.push_error || 'unknown')}`
        : data.message;
      alert(info);
    } else if (data.not_git_repo) {
      // Project has no GitHub connection yet — offer to publish
      showPublishModal(data.project_name || '');
    } else {
      alert('Push failed: ' + (data.error || 'Unknown'));
    }
  } catch (e) {
    alert('Push failed: ' + e.message);
  }
}

function showPublishModal(projectName) {
  document.getElementById('publishRepoName').value = projectName;
  document.getElementById('publishCommitMsg').value = '';
  document.getElementById('publishError').style.display = 'none';
  document.getElementById('publishBtn').disabled = false;
  document.getElementById('publishBtn').textContent = 'Create & Push';
  document.getElementById('publishOverlay').style.display = 'flex';
  setTimeout(() => document.getElementById('publishRepoName').focus(), 100);
}

function closePublishModal(e) {
  if (e && e.target !== e.currentTarget) return;
  document.getElementById('publishOverlay').style.display = 'none';
}

async function submitPublish() {
  const repoName = document.getElementById('publishRepoName').value.trim();
  const commitMsg = document.getElementById('publishCommitMsg').value.trim();
  const isPrivate = document.getElementById('publishPrivate').checked;
  const errEl = document.getElementById('publishError');
  const btn = document.getElementById('publishBtn');

  if (!repoName) {
    errEl.textContent = 'Repository name is required.';
    errEl.style.display = 'block';
    return;
  }

  errEl.style.display = 'none';
  btn.disabled = true;
  btn.textContent = 'Publishing…';

  try {
    const res = await fetch('/api/projects/publish', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_name: repoName, private: isPrivate, commit_message: commitMsg }),
    });
    const data = await res.json();
    if (data.ok) {
      closePublishModal();
      showGatewayBanner(`Published! "${data.repo_name}" created on GitHub.`);
      await _activateProject(document.getElementById('publishRepoName').value.trim() || data.repo_name);
    } else {
      errEl.textContent = data.error || 'Publish failed.';
      errEl.style.display = 'block';
      btn.disabled = false;
      btn.textContent = 'Create & Push';
    }
  } catch (e) {
    errEl.textContent = 'Network error: ' + e.message;
    errEl.style.display = 'block';
    btn.disabled = false;
    btn.textContent = 'Create & Push';
  }
}

// ── Tickets ────────────────────────────────────────────────────────────────

const TICKET_STATES = ['proposed','ready','in-progress','blocked','qa-failed','fixed','passed','released'];
const TICKET_STATE_TIPS = {
  'proposed': 'Ticket created but not yet approved for work. Needs triage/prioritization.',
  'ready': 'Approved and scoped — an agent can pick it up.',
  'in-progress': 'An agent is actively working on it. Stale warning if untouched >4 hours.',
  'blocked': 'Work started but can\'t continue (dependency, question, external blocker).',
  'qa-failed': 'QA reviewed and found issues — needs rework by the assignee.',
  'fixed': 'Developer believes it\'s done — waiting for QA validation.',
  'passed': 'QA confirmed it works — ready for release.',
  'released': 'Shipped. Terminal state.',
};

function renderTickets(tickets) {
  const board = document.getElementById('kanbanBoard');
  const details = tickets._details || {};
  const stale = tickets._stale || 0;
  board.innerHTML = TICKET_STATES.map(s => {
    const count = tickets[s] || 0;
    const cls = count > 0 ? 'has-items' : '';
    const items = details[s] || [];
    const clickable = count > 0 ? ' style="cursor:pointer" onclick="toggleKanbanDetail(this)"' : '';
    const arrow = count > 0 ? '<span class="kanban-arrow">&#9654;</span>' : '';
    let itemsHtml = '';
    if (items.length > 0) {
      itemsHtml = `<div class="kanban-detail" style="display:none;margin-top:6px;font-size:12px;">` +
        items.map(t => {
          const staleTag = t.stale ? ' <span style="color:#f5a623;" title="Stale">⚠</span>' : '';
          const sevTag = t.severity ? `<span class="badge badge-${sevColor(t.severity)}" style="margin-left:6px;font-size:10px">${escHtml(t.severity)}</span>` : '';
          const desc = t.description ? `<div style="color:var(--text-muted);font-size:11px;margin-top:2px;line-height:1.4;">${escHtml(t.description.substring(0, 120))}${t.description.length > 120 ? '…' : ''}</div>` : '';
          const by = t.found_by ? `<div style="font-size:10px;color:var(--text-muted);opacity:0.7;margin-top:2px;">— ${escHtml(t.found_by)}</div>` : '';
          const tBadge = typeBadge(t.type);
          const epicTag = t.epic ? `<span style="font-size:9px;color:#9b59b6;margin-left:6px;" title="Epic: ${escHtml(t.epic)}">[${escHtml(t.epic)}]</span>` : '';
          return `<div style="padding:6px 0;border-top:1px solid var(--border);" title="${escHtml(t.file)}">
            <div style="display:flex;align-items:center;">${tBadge}${escHtml(t.title)}${staleTag}${sevTag}${epicTag}</div>
            ${desc}${by}
          </div>`;
        }).join('') + '</div>';
    }
    return `
      <div class="kanban-col"${clickable}>
        <div class="kanban-col-title" title="${TICKET_STATE_TIPS[s] || ''}">
          ${arrow}<span>${s}</span>
          <span class="kanban-count ${cls}">${count}</span>
        </div>
        ${itemsHtml}
      </div>`;
  }).join('') + (stale > 0 ? `<div style="grid-column:1/-1;padding:6px 10px;background:#f5a62320;border:1px solid #f5a623;border-radius:6px;font-size:12px;color:#f5a623;margin-top:6px;">⚠ ${stale} ticket${stale > 1 ? 's' : ''} stale (in-progress or blocked &gt; 4 hours)</div>` : '');
}

function toggleKanbanDetail(col) {
  const detail = col.querySelector('.kanban-detail');
  const arrow = col.querySelector('.kanban-arrow');
  if (detail) {
    const open = detail.style.display === 'none';
    detail.style.display = open ? 'block' : 'none';
    if (arrow) arrow.classList.toggle('open', open);
  }
}

// ── New Ticket ────────────────────────────────────────────────────────────

function showNewTicketModal() {
  const overlay = document.getElementById('newTicketOverlay');
  if (overlay) overlay.style.display = 'flex';
}

function closeNewTicketModal(e) {
  if (e && e.target !== e.currentTarget) return;
  const overlay = document.getElementById('newTicketOverlay');
  if (overlay) overlay.style.display = 'none';
}

function toggleSeverityField() {
  const type = document.getElementById('ticketType').value;
  const sevRow = document.getElementById('ticketSeverityRow');
  if (sevRow) sevRow.style.display = type === 'BUG' ? 'block' : 'none';
}

async function submitNewTicket() {
  const type = document.getElementById('ticketType').value;
  const title = document.getElementById('ticketTitle').value.trim();
  const desc = document.getElementById('ticketDesc').value.trim();
  const priority = document.getElementById('ticketPriority').value;
  const severity = document.getElementById('ticketSeverity')?.value || '—';
  const epic = document.getElementById('ticketEpic')?.value.trim() || '—';
  if (!title) { alert('Title is required'); return; }
  const btn = document.getElementById('ticketSubmitBtn');
  btn.disabled = true; btn.textContent = 'Creating...';
  try {
    const res = await fetch('/api/tickets/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticket_type: type, title, description: desc, priority, severity, epic }),
    });
    const data = await res.json();
    if (data.ok) {
      closeNewTicketModal();
      document.getElementById('ticketTitle').value = '';
      document.getElementById('ticketDesc').value = '';
    } else {
      alert(data.error || 'Failed to create ticket');
    }
  } catch (e) {
    alert(`Error: ${e.message}`);
  } finally {
    btn.disabled = false; btn.textContent = 'Create Ticket';
  }
}

// ── Activity ───────────────────────────────────────────────────────────────

let _activityExpanded = false;

function renderActivity(activity) {
  const feed = document.getElementById('activityFeed');
  if (!activity.length) {
    feed.innerHTML = '<p style="color:var(--text-muted);font-size:13px">No recent activity.</p>';
    return;
  }
  const all = activity.slice(0, 20);
  const visible = _activityExpanded ? all : all.slice(0, 5);
  const hasMore = all.length > 5;
  feed.innerHTML = visible.map(a => `
    <div class="activity-item">
      <span class="activity-time">${timeAgo(a.time)}</span>
      <span class="activity-msg">${escHtml(a.message)}</span>
    </div>
  `).join('') + (hasMore ? `
    <button class="btn btn-ghost" style="width:100%;padding:4px 0;font-size:11px;margin-top:4px;" onclick="toggleActivity()">
      ${_activityExpanded ? 'Show less' : `Show all (${all.length})`}
    </button>` : '');
}

function toggleActivity() {
  _activityExpanded = !_activityExpanded;
  const state = window._lastState;
  if (state) renderActivity(state.activity || []);
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

// ── System Info ────────────────────────────────────────────────────────────

async function loadSysInfo() {
  const osEl = document.getElementById('sysinfoOs');
  const pyEl = document.getElementById('sysinfoPython');
  const diskEl = document.getElementById('sysinfoDisk');
  if (!osEl || !pyEl || !diskEl) return;

  try {
    const res = await fetch('/api/sysinfo');
    if (!res.ok) throw new Error('bad response');
    const data = await res.json();
    osEl.textContent = data.os || '—';
    pyEl.textContent = data.python || '—';
    const used = data.disk?.used_gb;
    const total = data.disk?.total_gb;
    if (typeof used === 'number' && typeof total === 'number') {
      diskEl.textContent = `${used} / ${total} GB`;
    } else {
      diskEl.textContent = '—';
    }
  } catch (e) {
    osEl.textContent = 'Unavailable';
    pyEl.textContent = 'Unavailable';
    diskEl.textContent = 'Unavailable';
  }
}

// ── Skills ─────────────────────────────────────────────────────────────

async function loadSkills() {
  const body = document.getElementById('skillsBody');
  if (!body) return;
  body.innerHTML = '<p style="color:var(--text-muted);font-size:13px">Loading...</p>';
  try {
    const res = await fetch('/api/skills');
    if (!res.ok) throw new Error('bad response');
    const data = await res.json();
    if (!data.ok) {
      body.innerHTML = `<p style="color:var(--text-muted);">${escHtml(data.error || 'Could not load skills')}</p>`;
      return;
    }
    const ready = (data.skills || []).filter(s => s.ready);
    const missing = (data.skills || []).filter(s => !s.ready);
    let html = `<div style="margin-bottom:8px;"><span style="font-weight:600;color:var(--green);">${data.ready_count}</span> / ${data.total_count} ready</div>`;
    if (ready.length > 0) {
      html += '<div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px;">';
      for (const s of ready) {
        html += `<span class="badge badge-green" title="${escHtml(s.description)}">${escHtml(s.name)}</span>`;
      }
      html += '</div>';
    }
    if (missing.length > 0) {
      html += `<details style="margin-top:4px;"><summary style="cursor:pointer;font-size:12px;color:var(--text-muted);">${missing.length} missing skills</summary>`;
      html += '<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:6px;">';
      for (const s of missing) {
        html += `<span class="badge badge-gray" title="${escHtml(s.description)}">${escHtml(s.name)}</span>`;
      }
      html += '</div></details>';
    }
    body.innerHTML = html;
  } catch (e) {
    body.innerHTML = '<p style="color:var(--text-muted);font-size:13px">Could not load skills.</p>';
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

function sevColor(sev) {
  if (!sev) return 'gray';
  const s = sev.toLowerCase();
  if (s.includes('d1') || s.includes('critical')) return 'red';
  if (s.includes('d2') || s.includes('high')) return 'yellow';
  if (s.includes('d3') || s.includes('medium')) return 'blue';
  return 'gray';
}

function typeColor(type) {
  switch ((type || '').toUpperCase()) {
    case 'BUG': return '#e74c3c';
    case 'FEAT': return '#3498db';
    case 'TASK': return '#95a5a6';
    case 'QUESTION': return '#f39c12';
    case 'EPIC': return '#9b59b6';
    default: return '#95a5a6';
  }
}

function typeBadge(type) {
  if (!type) return '';
  const color = typeColor(type);
  return `<span style="display:inline-block;font-size:9px;font-weight:700;color:#fff;background:${color};padding:1px 5px;border-radius:3px;margin-right:6px;letter-spacing:0.5px;">${escHtml(type)}</span>`;
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

// ── Workspace Backups ──────────────────────────────────────────────────

async function loadBackups() {
  const body = document.getElementById('backupsBody');
  if (!body) return;
  body.innerHTML = '<p style="color:var(--text-muted);font-size:13px">Loading...</p>';
  try {
    const res = await fetch('/api/backups');
    const data = await res.json();
    const backups = data.backups || [];
    if (backups.length === 0) {
      body.innerHTML = '<p style="color:var(--text-muted);font-size:13px">No backups yet. Click "Save Backup" to create one.</p>';
      return;
    }
    let html = '<div style="display:flex;flex-direction:column;gap:6px;">';
    for (const b of backups) {
      html += `<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 10px;background:var(--bg);border:1px solid var(--border);border-radius:4px;">
        <div>
          <div style="font-weight:500;font-size:13px;">${escHtml(b.workspace_name)}</div>
          <div style="font-size:11px;color:var(--text-muted);">${escHtml(b.timestamp)} · ${b.file_count} files</div>
        </div>
        <div style="display:flex;gap:6px;">
          <button class="btn btn-ghost" style="padding:3px 10px;font-size:11px;" onclick="browseBackup('${escHtml(b.id)}')">Browse</button>
          <button class="btn btn-ghost" style="padding:3px 10px;font-size:11px;" onclick="restoreBackup('${escHtml(b.id)}')">Restore</button>
          <button class="btn btn-ghost" style="padding:3px 10px;font-size:11px;color:var(--red);" onclick="deleteBackup('${escHtml(b.id)}')">Delete</button>
        </div>
      </div>`;
    }
    html += '</div>';
    body.innerHTML = html;
  } catch (e) {
    body.innerHTML = '<p style="color:var(--text-muted);font-size:13px">Could not load backups.</p>';
  }
}

async function saveBackup() {
  if (!confirm('Save a snapshot of the current workspace? This will create a timestamped copy in ~/.openclaw-mission-control/backups/')) return;
  try {
    const res = await fetch('/api/backups/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    const data = await res.json();
    if (data.ok) {
      showGatewayBanner(`Backup saved: ${data.backup_id} (${data.file_count} files)`);
      loadBackups();
      // Show file list in a confirmation modal
      const files = data.files || [];
      showBackupFilesModal(data.backup_id, files.map(f => ({path: f, size: null})), true);
    } else {
      alert('Backup failed: ' + (data.error || 'Unknown error'));
    }
  } catch (e) {
    alert('Backup error: ' + e.message);
  }
}

async function restoreBackup(backupId) {
  if (!confirm(`Restore workspace from backup "${backupId}"?\n\nA safety backup of the current state will be created first.`)) return;
  if (!confirm('This will overwrite all current workspace files. Are you sure?')) return;
  try {
    const res = await fetch('/api/backups/restore', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ backup_id: backupId }),
    });
    const data = await res.json();
    if (data.ok) {
      showGatewayBanner(`Restored from ${data.restored_from}. Safety backup: ${data.safety_backup}`);
      setTimeout(() => location.reload(), 1500);
    } else {
      alert('Restore failed: ' + (data.error || 'Unknown error'));
    }
  } catch (e) {
    alert('Restore error: ' + e.message);
  }
}

async function deleteBackup(backupId) {
  if (!confirm(`Delete backup "${backupId}"? This cannot be undone.`)) return;
  try {
    const res = await fetch(`/api/backups/${encodeURIComponent(backupId)}`, { method: 'DELETE' });
    const data = await res.json();
    if (data.ok) {
      loadBackups();
    } else {
      alert('Delete failed: ' + (data.error || 'Unknown error'));
    }
  } catch (e) {
    alert('Delete error: ' + e.message);
  }
}

async function browseBackup(backupId) {
  try {
    const res = await fetch(`/api/backups/${encodeURIComponent(backupId)}/files`);
    const data = await res.json();
    if (data.ok) {
      showBackupFilesModal(backupId, data.files, false);
    } else {
      alert('Browse failed: ' + (data.error || 'Unknown error'));
    }
  } catch (e) {
    alert('Browse error: ' + e.message);
  }
}

function showBackupFilesModal(backupId, files, isSaveConfirmation) {
  let overlay = document.getElementById('backupBrowseOverlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'backupBrowseOverlay';
    overlay.className = 'modal-overlay';
    overlay.onclick = (e) => { if (e.target === overlay) closeBackupBrowse(); };
    document.body.appendChild(overlay);
  }
  const title = isSaveConfirmation ? `Backup Saved — ${files.length} files` : `Browse Backup — ${files.length} files`;
  const subtitle = isSaveConfirmation ? `<div style="color:var(--green);font-size:12px;margin-bottom:8px;">Snapshot saved as <strong>${escHtml(backupId)}</strong></div>` : '';

  // Build file tree grouped by top-level directory
  const tree = {};
  for (const f of files) {
    const parts = f.path.split('/');
    const dir = parts.length > 1 ? parts[0] : '.';
    if (!tree[dir]) tree[dir] = [];
    tree[dir].push(f);
  }

  let fileListHtml = '';
  for (const [dir, dirFiles] of Object.entries(tree).sort((a, b) => a[0].localeCompare(b[0]))) {
    if (dir === '.') {
      for (const f of dirFiles) {
        fileListHtml += `<div class="backup-file-row" onclick="viewBackupFile('${escHtml(backupId)}','${escHtml(f.path)}')" title="Click to view">
          <span style="color:var(--text);">${escHtml(f.path)}</span>
          ${f.size != null ? `<span style="color:var(--text-muted);font-size:10px;">${formatSize(f.size)}</span>` : ''}
        </div>`;
      }
    } else {
      fileListHtml += `<div class="backup-dir-row" onclick="toggleBackupDir(this)">
        <span class="kanban-arrow">&#9654;</span>
        <span style="font-weight:500;">${escHtml(dir)}/</span>
        <span style="color:var(--text-muted);font-size:10px;margin-left:auto;">${dirFiles.length} files</span>
      </div>
      <div class="backup-dir-children" style="display:none;">`;
      for (const f of dirFiles) {
        fileListHtml += `<div class="backup-file-row" onclick="viewBackupFile('${escHtml(backupId)}','${escHtml(f.path)}')" title="Click to view">
          <span style="color:var(--text);padding-left:16px;">${escHtml(f.path.substring(dir.length + 1))}</span>
          ${f.size != null ? `<span style="color:var(--text-muted);font-size:10px;">${formatSize(f.size)}</span>` : ''}
        </div>`;
      }
      fileListHtml += '</div>';
    }
  }

  overlay.innerHTML = `
    <div class="modal" style="max-width:600px;max-height:80vh;display:flex;flex-direction:column;">
      <div class="modal-header">
        <h3 style="margin:0;font-size:15px;">${title}</h3>
        <button class="btn btn-ghost" onclick="closeBackupBrowse()" style="padding:2px 8px;">&times;</button>
      </div>
      ${subtitle}
      <div id="backupBrowseContent" style="overflow-y:auto;flex:1;border:1px solid var(--border);border-radius:4px;background:var(--bg);">
        <div id="backupFileList">${fileListHtml}</div>
        <div id="backupFileViewer" style="display:none;"></div>
      </div>
    </div>`;
  overlay.classList.add('open');
}

function closeBackupBrowse() {
  const overlay = document.getElementById('backupBrowseOverlay');
  if (overlay) overlay.classList.remove('open');
}

function toggleBackupDir(el) {
  const children = el.nextElementSibling;
  const arrow = el.querySelector('.kanban-arrow');
  if (children) {
    const open = children.style.display === 'none';
    children.style.display = open ? 'block' : 'none';
    if (arrow) arrow.classList.toggle('open', open);
  }
}

async function viewBackupFile(backupId, filePath) {
  const viewer = document.getElementById('backupFileViewer');
  const list = document.getElementById('backupFileList');
  viewer.innerHTML = '<p style="padding:12px;color:var(--text-muted);font-size:12px;">Loading...</p>';
  viewer.style.display = 'block';
  list.style.display = 'none';
  try {
    const res = await fetch(`/api/backups/${encodeURIComponent(backupId)}/file?path=${encodeURIComponent(filePath)}`);
    const data = await res.json();
    if (data.ok) {
      viewer.innerHTML = `
        <div style="padding:8px 12px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;">
          <button class="btn btn-ghost" onclick="backToFileList()" style="padding:2px 8px;font-size:12px;">&larr; Back</button>
          <span style="font-size:12px;font-weight:500;color:var(--text);">${escHtml(filePath)}</span>
        </div>
        <pre style="margin:0;padding:12px;font-size:11px;line-height:1.5;white-space:pre-wrap;word-break:break-all;overflow-y:auto;max-height:60vh;color:var(--text);background:var(--bg);">${escHtml(data.content)}</pre>`;
    } else {
      viewer.innerHTML = `
        <div style="padding:8px 12px;border-bottom:1px solid var(--border);">
          <button class="btn btn-ghost" onclick="backToFileList()" style="padding:2px 8px;font-size:12px;">&larr; Back</button>
        </div>
        <p style="padding:12px;color:var(--red);font-size:12px;">${escHtml(data.error || 'Could not read file')}</p>`;
    }
  } catch (e) {
    viewer.innerHTML = `
      <div style="padding:8px 12px;border-bottom:1px solid var(--border);">
        <button class="btn btn-ghost" onclick="backToFileList()" style="padding:2px 8px;font-size:12px;">&larr; Back</button>
      </div>
      <p style="padding:12px;color:var(--red);font-size:12px;">Error: ${escHtml(e.message)}</p>`;
  }
}

function backToFileList() {
  document.getElementById('backupFileViewer').style.display = 'none';
  document.getElementById('backupFileList').style.display = 'block';
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1048576).toFixed(1) + ' MB';
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
      html += '<div style="margin-bottom:16px;"><h4 style="font-size:12px;font-weight:600;color:var(--text);margin-bottom:8px;text-transform:uppercase;" title="Agent directories that appear to be from testing or probing — not part of your active agent lineup. Safe to archive or remove.">Leftover / Test Agents</h4>';
      html += '<div style="font-size:11px;color:var(--text-muted);margin-bottom:8px;">These agent directories are not in your active workspace lineup. They may be from earlier tests or probes. Your active agents are NOT affected by archiving or removing these.</div>';
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
      showGatewayBanner('⚠ Gateway restart recommended — persona change may require it.', { label: 'Restart Now', onclick: () => gatewayAction('restart') });
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

// ── Vault (Encrypted Credential Storage) ─────────────────────────────────

let _vaultUnlocked = false;

async function checkVaultStatus() {
  try {
    const res = await fetch('/api/vault/status');
    const data = await res.json();
    _vaultUnlocked = data.unlocked;
    renderVaultStatus(data);
    if (data.unlocked) loadVaultSecrets();
  } catch (_) {}
}

function renderVaultStatus(data) {
  const badge = document.getElementById('vaultStatusBadge');
  const btn = document.getElementById('vaultToggleBtn');
  if (data.unlocked) {
    badge.textContent = 'Unlocked';
    badge.style.background = 'rgba(76,175,80,0.15)';
    badge.style.color = '#4caf50';
    btn.textContent = 'Lock';
    btn.onclick = lockVault;
  } else {
    badge.textContent = data.initialized ? 'Locked' : 'Not set up';
    badge.style.background = 'rgba(239,68,68,0.15)';
    badge.style.color = 'var(--red)';
    btn.textContent = 'Unlock';
    btn.onclick = () => toggleVault();
    document.getElementById('vaultBody').innerHTML =
      '<p>Vault is locked. Unlock to view and manage secrets.</p>';
  }
}

let _vaultIsNew = false;

function toggleVault() {
  const overlay = document.getElementById('vaultUnlockOverlay');
  const title = document.getElementById('vaultUnlockTitle');
  const hint = document.getElementById('vaultUnlockHint');
  const confirmInput = document.getElementById('vaultPassphraseConfirm');
  document.getElementById('vaultPassphrase').value = '';
  confirmInput.value = '';
  document.getElementById('vaultUnlockError').style.display = 'none';
  // Check if vault exists for hint text
  fetch('/api/vault/status').then(r => r.json()).then(d => {
    _vaultIsNew = !d.initialized;
    if (_vaultIsNew) {
      title.textContent = 'Create Vault';
      hint.textContent = 'Choose a passphrase to encrypt your agent credentials. You will need this passphrase each time Mission Control starts.';
      confirmInput.style.display = 'block';
    } else {
      title.textContent = 'Unlock Vault';
      hint.textContent = 'Enter your vault passphrase to unlock encrypted secrets.';
      confirmInput.style.display = 'none';
    }
  });
  overlay.style.display = 'flex';
}

function closeVaultUnlockModal(e) {
  if (e && e.target !== document.getElementById('vaultUnlockOverlay')) return;
  document.getElementById('vaultUnlockOverlay').style.display = 'none';
}

async function submitVaultUnlock() {
  const passphrase = document.getElementById('vaultPassphrase').value;
  const confirm = document.getElementById('vaultPassphraseConfirm').value;
  const errEl = document.getElementById('vaultUnlockError');
  if (!passphrase) {
    errEl.textContent = 'Passphrase is required.';
    errEl.style.display = 'block';
    return;
  }
  if (_vaultIsNew && passphrase !== confirm) {
    errEl.textContent = 'Passphrases do not match.';
    errEl.style.display = 'block';
    return;
  }
  try {
    const res = await fetch('/api/vault/unlock', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ passphrase }),
    });
    const data = await res.json();
    if (data.ok) {
      closeVaultUnlockModal();
      checkVaultStatus();
    } else {
      errEl.textContent = data.error || 'Unlock failed.';
      errEl.style.display = 'block';
    }
  } catch (e) {
    errEl.textContent = `Error: ${e.message}`;
    errEl.style.display = 'block';
  }
}

async function lockVault() {
  await fetch('/api/vault/lock', { method: 'POST' });
  _vaultUnlocked = false;
  checkVaultStatus();
}

async function loadVaultSecrets() {
  const body = document.getElementById('vaultBody');
  try {
    const res = await fetch('/api/vault/list');
    const data = await res.json();
    if (!data.ok) { body.innerHTML = '<p>Vault is locked.</p>'; return; }
    const secrets = data.secrets || [];
    if (secrets.length === 0) {
      body.innerHTML = '<p>No secrets stored. Click <strong>+ Add Secret</strong> to store credentials.</p>';
      return;
    }
    const deletedHtml = await loadDeletedSecrets();
    body.innerHTML = `
      <table style="width:100%;border-collapse:collapse;">
        <thead>
          <tr style="border-bottom:1px solid var(--border);">
            <th style="text-align:left;padding:6px 8px;font-size:11px;color:var(--text-muted);text-transform:uppercase;">Name</th>
            <th style="text-align:left;padding:6px 8px;font-size:11px;color:var(--text-muted);text-transform:uppercase;">Value</th>
            <th style="width:80px;"></th>
          </tr>
        </thead>
        <tbody>
          ${secrets.map(name => `
            <tr style="border-bottom:1px solid var(--border);" id="vault-row-${name}">
              <td style="padding:8px;font-family:monospace;font-size:12px;font-weight:600;">${name}</td>
              <td style="padding:8px;">
                <span id="vault-val-${name}" style="font-family:monospace;font-size:12px;color:var(--text-muted);">••••••••</span>
              </td>
              <td style="padding:8px;text-align:right;white-space:nowrap;">
                <button class="btn btn-ghost" style="padding:2px 6px;font-size:11px;" onclick="revealSecret('${name}')">Show</button>
                <button class="btn btn-ghost" style="padding:2px 6px;font-size:11px;color:var(--red);" onclick="deleteSecret('${name}')">Del</button>
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
      ${deletedHtml}
    `;
  } catch (e) {
    body.innerHTML = `<p style="color:var(--red);">Failed to load secrets: ${e.message}</p>`;
  }
}

async function revealSecret(name) {
  const el = document.getElementById(`vault-val-${name}`);
  if (el.dataset.revealed === 'true') {
    el.textContent = '••••••••';
    el.dataset.revealed = 'false';
    return;
  }
  try {
    const res = await fetch(`/api/vault/get/${encodeURIComponent(name)}`);
    const data = await res.json();
    if (data.ok) {
      el.textContent = data.value;
      el.dataset.revealed = 'true';
      // Auto-hide after 10 seconds
      setTimeout(() => {
        if (el.dataset.revealed === 'true') {
          el.textContent = '••••••••';
          el.dataset.revealed = 'false';
        }
      }, 10000);
    }
  } catch (_) {}
}

async function deleteSecret(name) {
  if (!confirm(`Delete secret "${name}"?\n\nIt will be moved to the archive and can be recovered later.`)) return;
  try {
    const res = await fetch('/api/vault/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    const data = await res.json();
    if (data.ok) loadVaultSecrets();
  } catch (_) {}
}

async function loadDeletedSecrets() {
  try {
    const res = await fetch('/api/vault/deleted');
    const data = await res.json();
    if (!data.ok || !data.deleted || data.deleted.length === 0) return '';
    return `
      <div style="margin-top:12px;padding-top:10px;border-top:1px solid var(--border);">
        <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.4px;margin-bottom:6px;">Deleted Archive</div>
        <table style="width:100%;border-collapse:collapse;">
          <tbody>
            ${data.deleted.map(d => {
              const when = new Date(d.deleted_at).toLocaleString();
              return `
                <tr style="border-bottom:1px solid var(--border);opacity:0.6;">
                  <td style="padding:6px 8px;font-family:monospace;font-size:12px;text-decoration:line-through;">${d.name}</td>
                  <td style="padding:6px 8px;font-size:11px;color:var(--text-muted);">Deleted ${when}</td>
                  <td style="padding:6px 8px;text-align:right;white-space:nowrap;">
                    <button class="btn btn-ghost" style="padding:2px 6px;font-size:11px;color:#4caf50;" onclick="recoverSecret('${d.name}')">Recover</button>
                    <button class="btn btn-ghost" style="padding:2px 6px;font-size:11px;color:var(--red);" onclick="purgeSecret('${d.name}')">Purge</button>
                  </td>
                </tr>
              `;
            }).join('')}
          </tbody>
        </table>
      </div>
    `;
  } catch (_) { return ''; }
}

async function recoverSecret(name) {
  try {
    const res = await fetch('/api/vault/recover', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    const data = await res.json();
    if (data.ok) loadVaultSecrets();
  } catch (_) {}
}

async function purgeSecret(name) {
  if (!confirm(`Permanently delete "${name}" from archive?\n\nThis CANNOT be undone.`)) return;
  try {
    const res = await fetch('/api/vault/purge', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    const data = await res.json();
    if (data.ok) loadVaultSecrets();
  } catch (_) {}
}

function showAddSecretModal() {
  if (!_vaultUnlocked) { toggleVault(); return; }
  document.getElementById('secretName').value = '';
  document.getElementById('secretValue').value = '';
  document.getElementById('addSecretError').style.display = 'none';
  document.getElementById('addSecretOverlay').style.display = 'flex';
}

function closeAddSecretModal(e) {
  if (e && e.target !== document.getElementById('addSecretOverlay')) return;
  document.getElementById('addSecretOverlay').style.display = 'none';
}

function toggleSecretInputVisibility() {
  const input = document.getElementById('secretValue');
  const btn = document.getElementById('secretToggleBtn');
  if (input.style.webkitTextSecurity === 'disc') {
    input.style.webkitTextSecurity = 'none';
    btn.textContent = 'Hide';
  } else {
    input.style.webkitTextSecurity = 'disc';
    btn.textContent = 'Show';
  }
}

async function submitAddSecret() {
  const name = document.getElementById('secretName').value.trim().toUpperCase().replace(/[^A-Z0-9_]/g, '_');
  const value = document.getElementById('secretValue').value;
  const errEl = document.getElementById('addSecretError');
  if (!name || !value) {
    errEl.textContent = 'Name and value are required.';
    errEl.style.display = 'block';
    return;
  }
  try {
    const res = await fetch('/api/vault/store', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, value }),
    });
    const data = await res.json();
    if (data.ok) {
      closeAddSecretModal();
      loadVaultSecrets();
    } else {
      errEl.textContent = data.error || 'Failed to store secret.';
      errEl.style.display = 'block';
    }
  } catch (e) {
    errEl.textContent = `Error: ${e.message}`;
    errEl.style.display = 'block';
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

// ── Team Chat ──────────────────────────────────────────────────────────────

let _tcOpen = localStorage.getItem('teamChatOpen') === '1';
let _tcMessages = [];
let _tcCursor = null;
let _tcBusy = false;
let _tcAgents = {};  // {role: character_name}
let _tcLoaded = false;

// Agent colors for message labels
const TC_COLORS = {
  pm: '#58a6ff', architect: '#a78bfa', builder: '#34d399',
  qa: '#fbbf24', security: '#f87171', devops: '#fb923c',
  ux: '#c4b5fd', research: '#7dd3fc', graphics: '#fcd34d',
};

function toggleTeamChat() {
  _tcOpen = !_tcOpen;
  localStorage.setItem('teamChatOpen', _tcOpen ? '1' : '0');
  document.getElementById('teamChatPanel').classList.toggle('open', _tcOpen);
  document.body.classList.toggle('team-chat-open', _tcOpen);
  if (_tcOpen && !_tcLoaded) loadTeamChat();
}

async function loadTeamChat() {
  try {
    const url = _tcCursor
      ? `/api/team-chat/messages?cursor=${encodeURIComponent(_tcCursor)}`
      : '/api/team-chat/messages?limit=100';
    const res = await fetch(url);
    if (!res.ok) return;
    const data = await res.json();
    if (!data.ok) return;

    _tcCursor = data.cursor;
    _tcAgents = data.agents || {};
    _tcLoaded = true;

    if (!_tcCursor || !_tcMessages.length) {
      // Initial load — replace all
      _tcMessages = data.messages || [];
    } else {
      // Incremental — append
      appendTeamChatMessages(data.messages || []);
      return;
    }
    _updateTcAgentSelect();
    renderTeamChatTimeline();
  } catch (e) { /* network error */ }
}

function appendTeamChatMessages(msgs) {
  if (!msgs || !msgs.length) return;
  // Deduplicate by id
  const existing = new Set(_tcMessages.map(m => m.id));
  const fresh = msgs.filter(m => !existing.has(m.id));
  if (!fresh.length) return;
  _tcMessages.push(...fresh);
  renderTeamChatTimeline(true);
}

function _updateTcAgentSelect() {
  const sel = document.getElementById('tcAgentSelect');
  const roles = Object.keys(_tcAgents);
  if (!roles.length) return;
  sel.innerHTML = roles.map(r =>
    `<option value="${r}">${_tcAgents[r] || r} (${r})</option>`
  ).join('');
}

function renderTeamChatTimeline(scrollToBottom) {
  const container = document.getElementById('tcMessages');
  const empty = document.getElementById('tcEmpty');
  const wasAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 40;

  if (!_tcMessages.length) {
    empty.style.display = '';
    empty.textContent = _tcLoaded ? 'No messages yet. Start a conversation!' : 'Loading team chat...';
    // Remove any existing message elements
    container.querySelectorAll('.tc-msg,.tc-system-row').forEach(el => el.remove());
    return;
  }

  empty.style.display = 'none';
  container.querySelectorAll('.tc-msg,.tc-system-row').forEach(el => el.remove());

  for (const msg of _tcMessages) {
    if (msg.type === 'spawn') {
      const row = document.createElement('div');
      row.className = 'tc-system-row';
      const agentName = _tcAgents[msg.agent] || msg.agent;
      const targetName = msg.target ? (_tcAgents[msg.target] || msg.target) : '?';
      row.textContent = `${agentName} → ${targetName}: ${msg.text}`;
      container.appendChild(row);
    } else if (msg.type === 'yield') {
      const row = document.createElement('div');
      row.className = 'tc-system-row';
      const agentName = _tcAgents[msg.agent] || msg.agent;
      row.textContent = `${agentName} waiting: ${msg.text}`;
      container.appendChild(row);
    } else if (msg.type === 'user') {
      const div = document.createElement('div');
      div.className = 'tc-msg tc-msg-user';
      div.textContent = msg.text;
      container.appendChild(div);
    } else if (msg.type === 'assistant') {
      const div = document.createElement('div');
      div.className = 'tc-msg tc-msg-assistant';
      const color = TC_COLORS[msg.agent] || '#888';
      const name = _tcAgents[msg.agent] || msg.agent;
      const ts = msg.ts ? new Date(msg.ts).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : '';
      div.innerHTML = `<div class="tc-msg-label"><span class="tc-agent-dot" style="background:${color}"></span>${escHtml(name)}<span class="tc-msg-ts">${ts}</span></div>${escHtml(msg.text)}`;
      container.appendChild(div);
    }
  }

  if (scrollToBottom || wasAtBottom) {
    container.scrollTop = container.scrollHeight;
  }
}

function tcInputKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendTeamChatMessage();
  }
}

function tcInputResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 100) + 'px';
}

async function sendTeamChatMessage() {
  if (_tcBusy) return;
  const input = document.getElementById('tcInput');
  const message = input.value.trim();
  if (!message) return;

  // Parse @mention to route to specific agent
  let agentId = document.getElementById('tcAgentSelect').value || 'pm';
  const mentionMatch = message.match(/^@(\w+)\s/);
  if (mentionMatch) {
    const mention = mentionMatch[1].toLowerCase();
    // Check against role names and character names
    for (const [role, char] of Object.entries(_tcAgents)) {
      if (role === mention || (char && char.toLowerCase() === mention)) {
        agentId = role;
        break;
      }
    }
  }

  input.value = '';
  input.style.height = '34px';
  _tcBusy = true;
  document.getElementById('tcSendBtn').disabled = true;

  // Optimistic: add user message
  const userMsg = { id: 'local_' + Date.now(), ts: new Date().toISOString(), agent: agentId, type: 'user', text: message, target: null, model: null };
  _tcMessages.push(userMsg);
  renderTeamChatTimeline(true);

  try {
    const res = await fetch('/api/team-chat/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agentId, message }),
    });
    const data = await res.json();
    if (data.ok && data.response) {
      const respMsg = { id: 'resp_' + Date.now(), ts: new Date().toISOString(), agent: agentId, type: 'assistant', text: data.response, target: null, model: data.model || null };
      _tcMessages.push(respMsg);
      renderTeamChatTimeline(true);
    } else if (!data.ok) {
      const errMsg = { id: 'err_' + Date.now(), ts: new Date().toISOString(), agent: agentId, type: 'assistant', text: `Error: ${data.error || 'Unknown error'}`, target: null, model: null };
      _tcMessages.push(errMsg);
      renderTeamChatTimeline(true);
    }
  } catch (e) {
    const errMsg = { id: 'err_' + Date.now(), ts: new Date().toISOString(), agent: agentId, type: 'assistant', text: `Network error: ${e.message}`, target: null, model: null };
    _tcMessages.push(errMsg);
    renderTeamChatTimeline(true);
  } finally {
    _tcBusy = false;
    document.getElementById('tcSendBtn').disabled = false;
    document.getElementById('tcInput').focus();
  }
}

// ── Boot ───────────────────────────────────────────────────────────────────

// Initial state fetch (in case WebSocket is slow to connect)
fetch('/api/state')
  .then(r => r.json())
  .then(state => { if (!lastState) render(state); })
  .catch(() => {});

connect();
// Restore team chat panel state from localStorage
if (_tcOpen) {
  document.getElementById('teamChatPanel').classList.add('open');
  document.body.classList.add('team-chat-open');
  loadTeamChat();
}
checkOpenclawSync();
loadAgentRegistry();
loadSessionLog();
loadSysInfo();
loadSkills();
loadProjects();
loadAssetGallery();
loadBackups();
checkVaultStatus();
startGatewayPolling();
