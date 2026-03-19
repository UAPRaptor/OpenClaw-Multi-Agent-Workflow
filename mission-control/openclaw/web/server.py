"""
FastAPI application.
Binds ONLY to 127.0.0.1 — never accessible from the network.
Serves the installer wizard, monitor dashboard, REST API, and WebSocket.
"""
import asyncio
import json
import os
import sys
import platform
import shutil
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from openclaw.web.websocket_hub import hub
from openclaw.platform_utils import (
    get_corpus_dir, get_default_workspace_dir, find_existing_workspaces,
    save_last_workspace, load_last_workspace, write_openclaw_workspace_path,
    get_hardware_info, find_active_claude_processes,
    detect_openclaw_models, find_openclaw_config_path, update_openclaw_config,
    find_openclaw_binary, open_browser, is_windows,
)
from openclaw.installer.template_deployer import ROLE_LABELS
from openclaw import __version__

# These are injected at startup from the CLI
_store = None
_workspace_root: Path | None = None
_installer_context: dict = {}

app = FastAPI(title="OpenClaw Mission Control", docs_url=None, redoc_url=None)


def _static_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "openclaw" / "web" / "static"
    return Path(__file__).parent / "static"


# ── REST API ──────────────────────────────────────────────────────────────────

@app.get("/api/version")
async def get_version() -> JSONResponse:
    from openclaw.platform_utils import get_platform_label
    return JSONResponse({"version": __version__, "platform": get_platform_label()})


@app.get("/api/sysinfo")
async def get_sysinfo() -> JSONResponse:
    """Returns OS, Python version, and disk usage. Safe only when server is bound
    to 127.0.0.1 (localhost). If remote access is ever enabled, gate this behind auth."""
    root = os.path.abspath(os.sep)
    usage = shutil.disk_usage(root)
    def _gb(value: int) -> float:
        return round(value / (1024 ** 3), 1)
    return JSONResponse({
        "os": f"{platform.system()} {platform.release()}",
        "python": sys.version.split()[0],
        "disk": {
            "used_gb": _gb(usage.used),
            "total_gb": _gb(usage.total),
        },
    })


@app.get("/api/state")
async def get_state() -> JSONResponse:
    if _store is None:
        return JSONResponse({"error": "monitor not running"}, status_code=503)
    return JSONResponse(_store.get())


@app.get("/api/alerts/dismiss/{alert_id}")
async def dismiss_alert(alert_id: str) -> JSONResponse:
    if _store is None:
        return JSONResponse({"error": "monitor not running"}, status_code=503)
    _store.dismiss_alert(alert_id)
    return JSONResponse({"ok": True})


@app.get("/api/session-log")
async def session_log() -> JSONResponse:
    """Returns recent AGENT-SESSION-LOG.md entries for the active project."""
    if _workspace_root is None:
        return JSONResponse({"error": "no workspace"}, status_code=503)
    from openclaw.monitor.agent_state_reader import read_active_project
    active = read_active_project(_workspace_root)
    if not active:
        return JSONResponse({"rows": [], "raw": None})
    log_path = _workspace_root / active["path"] / "AGENT-SESSION-LOG.md"
    if not log_path.exists():
        return JSONResponse({"rows": [], "raw": None})
    content = log_path.read_text(encoding="utf-8", errors="ignore")
    # Parse markdown table rows (skip header and separator)
    import re as _re
    rows = []
    in_table = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("| Date"):
            in_table = True
            continue
        if in_table and stripped.startswith("|---"):
            continue
        if in_table and stripped.startswith("|"):
            cols = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cols) >= 3:
                rows.append({"date": cols[0], "agent": cols[1], "items": cols[2]})
    return JSONResponse({"rows": rows[-20:], "raw": content})


@app.get("/api/projects")
async def list_projects() -> JSONResponse:
    """Lists available projects in the workspace's projects/ directory."""
    if _workspace_root is None:
        return JSONResponse({"error": "no workspace"}, status_code=503)
    projects_dir = _workspace_root / "projects"
    if not projects_dir.exists():
        return JSONResponse({"projects": []})
    projects = []
    for d in sorted(projects_dir.iterdir()):
        if d.is_dir():
            projects.append({"name": d.name, "path": f"projects/{d.name}"})
    # Read active project
    from openclaw.monitor.agent_state_reader import read_active_project
    active = read_active_project(_workspace_root)
    active_name = active["name"] if active else None
    return JSONResponse({"projects": projects, "active": active_name})


@app.post("/api/projects/switch")
async def switch_project(request: Request) -> JSONResponse:
    """Switches the active project by rewriting active-project.md."""
    if _workspace_root is None:
        return JSONResponse({"error": "no workspace"}, status_code=503)
    body = await request.json()
    project_name = body.get("name", "").strip()
    if not project_name:
        return JSONResponse({"ok": False, "error": "project name required"}, status_code=400)
    project_dir = _workspace_root / "projects" / project_name
    if not project_dir.exists():
        return JSONResponse({"ok": False, "error": f"Project '{project_name}' not found"}, status_code=404)
    # Write active-project.md
    active_file = _workspace_root / "active-project.md"
    active_file.write_text(
        f"Active Project: {project_name}\nProject Path: projects/{project_name}\n",
        encoding="utf-8",
    )
    return JSONResponse({"ok": True, "active": project_name})


@app.post("/api/projects/create")
async def create_project(request: Request) -> JSONResponse:
    """Creates a new project directory with template files."""
    if _workspace_root is None:
        return JSONResponse({"error": "no workspace"}, status_code=503)
    body = await request.json()
    project_name = body.get("name", "").strip()
    if not project_name:
        return JSONResponse({"ok": False, "error": "project name required"}, status_code=400)
    import re as _re
    if not _re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,49}$", project_name):
        return JSONResponse({"ok": False, "error": "Invalid name: use letters, numbers, hyphens, underscores"}, status_code=400)
    project_dir = _workspace_root / "projects" / project_name
    if project_dir.exists():
        return JSONResponse({"ok": False, "error": f"Project '{project_name}' already exists"}, status_code=409)
    try:
        from openclaw.installer.template_deployer import deploy_project_files
        project_dir.mkdir(parents=True)
        (project_dir / "tickets" / "open").mkdir(parents=True, exist_ok=True)
        (project_dir / "tickets" / "closed").mkdir(parents=True, exist_ok=True)
        deploy_project_files(project_dir, project_name)
        return JSONResponse({"ok": True, "name": project_name})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/morning-report")
async def morning_report() -> JSONResponse:
    if _workspace_root is None:
        return JSONResponse({"error": "no workspace"}, status_code=503)
    from openclaw.monitor.agent_state_reader import read_active_project
    active = read_active_project(_workspace_root)
    if not active:
        return JSONResponse({"content": None})
    report = _workspace_root / active["path"] / "overnight-report.md"
    if not report.exists():
        return JSONResponse({"content": None})
    return JSONResponse({"content": report.read_text(encoding="utf-8")})


