"""Aggiorna local_conf.json con l'API di ticket.unical.it (raw_cache) e il dump ICT (uniticket-dump).

    python3 build_fixture.py --raw-cache DIR --dump DIR [--out FILE] [--report FILE]
    python3 build_fixture.py --raw-cache DIR --validate

--raw-cache: le risposte dell'API (structures.json, categories.json e forms/<struttura>__<categoria>.api.json).
--dump: i file del dump ICT nel formato di dumpdata (strutture, uffici, tipologie, moduli, campi).
--out: dove scrivere il catalogo aggiornato (default: sovrascrive local_conf.json accanto a questo file).
--report: dove scrivere l'elenco delle modifiche in Markdown (default: non lo scrive).
--validate: misura solo il convertitore form API -> campi, sui form già presenti in local_conf.json.

Non modifica nessun file di input. Regole:
- le categorie si abbinano per (slug struttura, slug categoria): gli ID del file locale sono rinumerati,
  quelli del dump sono di produzione; gli oggetti nuovi prendono ID sopra i massimi attuali;
- una categoria rinominata (stessa struttura e stesso `created` al microsecondo) si aggiorna sul posto;
- `receive_email` e `protocol_required` restano false e `allowed_users*` vuoti, come nel file di Angelo
  (in locale email e protocollo non sono configurati; gli utenti del dump non esistono nel file);
- una categoria è attiva solo se ha un modulo attivo, come nel file di Angelo;
- per le categorie ICT vale il dump (13/11), più recente dell'API (3/11).
"""

import argparse
import collections
import glob
import html
import json
import os
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.join(HERE, "local_conf.json")
# Impostati dagli argomenti della riga di comando.
RAW = DUMP = OUT = REPORT = None

STRUCT, OFFICE = "organizational_area.organizationalstructure", "organizational_area.organizationalstructureoffice"
CAT, MOD = "uni_ticket.ticketcategory", "uni_ticket.ticketcategorymodule"
FIELD, COND = "uni_ticket.ticketcategoryinputlist", "uni_ticket.ticketcategorycondition"
ROME = ZoneInfo("Europe/Rome")
# Campi della categoria che restano come nel file di Angelo, qualunque cosa dicano le fonti.
FORCED = {"receive_email": False, "protocol_required": False, "allowed_users": [], "allowed_users_lists": []}
# Campi della categoria aggiornati dalle fonti (is_active segue invece la presenza del modulo).
SYNCED = ["name", "slug", "description", "date_start", "date_end", "created", "modified", "not_available_message",
          "show_heading_text", "allow_anonymous", "allow_guest", "allow_user", "allow_employee", "allow_spid_cie",
          "is_notification", "footer_text", "is_hidden", "user_multiple_open_tickets", "max_requests_per_user",
          "confirm_message_text"]


def rome(value):
    """Le date del dump sono in UTC con 'Z'; il file locale le tiene in ora italiana, come l'API."""
    if not isinstance(value, str) or not value.endswith("Z"):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(ROME).isoformat()


def same_instant(a, b):
    if not (isinstance(a, str) and isinstance(b, str)):
        return False
    try:
        return abs((datetime.fromisoformat(a) - datetime.fromisoformat(b)).total_seconds()) < 0.001
    except ValueError:
        return False


# ---------------------------------------------------------------- convertitore form API -> campi

def option_values(markup):
    return [html.unescape(v) for v in re.findall(r'<option value="([^"]*)"', markup) if v != ""]


def input_values(markup):
    return [html.unescape(v) for v in re.findall(r'<input type="(?:radio|checkbox)"[^>]*value="([^"]*)"', markup)]


def table_columns(fid, markup):
    """CustomComplexTableField: le colonne del formset, nel formato `id({...})#id({...})` del file locale."""
    cols = []
    for row in markup.split("<tr>")[1:]:
        head = re.search(r'<label for="id_' + re.escape(fid) + r'-NNNNN-([^"]+)">(.*?):?</label>', row)
        if not head:
            continue
        col, label = html.unescape(head.group(1)), head.group(2)
        cell = row.split("<td>", 1)[1].split("</td>", 1)[0] if "<td>" in row else ""
        spec = {"type": cell_type(cell), "required": bool(re.search(r"\srequired[\s>=]", cell)),
                "label": html.unescape(label)}
        if spec["type"] in ("CustomSelectBoxField", "CustomRadioBoxField", "MultiCheckBoxField"):
            spec["choices"] = ";".join(option_values(cell) or input_values(cell))
        cols.append(f"{col}({spec!r})")
    return "#".join(cols)


