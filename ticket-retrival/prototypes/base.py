"""Shared retrieval interface."""

from abc import ABC, abstractmethod

from .models import Ticket


class Prototype(ABC):
    """Common contract for evaluating retrieval prototypes."""

    def __init__(self, tickets: list[Ticket]):
        self.tickets = tickets

    @abstractmethod
    def search(self, query: str, k: int = 5) -> list[tuple[int, float]]:
        pass
