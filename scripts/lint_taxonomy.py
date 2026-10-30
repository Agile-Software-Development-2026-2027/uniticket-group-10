#!/usr/bin/env python3
"""Validate taxonomy provenance and graph consistency against the catalog."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=Path("uniticket.json"))
    parser.add_argument("--taxonomy", type=Path, default=Path("taxonomy.json"))
    args = parser.parse_args()

    errors: list[str] = []
    try:
        catalog = json.loads(args.catalog.read_text())
        taxonomy = json.loads(args.taxonomy.read_text())
    except (OSError, ValueError) as error:
        print(f"taxonomy lint: unable to read inputs: {error}", file=sys.stderr)
        return 2

    catalog_items = catalog.get("allTicketsFlat") or []
    catalog_by_slug = {item.get("compositeSlug"): item for item in catalog_items}
    nodes = taxonomy.get("nodes") or []
    edges = taxonomy.get("edges") or []
    node_by_id = {node.get("id"): node for node in nodes}
    service_nodes = [node for node in nodes if node.get("type") == "service"]

    source = taxonomy.get("source") or {}
    if source.get("catalogVersion") != catalog.get("catalogVersion"):
        fail(errors, "catalogVersion does not match the catalog")
    if source.get("serviceCount") != len(catalog_items):
        fail(errors, "source.serviceCount does not match catalog size")
    if source.get("nodeCount") != len(nodes):
        fail(errors, "source.nodeCount does not match node count")

    if len(service_nodes) != len(catalog_items):
        fail(errors, "service node count does not match catalog size")
    if len({node.get("id") for node in nodes}) != len(nodes):
        fail(errors, "node IDs are not unique")

    for node in service_nodes:
        slug = node.get("compositeSlug")
        catalog_item = catalog_by_slug.get(slug)
        if catalog_item is None:
            fail(errors, f"service has no catalog entry: {slug}")
            continue
        if node.get("structureSlug") != catalog_item.get("structureSlug"):
            fail(errors, f"structure mismatch for service: {slug}")
        provenance = node.get("source") or {}
        if provenance.get("compositeSlug") != slug:
            fail(errors, f"provenance slug mismatch for service: {slug}")
        if provenance.get("schemaHash") != catalog_item.get("schemaHash"):
            fail(errors, f"schemaHash mismatch for service: {slug}")

    for edge in edges:
        if edge.get("source") not in node_by_id:
            fail(errors, f"edge source does not exist: {edge.get('source')}")
        if edge.get("target") not in node_by_id:
            fail(errors, f"edge target does not exist: {edge.get('target')}")
        if not edge.get("relation"):
            fail(errors, "edge has no relation")

    service_ids = {node.get("id") for node in service_nodes}
    relations = {(edge.get("source"), edge.get("relation"))
                 for edge in edges}
    for service_id in service_ids:
        for relation in ("owned-by", "in-domain", "has-lifecycle", "member-of"):
            if (service_id, relation) not in relations:
                fail(errors, f"service is missing {relation}: {service_id}")

    if errors:
        print(f"taxonomy lint: FAILED ({len(errors)} errors)", file=sys.stderr)
        for error in errors[:20]:
            print(f"- {error}", file=sys.stderr)
        if len(errors) > 20:
            print(f"- ... {len(errors) - 20} more", file=sys.stderr)
        return 1

    print(f"taxonomy lint: OK ({len(service_nodes)} services, "
          f"{len(nodes)} nodes, {len(edges)} edges)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
