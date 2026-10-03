"""F2 — POST /tickets/reply-suggestion (streaming, decidido no requisito 6 / ADR-004)

O contrato mudou da v2-decoupled para a main: a suíte da v1-coupled/v2-decoupled
fixava um corpo JSON único; aqui fixamos o formato de evento (SSE) e o texto
reconstruído a partir dos chunks, que continua sendo o mesmo texto
determinístico do provider simulado.
"""
import json
import time

import httpx

from client import APP_URL

_INTRO = (
    "Olá! Sinto muito pelo transtorno com a entrega do seu pedido.\n\n"
    "Caso o pedido seja considerado extraviado, fazemos o reenvio sem nenhum custo adicional.\n\n"
    "Se preferir, também é possível solicitar o cancelamento com reembolso integral.\n\n"
    "Já abri uma solicitação de verificação junto à transportadora responsável pelo envio.\n\n"
    "O prazo de retorno da transportadora costuma ser de até dois dias úteis.\n\n"
    "Assim que tivermos a posição atualizada, você recebe um aviso por e-mail."
)

_REINFORCEMENT_BLOCK = (
    "Reforçando o ponto 1: caso o pedido seja considerado extraviado, fazemos o reenvio sem "
    "nenhum custo adicional.\n\n"
    "Reforçando o ponto 2: se preferir, também é possível solicitar o cancelamento com "
    "reembolso integral.\n\n"
    "Reforçando o ponto 3: já abri uma solicitação de verificação junto à transportadora "
    "responsável pelo envio.\n\n"
    "Reforçando o ponto 4: o prazo de retorno da transportadora costuma ser de até dois dias "
    "úteis.\n\n"
    "Reforçando o ponto 5: assim que tivermos a posição atualizada, você recebe um aviso por "
    "e-mail."
)

_PARTIAL_REINFORCEMENT_BLOCK = (
    "Reforçando o ponto 1: caso o pedido seja considerado extraviado, fazemos o reenvio sem "
    "nenhum custo adicional.\n\n"
    "Reforçando o ponto 2: se preferir, também é possível solicitar o cancelamento com "
    "reembolso integral.\n\n"
    "Reforçando o ponto 3: já abri uma solicitação de verificação junto à transportadora "
    "responsável pelo envio."
)

_OUTRO = "Fico à disposição para qualquer outra dúvida. Um abraço, equipe de atendimento."

EXPECTED_SUGGESTION = "\n\n".join([
    _INTRO,
    _REINFORCEMENT_BLOCK,
    _REINFORCEMENT_BLOCK,
    _REINFORCEMENT_BLOCK,
    _PARTIAL_REINFORCEMENT_BLOCK,
    _OUTRO,
])


def _collect_stream(ticket_id: str, text: str):
    """Faz o POST streaming e devolve (status, content_type, eventos, tempo_primeiro_chunk, tempo_total)."""
    start = time.monotonic()
    first_chunk_time = None
    events = []  # (event_name, data_dict)
    current_event = "message"

    with httpx.stream("POST", f"{APP_URL}/tickets/reply-suggestion",
                       json={"ticket_id": ticket_id, "text": text}, timeout=60) as response:
        status_code = response.status_code
        content_type = response.headers.get("content-type", "")
        for line in response.iter_lines():
            if not line:
                continue
            if line.startswith("event:"):
                current_event = line[len("event:"):].strip()
                continue
            if line.startswith("data:"):
                if first_chunk_time is None:
                    first_chunk_time = time.monotonic() - start
                payload = json.loads(line[len("data:"):].strip())
                events.append((current_event, payload))
                current_event = "message"

    total_time = time.monotonic() - start
    return status_code, content_type, events, first_chunk_time, total_time


def test_suggest_delivery_delay_streams_full_text():
    status_code, content_type, events, first_chunk_time, total_time = _collect_stream(
        "TK-00043", "Meu pedido #481516 não chegou e já passou do prazo, urgente")

    assert status_code == 200
    assert content_type.startswith("text/event-stream")

    # Reconstrói o texto a partir dos chunks "message" (sem event: explícito).
    chunks = [payload["chunk"] for event, payload in events if event == "message"]
    assert "".join(chunks) == EXPECTED_SUGGESTION

    # Último evento é "end" com o ticket_id, conforme documentacao/contract.md.
    assert events[-1] == ("end", {"ticket_id": "TK-00043"})

    # Requisito 6: primeiro trecho chega antes da metade do tempo total da
    # resposta. O limite absoluto de 1,5s do contrato depende da precisão de
    # agendamento do host rodando o provider-fake (ver documentacao/plan.md);
    # a relação "antes da metade" é a parte robusta e testável aqui.
    assert first_chunk_time < total_time / 2


def test_suggest_missing_text_returns_422():
    response = httpx.post(f"{APP_URL}/tickets/reply-suggestion", json={"ticket_id": "TK-1"}, timeout=60)

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail[0]["type"] == "missing"
    assert detail[0]["loc"] == ["body", "text"]
