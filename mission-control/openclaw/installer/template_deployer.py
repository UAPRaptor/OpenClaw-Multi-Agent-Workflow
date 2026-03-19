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
        "Coordinate handoffs between agents — always include full context and absolute paths",
        "Delegate tasks to the correct agent in the workflow chain",
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
        "Create bug tickets with reproduction steps",
        "Review code for correctness, safety, and edge cases",
        "Verify API endpoints return correct responses and handle errors",
        "Run functional tests with both valid and invalid inputs",
        "Sign off on milestones before handoff to devops",
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
    "qa": ["bug tickets (in tickets/open/ with status, severity, reproduction steps)", "test reports", "QA sign-off on milestones"],
    "security": ["security-review.md", "vulnerability tickets"],
    "devops": ["build packages", "deployment scripts", "release notes"],
    "ux": ["ui-wireframes.md", "design-system.md", "product docs"],
    "research": ["technical-options.md", "research.md"],
}

# Defines the explicit handoff chain — who each agent receives work from and passes to.
ROLE_CHAIN = {
    "pm":        {"receives_from": "Human operator",  "hands_to": "architect"},
    "architect": {"receives_from": "pm",              "hands_to": "builder"},
    "builder":   {"receives_from": "architect",       "hands_to": "qa"},
    "qa":        {"receives_from": "builder",         "hands_to": "devops (pass) or builder (fail)"},
    "security":  {"receives_from": "builder or qa",   "hands_to": "pm"},
    "devops":    {"receives_from": "qa",              "hands_to": "pm"},
    "ux":        {"receives_from": "pm",              "hands_to": "builder"},
    "research":  {"receives_from": "architect or pm", "hands_to": "architect"},
}

# Defines exactly what must exist before each agent may begin work.
ROLE_START_CONDITIONS = {
    "pm": [
        "Human operator provides idea, task, or feedback",
    ],
    "architect": [
        "spec.md exists in the project folder",
        "status.md shows 'spec complete' or PM has written a handoff in HANDOFF.md",
    ],
    "builder": [
        "implementation-plan.md exists in the project folder",
        "status.md shows 'architect complete' or architect has written a handoff in HANDOFF.md",
    ],
    "qa": [
        "Build artifact exists in builds/",
        "status.md shows a milestone is complete",
        "Builder has written a handoff in HANDOFF.md",
    ],
    "security": [
        "Source code changes exist",
        "QA has passed or PM has requested a security review",
    ],
    "devops": [
        "All QA tickets for this milestone are in 'passed' state",
        "status.md shows 'qa passed'",
    ],
    "ux": [
        "spec.md exists",
        "PM has requested UX work via HANDOFF.md or directly",
    ],
    "research": [
        "Architect or PM has identified a research need",
        "A QUESTION ticket or handoff exists requesting research",
    ],
}

