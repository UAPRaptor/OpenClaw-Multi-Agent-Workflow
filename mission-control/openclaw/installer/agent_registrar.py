"""
Registers installed agents with OpenClaw's native agent directory so that
each agent appears as a distinct entry in OpenClaw's Agents list.

OpenClaw agent directory layout:
  ~/.openclaw/agents/{role}/
    IDENTITY.md     — who this agent is (character, role, philosophy)

OpenClaw loads this file when the launcher runs:
  openclaw start --agent {role} --model {model}
"""
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from openclaw.platform_utils import get_corpus_dir


def register_openclaw_agents(agents: list[dict]) -> list[str]:
    """
    Creates per-agent directories at ~/.openclaw/agents/{role}/ and renders
    an IDENTITY.md file in each one.

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

    for agent in agents:
        role = agent["role"]
        agent_dir = base_dir / role
        agent_dir.mkdir(exist_ok=True)
        created.append(str(agent_dir))

        context = {
            **agent,
            "install_date": date.today().isoformat(),
        }
        rendered = tmpl.render(**context)
        identity_path = agent_dir / "IDENTITY.md"
        identity_path.write_text(rendered, encoding="utf-8")
        created.append(str(identity_path))

    return created
