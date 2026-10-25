from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
import threading
import tempfile
import unittest
from unittest.mock import Mock, create_autospec, patch

from openai import OpenAI as OpenAIClient
from openai.types.chat import ChatCompletion
from openai_codex import Codex as CodexClient, Thread, TurnResult, ApprovalMode, Sandbox
from openai_codex.generated.v2_all import ModelListResponse, TurnStatus

from dataset.backends import Backend, Config, Codex, CodexConfig, OpenAI, OpenAIConfig, create_backend


SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}},
          "required": ["text"], "additionalProperties": False}


def completion(content='{"text":"ok"}', *, finish_reason="stop", refusal=None):
    return ChatCompletion.model_validate({
        "id": "response", "object": "chat.completion", "created": 0, "model": "model",
        "choices": [{"index": 0, "finish_reason": finish_reason,
                     "message": {"role": "assistant", "content": content, "refusal": refusal}}],
    })


def catalog(name="model", efforts=("low", "none")):
    return ModelListResponse.model_validate({"data": [{
        "id": name, "model": name, "displayName": name, "description": "Test model",
        "hidden": False, "isDefault": True, "defaultReasoningEffort": "low",
        "supportedReasoningEfforts": [{"reasoningEffort": value, "description": value}
                                      for value in efforts],
    }]})


def turn_result(content='{"text":"ok"}', status=TurnStatus.completed):
    return TurnResult(id="turn", status=status, error=None, started_at=None, completed_at=None,
                      duration_ms=None, final_response=content, items=[], usage=None)


class OpenAITests(unittest.TestCase):
    def setUp(self):
        self.client = Mock(spec=OpenAIClient)
        self.client.models = Mock()
        self.client.models.list.return_value = [SimpleNamespace(id="model")]
        self.client.chat = Mock()
        self.client.chat.completions.create.return_value = completion()

    def test_model_is_validated_once_and_backend_is_reusable(self):
        with OpenAI(OpenAIConfig(model_name="model"), client=self.client) as backend:
            for _ in range(2):
                self.assertEqual(backend.execute("hello"), '{"text":"ok"}')
        self.client.models.list.assert_called_once()
        self.client.close.assert_not_called()
        with self.assertRaisesRegex(RuntimeError, "closed"):
            backend.execute("hello")

    def test_request_preserves_all_openai_parameters_and_schema(self):
        config = OpenAIConfig(model_name="model", reasoning=False, max_tokens=8000,
                              temperature=0, top_p=0, top_k=0,
                              penalize={"frequency_penalty": 0.6, "presence_penalty": 0.2})
        with OpenAI(config, client=self.client) as backend:
            backend.execute("input", system_prompt="instructions", schema=SCHEMA)
        request = self.client.chat.completions.create.call_args.kwargs
        self.assertEqual(request["model"], "model")
        self.assertEqual(request["reasoning_effort"], "none")
        self.assertEqual(request["max_tokens"], 8000)
        self.assertEqual(request["temperature"], 0)
        self.assertEqual(request["top_p"], 0)
        self.assertEqual(request["extra_body"], {"top_k": 0})
        self.assertEqual(request["frequency_penalty"], 0.6)
        self.assertEqual(request["presence_penalty"], 0.2)
        self.assertEqual(request["messages"], [{"role": "system", "content": "instructions"},
                                               {"role": "user", "content": "input"}])
        self.assertEqual(request["response_format"]["json_schema"]["schema"], SCHEMA)

    def test_optional_request_parameters_are_omitted(self):
        with OpenAI(OpenAIConfig(model_name="model", reasoning="custom", max_tokens=None),
                    client=self.client) as backend:
            backend.execute("input")
        request = self.client.chat.completions.create.call_args.kwargs
        for key in ("response_format", "temperature", "top_p", "extra_body", "max_tokens",
                    "frequency_penalty", "presence_penalty"):
            self.assertNotIn(key, request)
        self.assertEqual(request["reasoning_effort"], "custom")

    def test_unknown_model_and_connection_failure_stop_initialization(self):
        self.client.models.list.return_value = []
        with self.assertRaisesRegex(ValueError, "Model unavailable"):
            OpenAI(OpenAIConfig(model_name="missing"), client=self.client)
        self.client.models.list.side_effect = ConnectionError("offline")
        with self.assertRaisesRegex(ConnectionError, "offline"):
            OpenAI(OpenAIConfig(model_name="model"), client=self.client)
        self.client.chat.completions.create.assert_not_called()

    def test_owned_client_uses_auth_and_is_closed_on_validation_failure(self):
        config = OpenAIConfig(model_name="model", api_key_env="CUSTOM_KEY", timeout=30)
        with patch("dataset.backends.openai.OpenAIClient", return_value=self.client) as create, \
             patch.dict("os.environ", {"CUSTOM_KEY": "test-key"}, clear=True):
            with OpenAI(config):
                pass
            create.assert_called_once_with(base_url=config.endpoint, api_key="test-key", timeout=30)
            self.client.close.assert_called_once()
            self.client.close.reset_mock()
            self.client.models.list.return_value = []
            with self.assertRaises(ValueError):
                OpenAI(config)
            self.client.close.assert_called_once()
        with patch("dataset.backends.openai.OpenAIClient") as create, patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "CUSTOM_KEY"):
                OpenAI(config)
            create.assert_not_called()

    def test_incomplete_refused_and_empty_responses_are_rejected(self):
        with OpenAI(OpenAIConfig(model_name="model"), client=self.client) as backend:
            for response in (completion(finish_reason="length"), completion(refusal="Cannot comply"),
                             completion(content=None), completion(content=" "),
                             completion().model_copy(update={"choices": []})):
                self.client.chat.completions.create.return_value = response
                with self.subTest(response=response), self.assertRaises(ValueError):
                    backend.execute("input")
            self.client.chat.completions.create.side_effect = ConnectionError("offline")
            with self.assertRaises(ConnectionError):
                backend.execute("input")


