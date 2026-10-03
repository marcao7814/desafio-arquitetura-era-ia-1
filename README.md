# Da integração frágil à arquitetura resiliente — Helpdesk com IA

> O enunciado completo do desafio está em [documentacao/solicitacao.md](documentacao/solicitacao.md). O planejamento (contrato, especificação técnica, plano de execução, ADRs propostos, runbook e plano de testes) está em [documentacao/](documentacao/). Este README documenta o estado real da entrega, atualizado conforme as fases avançam.

## Visão geral

O helpdesk de uma loja online tem 4 features de IA (classificação de ticket, sugestão de resposta, relatório de temas e extração de dados de pedido) acopladas diretamente a dois providers (OpenAI e Anthropic), de forma síncrona e sem resiliência. O objetivo deste trabalho é levar essa aplicação a um estado em que trocar de modelo ou de provider seja mudança de configuração — não um projeto — passando por: diagnóstico medido da v1, testes de caracterização, medição de acoplamento, refatoração assistida por agente atrás de um AI Gateway, e decisão explícita do modo de execução de cada feature.

**Status atual:** tag `v2-decoupled` — a aplicação já fala com os providers exclusivamente por um AI Gateway (LiteLLM, serviço `gateway` no compose), usando capacidades lógicas (`helpdesk-classify`, `helpdesk-suggest`, `helpdesk-topics`, `helpdesk-extract`) em vez de nomes de modelo físico. Nenhuma chave de provider chega ao serviço `app`. Governança (orçamento, limite de requisições), resiliência (timeout, retry, fallback técnico e com modelo fraco) e o modo de execução por feature ainda não existem — entram na Fase 5 e 6 do [plano de execução](documentacao/plan.md). Por isso, hoje, um provider instável ainda derruba as features que dependem dele (ver Dor 3 no diagnóstico abaixo); esta seção será atualizada com o comportamento final de resiliência ao fim da Fase 6.

## Diagnóstico da v1

