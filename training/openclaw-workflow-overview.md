OPENCLAW MULTI-AGENT SOFTWARE DEVELOPMENT WORKFLOW SUMMARY

SYSTEM PURPOSE
This document describes a structured workflow for using multiple OpenClaw agents as a collaborative development team capable of taking a software idea from concept to working application through planning, development, testing, and release. The system supports multiple projects, milestone-based development, bug tracking, and controlled autonomous work (such as overnight progress) while maintaining human oversight.

---

CORE SYSTEM ARCHITECTURE

OPENCLAW INSTANCE
An OpenClaw instance is the running server process on a machine. One instance can host multiple independent agents.

AGENTS
Agents are autonomous AI workers with distinct roles, workspaces, memory, and models. Each agent performs specialized tasks.

SUBAGENTS
Subagents are temporary workers spawned by agents for focused tasks. They are not permanent agents and disappear after completing a task.

WORKSPACE
Each agent has a workspace containing files that define identity, rules, memory, and project artifacts.

Typical workspace files include:

AGENTS.md
SOUL.md
TOOLS.md
IDENTITY.md
USER.md
HEARTBEAT.md
MEMORY.md
memory/YYYY-MM-DD.md

These files define the behavior and persistent knowledge of the agent.

---

AGENT TEAM STRUCTURE

A development team can be implemented using either a minimal set of agents or a full specialization model.

MINIMAL TEAM (4 AGENTS)

1. Project Manager (PM)
2. Architect / Research
3. Builder / Developer
4. QA / Release

EXPANDED TEAM (8 AGENTS)

1. Product Owner
2. Project Manager / Coordinator
3. Research Agent
4. Architect Agent
5. Builder / Developer
6. QA / Test Agent
7. Release / DevOps Agent
8. UX / Documentation Agent

---

AGENT ROLE RESPONSIBILITIES

PROJECT MANAGER

Responsible for:

* communicating with the human user
* writing the product specification
* creating and managing milestones
* coordinating handoffs between agents
* generating progress reports
* managing project switching
* running overnight development loops

Key outputs:
spec.md
milestones.md
status.md

---

RESEARCH AGENT

Responsible for:

* technology evaluation
* researching APIs, frameworks, and libraries
* identifying risks and constraints
* proposing implementation options

Key outputs:
technical-options.md
research.md

---

ARCHITECT AGENT

Responsible for:

* designing the system architecture
* choosing frameworks and stack
* defining repository structure
* defining data models and interfaces
* converting specs into technical plans

Key outputs:
implementation-plan.md
architecture.md

---

BUILDER / DEVELOPER AGENT

Responsible for:

* implementing code
* following implementation plans
* creating milestone builds
* fixing bugs
* updating ticket statuses

Key outputs:
source code
build artifacts
commit notes

---

QA / TEST AGENT

Responsible for:

* validating builds
* writing tests
* detecting regressions
* reporting bugs

Key outputs:
bug tickets
test reports

---

RELEASE / DEVOPS AGENT

Responsible for:

* packaging builds
* preparing deployment
* managing environment configurations
* creating release notes

Key outputs:
build packages
deployment scripts
release notes

---

UX / DOCUMENTATION AGENT (optional)

Responsible for:

* writing UI text
* defining user flows
* documenting the product
* improving usability

---

PROJECT STRUCTURE

Agents operate within project folders so the same team can work on multiple applications.

Example structure:

projects/
app1/
spec.md
milestones.md
tickets/
builds/
app2/
spec.md
milestones.md
tickets/
builds/
app3/
spec.md
milestones.md
tickets/
builds/

Agents operate only inside the active project folder.

---

PROJECT SWITCHING

A file named:

active-project.md

defines which project is currently active.

Example contents:

Active Project: app2
Project Path: projects/app2

All agents must read active-project.md before beginning work.

When switching projects:

1. The user instructs the Project Manager agent to change projects.
2. The Project Manager updates active-project.md.
3. The Project Manager notifies downstream agents of the new project path.

---

PROJECT ARTIFACTS

Each project contains the following key files:

spec.md
milestones.md
status.md
tickets/
builds/

---

SPECIFICATION CREATION

Workflow:

1. User describes application idea.
2. Project Manager asks clarifying questions.
3. Project Manager writes spec.md.
4. User reviews and approves specification.

spec.md contains:

