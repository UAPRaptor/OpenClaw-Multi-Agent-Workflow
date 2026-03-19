"""
Registers installed agents with OpenClaw's native agent directory so that
each agent appears as a distinct entry in OpenClaw's Agents list.

OpenClaw agent directory layout:
  ~/.openclaw/agents/{role}/
    IDENTITY.md     — who this agent is (character, role, philosophy)

Agents are invoked via:
  openclaw agent --agent {role} --message "..."
"""
from datetime import date, datetime, timezone
from pathlib import Path
import json
import shutil
import uuid

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from openclaw.platform_utils import get_corpus_dir


def register_openclaw_agents(agents: list[dict]) -> list[str]:
    """
    Creates per-agent directories at ~/.openclaw/agents/{role}/ and renders
    an IDENTITY.md file in each one. Also registers agents in openclaw.json
    so they appear in the OpenClaw agents list and are available for chat.

    Returns list of created paths (for display in the installer UI).
    """
    corpus = get_corpus_dir()
    env = Environment(
        loader=FileSystemLoader(str(corpus / "agents")),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    tmpl = env.get_template("IDENTITY.md.template")

    base_dir = Path.home() / ".openclaw" / "agents"
    base_dir.mkdir(parents=True, exist_ok=True)
    created = []
    agent_ids = []
    workspace_path = None
    workflow_id = uuid.uuid4().hex[:12]  # shared across all agents in this install batch

    for agent in agents:
        role = agent["role"]
        agent_dir = base_dir / role
        agent_dir.mkdir(exist_ok=True)
        created.append(str(agent_dir))

        # Extract workspace path from first agent (all agents in a team use the same workspace)
        if workspace_path is None and "workspace_path" in agent:
            workspace_path = agent["workspace_path"]

        context = {
            **agent,
            "install_date": date.today().isoformat(),
            "workflow_id": workflow_id,
        }
        rendered = tmpl.render(**context)
        identity_path = agent_dir / "IDENTITY.md"
        identity_path.write_text(rendered, encoding="utf-8")
        created.append(str(identity_path))
        agent_ids.append(role)

    # Register agents in openclaw.json so they appear in OpenClaw agents list
    _register_agents_in_config(agent_ids, workspace_path, agents)

    return created


def _register_agents_in_config(agent_ids: list[str], workspace_path: str | None = None, agents: list[dict] | None = None) -> bool:
    """
    Adds agents to openclaw.json's agents.list so they appear in the
    OpenClaw agents list and become available for chat.

    If workspace_path is provided, uses it; otherwise falls back to the default.
    If agents list is provided, writes identity.name so the gateway uses the
    correct character name instead of the default "Sensei".
    Returns True if successful, False otherwise.
    """
    config_path = Path.home() / ".openclaw" / "openclaw.json"
    if not config_path.exists():
        return False

    # Use provided workspace path or fall back to default
    if workspace_path is None:
        workspace_path = str(Path.home() / ".openclaw" / "workspace")
    else:
        workspace_path = str(workspace_path)

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))

        # Ensure agents.list exists
        if "agents" not in data:
            data["agents"] = {}
        if "list" not in data["agents"]:
            data["agents"]["list"] = []

        # Build character name lookup from agents list (role -> character)
        char_map = {a["role"]: a.get("character", "") for a in (agents or [])}

        # Add each agent (skip if already exists)
        openclaw_agents_base = str(Path.home() / ".openclaw" / "agents")
        for agent_id in agent_ids:
            existing = [a for a in data["agents"]["list"] if a.get("id") == agent_id]
            if existing:
                continue
            entry: dict = {
                "id": agent_id,
                "workspace": workspace_path,
                "agentDir": f"{openclaw_agents_base}/{agent_id}/agent",
            }
            if char_map.get(agent_id):
                entry["identity"] = {"name": char_map[agent_id]}
            data["agents"]["list"].append(entry)

        # Set subagents.allowAgents on every agent so agents can spawn each other.
        # Each agent gets access to all OTHER agents in the full list.
        all_ids = [a.get("id") for a in data["agents"]["list"] if a.get("id")]
        for agent in data["agents"]["list"]:
            agent_id = agent.get("id")
            if not agent_id:
                continue
            others = [aid for aid in all_ids if aid != agent_id]
            if others:
                agent.setdefault("subagents", {})["allowAgents"] = others

        # Write back to config
        config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def unregister_agent(agent_id: str) -> bool:
    """
    Removes the IDENTITY.md file for an agent, unregistering it from OpenClaw.
    Also removes it from openclaw.json agents.list.
    Keeps the directory and any sessions/state files intact.
    Returns True if successful, False if not found or error.
    """
    agent_dir = Path.home() / ".openclaw" / "agents" / agent_id
    identity_file = agent_dir / "IDENTITY.md"

    if not identity_file.exists():
        return False

    try:
        identity_file.unlink()
        # Also remove from config
        _remove_agent_from_config(agent_id)
        return True
    except Exception:
        return False


