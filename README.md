# Da integração frágil à arquitetura resiliente — Helpdesk com IA

> O enunciado completo do desafio está em [documentacao/solicitacao.md](documentacao/solicitacao.md). O planejamento (contrato, especificação técnica, plano de execução, ADRs propostos, runbook e plano de testes) está em [documentacao/](documentacao/). Este README documenta o estado real da entrega, atualizado conforme as fases avançam.

## Visão geral

O helpdesk de uma loja online tem 4 features de IA (classificação de ticket, sugestão de resposta, relatório de temas e extração de dados de pedido) acopladas diretamente a dois providers (OpenAI e Anthropic), de forma síncrona e sem resiliência. O objetivo deste trabalho é levar essa aplicação a um estado em que trocar de modelo ou de provider seja mudança de configuração — não um projeto — passando por: diagnóstico medido da v1, testes de caracterização, medição de acoplamento, refatoração assistida por agente atrás de um AI Gateway, e decisão explícita do modo de execução de cada feature.

**Status atual:** `main` — todas as 7 fases do [plano de execução](documentacao/plan.md) concluídas. A aplicação fala com os providers exclusivamente por um AI Gateway (LiteLLM, serviços `gateway`+`db` no compose), usando capacidades lógicas (`helpdesk-classify`, `helpdesk-suggest`, `helpdesk-topics`, `helpdesk-extract`) com timeout explícito, retry limitado, fallback técnico entre providers e fallback com modelo fraco decidido por feature (ligado para F1/F2/F3, desligado para F4 — ver Tabela de fallback), mais governança mínima (orçamento + limite de requisições). Nenhuma chave de provider chega ao serviço `app`. Cada feature tem o modo de execução decidido no contrato (requisito 6): **F1 e F4 síncronos** (timeout de 15s, erro explícito se estourar), **F2 em streaming** (SSE) e **F3 assíncrono** (`202` → polling → `303`). Com isso, as 4 dores do diagnóstico da v1 abaixo estão resolvidas: o relatório não trava mais o cliente (assíncrono), a sugestão mostra texto incremental (streaming), um provider instável não derruba mais o helpdesk (fallback técnico/fraco) e a troca de modelo é só configuração do gateway (ver Troca de modelo).

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

**Causa no código:** `app/helpdesk/suggestion.py:6` (v1) chamava `llm.call_anthropic` de forma síncrona e retornava o texto completo; `app/helpdesk/llm.py:20` (v1) usava `anthropic_client.messages.create(...)` sem `stream=True`, então a resposta só existia por completo no final. Ambos os arquivos mudaram desde então — `llm.py` foi removido na Fase 4 (ver métrica abaixo), e `suggestion.py` ganhou streaming de verdade na Fase 6 (ver Fluxos).

### Dor 3 — um provider instável derruba parte do helpdesk

**Comando:**
```bash
curl -s -X POST localhost:8090/admin/failures -H "Content-Type: application/json" \
  -d '{"provider": "anthropic", "mode": "error_500"}'
# em seguida, chamar as 4 features pela borda
```

**Observado:** com `anthropic` em `error_500`, F1 (classificação) e F4 (extração) continuaram respondendo `200` normalmente; F2 (sugestão) e F3 (relatório) passaram a responder `500 Internal Server Error` em ~1,2–1,5s. Metade do helpdesk parou porque metade das features depende exclusivamente do provider que caiu.

**Causa no código (v1):** `app/helpdesk/config.py:9-13` fixava `anthropic` para F2/F3 e `openai` para F1/F4, cada feature falando com um único provider via `app/helpdesk/llm.py` (removido na Fase 4), sem nenhum destino alternativo. Resolvido na Fase 5 com fallback técnico no gateway (ver Tabela de capacidades).

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

### Script de métrica

```bash
pip install -r metrics/requirements.txt
python metrics/measure.py app/helpdesk --out metrics/results/<nome-da-tag>.csv
pytest metrics/test_measure.py -v   # testa a régua do próprio script com um pacote sintético
```

