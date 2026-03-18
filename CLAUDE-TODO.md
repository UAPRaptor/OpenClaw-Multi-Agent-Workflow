# OpenClaw Multi-Agent Workflow — TODO

## Build Protocol

Run `package.bat` (Windows) or `package.sh` (Mac) to build a zip. Version is managed manually per commit:
- **Every bug fix** → patch increment (x.y.Z+1), no matter how small
- **New feature** → minor increment (x.Y+1.0)
- **Breaking change / architectural shift** → major increment (X+1.0.0)

---

## Bug Queue
Bugs reported during testing — fix these before resuming feature work. Each fix = patch bump.

- [x] [D2] **Mac: SETUP-MAC.command blocked by Gatekeeper** — Root cause: zip built on Windows (package.bat) can't set Unix execute bits, so all .command files land with no execute permission on Mac. Fixed with README-MAC.txt at zip root: one Terminal paste handles xattr, chmod, and launch regardless of version name or build OS. [📷](training/bugs/bug1-setup-mac-permissions.png)

- [x] [D2] **Step 2 (Model Setup): Allow unchecking configured models** — Models are now toggleable checkboxes. Clicking unchecks (strikethrough + grayed), removes from datalist dropdowns, and click again to re-enable. Selection persists through the install flow via state.deselectedModels. [📷](training/bugs/bug2-model-setup-uncheckable.png)

- [x] [D3] **Step 5 (Theme): Add custom theme option** — "✏ Custom Theme" card added; selecting it shows blank name inputs for all roles; names passed as custom_characters at install time. [📷](training/bugs/bug3-theme-custom.png)

- [x] [D3] **Step 5 (Theme): Allow editing character names after theme selection** — Editable roster appears below theme cards immediately after selection; inputs pre-filled with theme defaults; edits override character names at install time. [📷](training/bugs/bug3-theme-edit.png)

- [x] [D2] **Dashboard: Clarify "Install" tab label** — Renamed "Install" to "New Workspace" in both nav bars and the workspace card. [📷](training/bugs/bug4-install-tab-unclear.png)

- [x] [D2] **Dashboard: Add agent settings/details modal** — ⚙ cog button on each agent card opens modal with: status, last active, model, workspace path, launcher paths (Mac + Windows), OpenClaw agent dir, registration status (✔/✘). [📷](training/bugs/bug4-agent-details.png)

- [x] [D2] **Installer Step 3: "New location" button does nothing** — Root cause: goStep(1) triggered loadPrereqs() which re-detected the existing workspace and bounced back to step 0 in a loop. Fixed by jumping directly to step 2 (prereqs already passed). [📷](training/bugs/bug5-new-location-broken.png)

- [x] [D3] **Installer Step 3: Allow manually browsing for workspaces** — "Browse…" button added; calls /api/browse-folder which opens native OS folder dialog (PowerShell on Windows, osascript on Mac); selected path populates input and triggers existing-workspace detection. [📷](training/bugs/bug5-browse-workspace.png)

- [x] [D3] **Installer Step 3: Manage existing agents in detected workspace** — Agent list shown when existing workspace detected; each agent shows role, character, model with a Remove button; /api/workspace-agents parses AGENTS.md; /api/workspace-agents/delete removes from AGENTS.md and ~/.openclaw/agents/{role}/. [📷](training/bugs/bug5-manage-agents.png)

- [x] [D3] **Agents created by Mission Control don't appear in OpenClaw dashboard** — /api/reregister-agents re-runs registration from AGENTS.md; "Re-register Agents" button on dashboard; write_openclaw_workspace_path() now called on every install to write workspace path to ~/.openclaw/config.json. [📷](training/bugs/bug6-openclaw-discovery.png)

- [x] [D3] **Workspace path mismatch between Mission Control and OpenClaw** — /api/openclaw-workspace detects path mismatch; OpenClaw Sync card on dashboard shows ✔ match or ⚠ mismatch with both paths displayed and Re-register button to fix. [📷](training/bugs/bug6-workspace-path-mismatch.png)

