// OpenClaw Mission Control — Installer Wizard

// Show version badge in header
fetch('/api/version')
  .then(r => r.json())
  .then(d => {
    const el = document.getElementById('versionBadge');
    if (el && d.version) el.textContent = `v${d.version}`;
  })
  .catch(() => {});

const state = {
  currentStep: 1,
  targetDir: '',
  teamSize: 4,
  tier: 'standard',
  theme: 'historical',
  themes: [],
  updateMode: false,
  installMode: 'new',
  models: { strategic: '', implementation: '', support: '' },
  deselectedModels: new Set(),  // model IDs the user has unchecked
  customCharacters: {},         // {role: character_name} — overrides theme defaults
};

const ROLES_MINIMAL = ['pm', 'architect', 'builder', 'qa'];
const ROLES_FULL    = ['pm', 'architect', 'builder', 'qa', 'security', 'devops', 'ux', 'research'];
const ROLE_LABELS_MAP = { pm: 'PM', architect: 'Architect', builder: 'Builder', qa: 'QA', security: 'Security', devops: 'DevOps', ux: 'UX', research: 'Research' };

// ── XSS protection ────────────────────────────────────────────────────────

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ── Step navigation ────────────────────────────────────────────────────────

function goStep(n) {
  document.getElementById(`step${state.currentStep}`).classList.add('section-hidden');
  document.getElementById(`step${n}`).classList.remove('section-hidden');

  // Update step indicators (steps 1–6)
  const indicators = document.getElementById('stepIndicators');
  if (n >= 1) {
    indicators.style.display = '';
    for (let i = 1; i <= 6; i++) {
      const el = document.getElementById(`si-${i}`);
      el.className = 'step';
      if (i < n) el.classList.add('done');
      else if (i === n) el.classList.add('active');
    }
  } else {
    indicators.style.display = 'none';
  }

  state.currentStep = n;

  if (n === 1) loadPrereqs();
  if (n === 2) loadModels();
  if (n === 4) loadHardware();
  if (n === 5) loadThemes();
  if (n === 6) { loadReview(); checkActiveAgents(); }
}

// ── Step 0: Existing workspace choice ─────────────────────────────────────

function selectUpdateMode(path) {
  state.targetDir = path;
  state.updateMode = true;
  const input = document.getElementById('targetDir');
  if (input) input.value = path;
  goStep(2);  // Show models step even for updates
}

function selectNewMode() {
  state.updateMode = false;
  state.installMode = 'new';
  state.targetDir = '';
  // Skip goStep(1) — prereqs already passed to reach this screen.
  // Going to step 1 would re-run loadPrereqs() which re-detects the existing
  // workspace and immediately bounces back to step 0 (appears to do nothing).
  goStep(2);
}

// ── Step 1: Prerequisites ──────────────────────────────────────────────────

async function loadPrereqs() {
  const list = document.getElementById('prereqList');
  const btn = document.getElementById('btn1Next');
  const target = state.targetDir || '';

  list.innerHTML = '<p style="color:var(--text-muted)">Checking...</p>';
  btn.disabled = true;

  try {
    const res = await fetch(`/api/prerequisites?target=${encodeURIComponent(target)}`);
    const data = await res.json();
    const checks = data.checks || data;
    let html = '';

    for (const c of checks) {
      let icon, noteStyle;
      if (c.passed) {
        icon = '✅';
        noteStyle = '';
      } else if (!c.blocking) {
        icon = '⚠️';
        noteStyle = 'color:var(--yellow)';
      } else {
        icon = '❌';
        noteStyle = '';
      }

      html += `
        <div class="check-row">
          <span class="check-icon">${icon}</span>
          <div>
            <div class="check-name">${escHtml(c.name)}</div>
            <div class="check-detail" style="${noteStyle}">${escHtml(c.detail)}</div>
            ${!c.passed && c.fix ? `<div class="check-fix">${escHtml(c.fix)}</div>` : ''}
            ${!c.passed && !c.blocking ? '<div class="check-fix" style="color:var(--text-muted);font-style:italic">Optional — you can install the workspace now and add this later.</div>' : ''}
          </div>
        </div>`;
    }
    list.innerHTML = html;

    btn.disabled = !data.can_proceed;

    if (!state.targetDir && data.default_target) {
      state.targetDir = data.default_target;
      const input = document.getElementById('targetDir');
      if (input && !input.value) input.value = data.default_target;
    }
  } catch (e) {
    list.innerHTML = `<p style="color:var(--red)">Could not connect to server. Make sure OpenClaw Mission Control is running.</p>`;
  }
}

function getDefaultDir() {
  return state.targetDir || document.getElementById('targetDir')?.value || '';
}

// ── Step 2: Model Setup ────────────────────────────────────────────────────