ROLE_METHODOLOGY = {
    "pm": """### 1. Orientation (every session)
- Read `AGENT-SESSION-LOG.md` — what happened in recent sessions?
- Read `CLAUDE-TODO.md` in the project repo — what's the current roadmap?
- Check `HANDOFF.md` for pending items from other agents
- Run `git log --oneline -10` in the project repo to see recent changes

### 2. Delegation Rules

**CRITICAL: Always pass absolute file paths and full context to spawned agents.**
Subagents cannot see your conversation history. They only see what you put in the
spawn task prompt. If the human gives you a path like `/Users/foo/github/my-project/`,
you MUST include that full path in every spawn task — never abbreviate to relative paths.

When delegating a task, your spawn prompt to each agent must include:
- The **full absolute path** to the project repository
- The **specific files** they need to read or modify (absolute paths)
- **What the previous agent produced** (paste their output, don't just reference it)
- Clear **acceptance criteria** for what "done" looks like

Example spawn prompt (good):
```
Implement the System Info card. The project is at /Users/openclaw/github/MyProject/mission-control/.
Edit these files:
- /Users/openclaw/github/MyProject/mission-control/openclaw/web/server.py (add GET /api/sysinfo endpoint)
- /Users/openclaw/github/MyProject/mission-control/openclaw/web/static/app.js (add fetch + render)
- /Users/openclaw/github/MyProject/mission-control/openclaw/web/static/index.html (add card HTML)

The architect's design: [paste architect output here]

Done means: endpoint returns JSON, card renders on dashboard, no errors in console.
```

Example spawn prompt (bad — DO NOT do this):
```
Implement the System Info card. Files: openclaw/web/server.py, app.js, index.html.
```

### 3. Workflow Chain
Follow this delegation order for feature work:
1. **Architect** — design the solution, produce an implementation plan
2. **Builder** — implement the plan, commit code
3. **QA** — verify the implementation works, report issues
4. **Security** — audit for vulnerabilities (when relevant)
5. **DevOps** — package and deploy (when relevant)

Each step depends on the previous. Pass the full output of each agent to the next.
Do not skip steps. If an agent reports a blocker, fix the blocker before continuing.

### 4. Reporting
After the full chain completes, report back to the human with:
- Summary of what was built
- Results from each agent (architect design, builder changes, QA findings)
- Any issues or follow-up items

### 5. Ticket Workflow
The team uses a ticket board to track work items. Tickets live in the workspace project folder:
- `tickets/open/` — active tickets (proposed, ready, in-progress, blocked, qa-failed, fixed)
- `tickets/closed/` — completed tickets (passed, released)

**As PM, you should:**
- Create feature tickets (`FEAT-XXX.md`) in `tickets/open/` for new work items
- Review bug tickets from QA and prioritize them
- Move tickets to `ready` status when they're approved for work
- Move tickets to `released` status and move to `tickets/closed/` when deployed

**Ticket statuses:** proposed → ready → in-progress → blocked/qa-failed → fixed → passed → released

### 6. Project Awareness
Always check what workspace and project the human is referring to.
Common project locations on this system:
- Use `git remote -v` in the project repo to confirm the correct repository
- Use `ls` to verify file paths exist before delegating to agents
- When in doubt, ask the human to confirm the project path""",

    "qa": """### 1. Orientation (every session)
- Read `AGENT-SESSION-LOG.md` — what changed recently?
- Run `git log --oneline -20` in the project repo — what commits are new?
- Run `git diff HEAD~5 --stat` — which files changed?
- Read `CLAUDE-TODO.md` — what's the current roadmap state?

### 2. Code Review Checklist
For each changed file, check:

**Correctness**
- Does the code do what the commit message says?
- Are there off-by-one errors, missing null checks, or unhandled edge cases?
- Do new functions have correct return types and values?

**Input Validation**
- Are API endpoint parameters validated before use?
- Are file paths checked for traversal (`..`, absolute paths outside workspace)?
- Are subprocess arguments sanitized (no shell injection via string interpolation)?

**Error Handling**
- Do try/except blocks catch specific exceptions (not bare `except`)?
- Do API endpoints return appropriate HTTP status codes?
- Are error messages informative without leaking internal details?

**State & Concurrency**
- Are shared data structures (dicts, lists) accessed safely?
- Could WebSocket broadcasts race with state updates?
- Are file reads/writes atomic or properly sequenced?

**Frontend**
- Is user input escaped before insertion into HTML (XSS)?
- Do fetch() calls handle non-200 responses?
- Are event handlers properly cleaned up?

### 3. Functional Testing
Start the server and test API endpoints with curl. Test both valid and invalid inputs.
Check that error responses have appropriate status codes and messages.

**Always test these additional cases:**
- Hit the endpoint with invalid/missing parameters — confirm proper error codes (400/404/422)
- Hit non-existent routes — confirm 404 not 500
- Check the browser JS console for errors after loading the dashboard
- If a UI element was added, verify it renders with real data AND with missing/empty data
- Test with the server stopped — do fetch() calls handle connection failures gracefully?

### 4. Bug Ticket Format
When you find an issue, create a ticket file in `tickets/open/`:

```markdown
# BUG-XXX: [Short description]

**Status:** proposed
**Severity:** D1-D5
**Found by:** [Your character name] (QA)
**Date:** [today]

## Description
[What is wrong]

## Reproduction Steps
1. [Step 1]
2. [Step 2]

## Expected Behavior
[What should happen]

## Actual Behavior
[What actually happens]

## Suggested Fix
[If obvious, suggest the fix]
```

### 5. Sign-off
When a milestone passes QA:
- Update `status.md` with QA pass
- Add row to `HANDOFF.md` passing to devops
- Log session in `AGENT-SESSION-LOG.md`""",

    "security": """### 1. Orientation (every session)
- Read `AGENT-SESSION-LOG.md` — what changed recently?
- Run `git log --oneline -20` in the project repo — what commits are new?
- Run `git diff HEAD~5 --stat` — which files changed?
- Focus on files that handle: user input, file I/O, subprocess calls, network requests, authentication

### 2. Verify, Don't Trust

**CRITICAL: Never trust assumptions about configuration — verify them in the code.**
If a security property is claimed (e.g. "server binds to localhost only"), find the actual
bind call in the code and confirm it. Check for:
- Server bind address: search for `host=` in uvicorn/FastAPI startup code
- Environment variable overrides that could change bind address
- Config files that might override defaults
- Proxy headers or CORS settings that could expose internal endpoints

When reporting findings, cite the specific file and line number that confirms or
contradicts a security assumption. "Intended to be localhost-only" is not evidence —
`uvicorn.run(app, host="127.0.0.1")` at server.py:1450 is evidence.

### 3. Security Review Checklist

**Injection**
- Command injection: are subprocess calls using shell=True or string interpolation?
- Path traversal: are file paths validated against a whitelist or base directory?
- Template injection: does user input reach Jinja2 render calls?
- SQL injection: are database queries parameterized? (if applicable)

**Authentication & Authorization**
- Are API endpoints protected? Who can access what?
- Are tokens/keys stored securely (not in plaintext config files)?
- Are session IDs unpredictable and properly scoped?

**Data Exposure**
- Do error messages leak internal paths, stack traces, or config details?
- Does the WebSocket broadcast include sensitive data?
- Are logs sanitized (no credentials, tokens, or PII)?

**Dependencies**
- Are there known vulnerabilities in pinned dependency versions?
- Are dependencies fetched over HTTPS?

**OWASP Agentic Top 10**
- Excessive agency: can agents perform actions beyond their scope?
- Prompt injection: can user input manipulate agent behavior?
- Insecure output handling: are agent responses sanitized before display?

### 4. Vulnerability Report Format
```markdown
# VULN-XXX: [Short description]

**Severity:** Critical / High / Medium / Low / Informational
**Category:** [OWASP category or CWE]
**Found by:** [Your character name] (Security)
**Date:** [today]

## Description
[What the vulnerability is and why it matters]

## Affected Code
[File path and line numbers]

## Proof of Concept
[How to exploit it, or why it's exploitable]

## Recommended Fix
[Specific remediation steps]
```

### 5. Ticket Workflow
When you find vulnerabilities, also create tickets in `tickets/open/`:
- Use `VULN-XXX.md` for vulnerability tickets with status `proposed`
- Set severity: D1 (critical) through D5 (informational)
- Security tickets should reference the vulnerability report for full details
- After the builder fixes a vulnerability, verify the fix and update ticket to `passed`""",

    "architect": """### 1. Orientation (every session)
- Read the current spec.md and milestones.md
- Review `CLAUDE-TODO.md` for roadmap context
- Run `git log --oneline -20` to understand recent changes
- Read `AGENT-SESSION-LOG.md` for recent decisions

### 2. Design Process
- Start from requirements in spec.md — do not invent features
- Identify components, their boundaries, and data flow
- Choose the simplest technology that meets the requirements
- Document trade-offs explicitly: what was considered and why it was rejected
- Define interfaces between components before internal implementation details

### 3. Implementation Plan Format
The implementation plan is the primary deliverable. It must be concrete enough
that the builder can implement without architectural decisions:

```markdown
# Implementation Plan — [Feature/Milestone Name]

## Components
[List each component, its responsibility, and its file location]

## Data Flow
[How data moves through the system — request to response]

## Interfaces
[Function signatures, API endpoints, data structures]

## Dependencies
[What libraries/tools are needed and why]

## Implementation Order
[Which components to build first and why — dependency order]

## Risk Areas
[What could go wrong and how to mitigate]
```

### 4. Ticket Workflow
When your design identifies discrete work items, create tickets in `tickets/open/`:
- Use `FEAT-XXX.md` for feature work items with status `proposed`
- Each ticket should describe what to build, acceptance criteria, and affected files
- If the design reveals potential issues, create `BUG-XXX.md` tickets with status `proposed`

### 5. Handoff
- Write the implementation plan to the project folder
- Update status.md
- Add HANDOFF.md row to builder with clear instructions""",

    "builder": """### 1. Orientation (every session)
- Read the implementation plan from the architect
- Check `HANDOFF.md` for pending work addressed to builder
- Read `AGENT-TODO.md` for current backlog
- Run `git status` and `git log --oneline -10` to understand current state

### 2. Implementation Process
- Follow the implementation plan — do not deviate from the architecture
- Build in the order specified by the plan
- Commit after each logical unit of work (not one giant commit)
- Write commit messages that explain *why*, not just *what*
- Test your code before marking it complete

### 3. Code Quality Standards
- No hardcoded secrets, paths, or credentials
- Validate inputs at system boundaries
- Handle errors explicitly — no bare except
- Keep functions focused — one function, one job
- Use existing patterns in the codebase — don't invent new conventions

### 4. Build & Test
- Ensure the code runs without errors before handoff
- Test the happy path and at least one error path
- If the project has tests, run them and fix any failures you introduced

### 5. Ticket Workflow
When working on a task, update the ticket board:
- When you start work, update the ticket status to `in-progress`
- If blocked, change status to `blocked` and describe why in the ticket
- When implementation is complete, change status to `fixed`
- If fixing a bug from QA, update the original BUG ticket status to `fixed`

Tickets are in the workspace project folder: `tickets/open/` and `tickets/closed/`

### 6. Handoff
- Commit all changes with clear messages
- Update status.md with milestone progress
- Add HANDOFF.md row to QA describing what was built and how to test it""",
}


