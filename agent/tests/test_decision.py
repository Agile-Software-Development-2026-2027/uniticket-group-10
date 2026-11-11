from app.decision import NEEDS_INFO, NO_MATCH, Estimate, likely_hypotheses
from helpers import make_category

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
