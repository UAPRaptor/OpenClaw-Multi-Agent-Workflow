TRAINING RESOURCE TYPES FOR CLAUDE CODE AGENTS

To train a Claude Code agent well on top of the workflow summary, provide five additional resource types:

---

1. YOUR OPERATING CONSTITUTION

This is the non-negotiable behavior layer.
Include:

* how agents should behave
* when to ask vs act
* what files they may edit
* how tickets work
* how handoffs work
* what "done" means
* what not to do overnight

This usually becomes your baseline:

* AGENTS.md
* SOUL.md
* TOOLS.md
* USER.md

---

2. REAL PROJECT TEMPLATES

Do not just describe the workflow. Give it actual starter files.
Examples:

* spec-template.md
* milestones-template.md
* ticket-template.md
* status-template.md
* handoff-template.md
* overnight-report-template.md

Agents perform much better when they can copy a pattern instead of inventing one.

---

3. EXAMPLE FINISHED PROJECTS

Give it 1–3 small examples of a project that went from:
idea → spec → milestones → tickets → build → QA → release

This teaches the agent what "good output" looks like.

---

4. TOOL AND ENVIRONMENT DOCUMENTATION

The coding agent needs to know your actual dev environment.
Include:

* preferred languages/frameworks
* repo structure
* how to run builds
* how to run tests
* deployment targets
* secrets handling rules
* package manager preferences
* Git workflow

Examples:

* "Use Next.js + Tailwind by default"
* "Use pnpm, not npm"
* "Write tests with Playwright and Vitest"
* "Never invent env vars; document required ones in .env.example"

---

5. DECISION RULES AND ESCALATION RULES

This is the missing piece most people forget.
Teach it:

* when to open a bug ticket
* when to ask PM
* when to stop and wait
* when to continue autonomously
* when a milestone is blocked
* when human approval is required

Examples:

* unclear requirement → ask PM
* missing API key → mark blocked
* failing test with obvious fix → fix and retry
* architecture change → escalate
* new feature request during bugfix → ticket it, do not improvise

---

PRACTICAL ARTIFACTS FOR CLAUDE CODE AGENTS

Also provide these practical artifacts:

* a golden workspace template
* a sample multi-project folder layout
* a sample active-project file
* a sample ticket lifecycle
* a sample overnight workflow
* a small real repo to practice on

---

BEST POSSIBLE TRAINING PACK

1. your long workflow summary
2. your baseline policy files
3. your project templates
4. one example completed project
5. one example active repo
6. your coding standards
7. your escalation rules
