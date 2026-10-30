#!/usr/bin/env python3
"""Build the runtime catalog from the raw UniTicket cache.

The raw cache is the source of truth.  Form fields are retained for a future
form-filling stage, while ``jevCriterionSummary`` and ``ragSearchText`` are
derived views with different purposes.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import unicodedata
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


GENERIC_FIELD_IDS = {
    "ticket_subject",
    "ticket_description",
    "nome",
    "cognome",
    "codice_fiscale",
    "email",
    "telefono",
    "cellulare",
    "indirizzo_email",
    "indirizzo_e_mail",
    "numero_telefonico",
}
CONDITION_WORDS = (
    "dichiaro",
    "dichiarazione",
    "consenso",
    "responsabil",
    "presa visione",
    "accetto",
    "autorizzo",
    "privacy",
)


class OptionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.options: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "option":
            return
        attributes = dict(attrs)
        self._current = {
            "value": html.unescape((attributes.get("value") or "").strip()),
            "label": "",
        }

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._current["label"] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "option" and self._current is not None:
            item = {
                "value": re.sub(r"\s+", " ", self._current["value"]).strip(),
                "label": clean_domain_text(self._current["label"]),
            }
            if item["label"] or item["value"]:
                self.options.append(item)
            self._current = None


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def clean_domain_text(value: str | None) -> str:
    return re.sub(r"https?://\S+|\[[^\]]+\]\([^)]+\)", "", clean(value))


def is_generic_field(field: dict) -> bool:
    field_id = field["id"]
    label = field["label"].lower()
    if field_id in GENERIC_FIELD_IDS:
        return True
    return (
        ("email" in label or "e-mail" in label or "mail" in label)
        and not any(word in label for word in ("problema", "access", "account"))
    ) or (
        ("telefono" in label or "cellulare" in label or "recapito" in label)
        and not any(word in label for word in ("problema", "servizio"))
    )


def is_noise(value: str) -> bool:
    value = value.strip().lower()
    return (
        not value
        or value in {"scegli una opzione", "seleziona", "nessuna selezione"}
        or value.startswith(("http://", "https://", "[http://", "[https://"))
    )


def safe_id(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = normalized.encode("ascii", "ignore").decode("ascii").lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    return normalized or "field"


def parse_options(field: dict) -> list[dict[str, str]]:
    options = []
    for option in field.get("options") or []:
        if isinstance(option, dict):
            value = clean(str(option.get("value", "")))
            label = clean_domain_text(str(option.get("label", option.get("text", value))))
            if value or label:
                options.append({"value": value, "label": label})
    if not options and field.get("html"):
        parser = OptionParser()
        parser.feed(field["html"])
        options = parser.options
    unique = []
    seen = set()
    for option in options:
        key = (option["value"], option["label"])
        if key not in seen:
            seen.add(key)
            unique.append(option)
    return unique


def availability(category: dict, form: dict, status: int) -> tuple[str, str]:
    if status == 200 and form.get("form"):
        return "open", "form fetched successfully"
    if status == 403:
        return "unknown", "access denied for the scraping profile"
    if status == 404:
        return "unknown", "not available to the scraping profile or currently inactive"
    if status >= 500:
        return "unknown", "server error while fetching the form"
    return "unknown", f"HTTP {status}"


def observed_reason(form: dict, status: int) -> str | None:
    if status == 200:
        return None
    detail = form.get("detail")
    if detail:
        return f"HTTP {status}: {clean(str(detail))}"
    message = category_message(form)
    return f"HTTP {status}: {message}" if message else f"HTTP {status}"


def category_message(form: dict) -> str:
    messages = form.get("messages") or []
    if isinstance(messages, list):
        values = []
        for item in messages:
            if isinstance(item, dict):
                values.extend(str(v) for v in item.values() if v)
            elif item:
                values.append(str(item))
        if values:
            return clean(" ".join(values))
    return ""


def field_policy(field_id: str, label: str, field_type: str, disabled: bool) -> str:
    if disabled:
        return "NEVER"
    normalized = f"{field_id} {label}".lower()
    if field_id in {"ticket_subject", "ticket_description"}:
        return "AUTO_GENERATE_FROM_CONTEXT"
    if field_type == "checkbox" and (
        field_id == "condizioni_field_id"
        or any(word in normalized for word in CONDITION_WORDS)
    ):
        return "EXPLICIT_USER_CONFIRMATION"
    return "ASK_USER"


def build_field(field: dict, previous_fields: list[dict]) -> dict:
    original_id = clean(str(field.get("id", "")))
    label = clean_domain_text(str(field.get("label", "")))
    field_type = clean(str(field.get("type", "text"))).lower() or "text"
    form_field_name = original_id
    result = {
        "id": safe_id(original_id),
        "formFieldName": form_field_name,
        "label": label,
        "type": field_type,
        "required": bool(field.get("required")),
        "disabled": bool(field.get("disabled")),
        "initial": field.get("initial"),
        "helpText": clean(str(field.get("help_text", ""))) or None,
        "resolutionStrategy": field_policy(
            original_id, label, field_type, bool(field.get("disabled"))
        ),
    }
    options = parse_options(field)
    if options:
        result["options"] = options
    conditional_text = f"{original_id} {label}".lower()
    if re.search(
        r"^(se\b|qualora\b|nel caso\b)|\bse\s+['\"]?(no|si|sì|altro)\b|"
        r"\bse hai (selezionato|scelto)\b",
        conditional_text,
    ):
        dependency = next(
            (
                previous for previous in reversed(previous_fields)
                if previous["type"] in {"select", "radio", "checkbox"}
            ),
            None,
        )
        if dependency is not None:
            result["dependsOn"] = {
                "fieldId": dependency["id"],
                "conditionText": label,
            }
    return result


def target_audience(category: dict) -> str:
    audiences = []
    if category.get("allow_user"):
        audiences.append("utenti autenticati")
    if category.get("allow_employee"):
        audiences.append("personale")
    if category.get("allow_guest"):
        audiences.append("ospiti")
    if category.get("allow_spid_cie"):
        audiences.append("utenti SPID/CIE")
    return ", ".join(audiences) if audiences else "profilo non determinato"


def build_category(category: dict, raw_form: dict | None) -> dict:
    raw_form = raw_form or {}
    status = int(raw_form.get("_status", 0))
    form = raw_form.get("jsonBody", raw_form)
    title = clean_domain_text(category.get("name"))
    description = clean_domain_text(category.get("description"))
    structure_slug = clean(str(category.get("organizational_structure", "")))
    slug = clean(str(category.get("slug", "")))
    form_fields = []
    for field in form.get("form") or []:
        form_fields.append(build_field(field, form_fields))
    status_name, status_reason = availability(category, form, status)
    accessible = status == 200 and bool(form.get("form"))

    # Only domain-bearing field labels/options enter retrieval.  Generic
    # identity fields and legal declarations are form data, not service intent.
    search_parts = [clean(category.get("organizational_structure")), title, description]
    for field in form_fields:
        if is_generic_field(field):
            continue
        if field["resolutionStrategy"] == "EXPLICIT_USER_CONFIRMATION":
            continue
        if not is_noise(field["label"]):
            search_parts.append(field["label"])
        search_parts.extend(
            option["label"] for option in field.get("options", [])
            if not is_noise(option["label"])
        )
    search_parts = list(dict.fromkeys(part for part in search_parts if not is_noise(part)))
    rag_text = ". ".join(search_parts)

    card = {
        "title": title,
        "structure": clean(category.get("organizational_structure")),
        "targetAudience": target_audience(category),
        "scope": description or clean(category.get("description")),
        "availability": status_name,
        "availabilityObservation": status_reason,
    }
    summary = (
        f"Struttura: {card['structure']} | Richiesta: {title} | "
        f"Destinatari: {card['targetAudience']} | Ambito: {card['scope'] or 'non specificato'} | "
        f"Disponibilità osservata: {status_name}"
    )

    schema_payload = json.dumps(form_fields, ensure_ascii=False, sort_keys=True).encode()
    schema_hash = hashlib.sha256(schema_payload).hexdigest() if form_fields else None
    return {
        "compositeSlug": f"{structure_slug}__{slug}",
        "structureSlug": structure_slug,
        "structureName": structure_slug,
        "categorySlug": slug,
        "categoryTitle": title,
        "url": clean(raw_form.get("url") or category.get("url")),
        "accessible": accessible,
        "accessRestrictionReason": observed_reason(form, status),
        "availability": {
            "status": status_name,
            "reasonCode": (
                "OPEN" if status == 200 else
                "ACCESS_OBSERVATION" if status == 403 else
                "UNAVAILABLE_OBSERVATION" if status == 404 else
                "FETCH_ERROR"
            ),
            "observedHttpStatus": status,
            "observedAt": raw_form.get("fetchedAt"),
            "sourceProfile": "raw_cache",
        },
        "routerCard": card,
        "categoryNotes": description,
        "schemaHash": schema_hash,
        "jevCriterionSummary": summary,
        "ragSearchText": rag_text,
        "fields": form_fields,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-cache", type=Path, default=Path("raw_cache"))
    parser.add_argument("--output", type=Path, default=Path("uniticket.json"))
    args = parser.parse_args()

    categories = json.loads((args.raw_cache / "categories.json").read_text())
    forms_by_slug = {}
    for path in (args.raw_cache / "forms").glob("*.json"):
        payload = json.loads(path.read_text())
        body = payload.get("jsonBody") or {}
        structure_slug, filename_slug = path.name.removesuffix(".api.json").split("__", 1)
        slug = body.get("slug") or filename_slug
        payload["_status"] = payload.get("statusCode", 0)
        forms_by_slug[(structure_slug, slug)] = payload

    existing_names = {}
    if args.output.is_file():
        try:
            previous = json.loads(args.output.read_text())
            existing_names = {
                item.get("structureSlug"): item.get("structureName")
                for item in previous.get("structures", [])
                if item.get("structureSlug") and item.get("structureName")
            }
        except (OSError, ValueError):
            pass

    flat = [
        build_category(
            category,
            forms_by_slug.get(
                (category.get("organizational_structure"), category.get("slug"))
            ),
        )
        for category in categories
    ]
    for item in flat:
        item["structureName"] = existing_names.get(
            item["structureSlug"], item["structureSlug"]
        )
        item["routerCard"]["structure"] = item["structureName"]
        item["jevCriterionSummary"] = (
            item["jevCriterionSummary"]
            .replace(
                f"Struttura: {item['structureSlug']}",
                f"Struttura: {item['structureName']}",
                1,
            )
        )
    structures = {}
    for category, item in zip(categories, flat):
        slug = item["structureSlug"]
        structure = structures.setdefault(
            slug,
            {
                "structureSlug": slug,
                "structureName": item["structureName"],
                "active": False,
                "categories": [],
            },
        )
        structure["active"] |= bool(category.get("is_active"))
        structure["categories"].append(item)

    result = {
        "scrapedAt": datetime.now(timezone.utc).isoformat(),
        "baseUrl": "https://ticket.unical.it",
        "catalogVersion": "raw-cache-derived-v1",
        "structures": list(structures.values()),
        "allTicketsFlat": flat,
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {args.output}: {len(structures)} structures, {len(flat)} categories")


if __name__ == "__main__":
    main()
