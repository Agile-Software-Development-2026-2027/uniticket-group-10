"""Contratti Pydantic della POST JSON tra Django e l’agente.

Django inoltra l’input del frontend e aggiunge il catalogo delle categorie
autorizzate per l’utente e la lingua attiva. AgentRequest valida questi dati:
il campo `type` distingue messaggi, selezioni di moduli e richieste di aiuto.
Le suggestions vengono inviate come normali messaggi con il modulo come contesto.

L’agente costruisce AssistantMessage con testo, eventuali suggerimenti di ticket
e suggerimenti testuali o un’azione facoltativa. L’endpoint restituisce questi messaggi
nel campo `messages` del JSON di risposta. I contratti rifiutano campi aggiuntivi
per evitare che dati non previsti entrino nella logica conversazionale.
"""

from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class Contract(BaseModel):
    """Base dei contratti: accetta solo i campi dichiarati dal modello."""

    model_config = ConfigDict(extra="forbid")


class Category(Contract):
    """Categoria del catalogo autorizzato fornito da Django, con URL del modulo."""

    id: int = Field(gt=0, strict=True)
    name: str = Field(min_length=1, max_length=255, strict=True)
    description: str = ""
    structure_id: int = Field(gt=0, strict=True)
    structure_name: str = ""
    url: str
    hidden: bool = False


class TicketSuggestion(Contract):
    """Dati di una card ticket selezionata dall’agente a partire dal catalogo."""

    category_id: int
    title: str
    structure_name: str
    url: str


class TicketSuggestions(Contract):
    """Contenuto strutturato di un messaggio che presenta una lista di ticket."""

    type: Literal["tickets"] = "tickets"
    tickets: list[TicketSuggestion]


class MessageInput(Contract):
    """Messaggio utente di 1–500 caratteri, con eventuale modulo aperto come contesto."""

    type: Literal["message"]
    message: Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=500)]
    category_id: int | None = Field(default=None, gt=0, strict=True)


class FormSelectedInput(Contract):
    """Selezione di un modulo per cui l’agente deve proporre assistenza."""

    type: Literal["form_selected"]
    category_id: int = Field(gt=0, strict=True)


class RequestFormHelpInput(Contract):
    """Richiesta esplicita di avvio dell'assistenza su un modulo autorizzato."""

    type: Literal["request_form_help"]
    category_id: int = Field(gt=0, strict=True)


class FormHelpAction(RequestFormHelpInput):
    """Azione proposta dall'agente, con etichetta traducibile per il pulsante."""

    label: Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=500)]


class AssistantMessage(Contract):
    """Risposta dell’assistente con identificativo, testo e contenuti facoltativi."""

    id: UUID = Field(default_factory=uuid4)
    message: str
    content: TicketSuggestions | None = None
    suggestions: list[Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=500)]] = Field(default_factory=list)
    action: FormHelpAction | None = None

    def to_dict(self) -> dict:
        """Converte il messaggio in dati JSON, omettendo i campi senza valore."""
        return self.model_dump(mode="json", exclude_none=True)


class AgentRequest(Contract):
    """Richiesta completa: input del frontend, catalogo autorizzato e lingua."""

    input: Annotated[MessageInput | FormSelectedInput | RequestFormHelpInput, Field(discriminator="type")]
    catalog: list[Category]
    language: str = "it"
