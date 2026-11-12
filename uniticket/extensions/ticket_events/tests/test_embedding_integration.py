"""Prova facoltativa del CRUD con il modello Ollama reale e DB temporaneo."""
import json
import math
import os
from unittest import skipUnless
from unittest.mock import patch

from django.test import TransactionTestCase

from ..interfaces import CategoryOperation
from ..orchestrator import provider
from .helpers import CategoryTestsSetup


@skipUnless(os.getenv("TICKET_EVENTS_LIVE_EMBEDDING") == "1", "Richiede Ollama e il modello locale")
class LiveEmbeddingTests(CategoryTestsSetup, TransactionTestCase):
    # Verifica CREATE e UPDATE con Ollama reale; DELETE non deve generare un vettore.
    def test_crud_calls_real_model_only_for_create_and_update(self):
        self.synchronize_patch.stop()
        results = []
        real_embed = provider.embed

        # Conserva i risultati reali per verificarli senza stampare tutti i numeri.
        def record_embedding(text):
            vector = real_embed(text)
            results.append(vector)
            # Mostra un riepilogo leggibile del risultato reale restituito da Ollama.
            print(json.dumps({
                "operation": CategoryOperation.CREATE if len(results) == 1 else CategoryOperation.UPDATE,
                "model": provider.model_name,
                "embedding_text": text,
                "dimension": len(vector),
                "vector_preview": vector[:6],
            }, ensure_ascii=False, indent=2), flush=True)
            return vector

        with patch.object(provider, "embed", side_effect=record_embedding) as embed:
            category = self.create_category(name="Assistenza Wi-Fi", description="Supporto nelle residenze")
            category.description = "Supporto nelle aule"
            category.save(update_fields=["description"])
            category.delete()

        self.assertEqual([call.args[0] for call in embed.call_args_list], [
            "Assistenza Wi-Fi\nSupporto nelle residenze",
            "Assistenza Wi-Fi\nSupporto nelle aule",
        ])
        for vector in results:
            self.assertEqual(len(vector), provider.dimension)
            self.assertTrue(all(math.isfinite(value) for value in vector))
            self.assertTrue(any(value != 0 for value in vector))
        self.assertNotEqual(results[0], results[1])
        print("DELETE: categoria temporanea eliminata, nessuna chiamata al modello.", flush=True)
