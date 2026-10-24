"""Reusable backends: configuration, catalog validation and text generation."""

from pathlib import Path

from .base import Backend
from .config import Config, CodexConfig, OpenAIConfig, Penalties, load_config
from .codex import Codex
from .openai import OpenAI


def create_backend(config: Config | str | Path) -> Backend:
    """Create and validate a backend from parameters or a YAML file."""
    if isinstance(config, (str, Path)):
        config = load_config(config)
    if isinstance(config, CodexConfig):
        return Codex(config)
    if isinstance(config, OpenAIConfig):
        return OpenAI(config)
    raise TypeError(f"Unsupported backend configuration: {type(config).__name__}")


__all__ = ["Backend", "Config", "CodexConfig", "OpenAIConfig", "Penalties",
           "Codex", "OpenAI", "create_backend", "load_config"]
