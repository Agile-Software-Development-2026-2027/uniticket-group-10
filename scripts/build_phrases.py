#!/usr/bin/env python3
"""Generate colloquial student/staff phrasing for every catalog form.

The output is an overlay (form_phrases.json, compositeSlug -> list of phrases)
that the search index reads alongside uniticket.json. It uses catalog text only
and never writes to the catalog itself.

Reruns are incremental: forms that already have phrases are skipped, so a run
can be interrupted, and a stronger model can be used by deleting the file.

Usage: python3 scripts/build_phrases.py [--model NAME] [--url URL] [--out FILE]
"""
import argparse
import json
import os
import urllib.request

SYSTEM = (
    "Sei un esperto dei servizi dell'Università della Calabria. Dato un modulo di richiesta, "
    "scrivi 6 frasi brevi e colloquiali in italiano, in prima persona, con cui uno studente o un "
    "dipendente descriverebbe il proprio bisogno SENZA conoscere il nome del modulo. Usa parole "
    "quotidiane diverse da quelle del titolo. Non inventare servizi diversi da quello descritto."
)
SCHEMA = {
    "type": "object",
    "properties": {"frasi": {"type": "array", "items": {"type": "string"}}},
    "required": ["frasi"],
}
PHRASES_PER_FORM = 6


def generate(url, model, item):
    prompt = (
        f"Titolo: {item['categoryTitle']}\n"
        f"Struttura: {item['structureName']}\n"
        f"Descrizione: {(item.get('categoryNotes') or '')[:400]}\n"
        f"Contenuto del modulo: {(item.get('ragSearchText') or '')[:500]}"
    )
    body = json.dumps({
        "model": model,
        "stream": False,
        "format": SCHEMA,
        "options": {"temperature": 0.3, "num_ctx": 2048, "num_predict": 700},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
    }).encode()
    request = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=240) as response:
        content = json.load(response)["message"]["content"]
    phrases = [str(p).strip() for p in json.loads(content).get("frasi", [])]
    return [p for p in phrases if p][:PHRASES_PER_FORM]


def save(path, phrases):
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(phrases, handle, ensure_ascii=False, indent=0, sort_keys=True)
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default="uniticket.json")
    parser.add_argument("--out", default="form_phrases.json")
    parser.add_argument("--model", default="qwen2.5:3b")
    parser.add_argument("--url", default="http://localhost:11434/api/chat")
    parser.add_argument("--attempts", type=int, default=3)
    args = parser.parse_args()

    with open(args.catalog, encoding="utf-8") as handle:
        items = json.load(handle)["allTicketsFlat"]
    phrases = {}
    if os.path.exists(args.out):
        with open(args.out, encoding="utf-8") as handle:
            phrases = {k: v for k, v in json.load(handle).items() if v}

    missing = [item for item in items if item["compositeSlug"] not in phrases]
    failed = []
    for position, item in enumerate(missing, 1):
        for attempt in range(args.attempts):
            try:
                result = generate(args.url, args.model, item)
            except Exception as error:  # a timeout or truncated JSON: try again
                print(f"retry {attempt + 1} {item['compositeSlug']}: {error}", flush=True)
                continue
            if result:
                phrases[item["compositeSlug"]] = result
                break
        else:
            failed.append(item["compositeSlug"])
        if position % 20 == 0:
            save(args.out, phrases)
            print(f"{position}/{len(missing)}", flush=True)
    save(args.out, phrases)
    print(f"done: {len(phrases)}/{len(items)} forms, {len(failed)} failed")
    for slug in failed:
        print("failed", slug)


if __name__ == "__main__":
    main()
