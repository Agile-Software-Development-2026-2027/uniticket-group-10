"""Test CRUD del repository Qdrant con un client in memoria."""

from unittest.mock import Mock

from django.test import SimpleTestCase
from httpx import Headers
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse

from ..interfaces import IndexRepository
from ..repository import QdrantIndexRepository


class QdrantIndexRepositoryTests(SimpleTestCase):
    """Verifica persistenza, sostituzione e rimozione dei punti Qdrant."""

    def test_qdrant_repository_implements_index_repository_contract(self):
        """La classe concreta dichiara esplicitamente il contratto dell'interfaccia."""
        self.assertTrue(issubclass(QdrantIndexRepository, IndexRepository))

    def setUp(self):
        """Prepara un client Qdrant isolato e i metadata di una categoria."""
        self.client = QdrantClient(":memory:")
        self.collection_name = "test_ticket_categories"
        self.repository = QdrantIndexRepository(
            collection_name=self.collection_name,
            client=self.client,
        )
        self.metadata = {
            "organizational_structure_id": 7,
            "organizational_office_id": None,
            "allow_user": True,
            "allow_employee": False,
            "allow_anonymous": False,
            "allow_guest": True,
            "allow_spid_cie": False,
            "is_active": True,
        }

    def tearDown(self):
        """Rilascia il client Qdrant usato dal test."""
        self.client.close()

    def test_upsert_creates_category_with_vector_and_metadata(self):
        """CREATE persiste il vettore e i metadata sul punto con ID categoria."""
        self.repository.upsert(42, [1.0, 0.0], self.metadata)

        points = self.client.retrieve(
            collection_name=self.collection_name,
            ids=[42],
            with_payload=True,
            with_vectors=True,
        )

        self.assertEqual(len(points), 1)
        self.assertEqual(points[0].id, 42)
        self.assertEqual(points[0].vector, [1.0, 0.0])
        self.assertEqual(points[0].payload, self.metadata)

    def test_upsert_replaces_existing_category_without_duplicates(self):
        """UPDATE sostituisce vettore e metadata mantenendo un solo punto per ID."""
        self.repository.upsert(42, [1.0, 0.0], self.metadata)
        updated_metadata = {**self.metadata, "is_active": False}
        self.repository.upsert(42, [0.0, 1.0], updated_metadata)

        points = self.client.retrieve(
            collection_name=self.collection_name,
            ids=[42],
            with_payload=True,
            with_vectors=True,
        )

        self.assertEqual(len(points), 1)
        self.assertEqual(points[0].vector, [0.0, 1.0])
        self.assertEqual(points[0].payload, updated_metadata)

    def test_search_uses_updated_vector_not_the_previous_vector(self):
        """Dopo l'upsert la ricerca classifica il punto con il solo vettore nuovo."""
        self.repository.upsert(42, [1.0, 0.0], self.metadata)
        self.repository.upsert(43, [0.8, 0.2], self.metadata)

        self.repository.upsert(
            42,
            [0.0, 1.0],
            {**self.metadata, "is_active": False},
        )

        self.assertEqual(self.repository.search([1.0, 0.0], 1, [42, 43]), [43])
        self.assertEqual(self.repository.search([0.0, 1.0], 1, [42, 43]), [42])

    def test_delete_removes_existing_category(self):
        """DELETE rimuove il punto identificato dall'ID stabile della categoria."""
        self.repository.upsert(42, [1.0, 0.0], self.metadata)

        self.repository.delete(42)

        self.assertEqual(
            self.client.retrieve(collection_name=self.collection_name, ids=[42]),
            [],
        )

    def test_delete_is_safe_when_collection_or_point_is_absent(self):
        """DELETE è idempotente anche se la collezione o il punto non esistono."""
        self.repository.delete(42)
        self.repository.upsert(42, [1.0, 0.0], self.metadata)

        self.repository.delete(99)

        self.assertEqual(
            len(self.client.retrieve(collection_name=self.collection_name, ids=[42])),
            1,
        )

    def test_upsert_rejects_empty_vector(self):
        """Rifiuta un vettore vuoto invece di creare una collezione non valida."""
        with self.assertRaises(ValueError):
            self.repository.upsert(42, [], self.metadata)

        self.assertFalse(self.client.collection_exists(self.collection_name))

    def test_upsert_rejects_incomplete_or_unexpected_metadata(self):
        """Impedisce di salvare punti senza il payload completo previsto dal contratto."""
        incomplete_metadata = {**self.metadata}
        del incomplete_metadata["allow_guest"]

        with self.assertRaisesRegex(ValueError, "Metadata categoria non validi"):
            self.repository.upsert(42, [1.0, 0.0], incomplete_metadata)

        self.assertFalse(self.client.collection_exists(self.collection_name))

    def test_collection_created_concurrently_allows_upsert_to_continue(self):
        repository = QdrantIndexRepository(
            collection_name=self.collection_name,
            client=Mock(),
        )
        repository.client.collection_exists.side_effect = [False, True]
        repository.client.create_collection.side_effect = UnexpectedResponse(
            409, "Conflict", b'{"status":{"error":"already exists"}}', Headers()
        )

        repository.upsert(42, [1.0, 0.0], self.metadata)

        self.assertEqual(repository.client.collection_exists.call_count, 2)
        repository.client.upsert.assert_called_once()

    def test_collection_creation_errors_are_not_hidden_when_collection_is_absent(self):
        repository = QdrantIndexRepository(
            collection_name=self.collection_name,
            client=Mock(),
        )
        repository.client.collection_exists.side_effect = [False, False]
        error = UnexpectedResponse(
            409, "Conflict", b'{"status":{"error":"already exists"}}', Headers()
        )
        repository.client.create_collection.side_effect = error

        with self.assertRaises(UnexpectedResponse) as raised:
            repository._ensure_collection(vector_size=2)

        self.assertIs(raised.exception, error)

    def test_non_conflict_collection_creation_errors_are_not_hidden(self):
        repository = QdrantIndexRepository(
            collection_name=self.collection_name,
            client=Mock(),
        )
        repository.client.collection_exists.return_value = False
        error = UnexpectedResponse(
            500, "Internal Server Error", b'{"status":{"error":"failed"}}', Headers()
        )
        repository.client.create_collection.side_effect = error

        with self.assertRaises(UnexpectedResponse) as raised:
            repository._ensure_collection(vector_size=2)

        self.assertIs(raised.exception, error)
        repository.client.collection_exists.assert_called_once_with(self.collection_name)

    def test_search_returns_nearest_authorized_category_ids_up_to_top_k(self):
        """La ricerca ordina i vicini e filtra gli ID non autorizzati prima del top_k."""
        self.repository.upsert(42, [1.0, 0.0], self.metadata)
        self.repository.upsert(43, [0.8, 0.2], self.metadata)
        self.repository.upsert(44, [0.99, 0.01], self.metadata)

        results = self.repository.search(
            vector=[1.0, 0.0],
            top_k=2,
            authorized_category_ids=[42, 43],
        )

        self.assertEqual(results, [42, 43])
        self.assertNotIn(44, results)

    def test_search_returns_empty_when_no_authorized_ids_or_collection(self):
        """Non restituisce risultati senza categorie autorizzate o collezione."""
        self.assertEqual(self.repository.search([1.0, 0.0], 3, [42]), [])

        self.repository.upsert(42, [1.0, 0.0], self.metadata)

        self.assertEqual(self.repository.search([1.0, 0.0], 3, []), [])

    def test_search_rejects_invalid_top_k_or_empty_vector(self):
        """Rifiuta parametri di ricerca non validi con errori espliciti."""
        with self.assertRaises(ValueError):
            self.repository.search([1.0, 0.0], 0, [42])

        with self.assertRaises(ValueError):
            self.repository.search([], 1, [42])
