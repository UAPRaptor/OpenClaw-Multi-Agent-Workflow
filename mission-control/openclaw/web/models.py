"""
Pydantic request/response models for Mission Control API endpoints.
Provides schema validation at system boundaries.
"""
from pydantic import BaseModel, Field, field_validator
import re


class InstallRequest(BaseModel):
    target: str = ""
    theme: str = "historical"
    team_size: int = Field(default=4, ge=1, le=8)
    project_name: str = "example-app"
    operator_name: str = "Operator"
    install_mode: str = "new"
    model_strategic: str = "claude-sonnet-4-6"
    model_implementation: str = "claude-sonnet-4-6"
    model_support: str = "claude-sonnet-4-6"
    custom_characters: dict[str, str] | None = None

    @field_validator("install_mode")
    @classmethod
    def validate_install_mode(cls, v: str) -> str:
        if v not in ("new", "upgrade", "replace", "dashboard-only"):
            raise ValueError("install_mode must be new, upgrade, replace, or dashboard-only")
        return v

    @field_validator("theme")
    @classmethod
    def validate_theme(cls, v: str) -> str:
        if not re.match(r"^[a-z][a-z0-9_-]{0,30}$", v):
            raise ValueError("Invalid theme name")
        return v


class ChatSendRequest(BaseModel):
    agentId: str = Field(min_length=1, max_length=50)
    message: str = Field(min_length=1, max_length=100000)
    sessionId: str | None = None

    @field_validator("agentId")
    @classmethod
    def validate_agent_id(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Invalid agentId: only letters, numbers, hyphens, underscores")
        return v

    @field_validator("sessionId")
    @classmethod
    def validate_session_id(cls, v: str | None) -> str | None:
        if v is not None and not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Invalid sessionId format")
        return v


class AddAgentRequest(BaseModel):
    role: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=100)
    label: str = ""

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.match(r"^[a-z][a-z0-9-]{0,29}$", v):
            raise ValueError("Role ID must be lowercase letters/numbers/hyphens, 1-30 chars")
        return v


class AgentCleanupRequest(BaseModel):
    agentId: str = Field(min_length=1, max_length=50)
    action: str
    confirm: bool = False

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        if v not in ("archive", "unregister", "purge"):
            raise ValueError("action must be one of: archive, unregister, purge")
        return v


class ProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=50)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,49}$", v):
            raise ValueError("Invalid name: use letters, numbers, hyphens, underscores")
        return v


class BackupRestoreRequest(BaseModel):
    backup_id: str = Field(min_length=1, max_length=200)


class ConfigureProviderRequest(BaseModel):
    type: str = Field(min_length=1)
    key: str = Field(min_length=1, max_length=500)

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in ("openai-key", "openrouter-key"):
            raise ValueError(f"Unknown provider type: {v}")
        return v


class ReregisterRequest(BaseModel):
    path: str = Field(min_length=1)


class WorkspaceAgentDeleteRequest(BaseModel):
    path: str = Field(min_length=1)
    role: str = Field(min_length=1)