# ── Installer API ─────────────────────────────────────────────────────────────

@app.get("/api/hardware")
async def hardware_info() -> JSONResponse:
    return JSONResponse(get_hardware_info())


@app.get("/api/agent-check")
async def agent_check(target: str = "") -> JSONResponse:
    if not target:
        return JSONResponse({"active_count": 0, "processes": []})
    procs = find_active_claude_processes(Path(target))
    return JSONResponse({"active_count": len(procs), "processes": procs})


@app.get("/api/workspaces")
async def list_workspaces() -> JSONResponse:
    found = find_existing_workspaces()
    return JSONResponse({
        "found": [str(p) for p in found],
        "default_new_path": str(get_default_workspace_dir()),
    })


@app.get("/api/open-folder")
async def open_folder(path: str) -> JSONResponse:
    """Opens a workspace folder in the OS file explorer. Only opens paths inside home dir."""
    import subprocess
    target = Path(path).resolve()
    home = Path.home().resolve()
    if not str(target).startswith(str(home)):
        return JSONResponse({"ok": False, "error": "Path outside home directory"}, status_code=400)
    if not target.exists():
        return JSONResponse({"ok": False, "error": "Path does not exist"}, status_code=404)
    try:
        if is_windows():
            subprocess.Popen(["explorer", str(target)])
        else:
            subprocess.Popen(["open", str(target)])
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
    return JSONResponse({"ok": True})


@app.get("/api/browse-folder")
async def browse_folder() -> JSONResponse:
    """Opens the OS native folder-picker dialog; returns the selected path or null."""
    from openclaw.platform_utils import pick_folder_dialog
    selected = pick_folder_dialog("Select OpenClaw Workspace Folder")
    return JSONResponse({"path": selected})


@app.get("/api/prerequisites")
async def check_prerequisites(target: str = "") -> JSONResponse:
    from openclaw.installer.prerequisite_checker import run_all_checks, all_clear
    target_path = Path(target) if target else get_default_workspace_dir()
    results = run_all_checks(target_path)
    return JSONResponse({
        "checks": [
            {
                "name": r.name,
                "passed": r.passed,
                "blocking": r.blocking,
                "detail": r.detail,
                "fix": r.fix,
            }
            for r in results
        ],
        "can_proceed": all_clear(results),
        "default_target": str(target_path),
    })


@app.get("/api/themes")
async def list_themes() -> JSONResponse:
    import json as _json
    corpus = get_corpus_dir()
    themes = []
    for f in sorted((corpus / "characters").glob("*.json")):
        try:
            data = _json.loads(f.read_text(encoding="utf-8"))
            # Build simplified {role: character_name} map for roster preview
            roles_map = {
                role: info.get("character", "")
                for role, info in data.get("roles", {}).items()
            }
            themes.append({
                "id": f.stem,
                "label": data.get("label", f.stem),
                "description": data.get("description", ""),
                "roles": roles_map,
            })
        except Exception:
            pass
    return JSONResponse(themes)


@app.get("/api/check-workspace-path")
async def check_workspace_path(path: str) -> JSONResponse:
    """
    Checks whether a given path is an existing OpenClaw workspace.
    Returns: {exists: bool, is_workspace: bool, is_single_agent: bool, agent_count: int}
    """
    target = Path(path)
    if not target.exists():
        return JSONResponse({"exists": False, "is_workspace": False})

    has_agents = (target / "AGENTS.md").exists()
    has_project = (target / "active-project.md").exists()
    is_workspace = has_agents or has_project

    agent_count = 0
    is_single_agent = False
    if has_agents:
        try:
            content = (target / "AGENTS.md").read_text(encoding="utf-8")
            # Count "### " role headers as a proxy for agent count
            agent_count = content.count("\n### ")
            is_single_agent = agent_count <= 1
        except Exception:
            pass

    return JSONResponse({
        "exists": True,
        "is_workspace": is_workspace,
        "is_single_agent": is_single_agent,
        "agent_count": agent_count,
    })


@app.get("/api/workspace-agents")
async def get_workspace_agents(path: str) -> JSONResponse:
    """
    Parses AGENTS.md in the given workspace path and returns a list of
    configured agents: [{role, role_label, character, model}]
    """
    import re as _re
    target = Path(path)
    agents_file = target / "AGENTS.md"
    if not agents_file.exists():
        return JSONResponse({"agents": []})

    try:
        content = agents_file.read_text(encoding="utf-8")
    except Exception:
        return JSONResponse({"agents": []})

    # Split into per-agent sections at "### " headers
    sections = _re.split(r'^### ', content, flags=_re.MULTILINE)
    agents = []
    for section in sections[1:]:
        lines = section.strip().split('\n')
        role_label = lines[0].strip()
        char_match = _re.search(r'\*\*Character:\*\*\s*(.+)', section)
        model_match = _re.search(r'\*\*Model:\*\*\s*(.+)', section)
        character = char_match.group(1).strip() if char_match else '—'
        model = model_match.group(1).strip() if model_match else '—'
        # Derive role key from label (reverse of ROLE_LABELS)
        role_label_to_key = {v: k for k, v in ROLE_LABELS.items()}
        role = role_label_to_key.get(role_label, role_label.lower().split()[0])
        agents.append({"role": role, "role_label": role_label, "character": character, "model": model})

    return JSONResponse({"agents": agents})


@app.post("/api/workspace-agents/delete")
async def delete_workspace_agent(body: dict) -> JSONResponse:
    """
    Removes a single agent from the workspace AGENTS.md and its
    ~/.openclaw/agents/{role}/ registration directory.
    """
    import re as _re, shutil as _shutil
    path = body.get("path", "")
    role = body.get("role", "")
    if not path or not role:
        return JSONResponse({"ok": False, "error": "path and role required"}, status_code=400)

    agents_file = Path(path) / "AGENTS.md"
    if not agents_file.exists():
        return JSONResponse({"ok": False, "error": "AGENTS.md not found"}, status_code=404)

    try:
        content = agents_file.read_text(encoding="utf-8")
        # Remove the section for this agent — from its ### header to the next ###
        label = ROLE_LABELS.get(role, role.upper())
        # Remove block: ### {label}\n ... up to next ### or end of file
        pattern = _re.compile(
            r'^### ' + _re.escape(label) + r'\n.*?(?=^### |\Z)',
            _re.MULTILINE | _re.DOTALL,
        )
        new_content = pattern.sub('', content)
        agents_file.write_text(new_content, encoding="utf-8")
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    # Also remove the OpenClaw agent registration directory
    openclaw_agent_dir = Path.home() / ".openclaw" / "agents" / role
    if openclaw_agent_dir.exists():
        try:
            _shutil.rmtree(openclaw_agent_dir)
        except Exception:
            pass  # Non-critical

    return JSONResponse({"ok": True})


