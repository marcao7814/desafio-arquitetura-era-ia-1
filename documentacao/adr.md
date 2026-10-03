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
**Status:** Proposta

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
**Status:** Proposta

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
**Status:** Proposta — decisão por feature pendente de evidência

**Contexto.** R5 exige, para toda capacidade: timeout explícito, retry limitado com backoff, e fallback técnico para um destino equivalente em outro provider. Além disso, para cada feature, decidir se — sem nenhum modelo `large` disponível — vale responder com um `mini` ou falhar explicitamente. É decisão de produto, não só de infraestrutura.

**Opções consideradas.**
1. Fallback técnico apenas (outro provider, mesmo tamanho `large`) — sem fallback para `mini`.
2. Fallback técnico + fallback para `mini` em todas as features.
3. Fallback técnico sempre; fallback para `mini` decidido feature por feature, com base na comparação real de saídas `large` vs `mini` por tarefa.

**Decisão.** Opção 3. Fallback técnico (outro provider, mesmo capacidade) é obrigatório para as 4 features, com número máximo de tentativas por destino declarado no README. Fallback para `mini` é avaliado individualmente:

| Feature | Fallback técnico | Fallback com `mini`? | Racional preliminar |
|---|---|---|---|
| F1 Classificação | Sim | A confirmar | Saída curta e estruturada — candidata a tolerar `mini` se a comparação mostrar categorias/prioridades equivalentes |
| F2 Sugestão de resposta | Sim | A confirmar | Saída longa, visível ao cliente — risco de qualidade perceptível; decidir com base na comparação de texto |
| F3 Relatório de temas | Sim | A confirmar | Ninguém espera olhando; tolerância a latência maior pode reduzir a pressão por `mini`, mas volume (lotes de 150) pode mudar o cálculo de custo |
| F4 Extração de dados | Sim | A confirmar — tendência a **não** aceitar `mini` | Alimenta automação sem revisão humana; erro custa frete, estoque e cliente — precisa de evidência forte antes de aceitar degradação |

**Consequências.** A tabela final e a evidência (comparação real `large` vs `mini` por tarefa, via chamada direta ao `provider-fake`) substituem os "A confirmar" acima na Fase 5 de [plan.md](./plan.md), antes de ligar qualquer fallback para `mini` em produção.

**Evidência a coletar:** saídas de `classify`, `suggest`, `topics`, `extract` nos dois tamanhos de modelo, comparadas lado a lado — nenhuma inventada aqui.

---

## ADR-003: Capacidades lógicas e mapeamento para modelos físicos

**Nível:** software
**Status:** Proposta

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
**Status:** Proposta — decisão final depende da Fase 6 de [plan.md](./plan.md)

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
**Status:** Proposta

**Contexto.** R5 exige ≥1 chave com orçamento (budget) e ≥1 com limite de requisições, com recusa **antes** de chegar ao provider.

**Opções consideradas.**
1. Uma única virtual key para toda a app, com budget e rate limit combinados.
2. Virtual keys separadas por capacidade/feature, cada uma com seu próprio budget e/ou rate limit, para isolar o "orçamento estourado" de uma feature do resto.

**Decisão.** Opção 2, ao menos para demonstrar o critério de aceite: uma virtual key com budget mensal (ligada a [ADR-000](#adr-000-pol%C3%ADtica-corporativa-de-providers-e-or%C3%A7amento-de-ia)) e outra com limite de requisições (ex.: capacidade de alto volume como `helpdesk-topics`, que processa 5.000 tickets em lotes).

**Consequências.** `app/` usa só a(s) chave(s) do gateway — nunca `FAKE_OPENAI_KEY`/`FAKE_ANTHROPIC_KEY`. O roteiro de governança do README precisa produzir, de forma repetível, 1 recusa por orçamento e 1 por rate limit, sem incrementar `/admin/calls` (prova de que a recusa acontece antes do provider).

**Evidência a coletar:** execução do roteiro descrito em [runbook.md](./runbook.md#roteiro-de-governança).

---

## ADR-006: Leitura da métrica de acoplamento e exceções declaradas

**Nível:** software
**Status:** Proposta — a preencher após medições reais

**Contexto.** R3 define a régua fixa (Ca, Ce, I, A, D) sobre `app/helpdesk/`. Componentes concretos e estáveis por natureza podem cair na zona de dor sem serem um problema real; é permitido declará-los como exceção, com justificativa — exceto o componente que chama o gateway e os componentes de feature.

**Decisão.** Qualquer exceção à zona de dor será listada aqui com: nome do componente, por que é estável por natureza (ex.: tipo de valor de domínio que não muda com a infraestrutura), e os valores de A/I/D observados. Esta seção começa vazia — será preenchida com base nos CSVs reais gerados na Fase 3 (v1), Fase 4 (v2) e Fase 6 (main) de [plan.md](./plan.md), nunca com números hipotéticos.

**Consequências.** Se, na `main`, algum componente de feature ou o componente que chama o gateway estiver na zona de dor, a resposta é refatorar — não adicionar exceção aqui.

**Evidência a coletar:** `metrics/results/{v1-coupled,v2-decoupled,main}.csv`.
