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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response

from openclaw.web.websocket_hub import hub
from openclaw.platform_utils import (
    get_corpus_dir, get_default_workspace_dir, find_existing_workspaces,
    save_last_workspace, load_last_workspace, write_openclaw_workspace_path,
    get_hardware_info, find_active_claude_processes,
    detect_openclaw_models, find_openclaw_config_path, update_openclaw_config,
    find_openclaw_binary, open_browser, is_windows,
)
from openclaw.installer.template_deployer import ROLE_LABELS
from openclaw.web.models import (
    InstallRequest, ChatSendRequest, AddAgentRequest, AgentCleanupRequest,
    ProjectRequest, BackupRestoreRequest, ConfigureProviderRequest,
    ReregisterRequest, WorkspaceAgentDeleteRequest, CreateTicketRequest,
    CloneProjectRequest,
)
from openclaw import __version__

# These are injected at startup from the CLI
_store = None
_workspace_root: Path | None = None
_installer_context: dict = {}
_auth_token: str | None = None  # Set at startup; None = no auth required

app = FastAPI(title="OpenClaw Mission Control", docs_url=None, redoc_url=None)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Optional bearer token auth. Only enforced for /api/ routes when _auth_token is set."""
    if _auth_token and request.url.path.startswith("/api/"):
        auth_header = request.headers.get("Authorization", "")
        if auth_header != f"Bearer {_auth_token}":
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return await call_next(request)


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
    """Lists local projects merged with GitHub repos. Uncloned repos marked cloned=false."""
    if _workspace_root is None:
        return JSONResponse({"error": "no workspace"}, status_code=503)
    projects_dir = _workspace_root / "projects"
    from openclaw.installer.template_deployer import read_project_metadata

    # 1. Local projects
    local_projects = {}
    if projects_dir.exists():
        for d in sorted(projects_dir.iterdir()):
            if d.is_dir():
                meta = read_project_metadata(d)
                local_projects[d.name] = {
                    "name": d.name,
                    "path": f"projects/{d.name}",
                    "source": meta.get("source", "local"),
                    "remote_url": meta.get("remote_url"),
                    "cloned": True,
                }

    # 2. GitHub repos (best-effort, don't fail if gh unavailable)
    gh_repos = []
    if shutil.which("gh"):
        try:
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    "gh", "repo", "list", "--json", "name,url,description,isPrivate", "--limit", "100",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                ),
                timeout=15,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                gh_repos = json.loads(stdout.decode())
        except Exception:
            pass  # gh unavailable or timed out — show local projects only

    # 3. Merge: add uncloned GH repos (exclude MC infra repos)
    _infra_repos = {"openclaw-multi-agent-workflow", "mission-control", "openclaw-mission-control"}
    for repo in gh_repos:
        repo_name = repo.get("name", "")
        if repo_name and repo_name not in local_projects and repo_name.lower() not in _infra_repos:
            local_projects[repo_name] = {
                "name": repo_name,
                "path": None,
                "source": "github",
                "remote_url": repo.get("url"),
                "description": repo.get("description", ""),
                "cloned": False,
            }

    projects = sorted(local_projects.values(), key=lambda p: (not p["cloned"], p["name"]))

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
    _reserved = {"mission-control", "openclaw-mission-control", "openclaw-multi-agent-workflow"}
    if project_name.lower() in _reserved:
        return JSONResponse({"ok": False, "error": f"'{project_name}' is a reserved name."}, status_code=400)
    project_dir = _workspace_root / "projects" / project_name
    if project_dir.exists():
        return JSONResponse({"ok": False, "error": f"Project '{project_name}' already exists"}, status_code=409)
    try:
        from openclaw.installer.template_deployer import deploy_project_files, write_project_metadata
        project_dir.mkdir(parents=True)
        (project_dir / "tickets" / "open").mkdir(parents=True, exist_ok=True)
        (project_dir / "tickets" / "closed").mkdir(parents=True, exist_ok=True)
        deploy_project_files(project_dir, project_name)
        write_project_metadata(project_dir, "local")
        return JSONResponse({"ok": True, "name": project_name})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.post("/api/tickets/create")
async def create_ticket(body: CreateTicketRequest) -> JSONResponse:
    """Creates a new ticket file in the active project's tickets/open/ directory."""
    if _workspace_root is None:
        return JSONResponse({"error": "no workspace"}, status_code=503)
    from openclaw.monitor.agent_state_reader import read_active_project
    active = read_active_project(_workspace_root)
    if not active:
        return JSONResponse({"ok": False, "error": "No active project"}, status_code=400)
    open_dir = _workspace_root / active["path"] / "tickets" / "open"
    open_dir.mkdir(parents=True, exist_ok=True)
    closed_dir = _workspace_root / active["path"] / "tickets" / "closed"
    # Auto-increment: find highest existing number for this type prefix
    prefix = body.ticket_type
    max_num = 0
    for d in [open_dir, closed_dir]:
        if d.exists():
            for f in d.glob(f"{prefix}-*.md"):
                try:
                    num = int(f.stem.split("-", 1)[1])
                    max_num = max(max_num, num)
                except (ValueError, IndexError):
                    pass
    ticket_num = max_num + 1
    ticket_id = f"{prefix}-{ticket_num:03d}"
    # Render the template
    from openclaw.installer.template_deployer import get_corpus_dir
    from jinja2 import Environment, FileSystemLoader
    corpus = get_corpus_dir()
    template_name = "epic.md.template" if body.ticket_type == "EPIC" else "ticket.md.template"
    env = Environment(loader=FileSystemLoader(str(corpus / "project")), trim_blocks=True, lstrip_blocks=True)
    tmpl = env.get_template(template_name)
    from datetime import date
    rendered = tmpl.render(
        ticket_id=ticket_id,
        title=body.title,
        ticket_type=body.ticket_type,
        priority=body.priority,
        severity=body.severity,
        epic=body.epic,
        found_by=body.found_by,
        assigned_to=body.assigned_to,
        status="proposed",
        description=body.description or "[To be filled]",
        created_date=date.today().isoformat(),
        updated_date=date.today().isoformat(),
    )
    ticket_file = open_dir / f"{ticket_id}.md"
    ticket_file.write_text(rendered, encoding="utf-8")
    return JSONResponse({"ok": True, "ticket_id": ticket_id, "file": str(ticket_file)})


