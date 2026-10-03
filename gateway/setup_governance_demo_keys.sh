#!/bin/sh
# Cria as duas virtual keys de demonstração de governança do roteiro do README
# (ver documentacao/runbook.md, "Roteiro de governança"). Sem passo manual em
# painel: a criação é só este script, chamando a API do próprio LiteLLM.
#
# Pré-requisito: gateway no ar e saudável (docker compose up -d --wait gateway).
# Uso: GATEWAY_MASTER_KEY=... ./gateway/setup_governance_demo_keys.sh
set -eu

GATEWAY_URL="${GATEWAY_URL:-http://localhost:4000}"
MASTER_KEY="${GATEWAY_MASTER_KEY:?defina GATEWAY_MASTER_KEY (ver .env)}"

# Idempotente: remove as chaves demo de uma execução anterior antes de recriar
# (key_alias precisa ser único no LiteLLM). Ignora erro se não existirem.
curl -sf -X POST "$GATEWAY_URL/key/delete" \
  -H "Authorization: Bearer $MASTER_KEY" -H "Content-Type: application/json" \
  -d '{"key_aliases": ["demo-budget", "demo-ratelimit"]}' >/dev/null 2>&1 || true

echo "Criando demo-budget (max_budget baixo, estoura na 2a chamada de helpdesk-classify)..."
BUDGET_RESPONSE=$(curl -sf -X POST "$GATEWAY_URL/key/generate" \
  -H "Authorization: Bearer $MASTER_KEY" -H "Content-Type: application/json" \
  -d '{"key_alias": "demo-budget", "models": ["helpdesk-classify"], "max_budget": 0.0001}')
echo "$BUDGET_RESPONSE" | grep -o '"key":"[^"]*"'

echo "Criando demo-ratelimit (1 req/min, a 2a chamada imediata é recusada)..."
RATELIMIT_RESPONSE=$(curl -sf -X POST "$GATEWAY_URL/key/generate" \
  -H "Authorization: Bearer $MASTER_KEY" -H "Content-Type: application/json" \
  -d '{"key_alias": "demo-ratelimit", "models": ["helpdesk-classify"], "rpm_limit": 1}')
echo "$RATELIMIT_RESPONSE" | grep -o '"key":"[^"]*"'

echo "Chaves criadas. Use o valor de \"key\" de cada resposta acima no roteiro de governança do README."
