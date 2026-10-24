"""Generate validated queries for one ticket type, without dataset file handling."""

from __future__ import annotations

import json
from contextlib import nullcontext
from pathlib import Path
import sys
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

if not __package__:
    # Permette anche l'avvio diretto del file da qualunque cartella.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dataset.backends import Backend, Config, create_backend


NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class TicketType(BaseModel):
    """Required title; description and structure may be omitted, but cannot be null."""

    model_config = ConfigDict(extra="forbid")

    title: NonEmptyText
    description: str = ""
    structure: str = ""


class Queries(BaseModel):
    """All categories are required, each with three non-empty, distinct queries."""

    model_config = ConfigDict(extra="forbid")

    direct: list[NonEmptyText] = Field(min_length=3, max_length=3)
    paraphrase: list[NonEmptyText] = Field(min_length=3, max_length=3)
    indirect: list[NonEmptyText] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def reject_duplicates(self) -> Queries:
        queries = self.direct + self.paraphrase + self.indirect
        normalized = {" ".join(query.split()).casefold() for query in queries}
        if len(normalized) != len(queries):
            raise ValueError("Queries must be distinct across all categories")
        return self


class GeneratedQueries(BaseModel):
    """Both description_quality and queries are required and cannot be null."""

    model_config = ConfigDict(extra="forbid")

    description_quality: Literal["informative", "partially_informative", "uninformative"]
    queries: Queries


DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "generate.yaml"
PROMPT_PATH = Path(__file__).resolve().with_name("GENERATION_PROMPT.md")


def load_prompt() -> str:
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    if not prompt.strip():
        raise ValueError(f"Generation prompt is empty: {PROMPT_PATH}")
    return prompt


def generate_queries(
    ticket_type: TicketType, *, backend: Backend | None = None,
    config: Config | str | Path | None = None,
) -> GeneratedQueries:
    """Generate queries using a reusable backend, or own one for this single call."""
    if backend is not None and config is not None:
        raise ValueError("Pass backend or config, not both")
    system_prompt = load_prompt()
    if backend is None:
        context = create_backend(DEFAULT_CONFIG if config is None else config)
    else:
        context = nullcontext(backend)
    with context as engine:
        content = engine.execute(
            json.dumps(ticket_type.model_dump(), ensure_ascii=False),
            system_prompt=system_prompt, schema=GeneratedQueries.model_json_schema(),
        )
    if not content or not content.strip():
        raise ValueError("Empty LLM response")
    return GeneratedQueries.model_validate_json(content)


def main():
    load_prompt()
    print(f"Prompt: {PROMPT_PATH}", file=sys.stderr)
    ticket = TicketType(
        title="EL-S1 - Richiesta supporto piattaforma e-learning di Ateneo",
        description="Modulo di richiesta supporto piattaforma e-learning Moodle di Ateneo (non MS Teams)",
        structure="Area Servizi Informatici e Tecnologici",
    )
    with create_backend(DEFAULT_CONFIG) as backend:
        print(f"Backend: {type(backend).__name__}", file=sys.stderr)
        print(f"Modello: {backend.config.model_name}", file=sys.stderr)
        print(f"Configurazione:\n{backend.config.model_dump_json(indent=2)}", file=sys.stderr)
        queries = generate_queries(ticket, backend=backend)
    print(json.dumps(queries.model_dump(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
