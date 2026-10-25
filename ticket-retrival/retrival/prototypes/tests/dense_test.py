
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from retrival.base import Ticket
from retrival.prototypes.dense import Dense


class DenseTest(unittest.TestCase):

    @patch("retrival.prototypes.dense.SentenceTransformer")
    def test_creation_preserves_order(self, mock_transformer):
        tickets = [
            Ticket(91, "Certificato"),
            Ticket(7, "Borsa"),
            Ticket(42, "Iscrizione"),
        ]

        embeddings = np.eye(3)
        model = mock_transformer.return_value
        model.encode_document.return_value = embeddings

        with tempfile.TemporaryDirectory() as directory:
            with patch("retrival.prototypes.dense.OUTPUT_DIR", Path(directory)):
                dense = Dense(tickets, ticket_to_text=lambda ticket: ticket.title)
                
                model.encode_document.assert_called_once_with(
                    ["Certificato", "Borsa", "Iscrizione"],
                    normalize_embeddings=True,
                )

                saved_ids = json.loads(
                    dense.filename.with_suffix(".json").read_text()
                )
                saved_embeddings = np.load(dense.filename)

                self.assertEqual(saved_ids, [91, 7, 42])
                np.testing.assert_array_equal(saved_embeddings, embeddings)

                self.assertEqual(dense.ticket_ids, saved_ids)
                np.testing.assert_array_equal(dense.embeddings, embeddings)

@patch("retrival.prototypes.dense.SentenceTransformer")
def test_search_returns_matching_ids_and_scores(self, mock_transformer):
    tickets = [
        Ticket(91, "Certificato"),
        Ticket(7, "Borsa"),
    ]

    model = mock_transformer.return_value
    model.encode_document.return_value = np.eye(2)
    model.encode.return_value = np.array([0.0, 1.0])

    with tempfile.TemporaryDirectory() as directory:
        with patch("retrival.prototypes.dense.OUTPUT_DIR", Path(directory)):
            dense = Dense(tickets)
            results = dense.search("borsa", k=2)

    self.assertEqual(results, [(7, 1.0), (91, 0.0)])

    @patch("retrival.prototypes.dense.SentenceTransformer")
    def test_cache_skips_callback_and_embedding_generation(self, mock_transformer):
        tickets = [Ticket(91, "Certificato"), Ticket(7, "Borsa")]
        callback = Mock(side_effect=lambda ticket: ticket.title)
        model = mock_transformer.return_value
        model.encode_document.return_value = np.eye(2)

        with tempfile.TemporaryDirectory() as directory, patch(
            "retrival.prototypes.dense.OUTPUT_DIR", Path(directory)
        ):
            Dense(tickets, ticket_to_text=callback)
            callback.reset_mock()
            model.encode_document.reset_mock()

            cached = Dense(tickets, ticket_to_text=callback)

            callback.assert_not_called()
            model.encode_document.assert_not_called()
            self.assertEqual(cached.ticket_ids, [91, 7])
            np.testing.assert_array_equal(cached.embeddings, np.eye(2))


if __name__ == "__main__":
    unittest.main()
