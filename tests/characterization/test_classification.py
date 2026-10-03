"""F1 — POST /tickets/classification"""
from client import post


def test_classify_delivery_delay_returns_high_priority():
    response = post("/tickets/classification", {
        "ticket_id": "TK-00042",
        "text": "Meu pedido #481516 não chegou e já passou do prazo, urgente",
    })

    assert response.status_code == 200
    assert response.json() == {
        "ticket_id": "TK-00042",
        "category": "delivery",
        "priority": "high",
    }


def test_classify_missing_text_returns_422():
    response = post("/tickets/classification", {"ticket_id": "TK-1"})

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail[0]["type"] == "missing"
    assert detail[0]["loc"] == ["body", "text"]
