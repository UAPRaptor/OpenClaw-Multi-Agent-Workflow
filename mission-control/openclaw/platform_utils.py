"""
Platform abstraction layer.
All Mac vs Windows differences are isolated here.
The rest of the codebase calls these functions — never checks sys.platform inline.
"""
import json
import os
import sys
import shutil
import subprocess
from pathlib import Path

import psutil

_MISSION_CONTROL_CONFIG = Path.home() / ".openclaw-mission-control.json"


def is_windows() -> bool:
    return sys.platform == "win32"


def is_mac() -> bool:
    return sys.platform == "darwin"


def get_default_workspace_dir() -> Path:
    # Prefer Documents on Mac/Windows as it's reliably writable
    docs = Path.home() / "Documents"
    if docs.exists():
        return docs / "openclaw-workspace"
    return Path.home() / "openclaw-workspace"


def get_claude_config_dir() -> Path:
    """
    Returns the path to the OpenClaw config directory.
    Mac:     ~/.claude/
    Windows: %APPDATA%/Claude/  (fallback to ~/.claude if not found)
    """
    if is_windows():
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidate = Path(appdata) / "Claude"
            if candidate.exists():
                return candidate
    return Path.home() / ".claude"


def find_claude_binary() -> str | None:
    """Returns the path to the claude CLI binary, or None if not found."""
    # Check PATH first (works on both platforms)
    found = shutil.which("claude")
    if found:
        return found

    # Mac common install locations
    if is_mac():
        candidates = [
            Path.home() / ".local" / "bin" / "claude",
            Path("/usr/local/bin/claude"),
            Path("/opt/homebrew/bin/claude"),
        ]
        for c in candidates:
            if c.exists():
                return str(c)

    # Windows common install locations
    if is_windows():
        localappdata = os.environ.get("LOCALAPPDATA", "")
        appdata = os.environ.get("APPDATA", "")
        candidates = [
            Path(localappdata) / "Programs" / "claude" / "claude.exe",
            Path(localappdata) / "Programs" / "Claude" / "claude.exe",
            Path(appdata) / "npm" / "claude.cmd",
            Path(appdata) / "npm" / "claude",
        ]
        for c in candidates:
            if c.exists():
                return str(c)

    return None


def open_browser(url: str) -> None:
    """Opens the default browser to the given URL."""
    if is_mac():
        subprocess.Popen(["open", url])
    elif is_windows():
        os.startfile(url)
    else:
        subprocess.Popen(["xdg-open", url])


def pick_folder_dialog(title: str = "Select Workspace Folder") -> str | None:
    """
    Opens the OS native folder-picker dialog and returns the selected path,
    or None if the user cancelled.
    Blocks until the user closes the dialog.
    """
    if is_mac():
        script = f'choose folder with prompt "{title}"'
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                # osascript returns "alias Macintosh HD:Users:bob:Documents:foo:"
                # Convert alias syntax to POSIX path
                alias = result.stdout.strip()
                posix = subprocess.run(
                    ["osascript", "-e", f'POSIX path of ("{alias}" as alias)'],
                    capture_output=True, text=True, timeout=5,
                )
                if posix.returncode == 0:
                    return posix.stdout.strip().rstrip("/")
        except Exception:
            pass
        return None

    if is_windows():
        ps_script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
            f"$d.Description = '{title}'; "
            "$d.ShowNewFolderButton = $true; "
            "if ($d.ShowDialog() -eq 'OK') { Write-Output $d.SelectedPath }"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return None

    # Linux / fallback: try zenity (common on GNOME desktops)
    try:
        result = subprocess.run(
            ["zenity", "--file-selection", "--directory", f"--title={title}"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def get_platform_label() -> str:
    if is_mac():
        return "macOS"
    if is_windows():
        return "Windows"
    return "Linux"


def normalize_path_for_display(path: Path) -> str:
    """Returns a user-friendly path string appropriate for the current OS."""
    return str(path)


def find_existing_workspaces() -> list[Path]:
    """
    Returns all paths that look like an OpenClaw workspace (contain AGENTS.md
    or active-project.md). Checks the last-known workspace first, then common
    default locations.
    """
    candidates = []

    # Last workspace saved from a previous install
    if _MISSION_CONTROL_CONFIG.exists():
        try:
            data = json.loads(_MISSION_CONTROL_CONFIG.read_text(encoding="utf-8"))
            last = data.get("last_workspace")
            if last:
                candidates.append(Path(last))
        except Exception:
            pass

    # Common default locations
    home = Path.home()
    candidates += [
        home / "Documents" / "openclaw-workspace",
        home / "openclaw-workspace",
        home / "Desktop" / "openclaw-workspace",
        home / "Documents" / "OpenClaw",
        home / "OpenClaw",
    ]

    found = []
    seen = set()
    for p in candidates:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        seen.add(key)
        if p.is_dir() and ((p / "AGENTS.md").exists() or (p / "active-project.md").exists()):
            found.append(p)
    return found


def save_last_workspace(path: Path) -> None:
    """Saves the workspace path to ~/.openclaw-mission-control.json."""
    try:
        data = {}
        if _MISSION_CONTROL_CONFIG.exists():
            try:
                data = json.loads(_MISSION_CONTROL_CONFIG.read_text(encoding="utf-8"))
            except Exception:
                pass
        data["last_workspace"] = str(path)
        _MISSION_CONTROL_CONFIG.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass  # Non-critical — installer still succeeds


def get_hardware_info() -> dict:
    """
    Detects machine specs and returns a recommended tier + model config.
    All detection is best-effort and non-blocking — failures return safe defaults.
    """
    ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 1)
    cpu_cores = psutil.cpu_count(logical=False) or psutil.cpu_count(logical=True) or 1

    vram_gb = 0.0
    gpu_name = None

    # NVIDIA GPU
    if shutil.which("nvidia-smi"):
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total,name", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                line = result.stdout.strip().split("\n")[0]
                parts = line.split(",")
                if len(parts) >= 2:
                    vram_gb = round(float(parts[0].strip()) / 1024, 1)
                    gpu_name = parts[1].strip()
        except Exception:
            pass

    # Apple Silicon — unified memory, no discrete VRAM
    if is_mac() and gpu_name is None:
        try:
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=3,
            )
            if "Apple" in result.stdout:
                gpu_name = "Apple Silicon (unified memory)"
        except Exception:
            pass

    # Tier decision — RAM is the primary factor for API-based agents
    if ram_gb < 8 or cpu_cores < 4:
        tier = "lite"
        recommended_agents = 4
    elif ram_gb >= 32 or vram_gb >= 16 or cpu_cores >= 8:
        tier = "power"
        recommended_agents = 8
    else:
        tier = "standard"
        recommended_agents = 4

    return {
        "ram_gb": ram_gb,
        "cpu_cores": cpu_cores,
        "vram_gb": vram_gb,
        "gpu_name": gpu_name,
        "tier": tier,
        "recommended_agents": recommended_agents,
    }


