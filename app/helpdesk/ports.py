from collections.abc import Iterator
from typing import Protocol


class CompletionGateway(Protocol):
    """Abstração que as features dependem para pedir uma capacidade de IA.

    Nenhuma feature conhece o provider, o modelo físico ou o formato da API
    por trás da capacidade — só o nome lógico (ver app/helpdesk/config.py).
    """

    def complete(self, capability: str, task: str, content: str) -> str:
        ...

    def stream(self, capability: str, task: str, content: str) -> Iterator[str]:
        ...
