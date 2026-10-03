import os

# A aplicação só conhece a URL/chave do gateway e nomes lógicos de capacidade.
# Nenhum nome de modelo físico nem chave de provider aparece aqui.
GATEWAY_BASE_URL = os.environ["GATEWAY_BASE_URL"]
GATEWAY_API_KEY = os.environ["GATEWAY_API_KEY"]

CLASSIFICATION_CAPABILITY = "helpdesk-classify"
EXTRACTION_CAPABILITY = "helpdesk-extract"
SUGGESTION_CAPABILITY = "helpdesk-suggest"
REPORT_CAPABILITY = "helpdesk-topics"

MAX_OUTPUT_TOKENS = 2000

TICKETS_FILE = "/data/tickets.jsonl"
TICKETS_PER_CALL = 150
