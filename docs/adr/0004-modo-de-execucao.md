# 0004. Modo de execução por feature

- Status: aceita
- Data: 2026-10-02
- Nível: software

## Contexto

Uma chamada a LLM não se comporta como uma chamada HTTP comum: demora segundos, custa por token, chega aos poucos e prende conexões. O requisito 6 pede, para cada feature, uma decisão explícita entre síncrono, streaming e assíncrono, a partir de três perguntas: "alguém está esperando agora?", "cabe no orçamento de latência?", "é consumível aos poucos?". Contrato de referência de cada feature em [documentacao/contract.md](../../documentacao/contract.md).

## Opções consideradas

Para cada feature, as três opções do requisito 6 — síncrono, streaming, assíncrono — avaliadas contra as características do contrato de negócio daquela feature especificamente (não um padrão único para as 4).

## Decisão (uma seção por feature)

### F1 — Classificação

- **Características do contrato:** cliente aguarda confirmação na tela assim que abre o ticket (alguém espera agora); saída curta e estruturada (`category`+`priority`); orçamento de 3s em modo normal.
- **Árvore de decisão:** alguém espera agora? **Sim.** Cabe no orçamento síncrono? **Sim** (saída curta). Consumível aos poucos? **Não** — não há valor em parcelar dois campos.
- **Modo escolhido:** **Síncrono**, com timeout explícito de 15s a nível de aplicação.
- **Implementação:** rota `async def` em `app/helpdesk/main.py`, chamada bloqueante (`classification.classify`) envolvida em `asyncio.wait_for(..., timeout=15)`; estourou → `503` explícito, nunca fica pendurada. Cliente OpenAI do app usa `max_retries=0` (quem decide retry é o gateway).
- **Evidência:** normal → `200` em ~1,2-1,7s. Com primário em `timeout` → `200` via fallback em 11,1-11,8s (dentro do orçamento de 15s), testado em múltiplas sessões, inclusive em clone limpo.

### F2 — Sugestão de resposta

- **Características do contrato:** atendente olhando a tela, começa a ler/editar assim que o texto aparece (alguém espera agora, mas consumível aos poucos); saída longa (não cabe em um orçamento síncrono de poucos segundos).
- **Árvore de decisão:** alguém espera agora? **Sim.** Cabe no orçamento síncrono como resposta única? **Não** — saída longa, ≥15s sem streaming. Consumível aos poucos? **Sim** — o atendente já lê/edita antes do fim.
- **Modo escolhido:** **Streaming (SSE)**.
- **Implementação:** `StreamingResponse` com `media_type="text/event-stream"` e o header `X-Accel-Buffering: no`, que desativa o buffer do nginx da borda **sem alterar `edge/nginx.conf`** (proibido pelo enunciado) — nginx reconhece esse header por padrão. Erro no meio do stream vira evento `error` no formato do contrato.
- **Evidência:** `curl -N` mostra `Content-Type: text/event-stream` e chunks chegando incrementalmente (timestamp por linha, intervalos de 15-50ms — não "tudo de uma vez"); primeiro chunk sempre antes da metade do tempo total da resposta. Com `midstream_error` no primário, o cliente recebe `event: error` / `data: {"ticket_id": "...", "message": "A geração foi interrompida"}`. **Achado de ambiente:** o tempo *absoluto* até o primeiro chunk mediu 3-5s nesta sessão (acima dos 1,5s do contrato) porque o próprio `provider-fake`, chamado direto (sem app, sem gateway), já demora ~2,1-2,5s até o primeiro token neste ambiente de desenvolvimento (Docker Desktop/Windows) — acima do TTFT de 0,8s documentado no `provider-fake/README.md`. Não é buffer escondido na aplicação (confirmado medindo direto no provider); vale remedir no ambiente do avaliador.

### F3 — Relatório de temas

- **Características do contrato:** ninguém espera olhando (painel interno sem callback); 5.000 tickets processados em lotes de 150, não cabe num orçamento síncrono nem nos 30s da borda; resultado é "tudo ou nada" (não há valor real em consumir o relatório pela metade).
- **Árvore de decisão:** alguém espera agora? **Não.** Cabe no orçamento síncrono? **Não** — nem 1s nem 30s cobrem ~34 lotes sequenciais. Consumível aos poucos de forma útil? **Não realmente** — o valor está em não bloquear a conexão, não em consumir o relatório incompleto.
- **Modo escolhido:** **Asynchronous Request-Reply** (`202` → polling com `Location`/`Retry-After` → `303` → resultado).
- **Implementação:** job em memória (`report._jobs`, com lock — o handler HTTP e a tarefa de fundo rodam em threads diferentes do threadpool do Starlette), disparado via `BackgroundTasks` do FastAPI; `GET /reports/topics/status/{job_id}` responde `200` com `state`/`progress` enquanto não termina, `303` ao concluir; `GET /reports/topics/{job_id}` devolve o relatório final.
- **Evidência:** `202` em 45ms, com `Location`/`Retry-After`. Polling mostra progresso real (`{"state": "running", "progress": "300/5000"}`). Pedido do mês inteiro conclui com `total_tickets: 5000` e as chamadas da tarefa `topics` aparecem em `/admin/calls`. Com os dois providers em `error_500`, chega a `{"state": "failed", "reason": "..."}` em ~9-10s (dentro do orçamento de 60s), nunca preso em `running`.

### F4 — Extração de dados

- **Características do contrato:** alimenta automação de troca/devolução sem humano na tela (ninguém espera); saída curta e estruturada, consumida por outro sistema (não há valor em parcelar).
- **Árvore de decisão:** alguém espera agora? **Não.** Cabe no orçamento síncrono? **Sim** (saída curta), mas sem usuário aguardando o valor do streaming é baixo. Consumível aos poucos? **Não.**
- **Modo escolhido:** **Síncrono**, mesmo timeout de 15s de F1. Diferente de F1, **sem** fallback para modelo fraco (ver [0002-resiliencia-e-fallback.md](0002-resiliencia-e-fallback.md)) — por alimentar automação sem revisão humana, um erro de extração custa frete, estoque e cliente reais.
- **Implementação:** mesmo padrão de F1 (`asyncio.wait_for(..., timeout=15)`, `503` explícito se estourar).
- **Evidência:** normal → `200` em ~1,2-1,9s.

## Consequências

F1 e F4 mantêm o contrato síncrono já fixado nas tags anteriores. F2 e F3 mudam de contrato — por isso `tests/characterization/test_reply_suggestion.py` e `test_topics_report.py` foram atualizados na `main` (R2 permite isso explicitamente); `test_classification.py` e `test_extraction.py` continuam intocados (`git diff v2-decoupled main -- tests/characterization/test_classification.py tests/characterization/test_extraction.py` vazio).

## Evidência consolidada

Nenhum dos cenários testados (F1 timeout, F2 midstream_error, F3 falha total, operação normal das 4 features) produziu `504` da borda. Comandos exatos e saída completa de cada teste em [documentacao/runbook.md](../../documentacao/runbook.md) e na seção "Fluxos" do [README.md](../../README.md#fluxos).