Gera `metrics/results/<nome-da-tag>.csv` e o `.png` correspondente (gráfico A×I com a Main Sequence). Régua completa em [documentacao/specs.md](documentacao/specs.md#r3--métrica-de-acoplamento-régua-fixa).

## Métrica

Leitura dos três gráficos (`v1-coupled`, `v2-decoupled`, `main`) e as exceções declaradas.

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

**Leitura do gráfico da v2-decoupled:**

| Componente | Ca | Ce | I | A | D | Zona de dor? |
|---|---|---|---|---|---|---|
| `main` | 0 | 7 | 1,00 | 0,00 | 0,00 | não |
| `report` | 1 | 4 | 0,80 | 0,00 | 0,20 | não |
| `classification` / `extraction` / `suggestion` | 1 | 3 | 0,75 | 0,00 | 0,25 | não |
| `tickets` | 1 | 1 | 0,50 | 0,00 | 0,50 | não |
| `ports` | 4 | 0 | 0,00 | 1,00 | 0,00 | não |
| `adapters.gateway` | 1 | 0 | 0,00 | 0,00 | 1,00 | **sim** |
| `config` | 6 | 0 | 0,00 | 0,00 | 1,00 | **sim** |
| `schemas` | 5 | 0 | 0,00 | 0,00 | 1,00 | **sim** |

Nesta tag, `adapters.gateway` ainda está na zona de dor: é o componente novo que chama o gateway, com `Ca=1` (só `main` o importa, já no mínimo) mas `Ce=0` (não depende de nada internamente) — a régua classifica qualquer componente-folha assim como "zona de dor" mecanicamente. Como a régua proíbe exceção para esse componente, ele precisava ser corrigido de verdade antes da tag `main` (ver abaixo), não just declarado exceção aqui.

**Leitura do gráfico da `main` (final):**

| Componente | Ca | Ce | I | A | D | Zona de dor? |
|---|---|---|---|---|---|---|
| `main` | 0 | 6 | 1,00 | 0,00 | 0,00 | não |
| `report` | 1 | 4 | 0,80 | 0,00 | 0,20 | não |
| `classification` / `extraction` / `suggestion` | 1 | 3 | 0,75 | 0,00 | 0,25 | não |
| `tickets` | 1 | 1 | 0,50 | 0,00 | 0,50 | não |
| `adapters.gateway` | 1 | 1 | 0,50 | 0,00 | 0,50 | não |
| `ports` | 4 | 0 | 0,00 | 1,00 | 0,00 | não |
| `config` | 6 | 0 | 0,00 | 0,00 | 1,00 | **sim — exceção declarada** |
| `schemas` | 5 | 0 | 0,00 | 0,00 | 1,00 | **sim — exceção declarada** |

Entre a `v2-decoupled` e a `main`, `adapters.gateway` saiu da zona de dor: passou a depender de `config` para sua própria configuração (URL/chave do gateway), em vez de recebê-la via parâmetros do composition root — `Ce` subiu de 0 para 1 (`I` foi de 0,00 para 0,50, que não é `<0,50`). Essa mudança segue o mesmo padrão já usado por `classification`/`suggestion`/`extraction`/`report` (cada um lê sua própria config), não foi desenhada só para mexer no número. `config.py` e `schemas.py` continuam na zona de dor mecanicamente e são declarados exceção — nenhum dos dois é feature nem o componente que chama o gateway, e nenhum tem comportamento (só tipos de valor e constantes). Nenhum componente de feature está na zona de dor. Detalhe e evidência completa em [docs/adr/0005-metrica-excecoes.md](docs/adr/0005-metrica-excecoes.md).

## Tabela de capacidades

Configuração completa em [gateway/config.yaml](gateway/config.yaml). Número máximo de tentativas por destino (primário, fallback técnico e modelo fraco, quando existe): **2** (1 chamada + 1 retry — `litellm_settings.num_retries: 1`).

| Capacidade lógica | Feature | Modelo primário | Fallback técnico | Fallback com modelo fraco | Timeout |
|---|---|---|---|---|---|
| `helpdesk-classify` | F1 Classificação | `openai/gpt-fake-large` | `anthropic/claude-fake-large` | `openai/gpt-fake-mini` | 4s |
| `helpdesk-suggest` | F2 Sugestão de resposta | `anthropic/claude-fake-large` | `openai/gpt-fake-large` | `anthropic/claude-fake-mini` | 20s |
| `helpdesk-topics` | F3 Relatório de temas | `anthropic/claude-fake-large` | `openai/gpt-fake-large` | `anthropic/claude-fake-mini` | 15s |
| `helpdesk-extract` | F4 Extração de dados | `openai/gpt-fake-large` | `anthropic/claude-fake-large` | **nenhum** | 4s |

Timeout calibrado pela latência real de cada tarefa em modo normal (classify/extract ~1,1s; topics ~9,8s/lote; suggest ~15,9s sem streaming) — um valor único e baixo quebraria `suggest`/`topics` em operação normal, não só em falha. Detalhe em [docs/adr/0002-resiliencia-e-fallback.md](docs/adr/0002-resiliencia-e-fallback.md).

## Tabela de fallback

Decisão por feature, com evidência real (`large` vs `mini` nas 4 tarefas, [scripts/compare_models.py](scripts/compare_models.py)) — detalhe completo em [docs/adr/0002-resiliencia-e-fallback.md](docs/adr/0002-resiliencia-e-fallback.md).

| Feature | Sem nenhum `large` disponível | Evidência |
|---|---|---|
| F1 Classificação | Responde via `gpt-fake-mini` (`200`) | 0/4 divergências nos testes — `category`/`priority` idênticos ao `large` |
| F2 Sugestão de resposta | Responde via `claude-fake-mini` (`200`), texto mais curto | 2/2 divergências, mas texto coerente; atendente revisa antes de enviar |
| F3 Relatório de temas | Responde via `claude-fake-mini` (`200`) | 0 divergências nos 15 temas/contagens testados (dia 2026-08-01) |
| F4 Extração de dados | Falha explícita (`500`) — **sem fallback para `mini`** | 2/3 divergências; `mini` confundiu o número da nota fiscal com o número do pedido — erro real, não hipotético, numa feature sem revisão humana |

Testado nesta sessão: com os dois `large` de uma capacidade em `error_500`, `helpdesk-classify`/`helpdesk-suggest`/`helpdesk-topics` respondem `200` via `mini`; `helpdesk-extract` responde `500`.

## Fluxos

Decisão completa, com a árvore de perguntas por feature, em [docs/adr/0004-modo-de-execucao.md](docs/adr/0004-modo-de-execucao.md).

### F1 — Classificação (síncrono)

```bash
curl -s -X POST localhost:8000/tickets/classification -H "Content-Type: application/json" \
  -d '{"ticket_id": "TK-00042", "text": "Meu pedido #481516 não chegou, urgente"}'
# 200 {"ticket_id": "TK-00042", "category": "delivery", "priority": "high"}
```

Timeout de 15s no nível da aplicação: se estourar, responde `503` explícito em vez de ficar pendurada.

### F2 — Sugestão de resposta (streaming/SSE)

```bash
curl -N -X POST localhost:8000/tickets/reply-suggestion -H "Content-Type: application/json" \
  -d '{"ticket_id": "TK-00042", "text": "Meu pedido #481516 não chegou, urgente"}'
# 200, Content-Type: text/event-stream
# data: {"chunk": "Olá! ..."}
# data: {"chunk": "..."}
# ...
# event: end
# data: {"ticket_id": "TK-00042"}
```

Se o provider falhar no meio da geração (`midstream_error`), o cliente recebe `event: error` / `data: {"ticket_id": "...", "message": "A geração foi interrompida"}`, no formato de [documentacao/contract.md](documentacao/contract.md#f2--sugerir-resposta).

**Nota de ambiente:** o primeiro trecho chega sempre antes da metade do tempo total da resposta (confirmado), mas o tempo *absoluto* até o primeiro chunk mediu 3-5s nesta sessão de desenvolvimento, não os 1,5s do contrato — porque o próprio `provider-fake`, chamado direto (sem app, sem gateway), já demora ~2,1-2,5s até o primeiro token neste ambiente (Docker Desktop/Windows), acima do TTFT de 0,8s documentado. Não é um buffer escondido na aplicação — confirmado medindo chunk a chunk com timestamp. Detalhe em [docs/adr/0004-modo-de-execucao.md](docs/adr/0004-modo-de-execucao.md).

### F3 — Relatório de temas (assíncrono)

```bash
curl -s -i -X POST localhost:8000/reports/topics -H "Content-Type: application/json" \
  -d '{"start": "2026-08-01", "end": "2026-08-31"}'
# 202 Accepted
# Location: /reports/topics/status/<job_id>
# Retry-After: 5

curl -s localhost:8000/reports/topics/status/<job_id>
# 200 {"state": "running", "progress": "300/5000"}
# ... quando terminar:
# 303 See Other, Location: /reports/topics/<job_id>

curl -s localhost:8000/reports/topics/<job_id>
# 200 {"start": "...", "end": "...", "total_tickets": 5000, "topics": [...]}
```

Se o relatório não conseguir terminar (ex.: os dois providers fora do ar), o status chega a `{"state": "failed", "reason": "..."}` em até 60s — testado: 10s.

### F4 — Extração de dados (síncrono)

```bash
curl -s -X POST localhost:8000/tickets/extraction -H "Content-Type: application/json" \
  -d '{"ticket_id": "TK-00042", "text": "Quero trocar o pedido #605065, veio quebrado"}'
# 200 {"ticket_id": "TK-00042", "order_number": "#605065", "product": null}
```

Mesmo timeout de 15s de F1. Diferente de F1, sem fallback para modelo fraco (ver Tabela de fallback).

## Troca de modelo

Editar `litellm_params.model` da capacidade em [gateway/config.yaml](gateway/config.yaml) (ex.: `openai/gpt-fake-large` → `openai/gpt-fake-mini` em `helpdesk-classify`) e reiniciar **só** o gateway:

```bash
docker compose restart gateway
```

`app` não é tocado. Testado nesta sessão: trocando `helpdesk-classify` para `gpt-fake-mini`, a próxima chamada pela borda (`curl localhost:8000/tickets/classification`) já respondeu com o novo modelo (`GET localhost:8090/admin/calls` mostrou `"model":"gpt-fake-mini"`, `duration_ms` caiu de 1076 para 375), e `docker compose ps app` mostrou o mesmo tempo de atividade de antes da troca — `app` nunca reiniciou.

## Roteiro de governança

```bash
GATEWAY_MASTER_KEY=sk-gateway-master-0001 ./gateway/setup_governance_demo_keys.sh
```

Cria (de forma idempotente, sem passo manual em painel) duas virtual keys restritas a `helpdesk-classify`: `demo-budget` (orçamento de US$ 0,0001) e `demo-ratelimit` (1 requisição/minuto). O script imprime o valor de cada chave — use-o nos comandos abaixo.

**Recusa por orçamento:**
```bash
curl -s -X POST localhost:4000/chat/completions -H "Authorization: Bearer <demo-budget-key>" \
  -H "Content-Type: application/json" \
  -d '{"model": "helpdesk-classify", "messages": [{"role": "user", "content": "TASK: classify\nteste"}]}'
# repetir o mesmo comando — a 2a chamada responde 429:
# {"error":{"message":"Budget has been exceeded! ...","type":"budget_exceeded","code":"429"}}
```

**Recusa por limite de requisições:**
```bash
curl -s -X POST localhost:4000/chat/completions -H "Authorization: Bearer <demo-ratelimit-key>" \
  -H "Content-Type: application/json" \
  -d '{"model": "helpdesk-classify", "messages": [{"role": "user", "content": "TASK: classify\nteste"}]}'
# repetir imediatamente — a 2a chamada responde 429:
# {"error":{"message":"Rate limit exceeded ...","type":"throttling_error","code":"429"}}
```

Em ambos os casos, confirmado nesta sessão: `GET localhost:8090/admin/calls` não ganha um novo registro na chamada recusada — a recusa acontece no gateway, antes do provider. Detalhe e evidência completa em [docs/adr/0003-governanca-chaves.md](docs/adr/0003-governanca-chaves.md).

## Mapa de decisões

Rascunho e histórico de cada decisão (contexto, opções descartadas) em [documentacao/adr.md](documentacao/adr.md). ADRs definitivos, com evidência testada nesta sessão:

| ADR | Nível | Resumo |
|---|---|---|
| [0001](docs/adr/0001-banco-de-dados-do-gateway.md) | software | Postgres para persistir chaves virtuais do gateway |
| [0002](docs/adr/0002-resiliencia-e-fallback.md) | solução | Timeout por capacidade, retry limitado (2/destino), fallback técnico entre providers e fallback com modelo fraco decidido por feature com evidência real |
| [0003](docs/adr/0003-governanca-chaves.md) | software | Chaves de demonstração para orçamento e limite de requisições, criadas por script |
| [0004](docs/adr/0004-modo-de-execucao.md) | software | Modo de execução por feature: F1/F4 síncrono, F2 streaming, F3 assíncrono |
| [0005](docs/adr/0005-metrica-excecoes.md) | software | `adapters.gateway` corrigido estruturalmente; `config`/`schemas` declarados exceção |
| [0006](docs/adr/0006-posicao-e-escolha-do-gateway.md) | solução | LiteLLM Proxy como fronteira entre `app/` e os providers |
| [0007](docs/adr/0007-capacidades-logicas.md) | software | Uma capacidade lógica por tarefa (`helpdesk-<tarefa>`) |
| [0008](docs/adr/0008-politica-corporativa-providers-orcamento.md) | corporativa | Providers aceitos e teto de gasto aplicado como orçamento no gateway |
