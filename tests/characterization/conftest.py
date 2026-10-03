"""Suíte de caracterização (Feathers) do helpdesk.

Fixa o comportamento observado na v1-coupled, pelas 4 rotas HTTP, via borda.

Pré-requisito: `cp .env.example .env && docker compose up -d --build --wait` na raiz.
Execução: pip install -r tests/characterization/requirements.txt && pytest tests/characterization -v

Esta suíte precisa ser idêntica (git diff vazio) entre as tags v1-coupled e
v2-decoupled. Só evolui na main, para o contrato das features cujo modo de
execução mudou (ver docs/adr/ e documentacao/plan.md, Fase 6).
"""
import httpx
import pytest

from client import PROVIDER_URL


@pytest.fixture(autouse=True)
def reset_provider():
    httpx.post(f"{PROVIDER_URL}/admin/reset", timeout=10)
    yield
