"""Test CRUD del repository Qdrant con un client in memoria."""

from django.test import SimpleTestCase
from qdrant_client import QdrantClient

from ..repository import QdrantIndexRepository


class QdrantIndexRepositoryTests(SimpleTestCase):
    """Verifica persistenza, sostituzione e rimozione dei punti Qdrant."""

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
