"""I dipartimenti: quali strutture lo sono e come riconoscerli nelle parole dell'utente.

Più della metà delle categorie è di un solo dipartimento: a chi chiede "un certificato di laurea" senza
dire dove studia non si può dare per buona quella del DiBEST. Non sono riservate a chi ne fa parte (un
docente di un altro ateneo accetta l'incarico al DiBEST con il modulo del DiBEST): all'utente si chiede se
è quello il dipartimento che gli serve, non se ne fa parte.
`departments.json` è curato a mano: per ogni dipartimento, con il nome che ha in uniTicket ("DiBEST"),
il nome esteso, le sigle e i corsi di studio, per capire che "faccio giurisprudenza" vuol dire DiScAG.
"""

import json
import re
import unicodedata
from pathlib import Path

from .rules import Decision

DATA_FILE = Path(__file__).with_name("departments.json")
# Quanti corsi si citano come esempio quando si chiede all'utente se gli serve un dipartimento.
COURSE_EXAMPLES = 3

_NOT_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")
_PARENTHESIS = re.compile(r"\([^)]*\)")
# Dove finisce la prima parte di un corso come "Ingegneria per l'Ambiente e il Territorio".
_FIRST_PART_END = re.compile(r",|\s+e\s+", re.IGNORECASE)
_DEPARTMENT_PREFIX = re.compile(r"^Dipartimento di\s+", re.IGNORECASE)


def normalize(text: str) -> str:
    """Minuscole, senza accenti, punteggiatura ridotta a spazi: "dell'Antichità" = "dell antichita"."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _NOT_ALPHANUMERIC.sub(" ", without_marks).strip()


def phrases(name: str, entry: dict) -> list[str]:
    """Le espressioni che indicano un dipartimento: nome, sigle, nome esteso e corsi di studio."""
    names = [name, *entry.get("aliases", []), entry["full_name"], _DEPARTMENT_PREFIX.sub("", entry["full_name"])]
    for course in entry.get("courses", []):
        course = _PARENTHESIS.sub(" ", course)
        names.append(course)
        # "Ingegneria per l'Ambiente" basta, se sono almeno due parole: una sola non identifica nessuno.
        first_part = normalize(_FIRST_PART_END.split(course, maxsplit=1)[0])
        if len(first_part.split(" ")) >= 2:
            names.append(first_part)
    return list(dict.fromkeys(phrase for phrase in map(normalize, names) if phrase))


class Departments:
    """I dipartimenti per nome di struttura, senza distinguere maiuscole e minuscole."""

    def __init__(self, entries: dict[str, dict]):
        self._entries = {name.lower(): entry for name, entry in entries.items()}
        self._phrases = {name.lower(): phrases(name, entry) for name, entry in entries.items()}

    @classmethod
    def load(cls, file: Path = DATA_FILE) -> "Departments":
        return cls(json.loads(file.read_text(encoding="utf-8")))

    def is_department(self, structure_name: str) -> bool:
        return structure_name.lower() in self._entries

    def named_in(self, text: str) -> set[str]:
        """I dipartimenti nominati nel testo, per nome, sigla o corso di studi (in minuscolo).

        Confronta espressioni intere: "scienze" da sola non identifica nessuno e "fisicamente" non è
        "Fisica". Se un'espressione manca si fa una domanda in più, che è l'errore meno grave.
        """
        normalized = f" {normalize(text)} "
        return {name for name, known in self._phrases.items() if any(f" {phrase} " in normalized for phrase in known)}

    def label(self, structure_name: str) -> str:
        """Il nome esteso con la sigla, se è un dipartimento ("Dipartimento di Chimica... (CTC)"); se no il nome."""
        entry = self._entries.get(structure_name.lower())
        return f"{entry['full_name']} ({structure_name})" if entry else structure_name

    def courses(self, structure_name: str) -> list[str]:
        """I corsi di studio del dipartimento; nessuno se la struttura non è un dipartimento."""
        return list(self._entries.get(structure_name.lower(), {}).get("courses", []))

    def describe(self, structure_name: str) -> dict:
        """Come presentare il dipartimento all'utente: il nome esteso con la sigla e alcuni corsi."""
        return {"department": self.label(structure_name), "courses": self.courses(structure_name)[:COURSE_EXAMPLES]}


departments = Departments.load()


def confirm_department(decision: Decision, said: str, asked: set[int] = frozenset()) -> Decision:
    """Una sola categoria di un dipartimento non è una certezza finché l'utente non nomina quel dipartimento.

    `said` sono le parole dell'utente, non la query scritta dall'assistente, che potrebbe averlo dedotto.
    `asked` sono le categorie per cui la conferma è già stata chiesta: non si chiede due volte.
    """
    if decision.action != "PROPOSE" or len(decision.categories) != 1:
        return decision
    category = decision.categories[0]
    structure = category.structure_name
    if not departments.is_department(structure) or category.id in asked:
        return decision
    if structure.lower() in departments.named_in(said):
        return decision
    return Decision("CONFIRM", decision.categories)


def belongs_elsewhere(structure_name: str, said: str) -> bool:
    """L'utente ha nominato un dipartimento o un corso di studi, e non è quello di questa struttura."""
    named = departments.named_in(said)
    return bool(named) and structure_name.lower() not in named
