import os

import httpx

from .api import Catalog, Structure, UniTicketAPI


class UniTicketClient(UniTicketAPI):
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

    async def _get_items(self, path: str) -> list[dict]:
        items = []
        page = 1
        while True:
            response = await self._client.get(path, params={"page": page})
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                return items + data
            items.extend(data["results"])
            if not data["next"]:
                return items
            page += 1

    async def get_structures(self) -> list[Structure]:
        items = await self._get_items("assistant/structures/")
        return [Structure.model_validate(item) for item in items]

    async def get_ticket_categories(self) -> list[Catalog]:
        items = await self._get_items("assistant/categories/")
        return [Catalog.model_validate(item) for item in items]
