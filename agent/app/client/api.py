from typing import Any, Protocol, runtime_checkable
from pydantic import BaseModel, Field, JsonValue


class Structure(BaseModel):
    id: int
    name: str
    description: str | None


class Catalog(BaseModel):
    id: int
    name: str
    description: str | None
    structure_id: int = Field(gt=0, strict=True)
    structure_name: str
    url: str


# Descrive i dati ricevuti, senza applicare nuove validazioni ai valori del modulo.
class FormField(BaseModel):
    id: str
    label: str
    type: str
    required: bool
    constraints: dict[str, JsonValue]
    initial_value: JsonValue
    disabled: bool = False
    fields: list["FormField"] | None = None


class FormSchema(BaseModel):
    category_id: int = Field(gt=0, strict=True)
    module_id: int = Field(gt=0, strict=True)
    fields: list[FormField]


class FieldValidationError(BaseModel):
    field: str | None
    code: str
    message: str


class FormFieldUpdateResult(BaseModel):
    valid: bool
    field_id: str
    value: Any = None
    errors: list[FieldValidationError] = Field(default_factory=list)


@runtime_checkable
class UniTicketAPI(Protocol):
    async def get_form_schema(self, ticket_id: int) -> FormSchema:
        """Return the active form schema for a TicketCategory accessible to the current user."""

    async def get_structures(self) -> list[Structure]:
        """Return structures with categories available to the current user."""

    async def get_ticket_categories(self) -> list[Catalog]:
        """Return ticket categories available to the current user."""

    async def search_ticket_categories(
        self,
        query: str,
        excluded_category_ids: list[int] | None = None,
        structure_ids: list[int] | None = None,
    ) -> list[Catalog]:
        """Search available categories, excluding IDs and optionally limiting structures."""

    async def update_form_field(
        self,
        category_id: int,
        field_id: str,
        value: Any,
        data: dict[str, Any] | None = None,
    ) -> FormFieldUpdateResult:
        """Validate and normalize a single field value for the opened category form."""