def find_active_claude_processes(workspace: Path) -> list[dict]:
    """
    Returns running OpenClaw processes whose cwd is inside the given workspace.
    Uses psutil — non-blocking, ignores processes we can't access.
    """
    workspace_str = str(workspace.resolve())
    results = []
    for proc in psutil.process_iter(["pid", "name", "cwd"]):
        try:
            name = (proc.info["name"] or "").lower()
            cwd = proc.info["cwd"] or ""
            if "claude" in name and workspace_str in cwd:
                results.append({"pid": proc.info["pid"], "name": proc.info["name"], "cwd": cwd})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return results


def get_corpus_dir() -> Path:
    """Returns the path to the bundled corpus templates."""
    if getattr(sys, "frozen", False):
        # Running as PyInstaller bundle
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).parent
    return base / "corpus"


def find_openclaw_binary() -> str | None:
    """Returns the path to the openclaw CLI binary, or None if not found."""
    found = shutil.which("openclaw")
    if found:
        return found
    # Fallback: openclaw may be invoked as 'claude'
    return find_claude_binary()


def find_openclaw_config_path() -> Path | None:
    """Searches common locations for the OpenClaw config JSON file."""
    candidates = [
        Path.home() / ".openclaw" / "config.json",
        Path.home() / ".config" / "openclaw" / "config.json",
        Path.home() / ".claude" / "config.json",
    ]
    if is_windows():
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            candidates.append(Path(appdata) / "OpenClaw" / "config.json")
    for path in candidates:
        if path.exists():
            return path
    return None


def detect_openclaw_models() -> list[dict]:
    """
    Returns models already configured in OpenClaw.
    Tries CLI first, then config file. Returns [] if nothing found.
    """
    binary = find_openclaw_binary()
    if binary:
        for sub in (["models"], ["list-models"]):
            try:
                result = subprocess.run(
                    [binary] + sub, capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0 and result.stdout.strip():
                    import re as _re
                    # Primary: parse "Configured models (N): id1, id2, ..." line
                    # This is the cleanest source — present in verbose doctor output
                    for line in result.stdout.strip().splitlines():
                        m = _re.match(r'configured models\s*\(\d+\)\s*:\s*(.+)', line.strip(), _re.IGNORECASE)
                        if m:
                            ids = [x.strip() for x in m.group(1).split(',') if x.strip()]
                            if ids:
                                return [{"id": mid, "provider": "", "label": mid} for mid in ids]

                    # Fallback: lines that look like model IDs (no spaces, provider/model or provider:model format)
                    models = []
                    for line in result.stdout.strip().splitlines():
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if line.startswith("-") or line.startswith("*"):
                            line = line[1:].strip()
                        # Strip trailing status text ("ok expires in Xm", "expired", etc.)
                        for marker in (" ok ", " expired", " expires", " warning", " error"):
                            idx = line.lower().find(marker)
                            if idx != -1:
                                line = line[:idx].strip()
                        # Only accept token-like model IDs: no spaces, must contain / or :
                        if line and ' ' not in line and _re.search(r'[/:]', line):
                            models.append({"id": line, "provider": "", "label": line})
                    if models:
                        return models
            except Exception:
                pass

    config_path = find_openclaw_config_path()
    if config_path:
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            raw = data.get("models", [])
            models = []
            for m in raw:
                if isinstance(m, dict):
                    models.append({
                        "id": m.get("id", m.get("model", "")),
                        "provider": m.get("provider", ""),
                        "label": m.get("label", m.get("id", m.get("model", ""))),
                    })
                elif isinstance(m, str) and m:
                    models.append({"id": m, "provider": "", "label": m})
            if models:
                return models
        except Exception:
            pass

    return []


def update_openclaw_config(config_path: Path, provider: dict) -> None:
    """
    Merges a new provider/model entry into the OpenClaw config JSON.
    provider dict: {"id": "...", "provider": "...", "label": "..."}
    """
    data: dict = {}
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    models: list = data.get("models", [])
    existing_ids = {m.get("id") if isinstance(m, dict) else m for m in models}
    if provider.get("id") not in existing_ids:
        models.append(provider)
        data["models"] = models
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
