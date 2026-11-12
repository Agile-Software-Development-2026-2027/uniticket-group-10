import pytest
from pytest import approx

from app.jev import build_questions, parse_answers, ramp
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


def answers(vague, probabilities, fits):
    """Le risposte di Jev come arrivano: `fits` è l'"adatto" di M1, M2..."""
    replies = {"vago": {"noul": vague}, "modulo": {"probabilities": probabilities}}
    for index, fit in enumerate(fits):
        replies[f"adatto_M{index + 1}"] = {"noul": fit}
    return replies


def test_the_share_of_the_categories_is_split_as_the_choice_says():
    # vago 0,3 vale 0 e adatto 0,7 vale 1: tutta la quota va alle categorie.
    estimate = parse_answers(answers(0.3, {"M1": 0.5, "M2": 0.5}, [0.7, 0.5]), [LAUREA, TASSE])

    assert estimate.categories == [(LAUREA, approx(0.5)), (TASSE, approx(0.5))]
    assert estimate.no_match == approx(0)
    assert estimate.needs_info == approx(0)


def test_categories_are_ordered_from_the_most_probable():
    estimate = parse_answers(answers(0.1, {"M1": 0.2, "M2": 0.8}, [0.9, 0.9]), [LAUREA, TASSE])

    assert estimate.categories == [(TASSE, approx(0.8)), (LAUREA, approx(0.2))]


def test_categories_that_do_not_fit_mean_no_match():
    estimate = parse_answers(answers(0.1, {"M1": 0.9, "M2": 0.1}, [0.05, 0.1]), [LAUREA, TASSE])

    assert estimate.no_match == approx(1)


def test_a_lukewarm_fit_leaves_a_share_to_the_categories():
    estimate = parse_answers(answers(0.1, {"M1": 1.0}, [0.25, 0.1]), [LAUREA, TASSE])

    assert estimate.categories == [(LAUREA, approx(0.25))]
    assert estimate.no_match == approx(0.75)


def test_a_vague_request_needs_information():
    estimate = parse_answers(answers(0.9, {"M1": 1.0}, [0.9]), [LAUREA])

    assert estimate.needs_info == approx(1)
    assert estimate.categories == [(LAUREA, approx(0))]


def test_without_candidates_the_request_is_vague_or_has_no_match():
    estimate = parse_answers(answers(0.5, {}, []), [])

    assert (estimate.categories, estimate.no_match, estimate.needs_info) == ([], approx(0.5), approx(0.5))


def test_a_choice_without_probabilities_is_an_error():
    with pytest.raises(ValueError):
        parse_answers(answers(0.1, {}, [0.9]), [LAUREA])


def test_a_yes_or_no_of_jev_is_read_between_the_two_thresholds():
    assert ramp(0.2, no=0.3) == approx(0)
    assert ramp(0.5, no=0.3) == approx(0.5)
    assert ramp(0.9, no=0.3) == approx(1)
