"""Backend parameters, validated without network access."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
import yaml


NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    model_name: NonEmptyText
    reasoning: NonEmptyText | Literal[False] = False
    timeout: float = Field(default=300, gt=0, allow_inf_nan=False)

    @field_validator("reasoning", mode="before")
    @classmethod
    def require_string_or_false(cls, value):
        # Literal[False] also matches numeric zero, even in Pydantic strict mode.
        if value is not False and not isinstance(value, str):
            raise ValueError("reasoning must be a non-empty string or false")
        return value

    @property
    def reasoning_effort(self) -> str:
        return "none" if self.reasoning is False else self.reasoning


class CodexConfig(Config):
    pass


class Penalties(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)


class OpenAIConfig(Config):
    endpoint: NonEmptyText = "http://localhost:1234/v1"
    api_key_env: NonEmptyText | None = None
    max_tokens: int | None = Field(default=5000, ge=1)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_k: int | None = Field(default=None, ge=0)
    top_p: float | None = Field(default=None, ge=0, le=1)
    penalize: Penalties | None = None


def load_config(path: str | Path) -> CodexConfig | OpenAIConfig:
    """Validate the YAML profiles offline and return the selected backend config."""
    with Path(path).open(encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    if not isinstance(data, dict):
        raise ValueError("Backend configuration must be a YAML mapping")
    unknown = set(data) - {"backend", "openai", "codex"}
    if unknown:
        raise ValueError(f"Unknown configuration fields: {unknown}")
    backend = data.get("backend", "openai")
    if backend not in ("openai", "codex"):
        raise ValueError("backend must be openai or codex")
    profiles = {
        name: config_type.model_validate(data[name])
        for name, config_type in (("openai", OpenAIConfig), ("codex", CodexConfig))
        if data.get(name) is not None
    }
    if backend not in profiles:
        raise ValueError(f"Missing configuration for backend: {backend}")
    return profiles[backend]
