"""
Reads workspace files and infers agent and project state.
No AI inference — all interpretation is based on file paths and content patterns.
"""
import re
from datetime import datetime, timezone
from pathlib import Path


TICKET_STATES = [
    "proposed", "ready", "in-progress", "blocked",
    "qa-failed", "fixed", "passed", "released"
]

# File path patterns → human-readable activity messages
ACTIVITY_PATTERNS = [
    (r"tickets/open/BUG-\d+", "QA opened bug ticket"),
    (r"tickets/open/FEAT-\d+", "PM added feature request"),
    (r"tickets/open/QUESTION-\d+", "Agent raised a question"),
    (r"tickets/closed/", "Ticket closed"),
    (r"builds/build_v[\d.]+", "Builder produced a new build"),
    (r"builds/", "Build directory updated"),
    (r"implementation-plan\.md", "Architect wrote implementation plan"),
    (r"architecture\.md", "Architect updated architecture doc"),
    (r"spec\.md", "PM updated product specification"),
    (r"milestones\.md", "PM updated milestones"),
    (r"status\.md", "Status file updated"),
    (r"overnight-report\.md", "Morning report is ready"),
    (r"human_tasks\.md", "Human action required"),
    (r"AGENTS\.md", "Agent roster updated"),
    (r"\.claude/settings\.json", "SECURITY: settings.json was modified"),
]


def infer_activity_message(file_path: str) -> str:
    for pattern, message in ACTIVITY_PATTERNS:
        if re.search(pattern, file_path.replace("\\", "/")):
            return message
    return f"File updated: {Path(file_path).name}"


def read_active_project(workspace_root: Path) -> dict | None:
    active_file = workspace_root / "active-project.md"
    if not active_file.exists():
        return None
    content = active_file.read_text(encoding="utf-8")
    name = None
    path = None
    for line in content.splitlines():
        if line.startswith("Active Project:"):
            name = line.split(":", 1)[1].strip()
        if line.startswith("Project Path:"):
            path = line.split(":", 1)[1].strip()
    if name:
        return {"name": name, "path": path or f"projects/{name}"}
    return None


def read_project_status(workspace_root: Path, project_path: str) -> dict:
    status_file = workspace_root / project_path / "status.md"
    result = {
        "name": Path(project_path).name,
        "milestone_current": None,
        "milestone_total": None,
        "last_updated": None,
        "overnight_enabled": False,
        "report_available": False,
    }

    if not status_file.exists():
        return result

    content = status_file.read_text(encoding="utf-8")
    result["last_updated"] = datetime.fromtimestamp(
        status_file.stat().st_mtime, tz=timezone.utc
    ).isoformat()

    # Parse "Active Milestone:" line
    for line in content.splitlines():
        m = re.search(r"Active Milestone:\s*Milestone\s*(\d+)", line, re.IGNORECASE)
        if m:
            result["milestone_current"] = int(m.group(1))

    # Count milestone rows in table
    milestone_rows = re.findall(r"^\|\s*\d+\s*[—-]", content, re.MULTILINE)
    if milestone_rows:
        result["milestone_total"] = len(milestone_rows)

    # Check overnight
    for line in content.splitlines():
        if "Enabled: YES" in line and "Overnight" in content:
            result["overnight_enabled"] = True

    # Check for morning report
    report = workspace_root / project_path / "overnight-report.md"
    result["report_available"] = report.exists()

    return result


def read_tickets(workspace_root: Path, project_path: str) -> dict:
    counts = {s: 0 for s in TICKET_STATES}

    tickets_open = workspace_root / project_path / "tickets" / "open"
    tickets_closed = workspace_root / project_path / "tickets" / "closed"

    def count_by_status(directory: Path) -> None:
        if not directory.exists():
            return
        for f in directory.glob("*.md"):
            content = f.read_text(encoding="utf-8", errors="ignore")
            for line in content.splitlines():
                if line.startswith("**Status:**"):
                    status = line.split(":", 1)[1].strip().lower()
                    if status in counts:
                        counts[status] += 1
                    break

    count_by_status(tickets_open)
    count_by_status(tickets_closed)
    return counts


