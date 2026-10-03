# PRD — Da integração frágil à arquitetura resiliente: IA em produção num helpdesk

> Síntese de [solicitacao.md](./solicitacao.md), [contract.md](./contract.md), [specs.md](./specs.md) e [plan.md](./plan.md).

## 1. Problema

O helpdesk de uma loja online tem IA em 4 pontos do atendimento, mas integrada do jeito que "costuma nascer": cada feature chama o SDK de um provider direto do código, as chaves vivem na configuração da aplicação, tudo é síncrono e não há timeout nem retry configurados além do padrão dos SDKs.

Três meses depois, isso custa caro de forma concreta:

| Sintoma | Causa arquitetural |
|---|---|
| Relatório mensal de temas nunca termina (morre no proxy) | Chamada síncrona de longa duração sem modo de execução adequado; timeout da borda (30s) é mais curto que o tempo real do processamento |
| Atendente olha 15s para tela parada esperando a sugestão | F2 não entrega progresso incremental (sem streaming) |
| Instabilidade de 1 provider derruba parte do helpdesk | Nenhum fallback entre providers; acoplamento direto app→SDK→provider |
| Trocar modelo por um mais barato exige deploy | Nome do modelo físico está hardcoded em `app/` |

## 2. Objetivo

Levar essa aplicação, com decisões registradas e evidência medida, a um estado em que **trocar de modelo ou de provider é mudança de configuração — não um projeto**. O produto final é um fork público contendo:

1. Diagnóstico medido da v1 (prova de que as dores existem).
2. Decisões de arquitetura registradas (ADRs) e um plano de refatoração com piloto.
3. Medição de acoplamento (Main Sequence, Ca/Ce/I/A/D) das três versões: `v1-coupled`, `v2-decoupled`, `main`.
4. A aplicação evoluída atrás de um AI Gateway self-hosted, com modo de execução decidido por feature.

## 3. Fora de escopo (explícito)

Cache, RAG, observabilidade além de logs, evals de qualidade/segurança, autenticação de usuários, frontend, deploy em nuvem, sobrevivência a reinício com tarefas assíncronas em andamento, cancelamento de geração ao fechar stream, Batch API real, deduplicação de relatórios, circuit breaker. Qualidade do texto gerado e prompt engineering também não são avaliados — o provider é simulado e determinístico.

## 4. Usuários e stakeholders

| Papel | Interação | O que precisa |
|---|---|---|
| Cliente final (comprador) | Abre ticket (F1), recebe automação de troca/devolução (F4) | Classificação correta e rápida; dados extraídos sem erro |
| Atendente de helpdesk | Usa F1 (confirmação na tela) e F2 (sugestão de resposta) | Feedback em até 3s (F1) e primeiro trecho em até 1,5s (F2) |
| Painel interno / gestão | Dispara F3 (relatório de temas) | Resposta rápida ao pedido (≤1s) + resultado completo depois, sem travar o navegador |
| Automação de troca/devolução | Consome F4 sem revisão humana | Alta confiabilidade — erro em `order_number`/`product` custa frete, estoque e cliente |
| Pessoa de arquitetura (você) | Diagnostica, decide, refatora, documenta | Métrica e testes como juízes objetivos do agente de IA |
| Avaliador do desafio | Clona o fork, sobe com 1 comando, provoca falhas via `/admin/*` | Comportamento exatamente como os ADRs e o README descrevem |

## 5. Features (o que não muda — contrato de negócio)

Ver [contract.md](./contract.md) para request/response completos. Resumo:

| | Rota | Entrada→Saída | Característica de negócio | Orçamento de latência |
|---|---|---|---|---|
| F1 Classificar ticket | `POST /tickets/classification` | texto → categoria+prioridade | cliente espera confirmação na tela | ≤3s completo |
| F2 Sugerir resposta | `POST /tickets/reply-suggestion` | texto → sugestão | atendente lê/edita ao vivo | 1º trecho ≤1,5s |
| F3 Relatório de temas | `POST /reports/topics` | período → temas agregados | painel sem callback, ninguém espera olhando | aceite ≤1s, resultado depois |
| F4 Extrair dados do pedido | `POST /tickets/extraction` | texto → nº de pedido+produto | automação sem revisão humana | — |

O **modo de execução** (síncrono/streaming/assíncrono) de cada feature é uma decisão de arquitetura tomada na fase final (`main`), não parte do contrato de negócio — ver R6 em [specs.md](./specs.md).

## 6. Requisitos funcionais e não funcionais (resumo)

