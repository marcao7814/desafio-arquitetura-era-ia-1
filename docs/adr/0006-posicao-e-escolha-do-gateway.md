# 0006. Posição e escolha do AI Gateway

- Status: aceita
- Data: 2026-10-02
- Nível: solução

## Contexto

Na `v1-coupled`, a aplicação depende de detalhes concretos e voláteis de cada provider: SDK, formato de API, nome de modelo físico, credencial. É acoplamento no sentido do requisito 3 — medido em `metrics/results/v1-coupled.csv` (`llm.py`: `Ca=4, A=0, D=0,80`, na zona de dor). O requisito 5 pede um AI Gateway self-hosted como serviço `gateway` no compose, entregando capacidades lógicas, credenciais isoladas, troca de modelo por configuração, governança e resiliência.

## Opções consideradas

1. Gateway SaaS — descartado: restrição do desafio exige que o avaliador suba tudo localmente, sem depender de serviço externo.
2. LiteLLM Proxy self-hosted (sugestão do enunciado) — implementa virtual keys, orçamento, rate limit, fallback e retry nativamente; precisa de um banco de dados para persistir chaves ([0001-banco-de-dados-do-gateway.md](0001-banco-de-dados-do-gateway.md)).
3. Gateway próprio (middleware FastAPI na frente dos SDKs, dentro de `app/`) — mais controle, mas reimplementa o que o LiteLLM já entrega, e mistura infraestrutura de IA com o código de domínio do helpdesk.

## Decisão

Opção 2. LiteLLM Proxy (`ghcr.io/berriai/litellm:v1.102.1`) como serviço `gateway` no compose, com configuração versionada em `gateway/config.yaml`. Toda chamada de `app/` a um modelo passa por ele, usando nomes lógicos de capacidade (`helpdesk-classify`, `helpdesk-suggest`, `helpdesk-topics`, `helpdesk-extract` — ver [0007-capacidades-logicas.md](0007-capacidades-logicas.md)) e uma chave do próprio gateway — nunca as chaves de `provider-fake`.

A posição é a fronteira entre `app/` e os providers: `app/` não conhece `provider-fake` (criticamente, a restrição estrutural do requisito 3 garante isso em código — só `app/helpdesk/adapters/gateway.py` fala HTTP com o gateway, e só `main.py` importa esse módulo).

## Consequências

Precisa de um banco de dados (serviço `db`) para governança persistente. O LiteLLM não conhece o preço dos modelos simulados — sem declará-lo em `gateway/config.yaml`, o custo é calculado como zero e o orçamento nunca estoura (mitigado: preços reais declarados, ver [0003-governanca-chaves.md](0003-governanca-chaves.md)). Em troca, `app/` passa a pedir uma *capacidade*, não um modelo — trocar o provider ou o modelo físico por trás de uma capacidade não exige tocar em `app/`.

## Evidência

```bash
grep -rE "gpt-fake|claude-fake" app/   # vazio
grep -rE "FAKE_OPENAI_KEY|FAKE_ANTHROPIC_KEY" app/   # vazio
docker compose exec app env   # só GATEWAY_BASE_URL e GATEWAY_API_KEY
```

`metrics/results/main.csv`: nenhum componente de feature nem `adapters.gateway` na zona de dor (ver [0005-metrica-excecoes.md](0005-metrica-excecoes.md)).