# ── Asset Gallery ────────────────────────────────────────────────────────────

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"}


@app.get("/api/assets")
async def list_assets() -> JSONResponse:
    """Lists image assets from the active project's assets/ directory."""
    if _workspace_root is None:
        return JSONResponse({"error": "no workspace"}, status_code=503)
    from openclaw.monitor.agent_state_reader import read_active_project
    active = read_active_project(_workspace_root)
    if not active:
        return JSONResponse({"assets": [], "project": None})

    assets_dir = _workspace_root / active["path"] / "assets"
    if not assets_dir.exists():
        return JSONResponse({"assets": [], "project": active["name"]})

    assets = []
    for f in sorted(assets_dir.rglob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
        if f.is_file() and f.suffix.lower() in _IMAGE_EXTENSIONS:
            rel = f.relative_to(_workspace_root / active["path"])
            stat = f.stat()
            # Subfolder category (e.g. "icons", "banners") or "root"
            parts = rel.parts
            category = parts[1] if len(parts) > 2 else "uncategorized"
            assets.append({
                "name": f.name,
                "path": str(rel),
                "category": category,
                "size_bytes": stat.st_size,
                "size_kb": round(stat.st_size / 1024, 1),
                "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "ext": f.suffix.lower(),
            })

    return JSONResponse({"assets": assets, "project": active["name"]})


@app.get("/api/assets/file/{path:path}")
async def serve_asset(path: str) -> Response:
    """Serves an asset image file from the active project."""
    if _workspace_root is None:
        return JSONResponse({"error": "no workspace"}, status_code=503)
    from openclaw.monitor.agent_state_reader import read_active_project
    active = read_active_project(_workspace_root)
    if not active:
        return JSONResponse({"error": "no active project"}, status_code=404)

    file_path = (_workspace_root / active["path"] / path).resolve()
    project_root = (_workspace_root / active["path"]).resolve()

    # Security: ensure the path is within the project directory
    if not str(file_path).startswith(str(project_root)):
        return JSONResponse({"error": "access denied"}, status_code=403)
    if not file_path.exists() or not file_path.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)

    mime_map = {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
        ".bmp": "image/bmp", ".ico": "image/x-icon",
    }
    content_type = mime_map.get(file_path.suffix.lower(), "application/octet-stream")
    return Response(content=file_path.read_bytes(), media_type=content_type)


