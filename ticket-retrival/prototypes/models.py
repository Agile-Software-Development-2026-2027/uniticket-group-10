"""Shared ticket model matching the records in dumps/tickets.json."""

import json
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


def _compact_context(value):
    """
    Rimuove ricorsivamente i valori vuoti (None, stringhe, liste o dizionari vuoti) 
    per ottimizzare il contesto inviato all'LLM, riducendo i token inutili. 
    Preserva i valori validi come False e 0.
    """
    if isinstance(value, dict):
        return {key: cleaned for key, item in value.items()
                if (cleaned := _compact_context(item)) is not None} or None
    if isinstance(value, list):
        return [cleaned for item in value if (cleaned := _compact_context(item)) is not None] or None
    if value is None or isinstance(value, str) and not value.strip():
        return None
    return value


class OrganizationalStructure(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)

    id: int | None = None
    name: str = ""
    description: str | None = ""

    def as_llm_context(self) -> dict[str, Any]:
        return _compact_context({
            "name": self.name.strip(),
            "description": self.description,
        }) or {}


class TableColumn(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)

    name: str
    type: str
    label: str
    required: bool
    choices: list[str] = Field(default_factory=list)

    def as_llm_context(self) -> dict[str, Any]:
        return _compact_context({
            "name": self.name, "label": self.label, "field_type": self.type,
            "required": self.required, "choices": self.choices,
        })


class FormField(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)

    id: int
    name: str
    field_type: str
    is_required: bool
    valore: Any = ""
    aiuto: str | None = ""
    pre_text: str | None = ""
    ordinamento: int = 0
    category_module: int | None = None
    choices: list[str] = Field(default_factory=list)
    columns: list[TableColumn] = Field(default_factory=list)

    def as_llm_context(self) -> dict[str, Any]:
        # For choice/table fields, valore encodes the schema, not a default value.
        default_value = None if self.field_type in (
            "MultiCheckBoxField", "CustomSelectBoxField", "CustomRadioBoxField", "CustomComplexTableField",
        ) else self.valore
        return _compact_context({
            "name": self.name,
            "field_type": self.field_type,
            "required": self.is_required,
            "default_value": default_value,
            "help_message": self.aiuto,
            "pre_text": self.pre_text,
            "choices": self.choices,
            "columns": [column.as_llm_context() for column in self.columns],
        })


class Ticket(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)

    id: int
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    description: str | None = ""
    structure: OrganizationalStructure = Field(default_factory=OrganizationalStructure)
    fields: list[FormField] = Field(default_factory=list)
    header_text: str | None = ""
    footer_text: str | None = ""
    is_active: bool = False
    is_hidden: bool = False
    allow_user: bool = False
    allow_employee: bool = False
    allow_anonymous: bool = False
    allow_guest: bool = False
    allow_spid_cie: bool = False

    def as_llm_context(self) -> dict[str, Any]:
        return _compact_context({
            "title": self.title,
            "description": self.description,
            "structure": self.structure.as_llm_context(),
            "fields": [field.as_llm_context() for field in sorted(self.fields, key=lambda field: field.ordinamento)],
            "header_text": self.header_text,
            "footer_text": self.footer_text,
        })


def load_tickets(path: str | Path) -> list[Ticket]:
    """Read a JSON array of tickets, unwrapping {'ticket': ...} when present."""
    records = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("Il dataset deve essere una lista JSON di ticket")
    tickets = []
    seen = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Ogni ticket deve essere un oggetto JSON")
        ticket = Ticket.model_validate(record.get("ticket", record))
        if ticket.id in seen:
            raise ValueError(f"ID ticket duplicato: {ticket.id}")
        seen.add(ticket.id)
        tickets.append(ticket)
    return tickets