---

## Version Roadmap

### v0.2.0 — Validation + Security Foundation
Confirm the current build works end-to-end, then lock down the security surface before adding features.

**Validation (D1/D2)**
- [ ] [D1] Install Python deps: `cd mission-control && pip install -r requirements.txt`
- [ ] [D1] Run `python -m openclaw status` — verify text summary output
- [ ] [D1] Test release workflow: bump VERSION via package.bat, tag, push → verify zip in GitHub Releases
- [ ] [D2] Run `python -m openclaw install` — verify browser opens, all wizard steps work end-to-end
- [ ] [D2] Run `python -m openclaw monitor` — verify dashboard loads and reflects workspace state
- [ ] [D2] Test `launch_agents.bat` double-click on a Windows machine without Python pre-installed

**Security (D2/D3)**
- [ ] [D2] Encrypt API keys at rest — use OS keyring (`keyring` library) or machine-derived encrypted JSON; currently plaintext in OpenClaw config
- [ ] [D2] Ollama installer integrity — verify checksums for downloaded binaries before executing; pin to known-good versions
- [ ] [D3] Add authentication to the web server — random bearer token at startup, displayed in terminal, required for all API calls and WebSocket connections
- [ ] [D3] Add Pydantic request validation to all API endpoints — currently raw dict access with no schema enforcement

---

### v0.3.0 — OpenClaw Agent Registration + Agent Identity Model
Make installed agents first-class citizens of the OpenClaw universe so they appear in OpenClaw's native dashboard and can be chatted with directly.

**Problem:** The installer creates workspace files (AGENTS.md, SOUL.md, run scripts) but never registers agents with OpenClaw's own agent directory system at `~/.openclaw/agents/`. Agents are invisible to OpenClaw's native UI and chat interface. Additionally, no explicit `agentId`/`displayName` fields, no cleanup path for orphaned agents, no visibility into which agents are managed vs runtime vs test.

**Completed work:**
- [x] [D3] Create OpenClaw agent directories — for each installed role, create `~/.openclaw/agents/{role}/` with `IDENTITY.md` (character persona, role, philosophy) — invoked via `openclaw agent --agent {role} --message "..."`
- [x] [D3] Register agents at install time — `agent_registrar.py` renders `IDENTITY.md.template` per role and writes to `~/.openclaw/agents/{role}/IDENTITY.md`
- [x] [D3] Launch scripts per agent — per-role launchers run `openclaw agent --agent {role} --message "..."` from workspace root; also added missing `HEARTBEAT.md` to workspace
- [x] [D2] Agent identity model (Item 1) — explicit `agentId` and `displayName` fields throughout; centralized `ROLE_LABELS` dict (single import in `template_deployer.py`); removed 4 duplicate definitions
- [x] [D2] Agent cleanup tools (Item 5) — `unregister_agent()`, `archive_agent()`, `purge_agent()`, `sync_existing_agents_to_config()` functions; `POST /api/agents/cleanup` endpoint; Agent Cleanup UI card with action buttons
- [x] [D3] Agent reconciliation (Item 7) — `agent_reconciler.py` classifies agents as managed/runtime/test/orphaned/unmanaged/missing; `GET /api/agent-registry` endpoint; displayName markdown-strip fix

