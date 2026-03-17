# OpenClaw CLI Integration Guide

**Last Updated:** 2026-03-16
**OpenClaw Version:** 2026.3.13 (61d171a)
**Context:** Mission Control integration patterns and endpoint design

---

## Overview

This document captures the OpenClaw CLI structure and successful integration patterns discovered while building Mission Control (v0.3.3). It serves as a reference for integrating OpenClaw commands into Mission Control's FastAPI server and frontend.

---

## OpenClaw CLI Structure

OpenClaw is a comprehensive CLI tool with ~40 command groups. The version number follows: `openclaw --version` returns `OpenClaw 2026.3.13 (61d171a)`.

### Key Command Families

**Gateway & Agent Control:**
- `openclaw gateway *` — Full family for gateway management (run, inspect, query)
- `openclaw agent` — Execute one agent turn
- `openclaw agents *` — Manage isolated agent workspaces

**UI & Dashboard:**
- `openclaw dashboard` — Opens the OpenClaw Control UI
- `openclaw tui` — Terminal UI connected to the gateway

**Configuration:**
- `openclaw configure` — Interactive setup wizard
- `openclaw config *` — Non-interactive config (get/set/unset/file/validate)
- `openclaw setup` — Initialize local config and workspace

**Utilities:**
- `openclaw status` — Show channel health (NOT gateway health)
- `openclaw logs` — Tail gateway file logs via RPC
- `openclaw models *` — Model discovery and configuration
- `openclaw skills *` — List and inspect skills

See [openclaw-cli-reference.md](openclaw-cli-reference.md) for the full command list.

---

## Mission Control Gateway Control (v0.3.3)

### Problem Statement

When users promoted an agent to be the primary chat entrypoint (via "Set as Main" button), Mission Control showed a popup message: "Gateway may need a restart." But users had no way to act on that without dropping into the terminal.

**Solution:** Build a gateway control bar in the Mission Control dashboard with start/stop/restart buttons.

### What Doesn't Exist

Early attempts failed because certain commands don't exist in the OpenClaw CLI:

❌ `openclaw gateway start` — **Does not exist**
❌ `openclaw gateway stop` — **Does not exist**
❌ `openclaw gateway restart` — **Does not exist**

These commands were attempted based on the pattern of other OpenClaw subcommands, but the actual gateway lifecycle is managed via macOS `launchctl` and the `openclaw gateway install` helper.

### Correct macOS Gateway Control Approach

**Based on actual OpenClaw CLI behavior:**

**Start Gateway:**
```bash
# 1. Ensure the service is installed (idempotent)
openclaw gateway install

# 2. Load the service via launchctl
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/ai.openclaw.gateway.plist

# 3. Wait ~1.5 seconds for startup
sleep 1.5

# 4. Verify status (see "Status Detection" section below)
openclaw gateway status
```

**Stop Gateway:**
```bash
# Unload the service via launchctl
launchctl bootout gui/$UID ~/Library/LaunchAgents/ai.openclaw.gateway.plist

# Wait ~1 second for shutdown
sleep 1

# Verify status
openclaw gateway status
```

**Restart Gateway:**
```bash
# Unload
launchctl bootout gui/$UID ~/Library/LaunchAgents/ai.openclaw.gateway.plist
sleep 1

# Install and load
openclaw gateway install
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/ai.openclaw.gateway.plist
sleep 1.5

# Verify status
openclaw gateway status
```

### Status Detection

`openclaw gateway status` does NOT use returncode to indicate running state. Both "running" and "stopped" states return `returncode == 0`. Instead, parse the message content for keywords:

**Running indicators:** `"running"`, `"active"`
**Stopped indicators:** `"not loaded"`, `"rpc probe: failed"`, `"stopped"`

**Python example:**
```python
result = subprocess.run(
    ["openclaw", "gateway", "status"],
    capture_output=True, text=True, timeout=2
)

# Parse stdout + stderr for keywords
is_running = "running" in result.stdout.lower()
is_stopped = "not loaded" in result.stdout.lower() or "rpc probe: failed" in result.stderr.lower()

if is_running:
    state = "running"
elif is_stopped:
    state = "stopped"
else:
    state = "unknown"
```

