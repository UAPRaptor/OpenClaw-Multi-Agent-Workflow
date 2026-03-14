# OpenClaw Multi-Agent Workflow — TODO

## Priority Queue

### 1. First Run Testing [D2]
Verify the full install and monitor flow works end-to-end on a real machine.

- [ ] [D1] Install Python deps: `cd mission-control && pip install -r requirements.txt`
- [ ] [D2] Run `python -m openclaw install` — verify browser opens, all 6 wizard steps work (Check → Models → Location → Team → Theme → Install)
- [ ] [D2] Complete installer: configure a model provider, pick 4-agent team, Historical theme, default workspace path
- [ ] [D2] Run `python -m openclaw monitor` — verify dashboard loads and reflects workspace state
- [ ] [D1] Run `python -m openclaw status` — verify text summary output
- [ ] [D2] Test `launch_agents.bat` double-click on a Windows machine without Python pre-installed

### 2. PyInstaller Binary Build [D2]
Produce standalone distributable binaries that require no Python on the target machine.

- [ ] [D2] Run `build.bat` on Windows → verify `dist/openclaw-windows.exe` launches and opens browser
- [ ] [D2] Run `build.sh` on Mac → verify `dist/openclaw-mac` works
- [ ] [D1] Attach binaries to a GitHub Release alongside the zip

### 3. GitHub Repo Setup [D1]
Wire up the repo for automated releases.

- [ ] [D1] Push this repo to GitHub (create remote if not exists)
- [ ] [D1] Test the release workflow: bump VERSION to 0.1.0, tag v0.1.0, push — verify zip appears in GitHub Releases
- [ ] [D1] Verify `.gitignore` excludes `.venv/`, `dist/`, `build/`, `__pycache__/`

### 4. Agent Roster Detection [D3] ✅
~~The monitor currently uses a hardcoded 4-agent list. Make it dynamic.~~
Completed — file_watcher now parses AGENTS.md dynamically.

### 5. Installer Enhancements [D2]
Small UX improvements identified during planning.

- [x] [D2] Step 2: Add OS-appropriate default path to the directory input field on page load
- [ ] [D2] Step 4: Show character roster preview when a theme is selected (which character = which role)
- [x] [D1] Add "Open workspace folder" button on success screen

### 6. Monitor Enhancements [D3]
Nice-to-have dashboard improvements.

- [ ] [D3] Milestone completion count for overnight mode (parse overnight-report.md)
- [ ] [D2] Ticket stale badge: highlight tickets in `in-progress` or `blocked` > 4 hours
- [ ] [D2] Click kanban column to expand and show ticket file names
- [ ] [D3] Multi-workspace support: monitor more than one workspace simultaneously

### 7. Security Hardening [D3]
Issues identified in code review — security-critical items for a tool that orchestrates agents.

- [ ] [D3] Add authentication to the web server — at minimum a random bearer token generated at startup, displayed in terminal, required for all API calls and WebSocket connections
- [ ] [D2] Encrypt API keys at rest — provider keys saved via `/api/configure-provider` are currently plaintext in OpenClaw config; use OS keyring (`keyring` library) or encrypted JSON with a machine-derived key
- [ ] [D2] Ollama installer integrity — verify checksums for downloaded Ollama binaries before executing; pin to known-good versions
- [x] [D1] Populate deny list in `settings.json.base` — currently empty `allowedTools` array; add sensible defaults for dangerous commands
- [ ] [D3] Add Pydantic request validation to all API endpoints — currently raw dict access with no schema enforcement

### 8. Code Quality [D2]
Correctness and robustness fixes.

- [x] [D2] Fix shallow copy race in `state_store.get()` — `return self._state` shares the mutable dict; use `copy.deepcopy()` or return frozen snapshots
- [x] [D1] Fix WebSocket ping interval leak in `app.js` — `setInterval` inside `ws.onopen` creates a new interval on every reconnect without clearing the previous one
- [x] [D1] Replace deprecated `datetime.utcnow()` in `state_store.py` with `datetime.now(tz=timezone.utc)`
- [x] [D2] Launcher scripts still run `claude --model` instead of `openclaw --model` — update `workspace_builder.py` launcher generation

### 9. Monitor Feature Gaps [D3]
Dashboard currently shows summaries but lacks actionable detail.

- [ ] [D3] Show ticket content when clicking kanban columns (not just counts)
- [ ] [D3] Add agent start/stop controls from the dashboard
- [ ] [D2] Add session log viewer — show recent AGENT-SESSION-LOG.md entries per agent
- [ ] [D3] Add project management from UI — create/switch active projects without editing files

### 10. Testing [D3]
Zero test coverage currently.

- [ ] [D3] Add pytest suite: unit tests for state_store, alert_engine, template_deployer, platform_utils
- [ ] [D2] Add integration test: install flow end-to-end (create temp workspace, verify files)
- [ ] [D2] Add frontend smoke tests (playwright or similar) for installer wizard steps

### 11. Documentation [D1]
- [ ] [D1] Update `README.md` with full usage instructions and screenshot
- [ ] [D1] Add `QUICKSTART.txt` to the release zip for non-technical users

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
