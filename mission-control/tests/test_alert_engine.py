"""Tests for the alert engine."""
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from openclaw.monitor.alert_engine import AlertEngine, STALL_MAX_AGE_MINUTES
from openclaw.monitor.state_store import StateStore


@pytest.fixture
def tmp_workspace(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


@pytest.fixture
def store(tmp_workspace):
    with patch("openclaw.monitor.state_store._monitor_dir", return_value=tmp_workspace):
        return StateStore(tmp_workspace)


@pytest.fixture
def engine(tmp_workspace, store):
    return AlertEngine(tmp_workspace, store)


def test_settings_change_alert(engine, store, tmp_workspace):
    settings_dir = tmp_workspace / ".claude"
    settings_dir.mkdir()
    settings_file = settings_dir / "settings.json"
    settings_file.write_text("{}")
    engine.check_file_event(str(settings_file))
    state = store.get()
    alerts = [a for a in state["alerts"] if a["level"] == "security"]
    assert len(alerts) >= 1


def test_stall_max_age():
    """Stall alerts should have a max age cap."""
    assert STALL_MAX_AGE_MINUTES == 60 * 24  # 24 hours
