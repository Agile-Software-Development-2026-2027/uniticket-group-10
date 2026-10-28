"""Benchmark dei prototipi: Hit@1, Hit@5, Hit@10 e MRR@5."""

import argparse
import hashlib
import math
import statistics
from time import perf_counter
import json
import logging
import sys
from importlib import import_module
from importlib.util import module_from_spec, spec_from_file_location
from inspect import Parameter, getmembers, isabstract, isclass, signature
from pathlib import Path
from typing import Dict, List, TypedDict, get_type_hints

from prototypes.base import Prototype
from prototypes.models import load_tickets


class TicketEvaluation(TypedDict):
    ticket_category_id: int
    queries: Dict[str, List[str]]


def load_prototype_class(path):
    path = Path(path).resolve()
    if path.suffix != ".py":
        raise ValueError("Il prototipo deve essere il percorso di un file .py")
    if not path.is_file():
        raise ValueError(f"File del prototipo non trovato: {path}")
    try:
        relative_path = path.relative_to(Path(__file__).resolve().parent)
    except ValueError:
        # I file esterni possono importare il contratto con prototypes.base.
        module_name = "_benchmark_prototype"
        spec = spec_from_file_location(module_name, path)
        module = module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(module_name, None)
            raise
    else:
        # Conserva il package, così funzionano anche gli import relativi.
        module_name = ".".join(relative_path.with_suffix("").parts)
        module = import_module(module_name)
    classes = [
        cls for _, cls in getmembers(module, isclass)
        if cls.__module__ == module_name and issubclass(cls, Prototype) and not isabstract(cls)
    ]
    if len(classes) != 1:
        raise ValueError(f"Il file {path} deve definire una sola classe concreta derivata da Prototype")
    return classes[0]


def _json_or_string(value):
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def add_constructor_arguments(parser, prototype_class):
    """Espone i parametri espliciti del costruttore, preservandone tipi e default."""
    hints = get_type_hints(prototype_class.__init__)
    names = []
    for name, parameter in signature(prototype_class.__init__).parameters.items():
        if name in ("self", "tickets") or parameter.kind in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD):
            continue
        if parameter.kind == Parameter.POSITIONAL_ONLY:
            raise ValueError(f"Il parametro {name} deve poter essere passato per nome")
        default = parameter.default
        value_type = hints.get(name, type(default))
        options = {
            "dest": name,
            "default": argparse.SUPPRESS,
            "required": default is Parameter.empty,
            "help": "obbligatorio" if default is Parameter.empty else f"default: {getattr(default, '__name__', repr(default))}",
        }
        if value_type is bool:
            options["action"] = argparse.BooleanOptionalAction
        else:
            options["type"] = value_type if value_type in (str, int, float, Path) else _json_or_string
        flags = ["--" + name.replace("_", "-")]
        if "_" in name:
            flags.append("--" + name)
        parser.add_argument(*flags, **options)
        names.append(name)
    return names


def _metrics(ranks):
    count = len(ranks)
    ordered = sorted(ranks, key=lambda rank: math.inf if rank is None else rank)
    return {
        "count": count,
        "p95_rank": ordered[math.ceil(.95 * count) - 1] if count else None,
        **{
            f"hit@{k}": sum(rank is not None and rank <= k for rank in ranks) / count if count else None for k in (1, 5, 10)
        },
        "mrr@5": sum(1 / rank for rank in ranks if rank is not None and rank <= 5) / count if count else None,
    }


def _summary(ranks, times, errors, abstentions):
    ordered = sorted(times)
    return {
        **_metrics(ranks),
        "errors": errors,
        "abstentions": abstentions,
        "latency_ms": {
            "count": len(times),
            "mean": statistics.mean(times) if times else None,
            "median": statistics.median(times) if times else None,
            "p95": ordered[math.ceil(.95 * len(ordered)) - 1] if times else None,
        },
    }


