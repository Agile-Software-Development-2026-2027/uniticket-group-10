"""OpenAI-compatible backend using the official HTTP SDK."""

import os
from typing import Any

from openai import OpenAI as OpenAIClient

from .base import Backend
from .config import OpenAIConfig


class OpenAI(Backend[OpenAIConfig]):
    def __init__(self, config: OpenAIConfig, *, client: OpenAIClient | None = None) -> None:
        self._owns_client = client is None
        if client is None:
            api_key = "lm-studio"
            if config.api_key_env is not None:
                api_key = os.environ.get(config.api_key_env)
                if not api_key:
                    raise ValueError(f"Variabile d'ambiente {config.api_key_env} mancante o vuota")
            client = OpenAIClient(base_url=config.endpoint, api_key=api_key, timeout=config.timeout)
        self._client = client
        try:
            super().__init__(config)
        except BaseException:
            self.close()
            raise

    def is_model_valid(self) -> bool:
        self._ensure_open()
        return any(model.id == self.config.model_name for model in self._client.models.list())

    def execute(
        self, prompt: str, *, system_prompt: str = "", schema: dict[str, Any] | None = None,
    ) -> str:
        self._ensure_open()
        parameters = {
            name: getattr(self.config, name)
            for name in ("temperature", "top_p", "max_tokens")
            if getattr(self.config, name) is not None
        }
        parameters["reasoning_effort"] = self.config.reasoning_effort
        if self.config.top_k is not None:
            parameters["extra_body"] = {"top_k": self.config.top_k}
        if self.config.penalize is not None:
            parameters.update(self.config.penalize.model_dump(exclude_none=True))
        if schema is not None:
            parameters["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "response", "strict": True, "schema": schema},
            }
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        response = self._client.chat.completions.create(
            model=self.config.model_name, messages=messages, **parameters,
        )
        if not response.choices:
            raise ValueError("Empty LLM response: no choices")
        choice = response.choices[0]
        if choice.message.refusal:
            raise ValueError(f"LLM refused the request: {choice.message.refusal}")
        if choice.finish_reason != "stop":
            raise ValueError(f"Incomplete LLM response: {choice.finish_reason}")
        if not choice.message.content or not choice.message.content.strip():
            raise ValueError("Empty LLM response")
        return choice.message.content

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            if self._owns_client:
                self._client.close()
