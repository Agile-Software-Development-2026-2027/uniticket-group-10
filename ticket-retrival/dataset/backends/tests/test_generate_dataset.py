import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from dataset import generate_dataset as batch
from dataset.backends import OpenAIConfig
from dataset.generation.generate_queries import GeneratedQueries, Queries


class GenerateDatasetTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.source = self.directory / "ticket types.json"
        self.output = self.directory / "evaluation.json"
        self.records = [
            {"ticket_category_id": pk, "title": f"Ticket {pk}", "description": "Descrizione",
             "structure": {"id": 3, "name": "Università"}}
            for pk in range(4)
        ]
        self.source.write_text(json.dumps(self.records), encoding="utf-8")
        self.config = OpenAIConfig(model_name="local-model")
        factory = patch.object(batch, "create_backend")
        self.create_backend = factory.start()
        self.backend = self.create_backend.return_value.__enter__.return_value
        self.addCleanup(factory.stop)
        stdout = patch("sys.stdout", new_callable=io.StringIO)
        stdout.start()
        self.addCleanup(stdout.stop)

    def queries(self, ticket):
        return GeneratedQueries(description_quality="partially_informative", queries=Queries(
            **{kind: [f"{ticket.title} {kind} {i}" for i in range(3)]
               for kind in ("direct", "paraphrase", "indirect")}
        ))

    def run_batch(self, **kwargs):
        return batch.generate_dataset(self.source, output=self.output, config=self.config, **kwargs)

    def test_parallelism_is_bounded_and_results_keep_ticket_metadata(self):
        barrier = threading.Barrier(2, timeout=5)
        lock = threading.Lock()
        active = peak = 0
        main_thread = threading.get_ident()

        def generate(ticket, **kwargs):
            nonlocal active, peak
            self.assertIs(kwargs["backend"], self.backend)
            self.assertEqual(ticket.structure, "Università")
            with lock:
                active += 1
                peak = max(peak, active)
            try:
                barrier.wait()
                return self.queries(ticket)
            finally:
                with lock:
                    active -= 1

        save_results = batch._save_results
        def save(output, results):
            self.assertEqual(threading.get_ident(), main_thread)
            save_results(output, results)

        with patch.object(batch, "generate_queries", side_effect=generate), \
             patch.object(batch, "_save_results", side_effect=save):
            self.assertEqual(self.run_batch(parallel=2), 0)
        self.assertEqual(peak, 2)
        self.create_backend.assert_called_once_with(self.config)
        self.create_backend.return_value.__exit__.assert_called_once()
        results = json.loads(self.output.read_text())
        self.assertEqual({item["ticket_category_id"] for item in results}, set(range(4)))
        for result in results:
            self.assertEqual(result["description_quality"], "partially_informative")
            self.assertEqual(result["structure"], {"id": 3, "name": "Università"})
            self.assertEqual(result["queries"]["direct"][0], f"{result['title']} direct 0")
        self.assertEqual(json.loads(self.source.read_text()), self.records)

    def test_partial_failure_is_saved_and_only_failed_ticket_is_retried(self):
        def generate(ticket, **kwargs):
            if ticket.title == "Ticket 1":
                raise RuntimeError("Backend unavailable")
            return self.queries(ticket)

        with patch.object(batch, "generate_queries", side_effect=generate), \
             patch("sys.stderr", new_callable=io.StringIO) as stderr:
            self.assertEqual(self.run_batch(parallel=2), 1)
        self.assertIn("Errore ticket 1", stderr.getvalue())
        self.assertEqual(len(json.loads(self.output.read_text())), 3)
        with patch.object(batch, "generate_queries", side_effect=lambda ticket, **_: self.queries(ticket)) as generate:
            self.assertEqual(self.run_batch(), 0)
        generate.assert_called_once()
        self.assertEqual(generate.call_args.args[0].title, "Ticket 1")
        self.assertEqual(len(json.loads(self.output.read_text())), 4)

    def test_resume_rejects_results_without_description_quality(self):
        legacy = dict(self.records[0],
                      queries=self.queries(batch.TicketType(title="Ticket 0")).queries.model_dump())
        self.output.write_text(json.dumps([legacy]))
        original = self.output.read_text()
        with patch.object(batch, "generate_queries", side_effect=lambda ticket, **_: self.queries(ticket)) as generate:
            with self.assertRaisesRegex(ValueError, "description_quality"):
                self.run_batch()
        generate.assert_not_called()
        self.assertEqual(self.output.read_text(), original)

    def test_all_input_is_validated_before_backend_calls(self):
        cases = [None, {}, [self.records[0], self.records[0]],
                 [dict(self.records[0], ticket_category_id=True)],
                 [self.records[0], {"ticket_category_id": 9, "title": ""}]]
        for records in cases:
            with self.subTest(records=records), patch.object(batch, "generate_queries") as generate:
                self.source.write_text(json.dumps(records))
                with self.assertRaises(ValueError):
                    self.run_batch()
                generate.assert_not_called()
                self.assertFalse(self.output.exists())

    def test_refuses_same_input_output_and_invalid_parallelism(self):
        original = self.source.read_text()
        with self.assertRaisesRegex(ValueError, "file diversi"):
            batch.generate_dataset(self.source, output=self.source)
        self.assertEqual(self.source.read_text(), original)
        for parallel in (0, -1, True, 1.5):
            with self.subTest(parallel=parallel), self.assertRaises(ValueError):
                self.run_batch(parallel=parallel)

    def test_atomic_save_preserves_checkpoint_on_write_error(self):
        self.output.write_text("[]")
        with patch.object(batch.json, "dump", side_effect=OSError("Disk full")):
            with self.assertRaisesRegex(OSError, "Disk full"):
                batch._save_results(self.output, [{"ticket_category_id": 1}])
        self.assertEqual(self.output.read_text(), "[]")
        self.assertEqual(set(self.directory.iterdir()), {self.source, self.output})

    def test_resume_rejects_output_from_another_dataset(self):
        record = dict(self.records[0],
                      title="Different ticket", queries=self.queries(batch.TicketType(title="Test")).queries.model_dump())
        self.output.write_text(json.dumps([record]))
        original = self.output.read_text()
        with patch.object(batch, "generate_queries") as generate:
            with self.assertRaisesRegex(ValueError, "metadati diversi"):
                self.run_batch()
        generate.assert_not_called()
        self.assertEqual(self.output.read_text(), original)

    def test_empty_dataset_and_string_structure(self):
        self.source.write_text("[]")
        self.assertEqual(self.run_batch(), 0)
        self.assertEqual(json.loads(self.output.read_text()), [])
        self.create_backend.assert_not_called()
        self.source.write_text(json.dumps([
            {"ticket_category_id": 1, "title": "Assistenza", "structure": "Università"}
        ]))
        with patch.object(batch, "generate_queries", side_effect=lambda ticket, **_: self.queries(ticket)):
            self.assertEqual(self.run_batch(), 0)
        result = json.loads(self.output.read_text())[0]
        self.assertEqual(result["structure"], "Università")

    def test_invalid_backend_aborts_before_any_generation(self):
        self.create_backend.side_effect = ValueError("Model unavailable")
        with patch.object(batch, "generate_queries") as generate:
            with self.assertRaisesRegex(ValueError, "Model unavailable"):
                self.run_batch()
        generate.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_cli_rejects_invalid_parallelism_without_requests(self):
        result = subprocess.run(
            [sys.executable, str(Path(batch.__file__).resolve()), str(self.source), "--parallel=0"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--parallel", result.stderr)


if __name__ == "__main__":
    unittest.main()
