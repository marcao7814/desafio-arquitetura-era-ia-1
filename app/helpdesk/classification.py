import json

from fastapi import HTTPException

from . import config
from .ports import CompletionGateway
from .schemas import Classification, TicketInput

CATEGORIES = {"delivery", "payment", "exchange_return", "product_defect", "other"}
PRIORITIES = {"low", "medium", "high"}


def classify(ticket: TicketInput, gateway: CompletionGateway) -> Classification:
    text = gateway.complete(config.CLASSIFICATION_CAPABILITY, "classify", ticket.text)
    data = json.loads(text)
    if data.get("category") not in CATEGORIES or data.get("priority") not in PRIORITIES:
        raise HTTPException(status_code=502, detail="Classificação fora dos valores permitidos")
    return Classification(ticket_id=ticket.ticket_id, **data)