let _allModels = [];

async function loadModels() {
  const configuredEl = document.getElementById('configuredModels');

  // Fetch curated model list for datalist hints
  try {
    const res = await fetch('/api/models');
    const data = await res.json();
    _allModels = data.models || [];
    _populateDatalist(_allModels);
  } catch (e) {
    _allModels = [];
  }

  // Detect already-configured models from OpenClaw
  try {
    const res = await fetch('/api/configured-models');
    const data = await res.json();
    const models = data.models || [];
    _renderConfiguredModels(models);
    if (models.length > 0) autoFillModelAssignments(models);
  } catch (e) {
    const configuredEl = document.getElementById('configuredModels');
    if (configuredEl) configuredEl.innerHTML = '<p style="color:var(--text-muted);font-size:13px">Could not detect configured models.</p>';
  }
}

function _populateDatalist(models) {
  const dl = document.getElementById('modelOptions');
  if (!dl) return;
  // Only include models the user hasn't unchecked
  const active = models.filter(m => !state.deselectedModels.has(m.id));
  dl.innerHTML = active.map(m =>
    `<option value="${escHtml(m.id)}" label="${escHtml(m.label)} (${escHtml(m.provider)})">`
  ).join('');
}

function _renderConfiguredModels(models) {
  const configuredEl = document.getElementById('configuredModels');
  if (!configuredEl) return;
  if (!models.length) {
    configuredEl.innerHTML = '<p style="color:var(--text-muted);font-size:13px">No providers configured yet. Add one below, or skip to configure OpenClaw separately.</p>';
    return;
  }
  configuredEl.innerHTML = models.map(m => {
    const checked = !state.deselectedModels.has(m.id);
    return `<div class="model-item" onclick="toggleConfiguredModel('${escHtml(m.id)}')"
        style="cursor:pointer;user-select:none" title="${checked ? 'Click to exclude from deployment' : 'Click to include in deployment'}">
        <span style="font-size:16px;line-height:1">${checked ? '✅' : '⬜'}</span>
        <span class="model-item-id" style="${checked ? '' : 'opacity:0.4;text-decoration:line-through'}">${escHtml(m.id)}</span>
        <span class="model-item-provider">${escHtml(m.provider || '')}</span>
      </div>`;
  }).join('');
}

function toggleConfiguredModel(id) {
  if (state.deselectedModels.has(id)) {
    state.deselectedModels.delete(id);
  } else {
    state.deselectedModels.add(id);
  }
  // Re-render the list and rebuild datalist with updated selection
  const currentModels = _allModels.length ? _allModels : [];
  _renderConfiguredModels(currentModels);
  _populateDatalist(currentModels);
}

function autoFillModelAssignments(models) {
  if (!models.length) return;
  const first = models[0].id;
  const last = models[models.length - 1].id;
  if (!state.models.strategic) {
    state.models.strategic = first;
    const el = document.getElementById('modelStrategic');
    if (el && !el.value) el.value = first;
  }
  if (!state.models.implementation) {
    state.models.implementation = first;
    const el = document.getElementById('modelImplementation');
    if (el && !el.value) el.value = first;
  }
  if (!state.models.support) {
    state.models.support = last;
    const el = document.getElementById('modelSupport');
    if (el && !el.value) el.value = last;
  }
}

async function refreshConfiguredModels() {
  try {
    const res = await fetch('/api/configured-models');
    const data = await res.json();
    const models = data.models || [];
    // Merge into _allModels so toggles and datalist stay in sync
    for (const m of models) {
      if (!_allModels.find(x => x.id === m.id)) _allModels.push(m);
    }
    _renderConfiguredModels(_allModels.length ? _allModels : models);
    if (models.length > 0) {
      autoFillModelAssignments(models);
      _populateDatalist(_allModels.length ? _allModels : models);
    }
    return models;
  } catch (e) {
    return [];
  }
}

// ── Provider: API Key form ─────────────────────────────────────────────────

function showApiKeyForm(type) {
  const titles = { 'openai-key': 'OpenAI API Key', 'openrouter-key': 'OpenRouter API Key' };
  const placeholders = { 'openai-key': 'sk-...', 'openrouter-key': 'sk-or-...' };
  const form = document.getElementById('providerForm');
  form.className = 'inline-form';
  form.innerHTML = `
    <div class="inline-form-title">${titles[type] || 'API Key'}</div>
    <input type="password" id="apiKeyInput" placeholder="${placeholders[type] || 'Enter API key...'}" style="font-family:monospace" />
    <div id="apiKeyStatus" style="font-size:12px;margin-top:8px;min-height:18px;"></div>
    <div style="display:flex;gap:8px;margin-top:10px;">
      <button class="btn btn-ghost" onclick="closeProviderForm()">Cancel</button>
      <button class="btn btn-primary" id="apiKeySaveBtn" onclick="saveApiKey('${type}')">Save &amp; Connect</button>
    </div>`;
}

