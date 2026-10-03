# Plano de Testes

> Derivado de [specs.md](./specs.md) (R2, R5, R6), [contract.md](./contract.md) (formatos exatos a fixar) e [plan.md](./plan.md) (fases 2 e 6). Complementa [runbook.md](./runbook.md): lá estão os comandos manuais de demonstração; aqui está o que vira **suíte automatizada**, o que cobre, e como cada caso se rastreia a um critério de aceite.

## 1. Camadas de teste

| Camada | Pasta | Quando existe | Objetivo |
|---|---|---|---|
| Caracterização | `tests/characterization/` | desde `v1-coupled` | fixar o comportamento observado (Feathers) — rede de segurança para a refatoração |
| Resiliência/gateway | `tests/resilience/` (proposto) | a partir de `v2-decoupled`/Fase 5 | provar os efeitos de R5 (fallback, timeout, retry, governança) contra o `provider-fake` real |
| Fluxos de execução | atualização de `tests/characterization/` na `main` | Fase 6 | fixar o novo contrato (streaming/assíncrono) por feature, conforme R6 |

Todas as camadas rodam **pela borda** (`localhost:8000`) ou direto no `provider-fake` (`localhost:8090/admin/*`) quando precisam provocar falha ou inspecionar `/admin/calls` — nunca contra `app:8080` direto, para refletir o caminho real do avaliador.

## 2. Testes de caracterização (R2)

### 2.1 Regras de desenho

