from . import config
from .ports import CompletionGateway
from .schemas import ReplySuggestion, TicketInput


def suggest(ticket: TicketInput, gateway: CompletionGateway) -> ReplySuggestion:
    text = gateway.complete(config.SUGGESTION_CAPABILITY, "suggest", ticket.text)
    return ReplySuggestion(ticket_id=ticket.ticket_id, suggestion=text)