async function saveApiKey(type) {
  const input = document.getElementById('apiKeyInput');
  const status = document.getElementById('apiKeyStatus');
  const btn = document.getElementById('apiKeySaveBtn');
  const key = input?.value.trim();
  if (!key) { status.textContent = 'Enter a key first.'; return; }

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Connecting...';
  status.textContent = '';

  try {
    const res = await fetch('/api/configure-provider', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, key }),
    });
    const data = await res.json();
    if (data.ok) {
      status.style.color = 'var(--green)';
      status.textContent = `Connected — ${data.models?.length || 0} models available.`;
      btn.innerHTML = '✓ Saved';
      setTimeout(async () => { closeProviderForm(); await refreshConfiguredModels(); }, 1000);
    } else {
      status.style.color = 'var(--red)';
      status.textContent = data.error || 'Connection failed.';
      btn.disabled = false;
      btn.innerHTML = 'Save & Connect';
    }
  } catch (e) {
    status.style.color = 'var(--red)';
    status.textContent = `Error: ${e.message}`;
    btn.disabled = false;
    btn.innerHTML = 'Save & Connect';
  }
}

// ── Provider: OAuth (launches openclaw configure) ──────────────────────────

function showOAuthFlow(provider) {
  const labels = { anthropic: 'Anthropic (Claude Subscription)', openai: 'OpenAI OAuth', github: 'GitHub Copilot' };
  const form = document.getElementById('providerForm');
  form.className = 'inline-form';
  form.innerHTML = `
    <div class="inline-form-title">${labels[provider] || provider}</div>
    <p style="font-size:13px;color:var(--text-muted);margin-bottom:12px;">
      OpenClaw's OAuth flow opens in a terminal window. Complete the login there, then return here and click <strong>Check Again</strong>.
    </p>
    <div id="oauthStatus" style="font-size:12px;min-height:18px;"></div>
    <div style="display:flex;gap:8px;margin-top:10px;">
      <button class="btn btn-ghost" onclick="closeProviderForm()">Cancel</button>
      <button class="btn btn-primary" onclick="launchOAuth('${provider}')">Launch OpenClaw Configure</button>
      <button class="btn btn-ghost" onclick="checkOAuthDone('${provider}')">Check Again</button>
    </div>`;
}

async function launchOAuth(provider) {
  const status = document.getElementById('oauthStatus');
  try {
    const res = await fetch(`/oauth/start/${provider}`);
    const data = await res.json();
    status.style.color = data.error ? 'var(--red)' : 'var(--text-muted)';
    status.textContent = data.error || data.message || 'Terminal launched.';
  } catch (e) {
    const status = document.getElementById('oauthStatus');
    status.style.color = 'var(--red)';
    status.textContent = `Error: ${e.message}`;
  }
}

async function checkOAuthDone(provider) {
  const status = document.getElementById('oauthStatus');
  status.style.color = 'var(--text-muted)';
  status.textContent = 'Checking...';
  const models = await refreshConfiguredModels();
  if (models.length > 0) {
    status.style.color = 'var(--green)';
    status.textContent = `✓ ${models.length} model(s) detected. You can continue.`;
    setTimeout(closeProviderForm, 1500);
  } else {
    status.textContent = 'No models detected yet. Complete the auth flow in the terminal and try again.';
  }
}

// ── Provider: Ollama ───────────────────────────────────────────────────────

async function showOllamaSetup() {
  const form = document.getElementById('providerForm');
  form.className = 'inline-form';
  form.innerHTML = `<div class="inline-form-title">Ollama Local — qwen2.5:7b-instruct</div><p style="color:var(--text-muted);font-size:13px">Checking Ollama status...</p>`;

  let hasOllama = false, hasModel = false, statusText = '';
  try {
    const res = await fetch('/api/ollama-status');
    const data = await res.json();
    hasOllama = data.installed;
    hasModel = (data.models || []).includes('qwen2.5:7b-instruct');
    if (hasModel) {
      statusText = '✅ Ollama and qwen2.5:7b-instruct are already installed.';
    } else if (hasOllama) {
      statusText = 'Ollama is installed. qwen2.5:7b-instruct needs to be downloaded (~4.7 GB).';
    } else {
      statusText = 'Ollama is not installed. This will download Ollama then pull qwen2.5:7b-instruct (~4.7 GB total).';
    }
  } catch (e) {
    statusText = 'Could not check Ollama status.';
  }

  form.innerHTML = `
    <div class="inline-form-title">Ollama Local — qwen2.5:7b-instruct</div>
    <p style="font-size:13px;color:var(--text-muted);margin-bottom:8px;">${statusText}</p>
    ${hasModel ? '' : '<p style="font-size:12px;color:var(--yellow);margin-bottom:8px;">⚠️ Requires ~4.7 GB disk space and internet. May take several minutes.</p>'}
    <div id="ollamaLog" class="ollama-progress section-hidden"></div>
    <div style="display:flex;gap:8px;margin-top:10px;">
      <button class="btn btn-ghost" onclick="closeProviderForm()">Cancel</button>
      ${hasModel
        ? `<button class="btn btn-primary" onclick="registerOllamaModel()">Register in OpenClaw</button>`
        : `<button class="btn btn-primary" id="ollamaInstallBtn" onclick="startOllamaInstall()">Install &amp; Download</button>`
      }
    </div>`;
}

