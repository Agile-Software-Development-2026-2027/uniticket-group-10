"""Prova facoltativa del CRUD con Ollama e una collezione Qdrant temporanea."""
import json
import math
import os
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from django.test import TransactionTestCase
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams

from database.repository import QdrantIndexRepository
from embedder.embedder import SnowflakeEmbedder
from ..index_fields import METADATA_FIELDS
from ..interfaces import CategoryOperation
from ..orchestrator import provider
from .helpers import CategoryTestsSetup


@skipUnless(os.getenv("TICKET_EVENTS_LIVE_EMBEDDING") == "1", "Richiede Ollama e Qdrant locali")
class LiveEmbeddingTests(CategoryTestsSetup, TransactionTestCase):
    # Prepara una collezione nuova e la usa soltanto durante questa prova.
    def setUp(self):
        super().setUp()
        self.qdrant = QdrantClient(url=os.getenv("QDRANT_URL", "http://qdrant:6333"))
        self.addCleanup(self.qdrant.close)
        # Il nome non dipende dalla collezione configurata per l'applicazione.
        self.collection = f"ticket_categories_live_test_{uuid4().hex}"
        self.qdrant.create_collection(
            self.collection,
            vectors_config=VectorParams(size=SnowflakeEmbedder.dimension, distance=Distance.COSINE),
        )
        # Registra la pulizia solo dopo aver creato la collezione con successo.
        self.addCleanup(self.qdrant.delete_collection, self.collection)
        repository = QdrantIndexRepository(collection_name=self.collection, client=self.qdrant)
        repository_patch = patch("ticket_events.orchestrator.index_repository", repository)
        repository_patch.start()
        self.addCleanup(repository_patch.stop)
        # Riattiva la chiamata reale all'orchestratore dopo aver isolato il repository.
        self.synchronize_patch.stop()

    # Controlla il record salvato in Qdrant e ne stampa vettore e metadata.
    def read_record(self, operation, category):
        points = self.qdrant.retrieve(
            self.collection, ids=[category.pk], with_payload=True, with_vectors=True,
        )
        self.assertEqual(len(points), 1, "Il record non è stato salvato in Qdrant")
        point = points[0]
        self.assertEqual(point.id, category.pk)
        self.assertEqual(point.payload, {field: getattr(category, field) for field in METADATA_FIELDS})
        self.assertEqual(len(point.vector), SnowflakeEmbedder.dimension)
        self.assertTrue(all(math.isfinite(value) for value in point.vector))
        self.assertTrue(any(value != 0 for value in point.vector))
        self.assertEqual(self.qdrant.count(self.collection, exact=True).count, 1)
        print(json.dumps({
            "operation": operation,
            "category_id": point.id,
            "collection": self.collection,
            "model": SnowflakeEmbedder.model_name,
            "embedding_text": f"{category.name}\n{category.description or ''}",
            "dimension": len(point.vector),
            "vector_preview": point.vector[:6],
            "metadata": point.payload,
        }, ensure_ascii=False, indent=2), flush=True)
        return point.vector

    # Verifica inserimento, sostituzione e rimozione leggendo il database vettoriale reale.
    def test_crud_calls_real_model_only_for_create_and_update(self):
        # Osserva le chiamate senza simulare il modello o la risposta HTTP.
        with patch.object(provider, "embed", wraps=provider.embed) as embed:
            category = self.create_category(
                name="Assistenza Wi-Fi", description="Supporto nelle residenze",
                is_active=True, allow_guest=True,
            )
            first_vector = self.read_record(CategoryOperation.CREATE, category)

            category.description = "Supporto nelle aule"
            category.is_active = False
            category.allow_guest = False
            category.save(update_fields=["description", "is_active", "allow_guest"])
            second_vector = self.read_record(CategoryOperation.UPDATE, category)
            self.assertNotEqual(first_vector, second_vector)

            category_id = category.pk
            category.delete()
            self.assertEqual(self.qdrant.retrieve(self.collection, ids=[category_id]), [])
            self.assertEqual(self.qdrant.count(self.collection, exact=True).count, 0)

        self.assertEqual([call.args[0] for call in embed.call_args_list], [
            "Assistenza Wi-Fi\nSupporto nelle residenze",
            "Assistenza Wi-Fi\nSupporto nelle aule",
        ])
        print("DELETE: record Qdrant rimosso, nessuna chiamata al modello.", flush=True)