@app.post("/api/assets/commit")
async def commit_assets(request: Request) -> JSONResponse:
    """Commits and pushes all assets in the active project to its GitHub repo."""
    if _workspace_root is None:
        return JSONResponse({"error": "no workspace"}, status_code=503)
    from openclaw.monitor.agent_state_reader import read_active_project
    active = read_active_project(_workspace_root)
    if not active:
        return JSONResponse({"ok": False, "error": "No active project"}, status_code=400)

    project_dir = (_workspace_root / active["path"]).resolve()
    assets_dir = project_dir / "assets"
    if not assets_dir.exists():
        return JSONResponse({"ok": False, "error": "No assets/ directory"}, status_code=404)

    # Check if this is a git repo
    git_dir = project_dir / ".git"
    if not git_dir.exists():
        return JSONResponse({
            "ok": False,
            "error": "Project is not a git repo. Clone from GitHub first to enable asset commits.",
        }, status_code=400)

    try:
        # Stage all assets + asset-manifest.md
        stage_proc = await asyncio.create_subprocess_exec(
            "git", "add", "assets/", "asset-manifest.md",
            cwd=str(project_dir),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await stage_proc.communicate()

        # Check if there's anything to commit
        status_proc = await asyncio.create_subprocess_exec(
            "git", "diff", "--cached", "--quiet",
            cwd=str(project_dir),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await status_proc.communicate()
        if status_proc.returncode == 0:
            return JSONResponse({"ok": True, "message": "No new assets to commit"})

        # Count staged files for commit message
        count_proc = await asyncio.create_subprocess_exec(
            "git", "diff", "--cached", "--name-only",
            cwd=str(project_dir),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        count_out, _ = await count_proc.communicate()
        file_count = len(count_out.decode().strip().splitlines())

        # Commit
        msg = f"Add {file_count} asset(s) via OpenClaw Graphics Designer"
        commit_proc = await asyncio.create_subprocess_exec(
            "git", "commit", "-m", msg,
            cwd=str(project_dir),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        commit_out, commit_err = await commit_proc.communicate()
        if commit_proc.returncode != 0:
            return JSONResponse({"ok": False, "error": commit_err.decode(errors="replace")[:500]}, status_code=500)

        # Push
        push_proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                "git", "push",
                cwd=str(project_dir),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            ),
            timeout=30,
        )
        push_out, push_err = await push_proc.communicate()
        pushed = push_proc.returncode == 0

        return JSONResponse({
            "ok": True,
            "committed": file_count,
            "pushed": pushed,
            "push_error": push_err.decode(errors="replace")[:300] if not pushed else None,
            "message": msg,
        })

    except asyncio.TimeoutError:
        return JSONResponse({"ok": False, "error": "Push timed out"}, status_code=504)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/github/repos")
async def list_github_repos() -> JSONResponse:
    """Lists the user's GitHub repos using the gh CLI."""
    if not shutil.which("gh"):
        return JSONResponse({
            "ok": False,
            "error": "GitHub CLI (gh) not found",
            "install_hint": "Install from https://cli.github.com",
        }, status_code=503)
    try:
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                "gh", "repo", "list", "--json", "name,url,description,isPrivate", "--limit", "50",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            ),
            timeout=15,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode(errors="replace").strip()
            if "auth" in err.lower() or "login" in err.lower():
                return JSONResponse({"ok": False, "error": "Not authenticated. Run 'gh auth login' in your terminal."}, status_code=401)
            return JSONResponse({"ok": False, "error": err}, status_code=500)
        repos = json.loads(stdout.decode())
        return JSONResponse({"ok": True, "repos": repos})
    except asyncio.TimeoutError:
        return JSONResponse({"ok": False, "error": "gh CLI timed out"}, status_code=504)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.post("/api/projects/clone")
async def clone_project(body: CloneProjectRequest) -> JSONResponse:
    """Clones a GitHub repo into projects/ and deploys project template files."""
    if _workspace_root is None:
        return JSONResponse({"error": "no workspace"}, status_code=503)
    if not shutil.which("git"):
        return JSONResponse({"ok": False, "error": "git not found. Install from https://git-scm.com"}, status_code=503)
    # Derive project name from URL if not provided
    project_name = body.name
    if not project_name:
        project_name = body.repo_url.rstrip("/").split("/")[-1].removesuffix(".git")
    import re as _re
    if not _re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,49}$", project_name):
        return JSONResponse({"ok": False, "error": f"Invalid project name derived from URL: '{project_name}'"}, status_code=400)

    # Guard: prevent cloning the MC infrastructure repo as a project
    _infra_keywords = {"openclaw-multi-agent-workflow", "mission-control", "openclaw-mission-control"}
    if project_name.lower() in _infra_keywords:
        return JSONResponse({
            "ok": False,
            "error": (
                f"'{project_name}' looks like the Mission Control infrastructure repo, "
                "not a project to work on. If you really want this, use a different name."
            ),
        }, status_code=400)

    project_dir = _workspace_root / "projects" / project_name
    if project_dir.exists():
        return JSONResponse({"ok": False, "error": f"Project '{project_name}' already exists"}, status_code=409)
    try:
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                "git", "clone", body.repo_url, str(project_dir),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            ),
            timeout=120,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            # Clean up partial clone
            if project_dir.exists():
                shutil.rmtree(project_dir, ignore_errors=True)
            return JSONResponse({"ok": False, "error": stderr.decode(errors="replace").strip()}, status_code=500)
        # Deploy project template files inside the cloned repo
        from openclaw.installer.template_deployer import deploy_project_files, write_project_metadata
        (project_dir / "tickets" / "open").mkdir(parents=True, exist_ok=True)
        (project_dir / "tickets" / "closed").mkdir(parents=True, exist_ok=True)
        deploy_project_files(project_dir, project_name)
        write_project_metadata(project_dir, "github", remote_url=body.repo_url)
        return JSONResponse({"ok": True, "name": project_name})
    except asyncio.TimeoutError:
        if project_dir.exists():
            shutil.rmtree(project_dir, ignore_errors=True)
        return JSONResponse({"ok": False, "error": "Clone timed out after 120 seconds"}, status_code=504)
    except Exception as e:
        if project_dir.exists():
            shutil.rmtree(project_dir, ignore_errors=True)
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/backups")
async def list_backups() -> JSONResponse:
    """Lists available workspace backups."""
    backups_dir = Path.home() / ".openclaw-mission-control" / "backups"
    if not backups_dir.exists():
        return JSONResponse({"backups": []})
    backups = []
    for d in sorted(backups_dir.iterdir(), reverse=True):
        if d.is_dir():
            # Parse timestamp from dirname: workspace-name_2026-03-19T12-30-00
            parts = d.name.rsplit("_", 1)
            name = parts[0] if len(parts) > 1 else d.name
            ts = parts[1] if len(parts) > 1 else ""
            # Count files
            file_count = sum(1 for _ in d.rglob("*") if _.is_file())
            backups.append({
                "id": d.name,
                "workspace_name": name,
                "timestamp": ts.replace("-", ":").replace("T", " ") if ts else "",
                "path": str(d),
                "file_count": file_count,
            })
    return JSONResponse({"backups": backups[:20]})


