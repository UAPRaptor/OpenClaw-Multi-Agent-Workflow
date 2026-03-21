"""
OpenClaw Vault — Encrypted credential storage for agents.

Secrets are encrypted at rest using Fernet (AES-128-CBC + HMAC-SHA256).
The encryption key is derived from a user-supplied passphrase via PBKDF2
with a random salt (stored alongside the encrypted data).

Storage layout:
    ~/.openclaw/vault/
        salt            — 16-byte PBKDF2 salt (created once)
        secrets.enc     — Fernet-encrypted JSON blob

Internal JSON format:
    {"secrets": {"KEY": "value", ...},
     "deleted": [{"name": "OLD_KEY", "value": "old_val", "deleted_at": "ISO8601"}, ...]}

Agents retrieve secrets at runtime via the Mission Control API:
    GET  /api/vault/list           — list secret names (no values)
    GET  /api/vault/get/{name}     — retrieve a single secret value
    POST /api/vault/store          — store a secret  {name, value}
    POST /api/vault/delete         — soft-delete a secret {name}
    GET  /api/vault/deleted        — list deleted secrets (recoverable)
    POST /api/vault/recover        — recover a deleted secret {name}
    POST /api/vault/purge          — permanently delete from archive {name}
    POST /api/vault/unlock         — unlock vault for session {passphrase}
    POST /api/vault/lock           — lock vault immediately
    GET  /api/vault/status         — is vault unlocked?

Design principles:
    - Secrets NEVER written to plaintext files, logs, or agent memory
    - Vault must be unlocked (passphrase) once per MC session
    - Passphrase is not stored — only used to derive the Fernet key
    - Salt is unique per installation (regenerated on first init)
    - Deleted secrets are archived — recoverable until purged
"""

import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


VAULT_DIR = Path.home() / ".openclaw" / "vault"
SALT_FILE = VAULT_DIR / "salt"
SECRETS_FILE = VAULT_DIR / "secrets.enc"

# Number of PBKDF2 iterations — high enough to resist brute-force,
# low enough to not annoy the user on unlock (~0.3 s on M4).
_KDF_ITERATIONS = 480_000


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    """Derive a 32-byte Fernet key from passphrase + salt."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_KDF_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def _load_salt() -> bytes:
    """Load or create the PBKDF2 salt."""
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    if SALT_FILE.exists():
        return SALT_FILE.read_bytes()
    salt = os.urandom(16)
    SALT_FILE.write_bytes(salt)
    return salt


class Vault:
    """Encrypted secret store.  Must be unlocked before use."""

    def __init__(self) -> None:
        self._fernet: Fernet | None = None
        self._secrets: dict[str, str] = {}
        self._deleted: list[dict] = []
        self._unlocked = False

    # ── Public API ────────────────────────────────────────────────────────

    @property
    def is_unlocked(self) -> bool:
        return self._unlocked

    @property
    def is_initialized(self) -> bool:
        """True if a vault has been created (salt + secrets file exist)."""
        return SALT_FILE.exists()

    def init(self, passphrase: str) -> None:
        """Create a brand-new vault with the given passphrase."""
        if SECRETS_FILE.exists():
            raise VaultError("Vault already exists. Use unlock() to open it.")
        salt = _load_salt()
        key = _derive_key(passphrase, salt)
        self._fernet = Fernet(key)
        self._secrets = {}
        self._deleted = []
        self._persist()
        self._unlocked = True

    def unlock(self, passphrase: str) -> None:
        """Unlock an existing vault for this session."""
        if not SECRETS_FILE.exists():
            self.init(passphrase)
            return
        salt = _load_salt()
        key = _derive_key(passphrase, salt)
        fernet = Fernet(key)
        try:
            decrypted = fernet.decrypt(SECRETS_FILE.read_bytes())
            raw = json.loads(decrypted.decode("utf-8"))
        except InvalidToken:
            raise VaultError("Wrong passphrase.")
        except json.JSONDecodeError:
            raise VaultError("Vault data corrupted.")
        # Backward-compat: old vaults stored a flat dict of secrets
        if isinstance(raw, dict) and "secrets" in raw:
            self._secrets = raw["secrets"]
            self._deleted = raw.get("deleted", [])
        else:
            # Legacy flat dict format
            self._secrets = raw if isinstance(raw, dict) else {}
            self._deleted = []
        self._fernet = fernet
        self._unlocked = True

    def lock(self) -> None:
        """Lock the vault — clears the in-memory key and secrets."""
        self._fernet = None
        self._secrets = {}
        self._deleted = []
        self._unlocked = False

    def store(self, name: str, value: str) -> None:
        """Store (or overwrite) a named secret."""
        self._require_unlocked()
        self._secrets[name] = value
        self._persist()

    def get(self, name: str) -> str:
        """Retrieve a secret by name.  Raises KeyError if not found."""
        self._require_unlocked()
        if name not in self._secrets:
            raise KeyError(f"Secret '{name}' not found in vault.")
        return self._secrets[name]

    def delete(self, name: str) -> bool:
        """Soft-delete a secret — moves it to the deleted archive.
        Returns True if it existed."""
        self._require_unlocked()
        if name in self._secrets:
            self._deleted.append({
                "name": name,
                "value": self._secrets[name],
                "deleted_at": datetime.now(tz=timezone.utc).isoformat(),
            })
            del self._secrets[name]
            self._persist()
            return True
        return False

    def list_names(self) -> list[str]:
        """List all active secret names (no values)."""
        self._require_unlocked()
        return sorted(self._secrets.keys())

    def list_deleted(self) -> list[dict]:
        """List deleted secrets (name + deleted_at, no values)."""
        self._require_unlocked()
        return [{"name": d["name"], "deleted_at": d["deleted_at"]} for d in self._deleted]

    def recover(self, name: str) -> bool:
        """Recover the most recently deleted secret with this name.
        Returns True if found and recovered."""
        self._require_unlocked()
        # Find the most recent deleted entry with this name
        for i in range(len(self._deleted) - 1, -1, -1):
            if self._deleted[i]["name"] == name:
                entry = self._deleted.pop(i)
                self._secrets[name] = entry["value"]
                self._persist()
                return True
        return False

    def purge(self, name: str) -> int:
        """Permanently remove all deleted entries with this name.
        Returns the number of entries purged."""
        self._require_unlocked()
        before = len(self._deleted)
        self._deleted = [d for d in self._deleted if d["name"] != name]
        removed = before - len(self._deleted)
        if removed > 0:
            self._persist()
        return removed

    # ── Internal ──────────────────────────────────────────────────────────

    def _require_unlocked(self) -> None:
        if not self._unlocked or self._fernet is None:
            raise VaultError("Vault is locked. Unlock it first.")

    def _persist(self) -> None:
        """Encrypt and write secrets to disk."""
        VAULT_DIR.mkdir(parents=True, exist_ok=True)
        data = {"secrets": self._secrets, "deleted": self._deleted}
        plaintext = json.dumps(data).encode("utf-8")
        self._fernet: Fernet  # type: ignore[annotation-unchecked]
        encrypted = self._fernet.encrypt(plaintext)
        SECRETS_FILE.write_bytes(encrypted)


class VaultError(Exception):
    """Raised for vault-related errors (locked, wrong passphrase, etc.)."""