def cell_type(cell):
    """Il tipo di una colonna di CustomComplexTableField, dal widget della sua cella."""
    if "<select" in cell:
        return "MultiCheckBoxField" if "multiple" in cell else "CustomSelectBoxField"
    if "<textarea" in cell:
        return "TextAreaField"
    kind = re.search(r'<input type="([^"]+)"', cell)
    kind = kind.group(1) if kind else "text"
    if kind == "number":
        step = re.search(r'step="([^"]+)"', cell)
        return "PositiveIntegerField" if not step or step.group(1) == "1" else "PositiveFloatField"
    return {"date": "BaseDateField", "file": "CustomFileField", "email": "CustomEmailField",
            "checkbox": "CheckBoxField", "radio": "CustomRadioBoxField", "url": "CustomURLField",
            "hidden": "CustomHiddenField"}.get(kind, "CustomCharField")


def field_type(x):
    t, markup, label_help = x["type"], x["html"], (x["label"] + " " + x["help_text"]).lower()
    if t == "text":
        return "BaseDateField" if 'type="date"' in markup else "CustomCharField"
    if t == "file":
        return "CustomPDFField" if "pdf" in label_help else "CustomFileField"
    if t == "select":
        return "MultiCheckBoxField" if x["options"] or "multiple" in markup else "CustomSelectBoxField"
    if t == "number":
        step = re.search(r'step="([^"]+)"', markup)
        return "PositiveIntegerField" if not step or step.group(1) == "1" else "PositiveFloatField"
    if t == "textarea":
        return "CustomComplexTableField" if "formset-template" in markup else "TextAreaField"
    return {"hidden": "CustomHiddenField", "email": "CustomEmailField", "checkbox": "CheckBoxField",
            "radio": "CustomRadioBoxField", "url": "CustomURLField"}.get(t, "CustomCharField")


def convert_form(form):
    """I campi del modulo, come li scrive il file locale, da una risposta /api/<s>/<c>/ticket/new/."""
    fields = []
    custom = [x for x in form if not x["id"].startswith("ticket_") and x["id"] != "condizioni_field_id"]
    for order, x in enumerate(custom):
        kind = field_type(x)
        if kind == "MultiCheckBoxField":
            values = [o["value"] for o in x["options"]] or option_values(x["html"]) or input_values(x["html"])
        elif kind == "CustomSelectBoxField":
            values = option_values(x["html"])
        elif kind == "CustomRadioBoxField":
            values = input_values(x["html"])
        else:
            values = []
        valore = table_columns(x["id"], x["html"]) if kind == "CustomComplexTableField" else ";".join(values)
        fields.append({"name": x["label"], "field_type": kind, "valore": valore, "is_required": bool(x["required"]),
                       "aiuto": x["help_text"] or "", "pre_text": "", "ordinamento": order})
    return fields


# ---------------------------------------------------------------- caricamento

def load_local():
    objects = json.load(open(LOCAL, encoding="utf-8"))
    by = collections.defaultdict(dict)
    for o in objects:
        by[o["model"]][o["pk"]] = o["fields"]
    return objects, by


def load_api():
    structures = json.load(open(os.path.join(RAW, "structures.json"), encoding="utf-8"))
    categories = json.load(open(os.path.join(RAW, "categories.json"), encoding="utf-8"))
    forms = {}
    for path in glob.glob(os.path.join(RAW, "forms", "*.api.json")):
        s, c = os.path.basename(path)[:-len(".api.json")].split("__", 1)
        forms[(s, c)] = json.load(open(path, encoding="utf-8"))
    return structures, {(c["organizational_structure"], c["slug"]): c for c in categories}, forms


def load_dump():
    by = collections.defaultdict(dict)
    for path in sorted(glob.glob(os.path.join(DUMP, "*.json"))):
        for o in json.load(open(path, encoding="utf-8")):
            by[o["model"]][o["pk"]] = o["fields"]
    return by