@app.get("/api/openclaw-workspace")
async def get_openclaw_workspace() -> JSONResponse:
    """
    Returns OpenClaw's configured workspace path (from ~/.openclaw/config.json)
    and whether it matches Mission Control's last installed workspace.
    """
    import json as _json
    openclaw_config = Path.home() / ".openclaw" / "config.json"
    oc_workspace = None
    if openclaw_config.exists():
        try:
            data = _json.loads(openclaw_config.read_text(encoding="utf-8"))
            oc_workspace = data.get("workspace") or data.get("workspaceDirectory") or data.get("projectDirectory")
        except Exception:
            pass

    mc_config = Path.home() / ".openclaw-mission-control.json"
    mc_workspace = None
    if mc_config.exists():
        try:
            data = _json.loads(mc_config.read_text(encoding="utf-8"))
            mc_workspace = data.get("last_workspace")
        except Exception:
            pass

    match = (oc_workspace and mc_workspace and
             str(Path(oc_workspace).resolve()) == str(Path(mc_workspace).resolve()))

    return JSONResponse({
        "openclaw_workspace": oc_workspace,
        "mc_workspace": mc_workspace,
        "match": match,
    })


@app.post("/api/reregister-agents")
async def reregister_agents(body: dict) -> JSONResponse:
    """
    Re-runs OpenClaw agent registration for all agents in the given workspace.
    Reads AGENTS.md to get the current agent list, then rewrites IDENTITY.md files.
    """
    import re as _re
    path = body.get("path", "")
    if not path:
        return JSONResponse({"ok": False, "error": "path required"}, status_code=400)

    agents_file = Path(path) / "AGENTS.md"
    if not agents_file.exists():
        return JSONResponse({"ok": False, "error": "AGENTS.md not found"}, status_code=404)

    try:
        from openclaw.installer.agent_registrar import register_openclaw_agents
        # Parse agents from AGENTS.md
        content = agents_file.read_text(encoding="utf-8")
        sections = _re.split(r'^### ', content, flags=_re.MULTILINE)
        agents = []
        role_label_to_key = {v: k for k, v in ROLE_LABELS.items()}
        for section in sections[1:]:
            lines = section.strip().split('\n')
            role_label = lines[0].strip()
            char_match = _re.search(r'\*\*Character:\*\*\s*(.+)', section)
            model_match = _re.search(r'\*\*Model:\*\*\s*(.+)', section)
            phil_match = _re.search(r'\*\*Philosophy:\*\*\s*(.+)', section)
            role = role_label_to_key.get(role_label, role_label.lower().split()[0])
            agents.append({
                "role": role,
                "role_label": role_label,
                "character": char_match.group(1).strip() if char_match else role_label,
                "model": model_match.group(1).strip() if model_match else "claude-sonnet-4-6",
                "philosophy": phil_match.group(1).strip() if phil_match else "",
                "decision_style": "",
                "workspace_path": path,
            })

        created = register_openclaw_agents(agents)

        # Also write the workspace path to OpenClaw config
        from openclaw.platform_utils import write_openclaw_workspace_path
        write_openclaw_workspace_path(Path(path))

        return JSONResponse({"ok": True, "registered": len(agents), "files": created})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.post("/api/install")
async def run_install(body: dict) -> JSONResponse:
    from openclaw.installer.workspace_builder import build_layout, create_workspace, write_agent_launchers
    from openclaw.installer.template_deployer import deploy_workspace_files, deploy_project_files
    from openclaw.installer.config_writer import write_claude_settings
    from openclaw.installer.agent_registrar import register_openclaw_agents

    install_mode = body.get("install_mode", "new")

    # Dashboard-only mode: just register the workspace path, no file changes
    if install_mode == "dashboard-only":
        target = Path(body.get("target", str(Path.home() / "openclaw-workspace")))
        try:
            from openclaw.platform_utils import write_openclaw_workspace_path, save_last_workspace
            write_openclaw_workspace_path(target)
            save_last_workspace(str(target))
            global _workspace
            _workspace = target
            return JSONResponse({"ok": True, "workspace": str(target), "created": []})
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    target = Path(body.get("target", str(Path.home() / "openclaw-workspace")))
    theme = body.get("theme", "historical")
    custom_characters = body.get("custom_characters") or {}  # {role: character_name} overrides
    team_size = int(body.get("team_size", 4))
    project_name = body.get("project_name", "example-app")
    operator_name = body.get("operator_name", "Operator")
    # install_mode already parsed above: "new" | "upgrade" | "replace"
    update_mode = install_mode != "new"  # preserve project files if upgrading

    model_map = {
        "strategic":      body.get("model_strategic", "claude-sonnet-4-6"),
        "implementation": body.get("model_implementation", "claude-sonnet-4-6"),
        "support":        body.get("model_support", "claude-sonnet-4-6"),
    }
    default_model = model_map["strategic"]

    # Path safety: reject targets outside the user's home directory
    home = Path.home().resolve()
    try:
        resolved = target.resolve()
    except (OSError, ValueError):
        return JSONResponse({"ok": False, "error": f"Invalid path: {target}"}, status_code=400)
    if not str(resolved).startswith(str(home)):
        return JSONResponse(
            {"ok": False, "error": f"Target must be inside your home directory ({home})"},
            status_code=400,
        )

    try:
        layout = build_layout(target, project_name)
        created = create_workspace(layout)

        workspace_files, agents, team_name = deploy_workspace_files(
            target, theme, team_size, operator_name, project_name,
            model_map=model_map, install_mode=install_mode,
            custom_characters=custom_characters or None,
        )
        created.extend(workspace_files)

        launcher_files = write_agent_launchers(target, agents)
        created.extend(launcher_files)

        # Inject workspace path into agents so they register with the correct workspace
        for agent in agents:
            agent["workspace_path"] = str(target)

        agent_reg_files = register_openclaw_agents(agents)
        created.extend(agent_reg_files)

        project_path = target / "projects" / project_name
        project_files = deploy_project_files(project_path, project_name, update_mode=update_mode)
        created.extend(project_files)

        settings_path = write_claude_settings(target, default_model=default_model)
        created.append(settings_path)

        # Store workspace path for monitor startup
        _installer_context["last_installed_path"] = str(target)
        save_last_workspace(target)
        write_openclaw_workspace_path(target)  # tell OpenClaw where this workspace lives

        return JSONResponse({
            "ok": True,
            "created": created,
            "workspace": str(target),
            "install_mode": install_mode,
        })
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


# ── Model provider API ────────────────────────────────────────────────────────

