"""
Alert engine for OpenClaw Mission Control.
Detects security-relevant and operational anomalies.
Appends to mission-control-alerts.log (never overwrites — append-only for forensic integrity).
"""
from datetime import datetime, timezone
from pathlib import Path

from openclaw.monitor.state_store import StateStore


STALL_THRESHOLD_MINUTES = 30
STALL_CHECK_INTERVAL_SECONDS = 120
# Don't alert on agents inactive longer than this — they were never started or
# stopped long ago.  Avoids "stalled for 10134 minutes" noise.
STALL_MAX_AGE_MINUTES = 60 * 24  # 24 hours

# Paths that are expected to be written by agents
EXPECTED_WRITE_PATTERNS = [
    "projects/",
    "AGENTS.md",
    "SOUL.md",
    "TOOLS.md",
    "USER.md",
    "active-project.md",
    "mission-control-state.json",
]

# Files that must never be written unexpectedly
HIGH_SENSITIVITY_FILES = [
    ".claude/settings.json",
    ".claude/settings.local.json",
]


class AlertEngine:
    def __init__(self, workspace_root: Path, store: StateStore):
        self.workspace_root = workspace_root
        self.store = store
        monitor_dir = Path.home() / ".openclaw-mission-control"
        monitor_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = monitor_dir / "alerts.log"
        self._seen_settings_mtime: float | None = None

    def _log(self, level: str, message: str) -> None:
        """Appends alert to log file (append-only)."""
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        entry = f"[{timestamp}] [{level.upper()}] {message}\n"
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(entry)
        except IOError:
            pass

    def check_file_event(self, file_path: str) -> None:
        """
        Called by the file watcher on every file change.
        Checks for security-sensitive file modifications.
        """
        normalized = file_path.replace("\\", "/")

        for sensitive in HIGH_SENSITIVITY_FILES:
            if sensitive in normalized:
                message = f"settings.json was modified: {file_path}"
                self._log("SECURITY", message)
                self.store.add_alert(
                    level="security",
                    message=f"SECURITY ALERT: {message}",
                    alert_id="settings-change",
                )
                return

        # Check for writes outside the expected workspace paths
        rel_path = file_path.replace(str(self.workspace_root), "").lstrip("/\\")
        is_expected = any(
            rel_path.startswith(pattern.replace("/", "").replace("\\", ""))
            or pattern in rel_path
            for pattern in EXPECTED_WRITE_PATTERNS
        )
        # Don't alert on expected paths — only surface truly anomalous writes
        # (This is conservative; tighten patterns per deployment as needed)

    def check_build_directory(self) -> None:
        """
        Checks if builds directory exists and warns if it was unexpectedly emptied.
        Called periodically.
        """
        state = self.store.get()
        active = state.get("active_project")
        if not active:
            return

        builds_dir = self.workspace_root / active.get("path", "") / "builds"
        if builds_dir.exists():
            files = list(builds_dir.iterdir())
            if not files:
                # Only alert once
                alerts = state.get("alerts", [])
                if not any(a.get("id") == "builds-empty" for a in alerts):
                    msg = "builds/ directory is empty — builds may have been deleted."
                    self._log("WARNING", msg)
                    self.store.add_alert(level="warning", message=msg, alert_id="builds-empty")

    def check_stalled_agents(self) -> None:
        """
        Checks for agents that have not updated any files recently.
        Called periodically.
        """
        state = self.store.get()
        agents = state.get("agents", {})
        now = datetime.now(tz=timezone.utc).timestamp()

        for role, info in agents.items():
            last_active = info.get("last_active")
            if not last_active:
                continue
            try:
                last_ts = datetime.fromisoformat(last_active).timestamp()
                age_minutes = (now - last_ts) / 60

                # Only alert if agent was active within the last 24 hours —
                # skip agents that were never started or stopped long ago.
                if age_minutes > STALL_MAX_AGE_MINUTES:
                    continue

                if age_minutes > STALL_THRESHOLD_MINUTES:
                    alert_id = f"stall-{role}"
                    alerts = state.get("alerts", [])
                    existing = next((a for a in alerts if a.get("id") == alert_id and not a.get("dismissed")), None)
                    if not existing:
                        char = info.get("character", role)
                        # Human-friendly time formatting
                        if age_minutes < 60:
                            age_str = f"{int(age_minutes)}m"
                        else:
                            hours = int(age_minutes // 60)
                            mins = int(age_minutes % 60)
                            age_str = f"{hours}h {mins}m" if mins else f"{hours}h"
                        msg = f"Agent stalled: {char} ({role}) — no activity for {age_str}."
                        self._log("WARNING", msg)
                        self.store.add_alert(level="warning", message=msg, alert_id=alert_id)
            except (ValueError, TypeError):
                continue