class Index:
    """Il file locale come tabelle, con le chiavi per slug e i prossimi ID liberi."""

    def __init__(self, by):
        self.by = by
        self.next_pk = {m: max(rows) + 1 for m, rows in by.items()}

    def new(self, model, fields):
        pk = self.next_pk[model]
        self.next_pk[model] += 1
        self.by[model][pk] = fields
        return pk

    def struct_pk(self, slug):
        return next((pk for pk, f in self.by[STRUCT].items() if f["slug"] == slug), None)

    def office_pk(self, struct_pk, slug):
        return next((pk for pk, f in self.by[OFFICE].items()
                     if f["organizational_structure"] == struct_pk and f["slug"] == slug), None)

    def cat_key(self, pk):
        f = self.by[CAT][pk]
        return self.by[STRUCT][f["organizational_structure"]]["slug"], f["slug"]

    def cat_pk(self, key):
        return next((pk for pk in self.by[CAT] if self.cat_key(pk) == key), None)

    def modules(self, cat_pk, active_only=False):
        return [pk for pk, f in self.by[MOD].items() if f["ticket_category"] == cat_pk and (f["is_active"] or not active_only)]

    def fields(self, mod_pk):
        return sorted((f for f in self.by[FIELD].values() if f["category_module"] == mod_pk), key=lambda f: f["ordinamento"])

    def drop_modules(self, cat_pk):
        for m in self.modules(cat_pk):
            for pk in [pk for pk, f in self.by[FIELD].items() if f["category_module"] == m]:
                del self.by[FIELD][pk]
            del self.by[MOD][m]


def signature(fields):
    return sorted((f["name"], f["field_type"], f["valore"], f["is_required"], f["aiuto"]) for f in fields)


# ---------------------------------------------------------------- validazione del convertitore

def validate():
    _, by = load_local()
    idx = Index(by)
    _, _, forms = load_api()
    exact = total = 0
    by_type = collections.Counter()
    wrong = collections.Counter()
    for key, resp in forms.items():
        pk = idx.cat_pk(key)
        if resp["statusCode"] != 200 or pk is None or not idx.modules(pk):
            continue
        local = {f["name"]: f for m in idx.modules(pk) for f in idx.fields(m)}
        for f in convert_form(resp["jsonBody"]["form"]):
            ref = local.get(f["name"])
            if not ref:
                continue
            total += 1
            same = all(f[k] == ref[k] for k in ("field_type", "valore", "is_required", "aiuto", "ordinamento"))
            exact += same
            by_type[(ref["field_type"], same)] += 1
            if not same:
                wrong[(ref["field_type"], tuple(k for k in ("field_type", "valore", "is_required", "aiuto", "ordinamento") if f[k] != ref[k]))] += 1
    print(f"campi riprodotti esattamente: {exact}/{total} ({exact / total:.1%})")
    for (t, ok), n in sorted(by_type.items()):
        print(f"  {t:<26} {'ok ' if ok else 'NO '} {n}")
    print("differenze:", wrong.most_common(10))


# ---------------------------------------------------------------- aggiornamento

def visible(idx):
    """Quante categorie passano i filtri di category_queryset (attive, visibili, con modulo attivo...)."""
    now = datetime.now(ROME).isoformat()
    n = 0
    for pk, f in idx.by[CAT].items():
        s, o = idx.by[STRUCT][f["organizational_structure"]], idx.by[OFFICE][f["organizational_office"]]
        if (f["is_active"] and not f["is_hidden"] and s["is_active"] and o["is_active"] and idx.modules(pk, True)
                and (not f["date_start"] or f["date_start"] <= now) and (not f["date_end"] or f["date_end"] > now)):
            n += 1
    return n