class CodexTests(unittest.TestCase):
    def setUp(self):
        self.client = create_autospec(CodexClient, instance=True)
        self.client.models.return_value = catalog()
        self.thread = create_autospec(Thread, instance=True)
        self.thread.run.return_value = turn_result()
        self.client.thread_start.return_value = self.thread
        factory = patch("dataset.backends.codex.CodexClient", return_value=self.client)
        self.factory = factory.start()
        self.addCleanup(factory.stop)
        self.config = CodexConfig(model_name="model", reasoning="low")

    def test_catalog_validation_rejects_model_and_reasoning_before_turn(self):
        for config in (CodexConfig(model_name="missing", reasoning="low"),
                       CodexConfig(model_name="model", reasoning="unsupported")):
            self.client.close.reset_mock()
            with self.subTest(config=config), self.assertRaises(ValueError):
                Codex(config)
            self.client.close.assert_called_once()
        self.client.thread_start.assert_not_called()

    def test_incomplete_catalog_and_connection_errors_are_not_invalid_models(self):
        self.client.models.return_value = ModelListResponse(data=[], next_cursor="next-page")
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            Codex(self.config)
        self.client.models.side_effect = ConnectionError("offline")
        with self.assertRaises(ConnectionError):
            Codex(self.config)
        self.assertEqual(self.client.close.call_count, 2)

    def test_execute_uses_sdk_schema_and_isolated_threads(self):
        directories = []
        with Codex(self.config) as backend:
            for _ in range(2):
                self.assertEqual(backend.execute("input", system_prompt="instructions", schema=SCHEMA),
                                 '{"text":"ok"}')
                request = self.client.thread_start.call_args.kwargs
                directories.append(request["cwd"])
                self.assertEqual(request["model"], "model")
                self.assertTrue(request["ephemeral"])
                self.assertEqual(request["sandbox"], Sandbox.read_only)
                self.assertEqual(request["approval_mode"], ApprovalMode.deny_all)
                self.assertIn("instructions", request["developer_instructions"])
                self.assertFalse(Path(request["cwd"]).exists())
            self.thread.run.assert_called_with("input", effort="low", output_schema=SCHEMA)
        self.assertNotEqual(*directories)
        self.client.models.assert_called_once_with(include_hidden=True)
        self.client.close.assert_called_once()

    def test_false_maps_to_none_and_is_checked_against_catalog(self):
        with Codex(CodexConfig(model_name="model", reasoning=False)) as backend:
            backend.execute("input")
        self.thread.run.assert_called_with("input", effort="none", output_schema=None)
        self.client.models.return_value = catalog(efforts=("low",))
        with self.assertRaisesRegex(ValueError, "Unsupported reasoning 'none'"):
            Codex(CodexConfig(model_name="model", reasoning=False))

    def test_incomplete_and_empty_turns_are_rejected(self):
        with Codex(self.config) as backend:
            for result in (turn_result(status=TurnStatus.interrupted), turn_result(content=None)):
                self.thread.run.return_value = result
                with self.assertRaises((RuntimeError, ValueError)):
                    backend.execute("input")
            self.thread.run.side_effect = RuntimeError("SDK failure")
            with self.assertRaisesRegex(RuntimeError, "SDK failure"):
                backend.execute("input")

    def test_timeout_closes_runtime_and_backend_cannot_be_reused(self):
        stopped = threading.Event()
        finished = threading.Event()
        self.client.close.side_effect = stopped.set

        def run(*args, **kwargs):
            try:
                stopped.wait(2)
                raise RuntimeError("Transport closed")
            finally:
                finished.set()

        self.thread.run.side_effect = run
        with Codex(CodexConfig(model_name="model", reasoning="low", timeout=0.02)) as backend:
            with self.assertRaises(TimeoutError):
                backend.execute("input")
            self.assertTrue(finished.wait(1))
            with self.assertRaisesRegex(RuntimeError, "closed"):
                backend.execute("input")
        self.client.close.assert_called_once()

    def test_concurrent_executions_use_separate_threads(self):
        barrier = threading.Barrier(2, timeout=2)

        def thread_start(**kwargs):
            thread = create_autospec(Thread, instance=True)
            def run(prompt, **options):
                barrier.wait()
                return turn_result(content=prompt)
            thread.run.side_effect = run
            return thread

        self.client.thread_start.side_effect = thread_start
        with Codex(self.config) as backend, ThreadPoolExecutor(max_workers=2) as executor:
            self.assertEqual(list(executor.map(backend.execute, ["first", "second"])), ["first", "second"])
        self.assertEqual(self.client.thread_start.call_count, 2)


