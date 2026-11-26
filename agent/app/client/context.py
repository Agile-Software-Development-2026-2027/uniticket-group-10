"""Dati necessari ai nodi e ai tool durante il run."""

from dataclasses import dataclass, field
from typing import Any

from .api import UniTicketAPI


@dataclass(kw_only=True)
class UserContext:
    uniticket: UniTicketAPI
    category_id: int | None = None
    form_fields: dict[str, Any] = field(default_factory=dict)