def build():
    objects, by = load_local()
    idx = Index(by)
    api_structs, api_cats, forms = load_api()
    dump = load_dump()
    log = collections.defaultdict(list)
    before = {m: len(rows) for m, rows in by.items()}
    visible_before = visible(idx)

    def ensure_office(struct_pk, slug, name=None, extra=None):
        pk = idx.office_pk(struct_pk, slug)
        if pk is None:
            fields = {"organizational_structure": struct_pk, "slug": slug, "name": name or slug,
                      "description": "", "is_default": False, "is_private": False, "is_active": True}
            fields.update(extra or {})
            pk = idx.new(OFFICE, fields)
            log["uffici aggiunti"].append(f"{idx.by[STRUCT][struct_pk]['slug']}/{slug}")
        return pk

    def set_module(cat_pk, fields, created, source):
        idx.drop_modules(cat_pk)
        mod = idx.new(MOD, {"ticket_category": cat_pk, "name": "Modulo importato", "created": created, "is_active": True})
        for f in fields:
            idx.new(FIELD, {**f, "category_module": mod})
        log[f"moduli aggiunti ({source})"].append(f"{'/'.join(idx.cat_key(cat_pk))} ({len(fields)} campi)")

    # 1. API (raw_cache, 3/11) -------------------------------------------------------------
    local_keys = {idx.cat_key(pk): pk for pk in idx.by[CAT]}
    gone = {k: pk for k, pk in local_keys.items() if k not in api_cats}
    for key, api in api_cats.items():
        struct_pk = idx.struct_pk(key[0])
        if struct_pk is None:
            log["categorie API saltate: struttura sconosciuta"].append("/".join(key))
            continue
        pk = local_keys.get(key)
        if pk is None:  # rinominata? stessa struttura e stesso `created`
            pk = next((p for k, p in gone.items() if k[0] == key[0] and idx.by[CAT][p]["created"] == api["created"]), None)
            if pk is not None:
                log["categorie rinominate (aggiornate sul posto)"].append(f"{idx.cat_key(pk)[1]} -> {key[1]}")
        office = ensure_office(struct_pk, api["organizational_office"])
        if pk is None:
            pk = idx.new(CAT, {**{k: api.get(k) for k in SYNCED}, "confirm_message_text": "", **FORCED,
                               "organizational_structure": struct_pk, "organizational_office": office, "is_active": False})
            log["categorie aggiunte (API)"].append("/".join(key))
        cat = idx.by[CAT][pk]
        changed = [k for k in SYNCED if k in api and k != "confirm_message_text" and cat.get(k) != api[k]]
        for k in changed:
            cat[k] = api[k]
        if cat["organizational_office"] != office:
            cat["organizational_office"] = office
            changed.append("organizational_office")
        if changed and "categorie aggiunte (API)" not in log or (changed and "/".join(key) not in log["categorie aggiunte (API)"]):
            log["categorie aggiornate (API)"].append(f"{'/'.join(key)}: {', '.join(changed)}")
        resp = forms.get(key)
        if resp and resp["statusCode"] == 200 and not idx.modules(pk, True):
            set_module(pk, convert_form(resp["jsonBody"]["form"]), resp["fetchedAt"], "API")
            for c in resp["jsonBody"].get("conditions") or []:
                idx.new(COND, {**c["fields"], "category": pk})
                log["condizioni aggiunte (API)"].append("/".join(key))
    renamed_from = {e.split(" -> ")[0] for e in log["categorie rinominate (aggiornate sul posto)"]}
    for key, pk in gone.items():
        if key[1] not in renamed_from:
            log["categorie non più nell'API (lasciate come sono)"].append("/".join(key))

    # 2. dump ICT (uniticket-dump, 13/11) ---------------------------------------------------
    ds, do, dc, dm = dump[STRUCT], dump[OFFICE], dump[CAT], dump[MOD]
    for s in ds.values():
        if idx.struct_pk(s["slug"]) is None:
            log["strutture del dump non aggiunte (senza categorie nel dump)"].append(s["slug"])
    for dpk, d in dc.items():
        key = (ds[d["organizational_structure"]]["slug"], d["slug"])
        struct_pk = idx.struct_pk(key[0])
        doff = do[d["organizational_office"]]
        office = ensure_office(struct_pk, doff["slug"], doff["name"],
                               {k: doff[k] for k in ("description", "is_default", "is_private", "is_active")})
        fields = {**{k: rome(d[k]) for k in SYNCED}, **FORCED, "organizational_structure": struct_pk,
                  "organizational_office": office}
        pk = idx.cat_pk(key)
        if pk is not None:  # dumpdata tronca ai millisecondi: stesso istante, si tiene la data locale più precisa
            for k in ("created", "modified", "date_start", "date_end"):
                if same_instant(idx.by[CAT][pk].get(k), fields[k]):
                    fields[k] = idx.by[CAT][pk][k]
        if pk is None:
            pk = idx.new(CAT, {**fields, "is_active": False})
            log["categorie aggiunte (dump ICT)"].append("/".join(key))
        else:
            changed = [k for k, v in fields.items() if idx.by[CAT][pk].get(k) != v]
            idx.by[CAT][pk].update(fields)
            if changed:
                log["categorie aggiornate (dump ICT)"].append(f"{'/'.join(key)}: {', '.join(changed)}")
        active = [m for m, f in dm.items() if f["ticket_category"] == dpk and f["is_active"]]
        if active:
            dfields = sorted((f for f in dump[FIELD].values() if f["category_module"] == active[0]),
                             key=lambda f: f["ordinamento"])
            new_fields = [{k: f[k] for k in ("name", "field_type", "valore", "is_required", "aiuto", "pre_text", "ordinamento")}
                          for f in dfields]
            current = [f for m in idx.modules(pk, True) for f in idx.fields(m)]
            if signature(current) != signature(new_fields):
                set_module(pk, new_fields, rome(dm[active[0]]["created"]), "dump ICT")
        if len(active) > 1:
            log["categorie del dump con più moduli attivi (preso il primo)"].append("/".join(key))

    # 3. attiva = ha un modulo attivo -----------------------------------------------------
    for pk, cat in idx.by[CAT].items():
        should = bool(idx.modules(pk, True))
        if cat["is_active"] != should:
            cat["is_active"] = should
            log["categorie attivate" if should else "categorie disattivate"].append("/".join(idx.cat_key(pk)))

    check(idx)
    write(objects, idx)
    report(log, before, idx, visible_before, visible(idx))


