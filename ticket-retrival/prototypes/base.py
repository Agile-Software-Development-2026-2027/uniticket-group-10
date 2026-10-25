

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple, TypedDict

class TicketStructure(TypedDict, total=False):
    """Rappresenta una struttura organizzativa."""

    id: int
    name: str

@dataclass
class Fields:
    """Rappresenta un singolo campo all'interno del form."""

    type: str
    name: str
    is_required: bool
    options: List[dict] = field(default_factory=list)
    default_value: Any = None

    @classmethod
    def from_dict(cls, data: dict) -> "Fields":
        return cls(
            type=data["type"] if "type" in data else data["field_type"],
            name=data.get("name", data.get("field_name", data.get("label", ""))),
            is_required=data["is_required"],
            options=data.get("options") or [],
            default_value=data.get("default_value"),
        )

@dataclass
class Ticket:
    """Rappresenta un intero form, con titolo, descrizione, struttura e campi."""

    ticket_category_id: int
    title: str
    description: Optional[str] = None
    structure: TicketStructure = field(default_factory=dict)
    fields: List[Fields] = field(default_factory=list)

    def get_fields(self, types: List[str] = ["MultiCheckBoxField"]) -> List[Fields]:
        return [form_field for form_field in self.fields if form_field.type in types]

    @classmethod
    def from_dict(cls, data: dict) -> "Ticket":
        return cls(
            ticket_category_id=data["ticket_category_id"],
            title=data.get("title") or "",
            description=data.get("description"),
            structure=data.get("structure") or {},
            fields=[Fields.from_dict(item) if isinstance(item, dict) else item
                    for item in data.get("fields", [])],
        )


class Prototype(ABC):
    """Definisce il contratto comune per valutare i prototipi sullo stesso benchmark."""

    def __init__(self, tickets: List[Ticket]):
        # Converte anche i dizionari dei dataset JSON esistenti.
        self.tickets: List[Ticket] = (
            tickets if all(isinstance(ticket, Ticket) for ticket in tickets)
            else [Ticket.from_dict(ticket) if isinstance(ticket, dict) else ticket for ticket in tickets]
        )

    @abstractmethod
    def search(self, query: str, k: int = 5) -> List[Tuple[int, float]]:
        pass
