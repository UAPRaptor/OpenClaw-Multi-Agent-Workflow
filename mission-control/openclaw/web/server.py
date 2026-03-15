"""
FastAPI application.
Binds ONLY to 127.0.0.1 — never accessible from the network.
Serves the installer wizard, monitor dashboard, REST API, and WebSocket.
"""
import asyncio
import sys
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from openclaw.web.websocket_hub import hub
from openclaw.platform_utils import (
    get_corpus_dir, get_default_workspace_dir, find_existing_workspaces,
    save_last_workspace, get_hardware_info, find_active_claude_processes,
    detect_openclaw_models, find_openclaw_config_path, update_openclaw_config,
    find_openclaw_binary, open_browser, is_windows,
)
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


@app.post("/api/install")
async def run_install(body: dict) -> JSONResponse:
    from openclaw.installer.workspace_builder import build_layout, create_workspace, write_agent_launchers
    from openclaw.installer.template_deployer import deploy_workspace_files, deploy_project_files
    from openclaw.installer.config_writer import write_claude_settings
    from openclaw.installer.agent_registrar import register_openclaw_agents

    target = Path(body.get("target", str(Path.home() / "openclaw-workspace")))
    theme = body.get("theme", "historical")
    custom_characters = body.get("custom_characters") or {}  # {role: character_name} overrides
    team_size = int(body.get("team_size", 4))
    project_name = body.get("project_name", "example-app")
    operator_name = body.get("operator_name", "Operator")
    # install_mode: "new" | "upgrade" | "replace"
    # - new: fresh workspace
    # - upgrade: add multi-agent team to existing workspace, preserve projects/ and CLAUDE.md
    # - replace: redeploy all config to existing path, preserve projects/ only
    install_mode = body.get("install_mode", "new")
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


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    uvicorn.run(app, host=host, port=port, log_level="warning")