def read_agent_activity(workspace_root: Path, agents: list[str]) -> dict:
    """
    Infers agent status based on last-modified timestamps of workspace files.
    Returns {role: {status, character, last_active}}
    """
    now = datetime.now(tz=timezone.utc).timestamp()
    result = {}

    # Read AGENTS.md to extract character names
    characters = parse_agent_characters(workspace_root)

    for role in agents:
        # Check relevant output files for this agent
        last_mod = _find_last_modified(workspace_root, role)

        if last_mod is None:
            status = "unknown"
            last_active = None
        else:
            age_minutes = (now - last_mod) / 60
            if age_minutes < 5:
                status = "active"
            elif age_minutes < 30:
                status = "idle"
            elif age_minutes < 120:
                status = "idle"
            else:
                status = "unknown"
            last_active = datetime.fromtimestamp(last_mod, tz=timezone.utc).isoformat()

        # Launcher paths
        launcher_sh  = str(workspace_root / "launchers" / f"run-{role}.sh")
        launcher_bat = str(workspace_root / "launchers" / f"run-{role}.bat")

        # OpenClaw registration check: ~/.openclaw/agents/{role}/IDENTITY.md
        openclaw_agents = Path.home() / ".openclaw" / "agents"
        identity_path   = openclaw_agents / role / "IDENTITY.md"
        openclaw_registered = identity_path.exists()
        openclaw_dir    = str(openclaw_agents / role)

        # Model — read from launcher script if it exists
        model = "—"
        sh = Path(launcher_sh)
        if sh.exists():
            for line in sh.read_text(encoding="utf-8", errors="ignore").splitlines():
                m = re.search(r"--model\s+(\S+)", line)
                if m:
                    model = m.group(1)
                    break

        result[role] = {
            "role": role,
            "character": characters.get(role, "—"),
            "status": status,
            "last_active": last_active,
            "workspace_path": str(workspace_root),
            "launcher_sh": launcher_sh,
            "launcher_bat": launcher_bat,
            "openclaw_dir": openclaw_dir,
            "openclaw_registered": openclaw_registered,
            "model": model,
        }

    return result


def _find_last_modified(workspace_root: Path, role: str) -> float | None:
    """Find the most recent file modification timestamp relevant to a given role."""
    role_file_patterns = {
        "pm": ["**/spec.md", "**/milestones.md", "**/status.md", "**/overnight-report.md"],
        "architect": ["**/implementation-plan.md", "**/architecture.md"],
        "builder": ["**/builds/**", "**/*.py", "**/*.js", "**/*.ts", "**/*.go", "**/*.rs"],
        "qa": ["**/tickets/open/BUG-*.md", "**/tickets/**/*.md"],
        "security": ["**/security-review.md"],
        "devops": ["**/release-notes.md", "**/builds/**"],
        "ux": ["**/ui-wireframes.md", "**/design-system.md"],
        "research": ["**/research.md", "**/technical-options.md"],
    }

    patterns = role_file_patterns.get(role, [])
    latest = None

    for pattern in patterns:
        for f in workspace_root.glob(pattern):
            if f.is_file():
                mtime = f.stat().st_mtime
                if latest is None or mtime > latest:
                    latest = mtime

    return latest


def parse_agent_characters(workspace_root: Path) -> dict:
    """Parses AGENTS.md to extract {role_key: character_name} mapping."""
    agents_file = workspace_root / "AGENTS.md"
    if not agents_file.exists():
        return {}

    content = agents_file.read_text(encoding="utf-8", errors="ignore")
    characters = {}

    role_map = {
        "Project Manager": "pm",
        "System Architect": "architect",
        "Builder / Developer": "builder",
        "QA / Test Engineer": "qa",
        "Security Engineer": "security",
        "DevOps / Release": "devops",
        "UX / Documentation": "ux",
        "Research Agent": "research",
    }

    current_role = None
    for line in content.splitlines():
        for label, key in role_map.items():
            if f"### {label}" in line:
                current_role = key
                break
        if current_role and line.startswith("**Character:**"):
            char = line.split(":", 1)[1].strip()
            characters[current_role] = char
            current_role = None

    return characters
