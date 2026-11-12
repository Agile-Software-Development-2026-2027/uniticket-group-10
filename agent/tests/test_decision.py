import pytest

from app.decision import (NEEDS_INFO, NO_MATCH, Decision, DecisionModel, Estimate, decide, decide_with,
                          likely_hypotheses)
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

    assert likely_hypotheses(estimate) == [ESSE3, NO_MATCH, NEEDS_INFO, LAUREA]


def test_hypotheses_are_ordered_by_share_not_by_arrival():
    estimate = Estimate(categories=[(LAUREA, 0.05), (ESSE3, 0.9)], no_match=0.05)

    assert likely_hypotheses(estimate) == [ESSE3]


def test_hypotheses_without_share_are_never_likely():
    estimate = Estimate(categories=[(ESSE3, 0.0)], no_match=0.7, needs_info=0.0)

    assert likely_hypotheses(estimate) == [NO_MATCH]


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
