"""Codex backend using the official Python SDK and its model catalog."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
import tempfile
from typing import Any

from openai_codex import ApprovalMode, Codex as CodexClient, Sandbox
from openai_codex.generated.v2_all import ReasoningEffort, TurnStatus

from .base import Backend
from .config import CodexConfig


class Codex(Backend[CodexConfig]):
    def __init__(self, config: CodexConfig) -> None:
        self._client = CodexClient()
        self._executor = ThreadPoolExecutor()
        self._model = None
        try:
            super().__init__(config)
        except BaseException:
            self.close()
            raise

    def is_model_valid(self) -> bool:
        self._ensure_open()
        catalog = self._client.models(include_hidden=True)
        self._model = next((model for model in catalog.data
                            if model.model == self.config.model_name), None)
        if self._model is None and catalog.next_cursor is not None:
            raise RuntimeError("Codex returned an incomplete model catalog")
        return self._model is not None

    def is_config_valid(self) -> bool:
        if not self.is_model_valid():
            return False
        supported = [option.reasoning_effort for option in self._model.supported_reasoning_efforts]
        if self.config.reasoning_effort not in supported:
            raise ValueError(
                f"Unsupported reasoning {self.config.reasoning_effort!r} for "
                f"{self.config.model_name}; supported: {', '.join(supported)}"
            )
        return True

    def execute(
        self, prompt: str, *, system_prompt: str = "", schema: dict[str, Any] | None = None,
    ) -> str:
        self._ensure_open()
        future = self._executor.submit(self._execute, prompt, system_prompt, schema)
        try:
            return future.result(timeout=self.config.timeout)
        except FutureTimeout:
            # Closing the transport unblocks pending SDK calls, including concurrent turns.
            self.close()
            raise TimeoutError(f"Codex exceeded {self.config.timeout:g} seconds") from None

    def _execute(self, prompt, system_prompt, schema) -> str:
        with tempfile.TemporaryDirectory() as directory:
            thread = self._client.thread_start(
                model=self.config.model_name, cwd=directory, ephemeral=True,
                sandbox=Sandbox.read_only, approval_mode=ApprovalMode.deny_all,
                developer_instructions=system_prompt + "\nRespond without using tools or inspecting files.",
            )
            result = thread.run(
                prompt, effort=ReasoningEffort(self.config.reasoning_effort), output_schema=schema,
            )
        if result.status != TurnStatus.completed:
            raise RuntimeError(f"Codex turn did not complete: {result.status.value}")
        if not result.final_response or not result.final_response.strip():
            raise ValueError("Empty LLM response")
        return result.final_response

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            try:
                self._client.close()
            finally:
                self._executor.shutdown(wait=False, cancel_futures=True)
