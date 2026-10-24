"""Benchmark dei prototipi: Hit@1, Hit@5, Hit@10 e MRR@5."""

import argparse
import json
import logging
import sys
from importlib import import_module
from importlib.util import module_from_spec, spec_from_file_location
from inspect import Parameter, getmembers, isabstract, isclass, signature
from pathlib import Path
from typing import Dict, List, TypedDict, get_type_hints

from retrival.base import Prototype


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
        # I file esterni possono importare il contratto con retrival.base.
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
    return {
        "count": count,
        **{
            f"hit@{k}": sum(rank is not None and rank <= k for rank in ranks) / count if count else None
            for k in (1, 5, 10)
        },
        "mrr@5": sum(1 / rank for rank in ranks if rank is not None and rank <= 5) / count if count else None,
    }


def evaluate(prototype: Prototype, eval_set: List[TicketEvaluation]):
    """Media per query; ogni query ha un solo ticket atteso. I fallimenti valgono zero."""
    all_ranks = []
    by_query_type = {}
    for ticket in eval_set:
        expected_id = ticket["ticket_category_id"]
        for query_type, queries in ticket["queries"].items():
            ranks = by_query_type.setdefault(query_type, [])
            for query in queries:
                results = prototype.search(query, k=10)
                rank = next((
                    position for position, (ticket_id, _) in enumerate(results[:10], start=1)
                    if ticket_id == expected_id
                ), None)
                ranks.append(rank)
                all_ranks.append(rank)
    return {
        "overall": _metrics(all_ranks),
        "by_query_type": {query_type: _metrics(ranks) for query_type, ranks in by_query_type.items()},
    }


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    directory = Path(__file__).resolve().parent
    # Prima legge il percorso, poi completa la CLI con la firma del prototipo.
    parser = argparse.ArgumentParser(description=__doc__, add_help=False, allow_abbrev=False)
    parser.add_argument("--prototype", type=Path, required=True,
                        help="Percorso di un file .py")
    parser.add_argument("--dataset", type=Path, default=directory / "dataset.json")
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
        tickets = json.loads(args.dataset.read_text(encoding="utf-8"))
        eval_set = json.loads(args.eval_set.read_text(encoding="utf-8"))
        prototype = prototype_class(tickets=tickets, **kwargs)
    except (ValueError, TypeError, ImportError, AttributeError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(evaluate(prototype, eval_set), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
