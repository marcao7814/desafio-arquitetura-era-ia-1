# Plano de Execução

> Derivado de [solicitacao.md](./solicitacao.md) — seção "Ordem de execução sugerida", cruzado com os marcos do git exigidos em "Entregável". Consulte [specs.md](./specs.md) para o detalhe de cada requisito e [contract.md](./contract.md) para os limites de tempo/formatos por feature.

## Visão das fases e marcos

| Fase | Entregável de código | Tag/branch git |
|---|---|---|
| 0. Reconhecimento | — | — |
| 1. Diagnóstico da v1 | seção "Diagnóstico da v1" do README | — |
| 2. Caracterização | `tests/characterization/` | `v1-coupled` |
| 3. Métrica inicial | `metrics/results/v1-coupled.csv` + gráfico | (sobre `v1-coupled`) |
| 4. Plano + piloto + refatoração com agente | `docs/refactoring-plan.md`, app atrás do gateway | `v2-decoupled` |
| 5. Governança + resiliência no gateway | `gateway/` | (sobre `v2-decoupled`) |
| 6. Modo de execução por feature | contrato final das rotas | `main` |
| 7. ADRs e README final | `docs/adr/`, `README.md` | `main` |
| 8. Verificação final (clone limpo) | — | `main` |

## Estrutura final esperada do repositório