### Mission Control Implementation (server.py)

**File:** `mission-control/openclaw/web/server.py`

**Endpoints added in v0.3.3:**

```python
@app.get("/api/gateway/status")
async def get_gateway_status() -> JSONResponse:
    """Returns {ok, state: "running|stopped|error|unknown", message, stdout, stderr}"""
    # Calls: openclaw gateway status
    # Parses stdout/stderr for keywords to determine state
    # Returns structured response with state + message

@app.post("/api/gateway/start")
async def start_gateway() -> JSONResponse:
    """Returns {ok, state: "running|error", message, stdout, stderr}"""
    # Calls: openclaw gateway install
    # Then: launchctl bootstrap gui/$UID ~/Library/LaunchAgents/ai.openclaw.gateway.plist
    # Sleeps 1.5 seconds
    # Verifies with status check
    # Returns structured response

@app.post("/api/gateway/stop")
async def stop_gateway() -> JSONResponse:
    """Returns {ok, state: "stopped|error", message, stdout, stderr}"""
    # Calls: launchctl bootout gui/$UID ~/Library/LaunchAgents/ai.openclaw.gateway.plist
    # Sleeps 1 second
    # Verifies with status check
    # Returns structured response

@app.post("/api/gateway/restart")
async def restart_gateway() -> JSONResponse:
    """Returns {ok, state: "running|error", message, stdout, stderr}"""
    # Calls: bootout, install, bootstrap sequence
    # Sleeps appropriately between steps
    # Verifies final state
    # Returns structured response
```

**Response format (all endpoints):**
```json
{
  "ok": true,
  "state": "running|stopped|error|unknown",
  "message": "Human-readable status or error message",
  "stdout": "Command stdout",
  "stderr": "Command stderr"
}
```

**Key implementation details:**
- Import `os` for `os.getuid()` and `os.path.expanduser()`
- Use `subprocess.run()` with `capture_output=True, timeout=5` for launchctl commands
- Use `await asyncio.sleep()` between sequential operations (not blocking sleep)
- Always check status after start/stop/restart to verify the state changed

---

## Frontend Integration (app.js)

**File:** `mission-control/openclaw/web/static/app.js`

**State variables:**
```javascript
let _gwState = 'unknown';      // Current gateway state
let _gwBusy = false;           // True while operation in progress
let _gwPollTimer = null;       // setInterval handle for auto-polling
```

**Key functions:**

**`refreshGatewayStatus()`**
- Fetches `GET /api/gateway/status`
- Updates dot class: `gw-running` (green), `gw-stopped` (red), `gw-unknown` (gray)
- Updates label text: "Gateway · Running", "Gateway · Stopped", etc.
- Updates last-checked time
- Adjusts button availability (disable Start if running, disable Stop if stopped)

**`gatewayAction(action)`**
- Parameters: `"start"`, `"stop"`, `"restart"`
- Shows confirm dialog for stop/restart
- Sets `_gwBusy = true`, disables all buttons
- Sets dot to `gw-busy` (yellow, pulsing)
- Calls appropriate API endpoint
- On success: waits 1.5s, then calls `refreshGatewayStatus()`
- On error: shows `alert()` with error message
- Re-enables buttons in finally block

**`showGatewayBanner(message)` / `dismissGatewayBanner()`**
- Shows/hides the gateway banner above main content
- Used for "restart recommended" messages after config changes

**`startGatewayPolling()`**
- Calls `refreshGatewayStatus()` immediately
- Sets `setInterval(..., 5000)` for auto-polling every 5 seconds
- Called during app boot sequence

**Integration with "Set as Main":**
```javascript
// In setAsMain() success handler:
if (data.ok) {
    // Instead of: alert("Gateway restart recommended...");
    showGatewayBanner("Gateway restart recommended — persona change may require it.");
}
```

---

## Gateway Control Bar UI (index.html)

