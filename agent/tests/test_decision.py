import logging

import pytest

from app.decision.rules import (Decision, DecisionModel, Estimate, Hypothesis, decide, decide_with, likely_hypotheses,
                                stop_asking)
from helpers import FirstCandidateModel, ids, make_category

ESSE3 = make_category(1, "Assistenza Esse3")
LAUREA = make_category(2, "Certificato di laurea")
TASSE = make_category(3, "Pagamento tasse")


def test_a_confident_category_is_the_only_likely_hypothesis():
    estimate = Estimate(categories=[(ESSE3, 0.95)], no_match=0.05)

    assert likely_hypotheses(estimate) == [ESSE3]


def test_hypotheses_are_added_until_their_shares_reach_the_confidence():
    # 34% alla prima e il resto sparso: nessuna ipotesi da sola arriva all'80%.
    estimate = Estimate(categories=[(ESSE3, 0.34), (LAUREA, 0.11), (TASSE, 0.11)], no_match=0.22, needs_info=0.22)

    assert likely_hypotheses(estimate) == [ESSE3, Hypothesis.NO_MATCH, Hypothesis.NEEDS_INFO, LAUREA]


def test_shares_that_add_up_to_the_confidence_reach_it_despite_rounding():
    # 0,7 + 0,1 in float fa 0,7999999999999999: conta comunque come 80%.
    estimate = Estimate(categories=[(ESSE3, 0.7), (LAUREA, 0.1)], no_match=0.1, needs_info=0.1)

    assert likely_hypotheses(estimate) == [ESSE3, LAUREA]


def test_shares_just_below_the_confidence_do_not_reach_it():
    estimate = Estimate(categories=[(ESSE3, 0.79)], no_match=0.21)

    assert likely_hypotheses(estimate) == [ESSE3, Hypothesis.NO_MATCH]


def test_hypotheses_are_ordered_by_share_not_by_arrival():
    estimate = Estimate(categories=[(LAUREA, 0.05), (ESSE3, 0.9)], no_match=0.05)

    assert likely_hypotheses(estimate) == [ESSE3]


def test_hypotheses_without_share_are_never_likely():
    estimate = Estimate(categories=[(ESSE3, 0.0)], no_match=0.7, needs_info=0.0)

    assert likely_hypotheses(estimate) == [Hypothesis.NO_MATCH]


def test_an_empty_estimate_has_no_likely_hypothesis():
    assert likely_hypotheses(Estimate()) == []


def test_a_confident_category_is_proposed():
    decision = decide(Estimate(categories=[(ESSE3, 0.95)], no_match=0.05))

    assert decision == Decision("PROPOSE", [ESSE3])


def test_categories_that_reach_the_confidence_together_are_proposed_from_the_most_probable():
    decision = decide(Estimate(categories=[(LAUREA, 0.4), (ESSE3, 0.5)], no_match=0.1))

    assert decision == Decision("PROPOSE", [ESSE3, LAUREA])


def test_only_no_match_means_no_match():
    decision = decide(Estimate(categories=[(ESSE3, 0.0)], no_match=0.9, needs_info=0.1))

    assert decision == Decision("NO_MATCH")


def test_a_doubt_between_a_category_and_no_match_is_asked():
    decision = decide(Estimate(categories=[(ESSE3, 0.5)], no_match=0.5))

    assert decision == Decision("ASK", [ESSE3])


def test_a_vague_request_is_asked_without_categories():
    assert decide(Estimate(needs_info=1.0)) == Decision("ASK")


def test_an_empty_estimate_is_asked_and_not_proposed():
    assert decide(Estimate()) == Decision("ASK")


def test_too_many_likely_categories_are_asked_with_the_first_five():
    twelve = [(make_category(category_id), 1 / 12) for category_id in range(1, 13)]

    decision = decide(Estimate(categories=twelve))

    assert decision.action == "ASK"
    assert ids(decision.categories) == [1, 2, 3, 4, 5]


def test_a_decision_model_must_implement_estimate():
    class Incomplete(DecisionModel):
        max_candidates = 16

    with pytest.raises(TypeError):
        Incomplete()


def test_a_model_receives_only_the_highest_ranked_candidates_it_accepts():
    model = FirstCandidateModel(max_candidates=2)

    decision = decide_with(model, "laurea", [ESSE3, LAUREA, TASSE])

    assert model.received == [ESSE3, LAUREA]
    assert decision == Decision("PROPOSE", [ESSE3])


def test_a_model_receives_all_the_candidates_when_they_are_within_its_maximum():
    model = FirstCandidateModel(max_candidates=16)

    decide_with(model, "laurea", [ESSE3, LAUREA, TASSE])

    assert model.received == [ESSE3, LAUREA, TASSE]


class BrokenModel(DecisionModel):
    """Modello finto che non riesce mai a stimare, come Jev quando non risponde."""

    max_candidates = 16

    def estimate(self, query, candidates):
        raise ConnectionError("offline")


def test_a_model_that_fails_makes_the_agent_ask_about_the_first_five_candidates():
    seven = [make_category(category_id) for category_id in range(1, 8)]

    decision = decide_with(BrokenModel(), "laurea", seven)

    assert decision.action == "ASK"
    assert ids(decision.categories) == [1, 2, 3, 4, 5]


def test_a_model_that_fails_is_logged(caplog):
    with caplog.at_level(logging.ERROR, logger="app.decision.rules"):
        decide_with(BrokenModel(), "laurea", [ESSE3])

    assert "non ha dato una stima" in caplog.text
    assert "offline" in caplog.text


def test_a_question_says_if_no_match_is_the_most_probable_hypothesis():
    assert decide(Estimate(categories=[(ESSE3, 0.3)], no_match=0.7)).no_match_likely
    assert not decide(Estimate(categories=[(ESSE3, 0.6)], no_match=0.4)).no_match_likely


def test_after_a_question_a_still_unlikely_match_becomes_no_match():
    unlikely = decide(Estimate(categories=[(ESSE3, 0.3)], no_match=0.7))
    doubt = decide(Estimate(categories=[(ESSE3, 0.45), (LAUREA, 0.35)], no_match=0.2, needs_info=0.0))

    assert stop_asking(unlikely, asked=0) == unlikely
    assert stop_asking(unlikely, asked=1) == Decision("NO_MATCH")
    # Un dubbio tra categorie si può chiedere ancora: la categoria giusta può essere tra quelle.
    assert stop_asking(doubt, asked=3) == doubt
