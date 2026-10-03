# 0005. Leitura da métrica de acoplamento na main e exceções declaradas

- Status: aceita
- Data: 2026-10-02
- Nível: software

## Contexto

A régua fixa do requisito 3 (ver [documentacao/specs.md](../../documentacao/specs.md#r3--métrica-de-acoplamento-régua-fixa)) classifica um componente na "zona de dor" quando `A<0,5 ∧ I<0,5 ∧ D≥0,5` — concreto (`A` baixo) e muito dependido (`I` baixo porque `Ca` domina). Componentes de valor/configuração puros tendem a cair nessa zona mecanicamente, sem que isso seja um problema real de design. A régua permite declará-los exceção, **exceto** o componente que chama o gateway e os componentes de feature.

Na medição da `v2-decoupled` ([metrics/results/v2-decoupled.csv](../../metrics/results/v2-decoupled.csv)), `adapters.gateway` estava na zona de dor (`Ca=1, Ce=0, I=0,00, A=0,00, D=1,00`) — e, por ser o componente que chama o gateway, não podia virar exceção.

## Opções consideradas

Para `adapters.gateway`:
1. Declará-lo exceção mesmo assim — descartado, a régua proíbe explicitamente.
2. Adicionar uma classe abstrata artificial dentro do próprio módulo só para inflar `A` — descartado, é o anti-padrão que [documentacao/plan.md](../../documentacao/plan.md#riscos-e-fricções-a-vigiar-não-re-resolver-às-cegas) alerta ("não desenhe o código em função da fórmula").
3. Fazer `adapters.gateway` depender de `config` para sua própria configuração (URL/chave do gateway, `max_tokens`), em vez de recebê-la via parâmetros do composition root — eleva `Ce` de 0 para 1 organicamente, como já é o padrão em `classification.py`, `suggestion.py`, `extraction.py` e `report.py`.

Para `config.py` e `schemas.py`:
1. Refatorar para reduzir `Ca` artificialmente (quebrar em módulos menores só para a métrica) — descartado, mesmo anti-padrão.
2. Declarar exceção, com justificativa — permitido pela régua para componentes que não são feature nem o chamador do gateway.

## Decisão

- **`adapters.gateway`:** opção 3. `LiteLLMGateway.__init__()` agora lê `config.GATEWAY_BASE_URL`, `config.GATEWAY_API_KEY` e `config.MAX_OUTPUT_TOKENS` diretamente, em vez de recebê-los como argumentos de `main.py`. Isso tira o componente da zona de dor sem alterar seu comportamento externo (mesma suíte de caracterização, sem edição, continua passando).
- **`config.py` e `schemas.py`:** declarados exceção. São módulos de tipos de valor (modelos Pydantic) e configuração (constantes, nomes de capacidade), sem lógica de negócio, que não mudam quando a arquitetura muda por baixo deles — exatamente o exemplo que specs.md usa para justificar a exceção ("tipos de valor do domínio").

## Consequências

Na `main`, nenhum componente de feature nem o componente que chama o gateway está na zona de dor. As duas únicas exceções (`config`, `schemas`) são módulos sem comportamento — a métrica não está escondendo um problema real de acoplamento atrás delas.

## Evidência

```bash
python metrics/measure.py app/helpdesk --out metrics/results/main.csv
cat metrics/results/main.csv
```

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