_CURATED_MODELS = [
    # Anthropic
    {"id": "claude-opus-4-6",           "provider": "Anthropic", "label": "Claude Opus 4.6"},
    {"id": "claude-sonnet-4-6",         "provider": "Anthropic", "label": "Claude Sonnet 4.6"},
    {"id": "claude-haiku-4-5-20251001", "provider": "Anthropic", "label": "Claude Haiku 4.5"},
    # OpenAI
    {"id": "gpt-4o",       "provider": "OpenAI", "label": "GPT-4o"},
    {"id": "gpt-4o-mini",  "provider": "OpenAI", "label": "GPT-4o Mini"},
    {"id": "o3-mini",      "provider": "OpenAI", "label": "o3-mini"},
    {"id": "o1",           "provider": "OpenAI", "label": "o1"},
    # Google
    {"id": "gemini-2.0-flash",  "provider": "Google", "label": "Gemini 2.0 Flash"},
    {"id": "gemini-1.5-pro",    "provider": "Google", "label": "Gemini 1.5 Pro"},
    {"id": "gemini-1.5-flash",  "provider": "Google", "label": "Gemini 1.5 Flash"},
    # OpenRouter
    {"id": "openrouter/auto", "provider": "OpenRouter", "label": "OpenRouter Auto"},
    # Ollama local
    {"id": "qwen2.5:7b-instruct", "provider": "Ollama", "label": "Qwen 2.5 7B (local)"},
]

_oauth_state: dict[str, str] = {}  # provider → "pending" | "complete"


@app.get("/api/configured-models")
async def get_configured_models() -> JSONResponse:
    return JSONResponse({"models": detect_openclaw_models()})


@app.get("/api/models")
async def get_models() -> JSONResponse:
    return JSONResponse({"models": _CURATED_MODELS})


@app.post("/api/configure-provider")
async def configure_provider(body: dict) -> JSONResponse:
    import httpx
    provider_type = body.get("type", "")
    key = body.get("key", "").strip()
    if not key:
        return JSONResponse({"ok": False, "error": "API key is required"}, status_code=400)

    if provider_type == "openai-key":
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {key}"},
                )
            if r.status_code != 200:
                return JSONResponse({"ok": False, "error": f"OpenAI rejected key (HTTP {r.status_code})"})
            data = r.json()
            models = [
                {"id": m["id"], "provider": "OpenAI", "label": m["id"]}
                for m in data.get("data", [])
                if any(x in m["id"] for x in ("gpt", "o1", "o3"))
            ][:20]
        except Exception as e:
            return JSONResponse({"ok": False, "error": f"Could not reach OpenAI: {e}"})

    elif provider_type == "openrouter-key":
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {key}"},
                )
            if r.status_code != 200:
                return JSONResponse({"ok": False, "error": f"OpenRouter rejected key (HTTP {r.status_code})"})
            data = r.json()
            models = [
                {"id": m["id"], "provider": "OpenRouter", "label": m.get("name", m["id"])}
                for m in data.get("data", [])
            ][:20]
        except Exception as e:
            return JSONResponse({"ok": False, "error": f"Could not reach OpenRouter: {e}"})

    else:
        return JSONResponse({"ok": False, "error": f"Unknown provider type: {provider_type}"}, status_code=400)

    config_path = find_openclaw_config_path()
    if config_path:
        try:
            for m in models[:5]:
                update_openclaw_config(config_path, m)
        except Exception:
            pass

    return JSONResponse({"ok": True, "models": models})