**Remaining work:**
- [x] [D2] Mission Control "Start Agent" button — add a start button to each agent card on the dashboard that runs that agent's launcher script in a new Terminal window
- [x] [D4] Click-to-chat with agent — clicking an agent card in Mission Control opens a chat session with that agent (either via OpenClaw's native chat or an embedded chat panel)

---

### v0.3.x — Agent Identity UI (deferred from Items 2–4, 6, 8)

Remaining agent UX polish. Requires Items 1/5/7 (complete as of v0.3.0) as foundation.

- [ ] [D2] **Item 2**: Agent card redesign — show displayName as primary, role key as secondary, agentId as metadata footer
- [ ] [D3] **Item 3**: "Open in Chat" button on each agent card — deep-links to OpenClaw's native chat for that agent (requires figuring out OpenClaw chat URL scheme)
- [ ] [D3] **Item 4**: Dedicated Agent Registry page — full-page view of managed/runtime/test/orphaned/missing agents with sort/filter
- [ ] [D2] **Item 6**: Provenance timestamps — write createdAt + workflowId to IDENTITY.md footer at install time
- [ ] [D3] **Item 8**: displayName → role → agentId mapping panel — explicit table UI showing the three-field identity for each agent

---

### v0.4.x — Embedded Agent Chat (chat panel in Mission Control)

Allow chatting with agents directly from the Mission Control dashboard, without needing the OpenClaw native app.

**Architecture (as built):**
Used `openclaw agent --json --session-id` subprocess instead of WebSocket proxying. The gateway WebSocket requires `operator.read`/`operator.write` scopes which the static token does not grant; the `cli` client mode connects but scope checks block chat methods. The subprocess approach sidesteps this entirely and provides full session continuity via `--session-id` from the JSON response.

**Sub-tasks:**
- [x] [D2] Reverse-engineer OpenClaw gateway HTTP API — WebSocket RPC protocol reverse-engineered from gateway JS bundle; `openclaw agent --json` is the right integration path (scope constraints block direct WebSocket chat)
- [x] [D3] Gateway proxy endpoint — `POST /api/chat/send` in server.py; uses `asyncio.create_subprocess_exec` + `openclaw agent --json` with 120s timeout; validates agentId/sessionId to prevent injection
- [ ] [D3] SSE streaming — `openclaw agent` runs synchronously (no token stream); future: intercept gateway WebSocket events if scope issue is resolved
- [x] [D3] Session tracking — sessionId stored per-agent in browser JS (`_chatSessions`); `DELETE /api/chat/session/{agentId}` endpoint; "↺ New Chat" button clears session
- [x] [D2] Chat panel UI — slide-up modal with full message history, typing indicator, Enter-to-send, auto-resize textarea, model tag per response
- [x] [D2] Gateway health check — gateway status bar (v0.3.3+) already shows running/stopped with green/red indicator
- [x] [D2] Restart MC button — ↺ Restart MC in gateway bar, auto-reloads browser after recovery (v0.4.1)

---

### v0.4.x — Agent Communication + Identity (in progress)

- [x] [D3] Agent-to-agent spawning — subagents.allowAgents on all agents; any agent can now spawn any other (v0.4.3)
- [x] [D2] Correct agent identity names — identity.name in openclaw.json; gateway uses Splinter/Donatello/etc. not "Sensei" (v0.4.3)
- [x] [D2] "New Chat" button now calls DELETE /api/chat/session/{agentId} which clears server-side session store; server tracks sessionIds per agent and uses them as fallback; fresh chats truly start clean
- [x] [D2] GitHub push — sensei-crab added as collaborator on UAPRaptor/OpenClaw-Multi-Agent-Workflow; invitation accepted via API; all 17 pending commits pushed to origin/master
- [ ] [D3] SSE streaming — openclaw agent runs synchronously; no token stream yet; future: intercept gateway WebSocket events if scope issue is resolved
- [ ] [D3] Spawned agent visibility in chat panel — when Splinter (or any agent) spawns subagents, their responses appear in the gateway session system but not in the MC chat panel; subscribe to gateway WebSocket events or poll session activity to show spawned agent messages inline in the chat UI

---

### v0.4.0 — Monitor & Dashboard Improvements
Richer real-time visibility into agent activity.

- [x] [D2] Ticket stale badge — amber warning banner when tickets in `in-progress` or `blocked` > 4 hours (uses file mtime from ticket .md files)
- [x] [D2] Click kanban column to expand and show ticket file names — clickable columns reveal ticket titles with stale indicators; also fixed Status parsing bug (markdown ** not stripped)
- [x] [D2] Session log viewer — full-width dashboard card showing 10 most recent AGENT-SESSION-LOG.md entries with Refresh button; GET /api/session-log endpoint parses markdown table
- [ ] [D2] Installer: show character roster preview when a theme is selected (role → character mapping)
- [ ] [D3] Milestone completion count for overnight mode (parse overnight-report.md)
- [ ] [D3] Multi-workspace support — monitor more than one workspace simultaneously

---

### v0.5.0 — Agent Control & Project Management
Move from passive monitoring to active control from the dashboard.

- [ ] [D3] Show ticket content when clicking kanban columns (not just counts)
- [ ] [D3] Add project management from UI — create/switch active projects without editing files

---

### v0.6.0 — Testing Coverage
Establish a test baseline before the 1.0 release.

- [ ] [D2] Add integration test: install flow end-to-end (create temp workspace, verify files)
- [ ] [D2] Add frontend smoke tests (playwright or similar) for installer wizard steps
- [ ] [D3] Add pytest suite: unit tests for state_store, alert_engine, template_deployer, platform_utils

---

### v1.0.0 — Production Distribution
Standalone binaries and polished docs. Production-ready release.

- [ ] [D1] Update `README.md` with full usage instructions and screenshot
- [ ] [D1] Add `QUICKSTART.txt` to the release zip for non-technical users
- [ ] [D2] Run `build.bat` on Windows → verify `dist/openclaw-windows.exe` launches and opens browser
- [ ] [D2] Run `build.sh` on Mac → verify `dist/openclaw-mac` works
- [ ] [D1] Attach binaries to a GitHub Release alongside the zip

---

## Completed

| Date | Item |
|------|------|
| 2026-03-13 | Initial project planning — chose Python + FastAPI + browser dashboard architecture |
| 2026-03-13 | Built full Mission Control app: installer wizard, monitor dashboard, corpus templates, character themes (5), platform abstraction, FastAPI server, WebSocket live updates, alert engine, file watcher |
| 2026-03-13 | Added one-click launchers: launch_agents.bat, launch_agents.command, monitor_agents.bat, monitor_agents.command |
| 2026-03-13 | Added version tracking: VERSION file, /api/version endpoint, version badge in UI header |
| 2026-03-13 | Added packaging: package.bat, package.sh, releases/ folder, GitHub Actions release workflow |
| 2026-03-13 | Created CLAUDE.md, CLAUDE-TODO.md, CLAUDE-SESSION-LOG.md for this project |
| 2026-03-13 | Added agent session logging workflow: MEMORY.md.template, AGENT-TODO.md.template, AGENT-SESSION-LOG.md.template; baked rules into SOUL.md; wired all into template_deployer.py |
| 2026-03-13 | Bug fixes from first Mac run: fixed \C SyntaxWarning in platform_utils.py, made OpenClaw check non-blocking (warning not blocker), fixed default workspace to ~/Documents/openclaw-workspace, server now provides default_target to browser |
| 2026-03-13 | Vendor-agnostic model provider configuration: 6-step installer wizard, model setup step with API key validation (OpenAI, OpenRouter), OAuth fallback (Anthropic, GitHub), Ollama install+pull with SSE streaming, ROLE_GROUP-based model assignment |
| 2026-03-13 | Security quick wins: XSS protection (escHtml in installer.js), path traversal validation on /api/install, monitor state/alerts moved outside workspace to ~/.openclaw-mission-control/, dynamic agent roster from AGENTS.md, workspace discovery fix |
| 2026-03-13 | Branding cleanup: all "Claude Code" references → "OpenClaw" across platform_utils, config_writer, workspace_builder, CLAUDE.md.template; removed hardcoded Anthropic model recommendations from get_hardware_info() |
| 2026-03-14 | Code quality D1/D2 fixes: datetime.utcnow() → timezone.utc, WebSocket ping interval leak, shallow copy race (deepcopy), launcher scripts (claude→openclaw), deny list populated, "Open Folder" button on success screen |
| 2026-03-14 | Repo published to GitHub; v0.1.0 zip packaged (73KB); package.ps1 added as reliable Windows packager |
| 2026-03-14 | Agent handoff coordination: HANDOFF.md.template (per-project kickoff queue), ROLE_CHAIN + ROLE_START_CONDITIONS in template_deployer.py, AGENTS.md/SOUL.md/MEMORY.md templates updated with handoff protocol, three install modes (new/upgrade/replace), /api/check-workspace-path, installer Step 3 upgrade UI (debounceCheckPath, checkPath, selectInstallMode, confirmLocation), install_mode wired through server.py + installer.js |
| 2026-03-14 | Version auto-increment added to package.bat and package.sh (patch/minor/major/keep prompt); CLAUDE-TODO.md restructured into version milestones (v0.2.0 → v1.0.0) |
| 2026-03-14 | v0.2.0 — Agent registration first attempt (wrong — used CLAUDE.md naming, reverted in v0.2.1) |
| 2026-03-15 | v0.2.1 — Correct OpenClaw agent registration: IDENTITY.md.template in corpus/agents/ deployed to ~/.openclaw/agents/{role}/IDENTITY.md; HEARTBEAT.md added to workspace; launchers use openclaw agent --agent {role} --message "..."; all CLAUDE.md workspace files removed |
| 2026-03-16 | v0.3.0 — Agent identity model (Item 1): explicit agentId + displayName fields throughout; centralized ROLE_LABELS to single import in template_deployer.py; removed 4 duplicate definitions |
| 2026-03-16 | v0.3.0 — Agent cleanup tools (Item 5): unregister_agent(), archive_agent(), purge_agent(), sync_existing_agents_to_config(); POST /api/agents/cleanup endpoint; Agent Cleanup & Orphan Management UI card |
| 2026-03-16 | v0.3.0 — Agent reconciliation (Item 7): agent_reconciler.py classifies agents as managed/runtime/test/orphaned/unmanaged/missing; GET /api/agent-registry endpoint; displayName markdown-strip fix |
| 2026-03-16 | Training: Added openclaw-gateway-architecture.md explaining OpenClaw gateway, sessions, agent routing, and bindings system |
| 2026-03-16 | v0.3.1 — Bug fix: Agent workspace path registration + broken Start Agent button (launches in Terminal using non-existent openclaw start command) |
| 2026-03-16 | v0.3.2 — Fix: Remove broken openclaw start; add proper Set as Main feature (PUT /api/agents/set-main/{role}) to promote agents to primary chat entrypoint. Replace Start button with Chat/Verify/Set-as-Main actions. Update launchers to use valid openclaw agent command. |
| 2026-03-16 | v0.3.3 — Feature: Gateway control bar below header with status indicator (green/red/yellow) and buttons for start/stop/restart/refresh. All gateway lifecycle operations now available from UI. Auto-polls every 5 seconds. Restart banner shows after config changes. |
| 2026-03-16 | v0.4.0 — Feature: Embedded agent chat panel in Mission Control. POST /api/chat/send uses openclaw agent --json subprocess with session continuity (--session-id). DELETE /api/chat/session/{agentId} to reset. Slide-up chat modal with message history, typing indicator, Enter-to-send, model tag. Reverse-engineered OpenClaw gateway WebSocket protocol (RPC over WS, cli client mode works, operator.read scope blocked by token config). |
| 2026-03-17 | v0.4.1 — Fix: Request import missing in server.py (causing 422 on all chat calls). Add POST /api/server/restart with venv-safe spawn + os._exit(0). Add ↺ Restart MC button to gateway bar with browser auto-reload. |
| 2026-03-17 | v0.4.2 — Fix: Strip markdown bold from character names in agent_state_reader.py (** Splinter → Splinter). Chat panel and session continuity confirmed working end-to-end. Known-good milestone. |
| 2026-03-17 | v0.4.3 — Fix: Agent-to-agent spawning: add subagents.allowAgents to all agents in openclaw.json so any agent can spawn any other. Add agentDir and identity.name to each agent entry so gateway uses correct character name (Splinter not Sensei). Update agent_registrar.py to write all three fields at install time. Add neutral workspace IDENTITY.md.template. |
