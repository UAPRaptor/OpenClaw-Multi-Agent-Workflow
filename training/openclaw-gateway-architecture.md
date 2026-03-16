# OpenClaw Gateway — Architecture and Behavior

## 1. What the OpenClaw Gateway Is

The OpenClaw Gateway is the central runtime service of OpenClaw.

It is responsible for:
- routing requests to agents
- spawning agent sessions
- managing agent workspaces
- handling authentication
- managing tool execution
- maintaining agent state and memory
- exposing the API that external systems interact with

Think of it as the control plane and router for the entire OpenClaw system.

Without the gateway running, agents cannot be invoked, sessions cannot start, and requests cannot be routed.

Your agent manager application should assume:

**The gateway is the running OpenClaw server process.**

---

## 2. How OpenClaw Is Structured

OpenClaw has three main layers.

### 1. Gateway (Core Runtime)

The gateway process:
- runs the OpenClaw server
- exposes the API
- routes requests to agents
- manages sessions and memory
- controls agent permissions and tools

This is the main OpenClaw process.

---

### 2. Agents

Agents are logical entities configured in OpenClaw.

Each agent has:
- an agentId
- a workspace
- configuration
- memory/state
- allowed tools
- allowed sub-agents

Agents do not run as separate OS processes.

Instead, the gateway spawns agent sessions internally when needed.

---

### 3. Sessions

When an agent is invoked, the gateway creates a session.

A session represents:
- the running context
- message history
- tool usage
- temporary state

Sessions are what actually execute agent behavior.

---

## 3. How the Gateway Routes Work

Typical request flow:

```
Client
   ↓
OpenClaw Gateway
   ↓
Agent selection
   ↓
Session spawn
   ↓
Agent executes
   ↓
Tools + memory + subagents
   ↓
Response returned
```

Example:

User sends request → gateway receives it → gateway routes to pm-agent → session starts → pm-agent delegates to builder-agent.

---

## 4. Why the Gateway Must Be Running

If the gateway is not running:
- agents cannot be invoked
- sessions cannot be created
- tool calls will fail
- agent discovery fails
- agent delegation fails

Therefore:

**Your agent manager should assume the gateway is running before it attempts to spawn or communicate with agents.**

---

## 5. Correct Workflow for an Agent Manager

Your agent manager application should not replace the gateway.

Instead it should:
1. ensure the gateway is running
2. create or register agents
3. configure agent workspaces
4. use gateway APIs to spawn or message agents
5. monitor agent activity

The gateway remains the runtime execution engine.

---

## 6. OpenClaw CLI Behavior

OpenClaw provides CLI commands that interact with the gateway.

### Start/Stop/Restart the gateway

**Note:** `openclaw gateway start/stop/restart` subcommands do not exist. Gateway lifecycle on macOS is managed via `launchctl`:

```bash
# Install service (idempotent)
openclaw gateway install

# Start via launchctl
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/ai.openclaw.gateway.plist

# Stop via launchctl
launchctl bootout gui/$UID ~/Library/LaunchAgents/ai.openclaw.gateway.plist

# Check status
openclaw gateway status
```

For UI-based gateway control, use **OpenClaw Mission Control** dashboard (v0.3.3+) which provides Start/Stop/Restart buttons.

### List agents

```
openclaw agents list
```

### Manage agents

```
openclaw agent --agent <role> --message "<message>"
```

Runs a single agent turn.

### Spawn a session

Sessions are usually spawned via API or internal agent calls.

---

## 7. Agent Workspaces

Each agent typically has a workspace containing files like:

```
SOUL.md
AGENTS.md
MEMORY.md
PROJECTS/
```

These provide context for the agent but do not create the agent themselves.

**The agent must still be registered with the gateway.**

---

## 8. Agent-to-Agent Communication

Agents do not normally communicate via files.

Instead they use gateway tools such as:

```
agents_list
sessions_spawn
sessions_send
```

Example flow:

```
pm-agent receives task
↓
pm-agent calls sessions_spawn(builder-agent)
↓
builder-agent session executes
↓
result returned to pm-agent
```

This ensures coordination happens inside the OpenClaw runtime.

---

## 9. Relationship Between Your Agent Manager and the Gateway

Your agent manager should behave like this:

```
Agent Manager App
        ↓
OpenClaw Gateway API
        ↓
Agents
        ↓
Sessions
```

The manager:
- installs agents
- configures workspaces
- orchestrates workflows

But **the gateway executes the agents**.

---

## 10. Should OpenClaw Be Running During Installation?

**Best practice: Yes — keep OpenClaw running.**

Reasons:
- the manager can verify gateway connectivity
- agents can be registered immediately
- configuration errors appear immediately
- session tests can run during install

Stopping the gateway is only needed when:
- upgrading OpenClaw itself
- modifying core runtime files
- replacing the gateway configuration

Normal agent installation does not require stopping the gateway.

---

## 11. What Your Agent Builder Must Do

When creating a new agent, the builder must:
1. create the workspace directory
2. generate SOUL.md / templates
3. register the agent with the gateway
4. verify the agent appears in agents list
5. test spawn a session

If step 3 is skipped, the agent does not exist to OpenClaw.

---

## 12. Key Design Principle

Your manager should treat the gateway as:

**The operating system for agents.**

Agents are not separate programs — they are entities executed by the gateway runtime.

---

## 13. Quick Mental Model

```
OpenClaw Gateway  =  kernel
Agents            =  processes
Sessions          =  process instances
Agent manager     =  system administration tool
```

---

## 14. Critical Rule for Your System

Never build a system where agents coordinate only through files.

Always ensure coordination can happen through:

```
agents_list
sessions_spawn
sessions_send
```

That keeps the workflow native to OpenClaw.

---

## Final Recommendation for Your Setup

When running your Agent Manager / Mission Control:

- Keep OpenClaw running
- Verify gateway connectivity
- Register agents through OpenClaw
- Spawn test sessions immediately after install

**Do not treat the gateway as optional.**
