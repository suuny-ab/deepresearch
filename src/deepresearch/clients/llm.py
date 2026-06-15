from typing import Protocol

from openai import OpenAI, OpenAIError

from deepresearch.errors import LLMError
from deepresearch.state import UsageInfo

# DeepSeek pricing (per 1M tokens, USD). Configurable via kwargs.
_DEFAULT_INPUT_COST = 0.55   # cache miss
_DEFAULT_OUTPUT_COST = 2.19


class LLMClient(Protocol):
    def complete(self, prompt: str) -> tuple[str, UsageInfo]:
        ...


def _estimate_cost(prompt_tokens: int, completion_tokens: int,
                   input_cost: float = _DEFAULT_INPUT_COST,
                   output_cost: float = _DEFAULT_OUTPUT_COST) -> float:
    return (prompt_tokens / 1_000_000) * input_cost + (completion_tokens / 1_000_000) * output_cost


class DeepSeekLLMClient:
    def __init__(self, api_key: str, base_url: str, model: str,
                 input_cost_per_1m: float = _DEFAULT_INPUT_COST,
                 output_cost_per_1m: float = _DEFAULT_OUTPUT_COST):
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._input_cost = input_cost_per_1m
        self._output_cost = output_cost_per_1m

    def complete(self, prompt: str) -> tuple[str, UsageInfo]:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.choices[0].message.content
            if not content:
                raise LLMError("LLM returned empty content")
            usage = response.usage
            if usage:
                usage_info = UsageInfo(
                    prompt_tokens=usage.prompt_tokens or 0,
                    completion_tokens=usage.completion_tokens or 0,
                    estimated_cost=_estimate_cost(
                        usage.prompt_tokens or 0, usage.completion_tokens or 0,
                        self._input_cost, self._output_cost,
                    ),
                )
            else:
                usage_info = UsageInfo()
            return content, usage_info
        except (OpenAIError, IndexError, AttributeError) as exc:
            raise LLMError(str(exc)) from exc
