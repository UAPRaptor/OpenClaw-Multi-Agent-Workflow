"""
Registers installed agents with OpenClaw's native agent directory so that
each agent appears as a distinct entry in OpenClaw's Agents list and can be
chatted with directly from the OpenClaw UI.

OpenClaw agent directory layout:
  ~/.openclaw/agents/main/{role}/
    models.json     — specifies which model this agent uses
"""
import json
from pathlib import Path


def register_openclaw_agents(agents: list[dict]) -> list[str]:
    """
    Creates per-agent directories at ~/.openclaw/agents/main/{role}/
    and writes a models.json for each one.

    This registration makes each agent visible in OpenClaw's native
    Agents list. OpenClaw reads the agent's identity (character, role,
    instructions) from the CLAUDE.md in the per-agent workspace directory
    when the launcher script starts a session there.

    Returns list of created paths (for display in the installer UI).
    """
    base_dir = Path.home() / ".openclaw" / "agents" / "main"
    base_dir.mkdir(parents=True, exist_ok=True)
    created = []

    for agent in agents:
        role = agent["role"]
        character = agent.get("character", role.upper())
        model = agent.get("model", "claude-sonnet-4-6")
        role_label = agent.get("role_label", role)

        agent_dir = base_dir / role
        agent_dir.mkdir(exist_ok=True)
        created.append(str(agent_dir))

        models_path = agent_dir / "models.json"
        models_path.write_text(
            json.dumps({"model": model, "name": f"{character} ({role_label})"}, indent=2),
            encoding="utf-8",
        )
        created.append(str(models_path))

    return created
