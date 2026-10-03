# 0007. Capacidades lógicas e mapeamento para modelos físicos

- Status: aceita
- Data: 2026-10-02
- Nível: software

## Contexto

O requisito 5 exige que `app/` só conheça nomes lógicos de capacidade — nenhum nome de modelo físico (`gpt-fake-*`, `claude-fake-*`) pode aparecer em `app/`. É preciso decidir a granularidade dessas capacidades.

## Opções consideradas

1. Uma capacidade lógica por feature (`classification`, `reply-suggestion`, `topics-report`, `extraction`).
2. Uma capacidade lógica por tarefa do provider simulado (`classify`, `suggest`, `topics`, `extract`), no padrão `helpdesk-<tarefa>`.
3. Uma capacidade genérica única para tudo — descartada, impede decisão de fallback por feature (requisito 5/ADR de fallback).

## Decisão

Opção 2. Quatro capacidades: `helpdesk-classify`, `helpdesk-suggest`, `helpdesk-topics`, `helpdesk-extract` — definidas em `app/helpdesk/config.py` (`CLASSIFICATION_CAPABILITY` etc.) e mapeadas em `gateway/config.yaml`. Cada capacidade tem um destino primário (`large`), um fallback técnico (mesma capacidade, outro provider) e, quando o [ADR de fallback](0002-resiliencia-e-fallback.md) aceita, um fallback com modelo fraco.

## Consequências

O nome da capacidade já comunica a tarefa (facilita ler `gateway/config.yaml` e `/admin/calls`). Trocar o modelo físico por trás de uma capacidade é só editar `gateway/config.yaml` e reiniciar o `gateway` — `app/` nunca muda para isso (ver seção "Troca de modelo" do README).

## Evidência

```bash
grep -rE "gpt-fake|claude-fake" app/   # vazio
```

Tabela de capacidades completa no [README.md](../../README.md#tabela-de-capacidades).