def evaluate(prototype: Prototype, eval_set: List[TicketEvaluation]):
    """Single-label evaluation. Failed calls and abstentions stay in the denominator."""
    valid_ids = {ticket.id for ticket in prototype.tickets}
    # Invalid ground truth is a dataset problem, not a classifier error.
    for ticket in eval_set:
        if ticket["ticket_category_id"] not in valid_ids:
            raise ValueError(f"Ground truth outside catalog: {ticket['ticket_category_id']}")
        for queries in ticket["queries"].values():
            if not isinstance(queries, list) or any(not isinstance(q, str) or not q.strip() for q in queries):
                raise ValueError("Each query must be a non-empty string")
    all_ranks, all_times, by_type, details = [], [], {}, []
    ranks_by_ticket = {}
    errors = abstentions = 0
    for ticket in eval_set:
        expected_id = ticket["ticket_category_id"]
        for query_type, queries in ticket["queries"].items():
            group = by_type.setdefault(query_type, {"ranks": [], "times": [], "errors": 0, "abstentions": 0})
            for query_index, query in enumerate(queries):
                started = perf_counter()
                error = None
                predicted = []
                try:
                    results = prototype.search(query, k=len(prototype.tickets))
                    if not isinstance(results, list):
                        raise ValueError("search() must return a list")
                    seen = set()
                    for category_id, score in results:
                        if category_id not in valid_ids or category_id in seen or not math.isfinite(float(score)):
                            raise ValueError("Invalid or duplicate category ID or non-finite score")
                        seen.add(category_id)
                        predicted.append(category_id)
                except Exception as exc:
                    error = type(exc).__name__  # No provider messages or credentials in reports.
                    predicted = []
                elapsed = (perf_counter() - started) * 1000
                rank = predicted.index(expected_id) + 1 if expected_id in predicted else None
                abstention = not predicted and error is None
                errors += int(error is not None)
                abstentions += int(abstention)
                group["errors"] += int(error is not None)
                group["abstentions"] += int(abstention)
                group["ranks"].append(rank)
                group["times"].append(elapsed)
                all_ranks.append(rank)
                ranks_by_ticket.setdefault(expected_id, []).append(rank)
                all_times.append(elapsed)
                details.append({"expected_id": expected_id, "query_type": query_type,
                                "query_index": query_index, "predicted_ids": predicted,
                                "rank": rank, "latency_ms": elapsed, "error": error})
    by_ticket = {
        ticket_id: {"count": len(ranks),
                    "hit@10": sum(rank is not None and rank <= 10 for rank in ranks) / len(ranks)}
        for ticket_id, ranks in sorted(ranks_by_ticket.items())
    }
    tickets_without_hits = [ticket_id for ticket_id, metrics in by_ticket.items() if metrics["hit@10"] == 0]
    return {
        "overall": _summary(all_ranks, all_times, errors, abstentions),
        "by_ticket": by_ticket,
        "by_query_type": {name: _summary(g["ranks"], g["times"], g["errors"], g["abstentions"])
                          for name, g in by_type.items()},
        "coverage": {"catalog_categories": len(valid_ids),
                     "tickets_without_hit@10": len(tickets_without_hits),
                     "ticket_ids_without_hit@10": tickets_without_hits,
                     "evaluated_categories": len({t["ticket_category_id"] for t in eval_set if any(t["queries"].values())}),
                     "uncovered_category_ids": sorted(valid_ids - {t["ticket_category_id"] for t in eval_set if any(t["queries"].values())})},
        "cases": details,
    }


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    directory = Path(__file__).resolve().parent
    # Prima legge il percorso, poi completa la CLI con la firma del prototipo.
    parser = argparse.ArgumentParser(description=__doc__, add_help=False, allow_abbrev=False)
    parser.add_argument("--prototype", type=Path, required=True,
                        help="Percorso di un file .py")
    parser.add_argument("--dataset", type=Path, default=directory / "tickets.json")
    parser.add_argument("--eval-set", type=Path, default=directory / "evaluation_dataset.json")
    selection, _ = parser.parse_known_args()
    try:
        prototype_class = load_prototype_class(selection.prototype)
        names = add_constructor_arguments(parser, prototype_class)
    except (ValueError, TypeError, ImportError, AttributeError, argparse.ArgumentError) as exc:
        parser.error(str(exc))
    parser.add_argument("-h", "--help", action="help", help="Mostra i parametri del prototipo selezionato")
    args = parser.parse_args()
    try:
        kwargs = {name: vars(args)[name] for name in names if name in vars(args)}
        tickets = load_tickets(args.dataset)
        eval_set = json.loads(args.eval_set.read_text(encoding="utf-8"))
        started = perf_counter()
        prototype = prototype_class(tickets=tickets, **kwargs)
        initialization_ms = (perf_counter() - started) * 1000
    except (ValueError, TypeError, ImportError, AttributeError, OSError, NotImplementedError) as exc:
        parser.error(str(exc))
    try:
        report = evaluate(prototype, eval_set)
    except (ValueError, TypeError, KeyError) as exc:
        parser.error(str(exc))
    report["initialization_ms"] = initialization_ms
    report["experiment"] = {
        "prototype": str(args.prototype), "parameters": kwargs,
        "catalog_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
        "evaluation_sha256": hashlib.sha256(args.eval_set.read_bytes()).hexdigest(),
        "python": sys.version.split()[0],
        "protocol": "single-label; k=catalog size; full ranking; no warmup/retries; latency includes search and result validation; initialization separate; errors count as misses",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
