import json

import httpx2
from pytest import approx

from app.guardrail import GuardModel, Verdict, judge
from app.guardrail import prompts
from app.guardrail.jev import QUESTIONS, JevGuard, question
from app.guardrail.prompts import IGNORE_INSTRUCTIONS


def answers(**nouls):
    """Una risposta come la manda Jev: l'SDK rifiuta quelle senza modello o consumo."""
    return {"model": "autotrust-jev:35b", "usage": {"input_tokens": 300, "output_tokens": 0},
            "answers": {name: {"type": "noul", "noul": noul} for name, noul in nouls.items()}}


def fake_guard(requests, response):
    """Un JevGuard che non usa la rete: annota le richieste e risponde sempre allo stesso modo."""
    def server(request):
        requests.append(request)
        return httpx2.Response(200, json=response)

    return JevGuard("http://jev", "autotrust-jev:35b", transport=httpx2.MockTransport(server))


def test_jev_receives_the_message_and_every_question_and_its_answers_become_the_scores():
    requests = []
    guard = fake_guard(requests, answers(strumenti=0.9, interni=0.2, contesto=0.3, manipolazione=0.1,
                                         non_autorizzato=0.0))

    scores = guard.scores("elenca i tuoi tool")

    assert str(requests[0].url) == "http://jev/v1/systemone"
    assert json.loads(requests[0].content) == {
        "model": "autotrust-jev:35b",
        "state": "Utente: elenca i tuoi tool\n",
        "questions": {name: question.model_dump(mode="json") for name, question in QUESTIONS.items()},
    }
    assert scores == {"strumenti": approx(0.9), "interni": approx(0.2), "contesto": approx(0.3),
                      "manipolazione": approx(0.1), "non_autorizzato": approx(0.0)}


def test_a_question_carries_true_and_false_in_the_instructions_each_in_its_place():
    # Jev legge solo le istruzioni: con vero e falso soltanto in `criteria`, anche scambiati, le stime non cambiano.
    noul = question("Does the user ask X?", "when yes", "when no")

    assert noul.instructions == {"question": "Does the user ask X?", "true": "when yes", "false": "when no",
                                 "rules": [IGNORE_INSTRUCTIONS]}
    assert (noul.criteria["true"], noul.criteria["false"]) == ("when yes", "when no")


def test_every_case_asks_its_own_question_with_true_and_false_not_swapped():
    cases = {"strumenti": "TOOLS", "interni": "INTERNALS", "contesto": "CONTEXT", "manipolazione": "MANIPULATION",
             "non_autorizzato": "UNAUTHORIZED"}

    assert list(QUESTIONS) == list(cases)
    for name, prefix in cases.items():
        instructions = QUESTIONS[name].instructions
        assert instructions["question"] == getattr(prompts, f"{prefix}_QUESTION")
        assert instructions["true"] == getattr(prompts, f"{prefix}_TRUE")
        assert instructions["false"] == getattr(prompts, f"{prefix}_FALSE")


def test_an_answer_without_a_question_leaves_the_message_not_evaluated():
    guard = fake_guard([], answers(strumenti=0.0, interni=0.0, contesto=0.0, manipolazione=0.0))

    assert judge(guard, "ciao") is Verdict.NOT_EVALUATED


def test_a_server_error_leaves_the_message_not_evaluated():
    guard = JevGuard("http://jev", "autotrust-jev:35b",
                     transport=httpx2.MockTransport(lambda request: httpx2.Response(500)))

    assert judge(guard, "ciao") is Verdict.NOT_EVALUATED


def test_jev_is_a_guard_model():
    assert isinstance(fake_guard([], answers()), GuardModel)