product goals
major features
user flows
design requirements

---

MILESTONE CREATION

After spec approval:

1. Project Manager creates milestones.md.
2. Architect validates milestone feasibility.
3. Builder begins implementation.

Example milestones:

Milestone 1
Project skeleton and navigation

Milestone 2
Authentication system

Milestone 3
Core feature implementation

Milestone 4
Secondary features

Milestone 5
Testing and stabilization

Milestone 6
Release build

Milestones must be small enough to produce runnable builds frequently.

---

BUILD GENERATION

Every milestone should produce a runnable build.

Typical build versions:

v0.1 – skeleton build
v0.2 – core features
v0.3 – feature complete
v0.4 – stabilization
v1.0 – release

Builds are stored in:

builds/

Example:

builds/build_v0.1
builds/build_v0.2

---

BUG AND FEATURE TICKETING

A simple file-based ticket system is used.

Example structure:

tickets/open/
tickets/closed/
tickets/archive/

Ticket example:

tickets/open/BUG-001.md

Ticket template fields:

Title
Type (bug / feature / tech debt)
Priority
Found by
Assigned to
Steps to reproduce
Expected behavior
Actual behavior
Acceptance criteria
Status

---

BUG WORKFLOW

1. Builder completes milestone.

2. QA tests build.

3. If a bug is found:

   QA creates ticket
   QA updates status.md
   QA notifies Builder

4. Builder fixes bug.

5. Builder updates ticket status.

6. QA retests.

---

STATUS TRACKING

status.md tracks progress across milestones and tickets.

Typical statuses:

proposed
ready
in-progress
blocked
qa-failed
fixed
passed
released

---

HANDOFF PROCESS BETWEEN AGENTS

Agent work transitions using three elements:

1. Deliverable artifact
2. Status update
3. Explicit kickoff message

Example handoff:

Architect completes implementation-plan.md
status.md updated to "architect complete"

Message sent:

Builder: begin milestone 1 using implementation-plan.md.

---

DEVELOPER START CONDITIONS

The Builder agent should only begin work when required files exist.

Example rule:

Builder may begin coding only if:

spec.md exists
implementation-plan.md exists
status.md shows architect complete

---

QUESTION AND CLARIFICATION WORKFLOW

If the Builder agent encounters ambiguity:

1. Builder pauses work.
2. Builder sends question to Project Manager.
3. Alternatively Builder opens a clarification ticket.

Example ticket:

tickets/QUESTION-001.md

---

UI AND DESIGN GUIDANCE

UI layout instructions are defined in design documents.

Examples:

ui-wireframes.md
screens.md
components.md
design-system.md

These documents describe:

menu placement
navigation structure
button placement
page layouts

The Builder agent implements UI based on these artifacts.

---

HUMAN SETUP TASKS

Some milestones require manual human tasks such as:

API key creation
external account setup
service configuration

These are tracked in:

human_tasks.md

Example:

Create Firebase project
Generate API key
Add credentials to environment

Milestones requiring human tasks are marked:

BLOCKED

Agents may only work on milestones marked:

READY

---

OVERNIGHT AUTONOMOUS DEVELOPMENT

Agents may operate autonomously during defined periods.

Night mode rules:

Agents may:

implement milestones
run tests
fix bugs

Agents may not:

change architecture
modify specification
introduce new features

---

AUTONOMOUS WORK LIMITS

Agents may advance a limited number of milestones autonomously.

Example limit:

maximum 2–3 milestones per night.

---

OVERNIGHT WORKFLOW LOOP

While night_mode = true:

PM assigns next milestone
Builder implements
QA tests
Bug fixes performed
Repeat until milestone limit reached

---

MORNING REPORT

The Project Manager produces a summary file.

Example:

overnight-report.md

Contents include:

completed milestones
builds created
bugs fixed
remaining issues
next milestone

---

MULTIPLE PROJECT SUPPORT

The same agent team may work on multiple applications.

Each project has its own folder containing:

specification
milestones
tickets
builds

Project switching is controlled by the Project Manager updating active-project.md.

---

KEY PRINCIPLES

Milestones produce runnable builds.
Artifacts define handoffs between agents.
Tickets track bugs and features.
Status files control workflow state.
Project folders isolate different applications.
Agents only operate on READY tasks.
Human input is required for blocked tasks.
Night mode allows safe autonomous progress.
