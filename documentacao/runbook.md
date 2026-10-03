# Runbook Operacional

> Procedimentos práticos para operar, testar e demonstrar a entrega. Complementa [contract.md](./contract.md) (o que a API promete), [specs.md](./specs.md) (o que precisa ser verdade) e [adr.md](./adr.md) (por que foi decidido assim). Os comandos que ficarem repetíveis e documentados aqui alimentam as seções "Como rodar", "Troca de modelo" e "Roteiro de governança" do `README.md` final.

## 1. Subir o ambiente

```bash
cp .env.example .env
docker compose up -d --build --wait
curl -s localhost:8000/health
```

`--wait` só retorna quando os serviços estão saudáveis. Se `curl /health` não responder `200`, checar logs antes de qualquer outra ação:

```bash
docker compose logs app --tail=100
docker compose logs gateway --tail=100
docker compose logs provider-fake --tail=100
```

## 2. Reset do provider simulado (estado limpo antes de cada demonstração)

```bash
curl -s -X POST localhost:8090/admin/reset
```

Usar antes de cada roteiro abaixo, para não misturar `/admin/calls` de uma demonstração com a anterior.

## 3. Rodar a suíte de caracterização

```bash
# comando exato definido na Fase 2 de plan.md — preencher aqui quando a suíte existir
# ex.: docker compose exec app pytest tests/characterization/ -v
```

Critério: a suíte precisa passar sem alteração contra `v1-coupled` e `v2-decoupled` (`git diff v1-coupled v2-decoupled -- tests/characterization/` vazio).

## 4. Rodar o script de métrica

```bash
# ex.: python metrics/measure.py --path app/helpdesk --out metrics/results/<tag-ou-branch>.csv
```

Para medir uma tag específica sem trocar de branch na working copy atual:

```bash
git worktree add ../v1 v1-coupled
python metrics/measure.py --path ../v1/app/helpdesk --out metrics/results/v1-coupled.csv
git worktree remove ../v1
```

Conferir sempre o cabeçalho exato `component,ca,ce,i,a,d` e o gráfico A×I gerado.

## 5. Reproduzir as 4 dores do cenário (Diagnóstico da v1)

Executar contra a aplicação **recebida** (antes de qualquer refatoração), sempre pela borda (`localhost:8000`):

### Dor 1 — relatório do mês nunca termina
```bash
time curl -s -X POST localhost:8000/reports/topics \
  -H "Content-Type: application/json" \
  -d '{"start": "2026-08-01", "end": "2026-08-31"}'
```
Observar: tempo até `504` da borda; conferir `GET localhost:8090/admin/calls` nos minutos seguintes para confirmar se o provider continua sendo chamado após o `504` (dor "desistir não é cancelar").

### Dor 2 — atendente espera sem feedback (F2)
```bash
curl -s -X POST localhost:8000/tickets/reply-suggestion \
  -H "Content-Type: application/json" \
  -d '{"ticket_id": "TK-00042", "text": "..."}'
```
Observar: nada é entregue até a resposta completa (sem streaming); medir o tempo total.

### Dor 3 — provider instável derruba parte do helpdesk
```bash
curl -s -X POST localhost:8090/admin/failures \
  -H "Content-Type: application/json" \
  -d '{"provider": "anthropic", "mode": "error_500"}'

curl -s -X POST localhost:8000/tickets/reply-suggestion \
  -H "Content-Type: application/json" \
  -d '{"ticket_id": "TK-00042", "text": "..."}'
# repetir para /reports/topics (também usa anthropic)

curl -s -X POST localhost:8090/admin/failures \
  -H "Content-Type: application/json" \
  -d '{"provider": "anthropic", "mode": "normal"}'
```
Observar: F2 e F3 falham (sem fallback); F1 e F4 continuam normais (usam `openai`) — evidência do acoplamento direto a um provider por feature.

### Dor 4 — trocar modelo exige deploy
Localizar o nome do modelo físico hardcoded em `app/helpdesk/config.py`, alterar, reconstruir:
```bash
docker compose up -d --build app
```
Observar: não há como trocar sem rebuild. **Reverter a alteração antes de seguir** (regra do R1 — `app/` só pode ser tocado temporariamente para esta demonstração, e precisa estar de volta ao original antes da tag `v1-coupled`).

```bash
curl -s -X POST localhost:8090/admin/reset
```

## 6. Simular falhas do provider (para validar resiliência do gateway, Fase 5/6)