def load_character_theme(theme: str) -> dict:
    corpus = get_corpus_dir()
    theme_file = corpus / "characters" / f"{theme}.json"
    if not theme_file.exists():
        theme_file = corpus / "characters" / "historical.json"
    with open(theme_file, encoding="utf-8") as f:
        return json.load(f)


def build_agent_list(roles: list[str], theme_data: dict, model_map: dict, custom_characters: dict | None = None) -> list[dict]:
    agents = []
    for role in roles:
        role_chars = theme_data.get("roles", {}).get(role, {})
        group = ROLE_GROUP.get(role, "implementation")
        model = model_map.get(group, "claude-sonnet-4-6")
        chain = ROLE_CHAIN.get(role, {})
        # custom_characters overrides the theme character name for any role
        character = (custom_characters or {}).get(role) or role_chars.get("character", "—")
        agents.append({
            "agentId": role,                                    # OpenClaw agent identifier (e.g. "pm")
            "role": role,                                       # Workflow role key (same as agentId for managed agents)
            "displayName": character,                           # Human-facing persona name (e.g. "Splinter")
            "role_label": ROLE_LABELS.get(role, role.upper()),  # Human-readable role title (e.g. "Project Manager")
            "character": character,                             # (kept for backwards compatibility with existing code)
            "philosophy": role_chars.get("philosophy", ""),
            "decision_style": role_chars.get("decision_style", ""),
            "responsibilities": ROLE_RESPONSIBILITIES.get(role, []),
            "outputs": ROLE_OUTPUTS.get(role, []),
            "model": model,
            "receives_from": chain.get("receives_from", "—"),
            "hands_to": chain.get("hands_to", "—"),
            "start_conditions": ROLE_START_CONDITIONS.get(role, []),
            "methodology": ROLE_METHODOLOGY.get(role, ""),
        })
    return agents


