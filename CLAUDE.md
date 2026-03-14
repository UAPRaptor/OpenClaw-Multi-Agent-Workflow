# OpenClaw Multi-Agent Workflow — Project Context

## What This Project Is

A training corpus and operational framework for running multiple Claude Code (OpenClaw) agents as a coordinated software development team — plus **OpenClaw Mission Control**, a local installer and monitoring app for deploying and watching those agents.

## Repository Structure

```
OpenClaw-Multi-Agent-Workflow/
├── training/                        Workflow docs, security guidelines, character profiles
│   ├── openclaw-workflow-overview.md   Canonical agent workflow architecture
│   ├── agent-character-profiles.md     Historical character archetypes per role
│   ├── agent-character-profiles-fiction.md  TMNT, Star Trek, Avengers, LOTR themes
│   ├── agent-security.md               OWASP Agentic Top 10 threat intelligence
│   ├── agent-monitoring-and-control.md  Monitor requirements
│   ├── advanced-agent-training.md       Security, testing, dependency guidance
│   ├── network-host-security.md         Host hardening and network isolation
│   ├── official-sources.md             Approved reference sources
│   ├── training-corpus-index.md        Index of all training resources
│   └── training-resource-types.md      Five required resource types
│
├── mission-control/                  OpenClaw Mission Control app (Python)
│   ├── VERSION                       Current version (e.g. 0.1.0)
│   ├── requirements.txt              Python dependencies
│   ├── setup.py                      pip-installable package
│   ├── launch_agents.bat             Windows one-click launcher (install wizard)
│   ├── launch_agents.command         Mac one-click launcher (install wizard)
│   ├── monitor_agents.bat            Windows one-click monitor dashboard
│   ├── monitor_agents.command        Mac one-click monitor dashboard
│   ├── package.bat                   Windows: builds releases/ zip
│   ├── package.sh                    Mac: builds releases/ zip
│   ├── build.bat                     Windows: PyInstaller single-binary build
│   ├── build.sh                      Mac: PyInstaller single-binary build
│   ├── releases/                     Zip packages for distribution / USB
│   └── openclaw/                     Python package
│       ├── __init__.py               Version reader
│       ├── __main__.py               Entry point
│       ├── cli.py                    CLI: install / monitor / status commands
│       ├── platform_utils.py         Mac/Windows path abstraction
│       ├── corpus/                   Bundled workspace templates
│       │   ├── characters/           Theme JSON (historical, tmnt, star-trek, avengers, lotr)
│       │   ├── workspace/            AGENTS.md, SOUL.md, TOOLS.md, USER.md templates
│       │   ├── project/              spec.md, milestones.md, status.md, ticket.md templates
│       │   └── settings/             settings.json.base
│       ├── installer/                Prerequisite checker, workspace builder, template deployer
│       ├── monitor/                  File watcher, state reader, alert engine, state store
│       └── web/                      FastAPI server, WebSocket hub, static HTML/JS/CSS
│
└── .github/workflows/release.yml    Auto-builds zip on version tag push
```

## Tech Stack (Mission Control App)

- **Language:** Python 3.10+
- **Web framework:** FastAPI + uvicorn
- **Filesystem monitoring:** watchdog (FSEvents on Mac, ReadDirectoryChangesW on Windows)
- **Templates:** Jinja2
- **CLI:** Typer
- **Distribution:** PyInstaller (single binary), or bootstrap launchers + pip

## How to Run (Dev)

```bash
cd mission-control
pip install -r requirements.txt
python -m openclaw install       # Opens installer wizard at localhost:8765
python -m openclaw monitor       # Opens monitor dashboard
python -m openclaw status        # Quick text summary, no browser
```

## How to Package

```bash
# Build zip for distribution (USB or GitHub release)
cd mission-control
package.bat       # Windows
bash package.sh   # Mac

# Build standalone binary (no Python required on target)
build.bat         # Windows → dist/openclaw-windows.exe
bash build.sh     # Mac    → dist/openclaw-mac
```

## Security Notes

- Server binds to 127.0.0.1 only — never network-accessible
- Monitor is read-only — cannot modify workspace files
- `.claude/settings.json` modification triggers immediate security alert
- `mission-control-alerts.log` is append-only (forensic trail)
- No telemetry, no outbound calls

## Versioning

Bump `mission-control/VERSION`, commit, then `git tag vX.Y.Z && git push --tags`.
GitHub Actions automatically builds the release zip and posts it to GitHub Releases.
