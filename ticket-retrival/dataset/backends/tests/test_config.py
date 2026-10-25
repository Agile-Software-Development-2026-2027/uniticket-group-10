from pathlib import Path
import tempfile
import unittest

from pydantic import ValidationError

from dataset.backends import Config, CodexConfig, OpenAIConfig, load_config
import yaml


class ConfigTests(unittest.TestCase):
    def test_every_profile_requires_a_nonblank_model(self):
        for profile in (Config, CodexConfig, OpenAIConfig):
            for fields in ({}, {"model_name": None}, {"model_name": ""}, {"model_name": " \t\n"}):
                with self.subTest(profile=profile.__name__, fields=fields), self.assertRaises(ValidationError):
                    profile(**fields)
            self.assertEqual(profile(model_name=" model ").model_name, "model")

    def test_only_selected_profile_is_required(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            for backend, config_type in (("openai", OpenAIConfig), ("codex", CodexConfig)):
                path.write_text(yaml.safe_dump({"backend": backend, backend: {"model_name": "model"}}))
                self.assertIsInstance(load_config(path), config_type)
                path.write_text(yaml.safe_dump({"backend": backend}))
                with self.assertRaisesRegex(ValueError, "Missing configuration"):
                    load_config(path)
            path.write_text(yaml.safe_dump({"openai": {"model_name": "model"}, "codex": {}}))
            with self.assertRaises(ValidationError):
                load_config(path)

    def test_reasoning_accepts_nonempty_strings_or_false(self):
        for profile in (CodexConfig, OpenAIConfig):
            for reasoning in (False, "low", "max", "provider-specific"):
                settings = profile(model_name="model", reasoning=reasoning)
                self.assertEqual(settings.reasoning, reasoning)
                self.assertEqual(settings.reasoning_effort, "none" if reasoning is False else reasoning)
            for reasoning in (None, True, "", "   ", 42, 0):
                with self.subTest(reasoning=reasoning), self.assertRaises(ValidationError):
                    profile(model_name="model", reasoning=reasoning)

    def test_invalid_parameters_and_unknown_fields_are_rejected(self):
        for fields in ({"temperature": 3}, {"top_p": -0.1}, {"top_k": 1.5}, {"top_k": -1},
                       {"top_k": False}, {"temperature": "0.3"}, {"api_key_env": ""},
                       {"penalize": {"frequency_penalty": 3}}, {"penalize": {"presence_penalty": -3}},
                       {"penalize": {"unknown": 1}}, {"max_tokens": 0}, {"max_tokens": -1},
                       {"max_tokens": True}, {"max_tokens": "5000"}, {"timeout": 0},
                       {"model": "legacy"}, {"reasoning_effort": "legacy"}):
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                OpenAIConfig(model_name="model", **fields)
        for name in ("temperature", "top_p", "top_k", "max_tokens"):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                CodexConfig(model_name="model", **{name: 1})

    def test_config_cannot_change_after_backend_validation(self):
        settings = OpenAIConfig(model_name="model", penalize={"frequency_penalty": 0.1})
        with self.assertRaises(ValidationError):
            settings.model_name = "another-model"
        with self.assertRaises(ValidationError):
            settings.penalize.frequency_penalty = 3

    def test_yaml_loading_and_defaults(self):
        self.assertIsInstance(load_config(Path(__file__).resolve().parents[2] / "generate.yaml"), CodexConfig)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text("backend: codex\ncodex:\n  model_name: example\n  reasoning: low\n")
            settings = load_config(path)
            self.assertIsInstance(settings, CodexConfig)
            self.assertEqual(settings.reasoning, "low")
            for content in ("", "- model", "typo: value", "backend: unknown", "backend: []",
                            "backend: openai\nopenai:\n  model_name: null"):
                path.write_text(content)
                with self.subTest(content=content), self.assertRaises(ValueError):
                    load_config(path)
        settings = OpenAIConfig(model_name="model")
        self.assertIs(settings.reasoning, False)
        self.assertIsNone(settings.top_k)
        self.assertIsNone(settings.top_p)
        self.assertIsNone(settings.penalize)
