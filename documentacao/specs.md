# Especificações Técnicas

> Derivado de [solicitacao.md](./solicitacao.md) — seções "Requisitos", "Tecnologias obrigatórias", "Restrições", "Fora de escopo" e "Critérios de Aceite". Complementa [contract.md](./contract.md) (o que a API expõe) com o que precisa ser verdadeiro por trás da API.

## Stack e ambiente

- Python 3.12 + FastAPI (fixo; a refatoração evolui `app/`, não a reescreve nem troca de linguagem).
- Docker + Docker Compose v2; `cp .env.example .env && docker compose up -d --build --wait` sobe tudo sem passo manual.
- Git com tags publicadas (`git push --tags`): `v1-coupled`, `v2-decoupled`.
- Um AI Gateway self-hosted como serviço `gateway` no compose (sugestão: LiteLLM Proxy). Gateways SaaS não são aceitos.
- `provider-fake/`, `edge/`, `data/` são imutáveis.
- Ferramenta de testes e de medição de métrica: livre escolha.

## R1 — Diagnóstico da aplicação recebida

**Objetivo:** transformar as 4 dores do cenário em fatos observáveis antes de qualquer refatoração.

- Reproduzir, com evidência (comando + observação + causa no código):
  1. relatório do mês não termina (timeout da borda);
  2. sugestão de resposta deixa o atendente sem feedback visual;
  3. provider fora do ar/travado derruba parte do helpdesk;
  4. troca de modelo exige mudança de código + rebuild.
- `app/` não é alterado nesta etapa, exceto temporariamente para demonstrar a dor #4 (revertido antes da tag `v1-coupled`).
- Registro vive na seção "Diagnóstico da v1" do README final.

## R2 — Testes de caracterização

**Objetivo:** rede de segurança que separa refatoração (muda estrutura) de reescrita (muda comportamento).

- Local: `tests/characterization/`.
- Cobertura: as 4 features via HTTP, fixando o **corpo** das respostas (não só status), com ao menos 1 caso de erro de entrada por feature.
- Executável com um único comando documentado no README, contra a app no compose.
- Idêntica (`git diff` vazio) entre as tags `v1-coupled` e `v2-decoupled`; pode evoluir na `main` para o novo contrato de execução (R6).
- Tag `v1-coupled`: aplicada quando a suíte passa contra a app recebida, com `app/` idêntico ao repositório base.

## R3 — Métrica de acoplamento (régua fixa)

**Objetivo:** substituir "está acoplado" por número, via Main Sequence (A × I).

- Script em `metrics/`, parametrizado pelo caminho de `app/helpdesk/` de qualquer checkout.
- Saída: `metrics/results/<name>.csv` com cabeçalho exato `component,ca,ce,i,a,d`, mais gráfico A × I com a Main Sequence.
- **Definições (fixas, não negociáveis):**
  - Componente: cada módulo `.py` de `app/helpdesk/` (incl. subpastas), path com pontos (ex. `adapters.gateway`), exceto `__init__.py`.
  - Dependência: import (relativo ou absoluto) que resolve para outro componente; stdlib e libs externas não contam.
  - `Ca` = nº de componentes que importam este; `Ce` = nº que este importa.
  - `I = Ce / (Ce + Ca)`, ou `0` se ambos zero.
  - `A` = nº de classes abstratas (`typing.Protocol` ou `abc.ABC`) / total de classes do módulo, ou `0` sem classes.
  - `D = |A + I - 1|`.
  - Arredondamento: 2 casas decimais.
- Exceções à zona de dor (`A<0.5 ∧ I<0.5 ∧ D≥0.5`) só são aceitas se declaradas no ADR da métrica como "estáveis por natureza" com justificativa — **nunca** para o componente que chama o gateway nem para componentes de feature.
- `metrics/results/v1-coupled.csv` + gráfico versionados; o script é escrito depois da tag e roda sobre um checkout dela (`git worktree`).
- **Restrição estrutural (válida a partir da `main`):** o código que chama o gateway (SDK ou cliente HTTP) fica em **um único componente** de `app/`, identificado no README. Nenhum componente de feature pode importá-lo — só o ponto de composição da aplicação (onde os componentes são montados, ex. `main.py`) pode depender dele.

