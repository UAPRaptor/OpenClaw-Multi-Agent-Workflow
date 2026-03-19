"""
OpenClaw Mission Control — CLI entry point.
Commands: install, monitor, status
"""
import asyncio
import sys
import threading
from pathlib import Path
from typing import Optional

import typer

from openclaw.platform_utils import (
    get_default_workspace_dir,
    find_existing_workspaces,
    open_browser,
    get_platform_label,
)

app = typer.Typer(
    name="openclaw",
    help="OpenClaw Mission Control — install and monitor multi-agent workspaces.",
    add_completion=False,
)

SERVER_PORT = 8765
SERVER_HOST = "127.0.0.1"


@app.command()
def install(
    workspace: Optional[str] = typer.Option(
        None, "--workspace", "-w", help="Path for the new workspace (default: ~/openclaw-workspace)"
    ),
    auth: bool = typer.Option(False, "--auth", help="Enable bearer token auth for API endpoints"),
):
    """Launch the installation wizard in your browser."""
    workspace_path = Path(workspace) if workspace else get_default_workspace_dir()
    _start_server(workspace_root=workspace_path, open_path="/install", enable_auth=auth)


@app.command()
def monitor(
    workspace: Optional[str] = typer.Option(
        None, "--workspace", "-w", help="Workspace path to monitor"
    ),
    auth: bool = typer.Option(False, "--auth", help="Enable bearer token auth for API endpoints"),
):
    """Start the live monitor dashboard for an existing workspace."""
    workspace_path = Path(workspace) if workspace else _find_workspace()
    if not workspace_path.exists():
        typer.echo(
            f"Workspace not found at {workspace_path}\n"
            "Run 'openclaw install' to create a new workspace.",
            err=True,
        )
        raise typer.Exit(1)
    _start_server(workspace_root=workspace_path, open_path="/monitor", enable_auth=auth)


@app.command()
def status(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w")
):
    """Print a quick text summary of the workspace status (no browser required)."""
    workspace_path = Path(workspace) if workspace else _find_workspace()
    if not workspace_path.exists():
        typer.echo(f"Workspace not found at {workspace_path}", err=True)
        raise typer.Exit(1)

    from openclaw.monitor.agent_state_reader import (
        read_active_project,
        read_project_status,
        read_tickets,
    )

    active = read_active_project(workspace_path)
    if not active:
        typer.echo("No active project found in workspace.")
        return

    project_status = read_project_status(workspace_path, active["path"])
    tickets = read_tickets(workspace_path, active["path"])

    typer.echo(f"\nOpenClaw Workspace: {workspace_path}")
    typer.echo(f"Active project:     {active['name']}")
    typer.echo(f"Milestone:          {project_status.get('milestone_current', '?')} / {project_status.get('milestone_total', '?')}")
    typer.echo(f"\nTickets:")
    for state, count in tickets.items():
        if count > 0:
            typer.echo(f"  {state:12s} {count}")
    typer.echo()


# ── Server startup ─────────────────────────────────────────────────────────

def _find_workspace() -> Path:
    """Returns the most recently used workspace, or the default path."""
    found = find_existing_workspaces()
    if found:
        return found[0]
    return get_default_workspace_dir()


def _start_server(workspace_root: Path, open_path: str = "/", enable_auth: bool = False) -> None:
    """
    Starts the FastAPI server, wires up the monitor if workspace exists,
    opens the browser, and blocks until Ctrl+C.
    """
    import secrets
    from openclaw.monitor.state_store import StateStore
    from openclaw.monitor.alert_engine import AlertEngine
    from openclaw.monitor.file_watcher import WorkspaceWatcher
    from openclaw.web import server as web_server
    from openclaw.web.websocket_hub import hub

    typer.echo(f"OpenClaw Mission Control — {get_platform_label()}")
    typer.echo(f"Starting server at http://{SERVER_HOST}:{SERVER_PORT}")

    # Generate auth token if requested
    auth_token = None
    if enable_auth:
        auth_token = secrets.token_urlsafe(32)
        typer.echo(f"Auth token: {auth_token}")
        typer.echo("Include 'Authorization: Bearer <token>' in API requests.")

    # Set up monitor if workspace exists
    store = StateStore(workspace_root)
    alert_engine = AlertEngine(workspace_root, store)
    web_server.configure(store, workspace_root, auth_token=auth_token)

    watcher = None
    if workspace_root.exists():
        watcher = WorkspaceWatcher(workspace_root, store, alert_engine)
        watcher.start()
        typer.echo(f"Monitoring workspace: {workspace_root}")
    else:
        typer.echo(f"Workspace not found — install mode only.")

    # Open browser after a short delay (let server start first)
    def delayed_open():
        import time
        time.sleep(1.2)
        url = f"http://{SERVER_HOST}:{SERVER_PORT}{open_path}"
        open_browser(url)
        typer.echo(f"Opened browser: {url}")

    browser_thread = threading.Thread(target=delayed_open, daemon=True)
    browser_thread.start()

    typer.echo("Press Ctrl+C to stop.\n")

    # Wire WebSocket hub's event loop reference
    import asyncio

    async def _run():
        hub.set_loop(asyncio.get_event_loop())
        # Run uvicorn programmatically so we can capture the loop
        import uvicorn
        config = uvicorn.Config(
            web_server.app,
            host=SERVER_HOST,
            port=SERVER_PORT,
            log_level="warning",
            loop="asyncio",
        )
        server = uvicorn.Server(config)
        await server.serve()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        typer.echo("\nStopping...")
    finally:
        if watcher:
            watcher.stop()