async function startOllamaInstall() {
  const btn = document.getElementById('ollamaInstallBtn');
  const log = document.getElementById('ollamaLog');
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Installing...'; }
  log.classList.remove('section-hidden');
  log.textContent = '';

  try {
    const res = await fetch('/api/ollama-install', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const event = JSON.parse(line.slice(6));
            if (event.message || event.status) {
              log.textContent += (event.message || event.status) + '\n';
              log.scrollTop = log.scrollHeight;
            }
            if (event.status === 'done') {
              log.textContent += '✅ Done! qwen2.5:7b-instruct is ready.\n';
              await refreshConfiguredModels();
              if (btn) btn.innerHTML = '✓ Installed';
            } else if (event.status === 'error') {
              log.textContent += `❌ Error: ${event.message}\n`;
              if (btn) { btn.disabled = false; btn.innerHTML = 'Retry'; }
            }
          } catch (_) {}
        }
      }
    }
  } catch (e) {
    log.textContent += `Error: ${e.message}\n`;
    if (btn) { btn.disabled = false; btn.innerHTML = 'Retry'; }
  }
}

async function registerOllamaModel() {
  await refreshConfiguredModels();
  closeProviderForm();
}

function closeProviderForm() {
  const form = document.getElementById('providerForm');
  form.className = 'section-hidden';
  form.innerHTML = '';
}

// ── Step 3: Target directory ───────────────────────────────────────────────

async function browseFolderDialog() {
  const btn = document.getElementById('btnBrowse');
  if (btn) { btn.disabled = true; btn.textContent = 'Opening…'; }
  try {
    const res = await fetch('/api/browse-folder');
    const data = await res.json();
    if (data.path) {
      state.targetDir = data.path;
      const input = document.getElementById('targetDir');
      if (input) input.value = data.path;
      checkPath();
    }
  } catch (e) { /* user cancelled or dialog unavailable — no-op */ }
  finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Browse…'; }
  }
}

let _pathCheckTimer = null;

function debounceCheckPath() {
  state.targetDir = document.getElementById('targetDir')?.value || '';
  clearTimeout(_pathCheckTimer);
  _pathCheckTimer = setTimeout(checkPath, 600);
}

async function checkPath() {
  const path = state.targetDir.trim();
  const panel = document.getElementById('existingWorkspacePanel');
  const desc = document.getElementById('existingWorkspaceDesc');
  if (!panel) return;

  if (!path) {
    panel.classList.add('section-hidden');
    return;
  }

  try {
    const res = await fetch(`/api/check-workspace-path?path=${encodeURIComponent(path)}`);
    const data = await res.json();

    if (!data.is_workspace) {
      panel.classList.add('section-hidden');
      return;
    }

    // Populate description
    if (data.is_single_agent) {
      desc.textContent = `Single-agent workspace detected (${data.agent_count} agent role). Upgrade to add the full multi-agent team.`;
    } else {
      desc.textContent = `Multi-agent workspace detected (${data.agent_count} agent roles). Choose how to proceed below.`;
    }

    // Default selection: upgrade for single-agent, replace for already-multi
    const defaultMode = data.is_single_agent ? 'upgrade' : 'replace';
    selectInstallMode(defaultMode);
    panel.classList.remove('section-hidden');

    // Load and render the existing agent list
    loadExistingAgents(path);
  } catch (e) {
    panel.classList.add('section-hidden');
  }
}

