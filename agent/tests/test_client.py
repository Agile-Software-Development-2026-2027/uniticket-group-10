"""Test unitari per UniTicketClient.validate_form — nessun server reale richiesto."""

import asyncio

import httpx
import pytest

from app.client.client import UniTicketClient


def make_client(responses: list[tuple[int, dict]]) -> UniTicketClient:
    """Crea un client con un trasporto finto che risponde in sequenza."""
    response_iter = iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        status, body = next(response_iter)
        return httpx.Response(status, json=body)

    transport = httpx.MockTransport(handler)
    client = UniTicketClient.__new__(UniTicketClient)
    client._client = httpx.AsyncClient(
        base_url="http://uniticket/api/",
        transport=transport,
    )
    return client


def test_validate_form_valid():
    """Un form compilato correttamente torna valid=True e liste vuote."""
    client = make_client([
        (200, {"valid": True, "missing_fields": [], "errors": []}),
    ])

    result = asyncio.run(client.validate_form(42, {"nome": "Mario", "cognome": "Rossi"}))

    assert result.valid is True
    assert result.missing_fields == []
    assert result.errors == []


def test_validate_form_missing_fields():
    """Campi obbligatori mancanti tornano in missing_fields e valid=False."""
    client = make_client([
        (200, {"valid": False, "missing_fields": ["nome", "cognome"], "errors": []}),
    ])

    result = asyncio.run(client.validate_form(42, {}))

    assert result.valid is False
    assert result.missing_fields == ["nome", "cognome"]
    assert result.errors == []


def test_validate_form_field_errors():
    """Valori non validi tornano in errors con field, code e message."""
    client = make_client([
        (200, {
            "valid": False,
            "missing_fields": [],
            "errors": [
                {
                    "field": "email",
                    "code": "invalid",
                    "message": "Inserisci un indirizzo email valido.",
                }
            ],
        }),
    ])

    result = asyncio.run(client.validate_form(42, {"email": "non-una-email"}))

    assert result.valid is False
    assert len(result.errors) == 1
    assert result.errors[0].field == "email"
    assert result.errors[0].code == "invalid"


def test_validate_form_raises_on_404():
    """Se la categoria non esiste o non è accessibile, il client propaga l'errore HTTP."""
    client = make_client([
        (404, {"detail": "Categoria non disponibile."}),
    ])

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(client.validate_form(999, {"nome": "Mario"}))
