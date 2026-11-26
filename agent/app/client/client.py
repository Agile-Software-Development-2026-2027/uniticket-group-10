import os
from typing import Any

import httpx
from pydantic import TypeAdapter

from .api import (
    Catalog,
    FormFieldUpdateResult,
    FormSchema,
    Structure,
    UniTicketAPI,
)


class UniTicketClient(UniTicketAPI):
    # https://pydantic.dev/docs/validation/latest/concepts/type_adapter/
    # it is recommended to create a TypeAdapter for a given type just once and reuse it
    _structure_adapter = TypeAdapter(list[Structure])
    _ticket_adapter = TypeAdapter(list[Catalog])

    def __init__(self, *, session_cookie: str, base_url: str | None = None):
        if base_url is None:
            base_url = os.environ["UNITICKET_API_URL"]
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Cookie": session_cookie},
            timeout=10.0,
        )

    async def __aenter__(self):
        await self._client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return await self._client.__aexit__(exc_type, exc_value, traceback)

    async def get_structures(self) -> list[Structure]:
        response = await self._client.get("assistant/structures/")
        response.raise_for_status()
        return self._structure_adapter.validate_python(response.json())

    async def get_ticket_categories(self) -> list[Catalog]:
        response = await self._client.get("assistant/categories/")
        response.raise_for_status()
        return self._ticket_adapter.validate_python(response.json())

    async def search_ticket_categories(
        self,
        query: str,
        excluded_category_ids: list[int] | None = None,
        structure_ids: list[int] | None = None,
    ) -> list[Catalog]:
        response = await self._client.get(
            "assistant/search/",
            params={
                "query": query,
                "excluded_category_ids": excluded_category_ids or [],
                "structure_ids": structure_ids or [],
            },
        )
        response.raise_for_status()
        return self._ticket_adapter.validate_python(response.json())

    async def get_form_schema(self, category_id: int) -> FormSchema:
        response = await self._client.get(f"assistant/categories/{category_id}/form-schema/")
        response.raise_for_status()
        return FormSchema.model_validate(response.json())

    async def update_form_field(
        self,
        category_id: int,
        field_id: str,
        value: Any,
        data: dict[str, Any] | None = None,
    ) -> FormFieldUpdateResult:
        response = await self._client.post(
            f"assistant/categories/{category_id}/form-fields/",
            json={
                "field_id": str(field_id),
                "value": value,
                "data": data or {},
            },
        )
        if response.status_code in (200, 400):
            return FormFieldUpdateResult.model_validate(response.json())
        response.raise_for_status()
        return FormFieldUpdateResult.model_validate(response.json())