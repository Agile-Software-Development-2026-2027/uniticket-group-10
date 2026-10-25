"""Extract original tickets and form metadata from a Django configuration dump."""

import argparse
from collections import defaultdict
from datetime import datetime
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo


DEFAULT_SOURCE = "./local_conf.json"
MODELS = {
    "uni_ticket.ticketcategory",
    "uni_ticket.ticketcategorymodule",
    "uni_ticket.ticketcategoryinputlist",
    "organizational_area.organizationalstructure",
}


def extract_tickets(source=DEFAULT_SOURCE, *, active=None, hidden=None, expired=None, not_empty_fields=False):
    """Return {'ticket': ...} records, preserving original field IDs and metadata."""
    records = json.loads(Path(source).read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("Il dump deve essere una lista JSON")
    tables = {model: {} for model in MODELS}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Ogni record del dump deve essere un oggetto")
        model = record.get("model")
        if model not in tables:
            continue
        pk, fields = record.get("pk"), record.get("fields")
        if type(pk) is not int or not isinstance(fields, dict):
            raise ValueError(f"Record non valido per {model}: servono pk intero e fields oggetto")
        if pk in tables[model]:
            raise ValueError(f"ID duplicato per {model}: {pk}")
        tables[model][pk] = fields

    tickets = tables["uni_ticket.ticketcategory"]
    modules = tables["uni_ticket.ticketcategorymodule"]
    structures = tables["organizational_area.organizationalstructure"]
    fields_by_ticket = defaultdict(list)
    for module_id, module in modules.items():
        if module.get("ticket_category") not in tickets:
            raise ValueError(f"Modulo {module_id}: ticket non trovato")
    for field_id, field in tables["uni_ticket.ticketcategoryinputlist"].items():
        module_id = field.get("category_module")
        if module_id not in modules:
            raise ValueError(f"Campo {field_id}: modulo {module_id} non trovato")
        fields_by_ticket[modules[module_id]["ticket_category"]].append({**field, "id": field_id})

    results = []
    now = datetime.now(ZoneInfo("Europe/Rome"))
    for ticket_id, ticket in tickets.items():
        if not_empty_fields and not fields_by_ticket[ticket_id]:
            continue
        if active is not None and ticket.get("is_active") is not active:
            continue
        if hidden is not None and ticket.get("is_hidden") is not hidden:
            continue
        if expired is not None:
            date_end = ticket.get("date_end")
            is_expired = False
            if date_end:
                end = datetime.fromisoformat(date_end)
                if end.tzinfo is None:
                    end = end.replace(tzinfo=now.tzinfo)
                is_expired = end < now
            if is_expired is not expired:
                continue
        structure_id = ticket.get("organizational_structure")
        structure = {}
        if structure_id is not None:
            if structure_id not in structures:
                raise ValueError(f"Ticket {ticket_id}: struttura {structure_id} non trovata")
            original = structures[structure_id]
            structure = {"id": structure_id, "name": original.get("name", ""),
                         "description": original.get("description") or ""}
        fields = sorted(fields_by_ticket[ticket_id], key=lambda field: (
            field["category_module"], field.get("ordinamento", 0), field["id"],
        ))
        results.append({"ticket": {
            **{key: value for key, value in ticket.items() if key != "name"},
            "id": ticket_id,
            "title": ticket.get("name") or "",
            "description": ticket.get("description") or "",
            "structure": structure,
            "fields": fields,
        }})
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE,
                        help="Dump JSON (default: dumps/local_conf.json)")
    parser.add_argument("--output", type=Path, help="File JSON di output; se omesso stampa su stdout")
    parser.add_argument("--not-empty-fields", action="store_true",
                        help="Include solo i ticket con almeno un campo del form")
    for name, description in (
        ("active", "Filtra is_active"),
        ("hidden", "Filtra is_hidden"),
        ("expired", "Filtra i ticket con date_end passata; senza scadenza sono non scaduti"),
    ):
        parser.add_argument("--" + name, choices=("true", "false"), help=description)
    args = parser.parse_args(argv)
    if args.output and args.source.resolve() == args.output.resolve():
        parser.error("Input e output devono essere file diversi")
    try:
        filters = {name: None if getattr(args, name) is None else getattr(args, name) == "true"
                   for name in ("active", "hidden", "expired")}
        results = extract_tickets(args.source, not_empty_fields=args.not_empty_fields, **filters)
        content = json.dumps(results, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.write_text(content, encoding="utf-8")
        else:
            sys.stdout.write(content)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
