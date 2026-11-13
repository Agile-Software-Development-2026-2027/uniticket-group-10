import json

import httpx2
import pytest
from pytest import approx
from typesafe_sdk import TypeSafeAPIResponseValidationError

from app.decision import DecisionModel
from app.jev import NO_API_KEY, JevModel, build_questions, parse_answers, ramp
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


# Una risposta come la manda Jev, sia TypeSafe sia `autotrust-jev`: l'SDK rifiuta quelle incomplete.
JEV_RESPONSE = {
    "model": "autotrust-jev:35b",
    "usage": {"input_tokens": 431, "output_tokens": 0},
    "answers": {
        "vago": {"type": "noul", "noul": 0.1},
        "modulo": {"type": "choice", "choice": "M1", "confidence": 1.0, "probabilities": {"M1": 1.0}},
        "adatto_M1": {"type": "noul", "noul": 0.9},
    },
}


def fake_jev(requests, api_key="", response=JEV_RESPONSE):
    """Un JevModel che non usa la rete: annota le richieste e risponde sempre che M1 è la categoria giusta."""
    def server(request):
        requests.append(request)
        return httpx2.Response(200, json=response)

    return JevModel("http://jev", "autotrust-jev:35b", max_candidates=16, api_key=api_key,
                    transport=httpx2.MockTransport(server))


def test_jev_receives_the_request_and_the_questions_and_its_answers_become_an_estimate():
    requests = []

    estimate = fake_jev(requests).estimate("mi serve il certificato di laurea", [LAUREA])

    assert str(requests[0].url) == "http://jev/v1/systemone"
    assert json.loads(requests[0].content) == {
        "model": "autotrust-jev:35b",
        "state": "Utente: mi serve il certificato di laurea\n",
        "questions": build_questions([LAUREA]),
    }
    assert estimate.categories == [(LAUREA, approx(1))]


def test_the_api_key_is_sent_and_without_one_a_placeholder_goes_to_ollama():
    without_key, with_key = [], []

    fake_jev(without_key).estimate("laurea", [LAUREA])
    fake_jev(with_key, api_key="chiave").estimate("laurea", [LAUREA])

    assert without_key[0].headers["authorization"] == f"Bearer {NO_API_KEY}"
    assert with_key[0].headers["authorization"] == "Bearer chiave"


def test_an_incomplete_response_of_jev_is_an_error():
    incomplete = {"answers": answers(0.1, {"M1": 1.0}, [0.9])}

    with pytest.raises(TypeSafeAPIResponseValidationError):
        fake_jev([], response=incomplete).estimate("laurea", [LAUREA])


def test_jev_is_a_decision_model():
    assert isinstance(fake_jev([]), DecisionModel)