@app.post("/api/backups/save")
async def save_backup(request: Request) -> JSONResponse:
    """Creates a timestamped snapshot of the current workspace."""
    if _workspace_root is None:
        return JSONResponse({"error": "no workspace"}, status_code=503)
    try:
        backups_dir = Path.home() / ".openclaw-mission-control" / "backups"
        backups_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        ws_name = _workspace_root.name
        backup_dir = backups_dir / f"{ws_name}_{ts}"
        shutil.copytree(_workspace_root, backup_dir, dirs_exist_ok=False)
        # Include encrypted vault if it exists
        vault_src = Path.home() / ".openclaw" / "vault"
        if vault_src.exists():
            shutil.copytree(vault_src, backup_dir / ".vault-backup", dirs_exist_ok=False)
        files = []
        for f in sorted(backup_dir.rglob("*")):
            if f.is_file():
                files.append(str(f.relative_to(backup_dir)))
        return JSONResponse({
            "ok": True,
            "backup_id": backup_dir.name,
            "path": str(backup_dir),
            "file_count": len(files),
            "files": files,
        })
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.post("/api/backups/restore")
async def restore_backup(request: Request) -> JSONResponse:
    """Restores workspace from a backup. Creates a safety backup of current state first."""
    if _workspace_root is None:
        return JSONResponse({"error": "no workspace"}, status_code=503)
    body = await request.json()
    backup_id = body.get("backup_id", "")
    if not backup_id:
        return JSONResponse({"ok": False, "error": "backup_id required"}, status_code=400)
    backups_dir = Path.home() / ".openclaw-mission-control" / "backups"
    backup_path = backups_dir / backup_id
    if not backup_path.exists():
        return JSONResponse({"ok": False, "error": "Backup not found"}, status_code=404)
    # Path safety
    if not str(backup_path.resolve()).startswith(str(backups_dir.resolve())):
        return JSONResponse({"ok": False, "error": "Invalid backup path"}, status_code=400)
    try:
        # Auto-save current state before restoring
        ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        safety_dir = backups_dir / f"{_workspace_root.name}_pre-restore_{ts}"
        shutil.copytree(_workspace_root, safety_dir, dirs_exist_ok=False)
        # Clear current workspace and copy backup
        for item in _workspace_root.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        shutil.copytree(backup_path, _workspace_root, dirs_exist_ok=True)
        # Restore vault if backup contains one
        vault_backup = backup_path / ".vault-backup"
        if vault_backup.exists():
            vault_dst = Path.home() / ".openclaw" / "vault"
            vault_dst.mkdir(parents=True, exist_ok=True)
            shutil.copytree(vault_backup, vault_dst, dirs_exist_ok=True)
        # Remove .vault-backup from workspace (it's not a workspace file)
        restored_vault = _workspace_root / ".vault-backup"
        if restored_vault.exists():
            shutil.rmtree(restored_vault)
        return JSONResponse({
            "ok": True,
            "restored_from": backup_id,
            "safety_backup": safety_dir.name,
        })
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.delete("/api/backups/{backup_id}")
async def delete_backup(backup_id: str) -> JSONResponse:
    """Deletes a backup."""
    backups_dir = Path.home() / ".openclaw-mission-control" / "backups"
    backup_path = backups_dir / backup_id
    if not backup_path.exists():
        return JSONResponse({"ok": False, "error": "Backup not found"}, status_code=404)
    if not str(backup_path.resolve()).startswith(str(backups_dir.resolve())):
        return JSONResponse({"ok": False, "error": "Invalid backup path"}, status_code=400)
    try:
        shutil.rmtree(backup_path)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/backups/{backup_id}/files")
async def browse_backup(backup_id: str) -> JSONResponse:
    """Returns the file tree for a backup."""
    backups_dir = Path.home() / ".openclaw-mission-control" / "backups"
    backup_path = backups_dir / backup_id
    if not backup_path.exists():
        return JSONResponse({"ok": False, "error": "Backup not found"}, status_code=404)
    if not str(backup_path.resolve()).startswith(str(backups_dir.resolve())):
        return JSONResponse({"ok": False, "error": "Invalid backup path"}, status_code=400)
    files = []
    for f in sorted(backup_path.rglob("*")):
        if f.is_file():
            rel = str(f.relative_to(backup_path))
            files.append({"path": rel, "size": f.stat().st_size})
    return JSONResponse({"ok": True, "backup_id": backup_id, "files": files})


