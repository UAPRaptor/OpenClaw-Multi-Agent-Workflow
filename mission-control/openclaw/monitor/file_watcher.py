"""
Filesystem watcher for the OpenClaw workspace.
Uses watchdog — handles FSEvents (Mac) and ReadDirectoryChangesW (Windows) automatically.
"""
import threading
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from openclaw.monitor.state_store import StateStore
from openclaw.monitor.agent_state_reader import (
    infer_activity_message,
    read_active_project,
    read_project_status,
    read_tickets,
    read_agent_activity,
    parse_agent_characters,
)
from openclaw.monitor.alert_engine import AlertEngine
from openclaw.monitor.chat_aggregator import ChatAggregator


DEBOUNCE_SECONDS = 2.0
CHAT_DEBOUNCE_SECONDS = 1.0
DEFAULT_AGENTS = ["pm", "architect", "builder", "qa"]
ALL_AGENTS = ["pm", "architect", "builder", "qa", "security", "devops", "ux", "research"]


class WorkspaceEventHandler(FileSystemEventHandler):
    def __init__(self, workspace_root: Path, store: StateStore, alert_engine: AlertEngine):
        super().__init__()
        self.workspace_root = workspace_root
        self.store = store
        self.alert_engine = alert_engine
        self._debounce_timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def on_any_event(self, event: FileSystemEvent):
        if event.is_directory:
            return

        # Skip transient/temp files
        src = str(event.src_path)
        if any(skip in src for skip in [".tmp", ".swp", "~", "__pycache__", ".pyc"]):
            return

        # Security check first — immediate, not debounced
        self.alert_engine.check_file_event(src)

        # Record activity immediately
        message = infer_activity_message(src)
        self.store.add_activity(src, message)

        # Debounce the full state refresh
        self._schedule_refresh()

    def _schedule_refresh(self):
        with self._lock:
            if self._debounce_timer:
                self._debounce_timer.cancel()
            self._debounce_timer = threading.Timer(DEBOUNCE_SECONDS, self._refresh_state)
            self._debounce_timer.daemon = True
            self._debounce_timer.start()

    def _refresh_state(self):
        try:
            active = read_active_project(self.workspace_root)
            if not active:
                return

            project_status = read_project_status(self.workspace_root, active["path"])
            tickets = read_tickets(self.workspace_root, active["path"])

            # Discover actual agents from AGENTS.md; fall back to default 4
            characters = parse_agent_characters(self.workspace_root)
            agents = list(characters.keys()) if characters else DEFAULT_AGENTS
            agent_activity = read_agent_activity(self.workspace_root, agents)

            overnight = {
                "enabled": project_status.pop("overnight_enabled", False),
                "report_available": project_status.pop("report_available", False),
                "milestones_tonight": 0,
            }

            self.store.update({
                "active_project": active,
                "project": project_status,
                "tickets": tickets,
                "agents": agent_activity,
                "overnight": overnight,
            })

            # Periodic alert checks
            self.alert_engine.check_build_directory()
            self.alert_engine.check_stalled_agents()

        except Exception:
            pass  # Never crash the watcher thread


class ChatEventHandler(FileSystemEventHandler):
    """Watches ~/.openclaw/agents/ for JSONL session file changes and broadcasts new chat messages."""

    def __init__(self, aggregator: ChatAggregator, hub):
        super().__init__()
        self._aggregator = aggregator
        self._hub = hub
        self._cursors: dict[str, int] = {}
        self._debounce_timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def on_any_event(self, event: FileSystemEvent):
        if event.is_directory:
            return
        src = str(event.src_path)
        # Only care about .jsonl file changes
        if not src.endswith(".jsonl"):
            return
        # Skip reset/backup files
        if ".reset." in src:
            return
        self._schedule_scan()

    def _schedule_scan(self):
        with self._lock:
            if self._debounce_timer:
                self._debounce_timer.cancel()
            self._debounce_timer = threading.Timer(CHAT_DEBOUNCE_SECONDS, self._do_scan)
            self._debounce_timer.daemon = True
            self._debounce_timer.start()

    def _do_scan(self):
        try:
            new_messages, self._cursors = self._aggregator.scan_incremental(self._cursors)
            if new_messages:
                self._hub.broadcast_from_thread({
                    "type": "team_chat",
                    "messages": new_messages,
                })
        except Exception:
            pass  # Never crash the watcher thread

    def init_cursors(self):
        """Initialize cursors to current end-of-file positions so we only stream new messages."""
        _, self._cursors = self._aggregator.scan_all(limit=0)


class WorkspaceWatcher:
    def __init__(self, workspace_root: Path, store: StateStore, alert_engine: AlertEngine, hub=None):
        self.workspace_root = workspace_root
        self.store = store
        self.alert_engine = alert_engine
        self._hub = hub
        self._observer: Observer | None = None
        self._chat_observer: Observer | None = None

    def start(self):
        handler = WorkspaceEventHandler(self.workspace_root, self.store, self.alert_engine)
        self._observer = Observer()
        self._observer.schedule(handler, str(self.workspace_root), recursive=True)
        self._observer.start()

        # Do an initial state read on startup
        handler._refresh_state()

        # Start chat watcher for agent session files
        if self._hub:
            self._start_chat_watcher()

    def _start_chat_watcher(self):
        agents_dir = Path.home() / ".openclaw" / "agents"
        if not agents_dir.exists():
            return
        aggregator = ChatAggregator(agents_dir)
        chat_handler = ChatEventHandler(aggregator, self._hub)
        chat_handler.init_cursors()  # Skip existing messages, only stream new ones
        self._chat_observer = Observer()
        self._chat_observer.schedule(chat_handler, str(agents_dir), recursive=True)
        self._chat_observer.start()

    def stop(self):
        if self._observer:
            self._observer.stop()
            self._observer.join()
        if self._chat_observer:
            self._chat_observer.stop()
            self._chat_observer.join()
