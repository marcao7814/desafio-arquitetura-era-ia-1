from collections.abc import Iterator

from . import config
from .ports import CompletionGateway
from .schemas import TicketInput


def suggest_stream(ticket: TicketInput, gateway: CompletionGateway) -> Iterator[str]:
    yield from gateway.stream(config.SUGGESTION_CAPABILITY, "suggest", ticket.text)