@app.get("/api/backups/{backup_id}/file")
async def read_backup_file(backup_id: str, path: str = "") -> JSONResponse:
    """Reads a single file from a backup (read-only)."""
    backups_dir = Path.home() / ".openclaw-mission-control" / "backups"
    backup_path = backups_dir / backup_id
    if not backup_path.exists():
        return JSONResponse({"ok": False, "error": "Backup not found"}, status_code=404)
    if not str(backup_path.resolve()).startswith(str(backups_dir.resolve())):
        return JSONResponse({"ok": False, "error": "Invalid backup path"}, status_code=400)
    if not path:
        return JSONResponse({"ok": False, "error": "path parameter required"}, status_code=400)
    file_path = (backup_path / path).resolve()
    # Path traversal protection
    if not str(file_path).startswith(str(backup_path.resolve())):
        return JSONResponse({"ok": False, "error": "Invalid file path"}, status_code=400)
    if not file_path.exists() or not file_path.is_file():
        return JSONResponse({"ok": False, "error": "File not found"}, status_code=404)
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        # Cap at 100KB for safety
        if len(content) > 102400:
            content = content[:102400] + "\n\n... (truncated at 100KB)"
        return JSONResponse({"ok": True, "path": path, "content": content})
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
async def run_install(request: Request) -> JSONResponse:
    from openclaw.installer.workspace_builder import build_layout, create_workspace, write_agent_launchers
    from openclaw.installer.template_deployer import deploy_workspace_files, deploy_project_files
    from openclaw.installer.config_writer import write_claude_settings, write_mcp_config
    from openclaw.installer.agent_registrar import register_openclaw_agents

    try:
        body = InstallRequest(**(await request.json()))
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

    install_mode = body.install_mode

    # Dashboard-only mode: just register the workspace path, no file changes
    if install_mode == "dashboard-only":
        target = Path(body.target or str(Path.home() / "openclaw-workspace"))
        try:
            from openclaw.platform_utils import write_openclaw_workspace_path, save_last_workspace
            write_openclaw_workspace_path(target)
            save_last_workspace(str(target))
            global _workspace
            _workspace = target
            return JSONResponse({"ok": True, "workspace": str(target), "created": []})
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    target = Path(body.target or str(Path.home() / "openclaw-workspace"))

    # Auto-backup before upgrade/replace (safety net)
    if install_mode in ("upgrade", "replace") and target.exists():
        try:
            backups_dir = Path.home() / ".openclaw-mission-control" / "backups"
            backups_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
            backup_dir = backups_dir / f"{target.name}_pre-{install_mode}_{ts}"
            shutil.copytree(target, backup_dir, dirs_exist_ok=False)
        except Exception:
            pass  # Non-critical — don't block install on backup failure

    theme = body.theme
    custom_characters = body.custom_characters or {}
    team_size = body.team_size
    project_name = body.project_name
    operator_name = body.operator_name
    update_mode = install_mode != "new"

    model_map = {
        "strategic":      body.model_strategic,
        "implementation": body.model_implementation,
        "support":        body.model_support,
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

        mcp_path = write_mcp_config(target)
        created.append(mcp_path)

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


# ── Agent model management ────────────────────────────────────────────────────


@app.post("/api/agents/model")
async def change_agent_model(request: Request) -> JSONResponse:
    """Changes an agent's model in AGENTS.md and launcher scripts."""
    if _workspace_root is None:
        return JSONResponse({"error": "no workspace"}, status_code=503)
    body = await request.json()
    role = body.get("role", "").strip().lower()
    new_model = body.get("model", "").strip()
    if not role or not new_model:
        return JSONResponse({"ok": False, "error": "role and model required"}, status_code=400)

    updated = []

    # 1. Update AGENTS.md — find the agent section and replace its **Model:** line
    agents_md = _workspace_root / "AGENTS.md"
    if agents_md.exists():
        content = agents_md.read_text(encoding="utf-8")
        lines = content.splitlines()
        from openclaw.installer.template_deployer import ROLE_LABELS
        role_label = ROLE_LABELS.get(role, role.title())
        # Find the section for this role and update the Model line within it
        in_section = False
        for i, line in enumerate(lines):
            if line.startswith("### ") and role_label in line:
                in_section = True
            elif line.startswith("### ") and in_section:
                break  # moved past our section
            elif in_section and line.startswith("**Model:**"):
                lines[i] = f"**Model:** {new_model}"
                updated.append("AGENTS.md")
                break
        agents_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # 2. Update launcher scripts
    launchers = _workspace_root / "launchers"
    for ext, comment_prefix in [("sh", "#"), ("bat", "REM")]:
        script = launchers / f"run-{role}.{ext}"
        if script.exists():
            content = script.read_text(encoding="utf-8")
            new_lines = []
            for line in content.splitlines():
                # Update comment: # Model: old → # Model: new
                if line.strip().startswith(f"{comment_prefix} Model:"):
                    new_lines.append(f"{comment_prefix} Model: {new_model}")
                # Update command: --model old → --model new
                elif "--model " in line:
                    new_lines.append(re.sub(r"--model\s+\S+", f"--model {new_model}", line))
                else:
                    new_lines.append(line)
            script.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
            updated.append(f"run-{role}.{ext}")

    if not updated:
        return JSONResponse({"ok": False, "error": f"No files found for role '{role}'"}, status_code=404)

    return JSONResponse({"ok": True, "updated": updated, "role": role, "model": new_model})


@app.post("/api/agents/model/bulk")
async def change_all_agent_models(request: Request) -> JSONResponse:
    """Changes the model for ALL agents at once."""
    if _workspace_root is None:
        return JSONResponse({"error": "no workspace"}, status_code=503)
    body = await request.json()
    new_model = body.get("model", "").strip()
    if not new_model:
        return JSONResponse({"ok": False, "error": "model required"}, status_code=400)

    # Find all roles from AGENTS.md
    agents_md = _workspace_root / "AGENTS.md"
    if not agents_md.exists():
        return JSONResponse({"ok": False, "error": "AGENTS.md not found"}, status_code=404)

    content = agents_md.read_text(encoding="utf-8")
    # Replace all **Model:** lines
    new_content = re.sub(r"\*\*Model:\*\*\s*.+", f"**Model:** {new_model}", content)
    agents_md.write_text(new_content, encoding="utf-8")

    # Update all launcher scripts
    launchers = _workspace_root / "launchers"
    updated_launchers = 0
    if launchers.exists():
        for script in launchers.iterdir():
            if not script.is_file():
                continue
            ext = script.suffix
            comment_prefix = "#" if ext == ".sh" else "REM" if ext == ".bat" else None
            if comment_prefix is None:
                continue
            text = script.read_text(encoding="utf-8")
            new_lines = []
            changed = False
            for line in text.splitlines():
                if line.strip().startswith(f"{comment_prefix} Model:"):
                    new_lines.append(f"{comment_prefix} Model: {new_model}")
                    changed = True
                elif "--model " in line:
                    new_lines.append(re.sub(r"--model\s+\S+", f"--model {new_model}", line))
                    changed = True
                else:
                    new_lines.append(line)
            if changed:
                script.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
                updated_launchers += 1

    return JSONResponse({"ok": True, "model": new_model, "launchers_updated": updated_launchers})


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


@app.get("/api/system/specs")
async def system_specs() -> JSONResponse:
    """Returns machine specs for hardware-aware model recommendations."""
    import platform
    import subprocess as _sp

    specs: dict = {"os": platform.system(), "arch": platform.machine()}

    # RAM
    try:
        if platform.system() == "Darwin":
            mem = int(_sp.check_output(["sysctl", "-n", "hw.memsize"]).strip())
            specs["ram_gb"] = round(mem / (1024**3))
        elif platform.system() == "Windows":
            import ctypes
            mem = ctypes.c_ulonglong()
            ctypes.windll.kernel32.GetPhysicallyInstalledMemory(ctypes.byref(mem))
            specs["ram_gb"] = round(mem.value / (1024 * 1024))
        else:  # Linux
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        specs["ram_gb"] = round(int(line.split()[1]) / (1024 * 1024))
                        break
    except Exception:
        specs["ram_gb"] = 0

    # CPU / chip
    try:
        if platform.system() == "Darwin":
            specs["chip"] = _sp.check_output(["sysctl", "-n", "machdep.cpu.brand_string"]).decode().strip()
        else:
            specs["chip"] = platform.processor() or "Unknown"
    except Exception:
        specs["chip"] = "Unknown"

    # GPU
    try:
        if platform.system() == "Darwin":
            gpu_out = _sp.check_output(["system_profiler", "SPDisplaysDataType"], timeout=5).decode()
            for line in gpu_out.splitlines():
                if "Chipset Model:" in line or "Chip:" in line:
                    specs["gpu"] = line.split(":", 1)[1].strip()
                    break
                if "Metal Support:" in line:
                    specs["metal"] = line.split(":", 1)[1].strip()
            gpu_cores_line = [l for l in gpu_out.splitlines() if "Total Number of Cores" in l]
            if gpu_cores_line:
                specs["gpu_cores"] = int(gpu_cores_line[0].split(":", 1)[1].strip())
        elif platform.system() == "Windows":
            gpu_out = _sp.check_output(["wmic", "path", "win32_videocontroller", "get", "name"], timeout=5).decode()
            gpus = [l.strip() for l in gpu_out.splitlines()[1:] if l.strip()]
            if gpus:
                specs["gpu"] = gpus[0]
    except Exception:
        pass

    # Disk free space
    try:
        import shutil as _sh
        usage = _sh.disk_usage(str(Path.home()))
        specs["disk_free_gb"] = round(usage.free / (1024**3))
    except Exception:
        specs["disk_free_gb"] = 0

    # Recommend image models based on specs
    ram = specs.get("ram_gb", 0)
    chip = specs.get("chip", "").lower()
    has_apple_silicon = "apple" in chip or "m1" in chip or "m2" in chip or "m3" in chip or "m4" in chip
    has_nvidia = "nvidia" in specs.get("gpu", "").lower() or "geforce" in specs.get("gpu", "").lower()

    recommendations = []
    if ram >= 8 and (has_apple_silicon or has_nvidia):
        gpu_type = "Apple Metal (MPS)" if has_apple_silicon else "NVIDIA CUDA"
        recommendations.append({
            "id": "sdxl-turbo",
            "name": "SDXL Turbo",
            "maker": "Stability AI",
            "size_gb": 6.5,
            "speed": "2-4 sec/image",
            "quality": "Good",
            "description": "Fast, 1-4 diffusion steps. Best balance of speed and quality for agent workflows.",
            "why": f"Recommended for your {specs.get('chip', 'machine')}: generates in 1-4 steps vs 20+ for other models, "
                   f"runs on {gpu_type}, and handles logos/icons/banners well. Free — no API costs.",
            "recommended": True,
        })
    if ram >= 6:
        recommendations.append({
            "id": "sd-1.5",
            "name": "Stable Diffusion 1.5",
            "maker": "Stability AI (Runway)",
            "size_gb": 4.0,
            "speed": "5-15 sec/image",
            "quality": "Good",
            "description": "Classic model. Smaller download, wide compatibility.",
            "why": "Smaller download but slower (20+ steps) and lower resolution (512x512). "
                   "Good fallback if disk space is tight.",
            "recommended": ram < 12,
        })
    if ram >= 16 and (has_apple_silicon or has_nvidia):
        recommendations.append({
            "id": "sd-3.5-medium",
            "name": "Stable Diffusion 3.5 Medium",
            "maker": "Stability AI",
            "size_gb": 5.5,
            "speed": "8-12 sec/image",
            "quality": "Great",
            "description": "Latest architecture. Best quality for the size.",
            "why": "Higher fidelity output with newer MMDiT architecture. Worth adding if you need "
                   "photorealistic or highly detailed assets. Slower than SDXL Turbo.",
            "recommended": False,
        })

    # Cloud options (always available)
    recommendations.append({
        "id": "gemini",
        "name": "Google Gemini / Imagen",
        "maker": "Google",
        "size_gb": 0,
        "speed": "2-5 sec/image",
        "quality": "Great",
        "description": "Cloud API. Requires Google AI Studio API key with billing enabled.",
        "why": "Best quality but requires billing. Good complement to local models for high-fidelity final assets.",
        "recommended": False,
        "cloud": True,
    })

    specs["image_models"] = recommendations
    return JSONResponse(specs)


@app.get("/api/image-models/status")
async def image_model_status() -> JSONResponse:
    """Check which local image models are already downloaded."""
    models_dir = Path.home() / ".openclaw" / "models"
    installed = []
    for model_id in ["sdxl-turbo", "sd-1.5", "sd-3.5-medium"]:
        model_path = models_dir / model_id
        if model_path.exists() and any(model_path.iterdir()):
            size_mb = sum(f.stat().st_size for f in model_path.rglob("*") if f.is_file()) / (1024 * 1024)
            installed.append({"id": model_id, "path": str(model_path), "size_mb": round(size_mb)})
    return JSONResponse({"installed": installed})


@app.get("/api/image-models/deps")
async def image_model_deps() -> JSONResponse:
    """Check which Python packages needed for local image gen are installed."""
    deps = {}
    for pkg in ["torch", "diffusers", "transformers", "accelerate", "huggingface_hub"]:
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-c", f"import {pkg}; print({pkg}.__version__)",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                deps[pkg] = {"installed": True, "version": stdout.decode().strip()}
            else:
                deps[pkg] = {"installed": False}
        except Exception:
            deps[pkg] = {"installed": False}
    return JSONResponse({"deps": deps})


@app.post("/api/image-models/install-deps")
async def install_image_deps(request: Request) -> JSONResponse:
    """Install Python packages required for local image generation."""
    packages = [
        "torch", "torchvision",
        "diffusers", "transformers", "accelerate",
        "huggingface_hub", "protobuf", "sentencepiece",
    ]
    try:
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                sys.executable, "-m", "pip", "install", "-q", *packages,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            ),
            timeout=600,  # torch is large, can take a while
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            return JSONResponse({
                "ok": False,
                "error": stderr.decode(errors="replace")[:500],
            }, status_code=500)
        return JSONResponse({"ok": True, "packages": packages})
    except asyncio.TimeoutError:
        return JSONResponse({"ok": False, "error": "Install timed out (10 min limit)"}, status_code=504)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.post("/api/image-models/install")
