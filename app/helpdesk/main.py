from fastapi import FastAPI

from . import classification, config, extraction, report, suggestion
from .adapters.gateway import LiteLLMGateway
from .schemas import (Classification, OrderData, PeriodInput, ReplySuggestion, TicketInput,
                      TopicsReport)

app = FastAPI(title="Helpdesk")

# Composition root: só aqui o adapter concreto do gateway é construído e
# injetado nas features. Nenhuma feature importa adapters.gateway diretamente.
gateway = LiteLLMGateway(
    base_url=config.GATEWAY_BASE_URL,
    api_key=config.GATEWAY_API_KEY,
    max_tokens=config.MAX_OUTPUT_TOKENS,
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/tickets/classification")
def classify_ticket(ticket: TicketInput) -> Classification:
    return classification.classify(ticket, gateway)


@app.post("/tickets/reply-suggestion")
def suggest_reply(ticket: TicketInput) -> ReplySuggestion:
    return suggestion.suggest(ticket, gateway)


@app.post("/tickets/extraction")
def extract_order_data(ticket: TicketInput) -> OrderData:
    return extraction.extract(ticket, gateway)


@app.post("/reports/topics")
def topics_report(period: PeriodInput) -> TopicsReport:
    return report.topics(period, gateway)
