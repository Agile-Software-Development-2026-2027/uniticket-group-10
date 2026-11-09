"""Campi di TicketCategory rilevanti per testo e metadata dell’indice."""

from typing import Final, TypedDict


class CategoryMetadata(TypedDict):
    """Metadata obbligatori del record, separati dal testo da embeddare."""

    organizational_structure_id: int
    # La categoria può essere temporaneamente priva di un ufficio competente.
    organizational_office_id: int | None
    # I flag supportano i filtri dell’indice e affiancano i controlli Django.
    allow_user: bool
    allow_employee: bool
    allow_anonymous: bool
    allow_guest: bool
    allow_spid_cie: bool
    # Anche una categoria inattiva conserva un record con questo valore falso.
    is_active: bool


# Soltanto questi campi contribuiscono al testo dell’embedding.
TEXT_FIELDS: Final = (
    "name",
    "description",
)

# I nomi corrispondono alle chiavi del contratto CategoryMetadata.
METADATA_FIELDS: Final = (
    "organizational_structure_id",
    "organizational_office_id",
    "allow_user",
    "allow_employee",
    "allow_anonymous",
    "allow_guest",
    "allow_spid_cie",
    "is_active",
)

# Il futuro confronto prima/dopo deve includere anche le modifiche ai metadata.
INDEX_FIELDS: Final = TEXT_FIELDS + METADATA_FIELDS
