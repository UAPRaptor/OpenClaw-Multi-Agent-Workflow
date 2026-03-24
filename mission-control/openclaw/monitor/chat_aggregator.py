"""
Aggregates agent chat messages from JSONL session files into a unified timeline.
Supports cursor-based incremental reading for efficient real-time streaming.
"""
import base64
import json
from pathlib import Path


# Maximum text length for spawn task previews
_PREVIEW_LEN = 200


def _extract_text(content: list) -> str:
    """Extract concatenated text from message content blocks."""
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(parts)


def _parse_event(event: dict, role: str) -> list[dict]:
    """Parse a JSONL event into zero or more normalized chat messages."""
    if event.get("type") != "message":
        return []

    msg = event.get("message", {})
    msg_role = msg.get("role")
    content = msg.get("content", [])
    ts = event.get("timestamp", "")
    eid = event.get("id", "")

    results = []

    if msg_role in ("user", "assistant"):
        # Check for spawn/yield tool calls in content blocks
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "toolCall":
                name = block.get("name", "")
                args = block.get("arguments", {})
                if name == "sessions_spawn":
                    task = args.get("task", "")
                    # Try to extract target agent from task text
                    target = None
                    task_lower = task.lower()
                    for agent_role in ("architect", "builder", "qa", "security", "devops", "ux", "research", "graphics", "pm"):
                        if agent_role in task_lower:
                            target = agent_role
                            break
                    results.append({
                        "id": eid + "_spawn",
                        "ts": ts,
                        "agent": role,
                        "type": "spawn",
                        "text": task[:_PREVIEW_LEN] + ("..." if len(task) > _PREVIEW_LEN else ""),
                        "target": target,
                        "model": None,
                    })
                elif name == "sessions_yield":
                    wait_msg = args.get("message", "Waiting...")
                    results.append({
                        "id": eid + "_yield",
                        "ts": ts,
                        "agent": role,
                        "type": "yield",
                        "text": wait_msg,
                        "target": None,
                        "model": None,
                    })

        # Also emit the text content as a normal message (if any)
        text = _extract_text(content)
        if text.strip():
            results.append({
                "id": eid,
                "ts": ts,
                "agent": role,
                "type": msg_role,  # "user" or "assistant"
                "text": text,
                "target": None,
                "model": None,
            })

    return results


class ChatAggregator:
    """Reads JSONL session files and produces a unified message timeline."""

    def __init__(self, agents_dir: Path):
        self.agents_dir = agents_dir

    def get_active_session_file(self, role: str) -> Path | None:
        """Find the most recently modified .jsonl file for an agent role."""
        sessions_dir = self.agents_dir / role / "sessions"
        if not sessions_dir.exists():
            return None
        jsonl_files = list(sessions_dir.glob("*.jsonl"))
        # Exclude reset/backup files
        jsonl_files = [f for f in jsonl_files if ".reset." not in f.name]
        if not jsonl_files:
            return None
        return max(jsonl_files, key=lambda f: f.stat().st_mtime)

    def _get_all_roles(self) -> list[str]:
        """List all agent roles that have session files."""
        if not self.agents_dir.exists():
            return []
        roles = []
        for d in sorted(self.agents_dir.iterdir()):
            if d.is_dir() and (d / "sessions").exists():
                jsonl = list((d / "sessions").glob("*.jsonl"))
                jsonl = [f for f in jsonl if ".reset." not in f.name]
                if jsonl:
                    roles.append(d.name)
        return roles

    def _read_session_file(self, path: Path, offset: int = 0) -> tuple[list[dict], int]:
        """Read JSONL events from a file starting at byte offset.
        Returns (events, new_offset)."""
        events = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                f.seek(offset)
                while True:
                    line = f.readline()
                    if not line:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                new_offset = f.tell()
        except (OSError, IOError):
            return [], offset
        return events, new_offset

    def scan_all(self, limit: int = 100) -> tuple[list[dict], dict]:
        """Full scan of all agents' active sessions.
        Returns (messages sorted by timestamp, cursors dict)."""
        all_messages: list[dict] = []
        cursors: dict[str, int] = {}

        for role in self._get_all_roles():
            session_file = self.get_active_session_file(role)
            if not session_file:
                continue
            events, offset = self._read_session_file(session_file, 0)
            cursors[role] = offset
            for event in events:
                all_messages.extend(_parse_event(event, role))

        # Sort by timestamp, take last N
        all_messages.sort(key=lambda m: m["ts"])
        if len(all_messages) > limit:
            all_messages = all_messages[-limit:]

        return all_messages, cursors

    def scan_incremental(self, cursors: dict) -> tuple[list[dict], dict]:
        """Incremental scan using byte-offset cursors.
        Returns (new messages, updated cursors)."""
        new_messages: list[dict] = []
        updated_cursors = dict(cursors)

        for role in self._get_all_roles():
            session_file = self.get_active_session_file(role)
            if not session_file:
                continue

            offset = cursors.get(role, 0)

            # Check if file was truncated/reset (new file is smaller than cursor)
            try:
                file_size = session_file.stat().st_size
            except OSError:
                continue
            if file_size < offset:
                offset = 0  # file was reset, read from beginning

            events, new_offset = self._read_session_file(session_file, offset)
            updated_cursors[role] = new_offset

            for event in events:
                new_messages.extend(_parse_event(event, role))

        new_messages.sort(key=lambda m: m["ts"])
        return new_messages, updated_cursors

    @staticmethod
    def encode_cursor(cursors: dict) -> str:
        """Encode cursors dict as URL-safe base64 string."""
        return base64.urlsafe_b64encode(json.dumps(cursors).encode()).decode()

    @staticmethod
    def decode_cursor(cursor_str: str) -> dict:
        """Decode a cursor string back to a dict."""
        try:
            return json.loads(base64.urlsafe_b64decode(cursor_str.encode()).decode())
        except Exception:
            return {}