**Location:** Between `</header>` and `<div class="main-content">`

**HTML structure:**
```html
<div class="gateway-bar" id="gatewayBar">
  <div class="gateway-status">
    <span class="gw-dot" id="gwDot"></span>
    <span id="gwLabel">Gateway</span>
    <span class="gw-checked" id="gwChecked"></span>
  </div>
  <div class="gateway-actions">
    <button id="gwBtnStart" class="gw-btn" onclick="gatewayAction('start')">Start</button>
    <button id="gwBtnStop" class="gw-btn gw-btn-danger" onclick="gatewayAction('stop')">Stop</button>
    <button id="gwBtnRestart" class="gw-btn" onclick="gatewayAction('restart')">Restart</button>
    <button id="gwBtnRefresh" class="gw-btn gw-btn-ghost" onclick="refreshGatewayStatus()">↻</button>
  </div>
</div>

<div class="gateway-banner" id="gatewayBanner" style="display:none">
  <span id="gatewayBannerText"></span>
  <button class="gw-btn" onclick="gatewayAction('restart')">Restart Now</button>
  <button class="gw-banner-dismiss" onclick="dismissGatewayBanner()">✕</button>
</div>
```

**CSS classes:**
- `.gateway-bar` — Control bar container (dark background, 38px height)
- `.gateway-status` — Dot + label + last-checked display
- `.gw-dot` — 8x8 status indicator
- `.gw-running` — Green dot with glow shadow
- `.gw-stopped` — Red dot
- `.gw-busy` — Yellow dot with pulsing animation
- `.gw-unknown` — Gray dot (when binary not found)
- `.gw-btn` — Standard button styling
- `.gw-btn-danger` — Red text for destructive actions (stop)
- `.gw-btn-ghost` — Transparent button (refresh ↻)
- `.gateway-banner` — "Restart recommended" message bar

---

## Testing Checklist

✅ Load dashboard — gateway bar appears below header
✅ Gateway running → green dot, "Running", Start button disabled
✅ Gateway stopped → red dot, "Stopped", Stop button disabled
✅ Click Stop → confirm dialog → dot pulses yellow "Stopping..." → red dot
✅ Click Start → yellow "Starting..." → green dot + "Running"
✅ Click Restart → confirm dialog → yellow "Restarting..." → green dot
✅ Click ↻ Refresh → immediate status poll (updates dot + label + time)
✅ Click "Set as Main" → banner appears "Gateway restart recommended..."
✅ Click "Restart Now" in banner → restart executes → banner dismisses
✅ All buttons disabled if openclaw binary not found (gray dot + "Unreachable")

---

## Key Learnings

1. **Don't assume command patterns.** Just because `openclaw config *` and `openclaw models *` exist doesn't mean `openclaw gateway start/stop/restart` do. Always verify with `--help` or `openclaw <command> --help`.

2. **Parse output, not returncode.** OpenClaw's `gateway status` returns 0 regardless of state. Always examine stdout/stderr content.

3. **launchctl is the source of truth on macOS.** The OpenClaw gateway is managed via launchd service at `~/Library/LaunchAgents/ai.openclaw.gateway.plist`. Direct launchctl calls are reliable; shell-level `openclaw gateway` helpers are convenience wrappers.

4. **Timing matters.** Services take time to start/stop. Use appropriate sleep intervals (1-1.5s) and always verify final state after operations.

5. **User experience matters.** Adding buttons to the UI without explaining when they're disabled or why an operation failed leads to confusion. Always show state, provide clear error messages, and include a manual refresh button.

---

## Related Files

- `mission-control/openclaw/web/server.py` — Gateway endpoints (lines 973-1155)
- `mission-control/openclaw/web/static/index.html` — Gateway bar HTML + CSS
- `mission-control/openclaw/web/static/app.js` — Gateway control JS functions
- `CLAUDE-TODO.md` — v0.3.3 gateway feature completion notes
- `CLAUDE-TODO.md` — v0.4.x embedded agent chat (future work) roadmap
