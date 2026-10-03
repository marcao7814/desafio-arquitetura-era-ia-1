"""Único componente de app/ que fala com o AI Gateway.

Restrição estrutural (documentacao/specs.md, R3): nenhum componente de feature
importa este módulo. Só o composition root (app/helpdesk/main.py) o importa,
para construir a instância e injetá-la nas features via `ports.CompletionGateway`.
"""
from openai import OpenAI


class LiteLLMGateway:
    def __init__(self, base_url: str, api_key: str, max_tokens: int):
        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self._max_tokens = max_tokens

    def complete(self, capability: str, task: str, content: str) -> str:
        response = self._client.chat.completions.create(
            model=capability,
            max_tokens=self._max_tokens,
            messages=[{"role": "user", "content": f"TASK: {task}\n{content}"}],
        )
        return response.choices[0].message.content
