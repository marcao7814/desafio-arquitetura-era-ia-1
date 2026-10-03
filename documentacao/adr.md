# ADRs — Log de Decisões

> Síntese de [specs.md](./specs.md) (R5–R7) e [plan.md](./plan.md). Este arquivo é o **rascunho consolidado** das decisões de arquitetura; o entregável final exige 1 arquivo por decisão em `docs/adr/`, cada um com `Nível: corporativa|solução|software` — ao finalizar a Fase 7 do plano, cada seção abaixo deve ser promovida a um arquivo próprio (ex.: `docs/adr/0001-gateway.md`).
>
> Decisões marcadas **Proposta** ainda não têm evidência de execução (o código não existe neste repositório ainda); ao implementar, substituir "Evidência a coletar" pelo resultado real observado via `/admin/calls` ou pela borda — nunca inventar números.

## Índice por nível (mínimo exigido: ≥1 por nível)

| ADR | Nível | Título |
|---|---|---|
| [ADR-000](#adr-000-pol%C3%ADtica-corporativa-de-providers-e-or%C3%A7amento-de-ia) | Corporativa | Política de providers aceitos e teto de gasto mensal com IA |
| [ADR-001](#adr-001-posição-e-escolha-do-ai-gateway) | Solução | Posição e escolha do AI Gateway |
| [ADR-002](#adr-002-política-de-fallback-técnico-e-com-modelo-fraco) | Solução | Política de fallback (técnico e com modelo fraco) |
| [ADR-003](#adr-003-capacidades-lógicas-e-mapeamento-para-modelos-físicos) | Software | Capacidades lógicas e mapeamento para modelos físicos |
| [ADR-004](#adr-004-modo-de-execução-por-feature) | Software | Modo de execução por feature |
| [ADR-005](#adr-005-governança-de-chaves-orçamentos-e-limites) | Software | Governança de chaves, orçamentos e limites |
| [ADR-006](#adr-006-leitura-da-métrica-de-acoplamento-e-exceções) | Software | Leitura da métrica de acoplamento e exceções declaradas |

---

## ADR-000: Política corporativa de providers e orçamento de IA

**Nível:** corporativa
**Status:** Decidida — ver [docs/adr/0008-politica-corporativa-providers-orcamento.md](../docs/adr/0008-politica-corporativa-providers-orcamento.md) para o texto final.

**Contexto.** A empresa hoje usa OpenAI e Anthropic lado a lado sem critério ("funcionou melhor no teste"), sem teto de gasto declarado e sem responsável único pela decisão de qual provider é aceitável para dados de clientes.

**Opções consideradas.**
1. Não restringir — cada feature escolhe o provider que quiser.
2. Lista fechada de providers aceitos (OpenAI, Anthropic) + teto de gasto mensal declarado, aplicado no nível de infraestrutura (gateway), não no código de cada feature.
3. Provider único para toda a empresa.

**Decisão.** Opção 2: lista fechada de providers aceitos e um teto de gasto mensal com IA, aplicado via orçamento (budget) por chave no gateway (ver [ADR-005](#adr-005-governança-de-chaves-orçamentos-e-limites)). A escolha de qual provider físico atende cada chamada deixa de ser decisão de cada feature e passa a ser decisão de infraestrutura, revisável sem envolver código.

**Consequências.** Nenhuma feature pode decidir sozinha usar um provider fora da lista; todo aumento de orçamento é uma mudança de configuração no gateway, auditável. Fica mais fácil negociar contrato comercial com um número fechado de providers.

**Evidência a coletar:** valor do teto e lista final de providers — a confirmar com o roteiro de governança (Fase 5 de [plan.md](./plan.md)).

---

## ADR-001: Posição e escolha do AI Gateway

**Nível:** solução
**Status:** Decidida — ver [docs/adr/0006-posicao-e-escolha-do-gateway.md](../docs/adr/0006-posicao-e-escolha-do-gateway.md) para o texto final.

**Contexto.** Na v1, a app depende de detalhes concretos e voláteis de cada provider (SDK, formato de API, nome de modelo, credencial). R5 exige um gateway self-hosted como serviço `gateway` no compose, entregando capacidades lógicas, credenciais isoladas, troca de modelo por config, governança e resiliência.

**Opções consideradas.**
1. Gateway SaaS — descartado por restrição do desafio (avaliador precisa subir tudo localmente).
2. LiteLLM Proxy self-hosted (sugestão do enunciado) — implementa virtual keys, budget, rate limit, fallback e retry nativamente; precisa de um banco de dados para chaves/orçamento.
3. Gateway próprio (middleware FastAPI na frente dos SDKs) — mais controle, mais código para manter; reinventa o que o LiteLLM já entrega.

**Decisão.** LiteLLM Proxy como serviço `gateway` no compose, com configuração versionada em `gateway/`. Toda chamada de `app/` a um modelo passa por ele, usando nomes lógicos de capacidade e uma virtual key do próprio gateway (nunca as chaves de `provider-fake`).

**Consequências.** Precisa de um banco de dados para chaves/orçamento (serviço extra no compose → exige seu próprio ADR de justificativa, conforme restrição do desafio). Se o LiteLLM não conhecer o preço dos modelos simulados, custo é calculado como zero e o orçamento nunca estoura — mitigar isso é parte do roteiro de governança (ver [runbook.md](./runbook.md)).

**Evidência a coletar:** confirmação de que `grep -rE "gpt-fake|claude-fake" app/` não retorna nada após a Fase 4 de [plan.md](./plan.md).

---

## ADR-002: Política de fallback (técnico e com modelo fraco)

**Nível:** solução
**Status:** Decidida, com evidência

**Contexto.** R5 exige, para toda capacidade: timeout explícito, retry limitado com backoff, e fallback técnico para um destino equivalente em outro provider. Além disso, para cada feature, decidir se — sem nenhum modelo `large` disponível — vale responder com um `mini` ou falhar explicitamente. É decisão de produto, não só de infraestrutura.

**Opções consideradas.**
1. Fallback técnico apenas (outro provider, mesmo tamanho `large`) — sem fallback para `mini`.
2. Fallback técnico + fallback para `mini` em todas as features.
3. Fallback técnico sempre; fallback para `mini` decidido feature por feature, com base na comparação real de saídas `large` vs `mini` por tarefa.

**Decisão.** Opção 3. Fallback técnico (outro provider, mesmo capacidade) é obrigatório para as 4 features, com número máximo de tentativas por destino declarado no README.

**Evidência coletada** (script `compare_models.py`, chamando `gpt-fake-large/mini` e `claude-fake-large/mini` direto no `provider-fake`, mesmos tickets nos dois tamanhos):

| Tarefa | Amostras | Divergências | O que divergiu |
|---|---|---|---|
| `classify` (F1) | 4 tickets | 0/4 | nenhuma — `category` e `priority` idênticos em todos os casos |
| `topics` (F3) | 1 dia (137 tickets) | 0 | mesmos 15 temas, mesmas contagens exatas |
| `suggest` (F2) | 2 tickets | 2/2 | texto mais curto e com conselhos diferentes (ex.: `large` oferece coleta do produto sem custo; `mini` pede foto/vídeo) — diferente, mas coerente como rascunho |
| `extract` (F4) | 3 tickets | 2/3 | **`mini` extraiu o número da nota fiscal (`#530720`) como se fosse o número do pedido, em vez do pedido real (`#605065`)**, e perdeu o nome do produto num dos casos |

**Decisão por feature:**

| Feature | Fallback técnico | Fallback com `mini`? | Motivo |
|---|---|---|---|
| F1 Classificação | Sim | **Sim** | 0/4 divergências — `mini` entrega exatamente o mesmo resultado estruturado |
| F2 Sugestão de resposta | Sim | **Sim** | o atendente edita antes de enviar (não é saída final automática); um rascunho mais simples ainda é melhor que nenhum rascunho |
| F3 Relatório de temas | Sim | **Sim** | 0 divergências nos temas/contagens testados; ninguém espera olhando, e um relatório com `mini` ainda é melhor que nenhum relatório |
| F4 Extração de dados | Sim | **Não — falha explícita** | `mini` errou o número do pedido em 2 de 3 casos. F4 alimenta troca/devolução sem revisão humana: um pedido errado vira uma troca errada, que custa frete, estoque e cliente real. A evidência mostra que a degradação não é "uma resposta pior", é "uma resposta estruturalmente errada" |

**Consequências.** F1/F2/F3 ganham uma camada extra de disponibilidade (ainda respondem mesmo com os dois `large` fora do ar); F4 prioriza correção sobre disponibilidade — com os dois `gpt-fake-large`/`claude-fake-large` indisponíveis, F4 responde com erro explícito em vez de arriscar um número de pedido errado.

**Evidência:** `scripts/compare_models.py` (versionado no repo). Rodar com `pip install openai anthropic && python scripts/compare_models.py` contra o `provider-fake` no ar — reproduzível com qualquer ticket de `data/tickets.jsonl`.

---

## ADR-003: Capacidades lógicas e mapeamento para modelos físicos

**Nível:** software
**Status:** Decidida — ver [docs/adr/0007-capacidades-logicas.md](../docs/adr/0007-capacidades-logicas.md) para o texto final.

**Contexto.** R5 exige que nenhum nome de modelo físico (`gpt-fake-*`, `claude-fake-*`) apareça em `app/`. A app deve pedir uma capacidade lógica; o gateway resolve o modelo físico.

**Opções consideradas.**
1. Uma capacidade lógica por feature (`classification`, `reply-suggestion`, `topics-report`, `extraction`).
2. Uma capacidade lógica por tarefa do provider simulado (`classify`, `suggest`, `topics`, `extract`) — mais próxima do domínio do `provider-fake`, reutilizável se duas features um dia compartilharem tarefa.
3. Uma capacidade lógica genérica ("llm-default") para tudo — descartado, pois impede decisão de fallback por feature exigida em R5/R7.

**Decisão.** Opção 2: uma capacidade lógica por tarefa, nomeada no padrão `helpdesk-<tarefa>` (ex.: `helpdesk-classify`, `helpdesk-suggest`, `helpdesk-topics`, `helpdesk-extract`). Cada capacidade mapeia, na config do gateway, para um modelo primário (`large`) + fallback técnico (outro provider, mesmo tamanho) + fallback opcional para `mini` (conforme [ADR-002](#adr-002-política-de-fallback-técnico-e-com-modelo-fraco)).

**Consequências.** Trocar o modelo físico por trás de uma capacidade é só editar `gateway/` e reiniciar `gateway` — `app/` nunca muda para isso. O mapeamento completo (capacidade → primário → fallback técnico → fallback fraco → máx. tentativas) é documentado na "Tabela de capacidades" do README final. O código que fala com o gateway (SDK/cliente HTTP) fica em **um único componente** de `app/` — nenhum componente de feature o importa, só o ponto de composição (`main.py`) pode depender dele. Essa restrição é o que impede o acoplamento direto a provider de voltar pela porta dos fundos, e é verificada tanto pela métrica (R3) quanto pelos critérios de aceite.

**Evidência a coletar:** demonstração de troca de modelo sem rebuild/restart de `app`, conforme critério de aceite de [specs.md](./specs.md).

---

## ADR-004: Modo de execução por feature

**Nível:** software
**Status:** Decidida e implementada — ver [docs/adr/0004-modo-de-execucao.md](../docs/adr/0004-modo-de-execucao.md) para o texto final com evidência.

**Contexto.** Uma chamada a LLM não se comporta como uma chamada HTTP comum. R6 exige decidir, por feature, entre síncrono, streaming e assíncrono, a partir de 3 perguntas: "alguém está esperando agora?", "cabe no orçamento de latência?", "é consumível aos poucos?".

**Decisão preliminar (por feature):**

### F1 — Classificação
- Alguém está esperando agora? **Sim** (cliente aguarda confirmação na tela).
- Cabe no orçamento de latência (≤3s)? **Sim**, com modelo `large` e fallback técnico sob timeout de 15s.
- É consumível aos poucos? **Não** — saída curta e estruturada, sem valor em parcelar.
- **Modo:** síncrono, com timeout explícito e fallback técnico.

### F2 — Sugestão de resposta
- Alguém está esperando agora? **Sim** (atendente olhando a tela).
- Cabe no orçamento de latência como resposta única? **Não** — saída longa, ≥1,5s só para o primeiro trecho.
- É consumível aos poucos? **Sim** — atendente já começa a ler/editar antes do fim.
- **Modo:** streaming (SSE), com evento `error` no meio do stream em caso de falha.

### F3 — Relatório de temas
- Alguém está esperando agora? **Não** — painel sem callback, ninguém olha em tempo real.
- Cabe no orçamento de latência síncrono? **Não** — 5.000 tickets em lotes de 150 não cabe em 1s nem em 30s de borda.
- É consumível aos poucos de forma útil para quem pediu? **Não realmente** — o consumo é "tudo ou nada" (relatório fechado), o valor está em não bloquear a conexão.
- **Modo:** Asynchronous Request-Reply (`202` + polling/`303`), com `failed` explícito em até 60s se não concluir.

### F4 — Extração de dados
- Alguém está esperando agora? **Não** — alimenta automação, sem humano na tela.
- Cabe no orçamento de latência síncrono? **Sim**, mas sem usuário aguardando o valor do streaming é baixo.
- É consumível aos poucos? **Não** — saída curta e estruturada, consumida por outro sistema.
- **Modo:** síncrono, com timeout explícito e fallback técnico (mesmo racional de F1); por ser consumida sem revisão humana, fallback com modelo fraco tende a ficar desligado (ver [ADR-002](#adr-002-política-de-fallback-técnico-e-com-modelo-fraco)).

**Consequências.** F2 e F3 exigem testes de caracterização atualizados na `main` (R2 permite isso explicitamente). F1 e F4 mantêm o contrato síncrono já fixado nas tags anteriores.

**Evidência a coletar:** medição real de latência pela borda para cada feature, nos cenários de `specs.md` (`timeout`, `error_500` nos dois `large`, `midstream_error`).

---

## ADR-005: Governança de chaves, orçamentos e limites

**Nível:** software
**Status:** Decidida, com evidência — ver [docs/adr/0003-governanca-chaves.md](../docs/adr/0003-governanca-chaves.md) para o texto final.

**Contexto.** R5 exige ≥1 chave com orçamento (budget) e ≥1 com limite de requisições, com recusa **antes** de chegar ao provider.

**Opções consideradas.**
1. Uma única virtual key para toda a app, com budget e rate limit combinados.
2. Chave de produção (`app`) sem limites apertados + chaves de demonstração dedicadas para o roteiro de governança, isolando o risco de uma demo derrubar a operação normal.

**Decisão.** Opção 2. `app` usa `GATEWAY_API_KEY` sem budget/rate limit apertado. Duas virtual keys de demonstração (`demo-budget`, `demo-ratelimit`), restritas a `helpdesk-classify`, são criadas por script (`gateway/setup_governance_demo_keys.sh`, chamando `POST /key/generate` — sem passo manual em painel). Preço real por token declarado em `gateway/config.yaml` (sem isso o LiteLLM calcula custo zero e o orçamento nunca estoura).

**Consequências.** `app/` usa só a chave do gateway — nunca `FAKE_OPENAI_KEY`/`FAKE_ANTHROPIC_KEY` (confirmado: `docker compose exec app env` só mostra `GATEWAY_BASE_URL`/`GATEWAY_API_KEY`). O roteiro de governança do README produz, de forma repetível, 1 recusa por orçamento (`429 budget_exceeded`) e 1 por rate limit (`429 throttling_error`), sem incrementar `/admin/calls` — testado nesta sessão.

**Evidência a coletar:** execução do roteiro descrito em [runbook.md](./runbook.md#roteiro-de-governança).

---

## ADR-006: Leitura da métrica de acoplamento e exceções declaradas

**Nível:** software
**Status:** Decidida, com evidência — ver [docs/adr/0005-metrica-excecoes.md](../docs/adr/0005-metrica-excecoes.md) para o texto final.

**Contexto.** R3 define a régua fixa (Ca, Ce, I, A, D) sobre `app/helpdesk/`. Componentes concretos e estáveis por natureza podem cair na zona de dor sem serem um problema real; é permitido declará-los como exceção, com justificativa — exceto o componente que chama o gateway e os componentes de feature.

**Decisão.** Na medição da `main`, `config.py` e `schemas.py` caem na zona de dor mecanicamente (`Ca` alto, `A=0`, `Ce=0`) e são declarados exceção: são módulos de tipos de valor e configuração, sem comportamento, que não mudam com a infraestrutura. `adapters.gateway` — que caiu na zona de dor até a Fase 5 — **não** virou exceção (a régua proíbe): foi corrigido estruturalmente, fazendo-o depender de `config` para sua própria configuração em vez de recebê-la via parâmetros do composition root (`Ce` passou de 0 para 1, tirando-o da zona de dor: `I=0,5`, que não é `<0,5`).

**Consequências.** Nenhum componente de feature nem `adapters.gateway` está na zona de dor na `main` — confirmado em `metrics/results/main.csv`. As únicas exceções são os dois módulos de valor/configuração, exatamente o caso que specs.md antecipa como "não um problema real".

**Evidência:** `metrics/results/main.csv` — `adapters.gateway`: `Ca=1, Ce=1, I=0,50, A=0,00, D=0,50` (fora da zona de dor); `config`: `Ca=6, Ce=0, I=0,00, A=0,00, D=1,00` (zona de dor, exceção); `schemas`: `Ca=5, Ce=0, I=0,00, A=0,00, D=1,00` (zona de dor, exceção).