async function loadExistingAgents(workspacePath) {
  const list = document.getElementById('existingAgentList');
  if (!list) return;
  list.innerHTML = '<p style="color:var(--text-muted);font-size:12px">Loading agents…</p>';
  try {
    const res = await fetch(`/api/workspace-agents?path=${encodeURIComponent(workspacePath)}`);
    const data = await res.json();
    if (!data.agents || !data.agents.length) {
      list.innerHTML = '<p style="color:var(--text-muted);font-size:12px">No agents found in AGENTS.md.</p>';
      return;
    }
    list.innerHTML = data.agents.map(a => `
      <div class="existing-agent-row" id="agent-row-${escHtml(a.role)}">
        <div style="flex:1;">
          <span style="font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.4px;">${escHtml(a.role_label)}</span>
          <span style="margin-left:10px;font-size:13px;font-weight:600;">${escHtml(a.character)}</span>
          <span style="margin-left:8px;font-size:11px;color:var(--text-muted);font-family:monospace;">${escHtml(a.model)}</span>
        </div>
        <button class="btn btn-ghost" style="padding:3px 10px;font-size:11px;color:var(--red);border-color:rgba(248,81,73,0.3);"
          onclick="deleteAgent(${escHtml(JSON.stringify(workspacePath))}, '${escHtml(a.role)}')">Remove</button>
      </div>
    `).join('');
  } catch (e) {
    list.innerHTML = '<p style="color:var(--red);font-size:12px">Could not load agents.</p>';
  }
}

async function deleteAgent(workspacePath, role) {
  if (!confirm(`Remove the ${role} agent from this workspace? This also removes its OpenClaw registration.`)) return;
  try {
    const res = await fetch('/api/workspace-agents/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: workspacePath, role }),
    });
    const data = await res.json();
    if (data.ok) {
      const row = document.getElementById(`agent-row-${role}`);
      if (row) row.remove();
    } else {
      alert(`Could not remove agent: ${data.error}`);
    }
  } catch (e) {
    alert('Could not remove agent.');
  }
}

function selectInstallMode(mode) {
  state.installMode = mode;

  ['upgrade', 'replace', 'new', 'dashboard'].forEach(m => {
    const id = `mode${m.charAt(0).toUpperCase() + m.slice(1)}Card`;
    const card = document.getElementById(id);
    const radio = card?.querySelector('input[type=radio]');
    const modeKey = m === 'dashboard' ? 'dashboard-only' : m;
    if (card) card.style.borderColor = modeKey === mode ? 'var(--accent)' : 'var(--border)';
    if (radio) radio.checked = modeKey === mode;
  });

  // Show warnings for destructive modes
  const warn = document.getElementById('installModeWarning');
  if (mode === 'upgrade') {
    warn.innerHTML = '<strong>Warning:</strong> Upgrade will overwrite workspace config files (AGENTS.md, SOUL.md, TOOLS.md, USER.md, MEMORY.md). Your project files (specs, tickets, builds) are preserved. Agent session logs and TODOs will be reset.';
    warn.classList.remove('section-hidden');
  } else if (mode === 'replace') {
    warn.innerHTML = '<strong>Warning:</strong> Replace will overwrite ALL workspace config files including CLAUDE.md. Your project files (specs, tickets, builds) are preserved, but agent metadata will be reset. Use this only to recover a broken setup.';
    warn.classList.remove('section-hidden');
  } else {
    warn.classList.add('section-hidden');
  }
}

function selectDashboardOnlyMode() {
  // Skip straight to dashboard — no install needed
  window.location = '/monitor';
}

function confirmLocation() {
  const path = state.targetDir.trim();
  if (!path) {
    alert('Please enter a workspace folder path.');
    return;
  }

  // If user selected "new" mode from the existing-workspace panel,
  // the path they typed IS the existing workspace — they need a different path.
  // Highlight the input so they know to change it.
  if (state.installMode === 'new') {
    const panel = document.getElementById('existingWorkspacePanel');
    if (panel && !panel.classList.contains('section-hidden')) {
      const input = document.getElementById('targetDir');
      if (input) {
        input.focus();
        input.select();
        input.style.borderColor = 'var(--accent)';
        setTimeout(() => { input.style.borderColor = ''; }, 2000);
      }
      document.getElementById('existingWorkspaceDesc').textContent =
        'Enter a new path above for the independent workspace.';
      return;
    }
  }

  // Dashboard-only mode — skip team/theme, go straight to install
  if (state.installMode === 'dashboard-only') {
    goStep(6);
    return;
  }

  goStep(4);
}

document.addEventListener('DOMContentLoaded', async () => {
  const input = document.getElementById('targetDir');
  if (input) {
    input.addEventListener('input', e => { state.targetDir = e.target.value; });
  }

  // Check for existing workspaces — show Step 0 if any found
  try {
    const res = await fetch('/api/workspaces');
    const data = await res.json();
    if (data.found && data.found.length > 0) {
      const container = document.getElementById('workspaceChoices');
      container.innerHTML = data.found.map(p => `
        <button class="workspace-card" onclick="selectUpdateMode(${escHtml(JSON.stringify(p))})">
          <div class="workspace-card-title">Update Existing</div>
          <div class="workspace-card-path">${escHtml(p)}</div>
          <div class="workspace-card-desc">Refresh workspace files — existing projects are preserved.</div>
        </button>
      `).join('');
      document.getElementById('stepIndicators').style.display = 'none';
      document.getElementById('step1').classList.add('section-hidden');
      document.getElementById('step0').classList.remove('section-hidden');
      state.currentStep = 0;
    } else {
      loadPrereqs();
    }
  } catch (e) {
    loadPrereqs();
  }
});

