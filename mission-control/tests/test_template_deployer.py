"""Tests for workspace template deployment."""
from pathlib import Path

import pytest

from openclaw.installer.template_deployer import (
    ROLE_LABELS,
    ROLE_GROUP,
    ROLE_CHAIN,
    ROLE_METHODOLOGY,
    build_agent_list,
    load_character_theme,
    deploy_workspace_files,
    deploy_project_files,
)


def test_role_labels_complete():
    """All defined roles should have a label."""
    expected = {"pm", "architect", "builder", "qa", "security", "devops", "ux", "research", "graphics"}
    assert set(ROLE_LABELS.keys()) == expected


def test_role_group_complete():
    """All defined roles should have a capability group."""
    for role in ROLE_LABELS:
        assert role in ROLE_GROUP, f"Missing ROLE_GROUP for {role}"


def test_role_chain_complete():
    """All defined roles should have a chain entry."""
    for role in ROLE_LABELS:
        assert role in ROLE_CHAIN, f"Missing ROLE_CHAIN for {role}"
        assert "receives_from" in ROLE_CHAIN[role]
        assert "hands_to" in ROLE_CHAIN[role]


def test_load_character_theme():
    data = load_character_theme("tmnt")
    assert "label" in data
    assert "roles" in data
    assert "pm" in data["roles"]


def test_load_character_theme_fallback():
    """Unknown theme falls back to historical."""
    data = load_character_theme("nonexistent_theme_xyz")
    assert data["label"] is not None


def test_build_agent_list_minimal():
    theme_data = load_character_theme("historical")
    model_map = {"strategic": "test-model", "implementation": "test-model", "support": "test-model"}
    agents = build_agent_list(["pm", "architect", "builder", "qa"], theme_data, model_map)
    assert len(agents) == 4
    for a in agents:
        assert "agentId" in a
        assert "displayName" in a
        assert "role_label" in a
        assert "model" in a
        assert a["model"] == "test-model"


def test_build_agent_list_custom_characters():
    theme_data = load_character_theme("tmnt")
    model_map = {"strategic": "m", "implementation": "m", "support": "m"}
    custom = {"pm": "CustomPM"}
    agents = build_agent_list(["pm"], theme_data, model_map, custom_characters=custom)
    assert agents[0]["displayName"] == "CustomPM"
    assert agents[0]["character"] == "CustomPM"


def test_deploy_workspace_files(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    written, agents, team_name = deploy_workspace_files(ws, "tmnt", 4, "Tester", "test-project")
    assert len(written) > 0
    assert (ws / "AGENTS.md").exists()
    assert (ws / "SOUL.md").exists()
    assert (ws / "IDENTITY.md").exists()
    assert len(agents) == 4


def test_deploy_workspace_files_upgrade_preserves_memory(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    # First install
    deploy_workspace_files(ws, "tmnt", 4, install_mode="new")
    # Write custom content to MEMORY.md
    (ws / "MEMORY.md").write_text("My custom memory")
    # Upgrade
    deploy_workspace_files(ws, "tmnt", 4, install_mode="upgrade")
    assert (ws / "MEMORY.md").read_text() == "My custom memory"


def test_deploy_project_files(tmp_path):
    project = tmp_path / "test-project"
    project.mkdir()
    written = deploy_project_files(project, "test-project")
    assert len(written) > 0
    assert (project / "spec.md").exists()
    assert (project / "milestones.md").exists()
    assert (project / "status.md").exists()


def test_deploy_project_files_update_mode(tmp_path):
    project = tmp_path / "test-project"
    project.mkdir()
    deploy_project_files(project, "test-project")
    # Modify a file
    (project / "spec.md").write_text("Custom spec")
    # Update mode should preserve
    deploy_project_files(project, "test-project", update_mode=True)
    assert (project / "spec.md").read_text() == "Custom spec"


def test_methodology_exists_for_key_roles():
    """PM, QA, Security, Architect, Builder should have methodology."""
    for role in ["pm", "qa", "security", "architect", "builder"]:
        assert role in ROLE_METHODOLOGY, f"Missing methodology for {role}"
        assert len(ROLE_METHODOLOGY[role]) > 100, f"Methodology for {role} seems too short"
