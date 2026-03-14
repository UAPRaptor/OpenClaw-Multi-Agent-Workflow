"""
Writes .claude/settings.json to the workspace directory.
Merges with any existing settings rather than overwriting.
"""
import json
from pathlib import Path

from openclaw.platform_utils import get_corpus_dir


def load_base_settings() -> dict:
    corpus = get_corpus_dir()
    settings_file = corpus / "settings" / "settings.json.base"
    with open(settings_file, encoding="utf-8") as f:
        return json.load(f)


def write_claude_settings(workspace_root: Path, default_model: str | None = None) -> str:
    """
    Writes .claude/settings.json inside the workspace.
    If an existing settings.json is present, merges the allow list
    rather than overwriting user customizations.

    default_model: if provided, writes a "model" key as the fallback for
    manual OpenClaw starts (per-role models are enforced via launcher scripts).

    Returns the path of the file written.
    """
    claude_dir = workspace_root / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    settings_path = claude_dir / "settings.json"

    base = load_base_settings()

    if settings_path.exists():
        try:
            with open(settings_path, encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, IOError):
            existing = {}

        # Merge: combine allow lists, deduplicate, preserve existing deny list
        existing_allow = existing.get("permissions", {}).get("allow", [])
        base_allow = base.get("permissions", {}).get("allow", [])
        merged_allow = list(dict.fromkeys(existing_allow + base_allow))  # dedupe, preserve order

        merged = {
            "permissions": {
                "allow": merged_allow,
                "deny": existing.get("permissions", {}).get("deny", []),
            }
        }
        # Preserve any other top-level keys from existing settings
        for k, v in existing.items():
            if k != "permissions":
                merged[k] = v
    else:
        merged = base

    if default_model:
        merged["model"] = default_model

    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2)

    return str(settings_path)
