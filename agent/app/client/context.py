from dataclasses import dataclass, field
from typing import Any

from .api import UniTicketAPI


@dataclass(slots=True)
class UserContext:
    """Per-request dependencies injected into LangGraph tool runtimes."""

    uniticket: UniTicketAPI
    category_id: int | None = None
    form_fields: dict[str, Any] = field(default_factory=dict)