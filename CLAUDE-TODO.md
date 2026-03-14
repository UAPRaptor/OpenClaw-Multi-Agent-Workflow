# OpenClaw Multi-Agent Workflow — TODO

## Build Protocol

Running `package.bat` (Windows) or `package.sh` (Mac) now prompts for a version bump before building:
- `[1] patch` — bug fixes, small tweaks (x.y.Z+1)
- `[2] minor` — new features within a version milestone (x.Y+1.0)
- `[3] major` — breaking changes or production-grade releases (X+1.0.0)
- `[4] keep` — rebuild without bumping (e.g., testing the build itself)

The script writes the new version to `VERSION` and names the zip accordingly.

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

### v0.3.0 — Monitor & Dashboard Improvements
Richer real-time visibility into agent activity.

- [ ] [D2] Ticket stale badge — highlight tickets in `in-progress` or `blocked` > 4 hours
- [ ] [D2] Click kanban column to expand and show ticket file names
- [ ] [D2] Session log viewer — show recent AGENT-SESSION-LOG.md entries per agent in dashboard
- [ ] [D2] Installer: show character roster preview when a theme is selected (role → character mapping)
- [ ] [D3] Milestone completion count for overnight mode (parse overnight-report.md)
- [ ] [D3] Multi-workspace support — monitor more than one workspace simultaneously

---

### v0.4.0 — Agent Control & Project Management
Move from passive monitoring to active control from the dashboard.

- [ ] [D3] Show ticket content when clicking kanban columns (not just counts)
- [ ] [D3] Add agent start/stop controls from the dashboard
- [ ] [D3] Add project management from UI — create/switch active projects without editing files

---

### v0.5.0 — Testing Coverage
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
