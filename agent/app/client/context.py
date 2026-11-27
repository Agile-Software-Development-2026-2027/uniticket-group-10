"""Dati necessari ai nodi e ai tool durante il run."""

from dataclasses import dataclass

from .api import UniTicketAPI

@dataclass(kw_only=True)
class UserContext:
    first_name: str
    last_name: str
    email: str
    identifier: int
    is_employee: bool

@dataclass(kw_only=True)
class ConversationContext:
    uniticket: UniTicketAPI
    user: UserContext
    selected_form: int
