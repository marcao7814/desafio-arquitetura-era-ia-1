"""F3 — POST /reports/topics (assíncrono, decidido no requisito 6 / ADR-004)

O contrato mudou da v2-decoupled para a main: a suíte da v1-coupled/v2-decoupled
fixava um 200 síncrono com o relatório completo; aqui fixamos o fluxo
Asynchronous Request-Reply (202 -> polling -> 303 -> resultado), mas o
resultado final continua sendo os mesmos 15 temas determinísticos.

Usa um único dia (2026-08-01, 137 tickets) em vez do mês inteiro para manter a
suíte rápida — ver documentacao/runbook.md, Dor 1, sobre o tempo real do
relatório mensal completo.
"""
import time

from client import get, post

EXPECTED_TOPICS = [
    {"topic": "Problema no rastreio", "count": 20, "examples": ["TK-00001", "TK-00007", "TK-00008"]},
    {"topic": "Pedido extraviado", "count": 15, "examples": ["TK-00005", "TK-00006", "TK-00009"]},
    {"topic": "Troca por tamanho", "count": 11, "examples": ["TK-00015", "TK-00039", "TK-00045"]},
    {"topic": "Arrependimento de compra", "count": 9, "examples": ["TK-00022", "TK-00034", "TK-00044"]},
    {"topic": "Estorno pendente", "count": 9, "examples": ["TK-00024", "TK-00033", "TK-00046"]},
    {"topic": "Outros assuntos", "count": 9, "examples": ["TK-00003", "TK-00011", "TK-00017"]},
    {"topic": "Pix não reconhecido", "count": 9, "examples": ["TK-00021", "TK-00023", "TK-00050"]},
    {"topic": "Problema com boleto", "count": 9, "examples": ["TK-00020", "TK-00027", "TK-00029"]},
    {"topic": "Atraso na entrega", "count": 8, "examples": ["TK-00010", "TK-00025", "TK-00028"]},
    {"topic": "Defeito de fabricação", "count": 8, "examples": ["TK-00035", "TK-00041", "TK-00071"]},
    {"topic": "Produto não liga", "count": 8, "examples": ["TK-00018", "TK-00030", "TK-00036"]},
    {"topic": "Cobrança duplicada", "count": 6, "examples": ["TK-00058", "TK-00099", "TK-00102"]},
    {"topic": "Produto danificado", "count": 6, "examples": ["TK-00002", "TK-00040", "TK-00048"]},
    {"topic": "Acesso à conta", "count": 5, "examples": ["TK-00012", "TK-00014", "TK-00072"]},
    {"topic": "Cupom de desconto", "count": 5, "examples": ["TK-00004", "TK-00107", "TK-00108"]},
]


def _poll_until_done(status_path: str, timeout_seconds: float = 60) -> str:
    """Faz polling do status até 303 (done) ou falha; devolve a Location do resultado."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        response = get(status_path)
        if response.status_code == 303:
            return response.headers["location"]
        assert response.status_code == 200
        body = response.json()
        assert body["state"] in ("pending", "running"), body
        time.sleep(1)
    raise AssertionError(f"job não terminou em {timeout_seconds}s: último estado consultado acima")


def test_topics_for_single_day():
    accepted = post("/reports/topics", {"start": "2026-08-01", "end": "2026-08-01"})

    assert accepted.status_code == 202
    assert accepted.headers["location"].startswith("/reports/topics/status/")
    assert "retry-after" in accepted.headers

    result_path = _poll_until_done(accepted.headers["location"])
    assert result_path.startswith("/reports/topics/")

    result = get(result_path)
    assert result.status_code == 200
    assert result.json() == {
        "start": "2026-08-01",
        "end": "2026-08-01",
        "total_tickets": 137,
        "topics": EXPECTED_TOPICS,
    }


def test_topics_start_after_end_returns_422():
    response = post("/reports/topics", {"start": "2026-08-31", "end": "2026-08-01"})

    assert response.status_code == 422
    assert response.json() == {"detail": "A data inicial é posterior à data final"}
