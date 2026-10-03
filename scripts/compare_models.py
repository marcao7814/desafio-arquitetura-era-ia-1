"""Evidência do ADR-002 (fallback com modelo fraco): compara large vs mini
nas 4 tarefas do provider-fake, chamando-o direto (sem passar pelo gateway).

Pré-requisito: `docker compose up -d --wait provider-fake` (ou o compose
inteiro) na raiz do repo, e `pip install openai anthropic` no ambiente que
roda este script.

Uso (a partir da raiz do repo): python scripts/compare_models.py
"""
import json

from openai import OpenAI
from anthropic import Anthropic

oai = OpenAI(base_url="http://localhost:8090/openai/v1", api_key="sk-fake-openai-0001", max_retries=0)
ant = Anthropic(base_url="http://localhost:8090/anthropic", api_key="sk-ant-fake-0001", max_retries=0)


def classify(model, text):
    r = oai.chat.completions.create(model=model, messages=[{"role": "user", "content": f"TASK: classify\n{text}"}])
    return r.choices[0].message.content


def extract(model, text):
    r = oai.chat.completions.create(model=model, messages=[{"role": "user", "content": f"TASK: extract\n{text}"}])
    return r.choices[0].message.content


def suggest(model, text):
    r = ant.messages.create(model=model, max_tokens=2000, messages=[{"role": "user", "content": f"TASK: suggest\n{text}"}])
    return r.content[0].text


def topics(model, content):
    r = ant.messages.create(model=model, max_tokens=2000, messages=[{"role": "user", "content": f"TASK: topics\n{content}"}])
    return r.content[0].text


CLASSIFY_TICKETS = [
    ("TK-00001 (rastreio)", "O código de rastreio do pedido não mostra nenhuma atualização. Aguardo retorno."),
    ("TK-00003 (loja física)", "Vocês têm loja física na minha cidade? Referente ao pedido #117367."),
    ("TK-00004 (cupom)", "O cupom de desconto não foi aplicado na minha compra. Referente ao pedido nº 732789."),
    ("TK-00005 (extraviado)", "O rastreio diz que o pedido foi extraviado no centro de distribuição."),
]

EXTRACT_TICKETS = [
    ("TK-00002 (produto+pedido)", "Tenho aqui a nota fiscal 530720. O produto veio quebrado na caixa, pedido #605065."),
    ("mouse sem fio", "Tenho aqui a nota fiscal 530720. O mouse sem fio veio quebrado na caixa, pedido #605065."),
    ("sem pedido", "Vocês têm loja física na minha cidade?"),
]

SUGGEST_TICKETS = [
    ("TK-00005 (extraviado)", "O rastreio diz que o pedido foi extraviado no centro de distribuição."),
    ("TK-00002 (quebrado)", "Tenho aqui a nota fiscal 530720. O produto veio quebrado na caixa, pedido #605065."),
]


def main():
    print("=" * 70)
    print("CLASSIFY — gpt-fake-large vs gpt-fake-mini")
    print("=" * 70)
    diffs = 0
    for label, text in CLASSIFY_TICKETS:
        large, mini = classify("gpt-fake-large", text), classify("gpt-fake-mini", text)
        same = large == mini
        diffs += not same
        print(f"\n[{label}] igual={same}\n  large: {large}\n  mini:  {mini}")
    print(f"\n>>> CLASSIFY: {diffs}/{len(CLASSIFY_TICKETS)} divergências")

    print("\n" + "=" * 70)
    print("EXTRACT — gpt-fake-large vs gpt-fake-mini")
    print("=" * 70)
    diffs = 0
    for label, text in EXTRACT_TICKETS:
        large, mini = extract("gpt-fake-large", text), extract("gpt-fake-mini", text)
        same = large == mini
        diffs += not same
        print(f"\n[{label}] igual={same}\n  large: {large}\n  mini:  {mini}")
    print(f"\n>>> EXTRACT: {diffs}/{len(EXTRACT_TICKETS)} divergências")

    print("\n" + "=" * 70)
    print("SUGGEST — claude-fake-large vs claude-fake-mini")
    print("=" * 70)
    diffs = 0
    for label, text in SUGGEST_TICKETS:
        large, mini = suggest("claude-fake-large", text), suggest("claude-fake-mini", text)
        same = large == mini
        diffs += not same
        print(f"\n[{label}] igual={same}\n  large ({len(large)} chars): {large[:200]}...\n  mini  ({len(mini)} chars): {mini[:200]}...")
    print(f"\n>>> SUGGEST: {diffs}/{len(SUGGEST_TICKETS)} divergências")

    print("\n" + "=" * 70)
    print("TOPICS — claude-fake-large vs claude-fake-mini (dia 2026-08-01, 137 tickets)")
    print("=" * 70)
    lines = []
    with open("data/tickets.jsonl", encoding="utf-8") as f:
        for line in f:
            t = json.loads(line)
            if t["created_at"].startswith("2026-08-01"):
                lines.append(f"[{t['id']}] {t['text']}")
    content = "\n".join(lines)

    large_json = json.loads(topics("claude-fake-large", content))
    mini_json = json.loads(topics("claude-fake-mini", content))
    large_topics = {t["topic"]: t["count"] for t in large_json["topics"]}
    mini_topics = {t["topic"]: t["count"] for t in mini_json["topics"]}
    print(f"large: {len(large_topics)} temas, total classificado = {sum(large_topics.values())}")
    print(f"mini:  {len(mini_topics)} temas, total classificado = {sum(mini_topics.values())}")
    print(f"temas só no large: {set(large_topics) - set(mini_topics)}")
    print(f"temas só no mini: {set(mini_topics) - set(large_topics)}")
    common = set(large_topics) & set(mini_topics)
    print(f"temas em comum com contagem diferente: "
          f"{ {k: (large_topics[k], mini_topics[k]) for k in common if large_topics[k] != mini_topics[k]} }")


if __name__ == "__main__":
    main()
