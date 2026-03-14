# Additional Training Resources for a Claude Code Agent Operating an OpenClaw Multi-Agent Development Team

---

## OpenClaw Core Documentation and Source

Official GitHub Repository
https://github.com/openclaw/openclaw

OpenClaw Organization Repositories
https://github.com/openclaw

Official Documentation
https://docs.openclaw.ai

OpenClaw Releases
https://github.com/openclaw/openclaw/releases

OpenClaw Issues Tracker
https://github.com/openclaw/openclaw/issues

OpenClaw Discussions
https://github.com/openclaw/openclaw/discussions

---

## Agent Behavior Rules

The system must include a defined behavioral policy layer.

Files used to define agent behavior:

- AGENTS.md
- SOUL.md
- TOOLS.md
- USER.md

These files establish:
- agent responsibilities
- workflow rules
- handoff procedures
- file editing permissions
- ticket handling rules
- night mode rules
- escalation rules

---

## Workspace Project Templates

Provide reusable templates for all project artifacts:

- spec-template.md
- milestones-template.md
- ticket-template.md
- status-template.md
- handoff-template.md
- overnight-report-template.md
- human_tasks-template.md

Templates ensure agents produce consistent artifacts.

---

## Project Structure Template

```
projects/
  app-name/
    spec.md
    milestones.md
    status.md
    tickets/
    builds/
    docs/
    tests/

tickets/
  open/
  closed/
  archive/

builds/
  build_v0.1
  build_v0.2
```

---

## Active Project Control

The system must include a project selection file.

**active-project.md**

Example contents:
```
Active Project: project-name
Project Path: projects/project-name
```

All agents must read active-project.md before performing work.

---

## Specification Format Training

Agents must understand how to produce a complete product specification.

spec.md must contain:
- product overview
- user personas
- core features
- non-functional requirements
- UI expectations
- integration requirements
- technical constraints

---

## Milestone Design Training

Agents must be trained to break projects into milestones.

milestones.md format per milestone:
- Milestone Title
- Goal
- Deliverables
- Dependencies
- Required files
- Acceptance criteria

Milestones must produce runnable builds frequently.

---

## Build Artifact Structure

```
builds/
  build_v0.1
  build_v0.2
  build_v0.3
```

Each build must include:
- build instructions
- version identifier
- change summary

---

## Ticket System Training

Agents must follow a structured ticket workflow.

```
tickets/open/BUG-001.md
tickets/open/FEAT-002.md
```

Ticket template fields:
- Title
- Ticket Type
- Priority
- Description
- Steps to reproduce
- Expected behavior
- Actual behavior
- Assigned agent
- Status

---

## Ticket Status States

Allowed states:
- proposed
- ready
- in-progress
- blocked
- qa-failed
- fixed
- passed
- released

Agents may only modify ticket states within their allowed responsibilities.

---

## Bug Fix Loop Training

QA workflow:

1. Builder completes milestone
2. QA tests build
3. If bug detected:
   - QA creates ticket
   - QA updates status.md
   - QA notifies Builder
4. Builder fixes bug
5. Builder updates ticket
6. QA retests

---

## Handoff Contract Training

Agents must follow a deterministic handoff process.

Each handoff requires:
1. artifact creation
2. status update
3. kickoff message

Example handoff sequence:
- Architect produces implementation-plan.md
- status.md updated
- Builder receives: "Begin milestone implementation using implementation-plan.md"

---

## Human Task Handling

Agents must recognize tasks requiring human input.

human_tasks.md contains:
- external service setup
- API key generation
- manual account creation
- license approvals

Milestones requiring human action must be marked: **BLOCKED**

Agents may only proceed when milestone state becomes: **READY**

---

## Developer Start Conditions

Builder may begin coding only if:
- spec.md exists
- implementation-plan.md exists
- status.md shows "architect complete"

---

## Question Escalation Rules

If requirements are unclear, Builder must either:
- ask Project Manager directly
- create a clarification ticket

Example: `tickets/QUESTION-001.md`

---

## UI Design Reference Training

Agents must understand UI specification files:
- ui-wireframes.md
- screens.md
- components.md
- design-system.md

These define layout, navigation, button placement, and component structure.

---

## Overnight Autonomous Work Rules

Night mode permissions:
- implement milestones
- run tests
- fix bugs

Night mode restrictions:
- no architecture changes
- no new features
- no specification changes

---

## Autonomous Progress Limits

Agents may advance only a limited number of milestones without human approval.

Recommended limit: **2–3 milestones per overnight cycle.**

---

## Overnight Workflow Loop

While night mode enabled:
1. PM assigns milestone
2. Builder implements milestone
3. QA tests build
4. Bug fixes performed
5. Loop continues until milestone limit reached

---

## Morning Report Generation

Project Manager produces: **overnight-report.md**

Report must include:
- milestones completed
- builds created
- bugs fixed
- remaining issues
- next milestone

---

## Multi-Project Operation Training

Agents must operate across multiple projects without mixing artifacts.

Project isolation enforced through:
- project folder structure
- active-project.md

Agents may only modify files inside the active project path.

---

## Environment and Tooling Training

Provide environment rules including:
- preferred programming languages
- framework preferences
- package manager preference
- test framework standards
- repository structure
- build commands
- deployment targets

---

## Code Style Training

Agents must follow defined coding standards:
- consistent file naming
- modular architecture
- clear function boundaries
- documentation requirements
- test coverage expectations

---

## Security Training

Agents must follow security policies:
- no secrets stored in workspace files
- no API keys committed to source
- all credentials stored in environment configuration
- sensitive operations require human approval

---

## Decision and Escalation Rules

Agents must escalate decisions when:
- architecture must change
- requirements conflict
- external dependencies unavailable
- security concerns arise

---

## Example Project Training Data

Provide agents with examples of completed projects containing:
- spec.md
- milestones.md
- tickets
- status updates
- build artifacts

These examples teach the agent expected output patterns.

---

## Repository and Version Control Training

Typical flow:
- branch creation
- commit updates
- commit messages
- pull request creation
- merge process

---

## Final Training Dataset Components

The agent training corpus should contain:
1. workflow summary document
2. agent behavior policy files
3. workspace templates
4. project structure template
5. example completed projects
6. coding standards documentation
7. environment configuration documentation
8. ticket lifecycle rules
9. handoff rules
10. night mode rules
11. escalation rules
