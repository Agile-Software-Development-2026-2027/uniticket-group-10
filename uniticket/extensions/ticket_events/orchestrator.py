"""Generazione degli embedding delle categorie create o modificate."""
import logging

from embedder.embedder import SnowflakeEmbedder

from .content import embedding_text, snapshot
from .interfaces import CategoryOperation, EmbeddingProvider

logger = logging.getLogger("ticket_events.orchestrator")
# Crea il provider senza contattare Ollama: la richiesta parte con embed().
provider: EmbeddingProvider = SnowflakeEmbedder()


# Legge la categoria salvata e genera il vettore; DELETE non chiama il modello.
def synchronize(operation: CategoryOperation, category_id: int) -> None:
    if operation == "CREATE":
        # Pseudocodice quando sarà disponibile l'embedder:
        # category = snapshot(category_id, using="default")
        # text = embedding_text(category)
        # vector = embedder.embed(text)
        # metadata = category_metadata(category)
        # repository.upsert(category_id, vector, metadata)
        action = "INDEX"
    elif operation == "UPDATE":
        # Pseudocodice: ricalcolare il vettore e sostituire il punto esistente.
        # category = snapshot(category_id, using="default")
        # text = embedding_text(category)
        # vector = embedder.embed(text)
        # metadata = category_metadata(category)
        # repository.upsert(category_id, vector, metadata)
        action = "REINDEX"
    elif operation == CategoryOperation.DELETE:
        action = "REMOVE"
        # Pseudocodice: rimuovere dal repository il punto identificato dall'ID.
        # repository.delete(category_id)
    else:
        raise ValueError(f"Operazione sconosciuta: {operation}")

    logger.info(
        "[ORCHESTRATION] operation=%s category_id=%s action=%s",
        operation, category_id, action,
    )

    # La categoria eliminata non deve essere letta o inviata al modello.
    if operation == CategoryOperation.DELETE:
        return

    # Rilegge nome, descrizione e metadata dal database UniTicket.
    category = snapshot(category_id, "default")
    if category is None:
        logger.warning("Categoria non trovata: category_id=%s", category_id)
        return

    # Prepara solo nome e descrizione; i metadata restano fuori dal testo.
    text = embedding_text(category)
    # Il provider chiama Ollama e restituisce il vettore del testo.
    vector = provider.embed(text)
    # Il salvataggio del vettore sarà aggiunto con il repository.
    logger.info("Embedding generato: category_id=%s dimension=%s", category_id, len(vector))
