"""Genera il vettore per CREATE/UPDATE; DELETE non chiama il modello."""
import logging

from embedder.embedder import SnowflakeEmbedder

from .content import snapshot, embedding_text
from .interfaces import CategoryOperation, EmbeddingProvider

logger = logging.getLogger("ticket_events.orchestrator")
# Crea il provider; la richiesta al modello parte solo quando viene chiamato embed().
provider: EmbeddingProvider = SnowflakeEmbedder()


# Genera il vettore di una categoria creata o modificata; per DELETE usa solo l’ID.
def synchronize(operation: CategoryOperation, category_id: int) -> None:
    if operation == "CREATE":
        action = "INDEX"
    elif operation == "UPDATE":
        action = "REINDEX"
    elif operation == "DELETE":
        action = "REMOVE"
    else:
        raise ValueError(f"Operazione sconosciuta: {operation}")

    # Mostra l’azione richiesta prima di eseguirla.
    logger.info(
        "[ORCHESTRATION] operation=%s category_id=%s action=%s",
        operation, category_id, action,
    )

    # Per DELETE basta l’ID: la categoria è già stata eliminata dal database.
    if operation == "DELETE":
        return

    # Legge i valori salvati nel database UniTicket configurato come default.
    category = snapshot(category_id, "default")
    if category is None:
        logger.warning("Categoria non trovata: category_id=%s", category_id)
        return

    # Costruisce nome e descrizione su due righe, senza i metadata.
    text = embedding_text(category)
    # Mostra il testo nei log DEBUG senza aggiungere i metadata.
    logger.debug("Testo pronto: category_id=%s text=%s", category_id, text)

    # Il provider invia il testo al modello di embedding e restituisce la lista di numeri.
    vector = provider.embed(text)
    # Mostra la dimensione del vettore; il salvataggio nel DB vettoriale verrà aggiunto dopo.
    logger.info("Embedding generato: category_id=%s dimension=%s", category_id, len(vector))
