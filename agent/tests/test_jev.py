from app.jev import build_questions
from helpers import make_category

LAUREA = make_category(1, "Certificato di laurea", description="Richiesta del certificato", structure_name="DiBEST")
TASSE = make_category(2, "Pagamento tasse")


def test_every_candidate_is_an_option_of_the_choice():
    questions = build_questions([LAUREA, TASSE])

    assert questions["modulo"]["type"] == "choice"
    assert questions["modulo"]["criteria"] == {
        "M1": {"titolo": "Certificato di laurea", "descrizione": "Richiesta del certificato", "struttura": "DiBEST"},
        "M2": {"titolo": "Pagamento tasse"},
    }


def test_every_candidate_has_its_own_fit_question_without_the_structure():
    questions = build_questions([LAUREA, TASSE])

    assert questions["adatto_M1"]["type"] == "noul"
    assert questions["adatto_M1"]["instructions"]["modulo"] == {
        "titolo": "Certificato di laurea", "descrizione": "Richiesta del certificato"}
    assert questions["adatto_M2"]["instructions"]["modulo"] == {"titolo": "Pagamento tasse"}


def test_without_candidates_only_the_vague_question_is_asked():
    assert list(build_questions([])) == ["vago"]


def test_long_descriptions_are_cut():
    category = make_category(1, description="x" * 1000)

    assert len(build_questions([category])["modulo"]["criteria"]["M1"]["descrizione"]) == 240