Conforme "Estrutura obrigatória do entregável" em [solicitacao.md](./solicitacao.md#estrutura-obrigatória-do-entregável); cada fase acima só está completa quando a peça correspondente existir no lugar certo:

```
.
├── README.md                      (substituído — Fase 7)
├── compose.yaml                   (estendido — Fases 4–6)
├── .env.example                   (estendido — Fases 4–6)
├── provider-fake/                 (não alterar)
├── edge/                          (não alterar)
├── data/
│   └── tickets.jsonl              (não alterar)
├── app/                           (evoluído — Fases 1, 4, 6)
├── gateway/                       (criado — Fases 4–5)
├── tests/
│   └── characterization/          (criado — Fase 2, atualizado na Fase 6)
├── metrics/                       (criado — Fase 3)
│   └── results/                   v1-coupled (Fase 3), v2-decoupled (Fase 4), main (Fase 6)
└── docs/
    ├── refactoring-plan.md        (criado — Fase 4)
    └── adr/                       (criado — Fase 7, alimentado por adr.md)
```

## Fase 0 — Reconhecimento

- Subir o ambiente (`cp .env.example .env && docker compose up -d --build --wait`).
- Ler `provider-fake/README.md`, o código de `app/` e `edge/nginx.conf`.
- Chamar as quatro tarefas (`classify`, `suggest`, `topics`, `extract`) nos modelos `large` e `mini` direto no provider, para já ter intuição da diferença de qualidade (fricção proposital "o modelo barato não é tão bom").

**Saída:** entendimento do código herdado e da diferença `large` vs `mini` por tarefa.

## Fase 1 — Diagnóstico da v1 (R1)

- Reproduzir as 4 dores do cenário usando os modos de falha do `provider-fake` (`/admin/failures`) quando necessário.
- Para cada dor: comando executado, observação (status, tempo, `/admin/calls`), trecho de `app/` onde está a causa.
- `app/` não é alterado, exceto temporariamente para demonstrar a dor da troca de modelo (revertida antes do próximo passo).

**Saída:** conteúdo pronto para a seção "Diagnóstico da v1" do README.
**Depende de:** Fase 0.

## Fase 2 — Testes de caracterização + tag `v1-coupled` (R2)

- Escrever `tests/characterization/` cobrindo as 4 features via HTTP, fixando corpo da resposta + 1 caso de erro de entrada por feature.
- Documentar o comando único de execução da suíte no README.
- Confirmar que a suíte passa contra `app/` idêntico ao repositório base.
- `git tag v1-coupled` + `git push --tags`.

**Saída:** rede de segurança para a refatoração.
**Depende de:** Fase 1 (app/ já revertido ao estado original).
**Bloqueia:** toda refatoração subsequente (R4 em diante).

## Fase 3 — Métrica inicial (R3)

- Escrever o script em `metrics/` segundo a régua fixa (Ca, Ce, I, A, D).
- Medir sobre um checkout de `v1-coupled` (ex.: `git worktree add ../v1 v1-coupled`), já que o script nasce depois da tag.
- Versionar `metrics/results/v1-coupled.csv` + gráfico A×I.

**Saída:** baseline numérico de acoplamento.
**Depende de:** Fase 2 (tag precisa existir para medir sobre ela).

## Fase 4 — Plano, piloto e refatoração com agente → tag `v2-decoupled` (R4 + metade do R5)

- Escrever `docs/refactoring-plan.md`: componentes-alvo, estratégia por componente, critério de pronto.
- Executar piloto em 1 componente; medir antes/depois; registrar no plano.
- Revisar o plano com base no piloto (pelo menos 1 revisão justificada).
- Escalar a refatoração com um agente de IA, usando testes (Fase 2) + métrica (Fase 3) como juízes; registrar o handoff no plano.
- Colocar o gateway na frente dos providers: app só fala por nomes lógicos + chave do próprio gateway. Governança/resiliência completas podem ficar para a Fase 5.
- Confirmar que o comportamento externo não mudou (suíte de caracterização passando sem edição) e que cada capacidade ainda usa um modelo `large` equivalente.
- Medir novamente → `metrics/results/v2-decoupled.csv` + gráfico.
- `git tag v2-decoupled` + `git push --tags`.

**Saída:** app desacoplada do provider, atrás do gateway, com o mesmo contrato externo.
**Depende de:** Fase 2 (testes) e Fase 3 (métrica como critério de pronto).
**Bloqueia:** Fase 5 em diante (restrição: toda chamada a modelo passa pelo gateway a partir daqui).

## Fase 5 — Governança e resiliência no gateway (resto do R5)

- Configurar no `gateway/`: capacidades lógicas, credenciais isoladas, troca de modelo só por config, ≥1 chave com budget, ≥1 com rate limit, timeout/retry/backoff, fallback técnico entre providers, fallback com modelo fraco (decisão por feature).
- Testar cada modo de falha do `provider-fake` (`error_500`, `error_429`, `timeout`, `slow`, `midstream_error`) e confirmar o efeito via `/admin/calls`.
- Decidir, por feature, a política de modelo fraco com evidência real (comparar saídas `large` vs `mini` por tarefa).

**Saída:** gateway cumprindo os 5 pilares do R5 (capacidades, credenciais, troca por config, governança, resiliência+fallback).
**Depende de:** Fase 4 (gateway já posicionado).

## Fase 6 — Modo de execução por feature → `main` (R6)

- Para cada feature, decidir síncrono/streaming/assíncrono a partir da árvore de decisão do contrato (ver [contract.md](./contract.md)).
- Implementar o modo escolhido respeitando os orçamentos de latência e os formatos de contrato.
- Atualizar/complementar os testes de caracterização na `main` para o novo contrato (a suíte das tags permanece intacta como registro histórico).
- Medir → `metrics/results/main.csv` + gráfico.

**Saída:** contrato final de cada feature, validado contra os requisitos de experiência.
**Depende de:** Fase 5 (resiliência do gateway já no lugar, para os testes de timeout/fallback funcionarem de ponta a ponta).

## Fase 7 — ADRs e README final (R7)

- Escrever `docs/adr/` (1 arquivo por decisão, com `Nível:`), cobrindo no mínimo: gateway, capacidades→modelos, execução (1 ADR, 1 seção/feature), fallback técnico+modelo fraco, governança, leitura da métrica.
- Garantir ≥1 ADR por nível (corporativa, solução, software).
- Escrever o `README.md` final com todas as seções obrigatórias (ver [prd.md](./prd.md) e a seção "Entregável" de solicitacao.md).
- Regra de consistência: se um ADR descreve algo não demonstrável via `/admin/calls` ou pela borda, ADR ou código estão errados — corrigir o que estiver errado.

**Saída:** documentação final alinhada ao código.
**Depende de:** Fases 1–6 (todo o conteúdo factual já existe).

## Fase 8 — Verificação final

- Clone limpo do fork.
- Subir o ambiente seguindo só o README.
- Percorrer os Critérios de Aceite item a item (ver [specs.md](./specs.md#critérios-de-aceite-resumo-verificável)).

**Saída:** confirmação de que a entrega é reproduzível e passa nos critérios.
**Depende de:** Fase 7.

## Riscos e fricções a vigiar (não re-resolver às cegas)

- Timeout da borda (30s) é o mais curto da cadeia — qualquer SLA interno tem que respeitar esse teto, não o padrão do SDK.
- Cancelar = parar de responder ao cliente, não parar de pagar tokens — conferir se o provider continua sendo chamado após um `504`.
- Retries em mais de uma camada (SDK + gateway + app) se multiplicam — manter UMA camada responsável por retry.
- Modelo `mini` não é fallback neutro — decisão de produto, não de infra; precisa de evidência comparando saídas antes de ligar.
- `/admin/calls` é a fonte da verdade — qualquer afirmação sobre fallback, retry, troca de modelo ou orçamento no README/ADR precisa ser conferível ali; se o registro mostra 1 chamada ao primário quando o ADR descreve fallback, é o código ou o ADR que estão errados, não o registro.
- A régua da métrica é fixa para ser comparável entre todos — se o script der, para a `v1`, números diferentes dos calculados à mão para 2–3 módulos, o erro está no script, não na régua. E não desenhar `app/` em função da fórmula (ex.: um import só para tirar um módulo da zona de dor) — a métrica aponta onde olhar, o ADR explica por que a estrutura ficou melhor.
- Streaming só funciona se nada no caminho acumular a resposta — framework, middleware de compressão, gateway e proxy podem bufferizar e entregar tudo de uma vez no fim. Se `curl -N` pela borda mostrar o texto chegando em bloco, o buffer está em algum ponto da própria cadeia (app → gateway → edge), não no provider.
- Streaming e assíncrono resolvem problemas diferentes, não são intercambiáveis: streaming muda a espera percebida mas mantém a conexão aberta; assíncrono libera a conexão mas cobra estado e mais peças a operar. Se uma escolha resolve o requisito de experiência "por acidente" (ex.: usar assíncrono em F2 só porque resolve o timeout, ignorando que o atendente quer ver o texto chegando), o ADR de execução (R6) deve deixar isso evidente, não escondido.