// ── Step 4: Hardware + Tier ────────────────────────────────────────────────

const TIER_AGENTS = { lite: 4, standard: 4, power: 8 };

async function loadHardware() {
  // Pre-populate datalist and restore saved values immediately (before any awaits)
  // so dropdowns work even while async calls are in-flight.
  if (_allModels.length) _populateDatalist(_allModels);
  if (state.models.strategic)      document.getElementById('modelStrategic').value = state.models.strategic;
  if (state.models.implementation) document.getElementById('modelImplementation').value = state.models.implementation;
  if (state.models.support)        document.getElementById('modelSupport').value = state.models.support;

  try {
    const res = await fetch('/api/hardware');
    const hw = await res.json();

    document.getElementById('hwRam').textContent = `${hw.ram_gb} GB`;
    document.getElementById('hwCpu').textContent = `${hw.cpu_cores} cores`;
    document.getElementById('hwGpu').textContent =
      hw.gpu_name ? `${hw.gpu_name}${hw.vram_gb > 0 ? ' · ' + hw.vram_gb + ' GB' : ''}` : 'Not detected';

    const rec = hw.tier;
    document.getElementById(`tier-${rec}`).classList.add('recommended');

    if (state.tier === 'standard' && state.currentStep === 4) {
      selectTier(rec);
    } else {
      renderTierCards();
    }
  } catch (e) {
    renderTierCards();
  }

  // Populate model datalist with configured models
  try {
    const res = await fetch('/api/configured-models');
    const data = await res.json();
    const models = data.models || [];
    if (models.length > 0) {
      const dl = document.getElementById('modelOptions');
      if (dl) {
        const existingIds = new Set(Array.from(dl.options).map(o => o.value));
        for (const m of models) {
          if (!existingIds.has(m.id)) {
            const opt = document.createElement('option');
            opt.value = m.id;
            opt.label = `${m.label || m.id} (${m.provider || 'custom'})`;
            dl.appendChild(opt);
          }
        }
      }
      autoFillModelAssignments(models);
    }
  } catch (e) {}

  // Restore saved values to inputs
  if (state.models.strategic)      document.getElementById('modelStrategic').value = state.models.strategic;
  if (state.models.implementation) document.getElementById('modelImplementation').value = state.models.implementation;
  if (state.models.support)        document.getElementById('modelSupport').value = state.models.support;
}

function selectTier(tier) {
  state.tier = tier;
  state.teamSize = TIER_AGENTS[tier] || 4;
  renderTierCards();
}

function renderTierCards() {
  ['lite', 'standard', 'power'].forEach(t => {
    const card = document.getElementById(`tier-${t}`);
    if (card) {
      const isRec = card.classList.contains('recommended');
      card.className = 'tier-card' +
        (t === state.tier ? ' selected' : '') +
        (isRec ? ' recommended' : '');
    }
  });
}

// ── Step 5: Themes ────────────────────────────────────────────────────────

async function loadThemes() {
  const grid = document.getElementById('themeGrid');
  try {
    const res = await fetch('/api/themes');
    state.themes = await res.json();
    // Pre-populate customCharacters from the default theme so roster shows immediately
    const defaultTheme = state.themes.find(t => t.id === state.theme);
    if (defaultTheme && Object.keys(state.customCharacters).length === 0) {
      state.customCharacters = Object.assign({}, defaultTheme.roles);
    }
    renderThemes();
    renderAgentPreview();
  } catch (e) {
    grid.innerHTML = '<p style="color:var(--red)">Could not load themes.</p>';
  }
}

function renderThemes() {
  const grid = document.getElementById('themeGrid');
  const presetCards = state.themes.map(t => `
    <div class="theme-card ${t.id === state.theme ? 'selected' : ''}" onclick="selectTheme('${escHtml(t.id)}')">
      <div class="theme-label">${escHtml(t.label)}</div>
      <div class="theme-desc">${escHtml(t.description)}</div>
    </div>
  `).join('');
  const customCard = `
    <div class="theme-card ${'custom' === state.theme ? 'selected' : ''}" onclick="selectTheme('custom')">
      <div class="theme-label">✏ Custom Theme</div>
      <div class="theme-desc">Name your own characters — one per agent role.</div>
    </div>
  `;
  grid.innerHTML = presetCards + customCard;
}

