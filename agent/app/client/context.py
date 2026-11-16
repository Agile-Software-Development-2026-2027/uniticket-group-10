"""Dati necessari ai nodi e ai tool durante il run."""

from dataclasses import dataclass

from .api import UniTicketAPI


@dataclass(kw_only=True)
class UserContext:
    uniticket: UniTicketAPI
