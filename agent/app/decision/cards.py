"""Quello che Jev legge di una categoria: la sua scheda.

Come in uniticket-assistant-v1: titolo, per chi è, descrizione ripulita, i campi che la distinguono e, quando
conta dove, la struttura con il nome esteso e i corsi del dipartimento. I campi sono spesso l'unica cosa che
separa due moduli simili: l'esonero per fratelli iscritti si riconosce da "Altri componenti del nucleo
familiare attualmente iscritti" (misurato: g10w in misure/LEGGIMI.md).
"""

import re

from ..client.api import Catalog
from .departments import departments

MAX_DESCRIPTION_CHARS = 240
MAX_FIELD_LABELS = 6
AUDIENCE_NAMES = (("students", "studenti"), ("staff", "personale"), ("guests", "esterni"), ("anonymous", "chiunque"))

# Descrizioni che sono solo il testo precompilato del form: non dicono nulla del servizio.
_PLACEHOLDER_DESCRIPTION = re.compile(
    r"^(descrivi|descrivere|dettaglia|inserisci|inserire|insert here|cortesemente|indicare"
    r"|come possiamo aiutarti|motivare)\b.*", re.IGNORECASE | re.DOTALL)
_BOILERPLATE_SENTENCE = re.compile(
    r"ATTENZIONE: prenderemo in carico la richiesta entro due giorni lavorativi"
    r" successivi alla presentazione\.?", re.IGNORECASE)
_MARKDOWN_LINK = re.compile(r"!?\[([^\]]*)]\([^)]*\)")
_MARKDOWN_MARKS = re.compile(r"(^#{1,6}\s*)|(\*\*)|(^\s*[-*]\s+)", re.MULTILINE)
_WHITESPACE = re.compile(r"\s+")


def collapse(text: str | None) -> str:
    """Spazi superflui tolti, compresi quelli non separabili."""
    return _WHITESPACE.sub(" ", (text or "").replace("\xa0", " ")).strip()


def summary(description: str | None, name: str) -> str:
    """La descrizione senza markdown né frasi di rito; vuota se non dice nulla sul servizio ("Descrivi qui...")."""
    text = collapse(_MARKDOWN_MARKS.sub(" ", _MARKDOWN_LINK.sub(r"\1", description or "")))
    text = collapse(_BOILERPLATE_SENTENCE.sub(" ", text))
    if not text or text.lower() == name.lower() or _PLACEHOLDER_DESCRIPTION.fullmatch(text):
        return ""
    return text


def audience_text(audience: dict[str, bool]) -> str:
    """A chi è aperta la categoria, in chiaro: "studenti, esterni"."""
    return ", ".join(name for key, name in AUDIENCE_NAMES if audience.get(key))


def abbreviate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


def card(category: Catalog, with_structure: bool = False) -> dict:
    """La scheda di una categoria; con `with_structure` anche dove vale, per scegliere tra quelle di più strutture."""
    result: dict = {"titolo": category.name}
    who = audience_text(category.audience)
    if who:
        result["per"] = who
    description = summary(category.description, category.name)
    if description:
        result["descrizione"] = abbreviate(description, MAX_DESCRIPTION_CHARS)
    if category.field_labels:
        result["campi"] = category.field_labels[:MAX_FIELD_LABELS]
    if with_structure and category.structure_name:
        result["struttura"] = departments.label(category.structure_name)
        courses = departments.courses(category.structure_name)
        if courses:
            result["corsi"] = courses
    return result
