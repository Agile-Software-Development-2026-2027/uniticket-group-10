"""Reusable text-generation contract; no dataset or prompt dependencies."""

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from .config import Config


ConfigT = TypeVar("ConfigT", bound=Config)


class Backend(ABC, Generic[ConfigT]):
    def __init__(self, config: ConfigT) -> None:
        self.config = config
        self._closed = False
        if not self.is_config_valid():
            raise ValueError(f"Model unavailable in {type(self).__name__}: {config.model_name}")

    @abstractmethod
    def is_model_valid(self) -> bool:
        """Check the backend catalog; connection/authentication errors propagate."""

    def is_config_valid(self) -> bool:
        return self.is_model_valid()

    @abstractmethod
    def execute(
        self, prompt: str, *, system_prompt: str = "", schema: dict[str, Any] | None = None,
    ) -> str:
        """Generate text, optionally constrained by a JSON schema."""

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("Backend is closed")

    @abstractmethod
    def close(self) -> None:
        """Release owned resources after all executions have finished."""

    def __enter__(self):
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
