"""Dati necessari ai nodi e ai tool durante il run."""

from dataclasses import dataclass

from .api import UniTicketAPI


@dataclass(kw_only=True)
class UserContext:
    uniticket: UniTicketAPI
    user_first_name: str
    user_last_name: str
    user_email: str
    user_identifier: int
    user_is_employee: bool