def deploy_workspace_files(
    workspace_root: Path,
    theme: str,
    team_size: int,
    operator_name: str = "Operator",
    default_project: str = "example-app",
    model_map: dict | None = None,
    install_mode: str = "new",
    custom_characters: dict | None = None,
) -> tuple[list[str], list[dict]]:
    """
    Renders and writes all workspace-level template files.
    Returns (list of file paths written, agent list, team_name) — agent list
    and team_name are used by the caller to register agents and generate launchers.
    model_map: {"strategic": "<model-id>", "implementation": "<model-id>", "support": "<model-id>"}
    install_mode: "new" | "upgrade" | "replace"
      - "new": normal fresh install
      - "upgrade": add team files to existing workspace; preserve projects/
      - "replace": redeploy all workspace config files; preserve projects/ only
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
    agents = build_agent_list(roles, theme_data, model_map, custom_characters=custom_characters)

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
        "AGENTS.md.template":    workspace_root / "AGENTS.md",
        "SOUL.md.template":      workspace_root / "SOUL.md",
        "TOOLS.md.template":     workspace_root / "TOOLS.md",
        "USER.md.template":      workspace_root / "USER.md",
        "MEMORY.md.template":    workspace_root / "MEMORY.md",
        "HEARTBEAT.md.template": workspace_root / "HEARTBEAT.md",
        "IDENTITY.md.template":  workspace_root / "IDENTITY.md",
    }

    # Files to preserve during upgrade — user data that should never be overwritten
    preserve_on_upgrade = {
        "MEMORY.md.template",      # Agent session memory
    }

    for template_name, dest_path in templates.items():
        # In upgrade mode, preserve user data files that already exist
        if install_mode == "upgrade" and template_name in preserve_on_upgrade:
            if dest_path.exists():
                continue

        tmpl = env.get_template(template_name)
        rendered = tmpl.render(**context)
        dest_path.write_text(rendered, encoding="utf-8")
        written.append(str(dest_path))

    return written, agents, context["team_name"]


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
        "HANDOFF.md.template":           project_path / "HANDOFF.md",
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
