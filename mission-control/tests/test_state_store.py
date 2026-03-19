"""Tests for the in-memory state store."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

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


def test_initial_state(store, tmp_workspace):
    state = store.get()
    assert state["workspace"] == str(tmp_workspace)
    assert state["agents"] == {}
    assert state["tickets"]["proposed"] == 0
    assert state["alerts"] == []
    assert state["activity"] == []


def test_update_merges(store):
    store.update({"agents": {"pm": {"status": "active"}}})
    state = store.get()
    assert state["agents"]["pm"]["status"] == "active"


def test_deep_merge(store):
    store.update({"project": {"name": "test"}})
    store.update({"project": {"milestone_current": 1}})
    state = store.get()
    assert state["project"]["name"] == "test"
    assert state["project"]["milestone_current"] == 1


def test_get_returns_deepcopy(store):
    store.update({"agents": {"pm": {"status": "active"}}})
    s1 = store.get()
    s1["agents"]["pm"]["status"] = "hacked"
    s2 = store.get()
    assert s2["agents"]["pm"]["status"] == "active"


def test_add_activity(store):
    store.add_activity("test.py", "File updated")
    state = store.get()
    assert len(state["activity"]) == 1
    assert state["activity"][0]["message"] == "File updated"
    assert state["activity"][0]["file"] == "test.py"


def test_activity_capped_at_50(store):
    for i in range(60):
        store.add_activity(f"file{i}.py", f"Update {i}")
    state = store.get()
    assert len(state["activity"]) == 50


def test_add_alert(store):
    store.add_alert("security", "Settings changed")
    state = store.get()
    assert len(state["alerts"]) == 1
    assert state["alerts"][0]["level"] == "security"
    assert state["alerts"][0]["dismissed"] is False


def test_dismiss_alert(store):
    store.add_alert("warning", "Agent stalled", alert_id="test-123")
    store.dismiss_alert("test-123")
    state = store.get()
    assert state["alerts"][0]["dismissed"] is True


def test_listener_called_on_update(store):
    received = []
    store.register_listener(lambda s: received.append(s))
    store.update({"agents": {"pm": {"status": "active"}}})
    assert len(received) == 1
    assert received[0]["agents"]["pm"]["status"] == "active"


def test_persist_creates_file(store, tmp_workspace):
    with patch("openclaw.monitor.state_store._monitor_dir", return_value=tmp_workspace):
        store.update({"project": {"name": "test"}})
    state_file = tmp_workspace / "state.json"
    assert state_file.exists()
    data = json.loads(state_file.read_text())
    assert data["project"]["name"] == "test"
