"""F3 — POST /reports/topics

Usa um único dia (2026-08-01, 137 tickets) em vez do mês inteiro para manter a
suíte rápida: um único lote de até 150 tickets já exercita a mesma chamada ao
provider que o período inteiro, sem pagar pelos ~34 lotes sequenciais do mês
(ver documentacao/runbook.md, Dor 1, sobre o tempo real do relatório mensal).
"""
from client import post

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


def test_topics_for_single_day():
    response = post("/reports/topics", {"start": "2026-08-01", "end": "2026-08-01"})

    assert response.status_code == 200
    assert response.json() == {
        "start": "2026-08-01",
        "end": "2026-08-01",
        "total_tickets": 137,
        "topics": EXPECTED_TOPICS,
    }


def test_topics_start_after_end_returns_422():
    response = post("/reports/topics", {"start": "2026-08-31", "end": "2026-08-01"})

    assert response.status_code == 422
    assert response.json() == {"detail": "A data inicial é posterior à data final"}
