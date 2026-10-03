"""F2 — POST /tickets/reply-suggestion"""
from client import post

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


def test_suggest_delivery_delay_returns_full_text():
    response = post("/tickets/reply-suggestion", {
        "ticket_id": "TK-00043",
        "text": "Meu pedido #481516 não chegou e já passou do prazo, urgente",
    })

    assert response.status_code == 200
    assert response.json() == {
        "ticket_id": "TK-00043",
        "suggestion": EXPECTED_SUGGESTION,
    }


def test_suggest_missing_text_returns_422():
    response = post("/tickets/reply-suggestion", {"ticket_id": "TK-1"})

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail[0]["type"] == "missing"
    assert detail[0]["loc"] == ["body", "text"]
