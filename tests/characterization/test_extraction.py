"""F4 — POST /tickets/extraction"""
from client import post


def test_extract_order_with_product():
    response = post("/tickets/extraction", {
        "ticket_id": "TK-00045",
        "text": "Tenho aqui a nota fiscal 530720. O mouse sem fio veio quebrado na caixa, pedido #605065.",
    })

    assert response.status_code == 200
    assert response.json() == {
        "ticket_id": "TK-00045",
        "order_number": "#605065",
        "product": "mouse sem fio",
    }


def test_extract_order_without_identifiable_product():
    response = post("/tickets/extraction", {
        "ticket_id": "TK-00044",
        "text": "Quero trocar o pedido #605065, o produto veio quebrado",
    })

    assert response.status_code == 200
    assert response.json() == {
        "ticket_id": "TK-00044",
        "order_number": "#605065",
        "product": None,
    }


def test_extract_ticket_without_order_number():
    response = post("/tickets/extraction", {
        "ticket_id": "TK-00046",
        "text": "Voces tem loja fisica na minha cidade",
    })

    assert response.status_code == 200
    assert response.json() == {
        "ticket_id": "TK-00046",
        "order_number": None,
        "product": None,
    }


def test_extract_missing_text_returns_422():
    response = post("/tickets/extraction", {"ticket_id": "TK-1"})

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail[0]["type"] == "missing"
    assert detail[0]["loc"] == ["body", "text"]