def archive_agent(agent_id: str) -> str | None:
    """
    Renames an agent directory to preserve it: {id}-archived-{timestamp}.
    Also removes it from openclaw.json agents.list.
    Useful for keeping session history while removing the agent from active use.
    Returns the new directory path on success, None on failure.
    """
    agent_dir = Path.home() / ".openclaw" / "agents" / agent_id

    if not agent_dir.exists():
        return None

    try:
        timestamp = datetime.now(tz=timezone.utc).isoformat(timespec="seconds").replace(":", "-")
        archived_name = f"{agent_id}-archived-{timestamp}"
        archived_dir = agent_dir.parent / archived_name

        agent_dir.rename(archived_dir)
        # Remove from config
        _remove_agent_from_config(agent_id)
        return str(archived_dir)
    except Exception:
        return None


def purge_agent(agent_id: str) -> bool:
    """
    Completely removes an agent directory including all sessions and state.
    Also removes it from openclaw.json agents.list.
    This is destructive and should require user confirmation.
    Returns True if successful, False if not found or error.
    """
    agent_dir = Path.home() / ".openclaw" / "agents" / agent_id

    if not agent_dir.exists():
        return False

    try:
        shutil.rmtree(agent_dir)
        # Remove from config
        _remove_agent_from_config(agent_id)
        return True
    except Exception:
        return False


def _remove_agent_from_config(agent_id: str) -> bool:
    """
    Removes an agent from openclaw.json agents.list.
    Returns True if successful, False otherwise.
    """
    config_path = Path.home() / ".openclaw" / "openclaw.json"
    if not config_path.exists():
        return False

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))

        if "agents" not in data or "list" not in data["agents"]:
            return False

        # Remove agent from list
        data["agents"]["list"] = [a for a in data["agents"]["list"] if a.get("id") != agent_id]

        # Write back to config
        config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def sync_existing_agents_to_config() -> list[str]:
    """
    Scans ~/.openclaw/agents/ for agents with IDENTITY.md files and ensures
    they are registered in openclaw.json. This is useful for catching agents
    that were created but not yet registered.

    Returns list of newly registered agent IDs.
    """
    registered = []
    agents_dir = Path.home() / ".openclaw" / "agents"

    if not agents_dir.exists():
        return registered

    # Find all agents with IDENTITY.md and detect workspace from config if available
    agent_ids = []
    workspace_path = None
    config_path = Path.home() / ".openclaw" / "config.json"

    # Try to read the workspace path from Mission Control's config
    if config_path.exists():
        try:
            config_data = json.loads(config_path.read_text(encoding="utf-8"))
            workspace_path = config_data.get("workspace") or config_data.get("workspaceDirectory")
        except Exception:
            pass

    for agent_dir in agents_dir.iterdir():
        if agent_dir.is_dir() and (agent_dir / "IDENTITY.md").exists():
            agent_ids.append(agent_dir.name)

    # Register them
    if agent_ids:
        for agent_id in agent_ids:
            # Check if already in config
            openclaw_config = Path.home() / ".openclaw" / "openclaw.json"
            if openclaw_config.exists():
                try:
                    data = json.loads(openclaw_config.read_text(encoding="utf-8"))
                    existing = [a for a in data.get("agents", {}).get("list", []) if a.get("id") == agent_id]
                    if not existing:
                        registered.append(agent_id)
                except Exception:
                    pass

        _register_agents_in_config(agent_ids, workspace_path)

    return registered