Ambiente: `cp .env.example .env && docker compose up -d --build --wait`, provider simulado resetado (`POST localhost:8090/admin/reset`) antes de cada reprodução. Procedimento completo em [documentacao/runbook.md](documentacao/runbook.md#5-reproduzir-as-4-dores-do-cenário-diagnóstico-da-v1).

### Dor 1 — o relatório do mês nunca termina

**Comando:**
```bash
time curl -s -w "\nHTTP_STATUS:%{http_code} TOTAL_TIME:%{time_total}s\n" \
  -X POST localhost:8000/reports/topics -H "Content-Type: application/json" \
  -d '{"start": "2026-08-01", "end": "2026-08-31"}'
```

**Observado:** a borda devolveu `504 Gateway Time-out` em exatos `30,04s` (`TOTAL_TIME:30.040261s`). Consultando `GET localhost:8090/admin/calls` depois disso, a aplicação continuou chamando o provider: só nos ~90s seguintes ao `504` já havia 11 lotes da tarefa `topics` concluídos, de um total de 34 necessários para os 5.000 tickets do mês (cada lote demora ~9,8s, 150 tickets por vez) — ou seja, o processo real leva perto de 5,5 minutos, e a aplicação segue pagando tokens mesmo depois que o cliente desistiu.

**Causa no código:** [app/helpdesk/report.py](app/helpdesk/report.py) processa os lotes em um laço `for` síncrono, um depois do outro (`llm.call_anthropic` bloqueante, sem cancelamento); [edge/nginx.conf:21](edge/nginx.conf) define `proxy_read_timeout 30s`, bem menor que o tempo real da tarefa; nada no caminho (app, SDK) sabe ou se importa que o cliente já recebeu o `504`.

### Dor 2 — o atendente espera sem ver nada

**Comando:**
```bash
curl -s -o /dev/null -w "1o byte: %{time_starttransfer}s | fim: %{time_total}s\n" \
  -X POST localhost:8000/tickets/reply-suggestion -H "Content-Type: application/json" \
  -d '{"ticket_id": "TK-00043", "text": "..."}'
```

**Observado:** `1o byte: 15.872702s | fim: 15.872935s` — o primeiro byte chega praticamente no mesmo instante que o último. O atendente olha para uma tela parada por quase 16 segundos antes do texto aparecer inteiro de uma vez.

**Causa no código:** [app/helpdesk/suggestion.py:6](app/helpdesk/suggestion.py) chama `llm.call_anthropic` de forma síncrona e retorna o texto completo; [app/helpdesk/llm.py:20](app/helpdesk/llm.py) usa `anthropic_client.messages.create(...)` sem `stream=True`, então a resposta só existe por completo no final.

### Dor 3 — um provider instável derruba parte do helpdesk

**Comando:**
```bash
curl -s -X POST localhost:8090/admin/failures -H "Content-Type: application/json" \
  -d '{"provider": "anthropic", "mode": "error_500"}'
# em seguida, chamar as 4 features pela borda
```

**Observado:** com `anthropic` em `error_500`, F1 (classificação) e F4 (extração) continuaram respondendo `200` normalmente; F2 (sugestão) e F3 (relatório) passaram a responder `500 Internal Server Error` em ~1,2–1,5s. Metade do helpdesk parou porque metade das features depende exclusivamente do provider que caiu.

**Causa no código:** [app/helpdesk/config.py:9-13](app/helpdesk/config.py) fixa `anthropic` para F2/F3 e `openai` para F1/F4, cada feature falando com um único provider via [app/helpdesk/llm.py](app/helpdesk/llm.py), sem nenhum destino alternativo.

### Dor 4 — trocar modelo exige mudar código e reconstruir

**Comando:**
```bash
# editar CLASSIFICATION_MODEL em app/helpdesk/config.py de "gpt-fake-large" para "gpt-fake-mini"
curl -s -X POST localhost:8000/tickets/classification ... # ainda responde com gpt-fake-large
docker compose up -d --build app
curl -s -X POST localhost:8000/tickets/classification ... # agora responde com gpt-fake-mini
```

**Observado:** antes do rebuild, `GET /admin/calls` mostrava `"model":"gpt-fake-large"` mesmo com o código já alterado no host — a imagem do container não mudou. Só depois de `docker compose up -d --build app` o registro passou a mostrar `"model":"gpt-fake-mini"` (e, de fato, mais rápido: `duration_ms` caiu de 1077 para 375, compatível com os tempos declarados no README do `provider-fake`). A alteração foi revertida depois (`git status --short app/` vazio), conforme a regra do requisito 1.

**Causa no código:** [app/helpdesk/config.py:10-13](app/helpdesk/config.py) tem o nome do modelo físico hardcoded; nada na aplicação permite trocar isso sem alterar e reconstruir a imagem.

> **Nota (tag `v2-decoupled`):** `app/helpdesk/config.py` não tem mais nenhum nome de modelo físico — só capacidades lógicas (`helpdesk-classify` etc.). O mapeamento capacidade → modelo físico mora em [gateway/config.yaml](gateway/config.yaml). A demonstração completa de troca por configuração (editar só `gateway/`, reiniciar só o serviço `gateway`, `app` não reiniciar) fica para a seção "Troca de modelo" na Fase 5.

## Como rodar

```bash
cp .env.example .env
docker compose up -d --build --wait
curl -s localhost:8000/health   # 200 {"status":"ok"}
```

Sobe 4 serviços: `provider-fake`, `gateway` (AI Gateway, LiteLLM — ver [gateway/config.yaml](gateway/config.yaml)), `app` e `edge`. O `app` só recebe `GATEWAY_BASE_URL`/`GATEWAY_API_KEY`; as chaves do `provider-fake` ficam só no ambiente do `gateway` (ver `compose.yaml`).

### Testes de caracterização

```bash
pip install -r tests/characterization/requirements.txt
pytest tests/characterization -v
```

10 testes, cobrindo as 4 features (caso feliz + caso de erro de entrada cada), contra a borda (`localhost:8000`). Fixam o corpo completo das respostas, não só o status. F3 usa um único dia (2026-08-01, 137 tickets) em vez do mês inteiro para manter a suíte rápida — ver nota em [tests/characterization/test_topics_report.py](tests/characterization/test_topics_report.py).

### Métrica de acoplamento

```bash
pip install -r metrics/requirements.txt
python metrics/measure.py app/helpdesk --out metrics/results/<nome-da-tag>.csv
pytest metrics/test_measure.py -v   # testa a régua do próprio script com um pacote sintético
```

Gera `metrics/results/<nome-da-tag>.csv` e o `.png` correspondente (gráfico A×I com a Main Sequence). Régua completa em [documentacao/specs.md](documentacao/specs.md#r3--métrica-de-acoplamento-régua-fixa).

**v1-coupled → v2-decoupled:** `llm.py` (zona de dor, `Ca=4`) foi extinto; em seu lugar, `ports.py` (um `Protocol`, `A=1,00`, fora da zona de dor) e `adapters/gateway.py` (único componente de `app/` que fala com o gateway, importado só por `main.py`). As 4 features mantêm exatamente a mesma leitura de `v1` (`I` e `D` inalterados) — a refatoração trocou *quem* elas importam (de um módulo concreto para uma abstração), não *quanto* elas importam. `adapters.gateway` continua na zona de dor nesta tag (`Ca=1`, já no mínimo possível, mas `Ce=0` ⇒ `I=0`): é um achado registrado em [docs/refactoring-plan.md](docs/refactoring-plan.md#revisão-do-plano) e não é resolvido artificialmente aqui — a expectativa é que a Fase 5 (retry/backoff/fallback) decomponha esse adapter em colaboradores internos reais, subindo `Ce` organicamente. O critério de aceite que proíbe exceção para este componente é escopado à tag `main`, não a esta.

**Leitura do gráfico da v1-coupled:**

| Componente | Ca | Ce | I | A | D | Zona de dor? |
|---|---|---|---|---|---|---|
| `main` | 0 | 5 | 1,00 | 0,00 | 0,00 | não (I=1, correto para um composition root) |
| `report` | 1 | 4 | 0,80 | 0,00 | 0,20 | não |
| `extraction` / `suggestion` | 1 | 3 | 0,75 | 0,00 | 0,25 | não |
| `classification` | 1 | 3 | 0,75 | 0,00 | 0,25 | não |
| `tickets` | 1 | 1 | 0,50 | 0,00 | 0,50 | não (I=0,50 não é `<0,50`, fica no limite) |
| `llm` | 4 | 1 | 0,20 | 0,00 | 0,80 | **sim** |
| `config` | 6 | 0 | 0,00 | 0,00 | 1,00 | **sim** |
| `schemas` | 5 | 0 | 0,00 | 0,00 | 1,00 | **sim** |

`llm.py`, `config.py` e `schemas.py` caem na zona de dor (`A<0,5 ∧ I<0,5 ∧ D≥0,5`): são componentes muito dependidos (`Ca` alto) e totalmente concretos (`A=0`). `llm.py` é hoje o componente que fala direto com os SDKs dos providers — exatamente o papel que, segundo [documentacao/adr.md (ADR-003)](documentacao/adr.md#adr-003-capacidades-lógicas-e-mapeamento-para-modelos-físicos), **não pode** ser declarado exceção: é alvo prioritário da refatoração da Fase 4 (provavelmente introduzindo uma abstração/porta que as features dependam, invertendo a dependência). `schemas.py` é o candidato mais claro a "estável por natureza" (são só tipos de valor — modelos Pydantic de entrada/saída), mas a decisão de declará-lo exceção fica para o ADR da métrica ([ADR-006](documentacao/adr.md#adr-006-leitura-da-métrica-de-acoplamento-e-exceções-declaradas)), à luz da medição da `main`, não da `v1`.

## Tabela de capacidades

_A preencher na Fase 5 (gateway) — ver [documentacao/adr.md](documentacao/adr.md#adr-003-capacidades-lógicas-e-mapeamento-para-modelos-físicos)._

## Tabela de fallback

_A preencher na Fase 5, com evidência real de comparação `large` vs `mini` por tarefa — ver [documentacao/adr.md](documentacao/adr.md#adr-002-política-de-fallback-técnico-e-com-modelo-fraco)._

## Fluxos

_A preencher na Fase 6 (modo de execução por feature) — ver [documentacao/adr.md](documentacao/adr.md#adr-004-modo-de-execução-por-feature)._

## Troca de modelo

_A preencher na Fase 5 — hoje (v1-coupled) a troca de modelo exige editar [app/helpdesk/config.py](app/helpdesk/config.py) e reconstruir a imagem (ver Dor 4 acima); esse é exatamente o comportamento que o gateway vai eliminar._

## Roteiro de governança

_A preencher na Fase 5 — depende da configuração de orçamento e limite de requisições no gateway, que ainda não existe nesta tag._

## Mapa de decisões

_A preencher na Fase 7 — rascunho das decisões já em [documentacao/adr.md](documentacao/adr.md); os ADRs definitivos vão para `docs/adr/`._
