import threading

from deepresearch.state import UsageInfo


class FakeLLMClient:
    def __init__(self, responses: list[str], usages: list[UsageInfo] | None = None):
        self.responses = list(responses)
        self.usages = list(usages) if usages else [UsageInfo()] * len(responses)
        self.prompts: list[str] = []
        self._lock = threading.Lock()

    def complete(self, prompt: str) -> tuple[str, UsageInfo]:
        with self._lock:
            self.prompts.append(prompt)
            if not self.responses:
                raise AssertionError("No fake LLM response configured")
            usage = self.usages.pop(0) if self.usages else UsageInfo()
            return self.responses.pop(0), usage
