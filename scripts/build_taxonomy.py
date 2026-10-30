#!/usr/bin/env python3
"""Build a source-grounded semantic taxonomy from the compiled UniTicket catalog.

The taxonomy is a derived index, not a second source of truth. Every service
node points back to one catalog entry and its schema hash. Heuristic labels are
kept explicit so they can be reviewed or replaced without changing the raw
cache.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path


DOMAIN_RULES = (
    ("ict", ("wifi", "wireless", "esse3", "teams", "office365", "spid", "cie",
             "password", "posta elettronica", "email", "rete", "informatica",
             "e-learning", "eligo", "sistema informativo", "sito", "app")),
    ("taxation", ("tass", "pagopa", "contribuz", "rata", "mora", "rimborso")),
    ("mobility", ("erasmus", "mobilità internazionale", "mobilita internazionale",
                  "traineeship", "scambio")),
    ("accommodation-and-welfare", ("borsa", "alloggio", "residenz", "mensa",
                                   "sussid", "stato di bisogno", "necessità",
                                   "necessita", "ristoraz", "quartieri")),
    ("career-and-study", ("esam", "laurea", "tesi", "carriera", "iscrizion",
                          "immatricol", "trasfer", "rinuncia", "sospensione",
                          "certificat", "part-time", "tempo pieno")),
    ("human-resources", ("congedo", "permesso", "incarico", "docenza",
                         "tutorato", "personale", "lavoro agile")),
    ("research", ("ricerca", "dottorat", "pubblicaz", "euraxess")),
)

LIFECYCLE_RULES = (
    ("closure", ("chiusura", "chiudere", "rinuncia", "cessazione", "disattiv")),
    ("change", ("modifica", "cambio", "variazione", "aggiornamento")),
    ("recognition", ("riconoscimento", "convalida", "equipollenza")),
    ("application", ("domanda", "richiesta", "istanza", "partecipazione",
                     "assegnazione", "abilitazione", "attivazione")),
    ("support", ("assistenza", "supporto", "problema", "segnalazione",
                 "helpdesk", "help desk", "errore", "smarr", "reset")),
    ("certificate", ("certificat", "attestazione", "duplicato", "pergamena")),
    ("payment", ("pagamento", "pagare", "rata", "rimborso", "tassa", "mora")),
)

USER_ALIAS_RULES = (
    (("wifi", "wireless", "rete wifi", "rete wireless"),
     ("wifi", "wireless", "connessione internet", "rete internet", "internet non funziona")),
    (("esse3",),
     ("esse3", "prenotare un appello", "prenotazione esame", "esame online")),
    (("teams", "office365"),
     ("teams", "office 365", "account studenti", "piattaforma microsoft")),
    (("spid", "cie"),
     ("spid", "cie", "identita digitale", "accesso ai servizi online")),
    (("rinuncia", "lasciare l universita"),
     ("lasciare l universita", "abbandonare gli studi", "smettere universita")),
    (("sospensione",),
     ("mettere in pausa gli studi", "pausa della carriera", "fermare gli studi")),
    (("tass", "pagopa", "contribuz", "rata", "mora", "rimborso"),
     ("tasse universitarie", "pagamento tasse", "rata tasse", "rimborso tasse")),
    (("esam", "riconoscimento", "convalida"),
     ("convalidare esami", "riconoscere esami", "esami altro ateneo")),
    (("erasmus", "mobilita internazionale", "traineeship"),
     ("erasmus", "mobilita all estero", "partire in erasmus")),
    (("mensa", "ristoraz"),
     ("mensa universitaria", "pasti", "menu mensa")),
)

STOPWORDS = {
    "a", "al", "alla", "alle", "agli", "anche", "con", "da", "del", "della",
    "delle", "dei", "degli", "di", "e", "il", "in", "la", "le", "lo", "nel",
    "nella", "nelle", "non", "per", "su", "un", "una", "uno",
}


def normalize(value: str | None) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def slug(value: str) -> str:
    return normalize(value).replace(" ", "-") or "unknown"


def classify(text: str, rules: tuple[tuple[str, tuple[str, ...]], ...],
             fallback: str) -> tuple[str, list[str]]:
    normalized = normalize(text)
    matches = [
        name for name, keywords in rules
        if any(normalize(keyword) in normalized for keyword in keywords)
    ]
    return (matches[0] if matches else fallback, matches)


def user_aliases(text: str) -> list[str]:
    normalized = normalize(text)
    aliases = []
    for keywords, values in USER_ALIAS_RULES:
        if any(normalize(keyword) in normalized for keyword in keywords):
            aliases.extend(values)
    return list(dict.fromkeys(aliases))


def service_family(title: str) -> str:
    value = normalize(title)
    value = re.sub(r"\b(aa|a a|anno|anni|20\d\d|dd\s+\d+)\b", " ", value)
    value = re.sub(r"\b(per|del|della|di)\s+[a-z0-9-]+$", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return slug(value)


def add_node(nodes: dict[str, dict], node_id: str, node_type: str, label: str,
             **extra: object) -> None:
    nodes.setdefault(node_id, {
        "id": node_id,
        "type": node_type,
        "label": label,
        **extra,
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=Path("uniticket.json"))
    parser.add_argument("--output", type=Path, default=Path("taxonomy.json"))
    args = parser.parse_args()

    catalog = json.loads(args.catalog.read_text())
    items = catalog.get("allTicketsFlat") or []
    nodes: dict[str, dict] = {}
    edges: list[dict[str, str]] = []
    edge_keys: set[tuple[str, str, str]] = set()
    family_members: defaultdict[str, list[str]] = defaultdict(list)

    def edge(source: str, relation: str, target: str) -> None:
        key = (source, relation, target)
        if key not in edge_keys:
            edge_keys.add(key)
            edges.append({"source": source, "relation": relation, "target": target})

    for structure in catalog.get("structures") or []:
        structure_id = f"structure:{structure['structureSlug']}"
        add_node(
            nodes, structure_id, "structure", structure.get("structureName")
            or structure["structureSlug"], slug=structure["structureSlug"],
            active=bool(structure.get("active")),
        )

    for item in items:
        service_id = f"service:{item['compositeSlug']}"
        text = " ".join(filter(None, (
            item.get("categoryTitle"),
            item.get("categoryNotes"),
            item.get("ragSearchText"),
        )))
        domain, domain_matches = classify(text, DOMAIN_RULES, "general-administration")
        lifecycle, lifecycle_matches = classify(text, LIFECYCLE_RULES, "information")
        aliases = user_aliases(text)
        domain_id = f"domain:{domain}"
        lifecycle_id = f"lifecycle:{lifecycle}"
        family = service_family(item.get("categoryTitle", ""))
        family_id = f"family:{family}"

        add_node(nodes, domain_id, "domain", domain.replace("-", " ").title())
        add_node(nodes, lifecycle_id, "lifecycle", lifecycle.replace("-", " ").title())
        add_node(nodes, family_id, "service-family", item["categoryTitle"],
                 normalizedKey=family)
        add_node(
            nodes, service_id, "service", item["categoryTitle"],
            compositeSlug=item["compositeSlug"],
            structureSlug=item["structureSlug"],
            categorySlug=item["categorySlug"],
            source={
                "catalog": str(args.catalog),
                "compositeSlug": item["compositeSlug"],
                "schemaHash": item.get("schemaHash"),
                "availabilityObserved": item.get("availability", {}).get("observedAt"),
            },
            inferred={
                "domain": domain,
                "domainRuleMatches": domain_matches,
                "lifecycle": lifecycle,
                "lifecycleRuleMatches": lifecycle_matches,
                "serviceFamily": family,
                "userAliases": aliases,
            },
        )
        structure_id = f"structure:{item['structureSlug']}"
        edge(service_id, "owned-by", structure_id)
        edge(service_id, "in-domain", domain_id)
        edge(service_id, "has-lifecycle", lifecycle_id)
        edge(service_id, "member-of", family_id)
        family_members[family_id].append(service_id)

    for family_id, members in family_members.items():
        for service_id in members:
            for other_id in members:
                if service_id < other_id:
                    edge(service_id, "variant-of", other_id)

    output = {
        "source": {
            "catalog": str(args.catalog),
            "catalogVersion": catalog.get("catalogVersion"),
            "catalogScrapedAt": catalog.get("scrapedAt"),
            "nodeCount": len(nodes),
            "serviceCount": len(items),
        },
        "taxonomyVersion": "deterministic-v1",
        "generatedFrom": str(args.catalog),
        "inferencePolicy": (
            "Labels and relationships marked inferred are heuristic and must not "
            "override source catalog availability, fields, or eligibility."
        ),
        "nodes": list(nodes.values()),
        "edges": edges,
    }
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {args.output}: {len(nodes)} nodes, {len(edges)} edges")


if __name__ == "__main__":
    main()
