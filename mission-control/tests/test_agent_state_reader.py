"""Tests for agent state reader."""
from pathlib import Path
from datetime import datetime, timezone

import pytest

from openclaw.monitor.agent_state_reader import (
    infer_activity_message,
    read_active_project,
    read_project_status,
    read_tickets,
    parse_agent_characters,
    _infer_ticket_type,
    TICKET_STATES,
    TICKET_TYPES,
)


def test_infer_activity_message():
    assert "bug ticket" in infer_activity_message("tickets/open/BUG-001.md").lower()
    assert "feature" in infer_activity_message("tickets/open/FEAT-001.md").lower()
    assert "implementation plan" in infer_activity_message("implementation-plan.md").lower()
    assert "SECURITY" in infer_activity_message(".claude/settings.json")


def test_infer_activity_fallback():
    msg = infer_activity_message("some-random-file.txt")
    assert "some-random-file.txt" in msg


def test_read_active_project(tmp_path):
    active_file = tmp_path / "active-project.md"
    active_file.write_text("Active Project: my-app\nProject Path: projects/my-app\n")
    result = read_active_project(tmp_path)
    assert result is not None
    assert result["name"] == "my-app"
    assert result["path"] == "projects/my-app"


def test_read_active_project_missing(tmp_path):
    result = read_active_project(tmp_path)
    assert result is None


def test_read_project_status(tmp_path):
    project = tmp_path / "projects" / "test"
    project.mkdir(parents=True)
    status = project / "status.md"
    status.write_text("Active Milestone: Milestone 2\n\n| 1 — Setup | Done |\n| 2 — Build | In progress |\n")
    result = read_project_status(tmp_path, "projects/test")
    assert result["milestone_current"] == 2
    assert result["milestone_total"] == 2


def test_read_project_status_missing(tmp_path):
    result = read_project_status(tmp_path, "projects/nonexistent")
    assert result["name"] == "nonexistent"
    assert result["milestone_current"] is None


def test_read_tickets(tmp_path):
    project = tmp_path / "projects" / "test"
    open_dir = project / "tickets" / "open"
    closed_dir = project / "tickets" / "closed"
    open_dir.mkdir(parents=True)
    closed_dir.mkdir(parents=True)

    # Create test tickets
    (open_dir / "BUG-001.md").write_text(
        "# BUG-001: Test bug\n\n**Status:** in-progress\n**Severity:** D2\n\n## Description\nA test bug\n"
    )
    (open_dir / "FEAT-001.md").write_text(
        "# FEAT-001: New feature\n\n**Status:** proposed\n"
    )
    (closed_dir / "BUG-002.md").write_text(
        "# BUG-002: Fixed bug\n\n**Status:** passed\n"
    )

    counts = read_tickets(tmp_path, "projects/test")
    assert counts["in-progress"] == 1
    assert counts["proposed"] == 1
    assert counts["passed"] == 1
    assert counts["ready"] == 0
    # Details should include title and severity
    details = counts["_details"]
    assert len(details["in-progress"]) == 1
    assert details["in-progress"][0]["title"] == "BUG-001: Test bug"
    assert details["in-progress"][0]["severity"] == "D2"


def test_read_tickets_empty(tmp_path):
    counts = read_tickets(tmp_path, "projects/nonexistent")
    for state in TICKET_STATES:
        assert counts[state] == 0


def test_parse_agent_characters(tmp_path):
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text(
        "# Team\n\n### Project Manager\n**Character:** Splinter\n\n### Builder / Developer\n**Character:** Donatello\n"
    )
    chars = parse_agent_characters(tmp_path)
    assert chars.get("pm") == "Splinter"
    assert chars.get("builder") == "Donatello"


def test_parse_agent_characters_missing(tmp_path):
    chars = parse_agent_characters(tmp_path)
    assert chars == {}


def test_infer_ticket_type_from_field():
    content = "# BUG-001\n\n**Type:** BUG\n**Status:** proposed\n"
    assert _infer_ticket_type("BUG-001.md", content) == "BUG"


def test_infer_ticket_type_from_filename():
    content = "# TASK-001\n\n**Status:** proposed\n"
    assert _infer_ticket_type("TASK-001.md", content) == "TASK"


def test_infer_ticket_type_default():
    content = "# something\n\n**Status:** proposed\n"
    assert _infer_ticket_type("random.md", content) == "TASK"


def test_ticket_types_constant():
    assert set(TICKET_TYPES) == {"BUG", "FEAT", "TASK", "QUESTION", "EPIC"}


def test_read_tickets_type_counts(tmp_path):
    project = tmp_path / "projects" / "test"
    open_dir = project / "tickets" / "open"
    open_dir.mkdir(parents=True)
    (project / "tickets" / "closed").mkdir(parents=True)

    (open_dir / "BUG-001.md").write_text(
        "# BUG-001: Bug\n\n**Type:** BUG\n**Status:** proposed\n**Severity:** D2\n"
    )
    (open_dir / "TASK-001.md").write_text(
        "# TASK-001: Task\n\n**Type:** TASK\n**Status:** proposed\n"
    )
    (open_dir / "FEAT-001.md").write_text(
        "# FEAT-001: Feature\n\n**Type:** FEAT\n**Status:** ready\n"
    )

    counts = read_tickets(tmp_path, "projects/test")
    tc = counts["_type_counts"]
    assert tc["BUG"] == 1
    assert tc["TASK"] == 1
    assert tc["FEAT"] == 1
    assert tc["EPIC"] == 0
    # Verify type is on details
    details = counts["_details"]
    assert details["proposed"][0]["type"] in ("BUG", "TASK")
    assert details["ready"][0]["type"] == "FEAT"
