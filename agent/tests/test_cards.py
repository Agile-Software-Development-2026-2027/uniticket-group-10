from app.decision.cards import MAX_FIELD_LABELS, card, summary
from helpers import make_category

ESONERO = make_category(
    1, "Richiesta esonero IV rata per nucleo familiare", structure_name="Servizi Didattici",
    description="**Esonero** della IV rata per chi ha [familiari iscritti](https://www.unical.it).",
    audience={"students": True, "staff": False, "guests": True, "anonymous": False},
    field_labels=["Altri componenti del nucleo familiare attualmente iscritti"])


def test_the_card_says_who_the_category_is_for_and_the_fields_that_distinguish_it():
    assert card(ESONERO) == {
        "titolo": "Richiesta esonero IV rata per nucleo familiare",
        "per": "studenti, esterni",
        "descrizione": "Esonero della IV rata per chi ha familiari iscritti.",
        "campi": ["Altri componenti del nucleo familiare attualmente iscritti"],
    }


def test_with_the_structure_a_department_has_its_full_name_and_its_courses():
    category = make_category(2, "Certificato di laurea", structure_name="CTC")

    located = card(category, with_structure=True)

    assert located["struttura"] == "Dipartimento di Chimica e Tecnologie Chimiche (CTC)"
    assert located["corsi"] == ["Chimica"]


def test_with_the_structure_an_office_keeps_its_name_and_has_no_courses():
    located = card(ESONERO, with_structure=True)

    assert located["struttura"] == "Servizi Didattici"
    assert "corsi" not in located


def test_a_category_without_audience_or_fields_has_only_title_and_description():
    assert card(make_category(3, "Pagamento tasse", description="Tasse")) == {
        "titolo": "Pagamento tasse", "descrizione": "Tasse"}


def test_only_the_first_fields_are_kept():
    category = make_category(4, field_labels=[f"Campo {index}" for index in range(10)])

    assert card(category)["campi"] == [f"Campo {index}" for index in range(MAX_FIELD_LABELS)]


def test_long_descriptions_are_cut():
    description = card(make_category(5, description="x" * 1000))["descrizione"]

    assert description == "x" * 240 + "…"


def test_a_description_that_says_nothing_about_the_service_is_left_out():
    assert summary("Descrivi qui la tua richiesta", "Richiesta generica") == ""
    assert summary("Richiesta generica", "Richiesta generica") == ""
    assert summary("ATTENZIONE: prenderemo in carico la richiesta entro due giorni lavorativi successivi "
                   "alla presentazione.", "Helpdesk") == ""
