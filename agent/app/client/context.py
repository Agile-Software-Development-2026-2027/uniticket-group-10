from dataclasses import dataclass, field
from typing import Any

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
    category_id: int | None = None
    form_fields: dict[str, Any] = field(default_factory=dict)
