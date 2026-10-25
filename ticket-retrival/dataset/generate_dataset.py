"""Generate an evaluation dataset from ticket categories using concurrent backend calls."""

import argparse
from contextlib import nullcontext
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import sys
import tempfile

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dataset.backends import Config, create_backend, load_config
from dataset.generation.generate_queries import DEFAULT_CONFIG, GeneratedQueries, TicketType, generate_queries


def _read_tickets(source):
    records = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("Il dataset deve essere una lista JSON di ticket")
    tickets = {}
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict) or type(record.get("ticket_category_id")) is not int:
            raise ValueError(f"Ticket {index}: ticket_category_id deve essere un intero")
        category_id = record["ticket_category_id"]
        if category_id in tickets:
            raise ValueError(f"ticket_category_id duplicato: {category_id}")
        structure = record.get("structure") or ""
        ticket_type = TicketType(
            title=record.get("title"), description=record.get("description") or "",
            structure=structure.get("name", "") if isinstance(structure, dict) else structure,
        )
        metadata = dict(record, structure=structure)
        tickets[category_id] = (metadata, ticket_type)
    return tickets


def _save_results(output, results):
    # Replace the checkpoint only after the complete JSON has been written.
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent,
                                     suffix=".json", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(results, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.close()
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)


def generate_dataset(source, *, output="evaluation_dataset.json", parallel=1, config=None):
    """Save completed tickets incrementally, resume matching results, return the failure count."""
    if type(parallel) is not int or parallel < 1:
        raise ValueError("parallel deve essere un intero >= 1")
    source, output = Path(source), Path(output)
    if source.resolve() == output.resolve():
        raise ValueError("Input e output devono essere file diversi")
    if not output.parent.is_dir():
        raise ValueError(f"Directory di output inesistente: {output.parent}")
    tickets = _read_tickets(source)
    results = json.loads(output.read_text(encoding="utf-8")) if output.exists() else []
    if not isinstance(results, list):
        raise ValueError("L'output esistente deve essere una lista JSON")
    processed = set()
    for result in results:
        if not isinstance(result, dict) or type(result.get("ticket_category_id")) is not int:
            raise ValueError("Output esistente: ticket_category_id deve essere un intero")
        category_id = result["ticket_category_id"]
        if category_id not in tickets or category_id in processed:
            raise ValueError(f"Output esistente incompatibile con l'input: ticket {category_id}")
        metadata, _ = tickets[category_id]
        if any(result.get(key) != metadata.get(key) for key in ("title", "description", "structure")):
            raise ValueError(f"Output esistente con metadati diversi: ticket {category_id}")
        GeneratedQueries.model_validate({
            "description_quality": result.get("description_quality"), "queries": result.get("queries"),
        })
        processed.add(category_id)

    if not isinstance(config, Config):
        config = load_config(DEFAULT_CONFIG if config is None else config)
    failures = 0
    completed = len(processed)
    print(f"{completed}/{len(tickets)} ticket già elaborati")
    pending = [(category_id, ticket_type) for category_id, (_, ticket_type) in tickets.items()
               if category_id not in processed]
    context = create_backend(config) if pending else nullcontext(None)
    with context as backend, ThreadPoolExecutor(max_workers=parallel) as executor:
        futures = {
            executor.submit(generate_queries, ticket_type, backend=backend): category_id
            for category_id, ticket_type in pending
        }
        for future in as_completed(futures):
            category_id = futures[future]
            try:
                generated = future.result()
            except Exception as exc:
                failures += 1
                print(f"Errore ticket {category_id}: {exc}", file=sys.stderr)
                continue
            metadata, _ = tickets[category_id]
            results.append(dict(metadata, description_quality=generated.description_quality,
                                queries=generated.queries.model_dump()))
            _save_results(output, results)
            completed += 1
            print(f"[{completed}/{len(tickets)}] Ticket {category_id}: query salvate")
    if not output.exists():
        _save_results(output, results)
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="File JSON dei tipi di ticket")
    parser.add_argument("--parallel", type=int, default=1, help="Richieste simultanee (default: 1)")
    parser.add_argument("--output", type=Path, default=Path("evaluation_dataset.json"),
                        help="File di output/checkpoint (default: evaluation_dataset.json)")
    parser.add_argument("--config", type=Path, help="Configurazione alternativa a generate.yaml")
    args = parser.parse_args()
    if args.parallel < 1:
        parser.error("--parallel deve essere almeno 1")
    failures = generate_dataset(args.source, output=args.output, parallel=args.parallel, config=args.config)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
