import io
import json
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from pydantic import ValidationError

from dataset.generation import generate_queries as generator
from dataset.backends import Backend, OpenAIConfig
from dataset.generation.generate_queries import GeneratedQueries, Queries, TicketType, generate_queries


class GenerateQueriesTests(unittest.TestCase):
    def test_direct_script_imports_and_finds_config_without_pythonpath(self):
        script = Path(generator.__file__).resolve()
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([
                sys.executable, "-I", "-c",
                "import runpy, sys; data = runpy.run_path(sys.argv[1]); "
                "assert data['DEFAULT_CONFIG'].is_file(); assert data['PROMPT_PATH'].is_file()",
                str(script),
            ], cwd=directory, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def setUp(self):
        self.ticket = TicketType(title="Assistenza Moodle", description="Problemi di accesso",
                                 structure="Servizi informatici")
        self.queries = {
            "direct": ["Mi serve assistenza per Moodle", "Come accedo a Moodle?", "Aiuto con Moodle"],
            "paraphrase": ["Non riesco a entrare in Moodle", "Moodle non mi fa entrare", "Ho problemi col login Moodle"],
            "indirect": ["Devo vedere le lezioni ma non riesco a entrare",
                         "Non posso accedere ai materiali del corso", "Non riesco ad aprire il corso online"],
        }
        self.result = {"description_quality": "partially_informative", "queries": self.queries}
        self.content = json.dumps(self.result, ensure_ascii=False)

    def backend(self, content):
        backend = Mock(spec=Backend)
        backend.execute.return_value = content
        return backend

    def test_reusable_backend_receives_prompt_context_and_schema(self):
        backend = self.backend(self.content)
        result = generate_queries(self.ticket, backend=backend)
        self.assertEqual(result.model_dump(), self.result)
        request = backend.execute.call_args
        self.assertEqual(json.loads(request.args[0]), self.ticket.model_dump())
        self.assertEqual(request.kwargs["system_prompt"], generator.PROMPT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(request.kwargs["schema"], GeneratedQueries.model_json_schema())
        backend.close.assert_not_called()

    def test_prompt_is_reread_after_editing_the_file(self):
        backend = self.backend(self.content)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "GENERATION_PROMPT.md"
            with patch.object(generator, "PROMPT_PATH", path):
                for text in ("First saved prompt", "Second saved prompt"):
                    path.write_text(text, encoding="utf-8")
                    generate_queries(self.ticket, backend=backend)
                    self.assertEqual(backend.execute.call_args.kwargs["system_prompt"], text)

    def test_empty_prompt_stops_before_backend_initialization(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "GENERATION_PROMPT.md"
            with patch.object(generator, "PROMPT_PATH", path), \
                 patch.object(generator, "create_backend") as create:
                for text in ("", " \n\t"):
                    path.write_text(text, encoding="utf-8")
                    with self.subTest(text=text), self.assertRaisesRegex(ValueError, "prompt is empty"):
                        generate_queries(self.ticket)
                    with self.assertRaisesRegex(ValueError, "prompt is empty"):
                        generator.main()
                create.assert_not_called()

    def test_default_config_backend_is_owned_and_closed_on_failure(self):
        with patch.object(generator, "create_backend") as create:
            backend = create.return_value.__enter__.return_value
            backend.execute.return_value = self.content
            self.assertEqual(generate_queries(self.ticket).model_dump(), self.result)
            create.assert_called_once_with(generator.DEFAULT_CONFIG)
            create.return_value.__exit__.assert_called_once()
            backend.execute.side_effect = ConnectionError("Unavailable")
            with self.assertRaises(ConnectionError):
                generate_queries(self.ticket)
            self.assertEqual(create.return_value.__exit__.call_count, 2)

    def test_rejects_ambiguous_arguments_without_contacting_backend(self):
        backend = self.backend(self.content)
        with self.assertRaises(ValueError):
            generate_queries(self.ticket, backend=backend, config="unused.yaml")
        backend.execute.assert_not_called()

    def test_invalid_responses_are_rejected(self):
        for content in ("not json", "{}", json.dumps(dict(self.result, queries=dict(self.queries, direct=["Una sola"]))),
                        json.dumps(dict(self.result, extra="unexpected"))):
            with self.subTest(content=content), self.assertRaises(ValidationError):
                generate_queries(self.ticket, backend=self.backend(content))
        for content in (None, "", "  "):
            with self.subTest(content=content), self.assertRaisesRegex(ValueError, "Empty LLM response"):
                generate_queries(self.ticket, backend=self.backend(content))

    def test_description_quality_is_required_and_uses_supported_labels(self):
        for quality in ("informative", "partially_informative", "uninformative"):
            with self.subTest(quality=quality):
                content = json.dumps(dict(self.result, description_quality=quality))
                result = generate_queries(self.ticket, backend=self.backend(content))
                self.assertEqual(result.description_quality, quality)
        for fields in ({"queries": self.queries}, dict(self.result, description_quality="good")):
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                GeneratedQueries.model_validate(fields)


    def test_query_categories_are_required_and_cannot_be_null(self):
        for category in self.queries:
            for value in (None, []):
                with self.subTest(category=category, value=value), self.assertRaises(ValidationError):
                    Queries(**dict(self.queries, **{category: value}))
            fields = dict(self.queries)
            del fields[category]
            with self.subTest(missing=category), self.assertRaises(ValidationError):
                Queries(**fields)
        for field in self.result:
            with self.subTest(null=field), self.assertRaises(ValidationError):
                GeneratedQueries(**dict(self.result, **{field: None}))


    def test_queries_reject_blank_text_and_normalized_duplicates(self):
        for text in ("", " \t\n", None, 42, self.queries["direct"][1],
                     "  NON riesco  a entrare in Moodle \n"):
            queries = dict(self.queries, direct=[text, *self.queries["direct"][1:]])
            with self.subTest(text=text), self.assertRaises(ValidationError):
                Queries(**queries)
        queries = dict(self.queries, direct=["  Mi serve assistenza per Moodle \n",
                                            *self.queries["direct"][1:]])
        self.assertEqual(Queries(**queries).model_dump(), self.queries)


    def test_ticket_metadata_is_optional_but_title_is_required(self):
        self.assertEqual(TicketType(title="Assistenza").model_dump(),
                         {"title": "Assistenza", "description": "", "structure": ""})
        for fields in [{}, {"title": ""}, {"title": " \t\n"}, {"title": None},
                       {"title": "Assistenza", "description": None},
                       {"title": "Assistenza", "structure": None},
                       {"title": "Assistenza", "unknown": "value"}]:
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                TicketType(**fields)


    def test_main_generates_one_ticket_and_prints_json(self):
        with patch.object(generator, "generate_queries", return_value=GeneratedQueries(**self.result)) as generate, \
             patch.object(generator, "create_backend") as create, \
             patch("sys.stdout", new_callable=io.StringIO) as stdout, \
             patch("sys.stderr", new_callable=io.StringIO) as stderr:
            backend = create.return_value.__enter__.return_value
            backend.config = OpenAIConfig(model_name="test-model", temperature=0.3)
            generator.main()
        generate.assert_called_once()
        ticket = generate.call_args.args[0]
        self.assertIsInstance(ticket, TicketType)
        self.assertIs(generate.call_args.kwargs["backend"], backend)
        self.assertIn("Modello: test-model", stderr.getvalue())
        self.assertIn('"temperature": 0.3', stderr.getvalue())
        self.assertEqual(json.loads(stdout.getvalue()), self.result)

