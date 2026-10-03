"""Único componente de app/ que fala com o AI Gateway.

Restrição estrutural (documentacao/specs.md, R3): nenhum componente de feature
importa este módulo. Só o composition root (app/helpdesk/main.py) o importa,
para construir a instância e injetá-la nas features via `ports.CompletionGateway`.
"""
from collections.abc import Iterator

from openai import OpenAI

from .. import config


class LiteLLMGateway:
    def __init__(self):
        # max_retries=0: quem decide retry é o gateway (timeout/retry/fallback
        # já configurados em gateway/config.yaml). Retry também aqui duplicaria
        # tentativas (fricção descrita em documentacao/plan.md). timeout=30:
        # teto de segurança para a thread não ficar presa indefinidamente
        # mesmo se o gateway esgotar toda a cadeia de fallback; o teto de
        # negócio por feature (15s síncrono) é aplicado em main.py.
        self._client = OpenAI(
            base_url=config.GATEWAY_BASE_URL,
            api_key=config.GATEWAY_API_KEY,
            max_retries=0,
            timeout=30,
        )
        self._max_tokens = config.MAX_OUTPUT_TOKENS

    def complete(self, capability: str, task: str, content: str) -> str:
        response = self._client.chat.completions.create(
            model=capability,
            max_tokens=self._max_tokens,
            messages=[{"role": "user", "content": f"TASK: {task}\n{content}"}],
        )
        return response.choices[0].message.content

    def stream(self, capability: str, task: str, content: str) -> Iterator[str]:
        response = self._client.chat.completions.create(
            model=capability,
            max_tokens=self._max_tokens,
            messages=[{"role": "user", "content": f"TASK: {task}\n{content}"}],
            stream=True,
        )
        for chunk in response:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta
