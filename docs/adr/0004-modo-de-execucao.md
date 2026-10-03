# 0004. Modo de execução por feature

- Status: aceita
- Data: 2026-10-02
- Nível: software

## Contexto

Uma chamada a LLM não se comporta como uma chamada HTTP comum: demora segundos, custa por token, chega aos poucos e prende conexões. O requisito 6 pede, para cada feature, uma decisão explícita entre síncrono, streaming e assíncrono, a partir de três perguntas: "alguém está esperando agora?", "cabe no orçamento de latência?", "é consumível aos poucos?". Ver [documentacao/adr.md (ADR-004)](../../documentacao/adr.md#adr-004-modo-de-execução-por-feature) para o rascunho original das perguntas por feature.

## Opções consideradas

Para cada feature, as três opções do requisito 6 (síncrono, streaming, assíncrono), avaliadas contra o contrato de negócio de cada uma (ver [documentacao/contract.md](../../documentacao/contract.md)).

## Decisão

| Feature | Alguém espera agora? | Cabe no orçamento síncrono? | Consumível aos poucos? | Modo escolhido |
|---|---|---|---|---|
| F1 Classificação | Sim | Sim (saída curta) | Não | **Síncrono**, timeout de 15s |
| F2 Sugestão de resposta | Sim | Não (saída longa) | Sim | **Streaming (SSE)** |
| F3 Relatório de temas | Não | Não (5.000 tickets em lotes) | Não de forma útil | **Asynchronous Request-Reply** (`202` → polling → `303`) |
| F4 Extração de dados | Não (sem humano na tela) | Sim | Não | **Síncrono**, timeout de 15s |

F1 e F4 mantêm o contrato síncrono já fixado nas tags anteriores. F2 e F3 mudam de contrato — por isso `tests/characterization/test_reply_suggestion.py` e `test_topics_report.py` foram atualizados na `main` (R2 permite isso explicitamente; `test_classification.py` e `test_extraction.py` continuam intocados).

## Consequências

- **F1/F4 (síncrono):** o cliente OpenAI do app (`adapters/gateway.py`) usa `max_retries=0` (quem decide retry é o gateway); as rotas são `async def` e envolvem a chamada bloqueante com `asyncio.wait_for(..., timeout=15)`, devolvendo `503` explícito se estourar — nunca ficam penduradas.
- **F2 (streaming):** `StreamingResponse` com `media_type="text/event-stream"` e o header `X-Accel-Buffering: no`, que desativa o buffer do nginx da borda **sem precisar alterar `edge/nginx.conf`** (proibido pelo enunciado) — nginx reconhece esse header por padrão.
- **F3 (assíncrono):** job em memória (`report._jobs`, com lock, já que o handler HTTP e a tarefa de fundo rodam em threads diferentes do threadpool do Starlette), disparado via `BackgroundTasks` do FastAPI.

## Evidência

Testado nesta sessão, pela borda (`localhost:8000`):

- **F1 normal:** `200` em ~1,7s. **F1 com primário em `timeout`:** `200` via fallback em **11,77s** (dentro do orçamento de 15s).
- **F2 (`curl -N`):** `Content-Type: text/event-stream`; chunks chegam incrementalmente (confirmado com timestamp por linha, intervalos de 15-50ms entre chunks — não "tudo de uma vez"); primeiro chunk sempre antes da metade do tempo total. **Achado:** o tempo *absoluto* até o primeiro chunk mediu 3-5s nesta sessão (não os 1,5s do contrato) porque o próprio `provider-fake`, direto, já demora ~2,1-2,5s até o primeiro token neste ambiente (Docker Desktop/Windows) — acima do TTFT de 0,8s documentado no `provider-fake/README.md`. Confirmado que não é bug da aplicação: medido direto no `provider-fake` (sem gateway, sem app), o atraso já existe. É uma característica do ambiente de execução local, não da arquitetura — vale remedir no ambiente do avaliador.
- **F2 com `midstream_error` no primário:** cliente recebe `event: error` / `data: {"ticket_id": "...", "message": "A geração foi interrompida"}` depois de alguns chunks reais, exatamente no formato de [documentacao/contract.md](../../documentacao/contract.md#f2--sugerir-resposta).
- **F3 normal:** `202` em 45ms, com `Location`/`Retry-After`; polling mostra `{"state": "running", "progress": "300/5000"}`; ao concluir, `303` → resultado idêntico ao fixado pela suíte.
- **F3 com os dois providers em `error_500`:** `{"state": "failed", "reason": "..."}` em **10s** (bem dentro do orçamento de 60s), nunca preso em `running`.
- Nenhum dos cenários acima produziu `504` da borda.