class FactoryTests(unittest.TestCase):
    def test_factory_builds_the_selected_backend_from_yaml(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "backend.yaml"
            path.write_text("backend: codex\ncodex:\n  model_name: example\n  reasoning: low\n")
            with patch("dataset.backends.Codex") as codex, patch("dataset.backends.OpenAI") as openai:
                for source in (path, str(path)):
                    self.assertIs(create_backend(source), codex.return_value)
                codex.assert_called_with(CodexConfig(model_name="example", reasoning="low"))
                openai.assert_not_called()
                codex.reset_mock()
                path.write_text("backend: codex\ncodex: {}\n")
                with self.assertRaises(ValueError):
                    create_backend(path)
                codex.assert_not_called()

    def test_factory_dispatches_configuration_type(self):
        with patch("dataset.backends.Codex") as codex, patch("dataset.backends.OpenAI") as openai:
            codex_config = CodexConfig(model_name="model", reasoning="low")
            openai_config = OpenAIConfig(model_name="model")
            self.assertIs(create_backend(codex_config), codex.return_value)
            self.assertIs(create_backend(openai_config), openai.return_value)
            codex.assert_called_once_with(codex_config)
            openai.assert_called_once_with(openai_config)
            with self.assertRaises(TypeError):
                create_backend(Config(model_name="model"))
        with self.assertRaises(TypeError):
            Backend(Config(model_name="model"))
