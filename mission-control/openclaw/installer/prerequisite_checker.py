"""
Prerequisite checker for OpenClaw Mission Control installer.
Returns plain-English results — no stack traces shown to users.

blocking=True  → Continue button disabled until fixed (hard requirement)
blocking=False → shown as a warning; user can still proceed
"""
import subprocess
import shutil
from pathlib import Path
from dataclasses import dataclass


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
    fix: str       # plain-English fix instruction shown if failed/warned
    blocking: bool = True   # if False, failure shows as warning, not a blocker


def check_git() -> CheckResult:
    git = shutil.which("git")
    if not git:
        return CheckResult(
            name="Git",
            passed=False,
            blocking=False,  # warning — git needed for agent projects, not for installation
            detail="git not found in PATH",
            fix="Install Git from https://git-scm.com/downloads",
        )
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return CheckResult(
            name="Git",
            passed=True,
            blocking=False,
            detail=result.stdout.strip(),
            fix="",
        )
    except Exception:
        return CheckResult(
            name="Git",
            passed=False,
            blocking=False,
            detail="git found but failed to run",
            fix="Reinstall Git from https://git-scm.com/downloads",
        )


def check_target_directory(target: Path) -> CheckResult:
    try:
        target.mkdir(parents=True, exist_ok=True)
        test_file = target / ".openclaw_write_test"
        test_file.write_text("test")
        test_file.unlink()
        return CheckResult(
            name="Target Directory",
            passed=True,
            blocking=True,
            detail=f"Writable: {target}",
            fix="",
        )
    except PermissionError:
        return CheckResult(
            name="Target Directory",
            passed=False,
            blocking=True,
            detail=f"Permission denied: {target}",
            fix="Go back to Step 2 and choose a folder inside your Documents or Desktop folder.",
        )
    except Exception as e:
        return CheckResult(
            name="Target Directory",
            passed=False,
            blocking=True,
            detail=str(e),
            fix="Go back to Step 2 and choose a different folder.",
        )


def run_all_checks(target: Path) -> list[CheckResult]:
    return [
        check_git(),
        check_target_directory(target),
    ]


def all_clear(results: list[CheckResult]) -> bool:
    """Returns True if no blocking checks have failed."""
    return all(r.passed or not r.blocking for r in results)