function selectTheme(id) {
  state.theme = id;
  // Pre-populate customCharacters from the selected preset so edits start pre-filled
  if (id === 'custom') {
    state.customCharacters = {};
  } else {
    const themeData = state.themes.find(t => t.id === id);
    state.customCharacters = themeData ? Object.assign({}, themeData.roles) : {};
  }
  renderThemes();
  renderAgentPreview();
}

function renderAgentPreview() {
  const container = document.getElementById('agentPreview');
  if (!container) return;
  const roles = state.teamSize === 8 ? ROLES_FULL : ROLES_MINIMAL;
  const isCustom = state.theme === 'custom';

  container.style.display = 'block';
  container.innerHTML = `
    <div style="font-size:12px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px;">
      ${isCustom ? 'Enter a character name for each role' : 'Edit names before installing — changes apply to your workspace only'}
    </div>
    ${roles.map(role => {
      const defaultVal = state.customCharacters[role] || '';
      return `
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">
          <div style="width:90px;font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.4px;flex-shrink:0;">${ROLE_LABELS_MAP[role] || role}</div>
          <input
            type="text"
            value="${escHtml(defaultVal)}"
            placeholder="${isCustom ? 'Enter name' : 'Leave blank to keep default'}"
            oninput="updateCharacterName('${role}', this.value)"
            style="flex:1;background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:5px 8px;font-size:13px;color:var(--text);"
          />
        </div>
      `;
    }).join('')}
  `;
}

function updateCharacterName(role, value) {
  state.customCharacters[role] = value.trim();
}

// ── Step 6: Review & Install ───────────────────────────────────────────────

async function checkActiveAgents() {
  const target = state.targetDir || getDefaultDir();
  const warningBox = document.getElementById('activeAgentWarning');
  if (!target || !warningBox) return;
  try {
    const res = await fetch(`/api/agent-check?target=${encodeURIComponent(target)}`);
    const data = await res.json();
    if (data.active_count > 0) {
      warningBox.innerHTML =
        `⚠️ <strong>${data.active_count} OpenClaw agent${data.active_count > 1 ? 's are' : ' is'} currently running in this workspace.</strong><br>` +
        `They will finish their current sessions unaffected. New sessions after this update will use the refreshed workspace files.`;
      warningBox.classList.remove('section-hidden');
    } else {
      warningBox.classList.add('section-hidden');
    }
  } catch (e) {
    warningBox.classList.add('section-hidden');
  }
}

const TIER_LABELS = {
  lite: 'Lite (4 agents)',
  standard: 'Standard (4 agents)',
  power: 'Power (8 agents)',
};

function loadReview() {
  const target = state.targetDir || getDefaultDir();

  if (state.installMode === 'dashboard-only') {
    document.getElementById('reviewSummary').innerHTML = `
      <table style="border-collapse:collapse;width:100%">
        <tr><td style="padding:4px 0;color:var(--text-muted);width:170px">Mode</td><td><strong>Dashboard Only</strong></td></tr>
        <tr><td style="padding:4px 0;color:var(--text-muted)">Workspace</td><td><code style="font-size:12px;color:var(--accent)">${escHtml(target)}</code></td></tr>
      </table>
      <p style="font-size:12px;color:var(--text-muted);margin-top:12px">
        Mission Control will point at this workspace for monitoring. No files will be created or modified. No agents will be registered.
        You can add agents later using the + button on the dashboard.
      </p>
    `;
    document.getElementById('filePreview').innerHTML = '<span style="color:var(--text-muted)">No files will be modified.</span>';
    document.getElementById('btnInstall').textContent = 'Confirm';
    return;
  }

  const themeData = state.themes.find(t => t.id === state.theme) || { label: state.theme };
  const mS = state.models.strategic      || document.getElementById('modelStrategic')?.value      || '(not set)';
  const mI = state.models.implementation || document.getElementById('modelImplementation')?.value || '(not set)';
  const mU = state.models.support        || document.getElementById('modelSupport')?.value        || '(not set)';

  document.getElementById('reviewSummary').innerHTML = `
    <table style="border-collapse:collapse;width:100%">
      <tr><td style="padding:4px 0;color:var(--text-muted);width:170px">Location</td><td><code style="font-size:12px;color:var(--accent)">${escHtml(target)}</code></td></tr>
      <tr><td style="padding:4px 0;color:var(--text-muted)">Team size</td><td>${state.teamSize} agents (${escHtml(TIER_LABELS[state.tier] || state.tier)})</td></tr>
      <tr><td style="padding:4px 0;color:var(--text-muted)">Strategic model</td><td><code style="font-size:12px">${escHtml(mS)}</code></td></tr>
      <tr><td style="padding:4px 0;color:var(--text-muted)">Implementation model</td><td><code style="font-size:12px">${escHtml(mI)}</code></td></tr>
      <tr><td style="padding:4px 0;color:var(--text-muted)">Support model</td><td><code style="font-size:12px">${escHtml(mU)}</code></td></tr>
      <tr><td style="padding:4px 0;color:var(--text-muted)">Theme</td><td>${escHtml(themeData.label)}</td></tr>
    </table>
  `;

  document.getElementById('filePreview').innerHTML = `
    <span style="color:var(--text-muted)">
${escHtml(target)}/\n  AGENTS.md\n  SOUL.md\n  TOOLS.md\n  USER.md\n  active-project.md\n  .claude/\n    settings.json\n  projects/\n    example-app/\n      spec.md\n      milestones.md\n      status.md\n      tickets/\n        open/\n        closed/\n        archive/\n      builds/
    </span>`;
  document.getElementById('btnInstall').textContent = 'Install Workspace';
}

