from typing import Protocol

from openai import OpenAI, OpenAIError

from deepresearch.errors import LLMError


class LLMClient(Protocol):
    def complete(self, prompt: str) -> str:
        ...


class DeepSeekLLMClient:
    def __init__(self, api_key: str, base_url: str, model: str):
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def complete(self, prompt: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.choices[0].message.content
            if not content:
                raise LLMError("LLM returned empty content")
            return content
        except (OpenAIError, IndexError, AttributeError) as exc:
            raise LLMError(str(exc)) from exc
