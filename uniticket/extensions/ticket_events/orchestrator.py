"""Generazione degli embedding delle categorie create o modificate."""
import logging

from embedder.embedder import SnowflakeEmbedder

from .content import embedding_text, snapshot
from .index_fields import CategoryMetadata
from .interfaces import CategoryOperation, EmbeddingProvider, IndexRepository
from database.repository import QdrantIndexRepository

logger = logging.getLogger("ticket_events.orchestrator")
# Crea il provider senza contattare Ollama: la richiesta parte con embed().
provider: EmbeddingProvider = SnowflakeEmbedder()
index_repository: IndexRepository = QdrantIndexRepository()


def synchronize(operation: CategoryOperation, category_id: int) -> None:
    if operation == CategoryOperation.CREATE:
        action = "INDEX"
        upsert_category(category_id)

    elif operation == CategoryOperation.UPDATE:
        action = "REINDEX"
        upsert_category(category_id)

    elif operation == CategoryOperation.DELETE:
        action = "REMOVE"
        index_repository.delete(category_id)

    else:
        raise ValueError(f"Operazione sconosciuta: {operation}")

    logger.info(
        "[ORCHESTRATION] operation=%s category_id=%s action=%s",
        operation, category_id, action,
    )

def upsert_category(category_id: int) -> None:
    category = snapshot(category_id, "default")
    if category is None:
        logger.warning("Categoria non trovata: category_id=%s", category_id)
        index_repository.delete(category_id)
        return

    text = embedding_text(category)
    vector = provider.embed(text)
    metadata: CategoryMetadata = {
        "organizational_structure_id": category["organizational_structure_id"],
        "organizational_office_id": category["organizational_office_id"],
        "allow_user": category["allow_user"],
        "allow_employee": category["allow_employee"],
        "allow_anonymous": category["allow_anonymous"],
        "allow_guest": category["allow_guest"],
        "allow_spid_cie": category["allow_spid_cie"],
        "is_active": category["is_active"],
    }
    index_repository.upsert(category_id, vector, metadata)
    logger.info("Categoria indicizzata: category_id=%s dimension=%s", category_id, len(vector))