async def install_image_model(request: Request) -> JSONResponse:
    """Downloads and installs a local image generation model."""
    body = await request.json()
    model_id = body.get("model_id", "")

    # Model registry: HuggingFace repo IDs
    MODEL_REPOS = {
        "sdxl-turbo": "stabilityai/sdxl-turbo",
        "sd-1.5": "stable-diffusion-v1-5/stable-diffusion-v1-5",
        "sd-3.5-medium": "stabilityai/stable-diffusion-3.5-medium",
    }

    if model_id not in MODEL_REPOS:
        return JSONResponse({"ok": False, "error": f"Unknown model: {model_id}"}, status_code=400)

    models_dir = Path.home() / ".openclaw" / "models" / model_id
    if models_dir.exists() and any(models_dir.iterdir()):
        return JSONResponse({"ok": True, "already_installed": True, "path": str(models_dir)})

    # Ensure huggingface_hub is available before attempting download
    hf_check = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import huggingface_hub",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    await hf_check.communicate()
    if hf_check.returncode != 0:
        pip_proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "pip", "install", "-q", "huggingface_hub",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await pip_proc.communicate()

    models_dir.mkdir(parents=True, exist_ok=True)
    repo_id = MODEL_REPOS[model_id]

    try:
        # Download fp16 variant only — skip full-precision weights, ONNX, and docs
        # This cuts download from ~30 GB to ~6 GB for SDXL Turbo
        download_script = (
            f"from huggingface_hub import snapshot_download; "
            f"snapshot_download("
            f"'{repo_id}', "
            f"local_dir='{models_dir}', "
            f"ignore_patterns=["
            f"'*.ckpt', '*.safetensors.index.json', "
            f"'*.onnx', '*.onnx_data', '*.xml', '*.pb', "
            f"'README.md', 'LICENSE*'"
            f"], "
            f"allow_patterns=["
            f"'**/*.fp16.safetensors', '**/*.json', "
            f"'**/merges.txt', '**/vocab.json', '**/special_tokens_map.json', "
            f"'**/tokenizer_config.json', "
            f"'**/*.safetensors', 'model_index.json'"
            f"]"
            f")"
        )
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                sys.executable, "-c", download_script,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            ),
            timeout=600,  # 10 min for large downloads
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode(errors="replace").strip()
            return JSONResponse({"ok": False, "error": err[:500]}, status_code=500)

        # Clean up download cache to save disk space
        cache_dir = models_dir / ".cache"
        if cache_dir.exists():
            shutil.rmtree(cache_dir, ignore_errors=True)

        return JSONResponse({"ok": True, "path": str(models_dir), "model_id": model_id})

    except asyncio.TimeoutError:
        return JSONResponse({"ok": False, "error": "Download timed out (10 min limit)"}, status_code=504)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.post("/api/agents/add")
