"""
Deploys workspace and project templates from the bundled corpus
to the target directory, substituting placeholders.
"""
import json
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from openclaw.platform_utils import get_corpus_dir


AGENT_ROLES_MINIMAL = ["pm", "architect", "builder", "qa"]
AGENT_ROLES_FULL = ["pm", "architect", "builder", "qa", "security", "devops", "ux", "research"]

# Maps each role to its capability group for model assignment.
# The installer collects one model per group from configured providers.
ROLE_GROUP = {
    "pm": "strategic",
    "architect": "strategic",
    "security": "strategic",
    "builder": "implementation",
    "qa": "implementation",
    "devops": "support",
    "ux": "support",
    "research": "support",
}

ROLE_LABELS = {
    "pm": "Project Manager",
    "architect": "System Architect",
    "builder": "Builder / Developer",
    "qa": "QA / Test Engineer",
    "security": "Security Engineer",
    "devops": "DevOps / Release",
    "ux": "UX / Documentation",
    "research": "Research Agent",
}

ROLE_RESPONSIBILITIES = {
    "pm": [
        "Communicate with the human operator",
        "Write and maintain product specifications",
        "Create and manage milestones",
        "Coordinate handoffs between agents",
        "Generate progress reports",
        "Run overnight development loops",
    ],
    "architect": [
        "Design system architecture",
        "Choose frameworks and technology stack",
        "Define data models and interfaces",
        "Convert specs into implementation plans",
    ],
    "builder": [
        "Implement code from implementation plans",
        "Create milestone builds",
        "Fix bugs from QA tickets",
        "Update ticket statuses",
    ],
    "qa": [
        "Validate builds against acceptance criteria",
        "Write and run tests",
        "Detect regressions",
        "Create bug tickets",
    ],
    "security": [
        "Audit code for vulnerabilities",
        "Apply OWASP security guidelines",
        "Review for prompt injection surfaces",
        "Flag credential exposure or excessive permissions",
    ],
    "devops": [
        "Package build artifacts",
        "Prepare deployment configurations",
        "Manage environment setup",
        "Write release notes",
    ],
    "ux": [
        "Write UI text and microcopy",
        "Define user flows",
        "Document the product",
        "Improve usability and accessibility",
    ],
    "research": [
        "Evaluate technologies and frameworks",
        "Research APIs and libraries",
        "Identify risks and constraints",
        "Propose implementation options",
    ],
}

ROLE_OUTPUTS = {
    "pm": ["spec.md", "milestones.md", "status.md", "overnight-report.md"],
    "architect": ["implementation-plan.md", "architecture.md"],
    "builder": ["source code", "build artifacts", "commit notes"],
    "qa": ["bug tickets", "test reports"],
    "security": ["security-review.md", "vulnerability tickets"],
    "devops": ["build packages", "deployment scripts", "release notes"],
    "ux": ["ui-wireframes.md", "design-system.md", "product docs"],
    "research": ["technical-options.md", "research.md"],
}


def load_character_theme(theme: str) -> dict:
    corpus = get_corpus_dir()
    theme_file = corpus / "characters" / f"{theme}.json"
    if not theme_file.exists():
        theme_file = corpus / "characters" / "historical.json"
    with open(theme_file, encoding="utf-8") as f:
        return json.load(f)


def build_agent_list(roles: list[str], theme_data: dict, model_map: dict) -> list[dict]:
    agents = []
    for role in roles:
        role_chars = theme_data.get("roles", {}).get(role, {})
        group = ROLE_GROUP.get(role, "implementation")
        model = model_map.get(group, "claude-sonnet-4-6")
        agents.append({
            "role": role,
            "role_label": ROLE_LABELS.get(role, role.upper()),
            "character": role_chars.get("character", "—"),
            "philosophy": role_chars.get("philosophy", ""),
            "decision_style": role_chars.get("decision_style", ""),
            "responsibilities": ROLE_RESPONSIBILITIES.get(role, []),
            "outputs": ROLE_OUTPUTS.get(role, []),
            "model": model,
        })
    return agents


def deploy_workspace_files(
    workspace_root: Path,
    theme: str,
    team_size: int,
    operator_name: str = "Operator",
    default_project: str = "example-app",
    model_map: dict | None = None,
) -> tuple[list[str], list[dict]]:
    """
    Renders and writes all workspace-level template files.
    Returns (list of file paths written, agent list) — agent list is needed
    for generating per-role launcher scripts.
    model_map: {"strategic": "<model-id>", "implementation": "<model-id>", "support": "<model-id>"}
    """
    if model_map is None:
        model_map = {
            "strategic": "claude-sonnet-4-6",
            "implementation": "claude-sonnet-4-6",
            "support": "claude-sonnet-4-6",
        }

    corpus = get_corpus_dir()
    env = Environment(
        loader=FileSystemLoader(str(corpus / "workspace")),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    theme_data = load_character_theme(theme)
    roles = AGENT_ROLES_FULL if team_size == 8 else AGENT_ROLES_MINIMAL
    agents = build_agent_list(roles, theme_data, model_map)

    context = {
        "team_name": theme_data.get("label", "Development"),
        "team_size": team_size,
        "theme_label": theme_data.get("label", "Custom"),
        "agents": agents,
        "install_date": date.today().isoformat(),
        "operator_name": operator_name,
        "workspace_path": str(workspace_root),
        "default_project": default_project,
    }

    written = []
    templates = {
        "AGENTS.md.template": workspace_root / "AGENTS.md",
        "SOUL.md.template":   workspace_root / "SOUL.md",
        "TOOLS.md.template":  workspace_root / "TOOLS.md",
        "USER.md.template":   workspace_root / "USER.md",
        "MEMORY.md.template": workspace_root / "MEMORY.md",
    }

    for template_name, dest_path in templates.items():
        tmpl = env.get_template(template_name)
        rendered = tmpl.render(**context)
        dest_path.write_text(rendered, encoding="utf-8")
        written.append(str(dest_path))

    return written, agents


def deploy_project_files(
    project_path: Path,
    project_name: str,
    update_mode: bool = False,
) -> list[str]:
    """
    Renders and writes project-level template files (spec, milestones, status).
    Returns list of file paths written.
    """
    corpus = get_corpus_dir()
    env = Environment(
        loader=FileSystemLoader(str(corpus / "project")),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    context = {
        "project_name": project_name,
        "install_date": date.today().isoformat(),
    }

    written = []
    templates = {
        "spec.md.template":              project_path / "spec.md",
        "milestones.md.template":        project_path / "milestones.md",
        "status.md.template":            project_path / "status.md",
        "AGENT-TODO.md.template":        project_path / "AGENT-TODO.md",
        "AGENT-SESSION-LOG.md.template": project_path / "AGENT-SESSION-LOG.md",
    }

    for template_name, dest_path in templates.items():
        if update_mode and dest_path.exists():
            # Protect user data (session logs, TODO lists) from being overwritten
            continue
        tmpl = env.get_template(template_name)
        rendered = tmpl.render(**context)
        dest_path.write_text(rendered, encoding="utf-8")
        written.append(str(dest_path))

    return written
