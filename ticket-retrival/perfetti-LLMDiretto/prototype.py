"""Scaffold only: no provider, prompt or model chosen yet."""
from retrival.base import Prototype


class PerfettiLLMDiretto(Prototype):
    def __init__(self, tickets):
        super().__init__(tickets)
        raise NotImplementedError(
            "perfetti-LLMDiretto: scaffold pronto; modello e prompt da scegliere nel prossimo step."
        )

    def search(self, query: str, k: int = 5) -> list[tuple[int, float]]:
        raise NotImplementedError("Classificazione LLM diretta non ancora implementata.")