async function runInstall() {
  const target = state.targetDir || getDefaultDir();
  const btn = document.getElementById('btnInstall');
  const back = document.getElementById('btnBackFromInstall');
  const progress = document.getElementById('installProgress');
  const errorBox = document.getElementById('installError');
  const success = document.getElementById('installSuccess');
  const actions = document.getElementById('step6Actions');
  const postActions = document.getElementById('step6PostActions');

  // Dashboard-only mode — just register the workspace path, no file changes
  if (state.installMode === 'dashboard-only') {
    btn.disabled = true;
    try {
      const res = await fetch('/api/install', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target, install_mode: 'dashboard-only' }),
      });
      const data = await res.json();
      if (data.ok) {
        success.classList.remove('section-hidden');
        document.getElementById('successPath').textContent = target;
        actions.classList.add('section-hidden');
        postActions.classList.remove('section-hidden');
      } else {
        errorBox.innerHTML = `<div class="error-box">${escHtml(data.error || 'Failed')}</div>`;
        errorBox.classList.remove('section-hidden');
        btn.disabled = false;
      }
    } catch (e) {
      errorBox.innerHTML = `<div class="error-box">${escHtml(e.message)}</div>`;
      errorBox.classList.remove('section-hidden');
      btn.disabled = false;
    }
    return;
  }

  const modelStrategic = state.models.strategic      || document.getElementById('modelStrategic')?.value      || 'claude-sonnet-4-6';
  const modelImpl      = state.models.implementation || document.getElementById('modelImplementation')?.value || 'claude-sonnet-4-6';
  const modelSupport   = state.models.support        || document.getElementById('modelSupport')?.value        || 'claude-sonnet-4-6';

  btn.disabled = true;
  back.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Installing...';
  progress.style.display = 'block';
  errorBox.classList.add('section-hidden');
  success.classList.add('section-hidden');

  let pct = 0;
  const fill = document.getElementById('progressFill');
  const label = document.getElementById('progressLabel');
  const ticker = setInterval(() => {
    pct = Math.min(pct + 3, 85);
    fill.style.width = pct + '%';
  }, 150);

  try {
    const res = await fetch('/api/install', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        target,
        theme: state.theme === 'custom' ? 'historical' : state.theme,  // fallback for template load
        custom_characters: state.customCharacters,
        team_size: state.teamSize,
        tier: state.tier,
        install_mode: state.installMode,
        project_name: 'example-app',
        operator_name: 'Operator',
        model_strategic:      modelStrategic,
        model_implementation: modelImpl,
        model_support:        modelSupport,
      }),
    });
    const data = await res.json();
    clearInterval(ticker);

    if (data.ok) {
      fill.style.width = '100%';
      label.textContent = `${data.created?.length || 0} files created successfully.`;
      setTimeout(() => {
        progress.style.display = 'none';
        success.classList.remove('section-hidden');
        document.getElementById('successPath').textContent = data.workspace;
        actions.classList.add('section-hidden');
        postActions.classList.remove('section-hidden');
      }, 600);
    } else {
      clearInterval(ticker);
      progress.style.display = 'none';
      errorBox.innerHTML = `<div class="error-box">Installation failed: ${escHtml(data.error || 'Unknown error')}</div>`;
      errorBox.classList.remove('section-hidden');
      btn.disabled = false;
      back.disabled = false;
      btn.innerHTML = 'Retry Install';
    }
  } catch (e) {
    clearInterval(ticker);
    progress.style.display = 'none';
    errorBox.innerHTML = `<div class="error-box">Could not connect to installer service: ${escHtml(e.message)}</div>`;
    errorBox.classList.remove('section-hidden');
    btn.disabled = false;
    back.disabled = false;
    btn.innerHTML = 'Retry Install';
  }
}

async function openWorkspaceFolder() {
  const path = document.getElementById('successPath')?.textContent;
  if (!path) return;
  await fetch(`/api/open-folder?path=${encodeURIComponent(path)}`);
}