async def add_agent(request: Request) -> JSONResponse:
    """
    Adds a new custom agent role.
    Body: {role: str, name: str, label: str}
    Creates IDENTITY.md and registers in openclaw.json + AGENTS.md.
    """
    try:
        body = AddAgentRequest(**(await request.json()))
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

    role = body.role
    name = body.name.strip()
    label = body.label.strip() or name

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


# ── Vault (encrypted credential storage) ─────────────────────────────────────

from openclaw.vault import Vault, VaultError

_vault = Vault()


@app.get("/api/vault/status")
async def vault_status() -> JSONResponse:
    """Check if the vault is unlocked and initialized."""
    return JSONResponse({
        "initialized": _vault.is_initialized,
        "unlocked": _vault.is_unlocked,
    })


@app.post("/api/vault/unlock")
async def vault_unlock(request: Request) -> JSONResponse:
    """Unlock the vault with a passphrase (or create it on first use)."""
    body = await request.json()
    passphrase = body.get("passphrase", "")
    if not passphrase:
        return JSONResponse({"ok": False, "error": "Passphrase is required."}, status_code=400)
    try:
        _vault.unlock(passphrase)
        return JSONResponse({"ok": True, "created": not _vault.is_initialized})
    except VaultError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=401)


@app.post("/api/vault/lock")
async def vault_lock() -> JSONResponse:
    """Lock the vault immediately — clears in-memory keys."""
    _vault.lock()
    return JSONResponse({"ok": True})