- Fixam o **corpo** da resposta (campos e valores), não só o status HTTP.
- ≥1 caso de erro de entrada por feature (payload inválido, campo faltante, tipo errado).
- Idênticos byte-a-byte entre `v1-coupled` e `v2-decoupled` (`git diff` vazio é o critério de aceite).
- Na `main`, só mudam para as features cujo **modo de execução** mudou (R6); as que continuam síncronas (F1, F4, segundo [ADR-004](./adr.md#adr-004-modo-de-execução-por-feature)) mantêm o mesmo teste.
- Antes de cada execução da suíte: `POST /admin/reset` no `provider-fake`, para isolar o estado entre casos.

### 2.2 Matriz de casos por feature

| Feature | Caso feliz | Caso de erro de entrada | Observações de asserção |
|---|---|---|---|
| F1 Classificação | ticket válido → `category`+`priority` dentro dos domínios de [contract.md](./contract.md#domínios-de-valores-todas-as-features) | `text` ausente/vazio, `ticket_id` ausente | asserir valores exatos (determinístico no `provider-fake`), não só presença dos campos |
| F2 Sugestão de resposta | ticket válido → `suggestion` não vazia | payload sem `text` | na `v1`/`v2`: resposta síncrona completa; na `main`: ver §3 (streaming) |
| F3 Relatório de temas | período válido (`2026-08-01`–`2026-08-31`) → `total_tickets` e `topics` consistentes com `data/tickets.jsonl` | `start`/`end` ausentes, `start` > `end`, formato de data inválido | na `main`: ver §3 (assíncrono) |
| F4 Extração de dados | ticket com nº de pedido → `order_number` no formato `#` + 6 dígitos; ticket sem pedido → `order_number: null` | payload sem `text` | cobrir explicitamente o caso `null` (não é "erro", é resultado de negócio válido) |

### 2.3 Tag `v1-coupled`

- Critério de entrada: suíte escrita e **passando** contra `app/` idêntico ao repositório base.
- Nenhuma alteração em `app/` nesta tag (ver R1 em [specs.md](./specs.md) para a única exceção temporária, já revertida antes daqui).

### 2.4 Tag `v2-decoupled`

- Mesma suíte, sem edição, passando contra a app já atrás do gateway.
- Teste de guarda adicional (fora da suíte de caracterização, pode viver em `tests/resilience/`): confirmar que `app/` não importa nada de `provider-fake` e que as chamadas no `/admin/calls` aparecem com os modelos físicos escolhidos pelo gateway, não hardcoded na app.
- Teste de guarda arquitetural (pode reusar o próprio grafo de imports do script de métrica, ver R3 em [specs.md](./specs.md#r3--métrica-de-acoplamento-régua-fixa)): nenhum componente de feature importa o componente que chama o gateway; só o ponto de composição (`main.py`) depende dele.

## 3. Testes de fluxo de execução (R6, na `main`)

Escritos/atualizados só depois que o modo de cada feature for decidido (Fase 6 de [plan.md](./plan.md)). Usar os contratos de referência de [contract.md](./contract.md).

| Feature | Modo (ver ADR-004) | O que o teste precisa verificar |
|---|---|---|
| F1 | síncrono | resposta completa em até 3s; com provider primário em `timeout`, resposta (sucesso via fallback ou erro explícito) em até 15s |
| F2 | streaming (SSE) | `Content-Type: text/event-stream`; primeiro `data:` chega em até 1,5s e antes da metade do tempo total; com `midstream_error`, evento `error` chega no formato de [contract.md](./contract.md#f2--sugerir-resposta) após o `200` já enviado |
| F3 | assíncrono (Request-Reply) | `202` com `Location`+`Retry-After` em até 1s; polling retorna `pending`/`running` até `303`; relatório final tem `total_tickets = 5000` e as chamadas da tarefa `topics` aparecem em `/admin/calls`; com os dois providers em `error_500`, estado chega a `failed` com motivo em até 60s, nunca preso em `running` |
| F4 | síncrono | mesmo padrão de F1 |

Regra geral testável em qualquer um dos quatro: **nenhuma chamada, em nenhum cenário de falha do provider, produz `504` da borda.** Isso é testado batendo em `localhost:8000`, nunca direto em `app:8080`.

## 4. Testes de resiliência e governança do gateway (R5)

Propostos em `tests/resilience/` (ou equivalente), rodando contra o compose completo (`app` + `gateway` + `provider-fake` + `edge`). Cada teste segue o padrão: `POST /admin/failures` → disparar a feature pela borda → inspecionar `GET /admin/calls` → `POST /admin/reset`.

| Teste | Setup (`/admin/failures`) | Asserção |
|---|---|---|
| Fallback técnico entre providers | primário de uma capacidade em `error_500` | feature responde com sucesso; `/admin/calls` mostra tentativas no primário (≤ máx. declarado no README) seguidas de sucesso no destino equivalente do outro provider |
| Fallback com modelo fraco (por feature) | os dois `large` em `error_500` | cada feature se comporta exatamente como a tabela de fallback do README (resposta via `mini` ou erro explícito, conforme [ADR-002](./adr.md#adr-002-política-de-fallback-técnico-e-com-modelo-fraco)) |
| Timeout e não-travamento | primário em `timeout` | feature síncrona responde em ≤15s, nunca pendurada |
| Retry sem multiplicação | qualquer `error_500` transitório | nº de tentativas em `/admin/calls` bate com o nº máximo declarado no README — não o dobro (sintoma de retry configurado em mais de uma camada) |
| Retry absorve `429` do provider | primário em `error_429` | backoff absorve a falha transitória ou aciona o fallback técnico, sem distinguir de `error_500` no tratamento de retry; não é teste de equivalência a "recusa por limite" — aqui a origem é o provider, não o gateway |
| Latência alta sem travar | primário em `slow` | orçamento de latência da feature (3s/1,5s/1s, conforme [contract.md](./contract.md)) ainda é respeitado, ou o fallback/timeout entra antes do teto — não é um critério de aceite obrigatório, mas calibra os números do README antes de fechá-los |
| Recusa por orçamento | nenhum (é config do gateway, não do provider) | chamada acima do budget é recusada pelo gateway; `/admin/calls` **não** incrementa |
| Recusa por limite de requisições | nenhum | chamada acima do rate limit é recusada pelo gateway; `/admin/calls` **não** incrementa |
| Troca de modelo por config | nenhum (editar `gateway/` + `docker compose restart gateway`) | próxima chamada em `/admin/calls` mostra o novo modelo; `docker compose ps app` mostra que `app` não reiniciou |
| Isolamento de credenciais | nenhum | `grep` em `app/` e `docker compose exec app env`/`docker compose config` não mostram chaves de provider (automatizável como teste de CI, não só checagem manual) |

## 5. Testes de métrica (R3) — fora da suíte funcional

A verificação da régua de métrica não é um teste de comportamento HTTP; é a comparação de `metrics/results/<tag>.csv` com o recálculo do avaliador. Ver [specs.md](./specs.md#r3--métrica-de-acoplamento-régua-fixa) para a fórmula. Vale a pena, ainda assim, ter um teste unitário do próprio script de métrica (ex.: módulo sintético com Ca/Ce conhecidos) para garantir que `I`, `A`, `D` são calculados conforme a régua antes de rodar sobre `app/helpdesk/` de verdade.

## 6. Execução

```bash
# comando único a documentar no README — placeholder até a suíte existir
docker compose exec app pytest tests/characterization/ -v
docker compose exec app pytest tests/resilience/ -v   # se separado da suíte de caracterização
```

Pré-condição de qualquer execução: ambiente de pé (`docker compose up -d --build --wait`) e `provider-fake` resetado (`POST localhost:8090/admin/reset`).

## 7. Rastreabilidade (teste → requisito → critério de aceite)

| Suíte | Requisito ([specs.md](./specs.md)) | Critério de aceite correspondente |
|---|---|---|
| Caracterização (§2) | R2 | "A suíte fixa o corpo das respostas... passa na v1-coupled e na v2-decoupled"; `git diff v1-coupled v2-decoupled` vazio |
| Fluxos de execução (§3) | R6 | bloco "Fluxos de chamada (medidos pela borda)" |
| Resiliência/governança (§4) | R5 | bloco "Gateway" dos critérios de aceite |
| Métrica (§5) | R3 | "a medição da v1-coupled bate com a recalculada pelo avaliador" |

## 8. O que não testamos (fora de escopo, ver [specs.md](./specs.md#fora-de-escopo))

Qualidade do texto gerado, prompt injection/guardrails, cache, RAG, sobrevivência a reinício com tarefa assíncrona em andamento, cancelamento de stream ao fechar conexão do cliente, circuit breaker, deduplicação de pedidos de relatório.
