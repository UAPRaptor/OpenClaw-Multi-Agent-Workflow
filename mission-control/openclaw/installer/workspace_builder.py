"""
Creates the OpenClaw workspace directory structure on the target machine.
"""
import os
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class WorkspaceLayout:
    """Describes all directories and files that will be created."""
    root: Path
    directories: list[Path] = field(default_factory=list)
    files: list[tuple[Path, str]] = field(default_factory=list)  # (path, content)


def build_layout(root: Path, default_project: str = "example-app") -> WorkspaceLayout:
    """
    Returns the full workspace layout (directories + placeholder files)
    without writing anything to disk.
    """
    layout = WorkspaceLayout(root=root)

    # Top-level workspace directories
    layout.directories += [
        root,
        root / "projects",
        root / "projects" / default_project,
        root / "projects" / default_project / "tickets",
        root / "projects" / default_project / "tickets" / "open",
        root / "projects" / default_project / "tickets" / "closed",
        root / "projects" / default_project / "tickets" / "archive",
        root / "projects" / default_project / "builds",
        root / ".claude",
    ]

    # active-project.md
    layout.files.append((
        root / "active-project.md",
        f"Active Project: {default_project}\nProject Path: projects/{default_project}\n"
    ))

    return layout


def create_workspace(layout: WorkspaceLayout) -> list[str]:
    """
    Writes the workspace layout to disk.
    Returns a list of created paths (for display in the installer UI).
    """
    created = []

    for d in layout.directories:
        d.mkdir(parents=True, exist_ok=True)
        created.append(str(d))

    for file_path, content in layout.files:
        file_path.write_text(content, encoding="utf-8")
        created.append(str(file_path))

    return created


def write_agent_launchers(workspace: Path, agents: list[dict]) -> list[str]:
    """
    Generates per-agent launch scripts in workspace/launchers/.
    Each script opens OpenClaw with the role's assigned model.
    Returns list of created file paths.
    """
    launchers_dir = workspace / "launchers"
    launchers_dir.mkdir(exist_ok=True)
    workspace_str = str(workspace)
    written = []

    for agent in agents:
        role = agent["role"]
        label = agent.get("role_label", role)
        character = agent.get("character", role.upper())
        model = agent.get("model", "claude-sonnet-4-6")
        agent_dir_str = str(workspace / "agents" / role)

        # Unix / macOS
        sh_path = launchers_dir / f"run-{role}.sh"
        sh_path.write_text(
            f"#!/bin/bash\n"
            f"# Launch {label} agent ({character})\n"
            f"# Model: {model}\n"
            f'cd "{agent_dir_str}"\n'
            f"openclaw --model {model}\n",
            encoding="utf-8",
        )
        try:
            sh_path.chmod(0o755)
        except OSError:
            pass  # chmod not meaningful on Windows; ignore
        written.append(str(sh_path))

        # Windows
        bat_path = launchers_dir / f"run-{role}.bat"
        bat_path.write_text(
            f"@echo off\n"
            f"REM Launch {label} agent ({character})\n"
            f"REM Model: {model}\n"
            f'cd /d "{agent_dir_str}"\n'
            f"openclaw --model {model}\n",
            encoding="utf-8",
        )
        written.append(str(bat_path))

    return written


def get_file_preview(layout: WorkspaceLayout) -> list[str]:
    """
    Returns a human-readable list of paths that will be created,
    used in the installer step-5 review screen.
    """
    preview = []
    root_str = str(layout.root)

    for d in layout.directories:
        rel = str(d).replace(root_str, "").lstrip("/\\") or "."
        preview.append(f"[dir]  {rel}/")

    for file_path, _ in layout.files:
        rel = str(file_path).replace(root_str, "").lstrip("/\\")
        preview.append(f"[file] {rel}")

    return preview