@app.get("/api/ollama-status")
async def ollama_status() -> JSONResponse:
    import shutil as _shutil
    import subprocess as _sp
    installed = bool(_shutil.which("ollama"))
    running = False
    local_models: list[str] = []
    if installed:
        try:
            r = _sp.run(["ollama", "list"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                running = True
                for line in r.stdout.strip().splitlines()[1:]:
                    parts = line.split()
                    if parts:
                        local_models.append(parts[0])
        except Exception:
            pass
    return JSONResponse({"installed": installed, "running": running, "models": local_models})


@app.post("/api/ollama-install")
async def ollama_install_stream(body: dict) -> Any:
    import json as _json
    import shutil as _shutil
    from fastapi.responses import StreamingResponse as _SR

    async def event_stream():
        if _shutil.which("ollama"):
            yield f"data: {_json.dumps({'status': 'already_installed', 'message': 'Ollama already installed.'})}\n\n"
        else:
            if is_windows():
                import urllib.request as _ur
                import os as _os
                import tempfile as _tf
                yield f"data: {_json.dumps({'status': 'downloading', 'message': 'Downloading Ollama for Windows...'})}\n\n"
                try:
                    tmp = _os.path.join(_tf.gettempdir(), "OllamaSetup.exe")
                    _ur.urlretrieve("https://ollama.com/download/OllamaSetup.exe", tmp)
                    yield f"data: {_json.dumps({'status': 'installing', 'message': 'Running installer...'})}\n\n"
                    proc = await asyncio.create_subprocess_exec(
                        tmp, "/S",
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                    )
                    await proc.wait()
                except Exception as e:
                    yield f"data: {_json.dumps({'status': 'error', 'message': str(e)})}\n\n"
                    return
            else:
                yield f"data: {_json.dumps({'status': 'installing', 'message': 'Installing Ollama...'})}\n\n"
                proc = await asyncio.create_subprocess_shell(
                    "curl -fsSL https://ollama.com/install.sh | sh",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                )
                async for line in proc.stdout:
                    msg = line.decode(errors="replace").strip()
                    if msg:
                        yield f"data: {_json.dumps({'status': 'installing', 'message': msg})}\n\n"
                await proc.wait()

        yield f"data: {_json.dumps({'status': 'pulling', 'message': 'Downloading qwen2.5:7b-instruct (~4.7 GB)...'})}\n\n"
        proc = await asyncio.create_subprocess_exec(
            "ollama", "pull", "qwen2.5:7b-instruct",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        async for line in proc.stdout:
            msg = line.decode(errors="replace").strip()
            if msg:
                yield f"data: {_json.dumps({'status': 'pulling', 'message': msg})}\n\n"
        await proc.wait()

        config_path = find_openclaw_config_path()
        if config_path:
            try:
                update_openclaw_config(config_path, {
                    "id": "qwen2.5:7b-instruct",
                    "provider": "Ollama",
                    "label": "Qwen 2.5 7B (local)",
                })
            except Exception:
                pass

        yield f"data: {_json.dumps({'status': 'done', 'model': 'qwen2.5:7b-instruct'})}\n\n"

    return _SR(event_stream(), media_type="text/event-stream",
               headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/oauth/start/{provider}")
async def oauth_start(provider: str) -> JSONResponse:
    """Launches `openclaw configure` in a terminal for OAuth-based providers."""
    import subprocess as _sp
    binary = find_openclaw_binary()
    if not binary:
        return JSONResponse({"error": "OpenClaw binary not found on PATH"}, status_code=400)
    _oauth_state[provider] = "pending"
    if is_windows():
        _sp.Popen(["cmd", "/c", "start", "cmd", "/k", binary, "configure"], shell=False)
    else:
        # osascript tells Terminal to open a new window and run the command
        script = f'tell application "Terminal" to do script "{binary} configure"'
        try:
            _sp.Popen(["osascript", "-e", script])
        except Exception:
            _sp.Popen([binary, "configure"])
    return JSONResponse({
        "status": "launched",
        "message": "OpenClaw configure launched. Complete the auth in the terminal, then click 'Check Again'.",
    })


@app.get("/oauth/status/{provider}")
async def oauth_status_check(provider: str) -> JSONResponse:
    models = detect_openclaw_models()
    if models:
        _oauth_state[provider] = "complete"
        return JSONResponse({"status": "complete", "models": models})
    return JSONResponse({"status": _oauth_state.get(provider, "unknown"), "models": []})


@app.get("/api/agent-registry")
async def get_agent_registry() -> JSONResponse:
    """
    Returns agent reconciliation report: compares Mission Control's managed agents
    (from workspace AGENTS.md) against OpenClaw's registered agents.
    Classifies each agent as: managed, unmanaged, runtime, orphaned, test, or missing.
    """
    if not _workspace_root:
        return JSONResponse(
            {"error": "Workspace not loaded"},
            status_code=400,
        )

    from openclaw.monitor.agent_reconciler import reconcile

    report = reconcile(_workspace_root)
    return JSONResponse(report)


@app.post("/api/agents/cleanup")
async def cleanup_agent(body: dict) -> JSONResponse:
    """
    Performs cleanup operations on an agent:
    - "unregister": removes IDENTITY.md (keeps dir/sessions)
    - "archive": renames dir to {id}-archived-{timestamp}
    - "purge": removes entire directory (requires confirm: true)

    Body: {"agentId": "...", "action": "archive|unregister|purge", "confirm": true}
    """
    agent_id = body.get("agentId", "")
    action = body.get("action", "")
    confirm = body.get("confirm", False)

    if not agent_id or not action:
        return JSONResponse(
            {"error": "agentId and action required"},
            status_code=400,
        )

    if action not in ("archive", "unregister", "purge"):
        return JSONResponse(
            {"error": f"action must be one of: archive, unregister, purge"},
            status_code=400,
        )

    if action == "purge" and not confirm:
        return JSONResponse(
            {"error": "purge requires confirm: true"},
            status_code=400,
        )

    from openclaw.installer.agent_registrar import (
        unregister_agent, archive_agent, purge_agent,
    )

    try:
        if action == "unregister":
            ok = unregister_agent(agent_id)
            if not ok:
                return JSONResponse(
                    {"error": f"Agent {agent_id} not found"},
                    status_code=404,
                )
            return JSONResponse({"ok": True, "action": "unregister", "agentId": agent_id})

        elif action == "archive":
            new_path = archive_agent(agent_id)
            if not new_path:
                return JSONResponse(
                    {"error": f"Agent {agent_id} not found or archive failed"},
                    status_code=404,
                )
            return JSONResponse({
                "ok": True,
                "action": "archive",
                "agentId": agent_id,
                "newPath": new_path,
            })

        elif action == "purge":
            ok = purge_agent(agent_id)
            if not ok:
                return JSONResponse(
                    {"error": f"Agent {agent_id} not found or purge failed"},
                    status_code=404,
                )
            return JSONResponse({"ok": True, "action": "purge", "agentId": agent_id})

    except Exception as e:
        return JSONResponse(
            {"error": f"Operation failed: {str(e)}"},
            status_code=500,
        )


@app.put("/api/agents/set-main/{role}")
async def set_agent_as_main(role: str) -> JSONResponse:
    """
    Promotes an agent to be the primary chat entrypoint by making it the 'main' agent.
    Updates openclaw.json agents.list entry for 'main' to use the promoted agent's:
    - workspace
    - identity (IDENTITY.md)
    - default: true flag

    Path param: role (e.g. "pm", "architect", "builder")
    """
    import shutil

    try:
        config_path = Path.home() / ".openclaw" / "openclaw.json"
        if not config_path.exists():
            return JSONResponse(
                {"error": "OpenClaw config not found"},
                status_code=404,
            )

        # Read config
        data = json.loads(config_path.read_text(encoding="utf-8"))
        if "agents" not in data or "list" not in data["agents"]:
            return JSONResponse(
                {"error": "Invalid OpenClaw config structure"},
                status_code=400,
            )

        agents_list = data["agents"]["list"]

        # Find the role's workspace
        role_entry = next((a for a in agents_list if a.get("id") == role), None)
        if not role_entry:
            return JSONResponse(
                {"error": f"Agent {role} not found in config"},
                status_code=404,
            )

        role_workspace = role_entry.get("workspace")

        # Update the 'main' entry: set workspace and default flag
        main_entry = next((a for a in agents_list if a.get("id") == "main"), None)
        if not main_entry:
            # Create main entry if it doesn't exist
            main_entry = {"id": "main"}
            agents_list.append(main_entry)

        main_entry["workspace"] = role_workspace
        main_entry["default"] = True

        # Remove 'default' flag from all other agents
        for agent in agents_list:
            if agent.get("id") != "main":
                agent.pop("default", None)

        # Snapshot and copy IDENTITY.md
        role_identity = Path.home() / ".openclaw" / "agents" / role / "IDENTITY.md"
        main_identity = Path.home() / ".openclaw" / "agents" / "main" / "IDENTITY.md"
        identity_copied = False

        if role_identity.exists():
            # Archive old main identity if it exists
            if main_identity.exists():
                bak_path = main_identity.parent / f"{main_identity.name}.bak"
                shutil.copy2(main_identity, bak_path)

            # Copy role's identity to main
            main_identity.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(role_identity, main_identity)
            identity_copied = True

        # Write back config
        config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        # Try to get gateway status
        import subprocess
        gateway_status = "unknown"
        try:
            result = subprocess.run(
                ["openclaw", "gateway", "status"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            gateway_status = result.stdout.strip() if result.returncode == 0 else "gateway check failed"
        except Exception:
            gateway_status = "gateway status check error"

        return JSONResponse({
            "ok": True,
            "promoted": role,
            "workspace": role_workspace,
            "identityCopied": identity_copied,
            "gatewayStatus": gateway_status,
            "message": f"Promoted {role} to main chat agent. Gateway may need restart to apply changes.",
        })

    except Exception as e:
        return JSONResponse(
            {"error": f"Failed to promote agent: {str(e)}"},
            status_code=500,
        )


@app.post("/api/agents/verify/{role}")
async def verify_agent(role: str) -> JSONResponse:
    """
    Verifies an agent is responsive by sending a test message.
    Uses the 'main' agent if the role is currently main, else uses the role directly.

    Path param: role (e.g. "pm", "main")
    """
    import subprocess

    try:
        # Always test via 'main' since that's the primary entrypoint
        test_agent = "main"
        test_message = "Reply with your name and role only."

        result = subprocess.run(
            ["openclaw", "agent", "--agent", test_agent, "--message", test_message],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            return JSONResponse({
                "ok": True,
                "agent": test_agent,
                "response": result.stdout.strip(),
                "command": f"openclaw agent --agent {test_agent} --message \"{test_message}\"",
            })
        else:
            return JSONResponse({
                "ok": False,
                "error": result.stderr.strip() or "Agent command failed",
                "command": f"openclaw agent --agent {test_agent} --message \"{test_message}\"",
            })

    except subprocess.TimeoutExpired:
        return JSONResponse({
            "ok": False,
            "error": "Agent verification timed out after 10 seconds",
        }, status_code=408)
    except Exception as e:
        return JSONResponse({
            "ok": False,
            "error": f"Verification failed: {str(e)}",
        }, status_code=500)


@app.post("/api/agents/add")
async def add_agent(request: Request) -> JSONResponse:
    """
    Adds a new custom agent role.
    Body: {role: str, name: str, label: str}
    Creates IDENTITY.md and registers in openclaw.json + AGENTS.md.
    """
    import re
    body = await request.json()
    role = body.get("role", "").strip().lower()
    name = body.get("name", "").strip()
    label = body.get("label", "").strip() or name

    # Validate role ID
    if not role or not re.match(r"^[a-z][a-z0-9-]{0,29}$", role):
        return JSONResponse(
            {"ok": False, "error": "Role ID must be lowercase letters/numbers/hyphens, 1-30 chars."},
            status_code=400,
        )
    if not name:
        return JSONResponse(
            {"ok": False, "error": "Display name is required."},
            status_code=400,
        )

    from openclaw.installer.agent_registrar import register_openclaw_agents

    # Check if agent already exists
    agent_dir = Path.home() / ".openclaw" / "agents" / role
    if agent_dir.exists() and (agent_dir / "IDENTITY.md").exists():
        return JSONResponse(
            {"ok": False, "error": f"Agent '{role}' already exists."},
            status_code=409,
        )

    # Build minimal agent dict compatible with register_openclaw_agents
    workspace_path = str(
        Path(_workspace or Path.home() / "Documents" / "openclaw-workspace")
    )
    agent = {
        "role": role,
        "agentId": role,
        "displayName": name,
        "character": name,
        "role_label": label,
        "philosophy": "",
        "decision_style": "",
        "responsibilities": [],
        "outputs": [],
        "model": "claude-sonnet-4-6",
        "receives_from": "pm",
        "hands_to": "pm",
        "start_conditions": [],
        "methodology": "",
        "workspace_path": workspace_path,
    }

    try:
        created = register_openclaw_agents([agent])

        # Also append to AGENTS.md in the workspace
        ws = Path(workspace_path)
        agents_md = ws / "AGENTS.md"
        if agents_md.exists():
            entry = f"\n### {label}\n**Character:** {name}\n**Role:** {role}\n**Model:** claude-sonnet-4-6\n\n"
            with open(agents_md, "a", encoding="utf-8") as f:
                f.write(entry)

        return JSONResponse({"ok": True, "created": created})
    except Exception as e:
        return JSONResponse(
            {"ok": False, "error": f"Failed to add agent: {str(e)}"},
            status_code=500,
        )


@app.get("/api/gateway/status")
async def get_gateway_status() -> JSONResponse:
    """
    Checks if the OpenClaw gateway is running.
    Returns: {ok, state: "running|stopped|error|unreachable", message, stdout, stderr}
    """
    import subprocess

    try:
        result = subprocess.run(
            ["openclaw", "gateway", "status"],
            capture_output=True,
            text=True,
            timeout=3,
        )

        # Check both stdout and stderr for status keywords
        output_text = (result.stdout + result.stderr).lower()

        # Determine state based on message content, not return code
        # (status command returns 0 regardless of whether gateway is running or stopped)
        state = "unknown"

        # Check for running indicators
        if "running" in output_text or "active" in output_text or "launchagent (loaded)" in output_text:
            state = "running"
        # Check for stopped indicators
        elif ("not running" in output_text or "stopped" in output_text or "inactive" in output_text or
              "not loaded" in output_text or "rpc probe: failed" in output_text or
              "service not installed" in output_text):
            state = "stopped"
        elif result.returncode != 0:
            state = "error"
        else:
            state = "unknown"

        return JSONResponse({
            "ok": state == "running",
            "state": state,
            "message": result.stdout.strip() or result.stderr.strip() or f"Gateway is {state}",
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        })
    except subprocess.TimeoutExpired:
        return JSONResponse({
            "ok": False,
            "state": "unreachable",
            "message": "Gateway status check timed out",
            "stdout": "",
            "stderr": "timeout",
        })
    except Exception as e:
        return JSONResponse({
            "ok": False,
            "state": "unreachable",
            "message": f"Error checking gateway: {str(e)}",
            "stdout": "",
            "stderr": str(e),
        })


@app.post("/api/gateway/start")
async def start_gateway() -> JSONResponse:
    """
    Starts the OpenClaw gateway.
    Uses 'openclaw gateway install' to ensure service is installed, then starts it.
    Returns: {ok, state: "running|error|unknown", message, stdout, stderr}
    """
    import subprocess

    try:
        # First try to install the gateway service (idempotent)
        subprocess.run(
            ["openclaw", "gateway", "install"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Now start it via launchctl
        result = subprocess.run(
            ["launchctl", "bootstrap", f"gui/{os.getuid()}",
             f"{os.path.expanduser('~/Library/LaunchAgents/ai.openclaw.gateway.plist')}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Give it a moment to start, then check status
        await asyncio.sleep(1.5)
        status_check = subprocess.run(
            ["openclaw", "gateway", "status"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        state = "running" if "running" in status_check.stdout.lower() else "error"

        return JSONResponse({
            "ok": state == "running",
            "state": state,
            "message": "Gateway started successfully" if state == "running" else "Gateway start initiated; checking status...",
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        })
    except subprocess.TimeoutExpired:
        return JSONResponse({
            "ok": False,
            "state": "error",
            "message": "Gateway start command timed out",
            "stdout": "",
            "stderr": "timeout",
        })
    except Exception as e:
        return JSONResponse({
            "ok": False,
            "state": "error",
            "message": f"Failed to start gateway: {str(e)}",
            "stdout": "",
            "stderr": str(e),
        }, status_code=500)


@app.post("/api/gateway/stop")
async def stop_gateway() -> JSONResponse:
    """
    Stops the OpenClaw gateway.
    Uses launchctl bootout to stop the service.
    Returns: {ok, state: "stopped|error|unknown", message, stdout, stderr}
    """
    import subprocess

    try:
        # Use launchctl bootout to stop the service
        result = subprocess.run(
            ["launchctl", "bootout", f"gui/{os.getuid()}",
             f"{os.path.expanduser('~/Library/LaunchAgents/ai.openclaw.gateway.plist')}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Check if it stopped
        await asyncio.sleep(1)
        status_check = subprocess.run(
            ["openclaw", "gateway", "status"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        state = "stopped" if "not loaded" in status_check.stdout.lower() or "rpc probe: failed" in status_check.stderr.lower() else "error"

        return JSONResponse({
            "ok": state == "stopped",
            "state": state,
            "message": "Gateway stopped successfully" if state == "stopped" else "Error stopping gateway",
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        })
    except subprocess.TimeoutExpired:
        return JSONResponse({
            "ok": False,
            "state": "error",
            "message": "Gateway stop command timed out",
            "stdout": "",
            "stderr": "timeout",
        })
    except Exception as e:
        return JSONResponse({
            "ok": False,
            "state": "error",
            "message": f"Failed to stop gateway: {str(e)}",
            "stdout": "",
            "stderr": str(e),
        }, status_code=500)


@app.post("/api/gateway/restart")
async def restart_gateway() -> JSONResponse:
    """
    Restarts the OpenClaw gateway.
    Stops then starts the gateway service.
    Returns: {ok, state: "running|error|unknown", message, stdout, stderr}
    """
    import subprocess

    try:
        # Stop the gateway first
        subprocess.run(
            ["launchctl", "bootout", f"gui/{os.getuid()}",
             f"{os.path.expanduser('~/Library/LaunchAgents/ai.openclaw.gateway.plist')}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        await asyncio.sleep(1)

        # Install and start the gateway
        subprocess.run(
            ["openclaw", "gateway", "install"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        result = subprocess.run(
            ["launchctl", "bootstrap", f"gui/{os.getuid()}",
             f"{os.path.expanduser('~/Library/LaunchAgents/ai.openclaw.gateway.plist')}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Give it time to start
        await asyncio.sleep(1.5)

        # Verify it restarted successfully
        status_check = subprocess.run(
            ["openclaw", "gateway", "status"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        state = "running" if "running" in status_check.stdout.lower() else "error"

        return JSONResponse({
            "ok": state == "running",
            "state": state,
            "message": "Gateway restarted successfully" if state == "running" else "Gateway restart completed; checking status...",
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        })
    except subprocess.TimeoutExpired:
        return JSONResponse({
            "ok": False,
            "state": "error",
            "message": "Gateway restart command timed out",
            "stdout": "",
            "stderr": "timeout",
        })
    except Exception as e:
        return JSONResponse({
            "ok": False,
            "state": "error",
            "message": f"Failed to restart gateway: {str(e)}",
            "stdout": "",
            "stderr": str(e),
        }, status_code=500)


@app.post("/api/doctor")
async def run_doctor() -> JSONResponse:
    """
    Runs `openclaw doctor --repair --non-interactive` to auto-fix gateway and
    channel issues.  Returns stdout/stderr for display in the dashboard.
    """
    import subprocess

    try:
        result = subprocess.run(
            ["openclaw", "doctor", "--repair", "--non-interactive"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Strip ANSI escape codes from output for clean display
        import re as _re
        clean = _re.sub(r"\x1b\[[0-9;]*m", "", result.stdout + result.stderr)
        return JSONResponse({
            "ok": result.returncode == 0,
            "output": clean.strip(),
            "returncode": result.returncode,
        })
    except subprocess.TimeoutExpired:
        return JSONResponse({
            "ok": False,
            "error": "Doctor timed out after 30 seconds",
        }, status_code=408)
    except FileNotFoundError:
        return JSONResponse({
            "ok": False,
            "error": "openclaw command not found — is OpenClaw installed?",
        }, status_code=404)
    except Exception as e:
        return JSONResponse({
            "ok": False,
            "error": f"Doctor failed: {str(e)}",
        }, status_code=500)


@app.get("/api/skills")
async def get_skills() -> JSONResponse:
    """
    Returns installed OpenClaw skills by running `openclaw skills list`.
    Parses the table output to extract skill name, status, and description.
    """
    import subprocess
    import re as _re

    try:
        result = subprocess.run(
            ["openclaw", "skills", "list"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        output = result.stdout + result.stderr
        # Strip ANSI escape codes
        clean = _re.sub(r"\x1b\[[0-9;]*m", "", output)

        skills = []
        ready_count = 0
        total_count = 0

        # Parse summary line: "Skills (7/52 ready)"
        summary_match = _re.search(r"Skills\s*\((\d+)/(\d+)\s+ready\)", clean)
        if summary_match:
            ready_count = int(summary_match.group(1))
            total_count = int(summary_match.group(2))

        # Parse table rows: │ status │ name │ description │ source │
        for line in clean.splitlines():
            # Match rows with ✓ or ✗
            m = _re.match(
                r"│\s*(✓ ready|✗ missing)\s*│\s*\S*\s*(\S[\w-]+(?:\s+[\w-]+)*)\s*│\s*(.+?)\s*│\s*(\S+)\s*│",
                line,
            )
            if m:
                status_raw = m.group(1).strip()
                name = m.group(2).strip()
                desc = m.group(3).strip()
                source = m.group(4).strip()
                skills.append({
                    "name": name,
                    "ready": status_raw.startswith("✓"),
                    "description": desc,
                    "source": source,
                })

        return JSONResponse({
            "ok": True,
            "ready_count": ready_count,
            "total_count": total_count,
            "skills": skills,
        })
    except subprocess.TimeoutExpired:
        return JSONResponse({"ok": False, "error": "Skills list timed out"}, status_code=408)
    except FileNotFoundError:
        return JSONResponse({"ok": False, "error": "openclaw not found"}, status_code=404)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.post("/api/server/restart")
async def restart_server() -> JSONResponse:
    """
    Restarts the Mission Control server process by re-execing itself.
    The response is sent before the process replaces itself.
    """
    import threading

    # Resolve the venv Python: prefer the one next to sys.executable,
    # then fall back to sys.executable itself.
    _server_dir = Path(__file__).parent.parent.parent  # mission-control/
    _venv_python = _server_dir / ".venv" / "bin" / "python"
    python_bin = str(_venv_python) if _venv_python.exists() else sys.executable

    def _do_restart():
        import time, subprocess
        time.sleep(0.5)
        subprocess.Popen(
            [python_bin, "-m", "openclaw", "monitor"],
            cwd=str(_server_dir),
            start_new_session=True,
        )
        os._exit(0)

    t = threading.Thread(target=_do_restart, daemon=True)
    t.start()
    return JSONResponse({"ok": True, "message": "Mission Control restarting..."})


@app.post("/api/gateway/open-chat")
async def open_chat() -> JSONResponse:
    """
    Opens the OpenClaw dashboard in the browser.
    """
    import subprocess

    try:
        # Open dashboard (non-blocking)
        subprocess.Popen(["openclaw", "dashboard"])
        return JSONResponse({
            "ok": True,
            "message": "Opening OpenClaw dashboard...",
        })
    except Exception as e:
        return JSONResponse({
            "ok": False,
            "error": f"Failed to open dashboard: {str(e)}",
        }, status_code=500)


@app.post("/api/chat/send")
async def chat_send(request: Request) -> JSONResponse:
    """
    Sends a message to an agent and returns the response.
    Uses 'openclaw agent --json' subprocess for single-turn execution with session continuity.

    Body: {agentId, message, sessionId?}
    Returns: {ok, response, sessionId, model, runId}
    """
    body = await request.json()
    agent_id = str(body.get("agentId", "main")).strip()
    message = str(body.get("message", "")).strip()
    # Use client-provided sessionId, fall back to server-tracked session
    session_id = body.get("sessionId") or _chat_sessions.get(agent_id)

    if not message:
        return JSONResponse({"ok": False, "error": "Message is required"}, status_code=400)

    # Validate agentId to prevent injection
    import re as _re
    if not _re.match(r'^[a-zA-Z0-9_-]{1,64}$', agent_id):
        return JSONResponse({"ok": False, "error": "Invalid agentId"}, status_code=400)

    cmd = ["openclaw", "agent", "--agent", agent_id, "--message", message, "--json"]
    if session_id and _re.match(r'^[a-zA-Z0-9_-]{1,128}$', str(session_id)):
        cmd += ["--session-id", str(session_id)]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return JSONResponse({"ok": False, "error": "Agent timed out after 120 seconds"}, status_code=408)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"Failed to run agent: {str(e)}"}, status_code=500)

    if proc.returncode != 0:
        return JSONResponse({
            "ok": False,
            "error": stderr.decode(errors="replace").strip() or "Agent command failed",
        }, status_code=500)

    try:
        data = json.loads(stdout.decode(errors="replace"))
        payloads = data.get("result", {}).get("payloads", [])
        response_text = payloads[0].get("text", "") if payloads else ""
        meta = data.get("result", {}).get("meta", {}).get("agentMeta", {})
        new_session_id = meta.get("sessionId")
        if new_session_id:
            _chat_sessions[agent_id] = new_session_id
        model = meta.get("model", "")
        return JSONResponse({
            "ok": True,
            "response": response_text,
            "sessionId": new_session_id,
            "model": model,
            "runId": data.get("runId"),
        })
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        return JSONResponse({
            "ok": False,
            "error": f"Failed to parse agent response: {str(e)}",
            "raw": stdout.decode(errors="replace")[:500],
        }, status_code=500)


# Server-side session store: { agentId: sessionId }
_chat_sessions: dict[str, str] = {}


@app.delete("/api/chat/session/{agent_id}")
async def clear_chat_session(agent_id: str) -> JSONResponse:
    """
    Clears the server-side session state for an agent so the next chat
    message starts a fresh conversation (no --session-id passed).
    Returns: {ok, agentId}
    """
    import re as _re
    if not _re.match(r'^[a-zA-Z0-9_-]{1,64}$', agent_id):
        return JSONResponse({"ok": False, "error": "Invalid agentId"}, status_code=400)
    _chat_sessions.pop(agent_id, None)
    return JSONResponse({"ok": True, "agentId": agent_id})


@app.get("/api/agents/main")
async def get_main_agent() -> JSONResponse:
    """
    Returns information about which agent is currently the primary chat agent ('main').
    """
    try:
        config_path = Path.home() / ".openclaw" / "openclaw.json"
        if not config_path.exists():
            return JSONResponse({"mainAgent": None, "workspace": None})

        data = json.loads(config_path.read_text(encoding="utf-8"))
        agents_list = data.get("agents", {}).get("list", [])

        main_entry = next((a for a in agents_list if a.get("id") == "main"), None)
        if not main_entry:
            return JSONResponse({"mainAgent": None, "workspace": None})

        main_workspace = main_entry.get("workspace")

        # Try to infer which role is currently main by matching workspace
        promoted_role = None
        promoted_name = None

        # Load known agents from workspace if available
        mc_workspace = load_last_workspace()
        if mc_workspace:
            agents_file = Path(mc_workspace) / "AGENTS.md"
            if agents_file.exists():
                content = agents_file.read_text(encoding="utf-8")
                # Parse AGENTS.md for role → character mapping
                for role_name in ["pm", "architect", "builder", "qa", "security", "devops", "ux", "research"]:
                    if f"### Project Manager" in content and main_workspace and "openclaw-workspace" in main_workspace:
                        promoted_role = "pm"
                        promoted_name = "Project Manager"
                        break
                    # Simpler approach: read AGENTS.md sections

        return JSONResponse({
            "mainAgent": "main",
            "workspace": main_workspace,
            "promotedRole": promoted_role,
            "promotedName": promoted_name,
        })
    except Exception:
        return JSONResponse({"mainAgent": None, "workspace": None})


# ── WebSocket ──────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await hub.connect(websocket)
    # Send current state immediately on connect
    if _store:
        try:
            await websocket.send_json(_store.get())
        except Exception:
            pass
    try:
        while True:
            await websocket.receive_text()  # keep connection alive; client sends pings
    except WebSocketDisconnect:
        hub.disconnect(websocket)


# ── Static files and page routing ─────────────────────────────────────────────

@app.get("/")
async def index() -> FileResponse:
    return FileResponse(_static_dir() / "index.html")


@app.get("/install")
async def installer_page() -> FileResponse:
    return FileResponse(_static_dir() / "installer.html")


@app.get("/monitor")
async def monitor_page() -> FileResponse:
    return FileResponse(_static_dir() / "index.html")


# Mount static files last to avoid route conflicts
app.mount("/static", StaticFiles(directory=str(_static_dir())), name="static")


# ── Startup helpers ────────────────────────────────────────────────────────────

def configure(store, workspace_root: Path) -> None:
    global _store, _workspace_root
    _store = store
    _workspace_root = workspace_root
    # Wire state changes to WebSocket broadcasts
    store.register_listener(hub.broadcast_from_thread)

    # Sync any existing agents to openclaw.json (agents created but not yet registered)
    from openclaw.installer.agent_registrar import sync_existing_agents_to_config
    try:
        sync_existing_agents_to_config()
    except Exception:
        pass  # Non-critical — if sync fails, continue startup


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    uvicorn.run(app, host=host, port=port, log_level="warning")
