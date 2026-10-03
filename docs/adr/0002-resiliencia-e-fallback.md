# 0002. Resiliência técnica e fallback com modelo fraco decidido por feature

- Status: aceita
- Data: 2026-10-02
- Nível: solução

## Parte 1 — Resiliência técnica (timeout, retry, fallback entre providers)

Para as 4 capacidades, `gateway/config.yaml` declara: timeout explícito por capacidade (não um valor único — ver racional abaixo), `num_retries: 1` (2 tentativas por destino) e fallback técnico para o destino equivalente no outro provider, via `litellm_settings.fallbacks`.

**Por que o timeout não é um valor único para as 4 capacidades:** a latência real em modo normal, medida nesta sessão, varia muito entre tarefas — `classify`/`extract` (saída curta) ~1,1s; `topics` (lote de 150 tickets) ~9,8s; `suggest` (saída longa, sem streaming nesta fase) ~15,9s. Um timeout baixo único (ex. 15s, pensado para caber no orçamento de latência da borda) quebraria `suggest` e `topics` em operação **normal**, não só em falha. Por isso: `helpdesk-classify`/`helpdesk-extract` = 4s; `helpdesk-topics` = 15s; `helpdesk-suggest` = 20s (todas com folga sobre a latência normal observada).

**Número máximo de tentativas por destino: 2** (1 chamada + 1 retry, `num_retries: 1`). Confirmado via `/admin/calls`: com `openai/gpt-fake-large` em `error_500`, exatamente 2 chamadas malsucedidas no primário antes do sucesso no fallback técnico (`anthropic/claude-fake-large`) — sem retry configurado em mais de uma camada (SDK da app não faz retry; quem faz é só o gateway).

**Evidência (testada nesta sessão):**
- Fallback técnico: primário em `error_500` → 2 tentativas no primário, depois sucesso no destino equivalente do outro provider, resposta idêntica à esperada (`category: delivery, priority: high`).
- Timeout: primário em `timeout` (trava 300s) → gateway não espera o provider; com `helpdesk-classify` (timeout=4s), resposta via fallback em ~13s — dentro do orçamento de 15s do requisito 6 para F1 com provider primário travado.

## Parte 2 — Fallback com modelo fraco por feature, com evidência

## Contexto

Com os dois modelos `large` (um por provider) indisponíveis para uma capacidade, a aplicação precisa decidir: responder com um modelo `mini` (mais fraco) ou falhar explicitamente. É decisão de produto — depende do custo de um erro em cada feature — não só de infraestrutura. Ver [documentacao/adr.md (ADR-002)](../../documentacao/adr.md#adr-002-política-de-fallback-técnico-e-com-modelo-fraco) para o histórico completo da decisão.

## Opções consideradas

1. Nunca usar `mini` como fallback — toda feature falha explicitamente sem `large`.
2. Sempre usar `mini` como fallback — toda feature aceita a degradação.
3. Decidir por feature, com base em evidência real comparando saídas `large` vs `mini` nas 4 tarefas do `provider-fake`.

## Decisão

Opção 3. Script `scripts/compare_models.py` chamou `gpt-fake-large/mini` e `claude-fake-large/mini` direto no `provider-fake`, nas 4 tarefas, com os mesmos tickets:

| Tarefa (feature) | Amostras | Divergências | Achado |
|---|---|---|---|
| `classify` (F1) | 4 tickets | 0/4 | `category`/`priority` idênticos |
| `topics` (F3) | 137 tickets (1 dia) | 0 | mesmos 15 temas, mesmas contagens |
| `suggest` (F2) | 2 tickets | 2/2 | texto mais curto, conselho diferente, mas coerente |
| `extract` (F4) | 3 tickets | 2/3 | **`mini` trocou o número do pedido pelo número da nota fiscal** |

Decisão: `helpdesk-classify`, `helpdesk-suggest` e `helpdesk-topics` têm fallback para `mini` configurado em `gateway/config.yaml` (`litellm_settings.fallbacks`); `helpdesk-extract` **não tem** — com os dois `large` fora do ar, F4 responde com erro explícito.

## Consequências

F1/F2/F3 ganham disponibilidade extra (ainda respondem, com qualidade reduzida, quando os dois providers `large` caem). F4 prioriza correção: um pedido errado na extração vira uma troca errada, que custa frete, estoque e cliente de verdade — a evidência mostrou que esse risco é concreto (`mini` errou em 2 de 3 casos testados), não hipotético.

## Evidência

```bash
pip install openai anthropic
python scripts/compare_models.py
```

Para ver o fallback em produção: derrubar os dois `large` de uma capacidade (`POST /admin/failures` duas vezes) e chamar a capacidade pelo gateway — `helpdesk-classify`/`helpdesk-suggest`/`helpdesk-topics` respondem com sucesso via `mini` (`/admin/calls` mostra `model: gpt-fake-mini` ou `claude-fake-mini`); `helpdesk-extract` responde `500` explícito. Comandos completos em [documentacao/runbook.md](../../documentacao/runbook.md#6-simular-falhas-do-provider-para-validar-resiliência-do-gateway-fase-56).
