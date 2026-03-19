# OpenClaw Multi-Agent Workflow

A training corpus and operational framework for running multiple [OpenClaw](https://docs.openclaw.ai) agents as a coordinated software development team — plus **Mission Control**, a local installer and monitoring dashboard for deploying and watching those agents.

## What It Does

- **Installs** a multi-agent workspace with a browser-based wizard (theme selection, model config, team size)
- **Monitors** agent activity in real time: ticket board, stale alerts, session logs, system info
- **Chats** with individual agents from an embedded chat panel (session continuity, agent-to-agent spawning)
- **Manages** projects, backups, skills, and agent identity from the dashboard

## Quick Start

```bash
cd mission-control
pip install -r requirements.txt

# Install a new workspace (opens browser wizard at localhost:8765)
python -m openclaw install

# Monitor an existing workspace
python -m openclaw monitor

# Quick text summary (no browser)
python -m openclaw status
```

Or double-click the one-click launchers:
- **Mac:** `launch_agents.command` / `monitor_agents.command`
- **Windows:** `launch_agents.bat` / `monitor_agents.bat`

## Requirements

- Python 3.10+
- [OpenClaw](https://docs.openclaw.ai) installed and configured

## Repository Structure

```
OpenClaw-Multi-Agent-Workflow/
├── training/                   Workflow docs, security guidelines, character profiles
│   ├── openclaw-workflow-overview.md
│   ├── agent-character-profiles.md
│   ├── agent-character-profiles-fiction.md
│   ├── agent-security.md
│   └── ...
│
├── mission-control/            Mission Control app (Python + FastAPI)
│   ├── VERSION                 Current version
│   ├── requirements.txt        Python dependencies
│   ├── setup.py                pip-installable package
│   ├── openclaw/               Python package
│   │   ├── cli.py              CLI: install / monitor / status
│   │   ├── installer/          Prerequisite checker, workspace builder, template deployer
│   │   ├── monitor/            File watcher, state reader, alert engine, state store
│   │   ├── web/                FastAPI server, WebSocket hub, static dashboard
│   │   └── corpus/             Bundled templates (characters, workspace, project, settings)
│   ├── tests/                  pytest suite (34 tests)
│   ├── launch_agents.command   Mac one-click installer
│   ├── launch_agents.bat       Windows one-click installer
│   ├── monitor_agents.command  Mac one-click monitor
│   └── monitor_agents.bat      Windows one-click monitor
│
└── .github/workflows/         CI: auto-builds zip on version tag push
```

## Features

### Installer Wizard
- 6-step browser wizard: prerequisites, model setup, workspace location, team size, theme selection, deploy
- 5 character themes: Historical, TMNT, Star Trek, Avengers, Lord of the Rings (or custom)
- Configurable team size (1-8 agents) with role-based model assignment
- Install modes: new, upgrade (preserves custom files), replace

### Monitor Dashboard
- Real-time agent status cards with character identity and activity
- Kanban ticket board with severity badges and stale indicators
- Session log viewer
- System info card (OS, Python, disk usage)
- Gateway control bar (start/stop/restart)
- Embedded agent chat panel with session continuity
- Project switching and creation
- Workspace backup and restore
- Installed skills overview
- Security alerts (settings.json modifications, stalled agents)

### Agent Identity System
- Per-agent IDENTITY.md with character persona, role methodology, and provenance
- Agent registration with OpenClaw's native agent directory
- Agent-to-agent spawning (any agent can invoke any other)
- Cleanup tools for orphaned/archived agents

## Security

- Server binds to `127.0.0.1` only — never network-accessible
- Monitor is read-only — cannot modify workspace files
- `.claude/settings.json` modification triggers immediate security alert
- `mission-control-alerts.log` is append-only (forensic trail)
- Optional bearer token auth (`--auth` flag)
- Pydantic request validation on all API endpoints
- No telemetry, no outbound calls

## Packaging

```bash
cd mission-control

# Build zip for distribution
bash package.sh   # Mac
package.bat       # Windows

# Build standalone binary (no Python required on target)
bash build.sh     # Mac    → dist/openclaw-mac
build.bat         # Windows → dist/openclaw-windows.exe
```

## Running Tests

```bash
cd mission-control
pip install pytest
python -m pytest tests/ -v
```

## License

See repository for license details.
