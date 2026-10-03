# Plano de Refatoração — v1-coupled → v2-decoupled

> Ver [documentacao/specs.md](../documentacao/specs.md) (R3, R4, R5) para a régua da métrica e os critérios de aceite. Medição de partida: [metrics/results/v1-coupled.csv](../metrics/results/v1-coupled.csv).

## Ponto de partida (medição da v1-coupled)

| Componente | Ca | Ce | I | A | D | Zona de dor |
|---|---|---|---|---|---|---|
| `main` | 0 | 5 | 1,00 | 0,00 | 0,00 | não |
| `report` | 1 | 4 | 0,80 | 0,00 | 0,20 | não |
| `classification` / `extraction` / `suggestion` | 1 | 3 | 0,75 | 0,00 | 0,25 | não |
| `tickets` | 1 | 1 | 0,50 | 0,00 | 0,50 | não (limite) |
| `llm` | 4 | 1 | 0,20 | 0,00 | **0,80** | **sim** |
| `config` | 6 | 0 | 0,00 | 0,00 | **1,00** | **sim** |
| `schemas` | 5 | 0 | 0,00 | 0,00 | **1,00** | **sim** |

## Componentes-alvo e estratégia

### 1. `llm.py` — alvo prioritário

**Por que é alvo:** concentra as chamadas diretas aos SDKs `openai` e `anthropic`, é importado por todas as 4 features (`Ca=4`) e não tem nenhuma abstração (`A=0`). É também, segundo [documentacao/adr.md (ADR-003)](../documentacao/adr.md#adr-003-capacidades-lógicas-e-mapeamento-para-modelos-físicos), o componente que concentra a chamada ao provider — o que a régua da métrica proíbe de virar exceção.

**Estratégia:** inversão de dependência (Protocol) + isolamento em um único componente:
- `ports.py` (novo): define `CompletionGateway`, um `typing.Protocol` com um único método (`complete(capability, task, content) -> str`). É a abstração que as features passam a depender.
- `adapters/gateway.py` (novo): única implementação concreta de `CompletionGateway`. Fala HTTP com o AI Gateway (LiteLLM), usando nomes lógicos de capacidade e a chave do próprio gateway — nunca o `provider-fake` diretamente, nunca chaves de provider. É o único componente de `app/` que conhece o gateway; nenhuma feature pode importá-lo (restrição de specs.md R3) — só `main.py` o importa, para construir a instância e injetá-la nas features.
- Features (`classification.py`, `suggestion.py`, `extraction.py`, `report.py`) passam a receber um `CompletionGateway` por parâmetro em vez de importar `llm` no topo do módulo.

**Critério de pronto:** `adapters.gateway` fora da zona de dor (ou, se continuar lá por ser um adapter de borda com `A` baixo por natureza, isso precisa estar justificado — mas a régua proíbe exceção aqui, então a meta real é tirar `Ca` dele: só `main` pode depender dele). `ports` deve ter `A=1,00` (é só o Protocol). Nenhuma feature importa `adapters.gateway`.

### 2. `config.py`

**Por que está na lista:** `Ca=6` (quase tudo depende dele), `D=1,00`. Hoje mistura 3 responsabilidades: credenciais de provider, URLs físicas dos providers, e nomes de modelo físico por feature.

**Estratégia:** não é refatoração estrutural (não vamos quebrar `config.py` em vários módulos só para mexer na métrica — ver a dica final de [documentacao/plan.md](../documentacao/plan.md) sobre não desenhar código em função da fórmula). A mudança é de **conteúdo**: sai tudo que passa a ser responsabilidade do gateway (chaves de provider, URLs físicas, nomes de modelo físico); entra só o que a app precisa saber para falar com o gateway (URL do gateway, chave do gateway, nomes lógicos de capacidade por feature).

**Critério de pronto:** nenhuma chave de provider, URL de provider ou nome de modelo físico em `config.py`. Se `config.py` continuar na zona de dor mesmo assim (é plausível — configuração tende a ser muito referenciada por natureza), a decisão de declará-lo exceção é tomada no ADR da métrica, à luz da medição da `main` — não antecipada aqui.

### 3. `schemas.py`

**Por que está na lista:** `Ca=5`, `D=1,00`, mas são só tipos de valor (modelos Pydantic de entrada/saída).

**Estratégia:** nenhuma — é o candidato mais claro a "estável por natureza" (exemplo literal dado em specs.md R3: "tipos de valor do domínio"). Não entra no piloto nem na refatoração ativa.

## Critério de pronto geral (da refatoração como um todo)

- Nenhum componente de feature, nem o componente que fala com o gateway, está na zona de dor (`A<0,5 ∧ I<0,5 ∧ D≥0,5`) na medição da `v2-decoupled`.
- O código que fala com o gateway vive em um único componente de `app/`, e nenhuma feature o importa — só `main.py`.
- `grep -rE "gpt-fake|claude-fake" app/` vazio; nenhuma chave de provider em `app/` nem no ambiente do serviço `app`.
- `tests/characterization/` passa sem nenhuma alteração (mesmo comportamento externo).
- Cada capacidade continua atendida por um modelo `large` (as saídas que a suíte fixou não podem mudar).

## Piloto

**Escopo do piloto:** só `llm.py` → `ports.py` + `adapters/gateway.py`, e só a feature `classification.py` migrada para o novo padrão (recebe `CompletionGateway` por parâmetro). As outras 3 features ficam temporariamente chamando a nova estrutura via um shim, só para o piloto validar a abordagem antes de escalar.

**Medição antes do piloto:** ver tabela "Ponto de partida" acima (`llm`: Ca=4, Ce=1, I=0,20, A=0,00, D=0,80).

**Medição depois do piloto** (`llm.py` ainda existe, só `classification` migrou):

| Componente | Ca | Ce | I | A | D | Zona de dor |
|---|---|---|---|---|---|---|
| `ports` (novo) | 1 | 0 | 0,00 | **1,00** | **0,00** | não |
| `adapters.gateway` (novo) | 1 | 0 | 0,00 | 0,00 | 1,00 | **sim** |
| `classification` | 1 | 3 | 0,75 | 0,00 | 0,25 | não (igual à v1) |
| `llm` (legado, em extinção) | 3 | 1 | 0,25 | 0,00 | 0,75 | sim (esperado — será removido) |
| `config` | 7 | 0 | 0,00 | 0,00 | 1,00 | sim (inalterado em natureza) |
| `main` | 0 | 7 | 1,00 | 0,00 | 0,00 | não |

**Validação funcional do piloto:** `curl -X POST localhost:8000/tickets/classification` pela borda devolveu exatamente `{"ticket_id":"TK-00042","category":"delivery","priority":"high"}`, idêntico à suíte de caracterização; `GET /admin/calls` no `provider-fake` confirmou a chamada chegando como `provider: openai, model: gpt-fake-large`, originada do gateway. A suíte completa (`pytest tests/characterization -v`) passou — 10/10 — sem nenhuma alteração nos testes.

## Revisão do plano

**O que o piloto mostrou que o plano original não previu:** `ports` ficou exatamente onde deveria (abstração estável, `A=1,00`, fora da zona de dor) — mas `adapters.gateway`, o componente que a régua proíbe de virar exceção, **permaneceu na zona de dor** mesmo sendo o único ponto de acoplamento (`Ca=1`, só `main` o importa). A causa é estrutural na própria fórmula: qualquer componente-folha com `Ce=0` tem `I=0` *independente* do valor de `Ca` — reduzir ainda mais quem depende dele (já está no mínimo possível, 1) não resolve.

**Por que isso não é um sinal para abrir exceção:** adicionar uma classe abstrata artificial dentro do próprio `adapters/gateway.py` só para inflar `A` seria exatamente o anti-padrão que [documentacao/plan.md](../documentacao/plan.md#riscos-e-fricções-a-vigiar-não-re-resolver-às-cegas) alerta ("não desenhe o código em função da fórmula"). A leitura correta é: este componente hoje é um adapter deliberadamente burro (só monta a request HTTP), e isso é cedo demais no plano — a Fase 5 (resiliência: timeout, retry com backoff, fallback técnico) vai decompor essa lógica em colaboradores internos de verdade (ex.: um módulo de política de retry, um mapeador de erros do gateway para exceções da aplicação). Isso eleva `Ce` organicamente, o que é a forma legítima de tirar `adapters.gateway` da zona de dor.

**Mudança no plano:** o critério de pronto geral já previa "nenhum componente de feature, nem o componente que fala com o gateway, está na zona de dor" — mantido, mas a *verificação* desse critério específico fica adiada para depois da Fase 5 (resiliência), não para o fim da Fase 4 (`v2-decoupled`). Isso é consistente com specs.md R3, cujo critério de aceite rígido ("não podem ser exceção") é escopado à tag `main`, não à `v2-decoupled`. Registrado aqui para não esquecer de revisitar na Fase 5.

## Handoff para o agente de IA

**Agente:** Claude Code (Sonnet 5), nesta mesma sessão interativa — não um agente externo separado; o "handoff" é o brief abaixo, aceito ou rejeitado pelos mesmos juízes que valeriam para qualquer agente.

**O que foi entregue como brief:** a medição da `v1-coupled` (`metrics/results/v1-coupled.csv`), a suíte de caracterização já fixada (`tests/characterization/`), a régua da métrica (specs.md R3) e a decisão de arquitetura já tomada no ADR (ports & adapters, componente único de gateway — adr.md ADR-003). Não foi pedido "refatore `llm.py`" de forma aberta; foi pedido especificamente o padrão Protocol + adapter único + injeção pelo composition root, com o piloto restrito a 1 componente antes de escalar.

**Como o resultado foi aceito/rejeitado:** a cada mudança, dois juízes determinísticos, nesta ordem — (1) `pytest tests/characterization -v` teria que continuar 10/10 sem edição nos testes (comportamento externo intacto); (2) `metrics/measure.py` teria que mostrar o componente novo (`adapters.gateway`) com `Ca` mínimo (só `main`) e `ports` fora da zona de dor. O piloto só foi considerado aceito depois que os dois juízes passaram E a chamada real foi confirmada no `/admin/calls` do `provider-fake` (prova de que não é só "os testes passam por acidente", mas que a chamada física realmente saiu pelo gateway). Nenhuma saída do agente foi aceita só por "parecer razoável" — a validação é sempre contra o efeito observável, nunca contra a leitura do código.