| Cenário | Comando | Efeito esperado |
|---|---|---|
| Provider primário de uma capacidade fora do ar | `POST /admin/failures {"provider": "<p>", "model": "<m>", "mode": "error_500"}` | feature responde com sucesso via fallback técnico; `/admin/calls` mostra tentativas no primário (≤ máx. declarado) + sucesso no destino equivalente |
| Provider primário travado | `... "mode": "timeout"` | feature síncrona responde (sucesso ou erro explícito) em ≤15s |
| Os dois `large` indisponíveis | 2x `POST /admin/failures` com `model` dos dois `*-large` em `error_500` | comportamento exatamente o da tabela de fallback do README (mini ou erro explícito, por feature) |
| Erro no meio do stream (F2, se streaming) | `... "mode": "midstream_error"` | cliente recebe evento `error` no formato de [contract.md](./contract.md#f2--sugerir-resposta) |
| Falha total (F3) | os dois providers inteiros em `error_500` | relatório chega a estado `failed` com motivo em ≤60s, nunca preso em `running` |
| Rate limit do provider (não confundir com o rate limit do gateway) | `... "mode": "error_429"` | retry com backoff absorve a falha transitória (mesmo teto de tentativas do `error_500`) ou aciona o fallback técnico; não é o mesmo cenário da recusa por limite de requisições do §8 — aqui quem recusa é o `provider-fake`, lá é o `gateway` |
| Provider lento, mas não travado | `... "mode": "slow"` | útil para calibrar o timeout: confirmar que o orçamento de latência da feature (3s/1,5s/1s) ainda é respeitado ou que o fallback entra antes do teto de 15s/60s, sem esperar o `timeout` puro |

Não são cenários exigidos por nenhum critério de aceite — servem para robustez extra na calibração de timeout/retry antes de fechar os números do README.

Sempre inspecionar o resultado em:
```bash
curl -s localhost:8090/admin/calls | jq
```
e resetar depois:
```bash
curl -s -X POST localhost:8090/admin/reset
```

## 7. Troca de modelo físico por configuração (pós `v2-decoupled`)

1. Editar `litellm_params.model` da capacidade em [gateway/config.yaml](../gateway/config.yaml) (ex.: `openai/gpt-fake-large` → `openai/gpt-fake-mini`).
2. Reiniciar **só** o gateway:
   ```bash
   docker compose restart gateway
   ```
3. Confirmar que `app` não reiniciou:
   ```bash
   docker compose ps app
   ```
4. Disparar a feature correspondente e confirmar o novo modelo em:
   ```bash
   curl -s localhost:8090/admin/calls | jq '.[-1]'
   ```

## 8. Roteiro de governança

Implementado (Fase 5). Comandos exatos, com as chaves reais geradas pelo script, estão na seção "Roteiro de governança" do [README.md](../README.md#roteiro-de-governança) — não duplicados aqui para não divergir. Resumo:

```bash
GATEWAY_MASTER_KEY=sk-gateway-master-0001 ./gateway/setup_governance_demo_keys.sh
# usar as chaves impressas (demo-budget, demo-ratelimit) nos comandos do README
```

Em ambos os casos (orçamento e rate limit), a 2ª chamada responde `429` e `curl -s localhost:8090/admin/calls | jq 'length'` não aumenta — a recusa acontece no gateway, antes do provider. Decisões e evidência completas: [docs/adr/0003-governanca-chaves.md](../docs/adr/0003-governanca-chaves.md).

## 9. Verificações de isolamento de credenciais (antes de cada tag pós-`v2-decoupled`)

```bash
grep -rE "gpt-fake|claude-fake" app/
grep -rE "FAKE_OPENAI_KEY|FAKE_ANTHROPIC_KEY|sk-fake-openai|sk-ant-fake" app/
docker compose exec app env | grep -E "FAKE_OPENAI_KEY|FAKE_ANTHROPIC_KEY"
docker compose config | grep -A5 "app:" | grep -E "FAKE_OPENAI_KEY|FAKE_ANTHROPIC_KEY"
```
Todos devem retornar vazio.

## 10. Verificação final (clone limpo, Fase 8 de plan.md)

```bash
git clone <url-do-fork> /tmp/verificacao-final
cd /tmp/verificacao-final
cp .env.example .env
docker compose up -d --build --wait
curl -s localhost:8000/health
```

Depois, percorrer item a item os "Critérios de Aceite" de [specs.md](./specs.md#critérios-de-aceite-resumo-verificável), nesta ordem: diagnóstico/caracterização → métrica → plano/refatoração → gateway → fluxos de chamada → decisões → README/consistência geral.

## 11. Encerramento

```bash
docker compose down
```

Usar `-v` apenas se precisar descartar dados persistidos do gateway (ex.: banco de chaves/orçamento) — não usar por padrão, para não perder configuração de governança entre sessões de teste.
