# 0003. Governança de chaves, orçamento e limite de requisições

- Status: aceita
- Data: 2026-10-02
- Nível: software

## Contexto

O requisito 5 exige, no mínimo, uma chave com orçamento (budget) e uma com limite de requisições, com recusa acontecendo **antes** de chegar ao provider (ver [documentacao/specs.md](../../documentacao/specs.md#r5--ai-gateway)). Isso depende de persistência (ver [0001-banco-de-dados-do-gateway.md](0001-banco-de-dados-do-gateway.md)) e de preço real configurado por modelo — sem isso, o LiteLLM calcula custo zero e o orçamento nunca estoura.

## Opções consideradas

1. Uma única virtual key para toda a app, com budget e rate limit combinados na mesma chave.
2. Chaves separadas: a app usa uma chave "de produção" sem limites apertados; chaves de demonstração dedicadas (`demo-budget`, `demo-ratelimit`) existem só para o roteiro de governança do README.
3. Aplicar limites no nível da aplicação (fora do gateway).

## Decisão

Opção 2. A app usa `GATEWAY_API_KEY` (hoje igual à master key do LiteLLM) sem budget/rate limit apertado, para não arriscar quebrar a operação normal por causa de uma demonstração. Duas virtual keys de demonstração são criadas por script (`gateway/setup_governance_demo_keys.sh`, chamando `POST /key/generate` — sem passo manual em painel):

- `demo-budget`: `max_budget=0.0001` USD, restrita a `helpdesk-classify`. Com o preço real declarado em `gateway/config.yaml` (`input_cost_per_token`/`output_cost_per_token`, convertidos da tabela do `provider-fake/README.md`), uma chamada de classificação custa ~US$ 0,000135 — a 2ª chamada já estoura o orçamento.
- `demo-ratelimit`: `rpm_limit=1`, restrita a `helpdesk-classify`. A 2ª chamada no mesmo minuto é recusada.

Opção 3 foi descartada pelas mesmas razões do ADR-001: moveria governança de volta para a aplicação.

## Consequências

O roteiro de governança do README depende de rodar o script de setup primeiro (ele imprime o valor de cada chave, que muda a cada execução — não é fixo no README). As chaves demo são isoladas por `models: ["helpdesk-classify"]`, então não afetam as outras 3 capacidades.

## Evidência

```bash
GATEWAY_MASTER_KEY=sk-gateway-master-0001 ./gateway/setup_governance_demo_keys.sh
# usar o "key" de demo-budget:
curl -s -X POST localhost:4000/chat/completions -H "Authorization: Bearer <demo-budget-key>" \
  -H "Content-Type: application/json" \
  -d '{"model": "helpdesk-classify", "messages": [{"role": "user", "content": "TASK: classify\nteste"}]}'
# repetir — a 2a chamada responde 429 "Budget has been exceeded"
```

Testado nesta sessão: 1ª chamada `200`, 2ª chamada `429` com `"type":"budget_exceeded"` (chave de orçamento) e `429` com `"type":"throttling_error"` (chave de rate limit); em ambos os casos, `GET localhost:8090/admin/calls` não ganhou um novo registro na chamada recusada — confirma que a recusa acontece no gateway, antes do provider.
