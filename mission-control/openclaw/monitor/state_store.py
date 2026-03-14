"""
In-memory state store for the monitor dashboard.
Persists to mission-control-state.json on each update.
Notifies registered listeners (WebSocket hub) on change.
"""
import copy
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


def _monitor_dir() -> Path:
    """Returns ~/.openclaw-mission-control/ for storing monitor data outside the workspace."""
    d = Path.home() / ".openclaw-mission-control"
    d.mkdir(parents=True, exist_ok=True)
    return d


class StateStore:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self._state: dict = self._empty_state()
        self._lock = threading.Lock()
        self._listeners: list[Callable] = []
        self._state_file = _monitor_dir() / "state.json"

    def _empty_state(self) -> dict:
        return {
            "workspace": str(self.workspace_root) if hasattr(self, "workspace_root") else "",
            "active_project": None,
            "agents": {},
            "project": {
                "name": None,
                "milestone_current": None,
                "milestone_total": None,
                "last_updated": None,
            },
            "tickets": {
                "proposed": 0,
                "ready": 0,
                "in-progress": 0,
                "blocked": 0,
                "qa-failed": 0,
                "fixed": 0,
                "passed": 0,
                "released": 0,
            },
            "activity": [],  # list of {time, file, message}
            "overnight": {
                "enabled": False,
                "milestones_tonight": 0,
                "report_available": False,
            },
            "alerts": [],  # list of {id, time, level, message, dismissed}
        }

    def get(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._state)

    def update(self, partial: dict) -> None:
        with self._lock:
            self._merge(self._state, partial)
            self._state["last_refreshed"] = datetime.now(tz=timezone.utc).isoformat()
            self._persist()
        self._notify()

    def _merge(self, base: dict, updates: dict) -> None:
        for k, v in updates.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                self._merge(base[k], v)
            else:
                base[k] = v

    def _persist(self) -> None:
        try:
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2, default=str)
        except IOError:
            pass

    def register_listener(self, fn: Callable) -> None:
        self._listeners.append(fn)

    def _notify(self) -> None:
        snapshot = self.get()
        for fn in self._listeners:
            try:
                fn(snapshot)
            except Exception:
                pass

    def add_activity(self, file_path: str, message: str) -> None:
        entry = {
            "time": datetime.now(tz=timezone.utc).isoformat(),
            "file": file_path,
            "message": message,
        }
        with self._lock:
            self._state["activity"].insert(0, entry)
            self._state["activity"] = self._state["activity"][:50]  # keep last 50
            self._persist()
        self._notify()

    def add_alert(self, level: str, message: str, alert_id: str | None = None) -> None:
        import uuid
        entry = {
            "id": alert_id or str(uuid.uuid4())[:8],
            "time": datetime.now(tz=timezone.utc).isoformat(),
            "level": level,
            "message": message,
            "dismissed": False,
        }
        with self._lock:
            self._state["alerts"].insert(0, entry)
            self._state["alerts"] = self._state["alerts"][:20]  # keep last 20
            self._persist()
        self._notify()

    def dismiss_alert(self, alert_id: str) -> None:
        with self._lock:
            for alert in self._state["alerts"]:
                if alert["id"] == alert_id:
                    alert["dismissed"] = True
            self._persist()
        self._notify()