def check(idx):
    by = idx.by
    errors = []
    for pk, f in by[CAT].items():
        if f["organizational_structure"] not in by[STRUCT]: errors.append(f"categoria {pk}: struttura mancante")
        o = by[OFFICE].get(f["organizational_office"])
        if o is None: errors.append(f"categoria {pk}: ufficio mancante")
        elif o["organizational_structure"] != f["organizational_structure"]: errors.append(f"categoria {pk}: ufficio di un'altra struttura")
    errors += [f"modulo {pk}: categoria mancante" for pk, f in by[MOD].items() if f["ticket_category"] not in by[CAT]]
    errors += [f"campo {pk}: modulo mancante" for pk, f in by[FIELD].items() if f["category_module"] not in by[MOD]]
    errors += [f"condizione {pk}: categoria mancante" for pk, f in by[COND].items() if f["category"] not in by[CAT]]
    errors += [f"ufficio {pk}: struttura mancante" for pk, f in by[OFFICE].items() if f["organizational_structure"] not in by[STRUCT]]
    keys = collections.Counter((f["organizational_structure"], f["slug"]) for f in by[CAT].values())
    errors += [f"slug categoria duplicato: {k}" for k, n in keys.items() if n > 1]
    for model, rows in by.items():
        shapes = collections.Counter(tuple(sorted(f)) for f in rows.values())
        if len(shapes) > 1: errors.append(f"{model}: oggetti con campi diversi {list(shapes.values())}")
    if errors:
        sys.exit("ERRORI DI INTEGRITÀ:\n" + "\n".join(errors[:50]))


def write(objects, idx):
    """Stesso ordine e stessa formattazione del file originale; i nuovi oggetti in coda al loro modello."""
    order = list(dict.fromkeys(o["model"] for o in objects))
    out = []
    for model in order:
        original = [o["pk"] for o in objects if o["model"] == model]
        for pk in original + sorted(set(idx.by[model]) - set(original)):
            if pk in idx.by[model]:
                out.append({"model": model, "pk": pk, "fields": idx.by[model][pk]})
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(out, indent=2, ensure_ascii=False) + "\n")


def report(log, before, idx, visible_before, visible_after):
    lines = ["# local_conf_aggiornato.json: cosa è cambiato", "",
             "Generato da `build_fixture.py` partendo da `local_conf.json`, dalle risposte dell'API "
             "e dal dump ICT. Controlli di integrità superati.", "",
             "| tabella | prima | dopo |", "|---|---|---|"]
    for model in before:
        lines.append(f"| `{model}` | {before[model]} | {len(idx.by[model])} |")
    lines += ["", f"Categorie che l'assistente può vedere (filtri di `category_queryset`, prima dei permessi "
                  f"dell'utente): **{visible_before} → {visible_after}**.", ""]
    for title, items in log.items():
        lines.append(f"## {title} ({len(items)})")
        lines += [f"- {i}" for i in sorted(items)] + [""]
    if REPORT:
        with open(REPORT, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
    print("\n".join(lines[:12 + len(before)]))
    for title, items in log.items():
        print(f"  {title}: {len(items)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw-cache", required=True, help="cartella con le risposte dell'API")
    parser.add_argument("--dump", help="cartella con il dump ICT (obbligatoria senza --validate)")
    parser.add_argument("--out", default=LOCAL, help="file da scrivere (default: local_conf.json)")
    parser.add_argument("--report", help="file Markdown con l'elenco delle modifiche")
    parser.add_argument("--validate", action="store_true", help="misura solo il convertitore dei form")
    args = parser.parse_args()
    if not args.validate and not args.dump:
        parser.error("--dump è obbligatorio senza --validate")
    RAW, DUMP, OUT, REPORT = args.raw_cache, args.dump, args.out, args.report
    validate() if args.validate else build()