@app.get("/api/vault/list")
async def vault_list() -> JSONResponse:
    """List all secret names (values are NOT returned)."""
    if not _vault.is_unlocked:
        return JSONResponse({"ok": False, "error": "Vault is locked."}, status_code=403)
    return JSONResponse({"ok": True, "secrets": _vault.list_names()})


@app.get("/api/vault/get/{name}")
async def vault_get(name: str) -> JSONResponse:
    """Retrieve a single secret value by name."""
    if not _vault.is_unlocked:
        return JSONResponse({"ok": False, "error": "Vault is locked."}, status_code=403)
    try:
        value = _vault.get(name)
        return JSONResponse({"ok": True, "name": name, "value": value})
    except KeyError:
        return JSONResponse({"ok": False, "error": f"Secret '{name}' not found."}, status_code=404)


@app.post("/api/vault/store")
async def vault_store(request: Request) -> JSONResponse:
    """Store a named secret. Body: {name, value}"""
    if not _vault.is_unlocked:
        return JSONResponse({"ok": False, "error": "Vault is locked."}, status_code=403)
    body = await request.json()
    name = body.get("name", "").strip()
    value = body.get("value", "")
    if not name:
        return JSONResponse({"ok": False, "error": "Secret name is required."}, status_code=400)
    _vault.store(name, value)
    return JSONResponse({"ok": True, "name": name})


@app.post("/api/vault/delete")
async def vault_delete(request: Request) -> JSONResponse:
    """Soft-delete a named secret (moved to archive). Body: {name}"""
    if not _vault.is_unlocked:
        return JSONResponse({"ok": False, "error": "Vault is locked."}, status_code=403)
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        return JSONResponse({"ok": False, "error": "Secret name is required."}, status_code=400)
    existed = _vault.delete(name)
    if not existed:
        return JSONResponse({"ok": False, "error": f"Secret '{name}' not found."}, status_code=404)
    return JSONResponse({"ok": True, "name": name, "archived": True})


@app.get("/api/vault/deleted")
async def vault_deleted() -> JSONResponse:
    """List soft-deleted secrets (name + deleted_at, no values)."""
    if not _vault.is_unlocked:
        return JSONResponse({"ok": False, "error": "Vault is locked."}, status_code=403)
    return JSONResponse({"ok": True, "deleted": _vault.list_deleted()})


@app.post("/api/vault/recover")
async def vault_recover(request: Request) -> JSONResponse:
    """Recover a soft-deleted secret back to active. Body: {name}"""
    if not _vault.is_unlocked:
        return JSONResponse({"ok": False, "error": "Vault is locked."}, status_code=403)
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        return JSONResponse({"ok": False, "error": "Secret name is required."}, status_code=400)
    recovered = _vault.recover(name)
    if not recovered:
        return JSONResponse({"ok": False, "error": f"No deleted secret '{name}' found."}, status_code=404)
    return JSONResponse({"ok": True, "name": name})


@app.post("/api/vault/purge")
async def vault_purge(request: Request) -> JSONResponse:
    """Permanently delete a secret from the archive. Body: {name}"""
    if not _vault.is_unlocked:
        return JSONResponse({"ok": False, "error": "Vault is locked."}, status_code=403)
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        return JSONResponse({"ok": False, "error": "Secret name is required."}, status_code=400)
    count = _vault.purge(name)
    if count == 0:
        return JSONResponse({"ok": False, "error": f"No deleted entries for '{name}'."}, status_code=404)
    return JSONResponse({"ok": True, "name": name, "purged": count})


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
    try:
        body = ChatSendRequest(**(await request.json()))
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

    agent_id = body.agentId
    message = body.message.strip()
    session_id = body.sessionId or _chat_sessions.get(agent_id)

    if not message:
        return JSONResponse({"ok": False, "error": "Message is required"}, status_code=400)

    cmd = ["openclaw", "agent", "--agent", agent_id, "--message", message, "--json"]
    import re as _re
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

def configure(store, workspace_root: Path, auth_token: str | None = None) -> None:
    global _store, _workspace_root, _auth_token
    _store = store
    _workspace_root = workspace_root
    _auth_token = auth_token
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
