import os

import httpx

from .api import Catalog, Structure, UniTicketAPI
from pydantic import TypeAdapter


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