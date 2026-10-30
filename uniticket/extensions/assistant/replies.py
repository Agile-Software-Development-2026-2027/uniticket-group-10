"""Tipi delle risposte dell'assistente, senza validazione a runtime."""

from typing import Literal, TypedDict


class TextReply(TypedDict):
    """Risposta rapida selezionabile che invia un messaggio all'assistente."""

    type: Literal["reply_text"]
    label: str
    message: str


class TicketReply(TypedDict):
    """Tipo di ticket suggerito, con l'ID della TicketCategory da aprire."""

    type: Literal["ticket"]
    label: str
    title: str
    ticket_id: int
    structure_name: str


Reply = TextReply | TicketReply
