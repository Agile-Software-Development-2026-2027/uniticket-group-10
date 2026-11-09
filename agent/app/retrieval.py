"""Ricerca delle categorie di ticket più adatte alla richiesta dell'utente.

Django manda soltanto le categorie attive, non scadute e accessibili all'utente:
qui si scartano quelle nascoste e quelle che l'agente chiede di escludere.
"""

from .contracts import Category


def filter_categories(catalog: list[Category], exclude: list[int] | None = None,
                      structure_ids: list[int] | None = None) -> list[Category]:
    """Le categorie proponibili: visibili, non escluse e, se indicate, delle strutture scelte."""
    excluded = set(exclude or [])
    structures = set(structure_ids or [])
    return [
        category for category in catalog
        if not category.hidden
        and category.id not in excluded
        and (not structures or category.structure_id in structures)
    ]
