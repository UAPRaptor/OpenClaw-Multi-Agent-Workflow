import sys
from pathlib import Path


def _read_version() -> str:
    candidates = [
        Path(__file__).parent.parent / "VERSION",  # mission-control/VERSION (dev)
    ]
    if getattr(sys, "frozen", False):
        candidates.insert(0, Path(sys._MEIPASS) / "VERSION")
    for p in candidates:
        if p.exists():
            return p.read_text().strip()
    return "unknown"


__version__ = _read_version()
