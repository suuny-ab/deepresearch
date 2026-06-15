import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

from deepresearch.errors import ConfigError


def _get_int_env(name: str, default: int) -> int:
    value = os.getenv(name, str(default))
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc


def _collect_tavily_keys() -> list[tuple[str, int]]:
    """Collect all Tavily API keys from environment variables.

    Reads TAVILY_API_KEY (primary) and TAVILY_API_KEY_2, TAVILY_API_KEY_3, etc.
    Each key can optionally have a _REMAINING env var or default to 500.
    """
    keys: list[tuple[str, int]] = []
    # Primary key
    primary = os.getenv("TAVILY_API_KEY")
    if primary:
        remaining = int(os.getenv("TAVILY_API_KEY_REMAINING", "500"))
        keys.append((primary, remaining))
    # Additional keys
    for i in range(2, 10):
        key = os.getenv(f"TAVILY_API_KEY_{i}")
        if not key:
            break
        remaining = int(os.getenv(f"TAVILY_API_KEY_{i}_REMAINING", "500"))
        keys.append((key, remaining))
    return keys


@dataclass(frozen=True)
class AppConfig:
    deepseek_api_key: str | None
    tavily_api_key: str | None  # kept for backward compat
    tavily_api_keys: list[tuple[str, int]] = field(default_factory=list)
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-pro"
    max_subquestions: int = 5
    results_per_query: int = 5
    output_dir: str = "reports"

    @classmethod
    def from_env(cls) -> "AppConfig":
        load_dotenv()
        return cls(
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY"),
            tavily_api_key=os.getenv("TAVILY_API_KEY"),
            tavily_api_keys=_collect_tavily_keys(),
            deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
            max_subquestions=_get_int_env("DEEPRESEARCH_MAX_SUBQUESTIONS", 5),
            results_per_query=_get_int_env("DEEPRESEARCH_SEARCH_RESULTS_PER_QUERY", 5),
            output_dir=os.getenv("DEEPRESEARCH_OUTPUT_DIR", "reports"),
        )

    def with_overrides(
        self,
        *,
        max_subquestions: int | None = None,
        results_per_query: int | None = None,
        output_dir: str | None = None,
        model: str | None = None,
    ) -> "AppConfig":
        return AppConfig(
            deepseek_api_key=self.deepseek_api_key,
            tavily_api_key=self.tavily_api_key,
            tavily_api_keys=self.tavily_api_keys,
            deepseek_base_url=self.deepseek_base_url,
            deepseek_model=self.deepseek_model if model is None else model,
            max_subquestions=self.max_subquestions if max_subquestions is None else max_subquestions,
            results_per_query=self.results_per_query if results_per_query is None else results_per_query,
            output_dir=self.output_dir if output_dir is None else output_dir,
        )

    def validate_required(self) -> None:
        if not self.deepseek_api_key:
            raise ConfigError("DEEPSEEK_API_KEY is not set. Copy .env.example to .env and fill it in.")
        if not self.tavily_api_keys and not self.tavily_api_key:
            raise ConfigError("TAVILY_API_KEY is not set. Copy .env.example to .env and fill it in.")
        if self.max_subquestions < 1:
            raise ConfigError("DEEPRESEARCH_MAX_SUBQUESTIONS / --max-subquestions must be at least 1")
        if self.results_per_query < 1:
            raise ConfigError("DEEPRESEARCH_SEARCH_RESULTS_PER_QUERY / --results-per-query must be at least 1")