## R4 — Plano, piloto e refatoração assistida por agente (tag `v2-decoupled`)

**Objetivo:** usar testes (R2) + métrica (R3) como juízes determinísticos de um agente não determinístico.

- `docs/refactoring-plan.md` com componentes-alvo, estratégia por componente (↑A, ↓Ca, inversão de dependência, composição > herança) e critério de pronto baseado na métrica.
- Piloto obrigatório em 1 componente antes de escalar, com medição antes/depois registrada no plano.
- Pelo menos 1 revisão do plano registrada (o que mudou e por quê, à luz do piloto/medição).
- Registro do handoff ao agente: o que foi entregue a ele, como testes+métrica aceitaram/rejeitaram o produzido.
- Nesta tag, gateway já na frente dos providers: app chama só por nomes lógicos + chave do gateway, sem chaves de provider. Governança/resiliência/fallback podem vir depois.
- Comportamento externo inalterado: mesmas rotas/modos, suíte de R2 passando sem edição; manter um modelo `large` por capacidade (os `mini` mudam saídas que a suíte fixou).
- Medir com o mesmo script → `metrics/results/v2-decoupled.csv` + gráfico. Tag `v2-decoupled`.

## R5 — AI Gateway

**Objetivo:** inversão de dependência aplicada à IA — app pede capacidade, infra decide o modelo físico.

Serviço `gateway` no compose, config versionada em `gateway/`, entregando:

- **Capacidades lógicas:** nenhum nome físico (`gpt-fake-*`, `claude-fake-*`) aparece em `app/`.
- **Credenciais fora da app:** chaves de provider só no gateway; app usa virtual key (ou equivalente) do próprio gateway.
- **Troca de modelo por config:** alterar só `gateway/` + reiniciar só `gateway`; `app` não é reconstruída/reiniciada.
- **Governança mínima:** ≥1 chave com budget, ≥1 com limite de requisições; requisição fora do limite é recusada **antes** de chegar ao provider.
- **Resiliência:** timeout explícito, retry limitado com backoff, fallback técnico para destino equivalente em outro provider — para toda capacidade. Nº máximo de tentativas por destino declarado no README.
- **Fallback com modelo fraco:** decisão por feature (responder com `mini` vs. falhar explicitamente), registrada no ADR com evidência.

Cada mecanismo pode morar no gateway ou na app, desde que o efeito observável exista e o ADR diga onde.

**Pistas operacionais:** chaves virtuais/budget tipicamente exigem DB e criação sem passo manual; se o gateway não conhece o preço dos modelos simulados, custo pode ser calculado como zero (budget nunca estoura) — usar os preços do README do `provider-fake`; retries configurados em mais de um lugar (SDK + gateway + app) se multiplicam — visível em `/admin/calls`.

## R6 — Modo de execução por feature (`main`)

**Objetivo:** síncrono/streaming/assíncrono é decisão arquitetural por caso de uso, não padrão único.

- ADR único de execução, uma seção por feature, cada uma respondendo à árvore de decisão: "alguém está esperando agora?", "cabe no orçamento de latência?", "é consumível aos poucos?".
- Requisitos de experiência (medidos pela borda, provider em modo normal salvo indicação contrária) — ver [contract.md](./contract.md) para os valores exatos por feature.
- Nenhuma requisição termina em `504`, inclusive em cenários de falha do provider.
- Streaming: `Content-Type: text/event-stream`; erro no meio chega como evento `error` (status já enviado).
- Assíncrono: `202` + `Location`/`Retry-After`; status `pending`/`running`/`failed` (com motivo); `303` ao concluir; `failed` em até 60s, nunca preso em `running`.
- Toda feature síncrona tem timeout explícito; nunca pendurada — sucesso (via fallback) ou erro explícito em até 15s.
- Testes de R2 atualizados/complementados na `main` para o novo contrato; a suíte das tags continua registrando o comportamento antigo.
- Medir com o mesmo script → `metrics/results/main.csv` + gráfico.

