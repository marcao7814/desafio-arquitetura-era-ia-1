# 0008. Política de providers aceitos e teto de gasto mensal com IA

- Status: aceita
- Data: 2026-10-02
- Nível: corporativa

## Contexto

Na `v1-coupled`, a empresa usava OpenAI e Anthropic lado a lado sem critério declarado ("funcionou melhor no teste"), sem teto de gasto e sem responsável único pela decisão de qual provider é aceitável para processar texto de clientes. Essa é uma decisão de nível corporativo: qual problema resolver (reduzir risco de fornecedor único e descontrole de custo), não como resolver.

## Opções consideradas

1. Não restringir — cada feature escolhe o provider que quiser, sem teto de gasto.
2. Lista fechada de providers aceitos (OpenAI, Anthropic) + teto de gasto mensal, aplicado na infraestrutura (gateway), não no código de cada feature.
3. Provider único para toda a empresa — descartado: elimina o fallback técnico entre providers exigido pelo requisito 5, trocando risco de custo por risco de disponibilidade.

## Decisão

Opção 2. A lista de providers aceitos é a mesma usada tecnicamente no gateway (OpenAI e Anthropic, via `provider-fake` neste desafio). O teto de gasto é aplicado como orçamento (budget) de virtual key no gateway (ver [0003-governanca-chaves.md](0003-governanca-chaves.md)), não como um limite verificado manualmente. A escolha de qual provider físico atende cada chamada deixa de ser decisão de cada feature e passa a ser decisão de infraestrutura (ver [0006-posicao-e-escolha-do-gateway.md](0006-posicao-e-escolha-do-gateway.md) e [0007-capacidades-logicas.md](0007-capacidades-logicas.md)), revisável sem envolver código.

## Consequências

Nenhuma feature pode decidir sozinha usar um provider fora da lista aceita. Todo aumento de orçamento é uma mudança de configuração no gateway, auditável e reversível. Negociação comercial fica restrita a um número fechado de providers.

## Evidência

Roteiro de governança do [README.md](../../README.md#roteiro-de-governança): uma chamada acima do orçamento configurado é recusada pelo gateway (`429 budget_exceeded`) antes de chegar ao provider.
