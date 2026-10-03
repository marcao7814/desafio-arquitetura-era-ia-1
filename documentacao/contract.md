# Contrato do Helpdesk

> Derivado de [solicitacao.md](./solicitacao.md) — seções "O contrato do helpdesk" e "Contratos sugeridos".

## Topologia

- **Borda (`edge`)**: porta de entrada oficial, `http://localhost:8000`. Encaminha tudo para `app:8080`. Timeout de 30s sem bytes enviados → `504`.
- **Aplicação (`app`)**: escuta em `8080` dentro do compose.
- Todo cliente (avaliador, testes, curl) fala com o sistema **sempre pela borda** (`localhost:8000`).

## Health check

```
GET /health
200 OK
```

## F1 — Classificar ticket

- **Rota:** `POST /tickets/classification`
- **Entrada:** `{"ticket_id": string, "text": string}`
- **Saída (síncrono):** `{"ticket_id": string, "category": string, "priority": string}`
- **Características de negócio:** roda na abertura do ticket, cliente esperando confirmação na tela. Saída curta, valores fixos.
- **Orçamento de latência:** resultado completo em até **3 s** (pela borda, provider em modo normal).
- **Resiliência:** timeout explícito; nunca pendurada quando o provider trava — responde com sucesso (via fallback) ou erro explícito em até **15 s**.

```
POST /tickets/classification
{"ticket_id": "TK-00042", "text": "Meu pedido #481516 não chegou e já passou do prazo, urgente"}

200 OK
{"ticket_id": "TK-00042", "category": "delivery", "priority": "high"}
```

## F2 — Sugerir resposta

- **Rota:** `POST /tickets/reply-suggestion`
- **Entrada:** `{"ticket_id": string, "text": string}`
- **Saída (síncrono):** `{"ticket_id": string, "suggestion": string}`
- **Características de negócio:** atendente olhando a tela, lê/edita assim que o texto aparece. Saída longa.
- **Orçamento de latência:** primeiro trecho em até **1,5 s**; texto continua chegando até completar; primeiro trecho chega antes da metade do tempo total da resposta.
- **Se usar streaming:**
  - `Content-Type: text/event-stream`
  - erro no meio do stream chega como evento `error` dentro do próprio stream (status 200 já foi enviado)

```
POST /tickets/reply-suggestion
{"ticket_id": "TK-00042", "text": "Meu pedido #481516 não chegou e já passou do prazo, urgente"}

200 OK
Content-Type: text/event-stream

data: {"chunk": "Olá! Sinto muito pelo atraso"}
data: {"chunk": " na entrega do seu pedido"}
...
event: end
data: {"ticket_id": "TK-00042"}
```

Falha no meio do stream (status 200 já enviado; stream termina logo após o evento):

```
data: {"chunk": "Olá! Sinto muito pelo atraso"}
...
event: error
data: {"ticket_id": "TK-00042", "message": "A geração foi interrompida"}
```

## F3 — Relatório de temas

- **Rota:** `POST /reports/topics`
- **Entrada:** `{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}`
- **Saída:** `{"start", "end", "total_tickets", "topics": [{"topic", "count", "examples": [ids]}]}`
- **Características de negócio:** lê `data/tickets.jsonl` do período (mês inteiro = 5.000 tickets). Quem pede é um painel interno sem callback; ninguém espera olhando.
- **Orçamento de latência:** aceita o pedido do mês inteiro (`2026-08-01` a `2026-08-31`) respondendo em até **1 s**; relatório completo (5.000 tickets) disponível depois.
- **Falha total:** com os dois providers inteiros em `error_500`, chega a um estado de falha visível ao cliente, com motivo, em até **60 s**.
- **Se usar Asynchronous Request-Reply:**
  - `202 Accepted` com headers `Location` e `Retry-After`
  - URL de status responde `200` com `state` (`pending` | `running` | `failed` com motivo) enquanto não termina com sucesso
  - `303 See Other` apontando para o resultado quando chega a `done`
  - tarefa que não termina chega a `failed` em até **60 s**, nunca presa em `running`

```
POST /reports/topics
{"start": "2026-08-01", "end": "2026-08-31"}

202 Accepted
Location: /reports/topics/status/7f3a
Retry-After: 5

GET /reports/topics/status/7f3a
200 OK   {"state": "running", "progress": "1800/5000"}

GET /reports/topics/status/7f3a
303 See Other
Location: /reports/topics/7f3a

GET /reports/topics/7f3a
200 OK   {"start": "2026-08-01", "end": "2026-08-31", "total_tickets": 5000, "topics": [...]}
```

## F4 — Extrair dados do pedido

- **Rota:** `POST /tickets/extraction`
- **Entrada:** `{"ticket_id": string, "text": string}`
- **Saída:** `{"ticket_id": string, "order_number": string|null, "product": string|null}`
- **Características de negócio:** alimenta automação de troca/devolução sem revisão humana. Campo errado gera troca errada (custa frete, estoque, cliente).

## Domínios de valores (todas as features)

| Campo | Valores permitidos |
|---|---|
| `category` | `delivery`, `payment`, `exchange_return`, `product_defect`, `other` |
| `priority` | `low`, `medium`, `high` |
| `order_number` | `#` + 6 dígitos, ou `null` quando o ticket não cita pedido |
| `product` | texto livre, ou `null` |

## Garantias globais

- Nenhuma requisição de nenhuma feature termina em `504` da borda, inclusive em cenários de falha do provider.
- Cada modo usado (síncrono, streaming, assíncrono) segue exatamente o contrato de referência acima — qualquer campo adicional precisa estar documentado no README da entrega.
- O modo de execução de cada feature é uma decisão de arquitetura (ver [plan.md](./plan.md) e ADR de execução), não está fixado por este contrato — o que é fixo é o *efeito observável* (os limites de tempo e o formato de cada modo).
