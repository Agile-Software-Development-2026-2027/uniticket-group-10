from typing import Protocol, runtime_checkable
from pydantic import BaseModel, Field

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

@runtime_checkable
class UniTicketAPI(Protocol):
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