## R7 — Decisões nos três níveis (ADR)

**Objetivo:** localizar cada decisão de IA no nível certo (corporativa / solução / software) define quem decide e por quanto tempo vale.

- `docs/adr/`, 1 arquivo por decisão, com `Nível: corporativa|solução|software`.
- Cobertura mínima: posição/escolha do gateway; capacidades lógicas → modelos físicos; modo de execução (ADR único, 1 seção/feature); política de fallback técnico + modelo fraco (pode ser ADR único, 1 seção/feature); governança de chaves/orçamentos/limites; leitura da métrica com exceções declaradas.
- Pelo menos 1 decisão em cada nível.

## Restrições não negociáveis

- `provider-fake/`, `edge/`, `data/` imutáveis; fricções resolvidas em `app/`, `gateway/` ou `compose.yaml`.
- Em `v2-decoupled` e `main`: toda chamada a modelo passa pelo gateway; `app/` nunca chama `provider-fake` direto (testes podem usar `/admin`).
- Em `v2-decoupled` e `main`: `FAKE_OPENAI_KEY`/`FAKE_ANTHROPIC_KEY` não aparecem em `app/` nem no ambiente do serviço `app`.
- Régua da métrica é sempre a do R3, nas três medições.
- Avaliador não depende de provider real nem de serviço externo além de imagens públicas do compose.
- Todo serviço extra no compose (fila, banco, worker) precisa de ADR justificando-o a partir de um requisito.
- Limitação real da ferramenta de gateway: documentar no ADR e resolver na app, não abandonar o efeito exigido.

## Fora de escopo

Cache, RAG, observabilidade além de logs, evals de qualidade/segurança (prompt injection, guardrails), autenticação de usuários do helpdesk, frontend, deploy em nuvem, sobrevivência a reinício com tarefas assíncronas em andamento, cancelamento de geração no provider ao fechar stream, Batch API real, deduplicação de pedidos de relatório, circuit breaker.

## Critérios de aceite (resumo verificável)

Ver [solicitacao.md](./solicitacao.md#critérios-de-aceite) para a lista completa; destaques executáveis:

- `grep -rE "gpt-fake|claude-fake" app/` → vazio na `main`.
- `grep -rE "FAKE_OPENAI_KEY|FAKE_ANTHROPIC_KEY|sk-fake-openai|sk-ant-fake" app/` → vazio; `docker compose exec app env` sem chaves de provider; `docker compose config` não injeta essas chaves no serviço `app`.
- Troca de modelo físico: só `gateway/` + restart de `gateway`; próxima chamada em `/admin/calls` mostra o novo modelo; `app` não reinicia.
- Roteiro de governança: 1 recusa por orçamento + 1 por limite de requisições, sem incrementar `/admin/calls`.
- Provider primário de uma capacidade em `error_500` → sucesso via fallback técnico, com nº de tentativas ≤ o declarado no README.
- Dois `large` em `error_500` → cada feature se comporta exatamente como a tabela de fallback do README.
- `git diff v1-coupled v2-decoupled -- tests/characterization/` → vazio.
- Rodar o script de métrica da `main` sobre checkout de `v1-coupled` reproduz o CSV versionado daquela tag.
- Na `main`, o código que chama o gateway fica em um único componente de `app/`, identificado no README; nenhum componente de feature o importa — só o ponto de composição (ex. `main.py`) pode depender dele.
- O relatório da F3 tem `total_tickets = 5000` e as chamadas da tarefa `topics` que o produziram aparecem registradas em `/admin/calls`.
