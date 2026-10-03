# 0001. Adicionar Postgres como armazenamento de chaves virtuais do gateway

- Status: aceita
- Data: 2026-10-02
- Nível: software

## Contexto

O requisito 5 (ver [documentacao/specs.md](../../documentacao/specs.md#r5--ai-gateway)) exige governança mínima no AI Gateway: pelo menos uma chave com orçamento (budget) e uma com limite de requisições, com persistência do estado de consumo entre chamadas (e, idealmente, entre reinícios do container). O `provider-fake/README.md` já adianta isso: "gateways que oferecem chaves virtuais e orçamento costumam precisar de um banco de dados". O LiteLLM Proxy, escolhido em [documentacao/adr.md (ADR-001)](../../documentacao/adr.md#adr-001-posição-e-escolha-do-ai-gateway), guarda chaves virtuais, orçamento consumido e contadores de rate limit em memória por padrão — o que reinicia a zero a cada restart do container e não é adequado para demonstrar consumo acumulado de forma confiável.

A restrição do desafio (ver [documentacao/specs.md](../../documentacao/specs.md#restrições-não-negociáveis)) exige que todo serviço adicionado ao compose além de `app` e `gateway` tenha um ADR justificando-o a partir de um requisito — este é esse ADR.

## Opções consideradas

1. Manter o LiteLLM sem banco (chaves/orçamento só em memória, via `config.yaml` estático).
2. Adicionar um serviço `db` (Postgres) ao compose, usado exclusivamente pelo `gateway` para persistir chaves virtuais, orçamento e limites.
3. Implementar orçamento/limite de requisições na própria aplicação (`app/`), fora do gateway.

## Decisão

Opção 2. Um serviço `db` (`postgres:16-alpine`) é adicionado ao compose, usado só pelo `gateway` (`DATABASE_URL` aponta para ele em `general_settings` do LiteLLM). Chaves virtuais passam a ser criadas via a API de administração do próprio LiteLLM (`POST /key/generate`), não editadas à mão no `config.yaml` — isso também atende à pista do `provider-fake/README.md` de que "as chaves precisam ser criadas sem passo manual": a criação é feita por um script versionado (ver `gateway/`), não por clique em painel.

A opção 1 foi descartada porque não sobrevive a um restart do `gateway` (o requisito pede orçamento e limite como mecanismos reais, não demonstráveis só enquanto o processo não reinicia). A opção 3 foi descartada porque moveria governança de volta para a aplicação — exatamente o acoplamento que o gateway existe para eliminar (ver ADR-001).

## Consequências

Mais uma peça para operar: o `gateway` passa a depender de `db` estar saudável antes de subir (`depends_on: db: condition: service_healthy`). Em compensação, orçamento e limite de requisições sobrevivem a reinícios do `gateway`, e a criação de chaves fica auditável e reproduzível (script, não ação manual). O `db` não é acessado por `app`, `provider-fake` ou `edge` — é exclusivo do `gateway`.

## Evidência

```bash
docker compose config | grep -A5 "^  db:"
docker compose exec gateway curl -s http://localhost:4000/health/readiness
```

`docker compose ps db` mostra o serviço `healthy`; reiniciar só o `gateway` (`docker compose restart gateway`) preserva as chaves e o orçamento já consumido (verificável com `GET /key/info` logo após o restart).
