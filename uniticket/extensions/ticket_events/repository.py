"""Persistenza dei vettori delle categorie in Qdrant."""

import os

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    Filter,
    HasIdCondition,
    PointIdsList,
    PointStruct,
    VectorParams,
)

from .index_fields import CategoryMetadata


class QdrantIndexRepository:
    """Implementazione Qdrant del contratto di persistenza dell'indice."""

    def __init__(
        self,
        collection_name: str | None = None,
        client: QdrantClient | None = None,
    ) -> None:
        """Configura il client e la collezione, consentendo un client sostituibile nei test."""
        self.client = client if client is not None else QdrantClient(
            url=os.getenv("QDRANT_URL", "http://qdrant:6333")
        )
        self.collection_name = collection_name or os.getenv(
            "QDRANT_COLLECTION", "ticket_categories"
        )

    def upsert(
        self,
        category_id: int,
        vector: list[float],
        metadata: CategoryMetadata,
    ) -> None:
        """Crea o sostituisce il punto della categoria usando il suo ID stabile."""
        if not vector:
            raise ValueError("Il vettore della categoria non può essere vuoto")

        self._ensure_collection(len(vector))
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(
                    id=category_id,
                    vector=vector,
                    payload=dict(metadata),
                )
            ],
            wait=True,
        )

    def delete(self, category_id: int) -> None:
        """Elimina il punto della categoria e non fallisce se non esiste."""
        if not self.client.collection_exists(self.collection_name):
            return

        self.client.delete(
            collection_name=self.collection_name,
            points_selector=PointIdsList(points=[category_id]),
            wait=True,
        )

    def search(
        self,
        vector: list[float],
        top_k: int,
        authorized_category_ids: list[int],
    ) -> list[int]:
        """Restituisce gli ID più vicini, limitando la ricerca alle categorie autorizzate."""
        if top_k < 1:
            raise ValueError("top_k deve essere almeno 1")
        if not vector:
            raise ValueError("Il vettore di ricerca non può essere vuoto")
        if not authorized_category_ids or not self.client.collection_exists(self.collection_name):
            return []

        result = self.client.query_points(
            collection_name=self.collection_name,
            query=vector,
            query_filter=Filter(
                must=[HasIdCondition(has_id=authorized_category_ids)]
            ),
            limit=top_k,
            with_payload=False,
            with_vectors=False,
        )
        return [point.id for point in result.points]

    def _ensure_collection(self, vector_size: int) -> None:
        """Crea la collezione al primo inserimento usando la dimensione del vettore."""
        if self.client.collection_exists(self.collection_name):
            return

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