Detalhados em [specs.md](./specs.md). Nível PRD:

- **Diagnosticável:** toda dor do cenário precisa de comando + observação + causa no código, antes de qualquer refatoração (R1).
- **Seguro para refatorar:** suíte de caracterização fixando corpo de resposta, idêntica entre `v1-coupled` e `v2-decoupled` (R2).
- **Medível:** régua fixa de acoplamento (Ca, Ce, I, A, D) aplicada às 3 versões, com gráfico Main Sequence (R3).
- **Assistido por agente, mas verificado por humano+métrica:** plano com piloto, revisão e handoff documentado (R4).
- **Desacoplado de provider:** gateway self-hosted com capacidades lógicas, credenciais isoladas, troca de modelo só por config, governança (budget + rate limit) e resiliência (timeout, retry, fallback técnico, fallback com modelo fraco) (R5).
- **Resiliente de ponta a ponta:** nenhuma requisição termina em 504 da borda, mesmo com providers falhando (R6).
- **Decidido nos 3 níveis:** ADRs cobrindo corporativa, solução e software (R7).

## 7. Métricas de sucesso

| Métrica | Como medir | Meta |
|---|---|---|
| Latência F1 | curl pela borda | ≤3s |
| Time-to-first-byte F2 | `curl -N`, primeiro chunk | ≤1,5s e <50% do tempo total |
| Aceite F3 | tempo de resposta do `POST /reports/topics` | ≤1s |
| Resiliência a `504` | qualquer cenário de falha do provider, medido pela borda | 0 ocorrências |
| Resiliência a travamento (F1) | provider primário em `timeout` | resposta (sucesso ou erro explícito) ≤15s |
| Falha total visível (F3) | dois providers em `error_500` | estado `failed` com motivo ≤60s |
| Acoplamento | script de métrica sobre `app/helpdesk/` | nenhum componente de feature/gateway na zona de dor na `main` |
| Reprodutibilidade | script da `main` sobre checkout de `v1-coupled` | CSV idêntico ao versionado |
| Isolamento de credenciais | grep + `docker compose exec app env` + `docker compose config` | nenhuma chave de provider em `app/` ou no ambiente do serviço `app` |
| Governança efetiva | roteiro de governança do README | 1 recusa por orçamento + 1 por rate limit, sem incrementar `/admin/calls` |

## 8. Marcos e sequenciamento

Ver [plan.md](./plan.md) para o detalhe fase a fase. Resumo dos marcos git:

1. **`v1-coupled`** — app como recebida + suíte de caracterização.
2. **`v2-decoupled`** — app refatorada, já atrás do gateway (mínimo: capacidades lógicas + credencial do gateway), mesmo comportamento externo.
3. **`main`** — versão final, com modo de execução decidido por feature, governança e resiliência completas no gateway.

## 9. Restrições e premissas

- `provider-fake/`, `edge/`, `data/` são imutáveis — qualquer fricção se resolve em `app/`, `gateway/` ou `compose.yaml`.
- Stack fixa: Python 3.12 + FastAPI; a refatoração evolui o código existente, não reescreve do zero nem troca de linguagem.
- Gateway precisa ser self-hosted (sugestão: LiteLLM Proxy); SaaS não é aceito porque o avaliador sobe tudo localmente.
- O avaliador não depende de provider real nem de serviços externos além de imagens públicas do compose.
- Todo serviço extra no compose precisa de ADR justificando-o a partir de um requisito.

## 10. Entregáveis finais (checklist de alto nível)

- [ ] `README.md` com as 10 seções obrigatórias (visão geral, diagnóstico da v1, como rodar, leitura da métrica, tabela de capacidades, tabela de fallback, fluxos, troca de modelo, roteiro de governança, mapa de decisões).
- [ ] `docs/adr/` com ADRs nos 3 níveis, cobrindo gateway, capacidades, execução, fallback, governança e métrica.
- [ ] `docs/refactoring-plan.md` com piloto, medição antes/depois, revisão e handoff ao agente.
- [ ] `metrics/` com script + `results/{v1-coupled,v2-decoupled,main}.csv` e gráficos A×I.
- [ ] `app/` refatorada, só falando com o gateway, com cada feature no modo decidido.
- [ ] `gateway/` com config de capacidades, fallback, chaves, orçamentos e limites.
- [ ] `tests/characterization/` idênticos entre `v1-coupled` e `v2-decoupled`.
- [ ] Tags `v1-coupled` e `v2-decoupled` publicadas (`git push --tags`); `main` como versão final.
