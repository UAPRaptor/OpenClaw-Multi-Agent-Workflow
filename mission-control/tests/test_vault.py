"""Tests for the encrypted credential vault."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from openclaw.vault import Vault, VaultError


@pytest.fixture
def vault_dir(tmp_path):
    """Patch vault storage to a temp directory."""
    with patch("openclaw.vault.VAULT_DIR", tmp_path), \
         patch("openclaw.vault.SALT_FILE", tmp_path / "salt"), \
         patch("openclaw.vault.SECRETS_FILE", tmp_path / "secrets.enc"):
        yield tmp_path


def test_init_creates_vault(vault_dir):
    v = Vault()
    assert not v.is_initialized
    v.init("test-passphrase")
    assert v.is_unlocked
    assert (vault_dir / "salt").exists()
    assert (vault_dir / "secrets.enc").exists()


def test_store_and_retrieve(vault_dir):
    v = Vault()
    v.init("mypass")
    v.store("API_KEY", "sk-abc123")
    assert v.get("API_KEY") == "sk-abc123"


def test_list_names(vault_dir):
    v = Vault()
    v.init("mypass")
    v.store("B_TOKEN", "val1")
    v.store("A_TOKEN", "val2")
    assert v.list_names() == ["A_TOKEN", "B_TOKEN"]


def test_delete(vault_dir):
    v = Vault()
    v.init("mypass")
    v.store("TOKEN", "val")
    assert v.delete("TOKEN") is True
    assert v.delete("TOKEN") is False
    assert "TOKEN" not in v.list_names()


def test_lock_clears_state(vault_dir):
    v = Vault()
    v.init("mypass")
    v.store("TOKEN", "val")
    v.lock()
    assert not v.is_unlocked
    with pytest.raises(VaultError):
        v.get("TOKEN")


def test_unlock_existing_vault(vault_dir):
    # Create and lock
    v1 = Vault()
    v1.init("mypass")
    v1.store("SECRET", "hello")
    v1.lock()

    # Re-open with new instance
    v2 = Vault()
    v2.unlock("mypass")
    assert v2.get("SECRET") == "hello"


def test_wrong_passphrase_rejected(vault_dir):
    v = Vault()
    v.init("correct-pass")
    v.lock()

    v2 = Vault()
    with pytest.raises(VaultError, match="Wrong passphrase"):
        v2.unlock("wrong-pass")


def test_operations_require_unlock(vault_dir):
    v = Vault()
    with pytest.raises(VaultError, match="locked"):
        v.store("K", "V")
    with pytest.raises(VaultError, match="locked"):
        v.get("K")
    with pytest.raises(VaultError, match="locked"):
        v.list_names()


def test_overwrite_secret(vault_dir):
    v = Vault()
    v.init("pass")
    v.store("KEY", "old")
    v.store("KEY", "new")
    assert v.get("KEY") == "new"


def test_persistence_across_instances(vault_dir):
    """Secrets survive vault reopen."""
    v1 = Vault()
    v1.init("pass")
    v1.store("A", "1")
    v1.store("B", "2")
    v1.lock()

    v2 = Vault()
    v2.unlock("pass")
    assert v2.get("A") == "1"
    assert v2.get("B") == "2"


def test_soft_delete_archives(vault_dir):
    """Deleted secrets go to archive, not destroyed."""
    v = Vault()
    v.init("pass")
    v.store("TOKEN", "secret123")
    v.delete("TOKEN")
    assert "TOKEN" not in v.list_names()
    deleted = v.list_deleted()
    assert len(deleted) == 1
    assert deleted[0]["name"] == "TOKEN"
    assert "deleted_at" in deleted[0]


def test_recover_deleted_secret(vault_dir):
    """Recover restores a deleted secret to active."""
    v = Vault()
    v.init("pass")
    v.store("KEY", "val")
    v.delete("KEY")
    assert v.recover("KEY") is True
    assert v.get("KEY") == "val"
    assert len(v.list_deleted()) == 0


def test_recover_nonexistent_returns_false(vault_dir):
    v = Vault()
    v.init("pass")
    assert v.recover("NOPE") is False


def test_purge_permanently_deletes(vault_dir):
    """Purge removes from archive permanently."""
    v = Vault()
    v.init("pass")
    v.store("KEY", "val")
    v.delete("KEY")
    assert v.purge("KEY") == 1
    assert len(v.list_deleted()) == 0
    assert v.recover("KEY") is False


def test_deleted_archive_persists(vault_dir):
    """Deleted archive survives lock/unlock cycle."""
    v1 = Vault()
    v1.init("pass")
    v1.store("OLD", "data")
    v1.delete("OLD")
    v1.lock()

    v2 = Vault()
    v2.unlock("pass")
    deleted = v2.list_deleted()
    assert len(deleted) == 1
    assert deleted[0]["name"] == "OLD"
    assert v2.recover("OLD") is True
    assert v2.get("OLD") == "data"
